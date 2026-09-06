"""Unit tests for the R8 operational evaluation runner.

Hermetic tests replay synthetic suites from `tmp_path` through the real
observability code, so no test reads the tracked suite or writes outside
temporary directories. No test touches a model provider, Chroma data
creation, embeddings, or the network.
"""

import json
from pathlib import Path

import pytest

from backend.observability.evaluation.cli import main as cli_main
from backend.observability.evaluation.models import OpsResultState
from backend.observability.evaluation.runner import run_readiness_evaluation


def _write_suite(tmp_path: Path, examples, dataset_id="r8-test") -> Path:
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


def _emit_example(example_id="e-1", **overrides):
    payload = {
        "example_id": example_id,
        "slice": "log_privacy",
        "checks": [
            {
                "check": "emit_accepted",
                "event": {
                    "event_name": "chat.turn.completed",
                    "component": "chat",
                    "result": "success",
                    "fields": {"conversation_id": "cv_probe"},
                },
                "expect": {"component": "chat", "result": "success"},
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_valid_fixture_produces_pass(tmp_path: Path):
    manifest = _write_suite(
        tmp_path,
        [
            _emit_example(),
            {
                "example_id": "r-1",
                "slice": "readiness_degradation",
                "checks": [
                    {
                        "check": "readiness",
                        "setup": {"token": None},
                        "expect": {
                            "status": "not_ready",
                            "components": {
                                "model_provider": ["not_ready", "credential_missing"]
                            },
                        },
                    }
                ],
            },
        ],
    )

    report = run_readiness_evaluation(manifest, tmp_path / "out")

    assert report.result_state is OpsResultState.PASS
    assert report.eligible_examples == 2


def test_fixture_with_wrong_expectation_produces_fail(tmp_path: Path):
    manifest = _write_suite(
        tmp_path,
        [
            _emit_example(
                checks=[
                    {
                        "check": "emit_accepted",
                        "event": {
                            "event_name": "chat.turn.completed",
                            "component": "chat",
                            "result": "success",
                            "fields": {},
                        },
                        "expect": {"result": "failure"},
                    }
                ]
            )
        ],
    )

    report = run_readiness_evaluation(manifest, tmp_path / "out")

    assert report.result_state is OpsResultState.FAIL
    assert "field_mismatch" in report.per_example[0].failures


def test_unsafe_field_expectation_produces_fail(tmp_path: Path):
    manifest = _write_suite(
        tmp_path,
        [
            _emit_example(
                checks=[
                    {
                        "check": "emit_accepted",
                        "event": {
                            "event_name": "chat.turn.completed",
                            "component": "chat",
                            "result": "success",
                            "fields": {"prompt": "NEVER_LOG_PROMPT_SENTINEL"},
                        },
                        "expect": {"result": "success"},
                    }
                ]
            )
        ],
    )

    report = run_readiness_evaluation(manifest, tmp_path / "out")

    assert report.result_state is OpsResultState.FAIL
    assert any(
        failure.startswith("emit_failed") for failure in report.per_example[0].failures
    )


def test_malformed_fixture_produces_invalid(tmp_path: Path):
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir(exist_ok=True)
    (suite_dir / "manifest.json").write_text("not json", encoding="utf-8")

    report = run_readiness_evaluation(suite_dir / "manifest.json", tmp_path / "out")

    assert report.result_state is OpsResultState.INVALID


def test_empty_fixture_produces_inconclusive(tmp_path: Path):
    manifest = _write_suite(tmp_path, [])

    report = run_readiness_evaluation(manifest, tmp_path / "out")

    assert report.result_state is OpsResultState.INCONCLUSIVE


def test_reports_use_dataset_id_and_exclude_sentinels(tmp_path: Path):
    manifest = _write_suite(tmp_path, [_emit_example()], dataset_id="r8-x")
    out_dir = tmp_path / "out"
    report = run_readiness_evaluation(manifest, out_dir)

    assert report.result_state is OpsResultState.PASS
    assert (out_dir / "r8-x.json").exists()
    assert (out_dir / "r8-x.md").exists()
    combined = (out_dir / "r8-x.json").read_text(encoding="utf-8") + (
        out_dir / "r8-x.md"
    ).read_text(encoding="utf-8")
    assert "NEVER_LOG" not in combined


def test_cli_run_readiness_writes_reports(tmp_path: Path):
    manifest = _write_suite(tmp_path, [_emit_example()], dataset_id="r8-x")
    out_dir = tmp_path / "reports"
    assert (
        cli_main(
            [
                "run-readiness",
                "--fixture",
                str(manifest),
                "--output-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    payload = json.loads((out_dir / "r8-x.json").read_text(encoding="utf-8"))
    assert payload["result_state"] == "PASS"
