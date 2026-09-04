"""FastAPI workspace routes for runtime milestone R3.

These routes are mounted beside the existing chat route and do not change the
chat request or response contract. They construct no embedding model, Chroma
collection, or model-provider client.

`owner_user_id` is a local development scope label. These routes implement no
authentication, authorization, or tenant isolation, and must not be exposed
publicly.

Logging records route, action, workspace ID, owner scope label, counts, and
failure class only. Full user-entered titles and destination scopes are never
logged, and HTTP errors never echo them.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.config import settings
from backend.app.schemas.workspaces import (
    WorkspaceCreateRequest,
    WorkspaceListResponse,
    WorkspaceResponse,
)
from backend.workspaces.models import WorkspaceCreate, WorkspaceValidationError
from backend.workspaces.repository import WorkspaceRepositoryError
from backend.workspaces.service import WorkspaceService
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

logger = logging.getLogger("travel_agent_workspaces")
router = APIRouter()

_STORAGE_ERROR_DETAIL = "Workspace storage is unavailable."


def get_workspace_service() -> WorkspaceService:
    """Construct the workspace service over the configured local SQLite store.

    This is the only place that resolves `settings.WORKSPACE_DB_PATH`. Tests
    override this dependency with a temporary database path.

    Storage construction can fail before any route body runs, for example when
    the configured database reports an incompatible schema version or its
    directory is not writable. Converting that failure here keeps the caller's
    response a controlled `500` instead of an unhandled server error.

    Raises:
        HTTPException: Storage could not be opened or initialized.
    """
    try:
        repository = SQLiteWorkspaceRepository(db_path=settings.WORKSPACE_DB_PATH)
    except WorkspaceRepositoryError as error:
        logger.error(
            "workspace.storage unavailable failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error
    return WorkspaceService(repository=repository)


@router.post(
    "/workspaces",
    response_model=WorkspaceResponse,
    status_code=201,
)
def create_workspace(
    request: WorkspaceCreateRequest,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    """Create one local trip workspace record."""
    try:
        workspace_input = WorkspaceCreate(
            owner_user_id=request.owner_user_id,
            title=request.title,
            destination_scope=request.destination_scope,
            date_window=(
                request.date_window.to_domain() if request.date_window else None
            ),
            planning_status=request.planning_status,
        )
    except WorkspaceValidationError as error:
        logger.info("workspace.create rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error

    try:
        workspace = service.create_workspace(workspace_input)
    except WorkspaceValidationError as error:
        logger.info("workspace.create rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except WorkspaceRepositoryError as error:
        logger.error("workspace.create failed failure_class=%s", type(error).__name__)
        raise HTTPException(
            status_code=500,
            detail=_STORAGE_ERROR_DETAIL,
        ) from error

    logger.info(
        "workspace.create ok workspace_id=%s owner_scope=%s planning_status=%s",
        workspace.workspace_id,
        workspace.owner_user_id,
        workspace.planning_status.value,
    )
    return WorkspaceResponse.from_domain(workspace)


@router.get("/workspaces", response_model=WorkspaceListResponse)
def list_workspaces(
    owner_user_id: str = Query(..., description="Local development scope label"),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceListResponse:
    """List workspaces for one local development owner scope label."""
    try:
        workspaces = service.list_workspaces(owner_user_id)
    except WorkspaceValidationError as error:
        logger.info("workspace.list rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except WorkspaceRepositoryError as error:
        logger.error("workspace.list failed failure_class=%s", type(error).__name__)
        raise HTTPException(
            status_code=500,
            detail=_STORAGE_ERROR_DETAIL,
        ) from error

    logger.info(
        "workspace.list ok owner_scope=%s count=%s",
        owner_user_id.strip(),
        len(workspaces),
    )
    return WorkspaceListResponse(
        workspaces=[WorkspaceResponse.from_domain(item) for item in workspaces]
    )


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(
    workspace_id: str,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    """Retrieve one workspace by identifier."""
    try:
        workspace = service.get_workspace(workspace_id)
    except WorkspaceValidationError as error:
        logger.info("workspace.get rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except WorkspaceRepositoryError as error:
        logger.error("workspace.get failed failure_class=%s", type(error).__name__)
        raise HTTPException(
            status_code=500,
            detail=_STORAGE_ERROR_DETAIL,
        ) from error

    if workspace is None:
        logger.info("workspace.get miss failure_class=not_found")
        raise HTTPException(status_code=404, detail="Workspace not found.")

    logger.info("workspace.get ok workspace_id=%s", workspace.workspace_id)
    return WorkspaceResponse.from_domain(workspace)
