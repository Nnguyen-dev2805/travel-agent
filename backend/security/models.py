"""Security domain contracts for milestone R9.

`AuthenticatedPrincipal` carries server-resolved identity: the owner id
comes from the local token registry, never from caller-supplied labels.
This module uses only the standard library so route and service code can
depend on it without cycles.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SecurityValidationError(Exception):
    """A security domain value violates its governed contract."""


class SecurityConfigurationError(Exception):
    """Local auth configuration is missing or malformed.

    Messages raised as this type are safe for a controlled configuration
    failure: they never include token values or raw registry input.
    """


class AuthenticationError(Exception):
    """A bearer credential is missing or does not resolve to an owner.

    Messages raised as this type are safe for a controlled `401`
    response: they never include the presented or registered token value.
    Routes map this to `401` without logging credential material.
    """


class AuthMode(str, Enum):
    """Governed authentication mode vocabulary."""

    AUTHENTICATED = "authenticated"
    COMPATIBILITY = "compatibility"


def _require_owner(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SecurityValidationError(
            f"Security field '{field_name}' must be a non-empty string."
        )
    return value.strip()


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Server-resolved identity for one local caller.

    `owner_user_id` is resolved from the token registry in auth mode, or
    the local development owner in compatibility mode. `credential_label`
    names the credential kind (such as `local_token` or `none`) and never
    carries secret material.
    """

    owner_user_id: str
    auth_mode: AuthMode
    credential_label: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "owner_user_id",
            _require_owner(self.owner_user_id, "owner_user_id"),
        )
        if not isinstance(self.auth_mode, AuthMode):
            try:
                object.__setattr__(self, "auth_mode", AuthMode(self.auth_mode))
            except ValueError as error:
                allowed = ", ".join(member.value for member in AuthMode)
                raise SecurityValidationError(
                    f"Unknown auth_mode value. Allowed values: {allowed}."
                ) from error
        object.__setattr__(
            self,
            "credential_label",
            _require_owner(self.credential_label, "credential_label"),
        )


__all__ = [
    "AuthMode",
    "AuthenticatedPrincipal",
    "AuthenticationError",
    "SecurityConfigurationError",
    "SecurityValidationError",
]
