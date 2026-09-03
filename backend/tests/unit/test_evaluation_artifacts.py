"""Unit tests for deterministic evaluation artifacts (Task 3).

Artifacts must record enough identity to review and reproduce a run, serialize
deterministically, reject secrets before writing, and bound retrieved excerpts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.rag.evaluation.artifacts import (
    load_run_artifact,
    write_run_artifacts,
)
from backend.rag.evaluation.models import ResultState

RUN_RECORD: dict = {
    "run_id": "run-20260902-000001",
    "started_at": "2026-09-02T00:00:00Z",
    "completed_at": "2026-09-02T00:01:00Z",
    "state": "PASS",
    "dataset_id": "travel-agent-rag-benchmark",
    "dataset_version": "0.1",
    "dataset_role": "benchmark",
    "manifest_id": "travel-agent-rag-benchmark",
    "manifest_version": "0.1",
    "relevance_contract": "document_id_binary_v1",
    "eligible_count": 2,
    "invalid_count": 0,
    "skipped_count": 0,
    "code_revision": "abc1234",
    "dirty_working_tree": False,
    "config_id": "rag-current-runtime-v0.1",
    "config_version": "0.1",
    "runtime_adapter": "current_runtime",
    "collection_name": "vietnam_travel_parent_child",
    "embedding_model": "BAAI/bge-m3",
    "retrieval_k_values": [1, 3, 5, 10, 20],
    "primary_k": 5,
    "score_semantics": "higher_is_better_similarity",
    "generation_context_top_k": 4,
    "generation_model": "gpt-4o-mini",
    "prompt_id": "legacy-rag-service-inline-prompt-v1",
    "temperature": 0.7,
    "max_tokens": 800,
    "judge_config": None,
    "judge_valid_count": 0,
    "judge_invalid_count": 0,
    "baseline_run_id": None,
    "mandatory_slices": [
        "single_source_factual",
        "multi_evidence_synthesis",
        "ambiguous_underspecified",
        "source_citation_sensitive",
        "long_tail_difficult",
    ],
    "min_examples_per_slice": 1,
    "aggregate_metrics": {"hit@5": 0.5, "mrr@5": 0.5, "ndcg@5": 0.5},
    "slice_metrics": {},
    "paired_deltas": {},
    "uncertainty": {"uncertainty_status": "not_applicable_n_lt_30"},
    "gate_decisions": {},
    "failed_gates": [],
    "timing": {"total_seconds": 60.0},
    "errors": [],
    "failure_counts": {},
}

EXAMPLE_RECORDS: list[dict] = [
    {
        "example_id": "rag-bench-001",
        "slices": ["single_source_factual"],
        "category": "planning",
        "eligible": True,
        "expected_document_ids": ["doc-001"],
        "expected_source_urls": ["https://vietnam.travel/doc-001"],
        "ranked_evidence_ids": ["doc-001:child:0000:00"],
        "ranked_evidence": [],
        "context_evidence_ids": None,
        "answer": None,
        "reference_answer": "Reference 1",
        "citations": None,
        "metrics": {"hit@5": 1, "mrr@5": 1.0, "ndcg@5": 1.0},
        "judge_valid": None,
        "failure_labels": [],
        "timing_seconds": 0.5,
        "errors": [],
    },
    {
        "example_id": "rag-bench-002",
        "slices": ["single_source_factual"],
        "category": "planning",
        "eligible": True,
        "expected_document_ids": ["doc-002"],
        "expected_source_urls": ["https://vietnam.travel/doc-002"],
        "ranked_evidence_ids": ["doc-009:child:0000:00"],
        "ranked_evidence": [],
        "context_evidence_ids": None,
        "answer": None,
        "reference_answer": "Reference 2",
        "citations": None,
        "metrics": {"hit@5": 0, "mrr@5": 0.0, "ndcg@5": 0.0},
        "judge_valid": None,
        "failure_labels": ["retrieval_miss"],
        "timing_seconds": 0.4,
        "errors": [],
    },
]



def test_write_run_artifacts_creates_deterministic_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "run-1"

    write_run_artifacts(output_dir, RUN_RECORD, EXAMPLE_RECORDS)

    run_path = output_dir / "run.json"
    examples_path = output_dir / "examples.jsonl"
    assert run_path.is_file()
    assert examples_path.is_file()

    run_text = run_path.read_text(encoding="utf-8")
    assert run_text.endswith("\n")
    parsed = json.loads(run_text)
    assert parsed["run_id"] == "run-20260902-000001"
    assert parsed["state"] == "PASS"
    assert parsed["dataset_version"] == "0.1"
    assert parsed["primary_k"] == 5

    example_lines = examples_path.read_text(encoding="utf-8").splitlines()
    assert len(example_lines) == 2
    parsed_examples = [json.loads(line) for line in example_lines]
    assert parsed_examples[0]["example_id"] == "rag-bench-001"
    assert parsed_examples[1]["failure_labels"] == ["retrieval_miss"]


def test_write_run_artifacts_is_deterministic_across_writes(tmp_path: Path) -> None:
    dir_one = tmp_path / "one"
    dir_two = tmp_path / "two"

    write_run_artifacts(dir_one, RUN_RECORD, EXAMPLE_RECORDS)
    write_run_artifacts(dir_two, RUN_RECORD, EXAMPLE_RECORDS)

    assert (dir_one / "run.json").read_bytes() == (dir_two / "run.json").read_bytes()
    assert (
        (dir_one / "examples.jsonl").read_bytes()
        == (dir_two / "examples.jsonl").read_bytes()
    )


def test_run_record_required_identity_fields(tmp_path: Path) -> None:
    output_dir = tmp_path / "run-identity"

    write_run_artifacts(output_dir, RUN_RECORD, EXAMPLE_RECORDS)

    parsed = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    # Dataset identity
    assert parsed["dataset_id"] and parsed["dataset_version"] and parsed["dataset_role"]
    # Code identity
    assert parsed["code_revision"] is not None
    assert isinstance(parsed["dirty_working_tree"], bool)
    # Config identity and retrieval settings
    assert parsed["config_id"] and parsed["config_version"]
    assert parsed["collection_name"] and parsed["embedding_model"]
    assert parsed["retrieval_k_values"] == [1, 3, 5, 10, 20]
    assert parsed["score_semantics"] == "higher_is_better_similarity"
    # Generation settings
    assert parsed["generation_model"] and parsed["prompt_id"]
    # Counts and results
    assert parsed["eligible_count"] == 2
    assert "hit@5" in parsed["aggregate_metrics"]
    assert "uncertainty" in parsed
    assert "timing" in parsed and "errors" in parsed and "failure_counts" in parsed


def test_example_record_required_fields(tmp_path: Path) -> None:
    output_dir = tmp_path / "run-example-fields"

    write_run_artifacts(output_dir, RUN_RECORD, EXAMPLE_RECORDS)

    records = [
        json.loads(line)
        for line in (output_dir / "examples.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    first = records[0]
    assert first["example_id"] == "rag-bench-001"
    assert first["eligible"] is True
    assert first["expected_document_ids"] == ["doc-001"]
    assert first["ranked_evidence_ids"]
    assert "metrics" in first
    assert "judge_valid" in first
    assert "failure_labels" in first
    assert "timing_seconds" in first and "errors" in first


def test_write_run_artifacts_rejects_secret_values(tmp_path: Path) -> None:
    output_dir = tmp_path / "run-secret"
    record = dict(RUN_RECORD)
    record["generation_model"] = "model-with-ghp_abc123secret-token"

    with pytest.raises(ValueError, match="secret|credential"):
        write_run_artifacts(output_dir, record, EXAMPLE_RECORDS)
    assert not (output_dir / "run.json").exists()


def test_write_run_artifacts_rejects_configured_secret_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "run-env-secret"
    monkeypatch.setenv("GITHUB_TOKEN", "super-secret-token-value")
    record = dict(RUN_RECORD)
    record["errors"] = ["provider error: super-secret-token-value"]

    with pytest.raises(ValueError, match="secret|credential"):
        write_run_artifacts(output_dir, record, EXAMPLE_RECORDS)


def test_retrieved_text_excerpts_bounded_to_500_chars(tmp_path: Path) -> None:
    output_dir = tmp_path / "run-excerpts"
    long_text = "x" * 900
    records = [dict(EXAMPLE_RECORDS[0])]
    records[0]["evidence_excerpts"] = [{"chunk_id": "c1", "text": long_text}]
    run_record = dict(RUN_RECORD)
    run_record["eligible_count"] = 1
    run_record["aggregate_metrics"] = {
        "hit@5": 1.0,
        "mrr@5": 1.0,
        "ndcg@5": 1.0,
    }

    write_run_artifacts(output_dir, run_record, records)

    persisted = json.loads(
        (output_dir / "examples.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert len(persisted["evidence_excerpts"][0]["text"]) == 500


def test_load_run_artifact_round_trip(tmp_path: Path) -> None:
    output_dir = tmp_path / "run-roundtrip"

    write_run_artifacts(output_dir, RUN_RECORD, EXAMPLE_RECORDS)
    loaded = load_run_artifact(output_dir)

    assert loaded.run_record["run_id"] == "run-20260902-000001"
    assert loaded.run_record["state"] == ResultState.PASS.value
    assert [record["example_id"] for record in loaded.example_records] == [
        "rag-bench-001",
        "rag-bench-002",
    ]


def test_write_rejects_run_record_missing_comparison_critical_fields(
    tmp_path: Path,
) -> None:
    """Comparison-critical fields (slices/relevance/states/times) are required.

    These fields anchor the D5 mandatory-slice gates and compatibility checks;
    an artifact without them could make a later comparison silently PASS.
    """
    comparison_critical = (
        "started_at",
        "completed_at",
        "invalid_count",
        "skipped_count",
        "dirty_working_tree",
        "runtime_adapter",
        "relevance_contract",
        "mandatory_slices",
        "min_examples_per_slice",
        "generation_context_top_k",
        "temperature",
        "max_tokens",
        "judge_config",
        "judge_valid_count",
        "judge_invalid_count",
        "baseline_run_id",
        "slice_metrics",
        "paired_deltas",
        "uncertainty",
        "gate_decisions",
        "failed_gates",
    )
    for field in comparison_critical:
        record = dict(RUN_RECORD)
        record.pop(field)
        output_dir = tmp_path / f"run-missing-{field}"

        with pytest.raises(ValueError, match=field.replace("@", "@")):
            write_run_artifacts(output_dir, record, EXAMPLE_RECORDS)


def test_write_rejects_eligible_example_without_classification(
    tmp_path: Path,
) -> None:
    """Eligible examples need a slice or category for mandatory-slice reporting."""
    output_dir = tmp_path / "run-no-classification"
    record = dict(EXAMPLE_RECORDS[0])
    record.pop("slices")
    record.pop("category")

    with pytest.raises(ValueError, match="slice|category"):
        write_run_artifacts(output_dir, RUN_RECORD, [record])


def test_write_rejects_non_finite_numeric_values(tmp_path: Path) -> None:
    """NaN/inf evidence must be rejected before persist, never serialized."""
    output_dir = tmp_path / "run-nan"
    record = dict(RUN_RECORD)
    record["aggregate_metrics"] = {"hit@5": float("nan")}

    with pytest.raises(ValueError, match="finite|NaN"):
        write_run_artifacts(output_dir, record, EXAMPLE_RECORDS)
    assert not (output_dir / "run.json").exists()

    output_dir_inf = tmp_path / "run-inf"
    record_inf = dict(RUN_RECORD)
    record_inf["aggregate_metrics"] = {"mrr@5": float("inf")}
    with pytest.raises(ValueError, match="finite|NaN"):
        write_run_artifacts(output_dir_inf, record_inf, EXAMPLE_RECORDS)


def test_write_rejects_run_record_missing_required_identity(tmp_path: Path) -> None:
    """A run record without governed identity fields must be rejected."""
    output_dir = tmp_path / "run-schema"
    incomplete = {"run_id": "run-1", "state": "PASS"}

    with pytest.raises(ValueError, match="dataset_id"):
        write_run_artifacts(output_dir, incomplete, EXAMPLE_RECORDS)


def test_write_rejects_example_record_missing_required_fields(tmp_path: Path) -> None:
    """An example record without governed fields must be rejected."""
    output_dir = tmp_path / "run-example-schema"
    incomplete_examples = [{"example_id": "rag-bench-001"}]

    with pytest.raises(ValueError, match="example_id|eligible|metrics"):
        write_run_artifacts(output_dir, RUN_RECORD, incomplete_examples)


def test_load_run_artifact_rejects_empty_run_record(tmp_path: Path) -> None:
    """A reloaded artifact must satisfy the schema, not just parse as JSON."""
    output_dir = tmp_path / "run-empty"
    output_dir.mkdir()
    (output_dir / "run.json").write_text("{}\n", encoding="utf-8")
    (output_dir / "examples.jsonl").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="run_id|dataset_id|schema"):
        load_run_artifact(output_dir)


def test_load_run_artifact_rejects_non_finite_values(tmp_path: Path) -> None:
    """The loader validates finiteness after parse, not trusting the writer."""
    output_dir = tmp_path / "run-load-nan"
    output_dir.mkdir()
    record = dict(RUN_RECORD)
    record["aggregate_metrics"] = {"hit@5": float("nan")}
    (output_dir / "run.json").write_text(
        json.dumps(record), encoding="utf-8"
    )
    (output_dir / "examples.jsonl").write_text(
        json.dumps(EXAMPLE_RECORDS[0]) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="finite|NaN"):
        load_run_artifact(output_dir)


@pytest.mark.parametrize("value", ("5", 0, -1, True, 1.5))
def test_write_rejects_invalid_min_examples_per_slice(
    tmp_path: Path, value: object
) -> None:
    record = dict(RUN_RECORD)
    record["min_examples_per_slice"] = value

    with pytest.raises(ValueError, match="min_examples_per_slice"):
        write_run_artifacts(tmp_path / "invalid-min", record, EXAMPLE_RECORDS)


@pytest.mark.parametrize(
    ("metric", "value"),
    (("hit@5", 2.0), ("mrr@5", -0.1), ("ndcg@5", 1.1)),
)
def test_write_rejects_out_of_range_example_retrieval_metrics(
    tmp_path: Path, metric: str, value: float
) -> None:
    examples = [dict(EXAMPLE_RECORDS[0])]
    examples[0]["metrics"] = dict(examples[0]["metrics"])
    examples[0]["metrics"][metric] = value

    with pytest.raises(ValueError, match="range|hit@5|mrr@5|ndcg@5"):
        write_run_artifacts(tmp_path / "invalid-metric", RUN_RECORD, examples)


def test_write_rejects_numeric_string_metric(tmp_path: Path) -> None:
    examples = [dict(EXAMPLE_RECORDS[0])]
    examples[0]["metrics"] = dict(examples[0]["metrics"])
    examples[0]["metrics"]["hit@5"] = "1"

    with pytest.raises(ValueError, match="numeric"):
        write_run_artifacts(tmp_path / "string-metric", RUN_RECORD, examples)


def test_write_rejects_numeric_string_answer_metric(tmp_path: Path) -> None:
    record = dict(RUN_RECORD)
    record["answer_metrics"] = {
        "mean_groundedness": "4.5",
        "mean_correctness": 4.5,
    }

    with pytest.raises(ValueError, match="numeric"):
        write_run_artifacts(tmp_path / "string-answer", record, EXAMPLE_RECORDS)


def test_answer_metrics_require_valid_judge_contract(tmp_path: Path) -> None:
    """Answer scores are judge-based evidence; no judge contract, no evidence.

    A run record carrying ``answer_metrics`` without a valid ``judge_config``
    cannot anchor the D5 groundedness/correctness gates, so it must be
    rejected instead of becoming valid promotion evidence.
    """
    output_dir = tmp_path / "answer-without-judge"
    record = dict(RUN_RECORD)
    record["answer_metrics"] = {
        "mean_groundedness": 4.5,
        "mean_correctness": 4.5,
    }
    record["judge_config"] = None

    with pytest.raises(ValueError, match="judge_config|answer_metrics"):
        write_run_artifacts(output_dir, record, EXAMPLE_RECORDS)
    assert not (output_dir / "run.json").exists()


def test_answer_metrics_require_judge_contract_on_load(tmp_path: Path) -> None:
    """The loader re-checks the judge/answer dependency, not trusting the writer."""
    output_dir = tmp_path / "answer-without-judge-load"
    output_dir.mkdir()
    record = dict(RUN_RECORD)
    record["answer_metrics"] = {
        "mean_groundedness": 4.5,
        "mean_correctness": 4.5,
    }
    record["judge_config"] = None
    (output_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")
    (output_dir / "examples.jsonl").write_text(
        json.dumps(EXAMPLE_RECORDS[0]) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="judge_config|answer_metrics"):
        load_run_artifact(output_dir)


@pytest.mark.parametrize(
    ("metric", "value"),
    (
        ("source_url_hit@5", 0.5),
        ("relevant_chunks@5", -1),
        ("relevant_chunks@5", 1.5),
        ("unique_docs@5", 6),
    ),
)
def test_write_rejects_invalid_per_example_diagnostic_metrics(
    tmp_path: Path, metric: str, value: object
) -> None:
    examples = [dict(EXAMPLE_RECORDS[0])]
    examples[0]["metrics"] = dict(examples[0]["metrics"])
    examples[0]["metrics"][metric] = value

    with pytest.raises(ValueError, match=metric.split("@")[0]):
        write_run_artifacts(tmp_path / "invalid-diagnostic", RUN_RECORD, examples)


@pytest.mark.parametrize(
    ("field", "value"),
    (("eligible_count", "five"), ("eligible_count", -1), ("hit@5", "1"), ("hit@5", 2.0)),
)
def test_write_rejects_invalid_slice_metadata(
    tmp_path: Path, field: str, value: object
) -> None:
    record = dict(RUN_RECORD)
    record["slice_metrics"] = {
        "single_source_factual": {"hit@5": 1.0, "eligible_count": 1}
    }
    record["slice_metrics"]["single_source_factual"][field] = value

    with pytest.raises(ValueError, match=field):
        write_run_artifacts(tmp_path / "invalid-slice", record, EXAMPLE_RECORDS)


def test_load_run_artifact_rejects_non_object_example_line(tmp_path: Path) -> None:
    output_dir = tmp_path / "non-object-example"
    output_dir.mkdir()
    (output_dir / "run.json").write_text(json.dumps(RUN_RECORD) + "\n", encoding="utf-8")
    (output_dir / "examples.jsonl").write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="object|line 1"):
        load_run_artifact(output_dir)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("primary_k", "5"),
        ("retrieval_k_values", "5"),
        ("dataset_role", 123),
        ("relevance_contract", 123),
        ("mandatory_slices", ["single_source_factual", 7]),
    ),
)
def test_write_rejects_malformed_frozen_contract(
    tmp_path: Path, field: str, value: object
) -> None:
    record = dict(RUN_RECORD)
    record[field] = value

    with pytest.raises(ValueError, match=field):
        write_run_artifacts(tmp_path / "malformed-contract", record, EXAMPLE_RECORDS)


def test_write_rejects_non_d5_primary_k(tmp_path: Path) -> None:
    record = dict(RUN_RECORD)
    record["primary_k"] = 3

    with pytest.raises(ValueError, match="primary_k"):
        write_run_artifacts(tmp_path / "wrong-primary-k", record, EXAMPLE_RECORDS)


def test_write_rejects_missing_frozen_retrieval_k_values(tmp_path: Path) -> None:
    record = dict(RUN_RECORD)
    record["retrieval_k_values"] = [5]

    with pytest.raises(ValueError, match="retrieval_k_values"):
        write_run_artifacts(tmp_path / "missing-retrieval-k", record, EXAMPLE_RECORDS)


def test_write_rejects_non_d5_score_semantics(tmp_path: Path) -> None:
    record = dict(RUN_RECORD)
    record["score_semantics"] = "lower_is_better_distance"

    with pytest.raises(ValueError, match="score_semantics"):
        write_run_artifacts(tmp_path / "wrong-score-semantics", record, EXAMPLE_RECORDS)


def test_write_rejects_stale_run_eligible_count(tmp_path: Path) -> None:
    record = dict(RUN_RECORD)
    record["eligible_count"] = 999

    with pytest.raises(ValueError, match="eligible_count"):
        write_run_artifacts(tmp_path / "stale-eligible-count", record, EXAMPLE_RECORDS)


def test_load_rejects_tampered_run_eligible_count(tmp_path: Path) -> None:
    output_dir = tmp_path / "tampered-eligible-count"
    write_run_artifacts(output_dir, RUN_RECORD, EXAMPLE_RECORDS)
    run_path = output_dir / "run.json"
    persisted = json.loads(run_path.read_text(encoding="utf-8"))
    persisted["eligible_count"] = 999
    run_path.write_text(json.dumps(persisted) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="eligible_count"):
        load_run_artifact(output_dir)


def test_write_rejects_malformed_judge_config(tmp_path: Path) -> None:
    record = dict(RUN_RECORD)
    record["judge_config"] = "not-a-judge-object"

    with pytest.raises(ValueError, match="judge_config"):
        write_run_artifacts(tmp_path / "malformed-judge", record, EXAMPLE_RECORDS)


def test_write_rejects_non_boolean_eligible(tmp_path: Path) -> None:
    examples = [dict(EXAMPLE_RECORDS[0])]
    examples[0]["eligible"] = "false"

    with pytest.raises(ValueError, match="eligible"):
        write_run_artifacts(tmp_path / "malformed-eligible", RUN_RECORD, examples)


def test_write_rejects_empty_run_id(tmp_path: Path) -> None:
    """A run without a real identity cannot anchor later comparisons."""
    record = dict(RUN_RECORD)
    record["run_id"] = "   "

    with pytest.raises(ValueError, match="run_id"):
        write_run_artifacts(tmp_path / "empty-run-id", record, EXAMPLE_RECORDS)


def test_load_run_artifact_rejects_empty_run_id(tmp_path: Path) -> None:
    output_dir = tmp_path / "empty-run-id-load"
    output_dir.mkdir()
    record = dict(RUN_RECORD)
    record["run_id"] = ""
    (output_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")
    (output_dir / "examples.jsonl").write_text(
        json.dumps(EXAMPLE_RECORDS[0]) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="run_id"):
        load_run_artifact(output_dir)


def test_load_run_artifact_missing_files_raise(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(ValueError, match="run.json"):
        load_run_artifact(empty)


# ---------------------------------------------------------------------------
# Round-7 adversarial review findings (protocol correctness)
# ---------------------------------------------------------------------------


def test_role_aware_mandatory_slices_on_development_role(tmp_path: Path) -> None:
    """Task 2 contract: non-benchmark roles may declare mandatory_slices = [].

    A valid development run must persist; only benchmark runs are held to the
    frozen five-slice contract.
    """
    output_dir = tmp_path / "development-empty-slices"
    record = dict(RUN_RECORD)
    record["dataset_role"] = "development"
    record["mandatory_slices"] = []
    record["min_examples_per_slice"] = 1

    write_run_artifacts(output_dir, record, EXAMPLE_RECORDS)

    loaded = load_run_artifact(output_dir)
    assert loaded.run_record["mandatory_slices"] == []


def test_write_rejects_benchmark_role_without_frozen_slices(tmp_path: Path) -> None:
    """Benchmark runs must govern the five frozen D5 mandatory slices."""
    record = dict(RUN_RECORD)
    record["dataset_role"] = "benchmark"
    record["mandatory_slices"] = ["single_source_factual"]
    record["min_examples_per_slice"] = 1

    with pytest.raises(ValueError, match="mandatory slices"):
        write_run_artifacts(tmp_path / "benchmark-partial-slices", record, EXAMPLE_RECORDS)


def test_load_run_artifact_rejects_benchmark_role_without_frozen_slices(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "benchmark-partial-slices-load"
    output_dir.mkdir()
    record = dict(RUN_RECORD)
    record["dataset_role"] = "benchmark"
    record["mandatory_slices"] = ["single_source_factual"]
    (output_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")
    (output_dir / "examples.jsonl").write_text(
        json.dumps(EXAMPLE_RECORDS[0]) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="mandatory slices"):
        load_run_artifact(output_dir)


def test_run_record_requires_manifest_identity(tmp_path: Path) -> None:
    """Spec: run.json records dataset ID/version/role AND manifest identity."""
    output_dir = tmp_path / "manifest-identity"

    write_run_artifacts(output_dir, RUN_RECORD, EXAMPLE_RECORDS)

    parsed = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert parsed["manifest_id"] == "travel-agent-rag-benchmark"
    assert parsed["manifest_version"] == "0.1"


def test_write_rejects_invalid_expected_document_ids(tmp_path: Path) -> None:
    """Artifact relevance labels must preserve the validated Task 2 contract."""
    for value in ([], "not-a-list", [""]):
        examples = [dict(EXAMPLE_RECORDS[0])]
        examples[0]["expected_document_ids"] = value
        run_record = dict(RUN_RECORD)
        run_record["eligible_count"] = 1

        with pytest.raises(ValueError, match="expected_document_ids"):
            write_run_artifacts(tmp_path / f"bad-doc-labels-{type(value).__name__}", run_record, examples)


def test_write_requires_expected_source_urls_field(tmp_path: Path) -> None:
    """Expected source labels must remain reviewable even when the list is empty."""
    examples = [dict(EXAMPLE_RECORDS[0])]
    examples[0].pop("expected_source_urls")
    run_record = dict(RUN_RECORD)
    run_record["eligible_count"] = 1

    with pytest.raises(ValueError, match="expected_source_urls"):
        write_run_artifacts(tmp_path / "missing-source-labels", run_record, examples)


def test_write_rejects_duplicate_example_slices(tmp_path: Path) -> None:
    """One example cannot count twice toward a mandatory-slice minimum."""
    examples = [dict(EXAMPLE_RECORDS[0])]
    examples[0]["slices"] = ["single_source_factual", "single_source_factual"]
    run_record = dict(RUN_RECORD)
    run_record["eligible_count"] = 1

    with pytest.raises(ValueError, match="slices"):
        write_run_artifacts(tmp_path / "duplicate-slices", run_record, examples)


@pytest.mark.parametrize("field", ("context_evidence_ids", "answer", "citations"))
def test_write_requires_generation_evidence_slots(tmp_path: Path, field: str) -> None:
    """Generation evidence slots stay explicit; None means the layer did not run."""
    examples = [dict(EXAMPLE_RECORDS[0])]
    examples[0].pop(field)
    run_record = dict(RUN_RECORD)
    run_record["eligible_count"] = 1

    with pytest.raises(ValueError, match=field):
        write_run_artifacts(tmp_path / f"missing-{field}", run_record, examples)


# ---------------------------------------------------------------------------
# Round-8 adversarial review findings
# ---------------------------------------------------------------------------


def test_write_rejects_unknown_dataset_role(tmp_path: Path) -> None:
    record = dict(RUN_RECORD)
    record["dataset_role"] = "not-a-real-role"
    record["mandatory_slices"] = []

    with pytest.raises(ValueError, match="dataset_role"):
        write_run_artifacts(tmp_path / "bad-dataset-role", record, EXAMPLE_RECORDS)


def test_pass_run_rejects_judge_invalid_evidence(tmp_path: Path) -> None:
    record = dict(RUN_RECORD)
    record["judge_invalid_count"] = 1

    with pytest.raises(ValueError, match="judge-invalid|judge_invalid"):
        write_run_artifacts(tmp_path / "pass-with-invalid-judge", record, EXAMPLE_RECORDS)


def test_pass_judged_run_rejects_missing_per_example_judge_evidence(
    tmp_path: Path,
) -> None:
    record = dict(RUN_RECORD)
    record["judge_config"] = {
        "model": "gpt-4o-mini",
        "prompt_id": "rag-answer-judge-v0.1",
        "rubric_id": "d5-rag-answer-v0.1",
        "schema_version": 1,
        "temperature": 0.0,
    }
    record["answer_metrics"] = {
        "mean_groundedness": 4.5,
        "mean_correctness": 4.5,
    }

    with pytest.raises(ValueError, match="judge evidence|judge_valid"):
        write_run_artifacts(
            tmp_path / "judged-without-example-evidence", record, EXAMPLE_RECORDS
        )


def test_pass_run_rejects_invalid_retrieval_evidence_marker(tmp_path: Path) -> None:
    record = dict(RUN_RECORD)
    record["aggregate_metrics"] = dict(record["aggregate_metrics"])
    record["aggregate_metrics"]["invalid_evidence_count"] = 1
    examples = [dict(item) for item in EXAMPLE_RECORDS]
    examples[0] = dict(examples[0])
    examples[0]["metrics"] = dict(examples[0]["metrics"])
    examples[0]["metrics"]["invalid_evidence_count"] = 1

    with pytest.raises(ValueError, match="invalid retrieval evidence|invalid_evidence"):
        write_run_artifacts(
            tmp_path / "pass-with-invalid-retrieval-evidence", record, examples
        )


def test_write_rejects_stale_aggregate_metrics(tmp_path: Path) -> None:
    record = dict(RUN_RECORD)
    record["aggregate_metrics"] = {
        "hit@5": 1.0,
        "mrr@5": 1.0,
        "ndcg@5": 1.0,
    }

    with pytest.raises(ValueError, match="Aggregate metric"):
        write_run_artifacts(tmp_path / "stale-aggregate", record, EXAMPLE_RECORDS)
