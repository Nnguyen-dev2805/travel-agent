"""Integration tests for R9 route authentication behavior.

Every test pins the auth gate explicitly through settings overrides, so no
test depends on ambient environment variables. All tokens are synthetic
fixtures. No test touches a model provider, Chroma, or the network.
"""

from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.config import settings
from backend.app.main import app

OWNER_A_TOKEN = "secret-alpha-token"
OWNER_B_TOKEN = "secret-beta-token"

REGISTRY = '{"owner_a": "secret-alpha-token", "owner_b": "secret-beta-token"}'


def _auth_on(monkeypatch, registry=REGISTRY):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    monkeypatch.setattr(settings, "LOCAL_AUTH_TOKENS_JSON", SecretStr(registry))


def _auth_off(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False)


def _workspace_payload(**overrides):
    payload = {
        "title": "Da Nang family trip",
        "destination_scope": "Da Nang",
    }
    payload.update(overrides)
    return payload


def test_compat_mode_allows_health_and_product_without_token(monkeypatch):
    _auth_off(monkeypatch)
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    response = client.post(
        "/api/v1/workspaces", json=_workspace_payload(owner_user_id="owner_a")
    )
    assert response.status_code == 201


def test_auth_rejects_missing_token_with_401(monkeypatch):
    _auth_on(monkeypatch)
    client = TestClient(app)

    response = client.get("/api/v1/ops/readiness")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


def test_auth_rejects_invalid_token_with_401(monkeypatch):
    _auth_on(monkeypatch)
    client = TestClient(app)

    response = client.get(
        "/api/v1/ops/readiness", headers={"Authorization": "Bearer wrong-token"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid bearer token."}
    assert "wrong-token" not in response.text


def test_auth_accepts_valid_token(monkeypatch):
    _auth_on(monkeypatch)
    client = TestClient(app)

    response = client.get(
        "/api/v1/ops/readiness",
        headers={"Authorization": f"Bearer {OWNER_A_TOKEN}"},
    )

    assert response.status_code == 200
    assert OWNER_A_TOKEN not in response.text


def test_health_open_without_auth_when_gate_on(monkeypatch):
    _auth_on(monkeypatch)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
