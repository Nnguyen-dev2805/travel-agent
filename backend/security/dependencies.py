"""FastAPI security dependencies for milestone R9.

`require_principal` resolves the caller to a server-side principal:
the compatibility principal when auth is disabled, or an authenticated
owner from the local bearer-token registry when enabled. Invalid
credentials become controlled `401` responses here so routes never see
raw tokens; malformed registry configuration raises
`SecurityConfigurationError` for routes to fail closed with a `500`.

Request-size enforcement and CORS origin resolution also live here so
both the middleware and tests share one controlled policy. Product
authorization helpers arrive in a later R9 task.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from backend.app.config import settings
from backend.security.local_tokens import (
    parse_local_token_registry,
    resolve_local_principal,
)
from backend.security.models import (
    AuthMode,
    AuthenticatedPrincipal,
    AuthenticationError,
    SecurityConfigurationError,
)

logger = logging.getLogger("travel_agent_security")

COMPATIBILITY_OWNER_ID = "local-developer"
COMPATIBILITY_CREDENTIAL_LABEL = "none"

_MISSING_CREDENTIAL_DETAIL = "Authentication required."
_INVALID_CREDENTIAL_DETAIL = "Invalid bearer token."
_CONFIG_FAILED_DETAIL = "Authentication is unavailable."
_BODY_TOO_LARGE_DETAIL = "Request body too large."
_REQUEST_REJECTED_DETAIL = "Request rejected."

_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
_FALLBACK_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _compatibility_principal() -> AuthenticatedPrincipal:
    """Return the non-authoritative local development principal."""
    return AuthenticatedPrincipal(
        owner_user_id=COMPATIBILITY_OWNER_ID,
        auth_mode=AuthMode.COMPATIBILITY,
        credential_label=COMPATIBILITY_CREDENTIAL_LABEL,
    )


def _bearer_token(request: Request) -> Optional[str]:
    """Extract a bearer token, or return `None` when absent or malformed."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _registry() -> dict[str, str]:
    """Parse the configured token registry, failing closed on bad config."""
    raw = settings.LOCAL_AUTH_TOKENS_JSON.get_secret_value()
    return parse_local_token_registry(raw)


def _resolve_authenticated(token: Optional[str]) -> AuthenticatedPrincipal:
    if token is None:
        raise HTTPException(status_code=401, detail=_MISSING_CREDENTIAL_DETAIL)
    try:
        registry = _registry()
    except SecurityConfigurationError as error:
        logger.error(
            "security.auth configuration failure failure_class=%s",
            type(error).__name__,
        )
        raise HTTPException(status_code=500, detail=_CONFIG_FAILED_DETAIL) from error
    try:
        return resolve_local_principal(token, registry)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail=_INVALID_CREDENTIAL_DETAIL)


def get_optional_principal(request: Request) -> AuthenticatedPrincipal:
    """Resolve the caller principal, enforcing auth only when enabled.

    In compatibility mode every caller receives the non-authoritative
    local principal and existing request shapes keep working. When auth
    is enabled this enforces exactly like `require_principal`: the split
    exists so future anonymous-safe reads have a distinct seam.
    """
    if not settings.AUTH_REQUIRED:
        return _compatibility_principal()
    return _resolve_authenticated(_bearer_token(request))


def require_principal(request: Request) -> AuthenticatedPrincipal:
    """Resolve the caller principal, enforcing auth only when enabled."""
    if not settings.AUTH_REQUIRED:
        return _compatibility_principal()
    return _resolve_authenticated(_bearer_token(request))


def body_limit_bytes() -> int:
    """Return the configured body limit, failing closed when invalid."""
    limit = settings.MAX_REQUEST_BODY_BYTES
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise SecurityConfigurationError(
            "Request body limit must be a positive integer."
        )
    return limit


async def enforce_request_body_limit(request: Request) -> Optional[JSONResponse]:
    """Reject oversized bodies with a content-free `413`, if oversized.

    The `Content-Length` fast path avoids reading the body; requests with
    a missing or malformed length and a body-bearing method are measured
    from the stream up to one byte past the limit. Returns `None` when
    the request fits.
    """
    limit = body_limit_bytes()
    length = request.headers.get("content-length")
    if length is not None:
        try:
            if int(length) > limit:
                return JSONResponse(
                    status_code=413, content={"detail": _BODY_TOO_LARGE_DETAIL}
                )
            return None
        except (TypeError, ValueError):
            pass
    if request.method not in _BODY_METHODS:
        return None
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            return JSONResponse(
                status_code=413, content={"detail": _BODY_TOO_LARGE_DETAIL}
            )
    return None


def resolve_cors_origins() -> list[str]:
    """Resolve allowed CORS origins, failing closed on wildcard with auth.

    Compatibility mode preserves the existing local origins including the
    wildcard. When auth is enabled only explicit origins are allowed; a
    wildcard or blank configuration fails closed.
    """
    if not settings.AUTH_REQUIRED:
        return [*_FALLBACK_CORS_ORIGINS, "*"]
    origins = [
        part.strip()
        for part in settings.ALLOWED_CORS_ORIGINS.split(",")
        if part.strip()
    ]
    if not origins:
        return list(_FALLBACK_CORS_ORIGINS)
    if "*" in origins:
        raise SecurityConfigurationError(
            "Wildcard CORS origin is not allowed when auth is required."
        )
    return origins
