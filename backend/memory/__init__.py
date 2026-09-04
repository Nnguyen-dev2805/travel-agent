"""Memory candidate contracts for runtime milestone R5.

Per ADR 0006 this package owns memory candidate contracts, extraction
interfaces, policy decisions, repository interfaces, and local SQLite
persistence for candidate and shadow-run evidence. `models.py` holds the
value contracts only and depends on the Python standard library.

R5 is shadow-only: `accepted` means accepted into the shadow candidate set
for evaluation, not promoted into answer-eligible memory. No candidate from
this package may enter RAG retrieval, context assembly, prompts, or
generated answers.
"""

from backend.memory.extraction import (
    EXTRACTOR_ID,
    MemoryExtractor,
    RuleBasedMemoryExtractor,
)
from backend.memory.models import (
    CANDIDATE_TEXT_MAX_LENGTH,
    EVIDENCE_SUMMARY_MAX_LENGTH,
    MEMORY_CANDIDATE_ID_PREFIX,
    MEMORY_RUN_ID_PREFIX,
    MemoryCandidate,
    MemoryCandidateDraft,
    MemoryCandidateStatus,
    MemoryExtractionRun,
    MemoryExtractionTrigger,
    MemoryRunStatus,
    MemoryScope,
    MemorySourceMessage,
    MemoryType,
    MemoryValidationError,
    PolicyReason,
    SensitivityLabel,
    generate_memory_candidate_id,
    generate_memory_run_id,
    utc_now,
)
from backend.memory.policy import (
    POLICY_CONFIDENCE_ACCEPT,
    POLICY_CONFIDENCE_FLOOR,
    POLICY_ID,
    MemoryPolicy,
)

__all__ = [
    "CANDIDATE_TEXT_MAX_LENGTH",
    "EVIDENCE_SUMMARY_MAX_LENGTH",
    "EXTRACTOR_ID",
    "MEMORY_CANDIDATE_ID_PREFIX",
    "MEMORY_RUN_ID_PREFIX",
    "POLICY_CONFIDENCE_ACCEPT",
    "POLICY_CONFIDENCE_FLOOR",
    "POLICY_ID",
    "MemoryExtractor",
    "MemoryPolicy",
    "MemoryCandidate",
    "MemoryCandidateDraft",
    "MemoryCandidateStatus",
    "MemoryExtractionRun",
    "MemoryExtractionTrigger",
    "MemoryRunStatus",
    "MemoryScope",
    "MemorySourceMessage",
    "MemoryType",
    "MemoryValidationError",
    "PolicyReason",
    "SensitivityLabel",
    "RuleBasedMemoryExtractor",
    "generate_memory_candidate_id",
    "generate_memory_run_id",
    "utc_now",
]
