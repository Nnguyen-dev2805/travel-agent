"""Memory Orchestrator: Coordinates Short-term, Episodic, and Long-term Memory."""

import logging
from typing import Any, Dict, Optional
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models.user import User
from backend.app.database import SessionLocal
from backend.memory.episodic_memory import EpisodicMemoryService
from backend.memory.short_term_memory import ShortTermMemoryService
from backend.memory.fact_memory import FactMemoryService

logger = logging.getLogger("travel_agent_memory_manager")


class MemoryManager:
    """Orchestrator for managing memory context and turn processing."""

    def __init__(
        self,
        episodic_service: EpisodicMemoryService,
        short_term_service: ShortTermMemoryService,
        fact_service: FactMemoryService,
    ) -> None:
        self.episodic_service = episodic_service
        self.short_term_service = short_term_service
        self.fact_service = fact_service

    def build_memory_context(
        self, db: Session, session_id: str, user: Optional[User] = None, user_message: str = ""
    ) -> Dict[str, Any]:
        """Build memory context formatted for RAG LLM prompt generation.

        Returns:
            Dict containing:
            - 'conversation_history': List[Dict[str, str]] for OpenAI messages stream (Short-term buffer).
            - 'user_facts': Formatted string of long-term preferences relevant to user_message.
            - 'recalled_episodes': Formatted string of recalled past session summaries.
        """
        user_id = user.id if user else None

        # Ensure session exists in DB
        self.episodic_service.ensure_session_exists(db, session_id, user_id=user_id)

        # 1. Short-term Memory (Sliding Window history)
        recent_msgs = self.short_term_service.get_sliding_window(db, session_id)
        history = self.short_term_service.format_messages_for_llm(recent_msgs)

        # 2. Long-term Memory (Vector Retrieved Facts & Episodes) - Available ONLY for Authenticated Users
        user_facts = ""
        recalled_episodes = ""
        if user and user_message:
            user_facts = self.fact_service.retrieve_relevant_facts(user_id=user.id, query=user_message, top_k=5)
            recalled_episodes = self.episodic_service.recall_past_episodes(user_id=user.id, current_query=user_message, top_k=2)

        logger.debug(
            f"Built memory context for Session='{session_id}', UserID={user_id}. "
            f"HistoryMsgs={len(history)}, HasFacts={bool(user_facts)}, HasEpisodes={bool(recalled_episodes)}"
        )

        # We will append recalled_episodes to user_facts for simplicity in prompt injection
        if recalled_episodes:
            user_facts = f"{user_facts}\n\n{recalled_episodes}" if user_facts else recalled_episodes

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
        """Process a completed conversation turn: save messages (Episodic memory)."""
        user_id = user.id if user else None

        # 1. Save turn to Episodic Memory (SQL Database)
        self.episodic_service.add_message(
            db, session_id, role="user", content=user_message, user_id=user_id
        )
        self.episodic_service.add_message(
            db, session_id, role="assistant", content=assistant_reply, user_id=user_id
        )
        
        # Commit the transaction for both messages and any session updates
        db.commit()

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

    def run_consolidation_task(self, session_id: str) -> None:
        """Run episodic session consolidation in a background task."""
        with SessionLocal() as db_session:
            try:
                self.episodic_service.consolidate_session(db=db_session, session_id=session_id)
            except Exception as e:
                db_session.rollback()
                logger.error(f"Error consolidating episodic memory for Session={session_id}: {str(e)}")
