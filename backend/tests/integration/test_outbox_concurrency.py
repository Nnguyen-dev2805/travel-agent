import sys
import time
from pathlib import Path
# pyrefly: ignore [missing-import]
import pytest
from concurrent.futures import ProcessPoolExecutor

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from backend.app.database import SessionLocal, engine, Base
from backend.app.models.memory import MemoryOutbox, UserMemory
# pyrefly: ignore [missing-import]
from sqlalchemy import select, delete

def run_worker_process(worker_id: int) -> int:
    """A standalone worker loop to be run in a separate process."""
    # We must import inside the process to ensure new DB connections
    from backend.app.database import SessionLocal
    from backend.workers.outbox_worker import process_outbox_batch
    
    class DummyEmbedder:
        def embed_texts(self, texts):
            return [[0.1]*1024 for _ in texts]
            
    class DummyVectorStore:
        def __init__(self):
            self.upserts = 0
        def batch_upsert_user_memory(self, ids, texts, metadatas, embeddings):
            self.upserts += len(ids)
        def batch_delete_user_memory(self, ids):
            pass

    embedder = DummyEmbedder()
    vector_store = DummyVectorStore()
    
    total_processed = 0
    empty_polls = 0
    
    while empty_polls < 3: # Break after 3 empty polls
        db = SessionLocal()
        try:
            processed = process_outbox_batch(db, embedder, vector_store, batch_size=20)
            if processed == 0:
                empty_polls += 1
                time.sleep(0.5)
            else:
                total_processed += processed
                empty_polls = 0
            db.commit()
        except Exception as e:
            db.rollback()
        finally:
            db.close()
            
    return total_processed

def test_concurrency_skip_locked():
    """Test that multiple workers can process events concurrently without duplication."""
    if engine.url.drivername.startswith("sqlite"):
        pytest.skip("Concurrency with SKIP LOCKED requires PostgreSQL. SQLite does not support row-level locks.")
        
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    # 1. Clean DB
    db.execute(delete(MemoryOutbox).where(MemoryOutbox.memory_id.like("conc_%")))
    db.execute(delete(UserMemory).where(UserMemory.memory_id.like("conc_%")))
    db.commit()
    
    # 2. Insert 100 events
    memories = []
    events = []
    for i in range(100):
        mem = UserMemory(memory_id=f"conc_{i}", user_id="u1", fact_type="f", fact_key="k", content="C")
        event = MemoryOutbox(memory_id=f"conc_{i}", action="UPSERT", status="PENDING")
        memories.append(mem)
        events.append(event)
        
    db.add_all(memories)
    db.add_all(events)
    db.commit()
    
    # 3. Spin up 3 workers
    with ProcessPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_worker_process, i) for i in range(3)]
        results = [f.result() for f in futures]
        
    # The sum of events processed by all workers should be EXACTLY 100
    # because of SKIP LOCKED, no two workers should process the same event
    total_processed_by_workers = sum(results)
    
    # Verify DB state
    stmt = select(MemoryOutbox).where(MemoryOutbox.memory_id.like("conc_%"))
    final_events = list(db.scalars(stmt).all())
    completed_count = sum(1 for e in final_events if e.status == "COMPLETED")
    
    db.execute(delete(MemoryOutbox).where(MemoryOutbox.memory_id.like("conc_%")))
    db.execute(delete(UserMemory).where(UserMemory.memory_id.like("conc_%")))
    db.commit()
    db.close()
    
    assert total_processed_by_workers == 100
    assert completed_count == 100
