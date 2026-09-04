"""Unit tests for the R5 memory policy evaluator.

Policy is a pure draft-to-decision function: it never calls a model, never
touches storage, and never logs content. Each governed reason code has at
least one deterministic trigger defined by `MemoryPolicy` and documented
here by example.

No test here touches a database, a model provider, Chroma, or the network.
"""

import dataclasses

from backend.memory.models import (
    MemoryCandidateDraft,
    MemoryCandidateStatus,
    MemoryScope,
    MemoryType,
    PolicyReason,
    SensitivityLabel,
)
from backend.memory.policy import (
    POLICY_CONFIDENCE_ACCEPT,
    POLICY_CONFIDENCE_FLOOR,
    POLICY_ID,
    MemoryPolicy,
)


def _draft(**overrides) -> MemoryCandidateDraft:
    payload = {
        "source_message_id": "ms_example",
        "conversation_id": "cv_example",
        "workspace_id": "tw_example",
        "source_sequence": 1,
        "role": "user",
        "source": "ui",
        "trace_visibility": "included",
        "proposed_scope": MemoryScope.USER,
        "proposed_type": MemoryType.PREFERENCE,
        "confidence": 0.8,
        "sensitivity_label": SensitivityLabel.NONE,
        "text": "Người dùng ăn chay trường.",
        "evidence_summary": "ăn chay trường",
    }
    payload.update(overrides)
    return MemoryCandidateDraft(**payload)


def _decide(**overrides):
    decided = MemoryPolicy().evaluate(_draft(**overrides))
    return decided.status, decided.reason


# 1. Supported candidates are accepted with their governed reason.


def test_supported_preference_is_accepted():
    assert _decide() == (
        MemoryCandidateStatus.ACCEPTED,
        PolicyReason.SUPPORTED_PREFERENCE,
    )


def test_supported_constraint_is_accepted():
    assert _decide(
        proposed_scope=MemoryScope.WORKSPACE,
        proposed_type=MemoryType.CONSTRAINT,
    ) == (
        MemoryCandidateStatus.ACCEPTED,
        PolicyReason.SUPPORTED_CONSTRAINT,
    )


def test_supported_profile_fact_is_accepted():
    assert _decide(proposed_type=MemoryType.PROFILE_FACT) == (
        MemoryCandidateStatus.ACCEPTED,
        PolicyReason.SUPPORTED_PROFILE_FACT,
    )


def test_supported_trip_decision_is_accepted():
    assert _decide(
        proposed_scope=MemoryScope.WORKSPACE,
        proposed_type=MemoryType.DECISION,
    ) == (
        MemoryCandidateStatus.ACCEPTED,
        PolicyReason.SUPPORTED_TRIP_DECISION,
    )


def test_explicit_correction_is_accepted():
    assert _decide(proposed_type=MemoryType.CORRECTION) == (
        MemoryCandidateStatus.ACCEPTED,
        PolicyReason.EXPLICIT_CORRECTION,
    )


# 2. Weak or mismatched evidence is rejected with its governed reason.


def test_no_memory_signal_is_rejected():
    assert _decide(
        proposed_scope=MemoryScope.NONE,
        proposed_type=MemoryType.NONE,
        text="",
        evidence_summary="",
    ) == (MemoryCandidateStatus.REJECTED, PolicyReason.NO_MEMORY_SIGNAL)


def test_ambiguous_confidence_is_rejected():
    assert POLICY_CONFIDENCE_FLOOR <= 0.6 < POLICY_CONFIDENCE_ACCEPT
    assert _decide(confidence=0.6) == (
        MemoryCandidateStatus.REJECTED,
        PolicyReason.AMBIGUOUS,
    )


def test_transient_episode_is_rejected():
    assert _decide(proposed_type=MemoryType.EPISODE) == (
        MemoryCandidateStatus.REJECTED,
        PolicyReason.TRANSIENT,
    )


def test_wrong_scope_is_rejected():
    assert _decide(
        proposed_scope=MemoryScope.CONVERSATION,
        proposed_type=MemoryType.PREFERENCE,
    ) == (MemoryCandidateStatus.REJECTED, PolicyReason.WRONG_SCOPE)
    assert _decide(
        proposed_scope=MemoryScope.USER,
        proposed_type=MemoryType.DECISION,
    ) == (MemoryCandidateStatus.REJECTED, PolicyReason.WRONG_SCOPE)


def test_low_confidence_is_rejected():
    assert _decide(confidence=0.3) == (
        MemoryCandidateStatus.REJECTED,
        PolicyReason.LOW_CONFIDENCE,
    )


def test_unsupported_text_is_rejected():
    assert _decide(text="   ") == (
        MemoryCandidateStatus.REJECTED,
        PolicyReason.UNSUPPORTED,
    )


def test_system_generated_roles_are_rejected_without_new_vocabulary():
    for role in ("assistant", "tool", "system_event"):
        assert _decide(role=role) == (
            MemoryCandidateStatus.REJECTED,
            PolicyReason.SYSTEM_GENERATED,
        )


def test_non_user_source_is_system_generated():
    assert _decide(source="model") == (
        MemoryCandidateStatus.REJECTED,
        PolicyReason.SYSTEM_GENERATED,
    )


def test_trace_excluded_is_rejected():
    assert _decide(trace_visibility="excluded") == (
        MemoryCandidateStatus.REJECTED,
        PolicyReason.TRACE_EXCLUDED,
    )


# 3. Sensitive content fails closed without becoming shadow memory.


def test_personal_content_needs_user_action():
    assert _decide(sensitivity_label=SensitivityLabel.PERSONAL) == (
        MemoryCandidateStatus.NEEDS_USER_ACTION,
        PolicyReason.SENSITIVE,
    )
    assert _decide(sensitivity_label=SensitivityLabel.SENSITIVE) == (
        MemoryCandidateStatus.NEEDS_USER_ACTION,
        PolicyReason.SENSITIVE,
    )


def test_secret_like_content_is_rejected():
    assert _decide(sensitivity_label=SensitivityLabel.SECRET) == (
        MemoryCandidateStatus.REJECTED,
        PolicyReason.SECRET_LIKE,
    )
    assert _decide(sensitivity_label=SensitivityLabel.UNSAFE) == (
        MemoryCandidateStatus.REJECTED,
        PolicyReason.SECRET_LIKE,
    )


# 4. Safety precedence and decision hygiene.


def test_trace_exclusion_beats_everything():
    assert _decide(
        trace_visibility="excluded",
        role="assistant",
        sensitivity_label=SensitivityLabel.SECRET,
    ) == (MemoryCandidateStatus.REJECTED, PolicyReason.TRACE_EXCLUDED)


def test_secret_beats_acceptance_mapping():
    assert _decide(
        proposed_type=MemoryType.CORRECTION,
        sensitivity_label=SensitivityLabel.SECRET,
    ) == (MemoryCandidateStatus.REJECTED, PolicyReason.SECRET_LIKE)


def test_evaluate_preserves_provenance_and_sets_decision_only():
    draft = _draft()
    decided = MemoryPolicy().evaluate(draft)
    before = dataclasses.asdict(draft)
    after = dataclasses.asdict(decided)
    changed = {name for name in after if before[name] != after[name]}
    assert changed == {"status", "reason"}
    assert decided.source_message_id == "ms_example"
    assert decided.source_sequence == 1


def test_policy_identity():
    assert POLICY_ID == "policy-v1"
