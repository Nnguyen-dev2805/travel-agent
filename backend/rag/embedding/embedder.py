"""Vector Embedding module using BAAI/bge-m3 / sentence-transformers."""

import logging
from typing import List

logger = logging.getLogger("travel_agent_embedder")

try:
    from sentence_transformers import SentenceTransformer

    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


class VectorEmbedder:
    """Encodes texts and queries into 1024-dimensional dense vectors."""

    def __init__(self, model_name: str = "BAAI/bge-m3") -> None:
        """Initialize the vector embedding model.

        Args:
            model_name: HuggingFace model identifier (default: BAAI/bge-m3).
        """
        self.model_name = model_name
        self._model = None

    def warm(self) -> None:
        """Load the model now, so the first real query does not pay for it.

        `model` is a lazy property, so constructing a `VectorEmbedder` loads
        nothing. Startup used to claim the embedding model was pre-warmed while
        only the object graph existed, which made the first user query carry the
        whole load of a multi-gigabyte checkpoint.
        """
        _ = self.model

    @property
    def model(self):
        """Lazy load the embedding model on first use."""
        if self._model is None:
            if not HAS_SENTENCE_TRANSFORMERS:
                logger.warning(
                    "sentence-transformers not installed; embedding calls will fail closed."
                )
                return None

            logger.info(f"Loading embedding model: '{self.model_name}'...")
            self._model = SentenceTransformer(self.model_name)
            logger.info("Embedding model loaded successfully.")
        return self._model

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Encode a list of text strings into embedding vectors.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of float vectors (1024-dim each).
        """
        if not texts:
            return []

        if self.model is not None:
            embeddings = self.model.encode(
                texts, show_progress_bar=False, normalize_embeddings=True
            )
            return embeddings.tolist()

        # Fail closed: deterministic dummy vectors would silently corrupt
        # retrieval ranking on the online chat path. Evaluation preflight
        # already rejects unevaluated dummy embeddings; the runtime must not
        # produce them either.
        raise RuntimeError(
            "sentence-transformers is not installed; refusing to embed with "
            "dummy vectors. Install the dependency or provide an embedder."
        )

    def embed_query(self, query: str) -> List[float]:
        """Encode a single search query string into an embedding vector.

        Args:
            query: The user search query string.

        Returns:
            A single float vector (1024-dim).
        """
        query_text = query.strip()
        if not query_text:
            return [0.0] * 1024

        embeddings = self.embed_texts([query_text])
        return embeddings[0]
