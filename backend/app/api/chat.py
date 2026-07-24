import logging
from fastapi import APIRouter, HTTPException
from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.rag.generation import RAGService

logger = logging.getLogger("travel_agent_backend")
router = APIRouter()

# Global RAG service instance
_rag_service = None

def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service

@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """Chat endpoint receiving prompt and returning RAG-generated response with citations."""
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")
    
    logger.info(f"Received chat request: '{user_message[:50]}...'")

    try:
        rag_service = get_rag_service()
        result = rag_service.generate_answer(user_message, top_k=4)
        
        return ChatResponse(
            reply=result["reply"],
            model=result["model"],
            citations=result["citations"],
        )

    except ValueError as ve:
        logger.error(f"Validation error in RAG Chat: {str(ve)}")
        raise HTTPException(status_code=500, detail=str(ve))
    except Exception as e:
        logger.error(f"Error executing RAG Chat Endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"LLM RAG Service Error: {str(e)}")
