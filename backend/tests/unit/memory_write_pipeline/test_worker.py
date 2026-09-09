"""Unit tests for the memory write pipeline outbox worker runtime.

Covers:
- Short transaction claim, execution outside DB transaction
- Conversation debounce and new-message cursor
- Revalidation before commit: source existence, deletion epoch, idempotency
- Deletion cancellation: if conversation deleted/retracted, job cancelled immediately
- Error classification: transient retry with backoff vs permanent dead-letter
- Strict shadow outcome: zero active versions created
- Starvation protection & same-conversation serialization
"""

from datetime import datetime, timedelta, timezone
from typing import Sequence
import pytest

from backend.memory.write_pipeline.models import (
    Authority,
    DecisionOutcome,
    DecisionReason,
    MemoryCandidate,
    MemoryDecisionDraft,
    MemoryEvidence,
    MemoryOperation,
    MemoryRelation,
    MemoryScope,
    SensitivityBand,
    VersionStatus,
    new_candidate_id,
    new_evidence_id,
)
from backend.memory.write_pipeline.model_adapter import CostEvidence, TokenUsage
from backend.memory.write_pipeline.outbox import (
    InMemoryOutboxRepository,
    OutboxEvent,
    OutboxStatus,
)
from backend.memory.write_pipeline.worker import (
    MemoryOutboxWorker,
    WorkerResult,
)
from backend.security.models import AuthenticatedPrincipal, AuthMode

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)


class FakeExtractionModel:
    def __init__(self, candidates=None, should_raise=None):
        self.candidates = candidates or []
        self.should_raise = should_raise
        self.calls = []

    def extract(self, messages, owner_user_id, conversation_id):
        self.calls.append((messages, owner_user_id, conversation_id))
        if self.should_raise:
            raise self.should_raise
        return self.candidates


class FakeUoW:
    def __init__(self):
        self.applied_changes = []
        self.versions = []

    def apply_memory_change(
        self,
        change,
        principal,
        *,
        evidence=(),
        decision=None,
        idempotency_key=None,
        expected_version_id=None,
    ):
        self.applied_changes.append({
            "change": change,
            "principal": principal,
            "evidence": evidence,
            "decision": decision,
            "idempotency_key": idempotency_key,
        })
        # If any version were active, record it (for zero-active verification)
        if change.new_version and change.new_version.status == VersionStatus.ACTIVE:
            self.versions.append(change.new_version)


class FakeConversationService:
    def __init__(self):
        self.conversations = {}
        self.messages = {}
        self.deletion_epochs = {}

    def get_conversation(self, conversation_id):
        return self.conversations.get(conversation_id)

    def get_messages(self, conversation_id):
        return self.messages.get(conversation_id, [])

    def get_messages_in_range(self, conversation_id, after_sequence=None, limit=100):
        msgs = self.messages.get(conversation_id, [])
        if after_sequence is not None:
            return [m for m in msgs if m.get("sequence", 0) > after_sequence][:limit]
        return msgs[:limit]

    def get_deletion_epoch(self, conversation_id):
        return self.deletion_epochs.get(conversation_id, 0)


def _setup_worker(model=None, uow=None, outbox=None, conv_service=None, service=None):
    outbox_repo = outbox or InMemoryOutboxRepository()
    uow_fake = uow or FakeUoW()
    model_fake = model or FakeExtractionModel()
    conv_svc = conv_service or FakeConversationService()

    worker = MemoryOutboxWorker(
        outbox_repo=outbox_repo,
        model_adapter=model_fake,
        uow=uow_fake,
        conversation_service=conv_svc,
        service=service,
        worker_id="test_worker_1",
    )
    return worker, outbox_repo, uow_fake, model_fake, conv_svc


def test_worker_processes_event_to_succeeded():
    worker, outbox, uow, model, conv_svc = _setup_worker()

    # Seed conversation and message
    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "role": "user", "content": "I like quiet hotels."}
    ]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1", "message_id": "msg_1"},
        created_at=MOMENT,
    )
    outbox.save_event(event)

    result = worker.process_one(event)
    assert result.status == OutboxStatus.SUCCEEDED
    assert outbox.get_event("cout_1").status == OutboxStatus.SUCCEEDED
    # Verify zero active versions created in UoW
    assert len(uow.versions) == 0


def test_worker_cancels_if_conversation_deleted():
    worker, outbox, uow, model, conv_svc = _setup_worker()

    # Conversation retention_state is deleted
    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "deleted",
    }

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1", "message_id": "msg_1"},
        created_at=MOMENT,
    )
    outbox.save_event(event)

    result = worker.process_one(event)
    assert result.status == OutboxStatus.CANCELLED
    assert outbox.get_event("cout_1").status == OutboxStatus.CANCELLED
    # Model should NOT be called
    assert len(model.calls) == 0


def test_worker_pre_model_secret_scan_prevents_model_call():
    worker, outbox, uow, model, conv_svc = _setup_worker()

    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    # Message has a secret key
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "role": "user", "content": "Here is my key sk-proj-1234567890abcdef"}
    ]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1", "message_id": "msg_1"},
        created_at=MOMENT,
    )
    outbox.save_event(event)

    result = worker.process_one(event)
    assert result.status == OutboxStatus.SUCCEEDED  # Job succeeded by rejecting secret without leak
    # Model was NOT called with secret text
    assert len(model.calls) == 0


def test_worker_retries_transient_error_and_dead_letters_permanent():
    from backend.memory.write_pipeline.model_adapter import (
        ProviderTransientError,
        ProviderPermanentError,
    )

    # 1. Transient error
    transient_model = FakeExtractionModel(should_raise=ProviderTransientError("Rate limit 429"))
    worker, outbox, _, _, conv_svc = _setup_worker(model=transient_model)

    conv_svc.conversations["conv_1"] = {"conversation_id": "conv_1", "owner_user_id": "owner_1", "retention_state": "active"}
    conv_svc.messages["conv_1"] = [{"message_id": "msg_1", "role": "user", "content": "I prefer quiet rooms."}]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1", "message_id": "msg_1"},
        created_at=MOMENT,
    )
    outbox.save_event(event)

    res1 = worker.process_one(event)
    assert res1.status == OutboxStatus.PENDING  # Retried
    assert outbox.get_event("cout_1").status == OutboxStatus.PENDING

    # 2. Permanent error
    perm_model = FakeExtractionModel(should_raise=ProviderPermanentError("Invalid auth"))
    worker_perm, outbox_perm, _, _, conv_svc_perm = _setup_worker(model=perm_model)
    conv_svc_perm.conversations["conv_2"] = {"conversation_id": "conv_2", "owner_user_id": "owner_2", "retention_state": "active"}
    conv_svc_perm.messages["conv_2"] = [{"message_id": "msg_2", "role": "user", "content": "I prefer quiet rooms."}]

    event2 = OutboxEvent(
        outbox_id="cout_2",
        conversation_id="conv_2",
        message_id="msg_2",
        owner_user_id="owner_2",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_2", "message_id": "msg_2"},
        created_at=MOMENT,
    )
    outbox_perm.save_event(event2)

    res2 = worker_perm.process_one(event2)
    assert res2.status == OutboxStatus.DEAD_LETTER
    assert outbox_perm.get_event("cout_2").status == OutboxStatus.DEAD_LETTER


def test_worker_persists_shadow_evidence_and_zero_active_versions():
    candidate = MemoryCandidate(
        candidate_id="mc_1",
        evidence_ids=(),
        owner_user_id="owner_1",
        scope=MemoryScope.CONVERSATION,
        conversation_id="conv_1",
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        display_text="I love quiet places",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=MOMENT,
    )
    model = FakeExtractionModel(candidates=[candidate])
    worker, outbox, uow, _, conv_svc = _setup_worker(model=model)

    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "role": "user", "content": "I love quiet places"}
    ]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1", "message_id": "msg_1"},
        created_at=MOMENT,
    )
    outbox.save_event(event)

    result = worker.process_one(event)
    assert result.status == OutboxStatus.SUCCEEDED
    assert result.candidates_count == 1
    assert len(uow.applied_changes) == 1
    applied = uow.applied_changes[0]
    assert applied["decision"].outcome == DecisionOutcome.SHADOW
    assert len(uow.versions) == 0  # Zero active versions created!


def test_worker_cancels_when_deletion_epoch_advances():
    worker, outbox, _, _, conv_svc = _setup_worker()

    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.deletion_epochs["conv_1"] = 5  # Advanced epoch

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1", "message_id": "msg_1", "deletion_epoch": 2},
        created_at=MOMENT,
    )
    outbox.save_event(event)

    result = worker.process_one(event)
    assert result.status == OutboxStatus.CANCELLED
    assert outbox.get_event("cout_1").status == OutboxStatus.CANCELLED


def test_worker_run_batch_and_poll_once():
    worker, outbox, uow, model, conv_svc = _setup_worker()

    for i in range(1, 4):
        cid = f"conv_{i}"
        conv_svc.conversations[cid] = {"conversation_id": cid, "owner_user_id": f"owner_{i}", "retention_state": "active"}
        conv_svc.messages[cid] = [{"message_id": f"msg_{i}", "role": "user", "content": f"Message {i}"}]
        outbox.save_event(
            OutboxEvent(
                outbox_id=f"cout_{i}",
                conversation_id=cid,
                message_id=f"msg_{i}",
                owner_user_id=f"owner_{i}",
                event_type="memory.extract.conversation_range",
                payload={"conversation_id": cid, "message_id": f"msg_{i}"},
                created_at=MOMENT + timedelta(seconds=i),
            )
        )

    # run_batch with limit=2 processes first 2 events
    results = worker.run_batch(limit=2)
    assert len(results) == 2
    assert results[0].status == OutboxStatus.SUCCEEDED
    assert results[1].status == OutboxStatus.SUCCEEDED
    assert outbox.get_event("cout_1").status == OutboxStatus.SUCCEEDED
    assert outbox.get_event("cout_2").status == OutboxStatus.SUCCEEDED
    assert outbox.get_event("cout_3").status == OutboxStatus.PENDING

    # poll_once processes remaining 1 event
    count = worker.poll_once(limit=10)
    assert count == 1
    assert outbox.get_event("cout_3").status == OutboxStatus.SUCCEEDED


def test_worker_batch_same_conversation_serialization():
    worker, outbox, uow, model, conv_svc = _setup_worker()

    # Two events in the SAME conversation
    conv_svc.conversations["conv_1"] = {"conversation_id": "conv_1", "owner_user_id": "owner_1", "retention_state": "active"}
    conv_svc.messages["conv_1"] = [{"message_id": "msg_1", "role": "user", "content": "Msg 1"}]

    outbox.save_event(
        OutboxEvent(
            outbox_id="cout_1",
            conversation_id="conv_1",
            message_id="msg_1",
            owner_user_id="owner_1",
            event_type="memory.extract.conversation_range",
            payload={"conversation_id": "conv_1"},
            created_at=MOMENT,
        )
    )
    outbox.save_event(
        OutboxEvent(
            outbox_id="cout_2",
            conversation_id="conv_1",
            message_id="msg_2",
            owner_user_id="owner_1",
            event_type="memory.extract.conversation_range",
            payload={"conversation_id": "conv_1"},
            created_at=MOMENT + timedelta(seconds=1),
        )
    )

    # In a single batch, only 1 event from conv_1 is leased and processed
    results = worker.run_batch(limit=10)
    assert len(results) == 1
    assert results[0].status == OutboxStatus.SUCCEEDED
    assert outbox.get_event("cout_1").status == OutboxStatus.SUCCEEDED
    assert outbox.get_event("cout_2").status == OutboxStatus.PENDING


def test_worker_cursor_range_message_loading():
    worker, outbox, uow, model, conv_svc = _setup_worker()

    conv_svc.conversations["conv_1"] = {"conversation_id": "conv_1", "owner_user_id": "owner_1", "retention_state": "active"}
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "sequence": 1, "role": "user", "content": "First"},
        {"message_id": "msg_2", "sequence": 2, "role": "assistant", "content": "Second"},
        {"message_id": "msg_3", "sequence": 3, "role": "user", "content": "Third"},
        {"message_id": "msg_4", "sequence": 4, "role": "assistant", "content": "Fourth"},
    ]

    # Event specifies after_sequence=2
    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_4",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1", "after_sequence": 2},
        created_at=MOMENT,
    )
    outbox.save_event(event)

    res = worker.process_one(event)
    assert res.status == OutboxStatus.SUCCEEDED
    # Model should only have received messages with sequence > 2
    assert len(model.calls) == 1
    passed_messages = model.calls[0][0]
    assert len(passed_messages) == 2
    assert passed_messages[0]["message_id"] == "msg_3"
    assert passed_messages[1]["message_id"] == "msg_4"


def test_worker_stale_lease_commit_hazard_prevented():
    """Verify that if another worker took the lease during extraction, candidate persistence is aborted."""
    class StealingModel:
        def __init__(self, outbox_repo, candidate):
            self.outbox_repo = outbox_repo
            self.candidate = candidate

        def extract(self, messages, owner_user_id, conversation_id):
            # Simulate lease being stolen by worker_2 while model was processing
            ev = self.outbox_repo.get_event("cout_1")
            stolen = OutboxEvent(
                outbox_id=ev.outbox_id,
                conversation_id=ev.conversation_id,
                message_id=ev.message_id,
                owner_user_id=ev.owner_user_id,
                event_type=ev.event_type,
                payload=ev.payload,
                status=OutboxStatus.LEASED,
                lease_owner="worker_2",  # Stolen!
                lease_until=MOMENT + timedelta(seconds=60),
                attempt_count=ev.attempt_count,
                created_at=ev.created_at,
            )
            self.outbox_repo.save_event(stolen)
            return [self.candidate]

    candidate = MemoryCandidate(
        candidate_id=new_candidate_id(),
        evidence_ids=(),
        owner_user_id="owner_1",
        scope=MemoryScope.CONVERSATION,
        conversation_id="conv_1",
        canonical_key="travel.preference.style",
        normalized_value="luxury",
        display_text="I prefer luxury",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=MOMENT,
    )

    outbox = InMemoryOutboxRepository()
    stealing_model = StealingModel(outbox, candidate)
    worker, _, uow, _, conv_svc = _setup_worker(model=stealing_model, outbox=outbox)

    conv_svc.conversations["conv_1"] = {"conversation_id": "conv_1", "owner_user_id": "owner_1", "retention_state": "active"}
    conv_svc.messages["conv_1"] = [{"message_id": "msg_1", "role": "user", "content": "I prefer luxury"}]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT,
    )
    outbox.save_event(event)

    result = worker.process_one(event)
    # Must fail because lease was lost
    assert result.error == "lease_lost_before_commit"
    # Invariant: UoW was NOT mutated!
    assert len(uow.applied_changes) == 0


def test_worker_tracks_token_usage_and_cost_evidence():
    candidate = MemoryCandidate(
        candidate_id=new_candidate_id(),
        evidence_ids=(),
        owner_user_id="owner_1",
        scope=MemoryScope.CONVERSATION,
        conversation_id="conv_1",
        canonical_key="travel.preference.budget",
        normalized_value="moderate",
        display_text="moderate budget",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=MOMENT,
    )
    model = FakeExtractionModel(candidates=[candidate])
    model.prompt_version = "2026-09-07.v1"
    model.schema_version = "2026-09-07.v1"
    model.last_token_usage = TokenUsage(prompt_tokens=42, completion_tokens=15, total_tokens=57)
    model.last_cost_evidence = CostEvidence(estimated_cost_usd=0.00012, model_name="test-model")

    worker, outbox, uow, _, conv_svc = _setup_worker(model=model)
    conv_svc.conversations["conv_1"] = {"conversation_id": "conv_1", "owner_user_id": "owner_1", "retention_state": "active"}
    conv_svc.messages["conv_1"] = [{"message_id": "msg_1", "role": "user", "content": "moderate budget"}]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT,
    )
    outbox.save_event(event)

    res = worker.process_one(event)
    assert res.status == OutboxStatus.SUCCEEDED
    assert res.prompt_version == "2026-09-07.v1"
    assert res.schema_version == "2026-09-07.v1"
    assert res.token_usage == TokenUsage(prompt_tokens=42, completion_tokens=15, total_tokens=57)
    assert res.cost_evidence == CostEvidence(estimated_cost_usd=0.00012, model_name="test-model")


def test_worker_delegates_to_service_record_shadow_candidate():
    candidate = MemoryCandidate(
        candidate_id=new_candidate_id(),
        evidence_ids=(),
        owner_user_id="owner_1",
        scope=MemoryScope.CONVERSATION,
        conversation_id="conv_1",
        canonical_key="travel.preference.flight",
        normalized_value="window",
        display_text="window seat",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=MOMENT,
    )
    model = FakeExtractionModel(candidates=[candidate])

    class FakeService:
        def __init__(self):
            self.calls = []

        def record_shadow_candidate(self, principal, candidate, evidence, context=None, idempotency_key=None):
            self.calls.append({
                "principal": principal,
                "candidate": candidate,
                "evidence": evidence,
                "context": context,
                "idempotency_key": idempotency_key,
            })
            from backend.memory.write_pipeline.uow import MemoryWriteResult
            return MemoryWriteResult(
                operation=MemoryOperation.NOOP,
                version_id=None,
                superseded_version_ids=(),
                reference_version_id=None,
                decision_id="dec_1",
                reason=DecisionReason.SHADOW_VALID_UNPROMOTED.value,
            )

    fake_service = FakeService()
    worker, outbox, uow, _, conv_svc = _setup_worker(model=model, service=fake_service)

    conv_svc.conversations["conv_1"] = {"conversation_id": "conv_1", "owner_user_id": "owner_1", "retention_state": "active"}
    conv_svc.messages["conv_1"] = [{"message_id": "msg_1", "role": "user", "content": "window seat"}]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT,
    )
    outbox.save_event(event)

    res = worker.process_one(event)
    assert res.status == OutboxStatus.SUCCEEDED
    assert len(fake_service.calls) == 1
    call = fake_service.calls[0]
    assert call["principal"].owner_user_id == "owner_1"
    assert call["candidate"].canonical_key == "travel.preference.flight"
    assert call["idempotency_key"] == f"bg_cout_1_{candidate.candidate_id}"


def test_worker_aborts_when_mark_succeeded_fails():
    worker, outbox, uow, model, conv_svc = _setup_worker()

    conv_svc.conversations["conv_1"] = {"conversation_id": "conv_1", "owner_user_id": "owner_1", "retention_state": "active"}
    conv_svc.messages["conv_1"] = [{"message_id": "msg_1", "role": "user", "content": "I like quiet hotels."}]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT,
    )
    outbox.save_event(event)

    # Force mark_succeeded to return False
    outbox.mark_succeeded = lambda *args, **kwargs: False

    res = worker.process_one(event)
    assert res.status == OutboxStatus.CANCELLED
    assert res.error == "mark_succeeded_failed_lease_lost"



