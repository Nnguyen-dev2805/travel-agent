"""Unit tests for Chroma result mapping and the KnowledgeRetriever retrieval service."""

from __future__ import annotations

# pyrefly: ignore [missing-import]
import pytest

from backend.rag.contracts import RetrievalResult
from backend.rag.retrieval import service as retrieval_service_module
from backend.rag.retrieval.adapters import map_chroma_result
from backend.rag.retrieval.service import KnowledgeRetriever


def test_map_chroma_result_flattens_provenance():
    result = map_chroma_result(
        {
            "chunk_id": "child-1",
            "text": "source text",
            "score": 0.8,
            "metadata": {
                "document_id": "doc-1",
                "title": "Title",
                "url": "https://example.test/doc-1",
            },
        }
    )
    assert result.chunk_id == "child-1"
    assert result.document_id == "doc-1"
    assert result.title == "Title"
    assert result.url == "https://example.test/doc-1"
    assert result.score == 0.8
    assert result.text == "source text"


def test_map_chroma_result_supports_legacy_source_url():
    """Test legacy source_url metadata key still resolves to url."""
    result = map_chroma_result(
        {
            "chunk_id": "child-2",
            "text": "legacy text",
            "score": 0.5,
            "metadata": {
                "document_id": "doc-2",
                "title": "Legacy",
                "source_url": "https://example.test/legacy",
            },
        }
    )
    assert result.url == "https://example.test/legacy"


def test_map_chroma_result_prefers_url_over_source_url():
    """Test url takes precedence when both url and source_url exist."""
    result = map_chroma_result(
        {
            "chunk_id": "child-3",
            "text": "both keys text",
            "score": 0.5,
            "metadata": {
                "document_id": "doc-3",
                "title": "Both",
                "url": "https://example.test/primary",
                "source_url": "https://example.test/legacy",
            },
        }
    )
    assert result.url == "https://example.test/primary"


def test_map_chroma_result_missing_chunk_id_raises():
    """Test missing chunk identity raises instead of fabricating an ID."""
    with pytest.raises(ValueError):
        map_chroma_result(
            {
                "text": "text",
                "score": 0.5,
                "metadata": {
                    "document_id": "doc-4",
                    "title": "Title",
                },
            }
        )


def test_map_chroma_result_empty_chunk_id_raises():
    """Test blank chunk identity raises instead of fabricating an ID."""
    with pytest.raises(ValueError):
        map_chroma_result(
            {
                "chunk_id": "   ",
                "text": "text",
                "score": 0.5,
                "metadata": {
                    "document_id": "doc-4",
                    "title": "Title",
                },
            }
        )


def test_map_chroma_result_missing_document_id_raises():
    """Test missing document identity raises instead of fabricating an ID."""
    with pytest.raises(ValueError):
        map_chroma_result(
            {
                "chunk_id": "child-5",
                "text": "text",
                "score": 0.5,
                "metadata": {
                    "title": "No document",
                },
            }
        )


def test_map_chroma_result_missing_score_maps_to_none():
    """Test absent score maps to None per the retrieval result contract."""
    result = map_chroma_result(
        {
            "chunk_id": "child-6",
            "text": "text",
            "metadata": {
                "document_id": "doc-6",
                "title": "Title",
            },
        }
    )
    assert result.score is None


class FakeEmbedder:
    """Deterministic embedder fake recording embed_query calls."""

    def __init__(self) -> None:
        self.embed_calls: list[str] = []
        self.return_vector: list[float] = [0.25, 0.5, 0.75]

    def embed_query(self, query: str) -> list[float]:
        self.embed_calls.append(query)
        return list(self.return_vector)


class FakeVectorStore:
    """Deterministic vector-store fake recording search_similar calls."""

    def __init__(self, results: list[dict]) -> None:
        self.results = results
        self.search_calls: list[dict] = []

    def search_similar(self, query_embedding: list[float], top_k: int = 4) -> list[dict]:
        self.search_calls.append(
            {"query_embedding": query_embedding, "top_k": top_k}
        )
        return [dict(item) for item in self.results]


def _raw_item(
    chunk_id: str, document_id: str, title: str, url: str, text: str, score: float
) -> dict:
    """Build one raw Chroma search result in the vector-store result shape."""
    return {
        "chunk_id": chunk_id,
        "text": text,
        "metadata": {"document_id": document_id, "title": title, "url": url},
        "score": score,
    }


def test_knowledge_retriever_embeds_query_and_uses_configured_top_k():
    """retrieve() embeds the query once and passes the configured top_k to the store."""
    embedder = FakeEmbedder()
    store = FakeVectorStore(results=[])
    retriever = KnowledgeRetriever(embedder=embedder, vector_store=store, top_k=6)

    retriever.retrieve("Hà Nội có gì đẹp?")

    assert embedder.embed_calls == ["Hà Nội có gì đẹp?"]
    assert store.search_calls == [
        {"query_embedding": embedder.return_vector, "top_k": 6}
    ]


def test_knowledge_retriever_maps_every_item_in_order():
    """Every raw store item maps through map_chroma_result, preserving order and values."""
    embedder = FakeEmbedder()
    store = FakeVectorStore(
        results=[
            _raw_item(
                "doc-1:child:0001:00",
                "doc-1",
                "Ha Long",
                "https://vietnam.travel/ha-long",
                "First evidence text",
                0.91,
            ),
            _raw_item(
                "doc-2:child:0002:00",
                "doc-2",
                "Hoi An",
                "https://vietnam.travel/hoi-an",
                "Second evidence text",
                0.72,
            ),
            _raw_item(
                "doc-3:child:0003:00",
                "doc-3",
                "Da Nang",
                "https://vietnam.travel/da-nang",
                "Third evidence text",
                None,
            ),
        ]
    )
    retriever = KnowledgeRetriever(embedder=embedder, vector_store=store)

    results = retriever.retrieve("Bãi biển nào đẹp?")

    assert all(isinstance(item, RetrievalResult) for item in results)
    assert [item.chunk_id for item in results] == [
        "doc-1:child:0001:00",
        "doc-2:child:0002:00",
        "doc-3:child:0003:00",
    ]
    assert [item.title for item in results] == ["Ha Long", "Hoi An", "Da Nang"]
    assert [item.url for item in results] == [
        "https://vietnam.travel/ha-long",
        "https://vietnam.travel/hoi-an",
        "https://vietnam.travel/da-nang",
    ]
    assert [item.score for item in results] == [0.91, 0.72, None]
    assert [item.text for item in results] == [
        "First evidence text",
        "Second evidence text",
        "Third evidence text",
    ]
    assert [item.document_id for item in results] == ["doc-1", "doc-2", "doc-3"]


def test_knowledge_retriever_top_k_parameter_overrides_constructor_default():
    """An explicit retrieve(top_k=...) overrides the constructor default."""
    embedder = FakeEmbedder()
    store = FakeVectorStore(results=[])
    retriever = KnowledgeRetriever(embedder=embedder, vector_store=store, top_k=6)

    retriever.retrieve("Q?", top_k=2)

    assert store.search_calls == [
        {"query_embedding": embedder.return_vector, "top_k": 2}
    ]


def test_knowledge_retriever_default_construction_uses_module_defaults(monkeypatch):
    """Default construction builds the module-level embedder/store factories exactly once."""
    embedder = FakeEmbedder()
    store = FakeVectorStore(results=[])
    embedder_kwargs: list[dict] = []
    store_kwargs: list[dict] = []

    def fake_embedder_factory(*args, **kwargs):
        embedder_kwargs.append(kwargs)
        return embedder

    def fake_store_factory(*args, **kwargs):
        store_kwargs.append(kwargs)
        return store

    monkeypatch.setattr(
        retrieval_service_module, "VectorEmbedder", fake_embedder_factory
    )
    monkeypatch.setattr(
        retrieval_service_module, "ChromaVectorStore", fake_store_factory
    )

    retriever = KnowledgeRetriever()
    assert retriever.embedder is embedder
    assert retriever.vector_store is store
    assert embedder_kwargs == [{"model_name": "BAAI/bge-m3"}]
    assert store_kwargs == [{"collection_name": "vietnam_travel_parent_child"}]

    retriever.retrieve("Thủ đô Việt Nam là gì?")
    assert store.search_calls == [
        {"query_embedding": embedder.return_vector, "top_k": 4}
    ]
