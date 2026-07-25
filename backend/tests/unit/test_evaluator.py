"""Unit tests for RAGEvaluator benchmark module."""

from __future__ import annotations

import pytest
from backend.rag.evaluation.evaluator import RAGEvaluator


def test_evaluator_hit_rate_and_mrr_calculation():
    evaluator = RAGEvaluator()

    query_item = {
        "query": "Lịch trình đi Hạ Long thế nào?",
        "expected_keywords": ["hạ long", "du thuyền"],
    }

    mock_results = [
        {"text": "Tour du thuyền Hạ Long 2 ngày 1 đêm thăm hang Sửng Sốt", "metadata": {"title": "Hạ Long"}},
        {"text": "Kinh nghiệm đi du lịch Sa Pa", "metadata": {"title": "Sa Pa"}},
    ]

    hit, rr = evaluator.calculate_hit_rate_and_mrr(query_item, mock_results, top_k=5)

    assert hit == 1.0
    assert rr == 1.0


def test_evaluator_no_hit_calculation():
    evaluator = RAGEvaluator()

    query_item = {
        "query": "Kinh nghiệm du lịch Phú Quốc",
        "expected_keywords": ["phú quốc", "bãi sao"],
    }

    mock_results = [
        {"text": "Hướng dẫn leo núi Phan Xi Păng Sa Pa", "metadata": {"title": "Sa Pa"}},
    ]

    hit, rr = evaluator.calculate_hit_rate_and_mrr(query_item, mock_results, top_k=5)

    assert hit == 0.0
    assert rr == 0.0
