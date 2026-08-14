"""SQLAlchemy model for User entity."""

from datetime import datetime, timezone
from typing import List, Optional
# pyrefly: ignore [missing-import]
from sqlalchemy import Boolean, DateTime, Integer, String
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """User account entity for authentication and memory binding."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    sessions: Mapped[List["ChatSession"]] = relationship(
        "ChatSession", back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[List["UserMemory"]] = relationship(
        "UserMemory", back_populates="user", cascade="all, delete-orphan"
    )
