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
    MetricScore,
    SliceScore,
    report_to_dict,
)
from backend.memory.evaluation.runner import (
    MemoryEvaluationError,
    count_secret_promotions,
    count_workspace_leaks,
    decide_result_state,
    run_shadow_evaluation,
)

__all__ = [
    "ExampleScore",
    "HardGateScore",
    "MemoryEvaluationError",
    "MemoryEvaluationReport",
    "MemoryEvaluationResult",
    "MetricScore",
    "SliceScore",
    "count_secret_promotions",
    "count_workspace_leaks",
    "decide_result_state",
    "report_to_dict",
    "run_shadow_evaluation",
]
