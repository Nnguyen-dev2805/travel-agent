"""Unit tests for the R5 memory shadow evaluation runner.

Hermetic tests replay synthetic fixtures from `tmp_path` through the real
workspace, conversation, memory, extraction, and policy implementations, so
no test reads the tracked fixture or writes outside temporary directories.
Result-state rules are also pinned directly against `decide_result_state`.

No test here touches a model provider, Chroma, Docker, or the network.
"""

import json
from pathlib import Path

import pytest

from backend.memory.evaluation.cli import main as cli_main
from backend.memory.evaluation.models import MemoryEvaluationResult
from backend.memory.evaluation.runner import (
    MemoryEvaluationError,
    count_secret_promotions,
    count_workspace_leaks,
    decide_result_state,
    run_shadow_evaluation,
)
from backend.memory.models import (
    MemoryCandidate,
    MemoryCandidateStatus,
    MemoryScope,
    MemoryType,
    PolicyReason,
    SensitivityLabel,
    generate_memory_candidate_id,
    generate_memory_run_id,
)

SECRET_TEXT = "API key của tôi là sk-test-Unit000, đừng quên nhé."


def _write_fixture(tmp_path: Path, examples) -> Path:
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    manifest = {
        "dataset_id": "r5-shadow-test",
        "dataset_version": "0.1-test",
        "dataset_role": "development",
        "examples_file": "examples.jsonl",
    }
    (fixture_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (fixture_dir / "examples.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in examples) + "\n",
        encoding="utf-8",
    )
    return fixture_dir / "manifest.json"


def _example(example_id, content, expected, **overrides):
    payload = {
        "example_id": example_id,
        "slice": "explicit-preference",
        "messages": [
            {
                "role": "user",
                "source": "ui",
                "trace_visibility": "included",
                "content": content,
            }
        ],
        "expected": expected,
    }
    payload.update(overrides)
    return payload


def _accepted_preference():
    return [
        {
            "scope": "user",
            "type": "preference",
            "status": "accepted",
            "reason": "supported_preference",
        }
    ]


def _run_fixture(tmp_path: Path, examples):
    manifest = _write_fixture(tmp_path, examples)
    return run_shadow_evaluation(manifest, tmp_path / "out")


# 1. Result states on controlled evidence.


def test_matching_fixture_reports_pass(tmp_path: Path):
    report = _run_fixture(
        tmp_path,
        [_example("ex-1", "Tôi ăn chay trường.", _accepted_preference())],
    )
    assert report.result_state is MemoryEvaluationResult.PASS
    assert report.extraction_precision.value == 1.0
    assert report.extraction_recall.value == 1.0
    assert report.scope_accuracy.value == 1.0
    assert report.eligible_examples == 1
    assert all(gate.passed for gate in report.hard_gates if gate.applicable)


def test_mismatched_fixture_fails_quality_gate(tmp_path: Path):
    report = _run_fixture(
        tmp_path,
        [_example("ex-1", "Hôm nay trời đẹp quá.", _accepted_preference())],
    )
    assert report.result_state is MemoryEvaluationResult.FAIL
    assert report.extraction_precision.value == 0.0
    assert "memory_missed" in report.examples[0].failures
    assert "memory_false_write" in report.examples[0].failures


def test_empty_fixture_is_inconclusive(tmp_path: Path):
    manifest = _write_fixture(tmp_path, [])
    report = run_shadow_evaluation(manifest, tmp_path / "out")
    assert report.result_state is MemoryEvaluationResult.INCONCLUSIVE
    assert report.eligible_examples == 0


def test_malformed_example_is_invalid(tmp_path: Path):
    report = _run_fixture(tmp_path, [{"example_id": "ex-broken"}])
    assert report.result_state is MemoryEvaluationResult.INVALID
    assert report.invalid_examples == 1


def test_missing_manifest_raises(tmp_path: Path):
    with pytest.raises(MemoryEvaluationError):
        run_shadow_evaluation(tmp_path / "nope.json", tmp_path / "out")


# 2. Hard-gate dominance is pinned without needing a real violation.


def test_hard_gate_event_dominates_passing_metrics():
    assert (
        decide_result_state(
            invalid_examples=0,
            hard_gate_events=1,
            precision=1.0,
            recall=1.0,
            scope_accuracy=1.0,
            slice_precisions=[1.0],
        )
        is MemoryEvaluationResult.FAIL
    )


def test_invalid_evidence_dominates_everything():
    assert (
        decide_result_state(
            invalid_examples=1,
            hard_gate_events=1,
            precision=1.0,
            recall=1.0,
            scope_accuracy=1.0,
            slice_precisions=[1.0],
        )
        is MemoryEvaluationResult.INVALID
    )


def test_slice_regression_fails_despite_passing_averages():
    assert (
        decide_result_state(
            invalid_examples=0,
            hard_gate_events=0,
            precision=1.0,
            recall=1.0,
            scope_accuracy=1.0,
            slice_precisions=[1.0, 0.5],
        )
        is MemoryEvaluationResult.FAIL
    )


# 3. Reports never carry raw content.


def test_reports_contain_no_raw_content(tmp_path: Path):
    manifest = _write_fixture(
        tmp_path, [_example("ex-1", SECRET_TEXT, _accepted_preference())]
    )
    out_dir = tmp_path / "out"
    run_shadow_evaluation(manifest, out_dir)
    combined = (out_dir / "r5-shadow-test.json").read_text(encoding="utf-8") + (
        out_dir / "r5-shadow-test.md"
    ).read_text(encoding="utf-8")
    assert "sk-test-Unit000" not in combined


def test_metrics_are_deterministic_across_runs(tmp_path: Path):
    manifest = _write_fixture(
        tmp_path, [_example("ex-1", "Tôi ăn chay trường.", _accepted_preference())]
    )
    first = run_shadow_evaluation(manifest, tmp_path / "out-1")
    second = run_shadow_evaluation(manifest, tmp_path / "out-2")
    assert (
        first.extraction_precision.value,
        first.extraction_recall.value,
        first.scope_accuracy.value,
        first.result_state,
    ) == (
        second.extraction_precision.value,
        second.extraction_recall.value,
        second.scope_accuracy.value,
        second.result_state,
    )


def _gate_candidate(text, status=MemoryCandidateStatus.ACCEPTED, **overrides):
    from datetime import datetime, timezone

    payload = {
        "candidate_id": generate_memory_candidate_id(),
        "run_id": generate_memory_run_id(),
        "workspace_id": "tw_probe",
        "conversation_id": "cv_probe",
        "source_message_id": "ms_probe",
        "source_sequence": 1,
        "proposed_scope": MemoryScope.USER,
        "proposed_type": MemoryType.PREFERENCE,
        "status": status,
        "confidence": 0.9,
        "sensitivity_label": SensitivityLabel.NONE,
        "text": text,
        "evidence_summary": "signal=preference:thích",
        "reason": PolicyReason.SUPPORTED_PREFERENCE,
        "created_at": datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc),
    }
    payload.update(overrides)
    return MemoryCandidate(**payload)


def test_secret_detector_scans_content_not_labels():
    leaked = _gate_candidate("token = abcxyz9 còn đây")
    assert count_secret_promotions([leaked]) == 1
    clean = _gate_candidate("Người dùng thích đi biển.")
    assert count_secret_promotions([clean]) == 0
    rejected = _gate_candidate("sk-test-abc123", status=MemoryCandidateStatus.REJECTED)
    assert count_secret_promotions([rejected]) == 0


def test_workspace_leak_detector_fires_on_foreign_scope():
    own = _gate_candidate("Người dùng thích đi biển.")
    assert count_workspace_leaks([own], "tw_probe", "cv_probe") == 0
    foreign = _gate_candidate("Người dùng thích đi biển.", workspace_id="tw_other")
    assert count_workspace_leaks([foreign], "tw_probe", "cv_probe") == 1


def test_report_filenames_follow_dataset_id(tmp_path: Path):
    manifest = _write_fixture(tmp_path, [])
    raw = json.loads((tmp_path / "fixture" / "manifest.json").read_text())
    raw["dataset_id"] = "probe-dataset"
    (tmp_path / "fixture" / "manifest.json").write_text(json.dumps(raw))
    out_dir = tmp_path / "reports"
    run_shadow_evaluation(manifest, out_dir)
    assert (out_dir / "probe-dataset.json").exists()
    assert (out_dir / "probe-dataset.md").exists()
    assert not (out_dir / "r5-shadow-v0.1.json").exists()


def test_cli_writes_reports_to_tmp_output(tmp_path: Path):
    manifest = _write_fixture(
        tmp_path, [_example("ex-1", "Tôi ăn chay trường.", _accepted_preference())]
    )
    out_dir = tmp_path / "reports"
    assert (
        cli_main(
            [
                "run-shadow",
                "--fixture",
                str(manifest),
                "--output-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    assert (out_dir / "r5-shadow-test.json").exists()
    assert (out_dir / "r5-shadow-test.md").exists()
    payload = json.loads((out_dir / "r5-shadow-test.json").read_text(encoding="utf-8"))
    assert payload["result_state"] == "PASS"
