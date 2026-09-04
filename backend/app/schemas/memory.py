"""Public request and response JSON shapes for the R5 memory routes.

These schemas own the HTTP contract only. Run and candidate identity,
timestamps, counts, and policy decisions are server-owned and never accepted
from a request body. The manual trigger route accepts an empty body or `{}`
only: any caller-supplied field, including `trigger`, is refused with `422`.

Candidate responses deliberately exclude candidate `text`. They expose
identifiers, status values, confidence, controlled reason codes, sensitivity
labels, and the redacted evidence summary only, so no response can carry raw
source message content.

List responses are objects rather than bare arrays so a later milestone can
add pagination metadata without a breaking change.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

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


class MemoryExtractionRequest(BaseModel):
    """Trigger one manual shadow extraction run.

    The model carries no fields: the public route always creates a `manual`
    run, and any submitted field is rejected instead of interpreted.
    """

    model_config = ConfigDict(extra="forbid")


class MemoryExtractionRunResponse(BaseModel):
    """One shadow extraction run with its per-status candidate counts."""

    run_id: str
    workspace_id: str
    conversation_id: str
    trigger: MemoryExtractionTrigger
    extractor_id: str
    policy_id: str
    status: MemoryRunStatus
    started_at: datetime
    finished_at: Optional[datetime]
    candidate_count: int
    accepted_count: int
    rejected_count: int
    needs_user_action_count: int
    invalid_count: int
    failure_reason: Optional[str]

    @classmethod
    def from_domain(cls, run: MemoryExtractionRun) -> "MemoryExtractionRunResponse":
        return cls(
            run_id=run.run_id,
            workspace_id=run.workspace_id,
            conversation_id=run.conversation_id,
            trigger=run.trigger,
            extractor_id=run.extractor_id,
            policy_id=run.policy_id,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            candidate_count=run.candidate_count,
            accepted_count=run.accepted_count,
            rejected_count=run.rejected_count,
            needs_user_action_count=run.needs_user_action_count,
            invalid_count=run.invalid_count,
            failure_reason=run.failure_reason,
        )


class MemoryExtractionRunListResponse(BaseModel):
    """Extraction runs for one workspace, newest first."""

    runs: List[MemoryExtractionRunResponse] = Field(default_factory=list)


class MemoryCandidateResponse(BaseModel):
    """One shadow memory candidate with its policy decision.

    Candidate `text` is intentionally absent: review evidence travels in the
    redacted evidence summary, never as raw content.
    """

    candidate_id: str
    run_id: str
    workspace_id: str
    conversation_id: str
    source_message_id: str
    source_sequence: int
    proposed_scope: MemoryScope
    proposed_type: MemoryType
    status: MemoryCandidateStatus
    confidence: float
    sensitivity_label: SensitivityLabel
    evidence_summary: str
    reason: PolicyReason
    created_at: datetime

    @classmethod
    def from_domain(cls, candidate: MemoryCandidate) -> "MemoryCandidateResponse":
        return cls(
            candidate_id=candidate.candidate_id,
            run_id=candidate.run_id,
            workspace_id=candidate.workspace_id,
            conversation_id=candidate.conversation_id,
            source_message_id=candidate.source_message_id,
            source_sequence=candidate.source_sequence,
            proposed_scope=candidate.proposed_scope,
            proposed_type=candidate.proposed_type,
            status=candidate.status,
            confidence=candidate.confidence,
            sensitivity_label=candidate.sensitivity_label,
            evidence_summary=candidate.evidence_summary,
            reason=candidate.reason,
            created_at=candidate.created_at,
        )


class MemoryCandidateListResponse(BaseModel):
    """Candidate evidence in governed run and source order."""

    candidates: List[MemoryCandidateResponse] = Field(default_factory=list)
