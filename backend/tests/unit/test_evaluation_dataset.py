"""Unit tests for Task 2 dataset, run-config, and result-state validation.

These tests define the strict validation contract for R2 v0.1 evaluation
datasets and run configurations. Invalid inputs must raise explicit
validation errors; missing relevance labels must never be silently converted
into valid empty examples.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from backend.rag.evaluation.dataset import load_dataset, load_run_config
from backend.rag.evaluation.models import (
    DatasetManifest,
    DatasetRole,
    EvaluationDataset,
    EvaluationExample,
    JudgeConfig,
    ResultState,
    RunConfig,
)

VALID_MANIFEST: Dict[str, Any] = {
    "dataset_id": "rag-bench",
    "version": "0.1",
    "role": "benchmark",
    "domain": "rag",
    "created_at": "2026-09-01",
    "reviewed_at": "2026-09-02",
    "reviewer": "repository-owner",
    "provenance": "synthetic public travel content",
    "intended_population": "Vietnam travel questions",
    "inclusion_exclusion_rules": "One document per example; reviewed labels only.",
    "relevance_contract": "Document-level relevance by exact document_id match.",
    "mandatory_slices": [
        "single_source_factual",
        "multi_evidence_synthesis",
        "ambiguous_underspecified",
        "source_citation_sensitive",
        "long_tail_difficult",
    ],
    "min_examples_per_slice": 1,
}

VALID_EXAMPLE: Dict[str, Any] = {
    "example_id": "rag-bench-001",
    "question": "Khi nào nên đến Hạ Long?",
    "dataset_role": "benchmark",
    "category": "planning",
    "slices": ["single_source_factual"],
    "expected_document_ids": ["doc-halong"],
    "expected_source_urls": ["https://vietnam.travel/ha-long"],
    "reference_answer": "Thông tin tham chiếu được review từ source document.",
}


def benchmark_examples() -> list[Dict[str, Any]]:
    """Build five benchmark examples, one per frozen mandatory D5 slice.

    Mirrors the plan Task 4 rule that every benchmark row carries exactly one
    primary mandatory slice for unambiguous slice counts.
    """
    slice_by_id = {
        "rag-bench-001": "single_source_factual",
        "rag-bench-002": "multi_evidence_synthesis",
        "rag-bench-003": "ambiguous_underspecified",
        "rag-bench-004": "source_citation_sensitive",
        "rag-bench-005": "long_tail_difficult",
    }
    examples = []
    for index, (example_id, slice_id) in enumerate(slice_by_id.items(), start=1):
        example = dict(VALID_EXAMPLE)
        example["example_id"] = example_id
        example["question"] = f"Câu hỏi benchmark {index} cho slice {slice_id}?"
        example["expected_document_ids"] = [f"doc-{index:03d}"]
        example["expected_source_urls"] = [f"https://vietnam.travel/doc-{index:03d}"]
        example["slices"] = [slice_id]
        examples.append(example)
    return examples

VALID_JUDGE: Dict[str, Any] = {
    "model": "gpt-4o-mini",
    "prompt_id": "d5-judge-v0.1",
    "rubric_id": "d5-six-dimension-v0.1",
    "schema_version": 1,
    "temperature": 0.0,
}

VALID_RUN_CONFIG: Dict[str, Any] = {
    "config_id": "rag-current-runtime",
    "version": "0.1",
    "runtime_adapter": "current_runtime",
    "collection_name": "vietnam_travel_parent_child",
    "embedding_model": "BAAI/bge-m3",
    "retrieval_k_values": [1, 3, 5, 10, 20],
    "primary_k": 5,
    "score_semantics": "higher_is_better_similarity",
    "generation_context_top_k": 4,
    "generation_model": "gpt-4o-mini",
    "prompt_id": "current-runtime-prompt-v0.1",
    "temperature": 0.7,
    "max_tokens": 800,
    "judge": None,
}


def write_dataset(tmp_path: Path, manifest: Dict[str, Any], examples: list[Dict[str, Any]]) -> Path:
    """Materialize a manifest.json plus examples.jsonl dataset directory."""
    directory = tmp_path / "dataset"
    directory.mkdir()
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (directory / "examples.jsonl").open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(example, ensure_ascii=False) + "\n")
    return directory


def write_run_config(tmp_path: Path, config: Dict[str, Any]) -> Path:
    """Materialize a JSON run-config file."""
    path = tmp_path / "run-config.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Enums and result states
# ---------------------------------------------------------------------------


def test_dataset_role_enum_values() -> None:
    assert {role.value for role in DatasetRole} == {
        "development",
        "regression",
        "benchmark",
        "safety",
    }


def test_result_state_enum_values() -> None:
    assert {state.value for state in ResultState} == {
        "PASS",
        "FAIL",
        "INCONCLUSIVE",
        "INVALID",
    }


# ---------------------------------------------------------------------------
# Valid dataset loading
# ---------------------------------------------------------------------------


def test_load_dataset_valid_manifest_and_example(tmp_path: Path) -> None:
    directory = write_dataset(tmp_path, VALID_MANIFEST, benchmark_examples())

    dataset = load_dataset(directory)

    assert isinstance(dataset, EvaluationDataset)
    assert isinstance(dataset.manifest, DatasetManifest)
    assert dataset.manifest.dataset_id == "rag-bench"
    assert dataset.manifest.version == "0.1"
    assert dataset.manifest.role is DatasetRole.BENCHMARK
    assert dataset.manifest.domain == "rag"
    assert dataset.manifest.mandatory_slices == (
        "single_source_factual",
        "multi_evidence_synthesis",
        "ambiguous_underspecified",
        "source_citation_sensitive",
        "long_tail_difficult",
    )
    assert dataset.manifest.min_examples_per_slice == 1
    assert len(dataset.examples) == 5

    example = dataset.examples[0]
    assert isinstance(example, EvaluationExample)
    assert example.example_id == "rag-bench-001"
    assert example.dataset_role is DatasetRole.BENCHMARK
    assert example.expected_document_ids == ("doc-001",)
    assert example.expected_source_urls == ("https://vietnam.travel/doc-001",)
    assert example.slices == ("single_source_factual",)

    single_source = dataset.examples[0]
    assert single_source.question == "Câu hỏi benchmark 1 cho slice single_source_factual?"
    assert single_source.reference_answer == (
        "Thông tin tham chiếu được review từ source document."
    )


def test_load_dataset_rejects_non_utf8_bytes(tmp_path: Path) -> None:
    """UTF-8 decoding failures must raise an explicit validation error."""
    directory = tmp_path / "dataset"
    directory.mkdir()
    (directory / "manifest.json").write_bytes(
        b'{"dataset_id": "rag-bench", "invalid\xff": true}'
    )

    with pytest.raises(ValueError):
        load_dataset(directory)


def test_load_run_config_valid_with_judge(tmp_path: Path) -> None:
    config = dict(VALID_RUN_CONFIG)
    config["judge"] = dict(VALID_JUDGE)
    path = write_run_config(tmp_path, config)

    run_config = load_run_config(path)

    assert isinstance(run_config, RunConfig)
    assert run_config.config_id == "rag-current-runtime"
    assert run_config.version == "0.1"
    assert run_config.runtime_adapter == "current_runtime"
    assert run_config.collection_name == "vietnam_travel_parent_child"
    assert run_config.embedding_model == "BAAI/bge-m3"
    assert run_config.retrieval_k_values == (1, 3, 5, 10, 20)
    assert run_config.primary_k == 5
    assert run_config.score_semantics == "higher_is_better_similarity"
    assert run_config.generation_context_top_k == 4
    assert run_config.generation_model == "gpt-4o-mini"
    assert run_config.prompt_id == "current-runtime-prompt-v0.1"
    assert run_config.temperature == 0.7
    assert run_config.max_tokens == 800
    assert isinstance(run_config.judge, JudgeConfig)
    assert run_config.judge.model == "gpt-4o-mini"
    assert run_config.judge.prompt_id == "d5-judge-v0.1"
    assert run_config.judge.rubric_id == "d5-six-dimension-v0.1"
    assert run_config.judge.schema_version == 1
    assert run_config.judge.temperature == 0.0


def test_load_run_config_valid_without_judge(tmp_path: Path) -> None:
    path = write_run_config(tmp_path, dict(VALID_RUN_CONFIG))

    run_config = load_run_config(path)

    assert run_config.judge is None


# ---------------------------------------------------------------------------
# Dataset validation failures
# ---------------------------------------------------------------------------


def test_load_dataset_rejects_duplicate_example_ids(tmp_path: Path) -> None:
    duplicate = dict(VALID_EXAMPLE)
    duplicate["question"] = "Câu hỏi khác cũng dùng chung ID."
    directory = write_dataset(tmp_path, VALID_MANIFEST, [VALID_EXAMPLE, duplicate])

    with pytest.raises(ValueError, match="[Dd]uplicate example_id"):
        load_dataset(directory)


def test_load_dataset_rejects_role_mismatch(tmp_path: Path) -> None:
    mismatched = dict(VALID_EXAMPLE)
    mismatched["dataset_role"] = "development"
    directory = write_dataset(tmp_path, VALID_MANIFEST, [mismatched])

    with pytest.raises(ValueError, match="dataset_role"):
        load_dataset(directory)


def test_load_dataset_rejects_unknown_slice(tmp_path: Path) -> None:
    unknown = dict(VALID_EXAMPLE)
    unknown["slices"] = ["made_up_slice"]
    directory = write_dataset(tmp_path, VALID_MANIFEST, [unknown])

    with pytest.raises(ValueError, match="unknown slice"):
        load_dataset(directory)


def test_load_dataset_rejects_missing_expected_document_ids(tmp_path: Path) -> None:
    missing = dict(VALID_EXAMPLE)
    missing["expected_document_ids"] = []
    directory = write_dataset(tmp_path, VALID_MANIFEST, [missing])

    with pytest.raises(ValueError, match="expected_document_ids"):
        load_dataset(directory)


def test_load_dataset_rejects_missing_relevance_labels(tmp_path: Path) -> None:
    """A missing relevance label must be rejected, not converted to an empty valid example."""
    unlabeled = {key: value for key, value in VALID_EXAMPLE.items()}
    unlabeled.pop("expected_document_ids")
    unlabeled.pop("expected_source_urls")
    directory = write_dataset(tmp_path, VALID_MANIFEST, [unlabeled])

    with pytest.raises(ValueError, match="relevance label"):
        load_dataset(directory)


def test_load_dataset_rejects_invalid_domain(tmp_path: Path) -> None:
    manifest = dict(VALID_MANIFEST)
    manifest["domain"] = "memory"
    directory = write_dataset(tmp_path, manifest, [VALID_EXAMPLE])

    with pytest.raises(ValueError, match="domain"):
        load_dataset(directory)


def test_load_dataset_rejects_invalid_role_enum(tmp_path: Path) -> None:
    manifest = dict(VALID_MANIFEST)
    manifest["role"] = "experiment"
    directory = write_dataset(tmp_path, manifest, [VALID_EXAMPLE])

    with pytest.raises(ValueError):
        load_dataset(directory)


def test_load_dataset_rejects_mandatory_slice_violation(tmp_path: Path) -> None:
    """A mandatory slice with no examples must fail validation."""
    manifest = dict(VALID_MANIFEST)
    manifest["mandatory_slices"] = ["single_source_factual", "multi_evidence_synthesis"]
    example = dict(VALID_EXAMPLE)
    example["slices"] = ["single_source_factual"]
    directory = write_dataset(tmp_path, manifest, [example])

    with pytest.raises(ValueError, match="[Mm]andatory slice"):
        load_dataset(directory)


def test_load_dataset_rejects_minimum_count_violation(tmp_path: Path) -> None:
    """A mandatory slice below min_examples_per_slice must fail validation."""
    manifest = dict(VALID_MANIFEST)
    manifest["role"] = "development"
    manifest["mandatory_slices"] = ["single_source_factual"]
    manifest["min_examples_per_slice"] = 2
    example = dict(VALID_EXAMPLE)
    example["dataset_role"] = "development"
    example["slices"] = ["single_source_factual"]
    directory = write_dataset(tmp_path, manifest, [example])

    # The only example covers the mandatory slice, so the count (1) is below
    # the declared minimum (2).
    with pytest.raises(ValueError, match="min_examples_per_slice"):
        load_dataset(directory)


def test_load_dataset_rejects_manifest_missing_mandatory_slices(tmp_path: Path) -> None:
    """A manifest without mandatory_slices must fail, not default to no governance."""
    manifest = {key: value for key, value in VALID_MANIFEST.items() if key != "mandatory_slices"}
    directory = write_dataset(tmp_path, manifest, benchmark_examples())

    with pytest.raises(ValueError, match="mandatory_slices"):
        load_dataset(directory)


def test_load_dataset_rejects_manifest_missing_min_examples_per_slice(tmp_path: Path) -> None:
    """A manifest without min_examples_per_slice must fail, not default to 1."""
    manifest = {key: value for key, value in VALID_MANIFEST.items() if key != "min_examples_per_slice"}
    directory = write_dataset(tmp_path, manifest, benchmark_examples())

    with pytest.raises(ValueError, match="min_examples_per_slice"):
        load_dataset(directory)


def test_load_dataset_rejects_example_without_category_or_slices(tmp_path: Path) -> None:
    """Every example needs at least one of category or slices (spec: category OR slice)."""
    unclassified = dict(VALID_EXAMPLE)
    unclassified.pop("category")
    unclassified.pop("slices")
    directory = write_dataset(tmp_path, VALID_MANIFEST, [unclassified])

    with pytest.raises(ValueError, match="category|slice"):
        load_dataset(directory)


def test_load_dataset_accepts_empty_expected_source_urls(tmp_path: Path) -> None:
    """Source URLs are 'when available' per plan Task 4; empty list stays valid."""
    no_url = dict(VALID_EXAMPLE)
    no_url["expected_source_urls"] = []
    directory = write_dataset(tmp_path, VALID_MANIFEST, [no_url] + benchmark_examples()[1:])

    dataset = load_dataset(directory)
    assert dataset.examples[0].expected_source_urls == ()


def test_load_dataset_rejects_benchmark_with_empty_mandatory_slices(tmp_path: Path) -> None:
    """Benchmark v0.1 must govern all five frozen D5 slices; an empty list is invalid."""
    manifest = dict(VALID_MANIFEST)
    manifest["role"] = "benchmark"
    manifest["mandatory_slices"] = []
    directory = write_dataset(tmp_path, manifest, [VALID_EXAMPLE])

    with pytest.raises(ValueError, match="benchmark.*mandatory_slices|mandatory_slices"):
        load_dataset(directory)


def test_load_dataset_rejects_benchmark_missing_frozen_slice(tmp_path: Path) -> None:
    """A benchmark manifest missing any of the five frozen D5 slices is invalid."""
    manifest = dict(VALID_MANIFEST)
    manifest["role"] = "benchmark"
    manifest["mandatory_slices"] = [
        "single_source_factual",
        "multi_evidence_synthesis",
        "ambiguous_underspecified",
        "source_citation_sensitive",
    ]  # long_tail_difficult absent
    directory = write_dataset(tmp_path, manifest, [VALID_EXAMPLE])

    with pytest.raises(ValueError, match="long_tail_difficult"):
        load_dataset(directory)


def test_load_dataset_accepts_non_benchmark_with_fewer_slices(tmp_path: Path) -> None:
    """Non-benchmark roles are not held to the frozen five-slice v0.1 contract."""
    manifest = dict(VALID_MANIFEST)
    manifest["role"] = "development"
    manifest["mandatory_slices"] = ["single_source_factual"]
    example = dict(VALID_EXAMPLE)
    example["dataset_role"] = "development"
    directory = write_dataset(tmp_path, manifest, [example])

    dataset = load_dataset(directory)
    assert dataset.manifest.mandatory_slices == ("single_source_factual",)


def test_load_dataset_accepts_development_with_empty_mandatory_slices(tmp_path: Path) -> None:
    """Spec scopes mandatory-slice governance to benchmark versions; other roles may be empty."""
    manifest = dict(VALID_MANIFEST)
    manifest["role"] = "development"
    manifest["mandatory_slices"] = []
    manifest["min_examples_per_slice"] = 1
    example = dict(VALID_EXAMPLE)
    example["dataset_role"] = "development"
    directory = write_dataset(tmp_path, manifest, [example])

    dataset = load_dataset(directory)
    assert dataset.manifest.mandatory_slices == ()
    assert len(dataset.examples) == 1


def test_load_dataset_rejects_whitespace_only_category(tmp_path: Path) -> None:
    """A whitespace-only category is not a reviewable classification."""
    blank = dict(VALID_EXAMPLE)
    blank["category"] = "   "
    blank["slices"] = []
    directory = write_dataset(tmp_path, VALID_MANIFEST, [blank])

    with pytest.raises(ValueError, match="category|classification"):
        load_dataset(directory)


def test_load_dataset_rejects_malformed_json_manifest(tmp_path: Path) -> None:
    directory = tmp_path / "dataset"
    directory.mkdir()
    (directory / "manifest.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest"):
        load_dataset(directory)


def test_load_dataset_rejects_malformed_jsonl_example(tmp_path: Path) -> None:
    directory = tmp_path / "dataset"
    directory.mkdir()
    (directory / "manifest.json").write_text(
        json.dumps(VALID_MANIFEST, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "examples.jsonl").write_text("{broken\n", encoding="utf-8")

    with pytest.raises(ValueError, match="example"):
        load_dataset(directory)


def test_load_dataset_rejects_missing_manifest_file(tmp_path: Path) -> None:
    directory = tmp_path / "dataset"
    directory.mkdir()

    with pytest.raises(ValueError, match="manifest"):
        load_dataset(directory)


def test_load_dataset_rejects_empty_examples(tmp_path: Path) -> None:
    directory = write_dataset(tmp_path, VALID_MANIFEST, [])

    with pytest.raises(ValueError):
        load_dataset(directory)


# ---------------------------------------------------------------------------
# Run-config validation failures
# ---------------------------------------------------------------------------


def test_load_run_config_rejects_invalid_runtime_adapter(tmp_path: Path) -> None:
    config = dict(VALID_RUN_CONFIG)
    config["runtime_adapter"] = "future_adapter"
    path = write_run_config(tmp_path, config)

    with pytest.raises(ValueError, match="runtime_adapter"):
        load_run_config(path)


def test_load_run_config_rejects_missing_primary_k_five(tmp_path: Path) -> None:
    config = dict(VALID_RUN_CONFIG)
    config["primary_k"] = 10
    path = write_run_config(tmp_path, config)

    with pytest.raises(ValueError, match="primary_k"):
        load_run_config(path)


def test_load_run_config_rejects_missing_required_k_values(tmp_path: Path) -> None:
    config = dict(VALID_RUN_CONFIG)
    config["retrieval_k_values"] = [1, 3, 5, 10]
    path = write_run_config(tmp_path, config)

    with pytest.raises(ValueError, match="retrieval_k_values"):
        load_run_config(path)


def test_load_run_config_rejects_invalid_score_semantics(tmp_path: Path) -> None:
    config = dict(VALID_RUN_CONFIG)
    config["score_semantics"] = "lower_is_better_distance"
    path = write_run_config(tmp_path, config)

    with pytest.raises(ValueError, match="score_semantics"):
        load_run_config(path)


def test_load_run_config_rejects_invalid_judge_config(tmp_path: Path) -> None:
    config = dict(VALID_RUN_CONFIG)
    config["judge"] = {"model": "gpt-4o-mini"}
    path = write_run_config(tmp_path, config)

    with pytest.raises(ValueError):
        load_run_config(path)


def test_load_run_config_rejects_missing_required_field(tmp_path: Path) -> None:
    config = {key: value for key, value in VALID_RUN_CONFIG.items() if key != "embedding_model"}
    path = write_run_config(tmp_path, config)

    with pytest.raises(ValueError, match="embedding_model"):
        load_run_config(path)


def test_load_run_config_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "run-config.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match="run config"):
        load_run_config(path)


def test_load_run_config_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run config"):
        load_run_config(tmp_path / "does-not-exist.json")


def test_load_run_config_resolves_env_placeholders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini-resolved")
    config = dict(VALID_RUN_CONFIG)
    config["generation_model"] = "${LLM_MODEL}"
    config["judge"] = {
        "model": "${LLM_MODEL}",
        "prompt_id": "rag-answer-judge-v0.1",
        "rubric_id": "d5-rag-answer-v0.1",
        "schema_version": 1,
        "temperature": 0.0,
    }
    path = write_run_config(tmp_path, config)
    loaded = load_run_config(path)
    assert loaded.generation_model == "gpt-4o-mini-resolved"
    assert loaded.judge is not None
    assert loaded.judge.model == "gpt-4o-mini-resolved"


def test_load_run_config_rejects_unresolved_placeholder(tmp_path: Path) -> None:
    config = dict(VALID_RUN_CONFIG)
    config["generation_model"] = "${UNRESOLVED_PLACEHOLDER_XYZ_123}"
    path = write_run_config(tmp_path, config)
    with pytest.raises(ValueError, match="Unresolved placeholder"):
        load_run_config(path)
