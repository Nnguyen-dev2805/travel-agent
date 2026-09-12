"""Unit tests for the memory write pipeline outbox contracts and lifecycle.

Covers:
- States PENDING, LEASED, SUCCEEDED, DEAD_LETTER, CANCELLED
- Lease claim, duration, expiry, and renewal
- Idempotent claim and parallel owner partitioning
- Deletion cancellation when source conversation is removed
- Retry classification, backoff calculation, and dead-lettering after max attempts
"""

from dataclasses import replace
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
    PermissiveInMemoryOutboxRepository,
    calculate_backoff,
)

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 9, 7, 12, 10, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)


def _sample_event(
    outbox_id="cout_1",
    conversation_id="conv_1",
    message_id="msg_1",
    owner_user_id="owner_1",
    event_type="memory.extract.conversation_range",
    payload=None,
    status=OutboxStatus.PENDING,
    created_at=MOMENT,
    released_at=LATER,
):
    """A claimable event by default.

    Released, because that is what production hands a worker: `released_at` is the
    ADR 0027 gate and the double now applies it, so a sample that left it `None`
    would be an event no repository would ever claim. Tests that need a *blocked*
    event pass `released_at=None` explicitly.
    """
    return OutboxEvent(
        outbox_id=outbox_id,
        conversation_id=conversation_id,
        message_id=message_id,
        owner_user_id=owner_user_id,
        event_type=event_type,
        payload=payload or {"conversation_id": conversation_id, "message_id": message_id},
        status=status,
        created_at=created_at,
        released_at=released_at,
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



# --- ADR 0027: the release gate is a fact the model must carry ----------------


def test_released_at_defaults_to_blocked():
    """The gate defaults to `None`, which is the fail-closed direction.

    An event constructed without an explicit release is blocked, so a caller that
    forgets to release gets no extraction rather than premature extraction.

    Built directly rather than through `_sample_event`: the helper now returns a
    claimable event, because that is what almost every test wants, and this test is
    about the model's own default.
    """
    bare = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
    )
    assert bare.released_at is None


def test_released_at_is_carried_on_the_event():
    released = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        released_at=LATER,
    )
    assert released.released_at == LATER


def test_the_in_memory_double_models_the_release_gate():
    """The double mirrors production's claim predicate, so a unit test means something.

    It used to omit the gate, which let a worker unit test claim an event
    PostgreSQL would treat as blocked — passing on input production refuses. Its own
    characterisation test said: "If this test fails, the double has started modelling
    the gate: delete it and assert the gate here instead."
    """
    repo = InMemoryOutboxRepository()
    blocked = _sample_event(released_at=None)
    assert blocked.released_at is None
    repo.save_event(blocked)

    assert (
        repo.claim_event(
            outbox_id="cout_1",
            lease_owner="worker_1",
            lease_duration_seconds=30.0,
            now=LATER,
        )
        is None
    ), "an event whose turn is not terminal is not claimable"
    assert repo.get_event("cout_1").status is OutboxStatus.PENDING, "and is untouched"


def test_the_in_memory_double_refuses_a_live_lease_even_for_its_own_holder():
    """A `LEASED` row is reclaimable only when its window has closed.

    The PostgreSQL claim predicate reads `lease_until < now()` and does not
    consult the holder at all: a live lease belongs to whoever holds it, and
    identity does not turn a closed window into an open one or vice versa. The
    double's LEASED branch matched on `lease_owner != lease_owner` instead, so
    the *same* owner could reclaim a lease with hours of its window left —
    input production would never hand over, from a double whose docstring
    claims faithfulness. This test pins the corrected predicate.
    """
    repo = InMemoryOutboxRepository()
    leased = replace(
        _sample_event(),
        status=OutboxStatus.LEASED,
        lease_owner="worker_1",
        lease_until=NOW + timedelta(seconds=3600),
    )
    repo.save_event(leased)

    assert (
        repo.claim_event(
            outbox_id="cout_1",
            lease_owner="worker_1",  # the current holder itself
            lease_duration_seconds=30.0,
            now=NOW,
        )
        is None
    ), "a live lease is not claimable, not even by its own holder"
    assert repo.get_event("cout_1").lease_owner == "worker_1", "and is untouched"


def test_the_in_memory_double_reclaims_an_expired_lease_for_any_worker():
    """The expiry branch the previous predicate accidentally preserved.

    An expired window makes the row claimable for *any* worker, including the
    previous holder: identity is not the criterion, the closed window is.
    """
    repo = InMemoryOutboxRepository()
    expired = replace(
        _sample_event(),
        status=OutboxStatus.LEASED,
        lease_owner="worker_1",
        lease_until=NOW - timedelta(seconds=1),
    )
    repo.save_event(expired)

    claimed = repo.claim_event(
        outbox_id="cout_1",
        lease_owner="worker_2",  # a different worker takes over
        lease_duration_seconds=30.0,
        now=NOW,
    )
    assert claimed is not None
    assert claimed.status is OutboxStatus.LEASED
    assert claimed.lease_owner == "worker_2"


def test_the_in_memory_double_models_the_event_family_boundary():
    """The second predicate production applies, and the one the Agent layer needs.

    A shared queue plus a worker that does not filter by family is how a Memory
    worker ends up extracting a conversation range out of an `agent.resume` event.
    """
    repo = InMemoryOutboxRepository()
    repo.save_event(_sample_event(event_type="agent.resume"))

    assert (
        repo.claim_event(
            outbox_id="cout_1",
            lease_owner="worker_1",
            lease_duration_seconds=30.0,
            now=LATER,
        )
        is None
    )
    assert (
        list(
            repo.claim_batch(
                lease_owner="worker_1", lease_duration_seconds=30.0, now=LATER
            )
        )
        == []
    )


def test_the_permissive_double_hands_over_what_production_refuses():
    """Its whole purpose: the worker's defence-in-depth layers need this input.

    A faithful double cannot produce an event production would never claim, so the
    layer that exists to catch one would be untestable through the batch path. That
    is the only thing this double is for.
    """
    repo = PermissiveInMemoryOutboxRepository()
    repo.save_event(_sample_event(released_at=None))  # blocked on purpose

    claimed = repo.claim_event(
        outbox_id="cout_1",
        lease_owner="worker_1",
        lease_duration_seconds=30.0,
        now=LATER,
    )

    assert claimed is not None, "the permissive double claims a blocked event on purpose"
    assert claimed.status is OutboxStatus.LEASED


def test_mark_failed_refuses_a_caller_that_lost_the_lease():
    repo = InMemoryOutboxRepository()
    leased = replace(
        _sample_event(),
        status=OutboxStatus.LEASED,
        lease_owner="new_worker",
        lease_until=LATER,
    )
    repo.save_event(leased)

    returned = repo.mark_failed(
        outbox_id=leased.outbox_id,
        lease_owner="old_worker",
        error_message="boom",
        retryable=True,
        now=MOMENT,
    )

    assert returned is OutboxStatus.LEASED, "the event is reported unchanged"
    stored = repo.get_event(leased.outbox_id)
    assert stored.status is OutboxStatus.LEASED
    assert stored.lease_owner == "new_worker", (
        "an old worker must not clear a new worker's lease"
    )


def test_mark_failed_refuses_a_caller_whose_lease_expired():
    repo = InMemoryOutboxRepository()
    expired = replace(
        _sample_event(),
        status=OutboxStatus.LEASED,
        lease_owner="worker_1",
        lease_until=MOMENT - timedelta(minutes=5),
    )
    repo.save_event(expired)

    returned = repo.mark_failed(
        outbox_id=expired.outbox_id,
        lease_owner="worker_1",
        error_message="boom",
        retryable=True,
        now=MOMENT,
    )

    assert returned is OutboxStatus.LEASED, "an expired lease is not authority"


def test_mark_failed_applies_for_the_holder():
    repo = InMemoryOutboxRepository()
    leased = replace(
        _sample_event(),
        status=OutboxStatus.LEASED,
        lease_owner="worker_1",
        lease_until=LATER,
    )
    repo.save_event(leased)

    returned = repo.mark_failed(
        outbox_id=leased.outbox_id,
        lease_owner="worker_1",
        error_message="boom",
        retryable=True,
        now=MOMENT,
    )

    assert returned is OutboxStatus.PENDING
    stored = repo.get_event(leased.outbox_id)
    assert stored.lease_owner is None
    assert stored.last_error == "boom"


def test_cancel_events_scoped_to_a_lease_owner_spares_other_workers():
    """A worker cleaning up its own lost lease must not destroy a peer's claim."""
    repo = InMemoryOutboxRepository()
    mine = replace(
        _sample_event(outbox_id="cout_mine"),
        status=OutboxStatus.LEASED,
        lease_owner="me",
        lease_until=LATER,
    )
    theirs = replace(
        _sample_event(outbox_id="cout_theirs"),
        status=OutboxStatus.LEASED,
        lease_owner="them",
        lease_until=LATER,
    )
    unheld = replace(_sample_event(outbox_id="cout_pending"))
    for event in (mine, theirs, unheld):
        repo.save_event(event)

    cancelled = repo.cancel_events(
        mine.conversation_id, reason="fenced_by_source_move", now=MOMENT, lease_owner="me"
    )

    assert cancelled == 2, "my own lease and the unheld pending row"
    assert repo.get_event("cout_theirs").status is OutboxStatus.LEASED, (
        "another worker's claim is untouched"
    )
    assert repo.get_event("cout_theirs").lease_owner == "them"


def test_cancel_events_without_a_lease_owner_still_cancels_everything():
    """Deletion passes no holder and must still clear the whole conversation."""
    repo = InMemoryOutboxRepository()
    for owner, oid in (("a", "cout_a"), ("b", "cout_b")):
        repo.save_event(
            replace(
                _sample_event(outbox_id=oid),
                status=OutboxStatus.LEASED,
                lease_owner=owner,
                lease_until=LATER,
            )
        )

    assert repo.cancel_events("conv_1", reason="conversation_deleted", now=MOMENT) == 2
