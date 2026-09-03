"""Unit tests for D5 retrieval metrics (Task 3).

Relevance is governed by ``EvaluationExample`` labels and document identity
from ``RetrievalResult.document_id``. Missing or invalid evidence must never
silently become a valid score.
"""

from __future__ import annotations

import pytest

from backend.rag.contracts import RetrievalResult
from backend.rag.evaluation.metrics import (
    aggregate_retrieval_metrics,
    compute_retrieval_metrics,
)


def make_example(
    document_ids: tuple[str, ...] = ("doc-1",),
    source_urls: tuple[str, ...] = ("https://vietnam.travel/doc-1",),
):
    from backend.rag.evaluation.models import DatasetRole, EvaluationExample

    return EvaluationExample(
        example_id="ex-1",
        question="Câu hỏi test?",
        dataset_role=DatasetRole.BENCHMARK,
        expected_document_ids=document_ids,
        expected_source_urls=source_urls,
        reference_answer=None,
        category="planning",
        slices=("single_source_factual",),
    )


def make_result(
    chunk_id: str,
    document_id: str,
    url: str = "https://vietnam.travel/other",
    score: float | None = 0.9,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=document_id,
        title="Title",
        url=url,
        score=score,
        text="Evidence text",
    )


K_VALUES = (1, 3, 5, 10, 20)


# ---------------------------------------------------------------------------
# Core D5 metrics
# ---------------------------------------------------------------------------


def test_hit_at_k_relevant_at_rank_one() -> None:
    example = make_example()
    results = [make_result("c1", "doc-1"), make_result("c2", "doc-2")]

    metrics = compute_retrieval_metrics(example, results, k_values=K_VALUES)

    assert metrics["hit@5"] == 1


def test_hit_at_k_no_relevant_result() -> None:
    example = make_example()
    results = [make_result("c1", "doc-2"), make_result("c2", "doc-3")]

    metrics = compute_retrieval_metrics(example, results, k_values=K_VALUES)

    assert metrics["hit@5"] == 0


def test_mrr_at_k_first_relevant_at_rank_two() -> None:
    example = make_example()
    results = [make_result("c1", "doc-9"), make_result("c2", "doc-1")]

    metrics = compute_retrieval_metrics(example, results, k_values=K_VALUES)

    assert metrics["mrr@5"] == 0.5


def test_mrr_at_k_relevant_beyond_k_is_zero() -> None:
    example = make_example()
    # doc-1 sits at rank 4 (index 3): inside K=5 but outside K=3.
    results = [
        make_result("c1", "doc-9"),
        make_result("c2", "doc-8"),
        make_result("c3", "doc-7"),
        make_result("c4", "doc-1"),
    ]

    metrics = compute_retrieval_metrics(example, results, k_values=K_VALUES)

    assert metrics["mrr@3"] == 0.0
    assert metrics["mrr@5"] == 0.25


def test_ndcg_at_k_multiple_relevant_documents() -> None:
    example = make_example(document_ids=("doc-1", "doc-2"))
    results = [
        make_result("c1", "doc-9"),
        make_result("c2", "doc-1"),
        make_result("c3", "doc-2"),
    ]

    metrics = compute_retrieval_metrics(example, results, k_values=K_VALUES)

    # DCG = 1/log2(3) + 1/log2(4); IDCG = 1/log2(2) + 1/log2(3)
    dcg = 1.0 / __import__("math").log2(3) + 1.0 / __import__("math").log2(4)
    idcg = 1.0 / __import__("math").log2(2) + 1.0 / __import__("math").log2(3)
    assert metrics["ndcg@5"] == pytest.approx(dcg / idcg)
    assert 0.0 <= metrics["ndcg@5"] <= 1.0


def test_ndcg_document_level_gain_capped_by_known_relevant() -> None:
    """nDCG is document-level: one expected document gains at most once.

    Multiple retrieved chunks of the same expected document must not push
    DCG above the ideal; nDCG stays within [0, 1].
    """
    example = make_example(document_ids=("doc-1",))
    results = [make_result(f"c{i}", "doc-1") for i in (1, 2, 3)]

    metrics = compute_retrieval_metrics(example, results, k_values=K_VALUES)

    assert metrics["ndcg@5"] == pytest.approx(1.0)
    assert 0.0 <= metrics["ndcg@5"] <= 1.0
    # Chunk-level diagnostics still count each retrieved chunk separately.
    assert metrics["relevant_chunks@5"] == 3


def test_ndcg_at_k_no_relevant_result_is_zero() -> None:
    example = make_example()
    results = [make_result("c1", "doc-9")]

    metrics = compute_retrieval_metrics(example, results, k_values=K_VALUES)

    assert metrics["ndcg@5"] == 0.0


def test_precision_and_counts_at_k() -> None:
    example = make_example(document_ids=("doc-1", "doc-2"))
    results = [
        make_result("c1", "doc-1"),
        make_result("c2", "doc-9"),
        make_result("c3", "doc-2"),
        make_result("c4", "doc-1"),  # duplicate doc-1 chunk, distinct chunk ID
    ]

    metrics = compute_retrieval_metrics(example, results, k_values=K_VALUES)

    assert metrics["precision@5"] == pytest.approx(3 / 5)
    assert metrics["relevant_chunks@5"] == 3  # doc-1, doc-2, doc-1 again
    assert metrics["unique_docs@5"] == 3  # doc-1, doc-9, doc-2 (doc-1 repeats)


def test_source_url_hit_present_and_absent() -> None:
    example = make_example()
    hit_results = [make_result("c1", "doc-9", url="https://vietnam.travel/doc-1")]
    miss_results = [make_result("c1", "doc-1", url="https://vietnam.travel/other")]

    hit = compute_retrieval_metrics(example, hit_results, k_values=K_VALUES)
    miss = compute_retrieval_metrics(example, miss_results, k_values=K_VALUES)

    assert hit["source_url_hit@5"] == 1
    assert miss["source_url_hit@5"] == 0


def test_source_url_hit_absent_expected_url_is_none_not_zero() -> None:
    """Absent expected URL must produce None for the diagnostic, never 0."""
    example = make_example(source_urls=())

    metrics = compute_retrieval_metrics(example, [make_result("c1", "doc-1")], k_values=K_VALUES)

    assert metrics["source_url_hit@5"] is None


def test_metric_keys_do_not_embed_strategy_names() -> None:
    example = make_example()

    metrics = compute_retrieval_metrics(example, [make_result("c1", "doc-1")], k_values=K_VALUES)

    for key in metrics:
        assert "baseline" not in key
        assert "candidate" not in key
        assert "parent_child" not in key


# ---------------------------------------------------------------------------
# Invalid evidence must not become valid scores
# ---------------------------------------------------------------------------


def test_result_missing_document_identity_is_invalid_not_zero() -> None:
    """A retrieved item without document identity invalidates identity metrics."""
    example = make_example()
    broken = RetrievalResult(
        chunk_id="c1", document_id="", title="", url="", score=0.9, text="t"
    )

    metrics = compute_retrieval_metrics(example, [broken, make_result("c2", "doc-1")], k_values=K_VALUES)

    assert metrics["invalid_evidence_count"] == 1


def test_missing_relevance_label_is_invalid() -> None:
    """An example with no expected documents has no governed relevance contract."""
    example = make_example(document_ids=())

    metrics = compute_retrieval_metrics(example, [make_result("c1", "doc-1")], k_values=K_VALUES)

    # Governed metrics must not be produced from missing relevance labels;
    # the retrieved evidence itself is structurally valid here.
    assert metrics["invalid_evidence_count"] == 0
    assert metrics["hit@5"] is None


def test_duplicate_chunk_identity_is_invalid() -> None:
    """Duplicate chunk IDs mean unstable evidence identity: invalid, not a score."""
    example = make_example()
    results = [make_result("c1", "doc-1"), make_result("c1", "doc-2")]

    metrics = compute_retrieval_metrics(example, results, k_values=K_VALUES)

    assert metrics["invalid_evidence_count"] == 1


def test_invalid_evidence_keeps_rank_position() -> None:
    """Invalid evidence occupies its retrieved rank; it never compresses ranks.

    D5: invalid evidence must never become a favorable metric. A relevant item
    retrieved at rank 2 behind an invalid rank-1 item must score MRR 0.5.
    """
    example = make_example()
    invalid_first = RetrievalResult(
        chunk_id="", document_id="", title="", url="", score=0.9, text="t"
    )
    relevant_second = make_result("c2", "doc-1")

    metrics = compute_retrieval_metrics(
        example, [invalid_first, relevant_second], k_values=K_VALUES
    )

    assert metrics["invalid_evidence_count"] == 1
    assert metrics["mrr@5"] == pytest.approx(0.5)
    assert metrics["hit@5"] == 1


def test_duplicate_chunk_identity_keeps_rank_position() -> None:
    """A duplicate chunk ID is invalid but still occupies its retrieved rank."""
    example = make_example()
    # doc-1 sits at rank 3 behind the valid doc-9 and the duplicate c1.
    results = [
        make_result("c1", "doc-9"),
        make_result("c1", "doc-9"),  # duplicate chunk ID -> invalid placeholder
        make_result("c2", "doc-1"),
    ]

    metrics = compute_retrieval_metrics(example, results, k_values=K_VALUES)

    assert metrics["invalid_evidence_count"] == 1
    assert metrics["mrr@5"] == pytest.approx(1 / 3)


def test_unique_docs_counts_all_distinct_retrieved_documents() -> None:
    """D5: unique document count = distinct retrieved document IDs in top K."""
    example = make_example(document_ids=("doc-1", "doc-2"))
    results = [
        make_result("c1", "doc-1"),
        make_result("c2", "doc-9"),  # retrieved but not expected
        make_result("c3", "doc-2"),
    ]

    metrics = compute_retrieval_metrics(example, results, k_values=K_VALUES)

    assert metrics["unique_docs@5"] == 3


def test_ndcg_ideal_uses_known_relevant_count_from_contract() -> None:
    """D5: IDCG uses R = known relevant items from the dataset contract.

    Retrieving one of two known relevant documents perfectly must NOT score
    nDCG 1.0 — the missing relevant document is penalized.
    """
    example = make_example(document_ids=("doc-1", "doc-2"))
    results = [make_result("c1", "doc-1")]  # perfect rank, but R = 2

    metrics = compute_retrieval_metrics(example, results, k_values=K_VALUES)

    # DCG = 1/log2(2) = 1.0; IDCG = 1/log2(2) + 1/log2(3) ≈ 1.6309
    expected = 1.0 / (1.0 / __import__("math").log2(2) + 1.0 / __import__("math").log2(3))
    assert metrics["ndcg@5"] == pytest.approx(expected, rel=1e-6)
    assert metrics["ndcg@5"] < 1.0


def test_unique_docs_invalid_when_retrieved_document_identity_missing() -> None:
    """D5: missing document identity makes unique-docs invalid for the example."""
    example = make_example()
    broken = RetrievalResult(
        chunk_id="c1", document_id="", title="", url="", score=0.9, text="t"
    )

    metrics = compute_retrieval_metrics(example, [broken], k_values=K_VALUES)

    assert metrics["invalid_evidence_count"] == 1
    assert metrics["unique_docs@5"] is None


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------


def test_aggregate_retrieval_metrics_means_per_example() -> None:
    example_a = make_example()
    example_b = make_example(document_ids=("doc-2",))
    metrics_a = compute_retrieval_metrics(
        example_a, [make_result("c1", "doc-1")], k_values=(5,)
    )
    metrics_b = compute_retrieval_metrics(
        example_b, [make_result("c1", "doc-9")], k_values=(5,)
    )

    aggregate = aggregate_retrieval_metrics([metrics_a, metrics_b], k_values=(5,))

    assert aggregate["hit@5"] == pytest.approx(0.5)
    assert aggregate["mrr@5"] == pytest.approx(0.5)
    assert aggregate["example_count"] == 2


def test_aggregate_skips_none_diagnostic_values() -> None:
    """None diagnostics stay None in aggregates instead of averaging as zero."""
    example_no_url = make_example(source_urls=())
    metrics_a = compute_retrieval_metrics(
        example_no_url, [make_result("c1", "doc-1")], k_values=(5,)
    )
    # Both examples lack expected URLs, so no aggregate URL evidence exists.
    example_b = make_example(source_urls=())
    metrics_b = compute_retrieval_metrics(
        example_b, [make_result("c1", "doc-9")], k_values=(5,)
    )

    aggregate = aggregate_retrieval_metrics([metrics_a, metrics_b], k_values=(5,))

    assert aggregate["source_url_hit@5"] is None
    assert aggregate["hit@5"] == pytest.approx(0.5)
