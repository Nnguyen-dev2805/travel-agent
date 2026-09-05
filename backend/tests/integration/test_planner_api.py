"""Integration tests for the R7 planner routes.

Every test overrides the planner service dependency with repositories over
an isolated temporary SQLite database, so no test reads or writes the
developer database at `APP_DB_PATH`. No test constructs a RAG service, an
embedding model, a Chroma collection, a memory service, or a
model-provider client.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.planner import get_planner_service
from backend.app.main import app
from backend.planner.service import PlannerService
from backend.planner.sqlite_repository import SQLitePlannerRepository
from backend.workspaces.models import (
    PlanningStatus,
    RetentionState,
    TripWorkspace,
    generate_workspace_id,
)
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository
from backend.conversations.sqlite_repository import SQLiteConversationRepository

MOMENT = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


def _client(db_path: Path) -> TestClient:
    """Client bound to a throwaway database without lifespan warm-up."""
    service = PlannerService(
        planner_repository=SQLitePlannerRepository(db_path=db_path),
        workspace_repository=SQLiteWorkspaceRepository(db_path=db_path),
        conversation_repository=SQLiteConversationRepository(db_path=db_path),
    )
    app.dependency_overrides[get_planner_service] = lambda: service
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_planner_service, None)


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


def _itinerary_payload(**overrides):
    payload = {
        "status": "draft",
        "title": "Hà Nội 3 ngày",
        "items": [
            {
                "day_index": 1,
                "position": 1,
                "item_type": "meal",
                "title": "Bún chả Hương Liên",
            }
        ],
    }
    payload.update(overrides)
    return payload


def _decision_payload(**overrides):
    payload = {
        "decision_type": "preference",
        "status": "pending",
        "statement": "Chuyến này ăn chay.",
    }
    payload.update(overrides)
    return payload


def test_create_get_list_itineraries(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(db_path)
    url = f"/api/v1/workspaces/{workspace_id}/planner/itineraries"

    created = client.post(url, json=_itinerary_payload()).json()
    assert created["itinerary_version_id"].startswith("itv_")
    assert created["version_number"] == 1
    assert created["status"] == "draft"
    assert created["items"][0]["title"] == "Bún chả Hương Liên"

    fetched = client.get(f"{url}/{created['itinerary_version_id']}").json()
    assert fetched == created

    listed = client.get(url).json()
    assert [item["itinerary_version_id"] for item in listed] == [
        created["itinerary_version_id"]
    ]


def test_accept_supersedes_prior_accepted(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(db_path)
    url = f"/api/v1/workspaces/{workspace_id}/planner/itineraries"
    first = client.post(url, json=_itinerary_payload()).json()
    second = client.post(url, json=_itinerary_payload()).json()
    client.post(f"{url}/{first['itinerary_version_id']}/accept")

    accepted = client.post(f"{url}/{second['itinerary_version_id']}/accept").json()

    assert accepted["status"] == "accepted"
    assert (
        client.get(f"{url}/{first['itinerary_version_id']}").json()["status"]
        == "superseded"
    )


def test_archive_itinerary(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(db_path)
    url = f"/api/v1/workspaces/{workspace_id}/planner/itineraries"
    created = client.post(url, json=_itinerary_payload()).json()

    archived = client.post(f"{url}/{created['itinerary_version_id']}/archive").json()

    assert archived["status"] == "archived"


def test_record_list_update_decisions_and_replacement(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(db_path)
    url = f"/api/v1/workspaces/{workspace_id}/planner/decisions"

    old = client.post(url, json=_decision_payload()).json()
    assert old["decision_id"].startswith("td_")
    assert old["status"] == "pending"

    accepted = client.patch(
        f"{url}/{old['decision_id']}", json={"status": "accepted"}
    ).json()
    assert accepted["status"] == "accepted"

    replacement = client.post(
        url,
        json=_decision_payload(supersedes_decision_id=old["decision_id"]),
    ).json()
    assert replacement["supersedes_decision_id"] == old["decision_id"]
    listed = client.get(url).json()
    by_id = {item["decision_id"]: item for item in listed}
    assert by_id[old["decision_id"]]["status"] == "superseded"

    operations = client.get(
        f"/api/v1/workspaces/{workspace_id}/planner/operations"
    ).json()
    assert [item["operation_type"] for item in operations] == [
        "supersede_decision",
        "update_decision_status",
        "record_decision",
    ]


def test_rejected_decisions_stay_listable(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(db_path)
    url = f"/api/v1/workspaces/{workspace_id}/planner/decisions"
    rejected = client.post(url, json=_decision_payload(status="rejected")).json()

    listed = client.get(url, params={"status": "rejected"}).json()

    assert [item["decision_id"] for item in listed] == [rejected["decision_id"]]


def test_invalid_bodies_return_422(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(db_path)
    itinerary_url = f"/api/v1/workspaces/{workspace_id}/planner/itineraries"
    decision_url = f"/api/v1/workspaces/{workspace_id}/planner/decisions"

    assert (
        client.post(itinerary_url, json=_itinerary_payload(status="flying")).status_code
        == 422
    )
    assert (
        client.post(
            itinerary_url, json=_itinerary_payload(unknown_field="x")
        ).status_code
        == 422
    )
    assert (
        client.post(decision_url, json=_decision_payload(statement="   ")).status_code
        == 422
    )


def test_missing_workspace_returns_404(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _client(db_path)

    assert (
        client.post(
            "/api/v1/workspaces/tw_missing/planner/itineraries",
            json=_itinerary_payload(),
        ).status_code
        == 404
    )
    assert (
        client.get("/api/v1/workspaces/tw_missing/planner/operations").status_code
        == 404
    )


def test_cross_workspace_ids_return_404(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(db_path)
    other = _workspace_id(db_path)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/planner/itineraries",
        json=_itinerary_payload(),
    ).json()

    assert (
        client.get(
            f"/api/v1/workspaces/{other}/planner/itineraries/"
            f"{created['itinerary_version_id']}"
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/workspaces/{other}/planner/itineraries/"
            f"{created['itinerary_version_id']}/accept"
        ).status_code
        == 404
    )


def test_invalid_transitions_return_409(tmp_path: Path):
    db_path = tmp_path / "travel_agent.sqlite3"
    client = _client(db_path)
    workspace_id = _workspace_id(db_path)
    itinerary_url = f"/api/v1/workspaces/{workspace_id}/planner/itineraries"
    decision_url = f"/api/v1/workspaces/{workspace_id}/planner/decisions"
    created = client.post(itinerary_url, json=_itinerary_payload()).json()
    client.post(f"{itinerary_url}/{created['itinerary_version_id']}/accept")

    assert (
        client.post(
            f"{itinerary_url}/{created['itinerary_version_id']}/archive"
        ).status_code
        == 409
    )
    decision = client.post(decision_url, json=_decision_payload()).json()
    assert (
        client.patch(
            f"{decision_url}/{decision['decision_id']}",
            json={"status": "superseded"},
        ).status_code
        == 409
    )
