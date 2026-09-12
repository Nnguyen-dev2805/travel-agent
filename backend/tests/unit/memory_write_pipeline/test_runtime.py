"""Unit tests for the worker process (ADR 0029).

The loop is tested with an injected worker, counters and sleep function, so the
poll/stop behaviour is asserted without a process, a clock, or a database.
"""

import threading
from types import SimpleNamespace

import pytest

from backend.app.config import Settings
from backend.memory.write_pipeline.observability import WorkerCounters
from backend.memory.write_pipeline.runtime import (
    WorkerConfigurationError,
    build_worker,
    main,
    run_worker,
)


class FakeWorker:
    """Records each batch request and returns whatever it is told to."""

    def __init__(self, batches=None, worker_id="fake_worker"):
        self.worker_id = worker_id
        self.calls: list[int] = []
        self._batches = list(batches or [])

    def run_batch(self, limit=10, debounce_seconds=0.0):
        self.calls.append(limit)
        if self._batches:
            return self._batches.pop(0)
        return []


HEARTBEAT = "last_successful_poll_at_epoch"


def _result(status="succeeded", reason=None):
    """A minimal `WorkerResult` stand-in.

    Carries `reason`, not `error`: the counters branch on the typed reason, so a
    stand-in still using the old field name would make them read `None` and report
    zero — which is the defect this vocabulary exists to fix.
    """
    return SimpleNamespace(status=SimpleNamespace(value=status), reason=reason)


def test_run_worker_polls_the_configured_batch_size():
    worker = FakeWorker()
    settings = Settings(WORKER_BATCH_SIZE=3, WORKER_POLL_INTERVAL_SECONDS=0.0)

    run_worker(threading.Event(), worker, settings, sleep=lambda _s: None, max_iterations=2)

    assert worker.calls == [3, 3], "the batch size bounds every poll"


def test_run_worker_sleeps_the_configured_interval_between_polls():
    slept: list[float] = []
    settings = Settings(WORKER_BATCH_SIZE=1, WORKER_POLL_INTERVAL_SECONDS=2.5)

    run_worker(
        threading.Event(),
        FakeWorker(),
        settings,
        sleep=slept.append,
        max_iterations=3,
    )

    assert slept == [2.5, 2.5], "no sleep after the final iteration"


def test_run_worker_stops_between_batches_when_signalled():
    """A stop signal must not interrupt an event; it ends the loop after one."""
    stop = threading.Event()

    class StoppingWorker(FakeWorker):
        def run_batch(self, limit=10, debounce_seconds=0.0):
            result = super().run_batch(limit=limit, debounce_seconds=debounce_seconds)
            stop.set()  # as if SIGTERM arrived while this batch was running
            return result

    worker = StoppingWorker()
    run_worker(stop, worker, Settings(WORKER_POLL_INTERVAL_SECONDS=0.0), sleep=lambda _s: None)

    assert len(worker.calls) == 1, "the loop ends after the batch in flight"


def test_run_worker_records_a_sustained_empty_run():
    """An empty claim is the only signal that distinguishes idle from unable."""
    counters = WorkerCounters()

    run_worker(
        threading.Event(),
        FakeWorker(),
        Settings(WORKER_POLL_INTERVAL_SECONDS=0.0),
        counters=counters,
        sleep=lambda _s: None,
        max_iterations=4,
    )

    assert counters.polls == 4
    assert counters.claimed == 0
    assert counters.sustained_empty_polls == 4


def test_a_claimed_event_resets_the_sustained_empty_counter():
    counters = WorkerCounters()

    run_worker(
        threading.Event(),
        FakeWorker(batches=[[_result()], [], []]),
        Settings(WORKER_POLL_INTERVAL_SECONDS=0.0),
        counters=counters,
        sleep=lambda _s: None,
        max_iterations=3,
    )

    assert counters.claimed == 1
    assert counters.sustained_empty_polls == 2, "reset by the claim, then two empty polls"


def test_counters_fold_every_outcome_without_content():
    counters = WorkerCounters()
    counters.record_batch(
        [
            _result("succeeded"),
            _result("pending"),
            _result("dead_letter"),
            _result("cancelled"),
        ]
    )

    folded = counters.as_dict()
    # The heartbeat is a live timestamp, so it is excluded from the exact match and
    # asserted separately below.
    assert {k: v for k, v in folded.items() if k != HEARTBEAT} == {
        "claimed": 4,
        "processed": 4,
        "succeeded": 1,
        "retried": 1,
        "dead_lettered": 1,
        "cancelled": 1,
        "lease_lost": 0,
        "refused_foreign_event": 0,
        "sustained_empty_polls": 0,
        "polls": 1,
    }
    assert all(isinstance(value, int) for value in folded.values()), (
        "counters are numbers only; nothing carries message or evidence content"
    )


def test_lease_loss_is_counted_from_the_typed_reason():
    """The defect: `lease_lost` matched two strings the worker never emitted.

    `WorkerCounters.record_batch` compared `result.error` against the literals
    `"lease_lost"` and `"The source outbox lease was lost."`. Neither exists in
    `worker.py`, which produces thirteen other reasons, so the counter was dead
    code — a worker losing its lease on every poll reported a flat zero.
    """
    from backend.memory.write_pipeline.observability import WorkerReason

    lease_losses = [reason for reason in WorkerReason if reason.is_lease_loss]
    assert len(lease_losses) >= 5, "the family must not shrink silently"

    counters = WorkerCounters()
    counters.record_batch([_result("cancelled", reason=r) for r in lease_losses])

    assert counters.lease_lost == len(lease_losses)


def test_the_lease_loss_family_is_exactly_the_documented_one():
    """Total and pinned, so a new reason cannot join or leave unremarked."""
    from backend.memory.write_pipeline.observability import WorkerReason

    assert {reason.value for reason in WorkerReason if reason.is_lease_loss} == {
        "lease_claim_failed",
        "lease_renewal_failed",
        "leased_by_another_worker",
        "lease_lost_before_commit",
        "mark_succeeded_failed_lease_lost",
    }


def test_a_fence_is_not_counted_as_a_lease_loss():
    """A fence may be a lease loss *or* a deleted conversation.

    Counting it as a lease loss would corrupt the signal in the other direction: an
    operator deleting conversations would read as a lease problem. The typed
    `FenceReason` travels in `error_detail`, so the two stay distinguishable.
    """
    from backend.memory.write_pipeline.observability import WorkerReason

    counters = WorkerCounters()
    counters.record_batch(
        [_result("cancelled", reason=WorkerReason.FENCED_BY_SOURCE_MOVE)]
    )

    assert counters.lease_lost == 0
    assert counters.cancelled == 1


def test_a_foreign_event_is_counted_apart_from_a_lease_loss():
    """The worker never held that event: neither a loss nor a failure to process."""
    from backend.memory.write_pipeline.observability import WorkerReason

    counters = WorkerCounters()
    counters.record_batch([_result("pending", reason=WorkerReason.WRONG_EVENT_FAMILY)])

    assert counters.refused_foreign_event == 1
    assert counters.lease_lost == 0


def test_a_successful_result_carries_no_reason():
    """`None` means success, so it must not be counted as anything else."""
    counters = WorkerCounters()
    counters.record_batch([_result("succeeded")])

    assert counters.succeeded == 1
    assert counters.lease_lost == 0
    assert counters.refused_foreign_event == 0


def test_the_heartbeat_advances_on_a_completed_poll():
    """The one signal that separates a dead worker from an idle one.

    Readiness cannot make that distinction: the API shares no state with a separate
    process, so a worker that died and a worker with nothing to do leave the queue
    looking identical. A heartbeat that stops advancing does not.

    An *empty* poll advances it too, and that is the case that matters — a quiet
    worker is exactly the one whose death would otherwise be invisible.
    """
    import time

    counters = WorkerCounters()
    assert counters.as_dict()[HEARTBEAT] == 0, "0 means no poll has completed"

    before = int(time.time())
    counters.record_batch([])
    after = int(time.time())

    assert before <= counters.as_dict()[HEARTBEAT] <= after


def test_the_heartbeat_survives_a_batch_that_claimed_work():
    """A poll with results is also a completed poll."""
    counters = WorkerCounters()
    counters.record_batch([_result("succeeded")])

    assert counters.as_dict()[HEARTBEAT] > 0
    assert counters.succeeded == 1


def test_build_worker_requires_an_engine():
    with pytest.raises(WorkerConfigurationError):
        build_worker(None, Settings())


def test_build_worker_wires_the_configured_identity_and_limits():
    worker, provider = build_worker(
        SimpleNamespace(),
        Settings(WORKER_ID="w_test", WORKER_LEASE_SECONDS=7.0, WORKER_MAX_ATTEMPTS=5),
        provider=SimpleNamespace(close=lambda: None),
    )

    assert worker.worker_id == "w_test"
    assert worker._lease_duration_seconds == 7.0
    assert worker._max_attempts == 5
    assert provider is not None


def test_main_refuses_to_start_when_the_guard_rejects_the_role(monkeypatch):
    """A privileged worker role must exit non-zero, not run with RLS disabled."""
    from backend.memory.write_pipeline import runtime as module

    # ADR 0034 precondition. `config.py` loads `.env` into the process environment
    # at import, and this repository's `.env` carries the API's `DATABASE_URL`, so
    # without this the credential guard fires first and the role guard under test
    # is never reached. An isolated environment is now a precondition for the
    # worker starting at all; stating it here keeps the test about the role guard.
    monkeypatch.delenv("DATABASE_URL", raising=False)

    disposed: list[bool] = []

    class FakeEngine:
        def dispose(self):
            disposed.append(True)

    monkeypatch.setattr(module, "create_engine", lambda _dsn: FakeEngine())

    def reject(_engine, **_kwargs):
        raise RuntimeError("superuser or bypasses row-level security")

    monkeypatch.setattr(module, "assert_least_privilege_role", reject)

    assert main() == 1, "a rejected role exits non-zero"
    assert disposed == [True], "the engine is disposed on the failure path"


def test_main_builds_its_engine_from_the_worker_dsn(monkeypatch):
    """The worker must never fall back to the API's DATABASE_URL."""
    from backend.memory.write_pipeline import runtime as module

    # ADR 0034 precondition: see the note in the previous test. The credential
    # guard reads the process environment, not `Settings`, so an explicit
    # `Settings(DATABASE_URL=...)` below does not trip it — only the ambient one
    # loaded from `.env` would, and that is what this removes.
    monkeypatch.delenv("DATABASE_URL", raising=False)

    seen: list[str] = []
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://travel_app:api@db:5432/travel_agent",
        WORKER_DATABASE_URL="postgresql+psycopg://travel_worker:w@db:5432/travel_agent",
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)

    class FakeEngine:
        def dispose(self):
            pass

    monkeypatch.setattr(
        module, "create_engine", lambda dsn: (seen.append(dsn), FakeEngine())[1]
    )
    monkeypatch.setattr(module, "assert_least_privilege_role", lambda *_a, **_k: None)
    monkeypatch.setattr(
        module, "build_worker", lambda *_a, **_k: (FakeWorker(), SimpleNamespace(close=lambda: None))
    )
    monkeypatch.setattr(module, "run_worker", lambda *_a, **_k: WorkerCounters())

    assert main() == 0
    assert seen == ["postgresql+psycopg://travel_worker:w@db:5432/travel_agent"]
