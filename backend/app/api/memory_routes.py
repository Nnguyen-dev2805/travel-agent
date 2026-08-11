"""API endpoints for managing Chat History and User Long-term Memory Facts."""

import logging
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
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
    fact_value: str = Field(..., json_schema_extra={"example": "Dị ứng hải sản"})
    confidence: float = Field(1.0, json_schema_extra={"example": 1.0})


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
    """Clear all chat messages in a session."""
    _conv_service.clear_session(db, session_id.strip())


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
