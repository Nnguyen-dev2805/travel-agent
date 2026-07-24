# pyrefly: ignore [missing-import]
import pytest
from pathlib import Path
from backend.rag.chunking import TextChunk
from backend.rag.embedding import VectorEmbedder
from backend.rag.retrieval import ChromaVectorStore

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TEST_CHROMADB_DIR = ROOT_DIR / "data" / "test_chromadb"


def test_embedder_generation():
    """Test vector embedder returns 1024-dim float vectors."""
    embedder = VectorEmbedder()
    vector = embedder.embed_query("Hà Nội có gì đẹp?")
    assert isinstance(vector, list)
    assert len(vector) == 1024
    assert isinstance(vector[0], float)


def test_chroma_vector_store_add_and_search():
    """Test adding text chunks to ChromaDB and performing similarity search."""
    store = ChromaVectorStore(
        persist_directory=TEST_CHROMADB_DIR,
        collection_name="test_travel_collection",
    )

    sample_chunks = [
        TextChunk(
            chunk_id="test_c1",
            document_id="doc_1",
            text="Skylight Nha Trang is a famous rooftop bar in Vietnam on 43rd floor of Premier Havana Hotel.",
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

    embedder = VectorEmbedder()
    texts = [c.text for c in sample_chunks]
    embeddings = embedder.embed_texts(texts)

    # Add chunks
    added_count = store.add_chunks(sample_chunks, embeddings)
    assert added_count == 2
    assert store.count() >= 2

    # Query similarity
    query_vector = embedder.embed_query("Nha Trang rooftop bar")
    results = store.search_similar(query_vector, top_k=2)

    assert len(results) > 0
    top_result = results[0]
    assert "chunk_id" in top_result
    assert "text" in top_result
    assert "metadata" in top_result
    assert "score" in top_result
    assert top_result["metadata"]["title"] == "7 stunning rooftop bars"
