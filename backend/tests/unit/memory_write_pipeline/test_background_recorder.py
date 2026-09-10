"""Unit tests for BackgroundMemoryRecorder.

Verifies:
- record() delegates properly to policy -> resolver -> UoW.
- Non-storable, held sensitive, or rejected candidates cause no mutations.
- Low-confidence candidates cause no mutations.
- No user-initiated command methods exist on BackgroundMemoryRecorder.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

from backend.memory.write_pipeline.background_recorder import (
    BackgroundMemoryRecorder,
    BackgroundRecordResult,
    ShadowCandidate,
)
from backend.memory.write_pipeline.models import (
    Authority,
    DecisionOutcome,
    DecisionReason,
    MemoryCandidate,
    MemoryChangeSet,
    MemoryDecisionDraft,
    MemoryOperation,
    MemoryRelation,
    MemoryScope,
    SensitivityBand,
    assertion_identity,
)
from backend.memory.write_pipeline.uow import MemoryWriteResult

MOMENT = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)


class RecordingUoW:
    def __init__(self):
        self.applied_changes = []

    def apply_memory_change(
        self,
        change: MemoryChangeSet,
        principal,
        *,
        evidence=(),
        decision=None,
        idempotency_key=None,
    ) -> MemoryWriteResult:
        self.applied_changes.append(
            {
                "change": change,
                "principal": principal,
                "evidence": evidence,
                "decision": decision,
                "idempotency_key": idempotency_key,
            }
        )
        return MemoryWriteResult(
            operation=change.operation,
            version_id=None,
            superseded_version_ids=(),
            reference_version_id=None,
            decision_id="mdc_test_01",
            reason=change.reason,
        )


def _sample_shadow_candidate(
    confidence: float = 0.95,
    key: str = "travel.preference.hotel_atmosphere",
    value: str = "quiet",
) -> ShadowCandidate:
    return ShadowCandidate(
        candidate_id="mc_test_01",
        owner_user_id="user_alice",
        canonical_key=key,
        normalized_value=value,
        display_text="prefers quiet hotels",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        scope=MemoryScope.USER,
        scope_id="global",
        confidence=confidence,
        observed_at=MOMENT,
        conversation_id="cv_12345",
        source_message_id="mev_67890",
    )


@pytest.mark.anyio
async def test_record_delegates_to_policy_resolver_and_uow():
    uow = RecordingUoW()
    mock_policy = MagicMock()
    mock_policy.return_value = MemoryDecisionDraft(
        candidate_id="mc_test_01",
        outcome=DecisionOutcome.SHADOW,
        reason=DecisionReason.SHADOW_VALID_UNPROMOTED,
    )

    mock_resolver = MagicMock()
    mock_resolver.return_value = MemoryChangeSet(
        operation=MemoryOperation.ADD,
        identity=assertion_identity(
            MemoryCandidate(
                candidate_id="mc_test_01",
                evidence_ids=("mev_test_1",),
                owner_user_id="user_alice",
                scope=MemoryScope.USER,
                conversation_id="cv_12345",
                canonical_key="travel.preference.hotel_atmosphere",
                normalized_value="quiet",
                display_text="prefers quiet hotels",
                authority=Authority.REPEATED_INFERENCE,
                sensitivity=SensitivityBand.ORDINARY_PERSONAL,
                observed_at=MOMENT,
            )
        ),
        new_version=None,
        superseded_version_ids=(),
        reference_version_id=None,
        reason="shadow_valid_unpromoted",
    )

    recorder = BackgroundMemoryRecorder(
        policy=mock_policy,
        resolver=mock_resolver,
        uow_factory=lambda: uow,
    )

    candidate = _sample_shadow_candidate()
    result = await recorder.record(candidate)

    # 1. Policy was consulted
    mock_policy.assert_called_once()
    passed_candidate, ctx = mock_policy.call_args[0]
    assert passed_candidate.owner_user_id == "user_alice"
    assert passed_candidate.canonical_key == "travel.preference.hotel_atmosphere"

    # 2. Resolver was consulted
    mock_resolver.assert_called_once()

    # 3. UoW was called with shadow NOOP change set
    assert len(uow.applied_changes) == 1
    applied = uow.applied_changes[0]
    assert applied["change"].operation == MemoryOperation.NOOP
    assert applied["principal"].owner_user_id == "user_alice"
    assert len(applied["evidence"]) == 1
    assert applied["evidence"][0].conversation_id == "cv_12345"

    # 4. Result check
    assert isinstance(result, BackgroundRecordResult)
    assert result.status == "recorded"
    assert result.decision_outcome == DecisionOutcome.SHADOW
    assert result.operation == MemoryOperation.NOOP


@pytest.mark.anyio
async def test_non_storable_rejected_candidate_does_not_mutate_uow():
    uow = RecordingUoW()
    mock_policy = MagicMock()
    mock_policy.return_value = MemoryDecisionDraft(
        candidate_id="mc_test_01",
        outcome=DecisionOutcome.REJECTED,
        reason=DecisionReason.REJECTED_PROHIBITED,
    )

    recorder = BackgroundMemoryRecorder(
        policy=mock_policy,
        uow_factory=lambda: uow,
    )

    candidate = _sample_shadow_candidate()
    result = await recorder.record(candidate)

    assert result.status == "rejected"
    assert result.decision_outcome == DecisionOutcome.REJECTED
    # UoW MUST NOT be called
    assert len(uow.applied_changes) == 0


@pytest.mark.anyio
async def test_held_sensitive_candidate_does_not_mutate_uow():
    uow = RecordingUoW()
    mock_policy = MagicMock()
    mock_policy.return_value = MemoryDecisionDraft(
        candidate_id="mc_test_01",
        outcome=DecisionOutcome.HELD_SENSITIVE,
        reason=DecisionReason.HELD_SENSITIVE,
    )

    recorder = BackgroundMemoryRecorder(
        policy=mock_policy,
        uow_factory=lambda: uow,
    )

    candidate = _sample_shadow_candidate()
    result = await recorder.record(candidate)

    assert result.status == "held_sensitive"
    assert result.decision_outcome == DecisionOutcome.HELD_SENSITIVE
    # UoW MUST NOT be called
    assert len(uow.applied_changes) == 0


@pytest.mark.anyio
async def test_low_confidence_candidate_causes_no_mutations():
    uow = RecordingUoW()
    mock_policy = MagicMock()

    recorder = BackgroundMemoryRecorder(
        policy=mock_policy,
        uow_factory=lambda: uow,
        min_confidence=0.8,
    )

    candidate = _sample_shadow_candidate(confidence=0.4)
    result = await recorder.record(candidate)

    assert result.status == "low_confidence"
    # Policy and UoW should not be called
    mock_policy.assert_not_called()
    assert len(uow.applied_changes) == 0


def test_no_user_initiated_command_methods_exist():
    """Verify BackgroundMemoryRecorder exposes NO user-initiated memory management methods."""
    forbidden_methods = [
        "remember",
        "correct",
        "forget",
        "toggle",
        "preview",
        "confirm",
        "expand",
        "list_memories",
        "delete",
        "bulk_delete",
    ]

    for method in forbidden_methods:
        assert not hasattr(BackgroundMemoryRecorder, method), (
            f"BackgroundMemoryRecorder must not expose user-initiated method '{method}'"
        )


def test_record_sync_convenience():
    uow = RecordingUoW()
    mock_policy = MagicMock()
    mock_policy.return_value = MemoryDecisionDraft(
        candidate_id="mc_test_01",
        outcome=DecisionOutcome.SHADOW,
        reason=DecisionReason.SHADOW_VALID_UNPROMOTED,
    )

    recorder = BackgroundMemoryRecorder(policy=mock_policy, uow_factory=lambda: uow)

    candidate = _sample_shadow_candidate()
    result = recorder.record_sync(candidate)

    assert isinstance(result, BackgroundRecordResult)
    assert result.status == "recorded"
    assert len(uow.applied_changes) == 1
