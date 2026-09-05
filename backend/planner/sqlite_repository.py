"""SQLite planner storage for milestone R7.

The adapter owns every planner SQL statement and the `planner_state`
schema registration. It stores itinerary versions, trip decisions, and
append-only operations in the shared local application database without
changing any other schema module version. A stored row that violates the
domain contract fails closed instead of surfacing corrupt state.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.planner.models import (
    DecisionStatus,
    DecisionType,
    ItineraryItem,
    ItineraryItemType,
    ItineraryStatus,
    ItineraryVersion,
    PlannerOperation,
    PlannerOperationStatus,
    PlannerOperationType,
    PlannerValidationError,
    TripDecision,
)
from backend.planner.repository import (
    PlannerNotFoundError,
    PlannerRepositoryError,
    PlannerStorageError,
)
from backend.storage.schema_registry import (
    SchemaRegistryError,
    open_application_database,
    register_module_schema,
)

logger = logging.getLogger("travel_agent_planner")

PLANNER_SCHEMA_VERSION = 1
PLANNER_SCHEMA_MODULE = "planner_state"

VERSION_TABLE = "planner_itinerary_versions"
DECISION_TABLE = "planner_trip_decisions"
OPERATION_TABLE = "planner_operations"

_CREATE_VERSION_TABLE = f"""
CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
    itinerary_version_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    title TEXT,
    summary TEXT,
    items TEXT NOT NULL,
    created_from_operation_id TEXT,
    created_from_message_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(workspace_id, version_number)
)
"""

_CREATE_DECISION_TABLE = f"""
CREATE TABLE IF NOT EXISTS {DECISION_TABLE} (
    decision_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    status TEXT NOT NULL,
    statement TEXT NOT NULL,
    rationale TEXT,
    source_message_id TEXT,
    supersedes_decision_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_OPERATION_TABLE = f"""
CREATE TABLE IF NOT EXISTS {OPERATION_TABLE} (
    operation_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    conversation_id TEXT,
    operation_type TEXT NOT NULL,
    status TEXT NOT NULL,
    input_summary TEXT,
    result_itinerary_version_id TEXT,
    result_decision_id TEXT,
    source_message_id TEXT,
    created_at TEXT NOT NULL
)
"""


def _to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _from_iso(value: Any, column: str) -> datetime:
    if not isinstance(value, str):
        raise PlannerStorageError(
            f"Stored planner column '{column}' is not a timestamp string."
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise PlannerStorageError(
            f"Stored planner column '{column}' is not a valid timestamp."
        ) from error
    if parsed.tzinfo is None:
        raise PlannerStorageError(
            f"Stored planner column '{column}' is not timezone-aware."
        )
    return parsed.astimezone(timezone.utc)


def _item_to_json(item: ItineraryItem) -> dict[str, Any]:
    return {
        "day_index": item.day_index,
        "position": item.position,
        "item_type": item.item_type.value,
        "title": item.title,
        "location": item.location,
        "start_time": item.start_time,
        "end_time": item.end_time,
        "notes": item.notes,
        "source_decision_ids": list(item.source_decision_ids),
    }


def _item_from_json(payload: Any) -> ItineraryItem:
    if not isinstance(payload, dict):
        raise PlannerStorageError(
            "Stored planner column 'items' holds a non-object entry."
        )
    try:
        return ItineraryItem(
            day_index=payload["day_index"],
            position=payload["position"],
            item_type=ItineraryItemType(payload["item_type"]),
            title=payload["title"],
            location=payload.get("location"),
            start_time=payload.get("start_time"),
            end_time=payload.get("end_time"),
            notes=payload.get("notes"),
            source_decision_ids=tuple(payload.get("source_decision_ids") or ()),
        )
    except (KeyError, TypeError, ValueError, PlannerValidationError) as error:
        raise PlannerStorageError(
            "Stored planner column 'items' holds an invalid itinerary item."
        ) from error


def _items_to_json(items: tuple[ItineraryItem, ...]) -> str:
    return json.dumps([_item_to_json(item) for item in items])


def _items_from_json(value: Any) -> tuple[ItineraryItem, ...]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise PlannerStorageError(
            "Stored planner column 'items' is not valid JSON."
        ) from error
    if not isinstance(parsed, list):
        raise PlannerStorageError("Stored planner column 'items' is not a JSON list.")
    return tuple(_item_from_json(entry) for entry in parsed)


class SQLitePlannerRepository:
    """Persist planner state in the shared local application database."""

    def __init__(self, db_path: Path | str) -> None:
        """Open or initialize planner storage in the shared database.

        Raises:
            PlannerStorageError: The database cannot be opened or the
                recorded `planner_state` schema version is incompatible
                with `PLANNER_SCHEMA_VERSION`.
        """
        self._db_path = Path(db_path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        try:
            connection = open_application_database(self._db_path)
        except SchemaRegistryError as error:
            logger.error(
                "planner.storage unavailable module=%s failure_class=%s",
                PLANNER_SCHEMA_MODULE,
                type(error).__name__,
            )
            raise PlannerStorageError(
                "Could not open the local application database for planner storage."
            ) from error
        try:
            try:
                register_module_schema(
                    connection,
                    PLANNER_SCHEMA_MODULE,
                    PLANNER_SCHEMA_VERSION,
                    self._create_schema,
                )
            except SchemaRegistryError as error:
                logger.error(
                    "planner.storage schema mismatch module=%s version=%s "
                    "failure_class=%s",
                    PLANNER_SCHEMA_MODULE,
                    PLANNER_SCHEMA_VERSION,
                    type(error).__name__,
                )
                raise PlannerStorageError(
                    f"The local application database does not provide "
                    f"{PLANNER_SCHEMA_MODULE} schema version "
                    f"{PLANNER_SCHEMA_VERSION}. Refusing to migrate "
                    "automatically."
                ) from error
        finally:
            connection.close()

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.execute(_CREATE_VERSION_TABLE)
        connection.execute(_CREATE_DECISION_TABLE)
        connection.execute(_CREATE_OPERATION_TABLE)

    def _connect(self) -> sqlite3.Connection:
        try:
            return sqlite3.connect(self._db_path)
        except sqlite3.Error as error:
            raise PlannerStorageError(
                "Could not open the local planner database."
            ) from error

    def create_itinerary_version(self, version: ItineraryVersion) -> ItineraryVersion:
        """Persist a version with the next workspace version number."""
        import dataclasses

        connection = self._connect()
        try:
            with connection:
                row = connection.execute(
                    f"SELECT COALESCE(MAX(version_number), 0) FROM {VERSION_TABLE} "
                    "WHERE workspace_id = ?",
                    (version.workspace_id,),
                ).fetchone()
                assigned = int(row[0]) + 1
                try:
                    connection.execute(
                        f"INSERT INTO {VERSION_TABLE} (itinerary_version_id, "
                        "workspace_id, version_number, status, title, summary, "
                        "items, created_from_operation_id, "
                        "created_from_message_id, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            version.itinerary_version_id,
                            version.workspace_id,
                            assigned,
                            version.status.value,
                            version.title,
                            version.summary,
                            _items_to_json(version.items),
                            version.created_from_operation_id,
                            version.created_from_message_id,
                            _to_iso(version.created_at),
                        ),
                    )
                except sqlite3.IntegrityError as error:
                    raise PlannerStorageError(
                        "A planner itinerary version with this identity is "
                        "already recorded."
                    ) from error
        except sqlite3.Error as error:
            raise PlannerStorageError(
                "Could not persist the planner itinerary version."
            ) from error
        finally:
            connection.close()
        return dataclasses.replace(version, version_number=assigned)

    def get_itinerary_version(
        self, workspace_id: str, itinerary_version_id: str
    ) -> ItineraryVersion:
        """Return one itinerary version scoped to the workspace."""
        connection = self._connect()
        try:
            row = connection.execute(
                f"SELECT itinerary_version_id, workspace_id, version_number, "
                f"status, title, summary, items, created_from_operation_id, "
                f"created_from_message_id, created_at FROM {VERSION_TABLE} "
                "WHERE itinerary_version_id = ? AND workspace_id = ?",
                (itinerary_version_id, workspace_id),
            ).fetchone()
        except sqlite3.Error as error:
            raise PlannerStorageError(
                "Could not read the planner itinerary version."
            ) from error
        finally:
            connection.close()
        if row is None:
            raise PlannerNotFoundError(
                "The planner itinerary version does not exist in this workspace."
            )
        return self._row_to_version(row)

    def list_itinerary_versions(
        self, workspace_id: str, status: Optional[ItineraryStatus] = None
    ) -> tuple[ItineraryVersion, ...]:
        """Return workspace versions newest first, optionally filtered."""
        clauses = ["workspace_id = ?"]
        params: tuple[Any, ...] = (workspace_id,)
        if status is not None:
            clauses.append("status = ?")
            params += (status.value,)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT itinerary_version_id, workspace_id, version_number, "
                f"status, title, summary, items, created_from_operation_id, "
                f"created_from_message_id, created_at FROM {VERSION_TABLE} "
                f"WHERE {' AND '.join(clauses)} "
                "ORDER BY created_at DESC, rowid DESC",
                params,
            ).fetchall()
        except sqlite3.Error as error:
            raise PlannerStorageError(
                "Could not list the planner itinerary versions."
            ) from error
        finally:
            connection.close()
        return tuple(self._row_to_version(row) for row in rows)

    def accept_itinerary_version(
        self, workspace_id: str, itinerary_version_id: str
    ) -> ItineraryVersion:
        """Accept one version, superseding prior accepted ones atomically."""
        target = self.get_itinerary_version(workspace_id, itinerary_version_id)
        if target.status is ItineraryStatus.ACCEPTED:
            return target
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    f"UPDATE {VERSION_TABLE} SET status = ? "
                    "WHERE workspace_id = ? AND status = ?",
                    (
                        ItineraryStatus.SUPERSEDED.value,
                        workspace_id,
                        ItineraryStatus.ACCEPTED.value,
                    ),
                )
                updated = connection.execute(
                    f"UPDATE {VERSION_TABLE} SET status = ? "
                    "WHERE itinerary_version_id = ? AND workspace_id = ?",
                    (
                        ItineraryStatus.ACCEPTED.value,
                        itinerary_version_id,
                        workspace_id,
                    ),
                ).rowcount
                if updated != 1:
                    raise PlannerNotFoundError(
                        "The planner itinerary version does not exist in this "
                        "workspace."
                    )
        except sqlite3.Error as error:
            raise PlannerStorageError(
                "Could not accept the planner itinerary version."
            ) from error
        finally:
            connection.close()
        return self.get_itinerary_version(workspace_id, itinerary_version_id)

    def update_itinerary_status(
        self,
        workspace_id: str,
        itinerary_version_id: str,
        status: ItineraryStatus,
    ) -> ItineraryVersion:
        """Set one version status without lifecycle reasoning."""
        connection = self._connect()
        try:
            with connection:
                updated = connection.execute(
                    f"UPDATE {VERSION_TABLE} SET status = ? "
                    "WHERE itinerary_version_id = ? AND workspace_id = ?",
                    (status.value, itinerary_version_id, workspace_id),
                ).rowcount
                if updated != 1:
                    raise PlannerNotFoundError(
                        "The planner itinerary version does not exist in this "
                        "workspace."
                    )
        except sqlite3.Error as error:
            raise PlannerStorageError(
                "Could not update the planner itinerary version."
            ) from error
        finally:
            connection.close()
        return self.get_itinerary_version(workspace_id, itinerary_version_id)

    def create_decision(self, decision: TripDecision) -> TripDecision:
        """Persist a decision, superseding its cited target atomically."""
        connection = self._connect()
        try:
            with connection:
                if decision.supersedes_decision_id is not None:
                    flipped = connection.execute(
                        f"UPDATE {DECISION_TABLE} SET status = ? "
                        "WHERE decision_id = ? AND workspace_id = ?",
                        (
                            DecisionStatus.SUPERSEDED.value,
                            decision.supersedes_decision_id,
                            decision.workspace_id,
                        ),
                    ).rowcount
                    if flipped != 1:
                        raise PlannerNotFoundError(
                            "The superseded planner decision does not exist "
                            "in this workspace."
                        )
                try:
                    connection.execute(
                        f"INSERT INTO {DECISION_TABLE} (decision_id, "
                        "workspace_id, decision_type, status, statement, "
                        "rationale, source_message_id, supersedes_decision_id, "
                        "created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            decision.decision_id,
                            decision.workspace_id,
                            decision.decision_type.value,
                            decision.status.value,
                            decision.statement,
                            decision.rationale,
                            decision.source_message_id,
                            decision.supersedes_decision_id,
                            _to_iso(decision.created_at),
                            _to_iso(decision.updated_at),
                        ),
                    )
                except sqlite3.IntegrityError as error:
                    raise PlannerStorageError(
                        "A planner decision with this identity is already recorded."
                    ) from error
        except sqlite3.Error as error:
            if isinstance(error, PlannerRepositoryError):
                raise
            raise PlannerStorageError(
                "Could not persist the planner decision."
            ) from error
        finally:
            connection.close()
        return decision

    def get_decision(self, workspace_id: str, decision_id: str) -> TripDecision:
        """Return one decision scoped to the workspace."""
        connection = self._connect()
        try:
            row = connection.execute(
                f"SELECT decision_id, workspace_id, decision_type, status, "
                f"statement, rationale, source_message_id, "
                f"supersedes_decision_id, created_at, updated_at "
                f"FROM {DECISION_TABLE} "
                "WHERE decision_id = ? AND workspace_id = ?",
                (decision_id, workspace_id),
            ).fetchone()
        except sqlite3.Error as error:
            raise PlannerStorageError("Could not read the planner decision.") from error
        finally:
            connection.close()
        if row is None:
            raise PlannerNotFoundError(
                "The planner decision does not exist in this workspace."
            )
        return self._row_to_decision(row)

    def list_decisions(
        self,
        workspace_id: str,
        status: Optional[DecisionStatus] = None,
        decision_type: Optional[DecisionType] = None,
    ) -> tuple[TripDecision, ...]:
        """Return workspace decisions newest first, optionally filtered."""
        clauses = ["workspace_id = ?"]
        params: tuple[Any, ...] = (workspace_id,)
        if status is not None:
            clauses.append("status = ?")
            params += (status.value,)
        if decision_type is not None:
            clauses.append("decision_type = ?")
            params += (decision_type.value,)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT decision_id, workspace_id, decision_type, status, "
                f"statement, rationale, source_message_id, "
                f"supersedes_decision_id, created_at, updated_at "
                f"FROM {DECISION_TABLE} WHERE {' AND '.join(clauses)} "
                "ORDER BY created_at DESC, rowid DESC",
                params,
            ).fetchall()
        except sqlite3.Error as error:
            raise PlannerStorageError(
                "Could not list the planner decisions."
            ) from error
        finally:
            connection.close()
        return tuple(self._row_to_decision(row) for row in rows)

    def update_decision_status(
        self, workspace_id: str, decision_id: str, status: DecisionStatus
    ) -> TripDecision:
        """Set one decision status without lifecycle reasoning."""
        connection = self._connect()
        try:
            with connection:
                updated = connection.execute(
                    f"UPDATE {DECISION_TABLE} SET status = ? "
                    "WHERE decision_id = ? AND workspace_id = ?",
                    (status.value, decision_id, workspace_id),
                ).rowcount
                if updated != 1:
                    raise PlannerNotFoundError(
                        "The planner decision does not exist in this workspace."
                    )
        except sqlite3.Error as error:
            raise PlannerStorageError(
                "Could not update the planner decision."
            ) from error
        finally:
            connection.close()
        return self.get_decision(workspace_id, decision_id)

    def create_operation(self, operation: PlannerOperation) -> PlannerOperation:
        """Persist one planner operation row and return it."""
        connection = self._connect()
        try:
            with connection:
                try:
                    connection.execute(
                        f"INSERT INTO {OPERATION_TABLE} (operation_id, "
                        "workspace_id, conversation_id, operation_type, "
                        "status, input_summary, result_itinerary_version_id, "
                        "result_decision_id, source_message_id, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            operation.operation_id,
                            operation.workspace_id,
                            operation.conversation_id,
                            operation.operation_type.value,
                            operation.status.value,
                            operation.input_summary,
                            operation.result_itinerary_version_id,
                            operation.result_decision_id,
                            operation.source_message_id,
                            _to_iso(operation.created_at),
                        ),
                    )
                except sqlite3.IntegrityError as error:
                    raise PlannerStorageError(
                        "A planner operation with this identity is already recorded."
                    ) from error
        except sqlite3.Error as error:
            raise PlannerStorageError(
                "Could not persist the planner operation."
            ) from error
        finally:
            connection.close()
        return operation

    def list_operations(self, workspace_id: str) -> tuple[PlannerOperation, ...]:
        """Return workspace operations newest first."""
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT operation_id, workspace_id, conversation_id, "
                f"operation_type, status, input_summary, "
                f"result_itinerary_version_id, result_decision_id, "
                f"source_message_id, created_at FROM {OPERATION_TABLE} "
                "WHERE workspace_id = ? ORDER BY created_at DESC, rowid DESC",
                (workspace_id,),
            ).fetchall()
        except sqlite3.Error as error:
            raise PlannerStorageError(
                "Could not list the planner operations."
            ) from error
        finally:
            connection.close()
        return tuple(self._row_to_operation(row) for row in rows)

    def _row_to_version(self, row: tuple[Any, ...]) -> ItineraryVersion:
        try:
            return ItineraryVersion(
                itinerary_version_id=row[0],
                workspace_id=row[1],
                version_number=row[2],
                status=ItineraryStatus(row[3]),
                title=row[4],
                summary=row[5],
                items=_items_from_json(row[6]),
                created_from_operation_id=row[7],
                created_from_message_id=row[8],
                created_at=_from_iso(row[9], "created_at"),
            )
        except (PlannerValidationError, PlannerStorageError) as error:
            raise PlannerStorageError(
                "A stored planner itinerary version violates its contract."
            ) from error

    def _row_to_decision(self, row: tuple[Any, ...]) -> TripDecision:
        try:
            return TripDecision(
                decision_id=row[0],
                workspace_id=row[1],
                decision_type=DecisionType(row[2]),
                status=DecisionStatus(row[3]),
                statement=row[4],
                rationale=row[5],
                source_message_id=row[6],
                supersedes_decision_id=row[7],
                created_at=_from_iso(row[8], "created_at"),
                updated_at=_from_iso(row[9], "updated_at"),
            )
        except (PlannerValidationError, PlannerStorageError, ValueError) as error:
            raise PlannerStorageError(
                "A stored planner decision violates its contract."
            ) from error

    def _row_to_operation(self, row: tuple[Any, ...]) -> PlannerOperation:
        try:
            return PlannerOperation(
                operation_id=row[0],
                workspace_id=row[1],
                conversation_id=row[2],
                operation_type=PlannerOperationType(row[3]),
                status=PlannerOperationStatus(row[4]),
                input_summary=row[5],
                result_itinerary_version_id=row[6],
                result_decision_id=row[7],
                source_message_id=row[8],
                created_at=_from_iso(row[9], "created_at"),
            )
        except (PlannerValidationError, PlannerStorageError, ValueError) as error:
            raise PlannerStorageError(
                "A stored planner operation violates its contract."
            ) from error
