"""Integration tests for R9 workspace deletion routes and tombstones.

Every test runs against an isolated temporary SQLite database with real
adapters. Deleted state must hide from product reads and writes while
staying visible to coordination. No test touches a model provider,
Chroma, embeddings, or the network.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.api.chat import get_conversation_orchestrator
from backend.app.api.conversations import get_conversation_service
from backend.app.api.memory import get_memory_service
from backend.app.api.planner import get_planner_service
from backend.app.api.workspaces import get_deletion_service, get_workspace_service
from backend.security.authorization import get_workspace_repository
from backend.app.config import settings
from backend.app.main import app
from backend.conversations.models import (
    ConversationCreate,
    MessageRole,
    MessageSource,
    TraceVisibility,
)
from backend.conversations.service import ConversationService
from backend.conversations.sqlite_repository import SQLiteConversationRepository
from backend.memory.service import MemoryService
from backend.memory.sqlite_repository import SQLiteMemoryRepository
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator
from backend.planner.service import PlannerService
from backend.planner.sqlite_repository import SQLitePlannerRepository
from backend.privacy.deletion import DeletionService
from backend.workspaces.service import WorkspaceService
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

HEADERS = {"Authorization": "Bearer secret-alpha-token"}
HEADERS_B = {"Authorization": "Bearer secret-beta-token"}
MOMENT_TITLE = "Da Nang family trip"


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
        get_deletion_service,
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
    app.dependency_overrides[get_deletion_service] = lambda: DeletionService(
        workspace_repository=SQLiteWorkspaceRepository(db_path=db_path),
        conversation_repository=SQLiteConversationRepository(db_path=db_path),
        memory_repository=SQLiteMemoryRepository(db_path=db_path),
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


def _workspace_id(client: TestClient) -> str:
    response = client.post(
        "/api/v1/workspaces",
        json={"owner_user_id": "owner_a", "title": MOMENT_TITLE},
        headers=HEADERS,
    )
    assert response.status_code == 201
    return response.json()["workspace_id"]


def _conversation_id(client: TestClient, workspace_id: str) -> str:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations",
        json={},
        headers=HEADERS,
    )
    assert response.status_code == 201
    return response.json()["conversation_id"]


def test_owner_can_request_then_confirm_deletion(tmp_path: Path):
    db_path = tmp_path / "t.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(client)
    _conversation_id(client, workspace_id)

    requested = client.post(
        f"/api/v1/workspaces/{workspace_id}/deletion-requests",
        json={},
        headers=HEADERS,
    )
    assert requested.status_code == 201
    assert requested.json()["workspace_state"] == "deletion_requested"

    # Requested state already denies normal access.
    assert (
        client.get(f"/api/v1/workspaces/{workspace_id}", headers=HEADERS).status_code
        == 404
    )

    confirmed = client.post(
        f"/api/v1/workspaces/{workspace_id}/deletion-confirmations",
        json={},
        headers=HEADERS,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["workspace_state"] == "deleted"
    assert (
        client.get(f"/api/v1/workspaces/{workspace_id}", headers=HEADERS).status_code
        == 404
    )
    listed = client.get(
        "/api/v1/workspaces", params={"owner_user_id": "owner_a"}, headers=HEADERS
    ).json()
    assert listed["workspaces"] == []


def test_other_owner_cannot_request_deletion(tmp_path: Path):
    db_path = tmp_path / "t.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(client)

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/deletion-requests",
        json={},
        headers=HEADERS_B,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Workspace not found."}


def test_confirm_without_request_conflicts(tmp_path: Path):
    db_path = tmp_path / "t.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(client)

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/deletion-confirmations",
        json={},
        headers=HEADERS,
    )

    assert response.status_code == 409


def test_deleted_workspace_rejects_new_writes(tmp_path: Path):
    db_path = tmp_path / "t.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(client)
    conversation_id = _conversation_id(client, workspace_id)
    client.post(
        f"/api/v1/workspaces/{workspace_id}/deletion-requests",
        json={},
        headers=HEADERS,
    )
    client.post(
        f"/api/v1/workspaces/{workspace_id}/deletion-confirmations",
        json={},
        headers=HEADERS,
    )

    assert (
        client.post(
            f"/api/v1/workspaces/{workspace_id}/conversations",
            json={},
            headers=HEADERS,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/memory/extractions",
            json={},
            headers=HEADERS,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/workspaces/{workspace_id}/memory/promotions",
            json={},
            headers=HEADERS,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/workspaces/{workspace_id}/planner/itineraries",
            json={"title": "Sneaky", "items": []},
            headers=HEADERS,
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/chat",
            json={"message": "hi", "conversation_id": conversation_id},
            headers=HEADERS,
        ).status_code
        == 404
    )


def test_deleted_memory_not_selected_for_bound_chat(tmp_path: Path):
    db_path = tmp_path / "t.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(client)
    conversation_id = _conversation_id(client, workspace_id)
    conversations = SQLiteConversationRepository(db_path=db_path)
    workspaces = SQLiteWorkspaceRepository(db_path=db_path)
    conversation_service = ConversationService(conversations, workspaces)
    conversation_service.append_message(
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content="Tôi ăn chay trường, hãy nhớ giúp tôi.",
        source=MessageSource.UI,
        trace_visibility=TraceVisibility.INCLUDED,
    )
    memory = MemoryService(
        SQLiteMemoryRepository(db_path=db_path), conversations, workspaces
    )

    memory.run_conversation_extraction(workspace_id, conversation_id, "manual")
    promoted = memory.promote_workspace(workspace_id, conversation_id)
    assert promoted.promoted_count == 1

    client.post(
        f"/api/v1/workspaces/{workspace_id}/deletion-requests",
        json={},
        headers=HEADERS,
    )
    client.post(
        f"/api/v1/workspaces/{workspace_id}/deletion-confirmations",
        json={},
        headers=HEADERS,
    )

    remaining = SQLiteMemoryRepository(db_path=db_path).list_records(
        workspace_id=workspace_id
    )
    assert remaining, "expected tombstoned rows to remain for audit"
    assert {item.status.value for item in remaining} == {"deleted"}
