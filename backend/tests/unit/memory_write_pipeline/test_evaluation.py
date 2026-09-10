"""Unit tests for memory write pipeline evaluation harness and CLI."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import pytest

from backend.memory.write_pipeline.evaluation import (
    HARD_GATES,
    INITIAL_THRESHOLDS,
    MANDATORY_SLICES,
    DatasetManifest,
    EvaluationExample,
    EvaluationRunner,
    MetricAccounting,
    ResultState,
    SuiteReport,
    SuiteType,
    load_dataset,
    validate_dataset,
)
from backend.memory.write_pipeline.evaluation.cli import main
from backend.memory.write_pipeline.evaluation.dataset import DatasetValidationError
from backend.memory.write_pipeline.evaluation.models import sanitize_report_value

FIXTURES_DIR = Path("docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1")


def test_dataset_load_and_validation_success() -> None:
    """Validate that the canonical evaluation dataset loads and satisfies manifest rules."""
    manifest, examples = load_dataset(FIXTURES_DIR)
    assert manifest.dataset_id == "write-pipeline-hotel-atmosphere-v0.1"
    assert manifest.canonical_key == "travel.preference.hotel_atmosphere"
    assert len(examples) == 22
    assert manifest.examples_count == 22

    # Verify all 16 mandatory slices are represented
    slices_present = {ex.slice for ex in examples}
    for req_slice in MANDATORY_SLICES:
        assert req_slice in slices_present

    val_res = validate_dataset(FIXTURES_DIR)
    assert val_res["valid"] is True
    assert val_res["examples_count"] == 22


def test_dataset_missing_mandatory_slice(tmp_path: Path) -> None:
    """Empty or missing mandatory slices must cause dataset validation to fail."""
    manifest_data = {
        "dataset_id": "test-dataset",
        "version": "0.1.0",
        "role": "development",
        "canonical_key": "travel.preference.hotel_atmosphere",
        "values": ["quiet", "lively"],
        "languages": ["en"],
        "examples_count": 1,
        "mandatory_slices": list(MANDATORY_SLICES),
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    # Only provide 1 example for 'vietnamese_explicit'
    example_data = {
        "example_id": "ex1",
        "slice": "vietnamese_explicit",
        "language": "vi",
        "source_events": [],
    }
    (tmp_path / "examples.jsonl").write_text(json.dumps(example_data) + "\n", encoding="utf-8")

    with pytest.raises(DatasetValidationError) as exc_info:
        load_dataset(tmp_path)
    assert "missing mandatory slices" in str(exc_info.value).lower()


def test_dataset_duplicate_example_id(tmp_path: Path) -> None:
    """Duplicate example IDs must cause dataset validation to fail."""
    manifest_data = {
        "dataset_id": "test-dataset",
        "version": "0.1.0",
        "role": "development",
        "canonical_key": "travel.preference.hotel_atmosphere",
        "values": ["quiet"],
        "languages": ["en"],
        "examples_count": 2,
        "mandatory_slices": ["english_explicit"],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    ex1 = {"example_id": "duplicate_id", "slice": "english_explicit", "language": "en", "source_events": []}
    ex2 = {"example_id": "duplicate_id", "slice": "english_explicit", "language": "en", "source_events": []}
    (tmp_path / "examples.jsonl").write_text(
        json.dumps(ex1) + "\n" + json.dumps(ex2) + "\n", encoding="utf-8"
    )

    with pytest.raises(DatasetValidationError) as exc_info:
        load_dataset(tmp_path)
    assert "duplicate example_id" in str(exc_info.value).lower()


def test_dataset_count_mismatch(tmp_path: Path) -> None:
    """Mismatch between manifest examples_count and loaded rows must fail validation."""
    manifest_data = {
        "dataset_id": "test-dataset",
        "version": "0.1.0",
        "role": "development",
        "canonical_key": "travel.preference.hotel_atmosphere",
        "values": ["quiet"],
        "languages": ["en"],
        "examples_count": 5,
        "mandatory_slices": ["english_explicit"],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    ex1 = {"example_id": "ex_1", "slice": "english_explicit", "language": "en", "source_events": []}
    (tmp_path / "examples.jsonl").write_text(json.dumps(ex1) + "\n", encoding="utf-8")

    with pytest.raises(DatasetValidationError) as exc_info:
        load_dataset(tmp_path)
    assert "example count mismatch" in str(exc_info.value).lower()


def test_metric_accounting() -> None:
    """MetricAccounting calculates ratios and compares with thresholds."""
    metric = MetricAccounting(
        name="precision",
        numerator=95.0,
        denominator=100.0,
        threshold=0.95,
        passed=True,
    )
    assert metric.value == 0.95
    assert metric.passed is True

    # Zero denominator
    zero_metric = MetricAccounting(
        name="empty",
        numerator=0.0,
        denominator=0.0,
        threshold=1.0,
        passed=True,
    )
    assert zero_metric.value == 1.0


def test_runner_executes_suite_and_generates_reports(tmp_path: Path) -> None:
    """Runner should execute safety, quality, and operational suites cleanly."""
    runner = EvaluationRunner()
    manifest, examples = load_dataset(FIXTURES_DIR)

    report = runner.run_suite(FIXTURES_DIR, suite_type=SuiteType.SAFETY, output_dir=tmp_path)
    assert report.result_state == ResultState.PASS
    assert report.failed_examples == 0
    assert sum(report.hard_gate_events.values()) == 0

    json_file = tmp_path / "safety-report.json"
    md_file = tmp_path / "safety-report.md"
    assert json_file.exists()
    assert md_file.exists()

    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["result_state"] == "PASS"
    assert "metrics" in data


def test_report_sanitization() -> None:
    """Sensitive keys and tokens must be redacted in report serialization."""
    raw = {
        "key": "sk-1234567890abcdefghijklmnop",
        "github": "ghp_123456789012345678901234567890",
        "card": "1234567812345678",
        "nested": {"key": "sk-9999999999abcdef"},
    }
    sanitized = sanitize_report_value(raw)
    assert sanitized["key"] == "[REDACTED_API_KEY]"
    assert sanitized["github"] == "[REDACTED_TOKEN]"
    assert sanitized["card"] == "[REDACTED_PAYMENT_CARD]"
    assert sanitized["nested"]["key"] == "[REDACTED_API_KEY]"


def test_cli_subcommands(tmp_path: Path) -> None:
    """CLI subcommands should return expected exit codes."""
    # 1. validate-dataset
    code = main(["validate-dataset", "--dataset", str(FIXTURES_DIR)])
    assert code == 0

    # 2. preflight
    code = main(["preflight", "--dataset", str(FIXTURES_DIR)])
    assert code == 0

    # 3. run
    out_dir = tmp_path / "cli_reports"
    code = main(["run", "--dataset", str(FIXTURES_DIR), "--suite", "safety", "--output-dir", str(out_dir)])
    assert code == 0

    # 4. compare
    report_file = out_dir / "safety-report.json"
    comp_dir = tmp_path / "comp_reports"
    code = main(["compare", "--baseline", str(report_file), "--candidate", str(report_file), "--output-dir", str(comp_dir)])
    assert code == 0
