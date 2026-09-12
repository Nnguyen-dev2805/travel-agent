"""Memory write unit-of-work contract.

`MemoryWriteResult` lives here (not in the pure domain models) because
it describes a persistence outcome — stamped identifiers included —
while the domain package stays free of storage concepts. This module
imports the Child-2 contracts and the existing R9 security principal
only; it never touches SQLAlchemy, drivers, or the network, so the
protocol stays implementable against any backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from backend.memory.write_pipeline.models import (
    MemoryChangeSet,
    MemoryDecisionDraft,
    MemoryEvidence,
    MemoryOperation,
)
from backend.security.models import AuthenticatedPrincipal


class MemoryWriteError(Exception):
    """A memory write could not complete. Messages carry identifiers and
    governed reason codes only, never memory content or credentials."""


class CrossOwnerDeniedError(MemoryWriteError):
    """The principal does not own the change, record, or idempotency key."""


class StaleVersionError(MemoryWriteError):
    """The expected current version no longer matches stored state."""


class ConcurrentWriteError(MemoryWriteError):
    """A concurrent writer won the assertion; re-resolve and retry."""


class FenceReason(str, Enum):
    """Why a background memory write was fenced.

    These six causes were previously one free-text sentence. The worker could not
    branch on a sentence, so it treated all six identically — including "this
    worker lost its lease", which is a fact about one worker's tenure and says
    nothing about whether the conversation's other turns are still valid.

    The vocabulary is also what a future agent or tool event will extend, so the
    partition below is expressed once and asserted as total.
    """

    CONVERSATION_GONE = "conversation_gone"
    CONVERSATION_NOT_ACTIVE = "conversation_not_active"
    DELETION_EPOCH_MOVED = "deletion_epoch_moved"
    OUTBOX_EVENT_GONE = "outbox_event_gone"
    LEASE_LOST = "lease_lost"
    LEASE_EXPIRED = "lease_expired"

    @property
    def cancels_conversation_work(self) -> bool:
        """Whether this reason justifies cancelling the conversation's events.

        The rule, in one place: **cancel a conversation's remaining events only
        when the cause is a property of the conversation, never when it is a
        property of this worker's tenure.**

        `LEASE_LOST` and `LEASE_EXPIRED` are about one worker's tenure, so a
        worker that loses its lease cancels nothing: the event stays `LEASED` and
        becomes reclaimable when its window closes, and every other turn's
        `PENDING` event survives. `OUTBOX_EVENT_GONE` is about one event, and one
        event's absence says nothing about its siblings.
        """
        return self in _CONVERSATION_SHAPED_REASONS


#: Reasons that are properties of the conversation itself.
_CONVERSATION_SHAPED_REASONS = frozenset(
    {
        FenceReason.CONVERSATION_GONE,
        FenceReason.CONVERSATION_NOT_ACTIVE,
        FenceReason.DELETION_EPOCH_MOVED,
    }
)

#: The human-readable rendering of each reason, for logs.
_FENCE_MESSAGES = {
    FenceReason.CONVERSATION_GONE: "The source conversation is gone.",
    FenceReason.CONVERSATION_NOT_ACTIVE: "The source conversation is no longer active.",
    FenceReason.DELETION_EPOCH_MOVED: "The source conversation deletion epoch moved.",
    FenceReason.OUTBOX_EVENT_GONE: "The source outbox event is gone.",
    FenceReason.LEASE_LOST: "The source outbox lease was lost.",
    FenceReason.LEASE_EXPIRED: "The source outbox lease has expired.",
}


class FencedWriteError(MemoryWriteError):
    """The source conversation or outbox lease moved under this write.

    Raised when the fence check finds the conversation gone or no longer active,
    the deletion epoch advanced, the outbox event gone, or the lease lost or
    expired. The caller must treat the event as obsolete, never as successfully
    recorded.

    The reason is required and typed. It is the only thing that tells a caller
    whether cancelling the conversation's other work is justified — a decision
    that cannot be made from a message, which is why the message is derived from
    the reason rather than passed in.
    """

    def __init__(self, reason: FenceReason, message: str | None = None) -> None:
        if not isinstance(reason, FenceReason):
            raise TypeError(
                "FencedWriteError requires a FenceReason; a free-text reason is "
                "what made the six causes indistinguishable (ADR 0033)."
            )
        self.reason = reason
        super().__init__(message or _FENCE_MESSAGES[reason])


@dataclass(frozen=True)
class FenceContext:
    """Same-transaction fencing for a background memory write.

    Binds one write to the exact source state its extraction observed: the
    conversation must still be active at `expected_epoch`, and the outbox
    event must still be leased to `lease_owner`. Checked inside the write
    transaction so a delete landing between extraction and commit cannot
    slip a write through.
    """

    conversation_id: str
    expected_epoch: int
    outbox_id: str
    lease_owner: str


@dataclass(frozen=True)
class MemoryWriteResult:
    """One applied change: stamped identifiers plus the decided shape."""

    operation: MemoryOperation
    version_id: str | None
    superseded_version_ids: tuple[str, ...]
    reference_version_id: str | None
    decision_id: str | None
    reason: str


class MemoryUnitOfWork(Protocol):
    """Atomic, idempotent persistence boundary for resolved changes."""

    def apply_memory_change(
        self,
        change: MemoryChangeSet,
        principal: AuthenticatedPrincipal,
        *,
        evidence: tuple[MemoryEvidence, ...] = (),
        decision: MemoryDecisionDraft | None = None,
        idempotency_key: str | None = None,
        expected_version_id: str | None = None,
        fence: FenceContext | None = None,
    ) -> MemoryWriteResult:
        """Apply one resolved change atomically and idempotently.

        `evidence` and `decision` drafts are persisted alongside the
        version mutation in the same transaction when the operation
        writes anything. `idempotency_key`, when given, deduplicates
        redelivery to one semantic outcome. `expected_version_id`, when
        given, must match the stored current version or the write is
        rejected without touching state. `fence`, when given, is verified
        in the same transaction before any write; a moved fence raises
        `FencedWriteError` without touching state.
        """
        ...

    def get_active_versions(
        self, owner_user_id: str, canonical_key: str
    ) -> tuple[MemoryVersion, ...]:
        """Return the active versions for one owner and canonical key.

        Tenant-scoped: an implementation must bind `app.tenant` to
        `owner_user_id` for the duration of the read. A cross-owner read must
        return empty, never another owner's versions. An implementation that
        cannot perform the read must raise; it must not return an empty tuple,
        because an empty tuple is indistinguishable from a real empty history.
        """
        ...
