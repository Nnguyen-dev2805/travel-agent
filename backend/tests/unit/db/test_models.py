"""Unit tests for User, ChatSession, ChatMessage, and UserMemory models."""

import uuid
# pyrefly: ignore [missing-import]
import pytest
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker
from backend.app.models import Base, User, ChatSession, ChatMessage, UserMemory
from backend.app.core.security import get_password_hash


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for unit testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_user_creation_and_query(db_session):
    """Test creating a new User record and querying it from DB."""
    user = User(
        email="testuser@travel.vn",
        hashed_password=get_password_hash("password123"),
        full_name="Nguyễn Văn A",
    )
    db_session.add(user)
    db_session.commit()

    queried_user = db_session.query(User).filter_by(email="testuser@travel.vn").first()
    assert queried_user is not None
    assert queried_user.id is not None
    assert queried_user.full_name == "Nguyễn Văn A"
    assert queried_user.is_active is True
    assert queried_user.created_at is not None


def test_guest_and_user_chat_sessions(db_session):
    """Test creating Guest session (user_id=None) and Authenticated session (user_id=X)."""
    user = User(email="member@travel.vn", hashed_password="hashpassword")
    db_session.add(user)
    db_session.commit()

    guest_session_id = str(uuid.uuid4())
    user_session_id = str(uuid.uuid4())

    guest_session = ChatSession(id=guest_session_id, user_id=None)
    user_session = ChatSession(id=user_session_id, user_id=user.id)

    db_session.add_all([guest_session, user_session])
    db_session.commit()

    # Query Guest Session (using SQLAlchemy 2.0 Session.get syntax)
    q_guest = db_session.get(ChatSession, guest_session_id)
    assert q_guest is not None
    assert q_guest.user_id is None
    assert q_guest.user is None

    # Query User Session
    q_user_sess = db_session.get(ChatSession, user_session_id)
    assert q_user_sess is not None
    assert q_user_sess.user_id == user.id
    assert q_user_sess.user.email == "member@travel.vn"


def test_chat_message_relationship(db_session):
    """Test adding chat messages to a session and retrieving them in order."""
    session_id = str(uuid.uuid4())
    chat_sess = ChatSession(id=session_id)
    db_session.add(chat_sess)
    db_session.commit()

    msg1 = ChatMessage(session_id=session_id, role="user", content="Hà Nội có gì hay?")
    msg2 = ChatMessage(session_id=session_id, role="assistant", content="Hà Nội nổi tiếng với phố cổ.")

    db_session.add_all([msg1, msg2])
    db_session.commit()

    q_sess = db_session.get(ChatSession, session_id)
    assert len(q_sess.messages) == 2
    assert q_sess.messages[0].role == "user"
    assert q_sess.messages[1].role == "assistant"


def test_user_memory_fact_binding(db_session):
    """Test storing long-term memory facts bound to a User ID."""
    user = User(email="fact_user@travel.vn", hashed_password="hashpassword")
    db_session.add(user)
    db_session.commit()

    memory1 = UserMemory(
        user_id=user.id,
        fact_type="preference",
        fact_key="cuisine_preference",
        fact_value="Thích ẩm thực đường phố và các món cuốn",
        confidence=0.95,
    )
    memory2 = UserMemory(
        user_id=user.id,
        fact_type="visited_place",
        fact_key="visited_cities",
        fact_value="Hà Nội, Đà Nẵng, Phú Quốc",
        confidence=1.0,
    )

    db_session.add_all([memory1, memory2])
    db_session.commit()

    q_user = db_session.get(User, user.id)
    assert len(q_user.memories) == 2
    fact_keys = [m.fact_key for m in q_user.memories]
    assert "cuisine_preference" in fact_keys
    assert "visited_cities" in fact_keys
