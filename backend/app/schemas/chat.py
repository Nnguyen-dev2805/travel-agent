from typing import Any, Dict, List
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Chào bạn, Hà Nội có gì đẹp?"})

class Citation(BaseModel):
    title: str = Field(..., json_schema_extra={"example": "7 stunning rooftop bars in Vietnam"})
    url: str = Field(..., json_schema_extra={"example": "https://vietnam.travel/things-to-do/7-stunning-rooftop-bars-vietnam"})

class ChatResponse(BaseModel):
    reply: str = Field(..., json_schema_extra={"example": "Chào bạn! Hà Nội nổi tiếng với phố cổ và hồ Hoàn Kiếm."})
    model: str = Field("gpt-4o-mini")
    citations: List[Citation] = Field(default_factory=list)
