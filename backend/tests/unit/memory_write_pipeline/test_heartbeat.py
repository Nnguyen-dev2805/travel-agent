"""Unit tests for the worker heartbeat sink.

The heartbeat exists because "container running" is not "worker alive": a
worker wedged inside a model call or a deadlocked poll is still a running
container, and an idle-but-healthy worker looks exactly the same. The signal
that separates them is a timestamp that advances on every completed poll —
`WorkerCounters.last_successful_poll_at_epoch` already measures it, and this
sink publishes it somewhere an operator's healthcheck can read without the
process exposing an HTTP surface it deliberately does not have (ADR 0029).
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from backend.memory.write_pipeline.observability import (
    FileHeartbeatSink,
    StaleHeartbeatError,
    touch_is_fresh,
)


def test_touch_advances_the_file_mtime(tmp_path):
    sink = FileHeartbeatSink(tmp_path / "heartbeat")
    sink.touch(epoch_seconds=1000)

    mtime = (tmp_path / "heartbeat").stat().st_mtime
    assert mtime == pytest.approx(1000, abs=1)


def test_touch_overwrites_the_previous_beat(tmp_path):
    sink = FileHeartbeatSink(tmp_path / "heartbeat")
    sink.touch(epoch_seconds=1000)
    sink.touch(epoch_seconds=2000)

    assert (tmp_path / "heartbeat").stat().st_mtime == pytest.approx(2000, abs=1)


def test_touch_is_fresh_accepts_a_recent_beat(tmp_path):
    sink = FileHeartbeatSink(tmp_path / "heartbeat")
    now = datetime.now(timezone.utc)
    sink.touch(epoch_seconds=int(now.timestamp()))

    assert touch_is_fresh(tmp_path / "heartbeat", max_age_seconds=30.0)


def test_touch_is_fresh_rejects_a_stale_beat(tmp_path):
    sink = FileHeartbeatSink(tmp_path / "heartbeat")
    stale = datetime.now(timezone.utc) - timedelta(seconds=600)
    sink.touch(epoch_seconds=int(stale.timestamp()))

    assert not touch_is_fresh(tmp_path / "heartbeat", max_age_seconds=30.0)


def test_touch_is_fresh_rejects_a_missing_file(tmp_path):
    assert not touch_is_fresh(tmp_path / "never-touched", max_age_seconds=30.0)


def test_touch_is_fresh_rejects_a_clock_skew(tmp_path):
    """A beat stamped in the future by more than the tolerance is not fresh.

    A wildly future mtime means the file system clock and the heartbeat clock
    disagree, and a healthcheck must not read that as "always fresh" forever.
    """

    sink = FileHeartbeatSink(tmp_path / "heartbeat")
    future = datetime.now(timezone.utc) + timedelta(seconds=3600)
    sink.touch(epoch_seconds=int(future.timestamp()))

    assert not touch_is_fresh(tmp_path / "heartbeat", max_age_seconds=30.0)


def test_a_sink_created_from_a_directory_without_permission_fails_loudly(tmp_path):
    """A heartbeat that cannot be written is a configuration defect, not a silent no-op."""

    with pytest.raises(StaleHeartbeatError):
        FileHeartbeatSink(tmp_path / "missing-parent" / "heartbeat")


def test_the_loop_wires_the_sink_into_every_poll(tmp_path):
    """`run_worker` beats once per completed batch, including empty polls.

    This is the property an operator's healthcheck depends on: the file's age
    must stay bounded by one poll interval plus the batch duration, so a
    worker that stops polling — wedged in a call, deadlocked on the queue —
    goes stale and the container reports unhealthy.
    """
    from backend.memory.write_pipeline.runtime import run_worker

    class StubWorker:
        worker_id = "stub"

        def run_batch(self, limit=10):
            return [object()]  # one non-empty result per poll

    sink = FileHeartbeatSink(tmp_path / "heartbeat")
    stop = threading.Event()

    from backend.app.config import Settings

    class _FastSettings(Settings):
        WORKER_POLL_INTERVAL_SECONDS: float = 0.0
        WORKER_BATCH_SIZE: int = 1

    # Two polls, then stop.
    def _stop_after_two_polls(_seconds: float) -> None:
        if not hasattr(_stop_after_two_polls, "calls"):
            _stop_after_two_polls.calls = 0
        _stop_after_two_polls.calls += 1
        if _stop_after_two_polls.calls >= 2:
            stop.set()

    run_worker(
        stop,
        StubWorker(),
        settings=_FastSettings(),
        sleep=_stop_after_two_polls,
        max_iterations=5,
        heartbeat=sink,
    )

    assert touch_is_fresh(tmp_path / "heartbeat", max_age_seconds=30.0), (
        "the file was touched by the loop itself, so it must read as fresh"
    )


def test_the_healthcheck_cli_reports_fresh_as_zero_and_stale_as_one(tmp_path):
    """The container healthcheck contract: exit status, not output."""
    from backend.memory.write_pipeline.healthcheck import main as healthcheck_main

    fresh_path = tmp_path / "fresh"
    FileHeartbeatSink(fresh_path).touch(epoch_seconds=int(time.time()))
    assert healthcheck_main([str(fresh_path), "30"]) == 0

    stale_path = tmp_path / "stale"
    FileHeartbeatSink(stale_path).touch(
        epoch_seconds=int(
            (datetime.now(timezone.utc) - timedelta(seconds=600)).timestamp()
        )
    )
    assert healthcheck_main([str(stale_path), "30"]) == 1

    assert healthcheck_main([str(tmp_path / "missing"), "30"]) == 1
    assert healthcheck_main([]) == 1, "no arguments is a usage error, not a pass"
