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
from backend.app.runtime_container import get_runtime_container

OWNER_A_TOKEN = "secret-alpha-token"
OWNER_B_TOKEN = "secret-beta-token"
REGISTRY = '{"owner_a": "secret-alpha-token", "owner_b": "secret-beta-token"}'


class _ComposedContainer:
    """A container this test composed, standing in for the lifespan's.

    `get_runtime_container` used to build a production container on demand, and that
    container resolved `DATABASE_URL` from `.env` — so this test reached the
    *development* database to produce a readiness snapshot. ADR 0035 makes the
    dependency fail closed, because a request that finds no container is a process
    that never composed itself.

    This test is about the token being accepted, not about what the snapshot says,
    so it supplies the minimum container the route needs.
    """

    class _Probe:
        def check(self):
            return {"status": "ready", "database": "postgresql"}

        def check_revision(self, expected_revision=None):
            return {"status": "ready", "revision": expected_revision}

    def readiness_probe(self):
        return self._Probe()

    def count_ready_outbox_events(self):
        return 0

    def oldest_ready_outbox_event_age_seconds(self):
        return 0

    def dead_letter_outbox_event_count(self):
        return 0


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
    # The container the lifespan would have bound. Without it the dependency now
    # fails closed, which is the behaviour under test elsewhere and would mask the
    # token assertion here.
    app.dependency_overrides[get_runtime_container] = _ComposedContainer
    try:
        client = TestClient(app)

        response = client.get(
            "/api/v1/ops/readiness",
            headers={"Authorization": f"Bearer {OWNER_A_TOKEN}"},
        )

        assert response.status_code in (200, 503), response.text[:200]
        body = response.json()
        # A valid token must produce the readiness snapshot, not an error envelope.
        # The previous `!= 401` line was redundant — `401` is not in `(200, 503)` —
        # so the pair asserted nothing beyond its first line. This asserts what
        # acceptance actually looks like, which a 200- or 503-shaped error would not
        # satisfy.
        assert "components" in body, body
        assert "detail" not in body, body
        assert OWNER_A_TOKEN not in response.text
    finally:
        app.dependency_overrides.pop(get_runtime_container, None)


def test_health_open_without_auth():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code in (200, 503)
    assert response.status_code != 401
    assert response.json()["status"] == "ok"
