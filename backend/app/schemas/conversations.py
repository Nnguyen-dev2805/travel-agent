"""Public request and response JSON shapes for the R4 conversation routes.

These schemas own the HTTP contract only. Identity, ordering, and timestamps are
server-owned, so `conversation_id`, `message_id`, `sequence`, `created_at`,
`updated_at`, and `retention_state` are never accepted from a request body.

List responses are objects rather than bare arrays so a later milestone can add
pagination metadata without a breaking change.
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
    """Create one conversation under an existing trip workspace.

    `workspace_id` arrives in the path, not the body, so scope is a structural
    property of the route rather than a validation step a future change could
    forget.

    The title bound is enforced by the domain contract rather than declared here,
    so a rejection message names the rule without echoing the submitted title.
    """

    title: Optional[str] = Field(
        None, json_schema_extra={"example": "Da Nang food plan"}
    )


class ConversationResponse(BaseModel):
    """One conversation record."""

    conversation_id: str
    workspace_id: str
    title: Optional[str]
    retention_state: ConversationRetentionState
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, conversation: Conversation) -> "ConversationResponse":
        return cls(
            conversation_id=conversation.conversation_id,
            workspace_id=conversation.workspace_id,
            title=conversation.title,
            retention_state=conversation.retention_state,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class ConversationListResponse(BaseModel):
    """Workspace-scoped conversation list in governed newest-first order."""

    conversations: List[ConversationResponse] = Field(default_factory=list)


class MessageAppendRequest(BaseModel):
    """Append one message to an existing conversation.

    `role` is typed as the full governed vocabulary rather than only the publicly
    writable subset, so a restricted role is refused by the route with a message
    that names the restriction instead of echoing the submitted value back.

    The non-empty `content` rule is enforced by the domain contract, so a
    rejection never echoes submitted message content.
    """

    role: MessageRole = Field(..., json_schema_extra={"example": "user"})
    content: str = Field(
        ..., json_schema_extra={"example": "Nên đi Đà Nẵng vào tháng mấy?"}
    )
    source: Optional[MessageSource] = Field(None, json_schema_extra={"example": "ui"})
    trace_visibility: Optional[TraceVisibility] = Field(
        None, json_schema_extra={"example": "excluded"}
    )


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
