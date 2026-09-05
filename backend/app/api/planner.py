"""FastAPI planner routes for runtime milestone R7.

These routes expose explicit planner writes and reads beside the existing
chat, workspace, conversation, and memory routes and change no existing
contract. They construct no RAG service, embedding model, Chroma
collection, memory service, or model-provider client.

Planner state inherits scope from its parent workspace. These routes
implement no authentication, authorization, or tenant isolation, and must
not be exposed publicly.

Logging records route, action, workspace, itinerary, decision, and
operation identifiers, counts, and failure class only. Itinerary text,
decision statements, and raw chat messages are never logged, and HTTP
errors never echo them.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.config import settings
from backend.app.schemas.planner import (
    DecisionCreateRequest,
    DecisionStatusUpdateRequest,
    ItineraryCreateRequest,
    ItineraryVersionResponse,
    PlannerOperationResponse,
    TripDecisionResponse,
)
from backend.conversations.repository import ConversationRepositoryError
from backend.conversations.service import (
    ConversationNotFoundError,
    WorkspaceNotFoundError,
)
from backend.conversations.sqlite_repository import SQLiteConversationRepository
from backend.planner.models import (
    DecisionStatus,
    DecisionType,
    ItineraryItem,
    ItineraryStatus,
    ItineraryVersion,
    PlannerValidationError,
    TripDecision,
    generate_decision_id,
    generate_itinerary_version_id,
)
from backend.planner.repository import (
    PlannerNotFoundError,
    PlannerRepositoryError,
)
from backend.planner.service import (
    PlannerConflictError,
    PlannerScopeMismatchError,
    PlannerService,
    PlannerServiceError,
)
from backend.planner.sqlite_repository import SQLitePlannerRepository
from backend.workspaces.repository import WorkspaceRepositoryError
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

logger = logging.getLogger("travel_agent_planner")
router = APIRouter()

_STORAGE_ERROR_DETAIL = "Planner storage is unavailable."
_WORKSPACE_NOT_FOUND_DETAIL = "Workspace not found."
_CONVERSATION_NOT_FOUND_DETAIL = "Conversation not found."
_VERSION_NOT_FOUND_DETAIL = "Planner itinerary version not found."
_DECISION_NOT_FOUND_DETAIL = "Planner decision not found."
_SCOPE_MISMATCH_DETAIL = "Planner record does not belong to this workspace."
_TRANSITION_CONFLICT_DETAIL = "Planner lifecycle transition is not allowed."
_PLANNER_FAILED_DETAIL = "Planner operation could not complete."


def get_planner_service() -> PlannerService:
    """Construct the planner service over the shared local application store.

    This resolves `settings.APP_DB_PATH` alongside the workspace,
    conversation, and memory dependencies. All modules coexist in one
    database file with independent schema versions. Tests override this
    dependency with a temporary database path.

    Raises:
        HTTPException: Storage could not be opened or initialized.
    """
    try:
        planner = SQLitePlannerRepository(db_path=settings.APP_DB_PATH)
        conversations = SQLiteConversationRepository(db_path=settings.APP_DB_PATH)
        workspaces = SQLiteWorkspaceRepository(db_path=settings.APP_DB_PATH)
    except (
        PlannerRepositoryError,
        ConversationRepositoryError,
        WorkspaceRepositoryError,
    ) as error:
        logger.error(
            "planner.storage unavailable failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error
    return PlannerService(
        planner_repository=planner,
        conversation_repository=conversations,
        workspace_repository=workspaces,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@router.post(
    "/workspaces/{workspace_id}/planner/itineraries",
    response_model=ItineraryVersionResponse,
    status_code=201,
)
def create_itinerary(
    workspace_id: str,
    request: ItineraryCreateRequest,
    service: PlannerService = Depends(get_planner_service),
) -> ItineraryVersionResponse:
    """Create a draft or proposed itinerary version."""
    moment = _utc_now()
    try:
        stored = service.create_itinerary_version(
            workspace_id=workspace_id,
            draft=ItineraryVersion(
                itinerary_version_id=generate_itinerary_version_id(),
                workspace_id=workspace_id,
                version_number=1,
                status=request.status,
                title=request.title,
                summary=request.summary,
                items=tuple(
                    ItineraryItem(
                        day_index=item.day_index,
                        position=item.position,
                        item_type=item.item_type,
                        title=item.title,
                        location=item.location,
                        start_time=item.start_time,
                        end_time=item.end_time,
                        notes=item.notes,
                        source_decision_ids=tuple(item.source_decision_ids),
                    )
                    for item in request.items
                ),
                created_at=moment,
            ),
            conversation_id=request.conversation_id,
            source_message_id=request.source_message_id,
        )
    except PlannerValidationError as error:
        logger.info("planner.itinerary rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        logger.info("planner.itinerary miss failure_class=workspace_not_found")
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except ConversationNotFoundError as error:
        logger.info("planner.itinerary miss failure_class=conversation_not_found")
        raise HTTPException(
            status_code=404, detail=_CONVERSATION_NOT_FOUND_DETAIL
        ) from error
    except PlannerScopeMismatchError as error:
        logger.info("planner.itinerary mismatch failure_class=scope_mismatch")
        raise HTTPException(status_code=404, detail=_SCOPE_MISMATCH_DETAIL) from error
    except PlannerConflictError as error:
        logger.info("planner.itinerary conflict failure_class=lifecycle")
        raise HTTPException(
            status_code=409, detail=_TRANSITION_CONFLICT_DETAIL
        ) from error
    except PlannerServiceError as error:
        logger.error("planner.itinerary failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_PLANNER_FAILED_DETAIL) from error
    except PlannerRepositoryError as error:
        logger.error("planner.itinerary failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "planner.itinerary ok itinerary_version_id=%s workspace_id=%s "
        "version_number=%s",
        stored.itinerary_version_id,
        workspace_id,
        stored.version_number,
    )
    return ItineraryVersionResponse.from_domain(stored)


@router.get(
    "/workspaces/{workspace_id}/planner/itineraries",
    response_model=List[ItineraryVersionResponse],
)
def list_itineraries(
    workspace_id: str,
    status: Optional[ItineraryStatus] = Query(
        None, description="Return only versions with this status"
    ),
    service: PlannerService = Depends(get_planner_service),
) -> List[ItineraryVersionResponse]:
    """List itinerary versions for one workspace, newest first."""
    try:
        versions = service.list_itinerary_versions(workspace_id, status)
    except WorkspaceNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except PlannerServiceError as error:
        raise HTTPException(status_code=500, detail=_PLANNER_FAILED_DETAIL) from error
    except PlannerRepositoryError as error:
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error
    return [ItineraryVersionResponse.from_domain(item) for item in versions]


@router.get(
    "/workspaces/{workspace_id}/planner/itineraries/{itinerary_version_id}",
    response_model=ItineraryVersionResponse,
)
def get_itinerary(
    workspace_id: str,
    itinerary_version_id: str,
    service: PlannerService = Depends(get_planner_service),
) -> ItineraryVersionResponse:
    """Fetch one itinerary version scoped to the workspace."""
    try:
        stored = service.get_itinerary_version(workspace_id, itinerary_version_id)
    except WorkspaceNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except PlannerNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_VERSION_NOT_FOUND_DETAIL
        ) from error
    except PlannerServiceError as error:
        raise HTTPException(status_code=500, detail=_PLANNER_FAILED_DETAIL) from error
    except PlannerRepositoryError as error:
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error
    return ItineraryVersionResponse.from_domain(stored)


@router.post(
    "/workspaces/{workspace_id}/planner/itineraries/{itinerary_version_id}/accept",
    response_model=ItineraryVersionResponse,
)
def accept_itinerary(
    workspace_id: str,
    itinerary_version_id: str,
    service: PlannerService = Depends(get_planner_service),
) -> ItineraryVersionResponse:
    """Accept one version, superseding prior accepted versions."""
    try:
        stored = service.accept_itinerary_version(workspace_id, itinerary_version_id)
    except WorkspaceNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except PlannerNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_VERSION_NOT_FOUND_DETAIL
        ) from error
    except PlannerConflictError as error:
        raise HTTPException(
            status_code=409, detail=_TRANSITION_CONFLICT_DETAIL
        ) from error
    except PlannerServiceError as error:
        raise HTTPException(status_code=500, detail=_PLANNER_FAILED_DETAIL) from error
    except PlannerRepositoryError as error:
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "planner.itinerary accept ok itinerary_version_id=%s workspace_id=%s",
        stored.itinerary_version_id,
        workspace_id,
    )
    return ItineraryVersionResponse.from_domain(stored)


@router.post(
    "/workspaces/{workspace_id}/planner/itineraries/{itinerary_version_id}/archive",
    response_model=ItineraryVersionResponse,
)
def archive_itinerary(
    workspace_id: str,
    itinerary_version_id: str,
    service: PlannerService = Depends(get_planner_service),
) -> ItineraryVersionResponse:
    """Archive one itinerary version."""
    try:
        stored = service.archive_itinerary_version(workspace_id, itinerary_version_id)
    except WorkspaceNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except PlannerNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_VERSION_NOT_FOUND_DETAIL
        ) from error
    except PlannerConflictError as error:
        raise HTTPException(
            status_code=409, detail=_TRANSITION_CONFLICT_DETAIL
        ) from error
    except PlannerServiceError as error:
        raise HTTPException(status_code=500, detail=_PLANNER_FAILED_DETAIL) from error
    except PlannerRepositoryError as error:
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "planner.itinerary archive ok itinerary_version_id=%s workspace_id=%s",
        stored.itinerary_version_id,
        workspace_id,
    )
    return ItineraryVersionResponse.from_domain(stored)


@router.post(
    "/workspaces/{workspace_id}/planner/decisions",
    response_model=TripDecisionResponse,
    status_code=201,
)
def record_decision(
    workspace_id: str,
    request: DecisionCreateRequest,
    service: PlannerService = Depends(get_planner_service),
) -> TripDecisionResponse:
    """Record a trip decision, optionally superseding an earlier one."""
    moment = _utc_now()
    try:
        stored = service.record_decision(
            workspace_id=workspace_id,
            draft=TripDecision(
                decision_id=generate_decision_id(),
                workspace_id=workspace_id,
                decision_type=request.decision_type,
                status=request.status,
                statement=request.statement,
                rationale=request.rationale,
                source_message_id=request.source_message_id,
                supersedes_decision_id=request.supersedes_decision_id,
                created_at=moment,
                updated_at=moment,
            ),
            conversation_id=request.conversation_id,
            source_message_id=request.source_message_id,
        )
    except PlannerValidationError as error:
        logger.info("planner.decision rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_CONVERSATION_NOT_FOUND_DETAIL
        ) from error
    except PlannerScopeMismatchError as error:
        raise HTTPException(status_code=404, detail=_SCOPE_MISMATCH_DETAIL) from error
    except PlannerNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_DECISION_NOT_FOUND_DETAIL
        ) from error
    except PlannerConflictError as error:
        raise HTTPException(
            status_code=409, detail=_TRANSITION_CONFLICT_DETAIL
        ) from error
    except PlannerServiceError as error:
        logger.error("planner.decision failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_PLANNER_FAILED_DETAIL) from error
    except PlannerRepositoryError as error:
        logger.error("planner.decision failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "planner.decision ok decision_id=%s workspace_id=%s",
        stored.decision_id,
        workspace_id,
    )
    return TripDecisionResponse.from_domain(stored)


@router.get(
    "/workspaces/{workspace_id}/planner/decisions",
    response_model=List[TripDecisionResponse],
)
def list_decisions(
    workspace_id: str,
    status: Optional[DecisionStatus] = Query(
        None, description="Return only decisions with this status"
    ),
    decision_type: Optional[DecisionType] = Query(
        None, description="Return only decisions of this type"
    ),
    service: PlannerService = Depends(get_planner_service),
) -> List[TripDecisionResponse]:
    """List trip decisions for one workspace, newest first."""
    try:
        decisions = service.list_decisions(workspace_id, status, decision_type)
    except WorkspaceNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except PlannerServiceError as error:
        raise HTTPException(status_code=500, detail=_PLANNER_FAILED_DETAIL) from error
    except PlannerRepositoryError as error:
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error
    return [TripDecisionResponse.from_domain(item) for item in decisions]


@router.patch(
    "/workspaces/{workspace_id}/planner/decisions/{decision_id}",
    response_model=TripDecisionResponse,
)
def update_decision(
    workspace_id: str,
    decision_id: str,
    request: DecisionStatusUpdateRequest,
    service: PlannerService = Depends(get_planner_service),
) -> TripDecisionResponse:
    """Move one decision along its lifecycle."""
    try:
        stored = service.update_decision_status(
            workspace_id, decision_id, request.status
        )
    except WorkspaceNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except PlannerNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_DECISION_NOT_FOUND_DETAIL
        ) from error
    except PlannerConflictError as error:
        raise HTTPException(
            status_code=409, detail=_TRANSITION_CONFLICT_DETAIL
        ) from error
    except PlannerServiceError as error:
        raise HTTPException(status_code=500, detail=_PLANNER_FAILED_DETAIL) from error
    except PlannerRepositoryError as error:
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "planner.decision update ok decision_id=%s workspace_id=%s",
        stored.decision_id,
        workspace_id,
    )
    return TripDecisionResponse.from_domain(stored)


@router.get(
    "/workspaces/{workspace_id}/planner/operations",
    response_model=List[PlannerOperationResponse],
)
def list_operations(
    workspace_id: str,
    service: PlannerService = Depends(get_planner_service),
) -> List[PlannerOperationResponse]:
    """List planner operation rows for one workspace, newest first."""
    try:
        operations = service.list_operations(workspace_id)
    except WorkspaceNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except PlannerServiceError as error:
        raise HTTPException(status_code=500, detail=_PLANNER_FAILED_DETAIL) from error
    except PlannerRepositoryError as error:
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error
    return [PlannerOperationResponse.from_domain(item) for item in operations]
