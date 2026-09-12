"""Counters for the background Memory worker, and the vocabulary they count.

The counter that matters most is `sustained_empty_polls`. An empty claim is
otherwise indistinguishable from a healthy quiet system, and that is the exact
failure ADR 0028 fixed at the database level: the worker could not see the queue
and reported success. At the process level the same shape returns as "the worker
is running, the queue is empty" when the truth may be "the worker cannot claim".
A rising `sustained_empty_polls` next to a non-zero `ready_outbox_event_count()`
is that condition, and it is the only signal that distinguishes them.

**No counter carries content.** Counts only: no message text, no evidence text,
no prompt body, no owner identity. A counter is emitted into logs and metrics,
both of which are less protected than the database.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol


class WorkerReason(str, Enum):
    """Why one processing attempt ended the way it did.

    These were free-text strings on `WorkerResult.error`, and the counters matched
    two of them literally:

        if error in ("lease_lost", "The source outbox lease was lost."):

    Neither string was ever emitted — `worker.py` produces thirteen other reasons —
    so `lease_lost` was dead code that could not increment, and a worker losing its
    lease every minute reported a flat zero. A metric that cannot fire is worse than
    no metric, because it reads as evidence that the condition never happens.

    The same lesson the fence learned (ADR 0033): do not use an error string as
    domain state. Branch on a typed reason and keep any free text in a separate
    field.
    """

    ALREADY_CANCELLED = "already_cancelled"
    ALREADY_SUCCEEDED = "already_succeeded"
    ALREADY_DEAD_LETTER = "already_dead_letter"
    LEASE_CLAIM_FAILED = "lease_claim_failed"
    LEASE_RENEWAL_FAILED = "lease_renewal_failed"
    LEASED_BY_ANOTHER_WORKER = "leased_by_another_worker"
    LEASE_LOST_BEFORE_COMMIT = "lease_lost_before_commit"
    MARK_SUCCEEDED_FAILED_LEASE_LOST = "mark_succeeded_failed_lease_lost"
    CONVERSATION_NOT_FOUND = "conversation_not_found"
    CONVERSATION_DELETED = "conversation_deleted"
    DELETION_EPOCH_ADVANCED = "deletion_epoch_advanced"
    FENCED_BY_SOURCE_MOVE = "fenced_by_source_move"
    PROHIBITED_CONTENT = "prohibited_content"
    PROVIDER_TRANSIENT = "provider_transient"
    PROVIDER_PERMANENT = "provider_permanent"
    UNEXPECTED_FAILURE = "unexpected_failure"
    WRONG_EVENT_FAMILY = "wrong_event_family"

    @property
    def is_lease_loss(self) -> bool:
        """Whether this reason means a lease the worker expected was not held.

        Every one of these was invisible to the counter before: the two strings it
        matched are not in the worker's vocabulary at all.

        `FENCED_BY_SOURCE_MOVE` is deliberately **not** here. A fence can mean a
        lease loss *or* a deleted conversation, and the worker carries the typed
        `FenceReason` in the result's detail so the two can be told apart. Counting
        a deletion as a lease loss would corrupt the signal in the other direction.
        """
        return self in _LEASE_LOSS_REASONS


#: Reasons that mean the worker did not hold the lease it acted on.
_LEASE_LOSS_REASONS = frozenset(
    {
        WorkerReason.LEASE_CLAIM_FAILED,
        WorkerReason.LEASE_RENEWAL_FAILED,
        WorkerReason.LEASED_BY_ANOTHER_WORKER,
        WorkerReason.LEASE_LOST_BEFORE_COMMIT,
        WorkerReason.MARK_SUCCEEDED_FAILED_LEASE_LOST,
    }
)


@dataclass
class WorkerCounters:
    """Process-lifetime totals for one worker.

    Plain integers rather than a metrics client: the worker has no HTTP surface
    in this design, so these are read by the process itself, logged, and asserted
    in tests. Wiring them to a metrics backend is a deployment concern.
    """

    claimed: int = 0
    processed: int = 0
    succeeded: int = 0
    retried: int = 0
    dead_lettered: int = 0
    cancelled: int = 0
    lease_lost: int = 0
    refused_foreign_event: int = 0
    sustained_empty_polls: int = 0
    polls: int = 0
    #: Unix seconds of the last completed poll; `0` means none yet.
    #:
    #: This is the worker's heartbeat, and it is the only thing that distinguishes
    #: "the worker is dead" from "the worker is idle" — a distinction readiness
    #: cannot make, because the API shares no state with a separate process. An
    #: empty queue looks identical in both cases; a heartbeat that stops advancing
    #: does not. Integer seconds so the whole mapping stays numbers-only, and
    #: operational metadata rather than content.
    last_successful_poll_at_epoch: int = 0

    def record_batch(self, results: list) -> None:
        """Fold one batch of `WorkerResult` into the counters.

        `sustained_empty_polls` resets on any claimed event, so it measures an
        unbroken run of empty polls rather than a lifetime total.
        """
        self.polls += 1
        # A poll reached the end of its batch, which is what "successful" means
        # here: the worker got an answer from the queue rather than dying mid-poll.
        self.last_successful_poll_at_epoch = int(time.time())
        self.claimed += len(results)
        if not results:
            self.sustained_empty_polls += 1
            return

        self.sustained_empty_polls = 0
        for result in results:
            self.processed += 1
            status = getattr(getattr(result, "status", None), "value", None)
            if status == "succeeded":
                self.succeeded += 1
            elif status == "pending":
                self.retried += 1
            elif status == "dead_letter":
                self.dead_lettered += 1
            elif status == "cancelled":
                self.cancelled += 1

            reason = getattr(result, "reason", None)
            if reason is WorkerReason.WRONG_EVENT_FAMILY:
                # Counted separately: the event was never this worker's, so it is
                # neither a lease loss nor a failure to process.
                self.refused_foreign_event += 1
            elif reason is not None and reason.is_lease_loss:
                self.lease_lost += 1

    def as_dict(self) -> dict[str, int]:
        """Return the counters as a plain mapping, safe to log.

        `last_successful_poll_at_epoch` rides along, so every poll line carries the
        heartbeat and a supervisor does not need a second signal to notice that the
        worker stopped.
        """
        return asdict(self)


class StaleHeartbeatError(RuntimeError):
    """The heartbeat could not be published or read as a fresh signal.

    Raised rather than silently swallowed because a heartbeat that quietly
    stops writing — or quietly reads as fresh forever — is exactly the
    condition it exists to expose (ADR 0029: the worker has no HTTP surface,
    so liveness is the process itself plus a heartbeat).
    """


class HeartbeatSink(Protocol):
    """Where a completed poll publishes its heartbeat.

    One method, deliberately: the sink receives the poll's own clock and does
    whatever a deployment needs with it. The default sink touches a file's
    mtime, which a container healthcheck can read without the worker exposing
    a port, an HTTP route, or a metrics endpoint.
    """

    def touch(self, epoch_seconds: int) -> None: ...


class FileHeartbeatSink:
    """Publish the heartbeat as a file's mtime.

    `os.utime` with explicit times, not a write: the beat carries no content,
    so there is nothing to leak into a mounted volume, and `utime` is one
    syscall. A parent directory that does not exist is a configuration defect
    and fails loudly at construction rather than on the first poll.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        parent = self._path.parent
        if not parent.is_dir():
            raise StaleHeartbeatError(
                f"The heartbeat directory does not exist: {parent}. Create it "
                "or point the heartbeat path at an existing directory."
            )

    @property
    def path(self) -> Path:
        return self._path

    def touch(self, epoch_seconds: int) -> None:
        try:
            # Create on first beat, then restamp: `os.utime` alone fails on a
            # path that does not exist yet, and the first poll is exactly when
            # the file must appear. `os.O_CREAT | os.O_EXCL` guards the
            # intentional creation so a pre-existing beat is never truncated
            # — the file carries no content, but the guard costs one flag and
            # makes the write-once-then-stamp shape explicit.
            try:
                fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                pass
            else:
                os.close(fd)
            os.utime(self._path, (epoch_seconds, epoch_seconds))
        except OSError as error:
            raise StaleHeartbeatError(
                "The heartbeat file could not be touched."
            ) from error


#: How far in the future a beat may sit before it is treated as a clock
#: disagreement rather than a fresh signal. A healthcheck that trusted a
#: future-dated mtime would report healthy forever after one bad stamp.
_HEARTBEAT_SKEW_TOLERANCE_SECONDS = 5.0


def touch_is_fresh(path: str | Path, max_age_seconds: float) -> bool:
    """Return whether the heartbeat file's last beat is recent enough.

    `max_age_seconds` should cover one poll interval plus one batch duration:
    the worker beats once per completed batch, so a healthy worker's file is
    never older than that. A missing file, a beat older than the bound, or a
    beat in the future beyond the tolerance is not fresh — the last because a
    wildly future mtime means the two clocks disagree, and "disagreement"
    must not read as "always fresh".
    """
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        return False
    now = time.time()
    if mtime > now + _HEARTBEAT_SKEW_TOLERANCE_SECONDS:
        return False
    return (now - mtime) <= max_age_seconds
