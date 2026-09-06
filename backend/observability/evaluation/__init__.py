"""R8 operational evaluation harness.

The harness replays synthetic operational suites through the real
observability code over temporary state and writes traceable local
reports. It never calls a model provider, RAG retrieval, Chroma
collection creation, embeddings, memory, orchestration, or the network.
"""

from backend.observability.evaluation.models import (
    OpsEvaluationError,
    OpsExampleScore,
    OpsGateScore,
    OpsReport,
    OpsResultState,
)
from backend.observability.evaluation.runner import run_readiness_evaluation

__all__ = [
    "OpsEvaluationError",
    "OpsExampleScore",
    "OpsGateScore",
    "OpsReport",
    "OpsResultState",
    "run_readiness_evaluation",
]
