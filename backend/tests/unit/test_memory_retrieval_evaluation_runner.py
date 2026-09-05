"""Unit tests for the R6 memory retrieval evaluation runner.

Hermetic tests replay synthetic suites from `tmp_path` through the real
workspace, conversation, memory, promotion, and retrieval implementations, so
no test reads the tracked suite or writes outside temporary directories.
Answer-quality fields stay `INCONCLUSIVE` without a provider-backed judge.

No test here touches a model provider, Chroma, Docker, or the network.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.memory.evaluation.cli import main as cli_main
from backend.memory.evaluation.models import MemoryEvaluationResult
from backend.memory.evaluation.runner import (
    MemoryEvaluationError,
    _run_promoted_records,
    decide_retrieval_result,
    run_retrieval_evaluation,
)
from backend.memory.models import (
    MemoryRecord,
    MemoryRecordScope,
    MemoryRecordStatus,
    MemoryRecordType,
    SensitivityLabel,
    generate_memory_record_id,
)

PREFERENCE_MESSAGE = "Tôi ăn chay trường, hãy nhớ giúp tôi."


def _write_suite(tmp_path: Path, examples, dataset_id="r6-test") -> Path:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir(exist_ok=True)
    manifest = {
        "dataset_id": dataset_id,
        "dataset_version": "0.1-test",
        "dataset_role": "development",
        "examples_file": "examples.jsonl",
    }
    (suite_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (suite_dir / "examples.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in examples) + "\n",
        encoding="utf-8",
    )
    return suite_dir / "manifest.json"


def _promotion_example(example_id="p-1", content=PREFERENCE_MESSAGE, **overrides):
    payload = {
        "example_id": example_id,
        "kind": "promotion",
        "slice": "explicit-preference",
        "messages": [
            {
                "role": "user",
                "source": "ui",
                "trace_visibility": "included",
                "content": content,
            }
        ],
        "expected": {
            "promoted": [{"scope": "user", "type": "preference"}],
            "skipped": 0,
            "superseded": 0,
        },
    }
    payload.update(overrides)
    return payload


def _retrieval_example(example_id="r-1", **overrides):
    payload = {
        "example_id": example_id,
        "kind": "retrieval",
        "slice": "user-global",
        "seeds": [
            {
                "alias": "veg",
                "scope": "user",
                "memory_type": "preference",
                "status": "active",
                "text": "Tôi ăn chay trường mỗi ngày.",
                "confidence": 0.9,
                "sensitivity_label": "none",
            }
        ],
        "queries": [{"query": "ăn chay", "expected_aliases": ["veg"]}],
    }
    payload.update(overrides)
    return payload


def _run_suite(tmp_path: Path, examples, **kwargs):
    manifest = _write_suite(tmp_path, examples, **kwargs)
    return run_retrieval_evaluation(manifest, tmp_path / "out")


# 1. Result states on controlled evidence.


def test_matching_suite_reports_pass(tmp_path: Path):
    report = _run_suite(tmp_path, [_promotion_example(), _retrieval_example()])
    assert report.result_state is MemoryEvaluationResult.PASS
    assert report.promotion_precision.value == 1.0
    assert report.hit_at_5.value == 1.0
    assert report.irrelevant_rate.value == 0.0
    assert report.scope_accuracy.value == 1.0
    assert all(gate.passed for gate in report.hard_gates if gate.applicable)


def test_mismatched_suite_fails_quality_gate(tmp_path: Path):
    example = _retrieval_example()
    example["queries"] = [{"query": "ăn chay", "expected_aliases": ["ghost"]}]
    report = _run_suite(tmp_path, [example])
    assert report.result_state is MemoryEvaluationResult.FAIL
    assert report.hit_at_5.value == 0.0
    assert "memory_missed" in report.examples[0].failures


def test_empty_suite_is_inconclusive(tmp_path: Path):
    manifest = _write_suite(tmp_path, [])
    report = run_retrieval_evaluation(manifest, tmp_path / "out")
    assert report.result_state is MemoryEvaluationResult.INCONCLUSIVE


def test_malformed_example_is_invalid(tmp_path: Path):
    report = _run_suite(tmp_path, [{"example_id": "broken"}])
    assert report.result_state is MemoryEvaluationResult.INVALID
    assert report.invalid_examples == 1


def test_missing_manifest_raises(tmp_path: Path):
    with pytest.raises(MemoryEvaluationError):
        run_retrieval_evaluation(tmp_path / "nope.json", tmp_path / "out")


# 2. Hard-gate dominance and answer-quality limits.


def test_hard_gate_event_dominates_passing_metrics():
    assert (
        decide_retrieval_result(
            invalid_examples=0,
            hard_gate_events=1,
            promotion_precision=1.0,
            scope_accuracy=1.0,
            hit_at_5=1.0,
            irrelevant_rate=0.0,
            slice_precisions=[1.0],
        )
        is MemoryEvaluationResult.FAIL
    )


def test_measured_win_rate_below_threshold_fails():
    assert (
        decide_retrieval_result(
            invalid_examples=0,
            hard_gate_events=0,
            promotion_precision=1.0,
            scope_accuracy=1.0,
            hit_at_5=1.0,
            irrelevant_rate=0.0,
            personalization_win_rate=0.4,
            constraint_delta=0.1,
            slice_precisions=[1.0],
        )
        is MemoryEvaluationResult.FAIL
    )


def test_negative_constraint_delta_fails():
    assert (
        decide_retrieval_result(
            invalid_examples=0,
            hard_gate_events=0,
            promotion_precision=1.0,
            scope_accuracy=1.0,
            hit_at_5=1.0,
            irrelevant_rate=0.0,
            personalization_win_rate=0.8,
            constraint_delta=-0.05,
            slice_precisions=[1.0],
        )
        is MemoryEvaluationResult.FAIL
    )


def test_per_example_evidence_carries_selected_ids_and_reasons(tmp_path: Path):
    manifest = _write_suite(tmp_path, [_retrieval_example()])
    report = run_retrieval_evaluation(manifest, tmp_path / "out")
    (example,) = report.examples
    assert len(example.selected_ids) == 1
    assert example.selected_ids[0].startswith("mem_")
    assert list(example.selection_reasons) == ["lexical_match"]


def test_slices_carry_hit_rate_and_environment_is_recorded(tmp_path: Path):
    manifest = _write_suite(tmp_path, [_retrieval_example()])
    out_dir = tmp_path / "out"
    report = run_retrieval_evaluation(manifest, out_dir)
    assert report.slices[0].hit_rate == 1.0
    payload = json.loads((out_dir / "r6-test.json").read_text(encoding="utf-8"))
    assert "dirty_working_tree" in payload["environment"]
    assert "retrieval" in payload["environment"]
    assert payload["mandatory_slices"][0]["hit_rate"] == 1.0
    assert payload["per_example"][0]["selected_ids"] != []


def test_missing_evidence_does_not_mask_quality_failure():
    assert (
        decide_retrieval_result(
            invalid_examples=0,
            hard_gate_events=0,
            promotion_precision=None,
            scope_accuracy=None,
            hit_at_5=0.0,
            irrelevant_rate=None,
            slice_precisions=[],
        )
        is MemoryEvaluationResult.FAIL
    )


def test_answer_quality_fields_stay_inconclusive_without_judge(tmp_path: Path):
    report = _run_suite(tmp_path, [_promotion_example(), _retrieval_example()])
    assert report.personalization_win_rate.value is None
    assert report.constraint_delta.value is None
    assert any(
        "judge" in note.lower() or "INCONCLUSIVE" in note for note in report.notes
    )


# 3. Hygiene: redaction, determinism, filenames, CLI.


def test_reports_contain_no_raw_content(tmp_path: Path):
    secret = "API key của tôi là sk-test-R6unit9, đừng quên nhé."
    report = _run_suite(
        tmp_path,
        [
            _promotion_example(
                example_id="p-secret",
                content=secret,
                expected={
                    "promoted": [],
                    "skipped": 1,
                    "superseded": 0,
                },
            )
        ],
    )
    out_dir = tmp_path / "out"
    combined = (out_dir / "r6-test.json").read_text(encoding="utf-8") + (
        out_dir / "r6-test.md"
    ).read_text(encoding="utf-8")
    assert "sk-test-R6unit9" not in combined
    # A promotion-only suite has no retrieval evidence either way.
    assert report.result_state is MemoryEvaluationResult.INCONCLUSIVE


def test_metrics_are_deterministic_across_runs(tmp_path: Path):
    manifest = _write_suite(tmp_path, [_promotion_example(), _retrieval_example()])
    first = run_retrieval_evaluation(manifest, tmp_path / "out-1")
    second = run_retrieval_evaluation(manifest, tmp_path / "out-2")
    assert (
        first.promotion_precision.value,
        first.hit_at_5.value,
        first.irrelevant_rate.value,
        first.result_state,
    ) == (
        second.promotion_precision.value,
        second.hit_at_5.value,
        second.irrelevant_rate.value,
        second.result_state,
    )


def test_report_filenames_follow_dataset_id(tmp_path: Path):
    manifest = _write_suite(tmp_path, [_retrieval_example()], dataset_id="probe-suite")
    out_dir = tmp_path / "reports"
    run_retrieval_evaluation(manifest, out_dir)
    assert (out_dir / "probe-suite.json").exists()
    assert (out_dir / "probe-suite.md").exists()


def test_cli_run_retrieval_writes_reports(tmp_path: Path):
    manifest = _write_suite(tmp_path, [_promotion_example(), _retrieval_example()])
    out_dir = tmp_path / "reports"
    assert (
        cli_main(
            [
                "run-retrieval",
                "--fixture",
                str(manifest),
                "--output-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    payload = json.loads((out_dir / "r6-test.json").read_text(encoding="utf-8"))
    assert payload["result_state"] == "PASS"


def _scored_record(memory_id, created_at, **overrides):
    payload = {
        "memory_id": memory_id,
        "source_candidate_id": "mc_probe",
        "workspace_id": "tw_probe",
        "conversation_id": "cv_probe",
        "source_message_id": "ms_probe",
        "source_sequence": 1,
        "owner_user_id": "local-user",
        "scope": MemoryRecordScope.USER,
        "scope_id": "local-user",
        "memory_type": MemoryRecordType.PREFERENCE,
        "status": MemoryRecordStatus.ACTIVE,
        "text": "Người dùng ăn chay trường.",
        "confidence": 0.8,
        "sensitivity_label": SensitivityLabel.NONE,
        "supersedes_memory_id": None,
        "created_at": created_at,
        "updated_at": created_at,
        "expires_at": None,
    }
    payload.update(overrides)
    return MemoryRecord(**payload)


def test_run_records_follow_promoted_ids_not_timestamps():
    # A frozen or coarse clock can stamp a run record at or before the run
    # start, so attribution must follow the promoted ids the use case
    # returns, never a timestamp comparison.
    moment = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    promoted = _scored_record("mem_promoted", moment - timedelta(seconds=1))
    other = _scored_record("mem_other", moment + timedelta(seconds=1))

    selected = _run_promoted_records([other, promoted], ("mem_promoted",))

    assert [record.memory_id for record in selected] == ["mem_promoted"]
