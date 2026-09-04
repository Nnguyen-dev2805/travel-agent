"""Deterministic memory policy for milestone R5.

Policy is a pure draft-to-decision function. Extraction proposes; policy
disposes. It never calls a model, never touches storage, and never logs
content: decisions depend only on the draft's trace fields, scope, type,
confidence, sensitivity, and text presence.

Decision order is safety-first: trace exclusion, non-user provenance, and
secret-like sensitivity fail closed before any acceptance mapping runs.
Thresholds are module constants so evaluation fixtures pin them:

- `POLICY_CONFIDENCE_FLOOR` (0.5): below this a draft is `low_confidence`.
- `POLICY_CONFIDENCE_ACCEPT` (0.7): below this a surviving draft is
  `ambiguous`; at or above it a supported type is accepted.
"""

from __future__ import annotations

import dataclasses

from backend.memory.models import (
    MemoryCandidateDraft,
    MemoryCandidateStatus,
    MemoryScope,
    MemoryType,
    PolicyReason,
    SensitivityLabel,
)

POLICY_ID = "policy-v1"
POLICY_CONFIDENCE_FLOOR = 0.5
POLICY_CONFIDENCE_ACCEPT = 0.7

_USER_SOURCES = frozenset({"ui", "import"})

_ACCEPT_REASONS = {
    MemoryType.PREFERENCE: PolicyReason.SUPPORTED_PREFERENCE,
    MemoryType.CONSTRAINT: PolicyReason.SUPPORTED_CONSTRAINT,
    MemoryType.PROFILE_FACT: PolicyReason.SUPPORTED_PROFILE_FACT,
    MemoryType.DECISION: PolicyReason.SUPPORTED_TRIP_DECISION,
    MemoryType.CORRECTION: PolicyReason.EXPLICIT_CORRECTION,
}


def _is_wrong_scope(draft: MemoryCandidateDraft) -> bool:
    if draft.proposed_type is MemoryType.DECISION:
        return draft.proposed_scope is not MemoryScope.WORKSPACE
    if draft.proposed_type in (
        MemoryType.PREFERENCE,
        MemoryType.PROFILE_FACT,
        MemoryType.CORRECTION,
    ):
        return draft.proposed_scope is MemoryScope.CONVERSATION
    return False


class MemoryPolicy:
    """Decide one draft's shadow status with a governed reason code."""

    policy_id = POLICY_ID

    def evaluate(self, draft: MemoryCandidateDraft) -> MemoryCandidateDraft:
        """Return a copy of the draft carrying the policy decision."""
        status, reason = self._decide(draft)
        return dataclasses.replace(draft, status=status, reason=reason)

    def _decide(
        self, draft: MemoryCandidateDraft
    ) -> tuple[MemoryCandidateStatus, PolicyReason]:
        if draft.trace_visibility != "included":
            return MemoryCandidateStatus.REJECTED, PolicyReason.TRACE_EXCLUDED
        if draft.role != "user" or draft.source not in _USER_SOURCES:
            return MemoryCandidateStatus.REJECTED, PolicyReason.SYSTEM_GENERATED
        if draft.sensitivity_label in (
            SensitivityLabel.SECRET,
            SensitivityLabel.UNSAFE,
        ):
            return MemoryCandidateStatus.REJECTED, PolicyReason.SECRET_LIKE
        if (
            draft.proposed_scope is MemoryScope.NONE
            or draft.proposed_type is MemoryType.NONE
        ):
            return MemoryCandidateStatus.REJECTED, PolicyReason.NO_MEMORY_SIGNAL
        if not draft.text:
            return MemoryCandidateStatus.REJECTED, PolicyReason.UNSUPPORTED
        if draft.confidence < POLICY_CONFIDENCE_FLOOR:
            return MemoryCandidateStatus.REJECTED, PolicyReason.LOW_CONFIDENCE
        if draft.sensitivity_label in (
            SensitivityLabel.PERSONAL,
            SensitivityLabel.SENSITIVE,
        ):
            return (
                MemoryCandidateStatus.NEEDS_USER_ACTION,
                PolicyReason.SENSITIVE,
            )
        if _is_wrong_scope(draft):
            return MemoryCandidateStatus.REJECTED, PolicyReason.WRONG_SCOPE
        if draft.proposed_type is MemoryType.EPISODE:
            return MemoryCandidateStatus.REJECTED, PolicyReason.TRANSIENT
        if draft.proposed_type is MemoryType.SAFETY_NOTE:
            return (
                MemoryCandidateStatus.NEEDS_USER_ACTION,
                PolicyReason.SENSITIVE,
            )
        if draft.confidence < POLICY_CONFIDENCE_ACCEPT:
            return MemoryCandidateStatus.REJECTED, PolicyReason.AMBIGUOUS
        return (
            MemoryCandidateStatus.ACCEPTED,
            _ACCEPT_REASONS[draft.proposed_type],
        )
