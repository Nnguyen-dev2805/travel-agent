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

def process_outbox_events():
    """Poll the database for PENDING outbox events and process them."""
    logger.info("Initializing Memory Outbox Worker...")
    
    embedder = VectorEmbedder()
    vector_store = ChromaVectorStore(collection_name="user_memory")

    while _running:
        db: Session = SessionLocal()
        try:
            # 1. Fetch pending or retriable failed events (process 10 at a time)
            # Retries only for FAILED events with retry_count < 3
            stmt = select(MemoryOutbox).where(
                or_(
                    MemoryOutbox.status == "PENDING",
                    and_(MemoryOutbox.status == "FAILED", MemoryOutbox.retry_count < 3)
                )
            ).order_by(MemoryOutbox.created_at.asc()).limit(10)
            
            events = db.scalars(stmt).all()

            if not events:
                time.sleep(5) # Sleep if nothing to do
                continue

            logger.info(f"Found {len(events)} pending/retriable outbox events to process.")

            for event in events:
                if not _running:
                    break
                    
                # Basic exponential backoff check: retry_count 1 -> wait 5s, 2 -> wait 25s
                if event.status == "FAILED" and event.retry_count > 0:
                    time_since_update = (datetime.now(timezone.utc) - event.updated_at).total_seconds()
                    required_backoff = 5 ** event.retry_count
                    if time_since_update < required_backoff:
                        continue

                try:
                    if event.action == "UPSERT":
                        # Fetch the memory payload
                        mem_stmt = select(UserMemory).where(UserMemory.memory_id == event.memory_id)
                        memory = db.scalars(mem_stmt).first()
                        
                        if not memory:
                            raise ValueError(f"UserMemory {event.memory_id} not found for UPSERT.")
                        
                        # Embed text
                        embedding = embedder.embed_texts([memory.content])[0]
                        
                        # Prepare metadata
                        metadata = {
                            "user_id": memory.user_id,
                            "fact_type": memory.fact_type,
                            "fact_key": memory.fact_key,
                            "status": memory.status,
                            "version": memory.version,
                            "source": "outbox_worker"
                        }
                        
                        # Upsert to ChromaDB
                        vector_store.upsert_user_memory(
                            memory_id=memory.memory_id,
                            content=memory.content,
                            metadata=metadata,
                            embedding=embedding
                        )

                    elif event.action == "DELETE":
                        # Delete from ChromaDB
                        vector_store.delete_user_memory(memory_id=event.memory_id)

                    # Mark as COMPLETED
                    event.status = "COMPLETED"
                    db.commit()
                    logger.info(f"Processed outbox event ID {event.id} ({event.action} -> {event.memory_id})")

                except Exception as e:
                    logger.error(f"Error processing outbox event ID {event.id}: {str(e)}")
                    event.status = "FAILED"
                    event.error_message = str(e)
                    event.retry_count += 1
                    db.commit()

        except Exception as e:
            logger.error(f"Worker database connection error: {str(e)}")
            time.sleep(10) # Backoff on DB error
        finally:
            db.close()
            time.sleep(1) # Small sleep between batches

if __name__ == "__main__":
    process_outbox_events()
