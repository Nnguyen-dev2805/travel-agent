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

Runtime milestone R6 adds a second schema module in the same adapter:
`memory_records` at version 1 holds answer-eligible records, promotion runs,
and retrieval events, while R5's `memory` module stays at version 1. Record
writes are atomic per call like candidate writes. Only rows still `active`
move to `superseded`, so a repeated suppression call cannot clobber a record
that already left the active state.

Raised `MemoryStorageError` messages are safe for a controlled HTTP 500
response: they never include the local database path, full SQL text, or
message and candidate content.
"""

from __future__ import annotations

import json
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
    MemoryPromotionRun,
    MemoryRecord,
    MemoryRecordScope,
    MemoryRecordStatus,
    MemoryRecordType,
    MemoryRunStatus,
    MemoryScope,
    MemorySelectionReason,
    MemorySelectionStatus,
    MemorySelectionTrace,
    MemoryType,
    PolicyReason,
    PromotionSkipCount,
    PromotionSkipReason,
    SensitivityLabel,
    utc_now,
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

RECORDS_SCHEMA_VERSION = 1
RECORDS_SCHEMA_MODULE = "memory_records"
RECORD_TABLE = "memory_records"
PROMOTION_RUN_TABLE = "memory_promotion_runs"
RETRIEVAL_EVENT_TABLE = "memory_retrieval_events"

_CREATE_RECORD_TABLE = f"""
CREATE TABLE IF NOT EXISTS {RECORD_TABLE} (
    memory_id TEXT PRIMARY KEY,
    source_candidate_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    source_message_id TEXT NOT NULL,
    source_sequence INTEGER NOT NULL,
    owner_user_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    status TEXT NOT NULL,
    text TEXT NOT NULL CHECK(length(text) <= 500),
    confidence REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
    sensitivity_label TEXT NOT NULL,
    supersedes_memory_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT,
    UNIQUE(source_candidate_id)
)
"""

_CREATE_RECORD_SCOPE_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_memory_records_scope_filter
ON {RECORD_TABLE} (workspace_id, conversation_id, scope, status)
"""

_CREATE_RECORD_OWNER_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_memory_records_owner_filter
ON {RECORD_TABLE} (owner_user_id, scope, status)
"""

_CREATE_RECORD_CANDIDATE_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_memory_records_candidate
ON {RECORD_TABLE} (source_candidate_id)
"""

_CREATE_PROMOTION_RUN_TABLE = f"""
CREATE TABLE IF NOT EXISTS {PROMOTION_RUN_TABLE} (
    promotion_run_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    conversation_id TEXT,
    source_candidate_count INTEGER NOT NULL,
    promoted_count INTEGER NOT NULL,
    skipped_count INTEGER NOT NULL,
    skip_reasons TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
)
"""

_CREATE_RETRIEVAL_EVENT_TABLE = f"""
CREATE TABLE IF NOT EXISTS {RETRIEVAL_EVENT_TABLE} (
    trace_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    conversation_id TEXT,
    gate_enabled INTEGER NOT NULL,
    status TEXT NOT NULL,
    selected_ids TEXT NOT NULL,
    reasons TEXT NOT NULL,
    eligible_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
)
"""

_CREATE_RETRIEVAL_EVENT_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_memory_retrieval_events_scope
ON {RETRIEVAL_EVENT_TABLE} (workspace_id, conversation_id, created_at DESC, trace_id ASC)
"""

_INSERT_RECORD = f"""
INSERT INTO {RECORD_TABLE} (
    memory_id, source_candidate_id, workspace_id, conversation_id,
    source_message_id, source_sequence, owner_user_id, scope, scope_id,
    memory_type, status, text, confidence, sensitivity_label,
    supersedes_memory_id, created_at, updated_at, expires_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_RECORD_COLUMNS = """
    memory_id, source_candidate_id, workspace_id, conversation_id,
    source_message_id, source_sequence, owner_user_id, scope, scope_id,
    memory_type, status, text, confidence, sensitivity_label,
    supersedes_memory_id, created_at, updated_at, expires_at
"""

_MARK_SUPERSEDED = (
    f"UPDATE {RECORD_TABLE} SET status = ?, updated_at = ? "
    "WHERE memory_id = ? AND status = ?"
)

_INSERT_PROMOTION_RUN = f"""
INSERT INTO {PROMOTION_RUN_TABLE} (
    promotion_run_id, workspace_id, conversation_id, source_candidate_count,
    promoted_count, skipped_count, skip_reasons, started_at, finished_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_PROMOTION_RUN_COLUMNS = """
    promotion_run_id, workspace_id, conversation_id, source_candidate_count,
    promoted_count, skipped_count, skip_reasons, started_at, finished_at
"""

_INSERT_RETRIEVAL_EVENT = f"""
INSERT INTO {RETRIEVAL_EVENT_TABLE} (
    trace_id, workspace_id, conversation_id, gate_enabled, status,
    selected_ids, reasons, eligible_count, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_RETRIEVAL_EVENT_COLUMNS = """
    trace_id, workspace_id, conversation_id, gate_enabled, status,
    selected_ids, reasons, eligible_count, created_at
"""

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


def _create_record_schema(connection: sqlite3.Connection) -> None:
    """Create record, promotion run, and retrieval event tables on first use."""
    connection.execute(_CREATE_RECORD_TABLE)
    connection.execute(_CREATE_RECORD_SCOPE_INDEX)
    connection.execute(_CREATE_RECORD_OWNER_INDEX)
    connection.execute(_CREATE_RECORD_CANDIDATE_INDEX)
    connection.execute(_CREATE_PROMOTION_RUN_TABLE)
    connection.execute(_CREATE_RETRIEVAL_EVENT_TABLE)
    connection.execute(_CREATE_RETRIEVAL_EVENT_INDEX)


def _skip_reasons_to_json(reasons: Sequence[PromotionSkipCount]) -> str:
    return json.dumps(
        {item.reason.value: item.count for item in reasons}, sort_keys=True
    )


def _skip_reasons_from_json(value: Any) -> tuple[PromotionSkipCount, ...]:
    if not isinstance(value, str):
        raise MemoryStorageError(
            "Stored memory column 'skip_reasons' is not a JSON string."
        )
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise MemoryStorageError(
            "Stored memory column 'skip_reasons' is not valid JSON."
        ) from error
    if not isinstance(parsed, dict):
        raise MemoryStorageError(
            "Stored memory column 'skip_reasons' is not a reason mapping."
        )
    try:
        return tuple(
            PromotionSkipCount(PromotionSkipReason(reason), int(count))
            for reason, count in sorted(parsed.items())
        )
    except (ValueError, TypeError) as error:
        raise MemoryStorageError(
            "Stored memory column 'skip_reasons' is outside the governed vocabulary."
        ) from error


def _string_list_to_json(values: Sequence[str]) -> str:
    return json.dumps(list(values))


def _string_list_from_json(value: Any, column: str) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise MemoryStorageError(
            f"Stored memory column '{column}' is not a JSON string."
        )
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise MemoryStorageError(
            f"Stored memory column '{column}' is not valid JSON."
        ) from error
    if not isinstance(parsed, list) or not all(
        isinstance(item, str) for item in parsed
    ):
        raise MemoryStorageError(
            f"Stored memory column '{column}' is not a string list."
        )
    return tuple(parsed)


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
            self._register(
                connection,
                SCHEMA_MODULE,
                SCHEMA_VERSION,
                _create_memory_schema,
            )
            self._register(
                connection,
                RECORDS_SCHEMA_MODULE,
                RECORDS_SCHEMA_VERSION,
                _create_record_schema,
            )
        finally:
            connection.close()

    @staticmethod
    def _register(connection, module: str, version: int, create) -> None:
        try:
            register_module_schema(connection, module, version, create)
        except SchemaRegistryError as error:
            logger.error(
                "memory.storage schema mismatch module=%s version=%s failure_class=%s",
                module,
                version,
                type(error).__name__,
            )
            raise MemoryStorageError(
                f"The local application database does not provide {module} "
                f"schema version {version}. Refusing to migrate "
                "automatically."
            ) from error

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

    def create_promotion_run(self, run: MemoryPromotionRun) -> MemoryPromotionRun:
        """Persist a new promotion run and return it."""
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    _INSERT_PROMOTION_RUN,
                    (
                        run.promotion_run_id,
                        run.workspace_id,
                        run.conversation_id,
                        run.source_candidate_count,
                        run.promoted_count,
                        run.skipped_count,
                        _skip_reasons_to_json(run.skip_reasons),
                        _to_iso(run.started_at),
                        _to_iso(run.finished_at),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise MemoryAlreadyExistsError(
                "A memory promotion run with this identity already exists."
            ) from error
        except sqlite3.Error as error:
            raise MemoryStorageError(
                "Could not persist the memory promotion run."
            ) from error
        finally:
            connection.close()

        return run

    def create_records(
        self, records: Sequence[MemoryRecord]
    ) -> tuple[MemoryRecord, ...]:
        """Persist answer-eligible records atomically, in input order."""
        ordered = tuple(records)
        if not ordered:
            return ()

        connection = self._connect()
        try:
            with connection:
                connection.executemany(
                    _INSERT_RECORD,
                    [
                        (
                            record.memory_id,
                            record.source_candidate_id,
                            record.workspace_id,
                            record.conversation_id,
                            record.source_message_id,
                            record.source_sequence,
                            record.owner_user_id,
                            record.scope.value,
                            record.scope_id,
                            record.memory_type.value,
                            record.status.value,
                            record.text,
                            record.confidence,
                            record.sensitivity_label.value,
                            record.supersedes_memory_id,
                            _to_iso(record.created_at),
                            _to_iso(record.updated_at),
                            _to_iso(record.expires_at)
                            if record.expires_at is not None
                            else None,
                        )
                        for record in ordered
                    ],
                )
        except sqlite3.IntegrityError as error:
            raise MemoryAlreadyExistsError(
                "A memory record with this identity or source candidate has "
                "already been recorded."
            ) from error
        except sqlite3.Error as error:
            raise MemoryStorageError("Could not persist the memory records.") from error
        finally:
            connection.close()

        return ordered

    def list_records(
        self,
        workspace_id: str | None = None,
        conversation_id: str | None = None,
        owner_user_id: str | None = None,
        scope: MemoryRecordScope | str | None = None,
        status: MemoryRecordStatus | str | None = None,
    ) -> tuple[MemoryRecord, ...]:
        """Return records matching every supplied filter, oldest first."""
        query = f"SELECT {_RECORD_COLUMNS} FROM {RECORD_TABLE} "
        params: tuple[Any, ...] = ()
        clauses: list[str] = []
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params += (workspace_id,)
        if conversation_id is not None:
            clauses.append("conversation_id = ?")
            params += (conversation_id,)
        if owner_user_id is not None:
            clauses.append("owner_user_id = ?")
            params += (owner_user_id,)
        if scope is not None:
            clauses.append("scope = ?")
            params += (getattr(scope, "value", scope),)
        if status is not None:
            clauses.append("status = ?")
            params += (getattr(status, "value", status),)
        if clauses:
            query += "WHERE " + " AND ".join(clauses) + " "
        query += "ORDER BY created_at ASC, memory_id ASC"

        connection = self._connect()
        try:
            rows = connection.execute(query, params).fetchall()
        except sqlite3.Error as error:
            raise MemoryStorageError("Could not list memory records.") from error
        finally:
            connection.close()

        return tuple(self._row_to_record(row) for row in rows)

    def mark_records_superseded(self, memory_ids: Sequence[str]) -> int:
        """Flip active records to superseded; return the flipped count."""
        identities = tuple(memory_ids)
        if not identities:
            return 0

        connection = self._connect()
        try:
            with connection:
                cursor = connection.executemany(
                    _MARK_SUPERSEDED,
                    [
                        (
                            MemoryRecordStatus.SUPERSEDED.value,
                            _to_iso(utc_now()),
                            memory_id,
                            MemoryRecordStatus.ACTIVE.value,
                        )
                        for memory_id in identities
                    ],
                )
                flipped = cursor.rowcount
        except sqlite3.Error as error:
            raise MemoryStorageError(
                "Could not supersede the memory records."
            ) from error
        finally:
            connection.close()

        return flipped if flipped >= 0 else 0

    def write_retrieval_event(
        self, trace: MemorySelectionTrace
    ) -> MemorySelectionTrace:
        """Persist one retrieval event and return it."""
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    _INSERT_RETRIEVAL_EVENT,
                    (
                        trace.trace_id,
                        trace.workspace_id,
                        trace.conversation_id,
                        int(trace.gate_enabled),
                        trace.status.value,
                        _string_list_to_json(trace.selected_ids),
                        _string_list_to_json(
                            [reason.value for reason in trace.reasons]
                        ),
                        trace.eligible_count,
                        _to_iso(trace.created_at),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise MemoryAlreadyExistsError(
                "A memory retrieval event with this identity already exists."
            ) from error
        except sqlite3.Error as error:
            raise MemoryStorageError(
                "Could not persist the memory retrieval event."
            ) from error
        finally:
            connection.close()

        return trace

    def list_retrieval_events(
        self,
        workspace_id: str | None = None,
        conversation_id: str | None = None,
    ) -> tuple[MemorySelectionTrace, ...]:
        """Return retrieval events for the supplied filters, newest first."""
        query = f"SELECT {_RETRIEVAL_EVENT_COLUMNS} FROM {RETRIEVAL_EVENT_TABLE} "
        params: tuple[Any, ...] = ()
        clauses: list[str] = []
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params += (workspace_id,)
        if conversation_id is not None:
            clauses.append("conversation_id = ?")
            params += (conversation_id,)
        if clauses:
            query += "WHERE " + " AND ".join(clauses) + " "
        query += "ORDER BY created_at DESC, trace_id ASC"

        connection = self._connect()
        try:
            rows = connection.execute(query, params).fetchall()
        except sqlite3.Error as error:
            raise MemoryStorageError(
                "Could not list memory retrieval events."
            ) from error
        finally:
            connection.close()

        return tuple(self._row_to_trace(row) for row in rows)

    def _row_to_record(self, row: tuple[Any, ...]) -> MemoryRecord:
        try:
            return MemoryRecord(
                memory_id=row[0],
                source_candidate_id=row[1],
                workspace_id=row[2],
                conversation_id=row[3],
                source_message_id=row[4],
                source_sequence=row[5],
                owner_user_id=row[6],
                scope=_require_vocabulary(row[7], "scope", MemoryRecordScope),
                scope_id=row[8],
                memory_type=_require_vocabulary(
                    row[9], "memory_type", MemoryRecordType
                ),
                status=_require_vocabulary(row[10], "status", MemoryRecordStatus),
                text=row[11],
                confidence=row[12],
                sensitivity_label=_require_vocabulary(
                    row[13], "sensitivity_label", SensitivityLabel
                ),
                supersedes_memory_id=row[14],
                created_at=_from_iso(row[15], "created_at"),
                updated_at=_from_iso(row[16], "updated_at"),
                expires_at=None
                if row[17] is None
                else _from_iso(row[17], "expires_at"),
            )
        except MemoryStorageError:
            raise
        except Exception as error:
            raise MemoryStorageError(
                "A stored memory record is outside the governed contract."
            ) from error

    def _row_to_promotion_run(self, row: tuple[Any, ...]) -> MemoryPromotionRun:
        try:
            return MemoryPromotionRun(
                promotion_run_id=row[0],
                workspace_id=row[1],
                conversation_id=row[2],
                source_candidate_count=row[3],
                promoted_count=row[4],
                skipped_count=row[5],
                skip_reasons=_skip_reasons_from_json(row[6]),
                started_at=_from_iso(row[7], "started_at"),
                finished_at=_from_iso(row[8], "finished_at"),
            )
        except MemoryStorageError:
            raise
        except Exception as error:
            raise MemoryStorageError(
                "A stored memory promotion run is outside the governed contract."
            ) from error

    def _row_to_trace(self, row: tuple[Any, ...]) -> MemorySelectionTrace:
        try:
            gate_enabled = row[3]
            if gate_enabled not in (0, 1):
                raise MemoryStorageError(
                    "Stored memory column 'gate_enabled' is not a boolean."
                )
            reasons = tuple(
                _require_vocabulary(value, "reasons", MemorySelectionReason)
                for value in _string_list_from_json(row[6], "reasons")
            )
            return MemorySelectionTrace(
                trace_id=row[0],
                workspace_id=row[1],
                conversation_id=row[2],
                gate_enabled=bool(gate_enabled),
                status=_require_vocabulary(row[4], "status", MemorySelectionStatus),
                selected_ids=_string_list_from_json(row[5], "selected_ids"),
                reasons=reasons,
                eligible_count=row[7],
                created_at=_from_iso(row[8], "created_at"),
            )
        except MemoryStorageError:
            raise
        except Exception as error:
            raise MemoryStorageError(
                "A stored memory retrieval event is outside the governed contract."
            ) from error
