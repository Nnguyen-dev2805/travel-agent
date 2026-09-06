"""Deterministic R9 security/privacy evaluation runner.

The runner replays synthetic scenarios against isolated temporary
databases through the real FastAPI routes and services with a synthetic
two-owner token registry. Every example builds a fresh client, seeds its
own state, and restores global dependency and settings overrides, so
examples never share state and ambient configuration cannot leak in.

Gate events count successful violations only: a denied request is
passing evidence. Token-leakage scanning covers response bodies and the
log records emitted while each example replays, plus the written
reports. The report is `PASS` when every gate holds, `FAIL` on
any event or failure, `INCONCLUSIVE` for an empty but valid suite, and
`INVALID` when authentication cannot be enabled, the registry is
invalid, or fixture evidence is malformed.

The runner never touches real credentials, real user data, model
providers, Chroma collection creation, embeddings, or the network.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi.testclient import TestClient

from backend.app.api.chat import get_conversation_orchestrator
from backend.app.api.conversations import get_conversation_service
from backend.app.api.memory import get_memory_service
from backend.app.api.planner import get_planner_service
from backend.app.api.workspaces import get_deletion_service, get_workspace_service
from backend.app.config import settings
from backend.app.main import app
from backend.conversations.models import ConversationCreate
from backend.conversations.service import ConversationService
from backend.conversations.sqlite_repository import SQLiteConversationRepository
from backend.memory.retrieval import MemoryRetrievalService
from backend.memory.service import MemoryService
from backend.memory.sqlite_repository import SQLiteMemoryRepository
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator
from backend.planner.service import PlannerService
from backend.planner.sqlite_repository import SQLitePlannerRepository
from backend.privacy.deletion import DeletionService
from backend.security.authorization import get_workspace_repository
from backend.security.evaluation.models import (
    SecurityEvaluationError,
    SecurityExampleScore,
    SecurityGateScore,
    SecurityReport,
    SecurityResultState,
)
from backend.security.local_tokens import parse_local_token_registry
from backend.security.models import SecurityConfigurationError
from backend.workspaces.models import WorkspaceCreate
from backend.workspaces.service import WorkspaceService
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

_KNOWN_SLICES = frozenset(
    {
        "authentication",
        "cross_owner",
        "deletion",
        "error_hardening",
        "privacy",
    }
)

_GATE_NAMES = (
    "unauthenticated_access",
    "invalid_token_access",
    "cross_owner_access",
    "deleted_memory_retrieval",
    "raw_500_leakage",
    "token_leakage",
    "oversized_request_accepted",
)

_GATE_SLICES = {
    "unauthenticated_access": ("authentication",),
    "invalid_token_access": ("authentication",),
    "cross_owner_access": ("cross_owner",),
    "deleted_memory_retrieval": ("deletion",),
    "raw_500_leakage": ("error_hardening",),
    "token_leakage": ("privacy",),
    "oversized_request_accepted": ("error_hardening",),
}

_OVERRIDDEN_DEPENDENCIES = (
    get_workspace_service,
    get_conversation_service,
    get_memory_service,
    get_planner_service,
    get_deletion_service,
    get_workspace_repository,
    get_conversation_orchestrator,
)


def _auth_gate_problem() -> str | None:
    """Check the auth gate without running examples.

    Returns a report note describing the problem, or None when
    authenticated evidence can be observed.
    """
    if not settings.AUTH_REQUIRED:
        return (
            "Security evidence requires AUTH_REQUIRED=true; the gate was "
            "off, so protected behavior is unobservable."
        )
    try:
        registry = parse_local_token_registry(
            settings.LOCAL_AUTH_TOKENS_JSON.get_secret_value()
        )
    except SecurityConfigurationError:
        return (
            "Security evidence requires a valid synthetic token registry; "
            "the registry was missing or malformed."
        )
    if not registry:
        return "Security evidence requires a non-empty token registry."
    return None


def _registry() -> dict[str, str]:
    return parse_local_token_registry(
        settings.LOCAL_AUTH_TOKENS_JSON.get_secret_value()
    )


class _SilentRAG:
    """RAG double that must never be reached by denied turns."""

    def generate_answer(self, message, top_k=None):
        raise AssertionError("denied turns must never generate")

    def build_travel_context(self, message, top_k=None):
        raise AssertionError("denied turns must never retrieve")

    def generate_from_context(self, message, bundle):
        raise AssertionError("denied turns must never generate")


class _ExampleContext:
    """Isolated client, stores, and evidence pool for one example."""

    def __init__(self, db_path: Path, tokens: dict[str, str]) -> None:
        self.db_path = db_path
        self.tokens = tokens
        self.bodies: list[str] = []
        self._saved_overrides = dict(app.dependency_overrides)
        app.dependency_overrides[get_workspace_service] = lambda: WorkspaceService(
            repository=SQLiteWorkspaceRepository(db_path=db_path)
        )
        app.dependency_overrides[get_conversation_service] = lambda: (
            ConversationService(
                conversation_repository=SQLiteConversationRepository(db_path=db_path),
                workspace_repository=SQLiteWorkspaceRepository(db_path=db_path),
            )
        )
        app.dependency_overrides[get_memory_service] = lambda: MemoryService(
            memory_repository=SQLiteMemoryRepository(db_path=db_path),
            conversation_repository=SQLiteConversationRepository(db_path=db_path),
            workspace_repository=SQLiteWorkspaceRepository(db_path=db_path),
        )
        app.dependency_overrides[get_planner_service] = lambda: PlannerService(
            planner_repository=SQLitePlannerRepository(db_path=db_path),
            workspace_repository=SQLiteWorkspaceRepository(db_path=db_path),
            conversation_repository=SQLiteConversationRepository(db_path=db_path),
        )
        app.dependency_overrides[get_deletion_service] = lambda: DeletionService(
            workspace_repository=SQLiteWorkspaceRepository(db_path=db_path),
            conversation_repository=SQLiteConversationRepository(db_path=db_path),
            memory_repository=SQLiteMemoryRepository(db_path=db_path),
        )
        app.dependency_overrides[get_workspace_repository] = lambda: (
            SQLiteWorkspaceRepository(db_path=db_path)
        )
        conversation_service = ConversationService(
            SQLiteConversationRepository(db_path=db_path),
            SQLiteWorkspaceRepository(db_path=db_path),
        )
        app.dependency_overrides[get_conversation_orchestrator] = lambda: (
            ConversationOrchestrator(
                rag_service=_SilentRAG(),
                conversation_service_provider=lambda: conversation_service,
            )
        )
        self.client = TestClient(app, raise_server_exceptions=False)
        self.workspaces = SQLiteWorkspaceRepository(db_path=db_path)
        self.conversations = SQLiteConversationRepository(db_path=db_path)
        self.memory = SQLiteMemoryRepository(db_path=db_path)

    def close(self) -> None:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self._saved_overrides)

    def headers(self, owner: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[owner]}"}

    def call(self, method: str, path: str, owner: str | None, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if owner is not None:
            headers.update(self.headers(owner))
        response = self.client.request(method, path, headers=headers, **kwargs)
        self.bodies.append(response.text)
        return response

    def seed_workspace(self, owner: str, title: str = "Evaluation trip") -> str:
        service = WorkspaceService(repository=self.workspaces)
        return service.create_workspace(
            WorkspaceCreate(owner_user_id=owner, title=title)
        ).workspace_id

    def seed_conversation(self, workspace_id: str) -> str:
        service = ConversationService(self.conversations, self.workspaces)
        return service.create_conversation(
            ConversationCreate(workspace_id=workspace_id, title=None)
        ).conversation_id


def _scenario_missing_token_denied(ctx: _ExampleContext) -> dict[str, int]:
    events = {"unauthenticated_access": 0}
    failures: list[str] = []
    first = ctx.call("GET", "/api/v1/ops/readiness", None)
    second = ctx.call(
        "GET", "/api/v1/workspaces", None, params={"owner_user_id": "owner_a"}
    )
    for response in (first, second):
        if response.status_code != 401:
            events["unauthenticated_access"] += 1
            failures.append("unauthenticated_allowed")
    return {"events": events, "failures": failures}


def _scenario_invalid_token_denied(ctx: _ExampleContext) -> dict[str, int]:
    events = {"invalid_token_access": 0}
    failures: list[str] = []
    response = ctx.client.get(
        "/api/v1/ops/readiness", headers={"Authorization": "Bearer invalid-token"}
    )
    ctx.bodies.append(response.text)
    if response.status_code != 401:
        events["invalid_token_access"] += 1
        failures.append("invalid_token_allowed")
    return {"events": events, "failures": failures}


def _scenario_cross_owner_workspace_denied(ctx: _ExampleContext) -> dict[str, int]:
    events = {"cross_owner_access": 0}
    failures: list[str] = []
    workspace_b = ctx.seed_workspace("owner_b")
    response = ctx.call("GET", f"/api/v1/workspaces/{workspace_b}", "owner_a")
    if response.status_code != 404:
        events["cross_owner_access"] += 1
        failures.append("cross_owner_allowed")
    return {"events": events, "failures": failures}


def _scenario_cross_owner_conversation_denied(
    ctx: _ExampleContext,
) -> dict[str, int]:
    events = {"cross_owner_access": 0}
    failures: list[str] = []
    workspace_b = ctx.seed_workspace("owner_b")
    conversation_b = ctx.seed_conversation(workspace_b)
    response = ctx.call("GET", f"/api/v1/conversations/{conversation_b}", "owner_a")
    if response.status_code != 404:
        events["cross_owner_access"] += 1
        failures.append("cross_owner_allowed")
    return {"events": events, "failures": failures}


def _scenario_cross_owner_memory_denied(ctx: _ExampleContext) -> dict[str, int]:
    events = {"cross_owner_access": 0}
    failures: list[str] = []
    workspace_a = ctx.seed_workspace("owner_a")
    workspace_b = ctx.seed_workspace("owner_b")
    conversation_b = ctx.seed_conversation(workspace_b)
    response = ctx.call(
        "GET", f"/api/v1/workspaces/{workspace_b}/memory/extractions", "owner_a"
    )
    if response.status_code != 404:
        events["cross_owner_access"] += 1
        failures.append("cross_owner_allowed")
    child = ctx.call(
        "GET",
        f"/api/v1/workspaces/{workspace_a}/memory/extractions",
        "owner_a",
        params={"conversation_id": conversation_b},
    )
    if child.status_code != 404:
        events["cross_owner_access"] += 1
        failures.append("cross_owner_child_allowed")
    return {"events": events, "failures": failures}


def _scenario_cross_owner_planner_denied(ctx: _ExampleContext) -> dict[str, int]:
    events = {"cross_owner_access": 0}
    failures: list[str] = []
    workspace_b = ctx.seed_workspace("owner_b")
    response = ctx.call(
        "GET",
        f"/api/v1/workspaces/{workspace_b}/planner/itineraries",
        "owner_a",
    )
    if response.status_code != 404:
        events["cross_owner_access"] += 1
        failures.append("cross_owner_allowed")
    return {"events": events, "failures": failures}


def _scenario_deleted_memory_not_selected(ctx: _ExampleContext) -> dict[str, int]:
    from backend.conversations.models import (
        MessageRole,
        MessageSource,
        TraceVisibility,
    )

    events = {"deleted_memory_retrieval": 0}
    failures: list[str] = []
    workspace_id = ctx.seed_workspace("owner_a")
    conversation_id = ctx.seed_conversation(workspace_id)
    service = ConversationService(ctx.conversations, ctx.workspaces)
    service.append_message(
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content="Tôi ăn chay trường, hãy nhớ giúp tôi.",
        source=MessageSource.UI,
        trace_visibility=TraceVisibility.INCLUDED,
    )
    memory = MemoryService(ctx.memory, ctx.conversations, ctx.workspaces)
    memory.run_conversation_extraction(workspace_id, conversation_id, "manual")
    promoted = memory.promote_workspace(workspace_id, conversation_id)
    if promoted.promoted_count < 1:
        return {"events": events, "failures": ["promotion_empty"]}
    deletion = DeletionService(ctx.workspaces, ctx.conversations, ctx.memory)
    deletion.request_workspace_deletion(workspace_id)
    deletion.confirm_workspace_deletion(workspace_id)
    retrieval = MemoryRetrievalService(ctx.memory)
    selected = retrieval.select_memories(
        owner_user_id="owner_a",
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        query="ăn chay",
    )
    events["deleted_memory_retrieval"] += len(selected)
    if selected:
        failures.append("deleted_memory_selected")
    return {"events": events, "failures": failures}


def _scenario_deleted_workspace_rejects_writes(
    ctx: _ExampleContext,
) -> dict[str, int]:
    events = {"deleted_memory_retrieval": 0}
    failures: list[str] = []
    workspace_id = ctx.seed_workspace("owner_a")
    conversation_id = ctx.seed_conversation(workspace_id)
    created = ctx.call(
        "POST",
        f"/api/v1/workspaces/{workspace_id}/deletion-requests",
        "owner_a",
        json={},
    )
    confirmed = ctx.call(
        "POST",
        f"/api/v1/workspaces/{workspace_id}/deletion-confirmations",
        "owner_a",
        json={},
    )
    if created.status_code != 201 or confirmed.status_code != 200:
        return {"events": events, "failures": ["deletion_flow_failed"]}
    probes = [
        ("POST", f"/api/v1/workspaces/{workspace_id}/conversations", {}),
        (
            "POST",
            f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/memory/extractions",
            {},
        ),
        ("POST", f"/api/v1/workspaces/{workspace_id}/memory/promotions", {}),
        (
            "POST",
            f"/api/v1/workspaces/{workspace_id}/planner/itineraries",
            {"title": "Sneaky", "items": []},
        ),
        (
            "POST",
            "/api/v1/chat",
            {"message": "hi", "conversation_id": conversation_id},
        ),
    ]
    for method, path, payload in probes:
        response = ctx.call(method, path, "owner_a", json=payload)
        if response.status_code != 404:
            events["deleted_memory_retrieval"] += 1
            failures.append("deleted_workspace_write_allowed")
    return {"events": events, "failures": failures}


def _scenario_raw_500_detail_redacted(ctx: _ExampleContext) -> dict[str, int]:
    from backend.app.api.workspaces import get_workspace_service

    events = {"raw_500_leakage": 0}
    failures: list[str] = []

    def _exploding_service():
        raise RuntimeError("NEVER_LOG_HARNESS_SECRET")

    previous = app.dependency_overrides.get(get_workspace_service)
    app.dependency_overrides[get_workspace_service] = _exploding_service
    try:
        response = ctx.call(
            "GET", "/api/v1/workspaces", "owner_a", params={"owner_user_id": "x"}
        )
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_workspace_service, None)
        else:
            app.dependency_overrides[get_workspace_service] = previous
    body = response.json()
    if response.status_code != 500:
        failures.append("expected_500")
    elif body.get("detail") != "Internal server error.":
        events["raw_500_leakage"] += 1
        failures.append("raw_500_detail")
    elif not str(body.get("request_id", "")).startswith("rq_"):
        failures.append("missing_request_id")
    if "NEVER_LOG_HARNESS_SECRET" in response.text:
        events["raw_500_leakage"] += 1
        failures.append("raw_500_detail")
    return {"events": events, "failures": failures}


def _scenario_oversized_request_denied(ctx: _ExampleContext) -> dict[str, int]:
    from backend.app.config import settings

    events = {"oversized_request_accepted": 0}
    failures: list[str] = []
    previous = settings.MAX_REQUEST_BODY_BYTES
    settings.MAX_REQUEST_BODY_BYTES = 64
    try:
        response = ctx.call(
            "POST",
            "/api/v1/workspaces",
            "owner_a",
            json={"owner_user_id": "owner_a", "title": "x" * 5000},
        )
    finally:
        settings.MAX_REQUEST_BODY_BYTES = previous
    if response.status_code != 413:
        events["oversized_request_accepted"] += 1
        failures.append("oversized_request_allowed")
    return {"events": events, "failures": failures}


def _scenario_token_value_not_reported(ctx: _ExampleContext) -> dict[str, int]:
    events = {"token_leakage": 0}
    failures: list[str] = []
    workspace_id = ctx.seed_workspace("owner_a")
    first = ctx.call("GET", f"/api/v1/workspaces/{workspace_id}", "owner_a")
    second = ctx.call(
        "GET",
        "/api/v1/ops/readiness",
        "owner_a",
    )
    if first.status_code != 200 or second.status_code != 200:
        failures.append("setup_request_failed")
    for text in ctx.bodies:
        for token in ctx.tokens.values():
            if token in text:
                events["token_leakage"] += 1
                failures.append("token_leaked")
                break
    return {"events": events, "failures": failures}


def _scenario_auth_disabled_report_invalid(ctx: _ExampleContext) -> dict[str, int]:
    from backend.app.config import settings

    failures: list[str] = []
    previous = settings.AUTH_REQUIRED
    settings.AUTH_REQUIRED = False
    try:
        problem = _auth_gate_problem()
    finally:
        settings.AUTH_REQUIRED = previous
    if problem is None:
        failures.append("auth_gate_not_enforced")
    return {"events": {}, "failures": failures}


_SCENARIOS = {
    "missing_token_denied": _scenario_missing_token_denied,
    "invalid_token_denied": _scenario_invalid_token_denied,
    "cross_owner_workspace_denied": _scenario_cross_owner_workspace_denied,
    "cross_owner_conversation_denied": _scenario_cross_owner_conversation_denied,
    "cross_owner_memory_denied": _scenario_cross_owner_memory_denied,
    "cross_owner_planner_denied": _scenario_cross_owner_planner_denied,
    "deleted_memory_not_selected": _scenario_deleted_memory_not_selected,
    "deleted_workspace_rejects_writes": _scenario_deleted_workspace_rejects_writes,
    "raw_500_detail_redacted": _scenario_raw_500_detail_redacted,
    "oversized_request_denied": _scenario_oversized_request_denied,
    "token_value_not_reported": _scenario_token_value_not_reported,
    "auth_disabled_report_invalid": _scenario_auth_disabled_report_invalid,
}


class _LogCapture(logging.Handler):
    """Collect formatted log records emitted while one example replays.

    The token-leakage gate scans these alongside response bodies, so the
    report covers emitted logs instead of claiming unobserved coverage.
    """

    def __init__(self) -> None:
        super().__init__(level=0)
        self.texts: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.texts.append(self.format(record))
        except Exception:  # pragma: no cover - capture must not break scoring
            pass


def _score_example(
    example: dict[str, Any], tokens: dict[str, str], base_dir: Path, position: int
) -> tuple[SecurityExampleScore, dict[str, int], list[str]]:
    scenario = _SCENARIOS.get(example.get("scenario", ""))
    if scenario is None:
        raise SecurityEvaluationError(
            f"Unknown security scenario '{example.get('scenario', '')}'."
        )
    db_path = base_dir / f"example-{position}.sqlite3"
    ctx = _ExampleContext(db_path, tokens)
    capture = _LogCapture()
    capture.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_logger.addHandler(capture)
    root_logger.setLevel(logging.DEBUG)
    try:
        outcome = scenario(ctx)
    finally:
        root_logger.removeHandler(capture)
        root_logger.setLevel(previous_level)
        ctx.close()
    events = {name: 0 for name in _GATE_NAMES}
    for name, count in outcome["events"].items():
        events[name] = events.get(name, 0) + count
    bodies = list(ctx.bodies) + list(capture.texts)
    return (
        SecurityExampleScore(
            example_id=example["example_id"],
            slice=example["slice"],
            failures=tuple(outcome["failures"]),
        ),
        events,
        bodies,
    )


def _build_gates(
    examples: list[dict[str, Any]],
    scores: list[SecurityExampleScore],
    gate_events: dict[str, int],
) -> list[SecurityGateScore]:
    by_id = {item.example_id: item for item in scores}
    gates = []
    for name in _GATE_NAMES:
        relevant = [
            example for example in examples if example["slice"] in _GATE_SLICES[name]
        ]
        failures = sum(
            len(by_id[example["example_id"]].failures) for example in relevant
        )
        events = gate_events.get(name, 0)
        applicable = bool(relevant) or name == "token_leakage"
        gates.append(
            SecurityGateScore(
                gate=name,
                applicable=applicable,
                passed=(events == 0 and failures == 0) if applicable else True,
                events=events,
            )
        )
    return gates


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Security and Privacy Evaluation `{payload['dataset_id']}`",
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
) -> SecurityReport:
    report = SecurityReport(
        dataset_id=dataset_id,
        dataset_version="unknown",
        result_state=SecurityResultState.INVALID,
        eligible_examples=0,
        gates=tuple(
            SecurityGateScore(gate=name, applicable=False, passed=False)
            for name in _GATE_NAMES
        ),
        per_example=(),
    )
    if output_dir is not None:
        _write_reports(report, output_dir)
    return report


def _write_reports(report: SecurityReport, output_dir: Path) -> None:
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
        raise SecurityEvaluationError(
            f"Cannot read security fixture manifest at '{manifest_path}'."
        ) from error
    for key in ("dataset_id", "dataset_version", "examples_file"):
        if key not in manifest:
            raise SecurityEvaluationError(
                f"Security fixture manifest is missing '{key}'."
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
        raise SecurityEvaluationError(
            f"Cannot read security fixture examples at '{examples_path}'."
        ) from error
    examples = []
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            examples.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise SecurityEvaluationError(
                f"Security fixture line {lineno} is not valid JSON."
            ) from error
    return examples


def _validate_example(index: int, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SecurityEvaluationError(f"Security fixture index {index} is invalid.")
    for key in ("example_id", "slice", "scenario"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise SecurityEvaluationError(
                f"Security fixture index {index} is missing '{key}'."
            )
    if raw["slice"] not in _KNOWN_SLICES:
        raise SecurityEvaluationError(f"Unknown security slice '{raw['slice']}'.")
    if raw["scenario"] not in _SCENARIOS:
        raise SecurityEvaluationError(f"Unknown security scenario '{raw['scenario']}'.")
    return raw


def run_security_evaluation(
    manifest_path: Path | str, output_dir: Path | str
) -> SecurityReport:
    """Replay one security suite and write JSON plus Markdown reports."""
    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    try:
        dataset_id, dataset_version, examples_path = _load_manifest(manifest_path)
        raw_examples = _load_examples(examples_path)
        examples = [
            _validate_example(index, raw) for index, raw in enumerate(raw_examples)
        ]
    except SecurityEvaluationError:
        return _invalid_result(manifest_path.stem, output_dir)
    if not examples:
        report = SecurityReport(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            result_state=SecurityResultState.INCONCLUSIVE,
            eligible_examples=0,
            gates=tuple(
                SecurityGateScore(gate=name, applicable=False, passed=True)
                for name in _GATE_NAMES
            ),
            per_example=(),
        )
        _write_reports(report, output_dir)
        return report
    problem = _auth_gate_problem()
    if problem is not None:
        return _invalid_result(dataset_id, output_dir)
    try:
        tokens = _registry()
    except SecurityConfigurationError:
        return _invalid_result(dataset_id, output_dir)
    scores: list[SecurityExampleScore] = []
    gate_events = {name: 0 for name in _GATE_NAMES}
    bodies: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="r9-security-") as raw:
            base_dir = Path(raw)
            for position, example in enumerate(examples):
                score, events, texts = _score_example(
                    example, tokens, base_dir, position
                )
                scores.append(score)
                bodies.extend(texts)
                for name, count in events.items():
                    gate_events[name] = gate_events.get(name, 0) + count
    except SecurityEvaluationError:
        return _invalid_result(dataset_id, output_dir)
    for text in bodies:
        for token in tokens.values():
            if token in text:
                gate_events["token_leakage"] = gate_events.get("token_leakage", 0) + 1
                break
    gates = _build_gates(examples, scores, gate_events)
    failed = any(score.failures for score in scores) or any(
        gate.events > 0 for gate in gates if gate.applicable
    )
    report = SecurityReport(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        result_state=(SecurityResultState.FAIL if failed else SecurityResultState.PASS),
        eligible_examples=len(examples),
        gates=tuple(gates),
        per_example=tuple(scores),
    )
    _write_reports(report, output_dir)
    return report
