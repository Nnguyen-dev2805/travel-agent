# pyrefly: ignore [missing-import]
import pytest
from pathlib import Path
from backend.rag.chunking import load_jsonl_dataset, DocumentChunker, TextChunk

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATASET_PATH = ROOT_DIR / "data" / "vietnam-travel.jsonl"


def test_loader_real_dataset():
    """Test loader reads all 282 documents from vietnam-travel.jsonl."""
    assert DATASET_PATH.exists(), f"Dataset file missing at {DATASET_PATH}"
    docs = load_jsonl_dataset(DATASET_PATH)
    assert len(docs) >= 280
    
    first_doc = docs[0]
    assert "document_id" in first_doc
    assert "url" in first_doc
    assert "title" in first_doc
    assert "text" in first_doc
    assert len(first_doc["text"]) > 0


def test_chunker_basic_splitting():
    """Test chunker splits a sample text within size and overlap constraints."""
    sample_doc = {
        "document_id": "test_doc_01",
        "title": "7 Stunning Rooftop Bars",
        "url": "https://vietnam.travel/sample",
        "text": "Paragraph one. " * 50 + "\n\n" + "Paragraph two. " * 50,
    }

    chunker = DocumentChunker(chunk_size=500, chunk_overlap=100)
    chunks = chunker.chunk_document(sample_doc)

    assert len(chunks) > 1
    for chunk in chunks:
        assert isinstance(chunk, TextChunk)
        assert chunk.document_id == "test_doc_01"
        assert len(chunk.text) <= 600  # Allow slight flexibility for word boundary
        assert chunk.metadata["title"] == "7 Stunning Rooftop Bars"
        assert chunk.metadata["url"] == "https://vietnam.travel/sample"
        assert "chunk_index" in chunk.metadata


def test_chunker_empty_document():
    """Test chunker handles empty text gracefully without crashing."""
    empty_doc = {"document_id": "empty_01", "text": "", "title": "Empty"}
    chunker = DocumentChunker()
    chunks = chunker.chunk_document(empty_doc)
    assert len(chunks) == 0
