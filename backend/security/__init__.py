"""Local security boundary for milestone R9.

This package owns authenticated-principal contracts and the local
bearer-token registry. Token values never appear in logs, errors,
responses, or reports produced from here.
"""

from backend.security.dependencies import (
    body_limit_bytes,
    enforce_request_body_limit,
    get_optional_principal,
    require_principal,
    resolve_cors_origins,
)
from backend.security.local_tokens import (
    LOCAL_TOKEN_CREDENTIAL_LABEL,
    parse_local_token_registry,
    resolve_local_principal,
)
from backend.security.models import (
    AuthMode,
    AuthenticatedPrincipal,
    AuthenticationError,
    SecurityConfigurationError,
    SecurityValidationError,
)

__all__ = [
    "LOCAL_TOKEN_CREDENTIAL_LABEL",
    "AuthMode",
    "AuthenticatedPrincipal",
    "AuthenticationError",
    "SecurityConfigurationError",
    "SecurityValidationError",
    "body_limit_bytes",
    "enforce_request_body_limit",
    "get_optional_principal",
    "parse_local_token_registry",
    "require_principal",
    "resolve_cors_origins",
    "resolve_local_principal",
]
