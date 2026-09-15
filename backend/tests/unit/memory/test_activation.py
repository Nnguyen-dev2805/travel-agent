"""Unit tests for pure deterministic MemoryActivationPolicy (ADR 0038 / Plan v0.18)."""

from datetime import datetime, timezone
import pytest

from backend.memory.activation import (
    ActivationDecision,
    ActivationFacts,
    ActivationReason,
    EvidenceIdentity,
    MemoryActivationPolicy,
)
from backend.memory.write_pipeline.models import (
    Authority,
    MemoryEvidence,
    MemoryScope,
    VersionStatus,
)


def _make_evidence(
    eid: str, cid: str, mid: str, text: str = "preference text"
) -> MemoryEvidence:
    return MemoryEvidence(
        evidence_id=eid if eid.startswith("mev_") else f"mev_{eid}",
        owner_user_id="user_1",
        conversation_id=cid,
        source_message_id=mid,
        display_text=text,
        authority=Authority.REPEATED_INFERENCE,
        observed_at=datetime.now(timezone.utc),
    )


def _facts(**overrides) -> ActivationFacts:
    """Build activation facts with every gate input stated explicitly.

    `ActivationFacts` deliberately has no permissive defaults — a field that
    could *permit* activation is required — so each test states what it means
    rather than inheriting "eligible" or "conclusive" by omission.
    """
    base = dict(
        has_unresolved_conflict=False,
        is_constraint=False,
        lifecycle_eligible=True,
        type_evaluation_conclusive=True,
        memory_family="semantic",
    )
    base.update(overrides)
    return ActivationFacts(**base)


def test_conversation_scope_single_turn_is_shadow():
    policy = MemoryActivationPolicy()
    facts = _facts(
        scope=MemoryScope.CONVERSATION,
        canonical_key="travel.preference.hotel_atmosphere",
        target_conversation_id="conv_1",
        candidate_evidence=[_make_evidence("ev_1", "conv_1", "msg_1")],
        active_evidence=[],
        inferred_activation_enabled=True,
    )
    decision = policy.evaluate(facts)
    assert decision.target_status == VersionStatus.SHADOW
    assert decision.reason == ActivationReason.INSUFFICIENT_TURNS
    assert not decision.eligible


def test_conversation_scope_two_agreeing_turns_is_active():
    policy = MemoryActivationPolicy()
    facts = _facts(
        scope=MemoryScope.CONVERSATION,
        canonical_key="travel.preference.hotel_atmosphere",
        target_conversation_id="conv_1",
        candidate_evidence=[_make_evidence("ev_2", "conv_1", "msg_2")],
        active_evidence=[EvidenceIdentity(evidence_id="ev_1", conversation_id="conv_1", source_message_id="msg_1")],
        inferred_activation_enabled=True,
    )
    decision = policy.evaluate(facts)
    assert decision.target_status == VersionStatus.ACTIVE
    assert decision.reason == ActivationReason.ELIGIBLE_ACTIVE
    assert decision.eligible


def test_conversation_scope_duplicate_message_turn_does_not_increase_support():
    policy = MemoryActivationPolicy()
    facts = _facts(
        scope=MemoryScope.CONVERSATION,
        canonical_key="travel.preference.hotel_atmosphere",
        target_conversation_id="conv_1",
        # Same source_message_id msg_1 re-extracted
        candidate_evidence=[_make_evidence("ev_2", "conv_1", "msg_1")],
        active_evidence=[EvidenceIdentity(evidence_id="ev_1", conversation_id="conv_1", source_message_id="msg_1")],
        inferred_activation_enabled=True,
    )
    decision = policy.evaluate(facts)
    assert decision.target_status == VersionStatus.SHADOW
    assert decision.reason == ActivationReason.INSUFFICIENT_TURNS


def test_user_scope_two_evidence_across_two_convs_is_shadow():
    policy = MemoryActivationPolicy()
    facts = _facts(
        scope=MemoryScope.USER,
        canonical_key="travel.preference.hotel_atmosphere",
        target_conversation_id="conv_2",
        candidate_evidence=[_make_evidence("ev_2", "conv_2", "msg_2")],
        active_evidence=[_make_evidence("ev_1", "conv_1", "msg_1")],
        inferred_activation_enabled=True,
    )
    decision = policy.evaluate(facts)
    assert decision.target_status == VersionStatus.SHADOW
    assert decision.reason == ActivationReason.INSUFFICIENT_EVIDENCE


def test_user_scope_three_evidence_in_single_conv_is_shadow():
    policy = MemoryActivationPolicy()
    facts = _facts(
        scope=MemoryScope.USER,
        canonical_key="travel.preference.hotel_atmosphere",
        target_conversation_id="conv_1",
        candidate_evidence=[_make_evidence("ev_3", "conv_1", "msg_3")],
        active_evidence=[
            _make_evidence("ev_1", "conv_1", "msg_1"),
            _make_evidence("ev_2", "conv_1", "msg_2"),
        ],
        inferred_activation_enabled=True,
    )
    decision = policy.evaluate(facts)
    assert decision.target_status == VersionStatus.SHADOW
    assert decision.reason == ActivationReason.INSUFFICIENT_CONVERSATIONS


def test_user_scope_three_evidence_across_two_convs_is_active():
    policy = MemoryActivationPolicy()
    facts = _facts(
        scope=MemoryScope.USER,
        canonical_key="travel.preference.hotel_atmosphere",
        target_conversation_id="conv_2",
        candidate_evidence=[_make_evidence("ev_3", "conv_2", "msg_3")],
        active_evidence=[
            _make_evidence("ev_1", "conv_1", "msg_1"),
            _make_evidence("ev_2", "conv_1", "msg_2"),
        ],
        inferred_activation_enabled=True,
    )
    decision = policy.evaluate(facts)
    assert decision.target_status == VersionStatus.ACTIVE
    assert decision.reason == ActivationReason.ELIGIBLE_ACTIVE
    assert decision.eligible


def test_user_scope_duplicate_delivery_contributes_zero_additional_support():
    policy = MemoryActivationPolicy()
    facts = _facts(
        scope=MemoryScope.USER,
        canonical_key="travel.preference.hotel_atmosphere",
        target_conversation_id="conv_2",
        # ev_1 redelivered / same msg_1 re-extracted
        candidate_evidence=[_make_evidence("ev_1", "conv_1", "msg_1")],
        active_evidence=[
            _make_evidence("ev_1", "conv_1", "msg_1"),
            _make_evidence("ev_2", "conv_2", "msg_2"),
        ],
        inferred_activation_enabled=True,
    )
    decision = policy.evaluate(facts)
    assert decision.target_status == VersionStatus.SHADOW
    assert decision.reason == ActivationReason.INSUFFICIENT_EVIDENCE


def test_unresolved_conflict_refuses_active():
    policy = MemoryActivationPolicy()
    facts = _facts(
        scope=MemoryScope.CONVERSATION,
        canonical_key="travel.preference.hotel_atmosphere",
        target_conversation_id="conv_1",
        candidate_evidence=[_make_evidence("ev_2", "conv_1", "msg_2")],
        active_evidence=[_make_evidence("ev_1", "conv_1", "msg_1")],
        has_unresolved_conflict=True,
        inferred_activation_enabled=True,
    )
    decision = policy.evaluate(facts)
    assert decision.target_status == VersionStatus.SHADOW
    assert decision.reason == ActivationReason.UNRESOLVED_CONFLICT


def test_inferred_constraints_remain_shadow_only():
    policy = MemoryActivationPolicy()
    facts = _facts(
        scope=MemoryScope.CONVERSATION,
        canonical_key="travel.constraint.dietary",
        target_conversation_id="conv_1",
        candidate_evidence=[_make_evidence("ev_2", "conv_1", "msg_2")],
        active_evidence=[_make_evidence("ev_1", "conv_1", "msg_1")],
        is_constraint=True,
        inferred_activation_enabled=True,
    )
    decision = policy.evaluate(facts)
    assert decision.target_status == VersionStatus.SHADOW
    assert decision.reason == ActivationReason.CONSTRAINTS_SHADOW_ONLY


def test_procedural_memory_chat_forbidden():
    policy = MemoryActivationPolicy()
    facts = _facts(
        scope=MemoryScope.CONVERSATION,
        canonical_key="procedural.policy.refund",
        target_conversation_id="conv_1",
        candidate_evidence=[_make_evidence("ev_2", "conv_1", "msg_2")],
        active_evidence=[_make_evidence("ev_1", "conv_1", "msg_1")],
        memory_family="procedural",
        inferred_activation_enabled=True,
    )
    decision = policy.evaluate(facts)
    assert decision.target_status == VersionStatus.SHADOW
    assert decision.reason == ActivationReason.PROCEDURAL_CHAT_FORBIDDEN


def test_rollout_flag_disabled_refuses_active():
    policy = MemoryActivationPolicy()
    facts = _facts(
        scope=MemoryScope.CONVERSATION,
        canonical_key="travel.preference.hotel_atmosphere",
        target_conversation_id="conv_1",
        candidate_evidence=[_make_evidence("ev_2", "conv_1", "msg_2")],
        active_evidence=[_make_evidence("ev_1", "conv_1", "msg_1")],
        inferred_activation_enabled=False,
    )
    decision = policy.evaluate(facts)
    assert decision.target_status == VersionStatus.SHADOW
    assert decision.reason == ActivationReason.ROLLOUT_FLAG_DISABLED


def test_type_evaluation_inconclusive_refuses_active():
    policy = MemoryActivationPolicy()
    facts = _facts(
        scope=MemoryScope.CONVERSATION,
        canonical_key="travel.preference.hotel_atmosphere",
        target_conversation_id="conv_1",
        candidate_evidence=[_make_evidence("ev_2", "conv_1", "msg_2")],
        active_evidence=[_make_evidence("ev_1", "conv_1", "msg_1")],
        inferred_activation_enabled=True,
        type_evaluation_conclusive=False,
    )
    decision = policy.evaluate(facts)
    assert decision.target_status == VersionStatus.SHADOW
    assert decision.reason == ActivationReason.TYPE_EVALUATION_INCONCLUSIVE


def test_lifecycle_denial_prerequisite_fails_closed():
    policy = MemoryActivationPolicy()
    facts = _facts(
        scope=MemoryScope.CONVERSATION,
        canonical_key="travel.preference.hotel_atmosphere",
        target_conversation_id="conv_1",
        candidate_evidence=[_make_evidence("ev_2", "conv_1", "msg_2")],
        active_evidence=[_make_evidence("ev_1", "conv_1", "msg_1")],
        inferred_activation_enabled=True,
        lifecycle_eligible=False,
    )
    decision = policy.evaluate(facts)
    assert decision.target_status == VersionStatus.SHADOW
    assert decision.reason == ActivationReason.LIFECYCLE_DENIED
