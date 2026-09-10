"""Public request and response JSON shapes for standalone conversation routes.

These schemas own the HTTP contract only. Identity, ordering, and timestamps are
server-owned, so `conversation_id`, `created_at`, `updated_at`, and `retention_state`
are never accepted from a request body.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.conversations.models import (
    Conversation,
    ConversationRetentionState,
    Message,
    MessageRole,
    MessageSource,
    TraceVisibility,
)


class ConversationCreateRequest(BaseModel):
    """Create one standalone conversation."""

    title: Optional[str] = Field(
        None, json_schema_extra={"example": "Da Nang food plan"}
    )


class ConversationResponse(BaseModel):
    """One conversation record."""

    conversation_id: str
    owner_user_id: str
    title: Optional[str]
    retention_state: ConversationRetentionState | str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, conversation: Conversation) -> "ConversationResponse":
        return cls(
            conversation_id=conversation.conversation_id,
            owner_user_id=conversation.owner_user_id,
            title=conversation.title,
            retention_state=conversation.retention_state,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class ConversationListResponse(BaseModel):
    """Owner-scoped conversation list."""

    conversations: List[ConversationResponse] = Field(default_factory=list)


class MessageResponse(BaseModel):
    """One message record, including its server-assigned position."""

    message_id: str
    conversation_id: str
    sequence: int
    role: MessageRole
    content: str
    source: MessageSource
    trace_visibility: TraceVisibility
    created_at: datetime

    @classmethod
    def from_domain(cls, message: Message) -> "MessageResponse":
        return cls(
            message_id=message.message_id,
            conversation_id=message.conversation_id,
            sequence=message.sequence,
            role=message.role,
            content=message.content,
            source=message.source,
            trace_visibility=message.trace_visibility,
            created_at=message.created_at,
        )


class MessageListResponse(BaseModel):
    """One page of message history in transcript order.

    `next_cursor` is the last returned `message_id` when the page was full, so
    more records may exist, and `null` otherwise.
    """

    messages: List[MessageResponse] = Field(default_factory=list)
    next_cursor: Optional[str] = None
