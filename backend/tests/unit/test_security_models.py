"""Unit tests for R9 security contracts.

Tests pin principal construction, owner validation, credential labels,
and auth-mode vocabulary. No test uses real credentials, tokens, user
data, or the network.
"""

import pytest

from backend.security.models import (
    AuthMode,
    AuthenticatedPrincipal,
    AuthenticationError,
    SecurityConfigurationError,
    SecurityValidationError,
)


def test_valid_principal_construction():
    principal = AuthenticatedPrincipal(
        owner_user_id="owner_a",
        auth_mode=AuthMode.AUTHENTICATED,
        credential_label="local_token",
    )

    assert principal.owner_user_id == "owner_a"
    assert principal.auth_mode is AuthMode.AUTHENTICATED
    assert principal.credential_label == "local_token"


def test_blank_owner_rejected():
    with pytest.raises(SecurityValidationError):
        AuthenticatedPrincipal(
            owner_user_id="   ",
            auth_mode=AuthMode.AUTHENTICATED,
            credential_label="local_token",
        )


def test_credential_label_validation():
    with pytest.raises(SecurityValidationError):
        AuthenticatedPrincipal(
            owner_user_id="owner_a",
            auth_mode=AuthMode.AUTHENTICATED,
            credential_label="  ",
        )


def test_auth_mode_vocabulary_is_authenticated_only():
    assert {item.value for item in AuthMode} == {"authenticated"}


def test_compatibility_mode_is_removed():
    assert not hasattr(AuthMode, "COMPATIBILITY")
    with pytest.raises(SecurityValidationError):
        AuthenticatedPrincipal(
            owner_user_id="owner_a",
            auth_mode="compatibility",
            credential_label="local_token",
        )


def test_security_errors_share_a_common_base():
    assert issubclass(AuthenticationError, SecurityConfigurationError) is False
    assert issubclass(SecurityValidationError, Exception)
