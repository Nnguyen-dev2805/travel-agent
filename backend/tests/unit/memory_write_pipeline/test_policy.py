"""Unit tests for risk-based write policy.

Confirm-all is superseded: an ordinary preference from an explicit
command is direct-write-eligible with no second confirmation, while
restricted content is held, prohibited content is rejected, and valid
background evidence stays shadow. Decisions return data only — no
durable writes, no UI state, no confirmation tokens. No test here
touches a database, a model, HTTP, or the network.
"""

import dataclasses
from datetime import datetime, timezone

import pytest

from backend.memory.write_pipeline.models import (
    Authority,
    DecisionOutcome,
    DecisionReason,
    MemoryCandidate,
    MemoryDecisionDraft,
    SensitivityBand,
    new_candidate_id,
    new_evidence_id,
)
from backend.memory.write_pipeline.policy import (
    Actor,
    DecisionContext,
    EligibilityOutcome,
    Origin,
    classify_sensitivity,
    decide_candidate,
    evaluate_eligibility,
)
from backend.memory.write_pipeline.registry import HOTEL_ATMOSPHERE_KEY

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
RAW_SECRET = "sk-test-AbC999"


def _candidate(**overrides) -> MemoryCandidate:
    payload = {
        "candidate_id": new_candidate_id(),
        "evidence_ids": (new_evidence_id(),),
        "owner_user_id": "user_owner",
        "scope": "user",
        "conversation_id": None,
        "canonical_key": HOTEL_ATMOSPHERE_KEY,
        "normalized_value": "quiet",
        "display_text": "a quiet hotel",
        "authority": Authority.EXPLICIT_SAVE,
        "sensitivity": SensitivityBand.ORDINARY_PERSONAL,
        "observed_at": MOMENT,
    }
    payload.update(overrides)
    return MemoryCandidate(**payload)


def _context(**overrides) -> DecisionContext:
    payload = {
        "actor": Actor.USER,
        "authenticated": True,
        "origin": Origin.EXPLICIT_COMMAND,
        "source_deleted": False,
        "contextual_sensitivity": None,
    }
    payload.update(overrides)
    return DecisionContext(**payload)


# 1. Eligibility: authenticated user evidence passes; everything else fails.


def test_decision_context_requires_explicit_security_fields():
    with pytest.raises(TypeError):
        DecisionContext()


def test_unauthenticated_explicit_command_is_rejected_never_direct():
    decision = decide_candidate(_candidate(), _context(authenticated=False))

    assert decision.outcome is DecisionOutcome.REJECTED
    assert decision.outcome is not DecisionOutcome.DIRECT_WRITE


def test_authenticated_user_evidence_is_eligible():
    assert (
        evaluate_eligibility(
            actor=Actor.USER,
            authenticated=True,
            source_deleted=False,
            canonical_key=HOTEL_ATMOSPHERE_KEY,
        )
        is EligibilityOutcome.ELIGIBLE
    )


@pytest.mark.parametrize("actor", [Actor.ASSISTANT, Actor.TOOL, Actor.EXTERNAL])
def test_non_user_actors_are_rejected(actor):
    assert (
        evaluate_eligibility(
            actor=actor,
            authenticated=True,
            source_deleted=False,
            canonical_key=HOTEL_ATMOSPHERE_KEY,
        )
        is EligibilityOutcome.INELIGIBLE_ACTOR
    )


def test_unauthenticated_evidence_is_rejected():
    assert (
        evaluate_eligibility(
            actor=Actor.USER,
            authenticated=False,
            source_deleted=False,
            canonical_key=HOTEL_ATMOSPHERE_KEY,
        )
        is EligibilityOutcome.INELIGIBLE_AUTH
    )


def test_deleted_source_is_rejected():
    assert (
        evaluate_eligibility(
            actor=Actor.USER,
            authenticated=True,
            source_deleted=True,
            canonical_key=HOTEL_ATMOSPHERE_KEY,
        )
        is EligibilityOutcome.INELIGIBLE_SOURCE
    )


def test_unknown_key_is_rejected():
    assert (
        evaluate_eligibility(
            actor=Actor.USER,
            authenticated=True,
            source_deleted=False,
            canonical_key="travel.preference.unknown_key",
        )
        is EligibilityOutcome.INELIGIBLE_KEY
    )


# 2. Ordinary explicit saves commit directly with no second confirmation.


def test_ordinary_explicit_save_is_direct_write_eligible():
    candidate = _candidate()
    decision = decide_candidate(candidate, _context())

    assert decision.outcome is DecisionOutcome.DIRECT_WRITE
    assert decision.reason is DecisionReason.DIRECT_WRITE_ELIGIBLE
    assert decision.candidate_id == candidate.candidate_id


def test_direct_write_decision_carries_no_token_or_ui_state():
    decision = decide_candidate(_candidate(), _context())

    assert isinstance(decision, MemoryDecisionDraft)
    assert {item.name for item in dataclasses.fields(decision)} == {
        "candidate_id",
        "outcome",
        "reason",
    }
    assert "confirmation" not in str(decision).lower()
    assert "token" not in str(decision).lower()


def test_policy_same_input_equal():
    candidate = _candidate()
    context = _context()

    assert decide_candidate(candidate, context) == decide_candidate(candidate, context)


# 3. Sensitivity: floor first, contextual escalation only raises.


def test_registry_floor_without_escalation_stays_ordinary():
    assert (
        classify_sensitivity(
            floor=SensitivityBand.ORDINARY_PERSONAL,
            secret_hit=False,
            contextual=None,
        )
        is SensitivityBand.ORDINARY_PERSONAL
    )


def test_contextual_escalation_raises_but_never_lowers():
    assert (
        classify_sensitivity(
            floor=SensitivityBand.ORDINARY_PERSONAL,
            secret_hit=False,
            contextual=SensitivityBand.CONTEXTUALLY_SENSITIVE,
        )
        is SensitivityBand.CONTEXTUALLY_SENSITIVE
    )
    assert (
        classify_sensitivity(
            floor=SensitivityBand.CONTEXTUALLY_SENSITIVE,
            secret_hit=False,
            contextual=SensitivityBand.ORDINARY_PERSONAL,
        )
        is SensitivityBand.CONTEXTUALLY_SENSITIVE
    )


def test_secret_hit_escalates_to_prohibited():
    assert (
        classify_sensitivity(
            floor=SensitivityBand.ORDINARY_PERSONAL,
            secret_hit=True,
            contextual=None,
        )
        is SensitivityBand.PROHIBITED_SECRET
    )


def test_contextually_sensitive_content_is_held_not_durable():
    decision = decide_candidate(
        _candidate(), _context(contextual_sensitivity=SensitivityBand.RESTRICTED)
    )

    assert decision.outcome is DecisionOutcome.HELD_SENSITIVE
    assert decision.reason is DecisionReason.HELD_SENSITIVE


# 4. Prohibited content is rejected with zero raw-value leakage.


def test_prohibited_candidate_is_rejected():
    exposed = _candidate(
        display_text=f"api key {RAW_SECRET} remember it",
        sensitivity=SensitivityBand.PROHIBITED_SECRET,
    )
    decision = decide_candidate(exposed, _context())

    assert decision.outcome is DecisionOutcome.REJECTED
    assert decision.reason is DecisionReason.REJECTED_PROHIBITED
    assert RAW_SECRET not in str(decision)
    assert RAW_SECRET not in repr(decision)


def test_unknown_registry_value_is_invalid_never_direct():
    decision = decide_candidate(_candidate(normalized_value="beachfront"), _context())

    assert decision.outcome is DecisionOutcome.INVALID
    assert decision.reason is DecisionReason.INVALID_VALUE


def test_non_empty_condition_is_invalid():
    decision = decide_candidate(_candidate(condition="near the beach"), _context())

    assert decision.outcome is DecisionOutcome.INVALID
    assert decision.reason is DecisionReason.INVALID_CONDITION


# 5. Valid background evidence stays shadow, never active.


def test_background_evidence_is_shadow_not_active():
    inferred = _candidate(authority=Authority.REPEATED_INFERENCE)
    decision = decide_candidate(inferred, _context(origin=Origin.BACKGROUND_CHAT))

    assert decision.outcome is DecisionOutcome.SHADOW
    assert decision.reason is DecisionReason.SHADOW_VALID_UNPROMOTED


def test_explicit_command_below_save_authority_is_shadow():
    stated = _candidate(authority=Authority.EXPLICIT_STATEMENT)
    decision = decide_candidate(stated, _context())

    assert decision.outcome is DecisionOutcome.SHADOW


# 6. Hard-policy failures are never shadow.


@pytest.mark.parametrize(
    ("candidate_kwargs", "context_kwargs", "outcome"),
    [
        (
            {},
            {"actor": Actor.ASSISTANT},
            DecisionOutcome.REJECTED,
        ),
        ({}, {"authenticated": False}, DecisionOutcome.REJECTED),
        ({}, {"source_deleted": True}, DecisionOutcome.REJECTED),
        (
            {"canonical_key": "travel.preference.unknown_key"},
            {},
            DecisionOutcome.INVALID,
        ),
        (
            {"sensitivity": SensitivityBand.PROHIBITED_SECRET},
            {},
            DecisionOutcome.REJECTED,
        ),
    ],
    ids=["actor", "auth", "source", "key", "prohibited"],
)
def test_hard_policy_failures_are_never_shadow(
    candidate_kwargs, context_kwargs, outcome
):
    decision = decide_candidate(
        _candidate(**candidate_kwargs), _context(**context_kwargs)
    )

    assert decision.outcome is outcome
    assert decision.outcome is not DecisionOutcome.SHADOW
