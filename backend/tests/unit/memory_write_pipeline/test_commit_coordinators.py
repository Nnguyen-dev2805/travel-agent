"""Unit tests for Stage 2 Dual Commit Coordinators (ADR 0036, Plan v0.13 Task 7).

Covers CORE requirements:
- Canonical lock ordering:
  - Explicit: conversation/epoch -> memory rows (no outbox lease fence)
  - Worker: conversation/epoch -> outbox lease -> memory rows
- Explicit coordinator passes fence=None to MemoryWriteStore.apply_on
- Rejection of stale snapshot via expected_version_id
- Single atomic transaction / rollback on late failure
- Guard regressions: deletion epoch mismatch, idempotency deduplication, lease loss
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, call

import pytest

from backend.conversations.models import (
    Message,
    MessageRole,
    MessageStatus,
    TraceVisibility,
    TransitionResult,
)
from backend.memory.commit_coordinators import (
    BackgroundMemoryCommit,
    BackgroundMemoryCommitRequest,
    ExplicitMemoryCommitRequest,
    ExplicitMemoryCommitResult,
    ExplicitMemoryTurnCommit,
    ExplicitTurnTransitionError,
)
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingOutcome,
    SourceHandlingReason,
    SourceHandlingRecord,
)
from backend.memory.write_pipeline.models import (
    AssertionIdentity,
    Authority,
    Cardinality,
    MemoryChangeSet,
    MemoryDecisionDraft,
    MemoryEvidence,
    MemoryOperation,
    MemoryScope,
    NormalizedSemanticValue,
    RetentionMode,
    SensitivityBand,
    new_evidence_id,
)
from backend.memory.write_pipeline.uow import (
    FenceContext,
    FenceReason,
    FencedWriteError,
    MemoryWriteResult,
    StaleVersionError,
)
from backend.security.models import AuthenticatedPrincipal, AuthMode

MOMENT = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)


def _make_principal(owner_user_id: str = "usr_test_owner") -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        owner_user_id=owner_user_id,
        auth_mode=AuthMode.AUTHENTICATED,
        credential_label="local_token",
    )


def _make_evidence(owner_user_id: str = "usr_test_owner") -> MemoryEvidence:
    return MemoryEvidence(
        evidence_id=new_evidence_id(),
        owner_user_id=owner_user_id,
        conversation_id="cv_test",
        source_message_id="ms_user",
        display_text="I prefer quiet hotels",
        authority=Authority.EXPLICIT_STATEMENT,
        observed_at=MOMENT,
    )


def _make_change(owner_user_id: str = "usr_test_owner") -> MemoryChangeSet:
    identity = AssertionIdentity(
        owner_user_id=owner_user_id,
        scope=MemoryScope.USER,
        scope_id=owner_user_id,
        canonical_key="hotel_atmosphere",
        subject_key="self",
        condition_fingerprint="e3b0c44298fc1c149afbf4c8996fb924",
    )
    return MemoryChangeSet(
        operation=MemoryOperation.ADD,
        identity=identity,
        new_version=None,
        superseded_version_ids=(),
        reference_version_id=None,
        reason="user requested",
    )


def _make_set_supersede_change(
    owner_user_id: str = "usr_test_owner",
    reference_version_id: str = "ver_stale_123",
) -> MemoryChangeSet:
    identity = AssertionIdentity(
        owner_user_id=owner_user_id,
        scope=MemoryScope.USER,
        scope_id=owner_user_id,
        canonical_key="travel.preference.food_style",
        subject_key="self",
        condition_fingerprint="e3b0c44298fc1c149afbf4c8996fb924",
    )
    return MemoryChangeSet(
        operation=MemoryOperation.SUPERSEDE,
        identity=identity,
        new_version=None,
        superseded_version_ids=(reference_version_id,),
        reference_version_id=reference_version_id,
        reason="set_replacement_member_forget",
    )


def _make_source_handling_record() -> SourceHandlingRecord:
    return SourceHandlingRecord(
        source_outbox_id="cout_test_123",
        source_message_id="ms_user",
        family=MemoryFamily.SEMANTIC,
        outcome=SourceHandlingOutcome.EXPLICIT_APPLIED,
        reason_code=SourceHandlingReason.EXPLICIT_ACTION,
        recorded_at=MOMENT,
    )


def _make_assistant_message(
    content: str = "Understood, I will remember that.",
    status: MessageStatus = MessageStatus.COMPLETE,
) -> Message:
    return Message(
        message_id="ms_assistant",
        conversation_id="cv_test",
        sequence=2,
        role=MessageRole.ASSISTANT,
        content=content,
        source="system",
        trace_visibility=TraceVisibility.EXCLUDED,
        created_at=MOMENT,
        status=status,
    )


class TestCommitCoordinatorsLockOrder:
    """Assertions for canonical lock ordering according to ADR 0036 & Task 7 CORE."""

    def test_explicit_lock_order_conversation_then_memory(self):
        """Explicit commit lock order: tenant bind -> conversation/epoch -> memory rows.

        Crucially: check_outbox_lease must NOT be called, and fence=None must be passed.
        """
        journal = []

        fake_conn = MagicMock(name="connection")

        def record_bind(conn, owner):
            assert conn is fake_conn
            journal.append(("bind_tenant", owner))

        def record_conv_lock(conn, cid, epoch, owner):
            assert conn is fake_conn
            journal.append(("lock_conversation", cid, epoch, owner))

        def record_apply_on(conn, *, change, principal, evidence, decision,
                            idempotency_key, expected_version_id, fence, source_validity):
            assert conn is fake_conn
            journal.append(("memory_apply_on", fence))
            return MemoryWriteResult(
                operation=change.operation,
                version_id="ver_1",
                superseded_version_ids=(),
                reference_version_id=None,
                decision_id=None,
                reason="applied",
            )

        def record_source_handling(conn, owner, record):
            assert conn is fake_conn
            journal.append(("record_source_handling", record.family))

        def record_transition(conn, cid, mid, owner, *, status, content):
            assert conn is fake_conn
            journal.append(("transition_turn", mid, status, content))
            return TransitionResult(message=_make_assistant_message(), applied=True)

        class FakeTransactionContext:
            def __enter__(self):
                journal.append(("tx_begin",))
                return fake_conn

            def __exit__(self, exc_type, exc_val, exc_tb):
                if exc_type is None:
                    journal.append(("tx_commit",))
                else:
                    journal.append(("tx_rollback", exc_type.__name__))
                return False

        coordinator = ExplicitMemoryTurnCommit(
            transaction_factory=lambda: FakeTransactionContext(),
            bind_tenant_fn=record_bind,
            lock_conversation_fn=record_conv_lock,
            memory_write_store=MagicMock(apply_on=record_apply_on),
            record_source_handling_fn=record_source_handling,
            transition_turn_fn=record_transition,
        )

        principal = _make_principal()
        request = ExplicitMemoryCommitRequest(
            principal=principal,
            conversation_id="cv_test",
            assistant_message_id="ms_assistant",
            expected_deletion_epoch=0,
            acknowledgement_text="Understood, I will remember that.",
            change=_make_change(),
            evidence=(_make_evidence(),),
            decision=None,
            idempotency_key="idemp_123",
            expected_version_id=None,
            source_validity=None,
            source_handling_record=_make_source_handling_record(),
        )

        result = coordinator.commit(request)

        assert isinstance(result, ExplicitMemoryCommitResult)
        assert result.memory.version_id == "ver_1"
        assert result.transition.applied is True

        # Assert canonical order: tx_begin -> bind_tenant -> lock_conversation -> memory_apply_on -> record_source_handling -> transition_turn -> tx_commit
        order_steps = [item[0] for item in journal]
        assert order_steps == [
            "tx_begin",
            "bind_tenant",
            "lock_conversation",
            "memory_apply_on",
            "record_source_handling",
            "transition_turn",
            "tx_commit",
        ]

        # Verify fence=None passed to memory_apply_on
        memory_step = [item for item in journal if item[0] == "memory_apply_on"][0]
        assert memory_step[1] is None, "Explicit path must pass fence=None"

        # Verify outbox lease was NEVER checked
        assert "check_outbox_lease" not in order_steps, "Explicit path must not check outbox lease"

    def test_worker_lock_order_conversation_then_outbox_then_memory(self):
        """Worker commit lock order: tenant bind -> conversation/epoch -> outbox lease -> memory rows -> outbox succeeded."""
        journal = []
        fake_conn = MagicMock(name="connection")

        def record_bind(conn, owner):
            journal.append(("bind_tenant", owner))

        def record_conv_lock(conn, cid, epoch, owner):
            journal.append(("lock_conversation", cid, epoch, owner))

        def record_outbox_lease(conn, outbox_id, lease_owner):
            journal.append(("check_outbox_lease", outbox_id, lease_owner))
            return True, None

        def record_apply_on(conn, *, change, principal, evidence, decision,
                            idempotency_key, expected_version_id, fence, source_validity):
            journal.append(("memory_apply_on", fence))
            return MemoryWriteResult(
                operation=change.operation,
                version_id="ver_worker_1",
                superseded_version_ids=(),
                reference_version_id=None,
                decision_id=None,
                reason="worker_applied",
            )

        def record_mark_succeeded(conn, outbox_id, lease_owner):
            assert conn is fake_conn
            journal.append(("mark_outbox_succeeded", outbox_id, lease_owner))
            return True

        class FakeTransactionContext:
            def __enter__(self):
                journal.append(("tx_begin",))
                return fake_conn

            def __exit__(self, exc_type, exc_val, exc_tb):
                if exc_type is None:
                    journal.append(("tx_commit",))
                else:
                    journal.append(("tx_rollback", exc_type.__name__))
                return False

        coordinator = BackgroundMemoryCommit(
            transaction_factory=lambda: FakeTransactionContext(),
            bind_tenant_fn=record_bind,
            lock_conversation_fn=record_conv_lock,
            check_outbox_lease_fn=record_outbox_lease,
            memory_write_store=MagicMock(apply_on=record_apply_on),
            mark_outbox_succeeded_fn=record_mark_succeeded,
        )

        principal = _make_principal()
        fence = FenceContext(
            conversation_id="cv_test",
            expected_epoch=1,
            outbox_id="cout_test_123",
            lease_owner="worker_pod_1",
        )
        request = BackgroundMemoryCommitRequest(
            principal=principal,
            change=_make_change(),
            evidence=(_make_evidence(),),
            decision=None,
            idempotency_key="idemp_worker_123",
            expected_version_id=None,
            source_validity=None,
            fence=fence,
        )

        result = coordinator.commit(request)

        assert isinstance(result, MemoryWriteResult)
        assert result.version_id == "ver_worker_1"

        order_steps = [item[0] for item in journal]
        assert order_steps == [
            "tx_begin",
            "bind_tenant",
            "lock_conversation",
            "check_outbox_lease",
            "memory_apply_on",
            "mark_outbox_succeeded",
            "tx_commit",
        ]

        # Verify fence was passed to memory_apply_on
        memory_step = [item for item in journal if item[0] == "memory_apply_on"][0]
        assert memory_step[1] == fence, "Worker path must pass fence to memory_write_store"

        # Verify mark_outbox_succeeded was called with outbox_id and lease_owner
        outbox_step = [item for item in journal if item[0] == "mark_outbox_succeeded"][0]
        assert outbox_step[1] == fence.outbox_id
        assert outbox_step[2] == fence.lease_owner


class TestCommitCoordinatorsInvariants:
    """Tests for CORE invariants: stale version rejection, atomicity/rollback, fence errors."""

    def test_explicit_stale_expected_version_rejected(self):
        """When expected_version_id is stale, coordinator raises StaleVersionError without partial transition."""
        fake_conn = MagicMock(name="connection")
        rolled_back = False

        class FakeTransactionContext:
            def __enter__(self):
                return fake_conn

            def __exit__(self, exc_type, exc_val, exc_tb):
                nonlocal rolled_back
                if exc_type is not None:
                    rolled_back = True
                return False

        def failing_apply_on(conn, *, change, principal, expected_version_id, **kwargs):
            assert conn is fake_conn
            assert expected_version_id == "ver_stale_123", "expected_version_id must be forwarded to apply_on"
            assert change.operation is MemoryOperation.SUPERSEDE, "stale check must represent SET replacement/member-forget"
            assert change.reference_version_id == "ver_stale_123"
            assert change.identity.canonical_key == "travel.preference.food_style"
            raise StaleVersionError("Active version has changed since candidate was materialized.")

        transition_called = False

        def record_transition(*args, **kwargs):
            nonlocal transition_called
            transition_called = True
            return TransitionResult(message=_make_assistant_message(), applied=True)

        coordinator = ExplicitMemoryTurnCommit(
            transaction_factory=lambda: FakeTransactionContext(),
            bind_tenant_fn=MagicMock(),
            lock_conversation_fn=MagicMock(),
            memory_write_store=MagicMock(apply_on=failing_apply_on),
            record_source_handling_fn=MagicMock(),
            transition_turn_fn=record_transition,
        )

        request = ExplicitMemoryCommitRequest(
            principal=_make_principal(),
            conversation_id="cv_test",
            assistant_message_id="ms_assistant",
            expected_deletion_epoch=0,
            acknowledgement_text="Ack text",
            change=_make_set_supersede_change(reference_version_id="ver_stale_123"),
            evidence=(_make_evidence(),),
            decision=None,
            idempotency_key="idemp_stale",
            expected_version_id="ver_stale_123",
            source_validity=None,
            source_handling_record=_make_source_handling_record(),
        )

        with pytest.raises(StaleVersionError):
            coordinator.commit(request)

        assert rolled_back is True
        assert transition_called is False

    def test_explicit_rollback_on_late_failure(self):
        """When failure happens after memory write (e.g. during ack/transition), the whole tx rolls back."""
        fake_conn = MagicMock(name="connection")
        rolled_back = False

        class FakeTransactionContext:
            def __enter__(self):
                return fake_conn

            def __exit__(self, exc_type, exc_val, exc_tb):
                nonlocal rolled_back
                if exc_type is not None:
                    rolled_back = True
                return False

        def failing_transition(*args, **kwargs):
            raise RuntimeError("Database connection reset during transition")

        coordinator = ExplicitMemoryTurnCommit(
            transaction_factory=lambda: FakeTransactionContext(),
            bind_tenant_fn=MagicMock(),
            lock_conversation_fn=MagicMock(),
            memory_write_store=MagicMock(apply_on=MagicMock(return_value=MemoryWriteResult(
                operation=MemoryOperation.ADD,
                version_id="ver_written",
                superseded_version_ids=(),
                reference_version_id=None,
                decision_id=None,
                reason="ok",
            ))),
            record_source_handling_fn=MagicMock(),
            transition_turn_fn=failing_transition,
        )

        request = ExplicitMemoryCommitRequest(
            principal=_make_principal(),
            conversation_id="cv_test",
            assistant_message_id="ms_assistant",
            expected_deletion_epoch=0,
            acknowledgement_text="Ack text",
            change=_make_change(),
            evidence=(_make_evidence(),),
            decision=None,
            idempotency_key="idemp_late_fail",
            expected_version_id=None,
            source_validity=None,
            source_handling_record=_make_source_handling_record(),
        )

        with pytest.raises(RuntimeError, match="Database connection reset"):
            coordinator.commit(request)

        assert rolled_back is True

    def test_explicit_deletion_epoch_mismatch_raises(self):
        """When conversation epoch has moved, coordinator raises FencedWriteError without memory write."""
        fake_conn = MagicMock(name="connection")
        memory_called = False

        class FakeTransactionContext:
            def __enter__(self):
                return fake_conn

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

        def epoch_mismatch_lock(conn, cid, epoch, owner):
            raise FencedWriteError(FenceReason.DELETION_EPOCH_MOVED)

        def spy_apply_on(*args, **kwargs):
            nonlocal memory_called
            memory_called = True

        coordinator = ExplicitMemoryTurnCommit(
            transaction_factory=lambda: FakeTransactionContext(),
            bind_tenant_fn=MagicMock(),
            lock_conversation_fn=epoch_mismatch_lock,
            memory_write_store=MagicMock(apply_on=spy_apply_on),
            record_source_handling_fn=MagicMock(),
            transition_turn_fn=MagicMock(),
        )

        request = ExplicitMemoryCommitRequest(
            principal=_make_principal(),
            conversation_id="cv_test",
            assistant_message_id="ms_assistant",
            expected_deletion_epoch=0,
            acknowledgement_text="Ack text",
            change=_make_change(),
            evidence=(_make_evidence(),),
            decision=None,
            idempotency_key="idemp_epoch_fail",
            expected_version_id=None,
            source_validity=None,
            source_handling_record=_make_source_handling_record(),
        )

        with pytest.raises(FencedWriteError) as exc_info:
            coordinator.commit(request)

        assert exc_info.value.reason == FenceReason.DELETION_EPOCH_MOVED
        assert memory_called is False

    def test_worker_lease_loss_raises(self):
        """When outbox lease check fails, BackgroundMemoryCommit raises FencedWriteError without memory mutation."""
        fake_conn = MagicMock(name="connection")
        memory_called = False

        class FakeTransactionContext:
            def __enter__(self):
                return fake_conn

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

        def lease_lost_check(conn, outbox_id, lease_owner):
            return False, FenceReason.LEASE_LOST

        def spy_apply_on(*args, **kwargs):
            nonlocal memory_called
            memory_called = True

        coordinator = BackgroundMemoryCommit(
            transaction_factory=lambda: FakeTransactionContext(),
            bind_tenant_fn=MagicMock(),
            lock_conversation_fn=MagicMock(),
            check_outbox_lease_fn=lease_lost_check,
            memory_write_store=MagicMock(apply_on=spy_apply_on),
        )

        fence = FenceContext(
            conversation_id="cv_test",
            expected_epoch=0,
            outbox_id="cout_test_123",
            lease_owner="worker_pod_1",
        )
        request = BackgroundMemoryCommitRequest(
            principal=_make_principal(),
            change=_make_change(),
            evidence=(_make_evidence(),),
            decision=None,
            idempotency_key="idemp_worker_lease_fail",
            expected_version_id=None,
            source_validity=None,
            fence=fence,
        )

        with pytest.raises(FencedWriteError) as exc_info:
            coordinator.commit(request)

        assert exc_info.value.reason == FenceReason.LEASE_LOST
        assert memory_called is False

    def test_worker_outbox_mark_succeeded_failure_rolls_back(self):
        """When mark_outbox_succeeded returns False (e.g. lease lost), transaction rolls back."""
        fake_conn = MagicMock(name="connection")
        rolled_back = False

        class FakeTransactionContext:
            def __enter__(self):
                return fake_conn

            def __exit__(self, exc_type, exc_val, exc_tb):
                nonlocal rolled_back
                if exc_type is not None:
                    rolled_back = True
                return False

        def mark_succeeded_fails(conn, outbox_id, lease_owner):
            return False

        coordinator = BackgroundMemoryCommit(
            transaction_factory=lambda: FakeTransactionContext(),
            bind_tenant_fn=MagicMock(),
            lock_conversation_fn=MagicMock(),
            check_outbox_lease_fn=MagicMock(return_value=(True, None)),
            memory_write_store=MagicMock(apply_on=MagicMock(return_value=MemoryWriteResult(
                operation=MemoryOperation.ADD,
                version_id="ver_worker_tmp",
                superseded_version_ids=(),
                reference_version_id=None,
                decision_id=None,
                reason="applied",
            ))),
            mark_outbox_succeeded_fn=mark_succeeded_fails,
        )

        fence = FenceContext(
            conversation_id="cv_test",
            expected_epoch=1,
            outbox_id="cout_test_123",
            lease_owner="worker_pod_1",
        )
        request = BackgroundMemoryCommitRequest(
            principal=_make_principal(),
            change=_make_change(),
            evidence=(_make_evidence(),),
            decision=None,
            idempotency_key="idemp_worker_fail",
            expected_version_id=None,
            source_validity=None,
            fence=fence,
        )

        with pytest.raises(FencedWriteError) as exc_info:
            coordinator.commit(request)

        assert exc_info.value.reason == FenceReason.LEASE_LOST
        assert rolled_back is True

    def test_explicit_passes_fence_none_to_memory_store(self):
        """Explicit path never needs the outbox lease fence and must pass fence=None."""
        fake_conn = MagicMock(name="connection")
        captured_fence = "not_set"

        class FakeTransactionContext:
            def __enter__(self):
                return fake_conn

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

        def spy_apply_on(conn, *, change, principal, evidence, decision,
                         idempotency_key, expected_version_id, fence, source_validity):
            nonlocal captured_fence
            captured_fence = fence
            return MemoryWriteResult(
                operation=change.operation,
                version_id="ver_explicit",
                superseded_version_ids=(),
                reference_version_id=None,
                decision_id=None,
                reason="applied",
            )

        coordinator = ExplicitMemoryTurnCommit(
            transaction_factory=lambda: FakeTransactionContext(),
            bind_tenant_fn=MagicMock(),
            lock_conversation_fn=MagicMock(),
            memory_write_store=MagicMock(apply_on=spy_apply_on),
            record_source_handling_fn=MagicMock(),
            transition_turn_fn=MagicMock(return_value=TransitionResult(
                message=_make_assistant_message(),
                applied=True,
            )),
        )

        request = ExplicitMemoryCommitRequest(
            principal=_make_principal(),
            conversation_id="cv_test",
            assistant_message_id="ms_assistant",
            expected_deletion_epoch=0,
            acknowledgement_text="Ack text",
            change=_make_change(),
            evidence=(_make_evidence(),),
            decision=None,
            idempotency_key="idemp_fence_check",
            expected_version_id=None,
            source_validity=None,
            source_handling_record=_make_source_handling_record(),
        )

        result = coordinator.commit(request)

        assert result.memory.version_id == "ver_explicit"
        assert captured_fence is None

    def test_explicit_unapplied_transition_rolls_back_transaction(self):
        """When transition_turn returns applied=False (lost race), explicit coordinator fails-closed and rolls back."""
        fake_conn = MagicMock(name="connection")
        rolled_back = False

        class FakeTransactionContext:
            def __enter__(self):
                return fake_conn

            def __exit__(self, exc_type, exc_val, exc_tb):
                nonlocal rolled_back
                if exc_type is not None:
                    rolled_back = True
                return False

        first_result = MemoryWriteResult(
            operation=MemoryOperation.ADD,
            version_id="ver_worker_1",
            superseded_version_ids=(),
            reference_version_id=None,
            decision_id=None,
            reason="applied",
        )

        mock_apply_on = MagicMock(return_value=first_result)
        # Lost race: turn was transitioned by someone else or failed
        mock_transition = MagicMock(return_value=TransitionResult(
            message=_make_assistant_message(content="Someone else won", status=MessageStatus.COMPLETE),
            applied=False,
        ))

        coordinator = ExplicitMemoryTurnCommit(
            transaction_factory=lambda: FakeTransactionContext(),
            bind_tenant_fn=MagicMock(),
            lock_conversation_fn=MagicMock(),
            memory_write_store=MagicMock(apply_on=mock_apply_on),
            record_source_handling_fn=MagicMock(return_value=True),  # newly inserted handling record
            transition_turn_fn=mock_transition,
        )

        request = ExplicitMemoryCommitRequest(
            principal=_make_principal(),
            conversation_id="cv_test",
            assistant_message_id="ms_assistant",
            expected_deletion_epoch=0,
            acknowledgement_text="Ack text",
            change=_make_change(),
            evidence=(_make_evidence(),),
            decision=None,
            idempotency_key="idemp_unapplied",
            expected_version_id=None,
            source_validity=None,
            source_handling_record=_make_source_handling_record(),
        )

        with pytest.raises(ExplicitTurnTransitionError) as exc_info:
            coordinator.commit(request)

        assert "Could not complete the turn acknowledgement" in str(exc_info.value)
        assert rolled_back is True

    def test_explicit_duplicate_idempotent_retry_returns_same_result(self):
        """Duplicate explicit retry with same key returns identical semantic result without second mutation (ADR 0036)."""
        fake_conn = MagicMock(name="connection")
        rolled_back = False

        class FakeTransactionContext:
            def __enter__(self):
                return fake_conn

            def __exit__(self, exc_type, exc_val, exc_tb):
                nonlocal rolled_back
                if exc_type is not None:
                    rolled_back = True
                return False

        idempotent_result = MemoryWriteResult(
            operation=MemoryOperation.ADD,
            version_id="ver_idempotent_1",
            superseded_version_ids=(),
            reference_version_id=None,
            decision_id=None,
            reason="applied",
        )

        mock_apply_on = MagicMock(return_value=idempotent_result)
        # Replay: stored assistant row is already COMPLETE with exact acknowledgement text
        mock_transition = MagicMock(return_value=TransitionResult(
            message=_make_assistant_message(content="Ack text", status=MessageStatus.COMPLETE),
            applied=False,
        ))

        coordinator = ExplicitMemoryTurnCommit(
            transaction_factory=lambda: FakeTransactionContext(),
            bind_tenant_fn=MagicMock(),
            lock_conversation_fn=MagicMock(),
            memory_write_store=MagicMock(apply_on=mock_apply_on),
            record_source_handling_fn=MagicMock(return_value=False),  # identical record already exists
            transition_turn_fn=mock_transition,
        )

        request = ExplicitMemoryCommitRequest(
            principal=_make_principal(),
            conversation_id="cv_test",
            assistant_message_id="ms_assistant",
            expected_deletion_epoch=0,
            acknowledgement_text="Ack text",
            change=_make_change(),
            evidence=(_make_evidence(),),
            decision=None,
            idempotency_key="idemp_duplicate_ok",
            expected_version_id=None,
            source_validity=None,
            source_handling_record=_make_source_handling_record(),
        )

        result = coordinator.commit(request)

        assert result.memory.version_id == "ver_idempotent_1"
        assert result.transition.applied is False
        assert result.transition.message.content == "Ack text"
        assert rolled_back is False

