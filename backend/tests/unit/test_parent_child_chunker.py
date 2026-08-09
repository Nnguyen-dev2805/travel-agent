"""Unit tests for ParentChildChunker module."""

from __future__ import annotations

import pytest
from backend.rag.chunking.parent_child_chunker import ParentChildChunker


@pytest.fixture
def sample_document():
    return {
        "document_id": "test_doc_001",
        "raw_title": "7 Stunning Rooftop Bars in Vietnam | Vietnam Tourism",
        "clean_title": "7 Stunning Rooftop Bars in Vietnam",
        "url": "https://vietnam.travel/things-to-do/7-stunning-rooftop-bars-vietnam",
        "language": "en",
        "source_domain": "vietnam.travel",
        "meta_description": "A guide to rooftop bars across Vietnam.",
        "sections": [
            {
                "heading": "Best for river views: Sky 36, Da Nang",
                "heading_level": 2,
                "heading_path": [
                    "7 Stunning Rooftop Bars in Vietnam",
                    "Click the image below for a 360-degree tour",
                    "Best for river views: Sky 36, Da Nang",
                ],
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Sky 36 is the highest rooftop bar in Da Nang offering panoramic views over Han River and Dragon Bridge.",
                        "order": 1,
                    }
                ],
            },
            {
                "heading": "Best for after-dinner drinks: The Summit, Hanoi",
                "heading_level": 2,
                "heading_path": [
                    "7 Stunning Rooftop Bars in Vietnam",
                    "Best for after-dinner drinks: The Summit, Hanoi",
                ],
                "text": "Located on the top floor of Pan Pacific Hanoi, The Summit offers sunset views over West Lake and Truc Bach Lake.",
            },
        ],
    }


def test_parent_child_chunker_clean_title_and_summary(sample_document):
    chunker = ParentChildChunker(summary_max_words=30)
    parent, children = chunker.chunk_document(sample_document)

    assert parent.document_id == "test_doc_001"
    assert parent.clean_title == "7 Stunning Rooftop Bars in Vietnam"
    assert parent.parent_id == "test_doc_001:parent:document"
    assert parent.record_type == "parent"
    assert parent.url == "https://vietnam.travel/things-to-do/7-stunning-rooftop-bars-vietnam"
    assert parent.language == "en"
    assert parent.source_domain == "vietnam.travel"
    assert parent.metadata["chunker_version"] == "parent_child_v1"
    assert len(parent.child_ids) == len(children)
    assert len(children) > 0


def test_child_chunks_dual_text_fields(sample_document):
    chunker = ParentChildChunker()
    _, children = chunker.chunk_document(sample_document)

    for child in children:
        assert child.child_id.startswith("test_doc_001:child:")
        assert child.parent_id == "test_doc_001:parent:document"
        assert child.record_type == "child"
        assert child.heading_level == 2
        assert child.source_text != ""
        assert child.retrieval_text != ""
        assert "Article: 7 Stunning Rooftop Bars in Vietnam" in child.retrieval_text
        assert "Heading path:" in child.retrieval_text
        assert "Category:" in child.retrieval_text
        assert "Language: en" in child.retrieval_text
        assert child.metadata["source_domain"] == "vietnam.travel"
        assert "experience" in child.metadata["category"]
        assert "locations" in child.metadata
        assert child.metadata["content_type"] == "travel_guide"
        assert child.metadata["word_count"] > 0
        assert child.metadata["char_length"] == len(child.source_text)
        assert child.metadata["chunker_version"] == "parent_child_v1"


def test_noise_removal_in_heading_path(sample_document):
    chunker = ParentChildChunker()
    cleaned_path, removed = chunker.clean_heading_path([
        "7 Stunning Rooftop Bars in Vietnam",
        "Click the image below for a 360-degree tour",
        "Sky 36, Da Nang",
    ])

    assert "Click the image below for a 360-degree tour" not in cleaned_path
    assert "Click the image below for a 360-degree tour" in removed
    assert cleaned_path == ["7 Stunning Rooftop Bars in Vietnam", "Sky 36, Da Nang"]
