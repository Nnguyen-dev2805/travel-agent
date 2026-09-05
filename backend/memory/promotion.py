"""Candidate-to-record promotion policy for milestone R6.

Promotion decides which accepted R5 shadow candidates become durable
answer-eligible memory records. The policy is a pure candidate-level
function: the service resolves workspaces, conversations, messages, and
existing active records, and the policy maps one candidate plus that
evidence to a governed outcome. It never calls a model, never touches
storage, and never logs content.

Eligibility follows the approved R6 promotion rules in order: accepted
status, promotable scope, promotable type, minimum confidence, promotable
sensitivity, resolved provenance, allow-listed reason, and duplicate
detection. Corrections additionally resolve supersession targets from scope
identity and record age only, never from text similarity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from backend.memory.models import (
    MemoryCandidate,
    MemoryRecordScope,
    MemoryRecordStatus,
    MemoryCandidateStatus,
    MemoryScope,
    MemoryType,
    PolicyReason,
    PromotionSkipReason,
    SensitivityLabel,
)

MEMORY_PROMOTION_MIN_CONFIDENCE = 0.75
"""Minimum candidate confidence eligible for promotion per the R6 spec."""

PROMOTABLE_REASONS = frozenset(
    {
        PolicyReason.SUPPORTED_PREFERENCE,
        PolicyReason.SUPPORTED_CONSTRAINT,
        PolicyReason.SUPPORTED_PROFILE_FACT,
        PolicyReason.SUPPORTED_TRIP_DECISION,
        PolicyReason.EXPLICIT_CORRECTION,
    }
)
"""Policy reasons eligible for promotion.

`SUPPORTED_PROFILE_FACT` and `SUPPORTED_TRIP_DECISION` currently have no R5
producer, so they are forward-compatible entries: reachable through directly
constructed fixtures, never widened by changing R5 extraction here.
"""

_PROMOTABLE_SENSITIVITIES = frozenset(
    {SensitivityLabel.NONE, SensitivityLabel.PERSONAL}
)


@dataclass(frozen=True)
class PromotionAssessment:
    """One candidate's promotion decision before persistence.

    `scope_id` is resolved only when the outcome is `PROMOTED`.
    `superseded_ids` holds supersession targets oldest-first by the
    `(created_at, source_sequence)` age key, and is empty unless the
    candidate is a promoted correction with targets.
    """

    candidate_id: str
    outcome: PromotionSkipReason
    scope_id: Optional[str] = field(default=None)
    superseded_ids: tuple[str, ...] = field(default_factory=tuple)


class MemoryPromotionPolicy:
    """Decide one candidate's promotion outcome with a governed reason."""

    def __init__(self, min_confidence: float = MEMORY_PROMOTION_MIN_CONFIDENCE):
        self._min_confidence = min_confidence

    @property
    def min_confidence(self) -> float:
        return self._min_confidence

    def assess(
        self,
        candidate: MemoryCandidate,
        *,
        workspace,
        conversation,
        message_exists: bool,
        active_records,
    ) -> PromotionAssessment:
        """Assess one candidate against promotion rules in spec order."""
        if candidate.status is not MemoryCandidateStatus.ACCEPTED:
            return self._skip(candidate, PromotionSkipReason.NOT_ACCEPTED)
        if candidate.proposed_scope is MemoryScope.NONE:
            return self._skip(candidate, PromotionSkipReason.SCOPE_NOT_PROMOTABLE)
        if candidate.proposed_type in (MemoryType.NONE, MemoryType.SAFETY_NOTE):
            return self._skip(candidate, PromotionSkipReason.TYPE_NOT_PROMOTABLE)
        if candidate.confidence < self._min_confidence:
            return self._skip(candidate, PromotionSkipReason.BELOW_MIN_CONFIDENCE)
        if candidate.sensitivity_label not in _PROMOTABLE_SENSITIVITIES:
            return self._skip(candidate, PromotionSkipReason.SENSITIVITY_NOT_PROMOTABLE)
        if not self._provenance_resolves(candidate, workspace, conversation):
            return self._skip(candidate, PromotionSkipReason.PROVENANCE_UNRESOLVED)
        if not message_exists:
            return self._skip(candidate, PromotionSkipReason.PROVENANCE_UNRESOLVED)
        if candidate.reason not in PROMOTABLE_REASONS:
            return self._skip(candidate, PromotionSkipReason.REASON_NOT_PROMOTABLE)
        if self._is_duplicate(candidate, active_records):
            return self._skip(candidate, PromotionSkipReason.DUPLICATE_ACTIVE_RECORD)
        scope_id = self._resolve_scope_id(candidate, workspace)
        superseded: tuple[str, ...] = ()
        if candidate.proposed_type is MemoryType.CORRECTION:
            superseded = self._supersession_targets(
                candidate, workspace, scope_id, active_records
            )
        return PromotionAssessment(
            candidate_id=candidate.candidate_id,
            outcome=PromotionSkipReason.PROMOTED,
            scope_id=scope_id,
            superseded_ids=superseded,
        )

    @staticmethod
    def _skip(
        candidate: MemoryCandidate, outcome: PromotionSkipReason
    ) -> PromotionAssessment:
        return PromotionAssessment(candidate_id=candidate.candidate_id, outcome=outcome)

    @staticmethod
    def _provenance_resolves(
        candidate: MemoryCandidate, workspace, conversation
    ) -> bool:
        if workspace is None or conversation is None:
            return False
        return (
            conversation.workspace_id == candidate.workspace_id
            and candidate.conversation_id == conversation.conversation_id
        )

    @staticmethod
    def _resolve_scope_id(candidate: MemoryCandidate, workspace) -> str:
        if candidate.proposed_scope is MemoryScope.USER:
            return workspace.owner_user_id
        if candidate.proposed_scope is MemoryScope.WORKSPACE:
            return candidate.workspace_id
        return candidate.conversation_id

    @staticmethod
    def _is_duplicate(candidate: MemoryCandidate, active_records) -> bool:
        return any(
            record.text == candidate.text
            and record.scope.value == candidate.proposed_scope.value
            and record.source_candidate_id == candidate.candidate_id
            for record in active_records
        )

    @staticmethod
    def _supersession_targets(
        candidate: MemoryCandidate, workspace, scope_id: str, active_records
    ) -> tuple[str, ...]:
        """Find active records one correction suppresses, oldest first.

        Targets share the owner, scope, and scope identifier, are not
        corrections themselves, and are not newer than the correction under
        the `(created_at, source_sequence)` age key. Scope isolation comes
        from the scope match alone: a user-scope correction raised in one
        conversation can suppress a user-scope record created in another,
        while a record in any other scope is never a target.
        """
        scope_value = candidate.proposed_scope.value
        key = (candidate.created_at, candidate.source_sequence)
        targets = [
            record
            for record in active_records
            if record.status is MemoryRecordStatus.ACTIVE
            and record.owner_user_id == workspace.owner_user_id
            and record.scope.value == scope_value
            and record.scope_id == scope_id
            and record.memory_type.value != MemoryType.CORRECTION.value
            and (record.created_at, record.source_sequence) <= key
        ]
        targets.sort(
            key=lambda record: (
                record.created_at,
                record.source_sequence,
                record.memory_id,
            )
        )
        return tuple(record.memory_id for record in targets)
