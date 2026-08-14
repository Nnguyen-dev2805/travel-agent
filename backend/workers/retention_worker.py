"""Background Worker for Memory Retention Policy Cleanup."""

import time
import logging
from datetime import datetime, timezone, timedelta
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
# pyrefly: ignore [missing-import]
from sqlalchemy import select, and_, or_

from backend.app.database import SessionLocal
from backend.app.models.memory import UserMemory, MemoryOutbox
from backend.memory.enums import MemoryStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("travel_agent_retention_worker")

def process_retention_policy():
    """Archive memories that have expired or haven't been accessed in over 12 months."""
    logger.info("Initializing Memory Retention Cleanup Worker...")
    
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        one_year_ago = now - timedelta(days=365)
        
        # Find active memories that are expired or inactive for > 12 months
        stmt = select(UserMemory).where(
            UserMemory.status.in_([MemoryStatus.ACTIVE.value, MemoryStatus.REINFORCED.value]),
            or_(
                and_(UserMemory.expires_at != None, UserMemory.expires_at < now),
                and_(UserMemory.last_accessed_at != None, UserMemory.last_accessed_at < one_year_ago),
                # If last_accessed_at is None, fallback to updated_at
                and_(UserMemory.last_accessed_at == None, UserMemory.updated_at < one_year_ago)
            )
        )
        
        expired_memories = db.scalars(stmt).all()
        
        if not expired_memories:
            logger.info("No expired memories found.")
            return

        logger.info(f"Found {len(expired_memories)} expired memories to archive.")
        
        for mem in expired_memories:
            # Soft delete
            mem.status = MemoryStatus.DELETED.value
            
            # Create outbox entry to remove from ChromaDB
            outbox_entry = MemoryOutbox(
                memory_id=mem.memory_id,
                action="DELETE",
                status="PENDING"
            )
            db.add(outbox_entry)
            
        db.commit()
        logger.info(f"Successfully archived {len(expired_memories)} memories.")

    except Exception as e:
        logger.error(f"Error during retention cleanup: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    process_retention_policy()
