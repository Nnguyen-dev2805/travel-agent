"""Integration tests for the R6 promotion route.

Every test overrides the memory service dependency with repositories over an
isolated temporary SQLite database, so no test reads or writes the developer
database at `APP_DB_PATH`. No test constructs a RAG service, an embedding
model, a Chroma collection, or a model-provider client.

Fixture text is synthetic Vietnamese travel content and carries no secret.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.memory import get_memory_service
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
from backend.workspaces.models import (
    PlanningStatus,
    RetentionState,
    TripWorkspace,
    generate_workspace_id,
)
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

MOMENT = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
PREFERENCE_TEXT = "Tôi ăn chay trường, hãy nhớ giúp tôi."


def _client(db_path: Path):
    """Client bound to a throwaway database without the lifespan RAG warm-up."""
    memory = SQLiteMemoryRepository(db_path=db_path)
    conversations = SQLiteConversationRepository(db_path=db_path)
    workspaces = SQLiteWorkspaceRepository(db_path=db_path)
    service = MemoryService(
        memory_repository=memory,
        conversation_repository=conversations,
        workspace_repository=workspaces,
    )
    app.dependency_overrides[get_memory_service] = lambda: service
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_memory_service, None)


def _workspace_id(db_path: Path) -> str:
    return (
        SQLiteWorkspaceRepository(db_path=db_path)
        .create(
            TripWorkspace(
                workspace_id=generate_workspace_id(),
                owner_user_id="local-user",
                title="Da Nang family trip",
                destination_scope=None,
                date_window=None,
                planning_status=PlanningStatus.IDEA,
                created_at=MOMENT,
                updated_at=MOMENT,
                retention_state=RetentionState.ACTIVE,
            )
        )
        .workspace_id
    )


def _seed(db_path: Path, workspace_id: str, *contents) -> str:
    conversations = SQLiteConversationRepository(db_path=db_path)
    workspaces = SQLiteWorkspaceRepository(db_path=db_path)
    service = ConversationService(conversations, workspaces)
    conversation = service.create_conversation(
        ConversationCreate(workspace_id=workspace_id, title=None)
    )
    for content in contents:
        service.append_message(
            conversation_id=conversation.conversation_id,
            role=MessageRole.USER,
            content=content,
            source=MessageSource.UI,
            trace_visibility=TraceVisibility.INCLUDED,
        )
    return conversation.conversation_id


def _extract(client: TestClient, workspace_id: str, conversation_id: str):
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations/"
        f"{conversation_id}/memory/extractions",
        json={},
    )


def test_promotion_run_returns_201_with_counts(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(db_path)
    conversation_id = _seed(db_path, workspace_id, PREFERENCE_TEXT)
    assert _extract(client, workspace_id, conversation_id).status_code == 201

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/memory/promotions", json={}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["promotion_run_id"].startswith("mpr_")
    assert body["workspace_id"] == workspace_id
    assert body["source_candidate_count"] == 1
    assert body["promoted_count"] == 1
    assert body["skipped_count"] == 0
    assert body["promoted_memory_ids"][0].startswith("mem_")


def test_second_promotion_skips_duplicates(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(db_path)
    conversation_id = _seed(db_path, workspace_id, PREFERENCE_TEXT)
    _extract(client, workspace_id, conversation_id)
    url = f"/api/v1/workspaces/{workspace_id}/memory/promotions"
    assert client.post(url, json={}).json()["promoted_count"] == 1

    body = client.post(url, json={}).json()
    assert body["promoted_count"] == 0
    assert body["skipped_count"] == 1


def test_promotion_scope_errors(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(db_path)
    conversation_id = _seed(db_path, workspace_id, PREFERENCE_TEXT)
    _extract(client, workspace_id, conversation_id)

    assert (
        client.post("/api/v1/workspaces/tw_missing/memory/promotions").status_code
        == 404
    )
    other = _workspace_id(db_path)
    assert (
        client.post(
            f"/api/v1/workspaces/{other}/memory/promotions",
            params={"conversation_id": conversation_id},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/workspaces/{workspace_id}/memory/promotions",
            json={"trigger": "manual"},
        ).status_code
        == 422
    )
