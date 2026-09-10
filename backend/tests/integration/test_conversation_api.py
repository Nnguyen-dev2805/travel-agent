"""Integration tests for the standalone conversation routes.

All routes require authentication. Conversations are standalone and owned
directly by authenticated principals with zero workspace dependency.
Direct message append is permanently unmounted.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.api.conversations import get_conversation_service
from backend.app.config import settings
from backend.app.main import app
from backend.conversations.models import (
    Conversation,
    ConversationRetentionState,
    Message,
    MessageDraft,
    MessageHistoryQuery,
    MessageRole,
    MessageSource,
    TraceVisibility,
)
from backend.conversations.repository import (
    ConversationAlreadyExistsError,
    ConversationStorageError,
    MessageAlreadyExistsError,
    MessageSequenceConflictError,
)
from backend.conversations.service import ConversationService

ALICE_TOKEN = "token-alice-123"
BOB_TOKEN = "token-bob-456"
ALICE_HEADERS = {"Authorization": f"Bearer {ALICE_TOKEN}"}
BOB_HEADERS = {"Authorization": f"Bearer {BOB_TOKEN}"}
MISSING_CONVERSATION = "cv_missing"


class InMemoryConversationRepository:
    """In-memory repository for standalone conversation API tests."""

    def __init__(self) -> None:
        self.conversations: dict[str, Conversation] = {}
        self.messages: list[Message] = []

    def create(self, conversation: Conversation) -> Conversation:
        if conversation.conversation_id in self.conversations:
            raise ConversationAlreadyExistsError("Conversation identity collision")
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


@pytest.fixture(autouse=True)
def configure_auth_tokens(monkeypatch):
    registry_json = (
        f'{{"alice": "{ALICE_TOKEN}", "bob": "{BOB_TOKEN}"}}'
    )
    monkeypatch.setattr(settings, "LOCAL_AUTH_TOKENS_JSON", SecretStr(registry_json))


@pytest.fixture
def repository() -> InMemoryConversationRepository:
    return InMemoryConversationRepository()


@pytest.fixture
def service(repository: InMemoryConversationRepository) -> ConversationService:
    return ConversationService(conversation_repository=repository)


@pytest.fixture
def client(service: ConversationService):
    app.dependency_overrides[get_conversation_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_conversation_service, None)


def _seed_conversation(
    client: TestClient, headers: dict = ALICE_HEADERS, title: str = "Da Nang trip"
) -> str:
    response = client.post("/api/v1/conversations", json={"title": title}, headers=headers)
    assert response.status_code == 201
    return response.json()["conversation_id"]


# 1. Authentication requirements


def test_unauthenticated_requests_return_401(client):
    assert client.post("/api/v1/conversations", json={}).status_code == 401
    assert client.get("/api/v1/conversations").status_code == 401
    assert client.get("/api/v1/conversations/cv_test").status_code == 401
    assert client.get("/api/v1/conversations/cv_test/messages").status_code == 401
    assert client.delete("/api/v1/conversations/cv_test").status_code == 401


def test_invalid_bearer_token_returns_401(client):
    bad_headers = {"Authorization": "Bearer invalid-token"}
    assert client.post("/api/v1/conversations", json={}, headers=bad_headers).status_code == 401
    assert client.get("/api/v1/conversations", headers=bad_headers).status_code == 401


# 2. Standalone conversation creation


def test_create_conversation_returns_201_with_governed_identity(client):
    response = client.post(
        "/api/v1/conversations",
        json={"title": "  Da Nang food plan  "},
        headers=ALICE_HEADERS,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["conversation_id"].startswith("cv_")
    assert body["owner_user_id"] == "alice"
    assert body["title"] == "Da Nang food plan"
    assert body["retention_state"] == "active"
    assert "workspace_id" not in body


def test_create_conversation_allows_null_title(client):
    response = client.post(
        "/api/v1/conversations",
        json={},
        headers=ALICE_HEADERS,
    )
    assert response.status_code == 201
    assert response.json()["title"] is None


def test_create_conversation_rejects_too_long_title(client):
    response = client.post(
        "/api/v1/conversations",
        json={"title": "t" * 121},
        headers=ALICE_HEADERS,
    )
    assert response.status_code == 422


# 3. Listing conversations


def test_list_conversations_returns_owned_conversations(client):
    c1 = _seed_conversation(client, headers=ALICE_HEADERS, title="C1")
    c2 = _seed_conversation(client, headers=ALICE_HEADERS, title="C2")
    _seed_conversation(client, headers=BOB_HEADERS, title="Bob Conv")

    response = client.get("/api/v1/conversations", headers=ALICE_HEADERS)
    assert response.status_code == 200
    ids = [c["conversation_id"] for c in response.json()["conversations"]]
    assert c1 in ids
    assert c2 in ids
    assert len(ids) == 2


def test_list_conversations_empty_for_new_user(client):
    response = client.get("/api/v1/conversations", headers=BOB_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"conversations": []}


# 4. Reading one conversation


def test_get_conversation_returns_owned_record(client):
    conv_id = _seed_conversation(client, headers=ALICE_HEADERS, title="Alice Conv")

    response = client.get(f"/api/v1/conversations/{conv_id}", headers=ALICE_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == conv_id
    assert body["owner_user_id"] == "alice"
    assert body["title"] == "Alice Conv"


def test_get_missing_conversation_returns_404(client):
    response = client.get(f"/api/v1/conversations/{MISSING_CONVERSATION}", headers=ALICE_HEADERS)
    assert response.status_code == 404


def test_cross_owner_get_returns_404(client):
    alice_conv = _seed_conversation(client, headers=ALICE_HEADERS, title="Alice Secret")

    # Bob attempts to read Alice's conversation
    response = client.get(f"/api/v1/conversations/{alice_conv}", headers=BOB_HEADERS)
    assert response.status_code == 404


# 5. Deletion (tombstoning)


def test_delete_conversation_tombstones_and_returns_204(client):
    conv_id = _seed_conversation(client, headers=ALICE_HEADERS)

    response = client.delete(f"/api/v1/conversations/{conv_id}", headers=ALICE_HEADERS)
    assert response.status_code == 204

    # Subsequent GET returns 404
    assert client.get(f"/api/v1/conversations/{conv_id}", headers=ALICE_HEADERS).status_code == 404

    # Omitted from list
    list_resp = client.get("/api/v1/conversations", headers=ALICE_HEADERS)
    assert conv_id not in [c["conversation_id"] for c in list_resp.json()["conversations"]]


def test_delete_missing_conversation_returns_404(client):
    response = client.delete(f"/api/v1/conversations/{MISSING_CONVERSATION}", headers=ALICE_HEADERS)
    assert response.status_code == 404


def test_cross_owner_delete_returns_404(client):
    alice_conv = _seed_conversation(client, headers=ALICE_HEADERS)

    # Bob attempts to delete Alice's conversation
    response = client.delete(f"/api/v1/conversations/{alice_conv}", headers=BOB_HEADERS)
    assert response.status_code == 404

    # Still accessible to Alice
    assert client.get(f"/api/v1/conversations/{alice_conv}", headers=ALICE_HEADERS).status_code == 200


# 6. Messages history reading


def test_messages_history_returns_transcript(client, service):
    conv_id = _seed_conversation(client, headers=ALICE_HEADERS)
    service.append_message(conv_id, MessageRole.USER, "Xin chào", owner_user_id="alice")
    service.append_message(conv_id, MessageRole.ASSISTANT, "Chào bạn!", owner_user_id="alice")

    response = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=ALICE_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert len(body["messages"]) == 2
    assert body["messages"][0]["content"] == "Xin chào"
    assert body["messages"][1]["content"] == "Chào bạn!"


def test_cross_owner_messages_history_returns_404(client, service):
    conv_id = _seed_conversation(client, headers=ALICE_HEADERS)
    service.append_message(conv_id, MessageRole.USER, "Secret message", owner_user_id="alice")

    # Bob attempts to read history
    response = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=BOB_HEADERS)
    assert response.status_code == 404


# 7. Direct message append is permanently unmounted


def test_direct_message_append_route_is_unmounted_returns_404(client):
    conv_id = _seed_conversation(client, headers=ALICE_HEADERS)
    response = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"role": "user", "content": "direct append"},
        headers=ALICE_HEADERS,
    )
    # The route POST /conversations/{id}/messages does not exist on FastAPI
    assert response.status_code == 405 or response.status_code == 404
