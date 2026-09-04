"""Integration tests for the optional chat conversation binding.

A chat request that carries `conversation_id` persists its turn; a request
without it behaves exactly as it does today. Both paths are exercised here
against a fake RAG service and a temporary database, so no test requires a model
provider, an embedding model, Chroma state, or the network.

Persistence is verified through the history route rather than through a log,
because message content must never reach a log.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.chat import get_conversation_orchestrator
from backend.app.api.conversations import get_conversation_service
from backend.app.main import app
from backend.conversations.models import MessageDraft, MessageRole
from backend.conversations.repository import ConversationStorageError
from backend.conversations.service import ConversationService
from backend.conversations.sqlite_repository import SQLiteConversationRepository
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator
from backend.workspaces.models import (
    PlanningStatus,
    TripWorkspace,
    generate_workspace_id,
)
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

GENERATED_REPLY = "Tháng 3 đến tháng 8 là đẹp nhất."
USER_MESSAGE = "Nên đi Đà Nẵng vào tháng mấy?"
CITATIONS = [{"title": "Đà Nẵng", "url": "https://vietnam.travel/da-nang"}]


class FakeRAGService:
    """Stub `RAGService` facade recording every call it receives."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None]] = []

    def generate_answer(self, user_message: str, top_k: int | None = None) -> dict:
        self.calls.append((user_message, top_k))
        return {
            "reply": GENERATED_REPLY,
            "model": "gpt-4o-mini",
            "citations": CITATIONS,
        }


class RoleFailingRepository:
    """Conversation repository proxy that fails writes for one role.

    Used to observe how a partial persistence failure surfaces to the caller
    without weakening the real adapter.
    """

    def __init__(self, inner: SQLiteConversationRepository, failing_role: MessageRole):
        self._inner = inner
        self._failing_role = failing_role

    def create(self, conversation):
        return self._inner.create(conversation)

    def get(self, conversation_id):
        return self._inner.get(conversation_id)

    def list_by_workspace(self, workspace_id):
        return self._inner.list_by_workspace(workspace_id)

    def get_message(self, message_id):
        return self._inner.get_message(message_id)

    def list_messages(self, conversation_id, after_sequence, limit):
        return self._inner.list_messages(conversation_id, after_sequence, limit)

    def append_message(self, message: MessageDraft, message_id: str):
        if message.role is self._failing_role:
            raise ConversationStorageError("Could not persist the message record.")
        return self._inner.append_message(message, message_id)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "travel_agent.sqlite3"


@pytest.fixture
def workspace_repository(db_path: Path) -> SQLiteWorkspaceRepository:
    return SQLiteWorkspaceRepository(db_path=db_path)


@pytest.fixture
def conversation_repository(db_path: Path) -> SQLiteConversationRepository:
    return SQLiteConversationRepository(db_path=db_path)


@pytest.fixture
def workspace_id(workspace_repository: SQLiteWorkspaceRepository) -> str:
    moment = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    return workspace_repository.create(
        TripWorkspace(
            workspace_id=generate_workspace_id(),
            owner_user_id="local-user",
            title="Da Nang family trip",
            destination_scope=None,
            date_window=None,
            planning_status=PlanningStatus.IDEA,
            created_at=moment,
            updated_at=moment,
        )
    ).workspace_id


@pytest.fixture
def rag() -> FakeRAGService:
    return FakeRAGService()


def _bind(
    conversation_repository,
    workspace_repository: SQLiteWorkspaceRepository,
    rag: FakeRAGService,
):
    """Override both chat and conversation dependencies onto one fake stack."""
    service = ConversationService(
        conversation_repository=conversation_repository,
        workspace_repository=workspace_repository,
    )
    orchestrator = ConversationOrchestrator(
        rag_service=rag, conversation_service_provider=lambda: service
    )
    app.dependency_overrides[get_conversation_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_conversation_service] = lambda: service
    return TestClient(app)


@pytest.fixture
def client(conversation_repository, workspace_repository, rag: FakeRAGService):
    try:
        yield _bind(conversation_repository, workspace_repository, rag)
    finally:
        app.dependency_overrides.pop(get_conversation_orchestrator, None)
        app.dependency_overrides.pop(get_conversation_service, None)


@pytest.fixture
def user_write_fails_client(
    conversation_repository, workspace_repository, rag: FakeRAGService
):
    try:
        yield _bind(
            RoleFailingRepository(conversation_repository, MessageRole.USER),
            workspace_repository,
            rag,
        )
    finally:
        app.dependency_overrides.pop(get_conversation_orchestrator, None)
        app.dependency_overrides.pop(get_conversation_service, None)


@pytest.fixture
def assistant_write_fails_client(
    conversation_repository, workspace_repository, rag: FakeRAGService
):
    try:
        yield _bind(
            RoleFailingRepository(conversation_repository, MessageRole.ASSISTANT),
            workspace_repository,
            rag,
        )
    finally:
        app.dependency_overrides.pop(get_conversation_orchestrator, None)
        app.dependency_overrides.pop(get_conversation_service, None)


def _new_conversation(client: TestClient, workspace_id: str) -> str:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations", json={"title": "Da Nang"}
    )
    assert response.status_code == 201
    return response.json()["conversation_id"]


def _chat(client: TestClient, conversation_id: str | None, message: str = USER_MESSAGE):
    payload: dict = {"message": message}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    return client.post("/api/v1/chat", json=payload)


def _history(client: TestClient, conversation_id: str) -> list[dict]:
    response = client.get(f"/api/v1/conversations/{conversation_id}/messages")
    assert response.status_code == 200
    return response.json()["messages"]


# 1 and 2. A bound turn reports persistence and stores both sides in order.


def test_bound_chat_returns_the_reply_and_a_persisted_conversation_object(
    client, workspace_id, rag
):
    conversation_id = _new_conversation(client, workspace_id)

    response = _chat(client, conversation_id)

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"reply", "model", "citations", "conversation"}
    assert body["reply"] == GENERATED_REPLY
    assert body["model"] == "gpt-4o-mini"
    assert body["citations"] == CITATIONS
    assert body["conversation"]["conversation_id"] == conversation_id
    assert body["conversation"]["persisted"] is True
    assert body["conversation"]["user_message_id"].startswith("ms_")
    assert body["conversation"]["assistant_message_id"].startswith("ms_")
    assert rag.calls == [(USER_MESSAGE, 4)]


def test_bound_chat_persists_the_user_turn_then_the_assistant_turn(
    client, workspace_id
):
    conversation_id = _new_conversation(client, workspace_id)
    _chat(client, conversation_id)

    messages = _history(client, conversation_id)

    assert len(messages) == 2
    assert (messages[0]["role"], messages[0]["sequence"]) == ("user", 1)
    assert (messages[1]["role"], messages[1]["sequence"]) == ("assistant", 2)
    assert messages[0]["source"] == "ui"
    assert messages[1]["source"] == "model"


# 3. The persisted content is verified through the history route.


def test_persisted_user_content_equals_the_submitted_message(client, workspace_id):
    conversation_id = _new_conversation(client, workspace_id)
    _chat(client, conversation_id)

    messages = _history(client, conversation_id)

    assert messages[0]["content"] == USER_MESSAGE
    assert messages[1]["content"] == GENERATED_REPLY


def test_bound_chat_reports_the_message_ids_that_history_returns(client, workspace_id):
    conversation_id = _new_conversation(client, workspace_id)
    reported = _chat(client, conversation_id).json()["conversation"]

    messages = _history(client, conversation_id)

    assert reported["user_message_id"] == messages[0]["message_id"]
    assert reported["assistant_message_id"] == messages[1]["message_id"]


# 4. An unknown conversation stops the turn before any model call.


def test_unknown_conversation_returns_404_without_calling_rag(client, rag):
    response = _chat(client, "cv_absent")

    assert response.status_code == 404
    assert rag.calls == []


# 5. A user-turn write failure returns 500 before any model call.


def test_user_turn_write_failure_returns_500_without_calling_rag(
    user_write_fails_client, workspace_id, rag
):
    conversation_id = _new_conversation(user_write_fails_client, workspace_id)

    response = _chat(user_write_fails_client, conversation_id)

    assert response.status_code == 500
    assert rag.calls == [], "the caller must not be charged for an unrecorded turn"
    assert _history(user_write_fails_client, conversation_id) == []


def test_user_turn_write_failure_body_carries_no_message_content(
    user_write_fails_client, workspace_id
):
    conversation_id = _new_conversation(user_write_fails_client, workspace_id)

    response = _chat(user_write_fails_client, conversation_id)

    assert USER_MESSAGE not in response.text


# 6. An assistant-turn write failure is reported, never hidden.


def test_assistant_turn_write_failure_returns_the_reply_with_persisted_false(
    assistant_write_fails_client, workspace_id, rag
):
    conversation_id = _new_conversation(assistant_write_fails_client, workspace_id)

    response = _chat(assistant_write_fails_client, conversation_id)

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == GENERATED_REPLY
    assert body["conversation"]["persisted"] is False
    assert body["conversation"]["assistant_message_id"] is None
    assert body["conversation"]["user_message_id"].startswith("ms_")
    assert rag.calls == [(USER_MESSAGE, 4)]

    messages = _history(assistant_write_fails_client, conversation_id)
    assert [message["role"] for message in messages] == ["user"]


# 7. Sequential bound turns keep a continuous transcript order.


def test_two_sequential_bound_turns_produce_sequences_one_through_four(
    client, workspace_id
):
    conversation_id = _new_conversation(client, workspace_id)

    assert _chat(client, conversation_id).status_code == 200
    assert (
        _chat(client, conversation_id, message="Còn Hội An thì sao?").status_code == 200
    )

    messages = _history(client, conversation_id)

    assert [message["sequence"] for message in messages] == [1, 2, 3, 4]
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


# 8. Existing chat validation is unchanged on the bound path.


def test_empty_message_with_a_valid_conversation_still_returns_400(
    client, workspace_id, rag
):
    conversation_id = _new_conversation(client, workspace_id)

    response = _chat(client, conversation_id, message="   ")

    assert response.status_code == 400
    assert "cannot be empty" in response.json()["detail"]
    assert rag.calls == []
    assert _history(client, conversation_id) == []


def test_bound_chat_strips_the_message_before_persisting(client, workspace_id):
    conversation_id = _new_conversation(client, workspace_id)

    _chat(client, conversation_id, message=f"  {USER_MESSAGE}  ")

    assert _history(client, conversation_id)[0]["content"] == USER_MESSAGE


# The unbound path stays byte-for-byte compatible.


def test_unbound_chat_response_has_no_conversation_key(client, rag):
    response = _chat(client, conversation_id=None)

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"reply", "model", "citations"}
    assert "conversation" not in body
    assert rag.calls == [(USER_MESSAGE, 4)]


def test_unbound_chat_creates_no_conversation_record(
    client, workspace_id, conversation_repository
):
    _chat(client, conversation_id=None)

    assert conversation_repository.list_by_workspace(workspace_id) == ()


def test_explicit_null_conversation_id_behaves_as_unbound(client):
    response = client.post(
        "/api/v1/chat", json={"message": USER_MESSAGE, "conversation_id": None}
    )

    assert response.status_code == 200
    assert "conversation" not in response.json()
