"""Memory write pipeline evaluation package.

Provides deterministic test harness, dataset validation, metric computation,
hard-gate enforcement, and reporting for the basic semantic memory write pipeline.
"""

from backend.memory.write_pipeline.evaluation.dataset import (
    load_dataset,
    validate_dataset,
)
from backend.memory.write_pipeline.evaluation.models import (
    HARD_GATES,
    INITIAL_THRESHOLDS,
    MANDATORY_SLICES,
    DatasetManifest,
    EvaluationExample,
    ExampleEvaluationResult,
    MetricAccounting,
    ResultState,
    SuiteReport,
    SuiteType,
)
from backend.memory.write_pipeline.evaluation.runner import EvaluationRunner

__all__ = [
    "DatasetManifest",
    "EvaluationExample",
    "EvaluationRunner",
    "ExampleEvaluationResult",
    "HARD_GATES",
    "INITIAL_THRESHOLDS",
    "MANDATORY_SLICES",
    "MetricAccounting",
    "ResultState",
    "SuiteReport",
    "SuiteType",
    "load_dataset",
    "validate_dataset",
]
