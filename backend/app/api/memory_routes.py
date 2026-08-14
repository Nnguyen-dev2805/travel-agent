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
from backend.app.api.deps import get_current_user, get_optional_user
from backend.memory.conversation_memory import ConversationMemoryService
from backend.memory.fact_memory import FactMemoryService

logger = logging.getLogger("travel_agent_memory_api")
router = APIRouter(prefix="/memory", tags=["Memory Management"])
from backend.app.models.session import ChatSession
from functools import lru_cache

@lru_cache()
def get_conv_service() -> ConversationMemoryService:
    return ConversationMemoryService()

@lru_cache()
def get_fact_service() -> FactMemoryService:
    return FactMemoryService()


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
    conv_service: ConversationMemoryService = Depends(get_conv_service),
):
    """Get all chat sessions belonging to the authenticated user."""
    return conv_service.get_user_sessions(db, current_user.id)


@router.get("/history/{session_id}")
def get_session_history(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    conv_service: ConversationMemoryService = Depends(get_conv_service),
) -> List[Dict[str, str]]:
    """Get formatted sliding window conversation history for a chat session."""
    clean_sid = session_id.strip()
    session = db.get(ChatSession, clean_sid)
    if not session:
        return []
        
    if session.user_id is not None:
        if current_user is None or session.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền truy cập session này.")
            
    return conv_service.format_messages_for_llm(db, clean_sid)


@router.delete("/history/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session_history(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    conv_service: ConversationMemoryService = Depends(get_conv_service),
):
    """Clear all chat messages and delete a session."""
    user_id = current_user.id if current_user else None
    if not conv_service.delete_session(db, session_id.strip(), user_id=user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không tìm thấy session hoặc bạn không có quyền xóa.")


@router.get("/facts", response_model=List[UserMemoryResponse])
def get_user_facts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    fact_service: FactMemoryService = Depends(get_fact_service),
):
    """Get all long-term preference facts belonging to the authenticated user."""
    return fact_service.get_user_facts(db, current_user.id)


@router.delete("/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_fact(
    fact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    fact_service: FactMemoryService = Depends(get_fact_service),
):
    """Delete a specific memory fact ensuring strict user ownership isolation."""
    success = fact_service.delete_fact(db, user_id=current_user.id, fact_id=fact_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy bản ghi ký ức hoặc bạn không có quyền xóa.",
        )
