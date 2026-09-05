"""Integration test proving bound chat never writes planner state.

The test drives a real bound chat turn through `ConversationOrchestrator`
with a stub RAG service and repositories over an isolated temporary SQLite
database, then asserts the planner tables hold no rows. No test constructs
a real RAG service, an embedding model, a Chroma collection, or a
model-provider client.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.chat import get_conversation_orchestrator
from backend.app.main import app
from backend.conversations.models import (
    ConversationCreate,
    MessageRole,
    MessageSource,
    TraceVisibility,
)
from backend.conversations.service import ConversationService
from backend.conversations.sqlite_repository import SQLiteConversationRepository
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator
from backend.planner.sqlite_repository import SQLitePlannerRepository
from backend.rag.contracts import ContextBundle
from backend.workspaces.models import (
    PlanningStatus,
    RetentionState,
    TripWorkspace,
    generate_workspace_id,
)
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

MOMENT = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


class FakeRAG:
    """Stub RAG facade answering without retrieval side effects."""

    def generate_answer(self, message, top_k=None):
        return {
            "reply": "fake reply",
            "model": "fake-model",
            "citations": [{"title": "T", "url": "https://u"}],
        }

    def build_travel_context(self, message, top_k=None):
        return ContextBundle(
            prompt_context="travel context",
            evidence=(),
            citations=(),
            insufficient_evidence=False,
        )

    def generate_from_context(self, message, bundle):
        return {
            "reply": "fake reply",
            "model": "fake-model",
            "citations": [{"title": "T", "url": "https://u"}],
        }


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_conversation_orchestrator, None)


def test_bound_chat_creates_no_planner_rows(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    conversations = SQLiteConversationRepository(db_path=db_path)
    workspaces = SQLiteWorkspaceRepository(db_path=db_path)
    workspace_id = workspaces.create(
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
    conversation_service = ConversationService(conversations, workspaces)
    conversation_id = conversation_service.create_conversation(
        ConversationCreate(workspace_id=workspace_id, title=None)
    ).conversation_id
    orchestrator = ConversationOrchestrator(
        rag_service=FakeRAG(),
        conversation_service_provider=lambda: conversation_service,
        memory_enabled=False,
    )
    app.dependency_overrides[get_conversation_orchestrator] = lambda: orchestrator
    client = TestClient(app)

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Lên giúp tôi lịch trình Đà Nẵng 3 ngày.",
            "conversation_id": conversation_id,
        },
    )
    assert response.status_code == 200

    planner = SQLitePlannerRepository(db_path=db_path)
    assert planner.list_itinerary_versions(workspace_id) == ()
    assert planner.list_decisions(workspace_id) == ()
    assert planner.list_operations(workspace_id) == ()
