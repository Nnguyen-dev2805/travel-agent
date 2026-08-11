"""SQLAlchemy model for UserMemory entity (Long-term Fact Memory)."""

from datetime import datetime, timezone
# pyrefly: ignore [missing-import]
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserMemory(Base):
    """Extracted user fact/preference bound to User ID."""

    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fact_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "preference" | "visited_place" | "budget" | "travel_style" | "dietary"
    fact_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    fact_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="memories")
