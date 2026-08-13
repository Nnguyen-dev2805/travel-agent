"""API endpoints for managing Chat History and User Long-term Memory Facts."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.api.deps import get_current_user
from backend.memory.conversation_memory import ConversationMemoryService
from backend.memory.fact_memory import FactMemoryService

logger = logging.getLogger("travel_agent_memory_api")
router = APIRouter(prefix="/memory", tags=["Memory Management"])

# Helper instances
_conv_service = ConversationMemoryService()
_fact_service = FactMemoryService()


class UserMemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., json_schema_extra={"example": 1})
    user_id: int = Field(..., json_schema_extra={"example": 42})
    fact_type: str = Field(..., json_schema_extra={"example": "dietary"})
    fact_key: str = Field(..., json_schema_extra={"example": "food_allergy"})
    content: str = Field(..., json_schema_extra={"example": "Dị ứng hải sản"})
    confidence: float = Field(1.0, json_schema_extra={"example": 1.0})


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., json_schema_extra={"example": "550e8400-e29b-41d4-a716-446655440000"})
    user_id: Optional[int] = Field(None, json_schema_extra={"example": 1})
    title: Optional[str] = Field(None, json_schema_extra={"example": "Lịch trình đi Đà Lạt 3 ngày"})
    created_at: datetime
    updated_at: datetime


@router.get("/sessions", response_model=List[ChatSessionResponse])
def get_user_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all chat sessions belonging to the authenticated user."""
    return _conv_service.get_user_sessions(db, current_user.id)


@router.get("/history/{session_id}")
def get_session_history(
    session_id: str,
    db: Session = Depends(get_db),
) -> List[Dict[str, str]]:
    """Get formatted sliding window conversation history for a chat session."""
    return _conv_service.format_messages_for_llm(db, session_id.strip())


@router.delete("/history/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session_history(
    session_id: str,
    db: Session = Depends(get_db),
):
    """Clear all chat messages and delete a session."""
    _conv_service.delete_session(db, session_id.strip())


@router.get("/facts", response_model=List[UserMemoryResponse])
def get_user_facts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all long-term preference facts belonging to the authenticated user."""
    return _fact_service.get_user_facts(db, current_user.id)


@router.delete("/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_fact(
    fact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a specific memory fact ensuring strict user ownership isolation."""
    success = _fact_service.delete_fact(db, user_id=current_user.id, fact_id=fact_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy bản ghi ký ức hoặc bạn không có quyền xóa.",
        )
