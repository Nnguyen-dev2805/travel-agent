"""Integration tests for R9 authenticated cross-owner isolation.

Owner A must never read, mutate, or bind owner B resources, and denials
must not reveal whether a foreign id exists. Every test pins auth on
with a synthetic two-owner registry. No test touches a model provider,
Chroma, embeddings, or the network.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.api.conversations import get_conversation_service
from backend.app.api.memory import get_memory_service
from backend.app.api.planner import get_planner_service
from backend.app.api.workspaces import get_workspace_service
from backend.app.config import settings
from backend.app.main import app
from backend.conversations.models import ConversationCreate
from backend.conversations.service import ConversationService
from backend.conversations.sqlite_repository import SQLiteConversationRepository
from backend.app.api.chat import get_conversation_orchestrator
from backend.memory.service import MemoryService
from backend.memory.sqlite_repository import SQLiteMemoryRepository
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator
from backend.planner.service import PlannerService
from backend.planner.sqlite_repository import SQLitePlannerRepository
from backend.security.authorization import get_workspace_repository
from backend.workspaces.service import WorkspaceService
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

HEADERS_A = {"Authorization": "Bearer secret-alpha-token"}
HEADERS_B = {"Authorization": "Bearer secret-beta-token"}


@pytest.fixture(autouse=True)
def _auth_on(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    monkeypatch.setattr(
        settings,
        "LOCAL_AUTH_TOKENS_JSON",
        SecretStr('{"owner_a": "secret-alpha-token", "owner_b": "secret-beta-token"}'),
    )
    yield
    for dependency in (
        get_workspace_service,
        get_conversation_service,
        get_memory_service,
        get_planner_service,
        get_workspace_repository,
        get_conversation_orchestrator,
    ):
        app.dependency_overrides.pop(dependency, None)


def _client(db_path: Path) -> TestClient:
    app.dependency_overrides[get_workspace_service] = lambda: WorkspaceService(
        repository=SQLiteWorkspaceRepository(db_path=db_path)
    )
    app.dependency_overrides[get_conversation_service] = lambda: ConversationService(
        conversation_repository=SQLiteConversationRepository(db_path=db_path),
        workspace_repository=SQLiteWorkspaceRepository(db_path=db_path),
    )
    app.dependency_overrides[get_memory_service] = lambda: MemoryService(
        memory_repository=SQLiteMemoryRepository(db_path=db_path),
        conversation_repository=SQLiteConversationRepository(db_path=db_path),
        workspace_repository=SQLiteWorkspaceRepository(db_path=db_path),
    )
    app.dependency_overrides[get_planner_service] = lambda: PlannerService(
        planner_repository=SQLitePlannerRepository(db_path=db_path),
        workspace_repository=SQLiteWorkspaceRepository(db_path=db_path),
        conversation_repository=SQLiteConversationRepository(db_path=db_path),
    )
    app.dependency_overrides[get_workspace_repository] = lambda: (
        SQLiteWorkspaceRepository(db_path=db_path)
    )

    class _SilentRAG:
        def generate_answer(self, message, top_k=None):
            raise AssertionError("denied turns must never generate")

        def build_travel_context(self, message, top_k=None):
            raise AssertionError("denied turns must never retrieve")

        def generate_from_context(self, message, bundle):
            raise AssertionError("denied turns must never generate")

    conversation_service = ConversationService(
        SQLiteConversationRepository(db_path=db_path),
        SQLiteWorkspaceRepository(db_path=db_path),
    )
    app.dependency_overrides[get_conversation_orchestrator] = lambda: (
        ConversationOrchestrator(
            rag_service=_SilentRAG(),
            conversation_service_provider=lambda: conversation_service,
        )
    )
    return TestClient(app)


def _seed(db_path: Path):
    workspaces = SQLiteWorkspaceRepository(db_path=db_path)
    conversations = SQLiteConversationRepository(db_path=db_path)
    service = WorkspaceService(repository=workspaces)
    conversation_service = ConversationService(
        conversation_repository=conversations,
        workspace_repository=workspaces,
    )
    from backend.workspaces.models import WorkspaceCreate

    ws_a = service.create_workspace(
        WorkspaceCreate(owner_user_id="owner_a", title="A trip")
    ).workspace_id
    ws_b = service.create_workspace(
        WorkspaceCreate(owner_user_id="owner_b", title="B trip")
    ).workspace_id
    cv_b = conversation_service.create_conversation(
        ConversationCreate(workspace_id=ws_b, title=None)
    ).conversation_id
    return ws_a, ws_b, cv_b


def test_list_scopes_to_principal_and_rejects_foreign_label(tmp_path: Path):
    client = _client(tmp_path / "t.sqlite3")
    ws_a, ws_b, _ = _seed(tmp_path / "t.sqlite3")

    own = client.get(
        "/api/v1/workspaces", params={"owner_user_id": "owner_a"}, headers=HEADERS_A
    )
    assert own.status_code == 200
    assert [item["workspace_id"] for item in own.json()["workspaces"]] == [ws_a]

    foreign = client.get(
        "/api/v1/workspaces", params={"owner_user_id": "owner_b"}, headers=HEADERS_A
    )
    assert foreign.status_code == 403


def test_cross_owner_workspace_read_hides_existence(tmp_path: Path):
    client = _client(tmp_path / "t.sqlite3")
    _, ws_b, _ = _seed(tmp_path / "t.sqlite3")

    cross = client.get(f"/api/v1/workspaces/{ws_b}", headers=HEADERS_A)
    missing = client.get("/api/v1/workspaces/tw_missing", headers=HEADERS_A)

    assert cross.status_code == 404
    assert cross.json() == missing.json() == {"detail": "Workspace not found."}


def test_create_with_mismatched_body_owner_forbidden(tmp_path: Path):
    client = _client(tmp_path / "t.sqlite3")
    _seed(tmp_path / "t.sqlite3")

    response = client.post(
        "/api/v1/workspaces",
        json={"owner_user_id": "owner_b", "title": "Sneaky"},
        headers=HEADERS_A,
    )

    assert response.status_code == 403


def test_conversation_endpoints_deny_cross_owner(tmp_path: Path):
    client = _client(tmp_path / "t.sqlite3")
    _, ws_b, cv_b = _seed(tmp_path / "t.sqlite3")

    assert (
        client.post(
            f"/api/v1/workspaces/{ws_b}/conversations",
            json={},
            headers=HEADERS_A,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/workspaces/{ws_b}/conversations", headers=HEADERS_A
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/conversations/{cv_b}", headers=HEADERS_A).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/conversations/{cv_b}/messages",
            json={
                "role": "user",
                "content": "hi",
                "source": "ui",
                "trace_visibility": "included",
            },
            headers=HEADERS_A,
        ).status_code
        == 404
    )


def test_memory_endpoints_deny_cross_owner(tmp_path: Path):
    client = _client(tmp_path / "t.sqlite3")
    _, ws_b, cv_b = _seed(tmp_path / "t.sqlite3")

    assert (
        client.post(
            f"/api/v1/workspaces/{ws_b}/conversations/{cv_b}/memory/extractions",
            json={},
            headers=HEADERS_A,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/workspaces/{ws_b}/memory/promotions",
            json={},
            headers=HEADERS_A,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/workspaces/{ws_b}/memory/extractions", headers=HEADERS_A
        ).status_code
        == 404
    )


def test_planner_endpoints_deny_cross_owner(tmp_path: Path):
    client = _client(tmp_path / "t.sqlite3")
    _, ws_b, _ = _seed(tmp_path / "t.sqlite3")

    assert (
        client.post(
            f"/api/v1/workspaces/{ws_b}/planner/itineraries",
            json={"title": "Sneaky", "items": []},
            headers=HEADERS_A,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/workspaces/{ws_b}/planner/decisions", headers=HEADERS_A
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/workspaces/{ws_b}/planner/operations", headers=HEADERS_A
        ).status_code
        == 404
    )


def test_bound_chat_to_foreign_conversation_denied(tmp_path: Path):
    client = _client(tmp_path / "t.sqlite3")
    _, _, cv_b = _seed(tmp_path / "t.sqlite3")

    response = client.post(
        "/api/v1/chat",
        json={"message": "hi", "conversation_id": cv_b},
        headers=HEADERS_A,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found."}


def test_owner_b_controls_still_work(tmp_path: Path):
    client = _client(tmp_path / "t.sqlite3")
    _, ws_b, cv_b = _seed(tmp_path / "t.sqlite3")

    assert (
        client.get(f"/api/v1/workspaces/{ws_b}", headers=HEADERS_B).status_code == 200
    )
    assert (
        client.post(
            f"/api/v1/conversations/{cv_b}/messages",
            json={
                "role": "user",
                "content": "hello",
                "source": "ui",
                "trace_visibility": "included",
            },
            headers=HEADERS_B,
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/v1/workspaces/{ws_b}/planner/itineraries",
            json={"title": "B plan", "items": []},
            headers=HEADERS_B,
        ).status_code
        == 201
    )
