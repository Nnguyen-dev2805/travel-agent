"""Chat endpoint orchestration for authenticated chat."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.app.config import settings
from backend.app.runtime_container import (
    get_conversation_orchestrator,
    get_conversation_service,
)
from backend.app.schemas.chat import (
    ChatMemoryPayload,
    ChatRequest,
    ChatResponse,
    ConversationTurnPayload,
)
from backend.conversations.models import ConversationValidationError
from backend.conversations.repository import ConversationRepositoryError
from backend.conversations.service import (
    ConversationNotFoundError,
    ConversationService,
)
from backend.observability.events import emit_event
from backend.observability.models import (
    EventComponent,
    EventName,
    EventResult,
)
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator
from backend.rag.generation import RAGService
from backend.security.dependencies import require_principal
from backend.security.models import AuthenticatedPrincipal, CrossOwnerAccessError

logger = logging.getLogger("travel_agent_backend")
router = APIRouter()

_CONVERSATION_NOT_FOUND_DETAIL = "Conversation not found."
_CONVERSATION_STORAGE_DETAIL = "Conversation storage is unavailable."
_GENERATION_FAILED_DETAIL = "Chat generation failed."

# Global RAG service instance for pre-warming compatibility
_rag_service = None


def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    request: ChatRequest,
    orchestrator: ConversationOrchestrator = Depends(get_conversation_orchestrator),
    conversation_service: ConversationService = Depends(get_conversation_service),
    principal: AuthenticatedPrincipal = Depends(require_principal),
):
    """Chat endpoint receiving prompt and returning RAG-generated response with citations."""
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")

    emit_event(
        EventName.CHAT_REQUEST_ACCEPTED,
        EventComponent.CHAT,
        EventResult.SUCCESS,
    )

    target_conversation_id = request.conversation_id
    if not target_conversation_id:
        try:
            created = conversation_service.create_conversation(
                owner_user_id=principal.owner_user_id,
                title=user_message[:60],
            )
            target_conversation_id = created.conversation_id
        except (ConversationRepositoryError, Exception) as error:
            logger.error(
                "chat.turn failed stage=create_conversation failure_class=%s",
                type(error).__name__,
            )
            raise HTTPException(
                status_code=500, detail=_CONVERSATION_STORAGE_DETAIL
            ) from error

    try:
        outcome = orchestrator.handle_turn(
            message=user_message,
            conversation_id=target_conversation_id,
            principal=principal,
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

        emit_event(
            EventName.CHAT_TURN_COMPLETED,
            EventComponent.CHAT,
            EventResult.SUCCESS,
            conversation_id=(
                outcome.conversation.conversation_id
                if outcome.conversation is not None
                else None
            ),
            message_id=(
                outcome.conversation.user_message_id
                if outcome.conversation is not None
                else None
            ),
            counters={
                "citations": len(outcome.citations),
                "memory_selected": (
                    len(outcome.memory.selected_memory_ids)
                    if outcome.memory is not None
                    else 0
                ),
                "persisted": (
                    outcome.conversation.persisted
                    if outcome.conversation is not None
                    else False
                ),
            },
        )
        return ChatResponse(
            reply=outcome.reply,
            model=outcome.model,
            citations=outcome.citations,
            conversation=conversation,
            memory=memory,
        )

    except HTTPException:
        raise
    except CrossOwnerAccessError as error:
        logger.info("chat.turn miss failure_class=conversation_not_found")
        raise HTTPException(
            status_code=404, detail=_CONVERSATION_NOT_FOUND_DETAIL
        ) from error
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
        logger.info("chat.turn rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ValueError as ve:
        emit_event(
            EventName.MODEL_CALL_FAILED,
            EventComponent.MODEL_PROVIDER,
            EventResult.FAILURE,
            failure_class=type(ve).__name__,
            reason_code="validation_error",
        )
        raise HTTPException(status_code=500, detail=_GENERATION_FAILED_DETAIL) from ve
    except Exception as e:
        emit_event(
            EventName.MODEL_CALL_FAILED,
            EventComponent.MODEL_PROVIDER,
            EventResult.FAILURE,
            failure_class=type(e).__name__,
            reason_code="unhandled_exception",
        )
        raise HTTPException(status_code=500, detail=_GENERATION_FAILED_DETAIL) from e
