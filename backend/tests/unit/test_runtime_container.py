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
    ContainerUnavailableError,
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


def _role_flag_engine(elevated: bool) -> MagicMock:
    """Engine whose role check returns a concrete True/False flag."""
    engine = MagicMock(spec=Engine)
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar.return_value = elevated
    return engine


@pytest.mark.anyio
async def test_startup_rejects_privileged_role_by_default():
    container = RuntimeContainer(
        settings=Settings(ALLOW_PRIVILEGED_DB_ROLE=False),
        engine=_role_flag_engine(True),
    )
    with pytest.raises(RuntimeError, match="superuser|row-level security"):
        await container.startup()
    assert container._started is False


@pytest.mark.anyio
async def test_startup_allows_privileged_role_with_explicit_opt_in():
    container = RuntimeContainer(
        settings=Settings(ALLOW_PRIVILEGED_DB_ROLE=True),
        engine=_role_flag_engine(True),
    )
    await container.startup()
    assert container._started is True


@pytest.mark.anyio
async def test_startup_accepts_least_privilege_role():
    container = RuntimeContainer(
        settings=Settings(ALLOW_PRIVILEGED_DB_ROLE=False),
        engine=_role_flag_engine(False),
    )
    await container.startup()
    assert container._started is True


@pytest.mark.anyio
async def test_startup_propagates_role_check_failure():
    """A role lookup failure must surface, never pass silently."""
    engine = MagicMock(spec=Engine)
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.side_effect = RuntimeError("connection lost")
    container = RuntimeContainer(
        settings=Settings(ALLOW_PRIVILEGED_DB_ROLE=False),
        engine=engine,
    )
    with pytest.raises(RuntimeError, match="connection lost"):
        await container.startup()
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
                    assert bad not in alias.name, (
                        f"Forbidden import found: {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for bad in forbidden:
                    assert bad not in node.module, (
                        f"Forbidden import found: {node.module}"
                    )
            for alias in node.names:
                for bad in forbidden:
                    assert bad not in alias.name, (
                        f"Forbidden symbol found: {alias.name}"
                    )


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


def test_the_dependency_fails_closed_without_a_composed_container():
    """The defect: this used to build a production container on demand.

    That made request processing a second composition root, and it made this very
    test open a real PostgreSQL connection — so the suite's result depended on
    whether a database happened to be reachable. Application composition happens
    in the lifespan; a request that finds no container is a broken deployment.
    """
    app_state = SimpleNamespace()
    mock_request = SimpleNamespace(app=SimpleNamespace(state=app_state))

    with pytest.raises(ContainerUnavailableError):
        get_runtime_container(mock_request)

    assert getattr(app_state, "container", None) is None, (
        "the dependency must not bind a container it did not compose"
    )


# --- ADR 0028: the least-privilege guard is shared, not container-local -------


def test_shared_guard_rejects_an_elevated_role():
    from backend.storage.postgres import (
        PrivilegedRoleError,
        assert_least_privilege_role,
    )

    with pytest.raises(PrivilegedRoleError, match="superuser|row-level security"):
        assert_least_privilege_role(
            _role_flag_engine(True), allowed=False, context="test"
        )


def test_shared_guard_accepts_a_least_privilege_role():
    from backend.storage.postgres import assert_least_privilege_role

    assert_least_privilege_role(
        _role_flag_engine(False), allowed=False, context="test"
    )


def test_shared_guard_honours_the_explicit_opt_in():
    from backend.storage.postgres import assert_least_privilege_role

    # No exception even though the role is elevated: the flag is the escape hatch.
    assert_least_privilege_role(
        _role_flag_engine(True), allowed=True, context="test"
    )


def test_the_container_delegates_to_the_shared_guard():
    """The worker will call the same guard, so the rule must live in one place."""
    source = (
        ROOT_DIR / "backend" / "app" / "runtime_container.py"
    ).read_text(encoding="utf-8")
    assert "assert_least_privilege_role" in source, (
        "the container must delegate rather than reimplement the rule"
    )
    assert "rolsuper OR rolbypassrls" not in source, (
        "the raw role query belongs in backend.storage.postgres only"
    )


# --- there is no lazy composition path any more --------------------------------


def test_a_request_never_composes_a_container(monkeypatch):
    """`RuntimeContainer` must be unreachable from a request.

    The old lazy path constructed a container and then ran the role check on it,
    which is why a unit test reached the database. Now the dependency either
    returns what the lifespan bound or refuses, so construction must not be
    reachable from a request at all — asserted by making construction explode
    rather than by inspecting the source.
    """
    from backend.app import runtime_container as module

    def _explode(*_args, **_kwargs):
        raise AssertionError(
            "a request composed a RuntimeContainer; composition belongs to the lifespan"
        )

    monkeypatch.setattr(module, "RuntimeContainer", _explode)

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(ContainerUnavailableError):
        module.get_runtime_container(request)


def test_started_container_does_not_rerun_the_guard(monkeypatch):
    from backend.app import runtime_container as module

    checked: list = []
    monkeypatch.setattr(
        module.RuntimeContainer,
        "_assert_least_privilege_role",
        lambda self: checked.append(self),
    )

    started = module.RuntimeContainer(engine=MagicMock(spec=Engine))
    started._started = True
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(container=started))
    )

    assert module.get_runtime_container(request) is started
    assert checked == [], "an already-started container is not re-checked"
