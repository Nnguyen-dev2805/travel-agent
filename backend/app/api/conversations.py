"""FastAPI conversation routes for runtime milestone R4.

These routes are mounted beside the existing chat and workspace routes and change
neither contract. They construct no RAG service, embedding model, Chroma
collection, or model-provider client.

Conversations inherit scope from their parent workspace, whose `owner_user_id` is
a local development scope label. These routes implement no authentication,
authorization, or tenant isolation, and must not be exposed publicly.

Logging records route, action, conversation and message identifiers, sequence,
role, counts, and failure class only. Message content and conversation titles are
never logged, and HTTP errors never echo them.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.config import settings
from backend.app.schemas.conversations import (
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationResponse,
    MessageAppendRequest,
    MessageListResponse,
    MessageResponse,
)
from backend.conversations.models import (
    DEFAULT_HISTORY_LIMIT,
    MAX_HISTORY_LIMIT,
    PUBLIC_WRITABLE_ROLES,
    ConversationCreate,
    ConversationValidationError,
    MessageHistoryQuery,
)
from backend.conversations.repository import ConversationRepositoryError
from backend.conversations.service import (
    ConversationNotFoundError,
    ConversationService,
    WorkspaceNotFoundError,
)
from backend.conversations.sqlite_repository import SQLiteConversationRepository
from backend.workspaces.repository import WorkspaceRepositoryError
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

logger = logging.getLogger("travel_agent_conversations")
router = APIRouter()

_STORAGE_ERROR_DETAIL = "Conversation storage is unavailable."
_WORKSPACE_NOT_FOUND_DETAIL = "Workspace not found."
_CONVERSATION_NOT_FOUND_DETAIL = "Conversation not found."
_RESTRICTED_ROLE_DETAIL = (
    "This route accepts only the 'user' and 'system_event' message roles. "
    "Other roles are written by the conversation orchestrator."
)


def get_conversation_service() -> ConversationService:
    """Construct the conversation service over the shared local application store.

    This is one of the two places that resolve `settings.APP_DB_PATH`; the other
    is the workspace dependency. Both modules coexist in one database file with
    independent schema versions. Tests override this dependency with a temporary
    database path.

    Storage construction can fail before any route body runs, for example when
    the configured database records an incompatible schema version or its
    directory is not writable. Converting that failure here keeps the caller's
    response a controlled `500` instead of an unhandled server error.

    Raises:
        HTTPException: Storage could not be opened or initialized.
    """
    try:
        conversations = SQLiteConversationRepository(db_path=settings.APP_DB_PATH)
        workspaces = SQLiteWorkspaceRepository(db_path=settings.APP_DB_PATH)
    except (ConversationRepositoryError, WorkspaceRepositoryError) as error:
        logger.error(
            "conversation.storage unavailable failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error
    return ConversationService(
        conversation_repository=conversations, workspace_repository=workspaces
    )


@router.post(
    "/workspaces/{workspace_id}/conversations",
    response_model=ConversationResponse,
    status_code=201,
)
def create_conversation(
    workspace_id: str,
    request: ConversationCreateRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    """Create one conversation inside an existing trip workspace."""
    try:
        conversation_input = ConversationCreate(
            workspace_id=workspace_id, title=request.title
        )
    except ConversationValidationError as error:
        logger.info("conversation.create rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error

    try:
        conversation = service.create_conversation(conversation_input)
    except ConversationValidationError as error:
        logger.info("conversation.create rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        logger.info("conversation.create miss failure_class=workspace_not_found")
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except ConversationRepositoryError as error:
        logger.error(
            "conversation.create failed failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "conversation.create ok conversation_id=%s workspace_id=%s",
        conversation.conversation_id,
        conversation.workspace_id,
    )
    return ConversationResponse.from_domain(conversation)


@router.get(
    "/workspaces/{workspace_id}/conversations",
    response_model=ConversationListResponse,
)
def list_conversations(
    workspace_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationListResponse:
    """List conversations inside one trip workspace, newest updated first."""
    try:
        conversations = service.list_conversations(workspace_id)
    except ConversationValidationError as error:
        logger.info("conversation.list rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except WorkspaceNotFoundError as error:
        logger.info("conversation.list miss failure_class=workspace_not_found")
        raise HTTPException(
            status_code=404, detail=_WORKSPACE_NOT_FOUND_DETAIL
        ) from error
    except ConversationRepositoryError as error:
        logger.error("conversation.list failed failure_class=%s", type(error).__name__)
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "conversation.list ok workspace_id=%s count=%s",
        workspace_id.strip(),
        len(conversations),
    )
    return ConversationListResponse(
        conversations=[
            ConversationResponse.from_domain(record) for record in conversations
        ]
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    """Retrieve one conversation by identifier."""
    try:
        conversation = service.get_conversation(conversation_id)
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


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=201,
)
def append_message(
    conversation_id: str,
    request: MessageAppendRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> MessageResponse:
    """Append one message to an existing conversation.

    The public role restriction is enforced here, before the service call, so a
    caller can never forge an assistant or tool turn and poison later memory
    extraction through the public API.
    """
    if request.role not in PUBLIC_WRITABLE_ROLES:
        logger.info(
            "conversation.append rejected conversation_id=%s failure_class=restricted_role",
            conversation_id,
        )
        raise HTTPException(status_code=422, detail=_RESTRICTED_ROLE_DETAIL)

    try:
        message = service.append_message(
            conversation_id=conversation_id,
            role=request.role,
            content=request.content,
            source=request.source,
            trace_visibility=request.trace_visibility,
        )
    except ConversationValidationError as error:
        logger.info("conversation.append rejected failure_class=validation")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ConversationNotFoundError as error:
        logger.info("conversation.append miss failure_class=not_found")
        raise HTTPException(
            status_code=404, detail=_CONVERSATION_NOT_FOUND_DETAIL
        ) from error
    except ConversationRepositoryError as error:
        logger.error(
            "conversation.append failed failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error

    logger.info(
        "conversation.append ok conversation_id=%s message_id=%s sequence=%s role=%s",
        message.conversation_id,
        message.message_id,
        message.sequence,
        message.role.value,
    )
    return MessageResponse.from_domain(message)


@router.get(
    "/conversations/{conversation_id}/messages", response_model=MessageListResponse
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
) -> MessageListResponse:
    """Read one page of message history in transcript order."""
    try:
        query = MessageHistoryQuery(
            conversation_id=conversation_id,
            after_message_id=after_message_id,
            limit=limit,
        )
        messages = service.list_messages(query)
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

    # A full page means more records may exist, so the caller receives a cursor.
    # A short page is the last page and reports no cursor.
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
