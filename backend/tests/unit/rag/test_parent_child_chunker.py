"""Unit tests for ParentChildChunker module."""

from __future__ import annotations

import pytest
from backend.rag.chunking.parent_child_chunker import ParentChildChunker


@pytest.fixture
def sample_document():
    return {
        "document_id": "test_doc_001",
        "title": "7 Stunning Rooftop Bars in Vietnam | Vietnam Tourism",
        "url": "https://vietnam.travel/things-to-do/7-stunning-rooftop-bars-vietnam",
        "language": "en",
        "text": """When it comes to rooftop bars, Vietnam is up there with the best in Asia. From Hanoi to Saigon, here are 7 rooftop bars you must visit.

Best for river views: Sky 36, Da Nang
Click the image below for a 360-degree tour
Sky 36 is the highest rooftop bar in Da Nang offering panoramic views over Han River and Dragon Bridge.

Best for after-dinner drinks: The Summit, Hanoi
Located on the top floor of Pan Pacific Hanoi, The Summit offers breathtaking sunset views over West Lake and Truc Bach Lake. Photo by Vietnam Tourism.""",
    }


def test_parent_child_chunker_clean_title_and_summary(sample_document):
    chunker = ParentChildChunker(summary_max_words=30)
    parent, children = chunker.chunk_document(sample_document)

    assert parent.document_id == "test_doc_001"
    assert parent.clean_title == "7 Stunning Rooftop Bars in Vietnam"
    assert parent.parent_id == "test_doc_001:parent:document"
    assert len(parent.child_ids) == len(children)
    assert len(children) > 0


def test_child_chunks_dual_text_fields(sample_document):
    chunker = ParentChildChunker()
    _, children = chunker.chunk_document(sample_document)

    for child in children:
        assert child.child_id.startswith("test_doc_001:child:")
        assert child.parent_id == "test_doc_001:parent:document"
        assert child.source_text != ""
        assert child.retrieval_text != ""
        assert "Article: 7 Stunning Rooftop Bars in Vietnam" in child.retrieval_text
        assert "Source: https://vietnam.travel/" in child.retrieval_text


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
