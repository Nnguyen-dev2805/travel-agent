"""Background Worker for syncing Memory Outbox events to ChromaDB."""

import time
import logging
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
# pyrefly: ignore [missing-import]
from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models.memory import MemoryOutbox, UserMemory
from backend.rag.embedding.embedder import VectorEmbedder
from backend.rag.retrieval.vector_store import ChromaVectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("travel_agent_outbox_worker")


def process_outbox_events():
    """Poll the database for PENDING outbox events and process them."""
    logger.info("Initializing Memory Outbox Worker...")
    
    embedder = VectorEmbedder()
    vector_store = ChromaVectorStore(collection_name="user_memory")

    while True:
        db: Session = SessionLocal()
        try:
            # 1. Fetch pending events (process 10 at a time)
            stmt = select(MemoryOutbox).where(MemoryOutbox.status == "PENDING").limit(10)
            events = db.scalars(stmt).all()

            if not events:
                time.sleep(5) # Sleep if nothing to do
                continue

            logger.info(f"Found {len(events)} pending outbox events to process.")

            for event in events:
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
