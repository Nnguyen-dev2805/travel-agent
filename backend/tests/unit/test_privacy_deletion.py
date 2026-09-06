"""Unit tests for R9 privacy deletion orchestration.

The deletion service is exercised with in-memory fakes for the workspace,
conversation, and memory repositories. Fakes mirror production row types
with governed enums. Planner hiding is state-derived and needs no
transitions. Retrieval exclusion is proven through the real memory
retrieval service over a fake record store. No test touches a real
database, a model provider, Chroma, or the network.
"""

from datetime import datetime, timezone

import pytest

from backend.conversations.models import ConversationRetentionState
from backend.conversations.service import WorkspaceNotFoundError
from backend.memory.models import (
    MemoryRecordScope,
    MemoryRecordStatus,
    MemoryRecordType,
    MemoryRecord,
    SensitivityLabel,
    generate_memory_record_id,
)
from backend.memory.retrieval import MemoryRetrievalService
from backend.planner.models import (
    ItineraryStatus,
    ItineraryVersionDraft,
)
from backend.planner.service import PlannerService
from backend.privacy.deletion import (
    DeletionConflictError,
    DeletionResult,
    DeletionService,
    PrivacyServiceError,
)
from backend.workspaces.models import RetentionState

MOMENT = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)


class FakeWorkspaceRepository:
    def __init__(self, states=None):
        self.states = dict(states or {})

    def get(self, workspace_id):
        if workspace_id not in self.states:
            return None
        from types import SimpleNamespace

        return SimpleNamespace(
            workspace_id=workspace_id,
            owner_user_id="owner_a",
            retention_state=self.states[workspace_id],
        )

    def update_retention_state(self, workspace_id, state):
        if workspace_id not in self.states:
            return None
        self.states[workspace_id] = state
        return self.get(workspace_id)


class FakeConversationRepository:
    def __init__(self, records=()):
        # records: list of [workspace_id, ConversationRetentionState]
        self.records = [list(item) for item in records]
        self.fail_on_transition = False

    def list_by_workspace(self, workspace_id):
        from types import SimpleNamespace

        return tuple(
            SimpleNamespace(
                conversation_id=f"cv_{index}",
                workspace_id=item[0],
                retention_state=item[1],
            )
            for index, item in enumerate(self.records)
            if item[0] == workspace_id
        )

    def transition_workspace_conversations(self, workspace_id, to_state):
        if self.fail_on_transition:
            raise RuntimeError("conversation store unavailable")
        count = 0
        for item in self.records:
            if (
                item[0] == workspace_id
                and item[1]
                in (
                    ConversationRetentionState.ACTIVE,
                    ConversationRetentionState.DELETION_REQUESTED,
                )
                and item[1] is not to_state
            ):
                item[1] = to_state
                count += 1
        return count


class FakeMemoryRepository:
    def __init__(self, records=()):
        self.records = list(records)
        self.fail_on_transition = False

    def list_records(self, workspace_id=None, **filters):
        return tuple(
            item
            for item in self.records
            if workspace_id is None or item.workspace_id == workspace_id
        )

    def transition_workspace_records(self, workspace_id, to_state):
        import dataclasses

        if self.fail_on_transition:
            raise RuntimeError("memory store unavailable")
        count = 0
        for index, item in enumerate(self.records):
            if (
                item.workspace_id == workspace_id
                and item.status
                in (
                    MemoryRecordStatus.ACTIVE,
                    MemoryRecordStatus.DELETION_REQUESTED,
                )
                and item.status is not to_state
            ):
                self.records[index] = dataclasses.replace(item, status=to_state)
                count += 1
        return count


class FakeRecordStore:
    def __init__(self, records):
        self._records = tuple(records)

    def list_records(self, owner_user_id=None, status=None, **filters):
        return tuple(
            item for item in self._records if status is None or item.status is status
        )


def _service(workspaces=None, conversations=(), memory=()):
    repos = (
        FakeWorkspaceRepository(workspaces),
        FakeConversationRepository(conversations),
        FakeMemoryRepository(memory),
    )
    return DeletionService(*repos), repos


def _memory_record(status, workspace_id="tw_a"):
    return MemoryRecord(
        memory_id=generate_memory_record_id(),
        source_candidate_id="mc_probe",
        workspace_id=workspace_id,
        conversation_id="cv_probe",
        source_message_id="ms_probe",
        source_sequence=1,
        owner_user_id="owner_a",
        scope=MemoryRecordScope.USER,
        scope_id="owner_a",
        memory_type=MemoryRecordType.PREFERENCE,
        status=status,
        text="Người dùng ăn chay trường.",
        confidence=0.8,
        sensitivity_label=SensitivityLabel.NONE,
        supersedes_memory_id=None,
        created_at=MOMENT,
        updated_at=MOMENT,
        expires_at=None,
    )


def test_request_moves_workspace_and_children_to_requested():
    service, (workspaces, conversations, memory) = _service(
        workspaces={"tw_a": RetentionState.ACTIVE},
        conversations=[
            ["tw_a", ConversationRetentionState.ACTIVE],
            ["tw_a", ConversationRetentionState.ACTIVE],
        ],
        memory=[
            _memory_record(MemoryRecordStatus.ACTIVE),
            _memory_record(MemoryRecordStatus.ACTIVE),
            _memory_record(MemoryRecordStatus.SUPERSEDED),
        ],
    )

    result = service.request_workspace_deletion("tw_a")

    assert isinstance(result, DeletionResult)
    assert result.workspace_state == "deletion_requested"
    assert result.conversations_updated == 2
    assert result.memory_updated == 2
    assert workspaces.states["tw_a"] is RetentionState.DELETION_REQUESTED
    # Inactive records keep their lifecycle states.
    assert memory.records[2].status is MemoryRecordStatus.SUPERSEDED


def test_request_is_idempotent_and_missing_is_not_found():
    service, _ = _service(workspaces={"tw_a": RetentionState.DELETED})

    result = service.request_workspace_deletion("tw_a")

    assert result.workspace_state == "deleted"
    assert result.conversations_updated == 0
    with pytest.raises(WorkspaceNotFoundError):
        service.request_workspace_deletion("tw_missing")


def test_confirm_requires_request_first():
    service, _ = _service(workspaces={"tw_a": RetentionState.ACTIVE})

    with pytest.raises(DeletionConflictError):
        service.confirm_workspace_deletion("tw_a")


def test_confirm_moves_requested_children_to_deleted():
    service, (workspaces, conversations, memory) = _service(
        workspaces={"tw_a": RetentionState.ACTIVE},
        conversations=[["tw_a", ConversationRetentionState.ACTIVE]],
        memory=[_memory_record(MemoryRecordStatus.ACTIVE)],
    )
    service.request_workspace_deletion("tw_a")

    result = service.confirm_workspace_deletion("tw_a")

    assert result.workspace_state == "deleted"
    assert workspaces.states["tw_a"] is RetentionState.DELETED
    assert conversations.records == [["tw_a", ConversationRetentionState.DELETED]]
    assert [item.status for item in memory.records] == [MemoryRecordStatus.DELETED]


def test_confirm_deleted_is_idempotent_success():
    service, _ = _service(workspaces={"tw_a": RetentionState.DELETED})

    result = service.confirm_workspace_deletion("tw_a")

    assert result.workspace_state == "deleted"


def test_child_failure_leaves_barrier_and_propagates():
    service, (workspaces, conversations, memory) = _service(
        workspaces={"tw_a": RetentionState.ACTIVE},
        conversations=[["tw_a", ConversationRetentionState.ACTIVE]],
        memory=[_memory_record(MemoryRecordStatus.ACTIVE)],
    )
    memory.fail_on_transition = True

    with pytest.raises(PrivacyServiceError):
        service.request_workspace_deletion("tw_a")

    assert workspaces.states["tw_a"] is RetentionState.DELETION_REQUESTED
    assert conversations.records == [
        ["tw_a", ConversationRetentionState.DELETION_REQUESTED]
    ]
    assert [item.status for item in memory.records] == [MemoryRecordStatus.ACTIVE]


def test_retry_after_partial_failure_completes():
    service, (workspaces, conversations, memory) = _service(
        workspaces={"tw_a": RetentionState.ACTIVE},
        conversations=[["tw_a", ConversationRetentionState.ACTIVE]],
        memory=[_memory_record(MemoryRecordStatus.ACTIVE)],
    )
    memory.fail_on_transition = True
    with pytest.raises(PrivacyServiceError):
        service.request_workspace_deletion("tw_a")
    memory.fail_on_transition = False

    service.request_workspace_deletion("tw_a")
    result = service.confirm_workspace_deletion("tw_a")

    assert result.workspace_state == "deleted"
    assert [item.status for item in memory.records] == [MemoryRecordStatus.DELETED]


def test_deleted_and_requested_memory_never_selected():
    records = [
        _memory_record(MemoryRecordStatus.ACTIVE),
        _memory_record(MemoryRecordStatus.DELETION_REQUESTED),
        _memory_record(MemoryRecordStatus.DELETED),
    ]
    retrieval = MemoryRetrievalService(FakeRecordStore(records))

    selected = retrieval.select_memories(
        owner_user_id="owner_a",
        workspace_id="tw_a",
        conversation_id="cv_probe",
        query="ăn chay",
    )

    assert [item.memory_id for item in selected] == [records[0].memory_id]


def test_planner_service_denies_deleted_workspace():
    class _DeadWorkspaces:
        def get(self, workspace_id):
            from types import SimpleNamespace

            return SimpleNamespace(
                workspace_id=workspace_id,
                owner_user_id="owner_a",
                retention_state=RetentionState.DELETED,
            )

    planner = PlannerService(
        planner_repository=None,
        workspace_repository=_DeadWorkspaces(),
        conversation_repository=None,
    )

    with pytest.raises(WorkspaceNotFoundError):
        planner.list_itinerary_versions("tw_a")
    with pytest.raises(WorkspaceNotFoundError):
        planner.create_itinerary_version(
            "tw_a",
            ItineraryVersionDraft(workspace_id="tw_a", status=ItineraryStatus.DRAFT),
        )
