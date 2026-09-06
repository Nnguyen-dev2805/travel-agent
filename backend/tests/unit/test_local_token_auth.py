"""Unit tests for the R9 local token registry.

Tests pin registry parsing, safe comparison, and owner resolution. All
tokens are synthetic fixtures. No test logs, persists, or returns token
values, and no test touches the network.
"""

import pytest

from backend.security.local_tokens import (
    parse_local_token_registry,
    resolve_local_principal,
)
from backend.security.models import (
    AuthMode,
    AuthenticationError,
    SecurityConfigurationError,
)


def test_valid_json_registry_maps_owners_to_tokens():
    registry = parse_local_token_registry(
        '{"owner_a": "secret-alpha-token", "owner_b": "secret-beta-token"}'
    )

    assert registry == {
        "owner_a": "secret-alpha-token",
        "owner_b": "secret-beta-token",
    }


def test_blank_owner_or_token_rejected():
    with pytest.raises(SecurityConfigurationError):
        parse_local_token_registry('{"  ": "secret-alpha-token"}')
    with pytest.raises(SecurityConfigurationError):
        parse_local_token_registry('{"owner_a": "   "}')


def test_malformed_json_rejected_without_echoing_input():
    raw = '{"owner_a": "secret-alpha-token"'

    with pytest.raises(SecurityConfigurationError) as exc_info:
        parse_local_token_registry(raw)

    assert "secret-alpha-token" not in str(exc_info.value)
    assert raw not in str(exc_info.value)


def test_valid_token_resolves_correct_owner():
    registry = parse_local_token_registry(
        '{"owner_a": "secret-alpha-token", "owner_b": "secret-beta-token"}'
    )

    principal = resolve_local_principal("secret-beta-token", registry)

    assert principal.owner_user_id == "owner_b"
    assert principal.auth_mode is AuthMode.AUTHENTICATED
    assert principal.credential_label == "local_token"


def test_invalid_token_raises_without_echoing_value():
    registry = parse_local_token_registry('{"owner_a": "secret-alpha-token"}')

    with pytest.raises(AuthenticationError) as exc_info:
        resolve_local_principal("wrong-token", registry)

    assert "wrong-token" not in str(exc_info.value)
    assert "secret-alpha-token" not in str(exc_info.value)


def test_duplicate_token_values_rejected():
    with pytest.raises(SecurityConfigurationError) as exc_info:
        parse_local_token_registry('{"owner_a": "same-token", "owner_b": "same-token"}')

    assert "same-token" not in str(exc_info.value)


def test_non_string_entries_rejected():
    with pytest.raises(SecurityConfigurationError):
        parse_local_token_registry('{"owner_a": 42}')
    with pytest.raises(SecurityConfigurationError):
        parse_local_token_registry('["owner_a"]')


def test_settings_representation_hides_token_values():
    from backend.app.config import Settings

    configured = Settings(LOCAL_AUTH_TOKENS_JSON='{"owner_a": "sentinel-token-xyz"}')

    assert configured.LOCAL_AUTH_TOKENS_JSON.get_secret_value() == (
        '{"owner_a": "sentinel-token-xyz"}'
    )
    assert "sentinel-token-xyz" not in repr(configured)
    assert "sentinel-token-xyz" not in str(configured)
    assert "sentinel-token-xyz" not in configured.model_dump_json()
