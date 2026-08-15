"""Background Worker for syncing Memory Outbox events to ChromaDB."""

import time
import logging
import signal
from datetime import datetime, timezone
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
# pyrefly: ignore [missing-import]
from sqlalchemy import select, or_, and_

from backend.app.database import SessionLocal
from backend.app.models.memory import MemoryOutbox, UserMemory
from backend.rag.embedding.embedder import VectorEmbedder
from backend.rag.retrieval.vector_store import ChromaVectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("travel_agent_outbox_worker")

_running = True

def handle_shutdown(signum, frame):
    global _running
    logger.info("Shutdown signal received. Finishing current batch...")
    _running = False

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

def process_outbox_batch(db: Session, embedder, vector_store, batch_size: int = 50) -> int:
    """Process a single batch of outbox events. Returns the number of events processed."""
    # 1. Fetch a batch of pending or retriable failed events securely with SKIP LOCKED
    stmt = select(MemoryOutbox).where(
        or_(
            MemoryOutbox.status == "PENDING",
            and_(MemoryOutbox.status == "FAILED", MemoryOutbox.retry_count < 3)
        )
    ).order_by(MemoryOutbox.created_at.asc()).limit(batch_size).with_for_update(skip_locked=True)
    
    events = list(db.scalars(stmt).all())

    if not events:
        return 0

    logger.info(f"Processing batch of {len(events)} outbox events...")

    upsert_tasks = []
    delete_events = []

    for event in events:
        try:
            # Basic exponential backoff check
            if event.status == "FAILED" and event.retry_count > 0:
                updated_at = event.updated_at if event.updated_at.tzinfo else event.updated_at.replace(tzinfo=timezone.utc)
                time_since_update = (datetime.now(timezone.utc) - updated_at).total_seconds()
                required_backoff = 5 ** event.retry_count
                if time_since_update < required_backoff:
                    continue # Skip this event for now, let it remain in current status, wait for next fetch

            if event.action == "UPSERT":
                # Fetch the memory payload
                mem_stmt = select(UserMemory).where(UserMemory.memory_id == event.memory_id)
                memory = db.scalars(mem_stmt).first()
                
                if not memory:
                    logger.info(f"Skipping UPSERT for {event.memory_id}: UserMemory not found.")
                    event.status = "COMPLETED"
                    continue
                    
                upsert_tasks.append({"event": event, "memory": memory})

            elif event.action == "DELETE":
                delete_events.append(event)
                
        except Exception as e:
            logger.error(f"Error fetching data for outbox event ID {event.id}: {str(e)}")
            event.status = "FAILED"
            event.error_message = f"Fetch Error: {str(e)}"
            event.retry_count += 1

    # -- Xử lý Batch UPSERT với ChromaDB --
    if upsert_tasks:
        try:
            texts = [task["memory"].content for task in upsert_tasks]
            # Embed all texts in one batch call
            embeddings = embedder.embed_texts(texts)
            
            # Prepare metadata with memory_type
            metadatas = [
                {
                    "user_id": task["memory"].user_id,
                    "fact_type": task["memory"].fact_type,
                    "fact_key": task["memory"].fact_key,
                    "status": task["memory"].status,
                    "version": task["memory"].version,
                    "source": "outbox_worker",
                    "memory_type": "semantic_fact"
                }
                for task in upsert_tasks
            ]
            
            ids = [task["event"].memory_id for task in upsert_tasks]
            
            # Batch upsert to ChromaDB
            vector_store.batch_upsert_user_memory(ids, texts, metadatas, embeddings)
            
            # Mark as COMPLETED
            for task in upsert_tasks:
                task["event"].status = "COMPLETED"
                
        except Exception as e:
            logger.error(f"ChromaDB Batch Upsert Error: {str(e)}")
            for task in upsert_tasks:
                task["event"].status = "FAILED"
                task["event"].error_message = f"ChromaDB Error: {str(e)}"
                task["event"].retry_count += 1

    # -- Xử lý Batch DELETE với ChromaDB --
    if delete_events:
        try:
            ids = [e.memory_id for e in delete_events]
            vector_store.batch_delete_user_memory(ids)
            
            for e in delete_events:
                e.status = "COMPLETED"
                
        except Exception as e:
            logger.error(f"ChromaDB Batch Delete Error: {str(e)}")
            for e in delete_events:
                e.status = "FAILED"
                e.error_message = f"ChromaDB Delete Error: {str(e)}"
                e.retry_count += 1

    return len(events)

def process_outbox_events():
    """Poll the database for PENDING outbox events and process them in batches."""
    logger.info("Initializing Memory Outbox Worker (V2 - Batching)...")
    
    embedder = VectorEmbedder()
    vector_store = ChromaVectorStore(collection_name="user_memory")
    
    BATCH_SIZE = 50

    while _running:
        db: Session = SessionLocal()
        try:
            processed_count = process_outbox_batch(db, embedder, vector_store, BATCH_SIZE)
            
            if processed_count == 0:
                db.close()
                time.sleep(5) # Sleep if nothing to do
                continue

            db.commit()

        except Exception as e:
            logger.error(f"Worker transaction failed: {str(e)}")
            db.rollback()
            time.sleep(10) # Backoff on major DB error
        finally:
            db.close()

if __name__ == "__main__":
    process_outbox_events()
