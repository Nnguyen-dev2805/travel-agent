"""Authentication API routes (Register, Login, User Profile)."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.core.security import get_password_hash, verify_password, create_access_token
from backend.app.models.user import User
from backend.app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    UserResponse,
    MemoryConsentUpdate,
)
from backend.app.api.deps import get_current_user

logger = logging.getLogger("travel_agent_auth_api")
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    request: UserRegisterRequest,
    db: Session = Depends(get_db),
):
    """Register a new user account."""
    email_clean = request.email.strip().lower()

    # Check if email is already registered
    existing_user = db.query(User).filter(User.email == email_clean).first()
    if existing_user:
        logger.warning(f"Registration attempt with duplicate email: '{email_clean}'")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email này đã được đăng ký trong hệ thống.",
        )

    # Hash password and create user
    hashed_pwd = get_password_hash(request.password)
    user = User(
        email=email_clean,
        hashed_password=hashed_pwd,
        full_name=request.full_name.strip() if request.full_name else None,
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"Successfully registered new user ID={user.id}, Email='{user.email}'")
    return user


@router.post("/login", response_model=TokenResponse)
def login_user(
    request: UserLoginRequest,
    db: Session = Depends(get_db),
):
    """Authenticate user credentials and issue a JWT access token."""
    email_clean = request.email.strip().lower()

    user = db.query(User).filter(User.email == email_clean).first()
    if not user or not verify_password(request.password, user.hashed_password):
        logger.warning(f"Failed login attempt for email: '{email_clean}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tài khoản này đã bị vô hiệu hóa.",
        )

    access_token = create_access_token(subject=user.id)
    logger.info(f"User ID={user.id} logged in successfully.")

    return TokenResponse(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
def get_user_profile(
    current_user: User = Depends(get_current_user),
):
    """Get profile information for the authenticated user."""
    return current_user


@router.patch("/me/memory_consent", response_model=UserResponse)
def update_memory_consent(
    request: MemoryConsentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update memory consent (opt-in/opt-out) for the authenticated user."""
    current_user.memory_enabled = request.memory_enabled
    db.commit()
    db.refresh(current_user)
    
    logger.info(f"User ID={current_user.id} updated memory_enabled to {current_user.memory_enabled}")
    return current_user
