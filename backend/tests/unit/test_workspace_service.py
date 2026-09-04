"""Unit tests for the R3 workspace service use cases.

The service owns validation, identity generation, timestamping, and repository
calls. These tests use a fake repository so service behavior is reviewable
without SQLite, FastAPI, RAG, Chroma, a model provider, or the network.
"""

from datetime import date, timedelta, timezone

import pytest

from backend.workspaces.models import (
    WORKSPACE_ID_PREFIX,
    DateWindow,
    PlanningStatus,
    RetentionState,
    TripWorkspace,
    WorkspaceCreate,
    WorkspaceValidationError,
    generate_workspace_id,
)
from backend.workspaces.repository import (
    WorkspaceAlreadyExistsError,
    WorkspaceStorageError,
)
from backend.workspaces.service import WorkspaceService


class FakeWorkspaceRepository:
    """In-memory repository double recording every call."""

    def __init__(self) -> None:
        self.records: dict[str, TripWorkspace] = {}
        self.create_calls: list[TripWorkspace] = []
        self.get_calls: list[str] = []
        self.list_calls: list[str] = []
        self.collide_times = 0

    def create(self, workspace: TripWorkspace) -> TripWorkspace:
        self.create_calls.append(workspace)
        if self.collide_times > 0:
            self.collide_times -= 1
            raise WorkspaceAlreadyExistsError("duplicate workspace identity")
        self.records[workspace.workspace_id] = workspace
        return workspace

    def get(self, workspace_id: str) -> TripWorkspace | None:
        self.get_calls.append(workspace_id)
        return self.records.get(workspace_id)

    def list_by_owner(self, owner_user_id: str) -> tuple[TripWorkspace, ...]:
        self.list_calls.append(owner_user_id)
        return tuple(
            record
            for record in self.records.values()
            if record.owner_user_id == owner_user_id
        )


def _module_level_imports(module) -> set[str]:
    """Return every module name imported at module level by `module`."""
    import ast
    from pathlib import Path

    module_file = module.__file__
    assert module_file is not None
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.fixture
def repository() -> FakeWorkspaceRepository:
    return FakeWorkspaceRepository()


@pytest.fixture
def service(repository: FakeWorkspaceRepository) -> WorkspaceService:
    return WorkspaceService(repository=repository)


# 1. Invalid inputs fail before any repository write.


@pytest.mark.parametrize(
    "kwargs",
    [
        {"owner_user_id": "  ", "title": "Trip"},
        {"owner_user_id": "local-user", "title": "   "},
        {"owner_user_id": "local-user", "title": "t" * 121},
        {
            "owner_user_id": "local-user",
            "title": "Trip",
            "destination_scope": "d" * 161,
        },
        {"owner_user_id": "local-user", "title": "Trip", "planning_status": "draft"},
        {"owner_user_id": "local-user", "title": "Trip", "planning_status": "retained"},
    ],
)
def test_invalid_input_cannot_become_a_validated_create_contract(kwargs):
    """No `WorkspaceCreate` can exist for these inputs, so no write is possible.

    The contract raises during construction, which is why the service is not
    involved here. The service boundary itself is asserted below.
    """
    with pytest.raises(WorkspaceValidationError):
        WorkspaceCreate(**kwargs)


def test_inverted_date_window_cannot_be_constructed():
    """`DateWindow` rejects the range itself, so no create contract can carry it."""
    with pytest.raises(WorkspaceValidationError):
        DateWindow(date(2026, 12, 25), date(2026, 12, 20))


def test_service_rejects_unvalidated_mapping_without_touching_storage(
    repository, service
):
    """A raw mapping is not a validated contract; the service must refuse it."""
    with pytest.raises(WorkspaceValidationError):
        service.create_workspace({"owner_user_id": "local-user", "title": "Trip"})

    assert repository.create_calls == []
    assert repository.records == {}


@pytest.mark.parametrize("bad_input", [None, "local-user", 42, ["local-user"]])
def test_service_rejects_non_contract_inputs(repository, service, bad_input):
    with pytest.raises(WorkspaceValidationError):
        service.create_workspace(bad_input)

    assert repository.create_calls == []


def test_service_does_write_for_a_valid_contract(repository, service):
    """Control for the tests above: the same path does write when input is valid."""
    service.create_workspace(WorkspaceCreate(owner_user_id="local-user", title="Trip"))

    assert len(repository.create_calls) == 1


# 2. Create returns the repository-created workspace.


def test_create_returns_repository_record(repository, service):
    created = service.create_workspace(
        WorkspaceCreate(
            owner_user_id="  local-user  ",
            title="  Da Nang family trip  ",
            destination_scope="  Da Nang and Hoi An  ",
            date_window=DateWindow(date(2026, 12, 20), date(2026, 12, 25)),
        )
    )
    assert len(repository.create_calls) == 1
    assert created is repository.create_calls[0]
    assert created.workspace_id in repository.records


def test_create_generates_governed_identity_and_defaults(repository, service):
    created = service.create_workspace(
        WorkspaceCreate(owner_user_id="local-user", title="Trip")
    )
    assert created.workspace_id.startswith("tw_")
    assert created.planning_status is PlanningStatus.IDEA
    assert created.retention_state is RetentionState.ACTIVE


def test_create_normalizes_fields_before_persisting(repository, service):
    created = service.create_workspace(
        WorkspaceCreate(
            owner_user_id="  local-user  ",
            title="  Trip  ",
            destination_scope="   ",
        )
    )
    assert created.owner_user_id == "local-user"
    assert created.title == "Trip"
    assert created.destination_scope is None


def test_create_sets_timezone_aware_utc_timestamps(repository, service):
    created = service.create_workspace(
        WorkspaceCreate(owner_user_id="local-user", title="Trip")
    )
    assert created.created_at.tzinfo is not None
    assert created.created_at.utcoffset() == timedelta(0)
    assert created.updated_at.utcoffset() == timedelta(0)
    assert created.created_at == created.updated_at


def test_create_preserves_explicit_planning_status(repository, service):
    created = service.create_workspace(
        WorkspaceCreate(
            owner_user_id="local-user",
            title="Trip",
            planning_status=PlanningStatus.BOOKED,
        )
    )
    assert created.planning_status is PlanningStatus.BOOKED


# 3. Get returns None for a missing workspace.


def test_get_returns_none_when_absent(repository, service):
    assert service.get_workspace("tw_missing") is None
    assert repository.get_calls == ["tw_missing"]


def test_get_returns_stored_workspace(repository, service):
    created = service.create_workspace(
        WorkspaceCreate(owner_user_id="local-user", title="Trip")
    )
    assert service.get_workspace(created.workspace_id) == created


@pytest.mark.parametrize("blank", ["", "   "])
def test_get_rejects_blank_identifier_without_storage_call(repository, service, blank):
    with pytest.raises(WorkspaceValidationError):
        service.get_workspace(blank)
    assert repository.get_calls == []


# 4. List requires a non-empty owner scope label.


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_list_requires_owner_scope_label(repository, service, blank):
    with pytest.raises(WorkspaceValidationError):
        service.list_workspaces(blank)
    assert repository.list_calls == []


def test_list_strips_owner_scope_label_before_query(repository, service):
    service.list_workspaces("  local-user  ")
    assert repository.list_calls == ["local-user"]


# 5. List returns repository order without service-layer mutation.


def test_list_returns_repository_order_unchanged(repository, service):
    first = service.create_workspace(
        WorkspaceCreate(owner_user_id="local-user", title="First")
    )
    second = service.create_workspace(
        WorkspaceCreate(owner_user_id="local-user", title="Second")
    )
    third = service.create_workspace(
        WorkspaceCreate(owner_user_id="other-user", title="Other")
    )

    listed = service.list_workspaces("local-user")
    assert listed == (first, second)
    assert third not in listed


def test_list_returns_tuple_for_empty_owner(repository, service):
    listed = service.list_workspaces("nobody")
    assert listed == ()
    assert isinstance(listed, tuple)


# 6. Duplicate generated identity retries exactly once, then fails closed.


def test_duplicate_identity_is_retried_exactly_once(repository, service):
    repository.collide_times = 1

    created = service.create_workspace(
        WorkspaceCreate(owner_user_id="local-user", title="Trip")
    )

    assert len(repository.create_calls) == 2
    first_id = repository.create_calls[0].workspace_id
    second_id = repository.create_calls[1].workspace_id
    assert first_id != second_id, "retry must generate a fresh identity"
    assert created.workspace_id == second_id
    assert created.workspace_id in repository.records


def test_second_collision_raises_controlled_storage_error(repository, service):
    repository.collide_times = 2

    with pytest.raises(WorkspaceStorageError):
        service.create_workspace(
            WorkspaceCreate(owner_user_id="local-user", title="Trip")
        )

    assert len(repository.create_calls) == 2, "service must not retry more than once"
    assert repository.records == {}, "no partial write may remain"


def test_second_collision_error_message_excludes_user_content(repository, service):
    repository.collide_times = 2

    with pytest.raises(WorkspaceStorageError) as caught:
        service.create_workspace(
            WorkspaceCreate(
                owner_user_id="local-user",
                title="Secret honeymoon in Da Lat",
                destination_scope="Da Lat",
            )
        )

    message = str(caught.value)
    assert "Secret honeymoon in Da Lat" not in message
    assert "Da Lat" not in message


def test_create_fails_closed_when_attempt_budget_is_not_positive(
    repository, service, monkeypatch
):
    """`create_workspace` declares `-> TripWorkspace`, so it must never return None.

    A non-positive attempt budget leaves the retry loop body unreachable. Without
    a terminal raise the method falls through and returns None, which would hand
    the route a value the workspace response cannot represent while reporting
    success.
    """
    monkeypatch.setattr("backend.workspaces.service.MAX_IDENTITY_ATTEMPTS", 0)

    with pytest.raises(WorkspaceStorageError):
        service.create_workspace(
            WorkspaceCreate(owner_user_id="local-user", title="Trip")
        )

    assert repository.create_calls == [], "no storage attempt may be made"
    assert repository.records == {}, "no partial write may remain"


# 7. The service imports no web, storage, RAG, or evaluation module.


def test_service_module_imports_no_infrastructure():
    """Assert the real import graph, not the presence of words in the source."""
    import backend.workspaces.service as service_module

    imported = _module_level_imports(service_module)
    for forbidden in (
        "fastapi",
        "pydantic",
        "sqlite3",
        "chromadb",
        "openai",
        "sentence_transformers",
        "backend.rag",
        "backend.app",
    ):
        offenders = [name for name in imported if name.startswith(forbidden)]
        assert not offenders, f"service.py must not import {forbidden}: {offenders}"


def test_service_generates_a_distinct_identity_per_create(repository, service):
    """Identity comes from the governed generator, not from caller input."""
    first = service.create_workspace(
        WorkspaceCreate(owner_user_id="local-user", title="Trip")
    )
    second = service.create_workspace(
        WorkspaceCreate(owner_user_id="local-user", title="Trip")
    )

    assert first.workspace_id != second.workspace_id
    assert first.workspace_id.startswith(WORKSPACE_ID_PREFIX)
    assert second.workspace_id.startswith(WORKSPACE_ID_PREFIX)
