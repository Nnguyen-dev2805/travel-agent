"""Process-scoped composition root for application runtime.

Owns PostgreSQL engine and connection pool creation and disposal.
Provides single-source access to domain adapters and orchestrators without
SQLite, workspace, or planner dependencies.

Per ADR 0018 and ADR 0021, this container is the sole composition root
for the clean-break authenticated chat service.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import Depends, Request
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from backend.app.config import Settings, get_settings, pg_dsn
from backend.conversations.postgres_repository import PostgresConversationRepository
from backend.conversations.repository import ConversationRepository
from backend.conversations.service import ConversationService
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator

logger = logging.getLogger("travel_agent_runtime")


class PostgresReadinessProbe:
    """Check connectivity and operational readiness of PostgreSQL."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def check(self) -> dict[str, Any]:
        """Execute a connectivity probe query against PostgreSQL.

        Returns a dictionary safe for readiness responses, disclosing no credentials.
        """
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {
                "status": "ready",
                "database": "postgresql",
            }
        except Exception as exc:
            logger.warning("PostgreSQL readiness probe failed: %s", type(exc).__name__)
            return {
                "status": "unhealthy",
                "database": "postgresql",
                "error": type(exc).__name__,
            }

    def __call__(self) -> dict[str, Any]:
        return self.check()


class RuntimeContainer:
    """Process-scoped composition root.

    Owns PostgreSQL engine/pool creation and adapter construction.
    Accepts explicit settings and optional pre-built engine or rag_service for testing.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        engine: Optional[Engine] = None,
        rag_service: Any = None,
    ) -> None:
        self._settings = settings if settings is not None else get_settings()
        self._engine: Optional[Engine] = engine
        self._owns_engine: bool = engine is None
        self._rag_service: Any = rag_service
        self._conversation_repo: Optional[PostgresConversationRepository] = None
        self._conversation_service: Optional[ConversationService] = None
        self._readiness_probe: Optional[PostgresReadinessProbe] = None
        self._started: bool = False

    @property
    def _dsn(self) -> str:
        password = (
            self._settings.PG_PASSWORD.get_secret_value()
            if hasattr(self._settings.PG_PASSWORD, "get_secret_value")
            else str(self._settings.PG_PASSWORD)
        )
        return pg_dsn(
            password=password,
            host=self._settings.PG_HOST,
            port=self._settings.PG_PORT,
            db=self._settings.PG_DB,
            user=self._settings.PG_USER,
        )

    @property
    def engine(self) -> Engine:
        """Return the active PostgreSQL Engine, lazily creating it if needed."""
        if self._engine is None:
            self._engine = create_engine(
                self._dsn,
                pool_pre_ping=True,
            )
            self._owns_engine = True
        return self._engine

    async def startup(self) -> None:
        """Initialize process-scoped resources including the PostgreSQL engine."""
        logger.info("Initializing RuntimeContainer...")
        _ = self.engine
        self._started = True
        logger.info("RuntimeContainer startup complete.")

    async def shutdown(self) -> None:
        """Dispose of process-scoped resources including connection pools."""
        logger.info("Disposing RuntimeContainer resources...")
        if self._engine is not None and self._owns_engine:
            self._engine.dispose()
            self._engine = None
        self._started = False
        logger.info("RuntimeContainer shutdown complete.")

    def conversation_repo(self) -> PostgresConversationRepository:
        """Return the PostgreSQL conversation repository."""
        if self._conversation_repo is None:
            self._conversation_repo = PostgresConversationRepository(self.engine)
        return self._conversation_repo

    def conversation_service(self) -> ConversationService:
        """Return the standalone conversation service."""
        if self._conversation_service is None:
            self._conversation_service = ConversationService(
                conversation_repository=self.conversation_repo()
            )
        return self._conversation_service

    def rag_service(self) -> Any:
        """Return the RAG service instance."""
        if self._rag_service is None:
            from backend.rag.generation import RAGService
            self._rag_service = RAGService()
        return self._rag_service

    def conversation_orchestrator(
        self,
        outbox_enabled: bool | None = None,
        rag_service: Any = None,
    ) -> ConversationOrchestrator:
        """Return the conversation orchestrator for chat turns."""
        resolved_outbox = (
            self._settings.MEMORY_SHADOW_EXTRACT_ENABLED
            if outbox_enabled is None
            else outbox_enabled
        )
        resolved_rag = rag_service if rag_service is not None else self.rag_service()
        return ConversationOrchestrator(
            rag_service=resolved_rag,
            conversation_service_provider=self.conversation_service,
            outbox_enabled=resolved_outbox,
        )

    def readiness_probe(self) -> PostgresReadinessProbe:
        """Return the PostgreSQL readiness probe."""
        if self._readiness_probe is None:
            self._readiness_probe = PostgresReadinessProbe(self.engine)
        return self._readiness_probe


def get_runtime_container(request: Request) -> RuntimeContainer:
    """FastAPI dependency to retrieve the active RuntimeContainer from app state."""
    container = getattr(request.app.state, "container", None)
    if container is None:
        container = RuntimeContainer()
        request.app.state.container = container
    return container


def get_conversation_repository(
    container: RuntimeContainer = Depends(get_runtime_container),
) -> ConversationRepository:
    """FastAPI dependency for ConversationRepository."""
    return container.conversation_repo()


def get_conversation_service(
    container: RuntimeContainer = Depends(get_runtime_container),
) -> ConversationService:
    """FastAPI dependency for ConversationService."""
    return container.conversation_service()


def get_conversation_orchestrator(
    container: RuntimeContainer = Depends(get_runtime_container),
) -> ConversationOrchestrator:
    """FastAPI dependency for ConversationOrchestrator."""
    return container.conversation_orchestrator()


def get_readiness_probe(
    container: RuntimeContainer = Depends(get_runtime_container),
) -> PostgresReadinessProbe:
    """FastAPI dependency for PostgresReadinessProbe."""
    return container.readiness_probe()
