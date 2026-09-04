"""Integration tests for the R5 memory inspection routes.

Every test overrides the memory service dependency with repositories over an
isolated temporary SQLite database, so no test reads or writes the developer
database at `APP_DB_PATH`. No test constructs a RAG service, an embedding
model, a Chroma collection, or a model-provider client.

These routes implement no authentication, authorization, or tenant isolation.
Fixture text is synthetic Vietnamese travel content with one artificial
secret-like marker, and carries no real credential.
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

MOMENT = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
PREFERENCE_TEXT = "Tôi ăn chay trường, hãy nhớ giúp tôi."
SECRET_TEXT = "API key của tôi là sk-test-Shadow42x, đừng quên nhé."
LONG_PREFERENCE = "Tôi ăn chay trường vì lý do sức khỏe và môi trường. " * 12


def _workspace_id(workspace_repository: SQLiteWorkspaceRepository) -> str:
    return workspace_repository.create(
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
    ).workspace_id


def _client(db_path: Path):
    """Client bound to a throwaway database.

    Built without the lifespan context manager on purpose: memory routes
    construct no RAG service, embedding model, or Chroma collection.
    """
    memory = SQLiteMemoryRepository(db_path=db_path)
    conversations = SQLiteConversationRepository(db_path=db_path)
    workspaces = SQLiteWorkspaceRepository(db_path=db_path)
    conversation_service = ConversationService(
        conversation_repository=conversations,
        workspace_repository=workspaces,
    )
    service = MemoryService(
        memory_repository=memory,
        conversation_repository=conversations,
        workspace_repository=workspaces,
    )
    app.dependency_overrides[get_memory_service] = lambda: service
    return TestClient(app), conversation_service


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_memory_service, None)


def _seed(
    client: TestClient, conversation_service, workspace_id: str, *contents
) -> str:
    conversation = conversation_service.create_conversation(
        ConversationCreate(workspace_id=workspace_id, title=None)
    )
    for content in contents:
        if isinstance(content, tuple):
            text, trace = content
        else:
            text, trace = content, TraceVisibility.INCLUDED
        conversation_service.append_message(
            conversation_id=conversation.conversation_id,
            role=MessageRole.USER,
            content=text,
            source=MessageSource.UI,
            trace_visibility=trace,
        )
    return conversation.conversation_id


def _trigger(client: TestClient, workspace_id: str, conversation_id: str, body=None):
    url = (
        f"/api/v1/workspaces/{workspace_id}/conversations/"
        f"{conversation_id}/memory/extractions"
    )
    if body is None:
        return client.post(url)
    return client.post(url, json=body)


# 1. Manual trigger creates a shadow run without exposing content.


def test_manual_trigger_returns_201_with_counts(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client, conversation_service = _client(db_path)
    workspace_id = _workspace_id(SQLiteWorkspaceRepository(db_path=db_path))
    conversation_id = _seed(client, conversation_service, workspace_id, PREFERENCE_TEXT)

    response = _trigger(client, workspace_id, conversation_id, {})

    assert response.status_code == 201
    body = response.json()
    assert body["run_id"].startswith("mer_")
    assert body["workspace_id"] == workspace_id
    assert body["conversation_id"] == conversation_id
    assert body["trigger"] == "manual"
    assert body["status"] == "completed"
    assert body["candidate_count"] == 1
    assert body["accepted_count"] == 1
    assert body["failure_reason"] is None
    assert PREFERENCE_TEXT not in response.text


def test_trigger_without_body_also_works(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client, conversation_service = _client(db_path)
    workspace_id = _workspace_id(SQLiteWorkspaceRepository(db_path=db_path))
    conversation_id = _seed(client, conversation_service, workspace_id, PREFERENCE_TEXT)

    assert _trigger(client, workspace_id, conversation_id).status_code == 201


def test_caller_supplied_trigger_is_rejected(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client, conversation_service = _client(db_path)
    workspace_id = _workspace_id(SQLiteWorkspaceRepository(db_path=db_path))
    conversation_id = _seed(client, conversation_service, workspace_id, PREFERENCE_TEXT)

    response = _trigger(client, workspace_id, conversation_id, {"trigger": "manual"})
    assert response.status_code == 422


def test_unknown_request_fields_are_rejected(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client, conversation_service = _client(db_path)
    workspace_id = _workspace_id(SQLiteWorkspaceRepository(db_path=db_path))
    conversation_id = _seed(client, conversation_service, workspace_id, PREFERENCE_TEXT)

    response = _trigger(client, workspace_id, conversation_id, {"foo": 1})
    assert response.status_code == 422


def test_trigger_missing_scope_returns_404(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client, conversation_service = _client(db_path)
    workspace_id = _workspace_id(SQLiteWorkspaceRepository(db_path=db_path))
    conversation_id = _seed(client, conversation_service, workspace_id, PREFERENCE_TEXT)

    assert _trigger(client, "tw_missing", conversation_id, {}).status_code == 404
    assert _trigger(client, workspace_id, "cv_missing", {}).status_code == 404


def test_trigger_workspace_mismatch_returns_409(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client, conversation_service = _client(db_path)
    workspaces = SQLiteWorkspaceRepository(db_path=db_path)
    first = _workspace_id(workspaces)
    second = _workspace_id(workspaces)
    conversation_id = _seed(client, conversation_service, first, PREFERENCE_TEXT)

    assert _trigger(client, second, conversation_id, {}).status_code == 409


# 2. Run and candidate listing.


def test_list_runs_returns_newest_first(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client, conversation_service = _client(db_path)
    workspace_id = _workspace_id(SQLiteWorkspaceRepository(db_path=db_path))
    first = _seed(client, conversation_service, workspace_id, PREFERENCE_TEXT)
    second = _seed(client, conversation_service, workspace_id, PREFERENCE_TEXT)
    first_run = _trigger(client, workspace_id, first, {}).json()["run_id"]
    second_run = _trigger(client, workspace_id, second, {}).json()["run_id"]

    response = client.get(f"/api/v1/workspaces/{workspace_id}/memory/extractions")
    assert response.status_code == 200
    runs = response.json()["runs"]
    assert [item["run_id"] for item in runs] == [second_run, first_run]

    filtered = client.get(
        f"/api/v1/workspaces/{workspace_id}/memory/extractions",
        params={"conversation_id": first},
    )
    assert [item["run_id"] for item in filtered.json()["runs"]] == [first_run]


def test_list_runs_scope_errors(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client, conversation_service = _client(db_path)
    workspace_id = _workspace_id(SQLiteWorkspaceRepository(db_path=db_path))
    conversation_id = _seed(client, conversation_service, workspace_id, PREFERENCE_TEXT)

    assert (
        client.get("/api/v1/workspaces/tw_missing/memory/extractions").status_code
        == 404
    )
    other = _workspace_id(SQLiteWorkspaceRepository(db_path=db_path))
    assert (
        client.get(
            f"/api/v1/workspaces/{other}/memory/extractions",
            params={"conversation_id": conversation_id},
        ).status_code
        == 409
    )


def test_list_candidates_exposes_evidence_without_raw_text(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client, conversation_service = _client(db_path)
    workspace_id = _workspace_id(SQLiteWorkspaceRepository(db_path=db_path))
    conversation_id = _seed(
        client, conversation_service, workspace_id, LONG_PREFERENCE, SECRET_TEXT
    )
    run_id = _trigger(client, workspace_id, conversation_id, {}).json()["run_id"]

    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/memory/candidates",
        params={"run_id": run_id},
    )
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    assert len(candidates) == 2
    assert candidates[0]["source_sequence"] == 1
    assert candidates[0]["reason"] == "supported_preference"
    assert candidates[1]["reason"] == "secret_like"
    assert "text" not in candidates[0]
    assert LONG_PREFERENCE not in response.text
    assert "sk-test-Shadow42x" not in response.text


def test_list_candidates_scope_errors(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client, conversation_service = _client(db_path)
    workspace_id = _workspace_id(SQLiteWorkspaceRepository(db_path=db_path))
    conversation_id = _seed(client, conversation_service, workspace_id, PREFERENCE_TEXT)
    run_id = _trigger(client, workspace_id, conversation_id, {}).json()["run_id"]

    base = f"/api/v1/workspaces/{workspace_id}/memory/candidates"
    assert client.get(base, params={"run_id": "mer_missing"}).status_code == 404
    other = _workspace_id(SQLiteWorkspaceRepository(db_path=db_path))
    assert (
        client.get(
            f"/api/v1/workspaces/{other}/memory/candidates",
            params={"run_id": run_id},
        ).status_code
        == 409
    )
    assert (
        client.get("/api/v1/workspaces/tw_missing/memory/candidates").status_code == 404
    )
