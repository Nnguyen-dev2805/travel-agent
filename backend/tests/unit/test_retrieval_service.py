"""Unit tests for Chroma result adapter mapping to runtime evidence contracts."""

from __future__ import annotations

# pyrefly: ignore [missing-import]
import pytest

from backend.rag.retrieval.adapters import map_chroma_result


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
