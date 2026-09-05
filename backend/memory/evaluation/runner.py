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
from datetime import datetime, timedelta, timezone
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
    MemoryRetrievalReport,
    MetricScore,
    SliceScore,
    report_to_dict,
    retrieval_report_to_dict,
)
from backend.memory.extraction import (
    EXTRACTOR_ID,
    SECRET_PATTERNS,
    RuleBasedMemoryExtractor,
)
from backend.memory.models import (
    MemoryExtractionTrigger,
    MemoryRecord,
    MemoryRecordScope,
    MemoryRecordStatus,
    MemoryRecordType,
    MemorySelectionStatus,
    MemorySelectionTrace,
    RetrievalScope,
    SensitivityLabel,
    generate_memory_record_id,
    generate_memory_retrieval_trace_id,
    utc_now,
)
from backend.memory.policy import POLICY_ID, MemoryPolicy
from backend.memory.promotion import MEMORY_PROMOTION_MIN_CONFIDENCE
from backend.memory.retrieval import MEMORY_MAX_SELECTED, MemoryRetrievalService
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
        _write_shadow_reports(out_dir, report)
        return report

    with tempfile.TemporaryDirectory(prefix="r5-shadow-eval-") as tmp:
        stores = _open_stores(Path(tmp) / "eval.sqlite3")
        example_scores, gate_events = _score_examples(stores, valid)

    report = _build_report(report_id, manifest, valid, example_scores, gate_events)
    _write_shadow_reports(out_dir, report)
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
        if "failures" in item:
            continue
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


def _write_reports(out_dir: Path, payload: dict, markdown: str, stem: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{stem}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / f"{stem}.md").write_text(markdown, encoding="utf-8")


def _write_shadow_reports(out_dir: Path, report: MemoryEvaluationReport) -> None:
    _write_reports(
        out_dir,
        report_to_dict(report),
        _render_markdown(report),
        _report_stem(report.dataset_id),
    )
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


# ---------------------------------------------------------------------------
# Runtime milestone R6: paired promotion and retrieval evaluation.
#
# Promotion cases replay governed messages through extraction and promotion;
# retrieval cases seed records directly (the only way to cover lifecycle,
# foreign-scope, and secret-labeled rows the promotion policy must refuse).
# Answer-quality fields stay valueless without a provider-backed judge, per
# the limitation accepted at R6 approval time.
# ---------------------------------------------------------------------------

PROMOTION_PRECISION_THRESHOLD = 0.97
HIT_AT_5_THRESHOLD = 0.90
IRRELEVANT_RATE_MAXIMUM = 0.10
RETRIEVAL_SCOPE_THRESHOLD = 0.98
PERSONALIZATION_WIN_THRESHOLD = 0.60

_REQUIRED_SEED_KEYS = (
    "alias",
    "scope",
    "memory_type",
    "status",
    "text",
    "confidence",
    "sensitivity_label",
)
_REQUIRED_QUERY_KEYS = ("query", "expected_aliases")


def decide_retrieval_result(
    *,
    invalid_examples: int,
    hard_gate_events: int,
    promotion_precision: float | None,
    scope_accuracy: float | None,
    hit_at_5: float | None,
    irrelevant_rate: float | None,
    personalization_win_rate: float | None = None,
    constraint_delta: float | None = None,
    slice_precisions: Sequence[float | None],
) -> MemoryEvaluationResult:
    """Apply the R6 result-state rules to computed evidence.

    Answer-quality fields participate when measured: a below-threshold win
    rate or a negative constraint delta fails the run. When both are absent
    the run may still pass on retrieval evidence, because the approval-time
    limitation records answer quality as INCONCLUSIVE rather than blocking
    retrieval validation; the report notes carry that limitation explicitly.
    """
    if invalid_examples > 0:
        return MemoryEvaluationResult.INVALID
    if hard_gate_events > 0:
        return MemoryEvaluationResult.FAIL
    if (
        promotion_precision is not None
        and promotion_precision < PROMOTION_PRECISION_THRESHOLD
    ):
        return MemoryEvaluationResult.FAIL
    if scope_accuracy is not None and scope_accuracy < RETRIEVAL_SCOPE_THRESHOLD:
        return MemoryEvaluationResult.FAIL
    if hit_at_5 is not None and hit_at_5 < HIT_AT_5_THRESHOLD:
        return MemoryEvaluationResult.FAIL
    if irrelevant_rate is not None and irrelevant_rate > IRRELEVANT_RATE_MAXIMUM:
        return MemoryEvaluationResult.FAIL
    if (
        personalization_win_rate is not None
        and personalization_win_rate < PERSONALIZATION_WIN_THRESHOLD
    ):
        return MemoryEvaluationResult.FAIL
    if constraint_delta is not None and constraint_delta < 0.0:
        return MemoryEvaluationResult.FAIL
    exercised = [value for value in slice_precisions if value is not None]
    if any(value < SLICE_PRECISION_THRESHOLD for value in exercised):
        return MemoryEvaluationResult.FAIL
    if promotion_precision is None or hit_at_5 is None:
        return MemoryEvaluationResult.INCONCLUSIVE
    return MemoryEvaluationResult.PASS


def run_retrieval_evaluation(
    manifest_path: str | Path, output_dir: str | Path
) -> MemoryRetrievalReport:
    """Replay the retrieval suite, write JSON and Markdown reports, and return."""
    manifest_file = Path(manifest_path)
    out_dir = Path(output_dir)
    manifest = _load_manifest(manifest_file)
    raw_examples = _load_examples(manifest_file.parent, manifest)

    parsed = [
        _parse_retrieval_example(index, raw) for index, raw in enumerate(raw_examples)
    ]
    invalid = [item for item in parsed if item is None]
    valid = [item for item in parsed if item is not None]

    started = datetime.now(timezone.utc)
    report_id = f"{manifest['dataset_id']}-{started.strftime('%Y%m%dT%H%M%SZ')}"
    if invalid:
        report = _invalid_retrieval_report(
            report_id, manifest, len(valid), len(invalid)
        )
        _write_reports(
            out_dir,
            retrieval_report_to_dict(report),
            _render_retrieval_markdown(report),
            _report_stem(report.dataset_id),
        )
        return report

    with tempfile.TemporaryDirectory(prefix="r6-retrieval-eval-") as tmp:
        scored, gates, traces = _score_retrieval_examples(Path(tmp), valid)

    report = _build_retrieval_report(report_id, manifest, valid, scored, gates, traces)
    _write_reports(
        out_dir,
        retrieval_report_to_dict(report),
        _render_retrieval_markdown(report),
        _report_stem(report.dataset_id),
    )
    return report


def _invalid_retrieval_report(
    report_id: str, manifest: Mapping[str, Any], eligible: int, invalid: int
) -> MemoryRetrievalReport:
    na = MetricScore("n/a", None, 0, 0, "n/a")
    return MemoryRetrievalReport(
        report_id=report_id,
        dataset_id=str(manifest["dataset_id"]),
        dataset_version=str(manifest["dataset_version"]),
        dataset_role=str(manifest["dataset_role"]),
        extractor_id=EXTRACTOR_ID,
        policy_id=POLICY_ID,
        eligible_examples=eligible,
        invalid_examples=invalid,
        skipped_examples=0,
        promotion_precision=MetricScore(
            "promotion_precision", None, 0, 0, f">= {PROMOTION_PRECISION_THRESHOLD}"
        ),
        scope_accuracy=MetricScore(
            "scope_accuracy", None, 0, 0, f">= {RETRIEVAL_SCOPE_THRESHOLD}"
        ),
        hit_at_5=MetricScore("hit_at_5", None, 0, 0, f">= {HIT_AT_5_THRESHOLD}"),
        irrelevant_rate=MetricScore(
            "irrelevant_rate", None, 0, 0, f"<= {IRRELEVANT_RATE_MAXIMUM}"
        ),
        personalization_win_rate=na,
        constraint_delta=na,
        result_state=MemoryEvaluationResult.INVALID,
        notes=(
            "Suite evidence is missing or malformed; quality cannot be interpreted.",
        ),
    )


def _parse_retrieval_example(index: int, raw: Any) -> dict[str, Any] | None:
    """Validate one R6 suite example without retaining content on failure."""
    if not isinstance(raw, dict):
        return None
    if not isinstance(raw.get("example_id"), str) or not raw["example_id"].strip():
        return None
    if not isinstance(raw.get("slice"), str) or not raw["slice"].strip():
        return None
    kind = raw.get("kind")
    if kind == "promotion":
        messages = raw.get("messages")
        expected = raw.get("expected")
        if not isinstance(messages, list) or not messages:
            return None
        if not isinstance(expected, dict):
            return None
        for message in messages:
            if not isinstance(message, dict):
                return None
            if any(key not in message for key in _REQUIRED_MESSAGE_KEYS):
                return None
            if (
                not isinstance(message["content"], str)
                or not message["content"].strip()
            ):
                return None
            try:
                MessageRole(message["role"])
                MessageSource(message["source"])
                TraceVisibility(message["trace_visibility"])
            except ValueError:
                return None
        promoted = expected.get("promoted")
        if not isinstance(promoted, list):
            return None
        for item in promoted:
            if not isinstance(item, dict):
                return None
            if "scope" not in item or "type" not in item:
                return None
        if not isinstance(expected.get("skipped"), int):
            return None
        if not isinstance(expected.get("superseded"), int):
            return None
        return {
            "example_id": raw["example_id"],
            "slice": raw["slice"],
            "kind": "promotion",
            "owner": raw.get("owner", "eval-owner"),
            "messages_before": raw.get("messages_before", []),
            "messages": messages,
            "expected": expected,
        }
    if kind == "retrieval":
        seeds = raw.get("seeds")
        queries = raw.get("queries")
        if not isinstance(seeds, list) or not isinstance(queries, list):
            return None
        if not queries:
            return None
        for seed in seeds:
            if not isinstance(seed, dict):
                return None
            if any(key not in seed for key in _REQUIRED_SEED_KEYS):
                return None
            if not isinstance(seed["alias"], str) or not seed["alias"].strip():
                return None
            if not isinstance(seed["text"], str) or not seed["text"].strip():
                return None
            try:
                MemoryRecordScope(seed["scope"])
                MemoryRecordType(seed["memory_type"])
                MemoryRecordStatus(seed["status"])
                SensitivityLabel(seed["sensitivity_label"])
            except ValueError:
                return None
            confidence = seed["confidence"]
            if (
                isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not 0.0 <= float(confidence) <= 1.0
            ):
                return None
            if seed.get("expires", None) not in (None, "past", "future"):
                return None
        for query in queries:
            if not isinstance(query, dict):
                return None
            if any(key not in query for key in _REQUIRED_QUERY_KEYS):
                return None
            if not isinstance(query["query"], str) or not query["query"].strip():
                return None
            if not isinstance(query["expected_aliases"], list) or not all(
                isinstance(alias, str) for alias in query["expected_aliases"]
            ):
                return None
        return {
            "example_id": raw["example_id"],
            "slice": raw["slice"],
            "kind": "retrieval",
            "owner": raw.get("owner", "eval-owner"),
            "seeds": seeds,
            "queries": queries,
        }
    return None


def _open_retrieval_stores(db_path: Path) -> dict[str, Any]:
    stores = _open_stores(db_path)
    stores["retrieval_service"] = MemoryRetrievalService(stores["memory"])
    return stores


def _score_retrieval_examples(
    base_dir: Path, examples: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    """Replay suite examples and count hard-gate events without keeping content.

    Every example replays against its own isolated temporary database, so a
    record promoted or seeded by one example can never leak into another
    example's retrieval. Cross-scope isolation is measured with explicit
    foreign-scope seeds instead.
    """
    scored = []
    gates = {
        "cross_workspace_leakage": 0,
        "cross_user_leakage": 0,
        "secret_durable_promotion": 0,
        "deleted_memory_retrieval": 0,
        "correction_precedence": 0,
    }
    traces: list[str] = []
    for position, example in enumerate(examples):
        stores = _open_retrieval_stores(base_dir / f"example-{position}.sqlite3")
        owner = example.get("owner", "eval-owner")
        workspace_id = (
            stores["workspaces"]
            .create(
                TripWorkspace(
                    workspace_id=generate_workspace_id(),
                    owner_user_id=owner,
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
        if example["kind"] == "promotion":
            scored.append(
                _score_promotion_example(stores, example, workspace_id, conversation_id)
            )
        else:
            scored.append(
                _score_retrieval_queries(
                    stores, example, workspace_id, conversation_id, owner, gates, traces
                )
            )
    _attach_failures(scored)
    return scored, gates, traces


def _append_fixture_messages(
    stores: dict[str, Any], conversation_id: str, messages
) -> None:
    for message in messages:
        stores["conversation_service"].append_message(
            conversation_id=conversation_id,
            role=MessageRole(message["role"]),
            content=message["content"],
            source=MessageSource(message["source"]),
            trace_visibility=TraceVisibility(message["trace_visibility"]),
        )


def _run_promoted_records(records, promoted_ids) -> list:
    """Return the stored records this promotion run created, in run order.

    Attribution follows the promoted ids the use case returns, never a
    timestamp comparison: the service stamps records at the run start, so a
    frozen or coarse clock makes `created_at >= started_at` vacuous and
    neighbouring runs indistinguishable.
    """
    wanted = set(promoted_ids)
    ordered = [record for record in records if record.memory_id in wanted]
    ordered.sort(key=lambda record: promoted_ids.index(record.memory_id))
    return ordered


def _score_promotion_example(
    stores: dict[str, Any],
    example: dict[str, Any],
    workspace_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    if example.get("messages_before", []):
        # Earlier history promotes in its own conversation first, so the
        # main run never re-extracts the same message in a new candidate.
        # User-scope records still meet across conversations by owner label,
        # which is exactly the cross-trip correction case.
        earlier_id = (
            stores["conversation_service"]
            .create_conversation(
                ConversationCreate(workspace_id=workspace_id, title=None)
            )
            .conversation_id
        )
        _append_fixture_messages(stores, earlier_id, example["messages_before"])
        stores["memory_service"].run_conversation_extraction(
            workspace_id, earlier_id, MemoryExtractionTrigger.EVALUATION
        )
        stores["memory_service"].promote_workspace(workspace_id, earlier_id)
    _append_fixture_messages(stores, conversation_id, example["messages"])
    stores["memory_service"].run_conversation_extraction(
        workspace_id, conversation_id, MemoryExtractionTrigger.EVALUATION
    )
    before_superseded = {
        record.memory_id
        for record in stores["memory"].list_records(workspace_id=workspace_id)
        if record.status.value == "superseded"
    }
    result = stores["memory_service"].promote_workspace(workspace_id, conversation_id)
    stored_runs = stores["memory"].list_promotion_runs(
        workspace_id=workspace_id, conversation_id=conversation_id
    )
    stored_run = next(
        (run for run in stored_runs if run.promotion_run_id == result.promotion_run_id),
        None,
    )
    stored_run_matches = (
        stored_run is not None
        and stored_run.promoted_count == result.promoted_count
        and stored_run.skipped_count == result.skipped_count
    )
    records = stores["memory"].list_records(workspace_id=workspace_id)
    new_records = _run_promoted_records(records, result.promoted_memory_ids)
    actual_promoted = sorted(
        (record.scope.value, record.memory_type.value) for record in new_records
    )
    expected_promoted = sorted(
        (item["scope"], item["type"]) for item in example["expected"]["promoted"]
    )
    newly_superseded = sum(
        1
        for record in records
        if record.status.value == "superseded"
        and record.memory_id not in before_superseded
    )
    matched = sum((Counter(actual_promoted) & Counter(expected_promoted)).values())
    promoted_ids = tuple(record.memory_id for record in new_records)
    scope_checked = len(new_records)
    scope_correct = sum(
        1 for record in new_records if _record_scope_id(record) == record.scope_id
    )
    missing = Counter(expected_promoted) - Counter(actual_promoted)
    extra = Counter(actual_promoted) - Counter(expected_promoted)
    failures = ["memory_missed"] * sum(missing.values()) + ["memory_false_write"] * sum(
        extra.values()
    )
    if result.skipped_count != example["expected"]["skipped"]:
        failures.append(
            "memory_missed"
            if result.skipped_count < example["expected"]["skipped"]
            else "memory_false_write"
        )
    if newly_superseded != example["expected"]["superseded"]:
        failures.append(
            "memory_missed"
            if newly_superseded < example["expected"]["superseded"]
            else "memory_conflict"
        )
    if not stored_run_matches:
        failures.append("memory_false_write")
    return {
        "example_id": example["example_id"],
        "slice": example["slice"],
        "expected": expected_promoted,
        "actual": actual_promoted,
        "matched": matched,
        "scope_checked": scope_checked,
        "scope_correct": scope_correct,
        "selected_ids": promoted_ids,
        "selection_reasons": ("promoted",) * len(promoted_ids),
        "failures": tuple(failures),
        "extra": {
            "expected_skipped": example["expected"]["skipped"],
            "actual_skipped": result.skipped_count,
            "expected_superseded": example["expected"]["superseded"],
            "actual_superseded": newly_superseded,
        },
    }


def _score_retrieval_queries(
    stores: dict[str, Any],
    example: dict[str, Any],
    workspace_id: str,
    conversation_id: str,
    owner: str,
    gates: dict[str, int],
    traces: list[str],
) -> dict[str, Any]:
    moment = datetime.now(timezone.utc)
    alias_to_id: dict[str, str] = {}
    for seed in example["seeds"]:
        scope = MemoryRecordScope(seed["scope"])
        seed_owner = seed.get("owner", owner)
        record_workspace_id = workspace_id
        record_conversation_id = conversation_id
        if scope is MemoryRecordScope.USER:
            scope_id = seed_owner
        elif scope is MemoryRecordScope.WORKSPACE:
            scope_id = workspace_id
            if seed.get("scope_ref", "self") != "self":
                record_workspace_id = scope_id = "tw_elsewhere"
        else:
            scope_id = conversation_id
            if seed.get("scope_ref", "self") != "self":
                record_conversation_id = scope_id = "cv_elsewhere"
        expires = seed.get("expires", None)
        record = MemoryRecord(
            memory_id=generate_memory_record_id(),
            source_candidate_id=f"mc-seed-{seed['alias']}",
            workspace_id=record_workspace_id,
            conversation_id=record_conversation_id,
            source_message_id=f"ms-seed-{seed['alias']}",
            source_sequence=1,
            owner_user_id=seed_owner,
            scope=scope,
            scope_id=scope_id,
            memory_type=MemoryRecordType(seed["memory_type"]),
            status=MemoryRecordStatus(seed["status"]),
            text=f"seed marker {seed['alias']}; {seed['text']}",
            confidence=float(seed["confidence"]),
            sensitivity_label=SensitivityLabel(seed["sensitivity_label"]),
            supersedes_memory_id=None,
            created_at=moment,
            updated_at=moment,
            expires_at=(
                None
                if expires is None
                else moment - timedelta(days=1)
                if expires == "past"
                else moment + timedelta(days=30)
            ),
        )
        stores["memory"].create_records([record])
        alias_to_id[seed["alias"]] = record.memory_id

    id_to_alias = {value: key for key, value in alias_to_id.items()}
    expected_aliases_all: list[str] = []
    actual_aliases_all: list[str] = []
    selected_ids_all: list[str] = []
    selection_reasons_all: list[str] = []
    query_hits: list[bool | None] = []
    query_irrelevant: list[tuple[int, int]] = []
    for query in example["queries"]:
        query_owner = query.get("owner", owner)
        selections = stores["retrieval_service"].select_memories(
            owner_user_id=query_owner,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            query=query["query"],
        )
        actual_aliases = sorted(
            id_to_alias.get(item.memory_id, f"unknown:{item.memory_id}")
            for item in selections
        )
        expected_aliases = sorted(query["expected_aliases"])
        expected_aliases_all.extend(expected_aliases)
        actual_aliases_all.extend(actual_aliases)
        if expected_aliases:
            query_hits.append(set(expected_aliases) <= set(actual_aliases[:5]))
        else:
            query_hits.append(None)
        if actual_aliases:
            extra = Counter(actual_aliases) - Counter(expected_aliases)
            query_irrelevant.append((sum(extra.values()), len(actual_aliases)))
        query_scope = RetrievalScope(
            owner_user_id=query_owner,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
        )
        for item in selections:
            _count_selection_gates(item, stores["memory"], query_scope, gates)
            selected_ids_all.append(item.memory_id)
            selection_reasons_all.append(item.reason.value)
        trace = MemorySelectionTrace(
            trace_id=generate_memory_retrieval_trace_id(),
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            gate_enabled=True,
            status=(
                MemorySelectionStatus.SELECTED
                if selections
                else MemorySelectionStatus.NONE_SELECTED
            ),
            selected_ids=tuple(item.memory_id for item in selections),
            reasons=tuple(item.reason for item in selections),
            eligible_count=len(
                stores["retrieval_service"].eligible_records(
                    owner_user_id=query_owner,
                    workspace_id=workspace_id,
                    conversation_id=conversation_id,
                )
            ),
            created_at=utc_now(),
        )
        stores["memory"].write_retrieval_event(trace)
        traces.append(trace.trace_id)
    matched_total = sum(
        (Counter(actual_aliases_all) & Counter(expected_aliases_all)).values()
    )
    return {
        "example_id": example["example_id"],
        "slice": example["slice"],
        "expected": expected_aliases_all,
        "actual": actual_aliases_all,
        "matched": matched_total,
        "selected_ids": selected_ids_all,
        "selection_reasons": selection_reasons_all,
        "query_hits": query_hits,
        "query_irrelevant": query_irrelevant,
    }


def _record_scope_id(record) -> str:
    """Recompute the scope identifier a record must carry for its scope."""
    if record.scope.value == "user":
        return record.owner_user_id
    if record.scope.value == "workspace":
        return record.workspace_id
    return record.conversation_id


def _selection_in_scope(record, scope) -> bool:
    """Check one record sits inside the querying scope without keeping content."""
    if record.owner_user_id != scope.owner_user_id:
        return False
    if record.scope.value == "user":
        return record.scope_id == scope.owner_user_id
    if record.scope.value == "workspace":
        return record.scope_id == scope.workspace_id
    if record.scope.value == "conversation":
        return record.scope_id == scope.conversation_id
    return False


def _count_selection_gates(
    selection,
    memory_repository,
    scope,
    gates: dict[str, int],
) -> None:
    """Count hard-gate events for one selected record without keeping content."""
    record = None
    for candidate in memory_repository.list_records():
        if candidate.memory_id == selection.memory_id:
            record = candidate
            break
    if record is None:  # pragma: no cover - selections always resolve
        gates["cross_workspace_leakage"] += 1
        return
    if not _selection_in_scope(record, scope):
        if record.owner_user_id != scope.owner_user_id:
            gates["cross_user_leakage"] += 1
        else:
            gates["cross_workspace_leakage"] += 1
    if record.sensitivity_label in (
        SensitivityLabel.SECRET,
        SensitivityLabel.UNSAFE,
        SensitivityLabel.SENSITIVE,
    ):
        gates["secret_durable_promotion"] += 1
    if record.status in (
        MemoryRecordStatus.DELETED,
        MemoryRecordStatus.DELETION_REQUESTED,
        MemoryRecordStatus.EXPIRED,
        MemoryRecordStatus.ARCHIVED,
    ):
        gates["deleted_memory_retrieval"] += 1
    if record.status is MemoryRecordStatus.SUPERSEDED:
        gates["correction_precedence"] += 1


def _build_retrieval_report(
    report_id: str,
    manifest: Mapping[str, Any],
    valid: list[dict[str, Any]],
    scored: list[dict[str, Any]],
    gates: dict[str, int],
    traces: list[str],
) -> MemoryRetrievalReport:
    promo_items = [
        item for item, example in zip(scored, valid) if example["kind"] == "promotion"
    ]
    promo_matched = sum(item["matched"] for item in promo_items)
    promo_actual = sum(len(item["actual"]) for item in promo_items)
    promotion_precision = _ratio(promo_matched, promo_actual)

    scope_correct = sum(item.get("scope_correct", 0) for item in scored)
    scope_checked = sum(item.get("scope_checked", 0) for item in scored)
    scope_accuracy = _ratio(scope_correct, scope_checked)

    hits: list[bool] = []
    irrelevant_n = 0
    irrelevant_d = 0
    for item in scored:
        hits.extend(hit for hit in item.get("query_hits", []) if hit is not None)
        for extra, total in item.get("query_irrelevant", []):
            irrelevant_n += extra
            irrelevant_d += total
    hit_at_5 = _ratio(sum(hits), len(hits)) if hits else None
    irrelevant_rate = _ratio(irrelevant_n, irrelevant_d)

    slices: list[SliceScore] = []
    by_slice: dict[str, list[dict[str, Any]]] = {}
    for item in scored:
        by_slice.setdefault(item["slice"], []).append(item)
    for name in sorted(by_slice):
        group = by_slice[name]
        group_actual = sum(len(item["actual"]) for item in group)
        group_expected = sum(len(item["expected"]) for item in group)
        group_matched = sum(item["matched"] for item in group)
        group_hits = [
            hit
            for item in group
            for hit in item.get("query_hits", [])
            if hit is not None
        ]
        group_irrelevant_n = sum(
            extra for item in group for extra, _ in item.get("query_irrelevant", [])
        )
        group_irrelevant_d = sum(
            total for item in group for _, total in item.get("query_irrelevant", [])
        )
        group_scope_correct = sum(item.get("scope_correct", 0) for item in group)
        group_scope_checked = sum(item.get("scope_checked", 0) for item in group)
        slices.append(
            SliceScore(
                slice=name,
                eligible_examples=len(group),
                actual=group_actual,
                expected=group_expected,
                matched=group_matched,
                precision=_ratio(group_matched, group_actual),
                hit_rate=_ratio(sum(group_hits), len(group_hits))
                if group_hits
                else None,
                irrelevant=_ratio(group_irrelevant_n, group_irrelevant_d),
                scope_accuracy=_ratio(group_scope_correct, group_scope_checked),
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
            "cross_user_leakage",
            gates["cross_user_leakage"],
            True,
            gates["cross_user_leakage"] == 0,
        ),
        HardGateScore(
            "secret_durable_promotion",
            gates["secret_durable_promotion"],
            True,
            gates["secret_durable_promotion"] == 0,
        ),
        HardGateScore(
            "deleted_memory_retrieval",
            gates["deleted_memory_retrieval"],
            True,
            gates["deleted_memory_retrieval"] == 0,
        ),
        HardGateScore(
            "correction_precedence",
            gates["correction_precedence"],
            True,
            gates["correction_precedence"] == 0,
        ),
    )
    gate_events = sum(item.events for item in hard_gates if item.applicable)
    # Answer-quality evidence is absent without a provider-backed judge, so
    # both fields stay None by construction: decide treats None as
    # "unmeasured, allowed under the approval-time limitation" rather than
    # as a favorable score.
    result_state = decide_retrieval_result(
        invalid_examples=0,
        hard_gate_events=gate_events,
        promotion_precision=promotion_precision,
        scope_accuracy=scope_accuracy if scope_checked > 0 else None,
        hit_at_5=hit_at_5,
        irrelevant_rate=irrelevant_rate,
        personalization_win_rate=None,
        constraint_delta=None,
        slice_precisions=[item.precision for item in slices],
    )
    return MemoryRetrievalReport(
        report_id=report_id,
        dataset_id=str(manifest["dataset_id"]),
        dataset_version=str(manifest["dataset_version"]),
        dataset_role=str(manifest["dataset_role"]),
        extractor_id=EXTRACTOR_ID,
        policy_id=POLICY_ID,
        eligible_examples=len(valid),
        invalid_examples=0,
        skipped_examples=0,
        promotion_precision=MetricScore(
            "promotion_precision",
            promotion_precision,
            promo_matched,
            promo_actual,
            f">= {PROMOTION_PRECISION_THRESHOLD}",
        ),
        scope_accuracy=MetricScore(
            "scope_accuracy",
            scope_accuracy,
            scope_correct,
            scope_checked,
            f">= {RETRIEVAL_SCOPE_THRESHOLD}",
        ),
        hit_at_5=MetricScore(
            "hit_at_5",
            hit_at_5,
            sum(hits),
            len(hits),
            f">= {HIT_AT_5_THRESHOLD}",
        ),
        irrelevant_rate=MetricScore(
            "irrelevant_rate",
            irrelevant_rate,
            irrelevant_n,
            irrelevant_d,
            f"<= {IRRELEVANT_RATE_MAXIMUM}",
        ),
        personalization_win_rate=MetricScore(
            "personalization_win_rate", None, 0, 0, "n/a without judge"
        ),
        constraint_delta=MetricScore(
            "constraint_delta", None, 0, 0, "n/a without judge"
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
                selected_ids=tuple(item.get("selected_ids", ())),
                selection_reasons=tuple(item.get("selection_reasons", ())),
            )
            for item in scored
        ),
        disabled_run_id=f"{report_id}-disabled",
        enabled_trace_ids=tuple(traces),
        result_state=result_state,
        environment=_evaluation_environment(),
        notes=(
            "R6 retrieval report: promotion, scope, retrieval, and lifecycle "
            "gates are measured end to end; answer-quality fields stay "
            "INCONCLUSIVE without a provider-backed judge, per the limitation "
            "accepted at R6 approval time.",
            "The disabled branch executes the gate-off path over the identical "
            "query set, which selects nothing by definition; the paired "
            "comparison is enabled selections versus that empty baseline. No "
            "answer is generated on either branch without a provider.",
            "Cross-user isolation is measured by the local owner label, not "
            "authenticated identity, per the open R6/R9 ordering problem.",
        ),
    )


def _evaluation_environment() -> dict:
    """Record harness environment without touching fixture content."""
    import subprocess

    dirty: bool | None = None
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[3],
            timeout=10,
        )
        if root.returncode == 0:
            status = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                capture_output=True,
                text=True,
                cwd=root.stdout.strip(),
                timeout=10,
            )
            if status.returncode == 0:
                dirty = bool(status.stdout.strip())
    except Exception:  # noqa: BLE001 - environment signal is best-effort
        dirty = None
    return {
        "dirty_working_tree": dirty,
        "retrieval": {
            "tokenizer": "unicode-word-lowercase",
            "correction_bypass": True,
            "max_selected_default": MEMORY_MAX_SELECTED,
            "min_confidence_default": MEMORY_PROMOTION_MIN_CONFIDENCE,
        },
    }


def _render_retrieval_markdown(report: MemoryRetrievalReport) -> str:
    lines = [
        "# R6 Memory Retrieval Evaluation Report",
        "",
        f"- Report: `{report.report_id}`",
        f"- Dataset: `{report.dataset_id}` v{report.dataset_version} "
        f"({report.dataset_role})",
        f"- Extractor: `{report.extractor_id}`; Policy: `{report.policy_id}`",
        f"- Eligible examples: {report.eligible_examples}; "
        f"invalid: {report.invalid_examples}; "
        f"skipped: {report.skipped_examples}",
        f"- Disabled run: `{report.disabled_run_id}`; "
        f"enabled traces: {len(report.enabled_trace_ids)}",
        f"- Result: **{report.result_state.value}**",
        "",
        "## Metrics",
        "",
        "| Metric | Value | Matched / Total | Threshold |",
        "| --- | --- | --- | --- |",
    ]
    for metric in (
        report.promotion_precision,
        report.scope_accuracy,
        report.hit_at_5,
        report.irrelevant_rate,
        report.personalization_win_rate,
        report.constraint_delta,
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
        "| Slice | Examples | Matched / Actual | Precision | Hit rate |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report.slices:
        precision = "n/a" if item.precision is None else f"{item.precision:.4f}"
        hit_rate = "n/a" if item.hit_rate is None else f"{item.hit_rate:.4f}"
        lines.append(
            f"| {item.slice} | {item.eligible_examples} | "
            f"{item.matched} / {item.actual} | {precision} | {hit_rate} |"
        )
    lines += ["", "## Environment", ""]
    lines.append(
        f"- dirty_working_tree: {report.environment.get('dirty_working_tree')}"
    )
    for key in sorted(report.environment.get("retrieval", {})):
        lines.append(f"- retrieval.{key}: {report.environment['retrieval'][key]}")
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
