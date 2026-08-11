"""Security module for password hashing with Bcrypt and JWT token handling."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
# pyrefly: ignore [missing-import]
import bcrypt
# pyrefly: ignore [missing-import]
import jwt
from backend.app.config import settings

logger = logging.getLogger("travel_agent_security")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against a stored Bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}")
        return False


def get_password_hash(password: str) -> str:
    """Generate a Bcrypt hash for a plain text password."""
    if not password:
        raise ValueError("Password content cannot be empty.")
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def create_access_token(subject: Any, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token containing subject (user_id/email)."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "exp": expire,
        "iat": now,
        "sub": str(subject),
    }

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT Token has expired.")
        return None
    except jwt.PyJWTError as e:
        logger.warning(f"Invalid JWT Token: {str(e)}")
        return None
