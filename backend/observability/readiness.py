"""Read-only local readiness probes for clean-break architecture.

Probes inspect local metadata and service connectivity without creating state.
PostgreSQL connectivity is probed via the engine connection pool.
No provider is called for generation; Chroma and models are configuration/path checked.
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
_DEFAULT_REPORTS_DIR = Path("docs/reports")


def _utc_now():
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


def _probe_postgres(container: Any = None) -> ReadinessComponent:
    try:
        from sqlalchemy import text
        if container is not None and hasattr(container, "engine"):
            engine = container.engine
        else:
            from backend.app.runtime_container import RuntimeContainer
            engine = RuntimeContainer().engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return ReadinessComponent(
            name="database",
            status=ReadinessStatus.READY,
            reason_code="ok",
            details={"engine": "postgresql"},
        )
    except Exception as exc:
        logger.warning("readiness.postgres probe failed: %s", type(exc).__name__)
        return ReadinessComponent(
            name="database",
            status=ReadinessStatus.NOT_READY,
            reason_code="connectivity_failed",
            details={"engine": "postgresql", "error": type(exc).__name__},
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
    probes = (
        ("app", lambda: _probe_app()),
        ("model_provider", lambda: _probe_model_provider()),
        ("rag_chroma", lambda: _probe_rag_chroma(chroma_dir)),
        ("database", lambda: _probe_postgres(container)),
        ("memory_pipeline", lambda: _probe_memory_pipeline()),
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
