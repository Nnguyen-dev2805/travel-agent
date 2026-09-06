"""Integration tests for the R8 ops readiness surface.

Task 3 starts this file with request-id middleware coverage on the
compatibility `/health` endpoint; Task 5 extends it with readiness route
tests. No test touches a model provider, Chroma data creation, or the
network.
"""

import logging

from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.main import app


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
