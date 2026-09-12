# pyrefly: ignore [missing-import]
"""Vector store and embedder tests.

Split deliberately. `ChromaVectorStore` takes **vectors**, not text, so the store
round trip needs no embedding model at all and must never skip. Only the embedder
itself needs the real weights, and that one skips with its precondition named.

The store test previously wrote to `data/test_chromadb` — a shared path under a
git-ignored directory — and asserted `count() >= 2` against a collection it never
cleared, so leftover state could satisfy it.
"""

from pathlib import Path

import pytest

from backend.rag.chunking import TextChunk
from backend.rag.embedding import VectorEmbedder
from backend.rag.embedding.embedder import HAS_SENTENCE_TRANSFORMERS
from backend.rag.retrieval import ChromaVectorStore

DIMENSIONS = 1024
MODEL_NAME = "BAAI/bge-m3"
MODEL_CACHE_DIR = (
    Path.home() / ".cache" / "huggingface" / "hub"
    / f"models--{MODEL_NAME.replace('/', '--')}"
)


def _embedding_model_available() -> bool:
    """The import **and** the locally cached weights.

    Checking the cache as well as the import matters: with the package installed
    but the weights absent, the test would attempt a multi-gigabyte download
    instead of skipping.
    """
    return HAS_SENTENCE_TRANSFORMERS and MODEL_CACHE_DIR.is_dir()


requires_embedding_model = pytest.mark.skipif(
    not _embedding_model_available(),
    reason=(
        f"embedding weights unavailable: {MODEL_CACHE_DIR} "
        f"(the embedder test needs the real {MODEL_NAME} model)"
    ),
)


def _vector(seed: float) -> list[float]:
    """A deterministic vector. No model, no randomness, no network."""
    return [seed + (index % 7) * 0.001 for index in range(DIMENSIONS)]


def _vectors(count: int) -> list[list[float]]:
    return [_vector(0.1 * (index + 1)) for index in range(count)]


SAMPLE_CHUNKS = [
    TextChunk(
        chunk_id="test_c1",
        document_id="doc_1",
        text=(
            "Skylight Nha Trang is a famous rooftop bar in Vietnam on 43rd floor "
            "of Premier Havana Hotel."
        ),
        metadata={
            "title": "7 stunning rooftop bars",
            "url": "https://vietnam.travel/rooftop",
            "doc_id": "doc_1",
        },
    ),
    TextChunk(
        chunk_id="test_c2",
        document_id="doc_2",
        text="Phở and Bánh Mì are famous traditional street food dishes in Hanoi Vietnam.",
        metadata={
            "title": "Best Food in Vietnam",
            "url": "https://vietnam.travel/food",
            "doc_id": "doc_2",
        },
    ),
]


def test_chroma_store_round_trip_without_a_model(tmp_path: Path):
    """The store takes vectors, so no embedder is needed and nothing is skipped."""
    store = ChromaVectorStore(
        persist_directory=tmp_path / "chroma",
        collection_name="test_travel_collection",
    )

    assert store.count() == 0, "a fresh directory must be empty"

    added = store.add_chunks(SAMPLE_CHUNKS, _vectors(len(SAMPLE_CHUNKS)))
    assert added == 2
    assert store.count() == 2, "an exact count, not a lower bound on a shared path"

    results = store.search_similar(_vector(0.1), top_k=2)

    assert len(results) == 2
    top_result = results[0]
    assert "chunk_id" in top_result
    assert "text" in top_result
    assert "metadata" in top_result
    assert "score" in top_result
    assert top_result["metadata"]["title"] == "7 stunning rooftop bars"


def test_chroma_store_does_not_accumulate_across_instances(tmp_path: Path):
    """Re-opening the same fresh directory must not invent rows."""
    persist = tmp_path / "chroma"

    first = ChromaVectorStore(persist_directory=persist, collection_name="probe")
    first.add_chunks(SAMPLE_CHUNKS, _vectors(len(SAMPLE_CHUNKS)))
    assert first.count() == 2

    second = ChromaVectorStore(persist_directory=persist, collection_name="probe")
    assert second.count() == 2, "re-opening must see the same two rows, not more"


@requires_embedding_model
def test_the_suite_runs_with_the_hub_offline():
    """The embedder test must not depend on reaching huggingface.co.

    `VectorEmbedder.model` calls `SentenceTransformer(model_name)`, and the hub
    checks remote metadata even when the weights are already cached — measured on
    this repository at 11.89s with the network reachable versus 5.83s with
    `HF_HUB_OFFLINE=1`. Where that traffic is *blocked* rather than slow the check
    does not fail, it hangs, and the whole suite hangs with it.

    `backend/tests/conftest.py` pins the run offline before anything can import the
    hub. Asserted here rather than assumed: removing that pin would otherwise
    surface as an intermittent hang, which is the hardest kind of failure to
    attribute to its cause.
    """
    import huggingface_hub.constants as hub

    assert hub.HF_HUB_OFFLINE is True, (
        "the suite is not pinned offline; see backend/tests/conftest.py"
    )


def test_embedder_generation():
    """Test vector embedder returns 1024-dim float vectors."""
    embedder = VectorEmbedder()
    vector = embedder.embed_query("Hà Nội có gì đẹp?")

    assert isinstance(vector, list)
    assert len(vector) == DIMENSIONS
    assert isinstance(vector[0], float)
