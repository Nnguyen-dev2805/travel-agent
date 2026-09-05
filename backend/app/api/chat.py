"""FastAPI chat route.

Per ADR 0005 this route validates the request and delegates one turn to the
`ConversationOrchestrator`. Turn ordering and the partial-failure policy live in
the orchestrator, not here.

The optional `conversation_id` is additive: a request that omits it receives the
exact pre-R4 response, with no `conversation` key at all.

The conversation service is resolved lazily, inside the orchestrator, and only
for a bound turn. An unbound turn therefore constructs no local storage, so it
cannot be broken by a storage failure and cannot create the developer database.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from backend.app.api.conversations import get_conversation_service
from backend.app.config import settings
from backend.app.schemas.chat import (
    ChatMemoryPayload,
    ChatRequest,
    ChatResponse,
    ConversationTurnPayload,
)
from backend.conversations.models import ConversationValidationError
from backend.conversations.repository import ConversationRepositoryError
from backend.conversations.service import ConversationNotFoundError
from backend.memory.repository import MemoryRepositoryError
from backend.memory.retrieval import MemoryRetrievalService
from backend.memory.sqlite_repository import SQLiteMemoryRepository
from backend.orchestration.conversation_orchestrator import (
    ConversationOrchestrator,
    MemoryComponents,
)
from backend.rag.generation import RAGService
from backend.workspaces.repository import WorkspaceRepositoryError
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

logger = logging.getLogger("travel_agent_backend")
router = APIRouter()

_CONVERSATION_NOT_FOUND_DETAIL = "Conversation not found."
_CONVERSATION_STORAGE_DETAIL = "Conversation storage is unavailable."

# Global RAG service instance
_rag_service = None


def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


def get_memory_components():
    """Resolve memory retrieval components for one bound turn.

    The provider runs lazily inside the orchestrator, only when the feature
    gate is enabled for a bound turn, so gate-disabled and unbound turns
    never open the memory database. A `None` return means storage could not
    be opened, and the orchestrator degrades to an ungated answer with a
    `skipped` trace rather than failing the turn. Owner resolution swallows
    its own storage errors the same way, so the     orchestrator never imports
    workspace storage details and the R4 orchestration import boundary holds.
    """
    try:
        memory = SQLiteMemoryRepository(db_path=settings.APP_DB_PATH)
        workspaces = SQLiteWorkspaceRepository(db_path=settings.APP_DB_PATH)
    except (MemoryRepositoryError, WorkspaceRepositoryError) as error:
        logger.error(
            "memory.components unavailable failure_class=%s",
            type(error).__name__,
        )
        return None

    def resolve_owner(workspace_id: str):
        try:
            workspace = workspaces.get(workspace_id)
        except WorkspaceRepositoryError as error:
            logger.error(
                "memory.owner unavailable failure_class=%s",
                type(error).__name__,
            )
            return None
        return workspace.owner_user_id if workspace is not None else None

    return MemoryComponents(
        retrieval_service=MemoryRetrievalService(
            memory, max_selected=settings.MEMORY_MAX_SELECTED
        ),
        resolve_owner=resolve_owner,
    )


def get_conversation_orchestrator() -> ConversationOrchestrator:
    """Construct the orchestrator for one chat turn.

    The RAG service is resolved eagerly because every turn generates an answer.
    The conversation service is passed as a provider so it is constructed only
    when the caller supplied a `conversation_id`. Memory components travel
    behind a second provider so they resolve only for a gate-enabled bound
    turn. The public request body carries no memory override.
    """
    return ConversationOrchestrator(
        rag_service=get_rag_service(),
        conversation_service_provider=get_conversation_service,
        memory_enabled=settings.MEMORY_RETRIEVAL_ENABLED,
        memory_provider=get_memory_components,
        max_selected=settings.MEMORY_MAX_SELECTED,
    )


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    request: ChatRequest,
    orchestrator: ConversationOrchestrator = Depends(get_conversation_orchestrator),
):
    """Chat endpoint receiving prompt and returning RAG-generated response with citations."""
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")

    logger.info(f"Received chat request: '{user_message[:50]}...'")

    try:
        outcome = orchestrator.handle_turn(
            message=user_message, conversation_id=request.conversation_id
        )

        conversation = (
            ConversationTurnPayload(
                conversation_id=outcome.conversation.conversation_id,
                user_message_id=outcome.conversation.user_message_id,
                assistant_message_id=outcome.conversation.assistant_message_id,
                persisted=outcome.conversation.persisted,
            )
            if outcome.conversation is not None
            else None
        )

        memory = (
            ChatMemoryPayload(
                enabled=outcome.memory.enabled,
                status=outcome.memory.status.value,
                selected_memory_ids=list(outcome.memory.selected_memory_ids),
                selection_reasons=[
                    reason.value for reason in outcome.memory.selection_reasons
                ],
            )
            if outcome.memory is not None
            else None
        )

        return ChatResponse(
            reply=outcome.reply,
            model=outcome.model,
            citations=outcome.citations,
            conversation=conversation,
            memory=memory,
        )

    except HTTPException:
        # Storage construction already produced a controlled response.
        raise
    except ConversationNotFoundError as error:
        logger.info("chat.turn miss failure_class=conversation_not_found")
        raise HTTPException(
            status_code=404, detail=_CONVERSATION_NOT_FOUND_DETAIL
        ) from error
    except ConversationRepositoryError as error:
        logger.error(
            "chat.turn failed stage=user_message failure_class=%s",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=500, detail=_CONVERSATION_STORAGE_DETAIL
        ) from error
    except ConversationValidationError as error:
        # A `ValueError` subclass, so it must be handled before the RAG branch.
        logger.info("chat.turn rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ValueError as ve:
        logger.error(f"Validation error in RAG Chat: {str(ve)}")
        raise HTTPException(status_code=500, detail=str(ve))
    except Exception as e:
        logger.error(f"Error executing RAG Chat Endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"LLM RAG Service Error: {str(e)}")
