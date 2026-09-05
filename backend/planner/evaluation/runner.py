"""Deterministic R7 planner state evaluation runner.

The runner replays every fixture example end to end through the real
planner service and SQLite adapter against an isolated temporary database:
one synthetic workspace pair per example, planner writes through
`PlannerService`, chat-persistence activity through `ConversationService`,
and gate comparison against the example's expected evidence.

Comparison never carries raw content: reports hold identifiers, gate
evidence, and controlled failure labels only. Result states follow the D5
vocabulary without creating a canonical D5 planner protocol: `PASS` when
every gate holds, `FAIL` on any gate failure, `INCONCLUSIVE` for an empty
but valid suite, and `INVALID` for malformed fixture evidence.

The runner never calls a model provider, RAG retrieval, Chroma, memory, or
orchestration. Turn-level chat isolation is proven by the
`test_chat_planner_isolation` integration test; the harness gate covers
chat-persistence activity through message appends.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.conversations.models import (
    ConversationCreate,
    MessageRole,
    MessageSource,
    TraceVisibility,
)
from backend.conversations.service import ConversationService
from backend.conversations.sqlite_repository import SQLiteConversationRepository
from backend.planner.evaluation.models import (
    PlannerEvaluationError,
    PlannerExampleScore,
    PlannerGateScore,
    PlannerResultState,
    PlannerStateReport,
)
from backend.planner.models import (
    DecisionStatus,
    DecisionType,
    ItineraryItem,
    ItineraryItemType,
    ItineraryStatus,
    ItineraryVersion,
    TripDecision,
    generate_decision_id,
    generate_itinerary_version_id,
)
from backend.planner.repository import PlannerNotFoundError
from backend.planner.service import PlannerService
from backend.planner.sqlite_repository import SQLitePlannerRepository
from backend.workspaces.models import (
    PlanningStatus,
    RetentionState,
    TripWorkspace,
    generate_workspace_id,
)
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

_KNOWN_SLICES = frozenset(
    {
        "itinerary_versioning",
        "decision_lifecycle",
        "rejected_option_preservation",
        "cross_workspace_isolation",
        "operation_traceability",
        "chat_isolation",
    }
)

_GATE_NAMES = (
    "version_continuity",
    "single_accepted",
    "rejected_preservation",
    "cross_workspace_isolation",
    "operation_traceability",
    "no_implicit_chat_writes",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stores(db_path: Path) -> dict[str, Any]:
    planner = SQLitePlannerRepository(db_path=db_path)
    conversations = SQLiteConversationRepository(db_path=db_path)
    workspaces = SQLiteWorkspaceRepository(db_path=db_path)
    return {
        "planner": planner,
        "service": PlannerService(planner, workspaces, conversations),
        "conversation_service": ConversationService(conversations, workspaces),
    }


def _seed_workspace(workspaces: SQLiteWorkspaceRepository) -> str:
    moment = _utc_now()
    return workspaces.create(
        TripWorkspace(
            workspace_id=generate_workspace_id(),
            owner_user_id="local-user",
            title="Evaluation trip",
            destination_scope=None,
            date_window=None,
            planning_status=PlanningStatus.IDEA,
            created_at=moment,
            updated_at=moment,
            retention_state=RetentionState.ACTIVE,
        )
    ).workspace_id


class _ExampleContext:
    """Per-example stores, workspaces, and created-record references."""

    def __init__(self, db_path: Path) -> None:
        stores = _stores(db_path)
        self.service: PlannerService = stores["service"]
        self.conversations: ConversationService = stores["conversation_service"]
        workspaces: SQLiteWorkspaceRepository = SQLiteWorkspaceRepository(
            db_path=db_path
        )
        # Reuse the same database handle the service was built on.
        self.workspace_a = _seed_workspace(workspaces)
        self.workspace_b = _seed_workspace(workspaces)
        self.conversation_ids: dict[str, str] = {}
        self.versions: list[str] = []
        self.decisions: list[str] = []
        self.denied = 0
        self.failures: list[str] = []

    def conversation(self, workspace_id: str) -> str:
        if workspace_id not in self.conversation_ids:
            self.conversation_ids[workspace_id] = (
                self.conversations.create_conversation(
                    ConversationCreate(workspace_id=workspace_id, title=None)
                ).conversation_id
            )
        return self.conversation_ids[workspace_id]


def _build_item(payload: dict[str, Any]) -> ItineraryItem:
    return ItineraryItem(
        day_index=payload["day_index"],
        position=payload["position"],
        item_type=ItineraryItemType(payload["item_type"]),
        title=payload["title"],
        location=payload.get("location"),
        start_time=payload.get("start_time"),
        end_time=payload.get("end_time"),
        notes=payload.get("notes"),
        source_decision_ids=tuple(payload.get("source_decision_ids") or ()),
    )


def _run_action(ctx: _ExampleContext, action: dict[str, Any]) -> None:
    """Execute one fixture action, recording denials and failures."""
    op = action.get("op")
    service = ctx.service
    if op == "create_itinerary":
        stored = service.create_itinerary_version(
            ctx.workspace_a,
            ItineraryVersion(
                itinerary_version_id=generate_itinerary_version_id(),
                workspace_id=ctx.workspace_a,
                version_number=1,
                status=ItineraryStatus(action.get("status", "draft")),
                title=action.get("title"),
                summary=action.get("summary"),
                items=tuple(_build_item(item) for item in action.get("items", [])),
                created_at=_utc_now(),
            ),
        )
        ctx.versions.append(stored.itinerary_version_id)
    elif op == "accept_itinerary":
        stored = service.accept_itinerary_version(
            ctx.workspace_a, ctx.versions[action["version_ref"]]
        )
        ctx.versions[action["version_ref"]] = stored.itinerary_version_id
    elif op == "archive_itinerary":
        service.archive_itinerary_version(
            ctx.workspace_a, ctx.versions[action["version_ref"]]
        )
    elif op == "record_decision":
        supersedes_ref = action.get("supersedes_decision_ref")
        stored = service.record_decision(
            ctx.workspace_a,
            TripDecision(
                decision_id=generate_decision_id(),
                workspace_id=ctx.workspace_a,
                decision_type=DecisionType(action.get("decision_type", "preference")),
                status=DecisionStatus(action.get("status", "pending")),
                statement=action["statement"],
                rationale=action.get("rationale"),
                supersedes_decision_id=(
                    None if supersedes_ref is None else ctx.decisions[supersedes_ref]
                ),
                created_at=_utc_now(),
                updated_at=_utc_now(),
            ),
        )
        ctx.decisions.append(stored.decision_id)
    elif op == "update_decision":
        service.update_decision_status(
            ctx.workspace_a,
            ctx.decisions[action["decision_ref"]],
            DecisionStatus(action["status"]),
        )
    elif op == "append_message":
        ctx.conversations.append_message(
            conversation_id=ctx.conversation(ctx.workspace_a),
            role=MessageRole.USER,
            content=action["content"],
            source=MessageSource.UI,
            trace_visibility=TraceVisibility.INCLUDED,
        )
    elif op in (
        "get_itinerary_cross",
        "accept_itinerary_cross",
        "get_decision_cross",
    ):
        if op == "get_decision_cross":
            # The service exposes no single-decision fetch, so isolation
            # means the decision never appears in the other workspace list.
            ref = ctx.decisions[action["decision_ref"]]
            visible = [
                item.decision_id for item in service.list_decisions(ctx.workspace_b)
            ]
            if ref in visible:
                ctx.failures.append("cross_workspace_leak")
            else:
                ctx.denied += 1
            return
        ref = ctx.versions[action["version_ref"]]
        try:
            if op == "get_itinerary_cross":
                service.get_itinerary_version(ctx.workspace_b, ref)
            else:
                service.accept_itinerary_version(ctx.workspace_b, ref)
        except PlannerNotFoundError:
            ctx.denied += 1
            return
        if action.get("expect_denied"):
            ctx.failures.append("denied_not_raised")
        else:
            ctx.failures.append("unexpected_denial")
    else:
        raise PlannerEvaluationError(f"Unknown fixture action '{op}'.")


def _check_example(
    ctx: _ExampleContext, example: dict[str, Any]
) -> PlannerExampleScore:
    """Compare fresh reads against the example's expected evidence."""
    expected = example.get("expected", {})
    service = ctx.service
    if "version_numbers" in expected:
        actual = [
            service.get_itinerary_version(ctx.workspace_a, version_id).version_number
            for version_id in ctx.versions
        ]
        if actual != list(expected["version_numbers"]):
            ctx.failures.append("version_numbers_mismatch")
    if "statuses" in expected:
        actual_statuses: dict[str, str] = {}
        for index, version_id in enumerate(ctx.versions):
            actual_statuses[f"v{index}"] = service.get_itinerary_version(
                ctx.workspace_a, version_id
            ).status.value
        listed = {
            item.decision_id: item.status.value
            for item in service.list_decisions(ctx.workspace_a)
        }
        for index, decision_id in enumerate(ctx.decisions):
            actual_statuses[f"d{index}"] = listed[decision_id]
        for key, value in expected["statuses"].items():
            if actual_statuses.get(key) != value:
                ctx.failures.append("status_mismatch")
                break
    if "operations" in expected:
        actual = [
            item.operation_type.value
            for item in service.list_operations(ctx.workspace_a)
        ]
        if actual != list(expected["operations"]):
            ctx.failures.append("operations_mismatch")
    if "denied" in expected:
        if ctx.denied != expected["denied"]:
            ctx.failures.append("denied_mismatch")
    if "rejected_listable" in expected:
        actual = len(
            service.list_decisions(ctx.workspace_a, status=DecisionStatus.REJECTED)
        )
        if actual != expected["rejected_listable"]:
            ctx.failures.append("rejected_mismatch")
    if "planner_rows" in expected:
        total = sum(
            len(service.list_itinerary_versions(workspace_id))
            + len(service.list_decisions(workspace_id))
            + len(service.list_operations(workspace_id))
            for workspace_id in (ctx.workspace_a, ctx.workspace_b)
        )
        if total != expected["planner_rows"]:
            ctx.failures.append("planner_rows_written")
    return PlannerExampleScore(
        example_id=example["example_id"],
        slice=example["slice"],
        failures=tuple(ctx.failures),
    )


def _score_example(example: dict[str, Any]) -> PlannerExampleScore:
    for key in ("example_id", "slice", "actions"):
        if key not in example:
            raise PlannerEvaluationError(f"Fixture example is missing '{key}'.")
    if example["slice"] not in _KNOWN_SLICES:
        raise PlannerEvaluationError(f"Unknown fixture slice '{example['slice']}'.")
    if not isinstance(example["actions"], list):
        raise PlannerEvaluationError("Fixture example 'actions' must be a list.")
    with tempfile.TemporaryDirectory(prefix="r7-state-") as tmp:
        ctx = _ExampleContext(Path(tmp) / "eval.sqlite3")
        try:
            for action in example["actions"]:
                _run_action(ctx, action)
        except PlannerEvaluationError:
            raise
        except Exception as error:
            ctx.failures.append("action_error")
            return PlannerExampleScore(
                example_id=example["example_id"],
                slice=example["slice"],
                failures=tuple(ctx.failures),
            )
        return _check_example(ctx, example)


def _build_gates(
    examples: list[dict[str, Any]], scores: list[PlannerExampleScore]
) -> list[PlannerGateScore]:
    """Aggregate per-example failures into the six spec gates."""
    by_id = {item.example_id: item for item in scores}

    def failures_for(predicate) -> int:
        return sum(
            len(by_id[example["example_id"]].failures)
            for example in examples
            if predicate(example)
        )

    def applicable(predicate) -> bool:
        return any(predicate(example) for example in examples)

    versioning = lambda example: example["slice"] == "itinerary_versioning"  # noqa: E731
    declares_statuses = lambda example: "statuses" in example.get("expected", {})  # noqa: E731
    rejected = lambda example: example["slice"] == "rejected_option_preservation"  # noqa: E731
    isolation = lambda example: example["slice"] == "cross_workspace_isolation"  # noqa: E731
    declares_ops = lambda example: "operations" in example.get("expected", {})  # noqa: E731
    chat = lambda example: example["slice"] == "chat_isolation"  # noqa: E731

    specs = [
        ("version_continuity", versioning, "version_numbers_mismatch"),
        ("single_accepted", declares_statuses, "status_mismatch"),
        ("rejected_preservation", rejected, "rejected_mismatch"),
        (
            "cross_workspace_isolation",
            isolation,
            (
                "denied_mismatch",
                "denied_not_raised",
                "unexpected_denial",
                "cross_workspace_leak",
            ),
        ),
        ("operation_traceability", declares_ops, "operations_mismatch"),
        ("no_implicit_chat_writes", chat, "planner_rows_written"),
    ]
    gates = []
    for name, predicate, markers in specs:
        events = failures_for(predicate)
        is_applicable = applicable(predicate)
        gates.append(
            PlannerGateScore(
                gate=name,
                applicable=is_applicable,
                passed=events == 0 if is_applicable else True,
                events=events,
            )
        )
    return gates


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Planner State Evaluation `{payload['dataset_id']}`",
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


def _invalid_result(
    dataset_id: str, output_dir: Optional[Path] = None
) -> PlannerStateReport:
    report = PlannerStateReport(
        dataset_id=dataset_id,
        dataset_version="unknown",
        result_state=PlannerResultState.INVALID,
        eligible_examples=0,
        gates=tuple(
            PlannerGateScore(gate=name, applicable=False, passed=False)
            for name in _GATE_NAMES
        ),
        per_example=(),
    )
    if output_dir is not None:
        _write_reports(report, output_dir)
    return report


def _write_reports(report: PlannerStateReport, output_dir: Path) -> None:
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
        raise PlannerEvaluationError(
            f"Cannot read planner fixture manifest at '{manifest_path}'."
        ) from error
    for key in ("dataset_id", "dataset_version", "examples_file"):
        if key not in manifest:
            raise PlannerEvaluationError(
                f"Planner fixture manifest is missing '{key}'."
            )
    return (
        manifest["dataset_id"],
        manifest["dataset_version"],
        manifest_path.parent / manifest["examples_file"],
    )


def _load_examples(examples_path: Path) -> list[dict[str, Any]]:
    try:
        lines = examples_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise PlannerEvaluationError(
            f"Cannot read planner fixture examples at '{examples_path}'."
        ) from error
    examples = []
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            examples.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise PlannerEvaluationError(
                f"Planner fixture line {lineno} is not valid JSON."
            ) from error
    return examples


def run_state_evaluation(
    manifest_path: Path | str, output_dir: Path | str
) -> PlannerStateReport:
    """Replay one planner suite and write JSON plus Markdown reports."""
    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    try:
        dataset_id, dataset_version, examples_path = _load_manifest(manifest_path)
        examples = _load_examples(examples_path)
    except PlannerEvaluationError:
        return _invalid_result(manifest_path.stem, output_dir)
    if not examples:
        report = PlannerStateReport(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            result_state=PlannerResultState.INCONCLUSIVE,
            eligible_examples=0,
            gates=tuple(
                PlannerGateScore(gate=name, applicable=False, passed=True)
                for name in _GATE_NAMES
            ),
            per_example=(),
        )
        _write_reports(report, output_dir)
        return report
    try:
        scores = [_score_example(example) for example in examples]
    except PlannerEvaluationError:
        return _invalid_result(dataset_id, output_dir)
    gates = _build_gates(examples, scores)
    failed = any(score.failures for score in scores)
    report = PlannerStateReport(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        result_state=(PlannerResultState.FAIL if failed else PlannerResultState.PASS),
        eligible_examples=len(examples),
        gates=tuple(gates),
        per_example=tuple(scores),
    )
    _write_reports(report, output_dir)
    return report
