"""ChromaDB Vector Store management module."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import chromadb
from chromadb.config import Settings
from backend.rag.chunking.chunker import TextChunk

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
        """Store TextChunks and their vectors in ChromaDB.

        Args:
            chunks: List of TextChunk dataclass instances.
            embeddings: List of matching float vectors (1024-dim).

        Returns:
            Number of chunks successfully added/upserted.
        """
        if not chunks or not embeddings:
            return 0

        if len(chunks) != len(embeddings):
            raise ValueError("Length of chunks and embeddings must match exactly.")

        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.text for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]

        # Batch upsert into ChromaDB
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

        logger.info(f"Upserted {total_added} chunks into ChromaDB collection '{self.collection_name}'.")
        return total_added

    def search_similar(
        self, query_embedding: List[float], top_k: int = 4
    ) -> List[Dict[str, Any]]:
        """Search top-k most similar text chunks for a query embedding.

        Args:
            query_embedding: Search query float vector (1024-dim).
            top_k: Number of top documents to retrieve.

        Returns:
            List of dictionary items containing chunk_id, text, metadata, and score.
        """
        if not query_embedding:
            return []

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        formatted_results: List[Dict[str, Any]] = []

        if results and results["ids"] and results["ids"][0]:
            ids = results["ids"][0]
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            distances = results["distances"][0]

            for chunk_id, text, meta, dist in zip(ids, docs, metas, distances):
                # Convert L2 distance to similarity score
                similarity_score = round(1.0 / (1.0 + float(dist)), 4)
                formatted_results.append(
                    {
                        "chunk_id": chunk_id,
                        "text": text,
                        "metadata": meta,
                        "score": similarity_score,
                    }
                )

        return formatted_results

    def count(self) -> int:
        """Return total number of vectors in collection."""
        return self.collection.count()
