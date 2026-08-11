"""SQLAlchemy model for ChatMessage entity."""

from datetime import datetime, timezone
# pyrefly: ignore [missing-import]
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChatMessage(Base):
    """Single chat message in a conversation session."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
