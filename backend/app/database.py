"""Database infrastructure setup using SQLAlchemy ORM."""

import logging
from typing import Generator
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.config import settings

logger = logging.getLogger("travel_agent_database")

# Create SQLAlchemy engine with connection pool
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Session factory for DB interactions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative Base for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency injection for FastAPI routes to yield DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
