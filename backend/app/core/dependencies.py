"""Core application dependencies providing singletons for external services."""

import logging
from typing import Optional
# pyrefly: ignore [missing-import]
import httpx
# pyrefly: ignore [missing-import]
from openai import OpenAI

from backend.app.config import settings
from backend.rag.embedding.embedder import VectorEmbedder
from backend.rag.retrieval.vector_store import ChromaVectorStore

logger = logging.getLogger("travel_agent_core_deps")

_llm_client: Optional[OpenAI] = None
_vector_embedder: Optional[VectorEmbedder] = None
_user_memory_store: Optional[ChromaVectorStore] = None
_rag_store: Optional[ChromaVectorStore] = None
_episodic_memory_store: Optional[ChromaVectorStore] = None


def get_llm_client() -> OpenAI:
    """Provide a singleton instance of the OpenAI client."""
    global _llm_client
    if _llm_client is None:
        if not settings.GOOGLE_API_KEY:
            logger.warning("GOOGLE_API_KEY is not set. LLM features may fail.")
        _llm_client = OpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.GOOGLE_API_KEY or "dummy_key",
            timeout=httpx.Timeout(30.0)
        )
        logger.info("Initialized OpenAI Client singleton.")
    return _llm_client


def get_vector_embedder() -> VectorEmbedder:
    """Provide a singleton instance of the VectorEmbedder.
    Note: Pre-loads the ML model into memory.
    """
    global _vector_embedder
    if _vector_embedder is None:
        logger.info("Initializing VectorEmbedder singleton (this may take a moment)...")
        _vector_embedder = VectorEmbedder(model_name="BAAI/bge-m3")
        logger.info("VectorEmbedder singleton initialized.")
    return _vector_embedder


def get_user_memory_store() -> ChromaVectorStore:
    """Provide a singleton instance of the ChromaVectorStore for user_memory."""
    global _user_memory_store
    if _user_memory_store is None:
        logger.info("Initializing ChromaVectorStore for user_memory...")
        _user_memory_store = ChromaVectorStore(collection_name="user_memory")
    return _user_memory_store


def get_rag_store() -> ChromaVectorStore:
    """Provide a singleton instance of the ChromaVectorStore for RAG."""
    global _rag_store
    if _rag_store is None:
        logger.info("Initializing ChromaVectorStore for RAG (vietnam_travel_parent_child)...")
        _rag_store = ChromaVectorStore(collection_name="vietnam_travel_parent_child")
    return _rag_store


def get_episodic_memory_store() -> ChromaVectorStore:
    """Provide a singleton instance of the ChromaVectorStore for episodic_memory."""
    global _episodic_memory_store
    if _episodic_memory_store is None:
        logger.info("Initializing ChromaVectorStore for episodic_memory...")
        _episodic_memory_store = ChromaVectorStore(collection_name="episodic_memory")
    return _episodic_memory_store


def get_short_term_memory_service() -> "ShortTermMemoryService":
    """Provide a new instance of ShortTermMemoryService."""
    from backend.memory.short_term_memory import ShortTermMemoryService
    return ShortTermMemoryService()


def get_episodic_memory_service() -> "EpisodicMemoryService":
    """Provide a new instance of EpisodicMemoryService with injected singletons."""
    from backend.memory.episodic_memory import EpisodicMemoryService
    return EpisodicMemoryService(
        llm_client=get_llm_client(),
        vector_store=get_episodic_memory_store(),
        embedder=get_vector_embedder(),
    )
