"""Conversation module for authenticated chat.

This package owns conversation and message value contracts, the storage
interface, and conversation use cases. Per ADR 0021, conversations are
standalone and owned directly by authenticated users (`owner_user_id`),
with no dependency on workspaces.

Import from the submodules directly. This module re-exports the names a
caller needs to interact with the conversation domain.
"""

from backend.conversations.models import (
    CONVERSATION_ID_PREFIX,
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_MESSAGE_SOURCE,
    DEFAULT_RETENTION_STATE,
    DEFAULT_TRACE_VISIBILITY,
    MAX_HISTORY_LIMIT,
    MESSAGE_ID_PREFIX,
    PUBLIC_WRITABLE_ROLES,
    TITLE_MAX_LENGTH,
    Conversation,
    ConversationCreate,
    ConversationRetentionState,
    ConversationValidationError,
    Message,
    MessageDraft,
    MessageHistoryQuery,
    MessageRole,
    MessageSource,
    TraceVisibility,
    generate_conversation_id,
    generate_message_id,
    require_text,
    utc_now,
)
from backend.conversations.repository import (
    ConversationAlreadyExistsError,
    ConversationRepository,
    ConversationRepositoryError,
    ConversationStorageError,
    MessageAlreadyExistsError,
    MessageSequenceConflictError,
)
from backend.conversations.service import (
    ConversationNotFoundError,
    ConversationService,
)

__all__ = [
    "CONVERSATION_ID_PREFIX",
    "DEFAULT_HISTORY_LIMIT",
    "DEFAULT_MESSAGE_SOURCE",
    "DEFAULT_RETENTION_STATE",
    "DEFAULT_TRACE_VISIBILITY",
    "MAX_HISTORY_LIMIT",
    "MESSAGE_ID_PREFIX",
    "PUBLIC_WRITABLE_ROLES",
    "TITLE_MAX_LENGTH",
    "Conversation",
    "ConversationAlreadyExistsError",
    "ConversationCreate",
    "ConversationNotFoundError",
    "ConversationRepository",
    "ConversationRepositoryError",
    "ConversationRetentionState",
    "ConversationService",
    "ConversationStorageError",
    "ConversationValidationError",
    "Message",
    "MessageAlreadyExistsError",
    "MessageDraft",
    "MessageHistoryQuery",
    "MessageRole",
    "MessageSequenceConflictError",
    "MessageSource",
    "TraceVisibility",
    "generate_conversation_id",
    "generate_message_id",
    "require_text",
    "utc_now",
]
