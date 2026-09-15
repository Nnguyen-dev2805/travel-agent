"""The single owner of inferred Memory activation rules (ADR 0038 / Plan v0.18).

Pure deterministic domain policy: no database connections, SQL/ORM queries, I/O,
clock, or model calls. Decides whether an inferred candidate mutation achieves
ACTIVE status or remains SHADOW.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.memory.source_handling import MemoryFamily
from backend.memory.write_pipeline.models import (
    EvidenceIdentity,
    MemoryEvidence,
    MemoryScope,
    VersionStatus,
)


class ActivationReason(str, Enum):
    """Closed reason vocabulary for activation decisions, in precedence order."""

    LIFECYCLE_DENIED = "lifecycle_denied"
    PROCEDURAL_CHAT_FORBIDDEN = "procedural_chat_forbidden"
    CONSTRAINTS_SHADOW_ONLY = "constraints_shadow_only"
    ROLLOUT_FLAG_DISABLED = "rollout_flag_disabled"
    TYPE_EVALUATION_INCONCLUSIVE = "type_evaluation_inconclusive"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    INSUFFICIENT_TURNS = "insufficient_turns"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INSUFFICIENT_CONVERSATIONS = "insufficient_conversations"
    INVALID_SCOPE = "invalid_scope"
    ELIGIBLE_ACTIVE = "eligible_active"


@dataclass(frozen=True)
class ActivationFacts:
    """Typed, I/O-free snapshot of facts required to evaluate activation.

    Every fact that could *permit* activation is required. A permissive default
    would let a caller that forgot to supply one authorize an active version by
    omission — which is exactly how the per-key evaluation gate came to be open
    in its first implementation. Only two fields carry defaults, and both are
    fail-closed: `inferred_activation_enabled=False` denies, and an empty
    `active_evidence` can only lower support.
    """

    scope: MemoryScope | str
    canonical_key: str
    target_conversation_id: str | None
    candidate_evidence: Sequence[EvidenceIdentity | MemoryEvidence]
    has_unresolved_conflict: bool
    is_constraint: bool
    lifecycle_eligible: bool
    type_evaluation_conclusive: bool
    memory_family: MemoryFamily | str
    active_evidence: Sequence[EvidenceIdentity | MemoryEvidence] = field(
        default_factory=tuple
    )
    inferred_activation_enabled: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.scope, str):
            object.__setattr__(self, "scope", MemoryScope(self.scope))
        if isinstance(self.memory_family, str):
            object.__setattr__(
                self, "memory_family", MemoryFamily(self.memory_family)
            )


@dataclass(frozen=True)
class ActivationDecision:
    """The activation decision and reason."""

    target_status: VersionStatus
    reason: ActivationReason
    eligible: bool


def _evidence_tuple(item: Any) -> tuple[str, str, str]:
    return (
        getattr(item, "evidence_id", ""),
        getattr(item, "conversation_id", ""),
        getattr(item, "source_message_id", ""),
    )


class MemoryActivationPolicy:
    """Pure deterministic domain policy governing inferred memory activation."""

    def evaluate(self, facts: ActivationFacts) -> ActivationDecision:
        # 1. Lifecycle prerequisite check
        if not facts.lifecycle_eligible:
            return ActivationDecision(
                target_status=VersionStatus.SHADOW,
                reason=ActivationReason.LIFECYCLE_DENIED,
                eligible=False,
            )

        # 2. Procedural memory refusal
        if (
            facts.memory_family is MemoryFamily.PROCEDURAL
            or facts.canonical_key.startswith("procedural.")
        ):
            return ActivationDecision(
                target_status=VersionStatus.SHADOW,
                reason=ActivationReason.PROCEDURAL_CHAT_FORBIDDEN,
                eligible=False,
            )

        # 3. Inferred constraint check
        if (
            facts.is_constraint
            or facts.canonical_key.startswith("travel.constraint.")
        ):
            return ActivationDecision(
                target_status=VersionStatus.SHADOW,
                reason=ActivationReason.CONSTRAINTS_SHADOW_ONLY,
                eligible=False,
            )

        # 4. Rollout gate
        if not facts.inferred_activation_enabled:
            return ActivationDecision(
                target_status=VersionStatus.SHADOW,
                reason=ActivationReason.ROLLOUT_FLAG_DISABLED,
                eligible=False,
            )

        # 5. Type-specific evaluation gate
        if not facts.type_evaluation_conclusive:
            return ActivationDecision(
                target_status=VersionStatus.SHADOW,
                reason=ActivationReason.TYPE_EVALUATION_INCONCLUSIVE,
                eligible=False,
            )

        # 6. Unresolved conflict check
        if facts.has_unresolved_conflict:
            return ActivationDecision(
                target_status=VersionStatus.SHADOW,
                reason=ActivationReason.UNRESOLVED_CONFLICT,
                eligible=False,
            )

        # 7. Deduplicate evidence by provenance identity (conversation_id, source_message_id)
        all_evidence = list(facts.active_evidence) + list(facts.candidate_evidence)
        seen_provenance: set[tuple[str, str]] = set()
        unique_evidence: list[tuple[str, str, str]] = []
        for ev in all_evidence:
            eid, cid, mid = _evidence_tuple(ev)
            key = (cid, mid)
            if key not in seen_provenance:
                seen_provenance.add(key)
                unique_evidence.append((eid, cid, mid))

        # 8. Scope-specific activation thresholds
        if facts.scope == MemoryScope.CONVERSATION:
            conv_id = facts.target_conversation_id or ""
            conv_turns = [mid for _, cid, mid in unique_evidence if cid == conv_id]
            if len(conv_turns) < 2:
                return ActivationDecision(
                    target_status=VersionStatus.SHADOW,
                    reason=ActivationReason.INSUFFICIENT_TURNS,
                    eligible=False,
                )
            return ActivationDecision(
                target_status=VersionStatus.ACTIVE,
                reason=ActivationReason.ELIGIBLE_ACTIVE,
                eligible=True,
            )

        if facts.scope == MemoryScope.USER:
            if len(unique_evidence) < 3:
                return ActivationDecision(
                    target_status=VersionStatus.SHADOW,
                    reason=ActivationReason.INSUFFICIENT_EVIDENCE,
                    eligible=False,
                )
            distinct_convs = {cid for _, cid, _ in unique_evidence}
            if len(distinct_convs) < 2:
                return ActivationDecision(
                    target_status=VersionStatus.SHADOW,
                    reason=ActivationReason.INSUFFICIENT_CONVERSATIONS,
                    eligible=False,
                )
            return ActivationDecision(
                target_status=VersionStatus.ACTIVE,
                reason=ActivationReason.ELIGIBLE_ACTIVE,
                eligible=True,
            )

        return ActivationDecision(
            target_status=VersionStatus.SHADOW,
            reason=ActivationReason.INVALID_SCOPE,
            eligible=False,
        )
