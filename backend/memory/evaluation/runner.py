"""Deterministic R5 shadow memory evaluation runner.

The runner replays every fixture example end to end through the real
workspace, conversation, memory, extraction, and policy implementations
against an isolated temporary database: one synthetic workspace and
conversation per example, message appends with fixture trace visibility, one
`evaluation`-triggered extraction run, and candidate listing for comparison.

Comparison is multiset matching over `(scope, type, status, reason)` tuples,
so ordering never affects a score. Reports carry identifiers, counts, metric
values, gate evidence, and controlled failure labels only — never message
content, candidate text, or evidence summaries.

Quality thresholds follow the memory evaluation protocol: extraction
precision `>= 0.95` overall and `>= 0.90` on every exercised mandatory
slice, extraction recall `>= 0.90`, scope accuracy `>= 0.98`. Any applicable
hard-gate event forces `FAIL` and cannot be averaged away. An empty but
valid fixture yields `INCONCLUSIVE`; malformed fixture evidence yields
`INVALID`.
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from backend.conversations.models import (
    ConversationCreate,
    MessageRole,
    MessageSource,
    TraceVisibility,
)
from backend.conversations.service import ConversationService
from backend.conversations.sqlite_repository import SQLiteConversationRepository
from backend.memory.evaluation.models import (
    ExampleScore,
    HardGateScore,
    MemoryEvaluationReport,
    MemoryEvaluationResult,
    MetricScore,
    SliceScore,
    report_to_dict,
)
from backend.memory.extraction import (
    EXTRACTOR_ID,
    SECRET_PATTERNS,
    RuleBasedMemoryExtractor,
)
from backend.memory.models import MemoryExtractionTrigger
from backend.memory.policy import POLICY_ID, MemoryPolicy
from backend.memory.service import MemoryService
from backend.memory.sqlite_repository import SQLiteMemoryRepository
from backend.workspaces.models import (
    PlanningStatus,
    RetentionState,
    TripWorkspace,
    generate_workspace_id,
)
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

logger = logging.getLogger("travel_agent_memory_evaluation")

PRECISION_THRESHOLD = 0.95
RECALL_THRESHOLD = 0.90
SCOPE_THRESHOLD = 0.98
SLICE_PRECISION_THRESHOLD = 0.90

_REQUIRED_MANIFEST_KEYS = (
    "dataset_id",
    "dataset_version",
    "dataset_role",
    "examples_file",
)
_REQUIRED_MESSAGE_KEYS = ("role", "source", "trace_visibility", "content")
_REQUIRED_EXPECTED_KEYS = ("scope", "type", "status", "reason")


class MemoryEvaluationError(Exception):
    """The evaluation fixture or harness failed before scoring.

    Messages carry file names and key names only, never fixture content.
    """


def decide_result_state(
    *,
    invalid_examples: int,
    hard_gate_events: int,
    precision: float | None,
    recall: float | None,
    scope_accuracy: float | None,
    slice_precisions: Sequence[float | None],
) -> MemoryEvaluationResult:
    """Apply the protocol's result-state rules to computed evidence."""
    if invalid_examples > 0:
        return MemoryEvaluationResult.INVALID
    if hard_gate_events > 0:
        return MemoryEvaluationResult.FAIL
    if precision is None or recall is None:
        return MemoryEvaluationResult.INCONCLUSIVE
    if precision < PRECISION_THRESHOLD or recall < RECALL_THRESHOLD:
        return MemoryEvaluationResult.FAIL
    if scope_accuracy is not None and scope_accuracy < SCOPE_THRESHOLD:
        return MemoryEvaluationResult.FAIL
    exercised = [value for value in slice_precisions if value is not None]
    if any(value < SLICE_PRECISION_THRESHOLD for value in exercised):
        return MemoryEvaluationResult.FAIL
    return MemoryEvaluationResult.PASS


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def count_workspace_leaks(candidates, workspace_id: str, conversation_id: str) -> int:
    """Count candidates scoped outside the example they were extracted from.

    The check reads stored provenance identifiers, so a future service
    scoping regression would surface here even though no current fixture can
    produce such a row through the honest path.
    """
    return sum(
        1
        for item in candidates
        if item.workspace_id != workspace_id or item.conversation_id != conversation_id
    )


def count_secret_promotions(candidates) -> int:
    """Count accepted candidates whose text still matches a secret shape.

    The scan reads persisted candidate content with the extractor's
    secret-like patterns instead of trusting the sensitivity label, so a
    mislabeled draft cannot blind this gate.
    """
    return sum(
        1
        for item in candidates
        if item.status.value == "accepted"
        and any(pattern.search(item.text or "") for pattern in SECRET_PATTERNS)
    )


def run_shadow_evaluation(
    manifest_path: str | Path, output_dir: str | Path
) -> MemoryEvaluationReport:
    """Replay the shadow fixture, write JSON and Markdown reports, and return."""
    manifest_file = Path(manifest_path)
    out_dir = Path(output_dir)
    manifest = _load_manifest(manifest_file)
    raw_examples = _load_examples(manifest_file.parent, manifest)

    parsed = [_parse_example(index, raw) for index, raw in enumerate(raw_examples)]
    invalid = [item for item in parsed if item is None]
    valid = [item for item in parsed if item is not None]

    started = datetime.now(timezone.utc)
    report_id = f"{manifest['dataset_id']}-{started.strftime('%Y%m%dT%H%M%SZ')}"
    if invalid:
        report = MemoryEvaluationReport(
            report_id=report_id,
            dataset_id=str(manifest["dataset_id"]),
            dataset_version=str(manifest["dataset_version"]),
            dataset_role=str(manifest["dataset_role"]),
            extractor_id=EXTRACTOR_ID,
            policy_id=POLICY_ID,
            eligible_examples=len(valid),
            invalid_examples=len(invalid),
            skipped_examples=0,
            extraction_precision=MetricScore(
                "extraction_precision", None, 0, 0, f">= {PRECISION_THRESHOLD}"
            ),
            extraction_recall=MetricScore(
                "extraction_recall", None, 0, 0, f">= {RECALL_THRESHOLD}"
            ),
            scope_accuracy=MetricScore(
                "scope_accuracy", None, 0, 0, f">= {SCOPE_THRESHOLD}"
            ),
            result_state=MemoryEvaluationResult.INVALID,
            notes=(
                "Fixture evidence is missing or malformed; quality cannot be "
                "interpreted. Invalid example positions are not disclosed "
                "with content.",
            ),
        )
        _write_reports(out_dir, report)
        return report

    with tempfile.TemporaryDirectory(prefix="r5-shadow-eval-") as tmp:
        stores = _open_stores(Path(tmp) / "eval.sqlite3")
        example_scores, gate_events = _score_examples(stores, valid)

    report = _build_report(report_id, manifest, valid, example_scores, gate_events)
    _write_reports(out_dir, report)
    return report


def _load_manifest(manifest_file: Path) -> Mapping[str, Any]:
    try:
        raw = manifest_file.read_text(encoding="utf-8")
    except OSError as error:
        raise MemoryEvaluationError(
            f"Cannot read the evaluation manifest at '{manifest_file}'."
        ) from error
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as error:
        raise MemoryEvaluationError(
            f"The evaluation manifest at '{manifest_file}' is not valid JSON."
        ) from error
    if not isinstance(manifest, dict):
        raise MemoryEvaluationError(
            f"The evaluation manifest at '{manifest_file}' must be an object."
        )
    missing = [key for key in _REQUIRED_MANIFEST_KEYS if key not in manifest]
    if missing:
        raise MemoryEvaluationError(
            f"The evaluation manifest at '{manifest_file}' is missing keys: "
            f"{sorted(missing)}."
        )
    return manifest


def _load_examples(manifest_dir: Path, manifest: Mapping[str, Any]) -> list[Any]:
    examples_file = manifest_dir / str(manifest["examples_file"])
    try:
        lines = examples_file.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise MemoryEvaluationError(
            f"Cannot read the evaluation examples at '{examples_file}'."
        ) from error
    records = []
    for position, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise MemoryEvaluationError(
                f"Evaluation example line {position} at '{examples_file}' "
                "is not valid JSON."
            ) from error
    return records


def _parse_example(index: int, raw: Any) -> dict[str, Any] | None:
    """Validate one fixture example without retaining its content on failure."""
    if not isinstance(raw, dict):
        return None
    if not isinstance(raw.get("example_id"), str) or not raw["example_id"].strip():
        return None
    if not isinstance(raw.get("slice"), str) or not raw["slice"].strip():
        return None
    messages = raw.get("messages")
    expected = raw.get("expected")
    if not isinstance(messages, list) or not messages:
        return None
    if not isinstance(expected, list) or not expected:
        return None
    for message in messages:
        if not isinstance(message, dict):
            return None
        if any(key not in message for key in _REQUIRED_MESSAGE_KEYS):
            return None
        if not isinstance(message["content"], str) or not message["content"].strip():
            return None
        try:
            MessageRole(message["role"])
            MessageSource(message["source"])
            TraceVisibility(message["trace_visibility"])
        except ValueError:
            return None
    for item in expected:
        if not isinstance(item, dict):
            return None
        if any(key not in item for key in _REQUIRED_EXPECTED_KEYS):
            return None
    return {
        "example_id": raw["example_id"],
        "slice": raw["slice"],
        "messages": messages,
        "expected": expected,
    }


def _open_stores(db_path: Path) -> dict[str, Any]:
    workspaces = SQLiteWorkspaceRepository(db_path=db_path)
    conversations = SQLiteConversationRepository(db_path=db_path)
    memory = SQLiteMemoryRepository(db_path=db_path)
    return {
        "workspaces": workspaces,
        "conversations": conversations,
        "memory": memory,
        "conversation_service": ConversationService(
            conversation_repository=conversations,
            workspace_repository=workspaces,
        ),
        "memory_service": MemoryService(
            memory_repository=memory,
            conversation_repository=conversations,
            workspace_repository=workspaces,
            extractor=RuleBasedMemoryExtractor(),
            policy=MemoryPolicy(),
        ),
    }


def _score_examples(
    stores: dict[str, Any], examples: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Replay examples and count hard-gate events without keeping content."""
    scored = []
    gates = {
        "cross_workspace_leakage": 0,
        "secret_durable_promotion": 0,
    }
    for example in examples:
        workspace_id = (
            stores["workspaces"]
            .create(
                TripWorkspace(
                    workspace_id=generate_workspace_id(),
                    owner_user_id="eval-fixture",
                    title=f"fixture-{example['example_id']}",
                    destination_scope=None,
                    date_window=None,
                    planning_status=PlanningStatus.IDEA,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    retention_state=RetentionState.ACTIVE,
                )
            )
            .workspace_id
        )
        conversation_id = (
            stores["conversation_service"]
            .create_conversation(
                ConversationCreate(workspace_id=workspace_id, title=None)
            )
            .conversation_id
        )
        for message in example["messages"]:
            stores["conversation_service"].append_message(
                conversation_id=conversation_id,
                role=MessageRole(message["role"]),
                content=message["content"],
                source=MessageSource(message["source"]),
                trace_visibility=TraceVisibility(message["trace_visibility"]),
            )
        run = stores["memory_service"].run_conversation_extraction(
            workspace_id, conversation_id, MemoryExtractionTrigger.EVALUATION
        )
        candidates = stores["memory_service"].list_candidates(
            workspace_id, conversation_id, run.run_id
        )
        actual = [
            (
                item.proposed_scope.value,
                item.proposed_type.value,
                item.status.value,
                item.reason.value,
            )
            for item in candidates
        ]
        expected = [
            (item["scope"], item["type"], item["status"], item["reason"])
            for item in example["expected"]
        ]
        matches = sum((Counter(actual) & Counter(expected)).values())
        gates["cross_workspace_leakage"] += count_workspace_leaks(
            candidates, workspace_id, conversation_id
        )
        gates["secret_durable_promotion"] += count_secret_promotions(candidates)
        scored.append(
            {
                "example_id": example["example_id"],
                "slice": example["slice"],
                "expected": expected,
                "actual": actual,
                "matched": matches,
            }
        )
    _attach_failures(scored)
    return scored, gates


def _attach_failures(scored: list[dict[str, Any]]) -> None:
    for item in scored:
        missing = Counter(item["expected"]) - Counter(item["actual"])
        extra = Counter(item["actual"]) - Counter(item["expected"])
        item["failures"] = tuple(
            ["memory_missed"] * sum(missing.values())
            + ["memory_false_write"] * sum(extra.values())
        )


def _build_report(
    report_id: str,
    manifest: Mapping[str, Any],
    examples: list[dict[str, Any]],
    scored: list[dict[str, Any]],
    gates: dict[str, int],
) -> MemoryEvaluationReport:
    actual_total = sum(len(item["actual"]) for item in scored)
    expected_total = sum(len(item["expected"]) for item in scored)
    matched_total = sum(item["matched"] for item in scored)
    precision = _ratio(matched_total, actual_total)
    recall = _ratio(matched_total, expected_total)

    scope_matches = 0
    scope_denominator = 0
    for item in scored:
        if not item["expected"]:
            continue
        expected_scopes = Counter(entry[0] for entry in item["expected"])
        actual_scopes = Counter(entry[0] for entry in item["actual"])
        scope_matches += sum((actual_scopes & expected_scopes).values())
        scope_denominator += len(item["actual"])
    scope_accuracy = _ratio(scope_matches, scope_denominator)

    slices: list[SliceScore] = []
    by_slice: dict[str, list[dict[str, Any]]] = {}
    for item in scored:
        by_slice.setdefault(item["slice"], []).append(item)
    for name in sorted(by_slice):
        group = by_slice[name]
        group_actual = sum(len(item["actual"]) for item in group)
        group_expected = sum(len(item["expected"]) for item in group)
        group_matched = sum(item["matched"] for item in group)
        slices.append(
            SliceScore(
                slice=name,
                eligible_examples=len(group),
                actual=group_actual,
                expected=group_expected,
                matched=group_matched,
                precision=_ratio(group_matched, group_actual),
            )
        )

    hard_gates = (
        HardGateScore(
            "cross_workspace_leakage",
            gates["cross_workspace_leakage"],
            True,
            gates["cross_workspace_leakage"] == 0,
        ),
        HardGateScore(
            "secret_durable_promotion",
            gates["secret_durable_promotion"],
            True,
            gates["secret_durable_promotion"] == 0,
        ),
        HardGateScore("correction_precedence", 0, False, True),
        HardGateScore("deleted_memory_retrieval", 0, False, True),
        HardGateScore("cross_user_leakage", 0, False, True),
    )
    gate_events = sum(item.events for item in hard_gates if item.applicable)
    result_state = decide_result_state(
        invalid_examples=0,
        hard_gate_events=gate_events,
        precision=precision,
        recall=recall,
        scope_accuracy=scope_accuracy if scope_denominator > 0 else None,
        slice_precisions=[item.precision for item in slices],
    )
    return MemoryEvaluationReport(
        report_id=report_id,
        dataset_id=str(manifest["dataset_id"]),
        dataset_version=str(manifest["dataset_version"]),
        dataset_role=str(manifest["dataset_role"]),
        extractor_id=EXTRACTOR_ID,
        policy_id=POLICY_ID,
        eligible_examples=len(examples),
        invalid_examples=0,
        skipped_examples=0,
        extraction_precision=MetricScore(
            "extraction_precision",
            precision,
            matched_total,
            actual_total,
            f">= {PRECISION_THRESHOLD}",
        ),
        extraction_recall=MetricScore(
            "extraction_recall",
            recall,
            matched_total,
            expected_total,
            f">= {RECALL_THRESHOLD}",
        ),
        scope_accuracy=MetricScore(
            "scope_accuracy",
            scope_accuracy,
            scope_matches,
            scope_denominator,
            f">= {SCOPE_THRESHOLD}",
        ),
        slices=tuple(slices),
        hard_gates=hard_gates,
        examples=tuple(
            ExampleScore(
                example_id=item["example_id"],
                slice=item["slice"],
                expected_total=len(item["expected"]),
                actual_total=len(item["actual"]),
                matched=item["matched"],
                failures=item["failures"],
            )
            for item in scored
        ),
        result_state=result_state,
        notes=(
            "R5 shadow report: candidates are measured but never used in "
            "answers. Promotion precision, retrieval, and personalization "
            "metrics are not applicable and carry no values here.",
            "Cross-user and deleted-memory gates are not applicable: R5 has "
            "no user identity, no deletion path, and no memory retrieval.",
            "Correction precedence is not applicable as a hard-gate event: "
            "R5 keeps no competing memory store, so no older inference can "
            "override a correction at retrieval time. Correction "
            "classification is measured in the correction slice instead.",
            "The secret gate scans accepted candidate content with the "
            "secret-like patterns rather than trusting the sensitivity "
            "label.",
        ),
    )


def _report_stem(dataset_id: str) -> str:
    """Derive report file names from the dataset identity.

    A second dataset evaluated into the same directory must not silently
    overwrite the R5 report, so file names follow the manifest instead of a
    hard-coded stem.
    """
    stem = "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in dataset_id.strip()
    )
    return stem or "memory-shadow-report"


def _write_reports(out_dir: Path, report: MemoryEvaluationReport) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = report_to_dict(report)
    stem = _report_stem(report.dataset_id)
    (out_dir / f"{stem}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / f"{stem}.md").write_text(_render_markdown(report), encoding="utf-8")
    logger.info(
        "memory.evaluation reported result_state=%s eligible=%s",
        report.result_state.value,
        report.eligible_examples,
    )


def _render_markdown(report: MemoryEvaluationReport) -> str:
    lines = [
        "# R5 Shadow Memory Evaluation Report",
        "",
        f"- Report: `{report.report_id}`",
        f"- Dataset: `{report.dataset_id}` v{report.dataset_version} "
        f"({report.dataset_role})",
        f"- Extractor: `{report.extractor_id}`; Policy: `{report.policy_id}`",
        f"- Eligible examples: {report.eligible_examples}; "
        f"invalid: {report.invalid_examples}; "
        f"skipped: {report.skipped_examples}",
        f"- Result: **{report.result_state.value}**",
        "",
        "## Metrics",
        "",
        "| Metric | Value | Matched / Total | Threshold |",
        "| --- | --- | --- | --- |",
    ]
    for metric in (
        report.extraction_precision,
        report.extraction_recall,
        report.scope_accuracy,
    ):
        value = "n/a" if metric.value is None else f"{metric.value:.4f}"
        lines.append(
            f"| {metric.name} | {value} | "
            f"{metric.numerator} / {metric.denominator} | {metric.threshold} |"
        )
    lines += [
        "",
        "## Hard Gates",
        "",
        "| Gate | Events | Applicable | Passed |",
        "| --- | --- | --- | --- |",
    ]
    for gate in report.hard_gates:
        lines.append(
            f"| {gate.gate} | {gate.events} | "
            f"{'yes' if gate.applicable else 'no'} | "
            f"{'yes' if gate.passed else 'no'} |"
        )
    lines += [
        "",
        "## Mandatory Slices",
        "",
        "| Slice | Examples | Matched / Actual | Precision |",
        "| --- | --- | --- | --- |",
    ]
    for item in report.slices:
        precision = "n/a" if item.precision is None else f"{item.precision:.4f}"
        lines.append(
            f"| {item.slice} | {item.eligible_examples} | "
            f"{item.matched} / {item.actual} | {precision} |"
        )
    lines += [
        "",
        "## Per-example Evidence",
        "",
        "| Example | Slice | Matched / Expected / Actual | Failures |",
        "| --- | --- | --- | --- |",
    ]
    for item in report.examples:
        failures = ", ".join(item.failures) if item.failures else "—"
        lines.append(
            f"| `{item.example_id}` | {item.slice} | "
            f"{item.matched} / {item.expected_total} / {item.actual_total} | "
            f"{failures} |"
        )
    lines += ["", "## Notes", ""]
    lines += [f"- {note}" for note in report.notes]
    lines.append("")
    return "\n".join(lines)
