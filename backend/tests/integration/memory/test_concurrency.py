import threading
import time
# pyrefly: ignore [missing-import]
import pytest
from unittest.mock import patch, MagicMock
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker
# pyrefly: ignore [missing-import]
from testcontainers.postgres import PostgresContainer

from backend.app.database import Base
from backend.app.models.user import User
from backend.app.models.memory import UserMemory, MemoryStatus
from backend.memory.enums import ConflictAction
from backend.memory.fact_memory import FactMemoryService

@pytest.fixture(scope="session")
def postgres_container():
    """Spin up a Postgres container for all tests in this session."""
    with PostgresContainer("postgres:15-alpine") as postgres:
        yield postgres.get_connection_url()

@pytest.fixture(scope="function")
def db_session_factory(postgres_container):
    """Create a fresh database and session factory for each test."""
    engine = create_engine(postgres_container)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create all tables. Since it's Postgres, the partial index in models/memory.py
    # will be created automatically and correctly!
    Base.metadata.create_all(bind=engine)
    
    # Insert a mock user to satisfy Postgres strict foreign key constraints
    session = TestingSessionLocal()
    mock_user = User(id=1, email="test@example.com", hashed_password="pwd")
    session.add(mock_user)
    session.commit()
    session.close()
        
    yield TestingSessionLocal
    
    # Drop all tables after test
    Base.metadata.drop_all(bind=engine)
    engine.dispose()

@patch('backend.memory.fact_memory.OpenAI')
def test_toctou_race_condition(mock_openai, db_session_factory):
    """
    Simulate two identical extract_facts calls arriving at the exact same millisecond.
    This test verifies that the Optimistic Locking / UNIQUE Constraint retry loop catches
    the conflict and resolves it without throwing a 500 error or creating duplicate active rows.
    Now running on real PostgreSQL!
    """
    
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    
    # Thread-local storage for test results
    results = {}
    
    def simulate_worker(thread_id, user_msg):
        # We need independent sessions for each thread to simulate real requests
        db = db_session_factory()
        mock_embedder = MagicMock()
        mock_vector_store = MagicMock()
        service = FactMemoryService(
            llm_client=mock_client,
            embedder=mock_embedder,
            vector_store=mock_vector_store
        )
        
        # Mocking the first LLM call (extracting the fact)
        mock_completion_text = MagicMock()
        mock_completion_text.choices = [
            MagicMock(message=MagicMock(content=f'{{"facts": [{{"fact_type": "preference", "fact_key": "food_preference", "content": "{user_msg}", "confidence": 0.99}}]}}'))
        ]
        mock_client.chat.completions.create.return_value = mock_completion_text
        
        # Mocking the second LLM call (conflict resolution) - simulating 1s delay to widen race condition window
        mock_conflict_decision = MagicMock()
        mock_conflict_decision.action = ConflictAction.UPDATE
        mock_conflict_decision.merged_content = f"{user_msg} (Merged)"
        mock_conflict_completion = MagicMock()
        mock_conflict_completion.choices = [MagicMock(message=MagicMock(parsed=mock_conflict_decision))]
        
        def mock_parse(*args, **kwargs):
            if "Memory Conflict Resolver" in kwargs.get("messages", [{}])[0].get("content", ""):
                time.sleep(1) # Simulate slow LLM during conflict resolution
                return mock_conflict_completion
            return mock_conflict_completion

        mock_client.beta.chat.completions.parse.side_effect = mock_parse
        
        try:
            res = service.extract_facts(
                db=db,
                user_id=1,
                user_message=user_msg,
                assistant_reply="Vâng."
            )
            results[thread_id] = {"success": True, "data": res}
        except Exception as e:
            results[thread_id] = {"success": False, "error": e}
        finally:
            db.close()

    # Start two threads simultaneously
    t1 = threading.Thread(target=simulate_worker, args=("Thread_1", "Tôi thích ăn phở"))
    t2 = threading.Thread(target=simulate_worker, args=("Thread_2", "Tôi thích ăn bún chả"))
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
    
    # Assert Database State
    db = db_session_factory()
    memories = db.query(UserMemory).filter_by(user_id=1, fact_key="food_preference", status=MemoryStatus.ACTIVE.value).all()
    
    db.close()
    
    # Both threads should succeed because of the retry mechanism
    assert results["Thread_1"]["success"] is True, f"Thread 1 failed: {results['Thread_1'].get('error')}"
    assert results["Thread_2"]["success"] is True, f"Thread 2 failed: {results['Thread_2'].get('error')}"
    
    # Crucial assertion: There must be only ONE active memory for this fact_key
    assert len(memories) == 1
    
    # The version should be greater than 1, proving a conflict was resolved
    assert memories[0].version > 1
