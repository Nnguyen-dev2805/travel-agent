"""Security package for authenticated chat."""

from backend.security.dependencies import (
    body_limit_bytes,
    enforce_request_body_limit,
    require_principal,
    resolve_cors_origins,
)
from backend.security.local_tokens import (
    parse_local_token_registry,
    resolve_local_principal,
)
from backend.security.models import (
    AuthMode,
    AuthenticatedPrincipal,
    AuthenticationError,
    CrossOwnerAccessError,
    OwnerForbiddenError,
    SecurityConfigurationError,
)

__all__ = [
    "AuthMode",
    "AuthenticatedPrincipal",
    "AuthenticationError",
    "CrossOwnerAccessError",
    "OwnerForbiddenError",
    "SecurityConfigurationError",
    "body_limit_bytes",
    "enforce_request_body_limit",
    "parse_local_token_registry",
    "require_principal",
    "resolve_cors_origins",
    "resolve_local_principal",
]
