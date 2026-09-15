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

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    and_,
    exc as sa_exc,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from backend.memory.lifecycle import (
    LifecycleFacts,
    LifecycleStage,
    MemoryLifecyclePolicy,
)
from backend.memory.source_handling import SourceHandlingRecord
from backend.memory.write_pipeline.models import (
    AssertionIdentity,
    Authority,
    DecisionOutcome,
    EvidenceIdentity,
    MemoryChangeSet,
    MemoryDecisionDraft,
    MemoryEvidence,
    MemoryOperation,
    MemoryVersion,
    MemoryVersionDraft,
    NormalizedSemanticValue,
    RetentionMode,
    SourceValidity,
    VersionStatus,
    new_version_id,
)
from backend.memory.write_pipeline.uow import (
    ConcurrentWriteError,
    CrossOwnerDeniedError,
    FenceContext,
    FenceReason,
    FencedWriteError,
    MemoryUnitOfWork,
    MemoryWriteError,
    MemoryWriteResult,
    MemoryWriteStore,
    StaleVersionError,
)
from backend.security.models import AuthenticatedPrincipal
from backend.storage.postgres import (
    require_tenant_context,
    set_tenant,
    transaction,
)

logger = logging.getLogger("travel_agent_memory_write")

metadata = MetaData()

#: The durable authority record for positive family-specific source handling.
#: The table itself is created by migration `20260912_03`; this declaration
#: lets the storage seam speak in typed columns. The authority key is
#: `(source_outbox_id, family)`, matching the migration exactly.
source_handling_table = Table(
    "memory_source_handling",
    metadata,
    Column("owner_user_id", Text(), nullable=False),
    Column("source_outbox_id", Text(), nullable=False),
    Column("family", Text(), nullable=False),
    Column("source_message_id", Text(), nullable=False),
    Column("outcome", Text(), nullable=False),
    Column("reason_code", Text(), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "source_outbox_id",
        "family",
        name="uq_memory_source_handling_authority",
    ),
)

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
    #: Which forget era this assertion is in. A candidate stamped with an older
    #: generation can no longer form, activate, or read.
    Column(
        "suppression_generation",
        Integer(),
        nullable=False,
        server_default=text("1"),
    ),
    Column("has_unresolved_conflict", Boolean(), nullable=False, server_default=text("false")),
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
    Column("retention_mode", Text(), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column(
        "suppression_generation",
        Integer(),
        nullable=False,
        server_default=text("1"),
    ),
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
    Column("invalidated_at", DateTime(timezone=True), nullable=True),
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

#: The canonical episodic store (plan v0.20 Task 12).
#:
#: One table, evolved from the placeholder `20260907_02` created, never a second
#: canonical episode store. `actor`/`event`/`source_*` are required grounding
#: facts whose column defaults exist only for migration safety — the empty
#: string is refused by every grounding validator, so a pre-existing row is
#: ineligible rather than silently grounded. `status` defaults to `shadow` for
#: the same reason: a schema change must never make a row answer-eligible.
#:
#: `payload` is carried but is not policy authority for anything.
episodes_table = Table(
    "memory_episodes",
    metadata,
    Column("episode_id", Text(), primary_key=True),
    Column("owner_user_id", Text(), nullable=False),
    Column("conversation_id", Text(), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSONB(), nullable=False, server_default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("actor", Text(), nullable=False, server_default=""),
    Column("event", Text(), nullable=False, server_default=""),
    Column("source_message_id", Text(), nullable=False, server_default=""),
    Column("source_outbox_id", Text(), nullable=False, server_default=""),
    Column(
        "retention_mode",
        Text(),
        nullable=False,
        server_default="conversation_bound",
    ),
    Column("status", Text(), nullable=False, server_default="shadow"),
    Column("sensitivity", Text(), nullable=False, server_default="ordinary_personal"),
    Column("suppression_generation", Integer(), nullable=False, server_default="1"),
    Column("unresolved_conflict", Boolean(), nullable=False, server_default="false"),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("invalidated_at", DateTime(timezone=True), nullable=True),
)

#: The canonical Working Memory store (`20260915_03`). `memory_summaries` has
#: existed since `20260907_02` as an unused placeholder; Task 13 evolves it rather
#: than adding a parallel table, so there is one canonical open state per
#: conversation and no second store to keep in step.
#:
#: `content` is bound here only so the table object matches the physical schema.
#: Nothing in this codebase reads it or writes it: it is a migration-safety
#: column, never policy authority.
working_summaries_table = Table(
    "memory_summaries",
    metadata,
    Column("summary_id", Text(), primary_key=True),
    Column("owner_user_id", Text(), nullable=False),
    Column("conversation_id", Text(), nullable=False),
    Column("content", Text(), nullable=False, server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("open_goal", Text(), nullable=False, server_default=""),
    Column("through_sequence", Integer(), nullable=False, server_default="0"),
    Column(
        "origin",
        Text(),
        nullable=False,
        server_default="deterministic_transition",
    ),
    Column("source_message_id", Text(), nullable=False, server_default=""),
    Column("source_outbox_id", Text(), nullable=False, server_default=""),
    Column(
        "retention_mode",
        Text(),
        nullable=False,
        server_default="conversation_bound",
    ),
    Column("status", Text(), nullable=False, server_default="shadow"),
    Column("sensitivity", Text(), nullable=False, server_default="ordinary_personal"),
    Column("suppression_generation", Integer(), nullable=False, server_default="1"),
    Column("unresolved_conflict", Boolean(), nullable=False, server_default="false"),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("invalidated_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
)

_EPISODE_ID_PREFIX = "epi_"

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
        # `REVOKE` writes no version but it does write: it moves the governed
        # current version to `REVOKED` and advances the assertion's suppression
        # generation. Leaving it out of this set would let a revoke be applied
        # without ever being recorded as a writing operation.
        MemoryOperation.REVOKE,
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
            normalized_value=_rebuild_normalized_value(row),
            display_text=row["value_payload"]["display_text"],
            authority=row["authority"],
            sensitivity=row["sensitivity"],
            status=row["status"],
            valid_from=row["valid_from"],
            supersedes_version_id=row["supersedes_version_id"],
            retention_mode=row["retention_mode"],
            expires_at=row["expires_at"],
            suppression_generation=row["suppression_generation"],
        )
        for row in rows
    )


def record_source_handling_on(
    connection: Connection, owner_user_id: str, record: SourceHandlingRecord
) -> bool:
    """Persist one durable authority record on the given connection; replay-aware, fail-closed."""
    if not isinstance(record, SourceHandlingRecord):
        raise MemoryWriteError(
            "record_source_handling requires a SourceHandlingRecord."
        )
    set_tenant(connection, owner_user_id)
    existing = (
        connection.execute(
            select(source_handling_table).where(
                source_handling_table.c.owner_user_id == owner_user_id,
                source_handling_table.c.source_outbox_id
                == record.source_outbox_id,
                source_handling_table.c.family == record.family.value,
            )
        )
        .mappings()
        .fetchone()
    )
    if existing is not None:
        same = (
            existing["source_message_id"] == record.source_message_id
            and existing["outcome"] == record.outcome.value
            and existing["reason_code"] == record.reason_code.value
            and existing["recorded_at"] == record.recorded_at
        )
        if same:
            return False
        raise MemoryWriteError(
            "A different authority record already exists for this source "
            "and family; replay with identical content or re-derive the "
            "decision."
        )
    inserted = connection.execute(
        pg_insert(source_handling_table)
        .values(
            owner_user_id=owner_user_id,
            source_outbox_id=record.source_outbox_id,
            family=record.family.value,
            source_message_id=record.source_message_id,
            outcome=record.outcome.value,
            reason_code=record.reason_code.value,
            recorded_at=record.recorded_at,
        )
        .on_conflict_do_nothing(
            constraint="uq_memory_source_handling_authority"
        )
        .returning(source_handling_table.c.source_outbox_id)
    ).scalar_one_or_none()
    if inserted is not None:
        return True

    winner = (
        connection.execute(
            select(source_handling_table).where(
                source_handling_table.c.source_outbox_id == record.source_outbox_id,
                source_handling_table.c.family == record.family.value,
            )
        )
        .mappings()
        .one()
    )
    same = (
        winner["owner_user_id"] == owner_user_id
        and winner["source_message_id"] == record.source_message_id
        and winner["outcome"] == record.outcome.value
        and winner["reason_code"] == record.reason_code.value
        and winner["recorded_at"] == record.recorded_at
    )
    if same:
        return False
    raise MemoryWriteError(
        "A different authority record already exists for this source and family."
    )


def record_source_handling(
    engine: Engine, owner_user_id: str, record: SourceHandlingRecord
) -> bool:
    """Persist one durable authority record; replay-aware, fail-closed.

    The authority key is `(owner_user_id, source_outbox_id, family)`. An
    identical replay — every authoritative field equal — is idempotent and
    returns `False`; the same key with different content is a contradiction
    between two decisions about one source and fails closed with
    `MemoryWriteError` (`plan:734-748`). The unique constraint backs the
    race; the explicit comparison supplies the semantics, so a losing
    concurrent writer observes the winner's row and compares rather than
    treating constraint violation as "already done".

    Runs in its own tenant-bound transaction. `recorded_at` is part of the
    record's authoritative content: two records differing only in time are
    two different decisions and conflict.
    """
    with transaction(engine) as connection:
        return record_source_handling_on(connection, owner_user_id, record)


def load_source_handling(
    engine: Engine, owner_user_id: str, source_outbox_id: str, family: Any
) -> SourceHandlingRecord | None:
    """Return the durable record for one authority key, or `None`.

    `None` is `UNHANDLED`: it grants nothing — `allows_background_formation`
    denies it, and that denial is the point (`ADR 0038:59`). The read binds
    the tenant so RLS scopes it like every other owner-path read.
    """
    from backend.memory.source_handling import MemoryFamily

    resolved_family = (
        family if isinstance(family, MemoryFamily) else MemoryFamily(family)
    )
    with engine.connect() as connection:
        set_tenant(connection, owner_user_id)
        row = (
            connection.execute(
                select(source_handling_table).where(
                    source_handling_table.c.owner_user_id == owner_user_id,
                    source_handling_table.c.source_outbox_id == source_outbox_id,
                    source_handling_table.c.family == resolved_family.value,
                )
            )
            .mappings()
            .fetchone()
        )
    if row is None:
        return None
    return SourceHandlingRecord(
        source_outbox_id=row["source_outbox_id"],
        source_message_id=row["source_message_id"],
        family=resolved_family,
        outcome=row["outcome"],
        reason_code=row["reason_code"],
        recorded_at=row["recorded_at"],
    )


def _derived_normalized_text(value: NormalizedSemanticValue) -> str:
    """The deterministic textual form stored beside the JSON payload.

    A set is canonical compact JSON rather than delimiter text, so the column
    stays auditable without inventing an encoding a reader could mistake for the
    value itself. `"a|b"` is one value; `["a","b"]` is two.
    """
    if isinstance(value, tuple):
        return json.dumps(list(value), separators=(",", ":"), ensure_ascii=False)
    return value


def _typed_normalized_value(payload_value: Any) -> NormalizedSemanticValue:
    """Rebuild the in-process value from the authoritative JSON payload."""
    if isinstance(payload_value, list):
        return tuple(payload_value)
    return payload_value


def _rebuild_normalized_value(row: Any) -> NormalizedSemanticValue:
    """Rebuild a stored value, and cross-check the derived text on the way.

    The payload is authoritative and the text column is derived, so a
    disagreement means the row was not written by this writer. Returning the
    text instead would expose a raw JSON string as an in-process set value.
    """
    typed = _typed_normalized_value(row["value_payload"]["normalized_value"])
    if _derived_normalized_text(typed) != row["normalized_value"]:
        raise MemoryWriteError(
            "Stored normalized_value disagrees with value_payload."
        )
    return typed


def _require_fence_reason(reason: FenceReason | None, check: str) -> FenceReason:
    """Return the reason a fence check refused with, or fail loudly.

    `check_conversation_fence` and `check_outbox_lease` return a reason whenever
    they return `False`. A `None` here means that contract broke, and defaulting
    to some plausible reason would silently misclassify the fence — which is how
    the caller decides whether cancelling the conversation's other work is
    justified (ADR 0033). Misclassifying in that direction destroys valid memory
    formation, so the failure is raised instead of guessed.
    """
    if reason is None:
        raise RuntimeError(
            f"The {check} fence refused a write without naming a FenceReason; "
            "a refusal must always carry one."
        )
    return reason


class PostgresMemoryUnitOfWork(MemoryUnitOfWork, MemoryWriteStore):
    """Apply resolved changes atomically against PostgreSQL."""

    def __init__(self, engine: Engine, *, max_attempts: int = _MAX_ATTEMPTS) -> None:
        """Bind to an existing engine; schema comes from Alembic, not here."""
        self._engine = engine
        self._max_attempts = max_attempts

    def apply_on(
        self,
        connection: Connection,
        *,
        change: MemoryChangeSet,
        principal: AuthenticatedPrincipal,
        evidence: tuple[MemoryEvidence, ...] = (),
        decision: MemoryDecisionDraft | None = None,
        idempotency_key: str | None = None,
        expected_version_id: str | None = None,
        fence: FenceContext | None = None,
        source_validity: SourceValidity | None = None,
    ) -> MemoryWriteResult:
        """Apply one resolved change atomically on the supplied connection."""
        self._check_inputs(
            change, principal, evidence, decision, idempotency_key, source_validity
        )
        if fence is not None and not isinstance(fence, FenceContext):
            raise MemoryWriteError("A fence must be a FenceContext or null.")
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
        return self._apply_once(
            connection,
            change,
            principal,
            evidence,
            decision,
            idempotency_key,
            expected_version_id,
            fence,
            source_validity,
        )

    def apply_memory_change(
        self,
        change: MemoryChangeSet,
        principal: AuthenticatedPrincipal,
        *,
        evidence: tuple[MemoryEvidence, ...] = (),
        decision: MemoryDecisionDraft | None = None,
        idempotency_key: str | None = None,
        expected_version_id: str | None = None,
        fence: FenceContext | None = None,
        source_validity: SourceValidity | None = None,
    ) -> MemoryWriteResult:
        """Apply one change with bounded retry on write contention."""
        last_error: Exception | None = None
        for _ in range(self._max_attempts):
            try:
                with transaction(self._engine) as connection:
                    return self.apply_on(
                        connection,
                        change=change,
                        principal=principal,
                        evidence=evidence,
                        decision=decision,
                        idempotency_key=idempotency_key,
                        expected_version_id=expected_version_id,
                        fence=fence,
                        source_validity=source_validity,
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
    def _check_inputs(
        change, principal, evidence, decision, idempotency_key, source_validity
    ) -> None:
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
        if source_validity is not None and not isinstance(source_validity, SourceValidity):
            raise MemoryWriteError("source_validity must be a SourceValidity or null.")

    def _apply_once(
        self,
        connection: Connection,
        change,
        principal: AuthenticatedPrincipal,
        evidence: tuple[MemoryEvidence, ...],
        decision,
        idempotency_key: str | None,
        expected_version_id: str | None,
        fence: FenceContext | None,
        source_validity: SourceValidity | None,
    ) -> MemoryWriteResult:
        owner = principal.owner_user_id
        set_tenant(connection, owner)
        require_tenant_context(connection)
        if fence is not None:
            self._check_fence(connection, fence, owner)
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
        if operation is MemoryOperation.NOOP and not change.reason.startswith(
            "shadow_"
        ):
            return MemoryWriteResult(
                operation=operation,
                version_id=None,
                superseded_version_ids=(),
                reference_version_id=None,
                decision_id=None,
                reason=change.reason,
            )

        should_reserve = idempotency_key is not None and (
            change.operation in _WRITING_OPERATIONS
            or (change.operation is MemoryOperation.NOOP and decision is not None)
        )

        if idempotency_key is not None:
            prior = self._lookup_idempotency(connection, idempotency_key, owner)
            if prior is not None:
                return prior

        if should_reserve:
            # ADR 0031: claim the key *before* writing the effect it guards.
            # Recording it afterwards meant a losing transaction committed its
            # evidence, decision, version and event rows and then swallowed the
            # conflict — one key, two semantic effects.
            #
            # The reservation and the fill share this transaction, so a row any
            # other transaction can see is always complete. That is why no
            # "incomplete" marker is needed and the table's shape is unchanged.
            #
            # A conflict is deliberately not caught here: it propagates, the
            # transaction aborts and commits nothing, and the outer retry loop's
            # next attempt finds the winner's completed row and returns it.
            self._reserve_idempotency(connection, idempotency_key, owner, change)

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
        stored_generation = self._read_locked_assertion_generation(
            connection, assertion_id
        )
        if change.operation in _WRITING_OPERATIONS and change.new_version is not None:
            if stored_generation != change.new_version.suppression_generation:
                # The no-resurrection fence (`plan:710-722`): the domain
                # resolver compares stamps, but only this locked boundary
                # knows the durable fact. A write whose candidate carries an
                # older generation than the live assertion is delayed work
                # from before a REVOKE; letting it through would resurrect
                # the memory the revoke retired. The comparison happens after
                # the lock, so a revoke committing concurrently is observed
                # by one of the two writers.
                raise StaleVersionError(
                    "The change carries a stale suppression generation; "
                    "re-resolve against the current assertion."
                )
            lifecycle = MemoryLifecyclePolicy().evaluate(
                stage=LifecycleStage.WRITE,
                facts=LifecycleFacts(
                    retention_mode=change.new_version.retention_mode,
                    stamped_generation=change.new_version.suppression_generation,
                    current_generation=stored_generation,
                    scope=change.new_version.scope,
                    sensitivity=change.new_version.sensitivity,
                    source_validity=source_validity,
                    expires_at=change.new_version.expires_at,
                    evaluated_at=(
                        datetime.now(timezone.utc)
                        if change.new_version.expires_at is not None
                        else None
                    ),
                ),
            )
            if not lifecycle.eligible:
                raise MemoryWriteError(
                    f"Memory lifecycle write denied: {lifecycle.reason.value}."
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
            superseded = self._mark_versions_status(
                connection, assertion_id, change.superseded_version_ids
            )
            version_id = self._insert_version_row(
                connection, change.new_version, assertion_id, owner
            )
            reference = None
        elif operation is MemoryOperation.REVOKE:
            if not change.superseded_version_ids:
                raise ConcurrentWriteError("The revoke target is gone; re-resolve.")
            # Revoke is a terminal status, not a deletion: the row survives so
            # delayed work can be fenced against it. The suppression-generation
            # advance that goes with it is applied under the same lock, below.
            superseded = self._mark_versions_status(
                connection,
                assertion_id,
                change.superseded_version_ids,
                status=VersionStatus.REVOKED.value,
            )
            self._advance_suppression_generation(connection, assertion_id)
            version_id = None
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
            if operation is MemoryOperation.PENDING_CONFLICT:
                connection.execute(assertions_table.update().where(assertions_table.c.assertion_id == assertion_id).values(has_unresolved_conflict=True))
            version_id = None
            superseded = ()
            reference = None
        else:  # pragma: no cover - closed operation vocabulary
            raise MemoryWriteError("An unknown memory operation cannot be applied.")
        is_authoritative_explicit = fence is None and (
            change.new_version is None
            or change.new_version.authority in (Authority.EXPLICIT_SAVE, Authority.EXPLICIT_STATEMENT)
        )
        if is_authoritative_explicit and operation in (
            MemoryOperation.ADD,
            MemoryOperation.REINFORCE,
            MemoryOperation.SUPERSEDE,
            MemoryOperation.REVOKE,
        ):
            connection.execute(
                assertions_table.update()
                .where(assertions_table.c.assertion_id == assertion_id)
                .values(has_unresolved_conflict=False)
            )

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
            idempotency_key if should_reserve else None,
        )

    @staticmethod
    def _check_fence(
        connection: Connection,
        fence: FenceContext,
        owner: str,
    ) -> None:
        """Verify the source conversation and outbox lease inside this txn.

        Raises `FencedWriteError` without touching state when the
        conversation is gone or not active, the deletion epoch moved, or
        the outbox event is no longer leased to the expected worker *within its
        lease window*. This closes the race between a worker's pre-extraction
        revalidation and its memory commit.

        The window matters: matching the holder alone proved identity, not
        current authority, so a worker whose lease had expired could still write.

        No `now` is accepted or forwarded. Both checks judge their own state
        inside this transaction: the conversation by the row it locks, the lease
        by `now()`. A caller-supplied timestamp let the party being judged choose
        the clock (ADR 0032).
        """
        from backend.conversations.postgres_repository import (
            check_conversation_fence,
            check_outbox_lease,
        )

        ok, reason = check_conversation_fence(
            connection, fence.conversation_id, fence.expected_epoch, owner
        )
        if not ok:
            raise FencedWriteError(
                _require_fence_reason(reason, "conversation")
            )

        ok, reason = check_outbox_lease(connection, fence.outbox_id, fence.lease_owner)
        if not ok:
            raise FencedWriteError(
                _require_fence_reason(reason, "outbox lease")
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

    @staticmethod
    def _read_locked_assertion_generation(
        connection: Connection, assertion_id: str
    ) -> int:
        """The assertion's durable suppression generation, read under lock.

        The parent row is already `FOR UPDATE`-locked by `_resolve_assertion`,
        so this read is stable for the rest of the transaction: no concurrent
        revoke can advance the generation between this comparison and the
        write it guards.
        """
        row = (
            connection.execute(
                select(
                    assertions_table.c.suppression_generation
                ).where(assertions_table.c.assertion_id == assertion_id)
            )
            .mappings()
            .fetchone()
        )
        if row is None:  # pragma: no cover - the caller just resolved it
            raise MemoryWriteError("The assertion disappeared under the lock.")
        return int(row["suppression_generation"])

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
                normalized_value=_derived_normalized_text(draft.normalized_value),
                value_payload={
                    "normalized_value": (
                        list(draft.normalized_value)
                        if isinstance(draft.normalized_value, tuple)
                        else draft.normalized_value
                    ),
                    "display_text": draft.display_text,
                },
                authority=draft.authority.value,
                sensitivity=draft.sensitivity.value,
                status="active",
                valid_from=draft.valid_from,
                supersedes_version_id=draft.supersedes_version_id,
                retention_mode=draft.retention_mode.value,
                expires_at=draft.expires_at,
                suppression_generation=draft.suppression_generation,
                created_at=now,
            )
        )
        return version_id

    def _mark_versions_status(
        self,
        connection: Connection,
        assertion_id: str,
        version_ids,
        *,
        status: str = "superseded",
    ) -> tuple[str, ...]:
        """Move the named live versions to a terminal status, or refuse.

        Both terminal transitions flip first for the same reason: the
        one-current-version index forbids two live rows even momentarily inside
        the transaction. A target that is no longer live means another writer
        moved it, which is a concurrency refusal rather than a silent no-op.
        """
        identities = tuple(version_ids)
        if not identities:
            return ()
        result = connection.execute(
            versions_table.update()
            .where(versions_table.c.assertion_id == assertion_id)
            .where(versions_table.c.version_id.in_(identities))
            .where(versions_table.c.status == "active")
            .values(status=status)
        )
        if result.rowcount != len(identities):
            raise ConcurrentWriteError(
                "A supersession target moved; re-resolve and retry."
            )
        return identities

    def _advance_suppression_generation(
        self, connection: Connection, assertion_id: str
    ) -> int:
        """Advance the assertion's generation under the caller's lock.

        Storage owns this, not the resolver: a generation is a fact about what
        has been committed, and a pure function cannot know whether its change
        set will actually be applied. Doing it in the same statement that reads
        the current value keeps it atomic with the revocation.
        """
        return connection.execute(
            assertions_table.update()
            .where(assertions_table.c.assertion_id == assertion_id)
            .values(
                suppression_generation=assertions_table.c.suppression_generation
                + 1,
                updated_at=datetime.now(timezone.utc),
            )
        ).rowcount

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

    @staticmethod
    def _reserve_idempotency(
        connection: Connection,
        key: str,
        owner: str,
        change,
    ) -> None:
        """Claim the key before the effect it guards (ADR 0031).

        The operation and the reason are known here; the result columns are
        filled by `_fill_idempotency` once the effect exists. Both run in the
        same transaction, so any row another transaction can *see* is complete —
        which is why no "incomplete" marker is needed.

        A conflict is deliberately not caught. It propagates, the transaction
        aborts and commits nothing, and the caller's retry loop finds the
        winner's completed row on its next attempt.
        """
        connection.execute(
            idempotency_table.insert().values(
                idempotency_key=key,
                owner_user_id=owner,
                operation=change.operation.value,
                version_id=None,
                decision_id=None,
                superseded_version_ids=[],
                reference_version_id=None,
                reason_code=change.reason,
                created_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    def _fill_idempotency(
        connection: Connection,
        key: str,
        owner: str,
        result: MemoryWriteResult,
    ) -> None:
        """Record the effect on the key reserved earlier in this transaction."""
        connection.execute(
            idempotency_table.update()
            .where(
                and_(
                    idempotency_table.c.idempotency_key == key,
                    idempotency_table.c.owner_user_id == owner,
                )
            )
            .values(
                operation=result.operation.value,
                version_id=result.version_id,
                decision_id=result.decision_id,
                superseded_version_ids=list(result.superseded_version_ids),
                reference_version_id=result.reference_version_id,
                reason_code=result.reason,
            )
        )

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
        # The caller passes the key only when it reserved one (ADR 0031), so a
        # non-null key here means a reservation is waiting to be filled.
        if idempotency_key is not None:
            self._fill_idempotency(connection, idempotency_key, owner, result)
        logger.info(
            "memory.write applied operation=%s reason=%s",
            change.operation.value,
            change.reason,
        )
        return result

    def get_active_versions(
        self, owner_user_id: str, canonical_key: str
    ) -> tuple[MemoryVersion, ...]:
        """Return the active versions for one owner and canonical key.

        Tenant-scoped: `app.tenant` is bound and verified for the duration of
        the read, so row-level security filters to the same owner the predicate
        checks. A cross-owner read returns empty, never another owner's versions.
        """
        with transaction(self._engine) as connection:
            set_tenant(connection, owner_user_id)
            require_tenant_context(connection)
            return pg_list_active_versions(connection, owner_user_id, canonical_key)

    def get_assertion_generation(
        self, owner_user_id: str, canonical_key: str
    ) -> int:
        """Return the current suppression_generation for one owner and canonical key.

        Returns 1 if no assertion exists yet.
        """
        with transaction(self._engine) as connection:
            set_tenant(connection, owner_user_id)
            require_tenant_context(connection)
            return pg_get_assertion_generation(connection, owner_user_id, canonical_key)

    def get_active_evidence_for_assertion_on(
        self,
        connection: Connection,
        *,
        owner_user_id: str,
        assertion_id: str,
    ) -> Sequence[EvidenceIdentity]:
        """Return all active (uninvalidated) evidence identities for an assertion on connection."""
        stmt = (
            select(
                evidence_table.c.evidence_id,
                evidence_table.c.conversation_id,
                evidence_table.c.source_message_id,
            )
            .where(
                evidence_table.c.owner_user_id == owner_user_id,
                evidence_table.c.assertion_id == assertion_id,
                evidence_table.c.invalidated_at.is_(None),
            )
            .order_by(evidence_table.c.observed_at.asc())
        )
        rows = connection.execute(stmt).fetchall()
        return tuple(
            EvidenceIdentity(
                evidence_id=r[0],
                conversation_id=r[1],
                source_message_id=r[2],
            )
            for r in rows
        )

    def get_active_evidence_for_assertion(
        self, owner_user_id: str, assertion_id: str
    ) -> Sequence[EvidenceIdentity]:
        """Return all active (uninvalidated) evidence identities for an assertion."""
        with transaction(self._engine) as connection:
            set_tenant(connection, owner_user_id)
            require_tenant_context(connection)
            return self.get_active_evidence_for_assertion_on(
                connection, owner_user_id=owner_user_id, assertion_id=assertion_id
            )

    def get_assertion_conflict_state_on(
        self,
        connection: Connection,
        *,
        owner_user_id: str,
        assertion_id: str,
    ) -> bool:
        """Return stored has_unresolved_conflict flag from memory_assertions on connection."""
        stmt = (
            select(assertions_table.c.has_unresolved_conflict)
            .where(
                assertions_table.c.owner_user_id == owner_user_id,
                assertions_table.c.assertion_id == assertion_id,
            )
        )
        val = connection.execute(stmt).scalar()
        return bool(val) if val is not None else False

    def get_assertion_conflict_state(
        self, owner_user_id: str, assertion_id: str
    ) -> bool:
        """Return stored has_unresolved_conflict flag from memory_assertions."""
        with transaction(self._engine) as connection:
            set_tenant(connection, owner_user_id)
            require_tenant_context(connection)
            return self.get_assertion_conflict_state_on(
                connection, owner_user_id=owner_user_id, assertion_id=assertion_id
            )

    def get_assertion_identity_details_on(
        self,
        connection: Connection,
        identity: AssertionIdentity,
    ) -> tuple[str | None, bool]:
        """Return (assertion_id, has_unresolved_conflict) for an assertion identity."""
        stmt = (
            select(
                assertions_table.c.assertion_id,
                assertions_table.c.has_unresolved_conflict,
            ).where(
                assertions_table.c.owner_user_id == identity.owner_user_id,
                assertions_table.c.scope == identity.scope.value,
                assertions_table.c.scope_id == identity.scope_id,
                assertions_table.c.canonical_key == identity.canonical_key,
                assertions_table.c.subject_key == identity.subject_key,
                assertions_table.c.condition_fingerprint == identity.condition_fingerprint,
            )
        )
        row = connection.execute(stmt).fetchone()
        if row is None:
            return None, False
        return str(row[0]), bool(row[1])

    def get_assertion_identity_details(
        self,
        identity: AssertionIdentity,
    ) -> tuple[str | None, bool]:
        """Return (assertion_id, has_unresolved_conflict) for an assertion identity."""
        with transaction(self._engine) as connection:
            set_tenant(connection, identity.owner_user_id)
            require_tenant_context(connection)
            return self.get_assertion_identity_details_on(connection, identity)

    def prune_projection_outbox_on(
        self,
        connection: Connection,
        *,
        retention_cutoff: datetime,
        batch_size: int,
    ) -> int:
        """Prune eligible pending projection outbox events up to batch_size on connection."""
        subq = (
            select(outbox_table.c.outbox_id)
            .where(
                outbox_table.c.event_type == "memory.write.committed",
                outbox_table.c.status == "pending",
                outbox_table.c.created_at < retention_cutoff,
            )
            .order_by(outbox_table.c.created_at.asc())
            .limit(batch_size)
            .scalar_subquery()
        )
        stmt = outbox_table.delete().where(outbox_table.c.outbox_id.in_(subq))
        res = connection.execute(stmt)
        return int(res.rowcount or 0)

    def prune_projection_outbox(
        self, *, retention_cutoff: datetime, batch_size: int
    ) -> int:
        """Prune eligible pending projection outbox events up to batch_size."""
        with self._engine.begin() as connection:
            return self.prune_projection_outbox_on(
                connection, retention_cutoff=retention_cutoff, batch_size=batch_size
            )


def pg_get_assertion_generation(
    connection: Connection, owner: str, canonical_key: str
) -> int:
    """Return the current suppression generation for one assertion, or 1 if absent."""
    stmt = (
        select(assertions_table.c.suppression_generation)
        .where(
            assertions_table.c.owner_user_id == owner,
            assertions_table.c.canonical_key == canonical_key,
        )
    )
    gen = connection.scalar(stmt)
    return int(gen) if gen is not None else 1


def pg_list_active_versions(
    connection: Connection, owner: str, canonical_key: str | None = None
) -> tuple[MemoryVersion, ...]:
    """List one owner's active versions, oldest first.

    Takes a **tenant-bound connection**, not an engine. Under row-level security
    an unbound connection sees no rows at all, so a bare `engine.connect()` here
    would silently return an empty tuple — indistinguishable from a real empty
    history, which is the defect this read exists to remove. `canonical_key`
    narrows the read to one assertion key.
    """
    statement = (
        "SELECT v.version_id, v.owner_user_id, a.scope, a.scope_id, "
        "a.canonical_key, a.subject_key, a.condition_fingerprint, "
        "v.normalized_value, v.value_payload, "
        "v.value_payload ->> 'display_text' AS display_text, "
        "v.authority, v.sensitivity, v.status, v.valid_from, "
        "v.supersedes_version_id, v.retention_mode, v.expires_at, "
        "v.suppression_generation "
        "FROM memory_versions AS v "
        "JOIN memory_assertions AS a "
        "ON v.assertion_id = a.assertion_id "
        "WHERE v.owner_user_id = :owner AND v.status = 'active' "
    )
    params: dict[str, Any] = {"owner": owner}
    if canonical_key is not None:
        statement += "AND a.canonical_key = :canonical_key "
        params["canonical_key"] = canonical_key
    statement += "ORDER BY v.valid_from ASC, v.version_id ASC"

    rows = connection.execute(text(statement), params).mappings().fetchall()
    return tuple(
        MemoryVersion(
            version_id=row["version_id"],
            owner_user_id=row["owner_user_id"],
            scope=row["scope"],
            scope_id=row["scope_id"],
            canonical_key=row["canonical_key"],
            subject_key=row["subject_key"],
            condition_fingerprint=row["condition_fingerprint"],
            normalized_value=_rebuild_normalized_value(row),
            display_text=row["display_text"] or row["normalized_value"],
            authority=row["authority"],
            sensitivity=row["sensitivity"],
            status=row["status"],
            valid_from=row["valid_from"],
            supersedes_version_id=row["supersedes_version_id"],
            retention_mode=row["retention_mode"],
            expires_at=row["expires_at"],
            suppression_generation=row["suppression_generation"],
        )
        for row in rows
    )
