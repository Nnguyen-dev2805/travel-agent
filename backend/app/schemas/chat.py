from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(..., json_schema_extra={"example": "Chào bạn, Hà Nội có gì đẹp?"})

class ChatResponse(BaseModel):
    reply: str = Field(..., json_schema_extra={"example": "Chào bạn! Hà Nội nổi tiếng với phố cổ và hồ Hoàn Kiếm."})
    model: str = Field("gpt-4o-mini")
