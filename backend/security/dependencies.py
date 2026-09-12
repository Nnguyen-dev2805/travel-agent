"""FastAPI security policy for authenticated chat.

`enforce_authentication` is the enforcement point (ADR 0026). It runs in the
middleware, ahead of routing and therefore ahead of request-body parsing, so an
unauthenticated request is refused with a controlled `401` whether or not its
body parses. It resolves the caller to a server-side principal from the
bearer-token registry, and missing, malformed, or invalid credentials become
controlled responses that never disclose tokens.

`require_principal` is the route-side accessor of the principal that middleware
resolved. It fails closed when none was stashed, because that means the
middleware did not run.

Request-size enforcement, the public-path allowlist, and CORS origin resolution
also live here so the middleware and the tests share one controlled policy.
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
    AuthenticatedPrincipal,
    AuthenticationError,
    SecurityConfigurationError,
)

logger = logging.getLogger("travel_agent_security")

_MISSING_CREDENTIAL_DETAIL = "Authentication required."
_INVALID_CREDENTIAL_DETAIL = "Invalid bearer token."
_CONFIG_FAILED_DETAIL = "Authentication is unavailable."
_BODY_TOO_LARGE_DETAIL = "Request body too large."
_REQUEST_REJECTED_DETAIL = "Request rejected."

_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
_FALLBACK_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# The complete public surface (ADR 0026). A path is reachable without
# credentials only if it is listed here; nothing is public by omission.
#
# `GET /health` must stay open: a liveness probe that requires a token cannot
# report an authentication outage. The documentation paths are served without
# credentials today and are listed so the exemption is deliberate and
# reviewable rather than an accident of the framework's defaults. Closing them
# is a separate decision.
#
# This is a constant, not a setting: widening the public surface requires a
# code change and a review.
_PUBLIC_PATHS = frozenset({"/health"})
_PUBLIC_PATH_PREFIXES = ("/docs", "/redoc", "/openapi.json")


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


def is_public_path(path: str) -> bool:
    """Return whether `path` is reachable without credentials.

    Matching is exact for the listed paths and anchored for the prefixes, so
    `/docsomething` does not inherit `/docs` and `/healthz` does not inherit
    `/health`. A loose prefix rule would widen the public surface without
    anyone editing the allowlist.
    """
    if path in _PUBLIC_PATHS:
        return True
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in _PUBLIC_PATH_PREFIXES
    )


def enforce_authentication(request: Request) -> Optional[JSONResponse]:
    """Authenticate ahead of routing, or return the rejection to send.

    Returns `None` to continue. Reads the `Authorization` header and the URL
    path only, never the body, which is what makes the rejection cheaper than
    the request it refuses. On success the principal is stashed for the
    route-side accessor.
    """
    if is_public_path(request.url.path):
        return None
    try:
        principal = _resolve_authenticated(_bearer_token(request))
    except HTTPException as error:
        return JSONResponse(
            status_code=error.status_code, content={"detail": error.detail}
        )
    request.state.principal = principal
    return None


def require_principal(request: Request) -> AuthenticatedPrincipal:
    """Return the principal `enforce_authentication` resolved.

    Fails closed when none was stashed: that means the middleware did not run,
    which is a wiring defect. Resolving credentials here instead would restore
    a second source of truth and let a mis-wired stack authenticate silently.
    """
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=500, detail=_CONFIG_FAILED_DETAIL)
    return principal


def body_limit_bytes() -> int:
    """Return the configured body limit, failing closed when invalid."""
    limit = settings.MAX_REQUEST_BODY_BYTES
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise SecurityConfigurationError(
            "Request body limit must be a positive integer."
        )
    return limit


async def enforce_request_body_limit(request: Request) -> Optional[JSONResponse]:
    """Reject oversized bodies with a content-free `413`, if oversized."""
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
    chunks: list[bytes] = []
    async for chunk in request.stream():
        chunks.append(chunk)
        size += len(chunk)
        if size > limit:
            return JSONResponse(
                status_code=413, content={"detail": _BODY_TOO_LARGE_DETAIL}
            )
    request._body = b"".join(chunks)
    return None


def resolve_cors_origins() -> list[str]:
    """Resolve allowed CORS origins, failing closed on wildcard."""
    cors_raw = getattr(settings, "ALLOWED_CORS_ORIGINS", None) or ""
    origins_raw = getattr(settings, "ALLOWED_ORIGINS", None) or ""
    combined = f"{cors_raw},{origins_raw}" if (cors_raw and origins_raw and cors_raw != origins_raw) else (cors_raw or origins_raw)
    origins = [
        part.strip()
        for part in combined.split(",")
        if part.strip()
    ]
    if not origins:
        return list(_FALLBACK_CORS_ORIGINS)
    if "*" in origins:
        raise SecurityConfigurationError(
            "Wildcard CORS origin is not allowed."
        )
    return list(dict.fromkeys(origins))
