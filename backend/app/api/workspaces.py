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
    DeletionRequestBody,
    DeletionResultResponse,
    WorkspaceCreateRequest,
    WorkspaceListResponse,
    WorkspaceResponse,
)
from backend.conversations.service import WorkspaceNotFoundError
from backend.conversations.sqlite_repository import SQLiteConversationRepository
from backend.memory.sqlite_repository import SQLiteMemoryRepository
from backend.privacy.deletion import (
    DeletionConflictError,
    DeletionService,
    PrivacyServiceError,
)
from backend.security.authorization import (
    CrossOwnerAccessError,
    OwnerForbiddenError,
    get_workspace_repository,
    require_create_owner,
    require_workspace_owner,
    scope_list_owner,
)
from backend.security.dependencies import require_principal
from backend.security.models import AuthenticatedPrincipal
from backend.workspaces.models import WorkspaceCreate, WorkspaceValidationError
from backend.workspaces.repository import WorkspaceRepositoryError
from backend.workspaces.service import WorkspaceService
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

logger = logging.getLogger("travel_agent_workspaces")
router = APIRouter()

_STORAGE_ERROR_DETAIL = "Workspace storage is unavailable."
_OWNER_FORBIDDEN_DETAIL = "Workspace owner does not match the principal."
_DELETION_CONFLICT_DETAIL = "Workspace deletion cannot proceed yet."
_DELETION_FAILED_DETAIL = "Workspace deletion could not complete."


def get_deletion_service() -> DeletionService:
    """Construct the privacy deletion service over the shared local store.

    Tests override this dependency with repositories over a temporary
    database path.
    """
    return DeletionService(
        workspace_repository=SQLiteWorkspaceRepository(db_path=settings.APP_DB_PATH),
        conversation_repository=SQLiteConversationRepository(
            db_path=settings.APP_DB_PATH
        ),
        memory_repository=SQLiteMemoryRepository(db_path=settings.APP_DB_PATH),
    )


def get_workspace_service() -> WorkspaceService:
    """Construct the workspace service over the shared local application store.

    This is one of the two places that resolve `settings.APP_DB_PATH`; the other
    is the conversation dependency. Tests override this dependency with a
    temporary database path.

    Storage construction can fail before any route body runs, for example when
    the configured database records an incompatible workspace schema version or
    its directory is not writable. Converting that failure here keeps the
    caller's response a controlled `500` instead of an unhandled server error.

    Raises:
        HTTPException: Storage could not be opened or initialized.
    """
    try:
        repository = SQLiteWorkspaceRepository(db_path=settings.APP_DB_PATH)
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
    principal: AuthenticatedPrincipal = Depends(require_principal),
) -> WorkspaceResponse:
    """Create one local trip workspace record."""
    try:
        require_create_owner(request.owner_user_id, principal)
    except OwnerForbiddenError as error:
        logger.info("workspace.create denied failure_class=owner_forbidden")
        raise HTTPException(status_code=403, detail=_OWNER_FORBIDDEN_DETAIL) from error
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
    principal: AuthenticatedPrincipal = Depends(require_principal),
) -> WorkspaceListResponse:
    """List workspaces for one local development owner scope label."""
    try:
        scoped_owner = scope_list_owner(owner_user_id, principal)
    except OwnerForbiddenError as error:
        logger.info("workspace.list denied failure_class=owner_forbidden")
        raise HTTPException(status_code=403, detail=_OWNER_FORBIDDEN_DETAIL) from error
    try:
        workspaces = service.list_workspaces(scoped_owner)
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
    principal: AuthenticatedPrincipal = Depends(require_principal),
    workspaces=Depends(get_workspace_repository),
) -> WorkspaceResponse:
    """Retrieve one workspace by identifier."""
    try:
        require_workspace_owner(workspace_id, workspaces, principal)
    except CrossOwnerAccessError:
        logger.info("workspace.get miss failure_class=not_found")
        raise HTTPException(status_code=404, detail="Workspace not found.")
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


@router.post(
    "/workspaces/{workspace_id}/deletion-requests",
    response_model=DeletionResultResponse,
    status_code=201,
)
def request_workspace_deletion(
    workspace_id: str,
    request: DeletionRequestBody | None = None,
    service: DeletionService = Depends(get_deletion_service),
    principal: AuthenticatedPrincipal = Depends(require_principal),
    workspaces=Depends(get_workspace_repository),
) -> DeletionResultResponse:
    """Mark a workspace and its active children deletion-requested."""
    _ = request
    try:
        require_workspace_owner(workspace_id, workspaces, principal)
    except CrossOwnerAccessError:
        logger.info("workspace.deletion miss failure_class=not_found")
        raise HTTPException(status_code=404, detail="Workspace not found.")
    try:
        result = service.request_workspace_deletion(workspace_id)
    except WorkspaceNotFoundError as error:
        logger.info("workspace.deletion miss failure_class=not_found")
        raise HTTPException(status_code=404, detail="Workspace not found.") from error
    except PrivacyServiceError as error:
        logger.error(
            "workspace.deletion failed failure_class=%s", type(error).__name__
        )
        raise HTTPException(
            status_code=500, detail=_DELETION_FAILED_DETAIL
        ) from error

    logger.info(
        "workspace.deletion requested workspace_id=%s state=%s",
        result.workspace_id,
        result.workspace_state,
    )
    return DeletionResultResponse.from_domain(result)


@router.post(
    "/workspaces/{workspace_id}/deletion-confirmations",
    response_model=DeletionResultResponse,
)
def confirm_workspace_deletion(
    workspace_id: str,
    request: DeletionRequestBody | None = None,
    service: DeletionService = Depends(get_deletion_service),
    principal: AuthenticatedPrincipal = Depends(require_principal),
    workspaces=Depends(get_workspace_repository),
) -> DeletionResultResponse:
    """Confirm workspace deletion after verifying child transitions."""
    _ = request
    try:
        require_workspace_owner(workspace_id, workspaces, principal)
    except CrossOwnerAccessError:
        logger.info("workspace.deletion miss failure_class=not_found")
        raise HTTPException(status_code=404, detail="Workspace not found.")
    try:
        result = service.confirm_workspace_deletion(workspace_id)
    except WorkspaceNotFoundError as error:
        logger.info("workspace.deletion miss failure_class=not_found")
        raise HTTPException(status_code=404, detail="Workspace not found.") from error
    except DeletionConflictError as error:
        logger.info("workspace.deletion conflict failure_class=deletion_conflict")
        raise HTTPException(
            status_code=409, detail=_DELETION_CONFLICT_DETAIL
        ) from error
    except PrivacyServiceError as error:
        logger.error(
            "workspace.deletion failed failure_class=%s", type(error).__name__
        )
        raise HTTPException(
            status_code=500, detail=_DELETION_FAILED_DETAIL
        ) from error

    logger.info(
        "workspace.deletion confirmed workspace_id=%s state=%s",
        result.workspace_id,
        result.workspace_state,
    )
    return DeletionResultResponse.from_domain(result)
