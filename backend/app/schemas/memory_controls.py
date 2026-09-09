"""Public request and response shapes for risk-based memory controls.

These schemas own the HTTP contract only. Utterances arrive as opaque
text; everything the server echoes back is governed vocabulary
(operations, scopes, keys, normalized values, reason codes) plus
server-owned identifiers. Free-form display text and raw input are
never echoed, so refusal and error bodies cannot leak content.
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class MemoryCommandRequest(BaseModel):
    """One NL memory utterance with optional explicit scope context."""

    model_config = ConfigDict(extra="forbid")

    utterance: str = Field(min_length=1, max_length=2000)
    conversation_id: Optional[str] = None
    scope: Optional[Literal["user", "conversation"]] = None
    idempotency_key: Optional[str] = None


class UndoDescriptorResponse(BaseModel):
    """A compensating action descriptor; never auto-executed."""

    action: str
    version_ids: List[str] = Field(default_factory=list)
    note: str


class PreviewTargetResponse(BaseModel):
    """One governed target shown exactly as it would commit."""

    version_id: str
    canonical_key: str
    normalized_value: str
    scope: str
    old_scope: Optional[str] = None
    new_scope: Optional[str] = None


class PreviewPayloadResponse(BaseModel):
    """A pending preview with its one-time confirmation token."""

    preview_id: str
    token: str
    operation: str
    targets: List[PreviewTargetResponse] = Field(default_factory=list)
    expires_in_seconds: float


class MemoryCommandResponse(BaseModel):
    """One command outcome across saved/deleted/toggled/held/refused/pending."""

    status: str
    operation: Optional[str] = None
    scope: Optional[str] = None
    canonical_key: Optional[str] = None
    normalized_value: Optional[str] = None
    version_id: Optional[str] = None
    committed_version_ids: List[str] = Field(default_factory=list)
    reason_code: Optional[str] = None
    persistent: Optional[bool] = None
    note: Optional[str] = None
    undo: Optional[UndoDescriptorResponse] = None
    preview: Optional[PreviewPayloadResponse] = None


class MemoryEntryResponse(BaseModel):
    """One inspectable active memory in governed vocabulary only."""

    version_id: str
    canonical_key: str
    normalized_value: str
    scope: str
    authority: str
    sensitivity: str
    valid_from: datetime


class MemoryListResponse(BaseModel):
    """Active memories for one owner, oldest first."""

    memories: List[MemoryEntryResponse] = Field(default_factory=list)


class MemoryDeletionRequest(BaseModel):
    """Delete versions by id: one commits directly, many open a preview."""

    model_config = ConfigDict(extra="forbid")

    version_ids: List[str] = Field(min_length=1, max_length=20)


class MemoryExpansionRequest(BaseModel):
    """Open a scoped preview widening one conversation version to user."""

    model_config = ConfigDict(extra="forbid")

    version_id: str = Field(min_length=1)


class MemoryConfirmRequest(BaseModel):
    """Confirm a pending preview with its one-time token."""

    model_config = ConfigDict(extra="forbid")

    preview_id: str = Field(min_length=1)
    token: str = Field(min_length=1)
