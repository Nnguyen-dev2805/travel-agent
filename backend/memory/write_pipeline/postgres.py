"""PostgreSQL unit-of-work adapter for resolved memory changes.

One `apply_memory_change` call runs a single READ COMMITTED transaction:
tenant binding, owner authorization, idempotency lookup, assertion
insert-or-resolve with a row lock, fresh re-read of current versions,
staleness and concurrency checks, then atomic immutable inserts for
evidence, decision, version, trace event, and outbox. Identifiers and
timestamps are stamped here because drafts arrive without them. No
model or network call occurs inside the transaction.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    ARRAY,
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    Table,
    Text,
    exc as sa_exc,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection, Engine

from backend.memory.write_pipeline.models import (
    AssertionIdentity,
    DecisionOutcome,
    MemoryChangeSet,
    MemoryDecisionDraft,
    MemoryEvidence,
    MemoryOperation,
    MemoryVersion,
    MemoryVersionDraft,
    new_version_id,
)
from backend.memory.write_pipeline.uow import (
    ConcurrentWriteError,
    CrossOwnerDeniedError,
    MemoryUnitOfWork,
    MemoryWriteError,
    MemoryWriteResult,
    StaleVersionError,
)
from backend.memory.write_pipeline.service import (
    DELETION_TARGET_TYPE,
    MemoryCommandNotFoundError,
    MemoryCommandStaleError,
    UndoDescriptor,
)
from backend.security.models import AuthenticatedPrincipal
from backend.storage.postgres import (
    require_tenant_context,
    set_tenant,
    transaction,
)

logger = logging.getLogger("travel_agent_memory_write")

metadata = MetaData()

assertions_table = Table(
    "memory_assertions",
    metadata,
    Column("assertion_id", Text(), primary_key=True),
    Column("owner_user_id", Text(), nullable=False),
    Column("scope", Text(), nullable=False),
    Column("scope_id", Text(), nullable=False),
    Column("canonical_key", Text(), nullable=False),
    Column("subject_key", Text(), nullable=False),
    Column("condition_fingerprint", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

versions_table = Table(
    "memory_versions",
    metadata,
    Column("version_id", Text(), primary_key=True),
    Column(
        "assertion_id",
        Text(),
        ForeignKey("memory_assertions.assertion_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("owner_user_id", Text(), nullable=False),
    Column("normalized_value", Text(), nullable=False),
    Column("value_payload", JSONB(), nullable=False),
    Column("authority", Text(), nullable=False),
    Column("sensitivity", Text(), nullable=False),
    Column("status", Text(), nullable=False),
    Column("valid_from", DateTime(timezone=True), nullable=False),
    Column("supersedes_version_id", Text(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

evidence_table = Table(
    "memory_evidence",
    metadata,
    Column("evidence_id", Text(), primary_key=True),
    Column(
        "assertion_id",
        Text(),
        ForeignKey("memory_assertions.assertion_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("owner_user_id", Text(), nullable=False),
    Column("conversation_id", Text(), nullable=False),
    Column("source_message_id", Text(), nullable=False),
    Column("display_text", Text(), nullable=False),
    Column("authority", Text(), nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

decisions_table = Table(
    "memory_decisions",
    metadata,
    Column("decision_id", Text(), primary_key=True),
    Column("candidate_id", Text(), nullable=False),
    Column(
        "assertion_id",
        Text(),
        ForeignKey("memory_assertions.assertion_id", ondelete="CASCADE"),
        nullable=True,
    ),
    Column("owner_user_id", Text(), nullable=False),
    Column("outcome", Text(), nullable=False),
    Column("reason", Text(), nullable=False),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

events_table = Table(
    "memory_events",
    metadata,
    Column("event_id", Text(), primary_key=True),
    Column("owner_user_id", Text(), nullable=False),
    Column("event_type", Text(), nullable=False),
    Column(
        "assertion_id",
        Text(),
        ForeignKey("memory_assertions.assertion_id", ondelete="CASCADE"),
        nullable=True,
    ),
    Column("version_id", Text(), nullable=True),
    Column("reason_code", Text(), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)

outbox_table = Table(
    "memory_outbox",
    metadata,
    Column("outbox_id", Text(), primary_key=True),
    Column("owner_user_id", Text(), nullable=False),
    Column("event_type", Text(), nullable=False),
    Column("payload", JSONB(), nullable=False),
    Column("status", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

idempotency_table = Table(
    "memory_write_idempotency",
    metadata,
    Column("idempotency_key", Text(), primary_key=True),
    Column("owner_user_id", Text(), nullable=False),
    Column("operation", Text(), nullable=False),
    Column("version_id", Text(), nullable=True),
    Column("decision_id", Text(), nullable=True),
    Column("superseded_version_ids", ARRAY(Text()), nullable=False),
    Column("reference_version_id", Text(), nullable=True),
    Column("reason_code", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

_EVENT_ID_PREFIX = "mevt_"
_OUTBOX_ID_PREFIX = "mout_"
_DECISION_ID_PREFIX = "mdc_"
_ASSERTION_ID_PREFIX = "mas_"

_MAX_ATTEMPTS = 3
_RETRYABLE_PGCODES = frozenset({"40001", "40P01"})
_UNIQUE_PGCODE = "23505"

_WRITING_OPERATIONS = frozenset(
    {
        MemoryOperation.ADD,
        MemoryOperation.SUPERSEDE,
        MemoryOperation.ADD_EXCEPTION,
        MemoryOperation.REINFORCE,
        MemoryOperation.PENDING_CONFLICT,
    }
)


def _pgcode(error: Exception) -> str | None:
    return getattr(getattr(error, "orig", None), "pgcode", None)


def read_current_versions(
    engine: Engine, identity: AssertionIdentity
) -> tuple[MemoryVersion, ...]:
    """Return stored versions for one identity, oldest first."""
    with engine.connect() as connection:
        rows = (
            connection.execute(
                select(versions_table)
                .where(
                    versions_table.c.assertion_id.in_(
                        select(assertions_table.c.assertion_id).where(
                            assertions_table.c.owner_user_id == identity.owner_user_id,
                            assertions_table.c.scope == identity.scope.value,
                            assertions_table.c.scope_id == identity.scope_id,
                            assertions_table.c.canonical_key == identity.canonical_key,
                            assertions_table.c.subject_key == identity.subject_key,
                            assertions_table.c.condition_fingerprint
                            == identity.condition_fingerprint,
                        )
                    )
                )
                .order_by(
                    versions_table.c.valid_from.asc(),
                    versions_table.c.version_id.asc(),
                )
            )
            .mappings()
            .fetchall()
        )
    return tuple(
        MemoryVersion(
            version_id=row["version_id"],
            owner_user_id=row["owner_user_id"],
            scope=identity.scope,
            scope_id=identity.scope_id,
            canonical_key=identity.canonical_key,
            subject_key=identity.subject_key,
            condition_fingerprint=identity.condition_fingerprint,
            normalized_value=row["normalized_value"],
            display_text=row["value_payload"]["display_text"],
            authority=row["authority"],
            sensitivity=row["sensitivity"],
            status=row["status"],
            valid_from=row["valid_from"],
            supersedes_version_id=row["supersedes_version_id"],
        )
        for row in rows
    )


class PostgresMemoryUnitOfWork(MemoryUnitOfWork):
    """Apply resolved changes atomically against PostgreSQL."""

    def __init__(self, engine: Engine, *, max_attempts: int = _MAX_ATTEMPTS) -> None:
        """Bind to an existing engine; schema comes from Alembic, not here."""
        self._engine = engine
        self._max_attempts = max_attempts

    def apply_memory_change(
        self,
        change,
        principal: AuthenticatedPrincipal,
        *,
        evidence: tuple[MemoryEvidence, ...] = (),
        decision: MemoryDecisionDraft | None = None,
        idempotency_key: str | None = None,
        expected_version_id: str | None = None,
    ) -> MemoryWriteResult:
        """Apply one change with bounded retry on write contention."""
        self._check_inputs(change, principal, evidence, decision, idempotency_key)
        if change.identity is None:
            if change.operation in (MemoryOperation.REJECT, MemoryOperation.NOOP):
                return MemoryWriteResult(
                    operation=change.operation,
                    version_id=None,
                    superseded_version_ids=(),
                    reference_version_id=None,
                    decision_id=None,
                    reason=change.reason,
                )
            raise MemoryWriteError("A mutating change requires an assertion identity.")
        if change.identity.owner_user_id != principal.owner_user_id:
            raise CrossOwnerDeniedError(
                "The change does not belong to this owner scope."
            )
        last_error: Exception | None = None
        for _ in range(self._max_attempts):
            try:
                with transaction(self._engine) as connection:
                    return self._apply_once(
                        connection,
                        change,
                        principal,
                        evidence,
                        decision,
                        idempotency_key,
                        expected_version_id,
                    )
            except MemoryWriteError:
                raise
            except sa_exc.IntegrityError as error:
                last_error = error
                if _pgcode(error) != _UNIQUE_PGCODE:
                    raise MemoryWriteError(
                        "The memory write violated a storage constraint."
                    ) from error
            except sa_exc.DBAPIError as error:
                last_error = error
                if _pgcode(error) not in _RETRYABLE_PGCODES:
                    raise MemoryWriteError(
                        "The memory write could not reach storage."
                    ) from error
        raise ConcurrentWriteError(
            "A concurrent writer won the assertion; re-resolve and retry."
        ) from last_error

    @staticmethod
    def _check_inputs(change, principal, evidence, decision, idempotency_key) -> None:
        if not isinstance(change, MemoryChangeSet):
            raise MemoryWriteError("apply_memory_change requires a MemoryChangeSet.")
        if not isinstance(principal, AuthenticatedPrincipal):
            raise MemoryWriteError(
                "apply_memory_change requires an AuthenticatedPrincipal."
            )
        if not isinstance(evidence, tuple) or not all(
            isinstance(item, MemoryEvidence) for item in evidence
        ):
            raise MemoryWriteError("Evidence must be a tuple of MemoryEvidence.")
        if decision is not None and not isinstance(decision, MemoryDecisionDraft):
            raise MemoryWriteError("A decision must be a MemoryDecisionDraft or null.")
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str) or not idempotency_key.strip()
        ):
            raise MemoryWriteError("An idempotency key must be non-blank text.")

    def _apply_once(
        self,
        connection: Connection,
        change,
        principal: AuthenticatedPrincipal,
        evidence: tuple[MemoryEvidence, ...],
        decision,
        idempotency_key: str | None,
        expected_version_id: str | None,
    ) -> MemoryWriteResult:
        owner = principal.owner_user_id
        set_tenant(connection, owner)
        require_tenant_context(connection)
        identity = change.identity
        assert identity is not None  # narrowed by the caller

        operation = change.operation
        if operation is MemoryOperation.REJECT:
            return MemoryWriteResult(
                operation=operation,
                version_id=None,
                superseded_version_ids=(),
                reference_version_id=None,
                decision_id=None,
                reason=change.reason,
            )
        if operation is MemoryOperation.NOOP and (
            decision is None or decision.outcome == DecisionOutcome.DIRECT_WRITE
        ):
            return MemoryWriteResult(
                operation=operation,
                version_id=None,
                superseded_version_ids=(),
                reference_version_id=None,
                decision_id=None,
                reason=change.reason,
            )

        if idempotency_key is not None:
            prior = self._lookup_idempotency(connection, idempotency_key, owner)
            if prior is not None:
                return prior

        assertion_id = self._resolve_assertion(connection, identity, owner)
        fresh = self._read_locked_versions(connection, assertion_id)
        active_ids = tuple(
            row["version_id"] for row in fresh if row["status"] == "active"
        )
        if expected_version_id is not None:
            current = active_ids[0] if active_ids else None
            if current != expected_version_id:
                raise StaleVersionError(
                    "The expected current version no longer matches stored state."
                )

        operation = change.operation
        if operation in (MemoryOperation.ADD, MemoryOperation.ADD_EXCEPTION):
            if active_ids:
                raise ConcurrentWriteError(
                    "The assertion already has a current version; re-resolve."
                )
            version_id = self._insert_version_row(
                connection, change.new_version, assertion_id, owner
            )
            superseded: tuple[str, ...] = ()
            reference = change.reference_version_id
        elif operation is MemoryOperation.SUPERSEDE:
            if not change.superseded_version_ids:
                raise ConcurrentWriteError(
                    "The supersession target is gone; re-resolve."
                )
            # Flip first, then insert: the one-current-version index
            # forbids two live rows even momentarily inside the txn.
            superseded = self._mark_versions_superseded(
                connection, assertion_id, change.superseded_version_ids
            )
            version_id = self._insert_version_row(
                connection, change.new_version, assertion_id, owner
            )
            reference = None
        elif operation is MemoryOperation.REINFORCE:
            if change.reference_version_id not in active_ids:
                raise ConcurrentWriteError(
                    "The reinforced version is gone; re-resolve."
                )
            version_id = None
            superseded = ()
            reference = change.reference_version_id
        elif operation in (MemoryOperation.PENDING_CONFLICT, MemoryOperation.NOOP):
            version_id = None
            superseded = ()
            reference = None
        else:  # pragma: no cover - closed operation vocabulary
            raise MemoryWriteError("An unknown memory operation cannot be applied.")

        for item in evidence:
            if item.owner_user_id != owner:
                raise CrossOwnerDeniedError(
                    "Evidence does not belong to this owner scope."
                )
        self._insert_evidence_rows(connection, assertion_id, owner, evidence)
        decision_id: str | None = None
        if decision is not None:
            decision_id = self._insert_decision_row(
                connection, decision, assertion_id, owner
            )
        self._insert_event_row(
            connection, owner, assertion_id, version_id or reference, change.reason
        )
        self._insert_outbox_row(
            connection, owner, assertion_id, version_id or reference, change
        )
        return self._finish(
            connection,
            change,
            owner,
            assertion_id,
            version_id,
            superseded,
            reference,
            decision_id,
            idempotency_key,
        )

    def _lookup_idempotency(
        self, connection: Connection, key: str, owner: str
    ) -> MemoryWriteResult | None:
        row = (
            connection.execute(
                select(idempotency_table).where(
                    idempotency_table.c.idempotency_key == key
                )
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        if row["owner_user_id"] != owner:
            raise CrossOwnerDeniedError(
                "The idempotency key does not belong to this owner scope."
            )
        return MemoryWriteResult(
            operation=MemoryOperation(row["operation"]),
            version_id=row["version_id"],
            superseded_version_ids=tuple(row["superseded_version_ids"] or ()),
            reference_version_id=row["reference_version_id"],
            decision_id=row["decision_id"],
            reason=row["reason_code"],
        )

    def _resolve_assertion(self, connection: Connection, identity, owner: str) -> str:
        row = (
            connection.execute(
                select(assertions_table.c.assertion_id).where(
                    assertions_table.c.owner_user_id == owner,
                    assertions_table.c.scope == identity.scope.value,
                    assertions_table.c.scope_id == identity.scope_id,
                    assertions_table.c.canonical_key == identity.canonical_key,
                    assertions_table.c.subject_key == identity.subject_key,
                    assertions_table.c.condition_fingerprint
                    == identity.condition_fingerprint,
                )
            )
            .mappings()
            .fetchone()
        )
        if row is not None:
            locked = (
                connection.execute(
                    select(assertions_table.c.assertion_id)
                    .where(assertions_table.c.assertion_id == row["assertion_id"])
                    .with_for_update()
                )
                .mappings()
                .fetchone()
            )
            assert locked is not None
            return row["assertion_id"]
        now = datetime.now(timezone.utc)
        assertion_id = f"mas_{uuid.uuid4().hex}"
        try:
            # Savepoint: on a lost insert race only this statement rolls
            # back, so the re-read below runs in a usable transaction.
            with connection.begin_nested():
                connection.execute(
                    assertions_table.insert().values(
                        assertion_id=assertion_id,
                        owner_user_id=owner,
                        scope=identity.scope.value,
                        scope_id=identity.scope_id,
                        canonical_key=identity.canonical_key,
                        subject_key=identity.subject_key,
                        condition_fingerprint=identity.condition_fingerprint,
                        created_at=now,
                        updated_at=now,
                    )
                )
        except sa_exc.IntegrityError:
            existing = (
                connection.execute(
                    select(assertions_table.c.assertion_id).where(
                        assertions_table.c.owner_user_id == owner,
                        assertions_table.c.scope == identity.scope.value,
                        assertions_table.c.scope_id == identity.scope_id,
                        assertions_table.c.canonical_key == identity.canonical_key,
                        assertions_table.c.subject_key == identity.subject_key,
                        assertions_table.c.condition_fingerprint
                        == identity.condition_fingerprint,
                    )
                )
                .mappings()
                .fetchone()
            )
            if existing is None:  # pragma: no cover - lost race with deleter
                raise
            assertion_id = existing["assertion_id"]
        connection.execute(
            select(assertions_table.c.assertion_id)
            .where(assertions_table.c.assertion_id == assertion_id)
            .with_for_update()
        ).fetchone()
        return assertion_id

    def _read_locked_versions(self, connection: Connection, assertion_id: str) -> tuple:
        return tuple(
            connection.execute(
                select(versions_table.c.version_id, versions_table.c.status).where(
                    versions_table.c.assertion_id == assertion_id
                )
            )
            .mappings()
            .fetchall()
        )

    def _insert_evidence_rows(
        self,
        connection: Connection,
        assertion_id: str,
        owner: str,
        evidence: tuple[MemoryEvidence, ...],
    ) -> None:
        now = datetime.now(timezone.utc)
        for item in evidence:
            connection.execute(
                evidence_table.insert().values(
                    evidence_id=item.evidence_id,
                    assertion_id=assertion_id,
                    owner_user_id=owner,
                    conversation_id=item.conversation_id,
                    source_message_id=item.source_message_id,
                    display_text=item.display_text,
                    authority=item.authority.value,
                    observed_at=item.observed_at,
                    created_at=now,
                )
            )
        return None

    def _insert_decision_row(
        self, connection: Connection, decision, assertion_id: str, owner: str
    ) -> str:
        now = datetime.now(timezone.utc)
        decision_id = f"mdc_{uuid.uuid4().hex}"
        connection.execute(
            decisions_table.insert().values(
                decision_id=decision_id,
                candidate_id=decision.candidate_id,
                assertion_id=assertion_id,
                owner_user_id=owner,
                outcome=decision.outcome.value,
                reason=decision.reason.value,
                decided_at=now,
                created_at=now,
            )
        )
        return decision_id

    def _insert_version_row(
        self, connection: Connection, draft, assertion_id: str, owner: str
    ) -> str:
        if draft is None:
            raise MemoryWriteError("The change carries no version to persist.")
        now = datetime.now(timezone.utc)
        version_id = new_version_id()
        connection.execute(
            versions_table.insert().values(
                version_id=version_id,
                assertion_id=assertion_id,
                owner_user_id=owner,
                normalized_value=draft.normalized_value,
                value_payload={
                    "normalized_value": draft.normalized_value,
                    "display_text": draft.display_text,
                },
                authority=draft.authority.value,
                sensitivity=draft.sensitivity.value,
                status="active",
                valid_from=draft.valid_from,
                supersedes_version_id=draft.supersedes_version_id,
                created_at=now,
            )
        )
        return version_id

    def _mark_versions_superseded(
        self, connection: Connection, assertion_id: str, version_ids
    ) -> tuple[str, ...]:
        identities = tuple(version_ids)
        if not identities:
            return ()
        result = connection.execute(
            versions_table.update()
            .where(versions_table.c.assertion_id == assertion_id)
            .where(versions_table.c.version_id.in_(identities))
            .where(versions_table.c.status == "active")
            .values(status="superseded")
        )
        if result.rowcount != len(identities):
            raise ConcurrentWriteError(
                "A supersession target moved; re-resolve and retry."
            )
        return identities

    def _insert_event_row(
        self,
        connection: Connection,
        owner: str,
        assertion_id: str,
        version_id: str | None,
        reason: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        connection.execute(
            events_table.insert().values(
                event_id=f"mevt_{uuid.uuid4().hex}",
                owner_user_id=owner,
                event_type="memory.write.applied",
                assertion_id=assertion_id,
                version_id=version_id,
                reason_code=reason,
                occurred_at=now,
            )
        )

    def _insert_outbox_row(
        self,
        connection: Connection,
        owner: str,
        assertion_id: str,
        version_id: str | None,
        change,
    ) -> None:
        now = datetime.now(timezone.utc)
        connection.execute(
            outbox_table.insert().values(
                outbox_id=f"mout_{uuid.uuid4().hex}",
                owner_user_id=owner,
                event_type="memory.write.committed",
                payload={
                    "assertion_id": assertion_id,
                    "version_id": version_id,
                    "operation": change.operation.value,
                    "reason": change.reason,
                },
                status="pending",
                created_at=now,
            )
        )

    def _record_idempotency(
        self,
        connection: Connection,
        key: str,
        owner: str,
        result: MemoryWriteResult,
    ) -> None:
        try:
            # Savepoint: same discipline as the assertion insert — a lost
            # redelivery race must not poison this transaction.
            with connection.begin_nested():
                connection.execute(
                    idempotency_table.insert().values(
                        idempotency_key=key,
                        owner_user_id=owner,
                        operation=result.operation.value,
                        version_id=result.version_id,
                        decision_id=result.decision_id,
                        superseded_version_ids=list(result.superseded_version_ids),
                        reference_version_id=result.reference_version_id,
                        reason_code=result.reason,
                        created_at=datetime.now(timezone.utc),
                    )
                )
        except sa_exc.IntegrityError:
            # A concurrent redelivery recorded first; its result stands.
            existing = (
                connection.execute(
                    select(idempotency_table).where(
                        idempotency_table.c.idempotency_key == key
                    )
                )
                .mappings()
                .fetchone()
            )
            if (
                existing is None or existing["owner_user_id"] != owner
            ):  # pragma: no cover
                raise

    def _finish(
        self,
        connection: Connection,
        change,
        owner: str,
        assertion_id: str | None,
        version_id: str | None,
        superseded: tuple[str, ...],
        reference: str | None,
        decision_id: str | None,
        idempotency_key: str | None,
    ) -> MemoryWriteResult:
        result = MemoryWriteResult(
            operation=change.operation,
            version_id=version_id,
            superseded_version_ids=superseded,
            reference_version_id=reference,
            decision_id=decision_id,
            reason=change.reason,
        )
        should_record_idempotency = (
            idempotency_key is not None and (
                change.operation in _WRITING_OPERATIONS
                or (change.operation is MemoryOperation.NOOP and decision_id is not None)
            )
        )
        if should_record_idempotency:
            self._record_idempotency(connection, idempotency_key, owner, result)
        logger.info(
            "memory.write applied operation=%s reason=%s",
            change.operation.value,
            change.reason,
        )
        return result


def pg_list_active_versions(engine: Engine, owner: str) -> tuple[MemoryVersion, ...]:
    """List one owner's active versions, oldest first (PG read seam)."""
    with engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    "SELECT v.version_id, v.owner_user_id, a.scope, a.scope_id, "
                    "a.canonical_key, a.subject_key, a.condition_fingerprint, "
                    "v.normalized_value, "
                    "v.value_payload ->> 'display_text' AS display_text, "
                    "v.authority, v.sensitivity, v.status, v.valid_from, "
                    "v.supersedes_version_id "
                    "FROM memory_versions AS v "
                    "JOIN memory_assertions AS a "
                    "ON v.assertion_id = a.assertion_id "
                    "WHERE v.owner_user_id = :owner AND v.status = 'active' "
                    "ORDER BY v.valid_from ASC, v.version_id ASC"
                ),
                {"owner": owner},
            )
            .mappings()
            .fetchall()
        )
    return tuple(
        MemoryVersion(
            version_id=row["version_id"],
            owner_user_id=row["owner_user_id"],
            scope=row["scope"],
            scope_id=row["scope_id"],
            canonical_key=row["canonical_key"],
            subject_key=row["subject_key"],
            condition_fingerprint=row["condition_fingerprint"],
            normalized_value=row["normalized_value"],
            display_text=row["display_text"] or row["normalized_value"],
            authority=row["authority"],
            sensitivity=row["sensitivity"],
            status=row["status"],
            valid_from=row["valid_from"],
            supersedes_version_id=row["supersedes_version_id"],
        )
        for row in rows
    )


def pg_commit_delete_one(
    engine: Engine, owner: str, version_id: str, reason: str
) -> UndoDescriptor:
    """Tombstone one active version plus a deletion-ledger row, atomically.

    The version flips to superseded without a successor; the ledger row
    is the source of truth that the transition was a delete. The
    descriptor names the restore target; nothing is restored implicitly.
    """
    now = datetime.now(timezone.utc)
    ledger_id = f"mdel_{uuid.uuid4().hex}"
    with transaction(engine) as connection:
        set_tenant(connection, owner)
        require_tenant_context(connection)
        row = (
            connection.execute(
                text(
                    "SELECT status FROM memory_versions "
                    "WHERE version_id = :version AND owner_user_id = :owner "
                    "FOR UPDATE"
                ),
                {"version": version_id, "owner": owner},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            raise MemoryCommandNotFoundError("The memory entry does not exist.")
        if row["status"] != "active":
            raise MemoryCommandStaleError("The memory entry already changed.")
        connection.execute(
            text(
                "UPDATE memory_versions SET status = 'superseded' "
                "WHERE version_id = :version AND status = 'active'"
            ),
            {"version": version_id},
        )
        connection.execute(
            text(
                "INSERT INTO memory_deletion_ledger "
                "(ledger_id, owner_user_id, target_type, target_id, "
                "deleted_at, reason) "
                "VALUES (:ledger, :owner, :type, :target, :at, :reason)"
            ),
            {
                "ledger": ledger_id,
                "owner": owner,
                "type": DELETION_TARGET_TYPE,
                "target": version_id,
                "at": now,
                "reason": reason,
            },
        )
    return UndoDescriptor(
        action="restore",
        version_ids=(version_id,),
        note="Restore keeps history; re-check scope before restoring.",
    )


def pg_commit_bulk_delete(
    engine: Engine, owner: str, version_ids: tuple[str, ...], reason: str
) -> UndoDescriptor:
    """Tombstone every target plus ledger rows in one transaction.

    The affected count must match exactly; any drift aborts the whole
    commit so a bulk delete never partially lands.
    """
    identities = tuple(version_ids)
    now = datetime.now(timezone.utc)
    with transaction(engine) as connection:
        set_tenant(connection, owner)
        require_tenant_context(connection)
        result = connection.execute(
            text(
                "UPDATE memory_versions SET status = 'superseded' "
                "WHERE owner_user_id = :owner AND status = 'active' "
                "AND version_id = ANY(:versions)"
            ),
            {"owner": owner, "versions": list(identities)},
        )
        if result.rowcount != len(identities):
            raise MemoryCommandStaleError("The memory entries already changed.")
        for version_id in identities:
            connection.execute(
                text(
                    "INSERT INTO memory_deletion_ledger "
                    "(ledger_id, owner_user_id, target_type, target_id, "
                    "deleted_at, reason) "
                    "VALUES (:ledger, :owner, :type, :target, :at, :reason)"
                ),
                {
                    "ledger": f"mdel_{uuid.uuid4().hex}",
                    "owner": owner,
                    "type": DELETION_TARGET_TYPE,
                    "target": version_id,
                    "at": now,
                    "reason": reason,
                },
            )
    return UndoDescriptor(
        action="restore",
        version_ids=identities,
        note="Restore keeps history; re-check scope before restoring.",
    )
