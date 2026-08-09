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
                "record_type": chunk.record_type,
                "child_id": chunk.child_id,
                "parent_id": chunk.parent_id,
                "document_id": chunk.document_id,
                "heading": chunk.heading,
                "heading_level": chunk.heading_level,
                "heading_path": " > ".join(chunk.heading_path),
                "source_text": chunk.source_text,
                "url": str(chunk.metadata.get("url") or ""),
                "title": str(chunk.metadata.get("title") or ""),
                "language": str(chunk.metadata.get("language") or "en"),
                "source_domain": str(chunk.metadata.get("source_domain") or ""),
                "primary_location": str(chunk.metadata.get("primary_location") or ""),
                "locations": self._flatten_metadata_value(chunk.metadata.get("locations")),
                "region": str(chunk.metadata.get("region") or ""),
                "category": self._flatten_metadata_value(chunk.metadata.get("category")),
                "topic": str(chunk.metadata.get("topic") or ""),
                "entity_type": self._flatten_metadata_value(chunk.metadata.get("entity_type")),
                "content_type": str(chunk.metadata.get("content_type") or ""),
                "section_index": int(chunk.metadata.get("section_index") or 0),
                "chunk_index": int(chunk.metadata.get("chunk_index") or 0),
                "word_count": int(chunk.metadata.get("word_count") or 0),
                "char_length": int(chunk.metadata.get("char_length") or 0),
                "chunker_version": str(chunk.metadata.get("chunker_version") or ""),
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

    @staticmethod
    def _flatten_metadata_value(value: Any) -> str:
        """Flatten list-like metadata values for Chroma compatibility."""
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            return ", ".join(str(item) for item in value if str(item).strip())
        return str(value)

    def search_similar(
        self, query_embedding: List[float], top_k: int = 4
    ) -> List[Dict[str, Any]]:
        """Search top-k most similar text chunks for a query embedding.

        Returns:
            List of dictionary items containing chunk_id, text (source_text if present), metadata, and score.
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
