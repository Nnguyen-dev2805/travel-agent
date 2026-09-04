"""Local SQLite workspace repository adapter for runtime milestone R3.

Per ADR 0003 this adapter is the only module that knows SQLite exists. It owns
schema version 1 initialization, parameterized SQL, and SQLite error handling.
It is accepted for local development and tests only; it is not a production
database commitment, and it settles no production migration, backup, restore,
concurrency, retention, or deletion policy.

Raised `WorkspaceStorageError` messages are safe for a controlled HTTP 500
response: they never include the local database path, full SQL text, or
user-entered workspace content.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from backend.workspaces.models import (
    DateWindow,
    PlanningStatus,
    RetentionState,
    TripWorkspace,
    WorkspaceValidationError,
)
from backend.workspaces.repository import (
    WorkspaceAlreadyExistsError,
    WorkspaceStorageError,
)

logger = logging.getLogger("travel_agent_workspaces")

SCHEMA_VERSION = 1
TABLE_NAME = "trip_workspaces"

_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    workspace_id      TEXT PRIMARY KEY,
    owner_user_id     TEXT NOT NULL,
    title             TEXT NOT NULL,
    destination_scope TEXT,
    start_date        TEXT,
    end_date          TEXT,
    planning_status   TEXT NOT NULL,
    retention_state   TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
)
"""

_CREATE_OWNER_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_owner
ON {TABLE_NAME} (owner_user_id, updated_at DESC, created_at DESC, workspace_id ASC)
"""

_INSERT = f"""
INSERT INTO {TABLE_NAME} (
    workspace_id, owner_user_id, title, destination_scope,
    start_date, end_date, planning_status, retention_state,
    created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_COLUMNS = """
    workspace_id, owner_user_id, title, destination_scope,
    start_date, end_date, planning_status, retention_state,
    created_at, updated_at
"""

_SELECT_BY_ID = f"SELECT {_SELECT_COLUMNS} FROM {TABLE_NAME} WHERE workspace_id = ?"

# Listing excludes `deleted` records. R3 creates only `active` records, so this
# filter has no effect today, but it keeps a future deletion milestone from
# surfacing removed records through the list route.
_SELECT_BY_OWNER = f"""
SELECT {_SELECT_COLUMNS} FROM {TABLE_NAME}
WHERE owner_user_id = ? AND retention_state != ?
ORDER BY updated_at DESC, created_at DESC, workspace_id ASC
"""


def _to_iso_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _from_iso_datetime(value: Any, column: str) -> datetime:
    if not isinstance(value, str):
        raise WorkspaceStorageError(
            f"Stored workspace column '{column}' is not a timestamp string."
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise WorkspaceStorageError(
            f"Stored workspace column '{column}' is not a valid ISO timestamp."
        ) from error
    if parsed.tzinfo is None:
        raise WorkspaceStorageError(
            f"Stored workspace column '{column}' is missing timezone information."
        )
    return parsed.astimezone(timezone.utc)


def _to_iso_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _from_iso_date(value: Any, column: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise WorkspaceStorageError(
            f"Stored workspace column '{column}' is not a date string."
        )
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise WorkspaceStorageError(
            f"Stored workspace column '{column}' is not a valid ISO date."
        ) from error


class SQLiteWorkspaceRepository:
    """Persist trip workspace records in a local SQLite database."""

    def __init__(self, db_path: Path) -> None:
        """Open or initialize the local workspace database.

        Raises:
            WorkspaceStorageError: The parent directory cannot be created, the
                database cannot be opened, or the existing schema version is
                incompatible with `SCHEMA_VERSION`.
        """
        self._db_path = Path(db_path)
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self._db_path)
        except sqlite3.Error as error:
            raise WorkspaceStorageError(
                "Could not open the local workspace database."
            ) from error
        return connection

    def _initialize_schema(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise WorkspaceStorageError(
                "Could not create the local workspace database directory."
            ) from error

        connection = self._connect()
        try:
            with connection:
                current = connection.execute("PRAGMA user_version").fetchone()[0]

                if current == 0:
                    connection.execute(_CREATE_TABLE)
                    connection.execute(_CREATE_OWNER_INDEX)
                    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                    logger.info(
                        "Initialized local workspace schema version %s.",
                        SCHEMA_VERSION,
                    )
                elif current != SCHEMA_VERSION:
                    raise WorkspaceStorageError(
                        f"Local workspace database reports schema version {current}, "
                        f"but this build supports version {SCHEMA_VERSION}. "
                        "Refusing to migrate automatically."
                    )
        except sqlite3.Error as error:
            raise WorkspaceStorageError(
                "Could not initialize the local workspace schema."
            ) from error
        finally:
            connection.close()

    def create(self, workspace: TripWorkspace) -> TripWorkspace:
        """Persist a new workspace record and return it."""
        start_date = workspace.date_window.start_date if workspace.date_window else None
        end_date = workspace.date_window.end_date if workspace.date_window else None

        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    _INSERT,
                    (
                        workspace.workspace_id,
                        workspace.owner_user_id,
                        workspace.title,
                        workspace.destination_scope,
                        _to_iso_date(start_date),
                        _to_iso_date(end_date),
                        workspace.planning_status.value,
                        workspace.retention_state.value,
                        _to_iso_datetime(workspace.created_at),
                        _to_iso_datetime(workspace.updated_at),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise WorkspaceAlreadyExistsError(
                "A workspace with this identity already exists."
            ) from error
        except sqlite3.Error as error:
            raise WorkspaceStorageError(
                "Could not persist the workspace record."
            ) from error
        finally:
            connection.close()

        return workspace

    def get(self, workspace_id: str) -> TripWorkspace | None:
        """Return the stored workspace, or None when no record exists."""
        connection = self._connect()
        try:
            row = connection.execute(_SELECT_BY_ID, (workspace_id,)).fetchone()
        except sqlite3.Error as error:
            raise WorkspaceStorageError(
                "Could not read the workspace record."
            ) from error
        finally:
            connection.close()

        if row is None:
            return None
        return self._row_to_workspace(row)

    def list_by_owner(self, owner_user_id: str) -> tuple[TripWorkspace, ...]:
        """Return owner-scoped workspaces in governed deterministic order.

        Records in `RetentionState.DELETED` are excluded.
        """
        connection = self._connect()
        try:
            rows = connection.execute(
                _SELECT_BY_OWNER, (owner_user_id, RetentionState.DELETED.value)
            ).fetchall()
        except sqlite3.Error as error:
            raise WorkspaceStorageError("Could not list workspace records.") from error
        finally:
            connection.close()

        return tuple(self._row_to_workspace(row) for row in rows)

    def _row_to_workspace(self, row: tuple[Any, ...]) -> TripWorkspace:
        """Map one stored row to a workspace contract, failing closed."""
        (
            workspace_id,
            owner_user_id,
            title,
            destination_scope,
            start_date,
            end_date,
            planning_status,
            retention_state,
            created_at,
            updated_at,
        ) = row

        try:
            status = PlanningStatus(planning_status)
        except ValueError as error:
            raise WorkspaceStorageError(
                "Stored workspace column 'planning_status' is outside the "
                "governed vocabulary."
            ) from error

        try:
            retention = RetentionState(retention_state)
        except ValueError as error:
            raise WorkspaceStorageError(
                "Stored workspace column 'retention_state' is outside the "
                "governed vocabulary."
            ) from error

        window_start = _from_iso_date(start_date, "start_date")
        window_end = _from_iso_date(end_date, "end_date")
        date_window = (
            DateWindow(start_date=window_start, end_date=window_end)
            if window_start is not None or window_end is not None
            else None
        )

        try:
            return TripWorkspace(
                workspace_id=workspace_id,
                owner_user_id=owner_user_id,
                title=title,
                destination_scope=destination_scope,
                date_window=date_window,
                planning_status=status,
                created_at=_from_iso_datetime(created_at, "created_at"),
                updated_at=_from_iso_datetime(updated_at, "updated_at"),
                retention_state=retention,
            )
        except WorkspaceValidationError as error:
            raise WorkspaceStorageError(
                "Stored workspace record violates the workspace contract."
            ) from error
