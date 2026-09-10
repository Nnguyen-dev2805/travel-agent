"""Read-only local readiness probes for clean-break architecture.

Probes inspect local metadata and service connectivity without creating state:
- PostgreSQL connectivity check (connection pool / ping via SELECT 1).
- Alembic revision check (verifying applied revision matches head revision 20260910_01).
- RAG vector store check (Chroma collection accessible / path present).
- Model provider configuration check (API key configured).
- Background capture gate state check (MEMORY_SHADOW_EXTRACT_ENABLED).
- Application metadata probe.

Read-only probe: no DDL, no table creation as a side effect.
Controlled reason codes and status codes without content leakage (no DSNs, passwords, paths, or tenant data).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
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

logger = logging.getLogger("travel_agent_observability")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CHROMA_DIR = _REPO_ROOT / "data" / "chromadb"

EXPECTED_ALEMBIC_HEAD = "20260910_01"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _find_default_chroma_dir() -> Path:
    if _DEFAULT_CHROMA_DIR.exists():
        return _DEFAULT_CHROMA_DIR
    try:
        git_ref = _REPO_ROOT / ".git"
        if git_ref.is_file():
            text = git_ref.read_text().strip()
            if text.startswith("gitdir:"):
                git_dir_path = Path(text.split(":", 1)[1].strip())
                curr = git_dir_path
                for _ in range(5):
                    alt = curr / "data" / "chromadb"
                    if alt.exists():
                        return alt
                    curr = curr.parent
    except Exception:
        pass
    return _DEFAULT_CHROMA_DIR


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


def _probe_rag_chroma(chroma_dir: Optional[Path] = None) -> ReadinessComponent:
    path = Path(chroma_dir) if chroma_dir is not None else _find_default_chroma_dir()
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


def _resolve_probe(container: Any = None):
    if container is not None and hasattr(container, "readiness_probe"):
        return container.readiness_probe()
    if container is not None and hasattr(container, "engine"):
        from backend.app.runtime_container import PostgresReadinessProbe
        return PostgresReadinessProbe(container.engine)
    from backend.app.runtime_container import RuntimeContainer
    return RuntimeContainer().readiness_probe()


def _probe_postgres(container: Any = None) -> ReadinessComponent:
    try:
        probe = _resolve_probe(container)
        result = probe.check()
        if result.get("status") == "ready":
            return ReadinessComponent(
                name="database",
                status=ReadinessStatus.READY,
                reason_code="ok",
                details={"engine": "postgresql"},
            )
        details: dict[str, Any] = {"engine": "postgresql"}
        if result.get("error"):
            details["error"] = str(result["error"])
        return ReadinessComponent(
            name="database",
            status=ReadinessStatus.NOT_READY,
            reason_code="connectivity_failed",
            details=details,
        )
    except Exception as exc:
        logger.warning("readiness.postgres probe failed: %s", type(exc).__name__)
        return ReadinessComponent(
            name="database",
            status=ReadinessStatus.NOT_READY,
            reason_code="connectivity_failed",
            details={"engine": "postgresql", "error": type(exc).__name__},
        )


def _probe_alembic(container: Any = None) -> ReadinessComponent:
    try:
        probe = _resolve_probe(container)
        if hasattr(probe, "check_revision"):
            result = probe.check_revision(EXPECTED_ALEMBIC_HEAD)
        else:
            from sqlalchemy import text
            with probe._engine.connect() as conn:
                row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
                rev = str(row[0]) if row and row[0] is not None else None
            if rev == EXPECTED_ALEMBIC_HEAD:
                result = {"status": "ready", "revision": rev}
            else:
                result = {"status": "unhealthy", "expected": EXPECTED_ALEMBIC_HEAD, "current": rev}

        if result.get("status") == "ready":
            return ReadinessComponent(
                name="alembic",
                status=ReadinessStatus.READY,
                reason_code="ok",
                details={"revision": str(result.get("revision", EXPECTED_ALEMBIC_HEAD))},
            )
        details: dict[str, Any] = {"expected": EXPECTED_ALEMBIC_HEAD}
        if result.get("current") is not None:
            details["current"] = str(result["current"])
        if result.get("error") is not None:
            details["error"] = str(result["error"])
        return ReadinessComponent(
            name="alembic",
            status=ReadinessStatus.NOT_READY,
            reason_code="revision_mismatch",
            details=details,
        )
    except Exception as exc:
        logger.warning("readiness.alembic probe failed: %s", type(exc).__name__)
        return ReadinessComponent(
            name="alembic",
            status=ReadinessStatus.NOT_READY,
            reason_code="revision_check_failed",
            details={"expected": EXPECTED_ALEMBIC_HEAD, "error": type(exc).__name__},
        )


def _probe_memory_pipeline() -> ReadinessComponent:
    enabled = bool(settings.MEMORY_WRITE_PIPELINE_ENABLED)
    shadow = bool(settings.MEMORY_SHADOW_EXTRACT_ENABLED)
    return ReadinessComponent(
        name="memory_write_pipeline",
        status=ReadinessStatus.READY,
        reason_code="ok",
        details={"write_pipeline_enabled": enabled, "shadow_extract_enabled": shadow},
    )


def _compose_status(components: list[ReadinessComponent]) -> ReadinessStatus:
    states = {item.status for item in components}
    if ReadinessStatus.NOT_READY in states:
        return ReadinessStatus.NOT_READY
    if ReadinessStatus.UNKNOWN in states:
        return ReadinessStatus.UNKNOWN
    if ReadinessStatus.DEGRADED in states:
        return ReadinessStatus.DEGRADED
    return ReadinessStatus.READY


def build_readiness_snapshot(
    container: Any = None,
    chroma_dir: Optional[Path] = None,
) -> ReadinessSnapshot:
    """Compute one local readiness snapshot without changing any state."""
    import time

    start = time.perf_counter()
    resolved_chroma_dir = chroma_dir
    if resolved_chroma_dir is None and container is not None and hasattr(container, "chroma_dir"):
        resolved_chroma_dir = container.chroma_dir

    probes = (
        ("app", lambda: _probe_app()),
        ("model_provider", lambda: _probe_model_provider()),
        ("rag_chroma", lambda: _probe_rag_chroma(resolved_chroma_dir)),
        ("database", lambda: _probe_postgres(container)),
        ("alembic", lambda: _probe_alembic(container)),
        ("memory_write_pipeline", lambda: _probe_memory_pipeline()),
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
