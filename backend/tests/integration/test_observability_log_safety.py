"""Integration tests proving R8 log privacy across runtime paths.

Captured logs must carry identifiers, reason codes, and counts but never
raw user messages, prompts, memory text, itinerary text, decision
statements, or token values. Every test runs against an isolated temporary
SQLite database. No test constructs a real RAG service, an embedding
model, a Chroma collection, or a model-provider client.
"""

import json
import logging
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
from backend.memory.service import MemoryService
from backend.memory.sqlite_repository import SQLiteMemoryRepository
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator
from backend.planner.models import (
    DecisionStatus,
    DecisionType,
    ItineraryItem,
    ItineraryItemType,
    ItineraryStatus,
    ItineraryVersionDraft,
    TripDecision,
    generate_decision_id,
)
from backend.planner.service import PlannerService
from backend.planner.sqlite_repository import SQLitePlannerRepository
from backend.rag.contracts import ContextBundle
from backend.storage.schema_registry import (
    open_application_database,
    register_module_schema,
)
from backend.workspaces.models import (
    PlanningStatus,
    RetentionState,
    TripWorkspace,
    generate_workspace_id,
)
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

MOMENT = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)

USER_SENTINEL = "NEVER_LOG_USER_MESSAGE ăn chay trường"
MEMORY_SENTINEL = "NEVER_LOG_MEMORY_TEXT ăn chay trường"
ITINERARY_SENTINEL = "NEVER_LOG_ITINERARY_TEXT Hà Nội"
DECISION_SENTINEL = "NEVER_LOG_DECISION_STATEMENT ăn chay"
TOKEN_SENTINEL = "ghp_NEVER_LOG_TOKEN_VALUE"


@pytest.fixture(autouse=True)
def _capture_info_logs(caplog):
    caplog.set_level(logging.INFO)
    yield


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_conversation_orchestrator, None)


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


def _conversation_id(db_path: Path, workspace_id: str) -> str:
    service = ConversationService(
        SQLiteConversationRepository(db_path=db_path),
        SQLiteWorkspaceRepository(db_path=db_path),
    )
    conversation = service.create_conversation(
        ConversationCreate(workspace_id=workspace_id, title=None)
    )
    return conversation.conversation_id


def _append(db_path: Path, conversation_id: str, content: str) -> None:
    service = ConversationService(
        SQLiteConversationRepository(db_path=db_path),
        SQLiteWorkspaceRepository(db_path=db_path),
    )
    service.append_message(
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=content,
        source=MessageSource.UI,
        trace_visibility=TraceVisibility.INCLUDED,
    )


def _chat_client(db_path: Path) -> TestClient:
    conversations = SQLiteConversationRepository(db_path=db_path)
    workspaces = SQLiteWorkspaceRepository(db_path=db_path)
    conversation_service = ConversationService(conversations, workspaces)
    orchestrator = ConversationOrchestrator(
        rag_service=FakeRAG(),
        conversation_service_provider=lambda: conversation_service,
        memory_enabled=False,
    )
    app.dependency_overrides[get_conversation_orchestrator] = lambda: orchestrator
    return TestClient(app)


def _event_names(caplog) -> list:
    names = []
    for record in caplog.records:
        if record.name != "travel_agent_observability":
            continue
        try:
            names.append(json.loads(record.message)["event_name"])
        except (ValueError, KeyError):
            continue
    return names


def test_unbound_chat_logs_events_without_user_message(tmp_path: Path, caplog):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _chat_client(db_path)

    response = client.post("/api/v1/chat", json={"message": USER_SENTINEL})

    assert response.status_code == 200
    assert "NEVER_LOG_USER_MESSAGE" not in caplog.text
    assert "chat.request.accepted" in _event_names(caplog)
    assert "chat.turn.completed" in _event_names(caplog)


def test_bound_chat_gate_off_logs_no_memory_content(tmp_path: Path, caplog):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _chat_client(db_path)
    workspace_id = _workspace_id(db_path)
    conversation_id = _conversation_id(db_path, workspace_id)

    response = client.post(
        "/api/v1/chat",
        json={"message": USER_SENTINEL, "conversation_id": conversation_id},
    )

    assert response.status_code == 200
    assert "NEVER_LOG_USER_MESSAGE" not in caplog.text
    assert conversation_id in caplog.text


def test_blank_chat_message_rejected_without_content(tmp_path: Path, caplog):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _chat_client(db_path)

    response = client.post("/api/v1/chat", json={"message": "   "})

    assert response.status_code == 400
    assert "api.request.completed" in _event_names(caplog)


def test_token_like_message_never_reaches_logs(tmp_path: Path, caplog):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _chat_client(db_path)

    response = client.post(
        "/api/v1/chat", json={"message": f"Dùng token {TOKEN_SENTINEL} nhé"}
    )

    assert response.status_code == 200
    assert "ghp_NEVER_LOG_TOKEN_VALUE" not in caplog.text
    assert "[REDACTED]" not in response.text


def test_memory_extraction_logs_ids_not_text(tmp_path: Path, caplog):
    db_path = tmp_path / "travel_agent.sqlite3"
    workspace_id = _workspace_id(db_path)
    conversation_id = _conversation_id(db_path, workspace_id)
    _append(db_path, conversation_id, MEMORY_SENTINEL)
    service = MemoryService(
        memory_repository=SQLiteMemoryRepository(db_path=db_path),
        conversation_repository=SQLiteConversationRepository(db_path=db_path),
        workspace_repository=SQLiteWorkspaceRepository(db_path=db_path),
    )

    run = service.run_conversation_extraction(workspace_id, conversation_id, "manual")

    assert "NEVER_LOG_MEMORY_TEXT" not in caplog.text
    assert run.run_id in caplog.text
    assert "memory.extraction.completed" in _event_names(caplog)


def test_planner_writes_log_ids_not_text(tmp_path: Path, caplog):
    db_path = tmp_path / "travel_agent.sqlite3"
    workspace_id = _workspace_id(db_path)
    service = PlannerService(
        planner_repository=SQLitePlannerRepository(db_path=db_path),
        workspace_repository=SQLiteWorkspaceRepository(db_path=db_path),
        conversation_repository=SQLiteConversationRepository(db_path=db_path),
    )

    version = service.create_itinerary_version(
        workspace_id,
        ItineraryVersionDraft(
            workspace_id=workspace_id,
            status=ItineraryStatus.DRAFT,
            title=ITINERARY_SENTINEL,
            items=(
                ItineraryItem(
                    day_index=1,
                    position=1,
                    item_type=ItineraryItemType.MEAL,
                    title="Bún chả",
                ),
            ),
        ),
    )
    decision = service.record_decision(
        workspace_id,
        TripDecision(
            decision_id=generate_decision_id(),
            workspace_id=workspace_id,
            decision_type=DecisionType.PREFERENCE,
            status=DecisionStatus.PENDING,
            statement=DECISION_SENTINEL,
            created_at=MOMENT,
            updated_at=MOMENT,
        ),
    )

    assert "NEVER_LOG_ITINERARY_TEXT" not in caplog.text
    assert "NEVER_LOG_DECISION_STATEMENT" not in caplog.text
    assert version.itinerary_version_id in caplog.text
    assert decision.decision_id in caplog.text
    assert "planner.operation.applied" in _event_names(caplog)


def test_schema_mismatch_logs_failure_class_without_paths(tmp_path: Path, caplog):
    db_path = tmp_path / "travel_agent.sqlite3"
    connection = open_application_database(db_path)
    try:
        register_module_schema(connection, "memory", 99, lambda _: None)
    finally:
        connection.close()

    with pytest.raises(Exception):
        SQLiteMemoryRepository(db_path=db_path)

    assert "storage.schema.failed" in _event_names(caplog)
    assert str(db_path) not in caplog.text
