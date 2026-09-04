"""Integration tests for the R3 workspace routes.

Most tests override the workspace service dependency with an isolated temporary
SQLite database, so they never read or write the developer database at
`APP_DB_PATH`.

The storage-failure tests deliberately do NOT override that dependency. They
point `settings.APP_DB_PATH` at a temporary broken database so the real
dependency-construction path runs, which is the only way to observe how an
infrastructure failure surfaces to the caller.

`owner_user_id` is a local development scope label. These tests assert
deterministic repository filtering only; they make no authentication,
authorization, or tenant-isolation claim.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.api import chat as chat_module
from backend.app.api.workspaces import get_workspace_service
from backend.app.main import app
from backend.workspaces.models import (
    PlanningStatus,
    RetentionState,
    TripWorkspace,
    generate_workspace_id,
    utc_now,
)
from backend.workspaces.service import WorkspaceService
from backend.workspaces.sqlite_repository import (
    SCHEMA_VERSION,
    SQLiteWorkspaceRepository,
)

LONG_TITLE = "t" * 121
LONG_DESTINATION = "d" * 161
STORAGE_ERROR_DETAIL = "Workspace storage is unavailable."


@pytest.fixture
def workspace_repository(tmp_path: Path) -> SQLiteWorkspaceRepository:
    """Throwaway workspace repository for seeding records directly."""
    return SQLiteWorkspaceRepository(db_path=tmp_path / "workspaces.sqlite3")


@pytest.fixture
def workspace_client(workspace_repository: SQLiteWorkspaceRepository):
    """FastAPI client bound to a throwaway workspace database."""
    service = WorkspaceService(repository=workspace_repository)

    app.dependency_overrides[get_workspace_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_workspace_service, None)


@pytest.fixture
def broken_storage_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Client whose real dependency resolves to an unreadable database.

    This fixture intentionally leaves `get_workspace_service` in place so the
    genuine construction path executes and its failure mode is observable.

    The seeded database carries a `PRAGMA user_version` value that the ADR 0004
    schema registry does not recognize as its own store marker, so the shared
    store refuses the file and the workspace adapter translates that refusal
    into `WorkspaceStorageError`.
    """
    db_path = tmp_path / "incompatible.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    monkeypatch.setattr(config.settings, "APP_DB_PATH", db_path, raising=False)
    app.dependency_overrides.pop(get_workspace_service, None)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _create(client: TestClient, **overrides):
    payload = {"owner_user_id": "local-user", "title": "Da Nang family trip"}
    payload.update(overrides)
    return client.post("/api/v1/workspaces", json=payload)


def _seed_at(
    repository: SQLiteWorkspaceRepository,
    title: str,
    moment: datetime,
    *,
    workspace_id: str | None = None,
    owner_user_id: str = "local-user",
) -> TripWorkspace:
    """Persist one record with explicit timestamps, to pin list ordering."""
    return repository.create(
        TripWorkspace(
            workspace_id=workspace_id or generate_workspace_id(),
            owner_user_id=owner_user_id,
            title=title,
            destination_scope=None,
            date_window=None,
            planning_status=PlanningStatus.IDEA,
            created_at=moment,
            updated_at=moment,
            retention_state=RetentionState.ACTIVE,
        )
    )


def _seed(
    repository: SQLiteWorkspaceRepository,
    *,
    retention_state: RetentionState,
    title: str,
    owner_user_id: str = "local-user",
) -> TripWorkspace:
    """Persist one record directly, bypassing the create route.

    R3 routes only produce `active` records, so retention-state filtering can be
    exercised only by seeding storage directly.
    """
    moment = utc_now()
    return repository.create(
        TripWorkspace(
            workspace_id=generate_workspace_id(),
            owner_user_id=owner_user_id,
            title=title,
            destination_scope=None,
            date_window=None,
            planning_status=PlanningStatus.IDEA,
            created_at=moment,
            updated_at=moment,
            retention_state=retention_state,
        )
    )


# 1. Successful create returns 201 with governed identity and defaults.


def test_create_returns_201_and_governed_record(workspace_client):
    response = _create(
        workspace_client,
        destination_scope="  Da Nang and Hoi An  ",
        date_window={"start_date": "2026-12-20", "end_date": "2026-12-25"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["workspace_id"].startswith("tw_")
    assert body["owner_user_id"] == "local-user"
    assert body["title"] == "Da Nang family trip"
    assert body["destination_scope"] == "Da Nang and Hoi An"
    assert body["date_window"] == {
        "start_date": "2026-12-20",
        "end_date": "2026-12-25",
    }
    assert body["planning_status"] == "idea"
    assert body["retention_state"] == "active"
    assert body["created_at"]
    assert body["updated_at"]


def test_create_normalizes_whitespace(workspace_client):
    response = _create(
        workspace_client,
        owner_user_id="  local-user  ",
        title="  Trip  ",
        destination_scope="   ",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["owner_user_id"] == "local-user"
    assert body["title"] == "Trip"
    assert body["destination_scope"] is None


def test_create_omits_optional_fields(workspace_client):
    response = _create(workspace_client)

    assert response.status_code == 201
    body = response.json()
    assert body["destination_scope"] is None
    assert body["date_window"] is None
    assert body["planning_status"] == "idea"


def test_create_accepts_explicit_governed_planning_status(workspace_client):
    response = _create(workspace_client, planning_status="booked")

    assert response.status_code == 201
    assert response.json()["planning_status"] == "booked"


def test_create_generates_distinct_identities(workspace_client):
    first = _create(workspace_client).json()["workspace_id"]
    second = _create(workspace_client).json()["workspace_id"]
    assert first != second


# 2. Get returns the created workspace.


def test_get_returns_created_workspace(workspace_client):
    created = _create(workspace_client).json()

    response = workspace_client.get(f"/api/v1/workspaces/{created['workspace_id']}")

    assert response.status_code == 200
    assert response.json() == created


# 3. Get on a missing workspace returns 404.


def test_get_missing_workspace_returns_404(workspace_client):
    response = workspace_client.get("/api/v1/workspaces/tw_does_not_exist")
    assert response.status_code == 404


def test_get_missing_workspace_detail_excludes_identifier_echo(workspace_client):
    response = workspace_client.get("/api/v1/workspaces/tw_secret_trip_reference")
    assert response.status_code == 404
    assert "tw_secret_trip_reference" not in response.text


def test_blank_workspace_id_path_does_not_fall_through_to_list(workspace_client):
    _create(workspace_client)

    response = workspace_client.get("/api/v1/workspaces/%20")

    assert response.status_code == 422
    assert "workspaces" not in response.json()


# 4. List requires owner_user_id.


def test_list_without_owner_returns_422(workspace_client):
    response = workspace_client.get("/api/v1/workspaces")
    assert response.status_code == 422


@pytest.mark.parametrize("blank", ["", "%20%20"])
def test_list_with_blank_owner_returns_422(workspace_client, blank):
    response = workspace_client.get(f"/api/v1/workspaces?owner_user_id={blank}")
    assert response.status_code == 422


# 5. List returns the governed object shape, owner scope, and ordering.


def test_list_returns_workspaces_object_not_bare_array(workspace_client):
    _create(workspace_client)

    response = workspace_client.get("/api/v1/workspaces?owner_user_id=local-user")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert set(body.keys()) == {"workspaces"}
    assert isinstance(body["workspaces"], list)


def test_list_excludes_other_owner_scope_labels(workspace_client):
    mine = _create(workspace_client, title="Mine").json()
    _create(workspace_client, owner_user_id="other-user", title="Theirs")

    body = workspace_client.get("/api/v1/workspaces?owner_user_id=local-user").json()

    ids = [record["workspace_id"] for record in body["workspaces"]]
    assert ids == [mine["workspace_id"]]


def test_list_orders_newest_updated_first(workspace_client, workspace_repository):
    """Distinct `updated_at` values must come back newest first."""
    base = utc_now()
    oldest = _seed_at(
        workspace_repository, title="Oldest", moment=base - timedelta(days=2)
    )
    middle = _seed_at(
        workspace_repository, title="Middle", moment=base - timedelta(days=1)
    )
    newest = _seed_at(workspace_repository, title="Newest", moment=base)

    body = workspace_client.get("/api/v1/workspaces?owner_user_id=local-user").json()

    assert [record["workspace_id"] for record in body["workspaces"]] == [
        newest.workspace_id,
        middle.workspace_id,
        oldest.workspace_id,
    ]


def test_list_breaks_a_full_tie_by_workspace_id_ascending(
    workspace_client, workspace_repository
):
    """Identical timestamps must fall back to ascending workspace_id."""
    moment = utc_now()
    high = _seed_at(
        workspace_repository, title="High", moment=moment, workspace_id="tw_zzzz0001"
    )
    low = _seed_at(
        workspace_repository, title="Low", moment=moment, workspace_id="tw_aaaa0001"
    )

    body = workspace_client.get("/api/v1/workspaces?owner_user_id=local-user").json()

    assert [record["workspace_id"] for record in body["workspaces"]] == [
        low.workspace_id,
        high.workspace_id,
    ]


def test_list_returns_empty_array_for_unknown_owner(workspace_client):
    _create(workspace_client)

    body = workspace_client.get("/api/v1/workspaces?owner_user_id=nobody").json()

    assert body == {"workspaces": []}


def test_list_strips_owner_scope_label(workspace_client):
    created = _create(workspace_client).json()

    body = workspace_client.get(
        "/api/v1/workspaces?owner_user_id=%20local-user%20"
    ).json()

    assert [r["workspace_id"] for r in body["workspaces"]] == [created["workspace_id"]]


# 6. Invalid create input returns 422 and creates no record.


@pytest.mark.parametrize(
    "overrides",
    [
        {"owner_user_id": "   "},
        {"title": "   "},
        {"title": LONG_TITLE},
        {"destination_scope": LONG_DESTINATION},
        {"planning_status": "draft"},
        {"planning_status": "retained"},
        {"planning_status": "unknown"},
        {"date_window": {"start_date": "2026-12-25", "end_date": "2026-12-20"}},
    ],
)
def test_invalid_create_returns_422_and_creates_no_record(workspace_client, overrides):
    response = _create(workspace_client, **overrides)
    assert response.status_code == 422

    body = workspace_client.get("/api/v1/workspaces?owner_user_id=local-user").json()
    assert body == {"workspaces": []}


def test_create_missing_required_fields_returns_422(workspace_client):
    response = workspace_client.post("/api/v1/workspaces", json={})
    assert response.status_code == 422


def test_create_ignores_caller_supplied_workspace_id(workspace_client):
    """Identity is server-owned; an extra field cannot dictate it."""
    response = _create(workspace_client, workspace_id="tw_caller_supplied")

    assert response.status_code == 201
    assert response.json()["workspace_id"] != "tw_caller_supplied"


def test_create_ignores_caller_supplied_retention_state(workspace_client):
    """R3 creates `active` records only, whatever the caller sends."""
    response = _create(workspace_client, retention_state="deleted")

    assert response.status_code == 201
    assert response.json()["retention_state"] == "active"


# 7. Route errors never echo full user-entered content.


def test_validation_error_does_not_echo_full_title(workspace_client):
    """A rejected title must not come back in the error body."""
    secret_title = "Honeymoon surprise in Da Lat for Linh" * 4
    response = workspace_client.post(
        "/api/v1/workspaces",
        json={"owner_user_id": "local-user", "title": secret_title},
    )

    assert response.status_code == 422
    assert secret_title not in response.text
    assert "Honeymoon" not in response.text
    assert "Linh" not in response.text


def test_validation_error_does_not_echo_full_destination(workspace_client):
    secret_destination = "Private villa address 27 Nguyen Hue " * 6
    response = workspace_client.post(
        "/api/v1/workspaces",
        json={
            "owner_user_id": "local-user",
            "title": "Trip",
            "destination_scope": secret_destination,
        },
    )

    assert response.status_code == 422
    assert secret_destination not in response.text
    assert "Nguyen Hue" not in response.text


def test_validation_error_does_not_leak_local_database_path(workspace_client):
    response = _create(workspace_client, planning_status="draft")
    assert response.status_code == 422
    assert ".sqlite3" not in response.text
    assert "/Users/" not in response.text


# Storage-failure path. These tests use the REAL dependency, not an override.


def test_incompatible_schema_returns_controlled_500_on_create(broken_storage_client):
    response = broken_storage_client.post(
        "/api/v1/workspaces",
        json={"owner_user_id": "local-user", "title": "Trip"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == STORAGE_ERROR_DETAIL


def test_incompatible_schema_returns_controlled_500_on_get(broken_storage_client):
    response = broken_storage_client.get("/api/v1/workspaces/tw_anything")

    assert response.status_code == 500
    assert response.json()["detail"] == STORAGE_ERROR_DETAIL


def test_incompatible_schema_returns_controlled_500_on_list(broken_storage_client):
    response = broken_storage_client.get("/api/v1/workspaces?owner_user_id=local-user")

    assert response.status_code == 500
    assert response.json()["detail"] == STORAGE_ERROR_DETAIL


def test_storage_failure_response_leaks_no_path_or_sql(broken_storage_client):
    response = broken_storage_client.post(
        "/api/v1/workspaces",
        json={"owner_user_id": "local-user", "title": "Trip"},
    )

    body = response.text
    assert response.status_code == 500
    assert ".sqlite3" not in body
    assert "/Users/" not in body
    assert "PRAGMA" not in body
    assert "user_version" not in body
    assert "CREATE TABLE" not in body


# Retention-state filtering. R3 routes create only `active` records, so these
# tests seed storage directly.


def test_list_excludes_deleted_records(workspace_client, workspace_repository):
    kept = _seed(
        workspace_repository, retention_state=RetentionState.ACTIVE, title="Active"
    )
    deleted = _seed(
        workspace_repository, retention_state=RetentionState.DELETED, title="Deleted"
    )

    body = workspace_client.get("/api/v1/workspaces?owner_user_id=local-user").json()

    ids = [record["workspace_id"] for record in body["workspaces"]]
    assert kept.workspace_id in ids
    assert deleted.workspace_id not in ids


def test_list_includes_active_archived_and_deletion_requested(
    workspace_client, workspace_repository
):
    expected = {
        _seed(
            workspace_repository,
            retention_state=RetentionState.ACTIVE,
            title="Active",
        ).workspace_id,
        _seed(
            workspace_repository,
            retention_state=RetentionState.ARCHIVED,
            title="Archived",
        ).workspace_id,
        _seed(
            workspace_repository,
            retention_state=RetentionState.DELETION_REQUESTED,
            title="Deletion requested",
        ).workspace_id,
    }
    _seed(workspace_repository, retention_state=RetentionState.DELETED, title="Deleted")

    body = workspace_client.get("/api/v1/workspaces?owner_user_id=local-user").json()

    assert {record["workspace_id"] for record in body["workspaces"]} == expected


def test_get_still_returns_a_deleted_record_by_id(
    workspace_client, workspace_repository
):
    """Retention filtering governs listing only; direct lookup is unchanged."""
    deleted = _seed(
        workspace_repository, retention_state=RetentionState.DELETED, title="Deleted"
    )

    response = workspace_client.get(f"/api/v1/workspaces/{deleted.workspace_id}")

    assert response.status_code == 200
    assert response.json()["retention_state"] == "deleted"


# 8 and 9. Existing health and chat contracts remain compatible.


def test_health_endpoint_remains_unchanged(workspace_client):
    response = workspace_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "Vietnam Travel Agent API"


def test_chat_still_rejects_empty_message(workspace_client):
    response = workspace_client.post("/api/v1/chat", json={"message": "   "})
    assert response.status_code == 400
    assert "cannot be empty" in response.json()["detail"]


def test_chat_response_contract_is_exactly_reply_model_citations(workspace_client):
    """R3 must not change the chat response shape."""
    fake = SimpleNamespace(
        generate_answer=lambda message, top_k=4: {
            "reply": "answer",
            "model": "stub-model",
            "citations": [{"title": "T", "url": "https://example.test"}],
        }
    )
    with patch.object(chat_module, "get_rag_service", return_value=fake):
        response = workspace_client.post("/api/v1/chat", json={"message": "Hanoi?"})

    assert response.status_code == 200
    assert set(response.json().keys()) == {"reply", "model", "citations"}


def test_chat_request_contract_ignores_a_workspace_id(workspace_client):
    """An extra workspace_id must not become part of the chat contract."""
    captured: dict[str, object] = {}

    def _capture(message, top_k=4):
        captured["message"] = message
        captured["top_k"] = top_k
        return {"reply": "answer", "model": "stub-model", "citations": []}

    fake = SimpleNamespace(generate_answer=_capture)
    with patch.object(chat_module, "get_rag_service", return_value=fake):
        response = workspace_client.post(
            "/api/v1/chat",
            json={"message": "Hanoi?", "workspace_id": "tw_anything"},
        )

    assert response.status_code == 200
    assert captured["message"] == "Hanoi?"
    assert "tw_anything" not in response.text


def test_workspace_routes_construct_no_rag_dependency(workspace_client):
    """Workspace routes must work with the RAG service unavailable."""

    def _explode():
        raise AssertionError("workspace routes must not construct the RAG service")

    with patch.object(chat_module, "get_rag_service", side_effect=_explode):
        created = _create(workspace_client)
        listed = workspace_client.get("/api/v1/workspaces?owner_user_id=local-user")

    assert created.status_code == 201
    assert listed.status_code == 200
