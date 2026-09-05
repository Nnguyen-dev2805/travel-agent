"""Unit tests for the R7 planner service.

The service is exercised with in-memory fakes for the planner, workspace,
and conversation repositories. Lifecycle decisions, scope validation, and
operation evidence live here; SQL lives in the SQLite adapter. No test
touches a real database, a model provider, Chroma, RAG, memory, or the
network.
"""

from datetime import datetime, timezone

import pytest

from backend.conversations.models import Conversation
from backend.conversations.service import (
    ConversationNotFoundError,
    WorkspaceNotFoundError,
)
from backend.planner.models import (
    DecisionStatus,
    DecisionType,
    ItineraryItem,
    ItineraryItemType,
    ItineraryStatus,
    ItineraryVersion,
    ItineraryVersionDraft,
    PlannerOperationType,
    TripDecision,
    generate_decision_id,
)
from backend.planner.repository import PlannerNotFoundError, PlannerStorageError
from backend.planner.service import (
    PlannerConflictError,
    PlannerScopeMismatchError,
    PlannerService,
)
from backend.workspaces.models import TripWorkspace

MOMENT = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


class FakeWorkspaceRepository:
    def __init__(self, workspaces=()):
        self._workspaces = {item.workspace_id: item for item in workspaces}

    def get(self, workspace_id):
        return self._workspaces.get(workspace_id)


class FakeConversationRepository:
    def __init__(self, conversations=()):
        self._conversations = {item.conversation_id: item for item in conversations}

    def get(self, conversation_id):
        return self._conversations.get(conversation_id)


class FakePlannerRepository:
    """In-memory planner store mirroring the repository protocol.

    Writes apply state and operation evidence together: when the
    operation store is set to fail, nothing is stored, mirroring the
    atomic repository transaction.
    """

    def __init__(self, fail_operations=False):
        self.versions = {}
        self.decisions = {}
        self.operations = []
        self.fail_operations = fail_operations

    def _store_operation(self, operation):
        if operation is None:
            return
        if self.fail_operations:
            raise PlannerStorageError("operation store unavailable")
        self.operations.append(operation)

    def create_itinerary_version(self, draft, itinerary_version_id, operation=None):
        numbers = [
            item.version_number
            for item in self.versions.values()
            if item.workspace_id == draft.workspace_id
        ]
        stored = ItineraryVersion(
            itinerary_version_id=itinerary_version_id,
            workspace_id=draft.workspace_id,
            version_number=(max(numbers) + 1) if numbers else 1,
            status=draft.status,
            title=draft.title,
            summary=draft.summary,
            items=draft.items,
            created_from_operation_id=draft.created_from_operation_id,
            created_from_message_id=draft.created_from_message_id,
            created_at=draft.created_at,
        )
        self._store_operation(operation)
        self.versions[stored.itinerary_version_id] = stored
        return stored

    def get_itinerary_version(self, workspace_id, itinerary_version_id):
        version = self.versions.get(itinerary_version_id)
        if version is None or version.workspace_id != workspace_id:
            raise PlannerNotFoundError("missing")
        return version

    def list_itinerary_versions(self, workspace_id, status=None):
        return tuple(
            item
            for item in sorted(
                self.versions.values(),
                key=lambda item: item.version_number,
                reverse=True,
            )
            if item.workspace_id == workspace_id
            and (status is None or item.status is status)
        )

    def accept_itinerary_version(
        self, workspace_id, itinerary_version_id, operation=None
    ):
        import dataclasses

        target = self.get_itinerary_version(workspace_id, itinerary_version_id)
        if target.status is ItineraryStatus.ACCEPTED:
            return target
        flipped = [
            (key, dataclasses.replace(item, status=ItineraryStatus.SUPERSEDED))
            for key, item in self.versions.items()
            if item.workspace_id == workspace_id
            and item.status is ItineraryStatus.ACCEPTED
        ]
        accepted = dataclasses.replace(target, status=ItineraryStatus.ACCEPTED)
        self._store_operation(operation)
        for key, item in flipped:
            self.versions[key] = item
        self.versions[target.itinerary_version_id] = accepted
        return accepted

    def update_itinerary_status(
        self, workspace_id, itinerary_version_id, status, operation=None
    ):
        import dataclasses

        target = self.get_itinerary_version(workspace_id, itinerary_version_id)
        updated = dataclasses.replace(target, status=status)
        self._store_operation(operation)
        self.versions[target.itinerary_version_id] = updated
        return updated

    def create_decision(self, decision, operation=None):
        import dataclasses

        superseded = None
        if decision.supersedes_decision_id is not None:
            target = self.decisions.get(decision.supersedes_decision_id)
            if target is None or target.workspace_id != decision.workspace_id:
                raise PlannerNotFoundError("missing target")
            superseded = dataclasses.replace(target, status=DecisionStatus.SUPERSEDED)
        self._store_operation(operation)
        if superseded is not None:
            self.decisions[superseded.decision_id] = superseded
        self.decisions[decision.decision_id] = decision
        return decision

    def get_decision(self, workspace_id, decision_id):
        decision = self.decisions.get(decision_id)
        if decision is None or decision.workspace_id != workspace_id:
            raise PlannerNotFoundError("missing")
        return decision

    def list_decisions(self, workspace_id, status=None, decision_type=None):
        return tuple(
            item
            for item in self.decisions.values()
            if item.workspace_id == workspace_id
            and (status is None or item.status is status)
            and (decision_type is None or item.decision_type is decision_type)
        )

    def update_decision_status(self, workspace_id, decision_id, status, operation=None):
        import dataclasses

        target = self.get_decision(workspace_id, decision_id)
        updated = dataclasses.replace(target, status=status)
        self._store_operation(operation)
        self.decisions[target.decision_id] = updated
        return updated

    def create_operation(self, operation):
        self.operations.append(operation)
        return operation

    def list_operations(self, workspace_id):
        return tuple(
            item for item in self.operations if item.workspace_id == workspace_id
        )


def _workspace(workspace_id="tw_planner", **overrides):
    payload = {
        "workspace_id": workspace_id,
        "owner_user_id": "local-user",
        "title": "Da Nang trip",
        "destination_scope": "Da Nang",
        "date_window": None,
        "planning_status": "planning",
        "created_at": MOMENT,
        "updated_at": MOMENT,
    }
    payload.update(overrides)
    return TripWorkspace(**payload)


def _conversation(conversation_id="cv_planner", workspace_id="tw_planner"):
    return Conversation(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        title=None,
        created_at=MOMENT,
        updated_at=MOMENT,
    )


def _item(**overrides):
    payload = {
        "day_index": 1,
        "position": 1,
        "item_type": ItineraryItemType.MEAL,
        "title": "Bún chả Hương Liên",
        "location": None,
        "start_time": None,
        "end_time": None,
        "notes": None,
        "source_decision_ids": (),
    }
    payload.update(overrides)
    return ItineraryItem(**payload)


def _draft(**overrides):
    payload = {
        "workspace_id": "tw_planner",
        "status": ItineraryStatus.DRAFT,
        "title": "Hà Nội 3 ngày",
        "summary": None,
        "items": (_item(),),
        "created_from_operation_id": None,
        "created_from_message_id": None,
        "created_at": MOMENT,
    }
    payload.update(overrides)
    return ItineraryVersionDraft(**payload)


def _decision_draft(**overrides):
    payload = {
        "decision_id": generate_decision_id(),
        "workspace_id": "tw_planner",
        "decision_type": DecisionType.PREFERENCE,
        "status": DecisionStatus.PENDING,
        "statement": "Chuyến này ăn chay.",
        "rationale": None,
        "source_message_id": None,
        "supersedes_decision_id": None,
        "created_at": MOMENT,
        "updated_at": MOMENT,
    }
    payload.update(overrides)
    return TripDecision(**payload)


def _service(workspaces=None, conversations=(), fail_operations=False):
    planner = FakePlannerRepository(fail_operations=fail_operations)
    service = PlannerService(
        planner_repository=planner,
        workspace_repository=FakeWorkspaceRepository(
            workspaces if workspaces is not None else (_workspace(),)
        ),
        conversation_repository=FakeConversationRepository(conversations),
    )
    return service, planner


def test_failed_operation_leaves_no_state_behind():
    # The version and its operation commit together: when the operation
    # store fails, the service propagates the failure and no version,
    # decision, or flip survives.
    service, planner = _service(fail_operations=True)

    with pytest.raises(PlannerStorageError):
        service.create_itinerary_version("tw_planner", _draft())
    with pytest.raises(PlannerStorageError):
        service.record_decision("tw_planner", _decision_draft())

    assert planner.list_itinerary_versions("tw_planner") == ()
    assert planner.list_decisions("tw_planner") == ()
    assert planner.list_operations("tw_planner") == ()


def test_create_requires_existing_workspace():
    service, _ = _service(workspaces=())

    with pytest.raises(WorkspaceNotFoundError):
        service.create_itinerary_version("tw_missing", _draft())


def test_create_rejects_conversation_from_another_workspace():
    service, planner = _service(conversations=(_conversation(workspace_id="tw_other"),))

    with pytest.raises(PlannerScopeMismatchError):
        service.create_itinerary_version(
            "tw_planner", _draft(), conversation_id="cv_planner"
        )
    assert planner.list_operations("tw_planner") == ()


def test_create_assigns_next_version_and_logs_operation():
    service, planner = _service()
    first = service.create_itinerary_version("tw_planner", _draft())
    second = service.create_itinerary_version("tw_planner", _draft())

    assert (first.version_number, second.version_number) == (1, 2)
    operations = planner.list_operations("tw_planner")
    assert len(operations) == 2
    assert all(
        item.operation_type is PlannerOperationType.CREATE_ITINERARY
        for item in operations
    )
    assert operations[0].result_itinerary_version_id == first.itinerary_version_id


def test_create_rejects_non_draft_status_and_mismatched_workspace():
    service, planner = _service()

    with pytest.raises(PlannerConflictError):
        service.create_itinerary_version(
            "tw_planner", _draft(status=ItineraryStatus.ACCEPTED)
        )
    with pytest.raises(PlannerScopeMismatchError):
        service.create_itinerary_version("tw_planner", _draft(workspace_id="tw_other"))
    assert planner.list_operations("tw_planner") == ()


def test_accept_supersedes_prior_and_logs_operation():
    service, planner = _service()
    first = service.create_itinerary_version("tw_planner", _draft())
    second = service.create_itinerary_version("tw_planner", _draft())
    service.accept_itinerary_version("tw_planner", first.itinerary_version_id)

    accepted = service.accept_itinerary_version(
        "tw_planner", second.itinerary_version_id
    )

    assert accepted.status is ItineraryStatus.ACCEPTED
    assert (
        service.get_itinerary_version("tw_planner", first.itinerary_version_id).status
        is ItineraryStatus.SUPERSEDED
    )
    kinds = [item.operation_type for item in planner.list_operations("tw_planner")]
    assert kinds.count(PlannerOperationType.ACCEPT_ITINERARY) == 2


def test_accept_archived_or_missing_conflicts_without_operation():
    service, planner = _service()
    stored = service.create_itinerary_version("tw_planner", _draft())
    service.archive_itinerary_version("tw_planner", stored.itinerary_version_id)
    before = len(planner.list_operations("tw_planner"))

    with pytest.raises(PlannerConflictError):
        service.accept_itinerary_version("tw_planner", stored.itinerary_version_id)
    with pytest.raises(PlannerNotFoundError):
        service.accept_itinerary_version("tw_planner", "itv_missing")
    assert len(planner.list_operations("tw_planner")) == before


def test_archive_from_draft_logs_operation_but_accepted_conflicts():
    service, planner = _service()
    draft = service.create_itinerary_version("tw_planner", _draft())
    accepted_version = service.create_itinerary_version("tw_planner", _draft())
    service.accept_itinerary_version(
        "tw_planner", accepted_version.itinerary_version_id
    )

    archived = service.archive_itinerary_version(
        "tw_planner", draft.itinerary_version_id
    )
    assert archived.status is ItineraryStatus.ARCHIVED
    with pytest.raises(PlannerConflictError):
        service.archive_itinerary_version(
            "tw_planner", accepted_version.itinerary_version_id
        )


def test_record_decision_logs_operation_and_replacement_supersedes():
    service, planner = _service()
    old = service.record_decision("tw_planner", _decision_draft())
    replacement = service.record_decision(
        "tw_planner",
        _decision_draft(supersedes_decision_id=old.decision_id),
    )

    by_id = {item.decision_id: item for item in service.list_decisions("tw_planner")}
    assert by_id[old.decision_id].status is DecisionStatus.SUPERSEDED
    kinds = [item.operation_type for item in planner.list_operations("tw_planner")]
    assert kinds == [
        PlannerOperationType.RECORD_DECISION,
        PlannerOperationType.SUPERSEDE_DECISION,
    ]
    assert replacement.supersedes_decision_id == old.decision_id


def test_decision_status_lifecycle_and_no_direct_supersede():
    service, _ = _service()
    stored = service.record_decision("tw_planner", _decision_draft())

    accepted = service.update_decision_status(
        "tw_planner", stored.decision_id, DecisionStatus.ACCEPTED
    )
    assert accepted.status is DecisionStatus.ACCEPTED
    changed = service.update_decision_status(
        "tw_planner", stored.decision_id, DecisionStatus.CHANGED
    )
    assert changed.status is DecisionStatus.CHANGED

    with pytest.raises(PlannerConflictError):
        service.update_decision_status(
            "tw_planner", stored.decision_id, DecisionStatus.ACCEPTED
        )
    with pytest.raises(PlannerConflictError):
        service.update_decision_status(
            "tw_planner", stored.decision_id, DecisionStatus.SUPERSEDED
        )
    fresh = service.record_decision("tw_planner", _decision_draft())
    with pytest.raises(PlannerConflictError):
        service.update_decision_status(
            "tw_planner", fresh.decision_id, DecisionStatus.SUPERSEDED
        )


def test_lists_are_workspace_scoped():
    service, _ = _service(
        workspaces=(_workspace(), _workspace(workspace_id="tw_other"))
    )
    service.create_itinerary_version("tw_planner", _draft())
    service.create_itinerary_version("tw_other", _draft(workspace_id="tw_other"))
    service.record_decision("tw_planner", _decision_draft())

    assert len(service.list_itinerary_versions("tw_planner")) == 1
    assert len(service.list_itinerary_versions("tw_other")) == 1
    assert len(service.list_decisions("tw_planner")) == 1
    assert service.list_decisions("tw_other") == ()


def test_conversation_provenance_must_belong_to_workspace():
    service, _ = _service(conversations=(_conversation(),))

    with pytest.raises(ConversationNotFoundError):
        service.create_itinerary_version(
            "tw_planner", _draft(), conversation_id="cv_missing"
        )
