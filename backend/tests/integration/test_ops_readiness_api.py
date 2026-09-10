"""Integration tests for the ops readiness surface.

Tests verify request-id middleware coverage on /health and readiness route.
No test touches a model provider, Chroma data creation, or external network.
"""

import logging
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.config import settings
from backend.app.main import app

AUTH_TOKEN = "ops-test-token"
REGISTRY = '{"ops_admin": "ops-test-token"}'


@pytest.fixture(autouse=True)
def _setup_auth(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_AUTH_TOKENS_JSON", SecretStr(REGISTRY))


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


def test_readiness_route_returns_components_with_request_id():
    client = TestClient(app)

    response = client.get(
        "/api/v1/ops/readiness",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ready", "degraded", "not_ready", "unknown")
    assert {item["name"] for item in body["components"]} >= {
        "app",
        "model_provider",
        "rag_chroma",
        "database",
        "memory_write_pipeline",
    }
    assert response.headers["X-Request-ID"].startswith("rq_")


def test_readiness_response_carries_no_paths_tokens_or_content():
    client = TestClient(app)

    body = client.get(
        "/api/v1/ops/readiness",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
    ).text

    assert "sk-" not in body
    assert "ghp_" not in body
    assert "/Users/" not in body
    assert "prompt" not in body.lower()
