"""R9 security evaluation harness.

The harness replays synthetic security scenarios through the real routes
and services over temporary databases and writes traceable local
reports. It never touches real credentials, real user data, model
providers, Chroma collection creation, embeddings, or the network.
"""

from backend.security.evaluation.models import (
    SecurityEvaluationError,
    SecurityExampleScore,
    SecurityGateScore,
    SecurityReport,
    SecurityResultState,
)
from backend.security.evaluation.runner import run_security_evaluation

__all__ = [
    "SecurityEvaluationError",
    "SecurityExampleScore",
    "SecurityGateScore",
    "SecurityReport",
    "SecurityResultState",
    "run_security_evaluation",
]
