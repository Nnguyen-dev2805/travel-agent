"""Short-term Memory Service: Manages sliding window conversation history."""

import logging
from typing import Dict, List, Optional
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
# pyrefly: ignore [missing-import]
from sqlalchemy import select

from backend.app.config import settings
from backend.app.models.message import ChatMessage

logger = logging.getLogger("travel_agent_short_term_memory")


class ShortTermMemoryService:
    """Manages short-term conversation context for chat sessions."""

    def get_sliding_window(
        self, db: Session, session_id: str, limit: Optional[int] = None
    ) -> List[ChatMessage]:
        """Fetch N recent messages for sliding window context (ordered by creation time ascending)."""
        window_limit = limit if limit is not None else settings.MEMORY_WINDOW_SIZE
        if window_limit <= 0:
            return []

        clean_sid = session_id.strip()

        # Fetch recent messages ordered by created_at DESC to get the latest N
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == clean_sid)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(window_limit)
        )

        recent_desc = list(db.scalars(stmt).all())

        # Reverse back to ascending order for LLM context stream
        recent_asc = list(reversed(recent_desc))
        return recent_asc

    def format_messages_for_llm(self, messages: List[ChatMessage]) -> List[Dict[str, str]]:
        """Format sliding window messages into standard OpenAI message format."""
        return [{"role": msg.role, "content": msg.content} for msg in messages]
