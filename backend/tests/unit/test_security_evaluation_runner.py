"""Unit tests for the R9 security evaluation runner.

Hermetic tests replay synthetic suites from `tmp_path` with synthetic
owners and tokens, so no test reads the tracked suite, touches real
credentials, or writes outside temporary directories. No test touches a
model provider, Chroma, embeddings, or the network.
"""

import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from backend.app.config import settings
from backend.security.evaluation.cli import main as cli_main
from backend.security.evaluation.models import SecurityResultState
from backend.security.evaluation.runner import run_security_evaluation


def _auth_env(monkeypatch, enabled=True, registry=None):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", enabled)
    monkeypatch.setattr(
        settings,
        "LOCAL_AUTH_TOKENS_JSON",
        SecretStr(
            registry
            if registry is not None
            else '{"owner_a": "secret-alpha-token", "owner_b": "secret-beta-token"}'
        ),
    )


def _write_suite(tmp_path: Path, examples, dataset_id="r9-test") -> Path:
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


def _example(example_id="s-1", scenario="missing_token_denied", **overrides):
    payload = {
        "example_id": example_id,
        "slice": "authentication",
        "scenario": scenario,
    }
    payload.update(overrides)
    return payload


def test_valid_fixture_produces_pass(tmp_path: Path, monkeypatch):
    _auth_env(monkeypatch)
    manifest = _write_suite(
        tmp_path,
        [
            _example("s-missing", "missing_token_denied"),
            _example("s-cross", "cross_owner_workspace_denied", slice="cross_owner"),
        ],
    )

    report = run_security_evaluation(manifest, tmp_path / "out")

    assert report.result_state is SecurityResultState.PASS
    assert report.eligible_examples == 2
    assert all(gate.passed for gate in report.gates if gate.applicable)


def test_malformed_fixture_produces_invalid(tmp_path: Path, monkeypatch):
    _auth_env(monkeypatch)
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir(exist_ok=True)
    (suite_dir / "manifest.json").write_text("not json", encoding="utf-8")

    report = run_security_evaluation(suite_dir / "manifest.json", tmp_path / "out")

    assert report.result_state is SecurityResultState.INVALID


def test_empty_fixture_produces_inconclusive(tmp_path: Path, monkeypatch):
    _auth_env(monkeypatch)
    manifest = _write_suite(tmp_path, [])

    report = run_security_evaluation(manifest, tmp_path / "out")

    assert report.result_state is SecurityResultState.INCONCLUSIVE


def test_auth_disabled_produces_invalid(tmp_path: Path, monkeypatch):
    _auth_env(monkeypatch, enabled=False)
    manifest = _write_suite(tmp_path, [_example()])

    report = run_security_evaluation(manifest, tmp_path / "out")

    assert report.result_state is SecurityResultState.INVALID


def test_reports_use_dataset_id_and_exclude_tokens(tmp_path: Path, monkeypatch):
    _auth_env(monkeypatch)
    manifest = _write_suite(tmp_path, [_example()], dataset_id="r9-x")
    out_dir = tmp_path / "out"
    report = run_security_evaluation(manifest, out_dir)

    assert report.result_state is SecurityResultState.PASS
    assert (out_dir / "r9-x.json").exists()
    assert (out_dir / "r9-x.md").exists()
    combined = (out_dir / "r9-x.json").read_text(encoding="utf-8") + (
        out_dir / "r9-x.md"
    ).read_text(encoding="utf-8")
    assert "secret-alpha-token" not in combined
    assert "secret-beta-token" not in combined


def test_logged_token_value_fails_token_leakage_gate(tmp_path: Path, monkeypatch):
    _auth_env(monkeypatch)
    import logging

    from backend.security.evaluation import runner as runner_module

    def _leaky(ctx):
        logging.getLogger("travel_agent_security").warning(
            "probe emitted %s", ctx.tokens["owner_a"]
        )
        return {"events": {}, "failures": []}

    monkeypatch.setitem(runner_module._SCENARIOS, "logged_token_probe", _leaky)
    manifest = _write_suite(tmp_path, [_example("s-leak", "logged_token_probe")])

    report = run_security_evaluation(manifest, tmp_path / "out")

    gate = next(item for item in report.gates if item.gate == "token_leakage")
    assert gate.events == 1
    assert report.result_state is SecurityResultState.FAIL


def test_cli_run_security_writes_reports(tmp_path: Path, monkeypatch):
    _auth_env(monkeypatch)
    manifest = _write_suite(tmp_path, [_example()], dataset_id="r9-x")
    out_dir = tmp_path / "reports"
    assert (
        cli_main(
            [
                "run-security",
                "--fixture",
                str(manifest),
                "--output-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    payload = json.loads((out_dir / "r9-x.json").read_text(encoding="utf-8"))
    assert payload["result_state"] == "PASS"
