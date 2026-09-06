"""Read-only local readiness probes for milestone R8.

Every probe inspects local metadata without creating state: missing
databases stay missing, Chroma directories are only existence-checked,
and no provider is ever called. A dependency that cannot be inspected
safely reports `unknown` instead of pretending success. This module may
import domain adapters for expected schema versions, but it never calls a
constructor that creates databases, directories, or collections.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

from backend.app.config import settings
from backend.observability.events import emit_event
from backend.observability.models import (
    EventComponent,
    EventName,
    EventResult,
    ReadinessComponent,
    ReadinessSnapshot,
    ReadinessStatus,
)
from backend.storage.schema_registry import SENTINEL_USER_VERSION

logger = logging.getLogger("travel_agent_observability")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CHROMA_DIR = _REPO_ROOT / "data" / "chromadb"
_DEFAULT_REPORTS_DIR = Path("docs/reports")

_RESULT_STATES = frozenset({"PASS", "FAIL", "INCONCLUSIVE", "INVALID"})


def expected_schema_modules() -> dict[str, int]:
    """Return the schema versions this build understands, without opening state."""
    from backend.conversations.sqlite_repository import (
        SCHEMA_MODULE as CONVERSATIONS_MODULE,
    )
    from backend.conversations.sqlite_repository import (
        SCHEMA_VERSION as CONVERSATIONS_VERSION,
    )
    from backend.memory.sqlite_repository import (
        RECORDS_SCHEMA_MODULE,
        RECORDS_SCHEMA_VERSION,
        SCHEMA_MODULE as MEMORY_MODULE,
    )
    from backend.memory.sqlite_repository import (
        SCHEMA_VERSION as MEMORY_VERSION,
    )
    from backend.planner.sqlite_repository import (
        PLANNER_SCHEMA_MODULE,
        PLANNER_SCHEMA_VERSION,
    )
    from backend.workspaces.sqlite_repository import (
        SCHEMA_MODULE as WORKSPACES_MODULE,
    )
    from backend.workspaces.sqlite_repository import (
        SCHEMA_VERSION as WORKSPACES_VERSION,
    )

    return {
        WORKSPACES_MODULE: WORKSPACES_VERSION,
        CONVERSATIONS_MODULE: CONVERSATIONS_VERSION,
        MEMORY_MODULE: MEMORY_VERSION,
        RECORDS_SCHEMA_MODULE: RECORDS_SCHEMA_VERSION,
        PLANNER_SCHEMA_MODULE: PLANNER_SCHEMA_VERSION,
    }


def _utc_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _probe_app() -> ReadinessComponent:
    return ReadinessComponent(
        name="app",
        status=ReadinessStatus.READY,
        reason_code="ok",
        details={"version": settings.VERSION},
    )


def _probe_model_provider() -> ReadinessComponent:
    token = (settings.GITHUB_TOKEN or "").strip()
    if token:
        return ReadinessComponent(
            name="model_provider",
            status=ReadinessStatus.READY,
            reason_code="ok",
            details={"model": settings.LLM_MODEL},
        )
    return ReadinessComponent(
        name="model_provider",
        status=ReadinessStatus.NOT_READY,
        reason_code="credential_missing",
        details={"model": settings.LLM_MODEL},
    )


def _probe_rag_chroma(chroma_dir: Optional[Path]) -> ReadinessComponent:
    path = Path(chroma_dir) if chroma_dir is not None else _DEFAULT_CHROMA_DIR
    if path.exists():
        return ReadinessComponent(
            name="rag_chroma",
            status=ReadinessStatus.READY,
            reason_code="path_present",
            details={"present": True},
        )
    return ReadinessComponent(
        name="rag_chroma",
        status=ReadinessStatus.UNKNOWN,
        reason_code="path_missing",
        details={"present": False},
    )


def _read_schema_versions(db_path: Path) -> dict[str, int]:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        marker = connection.execute("PRAGMA user_version").fetchone()[0]
        if int(marker) != SENTINEL_USER_VERSION:
            raise _MarkerMismatch(int(marker))
        rows = connection.execute(
            "SELECT module, version FROM schema_versions"
        ).fetchall()
        return {str(module): int(version) for module, version in rows}
    finally:
        connection.close()


class _MarkerMismatch(Exception):
    def __init__(self, observed: int) -> None:
        super().__init__(observed)
        self.observed = observed


def _probe_app_db(db_path: Optional[Path]) -> ReadinessComponent:
    path = Path(db_path) if db_path is not None else Path(settings.APP_DB_PATH)
    if not path.exists():
        return ReadinessComponent(
            name="app_db",
            status=ReadinessStatus.UNKNOWN,
            reason_code="database_missing",
            details={"present": False},
        )
    try:
        recorded = _read_schema_versions(path)
    except _MarkerMismatch:
        return ReadinessComponent(
            name="app_db",
            status=ReadinessStatus.NOT_READY,
            reason_code="store_marker_mismatch",
            details={"present": True, "compatible": False},
        )
    except sqlite3.Error:
        return ReadinessComponent(
            name="app_db",
            status=ReadinessStatus.UNKNOWN,
            reason_code="schema_registry_missing",
            details={"present": True, "compatible": False},
        )
    expected = expected_schema_modules()
    for module, version in expected.items():
        if recorded.get(module) != version:
            return ReadinessComponent(
                name="app_db",
                status=ReadinessStatus.NOT_READY,
                reason_code="schema_incompatible",
                details={"present": True, "compatible": False, "module": module},
            )
    return ReadinessComponent(
        name="app_db",
        status=ReadinessStatus.READY,
        reason_code="ok",
        details={"present": True, "compatible": True},
    )


def _read_report_state(reports_dir: Path, area: str) -> str:
    area_dir = reports_dir / area
    try:
        candidates = sorted(area_dir.glob("*.json"))
    except OSError:
        return "missing"
    for candidate in reversed(candidates):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        state = payload.get("result_state")
        if state in _RESULT_STATES:
            return str(state)
    return "missing"


def _probe_memory(reports_dir: Path) -> ReadinessComponent:
    enabled = bool(settings.MEMORY_RETRIEVAL_ENABLED)
    report = _read_report_state(reports_dir, "memory")
    if enabled:
        return ReadinessComponent(
            name="memory",
            status=ReadinessStatus.READY,
            reason_code="ok",
            details={"enabled": True, "report": report},
        )
    return ReadinessComponent(
        name="memory",
        status=ReadinessStatus.DEGRADED,
        reason_code="memory_retrieval_disabled",
        details={"enabled": False, "report": report},
    )


def _probe_planner(reports_dir: Path) -> ReadinessComponent:
    available = importlib.util.find_spec("backend.planner") is not None
    report = _read_report_state(reports_dir, "planner")
    if available:
        return ReadinessComponent(
            name="planner",
            status=ReadinessStatus.READY,
            reason_code="ok",
            details={"available": True, "report": report},
        )
    return ReadinessComponent(
        name="planner",
        status=ReadinessStatus.UNKNOWN,
        reason_code="module_missing",
        details={"available": False, "report": report},
    )


def _probe_evaluation_reports(reports_dir: Path) -> ReadinessComponent:
    states = {
        area: _read_report_state(reports_dir, area)
        for area in ("rag", "memory", "planner")
    }
    if all(state != "missing" for state in states.values()):
        return ReadinessComponent(
            name="evaluation_reports",
            status=ReadinessStatus.READY,
            reason_code="ok",
            details=states,
        )
    return ReadinessComponent(
        name="evaluation_reports",
        status=ReadinessStatus.DEGRADED,
        reason_code="evidence_gap",
        details=states,
    )


def _compose_status(
    components: list[ReadinessComponent],
) -> ReadinessStatus:
    states = {item.status for item in components}
    if ReadinessStatus.NOT_READY in states:
        return ReadinessStatus.NOT_READY
    if ReadinessStatus.UNKNOWN in states:
        return ReadinessStatus.UNKNOWN
    if ReadinessStatus.DEGRADED in states:
        return ReadinessStatus.DEGRADED
    return ReadinessStatus.READY


def build_readiness_snapshot(
    reports_dir: Optional[Path] = None,
    db_path: Optional[Path] = None,
    chroma_dir: Optional[Path] = None,
) -> ReadinessSnapshot:
    """Compute one local readiness snapshot without changing any state.

    Optional overrides exist so tests can point probes at temporary paths;
    production callers use settings and repository-relative defaults. The
    function is total: an unexpected probe failure becomes an `unknown`
    component instead of an exception.
    """
    import time

    start = time.perf_counter()
    reports = Path(reports_dir) if reports_dir is not None else _DEFAULT_REPORTS_DIR
    probes = (
        ("app", lambda: _probe_app()),
        ("model_provider", lambda: _probe_model_provider()),
        ("rag_chroma", lambda: _probe_rag_chroma(chroma_dir)),
        ("app_db", lambda: _probe_app_db(db_path)),
        ("memory", lambda: _probe_memory(reports)),
        ("planner", lambda: _probe_planner(reports)),
        ("evaluation_reports", lambda: _probe_evaluation_reports(reports)),
    )
    components: list[ReadinessComponent] = []
    for name, probe in probes:
        try:
            components.append(probe())
        except Exception as error:
            logger.warning(
                "observability.readiness probe failed component=%s failure_class=%s",
                name,
                type(error).__name__,
            )
            components.append(
                ReadinessComponent(
                    name=name,
                    status=ReadinessStatus.UNKNOWN,
                    reason_code="probe_failed",
                    details={},
                )
            )
    snapshot = ReadinessSnapshot(
        status=_compose_status(components),
        checked_at=_utc_now(),
        components=tuple(components),
    )
    emit_event(
        EventName.OPS_READINESS_COMPLETED,
        EventComponent.OPS,
        EventResult.SUCCESS,
        reason_code=snapshot.status.value,
        duration_ms=(time.perf_counter() - start) * 1000,
        counters={"components": len(components)},
    )
    return snapshot
