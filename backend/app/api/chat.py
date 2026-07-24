import logging
from fastapi import APIRouter, HTTPException
from openai import OpenAI
from backend.app.config import settings
from backend.app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger("travel_agent_backend")
router = APIRouter()

def get_openai_client() -> OpenAI:
    if not settings.GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN not found in environment variables.")
        raise HTTPException(status_code=500, detail="GITHUB_TOKEN is missing in server environment.")
    
    return OpenAI(
        base_url=settings.GITHUB_MODELS_URL,
        api_key=settings.GITHUB_TOKEN,
    )

@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """Chat endpoint receiving prompt and returning LLM generated response."""
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")
    
    model_name = settings.LLM_MODEL
    logger.info(f"Received chat request: '{user_message[:50]}...'")

    try:
        client = get_openai_client()
        system_prompt = (
            "Bạn là trợ lý AI thông minh chuyên về du lịch Việt Nam. "
            "Hãy trả lời ngắn gọn, thân thiện và hữu ích bằng Tiếng Việt."
        )
        
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=800,
        )
        
        reply_content = completion.choices[0].message.content
        logger.info("Successfully received LLM response.")
        return ChatResponse(reply=reply_content, model=model_name)

    except Exception as e:
        logger.error(f"Error calling LLM API: {str(e)}")
        raise HTTPException(status_code=500, detail=f"LLM Service Error: {str(e)}")
