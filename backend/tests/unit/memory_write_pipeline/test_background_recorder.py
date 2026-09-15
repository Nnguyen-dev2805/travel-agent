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

from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingOutcome,
    SourceHandlingReason,
    SourceHandlingRecord,
)
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
    VersionStatus,
    assertion_identity,
)
from backend.memory.write_pipeline.uow import MemoryWriteResult

MOMENT = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)


class RecordingUoW:
    def __init__(self):
        self.applied_changes = []
        self.active_versions: list = []
        self.assertion_id: str | None = None
        self.has_unresolved_conflict = False
        self.assertion_generation = 1

    def get_active_versions(self, owner_user_id: str, canonical_key: str):
        """Return this double's active versions for one owner and key.

        Required by `MemoryUnitOfWork`. The recorder no longer probes with
        `hasattr`, so a double without this method is a type error rather than a
        silently empty history (C8).
        """
        return tuple(
            version
            for version in self.active_versions
            if getattr(version, "owner_user_id", None) == owner_user_id
            and getattr(version, "canonical_key", None) == canonical_key
        )

    def get_assertion_identity_details(self, identity):
        """Return `(assertion_id, has_unresolved_conflict)` for one identity.

        `(None, False)` models the first write to a key: the assertion does not
        exist yet, so there is nothing to be in conflict with.
        """
        return self.assertion_id, self.has_unresolved_conflict

    def get_assertion_generation(self, owner_user_id: str, canonical_key: str) -> int:
        """Return this double's current suppression generation.

        Required by `MemoryUnitOfWork`. The ACTIVATION-stage lifecycle facts
        compare it against the candidate's stamp; a double that cannot answer
        would make `STALE_GENERATION` structurally unsatisfiable.
        """
        return self.assertion_generation

    def apply_memory_change(
        self,
        change: MemoryChangeSet,
        principal,
        *,
        evidence=(),
        decision=None,
        idempotency_key=None,
        fence=None,
        source_validity=None,
    ) -> MemoryWriteResult:
        self.applied_changes.append(
            {
                "change": change,
                "principal": principal,
                "evidence": evidence,
                "decision": decision,
                "idempotency_key": idempotency_key,
                "fence": fence,
                "source_validity": source_validity,
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
    candidate_id: str = "mc_test_01",
) -> ShadowCandidate:
    return ShadowCandidate(
        candidate_id=candidate_id,
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


def _fence():
    from backend.memory.write_pipeline.uow import FenceContext

    return FenceContext(
        conversation_id="cv_12345",
        expected_epoch=0,
        outbox_id="cout_1",
        lease_owner="worker_1",
    )


def _eligible_record(outbox_id: str = "cout_1") -> SourceHandlingRecord:
    """A persisted positive source-handling authority record."""
    return SourceHandlingRecord(
        source_outbox_id=outbox_id,
        source_message_id="msg_source",
        family=MemoryFamily.SEMANTIC,
        outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
        recorded_at=MOMENT,
    )


def _recorder(**overrides) -> BackgroundMemoryRecorder:
    """Build a recorder whose source is positively handled.

    The recorder refuses every source without a persisted `BACKGROUND_ELIGIBLE`
    record — absence is `UNHANDLED`, and `UNHANDLED` is not permission. Tests that
    exercise the policy, resolver, or persistence path must therefore state that
    precondition instead of inheriting it from a fail-open gate.
    """
    overrides.setdefault(
        "source_handling_loader",
        lambda owner, outbox_id: _eligible_record(outbox_id),
    )
    return BackgroundMemoryRecorder(**overrides)


def test_record_delegates_to_policy_resolver_and_uow():
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

    recorder = _recorder(
        policy=mock_policy,
        resolver=mock_resolver,
        uow_factory=lambda: uow,
    )

    candidate = _sample_shadow_candidate()
    result = recorder.record_sync(candidate, fence=_fence())

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


def test_non_storable_rejected_candidate_does_not_mutate_uow():
    uow = RecordingUoW()
    mock_policy = MagicMock()
    mock_policy.return_value = MemoryDecisionDraft(
        candidate_id="mc_test_01",
        outcome=DecisionOutcome.REJECTED,
        reason=DecisionReason.REJECTED_PROHIBITED,
    )

    recorder = _recorder(
        policy=mock_policy,
        uow_factory=lambda: uow,
    )

    candidate = _sample_shadow_candidate()
    result = recorder.record_sync(candidate, fence=_fence())

    assert result.status == "rejected"
    assert result.decision_outcome == DecisionOutcome.REJECTED
    # UoW MUST NOT be called
    assert len(uow.applied_changes) == 0


def test_held_sensitive_candidate_does_not_mutate_uow():
    uow = RecordingUoW()
    mock_policy = MagicMock()
    mock_policy.return_value = MemoryDecisionDraft(
        candidate_id="mc_test_01",
        outcome=DecisionOutcome.HELD_SENSITIVE,
        reason=DecisionReason.HELD_SENSITIVE,
    )

    recorder = _recorder(
        policy=mock_policy,
        uow_factory=lambda: uow,
    )

    candidate = _sample_shadow_candidate()
    result = recorder.record_sync(candidate, fence=_fence())

    assert result.status == "held_sensitive"
    assert result.decision_outcome == DecisionOutcome.HELD_SENSITIVE
    # UoW MUST NOT be called
    assert len(uow.applied_changes) == 0


def test_low_confidence_candidate_causes_no_mutations():
    uow = RecordingUoW()
    mock_policy = MagicMock()

    recorder = _recorder(
        policy=mock_policy,
        uow_factory=lambda: uow,
        min_confidence=0.8,
    )

    candidate = _sample_shadow_candidate(confidence=0.4)
    result = recorder.record_sync(candidate, fence=_fence())

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

    recorder = _recorder(policy=mock_policy, uow_factory=lambda: uow)

    candidate = _sample_shadow_candidate()
    result = recorder.record_sync(candidate, fence=_fence())

    assert isinstance(result, BackgroundRecordResult)
    assert result.status == "recorded"
    assert len(uow.applied_changes) == 1


def test_redelivery_with_fresh_candidate_ids_deduplicates():
    """The idempotency key derives from the semantic effect, not the minted id."""
    uow = RecordingUoW()
    mock_policy = MagicMock()
    mock_policy.return_value = MemoryDecisionDraft(
        candidate_id="mc_test_01",
        outcome=DecisionOutcome.SHADOW,
        reason=DecisionReason.SHADOW_VALID_UNPROMOTED,
    )

    recorder = _recorder(policy=mock_policy, uow_factory=lambda: uow)

    first = _sample_shadow_candidate()
    second = ShadowCandidate(
        candidate_id="mc_test_02",
        owner_user_id="user_alice",
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        display_text="prefers quiet hotels",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        scope=MemoryScope.USER,
        scope_id="global",
        confidence=0.95,
        observed_at=MOMENT,
        conversation_id="cv_12345",
        source_message_id="mev_67890",
    )

    assert first.candidate_id != second.candidate_id
    recorder.record_sync(first, source_outbox_id="cout_1", fence=_fence())
    recorder.record_sync(second, source_outbox_id="cout_1", fence=_fence())

    keys = [applied["idempotency_key"] for applied in uow.applied_changes]
    assert len(keys) == 2
    assert keys[0] == keys[1]
    assert "mc_test_01" not in keys[0] and "mc_test_02" not in keys[0]


def test_different_values_produce_different_keys():
    uow = RecordingUoW()
    mock_policy = MagicMock()
    mock_policy.return_value = MemoryDecisionDraft(
        candidate_id="mc_test_01",
        outcome=DecisionOutcome.SHADOW,
        reason=DecisionReason.SHADOW_VALID_UNPROMOTED,
    )

    recorder = _recorder(policy=mock_policy, uow_factory=lambda: uow)

    recorder.record_sync(_sample_shadow_candidate(), source_outbox_id="cout_1", fence=_fence())
    lively = ShadowCandidate(
        candidate_id="mc_test_03",
        owner_user_id="user_alice",
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="lively",
        display_text="prefers lively hotels",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        scope=MemoryScope.USER,
        scope_id="global",
        confidence=0.95,
        observed_at=MOMENT,
        conversation_id="cv_12345",
        source_message_id="mev_67890",
    )
    recorder.record_sync(lively, source_outbox_id="cout_1", fence=_fence())

    keys = [applied["idempotency_key"] for applied in uow.applied_changes]
    assert keys[0] != keys[1]


def test_fence_is_propagated_to_the_uow():
    """Forgetting fence= must fail this test, not pass silently."""
    from backend.memory.write_pipeline.uow import FenceContext

    uow = RecordingUoW()
    mock_policy = MagicMock()
    mock_policy.return_value = MemoryDecisionDraft(
        candidate_id="mc_test_01",
        outcome=DecisionOutcome.SHADOW,
        reason=DecisionReason.SHADOW_VALID_UNPROMOTED,
    )

    recorder = _recorder(policy=mock_policy, uow_factory=lambda: uow)
    fence = FenceContext(
        conversation_id="cv_12345",
        expected_epoch=0,
        outbox_id="cout_1",
        lease_owner="worker_1",
    )
    recorder.record_sync(
        _sample_shadow_candidate(), source_outbox_id="cout_1", fence=fence
    )

    assert len(uow.applied_changes) == 1
    assert uow.applied_changes[0]["fence"] is fence


def test_same_observation_under_different_owners_keys_differently():
    """The owner is part of the key material: no cross-owner dedup."""
    from backend.memory.write_pipeline.uow import FenceContext  # noqa: F401

    uow = RecordingUoW()
    mock_policy = MagicMock()
    mock_policy.return_value = MemoryDecisionDraft(
        candidate_id="mc_test_01",
        outcome=DecisionOutcome.SHADOW,
        reason=DecisionReason.SHADOW_VALID_UNPROMOTED,
    )

    recorder = _recorder(policy=mock_policy, uow_factory=lambda: uow)

    def _owned(owner: str) -> ShadowCandidate:
        base = _sample_shadow_candidate()
        return ShadowCandidate(
            candidate_id=base.candidate_id,
            owner_user_id=owner,
            canonical_key=base.canonical_key,
            normalized_value=base.normalized_value,
            display_text=base.display_text,
            authority=base.authority,
            sensitivity=base.sensitivity,
            scope=base.scope,
            scope_id=base.scope_id,
            confidence=base.confidence,
            observed_at=base.observed_at,
            conversation_id=base.conversation_id,
            source_message_id=base.source_message_id,
        )

    recorder.record_sync(_owned("user_alice"), source_outbox_id="cout_1", fence=_fence())
    recorder.record_sync(_owned("user_bob"), source_outbox_id="cout_1", fence=_fence())

    keys = [applied["idempotency_key"] for applied in uow.applied_changes]
    assert len(keys) == 2
    assert keys[0] != keys[1]


# ---------------------------------------------------------------------------
# C8 - the resolver must receive the real active-version history
# ---------------------------------------------------------------------------


class _HistoryCaptured(Exception):
    """Raised by the stub resolver to stop the recorder once history is seen."""


def _shadow_policy():
    """A policy that shadows every candidate, so resolution is reached."""
    policy = MagicMock()
    policy.return_value = MemoryDecisionDraft(
        candidate_id="mc_test_01",
        outcome=DecisionOutcome.SHADOW,
        reason=DecisionReason.SHADOW_VALID_UNPROMOTED,
    )
    return policy


def _stored_version(owner: str, key: str, value: str = "quiet"):
    """A stand-in stored version; the double only needs an owner and a key."""
    from types import SimpleNamespace

    return SimpleNamespace(
        owner_user_id=owner, canonical_key=key, normalized_value=value
    )


def _capture_history(uow):
    """A recorder whose resolver records the history it was handed."""
    seen: list[tuple] = []

    def resolver(candidate, current, relation=None):
        seen.append(current)
        raise _HistoryCaptured()

    recorder = _recorder(
        policy=_shadow_policy(), resolver=resolver, uow_factory=lambda: uow
    )
    return recorder, seen


def test_recorder_passes_the_stored_active_versions_to_the_resolver():
    """C8: the resolver used to always receive `()`, so every contradiction,
    supersession and reinforcement was unreachable."""
    uow = RecordingUoW()
    stored = _stored_version("user_alice", "travel.preference.hotel_atmosphere")
    uow.active_versions.append(stored)
    recorder, seen = _capture_history(uow)

    with pytest.raises(_HistoryCaptured):
        recorder.record_sync(_sample_shadow_candidate(), fence=_fence())

    assert seen == [(stored,)]


def test_recorder_history_is_scoped_to_the_owner_and_the_key():
    """Another owner's versions, or another key's, must never leak in."""
    uow = RecordingUoW()
    uow.active_versions.append(
        _stored_version("user_bob", "travel.preference.hotel_atmosphere")
    )
    uow.active_versions.append(_stored_version("user_alice", "travel.other.key"))
    recorder, seen = _capture_history(uow)

    with pytest.raises(_HistoryCaptured):
        recorder.record_sync(_sample_shadow_candidate(), fence=_fence())

    assert seen == [()]


def test_recorder_fails_loudly_when_the_uow_lacks_the_capability():
    """A unit of work without the read is a type error, not an empty history.

    This is the fail-fast the specification requires: the removed `hasattr`
    probe is what let the defect live unnoticed, because a probe that returns
    false is indistinguishable from a legitimately empty history.
    """

    class _NoHistoryUoW:
        def apply_memory_change(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("must not be reached")

    recorder = _recorder(
        policy=_shadow_policy(),
        resolver=MagicMock(),
        uow_factory=lambda: _NoHistoryUoW(),
    )

    with pytest.raises(AttributeError):
        recorder.record_sync(_sample_shadow_candidate(), fence=_fence())


# ---------------------------------------------------------------------------
# C9 - the confidence gate must actually gate
# ---------------------------------------------------------------------------


def test_low_confidence_candidate_is_rejected_before_persistence():
    uow = RecordingUoW()
    recorder = _recorder(
        policy=_shadow_policy(), resolver=MagicMock(), uow_factory=lambda: uow
    )

    result = recorder.record_sync(
        _sample_shadow_candidate(confidence=0.2), fence=_fence()
    )

    assert result.status == "low_confidence"
    assert uow.applied_changes == [], "a rejected candidate must not be persisted"
    assert result.operation is MemoryOperation.NOOP


def test_confidence_just_below_the_threshold_is_rejected():
    from backend.memory.write_pipeline.background_recorder import (
        MIN_CONFIDENCE_THRESHOLD,
    )

    uow = RecordingUoW()
    recorder = _recorder(
        policy=_shadow_policy(), resolver=MagicMock(), uow_factory=lambda: uow
    )

    result = recorder.record_sync(
        _sample_shadow_candidate(confidence=MIN_CONFIDENCE_THRESHOLD - 0.01),
        fence=_fence(),
    )

    assert result.status == "low_confidence"


def test_confidence_at_the_threshold_reaches_resolution():
    from backend.memory.write_pipeline.background_recorder import (
        MIN_CONFIDENCE_THRESHOLD,
    )

    uow = RecordingUoW()

    def resolver(candidate, current, relation=None):
        raise _HistoryCaptured()

    recorder = _recorder(
        policy=_shadow_policy(), resolver=resolver, uow_factory=lambda: uow
    )

    with pytest.raises(_HistoryCaptured):
        recorder.record_sync(
            _sample_shadow_candidate(confidence=MIN_CONFIDENCE_THRESHOLD),
            fence=_fence(),
        )


def test_shadow_candidate_confidence_reaches_the_gate():
    """The gate reads the producer's own confidence, not a defaulted `1.0`."""
    uow = RecordingUoW()
    recorder = _recorder(
        policy=_shadow_policy(), resolver=MagicMock(), uow_factory=lambda: uow
    )

    result = recorder.record_sync(
        _sample_shadow_candidate(confidence=0.1), fence=_fence()
    )

    assert result.status == "low_confidence"
    assert "0.10" in result.reason


def test_candidate_confidence_is_carried_onto_the_memory_candidate():
    """`_to_memory_candidate` must not drop the field on the floor."""
    recorder = _recorder(uow_factory=RecordingUoW())

    converted = recorder._to_memory_candidate(
        _sample_shadow_candidate(confidence=0.3)
    )

    assert converted.confidence == pytest.approx(0.3)


def test_memory_candidate_keeps_its_own_confidence():
    """A `MemoryCandidate` is passed through, confidence included."""
    recorder = _recorder(uow_factory=RecordingUoW())
    candidate = MemoryCandidate(
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
        confidence=0.25,
    )

    assert recorder._to_memory_candidate(candidate).confidence == pytest.approx(0.25)


def test_memory_candidate_rejects_a_non_numeric_confidence():
    with pytest.raises(ValueError):
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
            confidence="high",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Task 11 / Stage 4: Background Semantic Formation, Activation & Source Handling
# ---------------------------------------------------------------------------


def test_non_eligible_source_handling_outcome_refuses_recording():
    from backend.memory.source_handling import (
        MemoryFamily,
        SourceHandlingOutcome,
        SourceHandlingReason,
        SourceHandlingRecord,
    )

    uow = RecordingUoW()
    recorder = _recorder(
        policy=_shadow_policy(),
        uow_factory=lambda: uow,
    )
    non_eligible_record = SourceHandlingRecord(
        source_outbox_id="cout_1",
        source_message_id="mev_1",
        family=MemoryFamily.SEMANTIC,
        outcome=SourceHandlingOutcome.EXPLICIT_APPLIED,
        reason_code=SourceHandlingReason.EXPLICIT_ACTION,
        recorded_at=MOMENT,
    )

    candidate = _sample_shadow_candidate()
    result = recorder.record_sync(
        candidate,
        source_outbox_id="cout_1",
        fence=_fence(),
        source_handling_record=non_eligible_record,
    )

    assert result.status == "rejected"
    assert result.decision_outcome == DecisionOutcome.REJECTED
    assert len(uow.applied_changes) == 0


def test_inferred_activation_disabled_keeps_candidate_shadow():
    from backend.memory.write_pipeline.models import VersionStatus

    uow = RecordingUoW()
    recorder = _recorder(
        policy=_shadow_policy(),
        uow_factory=lambda: uow,
        inferred_activation_enabled=False,
    )

    candidate = _sample_shadow_candidate()
    result = recorder.record_sync(candidate, fence=_fence())

    assert result.target_status == VersionStatus.SHADOW
    assert len(uow.applied_changes) == 1
    assert uow.applied_changes[0]["change"].operation == MemoryOperation.NOOP


def test_inferred_activation_promotes_conversation_scope_to_active_with_agreeing_turns():
    from backend.memory.write_pipeline.models import (
        EvidenceIdentity,
        MemoryVersionDraft,
        RetentionMode,
        VersionStatus,
    )

    class ActivationUoW(RecordingUoW):
        def get_assertion_identity_details(self, identity):
            return "ast_1", False

        def get_active_evidence_for_assertion(self, owner_user_id, assertion_id):
            return [
                EvidenceIdentity(
                    evidence_id="mev_prior",
                    conversation_id="cv_12345",
                    source_message_id="msg_turn_1",
                )
            ]

    uow = ActivationUoW()
    mock_resolver = MagicMock()
    mock_resolver.return_value = MemoryChangeSet(
        operation=MemoryOperation.ADD,
        identity=assertion_identity(
            MemoryCandidate(
                candidate_id="mc_test_01",
                evidence_ids=("mev_67890",),
                owner_user_id="user_alice",
                scope=MemoryScope.CONVERSATION,
                conversation_id="cv_12345",
                canonical_key="travel.preference.hotel_atmosphere",
                normalized_value="quiet",
                display_text="prefers quiet hotels",
                authority=Authority.REPEATED_INFERENCE,
                sensitivity=SensitivityBand.ORDINARY_PERSONAL,
                observed_at=MOMENT,
            )
        ),
        new_version=MemoryVersionDraft(
            owner_user_id="user_alice",
            scope=MemoryScope.CONVERSATION,
            scope_id="cv_12345",
            canonical_key="travel.preference.hotel_atmosphere",
            subject_key="self",
            condition_fingerprint="none",
            normalized_value="quiet",
            display_text="prefers quiet hotels",
            authority=Authority.REPEATED_INFERENCE,
            sensitivity=SensitivityBand.ORDINARY_PERSONAL,
            valid_from=MOMENT,
            retention_mode=RetentionMode.CONVERSATION_BOUND,
            status=VersionStatus.ACTIVE,
        ),
        superseded_version_ids=(),
        reference_version_id=None,
        reason="add_new",
    )

    recorder = _recorder(
        policy=_shadow_policy(),
        resolver=mock_resolver,
        uow_factory=lambda: uow,
        inferred_activation_enabled=True,
        # This test exercises the scope threshold, so it states that the key has
        # a conclusive evaluation. The gate itself is covered separately.
        type_evaluation_gate=lambda key: True,
    )

    candidate = ShadowCandidate(
        candidate_id="mc_test_01",
        owner_user_id="user_alice",
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        display_text="prefers quiet hotels",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        scope=MemoryScope.CONVERSATION,
        scope_id="cv_12345",
        confidence=0.95,
        observed_at=MOMENT,
        conversation_id="cv_12345",
        source_message_id="msg_turn_2",
    )
    result = recorder.record_sync(candidate, fence=_fence())

    assert result.target_status == VersionStatus.ACTIVE
    assert len(uow.applied_changes) == 1
    applied = uow.applied_changes[0]
    assert applied["change"].operation == MemoryOperation.ADD
    assert applied["change"].new_version is not None
    assert applied["change"].new_version.status == VersionStatus.ACTIVE


def test_inferred_activation_suppressed_by_unresolved_conflict():
    from backend.memory.write_pipeline.models import (
        EvidenceIdentity,
        MemoryVersionDraft,
        RetentionMode,
        VersionStatus,
    )

    class ConflictUoW(RecordingUoW):
        def get_assertion_identity_details(self, identity):
            return "ast_1", True

        def get_active_evidence_for_assertion(self, owner_user_id, assertion_id):
            return [
                EvidenceIdentity(
                    evidence_id="mev_prior",
                    conversation_id="cv_12345",
                    source_message_id="msg_turn_1",
                )
            ]

    uow = ConflictUoW()
    recorder = _recorder(
        policy=_shadow_policy(),
        uow_factory=lambda: uow,
        inferred_activation_enabled=True,
        # The conflict is the input under test, so every other gate is stated as
        # satisfied rather than left to a default.
        type_evaluation_gate=lambda key: True,
    )

    candidate = ShadowCandidate(
        candidate_id="mc_test_01",
        owner_user_id="user_alice",
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        display_text="prefers quiet hotels",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        scope=MemoryScope.CONVERSATION,
        scope_id="cv_12345",
        confidence=0.95,
        observed_at=MOMENT,
        conversation_id="cv_12345",
        source_message_id="msg_turn_2",
    )
    result = recorder.record_sync(candidate, fence=_fence())

    assert result.target_status == VersionStatus.SHADOW
    assert "unresolved_conflict" in result.reason
    assert len(uow.applied_changes) == 1
    assert uow.applied_changes[0]["change"].operation == MemoryOperation.NOOP


def test_recorder_delegates_to_commit_coordinator_when_provided():
    mock_coordinator = MagicMock()
    # The coordinator is invoked once per outbox event, so the recorder batches:
    # `commit_many` receives every candidate's request and completes the source
    # event once. Committing per candidate retired the lease after the first one.
    mock_coordinator.commit_many.return_value = (
        MemoryWriteResult(
            operation=MemoryOperation.NOOP,
            version_id=None,
            superseded_version_ids=(),
            reference_version_id=None,
            decision_id="mdc_commit_01",
            reason="shadow_valid_unpromoted",
        ),
    )

    uow = RecordingUoW()
    recorder = _recorder(
        policy=_shadow_policy(),
        uow_factory=lambda: uow,
        commit_coordinator=mock_coordinator,
    )

    candidate = _sample_shadow_candidate()
    fence = _fence()
    result = recorder.record_sync(candidate, source_outbox_id="cout_1", fence=fence)

    assert result.status == "recorded"
    assert result.write_result is not None
    mock_coordinator.commit_many.assert_called_once()
    (requests,) = mock_coordinator.commit_many.call_args[0]
    assert len(requests) == 1
    req = requests[0]
    assert req.fence is fence
    assert req.principal.owner_user_id == "user_alice"
    assert len(uow.applied_changes) == 0


def test_a_multi_candidate_event_commits_once_and_keeps_every_candidate():
    """One outbox event with several candidates must not lose any of them.

    The first revision committed per candidate, and the coordinator completes the
    source event inside that transaction — so candidate one marked the event
    SUCCEEDED and cleared its lease, and every later candidate failed
    `check_outbox_lease` with LEASE_LOST. The event reported CANCELLED while its
    row said succeeded, and the dropped candidates left no trace.
    """
    mock_coordinator = MagicMock()
    mock_coordinator.commit_many.return_value = tuple(
        MemoryWriteResult(
            operation=MemoryOperation.NOOP,
            version_id=None,
            superseded_version_ids=(),
            reference_version_id=None,
            decision_id=f"mdc_{index}",
            reason="shadow_valid_unpromoted",
        )
        for index in range(3)
    )

    recorder = _recorder(
        policy=_shadow_policy(),
        uow_factory=lambda: RecordingUoW(),
        commit_coordinator=mock_coordinator,
    )

    candidates = [
        _sample_shadow_candidate(candidate_id=f"mc_multi_{index}")
        for index in range(3)
    ]
    results = recorder.record_batch_sync(candidates, fence=_fence())

    assert len(results) == 3
    assert all(result.status == "recorded" for result in results)
    assert all(result.write_result is not None for result in results)
    mock_coordinator.commit_many.assert_called_once()
    (requests,) = mock_coordinator.commit_many.call_args[0]
    assert len(requests) == 3


def test_an_unhandled_source_is_refused_not_assumed_permitted():
    """Absence of a source-handling record is `UNHANDLED`, never permission.

    `ADR 0038:59` and plan constraint 8 both say so, and this is the one input
    the gate exists to refuse: the first revision read
    `if sh_record is not None and not allows_background_formation(sh_record)`,
    so a missing record passed the gate and was formed from.
    """
    uow = RecordingUoW()
    recorder = BackgroundMemoryRecorder(
        policy=_shadow_policy(),
        uow_factory=lambda: uow,
        # No loader and no record: the source is unhandled.
    )

    result = recorder.record_sync(_sample_shadow_candidate(), fence=_fence())

    assert result.status == "rejected"
    assert result.reason == "source_handling_denied"
    assert result.target_status == VersionStatus.SHADOW
    assert len(uow.applied_changes) == 0


def test_a_shadow_outcome_keeps_the_prefix_that_persists_evidence():
    """The `shadow_` reason prefix is load-bearing, and nothing else pins it.

    `PostgresMemoryUnitOfWork._apply_once` short-circuits a NOOP change unless its
    reason starts with `shadow_`. That prefix is exactly what lets a non-active
    decision persist its evidence, decision, and event rows **without** creating a
    version — the mechanism by which turns accumulate toward the 2-of-3 activation
    thresholds. Change the reason format and shadow accumulation stops silently,
    because the write still returns "recorded" and nothing goes red.
    """
    uow = RecordingUoW()
    recorder = _recorder(policy=_shadow_policy(), uow_factory=lambda: uow)

    result = recorder.record_sync(_sample_shadow_candidate(), fence=_fence())

    assert result.status == "recorded"
    assert result.target_status == VersionStatus.SHADOW
    assert result.operation == MemoryOperation.NOOP
    assert result.reason.startswith("shadow_"), result.reason
