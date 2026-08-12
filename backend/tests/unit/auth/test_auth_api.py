"""Unit and integration tests for Auth API endpoints (/api/v1/auth/*)."""

# pyrefly: ignore [missing-import]
import pytest
from fastapi.testclient import TestClient
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker
# pyrefly: ignore [missing-import]
from sqlalchemy.pool import StaticPool

from backend.app.main import app
from backend.app.database import Base, get_db
from backend.app.models.user import User
from backend.app.api.deps import get_optional_user
from backend.app.core.security import create_access_token


@pytest.fixture
def client_and_db():
    """Create a multithread-safe SQLite in-memory DB and FastAPI TestClient."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client, TestingSessionLocal()

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def test_register_user_success(client_and_db):
    """Test registering a new user account."""
    client, db = client_and_db

    payload = {
        "email": "newuser@travel.vn",
        "password": "securepassword123",
        "full_name": "Nguyễn Văn Mới",
    }

    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["email"] == "newuser@travel.vn"
    assert data["full_name"] == "Nguyễn Văn Mới"
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data

    # Verify user exists in DB with hashed password
    user_in_db = db.get(User, data["id"])
    assert user_in_db is not None
    assert user_in_db.hashed_password != "securepassword123"


def test_register_duplicate_email(client_and_db):
    """Test registering with an email that is already registered."""
    client, _ = client_and_db

    payload = {
        "email": "duplicate@travel.vn",
        "password": "password123",
        "full_name": "User One",
    }

    # First registration
    resp1 = client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201

    # Second registration with same email
    resp2 = client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 400
    assert "đã được đăng ký" in resp2.json()["detail"]


def test_login_success(client_and_db):
    """Test successful user login issuing a JWT access token."""
    client, _ = client_and_db

    # Register first
    client.post(
        "/api/v1/auth/register",
        json={"email": "loginuser@travel.vn", "password": "mypassword123", "full_name": "Login User"},
    )

    # Attempt login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "loginuser@travel.vn", "password": "mypassword123"},
    )

    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 20


def test_login_invalid_password(client_and_db):
    """Test login with wrong password returns 401 Unauthorized."""
    client, _ = client_and_db

    client.post(
        "/api/v1/auth/register",
        json={"email": "wrongpass@travel.vn", "password": "correctpassword"},
    )

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpass@travel.vn", "password": "incorrectpassword"},
    )

    assert login_resp.status_code == 401
    assert "không chính xác" in login_resp.json()["detail"]


def test_get_user_profile_me(client_and_db):
    """Test fetching profile for authenticated user via /auth/me."""
    client, _ = client_and_db

    # 1. Register & Login
    client.post(
        "/api/v1/auth/register",
        json={"email": "profileuser@travel.vn", "password": "password123", "full_name": "Profile Name"},
    )
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "profileuser@travel.vn", "password": "password123"},
    )
    token = login_resp.json()["access_token"]

    # 2. Call /auth/me with Bearer token
    headers = {"Authorization": f"Bearer {token}"}
    me_resp = client.get("/api/v1/auth/me", headers=headers)

    assert me_resp.status_code == 200
    profile = me_resp.json()
    assert profile["email"] == "profileuser@travel.vn"
    assert profile["full_name"] == "Profile Name"


def test_get_user_profile_unauthorized(client_and_db):
    """Test calling /auth/me without token returns 401 Unauthorized."""
    client, _ = client_and_db

    # No Authorization header
    resp1 = client.get("/api/v1/auth/me")
    assert resp1.status_code == 401

    # Invalid Authorization token
    resp2 = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid_token_123"})
    assert resp2.status_code == 401


def test_optional_user_dependency(client_and_db):
    """Test get_optional_user returns User for valid token and None for missing/invalid token."""
    client, db = client_and_db

    # Create a user directly in DB
    user = User(email="optional@travel.vn", hashed_password="hash", full_name="Optional User")
    db.add(user)
    db.commit()
    db.refresh(user)

    valid_token = create_access_token(subject=user.id)

    # Test with valid token -> returns User
    res_user = get_optional_user(db=db, token=valid_token)
    assert res_user is not None
    assert res_user.id == user.id

    # Test with None token (Guest) -> returns None
    res_guest = get_optional_user(db=db, token=None)
    assert res_guest is None

    # Test with invalid token -> returns None
    res_invalid = get_optional_user(db=db, token="bogustoken")
    assert res_invalid is None
