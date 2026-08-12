"""Short-term Memory Service: Manages sliding window conversation history per session."""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.app.config import settings
from backend.app.models.session import ChatSession
from backend.app.models.message import ChatMessage

logger = logging.getLogger("travel_agent_conversation_memory")


class ConversationMemoryService:
    """Manages short-term conversation context for chat sessions."""

    def ensure_session_exists(
        self, db: Session, session_id: str, user_id: Optional[int] = None
    ) -> ChatSession:
        """Ensure a ChatSession record exists in DB, creating one if missing."""
        clean_sid = session_id.strip()
        session = db.get(ChatSession, clean_sid)

        if not session:
            session = ChatSession(id=clean_sid, user_id=user_id)
            db.add(session)
            db.commit()
            db.refresh(session)
            logger.info(f"Created new ChatSession ID='{clean_sid}', UserID={user_id}")
        elif user_id and session.user_id is None:
            # Bind anonymous session to user upon login
            session.user_id = user_id
            db.commit()
            db.refresh(session)
            logger.info(f"Bound existing ChatSession ID='{clean_sid}' to UserID={user_id}")

        return session

    def add_message(
        self,
        db: Session,
        session_id: str,
        role: str,
        content: str,
        user_id: Optional[int] = None,
    ) -> ChatMessage:
        """Add a single message (user or assistant) to a chat session."""
        text_clean = content.strip()
        if not text_clean:
            raise ValueError("Message content cannot be empty.")

        if role not in ("user", "assistant"):
            raise ValueError(f"Invalid message role '{role}'. Must be 'user' or 'assistant'.")

        self.ensure_session_exists(db, session_id, user_id=user_id)
        clean_sid = session_id.strip()
        session = db.get(ChatSession, clean_sid)

        # Auto-set session title from first user message if missing
        if session and role == "user" and not session.title:
            title = text_clean[:45] + ("..." if len(text_clean) > 45 else "")
            session.title = title

        # Ensure session updated_at is refreshed on new message
        if session:
            from datetime import datetime, timezone
            session.updated_at = datetime.now(timezone.utc)
            db.commit()

        msg = ChatMessage(session_id=clean_sid, role=role, content=text_clean)
        db.add(msg)
        db.commit()
        db.refresh(msg)

        logger.debug(f"Added ChatMessage ID={msg.id} [{role}] to Session='{session_id}'")
        return msg

    def get_recent_messages(
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

    def format_messages_for_llm(
        self, db: Session, session_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """Format sliding window messages into standard OpenAI message format."""
        messages = self.get_recent_messages(db, session_id, limit=limit)
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    def get_user_sessions(self, db: Session, user_id: int) -> List[ChatSession]:
        """Fetch all chat sessions belonging to a specific User ID ordered by update time descending."""
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
        )
        return list(db.scalars(stmt).all())

    def clear_session(self, db: Session, session_id: str) -> None:
        """Clear all messages in a chat session."""
        clean_sid = session_id.strip()
        session = db.get(ChatSession, clean_sid)
        if session:
            db.delete(session)
            db.commit()
            logger.info(f"Cleared ChatSession ID='{clean_sid}'")

    def delete_session(
        self, db: Session, session_id: str, user_id: Optional[int] = None
    ) -> bool:
        """Delete a ChatSession ensuring optional user ownership validation."""
        clean_sid = session_id.strip()
        session = db.get(ChatSession, clean_sid)
        if not session:
            return False

        if user_id is not None and session.user_id != user_id:
            logger.warning(f"User ID {user_id} unauthorized to delete session {clean_sid}")
            return False

        db.delete(session)
        db.commit()
        logger.info(f"Deleted ChatSession ID='{clean_sid}' for User ID={user_id}")
        return True

