"""Standalone conversation routes for authenticated chat.

Every route requires authentication. Conversation identity and ordering are
server-owned; conversations are owned directly by the authenticated principal
with zero workspace dependency.

Direct message append is permanently removed: user turns enter through the
`/chat` route.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.runtime_container import get_conversation_service
from backend.app.schemas.conversations import (
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationResponse,
    MessageListResponse,
    MessageResponse,
)
from backend.conversations.models import (
    DEFAULT_HISTORY_LIMIT,
    MAX_HISTORY_LIMIT,
    ConversationValidationError,
    MessageHistoryQuery,
)
from backend.conversations.repository import ConversationRepositoryError
from backend.conversations.service import (
    ConversationNotFoundError,
    ConversationService,
)
from backend.security.dependencies import require_principal
from backend.security.models import AuthenticatedPrincipal

logger = logging.getLogger("travel_agent_conversations")
router = APIRouter()

_CONVERSATION_NOT_FOUND_DETAIL = "Conversation not found."
_STORAGE_ERROR_DETAIL = "Conversation storage is unavailable."


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=201,
)
def create_conversation(
    request: ConversationCreateRequest,
    service: ConversationService = Depends(get_conversation_service),
    principal: AuthenticatedPrincipal = Depends(require_principal),
) -> ConversationResponse:
    """Create one standalone conversation for the authenticated principal."""
    try:
        created = service.create_conversation(
            owner_user_id=principal.owner_user_id,
            title=request.title,
        )
    except ConversationValidationError as error:
        logger.info("conversation.create rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ConversationRepositoryError as error:
        logger.error(
            "conversation.create failed failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "conversation.create ok conversation_id=%s owner_user_id=%s",
        created.conversation_id,
        created.owner_user_id,
    )
    return ConversationResponse.from_domain(created)


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
)
def list_conversations(
    service: ConversationService = Depends(get_conversation_service),
    principal: AuthenticatedPrincipal = Depends(require_principal),
) -> ConversationListResponse:
    """List all active conversations owned by the authenticated principal."""
    try:
        conversations = service.list_conversations(principal.owner_user_id)
    except ConversationValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ConversationRepositoryError as error:
        logger.error("conversation.list failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    return ConversationListResponse(
        conversations=[
            ConversationResponse.from_domain(record) for record in conversations
        ]
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
)
def get_conversation(
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
    principal: AuthenticatedPrincipal = Depends(require_principal),
) -> ConversationResponse:
    """Retrieve one owned conversation by identifier, 404 if not found or foreign."""
    try:
        conversation = service.get_conversation_for_owner(
            conversation_id, principal.owner_user_id
        )
    except ConversationValidationError as error:
        logger.info("conversation.get rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ConversationRepositoryError as error:
        logger.error("conversation.get failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    if conversation is None:
        logger.info("conversation.get miss failure_class=not_found")
        raise HTTPException(status_code=404, detail=_CONVERSATION_NOT_FOUND_DETAIL)

    logger.info("conversation.get ok conversation_id=%s", conversation.conversation_id)
    return ConversationResponse.from_domain(conversation)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
)
def list_messages(
    conversation_id: str,
    after_message_id: str | None = Query(
        None, description="Return only messages after this message"
    ),
    limit: int = Query(
        DEFAULT_HISTORY_LIMIT,
        ge=1,
        le=MAX_HISTORY_LIMIT,
        description="Maximum messages to return",
    ),
    service: ConversationService = Depends(get_conversation_service),
    principal: AuthenticatedPrincipal = Depends(require_principal),
) -> MessageListResponse:
    """Read one page of message history in transcript order for an owned conversation."""
    try:
        query = MessageHistoryQuery(
            conversation_id=conversation_id,
            after_message_id=after_message_id,
            limit=limit,
        )
        messages = service.list_messages(query, owner_user_id=principal.owner_user_id)
    except ConversationValidationError as error:
        logger.info("conversation.history rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ConversationNotFoundError as error:
        logger.info("conversation.history miss failure_class=not_found")
        raise HTTPException(
            status_code=404, detail=_CONVERSATION_NOT_FOUND_DETAIL
        ) from error
    except ConversationRepositoryError as error:
        logger.error(
            "conversation.history failed failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    next_cursor = messages[-1].message_id if len(messages) == query.limit else None

    logger.info(
        "conversation.history ok conversation_id=%s count=%s cursor_supplied=%s",
        query.conversation_id,
        len(messages),
        after_message_id is not None,
    )
    return MessageListResponse(
        messages=[MessageResponse.from_domain(message) for message in messages],
        next_cursor=next_cursor,
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
)
def delete_conversation(
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
    principal: AuthenticatedPrincipal = Depends(require_principal),
) -> None:
    """Tombstone one owned conversation."""
    try:
        service.delete_conversation(conversation_id, principal.owner_user_id)
    except ConversationNotFoundError:
        logger.info("conversation.delete miss failure_class=not_found")
        raise HTTPException(status_code=404, detail=_CONVERSATION_NOT_FOUND_DETAIL)
    except ConversationValidationError as error:
        logger.info("conversation.delete rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ConversationRepositoryError as error:
        logger.error(
            "conversation.delete failed failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "conversation.delete ok conversation_id=%s owner_user_id=%s",
        conversation_id,
        principal.owner_user_id,
    )
