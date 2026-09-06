"""Integration tests for the R8 ops readiness surface.

Task 3 starts this file with request-id middleware coverage on the
compatibility `/health` endpoint; Task 5 extends it with readiness route
tests. No test touches a model provider, Chroma data creation, or the
network.
"""

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.main import app


@pytest.fixture(autouse=True)
def _compat_auth(monkeypatch):
    """Pin compatibility mode: R9 auth must not change these R8 expectations."""
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False)


def test_health_body_unchanged_with_request_id_header(caplog):
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="travel_agent_observability"):
        first = client.get("/health")
        second = client.get("/health")

    assert first.status_code == 200
    assert first.json() == {"status": "ok", "service": settings.PROJECT_NAME}
    assert first.headers["X-Request-ID"].startswith("rq_")
    assert second.headers["X-Request-ID"].startswith("rq_")
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]
    assert "message=" not in caplog.text
    assert "query_string" not in caplog.text


def test_readiness_route_returns_components_with_request_id(tmp_path: Path):
    client = TestClient(app)

    response = client.get("/api/v1/ops/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ready", "degraded", "not_ready", "unknown")
    assert {item["name"] for item in body["components"]} >= {
        "app",
        "model_provider",
        "rag_chroma",
        "app_db",
        "memory",
        "planner",
        "evaluation_reports",
    }
    assert response.headers["X-Request-ID"].startswith("rq_")


def test_readiness_response_carries_no_paths_tokens_or_content():
    client = TestClient(app)

    body = client.get("/api/v1/ops/readiness").text

    assert "sk-" not in body
    assert "ghp_" not in body
    assert "/Users/" not in body
    assert "prompt" not in body.lower()


def test_readiness_route_does_not_create_missing_db(tmp_path: Path, monkeypatch):
    missing = tmp_path / "absent.sqlite3"
    monkeypatch.setattr(settings, "APP_DB_PATH", missing)
    client = TestClient(app)

    response = client.get("/api/v1/ops/readiness")

    assert response.status_code == 200
    assert not missing.exists()
