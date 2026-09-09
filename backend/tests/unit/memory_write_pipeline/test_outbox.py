"""Unit tests for the memory write pipeline outbox contracts and lifecycle.

Covers:
- States PENDING, LEASED, SUCCEEDED, DEAD_LETTER, CANCELLED
- Lease claim, duration, expiry, and renewal
- Idempotent claim and parallel owner partitioning
- Deletion cancellation when source conversation is removed
- Retry classification, backoff calculation, and dead-lettering after max attempts
"""

from datetime import datetime, timedelta, timezone
import pytest

from backend.conversations.models import (
    ConversationValidationError,
    OutboxIntent,
    coerce_outbox_intent,
)
from backend.memory.write_pipeline.outbox import (
    OutboxEvent,
    OutboxStatus,
    InMemoryOutboxRepository,
    calculate_backoff,
)

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 9, 7, 12, 10, 0, tzinfo=timezone.utc)


def _sample_event(
    outbox_id="cout_1",
    conversation_id="conv_1",
    message_id="msg_1",
    owner_user_id="owner_1",
    event_type="memory.extract.conversation_range",
    payload=None,
    status=OutboxStatus.PENDING,
    created_at=MOMENT,
):
    return OutboxEvent(
        outbox_id=outbox_id,
        conversation_id=conversation_id,
        message_id=message_id,
        owner_user_id=owner_user_id,
        event_type=event_type,
        payload=payload or {"conversation_id": conversation_id, "message_id": message_id},
        status=status,
        created_at=created_at,
    )


def test_outbox_event_immutability_and_defaults():
    event = _sample_event()
    assert event.status == OutboxStatus.PENDING
    assert event.attempt_count == 0
    assert event.lease_owner is None
    assert event.lease_until is None
    with pytest.raises(AttributeError):
        event.status = OutboxStatus.LEASED  # frozen dataclass


def test_claim_batch_transitions_pending_to_leased():
    repo = InMemoryOutboxRepository()
    repo.save_event(_sample_event("cout_1", conversation_id="conv_1", created_at=MOMENT))
    repo.save_event(_sample_event("cout_2", conversation_id="conv_2", created_at=MOMENT + timedelta(seconds=1)))

    claimed = repo.claim_batch(
        lease_owner="worker_1",
        lease_duration_seconds=30.0,
        now=MOMENT,
        limit=10,
    )

    assert len(claimed) == 2
    assert claimed[0].outbox_id == "cout_1"
    assert claimed[0].status == OutboxStatus.LEASED
    assert claimed[0].lease_owner == "worker_1"
    assert claimed[0].lease_until == MOMENT + timedelta(seconds=30.0)
    assert claimed[0].attempt_count == 1

    # Second claim by another worker should return nothing since they are leased
    empty = repo.claim_batch(
        lease_owner="worker_2",
        lease_duration_seconds=30.0,
        now=MOMENT,
        limit=10,
    )
    assert len(empty) == 0


def test_claim_batch_same_conversation_serialization():
    repo = InMemoryOutboxRepository()
    # Two events in the SAME conversation
    repo.save_event(_sample_event("cout_1", conversation_id="conv_1", created_at=MOMENT))
    repo.save_event(_sample_event("cout_2", conversation_id="conv_1", created_at=MOMENT + timedelta(seconds=1)))

    claimed = repo.claim_batch(
        lease_owner="worker_1",
        lease_duration_seconds=30.0,
        now=MOMENT,
        limit=10,
    )

    # At most 1 event per conversation can be leased concurrently
    assert len(claimed) == 1
    assert claimed[0].outbox_id == "cout_1"


def test_claim_batch_debounce():
    repo = InMemoryOutboxRepository()
    # Event created at MOMENT
    repo.save_event(_sample_event("cout_1", created_at=MOMENT))

    # At MOMENT + 2s, with debounce_seconds=5.0, event is not ready (created_at + 5s > now)
    claimed = repo.claim_batch(
        lease_owner="worker_1",
        lease_duration_seconds=30.0,
        now=MOMENT + timedelta(seconds=2),
        debounce_seconds=5.0,
    )
    assert len(claimed) == 0

    # At MOMENT + 5s, event is ready
    claimed_ready = repo.claim_batch(
        lease_owner="worker_1",
        lease_duration_seconds=30.0,
        now=MOMENT + timedelta(seconds=5),
        debounce_seconds=5.0,
    )
    assert len(claimed_ready) == 1
    assert claimed_ready[0].outbox_id == "cout_1"


def test_claim_expired_lease_reclaims_event():
    repo = InMemoryOutboxRepository()
    repo.save_event(_sample_event("cout_1", created_at=MOMENT))

    # Worker 1 claims at MOMENT
    claimed = repo.claim_batch(
        lease_owner="worker_1",
        lease_duration_seconds=30.0,
        now=MOMENT,
        limit=10,
    )
    assert len(claimed) == 1

    # At MOMENT + 31 seconds, lease expired -> Worker 2 can reclaim
    reclaimed = repo.claim_batch(
        lease_owner="worker_2",
        lease_duration_seconds=30.0,
        now=MOMENT + timedelta(seconds=31),
        limit=10,
    )
    assert len(reclaimed) == 1
    assert reclaimed[0].lease_owner == "worker_2"
    assert reclaimed[0].attempt_count == 2


def test_mark_succeeded():
    repo = InMemoryOutboxRepository()
    repo.save_event(_sample_event("cout_1"))
    repo.claim_batch(lease_owner="worker_1", lease_duration_seconds=30.0, now=MOMENT)

    ok = repo.mark_succeeded("cout_1", lease_owner="worker_1", now=MOMENT + timedelta(seconds=5))
    assert ok is True

    event = repo.get_event("cout_1")
    assert event.status == OutboxStatus.SUCCEEDED
    assert event.lease_owner is None
    assert event.lease_until is None


def test_mark_succeeded_rejected_if_stale_lease():
    repo = InMemoryOutboxRepository()
    repo.save_event(_sample_event("cout_1"))
    repo.claim_batch(lease_owner="worker_1", lease_duration_seconds=10.0, now=MOMENT)

    # Worker 2 reclaims after expiry
    repo.claim_batch(lease_owner="worker_2", lease_duration_seconds=10.0, now=MOMENT + timedelta(seconds=15))

    # Worker 1 late commit is rejected
    ok = repo.mark_succeeded("cout_1", lease_owner="worker_1", now=MOMENT + timedelta(seconds=20))
    assert ok is False


def test_mark_failed_with_retry_and_dead_letter():
    repo = InMemoryOutboxRepository()
    repo.save_event(_sample_event("cout_1"))
    repo.claim_batch(lease_owner="worker_1", lease_duration_seconds=30.0, now=MOMENT)

    # First transient failure: resets to PENDING with backoff delay
    status = repo.mark_failed(
        outbox_id="cout_1",
        lease_owner="worker_1",
        error_message="Network 503",
        retryable=True,
        max_attempts=3,
        backoff_seconds=10.0,
        now=MOMENT + timedelta(seconds=5),
    )
    assert status == OutboxStatus.PENDING
    ev = repo.get_event("cout_1")
    assert ev.status == OutboxStatus.PENDING
    assert ev.last_error == "Network 503"
    # Cannot be claimed before backoff expires
    assert repo.claim_batch("w2", 30.0, now=MOMENT + timedelta(seconds=10)) == ()
    # Can be claimed after backoff expires
    assert len(repo.claim_batch("w2", 30.0, now=MOMENT + timedelta(seconds=20))) == 1

    # Permanent failure immediately goes to DEAD_LETTER
    status_perm = repo.mark_failed(
        outbox_id="cout_1",
        lease_owner="w2",
        error_message="Fatal schema error",
        retryable=False,
        max_attempts=3,
        now=MOMENT + timedelta(seconds=25),
    )
    assert status_perm == OutboxStatus.DEAD_LETTER
    assert repo.get_event("cout_1").status == OutboxStatus.DEAD_LETTER


def test_cancel_conversation_events():
    repo = InMemoryOutboxRepository()
    repo.save_event(_sample_event("cout_1", conversation_id="conv_a"))
    repo.save_event(_sample_event("cout_2", conversation_id="conv_a"))
    repo.save_event(_sample_event("cout_3", conversation_id="conv_b"))

    count = repo.cancel_events(conversation_id="conv_a", reason="conversation_deleted")
    assert count == 2
    assert repo.get_event("cout_1").status == OutboxStatus.CANCELLED
    assert repo.get_event("cout_2").status == OutboxStatus.CANCELLED
    assert repo.get_event("cout_3").status == OutboxStatus.PENDING


def test_calculate_backoff_deterministic():
    assert calculate_backoff(0, base_seconds=2.0, jitter=False) == 2.0
    assert calculate_backoff(1, base_seconds=2.0, jitter=False) == 2.0
    assert calculate_backoff(2, base_seconds=2.0, jitter=False) == 4.0
    assert calculate_backoff(3, base_seconds=2.0, jitter=False) == 8.0
    assert calculate_backoff(10, base_seconds=2.0, max_seconds=30.0, jitter=False) == 30.0


def test_calculate_backoff_jitter():
    # Deterministic mock random_fn
    mock_rf = lambda low, high: (low + high) / 2.0
    assert calculate_backoff(2, base_seconds=2.0, random_fn=mock_rf) == 2.0  # (0 + 4.0)/2 = 2.0

    # Default jitter is bounded
    for attempt in range(1, 6):
        val = calculate_backoff(attempt, base_seconds=2.0, max_seconds=60.0)
        max_bound = min(2.0 * (2 ** (attempt - 1)), 60.0)
        assert 0.0 <= val <= max_bound


def test_outbox_intent_dataclass_and_coercion():
    intent = OutboxIntent(event_type="test.event", payload={"k": "v"})
    assert intent.event_type == "test.event"
    assert intent.payload == {"k": "v"}

    # Immutability
    with pytest.raises(AttributeError):
        intent.event_type = "changed"  # frozen

    # Validation
    with pytest.raises(ConversationValidationError):
        OutboxIntent(event_type="", payload={})
    with pytest.raises(ConversationValidationError):
        OutboxIntent(event_type="test", payload="not-a-dict")  # type: ignore

    # Coercion
    assert coerce_outbox_intent(None) is None
    assert coerce_outbox_intent(intent) is intent

    coerced = coerce_outbox_intent({"event_type": "some.event", "payload": {"a": 1}})
    assert isinstance(coerced, OutboxIntent)
    assert coerced.event_type == "some.event"
    assert coerced.payload == {"a": 1}

    with pytest.raises(ConversationValidationError):
        coerce_outbox_intent({"event_type": ""})
    with pytest.raises(ConversationValidationError):
        coerce_outbox_intent("not-a-dict-or-intent")

