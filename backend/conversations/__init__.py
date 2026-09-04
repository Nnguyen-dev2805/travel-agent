"""Conversation module for runtime milestone R4.

This package owns conversation and message value contracts, the storage
interface, the local SQLite adapter, and conversation use cases. Conversations
are scoped to an existing `TripWorkspace` and depend on the workspace repository
interface in one direction only, to verify that a parent workspace exists.

R4 implements no authentication, authorization, sessions, collaboration, memory,
conversation summarization, planner state, itinerary versions, or deletion
semantics. Conversations carry no owner field: scope is inherited from the parent
workspace, whose `owner_user_id` is a local development scope label rather than a
verified principal.

Message content is stored, never logged, and never deleted by R4.

Import from the submodules directly. This module re-exports only the names a
caller outside the package needs to construct the conversation stack.
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
    WorkspaceNotFoundError,
)

# `SQLiteConversationRepository` is deliberately NOT re-exported here. Importing
# this package must not pull `sqlite3` or the shared schema registry into the
# graph, which is what makes the conversation service's dependency boundary
# verifiable by test rather than only documented. Import the adapter from
# `backend.conversations.sqlite_repository` at the dependency construction site.

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
    "WorkspaceNotFoundError",
    "generate_conversation_id",
    "generate_message_id",
    "require_text",
    "utc_now",
]
