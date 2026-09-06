"""Local bearer-token registry for milestone R9.

The registry maps `owner_user_id` to token values from environment
configuration. Tokens are compared with `hmac.compare_digest`, and no
function here logs, persists, returns, or echoes token values or raw
registry input. This module uses only the standard library plus security
models.
"""

from __future__ import annotations

import hmac
import json
from typing import Mapping

from backend.security.models import (
    AuthMode,
    AuthenticatedPrincipal,
    AuthenticationError,
    SecurityConfigurationError,
)

LOCAL_TOKEN_CREDENTIAL_LABEL = "local_token"


def parse_local_token_registry(raw: str) -> dict[str, str]:
    """Parse a JSON owner-to-token registry without echoing secrets.

    Every owner id and token must be a non-empty string, and every token
    value must be unique: a shared token cannot identify one owner.
    Error messages name the failure shape only, never the input.

    Raises:
        SecurityConfigurationError: The input is not a JSON object of
            unique non-empty string pairs.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as error:
        raise SecurityConfigurationError(
            "Local token registry is not valid JSON."
        ) from error
    if not isinstance(parsed, dict) or not parsed:
        raise SecurityConfigurationError(
            "Local token registry must be a non-empty JSON object."
        )
    registry: dict[str, str] = {}
    seen_tokens: set[str] = set()
    for owner_id, token in parsed.items():
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise SecurityConfigurationError(
                "Local token registry owner ids must be non-empty strings."
            )
        if not isinstance(token, str) or not token.strip():
            raise SecurityConfigurationError(
                "Local token registry tokens must be non-empty strings."
            )
        if token in seen_tokens:
            raise SecurityConfigurationError(
                "Local token registry token values must be unique per owner."
            )
        seen_tokens.add(token)
        registry[owner_id.strip()] = token
    return registry


def resolve_local_principal(
    token: str, registry: Mapping[str, str]
) -> AuthenticatedPrincipal:
    """Resolve one bearer token to its owner without leaking secrets.

    Comparison is constant-time per candidate. Failure messages never
    include the presented value or any registered value.

    Raises:
        AuthenticationError: The token does not resolve to an owner.
    """
    if not isinstance(token, str) or not token:
        raise AuthenticationError("Bearer credential is missing or invalid.")
    for owner_id, registered in registry.items():
        if hmac.compare_digest(token, registered):
            return AuthenticatedPrincipal(
                owner_user_id=owner_id,
                auth_mode=AuthMode.AUTHENTICATED,
                credential_label=LOCAL_TOKEN_CREDENTIAL_LABEL,
            )
    raise AuthenticationError("Bearer credential is missing or invalid.")
