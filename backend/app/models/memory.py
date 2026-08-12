"""SQLAlchemy model for UserMemory entity (Long-term Fact Memory)."""

import uuid
from datetime import datetime, timezone
# pyrefly: ignore [missing-import]
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.memory.enums import MemoryType, MemoryStatus

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def generate_uuid() -> str:
    return str(uuid.uuid4())

class UserMemory(Base):
    """Extracted user fact/preference bound to User ID."""

    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    memory_id: Mapped[str] = mapped_column(String(36), default=generate_uuid, unique=True, index=True, nullable=False)
    
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    memory_type: Mapped[str] = mapped_column(String(20), default=MemoryType.SEMANTIC.value, nullable=False)
    fact_type: Mapped[str] = mapped_column(String(30), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    status: Mapped[str] = mapped_column(String(20), default=MemoryStatus.CANDIDATE.value, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    
    confirmation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    superseded_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="memories")


class MemoryOutbox(Base):
    """Transactional Outbox pattern for syncing memory to ChromaDB asynchronously."""

    __tablename__ = "memory_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    memory_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False) # 'UPSERT' or 'DELETE'
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True) # 'PENDING', 'COMPLETED', 'FAILED'
    
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
