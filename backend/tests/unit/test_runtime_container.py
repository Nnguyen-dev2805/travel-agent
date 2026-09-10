"""Unit tests for the RuntimeContainer process-scoped composition root."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.app.config import Settings, get_settings
from backend.app.runtime_container import (
    PostgresReadinessProbe,
    RuntimeContainer,
    get_conversation_orchestrator,
    get_conversation_repository,
    get_conversation_service,
    get_readiness_probe,
    get_runtime_container,
)
from backend.conversations.postgres_repository import PostgresConversationRepository
from backend.conversations.service import ConversationService
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@pytest.fixture
def mock_engine():
    """Create a mock SQLAlchemy engine for testing."""
    engine = MagicMock(spec=Engine)
    return engine


@pytest.fixture
def container(mock_engine):
    """RuntimeContainer with mock engine and stub RAG service."""
    return RuntimeContainer(
        settings=get_settings(),
        engine=mock_engine,
        rag_service=SimpleNamespace(),
    )


def test_container_init_default_settings():
    container = RuntimeContainer()
    assert container._settings is get_settings()
    assert container._started is False


@pytest.mark.anyio
async def test_container_lifecycle_startup_and_shutdown(mock_engine):
    container = RuntimeContainer(engine=mock_engine)
    assert container._started is False

    await container.startup()
    assert container._started is True

    await container.shutdown()
    assert container._started is False


@pytest.mark.anyio
async def test_container_owns_and_disposes_engine():
    test_settings = Settings(
        PG_HOST="localhost",
        PG_PORT=5433,
        PG_DB="test_db",
        PG_USER="test_user",
    )
    container = RuntimeContainer(settings=test_settings)
    assert container._owns_engine is True

    with patch("backend.app.runtime_container.create_engine") as mock_create_engine:
        mock_created = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_created

        await container.startup()
        assert container.engine is mock_created
        mock_create_engine.assert_called_once()

        await container.shutdown()
        mock_created.dispose.assert_called_once()
        assert container._engine is None


def test_conversation_repo_returns_postgres_repository(container, mock_engine):
    repo = container.conversation_repo()
    assert isinstance(repo, PostgresConversationRepository)
    assert repo._engine is mock_engine
    # Memoized
    assert container.conversation_repo() is repo


def test_conversation_service_returns_wired_service(container):
    service = container.conversation_service()
    assert isinstance(service, ConversationService)
    assert service._conversations is container.conversation_repo()
    # Memoized
    assert container.conversation_service() is service


def test_conversation_orchestrator_returns_orchestrator(container):
    stub_rag = SimpleNamespace(generate=lambda *a, **kw: None)
    orchestrator = container.conversation_orchestrator(
        outbox_enabled=True,
        rag_service=stub_rag,
    )
    assert isinstance(orchestrator, ConversationOrchestrator)
    assert orchestrator._rag_service is stub_rag
    assert orchestrator._outbox_enabled is True


def test_readiness_probe_returns_probe_instance(container, mock_engine):
    probe = container.readiness_probe()
    assert isinstance(probe, PostgresReadinessProbe)
    assert probe._engine is mock_engine
    assert container.readiness_probe() is probe


def test_readiness_probe_healthy(mock_engine):
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    probe = PostgresReadinessProbe(mock_engine)
    result = probe.check()

    assert result["status"] == "ready"
    assert result["database"] == "postgresql"
    assert probe() == result


def test_readiness_probe_unhealthy_handles_exception(mock_engine):
    mock_engine.connect.side_effect = RuntimeError("database unavailable")

    probe = PostgresReadinessProbe(mock_engine)
    result = probe.check()

    assert result["status"] == "unhealthy"
    assert result["database"] == "postgresql"
    assert result["error"] == "RuntimeError"


def test_no_sqlite_or_workspace_planner_imports():
    """Verify AST of runtime_container.py does not import SQLite, workspaces, or planner."""
    source_path = ROOT_DIR / "backend" / "app" / "runtime_container.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    forbidden = (
        "sqlite3",
        "schema_registry",
        "SQLiteConversationRepository",
        "SQLiteWorkspaceRepository",
        "workspaces",
        "planner",
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for bad in forbidden:
                    assert bad not in alias.name, f"Forbidden import found: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for bad in forbidden:
                    assert bad not in node.module, f"Forbidden import found: {node.module}"
            for alias in node.names:
                for bad in forbidden:
                    assert bad not in alias.name, f"Forbidden symbol found: {alias.name}"


def test_fastapi_dependency_helpers(container):
    app_state = SimpleNamespace(container=container)
    mock_request = SimpleNamespace(app=SimpleNamespace(state=app_state))

    assert get_runtime_container(mock_request) is container
    assert get_conversation_repository(container) is container.conversation_repo()
    assert get_conversation_service(container) is container.conversation_service()
    assert get_readiness_probe(container) is container.readiness_probe()

    stub_rag = SimpleNamespace()
    container._rag_service = stub_rag
    orchestrator = get_conversation_orchestrator(container)
    assert isinstance(orchestrator, ConversationOrchestrator)


def test_fastapi_dependency_helper_fallback_creates_container():
    app_state = SimpleNamespace()
    mock_request = SimpleNamespace(app=SimpleNamespace(state=app_state))

    retrieved = get_runtime_container(mock_request)
    assert isinstance(retrieved, RuntimeContainer)
    assert app_state.container is retrieved
