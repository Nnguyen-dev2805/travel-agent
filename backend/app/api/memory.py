"""FastAPI memory routes for runtime milestone R5.

These routes expose manual shadow extraction and candidate inspection beside
the existing chat, workspace, and conversation routes and change no existing
contract. They construct no RAG service, embedding model, Chroma collection,
or model-provider client, and no candidate returned here ever enters an
answer: R5 is shadow-only.

Memory records inherit scope from their parent workspace through the parent
conversation. These routes implement no authentication, authorization, or
tenant isolation, and must not be exposed publicly.

Logging records route, action, run, workspace, conversation, and candidate
identifiers, counts, and failure class only. Message content, candidate text,
evidence summaries, and conversation titles are never logged, and HTTP errors
never echo them.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.config import settings
from backend.app.schemas.memory import (
    MemoryCandidateListResponse,
    MemoryCandidateResponse,
    MemoryExtractionRequest,
    MemoryExtractionRunListResponse,
    MemoryExtractionRunResponse,
    MemoryPromotionRequest,
    MemoryPromotionResultResponse,
)
from backend.conversations.repository import ConversationRepositoryError
from backend.conversations.service import (
    ConversationNotFoundError,
    WorkspaceNotFoundError,
)
from backend.conversations.sqlite_repository import SQLiteConversationRepository
from backend.memory.models import (
    MemoryExtractionTrigger,
    MemoryValidationError,
)
from backend.memory.repository import MemoryRepositoryError
from backend.memory.service import (
    MemoryRunNotFoundError,
    MemoryScopeMismatchError,
    MemoryService,
    MemoryServiceError,
)
from backend.memory.sqlite_repository import SQLiteMemoryRepository
from backend.workspaces.repository import WorkspaceRepositoryError
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

logger = logging.getLogger("travel_agent_memory")
router = APIRouter()

_STORAGE_ERROR_DETAIL = "Memory storage is unavailable."
_WORKSPACE_NOT_FOUND_DETAIL = "Workspace not found."
_CONVERSATION_NOT_FOUND_DETAIL = "Conversation not found."
_RUN_NOT_FOUND_DETAIL = "Memory extraction run not found."
_SCOPE_MISMATCH_DETAIL = "Conversation does not belong to this workspace."
_RUN_SCOPE_MISMATCH_DETAIL = "Memory extraction run does not belong to this workspace."
_EXTRACTION_FAILED_DETAIL = "Memory extraction could not complete."


def get_memory_service() -> MemoryService:
    """Construct the memory service over the shared local application store.

    This is the third place that resolves `settings.APP_DB_PATH`, after the
    workspace and conversation dependencies. All three modules coexist in one
    database file with independent schema versions. Tests override this
    dependency with a temporary database path.

    Storage construction can fail before any route body runs, for example when
    the configured database records an incompatible schema version or its
    directory is not writable. Converting that failure here keeps the caller's
    response a controlled `500` instead of an unhandled server error.

    Raises:
        HTTPException: Storage could not be opened or initialized.
    """
    try:
        memory = SQLiteMemoryRepository(db_path=settings.APP_DB_PATH)
        conversations = SQLiteConversationRepository(db_path=settings.APP_DB_PATH)
        workspaces = SQLiteWorkspaceRepository(db_path=settings.APP_DB_PATH)
    except (
        MemoryRepositoryError,
        ConversationRepositoryError,
        WorkspaceRepositoryError,
    ) as error:
        logger.error(
            "memory.storage unavailable failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error
    return MemoryService(
        memory_repository=memory,
        conversation_repository=conversations,
        workspace_repository=workspaces,
    )


@router.post(
    "/workspaces/{workspace_id}/conversations/{conversation_id}/memory/extractions",
    response_model=MemoryExtractionRunResponse,
    status_code=201,
)
def trigger_extraction(
    workspace_id: str,
    conversation_id: str,
    request: Optional[MemoryExtractionRequest] = None,
    service: MemoryService = Depends(get_memory_service),
) -> MemoryExtractionRunResponse:
    """Run one manual shadow extraction over a conversation's messages."""
    try:
        run = service.run_conversation_extraction(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            trigger=MemoryExtractionTrigger.MANUAL,
        )
    except MemoryValidationError as error:
        logger.info("memory.extract rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        logger.info("memory.extract miss failure_class=workspace_not_found")
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except ConversationNotFoundError as error:
        logger.info("memory.extract miss failure_class=conversation_not_found")
        raise HTTPException(
            status_code=404, detail=_CONVERSATION_NOT_FOUND_DETAIL
        ) from error
    except MemoryScopeMismatchError as error:
        logger.info("memory.extract mismatch failure_class=scope_mismatch")
        raise HTTPException(status_code=409, detail=_SCOPE_MISMATCH_DETAIL) from error
    except MemoryServiceError as error:
        logger.error("memory.extract failed failure_class=%s", type(error).__name__)
        raise HTTPException(
            status_code=500, detail=_EXTRACTION_FAILED_DETAIL
        ) from error
    except MemoryRepositoryError as error:
        logger.error("memory.extract failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "memory.extract ok run_id=%s workspace_id=%s conversation_id=%s "
        "accepted=%s rejected=%s",
        run.run_id,
        run.workspace_id,
        run.conversation_id,
        run.accepted_count,
        run.rejected_count,
    )
    return MemoryExtractionRunResponse.from_domain(run)


@router.get(
    "/workspaces/{workspace_id}/memory/extractions",
    response_model=MemoryExtractionRunListResponse,
)
def list_extraction_runs(
    workspace_id: str,
    conversation_id: Optional[str] = Query(
        None, description="Return only runs for this conversation"
    ),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryExtractionRunListResponse:
    """List shadow extraction runs for one workspace, newest first."""
    try:
        runs = service.list_runs(workspace_id, conversation_id)
    except MemoryValidationError as error:
        logger.info("memory.runs rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        logger.info("memory.runs miss failure_class=workspace_not_found")
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except ConversationNotFoundError as error:
        logger.info("memory.runs miss failure_class=conversation_not_found")
        raise HTTPException(
            status_code=404, detail=_CONVERSATION_NOT_FOUND_DETAIL
        ) from error
    except MemoryScopeMismatchError as error:
        logger.info("memory.runs mismatch failure_class=scope_mismatch")
        raise HTTPException(status_code=409, detail=_SCOPE_MISMATCH_DETAIL) from error
    except MemoryRepositoryError as error:
        logger.error("memory.runs failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "memory.runs ok workspace_id=%s count=%s",
        workspace_id.strip(),
        len(runs),
    )
    return MemoryExtractionRunListResponse(
        runs=[MemoryExtractionRunResponse.from_domain(run) for run in runs]
    )


@router.get(
    "/workspaces/{workspace_id}/memory/candidates",
    response_model=MemoryCandidateListResponse,
)
def list_candidates(
    workspace_id: str,
    conversation_id: Optional[str] = Query(
        None, description="Return only candidates for this conversation"
    ),
    run_id: Optional[str] = Query(
        None, description="Return only candidates for this extraction run"
    ),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryCandidateListResponse:
    """List shadow memory candidate evidence for the supplied filters."""
    try:
        candidates = service.list_candidates(workspace_id, conversation_id, run_id)
    except MemoryValidationError as error:
        logger.info("memory.candidates rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        logger.info("memory.candidates miss failure_class=workspace_not_found")
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except ConversationNotFoundError as error:
        logger.info("memory.candidates miss failure_class=conversation_not_found")
        raise HTTPException(
            status_code=404, detail=_CONVERSATION_NOT_FOUND_DETAIL
        ) from error
    except MemoryRunNotFoundError as error:
        logger.info("memory.candidates miss failure_class=run_not_found")
        raise HTTPException(status_code=404, detail=_RUN_NOT_FOUND_DETAIL) from error
    except MemoryScopeMismatchError as error:
        logger.info("memory.candidates mismatch failure_class=scope_mismatch")
        raise HTTPException(
            status_code=409, detail=_RUN_SCOPE_MISMATCH_DETAIL
        ) from error
    except MemoryRepositoryError as error:
        logger.error("memory.candidates failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "memory.candidates ok workspace_id=%s count=%s",
        workspace_id.strip(),
        len(candidates),
    )
    return MemoryCandidateListResponse(
        candidates=[MemoryCandidateResponse.from_domain(item) for item in candidates]
    )


@router.post(
    "/workspaces/{workspace_id}/memory/promotions",
    response_model=MemoryPromotionResultResponse,
    status_code=201,
)
def promote_candidates(
    workspace_id: str,
    conversation_id: Optional[str] = Query(
        None, description="Promote only candidates for this conversation"
    ),
    request: Optional[MemoryPromotionRequest] = None,
    service: MemoryService = Depends(get_memory_service),
) -> MemoryPromotionResultResponse:
    """Promote eligible shadow candidates into answer-eligible records."""
    try:
        result = service.promote_workspace(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            trigger=MemoryExtractionTrigger.MANUAL,
        )
    except MemoryValidationError as error:
        logger.info("memory.promote rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        logger.info("memory.promote miss failure_class=workspace_not_found")
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except ConversationNotFoundError as error:
        logger.info("memory.promote miss failure_class=conversation_not_found")
        raise HTTPException(
            status_code=404, detail=_CONVERSATION_NOT_FOUND_DETAIL
        ) from error
    except MemoryScopeMismatchError as error:
        logger.info("memory.promote mismatch failure_class=scope_mismatch")
        raise HTTPException(status_code=409, detail=_SCOPE_MISMATCH_DETAIL) from error
    except (MemoryServiceError, MemoryRepositoryError) as error:
        logger.error("memory.promote failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "memory.promote ok promotion_run_id=%s workspace_id=%s promoted=%s skipped=%s",
        result.promotion_run_id,
        result.workspace_id,
        result.promoted_count,
        result.skipped_count,
    )
    return MemoryPromotionResultResponse.from_domain(result)
