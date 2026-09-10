"""FastAPI ops routes for runtime readiness and health.

The readiness route returns a diagnostic snapshot of application components
(database, alembic migrations, model provider, chroma, and memory write pipeline).
It strictly requires authentication via require_principal.
Returns HTTP 200 when all components are ready, and HTTP 503 when any component is not ready.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status

from backend.app.runtime_container import RuntimeContainer, get_runtime_container
from backend.observability.models import ReadinessStatus
from backend.observability.readiness import build_readiness_snapshot
from backend.security.dependencies import require_principal
from backend.security.models import AuthenticatedPrincipal

logger = logging.getLogger("travel_agent_observability")
router = APIRouter()

_READINESS_FAILED_DETAIL = "Readiness probe failed."


@router.get("/ops/readiness")
def get_readiness(
    response: Response,
    _principal: AuthenticatedPrincipal = Depends(require_principal),
    container: RuntimeContainer = Depends(get_runtime_container),
) -> dict[str, Any]:
    """Return local readiness without changing any application state.

    Requires a valid bearer token.
    Returns HTTP 200 when ready, HTTP 503 when not ready.
    Discloses no credential material, secrets, or file paths.
    """
    try:
        snapshot = build_readiness_snapshot(container=container)
    except Exception as error:
        logger.error("ops.readiness failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_READINESS_FAILED_DETAIL) from error

    if snapshot.status != ReadinessStatus.READY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    logger.info("ops.readiness completed status=%s", snapshot.status.value)
    return snapshot.to_dict()
