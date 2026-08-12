from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Chào bạn, Hà Nội có gì đẹp?"})
    session_id: Optional[str] = Field(
        None, json_schema_extra={"example": "550e8400-e29b-41d4-a716-446655440000"}
    )


class Citation(BaseModel):
    title: str = Field(..., json_schema_extra={"example": "7 stunning rooftop bars in Vietnam"})
    url: str = Field(
        ...,
        json_schema_extra={
            "example": "https://vietnam.travel/things-to-do/7-stunning-rooftop-bars-vietnam"
        },
    )


class ChatResponse(BaseModel):
    reply: str = Field(..., json_schema_extra={"example": "Chào bạn! Hà Nội nổi tiếng với phố cổ."})
    model: str = Field("gpt-4o-mini")
    citations: List[Citation] = Field(default_factory=list)
    session_id: str = Field(..., json_schema_extra={"example": "550e8400-e29b-41d4-a716-446655440000"})
