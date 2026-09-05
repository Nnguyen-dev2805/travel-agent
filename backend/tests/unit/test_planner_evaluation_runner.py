"""Unit tests for the R7 planner state evaluation runner.

Hermetic tests replay synthetic suites from `tmp_path` through the real
planner service and SQLite adapter, so no test reads the tracked suite or
writes outside temporary directories. No test touches a model provider,
RAG retrieval, Chroma, memory, orchestration, or the network.
"""

import json
from pathlib import Path

import pytest

from backend.planner.evaluation.cli import main as cli_main
from backend.planner.evaluation.models import PlannerResultState
from backend.planner.evaluation.runner import run_state_evaluation

PREFERENCE_STATEMENT = "Chuyến này ăn chay."


def _write_suite(tmp_path: Path, examples, dataset_id="r7-test") -> Path:
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


def _versioning_example(example_id="v-1", **overrides):
    payload = {
        "example_id": example_id,
        "slice": "itinerary_versioning",
        "actions": [
            {
                "op": "create_itinerary",
                "status": "draft",
                "title": "Hà Nội 3 ngày",
                "items": [
                    {
                        "day_index": 1,
                        "position": 1,
                        "item_type": "meal",
                        "title": "Bún chả Hương Liên",
                    }
                ],
            },
            {
                "op": "create_itinerary",
                "status": "draft",
                "title": "Hà Nội 4 ngày",
                "items": [],
            },
            {"op": "accept_itinerary", "version_ref": 1},
        ],
        "expected": {
            "version_numbers": [1, 2],
            "statuses": {"v0": "draft", "v1": "accepted"},
            "operations": [
                "accept_itinerary",
                "create_itinerary",
                "create_itinerary",
            ],
        },
    }
    payload.update(overrides)
    return payload


def _rejected_example(example_id="j-1", **overrides):
    payload = {
        "example_id": example_id,
        "slice": "rejected_option_preservation",
        "actions": [
            {
                "op": "record_decision",
                "decision_type": "booking",
                "status": "rejected",
                "statement": "Không đặt khách sạn này.",
            }
        ],
        "expected": {
            "rejected_listable": 1,
            "operations": ["record_decision"],
        },
    }
    payload.update(overrides)
    return payload


def _chat_example(example_id="c-1", **overrides):
    payload = {
        "example_id": example_id,
        "slice": "chat_isolation",
        "actions": [
            {"op": "append_message", "content": "Lên giúp tôi lịch trình Huế."},
            {"op": "append_message", "content": "Thêm một ngày ở Hội An."},
        ],
        "expected": {"planner_rows": 0, "operations": []},
    }
    payload.update(overrides)
    return payload


def test_passing_suite_reports_pass(tmp_path: Path):
    manifest = _write_suite(
        tmp_path, [_versioning_example(), _rejected_example(), _chat_example()]
    )

    report = run_state_evaluation(manifest, tmp_path / "out")

    assert report.result_state is PlannerResultState.PASS
    assert all(gate.passed for gate in report.gates if gate.applicable)
    assert report.eligible_examples == 3


def test_broken_version_continuity_reports_fail(tmp_path: Path):
    manifest = _write_suite(
        tmp_path,
        [_versioning_example(expected={"version_numbers": [1, 3]})],
    )

    report = run_state_evaluation(manifest, tmp_path / "out")

    assert report.result_state is PlannerResultState.FAIL
    assert "version_numbers_mismatch" in report.per_example[0].failures


def test_cross_workspace_denial_gate(tmp_path: Path):
    manifest = _write_suite(
        tmp_path,
        [
            {
                "example_id": "x-1",
                "slice": "cross_workspace_isolation",
                "actions": [
                    {
                        "op": "create_itinerary",
                        "status": "draft",
                        "title": "t",
                        "items": [],
                    },
                    {
                        "op": "get_itinerary_cross",
                        "version_ref": 0,
                        "expect_denied": True,
                    },
                ],
                "expected": {
                    "version_numbers": [1],
                    "denied": 1,
                    "operations": ["create_itinerary"],
                },
            }
        ],
    )

    report = run_state_evaluation(manifest, tmp_path / "out")

    assert report.result_state is PlannerResultState.PASS


def test_empty_suite_is_inconclusive(tmp_path: Path):
    manifest = _write_suite(tmp_path, [])

    report = run_state_evaluation(manifest, tmp_path / "out")

    assert report.result_state is PlannerResultState.INCONCLUSIVE


def test_malformed_fixture_is_invalid(tmp_path: Path):
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir(exist_ok=True)
    (suite_dir / "manifest.json").write_text("not json", encoding="utf-8")
    manifest = suite_dir / "manifest.json"

    report = run_state_evaluation(manifest, tmp_path / "out")

    assert report.result_state is PlannerResultState.INVALID


def test_reports_carry_no_raw_content(tmp_path: Path):
    manifest = _write_suite(tmp_path, [_rejected_example()], dataset_id="r7-x")
    out_dir = tmp_path / "out"
    report = run_state_evaluation(manifest, out_dir)

    assert report.result_state is PlannerResultState.PASS
    combined = (out_dir / "r7-x.json").read_text(encoding="utf-8") + (
        out_dir / "r7-x.md"
    ).read_text(encoding="utf-8")
    assert "Không đặt khách sạn này" not in combined
    assert "Bún chả" not in combined


def test_cli_run_state_writes_reports(tmp_path: Path):
    manifest = _write_suite(tmp_path, [_versioning_example()], dataset_id="r7-x")
    out_dir = tmp_path / "reports"
    assert (
        cli_main(
            [
                "run-state",
                "--fixture",
                str(manifest),
                "--output-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    payload = json.loads((out_dir / "r7-x.json").read_text(encoding="utf-8"))
    assert payload["result_state"] == "PASS"
