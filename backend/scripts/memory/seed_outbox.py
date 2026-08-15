"""Script to seed 10 PENDING outbox events for manual concurrency testing."""
import sys
import os
from pathlib import Path

# Add project root to PYTHONPATH so we can import backend modules
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from backend.app.database import SessionLocal, engine, Base
from backend.app.models.memory import MemoryOutbox

def seed_outbox():
    # Ensure tables exist for manual testing
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    print("Seeding 10 dummy PENDING events to MemoryOutbox...")
    
    for i in range(1, 11):
        event = MemoryOutbox(
            memory_id=i,  # Dummy memory ID
            action="UPSERT",
            status="PENDING",
            retry_count=0
        )
        db.add(event)
    
    db.commit()
    print("Seeding complete. Run two instances of 'python backend/workers/outbox_worker.py' to observe.")
    db.close()

if __name__ == "__main__":
    seed_outbox()
