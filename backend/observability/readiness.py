"""Read-only local readiness probes for clean-break architecture.

Probes inspect local metadata and service connectivity without creating state:
- PostgreSQL connectivity check (connection pool / ping via SELECT 1).
- Alembic revision check (verifying the applied revision matches the declared
  head revision).
- RAG vector store check (Chroma collection row, vector count, and sample
  read through SQLite in immutable read-only mode; never constructs a
  Chroma client, which would initialize storage as a side effect).
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
from backend.storage.postgres import ALEMBIC_HEAD
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

EXPECTED_ALEMBIC_HEAD = ALEMBIC_HEAD


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
    """Report the provider usable only when both halves of its config are set.

    A credential alone is not enough. `config.py` deliberately provides no
    fallback for the endpoint, so an empty `GITHUB_MODELS_URL` makes the first
    model call fail with `APIConnectionError`. Checking the token alone reported
    `ready` for a deployment that could not answer a single request.
    """
    token = (settings.GITHUB_TOKEN or "").strip()
    if not token:
        return ReadinessComponent(
            name="model_provider",
            status=ReadinessStatus.NOT_READY,
            reason_code="credential_missing",
            details={"model": settings.LLM_MODEL},
        )
    if not (settings.GITHUB_MODELS_URL or "").strip():
        return ReadinessComponent(
            name="model_provider",
            status=ReadinessStatus.NOT_READY,
            reason_code="endpoint_missing",
            details={"model": settings.LLM_MODEL},
        )
    return ReadinessComponent(
        name="model_provider",
        status=ReadinessStatus.READY,
        reason_code="ok",
        details={"model": settings.LLM_MODEL},
    )


RAG_CHROMA_COLLECTION = "vietnam_travel_parent_child"
RAG_CHROMA_SQLITE = "chroma.sqlite3"


def _chroma_component(
    status: ReadinessStatus,
    reason_code: str,
    *,
    present: bool,
    vectors: int | None = None,
) -> ReadinessComponent:
    """Build the rag_chroma component with its governed detail shape."""
    details: dict[str, Any] = {
        "present": present,
        "collection": RAG_CHROMA_COLLECTION,
    }
    if vectors is not None:
        details["vectors"] = vectors
    return ReadinessComponent(
        name="rag_chroma",
        status=status,
        reason_code=reason_code,
        details=details,
    )


def _probe_rag_chroma(chroma_dir: Optional[Path] = None) -> ReadinessComponent:
    """Prove the Chroma index opens and answers without writing anything.

    Read-only by construction: the probe never constructs a Chroma client
    (whose initialization creates `chroma.sqlite3` in an empty directory).
    It opens the store file through SQLite in immutable read-only mode and
    verifies the expected collection row, its vector count, and one sample
    read.
    """
    from urllib.parse import quote

    import sqlite3

    path = Path(chroma_dir) if chroma_dir is not None else _find_default_chroma_dir()
    if not path.exists():
        return ReadinessComponent(
            name="rag_chroma",
            status=ReadinessStatus.UNKNOWN,
            reason_code="path_missing",
            details={"present": False},
        )
    sqlite_path = path / RAG_CHROMA_SQLITE
    if not sqlite_path.is_file():
        return _chroma_component(
            ReadinessStatus.NOT_READY, "index_missing", present=True
        )
    try:
        # mode=ro (not immutable=1): the live store may still be appended
        # by a writer, and immutable snapshots would error on change.
        uri = f"file:{quote(str(sqlite_path))}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            row = connection.execute(
                "SELECT id FROM collections WHERE name = ?",
                (RAG_CHROMA_COLLECTION,),
            ).fetchone()
            if row is None:
                return _chroma_component(
                    ReadinessStatus.NOT_READY, "collection_missing", present=True
                )
            collection_id = row[0]
            count = connection.execute(
                "SELECT COUNT(*) FROM embeddings AS e "
                "JOIN segments AS s ON s.id = e.segment_id "
                "WHERE s.collection = ?",
                (collection_id,),
            ).fetchone()[0]
            if count == 0:
                return _chroma_component(
                    ReadinessStatus.DEGRADED,
                    "collection_empty",
                    present=True,
                    vectors=0,
                )
            # C6: the catalogue rows above are independent of the HNSW segment
            # directories. Deleting a VECTOR segment leaves the count intact
            # while the application's query path fails, so check those
            # directories too. A collection also has a METADATA segment that
            # lives only in SQLite and has no directory — checking every
            # segment would flag it as missing.
            segment_ids = [
                segment_row[0]
                for segment_row in connection.execute(
                    "SELECT id FROM segments WHERE collection = ? AND scope = 'VECTOR'",
                    (collection_id,),
                ).fetchall()
            ]
            missing_segments = [
                segment_id
                for segment_id in segment_ids
                if not (path / segment_id).is_dir()
            ]
            if missing_segments:
                return _chroma_component(
                    ReadinessStatus.NOT_READY,
                    "segment_missing",
                    present=True,
                    vectors=int(count),
                )
            sample_row = connection.execute(
                "SELECT e.embedding_id FROM embeddings AS e "
                "JOIN segments AS s ON s.id = e.segment_id "
                "WHERE s.collection = ? LIMIT 1",
                (collection_id,),
            ).fetchone()
            if sample_row is None:
                return _chroma_component(
                    ReadinessStatus.DEGRADED, "index_unreadable", present=True
                )
            return _chroma_component(
                ReadinessStatus.READY,
                "collection_open",
                present=True,
                vectors=int(count),
            )
        finally:
            connection.close()
    except Exception as exc:
        logger.warning("readiness.rag_chroma probe failed: %s", type(exc).__name__)
        return _chroma_component(
            ReadinessStatus.NOT_READY, "collection_unavailable", present=True
        )


def _resolve_probe(container: Any = None):
    """Return a readiness probe for `container`, or refuse.

    This used to fall back to `RuntimeContainer().readiness_probe()`, which built a
    production container — its engine, its pool and its least-privilege role check —
    *inside a readiness probe*. That is a second composition root, and it was
    reachable from a unit test, so a probe's result depended on whether a database
    happened to be reachable. Composition happens in the lifespan; a probe with no
    container has nothing to report about, so it says so.
    """
    if container is not None and hasattr(container, "readiness_probe"):
        return container.readiness_probe()
    if container is not None and hasattr(container, "engine"):
        from backend.app.runtime_container import PostgresReadinessProbe

        return PostgresReadinessProbe(container.engine)
    from backend.app.runtime_container import ContainerUnavailableError

    raise ContainerUnavailableError(
        "A readiness probe was requested without a composed container. "
        "Application composition happens in the FastAPI lifespan."
    )


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
            result = {
                "status": "unhealthy",
                "expected": EXPECTED_ALEMBIC_HEAD,
                "error": "probe_missing_check_revision",
            }

        if result.get("status") == "ready":
            return ReadinessComponent(
                name="alembic",
                status=ReadinessStatus.READY,
                reason_code="ok",
                details={
                    "revision": str(result.get("revision", EXPECTED_ALEMBIC_HEAD))
                },
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


def _probe_memory_pipeline(container: Any = None) -> ReadinessComponent:
    """Report the observed state of the memory write pipeline.

    C7: this used to return READY unconditionally, so a dead worker, a missing
    outbox table, or a disabled pipeline were all reported healthy.

    It was then changed to use queue *depth* as health, which answers the wrong
    question in both directions — a healthy worker draining one event reported
    DEGRADED (and the ops route turns DEGRADED into HTTP 503), while a dead worker
    with an empty queue reported READY. Depth cannot distinguish "busy" from
    "stalled".

    What this reports now is what the API can actually observe:

    * the outbox is unreadable -> NOT_READY, `outbox_unavailable`
    * the oldest claimable event is older than `MEMORY_BACKLOG_STALE_SECONDS`
      -> DEGRADED, `backlog_stale`
    * otherwise -> READY, `ok`

    Depth and dead letters are reported as **details, not as status**: five events
    being drained steadily is a healthy pipeline, and a dead letter is a data
    condition an operator inspects rather than a reason to take the API out of
    service.

    The component is **non-critical**: it is reported, and it does not drive the
    aggregate. Memory formation is a background service and the chat surface works
    without it, so a stalled worker must not remove a healthy instance from
    rotation. What it must do is be visible, which it is.

    **What this deliberately does not claim: worker liveness.** The worker is a
    separate process and the API shares no state with it, so "the worker is dead
    and the queue is empty" is not observable from here — it is indistinguishable
    from an idle healthy system. The approved worker design puts worker liveness on
    the worker's own process, which is why that service carries its own restart
    policy. A heartbeat would need shared state and is a separate change; until
    then this component does not pretend to measure it.
    """
    enabled = bool(settings.MEMORY_WRITE_PIPELINE_ENABLED)
    shadow = bool(settings.MEMORY_SHADOW_EXTRACT_ENABLED)
    details: dict[str, Any] = {
        "write_pipeline_enabled": enabled,
        "shadow_extract_enabled": shadow,
    }

    if not enabled:
        return ReadinessComponent(
            name="memory_write_pipeline",
            status=ReadinessStatus.UNKNOWN,
            reason_code="disabled",
            details=details,
            critical=False,
        )

    try:
        probe = _resolve_probe(container)
        pending = probe.count_ready_outbox_events()
        oldest_age = probe.oldest_ready_outbox_event_age_seconds()
        dead_letters = probe.dead_letter_outbox_event_count()
    except Exception as exc:
        logger.warning(
            "readiness.memory_write_pipeline probe failed failure_class=%s",
            type(exc).__name__,
        )
        return ReadinessComponent(
            name="memory_write_pipeline",
            status=ReadinessStatus.NOT_READY,
            reason_code="outbox_unavailable",
            details=details,
            critical=False,
        )

    stale_after = float(settings.MEMORY_BACKLOG_STALE_SECONDS)
    # Built as a new mapping rather than merged in place. This module is scanned by
    # `test_readiness_sqlite_access_is_read_only` for SQL write verbs anywhere in
    # the source, and the in-place merge method is named after one of them. The scan
    # is deliberately blunt — a probe must never write — so the code avoids the
    # method rather than the guard being loosened for a method name.
    details = {
        **details,
        "ready_events": pending,
        "oldest_ready_event_age_seconds": oldest_age,
        "stale_after_seconds": stale_after,
        "dead_letters": dead_letters,
    }

    if oldest_age > stale_after:
        return ReadinessComponent(
            name="memory_write_pipeline",
            status=ReadinessStatus.DEGRADED,
            reason_code="backlog_stale",
            details=details,
            critical=False,
        )

    return ReadinessComponent(
        name="memory_write_pipeline",
        status=ReadinessStatus.READY,
        reason_code="ok",
        details=details,
        critical=False,
    )


def _compose_status(components: list[ReadinessComponent]) -> ReadinessStatus:
    """Worst-state composition over the *critical* components.

    Two kinds of component are excluded, for different reasons.

    A component that is explicitly disabled does not participate: disabling an
    optional subsystem is not a degradation of the instance, and counting it would
    report every deployment with the memory pipeline off as not ready.

    A non-critical component does not participate either. `ops.py` turns any
    aggregate status other than READY into HTTP 503, and that status is what a load
    balancer reads — so letting a stalled *background* worker drive it would remove
    every healthy chat instance from rotation. The background component is still
    reported, with its own status and reason code, which is what an operator reads;
    it simply does not decide whether the instance can serve.
    """
    states = {
        item.status
        for item in components
        if item.critical and item.reason_code != "disabled"
    }
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
    if (
        resolved_chroma_dir is None
        and container is not None
        and hasattr(container, "chroma_dir")
    ):
        resolved_chroma_dir = container.chroma_dir

    probes = (
        ("app", lambda: _probe_app()),
        ("model_provider", lambda: _probe_model_provider()),
        ("rag_chroma", lambda: _probe_rag_chroma(resolved_chroma_dir)),
        ("database", lambda: _probe_postgres(container)),
        ("alembic", lambda: _probe_alembic(container)),
        ("memory_write_pipeline", lambda: _probe_memory_pipeline(container)),
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
