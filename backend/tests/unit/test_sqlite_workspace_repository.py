"""Unit tests for the local SQLite workspace repository adapter.

Per ADR 0003 the SQLite adapter is a local R3 boundary, not production storage.
Every test uses a `tmp_path` database file so no test touches the developer's
local workspace database at `WORKSPACE_DB_PATH`.
"""

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.workspaces.models import (
    DateWindow,
    PlanningStatus,
    RetentionState,
    TripWorkspace,
    generate_workspace_id,
)
from backend.workspaces.repository import (
    WorkspaceAlreadyExistsError,
    WorkspaceStorageError,
)
from backend.workspaces.sqlite_repository import (
    SCHEMA_VERSION,
    SQLiteWorkspaceRepository,
)


def _workspace(
    *,
    workspace_id: str | None = None,
    owner_user_id: str = "local-user",
    title: str = "Da Nang family trip",
    destination_scope: str | None = "Da Nang and Hoi An",
    date_window: DateWindow | None = None,
    planning_status: PlanningStatus = PlanningStatus.IDEA,
    retention_state: RetentionState = RetentionState.ACTIVE,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> TripWorkspace:
    moment = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
    return TripWorkspace(
        workspace_id=workspace_id or generate_workspace_id(),
        owner_user_id=owner_user_id,
        title=title,
        destination_scope=destination_scope,
        date_window=date_window,
        planning_status=planning_status,
        created_at=created_at or moment,
        updated_at=updated_at or moment,
        retention_state=retention_state,
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "nested" / "workspaces.sqlite3"


@pytest.fixture
def repository(db_path: Path) -> SQLiteWorkspaceRepository:
    return SQLiteWorkspaceRepository(db_path=db_path)


# 1. Parent directory and schema version 1 initialize safely.


def test_initialization_creates_parent_directory(db_path: Path):
    assert not db_path.parent.exists()
    SQLiteWorkspaceRepository(db_path=db_path)
    assert db_path.parent.exists()
    assert db_path.exists()


def test_initialization_records_schema_version(repository, db_path: Path):
    with sqlite3.connect(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == SCHEMA_VERSION
    assert SCHEMA_VERSION == 1


def test_initialization_creates_workspace_table(repository, db_path: Path):
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    table_names = {row[0] for row in rows}
    assert "trip_workspaces" in table_names


def test_initialization_is_idempotent(db_path: Path):
    first = SQLiteWorkspaceRepository(db_path=db_path)
    stored = first.create(_workspace())
    second = SQLiteWorkspaceRepository(db_path=db_path)
    assert second.get(stored.workspace_id) == stored


# 2. An incompatible schema version fails closed without migrating.


def test_incompatible_schema_version_fails_closed(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(WorkspaceStorageError):
        SQLiteWorkspaceRepository(db_path=db_path)


def test_incompatible_schema_version_is_not_silently_migrated(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    future_version = SCHEMA_VERSION + 5
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"PRAGMA user_version = {future_version}")

    with pytest.raises(WorkspaceStorageError):
        SQLiteWorkspaceRepository(db_path=db_path)

    with sqlite3.connect(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == future_version, "adapter must not rewrite the schema version"


def test_storage_error_message_excludes_local_path(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(WorkspaceStorageError) as caught:
        SQLiteWorkspaceRepository(db_path=db_path)

    assert str(db_path) not in str(caught.value)


# 3. Create persists normalized fields and the server-generated `tw_` ID.


def test_create_persists_and_returns_record(repository):
    workspace = _workspace()
    stored = repository.create(workspace)
    assert stored == workspace
    assert stored.workspace_id.startswith("tw_")


def test_create_persists_full_date_window(repository):
    workspace = _workspace(
        date_window=DateWindow(date(2026, 12, 20), date(2026, 12, 25))
    )
    repository.create(workspace)
    loaded = repository.get(workspace.workspace_id)
    assert loaded is not None
    assert loaded.date_window is not None
    assert loaded.date_window.start_date == date(2026, 12, 20)
    assert loaded.date_window.end_date == date(2026, 12, 25)


def test_create_persists_absent_optional_fields(repository):
    workspace = _workspace(destination_scope=None, date_window=None)
    repository.create(workspace)
    loaded = repository.get(workspace.workspace_id)
    assert loaded is not None
    assert loaded.destination_scope is None
    assert loaded.date_window is None


def test_create_persists_partial_date_window(repository):
    workspace = _workspace(date_window=DateWindow(start_date=date(2026, 12, 20)))
    repository.create(workspace)
    loaded = repository.get(workspace.workspace_id)
    assert loaded is not None
    assert loaded.date_window is not None
    assert loaded.date_window.start_date == date(2026, 12, 20)
    assert loaded.date_window.end_date is None


def test_create_rejects_duplicate_identity(repository):
    workspace = _workspace()
    repository.create(workspace)
    with pytest.raises(WorkspaceAlreadyExistsError):
        repository.create(workspace)


def test_duplicate_create_does_not_overwrite_stored_record(repository):
    original = _workspace(title="Original")
    repository.create(original)
    clash = _workspace(workspace_id=original.workspace_id, title="Replacement")

    with pytest.raises(WorkspaceAlreadyExistsError):
        repository.create(clash)

    loaded = repository.get(original.workspace_id)
    assert loaded is not None
    assert loaded.title == "Original"


def test_created_timestamps_survive_round_trip_as_utc(repository):
    moment = datetime(2026, 9, 3, 5, 30, 15, tzinfo=timezone.utc)
    workspace = _workspace(created_at=moment, updated_at=moment)
    repository.create(workspace)
    loaded = repository.get(workspace.workspace_id)
    assert loaded is not None
    assert loaded.created_at == moment
    assert loaded.created_at.utcoffset() == timedelta(0)


def test_enum_values_survive_round_trip(repository):
    workspace = _workspace(
        planning_status=PlanningStatus.BOOKED,
        retention_state=RetentionState.ARCHIVED,
    )
    repository.create(workspace)
    loaded = repository.get(workspace.workspace_id)
    assert loaded is not None
    assert loaded.planning_status is PlanningStatus.BOOKED
    assert loaded.retention_state is RetentionState.ARCHIVED


# 4 and 5. Get returns the exact stored workspace, or None when absent.


def test_get_returns_exact_stored_workspace(repository):
    workspace = _workspace()
    repository.create(workspace)
    assert repository.get(workspace.workspace_id) == workspace


def test_get_returns_none_when_absent(repository):
    assert repository.get("tw_does_not_exist") is None


def test_get_persists_across_repository_instances(db_path: Path):
    first = SQLiteWorkspaceRepository(db_path=db_path)
    workspace = _workspace()
    first.create(workspace)

    second = SQLiteWorkspaceRepository(db_path=db_path)
    assert second.get(workspace.workspace_id) == workspace


# 6. List by owner excludes other owner labels.


def test_list_by_owner_excludes_other_owners(repository):
    mine_a = _workspace(owner_user_id="local-user", title="Mine A")
    mine_b = _workspace(owner_user_id="local-user", title="Mine B")
    theirs = _workspace(owner_user_id="other-user", title="Theirs")
    for record in (mine_a, mine_b, theirs):
        repository.create(record)

    listed = repository.list_by_owner("local-user")
    titles = {record.title for record in listed}
    assert titles == {"Mine A", "Mine B"}


def test_list_by_owner_returns_empty_tuple_when_none_match(repository):
    repository.create(_workspace(owner_user_id="local-user"))
    listed = repository.list_by_owner("nobody")
    assert listed == ()
    assert isinstance(listed, tuple)


# 7. Governed deterministic ordering.


def test_list_orders_by_updated_at_descending(repository):
    base = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
    older = _workspace(
        title="Older",
        created_at=base,
        updated_at=base,
    )
    newer = _workspace(
        title="Newer",
        created_at=base,
        updated_at=base + timedelta(days=2),
    )
    repository.create(older)
    repository.create(newer)

    listed = repository.list_by_owner("local-user")
    assert [record.title for record in listed] == ["Newer", "Older"]


def test_list_breaks_updated_at_tie_by_created_at_descending(repository):
    same_update = datetime(2026, 9, 5, 0, 0, 0, tzinfo=timezone.utc)
    earlier_created = _workspace(
        title="Created earlier",
        created_at=datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc),
        updated_at=same_update,
    )
    later_created = _workspace(
        title="Created later",
        created_at=datetime(2026, 9, 3, 0, 0, 0, tzinfo=timezone.utc),
        updated_at=same_update,
    )
    repository.create(earlier_created)
    repository.create(later_created)

    listed = repository.list_by_owner("local-user")
    assert [record.title for record in listed] == ["Created later", "Created earlier"]


def test_list_breaks_full_tie_by_workspace_id_ascending(repository):
    moment = datetime(2026, 9, 5, 0, 0, 0, tzinfo=timezone.utc)
    low = _workspace(
        workspace_id="tw_aaaa0000",
        title="Low id",
        created_at=moment,
        updated_at=moment,
    )
    high = _workspace(
        workspace_id="tw_zzzz9999",
        title="High id",
        created_at=moment,
        updated_at=moment,
    )
    repository.create(high)
    repository.create(low)

    listed = repository.list_by_owner("local-user")
    assert [record.workspace_id for record in listed] == ["tw_aaaa0000", "tw_zzzz9999"]


# 8. Invalid persisted values fail closed through repository errors.


def test_invalid_persisted_planning_status_fails_closed(repository, db_path: Path):
    workspace = _workspace()
    repository.create(workspace)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE trip_workspaces SET planning_status = ? WHERE workspace_id = ?",
            ("draft", workspace.workspace_id),
        )

    with pytest.raises(WorkspaceStorageError):
        repository.get(workspace.workspace_id)


def test_invalid_persisted_retention_state_fails_closed(repository, db_path: Path):
    workspace = _workspace()
    repository.create(workspace)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE trip_workspaces SET retention_state = ? WHERE workspace_id = ?",
            ("retained", workspace.workspace_id),
        )

    with pytest.raises(WorkspaceStorageError):
        repository.get(workspace.workspace_id)


def test_invalid_persisted_date_fails_closed(repository, db_path: Path):
    workspace = _workspace(
        date_window=DateWindow(date(2026, 12, 20), date(2026, 12, 25))
    )
    repository.create(workspace)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE trip_workspaces SET start_date = ? WHERE workspace_id = ?",
            ("not-a-date", workspace.workspace_id),
        )

    with pytest.raises(WorkspaceStorageError):
        repository.get(workspace.workspace_id)


def test_invalid_persisted_timestamp_fails_closed(repository, db_path: Path):
    workspace = _workspace()
    repository.create(workspace)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE trip_workspaces SET created_at = ? WHERE workspace_id = ?",
            ("never", workspace.workspace_id),
        )

    with pytest.raises(WorkspaceStorageError):
        repository.get(workspace.workspace_id)


def test_invalid_persisted_row_also_fails_closed_on_list(repository, db_path: Path):
    workspace = _workspace()
    repository.create(workspace)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE trip_workspaces SET planning_status = ? WHERE workspace_id = ?",
            ("draft", workspace.workspace_id),
        )

    with pytest.raises(WorkspaceStorageError):
        repository.list_by_owner("local-user")


# 9. Tests never touch the developer's default database path.


def test_repository_writes_only_under_the_supplied_path(db_path: Path, tmp_path: Path):
    """Storage stays inside the injected path, never a module-level default."""
    repository = SQLiteWorkspaceRepository(db_path=db_path)
    repository.create(_workspace())

    assert db_path.exists()
    assert db_path.is_relative_to(tmp_path)

    written = {path for path in tmp_path.rglob("*") if path.is_file()}
    assert all(path.name.startswith(db_path.name) for path in written), (
        f"unexpected files written under the temporary root: {written}"
    )


def test_repository_ignores_the_configured_default_path(db_path: Path):
    """The adapter takes its path from the caller, not from settings."""
    from backend.app.config import settings

    repository = SQLiteWorkspaceRepository(db_path=db_path)
    stored = repository.create(_workspace())

    assert repository.get(stored.workspace_id) == stored
    assert db_path != settings.WORKSPACE_DB_PATH
