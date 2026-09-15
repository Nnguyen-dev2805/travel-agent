"""Tenant-scoped physical projections for Memory reads."""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import exists, select
from sqlalchemy.engine import Engine

from backend.memory.episodic import (
    EpisodeReadRequest,
    StoredEpisodeRow,
)
from backend.memory.lifecycle import SourceValidity
from backend.memory.read_models import MemoryReadRequest, StoredMemoryRow
from backend.memory.write_pipeline.models import (
    Authority,
    MemoryScope,
    NormalizedSemanticValue,
    RetentionMode,
    SensitivityBand,
    VersionStatus,
)
from backend.memory.write_pipeline.postgres import (
    assertions_table,
    episodes_table,
    evidence_table,
    versions_table,
)
from backend.memory.write_pipeline.uow import MemoryWriteError
from backend.storage.postgres import require_tenant_context, set_tenant


class PostgresMemoryStore:
    """Projects physical memory rows for an owner under tenant-level isolation.

    Owns only physical query projection and type coercion back to domain enums
    and immutable tuples. Never computes read eligibility verdicts; that belongs
    exclusively to MemoryLifecyclePolicy inside MemoryReadEngine.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_storage_scoped(
        self, request: MemoryReadRequest
    ) -> Sequence[StoredMemoryRow]:
        if not request.requested_keys:
            return ()

        with self._engine.connect() as connection:
            set_tenant(connection, request.owner_user_id)
            require_tenant_context(connection)

            has_valid_evidence = exists(
                select(evidence_table.c.evidence_id).where(
                    evidence_table.c.assertion_id == versions_table.c.assertion_id,
                    evidence_table.c.invalidated_at.is_(None),
                )
            ).label("has_valid_evidence")

            query = (
                select(
                    versions_table.c.version_id,
                    versions_table.c.owner_user_id,
                    versions_table.c.value_payload,
                    versions_table.c.authority,
                    versions_table.c.sensitivity,
                    versions_table.c.status,
                    versions_table.c.valid_from,
                    versions_table.c.retention_mode,
                    versions_table.c.expires_at,
                    versions_table.c.suppression_generation.label("stamped_generation"),
                    assertions_table.c.canonical_key,
                    assertions_table.c.scope,
                    assertions_table.c.scope_id,
                    assertions_table.c.suppression_generation.label("current_generation"),
                    assertions_table.c.has_unresolved_conflict,
                    has_valid_evidence,
                )
                .select_from(
                    versions_table.join(
                        assertions_table,
                        versions_table.c.assertion_id == assertions_table.c.assertion_id,
                    )
                )
                .where(
                    versions_table.c.owner_user_id == request.owner_user_id,
                    assertions_table.c.canonical_key.in_(request.requested_keys),
                )
            )

            rows = connection.execute(query).mappings().all()

            results: list[StoredMemoryRow] = []
            for r in rows:
                raw_val = (
                    r["value_payload"].get("normalized_value")
                    if isinstance(r["value_payload"], dict)
                    else r["value_payload"]
                )
                normalized_value: NormalizedSemanticValue = (
                    tuple(raw_val) if isinstance(raw_val, list) else str(raw_val)
                )

                scope = MemoryScope(r["scope"])
                authority = Authority(r["authority"])
                retention_mode = RetentionMode(r["retention_mode"])
                status = VersionStatus(r["status"])
                sensitivity = SensitivityBand(r["sensitivity"])

                if retention_mode is RetentionMode.USER_DURABLE:
                    source_validity = SourceValidity.NOT_REQUIRED
                elif r["has_valid_evidence"]:
                    source_validity = SourceValidity.VALID
                else:
                    source_validity = SourceValidity.INVALID

                results.append(
                    StoredMemoryRow(
                        version_id=str(r["version_id"]),
                        canonical_key=str(r["canonical_key"]),
                        normalized_value=normalized_value,
                        owner_user_id=str(r["owner_user_id"]),
                        scope=scope,
                        scope_id=str(r["scope_id"]),
                        authority=authority,
                        valid_from=r["valid_from"],
                        retention_mode=retention_mode,
                        stamped_generation=int(r["stamped_generation"]),
                        current_generation=int(r["current_generation"]),
                        status=status,
                        sensitivity=sensitivity,
                        source_validity=source_validity,
                        expires_at=r["expires_at"],
                        unresolved_conflict=bool(r["has_unresolved_conflict"]),
                    )
                )

            return tuple(results)


class PostgresEpisodeStore:
    """Projects physical episode rows for an owner under tenant isolation.

    Owns physical projection and type coercion only. It never decides whether an
    episode is answer-eligible — `MemoryLifecyclePolicy` does that inside
    `EpisodicReadEngine` — and it never exposes raw source text, because a row
    that carried its source would be the prompt channel the architecture keeps
    closed.

    `source_validity` is derived here, not stored as a decision: the caller that
    owns the canonical source/evidence snapshot computes it before the pure
    lifecycle policy runs (`spec:692-702`). An episode whose source conversation
    was deleted has `invalidated_at` set by the same transaction that tombstoned
    the conversation, so this projection reports `INVALID` and the episode stops
    being eligible.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_storage_scoped(
        self, request: EpisodeReadRequest
    ) -> Sequence[StoredEpisodeRow]:
        with self._engine.connect() as connection:
            set_tenant(connection, request.owner_user_id)
            require_tenant_context(connection)

            query = select(episodes_table).where(
                episodes_table.c.owner_user_id == request.owner_user_id
            )
            if request.conversation_id is not None:
                query = query.where(
                    episodes_table.c.conversation_id == request.conversation_id
                )
            if request.occurred_after is not None:
                query = query.where(
                    episodes_table.c.occurred_at >= request.occurred_after
                )
            if request.occurred_before is not None:
                query = query.where(
                    episodes_table.c.occurred_at < request.occurred_before
                )

            rows = connection.execute(query).mappings().all()

        results: list[StoredEpisodeRow] = []
        for row in rows:
            retention_mode = RetentionMode(row["retention_mode"])
            if retention_mode is RetentionMode.USER_DURABLE:
                source_validity = SourceValidity.NOT_REQUIRED
            elif row["invalidated_at"] is None:
                source_validity = SourceValidity.VALID
            else:
                source_validity = SourceValidity.INVALID

            results.append(
                StoredEpisodeRow(
                    episode_id=str(row["episode_id"]),
                    owner_user_id=str(row["owner_user_id"]),
                    conversation_id=str(row["conversation_id"]),
                    actor=str(row["actor"]),
                    event=str(row["event"]),
                    occurred_at=row["occurred_at"],
                    source_message_id=str(row["source_message_id"]),
                    source_outbox_id=str(row["source_outbox_id"]),
                    retention_mode=retention_mode,
                    stamped_generation=int(row["suppression_generation"]),
                    current_generation=int(row["suppression_generation"]),
                    status=VersionStatus(row["status"]),
                    sensitivity=SensitivityBand(row["sensitivity"]),
                    source_validity=source_validity,
                    expires_at=row["expires_at"],
                    unresolved_conflict=bool(row["unresolved_conflict"]),
                )
            )
        return tuple(results)


def record_episode_on(
    connection,
    *,
    candidate,
    created_at: datetime,
    status: VersionStatus = VersionStatus.SHADOW,
) -> bool:
    """Persist one grounded episode candidate; replay-aware and fail-closed.

    The idempotency boundary is the provenance triple
    `(owner_user_id, source_outbox_id, source_message_id)`, backed by a unique
    index. Redelivery or re-extraction of one source therefore cannot create a
    second canonical episode, and the *comparison* is what gives the conflict its
    meaning: a replay with identical authoritative content returns `False`, while
    the same key carrying different content is two contradictory claims about one
    event and raises rather than silently keeping whichever landed first.

    Runs on a caller-owned connection so the episode row, its source-handling
    authority and the outbox success can commit in one transaction (`ADR 0036`).
    """
    values = {
        "episode_id": candidate.candidate_id,
        "owner_user_id": candidate.owner_user_id,
        "conversation_id": candidate.conversation_id,
        "occurred_at": candidate.grounding.occurred_at,
        "payload": {},
        "created_at": created_at,
        "actor": str(candidate.grounding.actor),
        "event": str(candidate.grounding.event),
        "source_message_id": str(candidate.grounding.provenance.source_message_id),
        "source_outbox_id": str(candidate.grounding.provenance.source_outbox_id),
        "retention_mode": RetentionMode(candidate.retention_mode).value,
        "status": VersionStatus(status).value,
        "sensitivity": SensitivityBand(candidate.sensitivity).value,
        "suppression_generation": int(candidate.suppression_generation),
        "unresolved_conflict": False,
        "expires_at": None,
        "invalidated_at": None,
    }

    existing = (
        connection.execute(
            select(episodes_table).where(
                episodes_table.c.owner_user_id == candidate.owner_user_id,
                episodes_table.c.source_outbox_id
                == values["source_outbox_id"],
                episodes_table.c.source_message_id
                == values["source_message_id"],
            )
        )
        .mappings()
        .fetchone()
    )
    if existing is not None:
        _assert_same_episode(existing, values)
        return False

    connection.execute(episodes_table.insert().values(**values))
    return True


def _assert_same_episode(existing, values: dict) -> None:
    """Refuse a replay whose authoritative content differs from the stored row."""
    for field in ("actor", "event", "conversation_id", "retention_mode"):
        if str(existing[field]) != str(values[field]):
            raise MemoryWriteError(
                "An episode already exists for this source with different "
                f"content in '{field}'; one source event cannot be two episodes."
            )


def invalidate_episodes_for_conversation_on(
    connection, *, conversation_id: str, invalidated_at: datetime
) -> int:
    """Mark every episode of a deleted conversation ineligible.

    Called from the same transaction that tombstones the conversation, cancels
    its outbox events and invalidates its `memory_evidence` rows — the existing
    deletion contract (`20260910_03`). Episodes are invalidated rather than
    deleted because a revoke is not an erase (`ADR 0037`), and the read path
    already fails closed on `invalidated_at IS NOT NULL`.

    Returns the number of rows touched so the caller can record it.
    """
    result = connection.execute(
        episodes_table.update()
        .where(
            episodes_table.c.conversation_id == conversation_id,
            episodes_table.c.invalidated_at.is_(None),
        )
        .values(invalidated_at=invalidated_at)
    )
    return int(result.rowcount or 0)
