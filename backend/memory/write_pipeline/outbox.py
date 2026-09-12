"""Transactional Outbox repository and event contracts for memory extraction.

Implements the transactional outbox pattern (ADR 0014) for decoupling chat
message storage from background model extraction.
States: PENDING, LEASED, SUCCEEDED, DEAD_LETTER, CANCELLED.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Protocol, Sequence

# The event family this queue's Memory worker is allowed to process. It lives
# beside `OutboxIntent` because that is the module both the producer and this
# consumer already import; see its docstring for why the claim filters on it.
from backend.conversations.models import MEMORY_EXTRACT_EVENT_TYPE


class OutboxStatus(str, Enum):
    """Lifecycle state of an outbox event."""

    PENDING = "pending"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class OutboxEvent:
    """Immutable representation of one scheduled extraction event.

    `released_at` is the ADR 0027 readiness gate and is deliberately separate
    from `status`: `status` records where the event sits in its retry lifecycle,
    while `released_at` records whether the turn that produced it has finished.
    `None` means blocked, and a blocked event is not claimable whatever its
    status. The default is `None`, so an event constructed without an explicit
    release is blocked — the fail-closed direction.
    """

    outbox_id: str
    conversation_id: str
    message_id: str
    owner_user_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: OutboxStatus = OutboxStatus.PENDING
    attempt_count: int = 0
    lease_owner: str | None = None
    lease_until: datetime | None = None
    last_error: str | None = None
    next_attempt_after: datetime | None = None
    released_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


def _interval_seconds(seconds: float):
    """A PostgreSQL interval built from a bound number of seconds.

    `text()` with named notation rather than `func.make_interval(secs=...)`:
    SQLAlchemy renders function keyword arguments as `secs=:param`, and
    `make_interval` accepts only `secs => :param`. The rendered interval is
    asserted against the database in
    `backend/tests/integration/test_outbox_lease_authority.py` rather than assumed.
    """
    from sqlalchemy import text

    return text("make_interval(secs => :lease_interval_seconds)").bindparams(
        lease_interval_seconds=float(seconds)
    )


def calculate_backoff(
    attempt_count: int,
    base_seconds: float = 2.0,
    max_seconds: float = 60.0,
    jitter: bool = True,
    random_fn: Callable[[float, float], float] | None = None,
) -> float:
    """Calculate bounded exponential backoff duration in seconds with full jitter per ADR 0014."""
    if attempt_count <= 0:
        capped = base_seconds
    else:
        capped = min(base_seconds * (2 ** (attempt_count - 1)), max_seconds)
    if not jitter:
        return capped
    rf = random_fn or random.uniform
    return rf(0.0, capped)


class OutboxRepository(Protocol):
    """Protocol for outbox event persistence and lease management."""

    def save_event(self, event: OutboxEvent) -> None:
        """Persist or upsert an outbox event."""
        ...

    def get_event(self, outbox_id: str) -> OutboxEvent | None:
        """Retrieve an event by ID, or None if not found."""
        ...

    def claim_event(
        self,
        outbox_id: str,
        lease_owner: str,
        lease_duration_seconds: float,
    ) -> OutboxEvent | None:
        """Atomically claim a single outbox event under lease if available."""
        ...

    def claim_batch(
        self,
        lease_owner: str,
        lease_duration_seconds: float,
        limit: int = 10,
        debounce_seconds: float = 0.0,
    ) -> Sequence[OutboxEvent]:
        """Claim a batch of pending or expired-lease events, enforcing same-conversation serialization."""
        ...

    def renew_lease(
        self,
        outbox_id: str,
        lease_owner: str,
        lease_duration_seconds: float,
    ) -> bool:
        """Extend a lease this owner still holds, and report whether it did.

        `claim_event` cannot serve this: it matches only a *due* `pending` row or an
        *expired* lease, so it returns `None` for a live lease that merely has little
        time left — the exact case a renewal is for.

        Returns `False` when the row is not `leased` to this owner or its window has
        already closed, so a caller can stop instead of renewing into a lease it no
        longer holds. Never revives an expired lease: that would take the row from
        whoever is entitled to claim it next.
        """
        ...

    def mark_succeeded(
        self,
        outbox_id: str,
        lease_owner: str,
    ) -> bool:
        """Mark an event as succeeded if held under a valid lease by lease_owner."""
        ...

    def mark_failed(
        self,
        outbox_id: str,
        lease_owner: str,
        error_message: str,
        retryable: bool,
        max_attempts: int = 3,
        backoff_seconds: float = 10.0,
    ) -> OutboxStatus:
        """Record an attempt failure, scheduling retry or dead-lettering."""
        ...

    def cancel_events(
        self,
        conversation_id: str,
        reason: str,
        now: datetime = ...,
        lease_owner: str | None = ...,
    ) -> int:
        """Cancel a conversation's events, optionally only this worker's leases.

        `lease_owner=None` cancels every pending or leased event, which is what a
        deletion wants. A worker reacting to its own lost lease passes its own id
        so it cannot cancel work another worker has already claimed.
        """
        ...


class InMemoryOutboxRepository:
    """Thread-safe in-memory implementation of OutboxRepository for testing.

    **It mirrors the two claim predicates.** The ADR 0027 release gate and the
    event-family boundary are applied here exactly as `PostgresOutboxRepository`
    applies them, because a double that omits them can hand the worker an event
    production would never claim — and a unit test that passes on that input says
    nothing about production. A test that wants such an input must ask for it
    explicitly, with `PermissiveInMemoryOutboxRepository`.

    **One disclosed divergence: the clock.** `now` stays injectable so lease and
    back-off behaviour can be driven deterministically, and it is optional so the
    worker can call this double the same way it calls the real repository — which
    has no `now` parameter at all (ADR 0032). This double therefore decides lease
    validity from a local clock, which the real repository never does. Use it to
    drive worker control flow; prove lease authority against PostgreSQL in
    `backend/tests/integration/test_outbox_lease_authority.py`.
    """

    def __init__(self) -> None:
        self._events: dict[str, OutboxEvent] = {}

    @staticmethod
    def _is_claimable(event: OutboxEvent) -> bool:
        """The two predicates production applies before it will claim a row.

        ADR 0027's release gate — an event whose turn is not terminal is invisible
        to the worker whatever its status — and the event-family boundary, which
        keeps a worker from extracting a conversation range out of an event of
        another family. Applied to both branches, as production does, so a
        `leased` row whose turn is unfinished is not reclaimable on lease expiry.
        """
        return (
            event.released_at is not None
            and event.event_type == MEMORY_EXTRACT_EVENT_TYPE
        )

    def save_event(self, event: OutboxEvent) -> None:
        self._events[event.outbox_id] = event

    def get_event(self, outbox_id: str) -> OutboxEvent | None:
        return self._events.get(outbox_id)

    def claim_event(
        self,
        outbox_id: str,
        lease_owner: str,
        lease_duration_seconds: float,
        now: datetime | None = None,
    ) -> OutboxEvent | None:
        if now is None:
            now = utc_now()
        ev = self._events.get(outbox_id)
        if ev is None:
            return None
        if not self._is_claimable(ev):
            return None
        # Must be PENDING (and backoff passed) or expired LEASED
        if ev.status == OutboxStatus.PENDING:
            if ev.next_attempt_after is not None and ev.next_attempt_after > now:
                return None
        elif ev.status == OutboxStatus.LEASED:
            # Production reclaims a `LEASED` row only when its window has closed
            # (`lease_until < now()`), for any worker, holder included: identity
            # is not the criterion, the closed window is. The previous predicate
            # matched on `lease_owner != lease_owner`, which let the *same*
            # owner reclaim a lease with hours of its window left — input
            # production would never hand over.
            if ev.lease_until is None or ev.lease_until >= now:
                return None
        else:
            return None

        updated = replace(
            ev,
            status=OutboxStatus.LEASED,
            lease_owner=lease_owner,
            lease_until=now + timedelta(seconds=lease_duration_seconds),
            attempt_count=ev.attempt_count + 1,
            updated_at=now,
        )
        self._events[outbox_id] = updated
        return updated

    def claim_batch(
        self,
        lease_owner: str,
        lease_duration_seconds: float,
        now: datetime | None = None,
        limit: int = 10,
        debounce_seconds: float = 0.0,
    ) -> Sequence[OutboxEvent]:
        if now is None:
            now = utc_now()
        lease_until = now + timedelta(seconds=lease_duration_seconds)

        # Collect currently active leased conversation IDs
        active_leased_conversations = {
            ev.conversation_id
            for ev in self._events.values()
            if ev.status == OutboxStatus.LEASED
            and ev.lease_until is not None
            and ev.lease_until >= now
        }

        candidates: list[OutboxEvent] = []
        for ev in self._events.values():
            if not self._is_claimable(ev):
                continue
            if debounce_seconds > 0.0 and (now - ev.created_at).total_seconds() < debounce_seconds:
                continue
            if ev.conversation_id in active_leased_conversations:
                continue
            if ev.status == OutboxStatus.PENDING:
                if ev.next_attempt_after is None or ev.next_attempt_after <= now:
                    candidates.append(ev)
            elif ev.status == OutboxStatus.LEASED:
                if ev.lease_until is not None and ev.lease_until < now:
                    candidates.append(ev)

        # FIFO ordering by created_at
        candidates.sort(key=lambda x: x.created_at)

        claimed: list[OutboxEvent] = []
        leased_in_batch: set[str] = set()
        for ev in candidates:
            if len(claimed) >= limit:
                break
            if ev.conversation_id in leased_in_batch:
                continue
            leased_in_batch.add(ev.conversation_id)
            updated = replace(
                ev,
                status=OutboxStatus.LEASED,
                lease_owner=lease_owner,
                lease_until=lease_until,
                attempt_count=ev.attempt_count + 1,
                updated_at=now,
            )
            self._events[ev.outbox_id] = updated
            claimed.append(updated)

        return tuple(claimed)

    def renew_lease(
        self,
        outbox_id: str,
        lease_owner: str,
        lease_duration_seconds: float,
        now: datetime | None = None,
    ) -> bool:
        if now is None:
            now = utc_now()
        ev = self._events.get(outbox_id)
        if ev is None or ev.status is not OutboxStatus.LEASED:
            return False
        if ev.lease_owner != lease_owner:
            return False
        if ev.lease_until is not None and ev.lease_until < now:
            return False
        self._events[outbox_id] = replace(
            ev,
            lease_until=now + timedelta(seconds=lease_duration_seconds),
            updated_at=now,
        )
        return True

    def mark_succeeded(
        self,
        outbox_id: str,
        lease_owner: str,
        now: datetime | None = None,
    ) -> bool:
        if now is None:
            now = utc_now()
        ev = self._events.get(outbox_id)
        if ev is None:
            return False
        if ev.status != OutboxStatus.LEASED:
            return False
        if ev.lease_owner != lease_owner:
            return False
        if ev.lease_until is not None and ev.lease_until < now:
            return False

        self._events[outbox_id] = replace(
            ev,
            status=OutboxStatus.SUCCEEDED,
            lease_owner=None,
            lease_until=None,
            updated_at=now,
        )
        return True

    def mark_failed(
        self,
        outbox_id: str,
        lease_owner: str,
        error_message: str,
        retryable: bool,
        max_attempts: int = 3,
        backoff_seconds: float = 10.0,
        now: datetime | None = None,
    ) -> OutboxStatus:
        if now is None:
            now = utc_now()
        ev = self._events.get(outbox_id)
        if ev is None:
            return OutboxStatus.DEAD_LETTER

        # Mirror the Postgres contract: a caller that no longer holds the lease
        # must not reset the event or clear a newer worker's lease.
        holds_lease = (
            ev.status is OutboxStatus.LEASED
            and ev.lease_owner == lease_owner
            and (ev.lease_until is None or ev.lease_until >= now)
        )
        if not holds_lease:
            return ev.status

        if retryable and ev.attempt_count < max_attempts:
            new_status = OutboxStatus.PENDING
            next_attempt = now + timedelta(seconds=backoff_seconds)
        else:
            new_status = OutboxStatus.DEAD_LETTER
            next_attempt = None

        self._events[outbox_id] = replace(
            ev,
            status=new_status,
            lease_owner=None,
            lease_until=None,
            last_error=error_message,
            next_attempt_after=next_attempt,
            updated_at=now,
        )
        return new_status

    def cancel_events(
        self,
        conversation_id: str,
        reason: str,
        now: datetime | None = None,
        lease_owner: str | None = None,
    ) -> int:
        """Cancel a conversation's work, optionally only this worker's leases.

        `lease_owner=None` cancels every pending or leased event, which is what a
        deletion wants. A worker reacting to its own lost lease must pass its own
        id, or it cancels work another worker has already claimed.
        """
        if now is None:
            now = utc_now()
        cancelled_count = 0
        for ev in list(self._events.values()):
            if ev.conversation_id != conversation_id:
                continue
            if ev.status not in (OutboxStatus.PENDING, OutboxStatus.LEASED):
                continue
            if (
                lease_owner is not None
                and ev.status is OutboxStatus.LEASED
                and ev.lease_owner != lease_owner
            ):
                continue
            self._events[ev.outbox_id] = replace(
                ev,
                status=OutboxStatus.CANCELLED,
                lease_owner=None,
                lease_until=None,
                last_error=reason,
                updated_at=now,
            )
            cancelled_count += 1
        return cancelled_count


class PermissiveInMemoryOutboxRepository(InMemoryOutboxRepository):
    """Deliberately **not** faithful: it claims what production would refuse.

    It omits the release gate and the event-family boundary, so it can hand the
    worker an event the real repository would never claim. That input is the whole
    reason the worker carries defence-in-depth layers, and a faithful double
    cannot produce it — which is why the layers would otherwise be untestable
    through the batch path.

    Use it only for that. Anything that is not testing a defence-in-depth layer
    wants `InMemoryOutboxRepository`, or the test will pass on input production
    refuses and mean nothing.
    """

    @staticmethod
    def _is_claimable(_event: OutboxEvent) -> bool:
        return True


class PostgresOutboxRepository:
    """PostgreSQL-backed implementation of OutboxRepository using SQLAlchemy."""

    def __init__(self, engine: Any, table: Any | None = None) -> None:
        self._engine = engine
        if table is None:
            from backend.conversations.postgres_repository import conversation_outbox_table

            self._table = conversation_outbox_table
        else:
            self._table = table

    def save_event(self, event: OutboxEvent) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(self._table).values(
            outbox_id=event.outbox_id,
            conversation_id=event.conversation_id,
            message_id=event.message_id,
            owner_user_id=event.owner_user_id,
            event_type=event.event_type,
            payload=event.payload,
            status=event.status.value,
            attempt_count=event.attempt_count,
            lease_owner=event.lease_owner,
            lease_until=event.lease_until,
            last_error=event.last_error,
            next_attempt_after=event.next_attempt_after,
            released_at=event.released_at,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[self._table.c.outbox_id],
            set_={
                "status": event.status.value,
                "attempt_count": event.attempt_count,
                "lease_owner": event.lease_owner,
                "lease_until": event.lease_until,
                "last_error": event.last_error,
                "next_attempt_after": event.next_attempt_after,
                "released_at": event.released_at,
                "updated_at": event.updated_at,
            },
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)

    def get_event(self, outbox_id: str) -> OutboxEvent | None:
        from sqlalchemy import select

        with self._engine.begin() as conn:
            row = conn.execute(
                select(self._table).where(self._table.c.outbox_id == outbox_id)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_event(row)

    def claim_event(
        self,
        outbox_id: str,
        lease_owner: str,
        lease_duration_seconds: float,
    ) -> OutboxEvent | None:
        from sqlalchemy import and_, func, or_, select

        with self._engine.begin() as conn:
            # ADR 0030: the single-event path takes the same per-conversation
            # lock as the batch path. Without it a worker re-claiming an expired
            # lease could still take an event out from under a peer that is
            # claiming the same conversation.
            conversation_id = conn.execute(
                select(self._table.c.conversation_id).where(
                    self._table.c.outbox_id == outbox_id
                )
            ).scalar_one_or_none()
            if conversation_id is None:
                return None
            if not self._lock_conversations(conn, [conversation_id]):
                return None

            stmt = (
                select(self._table.c.outbox_id)
                .where(
                    and_(
                        self._table.c.outbox_id == outbox_id,
                        # The family boundary. Without it a second event family
                        # on this shared queue would be claimed and extracted as
                        # if it were a conversation range.
                        self._table.c.event_type == MEMORY_EXTRACT_EVENT_TYPE,
                        # ADR 0027: a blocked event is not claimable at all, in
                        # either branch. The gate applies to the whole condition
                        # rather than to `pending` alone, so a `leased` row whose
                        # turn is not finished is not reclaimable on lease expiry.
                        self._table.c.released_at.is_not(None),
                        or_(
                            and_(
                                self._table.c.status == OutboxStatus.PENDING.value,
                                or_(
                                    self._table.c.next_attempt_after.is_(None),
                                    self._table.c.next_attempt_after <= func.now(),
                                ),
                            ),
                            and_(
                                self._table.c.status == OutboxStatus.LEASED.value,
                                self._table.c.lease_until.is_not(None),
                                self._table.c.lease_until < func.now(),
                            ),
                        ),
                    )
                )
                .with_for_update(skip_locked=True)
            )
            row = conn.execute(stmt).fetchone()
            if row is None:
                return None

            update_stmt = (
                self._table.update()
                .where(self._table.c.outbox_id == outbox_id)
                .values(
                    status=OutboxStatus.LEASED.value,
                    lease_owner=lease_owner,
                    lease_until=func.now() + _interval_seconds(lease_duration_seconds),
                    attempt_count=self._table.c.attempt_count + 1,
                    updated_at=func.now(),
                )
            )
            conn.execute(update_stmt)
            fetch_stmt = select(self._table).where(self._table.c.outbox_id == outbox_id)
            updated_row = conn.execute(fetch_stmt).fetchone()
            return self._row_to_event(updated_row) if updated_row else None

    @staticmethod
    def _lock_conversations(conn: Any, conversation_ids: Sequence[str]) -> list[str]:
        """Take a transaction-scoped advisory lock per conversation (ADR 0030).

        Returns the conversations whose lock this transaction now holds, in the
        order given. A conversation another transaction is already claiming is
        omitted, so the caller skips it rather than double-claiming its events.

        The lock needs no table privilege, which matters because the worker binds
        no tenant at claim time and therefore cannot see a `conversations` row to
        lock. It is keyed by a hash of the conversation id: a collision between
        two conversations costs a skipped claim in one poll, never correctness.

        `pg_try_...` never blocks, and `FOR UPDATE SKIP LOCKED` never blocks, so
        no lock ordering can deadlock two claimants.
        """
        from sqlalchemy import text

        held: list[str] = []
        for conversation_id in conversation_ids:
            acquired = conn.execute(
                text(
                    "SELECT pg_try_advisory_xact_lock("
                    "hashtextextended(:conversation_id, 0))"
                ),
                {"conversation_id": conversation_id},
            ).scalar()
            if acquired:
                held.append(conversation_id)
        return held

    def claim_batch(
        self,
        lease_owner: str,
        lease_duration_seconds: float,
        limit: int = 10,
        debounce_seconds: float = 0.0,
    ) -> Sequence[OutboxEvent]:
        from sqlalchemy import and_, exists, func, not_, or_, select

        debounce_cutoff = (
            func.now() - _interval_seconds(debounce_seconds)
            if debounce_seconds > 0.0
            else None
        )

        o2 = self._table.alias("o2")
        active_lease_exists = exists(
            select(o2.c.outbox_id).where(
                and_(
                    o2.c.conversation_id == self._table.c.conversation_id,
                    o2.c.status == OutboxStatus.LEASED.value,
                    o2.c.lease_until >= func.now(),
                )
            )
        )

        with self._engine.begin() as conn:
            conditions = [
                not_(active_lease_exists),
                # The family boundary, applied before any row is locked so an
                # event of another family is never even a candidate.
                self._table.c.event_type == MEMORY_EXTRACT_EVENT_TYPE,
                # ADR 0027: an event whose turn is not finished is invisible to
                # the worker, whatever its status. Applied to the whole condition
                # so the lease-expiry branch is gated too.
                self._table.c.released_at.is_not(None),
                or_(
                    and_(
                        self._table.c.status == OutboxStatus.PENDING.value,
                        or_(
                            self._table.c.next_attempt_after.is_(None),
                            self._table.c.next_attempt_after <= func.now(),
                        ),
                    ),
                    and_(
                        self._table.c.status == OutboxStatus.LEASED.value,
                        self._table.c.lease_until.is_not(None),
                        self._table.c.lease_until < func.now(),
                    ),
                ),
            ]
            if debounce_cutoff is not None:
                conditions.append(self._table.c.created_at <= debounce_cutoff)

            # ADR 0030: serialise claiming per conversation *before* touching its
            # rows. `active_lease_exists` is a read-time predicate and
            # `FOR UPDATE SKIP LOCKED` locks only the rows selected, so two
            # workers selecting different rows of one conversation never blocked
            # each other and both claimed.
            #
            # Ordered by the oldest waiting work, with the conversation id as a
            # tie-break, so two workers see the same order and neither starves.
            candidate_conversations = [
                row[0]
                for row in conn.execute(
                    select(self._table.c.conversation_id)
                    .where(and_(*conditions))
                    .group_by(self._table.c.conversation_id)
                    .order_by(
                        func.min(self._table.c.created_at).asc(),
                        self._table.c.conversation_id.asc(),
                    )
                    .limit(limit * 2)
                ).fetchall()
            ]
            if not candidate_conversations:
                return ()

            locked = self._lock_conversations(conn, candidate_conversations)
            if not locked:
                return ()

            # Query candidate outbox records with FOR UPDATE SKIP LOCKED, limited
            # to the conversations this transaction holds.
            stmt = (
                select(self._table.c.outbox_id, self._table.c.conversation_id)
                .where(
                    and_(
                        *conditions,
                        self._table.c.conversation_id.in_(locked),
                    )
                )
                .order_by(self._table.c.created_at.asc())
                .limit(limit * 2)
                .with_for_update(skip_locked=True)
            )
            rows = conn.execute(stmt).fetchall()
            if not rows:
                return ()

            claimed_ids = []
            seen_convs = set()
            for outbox_id, conv_id in rows:
                if conv_id in seen_convs:
                    continue
                seen_convs.add(conv_id)
                claimed_ids.append(outbox_id)
                if len(claimed_ids) >= limit:
                    break

            if not claimed_ids:
                return ()

            update_stmt = (
                self._table.update()
                .where(self._table.c.outbox_id.in_(claimed_ids))
                .values(
                    status=OutboxStatus.LEASED.value,
                    lease_owner=lease_owner,
                    lease_until=func.now() + _interval_seconds(lease_duration_seconds),
                    attempt_count=self._table.c.attempt_count + 1,
                    updated_at=func.now(),
                )
            )
            conn.execute(update_stmt)

            fetch_stmt = (
                select(self._table)
                .where(self._table.c.outbox_id.in_(claimed_ids))
                .order_by(self._table.c.created_at.asc())
            )
            updated_rows = conn.execute(fetch_stmt).fetchall()
            return tuple(self._row_to_event(r) for r in updated_rows)

    def renew_lease(
        self,
        outbox_id: str,
        lease_owner: str,
        lease_duration_seconds: float,
    ) -> bool:
        from sqlalchemy import and_, func, or_

        with self._engine.begin() as conn:
            stmt = (
                self._table.update()
                .where(
                    and_(
                        self._table.c.outbox_id == outbox_id,
                        self._table.c.status == OutboxStatus.LEASED.value,
                        self._table.c.lease_owner == lease_owner,
                        # The window must still be open. Without this a caller could
                        # renew a lease that had already lapsed, taking the row from
                        # whoever is entitled to claim it next.
                        or_(
                            self._table.c.lease_until.is_(None),
                            self._table.c.lease_until >= func.now(),
                        ),
                    )
                )
                .values(
                    lease_until=func.now() + _interval_seconds(lease_duration_seconds),
                    updated_at=func.now(),
                )
            )
            return conn.execute(stmt).rowcount > 0

    def mark_succeeded(
        self,
        outbox_id: str,
        lease_owner: str,
    ) -> bool:
        from sqlalchemy import and_, func, or_

        with self._engine.begin() as conn:
            stmt = (
                self._table.update()
                .where(
                    and_(
                        self._table.c.outbox_id == outbox_id,
                        self._table.c.status == OutboxStatus.LEASED.value,
                        self._table.c.lease_owner == lease_owner,
                        or_(
                            self._table.c.lease_until.is_(None),
                            self._table.c.lease_until >= func.now(),
                        ),
                    )
                )
                .values(
                    status=OutboxStatus.SUCCEEDED.value,
                    lease_owner=None,
                    lease_until=None,
                    updated_at=func.now(),
                )
            )
            res = conn.execute(stmt)
            return res.rowcount > 0

    def mark_failed(
        self,
        outbox_id: str,
        lease_owner: str,
        error_message: str,
        retryable: bool,
        max_attempts: int = 3,
        backoff_seconds: float = 10.0,
    ) -> OutboxStatus:
        from sqlalchemy import func, or_, select

        with self._engine.begin() as conn:
            # The lease window is judged by the statement that reads the row, not
            # by a timestamp the caller chose. A caller that captured `now` before
            # a model call of unbounded duration would otherwise report an expired
            # lease as held — the defect this replaces.
            lease_held = or_(
                self._table.c.lease_until.is_(None),
                self._table.c.lease_until >= func.now(),
            ).label("lease_held")
            row = conn.execute(
                select(
                    self._table.c.attempt_count,
                    self._table.c.status,
                    self._table.c.lease_owner,
                    lease_held,
                )
                .where(self._table.c.outbox_id == outbox_id)
                .with_for_update()
            ).fetchone()
            if row is None:
                return OutboxStatus.DEAD_LETTER

            attempt_count, raw_status, holder, lease_held_now = row
            current = OutboxStatus(raw_status)

            # The caller must still hold the lease. Without this check an old
            # worker whose lease had expired and been re-claimed could clear the
            # new worker's lease and reset the event. `mark_succeeded` already
            # required the holder and the lease window; this path required
            # neither. A caller that lost the lease gets the current status back,
            # unchanged, so the worker reports the truth instead of overwriting it.
            holds_lease = (
                current is OutboxStatus.LEASED
                and holder == lease_owner
                and bool(lease_held_now)
            )
            if not holds_lease:
                return current

            if retryable and attempt_count < max_attempts:
                new_status = OutboxStatus.PENDING
                next_attempt = func.now() + _interval_seconds(backoff_seconds)
            else:
                new_status = OutboxStatus.DEAD_LETTER
                next_attempt = None

            conn.execute(
                self._table.update()
                .where(self._table.c.outbox_id == outbox_id)
                .values(
                    status=new_status.value,
                    lease_owner=None,
                    lease_until=None,
                    last_error=error_message,
                    next_attempt_after=next_attempt,
                    updated_at=func.now(),
                )
            )
            return new_status

    def cancel_events(
        self,
        conversation_id: str,
        reason: str,
        now: datetime | None = None,
        lease_owner: str | None = None,
    ) -> int:
        """Cancel a conversation's events, optionally only this worker's leases.

        `lease_owner=None` cancels every pending or leased event, which is what a
        deletion wants. A worker reacting to its own lost lease passes its own id,
        so it cannot cancel an event another worker has already claimed — which
        is exactly what happened when every `FencedWriteError` cancelled the whole
        conversation.
        """
        from sqlalchemy import and_, or_

        if now is None:
            now = utc_now()

        conditions = [
            self._table.c.conversation_id == conversation_id,
            self._table.c.status.in_(
                [OutboxStatus.PENDING.value, OutboxStatus.LEASED.value]
            ),
        ]
        if lease_owner is not None:
            # A pending row has no holder, so it is always this conversation's to
            # cancel; a leased row belongs to whoever holds it.
            conditions.append(
                or_(
                    self._table.c.status == OutboxStatus.PENDING.value,
                    and_(
                        self._table.c.status == OutboxStatus.LEASED.value,
                        self._table.c.lease_owner == lease_owner,
                    ),
                )
            )

        with self._engine.begin() as conn:
            stmt = (
                self._table.update()
                .where(and_(*conditions))
                .values(
                    status=OutboxStatus.CANCELLED.value,
                    lease_owner=None,
                    lease_until=None,
                    last_error=reason,
                    updated_at=now,
                )
            )
            res = conn.execute(stmt)
            return res.rowcount

    def _row_to_event(self, row: Any) -> OutboxEvent:
        mapping = row._mapping if hasattr(row, "_mapping") else row
        return OutboxEvent(
            outbox_id=mapping["outbox_id"],
            conversation_id=mapping["conversation_id"],
            message_id=mapping["message_id"],
            owner_user_id=mapping["owner_user_id"],
            event_type=mapping["event_type"],
            payload=dict(mapping["payload"]) if mapping["payload"] else {},
            status=OutboxStatus(mapping["status"]),
            attempt_count=int(mapping["attempt_count"]),
            lease_owner=mapping["lease_owner"],
            lease_until=mapping["lease_until"],
            last_error=mapping["last_error"],
            next_attempt_after=mapping["next_attempt_after"],
            released_at=mapping["released_at"],
            created_at=mapping["created_at"],
            updated_at=mapping.get("updated_at") or mapping["created_at"],
        )

