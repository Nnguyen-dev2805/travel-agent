import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models.memory import UserMemory, MemoryOutbox, MemoryStatus
from backend.memory.fact_memory import FactMemoryService

# Create an in-memory SQLite database engine
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    # Create tables
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Drop tables after each test
        Base.metadata.drop_all(bind=engine)

@patch('backend.memory.fact_memory.OpenAI')
def test_extract_facts_creates_memory_and_outbox(mock_openai, db_session):
    # Setup mock LLM response
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    
    # Mock extract_facts_from_text response
    mock_completion_text = MagicMock()
    mock_completion_text.choices = [
        MagicMock(message=MagicMock(content='{"facts": [{"fact_type": "preference", "fact_key": "food_preference", "content": "Tôi thích ăn phở", "confidence": 0.99}]}'))
    ]
    mock_client.chat.completions.create.return_value = mock_completion_text
    
    mock_parsed_response = MagicMock()
    mock_parsed_response.facts = []
    mock_completion_parse = MagicMock()
    mock_completion_parse.choices = [MagicMock(message=MagicMock(parsed=mock_parsed_response))]
    mock_client.beta.chat.completions.parse.return_value = mock_completion_parse
    
    mock_embedder = MagicMock()
    mock_vector_store = MagicMock()
    service = FactMemoryService(
        llm_client=mock_client,
        embedder=mock_embedder,
        vector_store=mock_vector_store
    )
    
    # Execute
    results = service.extract_facts(
        db=db_session,
        user_id=1,
        user_message="Tôi thích ăn phở lắm",
        assistant_reply="Vâng, tôi đã ghi nhận."
    )
    
    # Assert return value
    assert len(results) == 1
    assert results[0].fact_key == "food_preference"
    assert results[0].content == "Tôi thích ăn phở"
    
    # Assert DB State
    memories = db_session.query(UserMemory).filter_by(user_id=1).all()
    assert len(memories) == 1
    assert memories[0].content == "Tôi thích ăn phở"
    assert memories[0].status == MemoryStatus.ACTIVE.value
    
    # Assert Outbox State
    outbox_events = db_session.query(MemoryOutbox).all()
    assert len(outbox_events) == 1
    assert outbox_events[0].action == "UPSERT"
    assert outbox_events[0].status == "PENDING"
    assert outbox_events[0].memory_id == memories[0].memory_id
