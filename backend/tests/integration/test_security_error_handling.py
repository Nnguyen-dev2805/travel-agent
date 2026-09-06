"""Integration tests for R9 request-size, CORS, and config-failure behavior.

Every test pins settings explicitly so ambient environment cannot change
outcomes. All tokens are synthetic fixtures. Controlled rejection bodies
must never echo request content or credential material.
"""

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
    assert response.json() == {"detail": "Request rejected."}


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
