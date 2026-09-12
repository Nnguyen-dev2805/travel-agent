"""Unit tests for the fail-closed embedding contract.

Deterministic dummy vectors must never flow into retrieval ranking on any
path: without the model backend, embedding calls raise instead of silently
returning plausible-looking vectors.
"""

import pytest

from backend.rag.embedding import embedder as embedder_module
from backend.rag.embedding.embedder import VectorEmbedder


def test_embed_texts_fails_closed_without_backend(monkeypatch):
    monkeypatch.setattr(embedder_module, "HAS_SENTENCE_TRANSFORMERS", False)
    with pytest.raises(RuntimeError, match="sentence-transformers"):
        VectorEmbedder().embed_texts(["Hà Nội có gì đẹp?"])


def test_embed_query_fails_closed_without_backend(monkeypatch):
    monkeypatch.setattr(embedder_module, "HAS_SENTENCE_TRANSFORMERS", False)
    with pytest.raises(RuntimeError, match="sentence-transformers"):
        VectorEmbedder().embed_query("Hà Nội có gì đẹp?")


def test_embed_empty_inputs_still_short_circuit(monkeypatch):
    """Empty inputs return empty results without touching any backend."""
    monkeypatch.setattr(embedder_module, "HAS_SENTENCE_TRANSFORMERS", False)
    assert VectorEmbedder().embed_texts([]) == []
