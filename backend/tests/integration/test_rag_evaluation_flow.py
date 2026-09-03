"""Deterministic end-to-end integration test for governed RAG evaluation flow.

Per the approved RAG repair plan (Task 4 Step 10):
- Uses fake retrieval and generation/judge adapters.
- Runs without external network access or real model downloads.
- Executes one baseline run, one candidate run with persisted artifacts.
- Reloads both run artifacts from disk.
- Compares baseline vs candidate under D5 comparison gates.
- Finishes with ResultState.PASS and 0 failed gates.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from backend.rag.contracts import CitationEvidence, GeneratedAnswer, RetrievalResult
from backend.rag.evaluation.artifacts import load_run_artifact
from backend.rag.evaluation.comparison import compare_runs
from backend.rag.evaluation.models import (
    DatasetManifest,
    DatasetRole,
    EvaluationDataset,
    EvaluationExample,
    JudgeConfig,
    ResultState,
    RunConfig,
)
from backend.rag.evaluation.runner import EvaluationRunner, RunMode


class DeterministicMockRuntime:
    """Mock runtime providing deterministic retrieval and answer generation."""

    def __init__(self, hit_rate: float = 1.0) -> None:
        self.hit_rate = hit_rate

    def retrieve(self, question: str, top_k: int) -> list[RetrievalResult]:
        # Generate predictable evidence where rank 1 matches the question target
        results = []
        for rank in range(1, top_k + 1):
            doc_id = f"doc-{rank:03d}"
            results.append(
                RetrievalResult(
                    chunk_id=f"{doc_id}:c{rank}",
                    document_id=doc_id,
                    title=f"Travel Guide for {doc_id}",
                    url=f"https://vietnam.travel/{doc_id}",
                    score=round(1.0 / rank, 3),
                    text=f"Content for {doc_id} with relevant information for tourists.",
                )
            )
        return results

    def generate(
        self, question: str, top_k: int
    ) -> tuple[GeneratedAnswer, tuple[RetrievalResult, ...]]:
        evidence = tuple(self.retrieve(question, top_k))
        citations = (
            CitationEvidence(
                title=evidence[0].title,
                url=evidence[0].url,
                evidence_ids=(evidence[0].chunk_id,),
            ),
        )
        answer = GeneratedAnswer(
            reply=f"Thành phố có nhiều điểm du lịch hấp dẫn phù hợp với câu hỏi: {question}",
            model="gpt-4o-mini",
            citations=citations,
        )
        return answer, evidence


class DeterministicMockJudge:
    """Mock judge returning deterministic passing scores across all 6 D5 dimensions."""

    def __init__(self, mean_score: int = 5) -> None:
        self.score_val = mean_score

    def score(self, question, answer, evidence, reference_answer=None):
        from backend.rag.evaluation.judge import JudgeResult

        scores = {
            "groundedness": self.score_val,
            "answer_relevance": self.score_val,
            "correctness": self.score_val,
            "completeness": self.score_val,
            "practical_usefulness": self.score_val,
            "clarity": self.score_val,
        }
        total = sum(scores.values())
        return JudgeResult(
            judge_valid=True,
            scores=scores,
            total_score=total,
            mean_score=float(self.score_val),
            reasoning="Câu trả lời xuất sắc, chính xác và đầy đủ căn cứ.",
            failure_label=None,
            error=None,
            raw_response=json.dumps({"scores": scores}),
        )


def _build_test_dataset(dataset_dir: Path) -> EvaluationDataset:
    """Create a temporary governed benchmark dataset with 5 mandatory slices."""
    manifest = DatasetManifest(
        dataset_id="travel-agent-integration-benchmark",
        version="0.1",
        role=DatasetRole.BENCHMARK,
        domain="rag",
        created_at="2026-09-01",
        reviewed_at="2026-09-01",
        reviewer="repository-owner",
        provenance="Synthetic test dataset for integration verification",
        intended_population="Vietnam travel planning queries",
        inclusion_exclusion_rules="All questions have verified target document IDs",
        relevance_contract="document_id_binary_v1",
        mandatory_slices=(
            "single_source_factual",
            "multi_evidence_synthesis",
            "ambiguous_underspecified",
            "source_citation_sensitive",
            "long_tail_difficult",
        ),
        min_examples_per_slice=1,
    )

    examples = []
    for idx, slice_name in enumerate(manifest.mandatory_slices, start=1):
        examples.append(
            EvaluationExample(
                example_id=f"rag-int-{idx:03d}",
                question=f"Gợi ý lịch trình du lịch cho {slice_name}?",
                dataset_role=DatasetRole.BENCHMARK,
                expected_document_ids=("doc-001",),
                expected_source_urls=("https://vietnam.travel/doc-001",),
                reference_answer=f"Lịch trình gợi ý cho {slice_name} với các điểm đến nổi tiếng.",
                category="planning",
                slices=(slice_name,),
            )
        )

    # Persist dataset files
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_data = {
        "dataset_id": manifest.dataset_id,
        "version": manifest.version,
        "role": manifest.role.value,
        "domain": manifest.domain,
        "created_at": manifest.created_at,
        "reviewed_at": manifest.reviewed_at,
        "reviewer": manifest.reviewer,
        "provenance": manifest.provenance,
        "intended_population": manifest.intended_population,
        "inclusion_exclusion_rules": manifest.inclusion_exclusion_rules,
        "relevance_contract": manifest.relevance_contract,
        "mandatory_slices": list(manifest.mandatory_slices),
        "min_examples_per_slice": manifest.min_examples_per_slice,
    }
    (dataset_dir / "manifest.json").write_text(
        json.dumps(manifest_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    example_lines = [
        json.dumps(
            {
                "example_id": ex.example_id,
                "question": ex.question,
                "dataset_role": ex.dataset_role.value,
                "expected_document_ids": list(ex.expected_document_ids),
                "expected_source_urls": list(ex.expected_source_urls),
                "reference_answer": ex.reference_answer,
                "category": ex.category,
                "slices": list(ex.slices),
            },
            ensure_ascii=False,
        )
        for ex in examples
    ]
    (dataset_dir / "examples.jsonl").write_text(
        "\n".join(example_lines) + "\n", encoding="utf-8"
    )

    return EvaluationDataset(manifest=manifest, examples=tuple(examples))


def test_rag_evaluation_flow_baseline_candidate_compare(tmp_path: Path) -> None:
    """Execute full baseline and candidate runs, persist, reload, and verify PASS comparison."""
    dataset_dir = tmp_path / "dataset"
    dataset = _build_test_dataset(dataset_dir)

    judge_conf = JudgeConfig(
        model="gpt-4o-mini",
        prompt_id="rag-answer-judge-v0.1",
        rubric_id="d5-rag-answer-v0.1",
        schema_version=1,
        temperature=0.0,
    )

    baseline_config = RunConfig(
        config_id="rag-baseline-test-v0.1",
        version="0.1",
        runtime_adapter="current_runtime",
        collection_name="vietnam_travel_knowledge",
        embedding_model="BAAI/bge-m3",
        retrieval_k_values=(1, 3, 5, 10, 20),
        primary_k=5,
        score_semantics="higher_is_better_similarity",
        generation_context_top_k=4,
        generation_model="gpt-4o-mini",
        prompt_id="rag-current-prompt-v0.1",
        temperature=0.7,
        max_tokens=800,
        judge=judge_conf,
    )

    candidate_config = RunConfig(
        config_id="rag-candidate-test-v0.1",
        version="0.1",
        runtime_adapter="current_runtime",
        collection_name="vietnam_travel_parent_child",
        embedding_model="BAAI/bge-m3",
        retrieval_k_values=(1, 3, 5, 10, 20),
        primary_k=5,
        score_semantics="higher_is_better_similarity",
        generation_context_top_k=4,
        generation_model="gpt-4o-mini",
        prompt_id="rag-current-prompt-v0.1",
        temperature=0.7,
        max_tokens=800,
        judge=judge_conf,
    )

    runtime = DeterministicMockRuntime(hit_rate=1.0)
    judge = DeterministicMockJudge(mean_score=5)

    # 1. Run Baseline
    baseline_dir = tmp_path / "runs" / "baseline"
    baseline_runner = EvaluationRunner(
        dataset=dataset,
        config=baseline_config,
        runtime=runtime,
        judge_adapter=judge,
    )
    baseline_artifact = baseline_runner.run(
        mode=RunMode.FULL, output_dir=baseline_dir
    )

    assert baseline_artifact.run_record["state"] == ResultState.PASS.value
    assert baseline_artifact.run_record["aggregate_metrics"]["hit@5"] == 1.0

    # 2. Run Candidate
    candidate_dir = tmp_path / "runs" / "candidate"
    candidate_runner = EvaluationRunner(
        dataset=dataset,
        config=candidate_config,
        runtime=runtime,
        judge_adapter=judge,
    )
    candidate_artifact = candidate_runner.run(
        mode=RunMode.FULL,
        output_dir=candidate_dir,
        baseline_run_id=baseline_artifact.run_record["run_id"],
    )


    assert candidate_artifact.run_record["state"] == ResultState.PASS.value
    assert candidate_artifact.run_record["aggregate_metrics"]["hit@5"] == 1.0

    # 3. Reload both run artifacts from disk
    reloaded_baseline = load_run_artifact(baseline_dir)
    reloaded_candidate = load_run_artifact(candidate_dir)

    assert reloaded_baseline.run_record["run_id"] == baseline_artifact.run_record["run_id"]
    assert reloaded_candidate.run_record["run_id"] == candidate_artifact.run_record["run_id"]

    # 4. Compare runs under D5 protocol
    comparison_result = compare_runs(
        reloaded_baseline.run_record,
        reloaded_baseline.example_records,
        reloaded_candidate.run_record,
        reloaded_candidate.example_records,
    )

    # 5. Verify comparison finishes PASS without regressions
    assert comparison_result.state == ResultState.PASS
    assert len(comparison_result.failed_gates) == 0
    assert comparison_result.paired_deltas["hit@5"] == 0.0
