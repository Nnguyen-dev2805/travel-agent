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

Age means user-intent order, not pipeline wall-clock: both sides of the
supersession age key use source-message creation times resolved through
stored provenance, because extraction and promotion timestamps cannot order
two candidates born in the same run. A same-run correction therefore
suppresses the inference it answers, which wall-clock comparison provably
misses.

Message-time keys make one exclusion necessary. R5 runs every draft builder
over each message, so one sentence can yield a correction and the inference
it states, tying on the age key exactly. A sibling from the same source
message is the same intent rather than an older inference, so it is never a
supersession target; without that rule the tie-suppressing bias would bury
the very memory the user just expressed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Optional, Sequence

from backend.memory.models import (
    MemoryCandidate,
    MemoryRecordScope,
    MemoryRecordStatus,
    MemoryCandidateStatus,
    MemoryRecordType,
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
    message-time age key, and is empty unless the candidate is a promoted
    correction with targets.
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
        message_created_at: Optional[datetime],
        active_records,
        record_source_times: Mapping[str, datetime],
        known_records=None,
    ) -> PromotionAssessment:
        """Assess one candidate against promotion rules in spec order.

        `message_created_at` is the candidate's source message creation time,
        or `None` when the message does not resolve. Only the timestamp is
        taken, never the message object, so this policy holds no user
        content. `record_source_times` maps source message ids to their
        creation times, so a record's age follows its source message rather
        than the promotion wall-clock that created it. Records whose message
        cannot be resolved fall back to record creation time.
        `known_records` is every record the service knows, including
        superseded ones; duplicate detection reads it because the record
        table constrains `source_candidate_id` across all lifecycles, so a
        rerun after a supersession must skip rather than reinsert.
        Supersession targets still come from `active_records` alone. Defaults
        to `active_records` when the caller tracks no wider set.
        """
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
        if message_created_at is None:
            return self._skip(candidate, PromotionSkipReason.PROVENANCE_UNRESOLVED)
        if candidate.reason not in PROMOTABLE_REASONS:
            return self._skip(candidate, PromotionSkipReason.REASON_NOT_PROMOTABLE)
        known = active_records if known_records is None else known_records
        duplicate = self._find_duplicate(candidate, known)
        if duplicate is not None:
            if duplicate.status is MemoryRecordStatus.ACTIVE:
                return self._skip(
                    candidate, PromotionSkipReason.DUPLICATE_ACTIVE_RECORD
                )
            return self._skip(
                candidate, PromotionSkipReason.DUPLICATE_SUPERSEDED_RECORD
            )
        scope_id = self._resolve_scope_id(candidate, workspace)
        superseded: tuple[str, ...] = ()
        if candidate.proposed_type is MemoryType.CORRECTION:
            superseded = self._supersession_targets(
                candidate,
                message_created_at,
                workspace,
                scope_id,
                active_records,
                record_source_times,
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
    def _find_duplicate(candidate: MemoryCandidate, known_records):
        """Return the known record from the same source candidate, if any."""
        for record in known_records:
            if (
                record.text == candidate.text
                and record.scope.value == candidate.proposed_scope.value
                and record.source_candidate_id == candidate.candidate_id
            ):
                return record
        return None

    @staticmethod
    def _supersession_targets(
        candidate: MemoryCandidate,
        message_created_at: datetime,
        workspace,
        scope_id: str,
        active_records,
        record_source_times: Mapping[str, datetime],
    ) -> tuple[str, ...]:
        """Find active records one correction suppresses, oldest first.

        Targets share the owner, scope, and scope identifier, are not
        corrections themselves, come from a different source message, and are
        not newer than the correction under the message-time age key
        `(source_message.created_at, source_sequence)`. A record tying on both
        values counts as older, erring toward forgetting rather than letting an
        older inference outrank a newer explicit correction.

        The same-message exclusion is what keeps that bias honest. R5 runs
        every draft builder over one message, so a single sentence such as
        "actually I prefer mountains, please fix that" yields both a
        correction and the preference it states. Those two share the age key
        exactly, so a tie-suppressing rule without this exclusion would bury
        the preference the user just expressed. A sibling from the same
        utterance is the same intent, not an older inference to correct.

        Scope isolation comes from the scope match alone: a user-scope
        correction raised in one conversation can suppress a user-scope record
        created in another.
        """
        scope_value = candidate.proposed_scope.value
        key = (message_created_at, candidate.source_sequence)
        targets = [
            record
            for record in active_records
            if record.status is MemoryRecordStatus.ACTIVE
            and record.owner_user_id == workspace.owner_user_id
            and record.scope.value == scope_value
            and record.scope_id == scope_id
            and record.memory_type is not MemoryRecordType.CORRECTION
            and record.source_message_id != candidate.source_message_id
            and (
                record_source_times.get(record.source_message_id, record.created_at),
                record.source_sequence,
            )
            <= key
        ]
        targets.sort(
            key=lambda record: (
                record_source_times.get(record.source_message_id, record.created_at),
                record.source_sequence,
                record.memory_id,
            )
        )
        return tuple(record.memory_id for record in targets)
