"""Unit tests for config-driven evaluation runner and role independence.

Per the approved RAG repair plan (Task 4 Step 5 & 8):
- RunConfig records behavior identity, not an experiment role.
- Runner assigns no inherent baseline or candidate roles (ADR 0001).
- Collection names do not imply role.
- Retrieval-only mode never constructs or calls a model provider.
- Lifecycle computes metrics, slice metrics, answer metrics, and D5 result states.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from backend.rag.contracts import CitationEvidence, GeneratedAnswer, RetrievalResult
from backend.rag.evaluation.artifacts import load_run_artifact
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


@pytest.fixture
def sample_manifest() -> DatasetManifest:
    return DatasetManifest(
        dataset_id="travel-agent-rag-benchmark",
        version="0.1",
        role=DatasetRole.BENCHMARK,
        domain="rag",
        created_at="2026-09-01",
        reviewed_at="2026-09-01",
        reviewer="repository-owner",
        provenance="Test provenance",
        intended_population="Vietnam travel",
        inclusion_exclusion_rules="Test rules",
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


@pytest.fixture
def sample_dataset(sample_manifest) -> EvaluationDataset:
    slices = sample_manifest.mandatory_slices
    examples = tuple(
        EvaluationExample(
            example_id=f"rag-bench-{idx:03d}",
            question=f"Question {idx} for {s}?",
            dataset_role=DatasetRole.BENCHMARK,
            expected_document_ids=(f"doc-{idx:03d}",),
            expected_source_urls=(f"https://vietnam.travel/doc-{idx:03d}",),
            reference_answer=f"Reference answer {idx}",
            category="planning",
            slices=(s,),
        )
        for idx, s in enumerate(slices, start=1)
    )
    return EvaluationDataset(manifest=sample_manifest, examples=examples)


@pytest.fixture
def sample_run_config() -> RunConfig:
    return RunConfig(
        config_id="rag-baseline-v0.1",
        version="0.1",
        runtime_adapter="current_runtime",
        collection_name="vietnam_travel_knowledge",
        embedding_model="BAAI/bge-m3",
        retrieval_k_values=(1, 3, 5, 10, 20),
        primary_k=5,
        score_semantics="higher_is_better_similarity",
        generation_context_top_k=4,
        generation_model="gpt-4o-mini",
        prompt_id="legacy-rag-service-inline-prompt-v1",
        temperature=0.7,
        max_tokens=800,
        judge=JudgeConfig(
            model="gpt-4o-mini",
            prompt_id="rag-answer-judge-v0.1",
            rubric_id="d5-rag-answer-v0.1",
            schema_version=1,
            temperature=0.0,
        ),
    )


class FakeRuntime:
    """Mock runtime returning deterministic retrieval and generation evidence."""

    def __init__(self, hit_docs: dict[str, str] | None = None, invalid_evidence: bool = False) -> None:
        self.hit_docs = hit_docs or {}
        self.invalid_evidence = invalid_evidence
        self.generate_called = False

    def retrieve(self, question: str, top_k: int) -> list[RetrievalResult]:
        # Return 5 items
        results = []
        for rank in range(1, top_k + 1):
            doc_id = self.hit_docs.get(question, f"doc-other-{rank}") if rank == 1 else f"doc-filler-{rank}"
            chunk_id = "" if self.invalid_evidence and rank == 1 else f"{doc_id}:c{rank}"
            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    title=f"Title for {doc_id}",
                    url=f"https://vietnam.travel/{doc_id}",
                    score=round(1.0 / rank, 3),
                    text=f"Sample text content for {doc_id} rank {rank}.",
                )
            )
        return results

    def generate(self, question: str, top_k: int) -> tuple[GeneratedAnswer, tuple[RetrievalResult, ...]]:
        self.generate_called = True
        evidence = tuple(self.retrieve(question, top_k))
        citations = (
            CitationEvidence(
                title=evidence[0].title,
                url=evidence[0].url,
                evidence_ids=(evidence[0].chunk_id,),
            ),
        )
        answer = GeneratedAnswer(
            reply=f"Generated answer for {question}",
            model="gpt-4o-mini",
            citations=citations,
        )
        return answer, evidence


class FakeJudge:
    def __init__(self, scores: dict[str, int] | None = None, valid: bool = True) -> None:
        self.scores = scores or {
            "groundedness": 5,
            "answer_relevance": 5,
            "correctness": 5,
            "completeness": 5,
            "practical_usefulness": 5,
            "clarity": 5,
        }
        self.valid = valid

    def score(self, question, answer, evidence, reference_answer=None):
        from backend.rag.evaluation.judge import JudgeResult
        if not self.valid:
            return JudgeResult(
                judge_valid=False,
                scores=None,
                total_score=None,
                mean_score=None,
                reasoning=None,
                failure_label="judge_invalid",
                error="Fake invalid judge",
                raw_response=None,
            )
        total = sum(self.scores.values())
        return JudgeResult(
            judge_valid=True,
            scores=dict(self.scores),
            total_score=total,
            mean_score=total / len(self.scores),
            reasoning="Fake valid reasoning",
            failure_label=None,
            error=None,
            raw_response="{}",
        )


def test_runner_role_independence(sample_dataset, sample_run_config, tmp_path):
    """The runner and config must not assume or embed experiment roles."""
    # Config has no 'role' field
    assert not hasattr(sample_run_config, "role")
    assert "role" not in sample_run_config.__dict__

    # Two configs with different collection names are both role-neutral
    config_a = sample_run_config
    config_b = RunConfig(
        config_id="rag-candidate-v0.1",
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
    )

    hits = {ex.question: ex.expected_document_ids[0] for ex in sample_dataset.examples}
    runtime = FakeRuntime(hit_docs=hits)
    runner = EvaluationRunner(dataset=sample_dataset, config=config_a, runtime=runtime)

    artifact_a = runner.run(mode=RunMode.RETRIEVAL, output_dir=tmp_path / "run_a")
    assert artifact_a.run_record["state"] == ResultState.PASS.value
    # Role is absent in run record (it is assigned at comparison time)
    assert "role" not in artifact_a.run_record

    runner_b = EvaluationRunner(dataset=sample_dataset, config=config_b, runtime=runtime)
    artifact_b = runner_b.run(mode=RunMode.RETRIEVAL, output_dir=tmp_path / "run_b")
    assert artifact_b.run_record["state"] == ResultState.PASS.value
    assert "role" not in artifact_b.run_record


def test_retrieval_only_mode_never_calls_generation_or_judge(sample_dataset, sample_run_config):
    """In retrieval-only mode, runtime.generate and judge are never constructed or called."""
    hits = {ex.question: ex.expected_document_ids[0] for ex in sample_dataset.examples}
    runtime = FakeRuntime(hit_docs=hits)
    judge = FakeJudge()

    runner = EvaluationRunner(
        dataset=sample_dataset,
        config=sample_run_config,
        runtime=runtime,
        judge_adapter=judge,
    )

    artifact = runner.run(mode=RunMode.RETRIEVAL)

    assert runtime.generate_called is False
    assert artifact.run_record["state"] == ResultState.PASS.value
    assert artifact.run_record["answer_metrics"] is None
    assert artifact.run_record["judge_config"] is None

    # Check per-example records in retrieval mode
    for ex_rec in artifact.example_records:
        assert ex_rec["answer"] is None
        assert ex_rec["context_evidence_ids"] is None
        assert ex_rec["citations"] is None
        assert ex_rec["judge_valid"] is None
        assert ex_rec["metrics"]["hit@5"] == 1


def test_full_mode_evaluates_answers_and_judge(sample_dataset, sample_run_config):
    """In full mode, generation and judge are executed and answer metrics aggregated."""
    hits = {ex.question: ex.expected_document_ids[0] for ex in sample_dataset.examples}
    runtime = FakeRuntime(hit_docs=hits)
    judge = FakeJudge(scores={"groundedness": 5, "answer_relevance": 5, "correctness": 4, "completeness": 4, "practical_usefulness": 5, "clarity": 5})

    runner = EvaluationRunner(
        dataset=sample_dataset,
        config=sample_run_config,
        runtime=runtime,
        judge_adapter=judge,
    )

    artifact = runner.run(mode=RunMode.FULL)

    assert runtime.generate_called is True
    assert artifact.run_record["state"] == ResultState.PASS.value
    assert artifact.run_record["answer_metrics"] is not None
    assert artifact.run_record["answer_metrics"]["mean_groundedness"] == 5.0
    assert artifact.run_record["answer_metrics"]["mean_correctness"] == 4.0
    assert artifact.run_record["judge_valid_count"] == len(sample_dataset.examples)
    assert artifact.run_record["judge_invalid_count"] == 0

    for ex_rec in artifact.example_records:
        assert ex_rec["answer"] is not None
        assert ex_rec["context_evidence_ids"] is not None
        assert ex_rec["judge_valid"] is True


def test_full_mode_gate_failure_mean_correctness(sample_dataset, sample_run_config):
    """Mean correctness < 4.0 results in FAIL with mean_correctness_minimum."""
    hits = {ex.question: ex.expected_document_ids[0] for ex in sample_dataset.examples}
    runtime = FakeRuntime(hit_docs=hits)
    # correctness 3 < 4.0 -> FAIL
    judge = FakeJudge(scores={"groundedness": 5, "answer_relevance": 5, "correctness": 3, "completeness": 5, "practical_usefulness": 5, "clarity": 5})

    runner = EvaluationRunner(
        dataset=sample_dataset,
        config=sample_run_config,
        runtime=runtime,
        judge_adapter=judge,
    )

    artifact = runner.run(mode=RunMode.FULL)

    assert artifact.run_record["state"] == ResultState.FAIL.value
    assert "mean_correctness_minimum" in artifact.run_record["failed_gates"]


def test_invalid_evidence_bars_pass(sample_dataset, sample_run_config):
    """Invalid retrieved evidence on any example produces INVALID, never PASS."""
    runtime = FakeRuntime(invalid_evidence=True)
    runner = EvaluationRunner(
        dataset=sample_dataset,
        config=sample_run_config,
        runtime=runtime,
    )

    artifact = runner.run(mode=RunMode.RETRIEVAL)

    assert artifact.run_record["state"] == ResultState.INVALID.value


def test_below_minimum_slice_is_inconclusive(sample_manifest, sample_run_config):
    """When a mandatory slice has fewer examples than min_examples_per_slice, state is INCONCLUSIVE."""
    # Create dataset with min_examples_per_slice=5, but only 1 example per slice
    manifest_strict = DatasetManifest(
        dataset_id=sample_manifest.dataset_id,
        version=sample_manifest.version,
        role=sample_manifest.role,
        domain=sample_manifest.domain,
        created_at=sample_manifest.created_at,
        reviewed_at=sample_manifest.reviewed_at,
        reviewer=sample_manifest.reviewer,
        provenance=sample_manifest.provenance,
        intended_population=sample_manifest.intended_population,
        inclusion_exclusion_rules=sample_manifest.inclusion_exclusion_rules,
        relevance_contract=sample_manifest.relevance_contract,
        mandatory_slices=sample_manifest.mandatory_slices,
        min_examples_per_slice=5,  # Requires at least 5!
    )
    # Only 1 example per slice
    examples = tuple(
        EvaluationExample(
            example_id=f"rag-bench-{idx:03d}",
            question=f"Question {idx} for {s}?",
            dataset_role=DatasetRole.BENCHMARK,
            expected_document_ids=(f"doc-{idx:03d}",),
            expected_source_urls=(f"https://vietnam.travel/doc-{idx:03d}",),
            reference_answer="Ref",
            category="planning",
            slices=(s,),
        )
        for idx, s in enumerate(sample_manifest.mandatory_slices, start=1)
    )
    dataset = EvaluationDataset(manifest=manifest_strict, examples=examples)
    hits = {ex.question: ex.expected_document_ids[0] for ex in examples}
    runtime = FakeRuntime(hit_docs=hits)

    runner = EvaluationRunner(dataset=dataset, config=sample_run_config, runtime=runtime)
    artifact = runner.run(mode=RunMode.RETRIEVAL)

    assert artifact.run_record["state"] == ResultState.INCONCLUSIVE.value


def test_runner_persistence_and_reload(sample_dataset, sample_run_config, tmp_path):
    """Artifacts written by runner can be cleanly reloaded with load_run_artifact."""
    hits = {ex.question: ex.expected_document_ids[0] for ex in sample_dataset.examples}
    runtime = FakeRuntime(hit_docs=hits)
    runner = EvaluationRunner(dataset=sample_dataset, config=sample_run_config, runtime=runtime)

    out_dir = tmp_path / "persisted_run"
    artifact = runner.run(mode=RunMode.RETRIEVAL, output_dir=out_dir)

    target_run_dir = out_dir / artifact.run_record["run_id"]
    reloaded = load_run_artifact(target_run_dir)
    assert reloaded.run_record["run_id"] == artifact.run_record["run_id"]
    assert reloaded.run_record["state"] == ResultState.PASS.value
    assert len(reloaded.example_records) == len(sample_dataset.examples)


def test_runner_retrieval_exception_fails_with_infrastructure_failure_and_invalid(
    sample_dataset, sample_run_config
):
    """Retrieval/index exceptions must record infrastructure_failure and result in INVALID state."""
    class FailingRuntime:
        def retrieve(self, question: str, top_k: int):
            raise RuntimeError("index disappeared")

        def generate(self, question: str, top_k: int):
            raise RuntimeError("index disappeared")

    runner = EvaluationRunner(
        dataset=sample_dataset, config=sample_run_config, runtime=FailingRuntime()
    )
    artifact = runner.run(mode=RunMode.RETRIEVAL)

    assert artifact.run_record["state"] == ResultState.INVALID.value
    assert artifact.run_record["invalid_count"] > 0
    assert "infrastructure_failure" in artifact.run_record["failed_gates"]
    assert artifact.run_record["failure_counts"].get("infrastructure_failure", 0) > 0
    assert any("retrieval_error" in err for err in artifact.run_record["errors"])
    for ex in artifact.example_records:
        assert "infrastructure_failure" in ex["failure_labels"]


def test_runner_output_dir_creates_run_id_subdirectory(
    sample_dataset, sample_run_config, tmp_path
):
    """Passing a parent runs directory creates a unique <run-id>/ subdirectory without overwrite."""
    hits = {ex.question: ex.expected_document_ids[0] for ex in sample_dataset.examples}
    runtime = FakeRuntime(hit_docs=hits)
    runner = EvaluationRunner(dataset=sample_dataset, config=sample_run_config, runtime=runtime)

    runs_dir = tmp_path / "runs"
    artifact1 = runner.run(mode=RunMode.RETRIEVAL, output_dir=runs_dir)
    run1_dir = runs_dir / artifact1.run_record["run_id"]
    assert run1_dir.is_dir()
    assert (run1_dir / "run.json").exists()
    assert (run1_dir / "examples.jsonl").exists()

    # Second run creates its own subdirectory and does not overwrite run1
    from dataclasses import replace
    runner.config = replace(runner.config, config_id="rag-baseline-v0.2")
    artifact2 = runner.run(mode=RunMode.RETRIEVAL, output_dir=runs_dir)
    run2_dir = runs_dir / artifact2.run_record["run_id"]
    assert artifact1.run_record["run_id"] != artifact2.run_record["run_id"]
    assert run1_dir != run2_dir
    assert run2_dir.is_dir()
    assert (run2_dir / "run.json").exists()
    assert (run1_dir / "run.json").exists()


def test_runner_refuses_to_overwrite_existing_run_directory(
    sample_dataset, sample_run_config, tmp_path
):
    """When target_dir already contains run.json, runner must raise FileExistsError."""
    hits = {ex.question: ex.expected_document_ids[0] for ex in sample_dataset.examples}
    runtime = FakeRuntime(hit_docs=hits)
    runner = EvaluationRunner(dataset=sample_dataset, config=sample_run_config, runtime=runtime)

    target_dir = tmp_path / "explicit-run-dir"
    target_dir.mkdir(parents=True)
    (target_dir / "run.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists. Overwrite is barred."):
        runner.run(mode=RunMode.RETRIEVAL, output_dir=target_dir)


def test_runner_citation_matching_uses_context_evidence(
    sample_dataset, sample_run_config
):
    """Citation mapping directly to generation context_evidence must NOT emit citation_mismatch."""
    from backend.rag.contracts import CitationEvidence, GeneratedAnswer, RetrievalResult

    ranked_item = RetrievalResult(
        chunk_id="chunk-retrieval",
        document_id="doc-retrieval",
        title="Retrieval Title",
        url="https://vietnam.travel/retrieval",
        score=0.9,
        text="text",
    )
    context_item = RetrievalResult(
        chunk_id="chunk-context",
        document_id="doc-context",
        title="Context Title",
        url="https://vietnam.travel/context",
        score=0.85,
        text="text",
    )

    class ContextOnlyRuntime:
        def retrieve(self, question: str, top_k: int):
            return [ranked_item]

        def generate(self, question: str, top_k: int):
            citations = (
                CitationEvidence(
                    title="Context Title",
                    url="https://vietnam.travel/context",
                    evidence_ids=("chunk-context",),
                ),
            )
            ans = GeneratedAnswer(reply="Answer", model="gpt-4o-mini", citations=citations)
            return ans, (context_item,)

    runner = EvaluationRunner(
        dataset=sample_dataset,
        config=sample_run_config,
        runtime=ContextOnlyRuntime(),
        judge_adapter=None,
    )
    artifact = runner.run(mode=RunMode.FULL)
    rec = artifact.example_records[0]
    assert "citation_mismatch" not in rec["failure_labels"]


def test_runner_records_structured_evidence_and_failure_taxonomy(
    sample_dataset, sample_run_config
):
    """Runner must record structured evidence and emit citation_mismatch and unsupported_claim."""
    from backend.rag.contracts import CitationEvidence, GeneratedAnswer, RetrievalResult
    from backend.rag.evaluation.judge import JudgeResult

    retrieved_item = RetrievalResult(
        chunk_id="chunk-001",
        document_id="doc-001",
        title="Guide 1",
        url="https://vietnam.travel/doc-001",
        score=0.95,
        text="Detail text for guide 1",
    )

    class CustomRuntime:
        def retrieve(self, question: str, top_k: int):
            return [retrieved_item]

        def generate(self, question: str, top_k: int):
            # Return citation that does NOT match retrieved evidence -> citation_mismatch
            citations = (
                CitationEvidence(
                    title="Hallucinated Title",
                    url="https://unrelated.com/fake",
                    evidence_ids=("fake-chunk",),
                ),
            )
            ans = GeneratedAnswer(reply="Answer text", model="gpt-4o-mini", citations=citations)
            return ans, (retrieved_item,)

    class LowGroundednessJudge:
        def score(self, question, answer, evidence, reference_answer=None):
            return JudgeResult(
                judge_valid=True,
                scores={
                    "groundedness": 2,  # < 3 triggers unsupported_claim
                    "answer_relevance": 4,
                    "correctness": 3,
                    "completeness": 3,
                    "practical_usefulness": 3,
                    "clarity": 4,
                },
                total_score=19,
                mean_score=3.17,
                reasoning="Evidence does not support answer claims.",
                failure_label="unsupported_claim",
                error=None,
                raw_response="{}",
            )

    runner = EvaluationRunner(
        dataset=sample_dataset,
        config=sample_run_config,
        runtime=CustomRuntime(),
        judge_adapter=LowGroundednessJudge(),
    )
    artifact = runner.run(mode=RunMode.FULL)

    rec = artifact.example_records[0]
    # Check failure labels
    assert "citation_mismatch" in rec["failure_labels"]
    assert "unsupported_claim" in rec["failure_labels"]

    # Check structured evidence persistence and reference_answer
    assert "ranked_evidence" in rec
    assert len(rec["ranked_evidence"]) == 1
    ev = rec["ranked_evidence"][0]
    assert ev["chunk_id"] == "chunk-001"
    assert ev["document_id"] == "doc-001"
    assert ev["title"] == "Guide 1"
    assert ev["url"] == "https://vietnam.travel/doc-001"
    assert ev["score"] == 0.95
    assert "text_excerpt" in ev
    assert "reference_answer" in rec
    assert rec["reference_answer"] is not None


def test_current_runtime_adapter_rejects_unsupported_prompt_id(sample_run_config):
    """CurrentRuntimeAdapter must reject arbitrary prompt IDs that it cannot execute."""
    from dataclasses import replace
    from backend.rag.evaluation.runtime import CurrentRuntimeAdapter

    bad_config = replace(sample_run_config, prompt_id="ARBITRARY_PROMPT_ID_THAT_IS_NOT_EXECUTED")
    with pytest.raises(ValueError, match="executes frozen prompt"):
        CurrentRuntimeAdapter(config=bad_config, embedder=object(), vector_store=object())


def test_current_runtime_adapter_rejects_mismatched_generation_model(sample_run_config):
    """CurrentRuntimeAdapter must reject generation_model that differs from settings.LLM_MODEL."""
    from dataclasses import replace
    from backend.rag.evaluation.runtime import CurrentRuntimeAdapter

    bad_config = replace(sample_run_config, generation_model="different-unexecuted-model")
    with pytest.raises(ValueError, match="executes settings.LLM_MODEL"):
        CurrentRuntimeAdapter(config=bad_config, embedder=object(), vector_store=object())
