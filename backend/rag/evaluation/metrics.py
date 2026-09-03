"""D5 retrieval metrics for the R2 evaluation harness.

Relevance is governed by ``EvaluationExample`` labels; retrieved identity comes
from runtime ``RetrievalResult`` values. Missing or invalid evidence is recorded
as invalid and never silently becomes a valid score (D5 protocol).
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

from backend.rag.contracts import RetrievalResult
from backend.rag.evaluation.models import EvaluationExample


def _normalize_url(url: str | None) -> str:
    """Normalize a URL for exact comparison, matching the legacy evaluator."""
    if not url:
        return ""
    return url.strip().rstrip("/")


def _validate_evidence(
    results: Sequence[RetrievalResult],
) -> tuple[list[RetrievalResult | None], int]:
    """Validate retrieved evidence while preserving each item's rank position.

    Governed identity requires non-empty ``chunk_id`` and ``document_id`` and
    unique chunk IDs. Invalid items are replaced with ``None`` placeholders so
    later items keep their original retrieved ranks (invalid evidence must
    never become a favorable metric by compressing ranks).
    """
    ranked: list[RetrievalResult | None] = []
    invalid = 0
    seen_chunk_ids: set[str] = set()
    for item in results:
        if not item.chunk_id or not item.document_id:
            ranked.append(None)
            invalid += 1
            continue
        if item.chunk_id in seen_chunk_ids:
            ranked.append(None)
            invalid += 1
            continue
        seen_chunk_ids.add(item.chunk_id)
        ranked.append(item)
    return ranked, invalid


def compute_retrieval_metrics(
    example: EvaluationExample,
    results: Sequence[RetrievalResult],
    k_values: Sequence[int],
) -> dict[str, Any]:
    """Compute governed D5 retrieval metrics for one example.

    Relevance is document-level: a retrieved item is relevant when its
    ``document_id`` appears in the example's ``expected_document_ids``.

    Missing governed relevance labels or invalid retrieved identity are
    recorded under ``invalid_evidence_count``; governed metrics become
    ``None`` when the example itself lacks a relevance contract instead of
    being scored as zero.
    """
    metrics: dict[str, Any] = {
        "example_id": example.example_id,
        "invalid_evidence_count": 0,
    }

    ranked, invalid_count = _validate_evidence(results)
    metrics["invalid_evidence_count"] = invalid_count

    # The example's governed relevance labels are the primary contract. An
    # example without expected documents has no governed relevance contract,
    # so identity-based metrics are invalid rather than zero.
    example_has_relevance_contract = bool(example.expected_document_ids)
    if not example_has_relevance_contract:
        for k in k_values:
            metrics[f"hit@{k}"] = None
            metrics[f"mrr@{k}"] = None
            metrics[f"ndcg@{k}"] = None
            metrics[f"precision@{k}"] = None
            metrics[f"relevant_chunks@{k}"] = None
            metrics[f"unique_docs@{k}"] = None
            metrics[f"source_url_hit@{k}"] = None
        return metrics

    expected_doc_ids = set(example.expected_document_ids)
    expected_urls = {_normalize_url(url) for url in example.expected_source_urls if url}
    has_expected_url = bool(expected_urls)

    relevance: list[int] = [
        1 if item is not None and item.document_id in expected_doc_ids else 0
        for item in ranked
    ]
    relevant_ranks = [rank for rank, rel in enumerate(relevance, start=1) if rel]

    def _dcg(rel: Sequence[int], k: int) -> float:
        return sum(
            1.0 / math.log2(index + 1)
            for index, val in enumerate(rel[:k], start=1)
            if val
        )

    # nDCG is document-level under this relevance contract: each expected
    # document contributes gain at most once, so retrieving many chunks of
    # one expected document cannot push nDCG above 1.0.
    seen_docs: set[str] = set()
    document_relevance: list[int] = []
    for item in ranked:
        if item is None:
            document_relevance.append(0)
            continue
        if item.document_id in expected_doc_ids and item.document_id not in seen_docs:
            seen_docs.add(item.document_id)
            document_relevance.append(1)
        else:
            document_relevance.append(0)

    # D5: R = the number of known relevant items under the dataset contract,
    # not the number of relevant items the system happened to retrieve.
    known_relevant_count = len(expected_doc_ids)

    for k in k_values:
        top_k = relevance[:k]

        metrics[f"hit@{k}"] = 1 if any(top_k) else 0

        first_rank = next((rank for rank in relevant_ranks if rank <= k), None)
        metrics[f"mrr@{k}"] = (1.0 / first_rank) if first_rank else 0.0

        ideal = [1] * min(known_relevant_count, k)
        ideal_dcg = _dcg(ideal, k)
        metrics[f"ndcg@{k}"] = (
            _dcg(document_relevance, k) / ideal_dcg if ideal_dcg > 0 else 0.0
        )

        metrics[f"precision@{k}"] = sum(top_k) / k if k > 0 else 0.0
        metrics[f"relevant_chunks@{k}"] = sum(top_k)

        # Diagnostic diversity: distinct retrieved document IDs in top K,
        # per the D5 protocol definition. Missing document identity makes
        # this metric invalid for the example (None), never a valid count.
        if invalid_count > 0 and not ranked[:k]:
            unique_docs_value: Any = None
        else:
            top_k_items = ranked[:k]
            if any(item is None for item in top_k_items):
                unique_docs_value = None
            else:
                unique_docs = {
                    item.document_id for item in top_k_items if item.document_id
                }
                unique_docs_value = len(unique_docs)
        metrics[f"unique_docs@{k}"] = unique_docs_value

        if not has_expected_url:
            metrics[f"source_url_hit@{k}"] = None
        else:
            hit = 0
            for item in ranked[:k]:
                if item is not None and _normalize_url(item.url) in expected_urls:
                    hit = 1
                    break
            metrics[f"source_url_hit@{k}"] = hit

    return metrics


def aggregate_retrieval_metrics(
    per_example: Iterable[Mapping[str, Any]],
    k_values: Sequence[int],
) -> dict[str, Any]:
    """Aggregate per-example metric dictionaries into run-level means.

    ``None`` diagnostic values (for example, source URL hit when no expected
    URL exists) stay ``None``; they never average as zero. Governed identity
    metrics require at least one valid per-example value.
    """
    records = list(per_example)
    aggregate: dict[str, Any] = {"example_count": len(records)}

    if not records:
        return aggregate

    for k in k_values:
        for base in ("hit", "mrr", "ndcg", "precision"):
            values = [
                record[f"{base}@{k}"]
                for record in records
                if record.get(f"{base}@{k}") is not None
            ]
            aggregate[f"{base}@{k}"] = (
                sum(values) / len(values) if values else None
            )

        chunk_counts = [
            record[f"relevant_chunks@{k}"]
            for record in records
            if record.get(f"relevant_chunks@{k}") is not None
        ]
        aggregate[f"relevant_chunks@{k}"] = (
            sum(chunk_counts) / len(chunk_counts) if chunk_counts else None
        )

        unique_counts = [
            record[f"unique_docs@{k}"]
            for record in records
            if record.get(f"unique_docs@{k}") is not None
        ]
        aggregate[f"unique_docs@{k}"] = (
            sum(unique_counts) / len(unique_counts) if unique_counts else None
        )

        url_hits = [
            record[f"source_url_hit@{k}"]
            for record in records
            if record.get(f"source_url_hit@{k}") is not None
        ]
        aggregate[f"source_url_hit@{k}"] = (
            sum(url_hits) / len(url_hits) if url_hits else None
        )

    aggregate["invalid_evidence_count"] = sum(
        record.get("invalid_evidence_count", 0) for record in records
    )
    return aggregate
