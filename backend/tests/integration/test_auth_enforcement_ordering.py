"""Integration tests for the authentication enforcement ordering (ADR 0026).

The finding: authentication was enforced by a route dependency, and FastAPI
parses the request body *before* it solves dependencies. A body that is not
valid JSON therefore produced `422` without the authentication decision running
at all. These tests pin the corrected behaviour end to end, over the real
application object.

The `TestClient` is deliberately not used as a context manager, so the
application lifespan never runs and no database or model endpoint is needed.
"""

import logging
import re

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.config import settings
from backend.app.main import app
from backend.app.runtime_container import (
    get_conversation_orchestrator,
    get_conversation_service,
)
from backend.security.dependencies import is_public_path, resolve_cors_origins

TOKEN = "token-alice-123"
REGISTRY = f'{{"alice": "{TOKEN}"}}'
AUTHED = {"Authorization": f"Bearer {TOKEN}"}
BAD = {"Authorization": "Bearer not-a-real-token"}
ORIGIN = resolve_cors_origins()[0]

CHAT = f"{settings.API_V1_STR}/chat"
CONVERSATIONS = f"{settings.API_V1_STR}/conversations"

MALFORMED = '{"message": "hi"'  # truncated JSON: a *parse* error
VALID = '{"message": "hi"}'
WRONG_SHAPE = '{"unexpected": 1}'  # valid JSON, invalid schema

BODY_LIMIT = 128
OVERSIZED = '{"message": "' + ("x" * (BODY_LIMIT * 2)) + '"}'


@pytest.fixture(autouse=True)
def configured_registry(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_AUTH_TOKENS_JSON", SecretStr(REGISTRY))


@pytest.fixture
def client():
    app.dependency_overrides[get_conversation_orchestrator] = lambda: object()
    app.dependency_overrides[get_conversation_service] = lambda: object()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def small_body_limit(monkeypatch):
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_BYTES", BODY_LIMIT)


def _post(client, path, body, headers=None, origin=False):
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    if origin:
        request_headers["Origin"] = ORIGIN
    return client.post(path, content=body.encode(), headers=request_headers)


def _mounted_api_routes():
    """(method, concrete path) for every mounted route under the API prefix.

    Enumerated from the OpenAPI schema, which is how the boundary suite already
    reads the mounted surface. `app.routes` cannot be walked directly here: this
    FastAPI version wraps an included router in a `_IncludedRouter` whose `path`
    is `None`.
    """
    found = []
    for path, path_item in app.openapi().get("paths", {}).items():
        if not path.startswith(settings.API_V1_STR):
            continue
        concrete = re.sub(r"\{[^}]+\}", "probe", path)
        for method in path_item:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                found.append((method.upper(), concrete))
    return found


# --------------------------------------------------------------------------
# The case table is the finding
# --------------------------------------------------------------------------

CASES = [
    ("malformed body, no header", CHAT, MALFORMED, {}, 401),
    ("malformed body, invalid token", CHAT, MALFORMED, BAD, 401),
    ("malformed body, valid token", CHAT, MALFORMED, AUTHED, 422),
    ("valid body, no header", CHAT, VALID, {}, 401),
    ("valid body, invalid token", CHAT, VALID, BAD, 401),
    ("wrong-shape body, no header", CHAT, WRONG_SHAPE, {}, 401),
    ("malformed body, no header (conversations)", CONVERSATIONS, MALFORMED, {}, 401),
]


@pytest.mark.parametrize(
    "label,path,body,headers,expected", CASES, ids=[case[0] for case in CASES]
)
def test_status_case_table(client, label, path, body, headers, expected):
    response = _post(client, path, body, headers)
    assert response.status_code == expected, f"{label}: {response.text[:120]}"


def test_a_rejected_token_is_not_treated_as_an_absent_one(client):
    """The defect was that both produced 422 on a malformed body, so the
    authentication decision was skipped rather than merely deferred."""
    absent = _post(client, CHAT, MALFORMED, {})
    rejected = _post(client, CHAT, MALFORMED, BAD)
    assert absent.status_code == rejected.status_code == 401


def test_an_authenticated_malformed_body_still_reports_a_schema_error(client):
    """The control: the middleware must let a valid request through to routing."""
    response = _post(client, CHAT, MALFORMED, AUTHED)
    assert response.status_code == 422


# --------------------------------------------------------------------------
# The rejection must be usable by the client
# --------------------------------------------------------------------------


def test_an_unauthenticated_rejection_carries_cors_headers(client):
    """Without this a browser sees an opaque network error, not a 401, because
    an early response from a middleware outside CORSMiddleware bypasses it."""
    response = _post(client, CHAT, VALID, origin=True)
    assert response.status_code == 401
    assert response.headers.get("access-control-allow-origin") == ORIGIN


def test_an_unauthenticated_rejection_carries_a_request_id(client):
    response = _post(client, CHAT, VALID)
    assert response.headers["X-Request-ID"].startswith("rq_")


def test_a_preflight_request_is_not_answered_401(client):
    """A preflight carries no credentials by definition. If it reached the
    authentication check, every browser request would fail before it was sent."""
    response = client.options(
        CHAT,
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200, response.text[:120]
    assert response.headers.get("access-control-allow-origin") == ORIGIN


# --------------------------------------------------------------------------
# Default-deny, over the mounted route table
# --------------------------------------------------------------------------


def test_the_route_inventory_is_not_vacuous(client):
    routes = _mounted_api_routes()
    assert len(routes) >= 7, routes
    assert ("POST", CHAT) in routes
    assert ("POST", CONVERSATIONS) in routes
    assert ("GET", f"{CONVERSATIONS}/probe/messages") in routes


def test_every_mounted_api_route_rejects_an_unauthenticated_request(client):
    """A route added later is covered without anyone remembering to guard it."""
    for method, path in _mounted_api_routes():
        assert not is_public_path(path), path
        response = client.request(method, path)
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}"


def test_an_unknown_path_is_rejected_too(client):
    """Default-deny covers paths that match no route, so an unauthenticated
    caller cannot enumerate the surface by comparing 401 against 404."""
    response = client.get(f"{settings.API_V1_STR}/does-not-exist")
    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/health", "/openapi.json", "/docs", "/redoc"])
def test_public_paths_are_reachable_without_credentials(client, path):
    """The allowlist must match reality, or a rename silently closes /health."""
    assert client.get(path).status_code != 401, path


# --------------------------------------------------------------------------
# Body-limit interaction
# --------------------------------------------------------------------------


def test_an_oversized_body_without_credentials_is_rejected_as_unauthenticated(
    client, small_body_limit
):
    """Authentication runs first, so an unauthenticated caller cannot learn the
    body limit by probing it."""
    response = _post(client, CHAT, OVERSIZED)
    assert response.status_code == 401


def test_an_oversized_body_with_credentials_is_still_rejected_as_too_large(
    client, small_body_limit
):
    """The size limit must survive the reordering."""
    response = _post(client, CHAT, OVERSIZED, AUTHED)
    assert response.status_code == 413


# --------------------------------------------------------------------------
# The early rejections are visible in the event stream
# --------------------------------------------------------------------------


def test_an_unauthenticated_rejection_emits_a_completion_event(client, caplog):
    with caplog.at_level(logging.INFO):
        _post(client, CHAT, VALID)
    assert '"status_code": 401' in caplog.text


def test_an_oversized_body_emits_a_completion_event(
    client, small_body_limit, caplog
):
    """This path returned before the emission point and appeared nowhere in the
    event stream. The change unifies the exits."""
    with caplog.at_level(logging.INFO):
        _post(client, CHAT, OVERSIZED, AUTHED)
    assert '"status_code": 413' in caplog.text


def test_the_event_carries_no_body_or_query_string(client, caplog):
    with caplog.at_level(logging.INFO):
        _post(client, CHAT, '{"message": "secret-marker"}', {})
    assert "secret-marker" not in caplog.text
