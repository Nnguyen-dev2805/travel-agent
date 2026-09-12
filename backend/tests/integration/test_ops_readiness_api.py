"""Integration tests for the ops readiness surface.

Tests verify request-id middleware coverage on /health and readiness route.
No test touches a model provider, Chroma data creation, or external network.
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.config import settings
from backend.app.main import app
from backend.app.runtime_container import PostgresReadinessProbe, get_runtime_container
from backend.observability.readiness import EXPECTED_ALEMBIC_HEAD

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


def test_readiness_requires_authentication():
    client = TestClient(app)

    response = client.get("/api/v1/ops/readiness")
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


_AGGREGATE_PRECEDENCE = ("not_ready", "unknown", "degraded")


def _expected_aggregate(components: list[dict]) -> str:
    """Worst-state composition, restated here rather than imported.

    Importing `_compose_status` would make the assertion compare the function
    with itself. Restating the documented rule is what lets a broken composition
    fail this test.

    A component explicitly `disabled` does not participate: disabling an optional
    subsystem is not a degradation of the instance, and counting it would report
    every deployment with the memory pipeline off as not ready.

    A **non-critical** component does not participate either. `ops.py` maps any
    aggregate other than `ready` to HTTP 503, which is what a load balancer reads,
    so a stalled background worker must not take a healthy chat instance out of
    rotation. The component is still in the response — it just does not decide.
    """
    states = {
        item["status"]
        for item in components
        if item.get("critical", True) and item.get("reason_code") != "disabled"
    }
    for state in _AGGREGATE_PRECEDENCE:
        if state in states:
            return state
    return "ready"


def _expected_http_status(aggregate: str) -> int:
    """The route maps anything other than `ready` to 503."""
    return 200 if aggregate == "ready" else 503


def test_readiness_route_returns_components_with_request_id(readiness_container):
    client = TestClient(app)

    response = client.get(
        "/api/v1/ops/readiness",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
    )

    body = response.json()
    # The aggregate must follow from the components the response itself reports.
    # Previously any of the four enum values was accepted, so a `degraded` report
    # satisfied a healthy-path expectation and the test could not tell the two
    # apart.
    expected = _expected_aggregate(body["components"])
    assert body["status"] == expected, (body["status"], body["components"])
    assert response.status_code == _expected_http_status(expected)
    assert {item["name"] for item in body["components"]} >= {
        "app",
        "model_provider",
        "rag_chroma",
        "database",
        "alembic",
        "memory_write_pipeline",
    }
    assert response.headers["X-Request-ID"].startswith("rq_")


@pytest.fixture
def readiness_container(tmp_path: Path, monkeypatch):
    """A composed container for the ops route, with no real database behind it.

    These tests used to rely on the lazy container the request dependency built on
    demand. That container resolved `DATABASE_URL` from `.env`, so the readiness
    surface was being exercised against the *development* database — and the suite
    passed or failed depending on whether that database happened to be reachable.
    ADR 0035 makes the dependency fail closed; this fixture is the replacement, and
    it is also the honest one: the route is handed a container the test composed.
    """
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_mock_token_12345")

    class MockEngine:
        """Strict probe engine: an unrecognised statement is a failure.

        The previous version returned `(1,)` for every statement, so it validated
        no SQL at all — a probe query that changed shape, or was simply broken,
        still produced a healthy snapshot.
        """

        _RECOGNISED = (
            "select 1",
            "alembic_version",
            "conversation_outbox",
            "ready_outbox_event_count",
            "oldest_ready_outbox_event_age_seconds",
            "dead_letter_outbox_event_count",
        )

        def connect(self):
            class MockConn:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *args):
                    pass

                def execute(self_inner, stmt):
                    statement = str(stmt).lower()
                    assert any(
                        token in statement for token in MockEngine._RECOGNISED
                    ), (
                        "the readiness probe issued an unrecognised statement, so "
                        f"this mock validates nothing: {statement[:120]}"
                    )
                    # Both access styles, because the probes use both: `.first()`
                    # for the row-shaped reads and `.scalar()` for the outbox
                    # signals. A mock that only supports one turns the other into a
                    # `MagicMock` and the probe into a silent failure.
                    if "alembic_version" in statement:
                        return MagicMock(
                            first=lambda: (EXPECTED_ALEMBIC_HEAD,),
                            scalar=lambda: EXPECTED_ALEMBIC_HEAD,
                        )
                    return MagicMock(first=lambda: (0,), scalar=lambda: 0)

            return MockConn()

    class MockContainer:
        def __init__(self):
            self.engine = MockEngine()
            self._readiness_probe = PostgresReadinessProbe(self.engine)
            self.chroma_dir = tmp_path
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            seed_client = chromadb.PersistentClient(
                path=str(tmp_path),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            seed_collection = seed_client.get_or_create_collection(
                name="vietnam_travel_parent_child"
            )
            seed_collection.add(
                ids=["seed_1"],
                documents=["seed document"],
                embeddings=[[0.1, 0.2, 0.3]],
            )

        def readiness_probe(self):
            return self._readiness_probe

        def count_ready_outbox_events(self):
            return 0

        def oldest_ready_outbox_event_age_seconds(self):
            return 0

        def dead_letter_outbox_event_count(self):
            return 0

    app.dependency_overrides[get_runtime_container] = lambda: MockContainer()
    yield
    app.dependency_overrides.pop(get_runtime_container, None)


def test_readiness_route_healthy_returns_200(readiness_container):
    client = TestClient(app)
    response = client.get(
        "/api/v1/ops/readiness",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"


def test_readiness_response_carries_no_paths_tokens_or_content(readiness_container):
    client = TestClient(app)

    body = client.get(
        "/api/v1/ops/readiness",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
    ).text

    assert "sk-" not in body
    assert "ghp_" not in body
    assert "/Users/" not in body
    assert "prompt" not in body.lower()
