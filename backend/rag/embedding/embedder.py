"""Vector Embedding module supporting local sentence-transformers and TEI."""

from __future__ import annotations

import logging
import os
from typing import List

import httpx
from dotenv import load_dotenv

logger = logging.getLogger("travel_agent_embedder")

load_dotenv()

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


class VectorEmbedder:
    """Encodes texts and queries into dense vectors."""

    def __init__(
        self,
        model_name: str | None = None,
        provider: str | None = None,
        tei_url: str | None = None,
        timeout_seconds: float | None = None,
        fallback_to_local: bool | None = None,
    ) -> None:
        """Initialize the vector embedding model.

        Args:
            model_name: HuggingFace model identifier used for local loading and logs.
            provider: Embedding provider, either "local" or "tei".
            tei_url: TEI /embed endpoint URL.
            timeout_seconds: HTTP timeout when calling TEI.
            fallback_to_local: Whether TEI failures should fall back to local model.
        """
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL_NAME", "Alibaba-NLP/gte-multilingual-base")
        self.provider = (provider or os.getenv("EMBEDDING_PROVIDER", "local")).lower()
        self.tei_url = tei_url or os.getenv("TEI_EMBEDDING_URL", "http://localhost:8080/embed")
        self.timeout_seconds = float(timeout_seconds or os.getenv("EMBEDDING_TIMEOUT_SECONDS", "120"))
        self.embedding_dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
        self.batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "8"))
        if fallback_to_local is None:
            fallback_to_local = os.getenv("EMBEDDING_FALLBACK_TO_LOCAL", "false").lower() == "true"
        self.fallback_to_local = fallback_to_local
        self._model = None

    @property
    def model(self):
        """Lazy load the embedding model on first use."""
        if self._model is None:
            if not HAS_SENTENCE_TRANSFORMERS:
                logger.warning("sentence-transformers not installed. Using dummy deterministic embeddings for testing.")
                return None

            logger.info(f"Loading embedding model: '{self.model_name}'...")
            self._model = SentenceTransformer(self.model_name)
            logger.info("Embedding model loaded successfully.")
        return self._model

    def _embed_texts_with_tei(self, texts: List[str]) -> List[List[float]]:
        """Encode texts by calling a TEI /embed endpoint."""
        logger.debug("Calling TEI embedding endpoint: %s", self.tei_url)
        response = httpx.post(
            self.tei_url,
            json={"inputs": texts},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, list):
            raise ValueError(f"Unexpected TEI response type: {type(payload).__name__}")
        if payload and not isinstance(payload[0], list):
            raise ValueError("Unexpected TEI response shape. Expected List[List[float]].")

        return payload

    def _embed_texts_with_tei_batches(self, texts: List[str]) -> List[List[float]]:
        """Encode texts through TEI in bounded batches to avoid large payloads."""
        embeddings: List[List[float]] = []
        batch_size = max(1, self.batch_size)
        total = len(texts)
        for start in range(0, total, batch_size):
            batch = texts[start : start + batch_size]
            logger.info(
                "Embedding batch %s-%s/%s via TEI",
                start + 1,
                start + len(batch),
                total,
            )
            embeddings.extend(self._embed_texts_with_tei(batch))
        return embeddings

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Encode a list of text strings into embedding vectors.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of float vectors.
        """
        if not texts:
            return []

        if self.provider == "tei":
            try:
                return self._embed_texts_with_tei_batches(texts)
            except Exception as err:
                if not self.fallback_to_local:
                    raise RuntimeError(f"TEI embedding request failed: {err}") from err
                logger.warning("TEI embedding failed; falling back to local model: %s", err)

        if self.model is not None:
            embeddings = self.model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
            return embeddings.tolist()

        # Dummy fallback vector generator for offline testing environment
        return [[float((hash(t) + i) % 1000) / 1000.0 for i in range(self.embedding_dimensions)] for t in texts]

    def embed_query(self, query: str) -> List[float]:
        """Encode a single search query string into an embedding vector.

        Args:
            query: The user search query string.

        Returns:
            A single float vector.
        """
        query_text = query.strip()
        if not query_text:
            return [0.0] * self.embedding_dimensions

        embeddings = self.embed_texts([query_text])
        return embeddings[0]
