"""Database model for storing full document text for Parent-Child Retrieval."""

from typing import Dict, Any
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class TravelDocument(Base):
    """Stores the full content of a travel document to be retrieved by parent_id."""
    __tablename__ = "travel_documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    def __repr__(self) -> str:
        return f"<TravelDocument(id={self.id}, title={self.title})>"
