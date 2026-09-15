"""Unit tests for runtime-owned RAG evidence value contracts.

Governed by Plan v0.15 and Spec v0.7:
- RAG retains RetrievalResult, CitationEvidence, and ContextBundle.
- RetrievalResult score/text/provenance do not leak into the generic generation layer.
- Neutral GenerationResult is tested separately in test_generation_contracts.py.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.rag.contracts import (
    CitationEvidence,
    ContextBundle,
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
    """Test citation evidence links back to supporting retrieval items in ContextBundle."""
    citation = CitationEvidence(
        title="Ha Long",
        url="https://vietnam.travel/ha-long",
        evidence_ids=("doc-1:child:0001:00", "doc-1:child:0002:00"),
    )
    bundle = ContextBundle(
        prompt_context="[Nguồn 1: Ha Long]\nEvidence text",
        evidence=(),
        citations=(citation,),
        insufficient_evidence=False,
    )
    assert bundle.citations[0].evidence_ids[0] == "doc-1:child:0001:00"
    assert bundle.citations[0].evidence_ids[1] == "doc-1:child:0002:00"


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
        item.chunk_id = "changed"  # type: ignore

    citation = CitationEvidence(
        title="Ha Long",
        url="https://vietnam.travel/ha-long",
        evidence_ids=("c1",),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        citation.title = "changed"  # type: ignore

    bundle = ContextBundle(
        prompt_context="text",
        evidence=(item,),
        citations=(citation,),
        insufficient_evidence=False,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        bundle.insufficient_evidence = True  # type: ignore
