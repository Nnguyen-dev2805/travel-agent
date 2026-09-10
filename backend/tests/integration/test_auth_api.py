"""Integration tests for route authentication behavior.

All tokens are synthetic fixtures.
Authentication is always enforced on /api/v1/* routes.
/health remains open without authentication.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.config import settings
from backend.app.main import app

OWNER_A_TOKEN = "secret-alpha-token"
OWNER_B_TOKEN = "secret-beta-token"
REGISTRY = '{"owner_a": "secret-alpha-token", "owner_b": "secret-beta-token"}'


@pytest.fixture(autouse=True)
def _setup_auth(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_AUTH_TOKENS_JSON", SecretStr(REGISTRY))


def test_auth_rejects_missing_token_with_401():
    client = TestClient(app)

    response = client.get("/api/v1/ops/readiness")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


def test_auth_rejects_invalid_token_with_401():
    client = TestClient(app)

    response = client.get(
        "/api/v1/ops/readiness", headers={"Authorization": "Bearer wrong-token"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid bearer token."}
    assert "wrong-token" not in response.text


def test_auth_accepts_valid_token():
    client = TestClient(app)

    response = client.get(
        "/api/v1/ops/readiness",
        headers={"Authorization": f"Bearer {OWNER_A_TOKEN}"},
    )

    assert response.status_code in (200, 503)
    assert response.status_code != 401
    assert OWNER_A_TOKEN not in response.text


def test_health_open_without_auth():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code in (200, 503)
    assert response.status_code != 401
    assert response.json()["status"] == "ok"
