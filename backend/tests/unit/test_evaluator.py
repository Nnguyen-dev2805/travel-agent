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
    assert metrics["mrr@5"] == 0.0


def test_evaluator_legacy_has_no_hardcoded_baseline_collections():
    import inspect
    from backend.rag.evaluation import evaluator
    source = inspect.getsource(evaluator)
    assert "vietnam_travel_knowledge" not in source
    assert "vietnam_travel_parent_child" not in source

    inst = RAGEvaluator()
    assert not hasattr(inst, "baseline_store")
    assert not hasattr(inst, "parent_child_store")


def test_evaluator_evaluate_benchmark_requires_stores():
    inst = RAGEvaluator()
    with pytest.raises(ValueError, match="evaluate_benchmark is deprecated and requires explicit stores"):
        inst.evaluate_benchmark()


def test_evaluator_main_delegates_to_cli():
    from backend.rag.evaluation import evaluator
    with pytest.raises(SystemExit) as exc:
        evaluator.main(["--help"])
    assert exc.value.code == 0


def test_generate_report_supports_unknown_strategy(tmp_path, monkeypatch):
    """generate_report must produce a Markdown file for any arbitrary strategy name."""
    import backend.rag.evaluation.evaluator as ev_mod

    monkeypatch.setattr(ev_mod, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(ev_mod, "REPORT_MARKDOWN_PATH", tmp_path / "report.md")

    evaluator = RAGEvaluator()
    monkeypatch.setattr(evaluator, "eval_path", tmp_path / "fake_dataset.jsonl")

    summary = [
        {
            "chunk_strategy": "hybrid_reranker",
            **{f"hit@{k}": 0.9 for k in ev_mod.K_VALUES},
            **{f"mrr@{k}": 0.85 for k in ev_mod.K_VALUES},
            **{f"ndcg@{k}": 0.88 for k in ev_mod.K_VALUES},
            **{f"precision@{k}": 0.45 for k in ev_mod.K_VALUES},
            "query_count": 10,
        }
    ]

    # Must not raise and must produce a file
    evaluator.generate_report(summary, total_queries=10)

    report_text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "hybrid_reranker" in report_text
    # Must NOT contain any hard-coded legacy strategy names
    assert "baseline_fixed_1000ch" not in report_text
    assert "semantic_parent_child" not in report_text
    assert "Hit Rate (hybrid_reranker)" in report_text
    assert "MRR (hybrid_reranker)" in report_text


def test_generate_report_multi_strategy_columns(tmp_path, monkeypatch):
    """generate_report must produce one column per strategy, for any number of strategies."""
    import backend.rag.evaluation.evaluator as ev_mod

    monkeypatch.setattr(ev_mod, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(ev_mod, "REPORT_MARKDOWN_PATH", tmp_path / "report.md")

    evaluator = RAGEvaluator()
    monkeypatch.setattr(evaluator, "eval_path", tmp_path / "fake_dataset.jsonl")

    strategy_names = ["dense_sparse", "parent_child_v2", "baseline_bm25"]
    summary = [
        {
            "chunk_strategy": s,
            **{f"hit@{k}": 0.7 + i * 0.05 for k in ev_mod.K_VALUES},
            **{f"mrr@{k}": 0.6 + i * 0.05 for k in ev_mod.K_VALUES},
            **{f"ndcg@{k}": 0.65 + i * 0.05 for k in ev_mod.K_VALUES},
            **{f"precision@{k}": 0.3 + i * 0.05 for k in ev_mod.K_VALUES},
            "query_count": 10,
        }
        for i, s in enumerate(strategy_names)
    ]

    evaluator.generate_report(summary, total_queries=10)

    report_text = (tmp_path / "report.md").read_text(encoding="utf-8")
    for name in strategy_names:
        assert f"Hit Rate ({name})" in report_text
        assert f"MRR ({name})" in report_text
        assert f"NDCG ({name})" in report_text
        assert f"Precision ({name})" in report_text

