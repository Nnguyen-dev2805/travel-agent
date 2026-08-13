"""Memory Orchestrator: Coordinates Short-term and Long-term Memory for Guest vs Authenticated users."""

import logging
from typing import Any, Dict, Optional
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models.user import User
from backend.app.database import SessionLocal
from backend.memory.conversation_memory import ConversationMemoryService
from backend.memory.fact_memory import FactMemoryService

logger = logging.getLogger("travel_agent_memory_manager")


class MemoryManager:
    """Orchestrator for managing memory context and turn processing."""

    def __init__(
        self,
        conversation_service: Optional[ConversationMemoryService] = None,
        fact_service: Optional[FactMemoryService] = None,
    ) -> None:
        self.conversation_service = conversation_service or ConversationMemoryService()
        self.fact_service = fact_service or FactMemoryService()

    def build_memory_context(
        self, db: Session, session_id: str, user: Optional[User] = None, user_message: str = ""
    ) -> Dict[str, Any]:
        """Build memory context formatted for RAG LLM prompt generation.

        Returns:
            Dict containing:
            - 'conversation_history': List[Dict[str, str]] for OpenAI messages stream.
            - 'user_facts': Formatted string of long-term preferences relevant to user_message.
        """
        user_id = user.id if user else None

        # Ensure session exists in DB
        self.conversation_service.ensure_session_exists(db, session_id, user_id=user_id)

        # 1. Short-term Memory (Sliding Window history) - Available for ALL users
        history = self.conversation_service.format_messages_for_llm(db, session_id)

        # 2. Long-term Memory (Vector Retrieved Facts) - Available ONLY for Authenticated Users
        user_facts = ""
        if user and user_message:
            user_facts = self.fact_service.retrieve_relevant_facts(user_id=user.id, query=user_message, top_k=5)

        logger.debug(
            f"Built memory context for Session='{session_id}', UserID={user_id}. "
            f"HistoryMsgs={len(history)}, HasLongTermFacts={bool(user_facts)}"
        )

        return {
            "conversation_history": history,
            "user_facts": user_facts,
        }

    def process_turn(
        self,
        db: Session,
        session_id: str,
        user_message: str,
        assistant_reply: str,
        user: Optional[User] = None,
    ) -> None:
        """Process a completed conversation turn: save messages (Short-term memory)."""
        user_id = user.id if user else None

        # 1. Save turn to Short-term Conversation Memory
        self.conversation_service.add_message(
            db, session_id, role="user", content=user_message, user_id=user_id
        )
        self.conversation_service.add_message(
            db, session_id, role="assistant", content=assistant_reply, user_id=user_id
        )

    def run_fact_extraction_task(
        self,
        user_id: int,
        user_message: str,
        assistant_reply: str,
        session_id: str
    ) -> None:
        """Run fact extraction in a background task with a dedicated database session."""
        with SessionLocal() as db_session:
            try:
                self.fact_service.extract_facts(
                    db=db_session,
                    user_id=user_id,
                    user_message=user_message,
                    assistant_reply=assistant_reply,
                    session_id=session_id
                )
            except Exception as e:
                db_session.rollback()
                logger.error(f"Error extracting long-term facts for UserID={user_id}: {str(e)}")
