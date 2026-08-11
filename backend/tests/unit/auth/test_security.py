"""Unit tests for security module (Password hashing & JWT Token handling)."""

from datetime import timedelta
import pytest
import jwt
from backend.app.config import settings
from backend.app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
)


def test_password_hashing():
    """Verify password hashing and verification logic."""
    raw_password = "SecretPassword123!"
    hashed = get_password_hash(raw_password)

    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False
    assert verify_password("", hashed) is False


def test_access_token_creation_and_decoding():
    """Verify JWT access token generation and payload decoding."""
    user_id = 42
    token = create_access_token(subject=user_id)

    assert isinstance(token, str)
    assert len(token) > 0

    payload = decode_access_token(token)
    assert payload is not None
    assert payload.get("sub") == str(user_id)
    assert "exp" in payload


def test_access_token_expiry():
    """Verify expired token returns None when decoded."""
    user_id = "test_user@example.com"
    # Token expired 10 seconds ago
    expired_token = create_access_token(subject=user_id, expires_delta=timedelta(seconds=-10))

    payload = decode_access_token(expired_token)
    assert payload is None


def test_access_token_invalid_signature():
    """Verify token signed with an invalid key cannot be decoded."""
    user_id = 100
    token = create_access_token(subject=user_id)

    # Decode with wrong secret key
    try:
        jwt.decode(token, "wrong-secret-key", algorithms=[settings.ALGORITHM])
        pytest.fail("Should have raised InvalidSignatureError")
    except jwt.PyJWTError:
        pass
