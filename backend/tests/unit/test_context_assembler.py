"""Unit tests for ContextAssembler legacy-compatible context and citation assembly."""

from __future__ import annotations

# pyrefly: ignore [missing-import]
import pytest

from backend.rag.contracts import CitationEvidence, ContextBundle, RetrievalResult
from backend.rag.generation.context import ContextAssembler


def _result(
    chunk_id: str,
    title: str,
    url: str,
    text: str,
    score: float | None = 0.9,
) -> RetrievalResult:
    """Build one RetrievalResult fixture directly from the runtime contract."""
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        title=title,
        url=url,
        score=score,
        text=text,
    )


def test_assemble_two_results_formats_prompt_and_preserves_order():
    """Non-empty evidence keeps legacy numbering, separator, and evidence order."""
    assembler = ContextAssembler()
    results = [
        _result("c1", "T1", "https://u1", "text1", score=0.91),
        _result("c2", "T2", "https://u2", "text2", score=0.72),
    ]

    bundle = assembler.assemble(results)

    assert isinstance(bundle, ContextBundle)
    assert bundle.prompt_context == "[Nguồn 1: T1]\ntext1\n\n---\n\n[Nguồn 2: T2]\ntext2"
    assert bundle.evidence == (
        _result("c1", "T1", "https://u1", "text1", score=0.91),
        _result("c2", "T2", "https://u2", "text2", score=0.72),
    )
    assert bundle.insufficient_evidence is False
    assert bundle.citations == (
        CitationEvidence(title="T1", url="https://u1", evidence_ids=("c1",)),
        CitationEvidence(title="T2", url="https://u2", evidence_ids=("c2",)),
    )


def test_assemble_zero_results_is_insufficient_with_legacy_placeholder():
    """Zero results is the only insufficient-evidence path; no score threshold exists."""
    assembler = ContextAssembler()

    bundle = assembler.assemble([])

    assert bundle.insufficient_evidence is True
    assert bundle.evidence == ()
    assert bundle.prompt_context == "Không tìm thấy tài liệu liên quan."
    assert bundle.citations == ()


def test_assemble_groups_citations_by_title_with_later_url_winning():
    """Citations group by title: later URL wins, every chunk id is accumulated."""
    assembler = ContextAssembler()
    results = [
        _result("c1", "T1", "https://u1", "text1"),
        _result("c2", "T2", "https://u2", "text2"),
        _result("c3", "T1", "https://u1-later", "text3"),
        _result("c4", "T4", "", "text4"),
    ]

    bundle = assembler.assemble(results)

    assert bundle.citations == (
        CitationEvidence(title="T1", url="https://u1-later", evidence_ids=("c1", "c3")),
        CitationEvidence(title="T2", url="https://u2", evidence_ids=("c2",)),
    )
    # Group order follows first appearance of the title, and the empty-URL
    # item contributes no citation anywhere.
    assert [c.title for c in bundle.citations] == ["T1", "T2"]
    assert all("c4" not in c.evidence_ids for c in bundle.citations)
    # The empty-URL item is still formatted into the model context.
    assert "[Nguồn 3: T1]\ntext3" in bundle.prompt_context
    assert "[Nguồn 4: T4]\ntext4" in bundle.prompt_context
    assert bundle.insufficient_evidence is False


def test_assemble_items_without_title_contribute_no_citation():
    """Items missing a title produce no citation and attach to no group."""
    assembler = ContextAssembler()
    results = [
        _result("c1", "T1", "https://u1", "text1"),
        _result("c2", "", "https://u2", "text2"),
    ]

    bundle = assembler.assemble(results)

    assert bundle.citations == (
        CitationEvidence(title="T1", url="https://u1", evidence_ids=("c1",)),
    )
    # The title-less item is still formatted into the model context.
    assert "[Nguồn 2: ]\ntext2" in bundle.prompt_context
    assert bundle.insufficient_evidence is False
