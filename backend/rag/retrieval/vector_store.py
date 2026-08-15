"""ChromaDB Vector Store management module supporting Dual Collections and Parent-Child Chunks."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
# pyrefly: ignore [missing-import]
import chromadb
# pyrefly: ignore [missing-import]
from chromadb.config import Settings
from backend.rag.chunking.chunker import TextChunk
from backend.rag.chunking.parent_child_chunker import ChildChunk

logger = logging.getLogger("travel_agent_vector_store")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_CHROMADB_DIR = ROOT_DIR / "data" / "chromadb"


class ChromaVectorStore:
    """Manages persistent ChromaDB vector storage and similarity retrieval."""

    def __init__(
        self,
        persist_directory: Optional[Path] = None,
        collection_name: str = "vietnam_travel_knowledge",
    ) -> None:
        """Initialize ChromaDB client and collection.

        Args:
            persist_directory: Path to persistent storage on disk.
            collection_name: ChromaDB collection identifier.
        """
        self.persist_directory = persist_directory or DEFAULT_CHROMADB_DIR
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name

        logger.info(f"Connecting to ChromaDB at: {self.persist_directory}")
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "Vietnam Travel Knowledge Base Vectors"},
        )

    def add_chunks(
        self, chunks: List[TextChunk], embeddings: List[List[float]]
    ) -> int:
        """Store Baseline TextChunks and their vectors in ChromaDB."""
        if not chunks or not embeddings:
            return 0

        if len(chunks) != len(embeddings):
            raise ValueError("Length of chunks and embeddings must match exactly.")

        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.text for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]

        batch_size = 200
        total_added = 0

        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_docs = documents[i : i + batch_size]
            batch_metas = metadatas[i : i + batch_size]
            batch_embeds = embeddings[i : i + batch_size]

            self.collection.upsert(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_metas,
                embeddings=batch_embeds,
            )
            total_added += len(batch_ids)

        logger.info(f"Upserted {total_added} baseline chunks into collection '{self.collection_name}'.")
        return total_added

    def add_parent_child_chunks(
        self, child_chunks: List[ChildChunk], embeddings: List[List[float]]
    ) -> int:
        """Store ChildChunks (using retrieval_text for embedding, source_text in metadata) in ChromaDB."""
        if not child_chunks or not embeddings:
            return 0

        if len(child_chunks) != len(embeddings):
            raise ValueError("Length of child_chunks and embeddings must match exactly.")

        ids = [chunk.child_id for chunk in child_chunks]
        documents = [chunk.retrieval_text for chunk in child_chunks]
        metadatas = [
            {
                "child_id": chunk.child_id,
                "parent_id": chunk.parent_id,
                "document_id": chunk.document_id,
                "heading": chunk.heading,
                "heading_path": " > ".join(chunk.heading_path),
                "source_text": chunk.source_text,
                "word_count": chunk.word_count,
                "url": str(chunk.metadata.get("url") or ""),
                "title": str(chunk.metadata.get("title") or ""),
                "language": str(chunk.metadata.get("language") or "en"),
            }
            for chunk in child_chunks
        ]

        batch_size = 200
        total_added = 0

        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_docs = documents[i : i + batch_size]
            batch_metas = metadatas[i : i + batch_size]
            batch_embeds = embeddings[i : i + batch_size]

            self.collection.upsert(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_metas,
                embeddings=batch_embeds,
            )
            total_added += len(batch_ids)

        logger.info(f"Upserted {total_added} parent-child chunks into collection '{self.collection_name}'.")
        return total_added

    def upsert_user_memory(self, memory_id: str, content: str, metadata: Dict[str, Any], embedding: List[float]) -> None:
        """Upsert a single user memory vector into ChromaDB (Phase 3 Outbox)."""
        self.collection.upsert(
            ids=[memory_id],
            documents=[content],
            metadatas=[metadata],
            embeddings=[embedding]
        )
        logger.info(f"Upserted UserMemory {memory_id} into ChromaDB.")

    def batch_upsert_user_memory(self, memory_ids: List[str], contents: List[str], metadatas: List[Dict[str, Any]], embeddings: List[List[float]]) -> None:
        """Upsert a batch of user memory vectors into ChromaDB."""
        if not memory_ids:
            return
            
        self.collection.upsert(
            ids=memory_ids,
            documents=contents,
            metadatas=metadatas,
            embeddings=embeddings
        )
        logger.info(f"Upserted batch of {len(memory_ids)} UserMemories into ChromaDB.")

    def delete_user_memory(self, memory_id: str) -> None:
        """Delete a single user memory vector from ChromaDB (Phase 3 Outbox)."""
        try:
            self.collection.delete(ids=[memory_id])
            logger.info(f"Deleted UserMemory {memory_id} from ChromaDB.")
        except ValueError:
            logger.warning(f"Failed to delete UserMemory {memory_id} from ChromaDB - Not found.")

    def batch_delete_user_memory(self, memory_ids: List[str]) -> None:
        """Delete a batch of user memory vectors from ChromaDB."""
        if not memory_ids:
            return
            
        try:
            self.collection.delete(ids=memory_ids)
            logger.info(f"Deleted batch of {len(memory_ids)} UserMemories from ChromaDB.")
        except ValueError:
            logger.warning(f"Failed to delete batch of UserMemories from ChromaDB - Not found.")

    def search_similar(
        self, query_embedding: List[float], top_k: int = 4, where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Search top-k most similar text chunks for a query embedding.

        Returns:
            List of dictionary items containing chunk_id, text (source_text if present), metadata, and score.
        """
        if not query_embedding:
            return []

        query_kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"]
        }
        if where:
            query_kwargs["where"] = where

        results = self.collection.query(**query_kwargs)

        formatted_results: List[Dict[str, Any]] = []

        if results and results["ids"] and results["ids"][0]:
            ids = results["ids"][0]
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            distances = results["distances"][0]

            for chunk_id, text, meta, dist in zip(ids, docs, metas, distances):
                similarity_score = round(1.0 / (1.0 + float(dist)), 4)
                # Prefer clean source_text from metadata if available
                display_text = meta.get("source_text") if meta and meta.get("source_text") else text
                formatted_results.append(
                    {
                        "chunk_id": chunk_id,
                        "text": display_text,
                        "metadata": meta,
                        "score": similarity_score,
                    }
                )

        return formatted_results

    def count(self) -> int:
        """Return total number of vectors in collection."""
        return self.collection.count()
