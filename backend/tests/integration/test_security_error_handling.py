"""Integration tests for R9 request-size, CORS, and config-failure behavior.

Every test pins settings explicitly so ambient environment cannot change
outcomes. All tokens are synthetic fixtures. Controlled rejection bodies
must never echo request content or credential material.
"""

from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from backend.app.config import settings
from backend.app.main import app
from backend.security.dependencies import resolve_cors_origins
from backend.security.models import SecurityConfigurationError

SENTINEL_TITLE = "NEVER_LOG_OVERSIZED_TITLE " + "x" * 5000


def _auth_on(monkeypatch, registry='{"owner_a": "secret-alpha-token"}'):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    monkeypatch.setattr(settings, "LOCAL_AUTH_TOKENS_JSON", SecretStr(registry))


def test_oversized_request_returns_413_without_echo(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False)
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_BYTES", 64)
    client = TestClient(app)

    response = client.post(
        "/api/v1/workspaces",
        json={"owner_user_id": "owner_a", "title": SENTINEL_TITLE},
    )

    assert response.status_code == 413
    assert "NEVER_LOG_OVERSIZED_TITLE" not in response.text


def test_invalid_body_limit_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False)
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_BYTES", 0)
    client = TestClient(app)

    response = client.post(
        "/api/v1/workspaces",
        json={"owner_user_id": "owner_a", "title": "Da Nang"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Request rejected."
    assert body["request_id"].startswith("rq_")
    assert response.headers["X-Request-ID"] == body["request_id"]


def test_chunked_body_without_length_still_parses(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False)
    monkeypatch.setattr(settings, "APP_DB_PATH", tmp_path / "t.sqlite3")
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_BYTES", 1024 * 1024)
    client = TestClient(app)

    def _chunks():
        payload = b'{"owner_user_id": "owner_a", "title": "Da Nang"}'
        yield payload[:16]
        yield payload[16:]

    response = client.post(
        "/api/v1/workspaces",
        content=_chunks(),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 201
    assert response.json()["title"] == "Da Nang"


def test_wildcard_cors_rejected_when_auth_enabled(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    monkeypatch.setattr(settings, "ALLOWED_CORS_ORIGINS", "https://x.test, *")

    with pytest.raises(SecurityConfigurationError):
        resolve_cors_origins()


def test_compat_mode_keeps_local_cors(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False)

    origins = resolve_cors_origins()

    assert "http://localhost:5173" in origins


def test_malformed_registry_fails_closed_not_compat(monkeypatch):
    _auth_on(monkeypatch, registry="not-json{{{")
    client = TestClient(app)

    response = client.get(
        "/api/v1/ops/readiness", headers={"Authorization": "Bearer x"}
    )

    assert response.status_code == 500
    assert "not-json" not in response.text
    assert response.headers["X-Request-ID"].startswith("rq_")


def test_unhandled_exception_returns_generic_correlated_500(monkeypatch, caplog):
    import json
    import logging

    from backend.app.api.workspaces import get_workspace_service

    monkeypatch.setattr(settings, "AUTH_REQUIRED", False)

    def _exploding_service():
        raise RuntimeError("NEVER_LOG_RUNTIME_SECRET")

    app.dependency_overrides[get_workspace_service] = _exploding_service
    try:
        # Unhandled exceptions always propagate out of the ASGI app, so
        # the default client would re-raise instead of returning the
        # handler response. Disabling that re-raise is the documented
        # pattern for asserting error-response contracts.
        client = TestClient(app, raise_server_exceptions=False)
        with caplog.at_level(logging.INFO, logger="travel_agent_observability"):
            response = client.get(
                "/api/v1/workspaces", params={"owner_user_id": "owner_a"}
            )
    finally:
        app.dependency_overrides.pop(get_workspace_service, None)

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


def test_storage_exception_returns_controlled_500_without_content(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False)
    monkeypatch.setattr(settings, "APP_DB_PATH", tmp_path)
    client = TestClient(app)

    response = client.get("/api/v1/workspaces", params={"owner_user_id": "owner_a"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Workspace storage is unavailable."}
    assert response.headers["X-Request-ID"].startswith("rq_")
