"""Task 13: Working Memory is governed conversation open state, not a transcript.

`plan v0.22` Task 13. Working Memory is the durable, conversation-scoped open
state that keeps continuity under context limits. It is **not** `DialogueState`
(`spec:330-331`): that is reconstructed per turn and discarded, and this module's
whole contract exists so the two can never be confused.

Three properties carry the slice, and each one is a way it could be got wrong:

1. **Two formation paths, one replacement semantics.** A deterministic
   synchronous transition derives open state that is certain from governed
   conversation state and runs no summarization model. The worker forms an
   inferred replacement over a bounded completed source range. Both write through
   the same replacement policy and the same canonical row, so there are not two
   canonical writers with different meanings.
2. **Source-consistent replacement.** A candidate replaces canonical state only
   when owner and conversation match, the source range is bounded and completed,
   source validity passes, lifecycle and suppression fences pass, and the
   candidate's cursor is strictly newer. A stale background candidate must never
   overwrite newer deterministic state — that is the rule that makes the two paths
   safe to run concurrently.
3. **No raw transcript becomes a durable instruction.** The open state is a
   bounded, structured projection. `memory_summaries.content` is a legacy
   migration-safety column, never policy authority.

No test here touches a database, a model, HTTP, or the network.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.conversations.models import (
    Message,
    MessageRole,
    MessageSource,
    MessageStatus,
    generate_message_id,
    utc_now,
)
from backend.memory.lifecycle import SourceValidity
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingOutcome,
    SourceHandlingReason,
    SourceHandlingRecord,
)
from backend.memory.write_pipeline.models import (
    Authority,
    MemoryScope,
    RetentionMode,
    SensitivityBand,
    VersionStatus,
)

CONVERSATION_A = "cv_" + "a" * 32
CONVERSATION_B = "cv_" + "b" * 32
OWNER = "owner_working"
OTHER_OWNER = "owner_other"
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 1. Deterministic derivation: no model, no semantics, bounded output.
# ---------------------------------------------------------------------------


def test_the_open_goal_is_the_last_user_request_that_is_not_an_answer():
    """A clarification exchange must not pin the goal to the answer."""
    from backend.memory.working import derive_open_state

    turns = [
        _user(1, "Tôi muốn đi Đà Nẵng tháng 10"),
        _assistant(2, "Bạn muốn ở bao nhiêu đêm?"),
        _user(3, "3 đêm"),
    ]

    state = derive_open_state(turns)

    assert state is not None
    assert state.open_goal == "Tôi muốn đi Đà Nẵng tháng 10", (
        "the latest user turn answers the assistant's question, so the open "
        "request is still the earlier one"
    )


def test_a_later_change_of_subject_moves_the_open_goal():
    from backend.memory.working import derive_open_state

    turns = [
        _user(1, "Tôi muốn đi Đà Nẵng"),
        _assistant(2, "Đây là vài gợi ý."),
        _user(3, "Thôi đổi sang Hội An đi"),
    ]

    state = derive_open_state(turns)

    assert state is not None
    assert state.open_goal == "Thôi đổi sang Hội An đi"


def test_the_cursor_is_the_highest_delivered_sequence():
    from backend.memory.working import derive_open_state

    turns = [
        _user(1, "Xin chào"),
        _assistant(2, "Chào bạn."),
        _user(4, "Tôi muốn đi Huế"),
    ]

    state = derive_open_state(turns)

    assert state is not None
    assert state.through_sequence == 4


def test_a_pending_row_is_not_a_turn_and_cannot_be_the_cursor():
    from backend.memory.working import derive_open_state

    turns = [
        _user(1, "Tôi muốn đi Huế"),
        _message(2, MessageRole.ASSISTANT, "", status=MessageStatus.PENDING),
    ]

    state = derive_open_state(turns)

    assert state is not None
    assert state.through_sequence == 1, (
        "an in-flight placeholder is not a delivered turn"
    )


def test_a_tool_row_is_not_a_turn():
    from backend.memory.working import derive_open_state

    turns = [
        _user(1, "Tôi muốn đi Huế"),
        _message(2, MessageRole.TOOL, "search()", status=MessageStatus.COMPLETE),
    ]

    state = derive_open_state(turns)

    assert state is not None
    assert state.through_sequence == 1


def test_no_delivered_user_turn_derives_no_state():
    from backend.memory.working import derive_open_state

    assert derive_open_state([]) is None
    assert derive_open_state([_assistant(1, "Chào bạn.")]) is None


def test_the_derivation_is_order_independent_and_deterministic():
    """Order comes from `sequence`, never from the caller's list order."""
    from backend.memory.working import derive_open_state

    turns = [
        _user(3, "Câu ba"),
        _user(1, "Câu một"),
        _assistant(2, "Trả lời."),
    ]

    first = derive_open_state(turns)
    second = derive_open_state(list(reversed(turns)))

    assert first == second
    assert first is not None
    assert first.open_goal == "Câu ba"
    assert first.through_sequence == 3


def test_the_derivation_reads_the_workers_message_dicts_too():
    """Both paths share one derivation, so both row shapes must work.

    The turn path holds `Message` rows; the worker holds the dictionaries
    `_load_messages` builds. Two accessors would be two rules, and the two paths
    would drift apart exactly where they must agree.
    """
    from backend.memory.working import derive_open_state

    rows = [
        {"sequence": 1, "role": "user", "content": "Tôi muốn đi Huế"},
        {"sequence": 2, "role": "assistant", "content": "Bạn đi mấy ngày?"},
        {"sequence": 3, "role": "user", "content": "3 ngày"},
    ]

    state = derive_open_state(rows)

    assert state is not None
    assert state.open_goal == "Tôi muốn đi Huế"
    assert state.through_sequence == 3


def test_a_message_dict_without_a_status_counts_as_delivered():
    """`Message.__post_init__` coerces an absent status to `COMPLETE`.

    The worker's `_is_extractable` documents the same rule, so applying a stricter
    one here would make one row complete to the repository and not-complete to
    this derivation.
    """
    from backend.memory.working import derive_open_state

    state = derive_open_state(
        [{"sequence": 1, "role": "user", "content": "Tôi muốn đi Huế"}]
    )

    assert state is not None
    assert state.open_goal == "Tôi muốn đi Huế"


def test_an_over_long_goal_is_refused_rather_than_truncated():
    """A blob is not an open state, and silently truncating one would hide it."""
    from backend.memory.working import MAX_GOAL_LENGTH, validate_working_state

    state = _state(open_goal="x" * (MAX_GOAL_LENGTH + 1), through_sequence=2)

    assert validate_working_state(state) is not None


def test_a_blank_goal_is_refused():
    from backend.memory.working import validate_working_state

    assert validate_working_state(_state(open_goal="   ", through_sequence=2)) is not None


def test_a_non_positive_cursor_is_refused():
    from backend.memory.working import validate_working_state

    assert validate_working_state(_state(open_goal="Đi Huế", through_sequence=0)) is not None


def test_a_valid_state_is_accepted():
    from backend.memory.working import validate_working_state

    assert validate_working_state(_state(open_goal="Đi Huế", through_sequence=2)) is None


# ---------------------------------------------------------------------------
# 2. Formation authority: the WORKING family's own record, never another's.
# ---------------------------------------------------------------------------


def test_working_formation_requires_a_working_family_record():
    from backend.memory.working import allows_working_formation

    assert allows_working_formation(_record(MemoryFamily.WORKING)) is True
    assert allows_working_formation(_record(MemoryFamily.SEMANTIC)) is False, (
        "a semantic record is positive authority for semantic formation only"
    )
    assert allows_working_formation(_record(MemoryFamily.EPISODIC)) is False


def test_working_formation_denies_absence_and_non_eligible_outcomes():
    from backend.memory.working import allows_working_formation

    assert allows_working_formation(None) is False, "absence is UNHANDLED"
    assert (
        allows_working_formation(
            _record(MemoryFamily.WORKING, outcome=SourceHandlingOutcome.EXPLICIT_APPLIED)
        )
        is False
    )


def test_the_deterministic_transition_needs_no_source_handling_authority():
    """It is a governed conversation transition, not background inference.

    `spec:1037` gives Working state two rows: an explicit input that is a
    deterministic conversation transition, and an inferred input that is a
    source-consistent replacement. Only the second one is background formation, so
    only the second one needs a persisted `BACKGROUND_ELIGIBLE` record.
    """
    from backend.memory.working import WorkingOrigin, WorkingStateTransition

    candidate = WorkingStateTransition().derive(
        turns=[_user(1, "Tôi muốn đi Huế")],
        owner_user_id=OWNER,
        conversation_id=CONVERSATION_A,
        origin=WorkingOrigin.DETERMINISTIC_TRANSITION,
        source_outbox_id="cout_working_1",
        source_message_id="msg_working_1",
        source_handling_record=None,
    )

    assert candidate is not None


def test_the_inferred_replacement_requires_positive_working_authority():
    from backend.memory.working import WorkingOrigin, WorkingStateTransition

    transition = WorkingStateTransition()
    arguments = dict(
        turns=[_user(1, "Tôi muốn đi Huế")],
        owner_user_id=OWNER,
        conversation_id=CONVERSATION_A,
        origin=WorkingOrigin.INFERRED_REPLACEMENT,
        source_outbox_id="cout_working_1",
        source_message_id="msg_working_1",
    )

    assert transition.derive(source_handling_record=None, **arguments) is None
    assert (
        transition.derive(
            source_handling_record=_record(MemoryFamily.SEMANTIC), **arguments
        )
        is None
    ), "another family's authority cannot authorize Working formation"
    assert (
        transition.derive(
            source_handling_record=_record(MemoryFamily.WORKING), **arguments
        )
        is not None
    )


def test_an_ineligible_lifecycle_refuses_formation():
    from backend.memory.working import WorkingOrigin, WorkingStateTransition

    candidate = WorkingStateTransition().derive(
        turns=[_user(1, "Tôi muốn đi Huế")],
        owner_user_id=OWNER,
        conversation_id=CONVERSATION_A,
        origin=WorkingOrigin.DETERMINISTIC_TRANSITION,
        source_outbox_id="cout_working_1",
        source_message_id="msg_working_1",
        source_validity=SourceValidity.INVALID,
    )

    assert candidate is None, "a deleted/invalid source cannot form working state"


def test_a_stale_generation_refuses_formation():
    from backend.memory.working import WorkingOrigin, WorkingStateTransition

    candidate = WorkingStateTransition().derive(
        turns=[_user(1, "Tôi muốn đi Huế")],
        owner_user_id=OWNER,
        conversation_id=CONVERSATION_A,
        origin=WorkingOrigin.DETERMINISTIC_TRANSITION,
        source_outbox_id="cout_working_1",
        source_message_id="msg_working_1",
        stamped_generation=1,
        current_generation=2,
    )

    assert candidate is None


def test_a_prohibited_secret_refuses_formation_before_any_model_exposure():
    from backend.memory.working import WorkingOrigin, WorkingStateTransition

    candidate = WorkingStateTransition().derive(
        turns=[_user(1, "Đặt phòng, mã là password=hunter2")],
        owner_user_id=OWNER,
        conversation_id=CONVERSATION_A,
        origin=WorkingOrigin.DETERMINISTIC_TRANSITION,
        source_outbox_id="cout_working_1",
        source_message_id="msg_working_1",
        secret_scan_text="password=hunter2",
    )

    assert candidate is None


def test_working_retention_is_the_shared_policy_decision():
    """Conversation-local state never outlives its conversation."""
    from backend.memory.working import WorkingOrigin, WorkingStateTransition

    candidate = WorkingStateTransition().derive(
        turns=[_user(1, "Tôi muốn đi Huế")],
        owner_user_id=OWNER,
        conversation_id=CONVERSATION_A,
        origin=WorkingOrigin.DETERMINISTIC_TRANSITION,
        source_outbox_id="cout_working_1",
        source_message_id="msg_working_1",
    )

    assert candidate is not None
    assert candidate.retention_mode is RetentionMode.CONVERSATION_BOUND


# ---------------------------------------------------------------------------
# 3. Source-consistent replacement, including the stale rule.
# ---------------------------------------------------------------------------


def test_a_newer_candidate_replaces_the_canonical_state():
    from backend.memory.working import WorkingReplacementPolicy, WorkingReplacementReason

    decision = WorkingReplacementPolicy().decide(
        candidate=_candidate(through_sequence=4),
        current=_stored(through_sequence=2, open_goal="Đi Huế"),
    )

    assert decision.replace is True
    assert decision.reason is WorkingReplacementReason.REPLACE


def test_an_older_background_candidate_never_overwrites_newer_deterministic_state():
    """The load-bearing rule of the two-path design.

    The worker's inferred replacement lags the turn path by construction, so
    without this rule a slow background event would silently undo a newer
    deterministic open state.
    """
    from backend.memory.working import (
        WorkingOrigin,
        WorkingReplacementPolicy,
        WorkingReplacementReason,
    )

    decision = WorkingReplacementPolicy().decide(
        candidate=_candidate(
            through_sequence=2, origin=WorkingOrigin.INFERRED_REPLACEMENT
        ),
        current=_stored(through_sequence=6, open_goal="Đi Hội An"),
    )

    assert decision.replace is False
    assert decision.reason is WorkingReplacementReason.NOT_NEWER


def test_an_equal_cursor_with_identical_content_is_a_noop():
    from backend.memory.working import WorkingReplacementPolicy, WorkingReplacementReason

    decision = WorkingReplacementPolicy().decide(
        candidate=_candidate(through_sequence=4, open_goal="Đi Huế"),
        current=_stored(through_sequence=4, open_goal="Đi Huế"),
    )

    assert decision.replace is False
    assert decision.reason is WorkingReplacementReason.IDENTICAL_NOOP


def test_an_equal_cursor_with_different_content_is_refused():
    """One cursor is one open state; two claims about it cannot both stand."""
    from backend.memory.working import WorkingReplacementPolicy, WorkingReplacementReason

    decision = WorkingReplacementPolicy().decide(
        candidate=_candidate(through_sequence=4, open_goal="Đi Huế"),
        current=_stored(through_sequence=4, open_goal="Đi Đà Nẵng"),
    )

    assert decision.replace is False
    assert decision.reason is WorkingReplacementReason.CURSOR_CONTENT_CONFLICT


def test_a_first_candidate_replaces_nothing():
    from backend.memory.working import WorkingReplacementPolicy, WorkingReplacementReason

    decision = WorkingReplacementPolicy().decide(
        candidate=_candidate(through_sequence=2), current=None
    )

    assert decision.replace is True
    assert decision.reason is WorkingReplacementReason.REPLACE


def test_a_cross_owner_candidate_is_refused():
    from backend.memory.working import WorkingReplacementPolicy, WorkingReplacementReason

    decision = WorkingReplacementPolicy().decide(
        candidate=_candidate(through_sequence=9, owner_user_id=OTHER_OWNER),
        current=_stored(through_sequence=2),
    )

    assert decision.replace is False
    assert decision.reason is WorkingReplacementReason.OWNER_MISMATCH


def test_a_cross_conversation_candidate_is_refused():
    from backend.memory.working import WorkingReplacementPolicy, WorkingReplacementReason

    decision = WorkingReplacementPolicy().decide(
        candidate=_candidate(through_sequence=9, conversation_id=CONVERSATION_B),
        current=_stored(through_sequence=2),
    )

    assert decision.replace is False
    assert decision.reason is WorkingReplacementReason.CONVERSATION_MISMATCH


def test_an_invalid_source_candidate_is_refused():
    from backend.memory.working import WorkingReplacementPolicy, WorkingReplacementReason

    decision = WorkingReplacementPolicy().decide(
        candidate=_candidate(through_sequence=9, source_validity=SourceValidity.INVALID),
        current=_stored(through_sequence=2),
    )

    assert decision.replace is False
    assert decision.reason is WorkingReplacementReason.SOURCE_INVALID


def test_a_stale_generation_candidate_is_refused():
    from backend.memory.working import WorkingReplacementPolicy, WorkingReplacementReason

    decision = WorkingReplacementPolicy().decide(
        candidate=_candidate(through_sequence=9, stamped_generation=1),
        current=_stored(through_sequence=2, current_generation=2),
    )

    assert decision.replace is False
    assert decision.reason is WorkingReplacementReason.STALE_GENERATION


def test_an_ineligible_lifecycle_candidate_is_refused():
    from backend.memory.working import WorkingReplacementPolicy, WorkingReplacementReason

    decision = WorkingReplacementPolicy().decide(
        candidate=_candidate(through_sequence=9), current=_stored(through_sequence=2),
        lifecycle_eligible=False,
    )

    assert decision.replace is False
    assert decision.reason is WorkingReplacementReason.LIFECYCLE_DENIED


def test_an_expired_canonical_state_is_still_replaced_by_a_newer_candidate():
    """Expiry makes the old row ineligible, not the new candidate invalid."""
    from backend.memory.working import WorkingReplacementPolicy

    decision = WorkingReplacementPolicy().decide(
        candidate=_candidate(through_sequence=9),
        current=_stored(through_sequence=2, expires_at=NOW - timedelta(days=1)),
    )

    assert decision.replace is True


# ---------------------------------------------------------------------------
# 4. Activation: two shapes, and inferred stays shadow by default.
# ---------------------------------------------------------------------------


def test_a_deterministic_transition_may_activate():
    from backend.memory.working import (
        WorkingActivationFacts,
        WorkingActivationPolicy,
        WorkingOrigin,
        WorkingActivationReason,
    )

    decision = WorkingActivationPolicy().evaluate(
        WorkingActivationFacts(
            origin=WorkingOrigin.DETERMINISTIC_TRANSITION,
            lifecycle_eligible=True,
            source_validity=SourceValidity.VALID,
            stamped_generation=1,
            current_generation=1,
        )
    )

    assert decision.eligible is True
    assert decision.target_status is VersionStatus.ACTIVE
    assert decision.reason is WorkingActivationReason.ELIGIBLE_ACTIVE


def test_an_inferred_replacement_stays_shadow_when_the_family_gate_is_off():
    from backend.memory.working import (
        WorkingActivationFacts,
        WorkingActivationPolicy,
        WorkingActivationReason,
        WorkingOrigin,
    )

    decision = WorkingActivationPolicy().evaluate(
        WorkingActivationFacts(
            origin=WorkingOrigin.INFERRED_REPLACEMENT,
            lifecycle_eligible=True,
            source_validity=SourceValidity.VALID,
            stamped_generation=1,
            current_generation=1,
        )
    )

    assert decision.eligible is False
    assert decision.target_status is VersionStatus.SHADOW
    assert decision.reason is WorkingActivationReason.WORKING_GATE_DISABLED


def test_an_inferred_replacement_stays_shadow_when_the_gate_is_inconclusive():
    from backend.memory.working import (
        WorkingActivationFacts,
        WorkingActivationPolicy,
        WorkingActivationReason,
        WorkingOrigin,
    )

    decision = WorkingActivationPolicy().evaluate(
        WorkingActivationFacts(
            origin=WorkingOrigin.INFERRED_REPLACEMENT,
            lifecycle_eligible=True,
            source_validity=SourceValidity.VALID,
            stamped_generation=1,
            current_generation=1,
            working_gate_enabled=True,
            working_gate_conclusive=False,
        )
    )

    assert decision.target_status is VersionStatus.SHADOW
    assert decision.reason is WorkingActivationReason.WORKING_GATE_INCONCLUSIVE


def test_the_activation_facts_do_not_accept_the_semantic_inferred_flag():
    """Passing semantic evaluation is not evidence Working was evaluated."""
    import dataclasses

    from backend.memory.working import WorkingActivationFacts

    names = {field.name for field in dataclasses.fields(WorkingActivationFacts)}

    assert "inferred_activation_enabled" not in names
    assert "working_gate_enabled" in names


def test_an_inferred_replacement_may_activate_only_with_a_conclusive_gate():
    from backend.memory.working import (
        WorkingActivationFacts,
        WorkingActivationPolicy,
        WorkingOrigin,
    )

    decision = WorkingActivationPolicy().evaluate(
        WorkingActivationFacts(
            origin=WorkingOrigin.INFERRED_REPLACEMENT,
            lifecycle_eligible=True,
            source_validity=SourceValidity.VALID,
            stamped_generation=1,
            current_generation=1,
            working_gate_enabled=True,
            working_gate_conclusive=True,
        )
    )

    assert decision.eligible is True
    assert decision.target_status is VersionStatus.ACTIVE


def test_activation_denies_on_invalid_source_and_stale_generation():
    from backend.memory.working import (
        WorkingActivationFacts,
        WorkingActivationPolicy,
        WorkingActivationReason,
        WorkingOrigin,
    )

    invalid = WorkingActivationPolicy().evaluate(
        WorkingActivationFacts(
            origin=WorkingOrigin.DETERMINISTIC_TRANSITION,
            lifecycle_eligible=True,
            source_validity=SourceValidity.INVALID,
            stamped_generation=1,
            current_generation=1,
        )
    )
    stale = WorkingActivationPolicy().evaluate(
        WorkingActivationFacts(
            origin=WorkingOrigin.DETERMINISTIC_TRANSITION,
            lifecycle_eligible=True,
            source_validity=SourceValidity.VALID,
            stamped_generation=1,
            current_generation=2,
        )
    )

    assert invalid.reason is WorkingActivationReason.SOURCE_INVALID
    assert invalid.target_status is VersionStatus.SHADOW
    assert stale.reason is WorkingActivationReason.STALE_GENERATION
    assert stale.target_status is VersionStatus.SHADOW


def test_activation_denies_when_the_lifecycle_owner_denies():
    from backend.memory.working import (
        WorkingActivationFacts,
        WorkingActivationPolicy,
        WorkingActivationReason,
        WorkingOrigin,
    )

    decision = WorkingActivationPolicy().evaluate(
        WorkingActivationFacts(
            origin=WorkingOrigin.DETERMINISTIC_TRANSITION,
            lifecycle_eligible=False,
            source_validity=SourceValidity.VALID,
            stamped_generation=1,
            current_generation=1,
        )
    )

    assert decision.reason is WorkingActivationReason.LIFECYCLE_DENIED
    assert decision.target_status is VersionStatus.SHADOW


# ---------------------------------------------------------------------------
# 5. Read: one conversation's eligible open state, or an abstention.
# ---------------------------------------------------------------------------


class _FakeStore:
    def __init__(self, rows):
        self.rows = tuple(rows)
        self.requests = []

    def get_storage_scoped(self, request):
        self.requests.append(request)
        return self.rows


def _select(rows, *, conversation_id=CONVERSATION_A, owner_user_id=OWNER):
    from backend.memory.working import WorkingMemoryReadEngine, WorkingReadRequest

    engine = WorkingMemoryReadEngine(_FakeStore(rows), clock=lambda: NOW)
    return engine.select(
        WorkingReadRequest(
            owner_user_id=owner_user_id, conversation_id=conversation_id
        )
    )


def test_an_eligible_active_state_is_selected():
    selection = _select([_stored(through_sequence=4, status=VersionStatus.ACTIVE)])

    assert len(selection.selected) == 1
    assert selection.selected[0].open_goal == "Đi Huế"
    assert selection.selected[0].through_sequence == 4
    assert selection.abstention_reason is None


def test_no_row_abstains():
    from backend.memory.working import WorkingAbstentionReason

    selection = _select([])

    assert selection.selected == ()
    assert selection.abstention_reason is WorkingAbstentionReason.NO_ELIGIBLE_WORKING_STATE


def test_a_shadow_state_is_not_selected():
    selection = _select([_stored(through_sequence=4, status=VersionStatus.SHADOW)])

    assert selection.selected == ()


def test_an_invalidated_state_is_not_selected():
    selection = _select(
        [_stored(through_sequence=4, status=VersionStatus.ACTIVE, invalidated=True)]
    )

    assert selection.selected == ()


def test_an_expired_state_is_not_selected():
    selection = _select(
        [
            _stored(
                through_sequence=4,
                status=VersionStatus.ACTIVE,
                expires_at=NOW - timedelta(seconds=1),
            )
        ]
    )

    assert selection.selected == ()


def test_a_stale_generation_state_is_not_selected():
    selection = _select(
        [
            _stored(
                through_sequence=4,
                status=VersionStatus.ACTIVE,
                stamped_generation=1,
                current_generation=2,
            )
        ]
    )

    assert selection.selected == ()


def test_a_revoked_state_is_not_selected():
    selection = _select([_stored(through_sequence=4, status=VersionStatus.REVOKED)])

    assert selection.selected == ()


def test_a_cross_owner_row_is_never_selected():
    """Tenant isolation is a read predicate, not a caller responsibility."""
    selection = _select(
        [_stored(through_sequence=4, status=VersionStatus.ACTIVE, owner_user_id=OTHER_OWNER)]
    )

    assert selection.selected == ()


def test_a_cross_conversation_row_is_never_selected():
    selection = _select(
        [
            _stored(
                through_sequence=4,
                status=VersionStatus.ACTIVE,
                conversation_id=CONVERSATION_B,
            )
        ]
    )

    assert selection.selected == ()


def test_the_selected_projection_carries_no_raw_source_fields():
    """A selected state is open state, not the row it came from."""
    import dataclasses

    from backend.memory.working import SelectedWorkingState

    names = {field.name for field in dataclasses.fields(SelectedWorkingState)}

    assert "source_message_id" not in names
    assert "source_outbox_id" not in names
    assert "content" not in names


# ---------------------------------------------------------------------------
# 6. Non-duplication with the ephemeral dialogue state.
# ---------------------------------------------------------------------------


def test_the_durable_state_and_the_ephemeral_state_are_different_types():
    from backend.memory.working import WorkingOpenState
    from backend.orchestration.dialogue_state import DialogueState

    assert WorkingOpenState is not DialogueState
    assert not issubclass(DialogueState, WorkingOpenState)
    assert not issubclass(WorkingOpenState, DialogueState)


def test_working_memory_is_not_a_memory_family_registry_key():
    """Working state is not a semantic registry key and carries no `canonical_key`."""
    import dataclasses

    from backend.memory.working import SelectedWorkingState

    names = {field.name for field in dataclasses.fields(SelectedWorkingState)}

    assert "canonical_key" not in names


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _message(
    sequence: int,
    role: MessageRole,
    content: str,
    status: MessageStatus = MessageStatus.COMPLETE,
    conversation_id: str = CONVERSATION_A,
) -> Message:
    return Message(
        message_id=generate_message_id(),
        conversation_id=conversation_id,
        sequence=sequence,
        role=role,
        content=content,
        source=MessageSource.UI if role is MessageRole.USER else MessageSource.MODEL,
        created_at=utc_now(),
        status=status,
    )


def _user(sequence: int, content: str, conversation_id: str = CONVERSATION_A) -> Message:
    return _message(sequence, MessageRole.USER, content, conversation_id=conversation_id)


def _assistant(
    sequence: int, content: str, conversation_id: str = CONVERSATION_A
) -> Message:
    return _message(
        sequence, MessageRole.ASSISTANT, content, conversation_id=conversation_id
    )


def _state(*, open_goal="Đi Huế", through_sequence=2):
    from backend.memory.working import WorkingOpenState

    return WorkingOpenState(open_goal=open_goal, through_sequence=through_sequence)


def _record(family: MemoryFamily, *, outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE):
    return SourceHandlingRecord(
        source_outbox_id="cout_working_1",
        source_message_id="msg_working_1",
        family=family,
        outcome=outcome,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
        recorded_at=NOW,
    )


def _candidate(
    *,
    through_sequence=4,
    open_goal="Đi Huế",
    owner_user_id=OWNER,
    conversation_id=CONVERSATION_A,
    origin=None,
    stamped_generation=1,
    source_validity=SourceValidity.VALID,
):
    from backend.memory.working import (
        WorkingCandidate,
        WorkingOrigin,
        WorkingProvenance,
    )

    return WorkingCandidate(
        candidate_id="wmc_1",
        owner_user_id=owner_user_id,
        conversation_id=conversation_id,
        origin=origin or WorkingOrigin.DETERMINISTIC_TRANSITION,
        state=_state(open_goal=open_goal, through_sequence=through_sequence),
        provenance=WorkingProvenance(
            source_outbox_id="cout_working_1", source_message_id="msg_working_1"
        ),
        retention_mode=RetentionMode.CONVERSATION_BOUND,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        suppression_generation=stamped_generation,
        source_validity=source_validity,
    )


def _stored(
    *,
    through_sequence=2,
    open_goal="Đi Huế",
    owner_user_id=OWNER,
    conversation_id=CONVERSATION_A,
    status=VersionStatus.ACTIVE,
    stamped_generation=1,
    current_generation=1,
    invalidated=False,
    expires_at=None,
):
    from backend.memory.working import StoredWorkingRow

    return StoredWorkingRow(
        summary_id="sum_1",
        owner_user_id=owner_user_id,
        conversation_id=conversation_id,
        open_goal=open_goal,
        through_sequence=through_sequence,
        retention_mode=RetentionMode.CONVERSATION_BOUND,
        stamped_generation=stamped_generation,
        current_generation=current_generation,
        status=status,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        source_validity=(
            SourceValidity.INVALID if invalidated else SourceValidity.VALID
        ),
        expires_at=expires_at,
    )
