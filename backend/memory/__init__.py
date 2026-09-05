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
    SECRET_PATTERNS,
    MemoryExtractor,
    RuleBasedMemoryExtractor,
)
from backend.memory.models import (
    CANDIDATE_TEXT_MAX_LENGTH,
    EVIDENCE_SUMMARY_MAX_LENGTH,
    MEMORY_CANDIDATE_ID_PREFIX,
    MEMORY_PROMOTION_RUN_ID_PREFIX,
    MEMORY_RECORD_ID_PREFIX,
    MEMORY_RETRIEVAL_TRACE_ID_PREFIX,
    MEMORY_RUN_ID_PREFIX,
    MemoryCandidate,
    MemoryCandidateDraft,
    MemoryCandidateStatus,
    MemoryExtractionRun,
    MemoryExtractionTrigger,
    MemoryPromotionResult,
    MemoryPromotionRun,
    MemoryRecord,
    MemoryRecordScope,
    MemoryRecordStatus,
    MemoryRecordType,
    MemoryRunStatus,
    MemoryScope,
    RetrievalScope,
    MemorySelection,
    MemorySelectionReason,
    MemorySelectionStatus,
    MemorySelectionTrace,
    MemorySourceMessage,
    MemoryType,
    MemoryValidationError,
    PolicyReason,
    PromotionSkipCount,
    PromotionSkipReason,
    SensitivityLabel,
    generate_memory_candidate_id,
    generate_memory_promotion_run_id,
    generate_memory_record_id,
    generate_memory_retrieval_trace_id,
    generate_memory_run_id,
    utc_now,
)
from backend.memory.policy import (
    POLICY_CONFIDENCE_ACCEPT,
    POLICY_CONFIDENCE_FLOOR,
    POLICY_ID,
    MemoryPolicy,
)
from backend.memory.promotion import (
    MEMORY_PROMOTION_MIN_CONFIDENCE,
    PROMOTABLE_REASONS,
    MemoryPromotionPolicy,
    PromotionAssessment,
)
from backend.memory.retrieval import MEMORY_MAX_SELECTED, MemoryRetrievalService
from backend.memory.repository import (
    MemoryAlreadyExistsError,
    MemoryRepository,
    MemoryRepositoryError,
    MemoryStorageError,
)
from backend.memory.service import (
    EXTRACTION_FAILED_REASON,
    MemoryRunNotFoundError,
    MemoryScopeMismatchError,
    MemoryService,
    MemoryServiceError,
)

# Runtime milestone R6 contracts live in the merged models import above; R5
# candidate names are unchanged.
__all__ = [
    "CANDIDATE_TEXT_MAX_LENGTH",
    "EVIDENCE_SUMMARY_MAX_LENGTH",
    "EXTRACTION_FAILED_REASON",
    "EXTRACTOR_ID",
    "MEMORY_CANDIDATE_ID_PREFIX",
    "MEMORY_PROMOTION_RUN_ID_PREFIX",
    "MEMORY_RECORD_ID_PREFIX",
    "MEMORY_RETRIEVAL_TRACE_ID_PREFIX",
    "MEMORY_RUN_ID_PREFIX",
    "POLICY_CONFIDENCE_ACCEPT",
    "POLICY_CONFIDENCE_FLOOR",
    "POLICY_ID",
    "MemoryAlreadyExistsError",
    "MemoryExtractor",
    "MemoryPolicy",
    "MemoryPromotionPolicy",
    "MemoryRetrievalService",
    "MEMORY_MAX_SELECTED",
    "MEMORY_PROMOTION_MIN_CONFIDENCE",
    "PROMOTABLE_REASONS",
    "PromotionAssessment",
    "MemoryRepository",
    "MemoryRepositoryError",
    "MemoryRunNotFoundError",
    "MemoryScopeMismatchError",
    "MemoryService",
    "MemoryServiceError",
    "MemoryStorageError",
    "MemoryCandidate",
    "MemoryCandidateDraft",
    "MemoryCandidateStatus",
    "MemoryExtractionRun",
    "MemoryExtractionTrigger",
    "MemoryPromotionResult",
    "MemoryPromotionRun",
    "MemoryRecord",
    "MemoryRecordScope",
    "MemoryRecordStatus",
    "MemoryRecordType",
    "MemoryRunStatus",
    "MemoryScope",
    "RetrievalScope",
    "MemorySelection",
    "MemorySelectionReason",
    "MemorySelectionStatus",
    "MemorySelectionTrace",
    "MemorySourceMessage",
    "MemoryType",
    "MemoryValidationError",
    "PolicyReason",
    "PromotionSkipCount",
    "PromotionSkipReason",
    "SensitivityLabel",
    "RuleBasedMemoryExtractor",
    "SECRET_PATTERNS",
    "generate_memory_candidate_id",
    "generate_memory_promotion_run_id",
    "generate_memory_record_id",
    "generate_memory_retrieval_trace_id",
    "generate_memory_run_id",
    "utc_now",
]
