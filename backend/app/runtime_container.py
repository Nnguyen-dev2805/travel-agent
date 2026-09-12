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

from backend.app.config import Settings, get_settings
from backend.conversations.postgres_repository import PostgresConversationRepository
from backend.conversations.repository import ConversationRepository
from backend.conversations.service import ConversationService
from backend.storage.postgres import ALEMBIC_HEAD, assert_least_privilege_role
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

    def count_ready_outbox_events(self) -> int:
        """Count outbox events a worker could claim right now.

        Reads through `ready_outbox_event_count()`, a parameterless
        `SECURITY DEFINER` function (ADR 0028). `conversation_outbox` is
        protected by a tenant policy that this role is subject to, and the
        claim path binds no tenant, so selecting the table directly returned a
        confident zero rather than the queue depth. The function also counts
        only *released* events: under ADR 0027 an event whose turn is not
        terminal is not claimable, so counting it would overstate the queue.

        Raises when the outbox cannot be read, so the readiness probe can
        report `not_ready` instead of a constant. Bounded by a statement
        timeout so a probe cannot become a load source.
        """
        with self._engine.connect() as conn:
            conn.execute(text("SET LOCAL statement_timeout = '2s'"))
            return int(
                conn.execute(text("SELECT ready_outbox_event_count()")).scalar()
                or 0
            )

    def oldest_ready_outbox_event_age_seconds(self) -> int:
        """Age, in whole seconds, of the oldest event a worker could claim now.

        The signal that separates "busy" from "stalled". Queue *depth* cannot:
        five events drained steadily is healthy, and one event nobody has claimed
        for twenty minutes is not. Read through a parameterless `SECURITY DEFINER`
        function for the same reason the count is — `conversation_outbox` is
        protected by a tenant policy this role cannot satisfy — so it cannot
        return a row, a payload, an owner, or a count.

        Raises when the outbox cannot be read, so the readiness probe reports
        `not_ready` rather than a constant. Bounded by a statement timeout so a
        probe cannot become a load source.
        """
        with self._engine.connect() as conn:
            conn.execute(text("SET LOCAL statement_timeout = '2s'"))
            return int(
                conn.execute(
                    text("SELECT oldest_ready_outbox_event_age_seconds()")
                ).scalar()
                or 0
            )

    def dead_letter_outbox_event_count(self) -> int:
        """How many outbox events exhausted their attempts.

        Reported, not alerted on: a dead letter is a data condition an operator
        inspects, and it does not by itself mean the service cannot serve. It is
        read through a `SECURITY DEFINER` function like the other two signals.
        """
        with self._engine.connect() as conn:
            conn.execute(text("SET LOCAL statement_timeout = '2s'"))
            return int(
                conn.execute(text("SELECT dead_letter_outbox_event_count()")).scalar()
                or 0
            )

    def check_revision(self, expected_revision: str = ALEMBIC_HEAD) -> dict[str, Any]:
        """Check current Alembic revision in PostgreSQL without side effects."""
        try:
            with self._engine.connect() as conn:
                result = conn.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                )
                row = result.first()
                current_rev = str(row[0]) if row and row[0] is not None else None
            if current_rev == expected_revision:
                return {
                    "status": "ready",
                    "revision": current_rev,
                }
            return {
                "status": "unhealthy",
                "expected": expected_revision,
                "current": current_rev,
            }
        except Exception as exc:
            logger.warning("Alembic revision probe failed: %s", type(exc).__name__)
            return {
                "status": "unhealthy",
                "expected": expected_revision,
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
        """Return the one PostgreSQL DSN resolved from settings.

        Delegates to `Settings.database_dsn()` so `DATABASE_URL` is honored
        when present and stays consistent with Alembic and readiness probes.
        """
        return self._settings.database_dsn()

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
        """Initialize process-scoped resources including the PostgreSQL engine.

        Fails closed when the connected role is a superuser or bypasses
        row-level security, unless `ALLOW_PRIVILEGED_DB_ROLE` explicitly
        permits it for throwaway local development. Without this guard a
        `PG_*` fallback to the bootstrap superuser would silently nullify
        the enforced tenant policies.
        """
        logger.info("Initializing RuntimeContainer...")
        _ = self.engine
        self._assert_least_privilege_role()
        self._started = True
        logger.info("RuntimeContainer startup complete.")

    def _assert_least_privilege_role(self) -> None:
        """Reject superuser / BYPASSRLS runtime roles unless explicitly allowed.

        Delegates to the shared guard so the API runtime and the background
        worker cannot drift apart on the rule.
        """
        assert_least_privilege_role(
            self.engine,
            allowed=self._settings.ALLOW_PRIVILEGED_DB_ROLE,
            context="RuntimeContainer",
        )

    async def shutdown(self) -> None:
        """Dispose of process-scoped resources including connection pools."""
        logger.info("Disposing RuntimeContainer resources...")
        if self._engine is not None and self._owns_engine:
            self._engine.dispose()
            self._engine = None
        if self._rag_service is not None:
            self._rag_service.generator.close()
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
            from backend.rag.generation.rag_service import RAGService

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


class ContainerUnavailableError(RuntimeError):
    """No composed RuntimeContainer is bound to the application.

    Raised when a request is served without the FastAPI lifespan having run. It is
    a broken deployment, not a request to serve.
    """


def get_runtime_container(request: Request) -> RuntimeContainer:
    """Return the container the lifespan bound to `app.state`.

    **Fails closed when it is absent.** This used to construct a production
    container on demand and run the least-privilege role check on it, which made
    request processing a second composition root: a request served without the
    lifespan — a bare ASGI mount, a probe, a test — silently built its own runtime
    instead of reporting that startup had not happened.

    That was not only a design smell. The lazy path opened a *real* PostgreSQL
    connection from a unit test, so the suite's result depended on whether a
    database happened to be reachable, and on which role it granted. Application
    composition happens at startup (ADR 0035); a request that finds no container
    is a process that never composed itself.
    """
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise ContainerUnavailableError(
            "No RuntimeContainer is bound to app.state. Application composition "
            "happens in the FastAPI lifespan; this process is serving requests "
            "without it."
        )
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
