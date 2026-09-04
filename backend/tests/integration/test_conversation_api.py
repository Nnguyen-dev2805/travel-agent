"""Integration tests for the R4 conversation routes.

Every test overrides the conversation service dependency with an isolated
temporary SQLite database, so no test reads or writes the developer database at
`APP_DB_PATH`. No test constructs a RAG service, an embedding model, a Chroma
collection, or a model-provider client.

These routes implement no authentication, authorization, or tenant isolation.
The tests assert deterministic repository filtering only.

Fixture text is synthetic Vietnamese and English travel content and carries no
secret.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.conversations import get_conversation_service
from backend.app.main import app
from backend.conversations.models import TITLE_MAX_LENGTH
from backend.conversations.service import ConversationService
from backend.conversations.sqlite_repository import SQLiteConversationRepository
from backend.workspaces.models import (
    PlanningStatus,
    RetentionState,
    TripWorkspace,
    generate_workspace_id,
)
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

PRIVATE_CONTENT = "Nội dung riêng tư không được lộ ra lỗi"
LONG_TITLE = "t" * (TITLE_MAX_LENGTH + 1)
MISSING_WORKSPACE = "tw_missing"
MISSING_CONVERSATION = "cv_missing"


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
    stored = workspace_repository.create(
        TripWorkspace(
            workspace_id=generate_workspace_id(),
            owner_user_id="local-user",
            title="Da Nang family trip",
            destination_scope=None,
            date_window=None,
            planning_status=PlanningStatus.IDEA,
            created_at=moment,
            updated_at=moment,
            retention_state=RetentionState.ACTIVE,
        )
    )
    return stored.workspace_id


@pytest.fixture
def client(
    conversation_repository: SQLiteConversationRepository,
    workspace_repository: SQLiteWorkspaceRepository,
):
    """Client bound to a throwaway database.

    Built without the lifespan context manager on purpose: conversation routes
    construct no RAG service, embedding model, or Chroma collection, so
    pre-warming them here would add cost and an external dependency the routes
    do not have.
    """
    service = ConversationService(
        conversation_repository=conversation_repository,
        workspace_repository=workspace_repository,
    )
    app.dependency_overrides[get_conversation_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_conversation_service, None)


def _create_conversation(client: TestClient, workspace_id: str, **payload):
    return client.post(f"/api/v1/workspaces/{workspace_id}/conversations", json=payload)


def _append(client: TestClient, conversation_id: str, **payload):
    body = {"role": "user", "content": "Nên đi Đà Nẵng vào tháng mấy?"}
    body.update(payload)
    return client.post(f"/api/v1/conversations/{conversation_id}/messages", json=body)


def _seed_conversation(client: TestClient, workspace_id: str, **payload) -> str:
    response = _create_conversation(client, workspace_id, **payload)
    assert response.status_code == 201
    return response.json()["conversation_id"]


# 1, 2 and 3. Creation.


def test_create_returns_201_with_governed_identity_and_defaults(client, workspace_id):
    response = _create_conversation(client, workspace_id, title="  Da Nang food plan  ")

    assert response.status_code == 201
    body = response.json()
    assert body["conversation_id"].startswith("cv_")
    assert body["workspace_id"] == workspace_id
    assert body["title"] == "Da Nang food plan"
    assert body["retention_state"] == "active"
    assert body["created_at"] == body["updated_at"]
    assert set(body.keys()) == {
        "conversation_id",
        "workspace_id",
        "title",
        "retention_state",
        "created_at",
        "updated_at",
    }


def test_create_accepts_an_absent_title(client, workspace_id):
    response = _create_conversation(client, workspace_id)
    assert response.status_code == 201
    assert response.json()["title"] is None


def test_create_normalizes_a_blank_title_to_absent(client, workspace_id):
    response = _create_conversation(client, workspace_id, title="   ")
    assert response.status_code == 201
    assert response.json()["title"] is None


def test_create_under_a_missing_workspace_returns_404(client, conversation_repository):
    response = _create_conversation(client, MISSING_WORKSPACE, title="Orphan")

    assert response.status_code == 404
    assert conversation_repository.list_by_workspace(MISSING_WORKSPACE) == ()


def test_create_with_an_overlong_title_returns_422_and_creates_nothing(
    client, workspace_id, conversation_repository
):
    response = _create_conversation(client, workspace_id, title=LONG_TITLE)

    assert response.status_code == 422
    assert conversation_repository.list_by_workspace(workspace_id) == ()
    assert LONG_TITLE not in response.text


# 4. Reading one conversation.


def test_get_returns_the_stored_conversation(client, workspace_id):
    conversation_id = _seed_conversation(client, workspace_id, title="Da Nang")

    response = client.get(f"/api/v1/conversations/{conversation_id}")

    assert response.status_code == 200
    assert response.json()["conversation_id"] == conversation_id


def test_get_a_missing_conversation_returns_404(client):
    response = client.get(f"/api/v1/conversations/{MISSING_CONVERSATION}")
    assert response.status_code == 404


# 5, 6 and 7. Listing.


def test_list_returns_an_object_not_a_bare_array(client, workspace_id):
    _seed_conversation(client, workspace_id, title="Only")

    response = client.get(f"/api/v1/workspaces/{workspace_id}/conversations")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert set(body.keys()) == {"conversations"}
    assert [record["title"] for record in body["conversations"]] == ["Only"]


def test_list_excludes_other_workspaces(client, workspace_id, workspace_repository):
    moment = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    other = workspace_repository.create(
        TripWorkspace(
            workspace_id=generate_workspace_id(),
            owner_user_id="local-user",
            title="Other trip",
            destination_scope=None,
            date_window=None,
            planning_status=PlanningStatus.IDEA,
            created_at=moment,
            updated_at=moment,
        )
    )
    _seed_conversation(client, workspace_id, title="Mine")
    _seed_conversation(client, other.workspace_id, title="Theirs")

    body = client.get(f"/api/v1/workspaces/{workspace_id}/conversations").json()

    assert [record["title"] for record in body["conversations"]] == ["Mine"]


def test_list_applies_the_governed_newest_first_ordering(client, workspace_id):
    first = _seed_conversation(client, workspace_id, title="First")
    second = _seed_conversation(client, workspace_id, title="Second")
    # Appending bumps `updated_at`, which is the primary ordering key.
    assert _append(client, first, content="đẩy lên đầu").status_code == 201

    body = client.get(f"/api/v1/workspaces/{workspace_id}/conversations").json()
    ordered = [record["conversation_id"] for record in body["conversations"]]

    assert ordered == [first, second]


def test_list_for_a_workspace_with_no_conversations_returns_an_empty_array(
    client, workspace_id
):
    response = client.get(f"/api/v1/workspaces/{workspace_id}/conversations")
    assert response.status_code == 200
    assert response.json() == {"conversations": []}


def test_list_under_a_missing_workspace_returns_404(client):
    response = client.get(f"/api/v1/workspaces/{MISSING_WORKSPACE}/conversations")
    assert response.status_code == 404


# 8 and 9. Appending permitted roles.


def test_append_a_user_message_returns_201_with_incrementing_sequence(
    client, workspace_id
):
    conversation_id = _seed_conversation(client, workspace_id)

    first = _append(client, conversation_id, content="một")
    second = _append(client, conversation_id, content="hai")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["sequence"] == 1
    assert second.json()["sequence"] == 2

    body = first.json()
    assert body["message_id"].startswith("ms_")
    assert body["conversation_id"] == conversation_id
    assert body["role"] == "user"
    assert body["content"] == "một"
    assert body["source"] == "ui"
    assert body["trace_visibility"] == "excluded"
    assert set(body.keys()) == {
        "message_id",
        "conversation_id",
        "sequence",
        "role",
        "content",
        "source",
        "trace_visibility",
        "created_at",
    }


def test_append_a_system_event_message_succeeds(client, workspace_id):
    conversation_id = _seed_conversation(client, workspace_id)

    response = _append(
        client, conversation_id, role="system_event", content="workspace linked"
    )

    assert response.status_code == 201
    assert response.json()["role"] == "system_event"


def test_append_accepts_explicit_governed_source_and_visibility(client, workspace_id):
    conversation_id = _seed_conversation(client, workspace_id)

    response = _append(
        client, conversation_id, source="import", trace_visibility="included"
    )

    assert response.status_code == 201
    assert response.json()["source"] == "import"
    assert response.json()["trace_visibility"] == "included"


# 10, 11 and 12. Restricted and ungoverned vocabulary.


def test_append_an_assistant_role_returns_422_without_echoing_input(
    client, workspace_id, conversation_repository
):
    conversation_id = _seed_conversation(client, workspace_id)

    response = _append(
        client, conversation_id, role="assistant", content=PRIVATE_CONTENT
    )

    assert response.status_code == 422
    assert PRIVATE_CONTENT not in response.text
    assert "assistant" not in response.text
    assert conversation_repository.list_messages(conversation_id, None, 50) == ()


def test_append_a_tool_role_returns_422(client, workspace_id, conversation_repository):
    conversation_id = _seed_conversation(client, workspace_id)

    response = _append(client, conversation_id, role="tool", content=PRIVATE_CONTENT)

    assert response.status_code == 422
    assert PRIVATE_CONTENT not in response.text
    assert conversation_repository.list_messages(conversation_id, None, 50) == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("role", "moderator"),
        ("source", "browser"),
        ("trace_visibility", "hidden"),
    ],
)
def test_append_an_ungoverned_vocabulary_value_returns_422(
    client, workspace_id, conversation_repository, field, value
):
    conversation_id = _seed_conversation(client, workspace_id)

    response = _append(client, conversation_id, **{field: value})

    assert response.status_code == 422
    assert conversation_repository.list_messages(conversation_id, None, 50) == ()


# 13 and 14. Invalid append input.


@pytest.mark.parametrize("content", ["", "   "])
def test_append_blank_content_returns_422_and_creates_nothing(
    client, workspace_id, conversation_repository, content
):
    conversation_id = _seed_conversation(client, workspace_id)

    response = _append(client, conversation_id, content=content)

    assert response.status_code == 422
    assert conversation_repository.list_messages(conversation_id, None, 50) == ()


def test_append_to_a_missing_conversation_returns_404(client, conversation_repository):
    response = _append(client, MISSING_CONVERSATION, content=PRIVATE_CONTENT)

    assert response.status_code == 404
    assert PRIVATE_CONTENT not in response.text
    assert conversation_repository.list_messages(MISSING_CONVERSATION, None, 50) == ()


# 15, 16, 17, 18 and 19. History reads.


def test_history_returns_messages_in_sequence_ascending_order(client, workspace_id):
    conversation_id = _seed_conversation(client, workspace_id)
    for content in ("một", "hai", "ba"):
        assert _append(client, conversation_id, content=content).status_code == 201

    response = client.get(f"/api/v1/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"messages", "next_cursor"}
    assert [message["content"] for message in body["messages"]] == ["một", "hai", "ba"]
    assert [message["sequence"] for message in body["messages"]] == [1, 2, 3]


def test_history_cursor_returns_only_later_messages_and_a_null_final_cursor(
    client, workspace_id
):
    conversation_id = _seed_conversation(client, workspace_id)
    ids = [
        _append(client, conversation_id, content=content).json()["message_id"]
        for content in ("một", "hai", "ba")
    ]

    response = client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        params={"after_message_id": ids[0]},
    )

    assert response.status_code == 200
    body = response.json()
    assert [message["content"] for message in body["messages"]] == ["hai", "ba"]
    assert body["next_cursor"] is None, "a partial page is the last page"


def test_history_reports_a_cursor_while_a_full_page_is_returned(client, workspace_id):
    conversation_id = _seed_conversation(client, workspace_id)
    for content in ("một", "hai", "ba"):
        _append(client, conversation_id, content=content)

    first_page = client.get(
        f"/api/v1/conversations/{conversation_id}/messages", params={"limit": 2}
    ).json()

    assert [message["content"] for message in first_page["messages"]] == ["một", "hai"]
    assert first_page["next_cursor"] == first_page["messages"][-1]["message_id"]

    second_page = client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        params={"limit": 2, "after_message_id": first_page["next_cursor"]},
    ).json()

    assert [message["content"] for message in second_page["messages"]] == ["ba"]
    assert second_page["next_cursor"] is None


@pytest.mark.parametrize("limit", [0, 201, -1])
def test_history_with_a_limit_outside_the_governed_range_returns_422(
    client, workspace_id, limit
):
    conversation_id = _seed_conversation(client, workspace_id)

    response = client.get(
        f"/api/v1/conversations/{conversation_id}/messages", params={"limit": limit}
    )

    assert response.status_code == 422


def test_history_with_a_cursor_from_another_conversation_returns_422(
    client, workspace_id
):
    mine = _seed_conversation(client, workspace_id, title="Mine")
    theirs = _seed_conversation(client, workspace_id, title="Theirs")
    foreign = _append(client, theirs, content="của họ").json()["message_id"]

    response = client.get(
        f"/api/v1/conversations/{mine}/messages",
        params={"after_message_id": foreign},
    )

    assert response.status_code == 422


def test_history_with_an_unknown_cursor_returns_422(client, workspace_id):
    conversation_id = _seed_conversation(client, workspace_id)

    response = client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        params={"after_message_id": "ms_never_stored"},
    )

    assert response.status_code == 422


def test_history_for_a_conversation_with_no_messages_is_empty_with_a_null_cursor(
    client, workspace_id
):
    conversation_id = _seed_conversation(client, workspace_id)

    response = client.get(f"/api/v1/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    assert response.json() == {"messages": [], "next_cursor": None}


def test_history_for_a_missing_conversation_returns_404(client):
    response = client.get(f"/api/v1/conversations/{MISSING_CONVERSATION}/messages")
    assert response.status_code == 404


# 20. No error body leaks user content.


def test_no_error_body_contains_submitted_content_or_titles(client, workspace_id):
    conversation_id = _seed_conversation(client, workspace_id)
    secret_title = "Bí mật chuyến đi của tôi"

    failures = [
        _create_conversation(client, MISSING_WORKSPACE, title=secret_title),
        _create_conversation(client, workspace_id, title=LONG_TITLE + secret_title),
        _append(client, conversation_id, role="assistant", content=PRIVATE_CONTENT),
        _append(client, conversation_id, role="tool", content=PRIVATE_CONTENT),
        _append(client, MISSING_CONVERSATION, content=PRIVATE_CONTENT),
        client.get(f"/api/v1/conversations/{MISSING_CONVERSATION}/messages"),
        client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            params={"after_message_id": "ms_never_stored"},
        ),
    ]

    for response in failures:
        assert response.status_code in (404, 422), response.text
        assert PRIVATE_CONTENT not in response.text
        assert secret_title not in response.text


def test_routes_are_mounted_under_the_configured_api_prefix(client, workspace_id):
    """The router is mounted with `settings.API_V1_STR`, like chat and workspaces."""
    from backend.app.config import settings

    assert settings.API_V1_STR == "/api/v1"
    assert (
        client.get(
            f"{settings.API_V1_STR}/workspaces/{workspace_id}/conversations"
        ).status_code
        == 200
    )


def test_conversation_routes_do_not_disturb_health_or_chat(client):
    assert client.get("/health").status_code == 200
    assert client.post("/api/v1/chat", json={"message": "   "}).status_code == 400


# Schema-level validation must not echo the submitted value either.
#
# The domain contract owns the blank, length, and vocabulary rules, so those
# rejections already carry no user input. A wrong-typed payload is different: it
# fails inside the request schema, and FastAPI's default validation body reports
# the offending value under `input`. That would defeat the requirement that no
# error body carries message content or a conversation title, and a caller could
# defeat it deliberately by putting content in any field.


@pytest.mark.parametrize(
    "payload",
    [
        {"title": ["SUPER_SECRET_TITLE"]},
        {"title": {"nested": "SUPER_SECRET_TITLE"}},
        {"title": 12345},
    ],
)
def test_wrong_typed_title_returns_422_without_echoing_the_value(
    client, workspace_id, conversation_repository, payload
):
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations", json=payload
    )

    assert response.status_code == 422
    assert "SUPER_SECRET_TITLE" not in response.text
    assert "12345" not in response.text
    assert conversation_repository.list_by_workspace(workspace_id) == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content", ["SUPER_SECRET_CONTENT"]),
        ("content", {"nested": "SUPER_SECRET_CONTENT"}),
        ("role", {"nested": "SUPER_SECRET_CONTENT"}),
        ("source", ["SUPER_SECRET_CONTENT"]),
        ("trace_visibility", ["SUPER_SECRET_CONTENT"]),
    ],
)
def test_wrong_typed_message_field_returns_422_without_echoing_the_value(
    client, workspace_id, conversation_repository, field, value
):
    conversation_id = _seed_conversation(client, workspace_id)

    response = _append(client, conversation_id, **{field: value})

    assert response.status_code == 422
    assert "SUPER_SECRET_CONTENT" not in response.text
    assert conversation_repository.list_messages(conversation_id, None, 50) == ()


def test_sanitized_validation_body_keeps_its_useful_shape(client, workspace_id):
    """Redaction must remove the value, not the diagnostic."""
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations",
        json={"title": ["SUPER_SECRET_TITLE"]},
    )

    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], list)
    entry = body["detail"][0]
    assert set(entry.keys()) == {"type", "loc", "msg"}
    assert entry["loc"] == ["body", "title"]
    assert entry["type"] == "string_type"


def test_sanitized_validation_body_still_names_the_permitted_vocabulary(
    client, workspace_id
):
    """Dropping `ctx` loses no information: `msg` already lists the values."""
    conversation_id = _seed_conversation(client, workspace_id)

    response = _append(client, conversation_id, role="moderator")

    assert response.status_code == 422
    entry = response.json()["detail"][0]
    assert "user" in entry["msg"]
    assert "system_event" in entry["msg"]
    assert "input" not in entry


def test_malformed_json_body_returns_422_without_echoing_the_payload(
    client, workspace_id
):
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations",
        content=b'{"title": "SUPER_SECRET_TITLE"',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert "SUPER_SECRET_TITLE" not in response.text


def test_the_sanitizing_handler_is_application_wide(client):
    """Registered on the app, so workspace and chat payloads are covered too.

    Recorded as blast-radius evidence: the handler is not scoped to conversation
    routes, and the R3 workspace routes inherit the same redaction.
    """
    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"owner_user_id": "local-user", "title": ["SUPER_SECRET_TITLE"]},
    )
    assert workspace_response.status_code == 422
    assert "SUPER_SECRET_TITLE" not in workspace_response.text

    chat_response = client.post(
        "/api/v1/chat", json={"message": ["SUPER_SECRET_TITLE"]}
    )
    assert chat_response.status_code == 422
    assert "SUPER_SECRET_TITLE" not in chat_response.text
