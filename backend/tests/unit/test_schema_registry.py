"""Unit tests for the shared local application store schema registry.

Per ADR 0004 one local SQLite file holds every relational product record for the
prototype, and schema versions are tracked per module in a `schema_versions`
table rather than in `PRAGMA user_version`. The pragma still carries a sentinel
so a pre-R4 build recognizes the file as foreign and fails closed.

Every test uses a `tmp_path` database file, so no test reads or writes the
developer database at `APP_DB_PATH`.
"""

import sqlite3
from pathlib import Path

import pytest

from backend.storage.schema_registry import (
    SENTINEL_USER_VERSION,
    SchemaRegistryError,
    open_application_database,
    read_module_version,
    register_module_schema,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "nested" / "travel_agent.sqlite3"


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row[0] for row in rows}


def _user_version(db_path: Path) -> int:
    with sqlite3.connect(db_path) as connection:
        return connection.execute("PRAGMA user_version").fetchone()[0]


def _seed_pragma(db_path: Path, value: int) -> None:
    """Create a database file carrying only a `PRAGMA user_version` value."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"PRAGMA user_version = {value}")


class _RecordingCreate:
    """Schema create callback that records how many times it ran."""

    def __init__(self, statement: str) -> None:
        self._statement = statement
        self.calls = 0

    def __call__(self, connection: sqlite3.Connection) -> None:
        self.calls += 1
        connection.execute(self._statement)


# 1. A fresh database initializes the registry and writes the sentinel.


def test_open_creates_parent_directory_registry_table_and_sentinel(db_path: Path):
    assert not db_path.parent.exists()

    connection = open_application_database(db_path)
    connection.close()

    assert db_path.parent.exists()
    assert db_path.exists()
    assert "schema_versions" in _table_names(db_path)
    assert _user_version(db_path) == SENTINEL_USER_VERSION


def test_sentinel_value_is_distinct_from_zero_and_one():
    """The sentinel must not collide with `uninitialized` or a pre-R4 version."""
    assert SENTINEL_USER_VERSION == 1000
    assert SENTINEL_USER_VERSION not in (0, 1)


# 2. Reopening a registry-managed database is idempotent.


def test_reopening_a_registry_database_leaves_the_sentinel_unchanged(db_path: Path):
    first = open_application_database(db_path)
    first.close()

    second = open_application_database(db_path)
    second.close()

    assert _user_version(db_path) == SENTINEL_USER_VERSION
    assert "schema_versions" in _table_names(db_path)


# 3 and 4. A legacy or unknown pragma value fails closed without migrating.


def test_legacy_pre_r4_pragma_value_fails_closed(db_path: Path):
    _seed_pragma(db_path, 1)

    with pytest.raises(SchemaRegistryError):
        open_application_database(db_path)

    assert "schema_versions" not in _table_names(db_path)
    assert _user_version(db_path) == 1, "the registry must not rewrite the pragma"


def test_unknown_nonzero_pragma_value_fails_closed(db_path: Path):
    _seed_pragma(db_path, 77)

    with pytest.raises(SchemaRegistryError):
        open_application_database(db_path)

    assert "schema_versions" not in _table_names(db_path)
    assert _user_version(db_path) == 77


# 5 and 6. Module registration runs its create callback exactly once.


def test_registering_a_module_runs_create_once_and_records_the_version(db_path: Path):
    create = _RecordingCreate(
        "CREATE TABLE IF NOT EXISTS widgets (id TEXT PRIMARY KEY)"
    )

    connection = open_application_database(db_path)
    try:
        register_module_schema(connection, "widgets", 1, create)
        assert create.calls == 1
        assert read_module_version(connection, "widgets") == 1
    finally:
        connection.close()

    assert "widgets" in _table_names(db_path)


def test_registering_the_same_module_again_does_not_rerun_create(db_path: Path):
    create = _RecordingCreate(
        "CREATE TABLE IF NOT EXISTS widgets (id TEXT PRIMARY KEY)"
    )

    first = open_application_database(db_path)
    try:
        register_module_schema(first, "widgets", 1, create)
    finally:
        first.close()

    second = open_application_database(db_path)
    try:
        register_module_schema(second, "widgets", 1, create)
        assert read_module_version(second, "widgets") == 1
    finally:
        second.close()

    assert create.calls == 1, "an already-registered module must not re-run create"


# 7. A recorded version the build does not support fails closed.


def test_recorded_version_higher_than_requested_fails_closed(db_path: Path):
    create = _RecordingCreate(
        "CREATE TABLE IF NOT EXISTS widgets (id TEXT PRIMARY KEY)"
    )

    connection = open_application_database(db_path)
    try:
        register_module_schema(connection, "widgets", 2, create)

        with pytest.raises(SchemaRegistryError):
            register_module_schema(connection, "widgets", 1, create)

        assert read_module_version(connection, "widgets") == 2
        assert create.calls == 1
    finally:
        connection.close()


def test_recorded_version_lower_than_requested_fails_closed_without_migrating(
    db_path: Path,
):
    """R4 has no migration framework, so any version mismatch must fail closed."""
    create = _RecordingCreate(
        "CREATE TABLE IF NOT EXISTS widgets (id TEXT PRIMARY KEY)"
    )

    connection = open_application_database(db_path)
    try:
        register_module_schema(connection, "widgets", 1, create)

        with pytest.raises(SchemaRegistryError):
            register_module_schema(connection, "widgets", 2, create)

        assert read_module_version(connection, "widgets") == 1
    finally:
        connection.close()


# 8. Two modules record independent versions in one file.


def test_two_modules_register_independent_versions(db_path: Path):
    widgets = _RecordingCreate(
        "CREATE TABLE IF NOT EXISTS widgets (id TEXT PRIMARY KEY)"
    )
    gadgets = _RecordingCreate(
        "CREATE TABLE IF NOT EXISTS gadgets (id TEXT PRIMARY KEY)"
    )

    connection = open_application_database(db_path)
    try:
        register_module_schema(connection, "widgets", 1, widgets)
        register_module_schema(connection, "gadgets", 3, gadgets)

        assert read_module_version(connection, "widgets") == 1
        assert read_module_version(connection, "gadgets") == 3
    finally:
        connection.close()

    assert {"widgets", "gadgets"} <= _table_names(db_path)


def test_one_module_registration_does_not_disturb_another(db_path: Path):
    widgets = _RecordingCreate(
        "CREATE TABLE IF NOT EXISTS widgets (id TEXT PRIMARY KEY)"
    )
    gadgets = _RecordingCreate(
        "CREATE TABLE IF NOT EXISTS gadgets (id TEXT PRIMARY KEY)"
    )

    connection = open_application_database(db_path)
    try:
        register_module_schema(connection, "widgets", 1, widgets)
        register_module_schema(connection, "gadgets", 3, gadgets)
        register_module_schema(connection, "widgets", 1, widgets)

        assert read_module_version(connection, "gadgets") == 3
        assert gadgets.calls == 1
    finally:
        connection.close()


# 9. An unregistered module has no version.


def test_read_module_version_returns_none_for_an_unregistered_module(db_path: Path):
    connection = open_application_database(db_path)
    try:
        assert read_module_version(connection, "never_registered") is None
    finally:
        connection.close()


# 10. Registry errors are safe for a controlled HTTP 500 response.


def test_registry_error_message_excludes_database_path_and_sql_text(db_path: Path):
    _seed_pragma(db_path, 1)

    with pytest.raises(SchemaRegistryError) as caught:
        open_application_database(db_path)

    message = str(caught.value)
    assert str(db_path) not in message
    assert db_path.name not in message
    assert "CREATE TABLE" not in message
    assert "SELECT" not in message


def test_module_version_mismatch_message_excludes_database_path_and_sql_text(
    db_path: Path,
):
    create = _RecordingCreate(
        "CREATE TABLE IF NOT EXISTS widgets (id TEXT PRIMARY KEY)"
    )

    connection = open_application_database(db_path)
    try:
        register_module_schema(connection, "widgets", 2, create)

        with pytest.raises(SchemaRegistryError) as caught:
            register_module_schema(connection, "widgets", 1, create)
    finally:
        connection.close()

    message = str(caught.value)
    assert str(db_path) not in message
    assert db_path.name not in message
    assert "CREATE TABLE" not in message
    assert "SELECT" not in message


# 11. Storage rollback evidence for the R4 exit gate.


def test_r4_database_pragma_is_rejected_by_the_pre_r4_workspace_rule_rollback_evidence(
    db_path: Path,
):
    """Schema rollback evidence required by the `R4` roadmap exit gate.

    A pre-R4 workspace build reads `PRAGMA user_version` and accepts exactly two
    values without raising: `0`, which it treats as an uninitialized file, and
    its own `SCHEMA_VERSION`, which it treats as a compatible file. Every other
    value takes the fail-closed branch at
    `backend/workspaces/sqlite_repository.py:170`.

    A database initialized by R4 therefore must present neither value, so an
    older build refuses the file instead of writing into a schema it does not
    understand.
    """
    from backend.workspaces.sqlite_repository import SCHEMA_VERSION

    connection = open_application_database(db_path)
    connection.close()

    observed = _user_version(db_path)

    assert observed == SENTINEL_USER_VERSION
    assert observed != 0, "a pre-R4 build would treat 0 as an uninitialized file"
    assert observed != SCHEMA_VERSION, (
        "a pre-R4 build would treat its own SCHEMA_VERSION as compatible"
    )


def test_registry_writes_only_under_the_supplied_path(db_path: Path, tmp_path: Path):
    """Storage stays inside the injected path, never a module-level default."""
    connection = open_application_database(db_path)
    connection.close()

    assert db_path.is_relative_to(tmp_path)

    written = {path for path in tmp_path.rglob("*") if path.is_file()}
    assert all(path.name.startswith(db_path.name) for path in written), (
        f"unexpected files written under the temporary root: {written}"
    )
