"""Unit tests for runtime-owned RAG evidence value contracts."""

from __future__ import annotations

import dataclasses

# pyrefly: ignore [missing-import]
import pytest

from backend.rag.contracts import (
    CitationEvidence,
    ContextBundle,
    GeneratedAnswer,
    RetrievalResult,
)


def test_context_bundle_keeps_selected_evidence_identity():
    item = RetrievalResult(
        chunk_id="doc-1:child:0001:00",
        document_id="doc-1",
        title="Ha Long",
        url="https://vietnam.travel/ha-long",
        score=0.91,
        text="Evidence text",
    )
    bundle = ContextBundle(
        prompt_context="[Nguồn 1: Ha Long]\nEvidence text",
        evidence=(item,),
        citations=(),
        insufficient_evidence=False,
    )
    assert bundle.evidence[0].chunk_id == "doc-1:child:0001:00"
    assert bundle.insufficient_evidence is False


def test_citation_evidence_keeps_retrieval_linkage():
    """Test citation evidence links back to supporting retrieval items."""
    citation = CitationEvidence(
        title="Ha Long",
        url="https://vietnam.travel/ha-long",
        evidence_ids=("doc-1:child:0001:00", "doc-1:child:0002:00"),
    )
    answer = GeneratedAnswer(
        reply="Answer text",
        model="gpt-4o-mini",
        citations=(citation,),
    )
    assert answer.citations[0].evidence_ids[0] == "doc-1:child:0001:00"
    assert answer.citations[0].evidence_ids[1] == "doc-1:child:0002:00"


def test_retrieval_result_allows_missing_score():
    """Test score may be None when a backend does not expose one."""
    item = RetrievalResult(
        chunk_id="child-1",
        document_id="doc-1",
        title="",
        url="",
        score=None,
        text="Evidence text",
    )
    assert item.score is None


def test_contracts_are_frozen():
    """Test runtime contracts are immutable after construction."""
    item = RetrievalResult(
        chunk_id="child-1",
        document_id="doc-1",
        title="Ha Long",
        url="https://vietnam.travel/ha-long",
        score=0.91,
        text="Evidence text",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.chunk_id = "changed"
