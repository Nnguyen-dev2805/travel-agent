"""Integration tests for authenticated chat and conversation binding.

All chat requests require authentication.
A chat request without `conversation_id` auto-creates a standalone conversation.
A chat request with `conversation_id` persists the turn into the owned conversation.
Cross-owner chat attempts return 404 (indistinguishable from missing).

Tests exercise the endpoint against a fake RAG service and an in-memory repository,
so no external models, network, or live databases are required.
"""

from datetime import datetime, timezone
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.api.chat import get_conversation_orchestrator
from backend.app.api.conversations import get_conversation_service
from backend.app.config import settings
from backend.app.main import app
from backend.conversations.models import (
    Conversation,
    ConversationRetentionState,
    Message,
    MessageDraft,
    MessageRole,
    MessageSource,
    TraceVisibility,
)
from backend.conversations.repository import (
    ConversationAlreadyExistsError,
    ConversationStorageError,
)
from backend.conversations.service import ConversationService
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator

GENERATED_REPLY = "Tháng 3 đến tháng 8 là đẹp nhất."
USER_MESSAGE = "Nên đi Đà Nẵng vào tháng mấy?"
CITATIONS = [{"title": "Đà Nẵng", "url": "https://vietnam.travel/da-nang"}]

ALICE_TOKEN = "token-alice-123"
BOB_TOKEN = "token-bob-456"
ALICE_HEADERS = {"Authorization": f"Bearer {ALICE_TOKEN}"}
BOB_HEADERS = {"Authorization": f"Bearer {BOB_TOKEN}"}


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


class InMemoryConversationRepository:
    """In-memory repository for chat conversation binding tests."""

    def __init__(self) -> None:
        self.conversations: dict[str, Conversation] = {}
        self.messages: list[Message] = []

    def create(self, conversation: Conversation) -> Conversation:
        if conversation.conversation_id in self.conversations:
            raise ConversationAlreadyExistsError("Conversation already exists")
        self.conversations[conversation.conversation_id] = conversation
        return conversation

    def get(self, conversation_id: str) -> Optional[Conversation]:
        return self.conversations.get(conversation_id)

    def list_by_owner(
        self, owner_user_id: str, include_deletion: bool = False
    ) -> tuple[Conversation, ...]:
        results = []
        for conv in self.conversations.values():
            if conv.owner_user_id != owner_user_id:
                continue
            if not include_deletion and conv.retention_state in (
                ConversationRetentionState.TOMBSTONED,
                ConversationRetentionState.DELETED,
                ConversationRetentionState.DELETION_REQUESTED,
            ):
                continue
            results.append(conv)
        return tuple(results)

    def delete(self, conversation_id: str) -> bool:
        conv = self.conversations.get(conversation_id)
        if conv is None or conv.retention_state == ConversationRetentionState.TOMBSTONED:
            return False
        self.conversations[conversation_id] = Conversation(
            conversation_id=conv.conversation_id,
            owner_user_id=conv.owner_user_id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=datetime.now(timezone.utc),
            retention_state=ConversationRetentionState.TOMBSTONED,
        )
        return True

    def append_message(
        self,
        message: MessageDraft,
        message_id: str,
        outbox_event: dict | None = None,
    ) -> Message:
        sequence = (
            sum(
                1
                for stored in self.messages
                if stored.conversation_id == message.conversation_id
            )
            + 1
        )
        stored = Message(
            message_id=message_id,
            conversation_id=message.conversation_id,
            sequence=sequence,
            role=message.role,
            content=message.content,
            source=message.source,
            trace_visibility=message.trace_visibility,
            created_at=message.created_at,
        )
        self.messages.append(stored)
        return stored

    def get_message(self, message_id: str) -> Optional[Message]:
        for msg in self.messages:
            if msg.message_id == message_id:
                return msg
        return None

    def list_messages(
        self, conversation_id: str, after_sequence: int | None, limit: int
    ) -> tuple[Message, ...]:
        selected = [
            msg
            for msg in self.messages
            if msg.conversation_id == conversation_id
            and (after_sequence is None or msg.sequence > after_sequence)
        ]
        selected.sort(key=lambda m: m.sequence)
        return tuple(selected[:limit])


class RoleFailingRepository:
    """Conversation repository proxy that fails writes for one role."""

    def __init__(self, inner: InMemoryConversationRepository, failing_role: MessageRole):
        self._inner = inner
        self._failing_role = failing_role

    def create(self, conversation):
        return self._inner.create(conversation)

    def get(self, conversation_id):
        return self._inner.get(conversation_id)

    def list_by_owner(self, owner_user_id, include_deletion=False):
        return self._inner.list_by_owner(owner_user_id, include_deletion)

    def delete(self, conversation_id):
        return self._inner.delete(conversation_id)

    def get_message(self, message_id):
        return self._inner.get_message(message_id)

    def list_messages(self, conversation_id, after_sequence=None, limit=100):
        return self._inner.list_messages(conversation_id, after_sequence, limit)

    def append_message(
        self,
        message: MessageDraft,
        message_id: str,
        outbox_event: dict | None = None,
    ):
        if message.role is self._failing_role:
            raise ConversationStorageError("Could not persist the message record.")
        return self._inner.append_message(message, message_id, outbox_event=outbox_event)


@pytest.fixture(autouse=True)
def configure_auth_tokens(monkeypatch):
    registry_json = f'{{"alice": "{ALICE_TOKEN}", "bob": "{BOB_TOKEN}"}}'
    monkeypatch.setattr(settings, "LOCAL_AUTH_TOKENS_JSON", SecretStr(registry_json))


@pytest.fixture
def conversation_repository() -> InMemoryConversationRepository:
    return InMemoryConversationRepository()


@pytest.fixture
def rag() -> FakeRAGService:
    return FakeRAGService()


def _bind(repo, rag_service: FakeRAGService):
    service = ConversationService(conversation_repository=repo)
    orchestrator = ConversationOrchestrator(
        rag_service=rag_service,
        conversation_service_provider=lambda: service,
    )
    app.dependency_overrides[get_conversation_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_conversation_service] = lambda: service
    return TestClient(app)


@pytest.fixture
def client(conversation_repository, rag: FakeRAGService):
    try:
        yield _bind(conversation_repository, rag)
    finally:
        app.dependency_overrides.pop(get_conversation_orchestrator, None)
        app.dependency_overrides.pop(get_conversation_service, None)


@pytest.fixture
def user_write_fails_client(conversation_repository, rag: FakeRAGService):
    try:
        yield _bind(
            RoleFailingRepository(conversation_repository, MessageRole.USER),
            rag,
        )
    finally:
        app.dependency_overrides.pop(get_conversation_orchestrator, None)
        app.dependency_overrides.pop(get_conversation_service, None)


@pytest.fixture
def assistant_write_fails_client(conversation_repository, rag: FakeRAGService):
    try:
        yield _bind(
            RoleFailingRepository(conversation_repository, MessageRole.ASSISTANT),
            rag,
        )
    finally:
        app.dependency_overrides.pop(get_conversation_orchestrator, None)
        app.dependency_overrides.pop(get_conversation_service, None)


def _new_conversation(client: TestClient, headers: dict = ALICE_HEADERS, title: str = "Da Nang") -> str:
    response = client.post("/api/v1/conversations", json={"title": title}, headers=headers)
    assert response.status_code == 201
    return response.json()["conversation_id"]


def _chat(
    client: TestClient,
    conversation_id: str | None,
    message: str = USER_MESSAGE,
    headers: dict = ALICE_HEADERS,
):
    payload: dict = {"message": message}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    return client.post("/api/v1/chat", json=payload, headers=headers)


def _history(client: TestClient, conversation_id: str, headers: dict = ALICE_HEADERS) -> list[dict]:
    response = client.get(f"/api/v1/conversations/{conversation_id}/messages", headers=headers)
    assert response.status_code == 200
    return response.json()["messages"]


# 1. Unconditional authentication enforcement


def test_unauthenticated_chat_returns_401(client, rag):
    response = client.post("/api/v1/chat", json={"message": USER_MESSAGE})
    assert response.status_code == 401
    assert rag.calls == []


def test_invalid_bearer_token_chat_returns_401(client, rag):
    response = client.post(
        "/api/v1/chat",
        json={"message": USER_MESSAGE},
        headers={"Authorization": "Bearer invalid_token"},
    )
    assert response.status_code == 401
    assert rag.calls == []


# 2. Auto-creation on first chat turn (ADR 0021)


def test_chat_without_conversation_id_auto_creates_conversation(client, rag):
    response = _chat(client, conversation_id=None)

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == GENERATED_REPLY
    assert body["model"] == "gpt-4o-mini"
    assert body["citations"] == CITATIONS

    conv_info = body["conversation"]
    assert conv_info is not None
    assert conv_info["persisted"] is True
    assert conv_info["conversation_id"].startswith("cv_")
    assert conv_info["user_message_id"].startswith("ms_")
    assert conv_info["assistant_message_id"].startswith("ms_")

    auto_id = conv_info["conversation_id"]
    messages = _history(client, auto_id)
    assert len(messages) == 2
    assert (messages[0]["role"], messages[0]["sequence"]) == ("user", 1)
    assert (messages[1]["role"], messages[1]["sequence"]) == ("assistant", 2)
    assert messages[0]["content"] == USER_MESSAGE
    assert messages[1]["content"] == GENERATED_REPLY
    assert rag.calls == [(USER_MESSAGE, 4)]


def test_explicit_null_conversation_id_auto_creates_conversation(client):
    response = client.post(
        "/api/v1/chat",
        json={"message": USER_MESSAGE, "conversation_id": None},
        headers=ALICE_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["conversation"] is not None
    assert body["conversation"]["conversation_id"].startswith("cv_")
    assert body["conversation"]["persisted"] is True


def test_auto_created_conversation_is_listed_for_owner(client):
    response = _chat(client, conversation_id=None)
    auto_id = response.json()["conversation"]["conversation_id"]

    list_resp = client.get("/api/v1/conversations", headers=ALICE_HEADERS)
    assert list_resp.status_code == 200
    listed_ids = [c["conversation_id"] for c in list_resp.json()["conversations"]]
    assert auto_id in listed_ids


def test_subsequent_chat_in_auto_created_conversation_continues_transcript(client):
    resp1 = _chat(client, conversation_id=None, message="Turn 1")
    conv_id = resp1.json()["conversation"]["conversation_id"]

    resp2 = _chat(client, conversation_id=conv_id, message="Turn 2")
    assert resp2.status_code == 200

    messages = _history(client, conv_id)
    assert len(messages) == 4
    assert [m["sequence"] for m in messages] == [1, 2, 3, 4]
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]


# 3. Explicit conversation binding and persistence


def test_bound_chat_returns_the_reply_and_a_persisted_conversation_object(client, rag):
    conversation_id = _new_conversation(client)

    response = _chat(client, conversation_id)

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= {"reply", "model", "citations", "conversation"}
    assert body["reply"] == GENERATED_REPLY
    assert body["model"] == "gpt-4o-mini"
    assert body["citations"] == CITATIONS
    assert body["conversation"]["conversation_id"] == conversation_id
    assert body["conversation"]["persisted"] is True
    assert body["conversation"]["user_message_id"].startswith("ms_")
    assert body["conversation"]["assistant_message_id"].startswith("ms_")
    assert rag.calls == [(USER_MESSAGE, 4)]


def test_bound_chat_persists_the_user_turn_then_the_assistant_turn(client):
    conversation_id = _new_conversation(client)
    _chat(client, conversation_id)

    messages = _history(client, conversation_id)

    assert len(messages) == 2
    assert (messages[0]["role"], messages[0]["sequence"]) == ("user", 1)
    assert (messages[1]["role"], messages[1]["sequence"]) == ("assistant", 2)
    assert messages[0]["source"] == "ui"
    assert messages[1]["source"] == "model"


def test_persisted_user_content_equals_the_submitted_message(client):
    conversation_id = _new_conversation(client)
    _chat(client, conversation_id)

    messages = _history(client, conversation_id)

    assert messages[0]["content"] == USER_MESSAGE
    assert messages[1]["content"] == GENERATED_REPLY


def test_bound_chat_reports_the_message_ids_that_history_returns(client):
    conversation_id = _new_conversation(client)
    reported = _chat(client, conversation_id).json()["conversation"]

    messages = _history(client, conversation_id)

    assert reported["user_message_id"] == messages[0]["message_id"]
    assert reported["assistant_message_id"] == messages[1]["message_id"]


def test_bound_chat_strips_the_message_before_persisting(client):
    conversation_id = _new_conversation(client)

    _chat(client, conversation_id, message=f"  {USER_MESSAGE}  ")

    assert _history(client, conversation_id)[0]["content"] == USER_MESSAGE


def test_two_sequential_bound_turns_produce_sequences_one_through_four(client):
    conversation_id = _new_conversation(client)

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


# 4. Cross-owner isolation (ADR 0021: returns 404, not 403)


def test_cross_owner_chat_returns_404_without_calling_rag(client, rag):
    # Alice creates a conversation
    alice_conv_id = _new_conversation(client, headers=ALICE_HEADERS)

    # Bob attempts to chat in Alice's conversation
    response = _chat(client, alice_conv_id, headers=BOB_HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found."
    assert rag.calls == []


# 5. Validation and error handling


def test_unknown_conversation_returns_404_without_calling_rag(client, rag):
    response = _chat(client, "cv_absent")

    assert response.status_code == 404
    assert rag.calls == []


def test_empty_message_with_a_valid_conversation_still_returns_400(client, rag):
    conversation_id = _new_conversation(client)

    response = _chat(client, conversation_id, message="   ")

    assert response.status_code == 400
    assert "cannot be empty" in response.json()["detail"]
    assert rag.calls == []
    assert _history(client, conversation_id) == []


def test_empty_message_without_conversation_returns_400(client, rag):
    response = _chat(client, conversation_id=None, message="   ")

    assert response.status_code == 400
    assert "cannot be empty" in response.json()["detail"]
    assert rag.calls == []


def test_user_turn_write_failure_returns_500_without_calling_rag(user_write_fails_client, rag):
    conversation_id = _new_conversation(user_write_fails_client)

    response = _chat(user_write_fails_client, conversation_id)

    assert response.status_code == 500
    assert rag.calls == [], "the caller must not be charged for an unrecorded turn"
    assert _history(user_write_fails_client, conversation_id) == []


def test_user_turn_write_failure_body_carries_no_message_content(user_write_fails_client):
    conversation_id = _new_conversation(user_write_fails_client)

    response = _chat(user_write_fails_client, conversation_id)

    assert USER_MESSAGE not in response.text


def test_assistant_turn_write_failure_returns_the_reply_with_persisted_false(
    assistant_write_fails_client, rag
):
    conversation_id = _new_conversation(assistant_write_fails_client)

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
