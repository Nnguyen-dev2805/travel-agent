from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_serializer


class ChatRequest(BaseModel):
    """One chat turn.

    `conversation_id` is optional and additive per ADR 0005. A request that omits
    it receives exactly the response it received before R4.
    """

    message: str = Field(
        ..., json_schema_extra={"example": "Chào bạn, Hà Nội có gì đẹp?"}
    )
    conversation_id: Optional[str] = Field(
        None, json_schema_extra={"example": "cv_example"}
    )


class Citation(BaseModel):
    title: str = Field(
        ..., json_schema_extra={"example": "7 stunning rooftop bars in Vietnam"}
    )
    url: str = Field(
        ...,
        json_schema_extra={
            "example": "https://vietnam.travel/things-to-do/7-stunning-rooftop-bars-vietnam"
        },
    )


class ConversationTurnPayload(BaseModel):
    """Persistence outcome for a chat turn bound to a conversation.

    `persisted` is `false` with a `null` `assistant_message_id` when the reply was
    generated but could not be stored, so a persistence gap is reported rather
    than hidden.
    """

    conversation_id: str = Field(..., json_schema_extra={"example": "cv_example"})
    user_message_id: Optional[str] = Field(
        None, json_schema_extra={"example": "ms_user_example"}
    )
    assistant_message_id: Optional[str] = Field(
        None, json_schema_extra={"example": "ms_assistant_example"}
    )
    persisted: bool = Field(..., json_schema_extra={"example": True})


class ChatMemoryPayload(BaseModel):
    """Controlled memory trace metadata for one feature-gated bound turn.

    Carries selected memory identifiers and controlled selection reasons
    only. Memory records are never citations, and no raw source message or
    memory content travels in this object.
    """

    enabled: bool = Field(..., json_schema_extra={"example": True})
    status: str = Field(..., json_schema_extra={"example": "selected"})
    selected_memory_ids: List[str] = Field(default_factory=list)
    selection_reasons: List[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str = Field(
        ...,
        json_schema_extra={
            "example": "Chào bạn! Hà Nội nổi tiếng với phố cổ và hồ Hoàn Kiếm."
        },
    )
    model: str = Field("gpt-4o-mini")
    citations: List[Citation] = Field(default_factory=list)
    conversation: Optional[ConversationTurnPayload] = None
    memory: Optional[ChatMemoryPayload] = None

    @model_serializer(mode="wrap")
    def _omit_absent_conversation(self, handler) -> Dict[str, Any]:
        """Drop `conversation` and `memory` entirely when each is absent.

        R3 froze `reply`, `model`, and `citations`. An unbound response must carry
        no `conversation` key at all, not a `null` one, so an existing client
        observes no difference. The same rule covers `memory`: a gate-disabled
        or unbound turn carries no `memory` key at all. Nested `null` values
        inside a present `conversation` object are preserved, because a `null`
        `assistant_message_id` is meaningful.
        """
        data = handler(self)
        if data.get("conversation") is None:
            data.pop("conversation", None)
        if data.get("memory") is None:
            data.pop("memory", None)
        return data
