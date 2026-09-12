"""ADR 0033: a fenced write carries a typed reason, not a sentence.

`check_conversation_fence` and `check_outbox_lease` detected six distinct causes
and reported each as a sentence. `_check_fence` raised one `FencedWriteError`
carrying whichever sentence applied, so the worker could not branch on the cause
and treated all six identically — including "this worker lost its lease", which is
a fact about one worker's tenure and not about the conversation's validity.

These tests pin the vocabulary and its partition. The partition is the part that
matters: `cancels_conversation_work` is the single expression of the rule "cancel a
conversation's remaining events only when the cause is a property of the
conversation, never when it is a property of this worker's tenure".
"""

from __future__ import annotations

import pytest

from backend.memory.write_pipeline.uow import (
    FenceReason,
    FencedWriteError,
    MemoryWriteError,
)

CONVERSATION_SHAPED = (
    FenceReason.CONVERSATION_GONE,
    FenceReason.CONVERSATION_NOT_ACTIVE,
    FenceReason.DELETION_EPOCH_MOVED,
)

WORKER_SHAPED = (
    FenceReason.LEASE_LOST,
    FenceReason.LEASE_EXPIRED,
)


def test_the_six_causes_are_distinguishable():
    """One exception type covering six sentences was the defect."""
    assert {member.value for member in FenceReason} == {
        "conversation_gone",
        "conversation_not_active",
        "deletion_epoch_moved",
        "outbox_event_gone",
        "lease_lost",
        "lease_expired",
    }


@pytest.mark.parametrize("reason", CONVERSATION_SHAPED)
def test_a_conversation_shaped_reason_justifies_cancelling(reason):
    assert reason.cancels_conversation_work is True


@pytest.mark.parametrize("reason", WORKER_SHAPED)
def test_a_worker_shaped_reason_never_justifies_cancelling(reason):
    """The defect: a lease loss cancelled every `PENDING` turn in the conversation.

    Turn 2 and turn 3 were cancelled because turn 1's worker was slow. They were
    never at fault, and a cancelled event is never re-created.
    """
    assert reason.cancels_conversation_work is False


def test_one_event_going_missing_says_nothing_about_its_siblings():
    assert FenceReason.OUTBOX_EVENT_GONE.cancels_conversation_work is False


def test_the_partition_is_total():
    """Every member must be classified, so a new reason cannot be added silently.

    `FenceReason` is the vocabulary a future agent or tool event will extend. A
    member with no classification would default to whichever branch the caller
    happened to write, which is how the original defect arose.
    """
    classified = set(CONVERSATION_SHAPED) | set(WORKER_SHAPED) | {
        FenceReason.OUTBOX_EVENT_GONE
    }
    assert classified == set(FenceReason)


def test_the_error_carries_a_required_reason():
    error = FencedWriteError(FenceReason.LEASE_LOST)

    assert error.reason is FenceReason.LEASE_LOST
    assert str(error), "the error must still render a human-readable message"
    assert isinstance(error, MemoryWriteError), "it remains a memory write failure"


def test_the_message_is_derived_from_the_reason():
    """Logs stay readable without branching on prose."""
    lost = str(FencedWriteError(FenceReason.LEASE_LOST))
    expired = str(FencedWriteError(FenceReason.LEASE_EXPIRED))
    assert lost != expired


def test_the_message_can_be_overridden():
    error = FencedWriteError(FenceReason.CONVERSATION_GONE, "custom detail")
    assert str(error) == "custom detail"
    assert error.reason is FenceReason.CONVERSATION_GONE


def test_a_reason_is_required():
    """Optional would let a caller raise an unclassifiable fence."""
    with pytest.raises(TypeError):
        FencedWriteError()


def test_the_reason_is_not_required_to_be_a_string():
    """Guards against a caller passing the old free-text sentence."""
    with pytest.raises((TypeError, ValueError)):
        FencedWriteError("The source conversation is gone.")
