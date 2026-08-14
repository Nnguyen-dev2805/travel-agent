import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.concurrency import run_in_threadpool
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
from backend.app.config import settings

from backend.app.database import get_db
from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.models.user import User
from backend.app.api.deps import get_optional_user
from backend.memory.memory_manager import MemoryManager
from backend.rag.generation import RAGService
from backend.rag.routing.router import ContextRouter, RouteType, RouteDecision

logger = logging.getLogger("travel_agent_backend")
router = APIRouter()

from functools import lru_cache

@lru_cache()
def get_rag_service() -> RAGService:
    return RAGService()

@lru_cache()
def get_memory_manager() -> MemoryManager:
    return MemoryManager()

@lru_cache()
def get_router() -> ContextRouter:
    return ContextRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
    memory_mgr: MemoryManager = Depends(get_memory_manager),
    rag_service: RAGService = Depends(get_rag_service),
    router: ContextRouter = Depends(get_router),
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

        # 1. Fetch History for routing
        user_id = current_user.id if current_user else None
        await run_in_threadpool(memory_mgr.conversation_service.ensure_session_exists, db, session_id, user_id=user_id)
        history = await run_in_threadpool(memory_mgr.conversation_service.format_messages_for_llm, db, session_id)

        # 2. Determine Route
        if settings.ENABLE_CONTEXT_ROUTER:
            decision = await run_in_threadpool(router.determine_route, user_query=user_message, history=history)
        else:
            decision = RouteDecision(
                route=RouteType.RAG_AND_MEMORY,
                needs_rag=True,
                needs_memory_read=True,
                should_write_memory=True,
                confidence=1.0,
                rewritten_query=user_message,
                reason="Router disabled, defaulting to full RAG."
            )

        # 3. Read Memory if needed
        user_facts = ""
        if decision.needs_memory_read and current_user and current_user.memory_enabled:
            user_facts = await run_in_threadpool(
                memory_mgr.fact_service.retrieve_relevant_facts, 
                user_id=current_user.id, 
                query=user_message, 
                top_k=5
            )

        # 4. Generate Answer based on Route
        if decision.route == RouteType.MEMORY_WRITE and decision.confidence >= 0.8:
            result = {
                "reply": "Vâng, tôi đã ghi nhận thông tin này của bạn.",
                "model": "rule-based",
                "citations": []
            }
        elif decision.route == RouteType.CLARIFY:
            result = {
                "reply": "Bạn có thể nói rõ hơn ý của mình hoặc cung cấp thêm thông tin về địa điểm/sở thích bạn đang tìm kiếm không?",
                "model": "rule-based",
                "citations": []
            }
        else:
            # RAG, DIRECT_ANSWER, MEMORY_READ, RAG_AND_MEMORY
            result = await run_in_threadpool(
                rag_service.generate_answer,
                user_message=decision.rewritten_query if decision.needs_rag else user_message,
                top_k=4,
                conversation_history=history,
                user_facts=user_facts if decision.needs_memory_read else None,
                skip_rag_search=not decision.needs_rag
            )

        # 5. Process turn: Save message history
        await run_in_threadpool(
            memory_mgr.process_turn,
            db=db,
            session_id=session_id,
            user_message=user_message,
            assistant_reply=result["reply"],
            user=current_user,
        )

        # 6. Schedule Fact Extraction in Background Task
        if current_user and current_user.memory_enabled and settings.MEMORY_EXTRACTION_ENABLED and decision.should_write_memory:
            background_tasks.add_task(
                memory_mgr.run_fact_extraction_task,
                user_id=current_user.id,
                user_message=user_message,
                assistant_reply=result["reply"],
                session_id=session_id
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
