"""Local SQLite memory repository adapter for runtime milestone R5.

Per ADR 0006 this adapter is one of the few modules that knows SQLite exists.
It owns the memory table definitions, parameterized SQL, and SQLite error
handling. It registers `('memory', 1)` with the shared schema registry, so it
coexists with the workspace and conversation modules in one local database
file. It is accepted for local development and tests only; it is not a
production database commitment, and it settles no production migration,
backup, restore, concurrency, retention, or deletion policy.

Two properties are load-bearing:

1. **Candidate writes are atomic per call.** `create_candidates` inserts the
   whole batch inside one transaction, so a failing batch leaves no partial
   candidate rows behind the run's counts.
2. **A stored row that violates the contract fails closed.** Row mapping never
   coerces an unknown vocabulary value or an untyped timestamp into something
   plausible, and controlled errors never carry stored content.

Raised `MemoryStorageError` messages are safe for a controlled HTTP 500
response: they never include the local database path, full SQL text, or
message and candidate content.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from backend.memory.models import (
    MemoryCandidate,
    MemoryCandidateStatus,
    MemoryExtractionRun,
    MemoryExtractionTrigger,
    MemoryRunStatus,
    MemoryScope,
    MemoryType,
    PolicyReason,
    SensitivityLabel,
)
from backend.memory.repository import (
    MemoryAlreadyExistsError,
    MemoryStorageError,
)
from backend.storage.schema_registry import (
    SchemaRegistryError,
    open_application_database,
    register_module_schema,
)

logger = logging.getLogger("travel_agent_memory")

SCHEMA_VERSION = 1
SCHEMA_MODULE = "memory"
RUN_TABLE = "memory_extraction_runs"
CANDIDATE_TABLE = "memory_candidates"

_CREATE_RUN_TABLE = f"""
CREATE TABLE IF NOT EXISTS {RUN_TABLE} (
    run_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    trigger TEXT NOT NULL,
    extractor_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    candidate_count INTEGER NOT NULL,
    accepted_count INTEGER NOT NULL,
    rejected_count INTEGER NOT NULL,
    needs_user_action_count INTEGER NOT NULL,
    invalid_count INTEGER NOT NULL,
    failure_reason TEXT
)
"""

_CREATE_RUN_WORKSPACE_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_memory_runs_workspace_order
ON {RUN_TABLE} (workspace_id, started_at DESC, run_id ASC)
"""

_CREATE_RUN_CONVERSATION_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_memory_runs_conversation_order
ON {RUN_TABLE} (conversation_id, started_at DESC, run_id ASC)
"""

_CREATE_CANDIDATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {CANDIDATE_TABLE} (
    candidate_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    source_message_id TEXT NOT NULL,
    source_sequence INTEGER NOT NULL,
    proposed_scope TEXT NOT NULL,
    proposed_type TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
    sensitivity_label TEXT NOT NULL,
    text TEXT NOT NULL CHECK(length(text) <= 500),
    evidence_summary TEXT NOT NULL CHECK(length(evidence_summary) <= 240),
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, source_message_id, proposed_scope, proposed_type, text)
)
"""

_CREATE_CANDIDATE_RUN_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_memory_candidates_run_order
ON {CANDIDATE_TABLE} (run_id, source_sequence ASC, candidate_id ASC)
"""

_CREATE_CANDIDATE_WORKSPACE_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_memory_candidates_workspace_filter
ON {CANDIDATE_TABLE} (workspace_id, conversation_id, run_id)
"""

_INSERT_RUN = f"""
INSERT INTO {RUN_TABLE} (
    run_id, workspace_id, conversation_id, trigger, extractor_id,
    policy_id, status, started_at, finished_at, candidate_count,
    accepted_count, rejected_count, needs_user_action_count,
    invalid_count, failure_reason
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_RUN_COLUMNS = """
    run_id, workspace_id, conversation_id, trigger, extractor_id,
    policy_id, status, started_at, finished_at, candidate_count,
    accepted_count, rejected_count, needs_user_action_count,
    invalid_count, failure_reason
"""

_INSERT_CANDIDATE = f"""
INSERT INTO {CANDIDATE_TABLE} (
    candidate_id, run_id, workspace_id, conversation_id, source_message_id,
    source_sequence, proposed_scope, proposed_type, status, confidence,
    sensitivity_label, text, evidence_summary, reason, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_CANDIDATE_COLUMNS = """
    candidate_id, run_id, workspace_id, conversation_id, source_message_id,
    source_sequence, proposed_scope, proposed_type, status, confidence,
    sensitivity_label, text, evidence_summary, reason, created_at
"""

_RUN_EXISTS = f"SELECT 1 FROM {RUN_TABLE} WHERE run_id = ?"


def _to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _from_iso(value: Any, column: str) -> datetime:
    if not isinstance(value, str):
        raise MemoryStorageError(
            f"Stored memory column '{column}' is not a timestamp string."
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise MemoryStorageError(
            f"Stored memory column '{column}' is not a valid ISO timestamp."
        ) from error
    if parsed.tzinfo is None:
        raise MemoryStorageError(
            f"Stored memory column '{column}' is missing timezone information."
        )
    return parsed.astimezone(timezone.utc)


def _require_vocabulary(value: Any, column: str, enum_type: type) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise MemoryStorageError(
            f"Stored memory column '{column}' is outside the governed vocabulary."
        ) from error


def _create_memory_schema(connection: sqlite3.Connection) -> None:
    """Create both memory tables and all four indexes on first registration."""
    connection.execute(_CREATE_RUN_TABLE)
    connection.execute(_CREATE_RUN_WORKSPACE_INDEX)
    connection.execute(_CREATE_RUN_CONVERSATION_INDEX)
    connection.execute(_CREATE_CANDIDATE_TABLE)
    connection.execute(_CREATE_CANDIDATE_RUN_INDEX)
    connection.execute(_CREATE_CANDIDATE_WORKSPACE_INDEX)


class SQLiteMemoryRepository:
    """Persist shadow memory runs and candidates in the shared local database."""

    def __init__(self, db_path: Path) -> None:
        """Open or initialize memory storage in the shared application database.

        Raises:
            MemoryStorageError: The parent directory cannot be created, the
                database cannot be opened, the file is not owned by a build
                this one recognizes, or the recorded memory schema version is
                incompatible with `SCHEMA_VERSION`.
        """
        self._db_path = Path(db_path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        try:
            connection = open_application_database(self._db_path)
        except SchemaRegistryError as error:
            logger.error(
                "memory.storage unavailable module=%s failure_class=%s",
                SCHEMA_MODULE,
                type(error).__name__,
            )
            raise MemoryStorageError(
                "Could not open the local application database for memory storage."
            ) from error

        try:
            register_module_schema(
                connection, SCHEMA_MODULE, SCHEMA_VERSION, _create_memory_schema
            )
        except SchemaRegistryError as error:
            logger.error(
                "memory.storage schema mismatch module=%s version=%s failure_class=%s",
                SCHEMA_MODULE,
                SCHEMA_VERSION,
                type(error).__name__,
            )
            raise MemoryStorageError(
                "The local application database does not provide memory "
                f"schema version {SCHEMA_VERSION}. Refusing to migrate "
                "automatically."
            ) from error
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        try:
            return sqlite3.connect(self._db_path)
        except sqlite3.Error as error:
            raise MemoryStorageError(
                "Could not open the local memory database."
            ) from error

    def create_run(self, run: MemoryExtractionRun) -> MemoryExtractionRun:
        """Persist a new extraction run and return it."""
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    _INSERT_RUN,
                    (
                        run.run_id,
                        run.workspace_id,
                        run.conversation_id,
                        run.trigger.value,
                        run.extractor_id,
                        run.policy_id,
                        run.status.value,
                        _to_iso(run.started_at),
                        _to_iso(run.finished_at)
                        if run.finished_at is not None
                        else None,
                        run.candidate_count,
                        run.accepted_count,
                        run.rejected_count,
                        run.needs_user_action_count,
                        run.invalid_count,
                        run.failure_reason,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise MemoryAlreadyExistsError(
                "A memory extraction run with this identity already exists."
            ) from error
        except sqlite3.Error as error:
            raise MemoryStorageError(
                "Could not persist the memory extraction run."
            ) from error
        finally:
            connection.close()

        return run

    def create_candidates(
        self, candidates: Sequence[MemoryCandidate]
    ) -> tuple[MemoryCandidate, ...]:
        """Persist one batch of candidates atomically, in input order."""
        ordered = tuple(candidates)
        if not ordered:
            return ()

        connection = self._connect()
        try:
            with connection:
                for candidate in ordered:
                    exists = connection.execute(
                        _RUN_EXISTS, (candidate.run_id,)
                    ).fetchone()
                    if exists is None:
                        raise MemoryStorageError(
                            "A memory candidate references an unknown extraction run."
                        )
                connection.executemany(
                    _INSERT_CANDIDATE,
                    [
                        (
                            candidate.candidate_id,
                            candidate.run_id,
                            candidate.workspace_id,
                            candidate.conversation_id,
                            candidate.source_message_id,
                            candidate.source_sequence,
                            candidate.proposed_scope.value,
                            candidate.proposed_type.value,
                            candidate.status.value,
                            candidate.confidence,
                            candidate.sensitivity_label.value,
                            candidate.text,
                            candidate.evidence_summary,
                            candidate.reason.value,
                            _to_iso(candidate.created_at),
                        )
                        for candidate in ordered
                    ],
                )
        except sqlite3.IntegrityError as error:
            raise MemoryAlreadyExistsError(
                "A memory candidate with this identity has already been "
                "recorded for its extraction run."
            ) from error
        except sqlite3.Error as error:
            raise MemoryStorageError(
                "Could not persist the memory candidates."
            ) from error
        finally:
            connection.close()

        return ordered

    def list_runs(
        self, workspace_id: str, conversation_id: str | None = None
    ) -> tuple[MemoryExtractionRun, ...]:
        """Return runs for one workspace, newest first."""
        query = (
            f"SELECT {_RUN_COLUMNS} FROM {RUN_TABLE} "
            "WHERE workspace_id = ? "
            "ORDER BY started_at DESC, run_id ASC"
        )
        params: tuple[Any, ...] = (workspace_id,)
        if conversation_id is not None:
            query = (
                f"SELECT {_RUN_COLUMNS} FROM {RUN_TABLE} "
                "WHERE workspace_id = ? AND conversation_id = ? "
                "ORDER BY started_at DESC, run_id ASC"
            )
            params = (workspace_id, conversation_id)

        connection = self._connect()
        try:
            rows = connection.execute(query, params).fetchall()
        except sqlite3.Error as error:
            raise MemoryStorageError(
                "Could not list memory extraction runs."
            ) from error
        finally:
            connection.close()

        return tuple(self._row_to_run(row) for row in rows)

    def list_candidates(
        self,
        run_id: str | None = None,
        workspace_id: str | None = None,
        conversation_id: str | None = None,
    ) -> tuple[MemoryCandidate, ...]:
        """Return candidates matching every supplied filter."""
        if run_id is not None:
            query = (
                f"SELECT {_CANDIDATE_COLUMNS} FROM {CANDIDATE_TABLE} WHERE run_id = ? "
            )
            params: tuple[Any, ...] = (run_id,)
            clauses: list[str] = []
            if workspace_id is not None:
                clauses.append("workspace_id = ?")
                params += (workspace_id,)
            if conversation_id is not None:
                clauses.append("conversation_id = ?")
                params += (conversation_id,)
            if clauses:
                query += "AND " + " AND ".join(clauses) + " "
            query += "ORDER BY source_sequence ASC, candidate_id ASC"
        else:
            query = (
                f"SELECT {', '.join('c.' + column.strip() for column in _CANDIDATE_COLUMNS.split(','))} "
                f"FROM {CANDIDATE_TABLE} AS c "
                f"JOIN {RUN_TABLE} AS r ON c.run_id = r.run_id "
            )
            params = ()
            clauses = []
            if workspace_id is not None:
                clauses.append("c.workspace_id = ?")
                params += (workspace_id,)
            if conversation_id is not None:
                clauses.append("c.conversation_id = ?")
                params += (conversation_id,)
            if clauses:
                query += "WHERE " + " AND ".join(clauses) + " "
            query += (
                "ORDER BY r.started_at DESC, r.run_id ASC, "
                "c.source_sequence ASC, c.candidate_id ASC"
            )

        connection = self._connect()
        try:
            rows = connection.execute(query, params).fetchall()
        except sqlite3.Error as error:
            raise MemoryStorageError("Could not list memory candidates.") from error
        finally:
            connection.close()

        return tuple(self._row_to_candidate(row) for row in rows)

    def _row_to_run(self, row: tuple[Any, ...]) -> MemoryExtractionRun:
        try:
            return MemoryExtractionRun(
                run_id=row[0],
                workspace_id=row[1],
                conversation_id=row[2],
                trigger=_require_vocabulary(row[3], "trigger", MemoryExtractionTrigger),
                extractor_id=row[4],
                policy_id=row[5],
                status=_require_vocabulary(row[6], "status", MemoryRunStatus),
                started_at=_from_iso(row[7], "started_at"),
                finished_at=None
                if row[8] is None
                else _from_iso(row[8], "finished_at"),
                candidate_count=row[9],
                accepted_count=row[10],
                rejected_count=row[11],
                needs_user_action_count=row[12],
                invalid_count=row[13],
                failure_reason=row[14],
            )
        except MemoryStorageError:
            raise
        except Exception as error:
            raise MemoryStorageError(
                "A stored memory extraction run is outside the governed contract."
            ) from error

    def _row_to_candidate(self, row: tuple[Any, ...]) -> MemoryCandidate:
        try:
            return MemoryCandidate(
                candidate_id=row[0],
                run_id=row[1],
                workspace_id=row[2],
                conversation_id=row[3],
                source_message_id=row[4],
                source_sequence=row[5],
                proposed_scope=_require_vocabulary(
                    row[6], "proposed_scope", MemoryScope
                ),
                proposed_type=_require_vocabulary(row[7], "proposed_type", MemoryType),
                status=_require_vocabulary(row[8], "status", MemoryCandidateStatus),
                confidence=row[9],
                sensitivity_label=_require_vocabulary(
                    row[10], "sensitivity_label", SensitivityLabel
                ),
                text=row[11],
                evidence_summary=row[12],
                reason=_require_vocabulary(row[13], "reason", PolicyReason),
                created_at=_from_iso(row[14], "created_at"),
            )
        except MemoryStorageError:
            raise
        except Exception as error:
            raise MemoryStorageError(
                "A stored memory candidate is outside the governed contract."
            ) from error
