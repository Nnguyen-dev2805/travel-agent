"""Episodic Memory Service: Manages raw chat logs and hierarchical summarization in ChromaDB."""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone
import uuid

# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
# pyrefly: ignore [missing-import]
from sqlalchemy import select
# pyrefly: ignore [missing-import]
from openai import OpenAI

from backend.app.config import settings
from backend.app.models.session import ChatSession
from backend.app.models.message import ChatMessage
from backend.rag.embedding.embedder import VectorEmbedder
from backend.rag.retrieval.vector_store import ChromaVectorStore

logger = logging.getLogger("travel_agent_episodic_memory")


class EpisodicMemoryService:
    """Manages long-term conversational memory (Episodic) using SQL + ChromaDB."""

    def __init__(
        self,
        llm_client: OpenAI,
        vector_store: ChromaVectorStore,
        embedder: VectorEmbedder,
    ):
        self.llm_client = llm_client
        self.vector_store = vector_store
        self.embedder = embedder

    # --- SQL RAW STORAGE METHODS ---

    def ensure_session_exists(
        self, db: Session, session_id: str, user_id: Optional[int] = None
    ) -> ChatSession:
        """Ensure a ChatSession record exists in DB, creating one if missing."""
        clean_sid = session_id.strip()
        session = db.get(ChatSession, clean_sid)

        if not session:
            session = ChatSession(id=clean_sid, user_id=user_id)
            db.add(session)
            db.flush()
            logger.info(f"Created new ChatSession ID='{clean_sid}', UserID={user_id}")
        elif user_id and session.user_id is None:
            # Bind anonymous session to user upon login
            session.user_id = user_id
            db.flush()
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
        """Add a single raw message (user or assistant) to a chat session."""
        text_clean = content.strip()
        if not text_clean:
            raise ValueError("Message content cannot be empty.")

        if role not in ("user", "assistant"):
            raise ValueError(f"Invalid message role '{role}'. Must be 'user' or 'assistant'.")

        session = self.ensure_session_exists(db, session_id, user_id=user_id)
        clean_sid = session_id.strip()

        # Auto-set session title from first user message if missing
        if session and role == "user" and not session.title:
            title = text_clean[:45] + ("..." if len(text_clean) > 45 else "")
            session.title = title

        # Ensure session updated_at is refreshed on new message
        if session:
            session.updated_at = datetime.now(timezone.utc)
            db.flush()

        msg = ChatMessage(session_id=clean_sid, role=role, content=text_clean)
        db.add(msg)
        db.flush()

        logger.debug(f"Added ChatMessage ID={msg.id} [{role}] to Session='{session_id}'")
        return msg

    def get_session_messages(self, db: Session, session_id: str) -> List[ChatMessage]:
        """Fetch all messages for a given session ordered by creation time."""
        clean_sid = session_id.strip()
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == clean_sid)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
        return list(db.scalars(stmt).all())

    def get_user_sessions(self, db: Session, user_id: int) -> List[ChatSession]:
        """Fetch all chat sessions belonging to a specific User ID."""
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

    # --- CHROMA DB SUMMARIZATION & RETRIEVAL METHODS ---

    def consolidate_session(self, db: Session, session_id: str) -> None:
        """Background task to summarize a session and store in ChromaDB."""
        messages = self.get_session_messages(db, session_id)
        if len(messages) < 10:
            logger.info(f"Session {session_id} has < 10 messages. Skipping consolidation.")
            return

        session = db.get(ChatSession, session_id)
        if not session or not session.user_id:
            return

        # Prepare chat log for LLM
        chat_log = ""
        for msg in messages:
            chat_log += f"{msg.role.upper()}: {msg.content}\n"

        prompt = f"""Summarize the following travel planning conversation into a concise narrative. 
Focus on what the user wants, their constraints (budget, allergies), and decisions made.
Do not include conversational filler. Keep it under 3-4 sentences.

Conversation:
{chat_log}"""

        logger.info(f"\n{'='*20} EPISODIC SUMMARY PROMPT {'='*20}\n{prompt}\n{'='*65}")

        try:
            response = self.llm_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=200,
            )
            summary = response.choices[0].message.content
            logger.info(f"\n{'='*20} EPISODIC SUMMARY OUTPUT {'='*20}\n{summary}\n{'='*65}")

            if not summary:
                return

            logger.info(f"Consolidated session {session_id}: {summary}")

            # Embed and store
            embedding = self.embedder.embed_query(summary)
            if not embedding:
                return

            memory_id = f"ep_{session_id}"
            metadata = {
                "user_id": session.user_id,
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "episodic_summary"
            }

            self.vector_store.upsert_user_memory(
                memory_id=memory_id,
                content=summary,
                metadata=metadata,
                embedding=embedding
            )

        except Exception as e:
            logger.error(f"Error consolidating session {session_id}: {e}", exc_info=True)

    def recall_past_episodes(self, user_id: int, current_query: str, top_k: int = 2) -> str:
        """Retrieve relevant past episode summaries for a user based on the current query."""
        embedding = self.embedder.embed_query(current_query)
        if not embedding:
            return ""

        results = self.vector_store.search_similar(
            query_embedding=embedding,
            top_k=top_k,
            where={"user_id": user_id}
        )

        if not results:
            return ""

        recalled_texts = []
        for res in results:
            if res["score"] > 0.6:  # Relevance threshold
                recalled_texts.append(res["text"])

        if recalled_texts:
            return " === HỒI TƯỞNG CÁC PHIÊN CHAT CŨ ===\n" + "\n".join(recalled_texts)
        return ""
