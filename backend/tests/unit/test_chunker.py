# pyrefly: ignore [missing-import]
import json
from pathlib import Path

import pytest

from backend.rag.chunking import DocumentChunker, TextChunk, load_jsonl_dataset

ROOT_DIR = Path(__file__).resolve().parents[3]
DATASET_PATH = ROOT_DIR / "data" / "processed" / "vietnam_travel_raw.jsonl"

requires_dataset = pytest.mark.skipif(
    not DATASET_PATH.exists(),
    reason=(
        f"generated artifact absent: {DATASET_PATH} "
        "(data/ is git-ignored, so this check cannot run on a clean checkout)"
    ),
)

FIXTURE_DOCS = [
    {
        "document_id": f"fixture_doc_{index:02d}",
        "url": f"https://vietnam.travel/fixture-{index}",
        "title": f"Fixture document {index}",
        "text": f"Body text for fixture document {index}. " * 6,
    }
    for index in range(1, 4)
]


def _write_jsonl(path: Path, docs: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(doc, ensure_ascii=False) for doc in docs) + "\n",
        encoding="utf-8",
    )
    return path


def test_the_loader_reads_a_fixture_dataset(tmp_path: Path):
    """The loader's behaviour, asserted where the repository is the only input.

    The previous version read a git-ignored artifact and asserted a lower bound,
    so it failed on a clean checkout and could not detect a truncation when the
    artifact was present.
    """
    path = _write_jsonl(tmp_path / "fixture.jsonl", FIXTURE_DOCS)

    docs = load_jsonl_dataset(path)

    assert len(docs) == len(FIXTURE_DOCS), "an exact count, not a lower bound"
    assert [doc["document_id"] for doc in docs] == [
        doc["document_id"] for doc in FIXTURE_DOCS
    ], "order and identity must survive the round trip"
    assert set(docs[0]) >= {"document_id", "url", "title", "text"}
    assert docs[0]["text"]


def test_the_loader_fails_closed_on_an_empty_file(tmp_path: Path):
    """An empty corpus is an error, not a silent empty result.

    Established by observation, not assumption: `load_jsonl_dataset` raises
    rather than returning an empty list, which is the fail-closed behaviour a
    caller can act on.
    """
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="No valid document records"):
        load_jsonl_dataset(path)


@requires_dataset
def test_loader_real_dataset():
    """The generated corpus loads whole, if it has been generated.

    Skipped rather than failed when absent: `data/` is git-ignored, so a clean
    checkout has no corpus to read. The expected count is derived from the file
    rather than hardcoded, so the assertion cannot drift from the artifact — and
    it is exact, so a truncation fails instead of passing a lower bound.
    """
    docs = load_jsonl_dataset(DATASET_PATH)

    expected = sum(
        1
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    assert len(docs) == expected, (
        f"the loader must return every non-blank line: {len(docs)} of {expected}"
    )

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
