"""Deterministic R8 operational evaluation runner.

The runner replays every fixture example through the real observability
code: event emission and redaction for privacy slices, readiness probes
over isolated temporary state for degradation and schema slices, and a
reason-to-runbook routing table for runbook slices. Reports carry
identifiers, gate evidence, and controlled failure labels only.

Result states follow the D5 vocabulary without creating a canonical D5
operations protocol: `PASS` when every gate holds, `FAIL` on any gate
failure, `INCONCLUSIVE` for an empty but valid suite, and `INVALID` for
malformed fixture evidence.

The runner never calls a model provider, RAG retrieval, Chroma collection
creation, embeddings, memory, orchestration, or the network.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Optional

from backend.app.config import settings
from backend.observability import events
from backend.observability.context import reset_request_id, set_request_id
from backend.observability.evaluation.models import (
    OpsEvaluationError,
    OpsExampleScore,
    OpsGateScore,
    OpsReport,
    OpsResultState,
)
from backend.observability.models import (
    EventComponent,
    EventName,
    EventResult,
    ObservabilityValidationError,
)
from backend.observability.readiness import (
    expected_schema_modules,
    build_readiness_snapshot,
)
from backend.observability.redaction import sanitize_event_fields
from backend.storage.schema_registry import (
    open_application_database,
    register_module_schema,
)

_KNOWN_SLICES = frozenset(
    {
        "request_correlation",
        "log_privacy",
        "readiness_degradation",
        "storage_schema",
        "evaluation_report_evidence",
        "runbook_routing",
    }
)

_GATE_NAMES = (
    "request_correlation",
    "log_privacy",
    "readiness_degradation",
    "storage_schema",
    "evaluation_report_evidence",
    "runbook_routing",
)

RUNBOOK_ROUTES = {
    "credential_missing": "docs/runbooks/local-development.md",
    "path_missing": "docs/runbooks/local-development.md",
    "database_missing": "docs/runbooks/local-development.md",
    "memory_retrieval_disabled": "docs/runbooks/local-development.md",
    "module_missing": "docs/runbooks/local-development.md",
    "probe_failed": "docs/runbooks/local-development.md",
    "store_marker_mismatch": "docs/runbooks/incident-response.md",
    "schema_incompatible": "docs/runbooks/incident-response.md",
    "schema_registry_missing": "docs/runbooks/incident-response.md",
    "unreadable": "docs/runbooks/incident-response.md",
    "evidence_gap": "docs/runbooks/deployment.md",
}
"""Reason code to runbook routing table for degraded readiness states."""


def _event_view(event) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_name": event.event_name.value,
        "component": event.component.value,
        "severity": event.severity.value,
        "result": event.result.value,
        "request_id": event.request_id,
        "workspace_id": event.workspace_id,
        "conversation_id": event.conversation_id,
        "message_id": event.message_id,
        "memory_id": event.memory_id,
        "itinerary_version_id": event.itinerary_version_id,
        "decision_id": event.decision_id,
        "operation_id": event.operation_id,
        "failure_class": event.failure_class,
        "reason_code": event.reason_code,
        "duration_ms": event.duration_ms,
        "counters": dict(event.counters),
    }


def _check_emit_accepted(spec: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    payload = spec.get("event", {})
    fields = dict(payload.get("fields", {}))
    request_id = fields.pop("request_id", None)
    token = None
    if request_id is not None:
        token = set_request_id(request_id)
    try:
        try:
            event = events.emit_event(
                EventName(payload["event_name"]),
                EventComponent(payload["component"]),
                EventResult(payload["result"]),
                **fields,
            )
        except (ObservabilityValidationError, ValueError) as error:
            return [f"emit_failed:{type(error).__name__}"]
        view = _event_view(event)
        for key, value in spec.get("expect", {}).items():
            if view.get(key) != value:
                failures.append("field_mismatch")
                break
    finally:
        if token is not None:
            reset_request_id(token)
    return failures


def _check_emit_rejected(spec: dict[str, Any]) -> list[str]:
    payload = spec.get("event", {})
    try:
        events.emit_event(
            EventName(payload["event_name"]),
            EventComponent(payload["component"]),
            EventResult(payload["result"]),
            **dict(payload.get("fields", {})),
        )
    except (ObservabilityValidationError, ValueError):
        return []
    return ["emit_not_rejected"]


def _check_sanitize(spec: dict[str, Any]) -> list[str]:
    try:
        cleaned = sanitize_event_fields(spec.get("fields", {}))
    except ObservabilityValidationError:
        return [] if spec.get("expect_rejected") else ["sanitize_failed"]
    if spec.get("expect_rejected"):
        return ["sanitize_not_rejected"]
    for key, value in spec.get("expect", {}).items():
        if cleaned.get(key) != value:
            return ["sanitize_mismatch"]
    return []


def _setup_readiness(tmp: Path, setup: dict[str, Any]) -> dict[str, Any]:
    """Build isolated probe inputs; restore global settings afterwards."""
    overlays: dict[str, Any] = {}
    previous: dict[str, Any] = {}
    if "token" in setup:
        token = setup["token"]
        previous["GITHUB_TOKEN"] = settings.GITHUB_TOKEN
        settings.GITHUB_TOKEN = token if token is not None else ""
        overlays["token"] = True
    if "memory_enabled" in setup:
        previous["MEMORY_RETRIEVAL_ENABLED"] = settings.MEMORY_RETRIEVAL_ENABLED
        settings.MEMORY_RETRIEVAL_ENABLED = bool(setup["memory_enabled"])
        overlays["memory_enabled"] = True
    reports_dir = tmp / "reports"
    reports_dir.mkdir(exist_ok=True)
    for relpath, payload in setup.get("reports", {}).items():
        target = reports_dir / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload), encoding="utf-8")
    overlays["reports_dir"] = reports_dir
    if setup.get("good_schema"):
        db_path = tmp / "app.sqlite3"
        connection = open_application_database(db_path)
        try:
            for module, version in expected_schema_modules().items():
                register_module_schema(connection, module, version, lambda _: None)
        finally:
            connection.close()
        overlays["db_path"] = db_path
    elif "bad_schema" in setup:
        bad = setup["bad_schema"]
        db_path = tmp / "app.sqlite3"
        connection = open_application_database(db_path)
        try:
            register_module_schema(
                connection, bad["module"], int(bad["version"]), lambda _: None
            )
        finally:
            connection.close()
        overlays["db_path"] = db_path
    elif setup.get("missing_db"):
        overlays["db_path"] = tmp / "absent.sqlite3"
    if setup.get("missing_chroma"):
        overlays["chroma_dir"] = tmp / "absent-chromadb"
    if setup.get("chroma_present"):
        present = tmp / "chromadb"
        present.mkdir(exist_ok=True)
        overlays["chroma_dir"] = present
    return {"overlays": overlays, "previous": previous}


def _check_readiness(spec: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="r8-readiness-") as raw:
        tmp = Path(raw)
        previous: dict[str, Any] = {}
        try:
            try:
                built = _setup_readiness(tmp, spec.get("setup", {}))
            except (OSError, ValueError) as error:
                return [f"setup_failed:{type(error).__name__}"]
            previous = built["previous"]
            overlays = built["overlays"]
            snapshot = build_readiness_snapshot(
                reports_dir=overlays.get("reports_dir"),
                db_path=overlays.get("db_path"),
                chroma_dir=overlays.get("chroma_dir"),
            )
        finally:
            for key, value in previous.items():
                setattr(settings, key, value)
        expect = spec.get("expect", {})
        if "status" in expect and snapshot.status.value != expect["status"]:
            failures.append("status_mismatch")
        by_name = {item.name: item for item in snapshot.components}
        for name, wanted in expect.get("components", {}).items():
            actual = by_name.get(name)
            if (
                actual is None
                or actual.status.value != wanted[0]
                or actual.reason_code != wanted[1]
            ):
                failures.append("component_mismatch")
                break
    return failures


def _check_runbook_route(spec: dict[str, Any]) -> list[str]:
    actual = RUNBOOK_ROUTES.get(spec.get("reason_code", ""))
    if actual != spec.get("expect_route"):
        return ["route_mismatch"]
    return []


_CHECKERS = {
    "emit_accepted": _check_emit_accepted,
    "emit_rejected": _check_emit_rejected,
    "sanitize": _check_sanitize,
    "readiness": _check_readiness,
    "runbook_route": _check_runbook_route,
}


def _score_example(example: dict[str, Any]) -> OpsExampleScore:
    for key in ("example_id", "slice", "checks"):
        if key not in example:
            raise OpsEvaluationError(f"Fixture example is missing '{key}'.")
    if example["slice"] not in _KNOWN_SLICES:
        raise OpsEvaluationError(f"Unknown fixture slice '{example['slice']}'.")
    if not isinstance(example["checks"], list):
        raise OpsEvaluationError("Fixture example 'checks' must be a list.")
    failures: list[str] = []
    for check in example["checks"]:
        checker = _CHECKERS.get(check.get("check", ""))
        if checker is None:
            raise OpsEvaluationError(
                f"Unknown fixture check '{check.get('check', '')}'."
            )
        failures.extend(checker(check))
    return OpsExampleScore(
        example_id=example["example_id"],
        slice=example["slice"],
        failures=tuple(failures),
    )


def _build_gates(
    examples: list[dict[str, Any]], scores: list[OpsExampleScore]
) -> list[OpsGateScore]:
    by_id = {item.example_id: item for item in scores}
    gates = []
    for name in _GATE_NAMES:
        relevant = [example for example in examples if example["slice"] == name]
        events = sum(len(by_id[example["example_id"]].failures) for example in relevant)
        gates.append(
            OpsGateScore(
                gate=name,
                applicable=bool(relevant),
                passed=events == 0 if relevant else True,
                events=events,
            )
        )
    return gates


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Operational Readiness Evaluation `{payload['dataset_id']}`",
        "",
        f"Result: **{payload['result_state']}**",
        "",
        "## Gates",
        "",
        "| Gate | Applicable | Passed | Events |",
        "| --- | --- | --- | --- |",
    ]
    for gate in payload["gates"]:
        lines.append(
            f"| {gate['gate']} | {gate['applicable']} | {gate['passed']} "
            f"| {gate['events']} |"
        )
    lines += [
        "",
        "## Examples",
        "",
        "| Example | Slice | Failures |",
        "| --- | --- | --- |",
    ]
    for item in payload["per_example"]:
        failures = ", ".join(item["failures"]) or "-"
        lines.append(f"| {item['example_id']} | {item['slice']} | {failures} |")
    lines.append("")
    return "\n".join(lines)


def _invalid_result(dataset_id: str, output_dir: Optional[Path] = None) -> OpsReport:
    report = OpsReport(
        dataset_id=dataset_id,
        dataset_version="unknown",
        result_state=OpsResultState.INVALID,
        eligible_examples=0,
        gates=tuple(
            OpsGateScore(gate=name, applicable=False, passed=False)
            for name in _GATE_NAMES
        ),
        per_example=(),
    )
    if output_dir is not None:
        _write_reports(report, output_dir)
    return report


def _write_reports(report: OpsReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    (output_dir / f"{report.dataset_id}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output_dir / f"{report.dataset_id}.md").write_text(
        _render_markdown(payload), encoding="utf-8"
    )


def _load_manifest(manifest_path: Path) -> tuple[str, str, Path]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OpsEvaluationError(
            f"Cannot read ops fixture manifest at '{manifest_path}'."
        ) from error
    for key in ("dataset_id", "dataset_version", "examples_file"):
        if key not in manifest:
            raise OpsEvaluationError(f"Ops fixture manifest is missing '{key}'.")
    return (
        manifest["dataset_id"],
        manifest["dataset_version"],
        manifest_path.parent / manifest["examples_file"],
    )


def _load_examples(examples_path: Path) -> list[dict[str, Any]]:
    try:
        lines = examples_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise OpsEvaluationError(
            f"Cannot read ops fixture examples at '{examples_path}'."
        ) from error
    examples = []
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            examples.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise OpsEvaluationError(
                f"Ops fixture line {lineno} is not valid JSON."
            ) from error
    return examples


def run_readiness_evaluation(
    manifest_path: Path | str, output_dir: Path | str
) -> OpsReport:
    """Replay one ops suite and write JSON plus Markdown reports."""
    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    try:
        dataset_id, dataset_version, examples_path = _load_manifest(manifest_path)
        examples = _load_examples(examples_path)
    except OpsEvaluationError:
        return _invalid_result(manifest_path.stem, output_dir)
    if not examples:
        report = OpsReport(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            result_state=OpsResultState.INCONCLUSIVE,
            eligible_examples=0,
            gates=tuple(
                OpsGateScore(gate=name, applicable=False, passed=True)
                for name in _GATE_NAMES
            ),
            per_example=(),
        )
        _write_reports(report, output_dir)
        return report
    try:
        scores = [_score_example(example) for example in examples]
    except OpsEvaluationError:
        return _invalid_result(dataset_id, output_dir)
    gates = _build_gates(examples, scores)
    failed = any(score.failures for score in scores)
    report = OpsReport(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        result_state=(OpsResultState.FAIL if failed else OpsResultState.PASS),
        eligible_examples=len(examples),
        gates=tuple(gates),
        per_example=tuple(scores),
    )
    _write_reports(report, output_dir)
    return report
