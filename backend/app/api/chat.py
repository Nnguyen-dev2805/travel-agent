import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.models.user import User
from backend.app.api.deps import get_optional_user
from backend.memory.memory_manager import MemoryManager
from backend.rag.generation import RAGService

logger = logging.getLogger("travel_agent_backend")
router = APIRouter()

# Global instances
_rag_service = None
_memory_manager = None


def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


def get_memory_manager() -> MemoryManager:
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Chat endpoint supporting Guest (Session-based) and Authenticated User (Dual-layer Memory)."""
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nội dung tin nhắn không được để trống.")

    # Resolve or auto-generate session_id UUID
    session_id = request.session_id.strip() if (request.session_id and request.session_id.strip()) else str(uuid.uuid4())
    user_id_log = current_user.id if current_user else "Guest"
    logger.info(f"Received chat request from User={user_id_log}, Session='{session_id}': '{user_message[:50]}...'")

    try:
        memory_mgr = get_memory_manager()
        rag_service = get_rag_service()

        # 1. Build memory context (Short-term history + Long-term facts if authenticated)
        memory_context = memory_mgr.build_memory_context(db, session_id, user=current_user)

        # 2. Generate RAG Answer with injected memory context
        result = rag_service.generate_answer(
            user_message=user_message,
            top_k=4,
            conversation_history=memory_context["conversation_history"],
            user_facts=memory_context["user_facts"],
        )

        # 3. Process turn: Save message history & extract facts if authenticated
        memory_mgr.process_turn(
            db=db,
            session_id=session_id,
            user_message=user_message,
            assistant_reply=result["reply"],
            user=current_user,
        )

        return ChatResponse(
            reply=result["reply"],
            model=result["model"],
            citations=result["citations"],
            session_id=session_id,
        )

    except ValueError as ve:
        logger.error(f"Validation error in RAG Chat: {str(ve)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error executing RAG Chat Endpoint: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"LLM RAG Service Error: {str(e)}")
