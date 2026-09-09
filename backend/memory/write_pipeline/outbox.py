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
    """Immutable representation of one scheduled extraction event."""

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
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


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
        now: datetime,
    ) -> OutboxEvent | None:
        """Atomically claim a single outbox event under lease if available."""
        ...

    def claim_batch(
        self,
        lease_owner: str,
        lease_duration_seconds: float,
        now: datetime,
        limit: int = 10,
        debounce_seconds: float = 0.0,
    ) -> Sequence[OutboxEvent]:
        """Claim a batch of pending or expired-lease events, enforcing same-conversation serialization."""
        ...

    def mark_succeeded(
        self,
        outbox_id: str,
        lease_owner: str,
        now: datetime,
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
        now: datetime = ...,
    ) -> OutboxStatus:
        """Record an attempt failure, scheduling retry or dead-lettering."""
        ...

    def cancel_events(
        self,
        conversation_id: str,
        reason: str,
        now: datetime = ...,
    ) -> int:
        """Cancel all pending or leased events for a conversation."""
        ...


class InMemoryOutboxRepository:
    """Thread-safe in-memory implementation of OutboxRepository for testing."""

    def __init__(self) -> None:
        self._events: dict[str, OutboxEvent] = {}

    def save_event(self, event: OutboxEvent) -> None:
        self._events[event.outbox_id] = event

    def get_event(self, outbox_id: str) -> OutboxEvent | None:
        return self._events.get(outbox_id)

    def claim_event(
        self,
        outbox_id: str,
        lease_owner: str,
        lease_duration_seconds: float,
        now: datetime,
    ) -> OutboxEvent | None:
        ev = self._events.get(outbox_id)
        if ev is None:
            return None
        # Must be PENDING (and backoff passed) or expired LEASED
        if ev.status == OutboxStatus.PENDING:
            if ev.next_attempt_after is not None and ev.next_attempt_after > now:
                return None
        elif ev.status == OutboxStatus.LEASED:
            if ev.lease_until is not None and ev.lease_until >= now and ev.lease_owner != lease_owner:
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
        now: datetime,
        limit: int = 10,
        debounce_seconds: float = 0.0,
    ) -> Sequence[OutboxEvent]:
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

    def mark_succeeded(
        self,
        outbox_id: str,
        lease_owner: str,
        now: datetime,
    ) -> bool:
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
    ) -> int:
        if now is None:
            now = utc_now()
        cancelled_count = 0
        for ev in list(self._events.values()):
            if ev.conversation_id == conversation_id and ev.status in (
                OutboxStatus.PENDING,
                OutboxStatus.LEASED,
            ):
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
        now: datetime,
    ) -> OutboxEvent | None:
        from sqlalchemy import and_, or_, select

        lease_until = now + timedelta(seconds=lease_duration_seconds)
        with self._engine.begin() as conn:
            stmt = (
                select(self._table.c.outbox_id)
                .where(
                    and_(
                        self._table.c.outbox_id == outbox_id,
                        or_(
                            and_(
                                self._table.c.status == OutboxStatus.PENDING.value,
                                or_(
                                    self._table.c.next_attempt_after.is_(None),
                                    self._table.c.next_attempt_after <= now,
                                ),
                            ),
                            and_(
                                self._table.c.status == OutboxStatus.LEASED.value,
                                self._table.c.lease_until.is_not(None),
                                self._table.c.lease_until < now,
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
                    lease_until=lease_until,
                    attempt_count=self._table.c.attempt_count + 1,
                    updated_at=now,
                )
            )
            conn.execute(update_stmt)
            fetch_stmt = select(self._table).where(self._table.c.outbox_id == outbox_id)
            updated_row = conn.execute(fetch_stmt).fetchone()
            return self._row_to_event(updated_row) if updated_row else None

    def claim_batch(
        self,
        lease_owner: str,
        lease_duration_seconds: float,
        now: datetime,
        limit: int = 10,
        debounce_seconds: float = 0.0,
    ) -> Sequence[OutboxEvent]:
        from sqlalchemy import and_, exists, not_, or_, select

        lease_until = now + timedelta(seconds=lease_duration_seconds)
        debounce_cutoff = now - timedelta(seconds=debounce_seconds) if debounce_seconds > 0.0 else None

        o2 = self._table.alias("o2")
        active_lease_exists = exists(
            select(o2.c.outbox_id).where(
                and_(
                    o2.c.conversation_id == self._table.c.conversation_id,
                    o2.c.status == OutboxStatus.LEASED.value,
                    o2.c.lease_until >= now,
                )
            )
        )

        with self._engine.begin() as conn:
            conditions = [
                not_(active_lease_exists),
                or_(
                    and_(
                        self._table.c.status == OutboxStatus.PENDING.value,
                        or_(
                            self._table.c.next_attempt_after.is_(None),
                            self._table.c.next_attempt_after <= now,
                        ),
                    ),
                    and_(
                        self._table.c.status == OutboxStatus.LEASED.value,
                        self._table.c.lease_until.is_not(None),
                        self._table.c.lease_until < now,
                    ),
                ),
            ]
            if debounce_cutoff is not None:
                conditions.append(self._table.c.created_at <= debounce_cutoff)

            # Query candidate outbox records with FOR UPDATE SKIP LOCKED
            stmt = (
                select(self._table.c.outbox_id, self._table.c.conversation_id)
                .where(and_(*conditions))
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
                    lease_until=lease_until,
                    attempt_count=self._table.c.attempt_count + 1,
                    updated_at=now,
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

    def mark_succeeded(
        self,
        outbox_id: str,
        lease_owner: str,
        now: datetime,
    ) -> bool:
        from sqlalchemy import and_, or_

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
                            self._table.c.lease_until >= now,
                        ),
                    )
                )
                .values(
                    status=OutboxStatus.SUCCEEDED.value,
                    lease_owner=None,
                    lease_until=None,
                    updated_at=now,
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
        now: datetime | None = None,
    ) -> OutboxStatus:
        from sqlalchemy import select

        if now is None:
            now = utc_now()

        with self._engine.begin() as conn:
            row = conn.execute(
                select(self._table.c.attempt_count)
                .where(self._table.c.outbox_id == outbox_id)
                .with_for_update()
            ).fetchone()
            if row is None:
                return OutboxStatus.DEAD_LETTER

            attempt_count = row[0]
            if retryable and attempt_count < max_attempts:
                new_status = OutboxStatus.PENDING
                next_attempt = now + timedelta(seconds=backoff_seconds)
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
                    updated_at=now,
                )
            )
            return new_status

    def cancel_events(
        self,
        conversation_id: str,
        reason: str,
        now: datetime | None = None,
    ) -> int:
        if now is None:
            now = utc_now()

        with self._engine.begin() as conn:
            stmt = (
                self._table.update()
                .where(
                    self._table.c.conversation_id == conversation_id,
                    self._table.c.status.in_(
                        [OutboxStatus.PENDING.value, OutboxStatus.LEASED.value]
                    ),
                )
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
            created_at=mapping["created_at"],
            updated_at=mapping.get("updated_at") or mapping["created_at"],
        )

