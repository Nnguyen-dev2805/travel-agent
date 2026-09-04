"""Unit tests for the local SQLite workspace repository adapter.

Per ADR 0003 the SQLite adapter is a local R3 boundary, not production storage.
Per ADR 0004 its schema version now lives in the shared `schema_versions`
registry table rather than in `PRAGMA user_version`, which carries a shared
store marker instead.

Every test uses a `tmp_path` database file so no test touches the developer's
local database at `APP_DB_PATH`.
"""

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.storage.schema_registry import (
    SENTINEL_USER_VERSION,
    open_application_database,
)
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

WORKSPACE_SCHEMA_MODULE = "workspaces"
"""The registry key the workspace module must persist.

Asserted as a literal rather than imported from the adapter, because this is the
stored key a future build reads back from the shared database.
"""


def _recorded_module_version(db_path: Path, module: str) -> int | None:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT version FROM schema_versions WHERE module = ?", (module,)
        ).fetchone()
    return None if row is None else row[0]


def _store_marker(db_path: Path) -> int:
    with sqlite3.connect(db_path) as connection:
        return connection.execute("PRAGMA user_version").fetchone()[0]


def _seed_recorded_workspace_version(db_path: Path, version: int) -> None:
    """Create a registry-owned database that already records a workspace version."""
    connection = open_application_database(db_path)
    try:
        with connection:
            connection.execute(
                "INSERT INTO schema_versions (module, version) VALUES (?, ?)",
                (WORKSPACE_SCHEMA_MODULE, version),
            )
    finally:
        connection.close()


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
    """The workspace module records its version in the shared registry.

    Rewritten for ADR 0004: version bookkeeping moved out of
    `PRAGMA user_version`, which now carries the shared store marker so a
    pre-R4 build refuses the file.
    """
    assert _recorded_module_version(db_path, WORKSPACE_SCHEMA_MODULE) == SCHEMA_VERSION
    assert SCHEMA_VERSION == 1
    assert _store_marker(db_path) == SENTINEL_USER_VERSION


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
    """A recorded workspace version above the supported one fails closed.

    Rewritten for ADR 0004 to seed the registry row rather than the pragma.
    """
    _seed_recorded_workspace_version(db_path, SCHEMA_VERSION + 1)

    with pytest.raises(WorkspaceStorageError):
        SQLiteWorkspaceRepository(db_path=db_path)


def test_registry_owned_database_without_a_workspace_row_is_adopted(db_path: Path):
    """The store marker alone must not be the reason a database is refused.

    This is the discriminator for the two fail-closed tests around it: a
    registry-owned file carrying the shared marker but no workspace row is
    adopted normally, so their failures are caused by the recorded module
    version and not by the marker.
    """
    connection = open_application_database(db_path)
    connection.close()

    repository = SQLiteWorkspaceRepository(db_path=db_path)
    stored = repository.create(_workspace())

    assert repository.get(stored.workspace_id) == stored
    assert _recorded_module_version(db_path, WORKSPACE_SCHEMA_MODULE) == SCHEMA_VERSION


def test_incompatible_schema_version_is_not_silently_migrated(db_path: Path):
    """The adapter must not rewrite a recorded version it does not support."""
    future_version = SCHEMA_VERSION + 5
    _seed_recorded_workspace_version(db_path, future_version)

    with pytest.raises(WorkspaceStorageError):
        SQLiteWorkspaceRepository(db_path=db_path)

    assert (
        _recorded_module_version(db_path, WORKSPACE_SCHEMA_MODULE) == future_version
    ), "adapter must not rewrite the recorded schema version"
    assert _store_marker(db_path) == SENTINEL_USER_VERSION


def test_pre_r4_database_is_refused_instead_of_adopted(db_path: Path):
    """A database carrying only a pre-R4 pragma value fails closed.

    This is the forward direction of the ADR 0004 sentinel rule: an R4 build
    must refuse a file whose ownership it cannot establish, rather than creating
    a registry beside a schema it did not write.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    with pytest.raises(WorkspaceStorageError):
        SQLiteWorkspaceRepository(db_path=db_path)

    assert _store_marker(db_path) == SCHEMA_VERSION


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
