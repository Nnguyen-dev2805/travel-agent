"""Unit tests for ConversationMemoryService, FactMemoryService, and MemoryManager."""

import uuid
from unittest.mock import MagicMock
# pyrefly: ignore [missing-import]
import pytest
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, User, UserMemory
from backend.memory.episodic_memory import EpisodicMemoryService
from backend.memory.short_term_memory import ShortTermMemoryService
from backend.memory.fact_memory import FactMemoryService
from backend.memory.memory_manager import MemoryManager


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for memory service testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_conversation_memory_sliding_window(db_session):
    """Test sliding window retrieves only N most recent messages in chronological order."""
    episodic_service = EpisodicMemoryService(llm_client=MagicMock(), embedder=MagicMock(), vector_store=MagicMock())
    short_term_service = ShortTermMemoryService()
    session_id = str(uuid.uuid4())

    # Add 15 messages (15 turns)
    for i in range(1, 16):
        role = "user" if i % 2 != 0 else "assistant"
        episodic_service.add_message(db_session, session_id, role=role, content=f"Message {i}")

    # Fetch recent messages with limit=6
    recent = short_term_service.get_sliding_window(db_session, session_id, limit=6)
    assert len(recent) == 6

    # Verify chronological order (Message 10 to Message 15)
    contents = [m.content for m in recent]
    assert contents == ["Message 10", "Message 11", "Message 12", "Message 13", "Message 14", "Message 15"]


def test_conversation_memory_formatting(db_session):
    """Test format_messages_for_llm produces OpenAI-compatible message list."""
    episodic_service = EpisodicMemoryService(llm_client=MagicMock(), embedder=MagicMock(), vector_store=MagicMock())
    short_term_service = ShortTermMemoryService()
    session_id = str(uuid.uuid4())

    episodic_service.add_message(db_session, session_id, "user", "Hà Nội đi đâu đẹp?")
    episodic_service.add_message(db_session, session_id, "assistant", "Bạn nên thăm Hồ Hoàn Kiếm.")

    msgs = short_term_service.get_sliding_window(db_session, session_id)
    formatted = short_term_service.format_messages_for_llm(msgs)
    assert formatted == [
        {"role": "user", "content": "Hà Nội đi đâu đẹp?"},
        {"role": "assistant", "content": "Bạn nên thăm Hồ Hoàn Kiếm."},
    ]


def test_fact_memory_upsert_and_isolation(db_session):
    """Test fact memory upserts existing keys and isolates user facts."""
    fact_service = FactMemoryService(llm_client=MagicMock(), embedder=MagicMock(), vector_store=MagicMock())

    # Create User A and User B
    user_a = User(email="usera@travel.vn", hashed_password="hashpassword")
    user_b = User(email="userb@travel.vn", hashed_password="hashpassword")
    db_session.add_all([user_a, user_b])
    db_session.commit()

    # Add fact for User A
    mem_a1 = UserMemory(
        user_id=user_a.id,
        fact_type="dietary",
        fact_key="allergy",
        content="Dị ứng hải sản",
        status="active"
    )
    db_session.add(mem_a1)
    db_session.commit()

    # Verify User A has 1 fact, User B has 0 facts
    facts_a = fact_service.get_user_facts(db_session, user_a.id)
    facts_b = fact_service.get_user_facts(db_session, user_b.id)
    assert len(facts_a) == 1
    assert len(facts_b) == 0
    assert facts_a[0].content == "Dị ứng hải sản"

    # Upsert fact for User A (Updating same key 'food_allergy')
    existing_mem = db_session.query(UserMemory).filter_by(user_id=user_a.id, fact_key="allergy").first()
    existing_mem.content = "Dị ứng hải sản và đậu nành"
    db_session.commit()

    # Verify fact updated without creating duplicate row
    facts_a_updated = fact_service.get_user_facts(db_session, user_a.id)
    assert len(facts_a_updated) == 1
    assert facts_a_updated[0].content == "Dị ứng hải sản và đậu nành"


def test_delete_fact_isolation(db_session):
    """Test fact deletion enforces strict User ID authorization."""
    fact_service = FactMemoryService(llm_client=MagicMock(), embedder=MagicMock(), vector_store=MagicMock())

    user_a = User(email="owner@travel.vn", hashed_password="hash")
    user_b = User(email="attacker@travel.vn", hashed_password="hash")
    db_session.add_all([user_a, user_b])
    db_session.commit()

    fact_a = UserMemory(
        user_id=user_a.id,
        fact_type="preference",
        fact_key="fav_city",
        content="Đà Nẵng",
        status="active"
    )
    db_session.add(fact_a)
    db_session.commit()

    # User B tries to delete User A's fact -> fails
    deleted_by_b = fact_service.delete_fact(db_session, user_id=user_b.id, fact_id=fact_a.id)
    assert deleted_by_b is False
    assert db_session.get(UserMemory, fact_a.id) is not None

    # User A deletes their own fact -> succeeds (soft delete)
    deleted_by_a = fact_service.delete_fact(db_session, user_id=user_a.id, fact_id=fact_a.id)
    assert deleted_by_a is True
    assert db_session.get(UserMemory, fact_a.id).status == "deleted"


from unittest.mock import patch

@patch("backend.memory.fact_memory.FactMemoryService.retrieve_relevant_facts")
@patch("backend.memory.episodic_memory.EpisodicMemoryService.recall_past_episodes")
def test_memory_manager_guest_vs_user_context(mock_recall, mock_retrieve, db_session):
    """Test MemoryManager routes context differently for Guest vs Authenticated User."""
    mock_retrieve.return_value = "• [PREFERENCE] Thích du lịch sinh thái"
    mock_recall.return_value = "=== HỒI TƯỞNG CÁC PHIÊN CHAT CŨ ===\nLần trước User hỏi về Sapa"
    
    mock_episodic = EpisodicMemoryService(llm_client=MagicMock(), embedder=MagicMock(), vector_store=MagicMock())
    mock_episodic.recall_past_episodes = mock_recall
    
    manager = MemoryManager(
        episodic_service=mock_episodic,
        short_term_service=ShortTermMemoryService(),
        fact_service=MagicMock()
    )
    # Re-mock fact_service retrieval since we overwrote the instance
    manager.fact_service.retrieve_relevant_facts = mock_retrieve
    
    session_id = str(uuid.uuid4())

    user = User(email="member@travel.vn", hashed_password="hash")
    db_session.add(user)
    db_session.commit()

    # Add long-term fact for User
    fact = UserMemory(
        user_id=user.id,
        fact_type="preference",
        fact_key="style",
        content="Thích du lịch sinh thái",
        status="active"
    )
    db_session.add(fact)
    db_session.commit()

    # Process turn
    manager.process_turn(db_session, session_id, "Tôi muốn tìm địa điểm đẹp", "Bạn có thể đi Tràng An.")

    # 1. Build context for Guest User (user=None) -> Has history, NO long-term facts
    guest_context = manager.build_memory_context(db_session, session_id, user=None)
    assert len(guest_context["conversation_history"]) == 2
    assert guest_context["user_facts"] == ""

    # 2. Build context for Authenticated User -> Has history AND long-term facts
    user_context = manager.build_memory_context(db_session, session_id, user=user, user_message="Tôi muốn tìm địa điểm đẹp")
    assert len(user_context["conversation_history"]) == 2
    assert "Thích du lịch sinh thái" in user_context["user_facts"]


def test_session_auto_title_creation(db_session):
    """Test first user message automatically sets the title for ChatSession."""
    service = EpisodicMemoryService(llm_client=MagicMock(), embedder=MagicMock(), vector_store=MagicMock())
    session_id = str(uuid.uuid4())

    # Add first user message
    service.add_message(db_session, session_id, "user", "Tư vấn cho tôi lịch trình đi Phú Quốc 4 ngày 3 đêm")

    from backend.app.models import ChatSession
    session = db_session.get(ChatSession, session_id)
    assert session is not None
    assert session.title is not None
    assert "Tư vấn cho tôi lịch trình đi Phú Quốc" in session.title


def test_get_and_delete_user_sessions(db_session):
    """Test fetching user session list and deleting sessions cleanly."""
    service = EpisodicMemoryService(llm_client=MagicMock(), embedder=MagicMock(), vector_store=MagicMock())
    user = User(email="sessionowner@travel.vn", hashed_password="hash")
    db_session.add(user)
    db_session.commit()

    sid1 = str(uuid.uuid4())
    sid2 = str(uuid.uuid4())

    service.add_message(db_session, sid1, "user", "Chuyến đi 1", user_id=user.id)
    service.add_message(db_session, sid2, "user", "Chuyến đi 2", user_id=user.id)

    sessions = service.get_user_sessions(db_session, user.id)
    assert len(sessions) == 2

    # Delete sid1
    deleted = service.delete_session(db_session, sid1, user_id=user.id)
    assert deleted is True

    sessions_after = service.get_user_sessions(db_session, user.id)
    assert len(sessions_after) == 1
    assert sessions_after[0].id == sid2

