"""Unit tests for RAGEvaluator benchmark module."""

from __future__ import annotations

# pyrefly: ignore [missing-import]
import pytest
from backend.rag.evaluation.evaluator import (
    RAGEvaluator,
    reciprocal_rank,
    ndcg_at_k,
    source_url_hit,
)


def test_reciprocal_rank():
    assert reciprocal_rank([1, 3], 5) == 1.0
    assert reciprocal_rank([2, 5], 5) == 0.5
    assert reciprocal_rank([6], 5) == 0.0


def test_ndcg_at_k():
    relevance = [1, 0, 0, 1, 0]
    assert ndcg_at_k(relevance, 5) > 0.0
    assert ndcg_at_k([0, 0, 0], 5) == 0.0


def test_evaluator_compute_query_metrics_hit():
    evaluator = RAGEvaluator()

    query_item = {
        "query_id": "q1",
        "question": "Lịch trình đi Hạ Long thế nào?",
        "expected_document_id": "doc_halong_001",
        "expected_source_url": "https://vietnam.travel/halong",
    }

    mock_results = [
        {"text": "Tour du thuyền Hạ Long", "metadata": {"document_id": "doc_halong_001", "title": "Hạ Long", "source_url": "https://vietnam.travel/halong"}},
        {"text": "Kinh nghiệm đi du lịch Sa Pa", "metadata": {"document_id": "doc_sapa_002", "title": "Sa Pa"}},
    ]

    metrics = evaluator.compute_query_metrics(query_item, mock_results, chunk_strategy="baseline", k_values=[1, 5])

    assert metrics["hit@1"] == 1
    assert metrics["hit@5"] == 1
    assert metrics["mrr@1"] == 1.0
    assert metrics["source_url_hit@1"] == 1
    assert metrics["precision@5"] == 0.2


def test_evaluator_compute_query_metrics_no_hit():
    evaluator = RAGEvaluator()

    query_item = {
        "query_id": "q2",
        "question": "Kinh nghiệm du lịch Phú Quốc",
        "expected_document_id": "doc_phuquoc_999",
    }

    mock_results = [
        {"text": "Hướng dẫn leo núi Sa Pa", "metadata": {"document_id": "doc_sapa_002", "title": "Sa Pa"}},
    ]

    metrics = evaluator.compute_query_metrics(query_item, mock_results, chunk_strategy="baseline", k_values=[1, 5])

    assert metrics["hit@1"] == 0
    assert metrics["hit@5"] == 0
    assert metrics["mrr@5"] == 0.0
