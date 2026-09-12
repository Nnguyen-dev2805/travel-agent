"""The background Memory worker process (ADR 0029).

The worker runs as its own process, as its own service, holding only the
`travel_worker` credential. It builds its own object graph from `worker_dsn()`,
refuses to start on a privileged role, polls the outbox on an interval, and
releases what it holds on `SIGTERM`.

**This module is the only place the pipeline is composed.** Every piece already
existed and was tested; nothing assembled them outside tests, so chat wrote outbox
events that nothing read. Composition lives here rather than in
`RuntimeContainer` because the API must never hold the worker's credential
(ADR 0029).

The loop is deliberately small and injectable: `run_worker` takes its worker, its
counters and its sleep function, so the poll/stop behaviour is testable without a
process or a clock.
"""

from __future__ import annotations

import logging
import signal
import threading
import time
from typing import Any, Callable

from backend.app.config import Settings, assert_credential_isolation, get_settings
from backend.conversations.postgres_repository import PostgresConversationRepository
from backend.conversations.service import ConversationService
from backend.memory.write_pipeline.background_recorder import BackgroundMemoryRecorder
from backend.memory.write_pipeline.model_adapter import MemoryExtractionModel
from backend.memory.write_pipeline.observability import (
    FileHeartbeatSink,
    HeartbeatSink,
    WorkerCounters,
)
from backend.memory.write_pipeline.outbox import PostgresOutboxRepository
from backend.memory.write_pipeline.postgres import PostgresMemoryUnitOfWork
from backend.memory.write_pipeline.provider import OpenAICompatibleProvider
from backend.memory.write_pipeline.worker import MemoryOutboxWorker
from backend.storage.postgres import assert_least_privilege_role, create_engine

logger = logging.getLogger("travel_agent_memory_worker")


class WorkerConfigurationError(RuntimeError):
    """The worker cannot be assembled from the current settings."""


def build_worker(
    engine: Any,
    settings: Settings | None = None,
    provider: Any = None,
) -> tuple[MemoryOutboxWorker, Any]:
    """Assemble the worker and the provider it owns.

    Returns `(worker, provider)` so the caller can close the provider. The
    provider is built from `.env`-backed settings: the same endpoint, credential
    and model the chat path uses.
    """
    resolved = settings if settings is not None else get_settings()
    if engine is None:
        raise WorkerConfigurationError("The worker requires a database engine.")

    owned_provider = provider if provider is not None else OpenAICompatibleProvider(
        settings=resolved
    )
    model = MemoryExtractionModel(
        provider=owned_provider,
        model_name=resolved.LLM_MODEL,
    )

    outbox_repo = PostgresOutboxRepository(engine)
    conversation_service = ConversationService(
        conversation_repository=PostgresConversationRepository(engine)
    )
    recorder = BackgroundMemoryRecorder(
        uow_factory=lambda: PostgresMemoryUnitOfWork(engine)
    )

    worker = MemoryOutboxWorker(
        outbox_repo=outbox_repo,
        model_adapter=model,
        conversation_service=conversation_service,
        recorder=recorder,
        worker_id=resolved.WORKER_ID,
        lease_duration_seconds=resolved.WORKER_LEASE_SECONDS,
        max_attempts=resolved.WORKER_MAX_ATTEMPTS,
        backoff_base_seconds=resolved.WORKER_BACKOFF_BASE_SECONDS,
    )
    return worker, owned_provider


def run_worker(
    stop_event: threading.Event,
    worker: MemoryOutboxWorker,
    settings: Settings | None = None,
    counters: WorkerCounters | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_iterations: int | None = None,
    heartbeat: HeartbeatSink | None = None,
) -> WorkerCounters:
    """Poll until `stop_event` is set.

    Stops *between* batches, never mid-event: `run_batch` processes every event it
    claimed, so an event is either finished or left leased and reclaimable. The
    batch size bounds how long a shutdown can take.

    After every completed batch — empty or not — the heartbeat sink receives the
    poll's own clock, so a supervisor reading the sink sees an age bounded by one
    poll interval plus one batch duration. A worker wedged inside a call stops
    beating, and that is the signal "container running" cannot provide by itself
    (ADR 0029: the worker has no HTTP surface, so liveness is the process plus a
    heartbeat).
    """
    resolved = settings if settings is not None else get_settings()
    state = counters if counters is not None else WorkerCounters()
    interval = max(0.0, resolved.WORKER_POLL_INTERVAL_SECONDS)
    batch_size = max(1, resolved.WORKER_BATCH_SIZE)

    iterations = 0
    logger.info(
        "memory worker started worker_id=%s interval=%.2fs batch=%s",
        worker.worker_id,
        interval,
        batch_size,
    )
    while not stop_event.is_set():
        results = worker.run_batch(limit=batch_size)
        state.record_batch(results)
        logger.info("memory worker poll %s", state.as_dict())
        if heartbeat is not None:
            heartbeat.touch(epoch_seconds=state.last_successful_poll_at_epoch)

        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break
        if stop_event.is_set():
            break
        sleep(interval)

    logger.info("memory worker stopped %s", state.as_dict())
    return state


def _configure_logging() -> None:
    """Send the worker's own logs to stderr at INFO.

    Without this the process is silent: a container running the worker produces no
    evidence that it started, polled, or stopped, and the counters — including the
    sustained-empty signal that exists to expose a worker that cannot claim —
    would go nowhere. Only configured when nothing else has been, so an embedding
    process keeps its own logging setup.
    """
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _heartbeat_sink(settings: Settings) -> HeartbeatSink | None:
    """Build the process's heartbeat sink, or `None` when the path is unset.

    An unset path keeps the worker exactly as it was — the beat was already
    in the log line and `WorkerCounters`; the sink publishes it where a
    healthcheck can read it. A set path that cannot be constructed fails
    loudly rather than degrading to "run without a heartbeat", because an
    operator who configures a heartbeat and silently gets none is the exact
    condition ADR 0029's liveness rule exists to prevent.
    """
    path = (settings.WORKER_HEARTBEAT_PATH or "").strip()
    if not path:
        return None
    return FileHeartbeatSink(path)


def main(argv: list[str] | None = None) -> int:
    """Process entry point.

    Fails closed on a leaked credential and on a privileged role, then polls until
    `SIGTERM` or `SIGINT`. Returns 0 on a clean shutdown and 1 when it cannot start.
    """
    _configure_logging()
    settings = get_settings()
    engine = None
    provider = None
    try:
        # ADR 0034, before the engine: the worker must never hold the API's
        # `travel_app` credential. `worker_dsn()` has no fallback to it, so the
        # leaked value is inert today — but it becomes live the moment any code in
        # this process resolves the API DSN, and nothing prevents that. Failing
        # here names the environment rather than surfacing later as a wrong-role
        # connection.
        assert_credential_isolation("worker")
        engine = create_engine(settings.worker_dsn())
        # The same guard the API runs. A superuser or BYPASSRLS worker would make
        # every tenant policy decorative, and the worker reads other owners'
        # queues by design, so the check matters more here than there.
        assert_least_privilege_role(
            engine,
            allowed=settings.ALLOW_PRIVILEGED_DB_ROLE,
            context="MemoryWorker",
        )
        worker, provider = build_worker(engine, settings)
    except Exception as error:  # noqa: BLE001 - reported, then exit non-zero
        logger.error(
            "memory worker failed to start failure_class=%s", type(error).__name__
        )
        if engine is not None:
            engine.dispose()
        return 1

    heartbeat = _heartbeat_sink(settings)

    stop_event = threading.Event()

    def request_stop(signum: int, _frame: Any) -> None:
        logger.info("memory worker received signal %s", signum)
        stop_event.set()

    for signal_name in ("SIGTERM", "SIGINT"):
        if hasattr(signal, signal_name):
            signal.signal(getattr(signal, signal_name), request_stop)

    try:
        run_worker(stop_event, worker, settings, heartbeat=heartbeat)
    finally:
        if provider is not None and hasattr(provider, "close"):
            provider.close()
        engine.dispose()
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
