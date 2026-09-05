"""R5 memory shadow evaluation entry points.

Memory-specific evaluation lives beside the memory module per ADR 0006, so
RAG evaluation never imports memory state. Reports follow the result
vocabulary of the memory evaluation protocol.
"""

from backend.memory.evaluation.models import (
    ExampleScore,
    HardGateScore,
    MemoryEvaluationReport,
    MemoryEvaluationResult,
    MemoryRetrievalReport,
    MetricScore,
    SliceScore,
    report_to_dict,
    retrieval_report_to_dict,
)
from backend.memory.evaluation.runner import (
    MemoryEvaluationError,
    count_secret_promotions,
    count_workspace_leaks,
    decide_result_state,
    decide_retrieval_result,
    run_retrieval_evaluation,
    run_shadow_evaluation,
)

__all__ = [
    "ExampleScore",
    "HardGateScore",
    "MemoryEvaluationError",
    "MemoryEvaluationReport",
    "MemoryEvaluationResult",
    "MemoryRetrievalReport",
    "MetricScore",
    "SliceScore",
    "count_secret_promotions",
    "count_workspace_leaks",
    "decide_result_state",
    "decide_retrieval_result",
    "report_to_dict",
    "retrieval_report_to_dict",
    "run_retrieval_evaluation",
    "run_shadow_evaluation",
]
