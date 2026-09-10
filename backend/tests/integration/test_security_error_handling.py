"""Integration tests for request-size, CORS, and config-failure behavior.

Every test pins settings explicitly so ambient environment cannot change outcomes.
Controlled rejection bodies must never echo request content or credential material.
"""

import json
import logging
from pathlib import Path
from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from backend.app.config import settings
from backend.app.main import app
from backend.security.dependencies import resolve_cors_origins
from backend.security.models import SecurityConfigurationError

SENTINEL_TITLE = "NEVER_LOG_OVERSIZED_TITLE " + "x" * 5000
AUTH_TOKEN = "secret-alpha-token"
REGISTRY = '{"owner_a": "secret-alpha-token"}'


@pytest.fixture(autouse=True)
def _setup_auth(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_AUTH_TOKENS_JSON", SecretStr(REGISTRY))


def test_oversized_request_returns_413_without_echo(monkeypatch):
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_BYTES", 64)
    client = TestClient(app)

    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        json={"message": SENTINEL_TITLE},
    )

    assert response.status_code == 413
    assert "NEVER_LOG_OVERSIZED_TITLE" not in response.text


def test_invalid_body_limit_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_BYTES", 0)
    client = TestClient(app)

    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        json={"message": "Da Nang"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Request rejected."
    assert body["request_id"].startswith("rq_")
    assert response.headers["X-Request-ID"] == body["request_id"]


def test_wildcard_cors_rejected(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_CORS_ORIGINS", "https://x.test, *")

    with pytest.raises(SecurityConfigurationError):
        resolve_cors_origins()


def test_malformed_registry_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_AUTH_TOKENS_JSON", SecretStr("not-json{{{"))
    client = TestClient(app)

    response = client.get(
        "/api/v1/ops/readiness", headers={"Authorization": "Bearer x"}
    )

    assert response.status_code == 500
    assert "not-json" not in response.text
    assert response.headers["X-Request-ID"].startswith("rq_")


def test_unhandled_exception_returns_generic_correlated_500(monkeypatch, caplog):
    from backend.app.api.conversations import get_conversation_service

    def _exploding_service():
        raise RuntimeError("NEVER_LOG_RUNTIME_SECRET")

    app.dependency_overrides[get_conversation_service] = _exploding_service
    try:
        client = TestClient(app, raise_server_exceptions=False)
        with caplog.at_level(logging.INFO, logger="travel_agent_observability"):
            response = client.get(
                "/api/v1/conversations",
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            )
    finally:
        app.dependency_overrides.pop(get_conversation_service, None)

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error."
    assert body["request_id"].startswith("rq_")
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert "NEVER_LOG_RUNTIME_SECRET" not in response.text
    completions = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "travel_agent_observability"
        and "api.request.completed" in record.message
    ]
    assert completions, "expected one request completion event"
    assert completions[0]["request_id"] == body["request_id"]
    assert completions[0]["failure_class"] == "RuntimeError"
