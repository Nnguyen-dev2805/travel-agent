"""Structured retrieval service mapping vector-store results to runtime contracts."""

from __future__ import annotations

from typing import Optional

from backend.rag.contracts import RetrievalResult
from backend.rag.embedding import VectorEmbedder
from backend.rag.retrieval.adapters import map_chroma_result
from backend.rag.retrieval.vector_store import ChromaVectorStore

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_COLLECTION_NAME = "vietnam_travel_parent_child"


class KnowledgeRetriever:
    """Retrieves ordered structured evidence from the travel knowledge store.

    Embeds the user query with the configured embedder, queries the configured
    Chroma collection, and maps every raw result through ``map_chroma_result``
    into ``RetrievalResult`` contracts. Dependencies are injectable for tests;
    when omitted, production defaults construct a ``VectorEmbedder`` and a
    ``ChromaVectorStore``.
    """

    def __init__(
        self,
        embedder: Optional[VectorEmbedder] = None,
        vector_store: Optional[ChromaVectorStore] = None,
        top_k: int = 4,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        self.embedder = embedder or VectorEmbedder(model_name=DEFAULT_EMBEDDING_MODEL)
        self.vector_store = vector_store or ChromaVectorStore(
            collection_name=collection_name
        )
        self.top_k = top_k

    def retrieve(self, query: str, top_k: Optional[int] = None) -> list[RetrievalResult]:
        """Embed the query and return mapped evidence in retrieval order.

        Args:
            query: User query string.
            top_k: Number of results to request; overrides the constructor
                default when provided.

        Returns:
            Ordered ``RetrievalResult`` list, one per raw store item.
        """
        resolved_top_k = top_k if top_k is not None else self.top_k
        query_vector = self.embedder.embed_query(query)
        raw_results = self.vector_store.search_similar(
            query_vector, top_k=resolved_top_k
        )
        return [map_chroma_result(item) for item in raw_results]
