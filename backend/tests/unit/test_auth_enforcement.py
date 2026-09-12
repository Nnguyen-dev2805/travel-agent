"""Unit tests for the authentication enforcement point (ADR 0026).

The control lives in `enforce_authentication`, which runs before routing and
therefore before the request body is parsed. `require_principal` is an accessor
of the principal the middleware resolved; it no longer resolves credentials.

These tests are unit-level: they build a `Request` directly rather than going
through a client, so they can assert what the middleware does *not* touch.
"""

import json

import pytest
from fastapi import HTTPException, Request
from pydantic import SecretStr

from backend.app.config import settings
from backend.security.dependencies import (
    enforce_authentication,
    is_public_path,
    require_principal,
)

TOKEN = "token-alice-123"
REGISTRY = f'{{"alice": "{TOKEN}"}}'


@pytest.fixture(autouse=True)
def configured_registry(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_AUTH_TOKENS_JSON", SecretStr(REGISTRY))


def _request(path: str, headers: dict | None = None) -> Request:
    """Build a bare request. No receive channel: nothing here reads a body."""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [
                (name.lower().encode(), value.encode())
                for name, value in (headers or {}).items()
            ],
        }
    )


def _detail(response) -> dict:
    return json.loads(response.body)


def _bearer() -> dict:
    return {"authorization": f"Bearer {TOKEN}"}


# --------------------------------------------------------------------------
# The public surface is an allowlist
# --------------------------------------------------------------------------


def test_health_is_public():
    assert is_public_path("/health") is True


def test_documentation_paths_are_public():
    for path in ("/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"):
        assert is_public_path(path) is True, path


def test_guarded_routes_are_not_public():
    for path in ("/api/v1/chat", "/api/v1/conversations", "/api/v1/ops/readiness"):
        assert is_public_path(path) is False, path


def test_a_path_merely_sharing_a_public_prefix_is_not_public():
    """`/docsomething` must not inherit `/docs`, and `/healthz` must not inherit
    `/health`. A prefix rule that matches loosely would widen the public surface
    without anyone editing the allowlist."""
    assert is_public_path("/docsomething") is False
    assert is_public_path("/healthz") is False
    assert is_public_path("/health/deep") is False


# --------------------------------------------------------------------------
# Enforcement
# --------------------------------------------------------------------------


def test_a_public_path_passes_without_resolving_anything():
    assert enforce_authentication(_request("/health")) is None


def test_a_missing_header_is_rejected():
    response = enforce_authentication(_request("/api/v1/chat"))
    assert response.status_code == 401
    assert _detail(response) == {"detail": "Authentication required."}


def test_a_malformed_header_is_rejected_as_missing():
    for value in ("Bearer", "Basic abc", "Bearer    ", "token-alice-123"):
        response = enforce_authentication(
            _request("/api/v1/chat", {"authorization": value})
        )
        assert response.status_code == 401, value
        assert _detail(response) == {"detail": "Authentication required."}, value


def test_an_invalid_token_is_rejected_distinctly():
    response = enforce_authentication(
        _request("/api/v1/chat", {"authorization": "Bearer not-a-real-token"})
    )
    assert response.status_code == 401
    assert _detail(response) == {"detail": "Invalid bearer token."}


def test_a_valid_token_is_accepted_and_stashed():
    request = _request("/api/v1/chat", _bearer())
    assert enforce_authentication(request) is None
    assert request.state.principal.owner_user_id == "alice"


def test_enforcement_never_reads_the_body():
    """Reading the body here would spend exactly what the rejection saves."""
    request = _request("/api/v1/chat")
    assert enforce_authentication(request) is not None
    assert getattr(request, "_body", None) is None


def test_an_unconfigured_registry_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_AUTH_TOKENS_JSON", SecretStr(""))
    response = enforce_authentication(_request("/api/v1/chat", _bearer()))
    assert response.status_code == 500
    assert _detail(response) == {"detail": "Authentication is unavailable."}


def test_a_registry_with_a_duplicate_token_fails_closed(monkeypatch):
    monkeypatch.setattr(
        settings,
        "LOCAL_AUTH_TOKENS_JSON",
        SecretStr('{"alice": "same", "bob": "same"}'),
    )
    response = enforce_authentication(_request("/api/v1/chat", _bearer()))
    assert response.status_code == 500
    assert _detail(response) == {"detail": "Authentication is unavailable."}


# --------------------------------------------------------------------------
# The accessor fails closed
# --------------------------------------------------------------------------


def test_the_accessor_fails_closed_without_the_middleware():
    """An absent principal means the middleware did not run. Resolving
    credentials here instead would restore a second source of truth and let a
    mis-wired stack authenticate silently."""
    with pytest.raises(HTTPException) as excinfo:
        require_principal(_request("/api/v1/chat", _bearer()))

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == "Authentication is unavailable."


def test_the_accessor_reads_the_stashed_principal():
    request = _request("/api/v1/chat", _bearer())
    enforce_authentication(request)
    assert require_principal(request).owner_user_id == "alice"


def test_the_accessor_does_not_resolve_credentials_itself():
    """A valid token in the header is not enough: only the middleware's stash
    counts. This is what makes the ordering load-bearing."""
    with pytest.raises(HTTPException) as excinfo:
        require_principal(_request("/api/v1/chat", _bearer()))
    assert excinfo.value.status_code == 500
