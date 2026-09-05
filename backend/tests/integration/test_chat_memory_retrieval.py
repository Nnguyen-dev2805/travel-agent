"""Integration tests for R6 feature-gated memory chat integration.

Every test overrides the orchestrator dependency with a real
`ConversationOrchestrator` wired to a stub RAG service and repositories over
an isolated temporary SQLite database. Gate-off turns must never resolve
memory storage; gate-on turns select governed memory metadata only.

No test constructs a real RAG service, an embedding model, a Chroma
collection, or a model-provider client.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.chat import get_conversation_orchestrator
from backend.app.config import Settings, _env_flag
from backend.app.main import app
from backend.conversations.models import (
    ConversationCreate,
    MessageRole,
    MessageSource,
    TraceVisibility,
)
from backend.conversations.service import ConversationService
from backend.conversations.sqlite_repository import SQLiteConversationRepository
from backend.memory.retrieval import MemoryRetrievalService
from backend.memory.service import MemoryService
from backend.memory.sqlite_repository import SQLiteMemoryRepository
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator
from backend.rag.contracts import ContextBundle
from backend.workspaces.models import (
    PlanningStatus,
    RetentionState,
    TripWorkspace,
    generate_workspace_id,
)
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

MOMENT = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
PREFERENCE_TEXT = "Tôi ăn chay trường, hãy nhớ giúp tôi."


class FakeRAG:
    """Stub RAG facade with the R6 travel-context seam."""

    def __init__(self):
        self.answer_calls = []
        self.context_calls = []
        self.generate_calls = []
        self.prompt_contexts = []

    def generate_answer(self, message, top_k=None):
        self.answer_calls.append((message, top_k))
        return {
            "reply": "fake reply",
            "model": "fake-model",
            "citations": [{"title": "T", "url": "https://u"}],
        }

    def build_travel_context(self, message, top_k=None):
        self.context_calls.append((message, top_k))
        return ContextBundle(
            prompt_context="travel context",
            evidence=(),
            citations=(),
            insufficient_evidence=False,
        )

    def generate_from_context(self, message, bundle):
        self.generate_calls.append((message, bundle))
        self.prompt_contexts.append(bundle.prompt_context)
        return {
            "reply": "fake reply",
            "model": "fake-model",
            "citations": [{"title": "T", "url": "https://u"}],
        }


class _ExplodingMemoryProvider:
    def __call__(self):
        raise AssertionError("memory must not resolve on this path")


def _stores(db_path: Path):
    memory = SQLiteMemoryRepository(db_path=db_path)
    conversations = SQLiteConversationRepository(db_path=db_path)
    workspaces = SQLiteWorkspaceRepository(db_path=db_path)
    return memory, conversations, workspaces


def _workspace_id(workspaces: SQLiteWorkspaceRepository) -> str:
    return workspaces.create(
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


def _conversation(conversation_service, workspace_id: str) -> str:
    return conversation_service.create_conversation(
        ConversationCreate(workspace_id=workspace_id, title=None)
    ).conversation_id


CONSTRAINT_TEXT = "Ngân sách chuyến này tối đa 20 triệu."


def _promote_preference(
    db_path: Path, workspace_id: str, conversation_id: str, content=PREFERENCE_TEXT
):
    """Seed one message, extract it, and promote it; return the memory id."""
    memory, conversations, workspaces = _stores(db_path)
    conversation_service = ConversationService(conversations, workspaces)
    memory_service = MemoryService(memory, conversations, workspaces)
    conversation_service.append_message(
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=content,
        source=MessageSource.UI,
        trace_visibility=TraceVisibility.INCLUDED,
    )
    memory_service.run_conversation_extraction(workspace_id, conversation_id, "manual")
    result = memory_service.promote_workspace(workspace_id, conversation_id)
    assert result.promoted_count == 1
    return result.promoted_memory_ids[0]


def _client(db_path: Path, orchestrator: ConversationOrchestrator) -> TestClient:
    app.dependency_overrides[get_conversation_orchestrator] = lambda: orchestrator
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_conversation_orchestrator, None)


def _orchestrator(db_path: Path, fake_rag, enabled: bool, provider=None):
    memory, conversations, workspaces = _stores(db_path)
    conversation_service = ConversationService(conversations, workspaces)

    def real_provider():
        def resolve_owner(workspace_id: str):
            workspace = workspaces.get(workspace_id)
            return workspace.owner_user_id if workspace is not None else None

        return (
            MemoryRetrievalService(memory),
            resolve_owner,
        )

    return (
        ConversationOrchestrator(
            rag_service=fake_rag,
            conversation_service_provider=lambda: conversation_service,
            memory_enabled=enabled,
            memory_provider=real_provider if provider is None else provider,
        ),
        fake_rag,
    )


# 1. Gate-off behavior is byte-for-byte R4/R5 behavior.


def test_gate_off_preserves_schema_and_never_resolves_memory(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    memory, conversations, workspaces = _stores(db_path)
    workspace_id = _workspace_id(workspaces)
    conversation_service = ConversationService(conversations, workspaces)
    conversation_id = _conversation(conversation_service, workspace_id)
    fake_rag = FakeRAG()
    orchestrator, _ = _orchestrator(
        db_path, fake_rag, enabled=False, provider=_ExplodingMemoryProvider()
    )
    client = _client(db_path, orchestrator)

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Nên đi Đà Nẵng vào tháng mấy?",
            "conversation_id": conversation_id,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"reply", "model", "citations", "conversation"}
    assert "memory" not in response.text
    assert len(fake_rag.answer_calls) == 1
    assert fake_rag.context_calls == []


def test_gate_defaults_off_without_environment(monkeypatch):
    for name in (
        "MEMORY_RETRIEVAL_ENABLED",
        "MEMORY_PROMOTION_MIN_CONFIDENCE",
        "MEMORY_MAX_SELECTED",
    ):
        monkeypatch.delenv(name, raising=False)
    fresh = Settings()
    assert fresh.MEMORY_RETRIEVAL_ENABLED is False
    assert fresh.MEMORY_PROMOTION_MIN_CONFIDENCE == 0.75
    assert fresh.MEMORY_MAX_SELECTED == 5


def test_gate_enabled_by_explicit_true(monkeypatch):
    monkeypatch.setenv("MEMORY_RETRIEVAL_ENABLED", "True")
    assert _env_flag("MEMORY_RETRIEVAL_ENABLED", False) is True
    monkeypatch.setenv("MEMORY_RETRIEVAL_ENABLED", "0")
    assert _env_flag("MEMORY_RETRIEVAL_ENABLED", False) is False


def test_unbound_chat_skips_memory_when_enabled(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    fake_rag = FakeRAG()
    orchestrator, _ = _orchestrator(
        db_path, fake_rag, enabled=True, provider=_ExplodingMemoryProvider()
    )
    client = _client(db_path, orchestrator)

    response = client.post("/api/v1/chat", json={"message": "Xin chào"})
    assert response.status_code == 200
    assert "memory" not in response.text
    assert len(fake_rag.answer_calls) == 1


# 2. Gate-on bound turns select governed memory metadata.


def test_enabled_bound_turn_selects_memory_and_preserves_citations(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    memory, conversations, workspaces = _stores(db_path)
    workspace_id = _workspace_id(workspaces)
    conversation_service = ConversationService(conversations, workspaces)
    conversation_id = _conversation(conversation_service, workspace_id)
    memory_id = _promote_preference(db_path, workspace_id, conversation_id)
    fake_rag = FakeRAG()
    orchestrator, _ = _orchestrator(db_path, fake_rag, enabled=True)
    client = _client(db_path, orchestrator)

    response = client.post(
        "/api/v1/chat",
        json={"message": "Tôi ăn chay thì đi đâu?", "conversation_id": conversation_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["memory"]["enabled"] is True
    assert body["memory"]["status"] == "selected"
    assert body["memory"]["selected_memory_ids"] == [memory_id]
    assert body["memory"]["selection_reasons"] == ["lexical_match"]
    assert body["citations"] == [{"title": "T", "url": "https://u"}]
    assert len(fake_rag.context_calls) == 1
    assert fake_rag.answer_calls == []
    prompt = fake_rag.prompt_contexts[0]
    assert "[Bộ nhớ liên quan]" in prompt
    assert PREFERENCE_TEXT in prompt
    assert "travel context" in prompt


def test_enabled_turn_without_eligible_memory_reports_none_selected(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    memory, conversations, workspaces = _stores(db_path)
    workspace_id = _workspace_id(workspaces)
    conversation_service = ConversationService(conversations, workspaces)
    conversation_id = _conversation(conversation_service, workspace_id)
    fake_rag = FakeRAG()
    orchestrator, _ = _orchestrator(db_path, fake_rag, enabled=True)
    client = _client(db_path, orchestrator)

    response = client.post(
        "/api/v1/chat",
        json={"message": "Xin chào", "conversation_id": conversation_id},
    )
    assert response.status_code == 200
    assert response.json()["memory"]["status"] == "none_selected"


def test_out_of_scope_and_superseded_records_are_not_selected(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    memory, conversations, workspaces = _stores(db_path)
    home = _workspace_id(workspaces)
    away = _workspace_id(workspaces)
    home_conversation = _conversation(
        ConversationService(conversations, workspaces), home
    )
    away_conversation = _conversation(
        ConversationService(conversations, workspaces), away
    )
    foreign_id = _promote_preference(
        db_path, away, away_conversation, content=CONSTRAINT_TEXT
    )
    home_id = _promote_preference(db_path, home, home_conversation)
    SQLiteMemoryRepository(db_path=db_path).mark_records_superseded([home_id])
    fake_rag = FakeRAG()
    orchestrator, _ = _orchestrator(db_path, fake_rag, enabled=True)
    client = _client(db_path, orchestrator)

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "ngân sách ăn chay",
            "conversation_id": home_conversation,
        },
    )
    assert response.status_code == 200
    assert response.json()["memory"]["status"] == "none_selected"
    assert foreign_id not in response.text


def test_missing_conversation_stays_404_without_memory(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    fake_rag = FakeRAG()
    orchestrator, _ = _orchestrator(
        db_path, fake_rag, enabled=True, provider=_ExplodingMemoryProvider()
    )
    client = _client(db_path, orchestrator)

    response = client.post(
        "/api/v1/chat",
        json={"message": "Xin chào", "conversation_id": "cv_missing"},
    )
    assert response.status_code == 404
