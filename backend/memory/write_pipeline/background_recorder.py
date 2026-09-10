"""Narrow background recording interface for semantic memory.

Per ADR 0020, ADR 0021, and ADR 0022, background extraction is strictly separated
from user-initiated memory management. Background extraction produces shadow
observations only and never creates active versions or confirmable proposals.

BackgroundMemoryRecorder provides a single write-pipeline entry point:
`record(candidate: ShadowCandidate) -> BackgroundRecordResult`.
It exposes NO user-initiated methods (no remember, correct, forget, toggle, preview, confirm, expand).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Callable

from backend.memory.write_pipeline.models import (
    Authority,
    DecisionOutcome,
    MemoryCandidate,
    MemoryChangeSet,
    MemoryEvidence,
    MemoryOperation,
    MemoryRelation,
    MemoryScope,
    MemoryVersion,
    SensitivityBand,
    assertion_identity,
    new_candidate_id,
    new_evidence_id,
    CANDIDATE_ID_PREFIX,
    EVIDENCE_ID_PREFIX,
)
from backend.memory.write_pipeline.policy import (
    Actor,
    DecisionContext,
    Origin,
    decide_candidate,
)
from backend.memory.write_pipeline.resolver import resolve_change
from backend.memory.write_pipeline.uow import MemoryUnitOfWork
from backend.security.models import AuthenticatedPrincipal, AuthMode

logger = logging.getLogger("travel_agent_memory_recorder")

MIN_CONFIDENCE_THRESHOLD = 0.5


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ShadowCandidate:
    """Input candidate for background memory recording."""

    candidate_id: str
    owner_user_id: str
    canonical_key: str
    normalized_value: Any
    display_text: str
    authority: Authority = Authority.REPEATED_INFERENCE
    sensitivity: SensitivityBand = SensitivityBand.ORDINARY_PERSONAL
    scope: MemoryScope = MemoryScope.USER
    scope_id: str = "global"
    confidence: float = 1.0
    subject_key: str | None = None
    relation: MemoryRelation = MemoryRelation.UNRELATED
    condition_fingerprint: str | None = None
    observed_at: datetime | None = None
    conversation_id: str | None = None
    source_message_id: str | None = None


@dataclass(frozen=True)
class BackgroundRecordResult:
    """Outcome of one background memory recording attempt."""

    status: str  # "recorded", "held_sensitive", "rejected", "low_confidence"
    candidate_id: str
    decision_outcome: DecisionOutcome
    operation: MemoryOperation
    reason: str
    write_result: Any = None


class BackgroundMemoryRecorder:
    """Narrow background recording service for shadow memory extraction.

    Coordinates:
    - Policy evaluation (decide_candidate)
    - Conflict and cardinality resolution (resolve_change)
    - Atomic persistence through MemoryUnitOfWork
    """

    def __init__(
        self,
        policy: Any = None,
        resolver: Any = None,
        uow_factory: Callable[[], MemoryUnitOfWork] | MemoryUnitOfWork | None = None,
        *,
        uow: MemoryUnitOfWork | None = None,
        min_confidence: float = MIN_CONFIDENCE_THRESHOLD,
    ) -> None:
        self._policy = policy if policy is not None else decide_candidate
        self._resolver = resolver if resolver is not None else resolve_change
        resolved_uow = uow_factory if uow_factory is not None else uow
        if resolved_uow is None:
            raise ValueError("uow_factory or uow must be provided")
        self._uow_factory = resolved_uow if callable(resolved_uow) else lambda: resolved_uow
        self._min_confidence = min_confidence

    def _to_memory_candidate(self, candidate: ShadowCandidate | MemoryCandidate) -> MemoryCandidate:
        if isinstance(candidate, MemoryCandidate):
            return candidate
        cid = candidate.candidate_id or new_candidate_id()
        if not cid.startswith(CANDIDATE_ID_PREFIX):
            cid = f"{CANDIDATE_ID_PREFIX}{cid}"
        ev_id = getattr(candidate, "source_message_id", None) or new_evidence_id()
        if not ev_id.startswith(EVIDENCE_ID_PREFIX):
            ev_id = f"{EVIDENCE_ID_PREFIX}{ev_id}"
        return MemoryCandidate(
            candidate_id=cid,
            evidence_ids=(ev_id,),
            owner_user_id=candidate.owner_user_id,
            scope=candidate.scope,
            conversation_id=getattr(candidate, "conversation_id", None),
            canonical_key=candidate.canonical_key,
            normalized_value=str(candidate.normalized_value),
            display_text=candidate.display_text,
            authority=candidate.authority,
            sensitivity=candidate.sensitivity,
            condition=getattr(candidate, "condition", "") or "",
            subject_key=getattr(candidate, "subject_key", None) or "self",
            observed_at=candidate.observed_at or _utc_now(),
        )

    def _record_core(self, candidate: ShadowCandidate | MemoryCandidate) -> BackgroundRecordResult:
        # 1. Confidence check
        confidence = getattr(candidate, "confidence", 1.0)
        if confidence < self._min_confidence:
            return BackgroundRecordResult(
                status="low_confidence",
                candidate_id=candidate.candidate_id,
                decision_outcome=DecisionOutcome.REJECTED,
                operation=MemoryOperation.NOOP,
                reason=f"confidence_{confidence:.2f}_below_threshold_{self._min_confidence:.2f}",
            )

        mem_candidate = self._to_memory_candidate(candidate)

        # 2. Policy check
        ctx = DecisionContext(
            actor=Actor.USER,
            authenticated=True,
            origin=Origin.BACKGROUND_CHAT,
            source_deleted=False,
        )
        if callable(self._policy):
            decision = self._policy(mem_candidate, ctx)
        else:
            decision = self._policy.decide(mem_candidate, ctx)

        # Non-storable or rejected candidates cause NO mutation
        if decision.outcome in (DecisionOutcome.REJECTED, DecisionOutcome.INVALID):
            reason_str = decision.reason.value if hasattr(decision.reason, "value") else str(decision.reason)
            return BackgroundRecordResult(
                status="rejected",
                candidate_id=candidate.candidate_id,
                decision_outcome=decision.outcome,
                operation=MemoryOperation.NOOP,
                reason=reason_str,
            )

        if decision.outcome == DecisionOutcome.HELD_SENSITIVE:
            reason_str = decision.reason.value if hasattr(decision.reason, "value") else str(decision.reason)
            return BackgroundRecordResult(
                status="held_sensitive",
                candidate_id=candidate.candidate_id,
                decision_outcome=decision.outcome,
                operation=MemoryOperation.NOOP,
                reason=reason_str,
            )

        # 3. Resolve candidate against existing active versions
        uow = self._uow_factory()
        existing_versions: tuple[MemoryVersion, ...] = ()
        if hasattr(uow, "get_active_versions"):
            existing_versions = tuple(
                uow.get_active_versions(mem_candidate.owner_user_id, mem_candidate.canonical_key)
            )
        elif hasattr(uow, "list_active_versions"):
            existing_versions = tuple(uow.list_active_versions(mem_candidate.owner_user_id))

        relation = getattr(candidate, "relation", None) or MemoryRelation.UNRELATED
        if callable(self._resolver):
            try:
                resolved_change = self._resolver(mem_candidate, existing_versions, relation)
            except TypeError:
                resolved_change = self._resolver(mem_candidate, existing_versions)
        else:
            try:
                resolved_change = self._resolver.resolve(mem_candidate, existing_versions, relation)
            except TypeError:
                resolved_change = self._resolver.resolve(mem_candidate, existing_versions)

        # Invariant: background extraction produces shadow evidence only (never active versions)
        reason_str = decision.reason.value if hasattr(decision.reason, "value") else str(decision.reason)
        shadow_change = MemoryChangeSet(
            operation=MemoryOperation.NOOP,
            identity=assertion_identity(mem_candidate),
            new_version=None,
            superseded_version_ids=(),
            reference_version_id=None,
            reason=reason_str,
        )

        principal = AuthenticatedPrincipal(
            owner_user_id=mem_candidate.owner_user_id,
            auth_mode=AuthMode.AUTHENTICATED,
            credential_label="background_recorder",
        )

        conv_id = getattr(candidate, "conversation_id", None)
        msg_id = getattr(candidate, "source_message_id", None)
        evidence = MemoryEvidence(
            evidence_id=new_evidence_id(),
            owner_user_id=mem_candidate.owner_user_id,
            conversation_id=conv_id,
            source_message_id=msg_id,
            display_text=mem_candidate.display_text,
            authority=mem_candidate.authority,
            observed_at=mem_candidate.observed_at or _utc_now(),
        )

        write_result = uow.apply_memory_change(
            shadow_change,
            principal,
            evidence=(evidence,),
            decision=decision,
            idempotency_key=f"bg_rec_{candidate.candidate_id}",
        )

        return BackgroundRecordResult(
            status="recorded",
            candidate_id=candidate.candidate_id,
            decision_outcome=decision.outcome,
            operation=shadow_change.operation,
            reason=reason_str,
            write_result=write_result,
        )

    async def record(self, candidate: ShadowCandidate | MemoryCandidate) -> BackgroundRecordResult:
        """Asynchronously record a background memory candidate as shadow evidence."""
        return self._record_core(candidate)

    def record_sync(self, candidate: ShadowCandidate | MemoryCandidate) -> BackgroundRecordResult:
        """Synchronously record a background memory candidate as shadow evidence."""
        return self._record_core(candidate)
