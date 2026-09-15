"""Unit tests for ContextArbiter.

Governed by Plan v0.15, Spec v0.7, and ADR 0039:
- Owns context admission, precedence, and projection to GenerationContext.
- ContextMode.NONE -> ContextSufficiency.NOT_REQUIRED, citations=().
- ContextMode.RAG_ONLY -> preserves legacy top_k=4 travel context & citations;
  insufficient_evidence=True maps to ContextSufficiency.INSUFFICIENT.
- ContextMode.MEMORY_ONLY -> bounded structured Memory (<= 8 records), 0 travel citations;
  valid selection -> ContextSufficiency.SUFFICIENT, empty -> ContextSufficiency.INSUFFICIENT.
- ContextMode.BOTH -> complete bounded RAG context + bounded structured Memory without
  arbitrary percentage split or dropping travel evidence. Travel citations only.
- RAG retrieval provenance preserved outside the neutral contract.
- Never copies raw RetrievalResult.text or raw Memory evidence as an instruction channel.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.generation.contracts import (
    ContextSufficiency,
    GenerationCitation,
    GenerationContext,
)
from backend.memory.read_models import AbstentionReason, MemorySelection, SelectedMemory
from backend.memory.write_pipeline.models import Authority, MemoryScope
from backend.orchestration.turn_models import ContextMode
from backend.rag.contracts import CitationEvidence, ContextBundle, RetrievalResult


def _sample_rag_bundle(
    prompt_context: str = "Thành phố Đà Nẵng có bãi biển Mỹ Khê nổi tiếng.",
    insufficient_evidence: bool = False,
) -> ContextBundle:
    retrieval = RetrievalResult(
        chunk_id="chunk-1",
        document_id="doc-1",
        title="Cẩm nang Đà Nẵng",
        url="https://example.com/danang",
        score=0.95,
        text="Đà Nẵng có bãi biển Mỹ Khê.",
    )
    citation = CitationEvidence(
        title="Cẩm nang Đà Nẵng",
        url="https://example.com/danang",
        evidence_ids=("chunk-1",),
    )
    return ContextBundle(
        prompt_context=prompt_context,
        evidence=(retrieval,),
        citations=(citation,),
        insufficient_evidence=insufficient_evidence,
    )


def _sample_memory_selection(
    key: str = "travel.preference.hotel_atmosphere",
    value: str = "quiet",
) -> MemorySelection:
    mem = SelectedMemory(
        version_id="ver-1",
        canonical_key=key,
        normalized_value=value,
        scope=MemoryScope.USER,
        scope_id="user-1",
        authority=Authority.EXPLICIT_SAVE,
        valid_from=datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc),
    )
    return MemorySelection(selected=(mem,))


# ---------------------------------------------------------------------------
# Mode: NONE
# ---------------------------------------------------------------------------


def test_arbiter_none_mode_returns_not_required():
    from backend.orchestration.context_arbiter import ContextArbiter

    arbiter = ContextArbiter()
    ctx = arbiter.arbitrate(ContextMode.NONE)

    assert isinstance(ctx, GenerationContext)
    assert ctx.sufficiency is ContextSufficiency.NOT_REQUIRED
    assert ctx.citations == ()
    assert ctx.prompt_context == ""


# ---------------------------------------------------------------------------
# Mode: RAG_ONLY
# ---------------------------------------------------------------------------


def test_arbiter_rag_only_sufficient_preserves_bundle():
    from backend.orchestration.context_arbiter import ContextArbiter

    arbiter = ContextArbiter()
    bundle = _sample_rag_bundle()
    ctx = arbiter.arbitrate(ContextMode.RAG_ONLY, rag_bundle=bundle)

    assert ctx.sufficiency is ContextSufficiency.SUFFICIENT
    assert len(ctx.citations) == 1
    assert ctx.citations[0] == GenerationCitation(
        title="Cẩm nang Đà Nẵng",
        url="https://example.com/danang",
    )
    assert bundle.prompt_context in ctx.prompt_context
    assert "=== CẨM NANG DU LỊCH THAM KHẢO ===" in ctx.prompt_context


def test_arbiter_rag_only_insufficient_evidence():
    from backend.orchestration.context_arbiter import ContextArbiter

    arbiter = ContextArbiter()
    bundle = _sample_rag_bundle(insufficient_evidence=True)
    ctx = arbiter.arbitrate(ContextMode.RAG_ONLY, rag_bundle=bundle)

    assert ctx.sufficiency is ContextSufficiency.INSUFFICIENT
    assert ctx.citations == ()


def test_arbiter_rag_only_missing_bundle_is_insufficient():
    from backend.orchestration.context_arbiter import ContextArbiter

    arbiter = ContextArbiter()
    ctx = arbiter.arbitrate(ContextMode.RAG_ONLY, rag_bundle=None)

    assert ctx.sufficiency is ContextSufficiency.INSUFFICIENT
    assert ctx.citations == ()


# ---------------------------------------------------------------------------
# Mode: MEMORY_ONLY
# ---------------------------------------------------------------------------


def test_arbiter_memory_only_sufficient_has_zero_travel_citations():
    from backend.orchestration.context_arbiter import ContextArbiter

    arbiter = ContextArbiter()
    sel = _sample_memory_selection()
    ctx = arbiter.arbitrate(ContextMode.MEMORY_ONLY, memory_selection=sel)

    assert ctx.sufficiency is ContextSufficiency.SUFFICIENT
    # Memory is NEVER a travel citation
    assert ctx.citations == ()
    assert "travel.preference.hotel_atmosphere" in ctx.prompt_context
    assert "quiet" in ctx.prompt_context


def test_arbiter_memory_only_empty_selection_is_insufficient():
    from backend.orchestration.context_arbiter import ContextArbiter

    arbiter = ContextArbiter()
    sel = MemorySelection(selected=(), abstention_reason=AbstentionReason.NO_ELIGIBLE_MEMORY)
    ctx = arbiter.arbitrate(ContextMode.MEMORY_ONLY, memory_selection=sel)

    assert ctx.sufficiency is ContextSufficiency.INSUFFICIENT
    assert ctx.citations == ()


def test_arbiter_memory_only_missing_selection_is_insufficient():
    from backend.orchestration.context_arbiter import ContextArbiter

    arbiter = ContextArbiter()
    ctx = arbiter.arbitrate(ContextMode.MEMORY_ONLY, memory_selection=None)

    assert ctx.sufficiency is ContextSufficiency.INSUFFICIENT
    assert ctx.citations == ()


# ---------------------------------------------------------------------------
# Mode: BOTH
# ---------------------------------------------------------------------------


def test_arbiter_both_combines_bounded_rag_and_memory_without_truncation():
    from backend.orchestration.context_arbiter import ContextArbiter

    arbiter = ContextArbiter()
    bundle = _sample_rag_bundle(prompt_context="Thông tin Đà Nẵng")
    sel = _sample_memory_selection(key="travel.preference.budget_level", value="luxury")

    ctx = arbiter.arbitrate(ContextMode.BOTH, rag_bundle=bundle, memory_selection=sel)

    assert ctx.sufficiency is ContextSufficiency.SUFFICIENT
    # Citations are travel citations only
    assert len(ctx.citations) == 1
    assert ctx.citations[0].title == "Cẩm nang Đà Nẵng"
    # Prompt context contains BOTH RAG context and Memory context
    assert "Thông tin Đà Nẵng" in ctx.prompt_context
    assert "travel.preference.budget_level" in ctx.prompt_context
    assert "luxury" in ctx.prompt_context


def test_arbiter_both_insufficient_rag_yields_insufficient():
    from backend.orchestration.context_arbiter import ContextArbiter

    arbiter = ContextArbiter()
    bundle = _sample_rag_bundle(insufficient_evidence=True)
    sel = _sample_memory_selection()

    ctx = arbiter.arbitrate(ContextMode.BOTH, rag_bundle=bundle, memory_selection=sel)

    # If the travel grounding source failed, whole context is insufficient
    assert ctx.sufficiency is ContextSufficiency.INSUFFICIENT
