"""Unit tests for Stage 2 Chat-Native Explicit Remember/Correct/Forget.

Tests:
1. explicit_semantic_idempotency_key:
   - deterministic output from stable inputs
   - no candidate/evidence random IDs
   - identical key on replay
   - set values order-independent
2. ExplicitMemoryProposal and ProposalOutcome
3. ExplicitMemoryActionHandler:
   - Remember positive single key -> ADD / SUPERSEDE
   - Remember positive set key -> set union SUPERSEDE
   - Set subset remember -> REINFORCE
   - Explicit set correction -> full replacement SUPERSEDE with expected_version_id
   - Targeted member forget for set key -> member removal SUPERSEDE with expected_version_id
   - Targeted member forget of last remaining member -> REVOKE with expected_version_id
   - Whole-key forget for single and set keys -> REVOKE with expected_version_id
   - Forget with no active versions -> NOOP
   - Re-remember after forget -> ADD
   - Prohibited secrets in utterance -> fail closed NOOP
   - Registry-invalid input -> CLARIFICATION
   - Ambiguous speech act -> CLARIFICATION
   - Deterministic template acknowledgements
"""

from datetime import datetime, timezone
import hashlib
import pytest

from backend.conversations.models import Message, MessageRole, MessageSource, TraceVisibility
from backend.memory.write_pipeline.models import (
    Authority,
    MemoryChangeSet,
    MemoryOperation,
    MemoryScope,
    MemoryVersion,
    RetentionMode,
    SensitivityBand,
    VersionStatus,
)
from backend.orchestration.dialogue_state import DialogueState
from backend.orchestration.turn_models import (
    InteractionMode,
    TurnUnderstandingResult,
    UnderstandingReason,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_state(user_content: str, conversation_id: str = "cv_test_1") -> DialogueState:
    user_msg = Message(
        message_id="ms_user_1",
        conversation_id=conversation_id,
        sequence=1,
        role=MessageRole.USER,
        content=user_content,
        source=MessageSource.UI,
        trace_visibility=TraceVisibility.EXCLUDED,
        created_at=_utc_now(),
    )
    return DialogueState(
        turns=(user_msg,),
        latest_user_turn=user_msg,
        latest_assistant_turn=None,
    )


def _make_version(
    version_id: str,
    canonical_key: str,
    normalized_value: str | tuple[str, ...],
    owner_user_id: str = "user_1",
) -> MemoryVersion:
    return MemoryVersion(
        version_id=version_id,
        owner_user_id=owner_user_id,
        scope=MemoryScope.USER,
        scope_id=owner_user_id,
        canonical_key=canonical_key,
        subject_key="self",
        condition_fingerprint=hashlib.sha256(b"").hexdigest(),
        normalized_value=normalized_value,
        display_text=str(normalized_value),
        authority=Authority.EXPLICIT_SAVE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        status=VersionStatus.ACTIVE,
        valid_from=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        retention_mode=RetentionMode.USER_DURABLE,
        suppression_generation=1,
    )


# ---------------------------------------------------------------------------
# 1. Idempotency Key Tests
# ---------------------------------------------------------------------------


def test_explicit_semantic_idempotency_key_is_deterministic():
    from backend.memory.explicit_actions import explicit_semantic_idempotency_key

    k1 = explicit_semantic_idempotency_key(
        source_message_id="msg_123",
        owner_user_id="user_abc",
        canonical_key="travel.preference.hotel_atmosphere",
        operation="SUPERSEDE",
        normalized_value="quiet",
    )
    k2 = explicit_semantic_idempotency_key(
        source_message_id="msg_123",
        owner_user_id="user_abc",
        canonical_key="travel.preference.hotel_atmosphere",
        operation="SUPERSEDE",
        normalized_value="quiet",
    )
    assert k1.startswith("exp_")
    assert k1 == k2


def test_explicit_semantic_idempotency_key_set_order_independent():
    from backend.memory.explicit_actions import explicit_semantic_idempotency_key

    k1 = explicit_semantic_idempotency_key(
        source_message_id="msg_123",
        owner_user_id="user_abc",
        canonical_key="travel.preference.accommodation_type",
        operation="SUPERSEDE",
        normalized_value=("hotel", "resort"),
    )
    k2 = explicit_semantic_idempotency_key(
        source_message_id="msg_123",
        owner_user_id="user_abc",
        canonical_key="travel.preference.accommodation_type",
        operation="SUPERSEDE",
        normalized_value=("resort", "hotel"),
    )
    assert k1 == k2


def test_explicit_semantic_idempotency_key_differs_on_distinct_effect():
    from backend.memory.explicit_actions import explicit_semantic_idempotency_key

    k1 = explicit_semantic_idempotency_key(
        source_message_id="msg_123",
        owner_user_id="user_abc",
        canonical_key="travel.preference.hotel_atmosphere",
        operation="SUPERSEDE",
        normalized_value="quiet",
    )
    k2 = explicit_semantic_idempotency_key(
        source_message_id="msg_123",
        owner_user_id="user_abc",
        canonical_key="travel.preference.hotel_atmosphere",
        operation="REVOKE",
        normalized_value="",
    )
    assert k1 != k2


# ---------------------------------------------------------------------------
# 2. Handler: Single-Key Remember & Correct
# ---------------------------------------------------------------------------


def test_handler_remember_single_key_first_add():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: ()
    )
    state = _make_state("Nhớ là tôi thích khách sạn yên tĩnh")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_REMEMBER,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.change is not None
    assert proposal.change.operation == MemoryOperation.ADD
    assert proposal.change.new_version is not None
    assert proposal.change.new_version.canonical_key == "travel.preference.hotel_atmosphere"
    assert proposal.change.new_version.normalized_value == "quiet"
    assert proposal.expected_version_id is None
    assert "yên tĩnh" in proposal.acknowledgement_text.lower() or "quiet" in proposal.acknowledgement_text.lower() or "ghi nhận" in proposal.acknowledgement_text.lower() or "noted" in proposal.acknowledgement_text.lower() or "đã lưu" in proposal.acknowledgement_text.lower()


def test_handler_remember_single_key_supersede_active():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    active = (_make_version("mem_1", "travel.preference.hotel_atmosphere", "quiet"),)
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: active
    )
    state = _make_state("Remember that I prefer central hotels")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_REMEMBER,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.change is not None
    assert proposal.change.operation == MemoryOperation.SUPERSEDE
    assert proposal.change.new_version is not None
    assert proposal.change.new_version.normalized_value == "central"
    assert proposal.expected_version_id == "mem_1"


def test_handler_remember_single_key_reinforce():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    active = (_make_version("mem_1", "travel.preference.hotel_atmosphere", "quiet"),)
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: active
    )
    state = _make_state("Nhớ là tôi thích khách sạn yên tĩnh nhé")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_REMEMBER,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.change is not None
    assert proposal.change.operation == MemoryOperation.REINFORCE
    assert proposal.expected_version_id == "mem_1"


# ---------------------------------------------------------------------------
# 3. Handler: Set-Key Remember, Correct, Forget
# ---------------------------------------------------------------------------


def test_handler_remember_set_key_member_union():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    active = (_make_version("mem_act_1", "travel.preference.accommodation_type", ("hotel",)),)
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: active
    )
    state = _make_state("Remember that I also like resorts")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_REMEMBER,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.change is not None
    assert proposal.change.operation == MemoryOperation.SUPERSEDE
    assert proposal.change.new_version is not None
    assert proposal.change.new_version.normalized_value == ("hotel", "resort")
    assert proposal.expected_version_id == "mem_act_1"


def test_handler_remember_set_key_subset_reinforce():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    active = (_make_version("mem_act_1", "travel.preference.accommodation_type", ("hotel", "resort")),)
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: active
    )
    state = _make_state("Remember that I like hotels")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_REMEMBER,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.change is not None
    assert proposal.change.operation == MemoryOperation.REINFORCE
    assert proposal.expected_version_id == "mem_act_1"


def test_handler_correct_set_key_full_replacement():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    active = (_make_version("mem_trans_1", "travel.preference.transport_mode", ("flight", "train")),)
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: active
    )
    state = _make_state("Sửa lại là tôi chỉ đi xe buýt")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_CORRECT,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.change is not None
    assert proposal.change.operation == MemoryOperation.SUPERSEDE
    assert proposal.change.new_version is not None
    assert proposal.change.new_version.normalized_value == ("bus",)
    assert proposal.expected_version_id == "mem_trans_1"


def test_handler_targeted_member_forget_set_key():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    active = (_make_version("mem_food_1", "travel.preference.food_style", ("local", "street_food")),)
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: active
    )
    state = _make_state("Hãy quên đồ ăn đường phố đi")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_FORGET,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.change is not None
    assert proposal.change.operation == MemoryOperation.SUPERSEDE
    assert proposal.change.new_version is not None
    assert proposal.change.new_version.normalized_value == ("local",)
    assert proposal.expected_version_id == "mem_food_1"


def test_handler_targeted_member_forget_last_member_revokes():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    active = (_make_version("mem_food_2", "travel.preference.food_style", ("street_food",)),)
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: active
    )
    state = _make_state("Forget that I like street food")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_FORGET,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.change is not None
    assert proposal.change.operation == MemoryOperation.REVOKE
    assert proposal.change.new_version is None
    assert proposal.expected_version_id == "mem_food_2"


def test_handler_whole_key_forget_single_key():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    active = (_make_version("mem_budget_1", "travel.constraint.budget_level", "luxury"),)
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: active
    )
    state = _make_state("Forget my budget level")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_FORGET,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.change is not None
    assert proposal.change.operation == MemoryOperation.REVOKE
    assert proposal.change.new_version is None
    assert proposal.expected_version_id == "mem_budget_1"


def test_handler_forget_no_active_yields_noop():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: ()
    )
    state = _make_state("Forget my hotel preference")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_FORGET,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.NOOP
    assert proposal.change is None


# ---------------------------------------------------------------------------
# 4. Security & Guard Boundaries: Secrets, Clarifications, Inspect
# ---------------------------------------------------------------------------


def test_handler_prohibited_secrets_fail_closed_noop():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: ()
    )
    # Secret included in user utterance
    state = _make_state("Remember that my api_key is sk-proj-12345678901234567890")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_REMEMBER,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.NOOP
    assert proposal.change is None
    assert "secret" in proposal.reason.lower() or "prohibited" in proposal.reason.lower()


def test_handler_unrecognized_preference_yields_clarification():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: ()
    )
    state = _make_state("Remember that I like green elephants")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_REMEMBER,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.CLARIFICATION
    assert proposal.change is None
    assert proposal.clarification_prompt is not None


def test_handler_ambiguous_intent_yields_clarification():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: ()
    )
    state = _make_state("Remember something maybe")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_REMEMBER,
        needs_clarification=True,
        reason_codes=(UnderstandingReason.AMBIGUOUS_SPEECH_ACT,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.CLARIFICATION
    assert proposal.change is None


def test_handler_inspect_yields_noop_unavailable():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: ()
    )
    state = _make_state("What do you remember about me?")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_INSPECT,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.NOOP
    assert "not yet available" in proposal.acknowledgement_text.lower() or "chưa hỗ trợ" in proposal.acknowledgement_text.lower()


def test_handler_whole_key_forget_set_key():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )
    from backend.memory.write_pipeline.models import MemoryOperation

    active_v = _make_version(
        "mem_food_1",
        "travel.preference.food_style",
        ("fine_dining", "street_food"),
    )
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: (active_v,)
    )
    state = _make_state("Quên sở thích ẩm thực của tôi đi")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_FORGET,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.canonical_key == "travel.preference.food_style"
    assert proposal.change is not None
    assert proposal.change.operation is MemoryOperation.REVOKE
    assert proposal.change.superseded_version_ids == ("mem_food_1",)
    assert "toàn bộ sở thích" in proposal.acknowledgement_text


def test_handler_propose_with_empty_state_and_explicit_utterance():
    """Turn 1 of conversation: state.latest_user_turn is None; utterance and conversation_id are passed explicitly."""
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )
    from backend.orchestration.dialogue_state import DialogueState

    empty_state = DialogueState(
        turns=(),
        latest_user_turn=None,
        latest_assistant_turn=None,
    )
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: ()
    )
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_REMEMBER,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(
        understanding,
        empty_state,
        owner_user_id="user_1",
        utterance="Nhớ là tôi thích khách sạn yên tĩnh",
        conversation_id="conv_turn_1",
    )

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.canonical_key == "travel.preference.hotel_atmosphere"
    assert proposal.change is not None
    assert proposal.change.new_version is not None
    assert proposal.change.new_version.normalized_value == "quiet"


def test_business_class_flights_does_not_false_match_bus():
    """'Remember I prefer business class flights' must match 'flight', NOT 'bus'."""
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: ()
    )
    state = _make_state("Remember I prefer business class flights")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_REMEMBER,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.canonical_key == "travel.preference.transport_mode"
    assert proposal.change is not None
    assert proposal.change.new_version is not None
    # Must be flight, NOT bus
    assert proposal.change.new_version.normalized_value == ("flight",)


def test_targeted_forget_invalid_member_returns_clarification_no_wipe():
    """'Forget helicopter from my transport preferences' must return CLARIFICATION and NOT wipe the set."""
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    active_v = _make_version(
        "mem_trans_1",
        "travel.preference.transport_mode",
        ("bus", "train"),
    )
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: (active_v,)
    )
    state = _make_state("Forget helicopter from my transport preferences")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_FORGET,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.CLARIFICATION
    assert proposal.canonical_key == "travel.preference.transport_mode"
    assert proposal.change is None
    assert proposal.reason == "invalid_member_to_forget"


def test_targeted_forget_member_not_in_set_returns_noop():
    """'Forget flight from my transport preferences' when only bus/train active must return NOOP."""
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )

    active_v = _make_version(
        "mem_trans_1",
        "travel.preference.transport_mode",
        ("bus", "train"),
    )
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: (active_v,)
    )
    state = _make_state("Forget flight from my transport preferences")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_FORGET,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.NOOP
    assert proposal.canonical_key == "travel.preference.transport_mode"
    assert proposal.change is None
    assert proposal.reason == "member_not_in_set"


def test_targeted_forget_valid_member_removes_member_from_set():
    """'Forget bus from my transport preferences' when bus/train active mutates to ('train',)."""
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
    )
    from backend.memory.write_pipeline.models import MemoryOperation

    active_v = _make_version(
        "mem_trans_1",
        "travel.preference.transport_mode",
        ("bus", "train"),
    )
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: (active_v,)
    )
    state = _make_state("Forget bus from my transport preferences")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_FORGET,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.canonical_key == "travel.preference.transport_mode"
    assert proposal.change is not None
    assert proposal.change.operation is MemoryOperation.SUPERSEDE
    assert proposal.change.new_version is not None
    assert proposal.change.new_version.normalized_value == ("train",)


def test_suppression_generation_forwarded_and_hashes_into_idempotency_key():
    """GenerationProvider must supply generation to proposal and affect the idempotency key."""
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ProposalOutcome,
        explicit_semantic_idempotency_key,
    )

    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda owner, key: (),
        generation_provider=lambda owner, key: 4,
    )
    state = _make_state("Tôi thích đi tàu hỏa")
    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_REMEMBER,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )

    proposal = handler.propose(understanding, state, owner_user_id="user_1")

    assert proposal.outcome == ProposalOutcome.MUTATION
    assert proposal.suppression_generation == 4

    key_gen_4 = explicit_semantic_idempotency_key(
        source_message_id="msg_1",
        owner_user_id="user_1",
        canonical_key="travel.preference.transport_mode",
        operation="add",
        normalized_value=("train",),
        suppression_generation=4,
    )
    key_gen_1 = explicit_semantic_idempotency_key(
        source_message_id="msg_1",
        owner_user_id="user_1",
        canonical_key="travel.preference.transport_mode",
        operation="add",
        normalized_value=("train",),
        suppression_generation=1,
    )
    assert key_gen_4 != key_gen_1


def test_format_inspect_reply_empty_and_populated():
    from backend.memory.explicit_actions import format_inspect_reply
    from unittest.mock import MagicMock

    # Empty selection
    assert format_inspect_reply(None) == "Hiện tại tôi chưa ghi nhớ thông tin nào về sở thích của bạn."
    empty_sel = MagicMock(selected=())
    assert format_inspect_reply(empty_sel) == "Hiện tại tôi chưa ghi nhớ thông tin nào về sở thích của bạn."

    # Populated selection
    item1 = MagicMock(
        canonical_key="travel.preference.cuisine",
        normalized_value=("vietnamese", "italian"),
        scope="conversation",
    )
    item2 = MagicMock(
        canonical_key="travel.preference.budget",
        normalized_value="luxury",
        scope="user",
    )
    pop_sel = MagicMock(selected=(item1, item2))
    reply = format_inspect_reply(pop_sel)
    assert "Dưới đây là các sở thích mà tôi đã ghi nhớ:" in reply
    assert "- travel.preference.cuisine: vietnamese, italian (trong đoạn hội thoại này)" in reply
    assert "- travel.preference.budget: luxury (chung cho tài khoản của bạn)" in reply


def test_inspect_explicit_memory_and_handler_inspect():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        INSPECT_UNAVAILABLE_REPLY,
        inspect_explicit_memory,
    )
    from unittest.mock import MagicMock

    # When disabled
    res = inspect_explicit_memory(None, owner_user_id="user_1", memory_read_enabled=False)
    assert res.delivered is False
    assert res.reply == INSPECT_UNAVAILABLE_REPLY

    handler = ExplicitMemoryActionHandler(active_version_provider=lambda o, k: ())
    res_h = handler.inspect(None, owner_user_id="user_1", memory_read_enabled=False)
    assert res_h.delivered is False
    assert res_h.reply == INSPECT_UNAVAILABLE_REPLY

    # When enabled with mock read engine
    mock_engine = MagicMock()
    mock_item = MagicMock(
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        scope="user",
    )
    mock_engine.select.return_value = MagicMock(selected=(mock_item,))
    res_enabled = inspect_explicit_memory(
        mock_engine,
        owner_user_id="user_1",
        conversation_id="conv_1",
        memory_read_enabled=True,
    )
    assert res_enabled.delivered is True
    assert "travel.preference.hotel_atmosphere: quiet" in res_enabled.reply
    mock_engine.select.assert_called_once()


def test_build_explicit_source_handling_record():
    from backend.memory.explicit_actions import build_explicit_source_handling_record
    from backend.memory.source_handling import (
        MemoryFamily,
        SourceHandlingOutcome,
        SourceHandlingReason,
    )

    rec = build_explicit_source_handling_record(
        source_outbox_id="outbox_123",
        source_message_id="msg_456",
        outcome=SourceHandlingOutcome.EXPLICIT_APPLIED,
    )
    assert rec.source_outbox_id == "outbox_123"
    assert rec.source_message_id == "msg_456"
    assert rec.family == MemoryFamily.SEMANTIC
    assert rec.outcome == SourceHandlingOutcome.EXPLICIT_APPLIED
    assert rec.reason_code == SourceHandlingReason.EXPLICIT_ACTION
    assert rec.recorded_at is not None


def test_build_explicit_commit_request_and_handler():
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ExplicitMemoryProposal,
        ProposalOutcome,
        build_explicit_commit_request,
    )
    from backend.memory.source_handling import SourceHandlingOutcome
    from backend.memory.write_pipeline.models import (
        MemoryChangeSet,
        MemoryOperation,
        SourceValidity,
    )
    from backend.security.models import AuthenticatedPrincipal, AuthMode
    import pytest

    p_no_change = ExplicitMemoryProposal(outcome=ProposalOutcome.NOOP)
    principal = AuthenticatedPrincipal(
        owner_user_id="user_1",
        auth_mode=AuthMode.AUTHENTICATED,
        credential_label="jwt",
    )
    with pytest.raises(ValueError, match="Cannot build commit request"):
        build_explicit_commit_request(
            proposal=p_no_change,
            principal=principal,
            conversation_id="conv_1",
            user_message_id="msg_1",
            assistant_message_id="asst_1",
            expected_deletion_epoch=0,
            source_outbox_id="outbox_1",
        )

    # Real proposal from handler.propose for remember
    handler = ExplicitMemoryActionHandler(
        active_version_provider=lambda o, k: (),
        generation_provider=lambda o, k: 2,
    )
    state_rem = _make_state("Tôi thích đi tàu hỏa")
    und_rem = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_REMEMBER,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )
    p_mut = handler.propose(und_rem, state_rem, owner_user_id="user_1")

    req = build_explicit_commit_request(
        proposal=p_mut,
        principal=principal,
        conversation_id="conv_1",
        user_message_id="msg_1",
        assistant_message_id="asst_1",
        expected_deletion_epoch=5,
        source_outbox_id="outbox_1",
    )
    assert req.principal == principal
    assert req.conversation_id == "conv_1"
    assert req.assistant_message_id == "asst_1"
    assert req.expected_deletion_epoch == 5
    assert req.acknowledgement_text == p_mut.acknowledgement_text
    assert req.change == p_mut.change
    assert req.source_validity == SourceValidity.NOT_REQUIRED
    assert req.source_handling_record.outcome == SourceHandlingOutcome.EXPLICIT_APPLIED
    assert req.idempotency_key.startswith("exp_")

    # Real proposal for forget / revoke
    active_v = _make_version(
        "mem_trans_1",
        "travel.preference.transport_mode",
        ("bus", "train"),
    )
    handler_forget = ExplicitMemoryActionHandler(
        active_version_provider=lambda o, k: (active_v,)
    )
    state_forget = _make_state("Quên toàn bộ sở thích phương tiện di chuyển")
    und_forget = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_FORGET,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )
    p_revoke = handler_forget.propose(und_forget, state_forget, owner_user_id="user_1")

    req_revoke = handler_forget.build_commit_request(
        proposal=p_revoke,
        principal=principal,
        conversation_id="conv_1",
        user_message_id="msg_1",
        assistant_message_id="asst_1",
        expected_deletion_epoch=0,
        source_outbox_id="outbox_1",
        interaction_mode=InteractionMode.EXPLICIT_FORGET,
    )
    assert req_revoke.source_handling_record.outcome == SourceHandlingOutcome.FORGET_APPLIED
    assert req_revoke.change.operation == MemoryOperation.REVOKE
