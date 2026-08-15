from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Chào bạn, Hà Nội có gì đẹp?"})
    session_id: Optional[str] = Field(
        None, json_schema_extra={"example": "550e8400-e29b-41d4-a716-446655440000"}
    )


class DebugInfo(BaseModel):
    router_decision: Optional[Dict[str, Any]] = Field(default=None, description="Raw output from the context router.")
    user_facts: Optional[str] = Field(default=None, description="The user facts and episodic memory retrieved for the query.")
    rag_context_used: Optional[bool] = Field(default=None, description="Whether RAG was queried.")


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
    debug_info: Optional[DebugInfo] = Field(default=None, description="Optional debug information containing system routing details.")
