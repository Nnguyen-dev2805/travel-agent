import sys
from pathlib import Path
# pyrefly: ignore [missing-import]
import pytest
from unittest.mock import MagicMock

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from backend.app.database import SessionLocal, Base, engine
from backend.app.models.memory import MemoryOutbox, UserMemory
from backend.workers.outbox_worker import process_outbox_batch
# pyrefly: ignore [missing-import]
from sqlalchemy import delete

@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    # Clean test data
    db.execute(delete(MemoryOutbox).where(MemoryOutbox.memory_id.like("test_%")))
    db.execute(delete(UserMemory).where(UserMemory.memory_id.like("test_%")))
    db.commit()
    
    yield db
    
    db.execute(delete(MemoryOutbox).where(MemoryOutbox.memory_id.like("test_%")))
    db.execute(delete(UserMemory).where(UserMemory.memory_id.like("test_%")))
    db.commit()
    db.close()

@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.embed_texts.side_effect = lambda texts: [[0.1]*1024 for _ in texts]
    return embedder

@pytest.fixture
def mock_vector_store():
    return MagicMock()

def test_missing_memory(db_session, mock_embedder, mock_vector_store):
    """Test when UserMemory doesn't exist for an UPSERT event."""
    # Insert event but NO UserMemory
    event = MemoryOutbox(memory_id="test_missing_1", action="UPSERT", status="PENDING", retry_count=0)
    db_session.add(event)
    db_session.commit()
    
    processed = process_outbox_batch(db_session, mock_embedder, mock_vector_store, batch_size=50)
    db_session.commit() # Commit the state changes made by worker
    
    assert processed == 1
    
    # Event should be COMPLETED (skipped)
    db_session.refresh(event)
    assert event.status == "COMPLETED"
    
    # ChromaDB should NOT be called
    mock_vector_store.batch_upsert_user_memory.assert_not_called()

def test_chromadb_failure(db_session, mock_embedder, mock_vector_store):
    """Test when ChromaDB throws an exception during batch upsert."""
    mem = UserMemory(memory_id="test_chroma_1", user_id="u1", fact_type="f", fact_key="k", content="C")
    event = MemoryOutbox(memory_id="test_chroma_1", action="UPSERT", status="PENDING", retry_count=0)
    db_session.add_all([mem, event])
    db_session.commit()
    
    # Force ChromaDB to fail
    mock_vector_store.batch_upsert_user_memory.side_effect = Exception("Network timeout")
    
    process_outbox_batch(db_session, mock_embedder, mock_vector_store, batch_size=50)
    db_session.commit()
    
    db_session.refresh(event)
    assert event.status == "FAILED"
    assert event.retry_count == 1
    assert "Network timeout" in event.error_message

def test_mixed_batch(db_session, mock_embedder, mock_vector_store):
    """Test a batch containing both UPSERT and DELETE events."""
    mem1 = UserMemory(memory_id="test_mixed_1", user_id="u1", fact_type="f", fact_key="k1", content="C1")
    event1 = MemoryOutbox(memory_id="test_mixed_1", action="UPSERT", status="PENDING")
    
    event2 = MemoryOutbox(memory_id="test_mixed_2", action="DELETE", status="PENDING")
    
    db_session.add_all([mem1, event1, event2])
    db_session.commit()
    
    processed = process_outbox_batch(db_session, mock_embedder, mock_vector_store, batch_size=50)
    db_session.commit()
    
    assert processed == 2
    db_session.refresh(event1)
    db_session.refresh(event2)
    
    assert event1.status == "COMPLETED"
    assert event2.status == "COMPLETED"
    
    # Verify both VectorStore methods were called
    mock_vector_store.batch_upsert_user_memory.assert_called_once()
    mock_vector_store.batch_delete_user_memory.assert_called_once_with(["test_mixed_2"])

def test_batch_boundaries(db_session, mock_embedder, mock_vector_store):
    """Test BATCH_SIZE limits."""
    # Insert 60 events
    for i in range(60):
        db_session.add(MemoryOutbox(memory_id=f"test_bound_{i}", action="DELETE", status="PENDING"))
    db_session.commit()
    
    # Process with batch_size=50
    processed = process_outbox_batch(db_session, mock_embedder, mock_vector_store, batch_size=50)
    db_session.commit()
    
    assert processed == 50
    mock_vector_store.batch_delete_user_memory.assert_called_once()
    deleted_ids = mock_vector_store.batch_delete_user_memory.call_args[0][0]
    assert len(deleted_ids) == 50
