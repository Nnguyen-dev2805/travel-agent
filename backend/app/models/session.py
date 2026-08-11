"""SQLAlchemy model for ChatSession entity."""

from datetime import datetime, timezone
from typing import List, Optional
# pyrefly: ignore [missing-import]
from sqlalchemy import DateTime, ForeignKey, Integer, String
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChatSession(Base):
    """Chat session entity representing a conversation thread."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)  # UUID string
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="sessions")
    messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan"
    )
