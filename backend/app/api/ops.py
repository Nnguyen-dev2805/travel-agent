"""FastAPI ops routes for runtime milestone R8.

The readiness route returns a local diagnostic snapshot beside the
existing chat, workspace, conversation, memory, and planner routes and
changes no existing contract. It calls the readiness service only: no
probe logic, SQL, Chroma calls, filesystem traversal, or redaction
policy lives here.

This route is an unauthenticated local development diagnostic. It must
not be represented as production-safe, and its response carries safe
diagnostic fields only.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.observability.readiness import build_readiness_snapshot

logger = logging.getLogger("travel_agent_observability")
router = APIRouter()

_READINESS_FAILED_DETAIL = "Readiness probe failed."


@router.get("/ops/readiness")
def get_readiness() -> dict[str, Any]:
    """Return local readiness without changing any application state."""
    try:
        snapshot = build_readiness_snapshot()
    except Exception as error:
        logger.error("ops.readiness failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_READINESS_FAILED_DETAIL) from error
    logger.info("ops.readiness completed status=%s", snapshot.status.value)
    return snapshot.to_dict()
