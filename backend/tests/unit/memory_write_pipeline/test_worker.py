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
from backend.conversations.models import MEMORY_EXTRACT_EVENT_TYPE
from backend.memory.write_pipeline.observability import WorkerReason
from backend.memory.write_pipeline.uow import FenceReason
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
        self.active_versions: list = []

    def get_active_versions(self, owner_user_id: str, canonical_key: str):
        """Return this double's active versions for one owner and key.

        Required by `MemoryUnitOfWork`: the recorder reads the real history
        instead of probing for the capability (C8).
        """
        return tuple(
            version
            for version in self.active_versions
            if getattr(version, "owner_user_id", None) == owner_user_id
            and getattr(version, "canonical_key", None) == canonical_key
        )

    def apply_memory_change(
        self,
        change,
        principal,
        *,
        evidence=(),
        decision=None,
        idempotency_key=None,
        expected_version_id=None,
        fence=None,
    ):
        self.applied_changes.append(
            {
                "change": change,
                "principal": principal,
                "evidence": evidence,
                "decision": decision,
                "idempotency_key": idempotency_key,
                "fence": fence,
            }
        )
        # If any version were active, record it (for zero-active verification)
        if change.new_version and change.new_version.status == VersionStatus.ACTIVE:
            self.versions.append(change.new_version)


class FakeConversationService:
    def __init__(self):
        self.conversations = {}
        self.messages = {}
        self.deletion_epochs = {}

    def get_conversation(self, conversation_id, owner_user_id):
        return self.conversations.get(conversation_id)

    def get_messages(self, conversation_id, owner_user_id):
        return self.messages.get(conversation_id, [])

    def get_message(self, message_id, owner_user_id):
        for msgs in self.messages.values():
            for msg in msgs:
                if msg.get("message_id") == message_id:
                    return msg
        return None

    def get_messages_in_range(
        self,
        conversation_id,
        owner_user_id,
        after_sequence=None,
        limit=100,
        until_sequence=None,
    ):
        msgs = self.messages.get(conversation_id, [])
        return [
            m
            for m in msgs
            if (after_sequence is None or m.get("sequence", 0) > after_sequence)
            and (until_sequence is None or m.get("sequence", 0) <= until_sequence)
        ][:limit]

    def get_deletion_epoch(self, conversation_id, owner_user_id):
        return self.deletion_epochs.get(conversation_id, 0)


def _setup_worker(model=None, uow=None, outbox=None, conv_service=None, recorder=None):
    outbox_repo = outbox or InMemoryOutboxRepository()
    uow_fake = uow or FakeUoW()
    model_fake = model or FakeExtractionModel()
    conv_svc = conv_service or FakeConversationService()
    if recorder is None:
        from backend.memory.write_pipeline.background_recorder import (
            BackgroundMemoryRecorder,
        )

        recorder = BackgroundMemoryRecorder(uow_factory=lambda: uow_fake)

    worker = MemoryOutboxWorker(
        outbox_repo=outbox_repo,
        model_adapter=model_fake,
        conversation_service=conv_svc,
        recorder=recorder,
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
        released_at=MOMENT,
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
        released_at=MOMENT,
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
        {
            "message_id": "msg_1",
            "role": "user",
            "content": "Here is my key sk-proj-1234567890abcdef",
        }
    ]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1", "message_id": "msg_1"},
        created_at=MOMENT,
        released_at=MOMENT,
    )
    outbox.save_event(event)

    result = worker.process_one(event)
    assert (
        result.status == OutboxStatus.SUCCEEDED
    )  # Job succeeded by rejecting secret without leak
    # Model was NOT called with secret text
    assert len(model.calls) == 0


def test_worker_pre_model_scan_covers_non_string_content():
    """Structured block content is scanned serialized, not skipped."""
    worker, outbox, uow, model, conv_svc = _setup_worker()

    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {
            "message_id": "msg_1",
            "role": "user",
            "content": [{"type": "text", "text": "api_key: sk-proj-1234567890abcdef"}],
        }
    ]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1", "message_id": "msg_1"},
        created_at=MOMENT,
        released_at=MOMENT,
    )
    outbox.save_event(event)

    result = worker.process_one(event)
    assert result.status == OutboxStatus.SUCCEEDED
    assert result.reason is WorkerReason.PROHIBITED_CONTENT
    assert len(model.calls) == 0


def test_worker_retries_transient_error_and_dead_letters_permanent():
    from backend.memory.write_pipeline.model_adapter import (
        ProviderTransientError,
        ProviderPermanentError,
    )

    # 1. Transient error
    transient_model = FakeExtractionModel(
        should_raise=ProviderTransientError("Rate limit 429")
    )
    worker, outbox, _, _, conv_svc = _setup_worker(model=transient_model)

    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "role": "user", "content": "I prefer quiet rooms."}
    ]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1", "message_id": "msg_1"},
        created_at=MOMENT,
        released_at=MOMENT,
    )
    outbox.save_event(event)

    res1 = worker.process_one(event)
    assert res1.status == OutboxStatus.PENDING  # Retried
    assert outbox.get_event("cout_1").status == OutboxStatus.PENDING

    # 2. Permanent error
    perm_model = FakeExtractionModel(
        should_raise=ProviderPermanentError("Invalid auth")
    )
    worker_perm, outbox_perm, _, _, conv_svc_perm = _setup_worker(model=perm_model)
    conv_svc_perm.conversations["conv_2"] = {
        "conversation_id": "conv_2",
        "owner_user_id": "owner_2",
        "retention_state": "active",
    }
    conv_svc_perm.messages["conv_2"] = [
        {"message_id": "msg_2", "role": "user", "content": "I prefer quiet rooms."}
    ]

    event2 = OutboxEvent(
        outbox_id="cout_2",
        conversation_id="conv_2",
        message_id="msg_2",
        owner_user_id="owner_2",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_2", "message_id": "msg_2"},
        created_at=MOMENT,
        released_at=MOMENT,
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
        released_at=MOMENT,
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
        payload={
            "conversation_id": "conv_1",
            "message_id": "msg_1",
            "deletion_epoch": 2,
        },
        created_at=MOMENT,
        released_at=MOMENT,
    )
    outbox.save_event(event)

    result = worker.process_one(event)
    assert result.status == OutboxStatus.CANCELLED
    assert outbox.get_event("cout_1").status == OutboxStatus.CANCELLED


def test_worker_run_batch_and_poll_once():
    worker, outbox, uow, model, conv_svc = _setup_worker()

    for i in range(1, 4):
        cid = f"conv_{i}"
        conv_svc.conversations[cid] = {
            "conversation_id": cid,
            "owner_user_id": f"owner_{i}",
            "retention_state": "active",
        }
        conv_svc.messages[cid] = [
            {"message_id": f"msg_{i}", "role": "user", "content": f"Message {i}"}
        ]
        outbox.save_event(
            OutboxEvent(
                outbox_id=f"cout_{i}",
                conversation_id=cid,
                message_id=f"msg_{i}",
                owner_user_id=f"owner_{i}",
                event_type="memory.extract.conversation_range",
                payload={"conversation_id": cid, "message_id": f"msg_{i}"},
                created_at=MOMENT + timedelta(seconds=i),
                released_at=MOMENT,
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
    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "role": "user", "content": "Msg 1"}
    ]

    outbox.save_event(
        OutboxEvent(
            outbox_id="cout_1",
            conversation_id="conv_1",
            message_id="msg_1",
            owner_user_id="owner_1",
            event_type="memory.extract.conversation_range",
            payload={"conversation_id": "conv_1"},
            created_at=MOMENT,
            released_at=MOMENT,
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
            released_at=MOMENT,
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

    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "sequence": 1, "role": "user", "content": "First"},
        {
            "message_id": "msg_2",
            "sequence": 2,
            "role": "assistant",
            "content": "Second",
        },
        {"message_id": "msg_3", "sequence": 3, "role": "user", "content": "Third"},
        {
            "message_id": "msg_4",
            "sequence": 4,
            "role": "assistant",
            "content": "Fourth",
        },
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
        released_at=MOMENT,
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
                released_at=MOMENT,
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

    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "role": "user", "content": "I prefer luxury"}
    ]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT,
        released_at=MOMENT,
    )
    outbox.save_event(event)

    result = worker.process_one(event)
    # Must fail because lease was lost
    assert result.reason is WorkerReason.LEASE_LOST_BEFORE_COMMIT
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
    model.last_token_usage = TokenUsage(
        prompt_tokens=42, completion_tokens=15, total_tokens=57
    )
    model.last_cost_evidence = CostEvidence(
        estimated_cost_usd=0.00012, model_name="test-model"
    )

    worker, outbox, uow, _, conv_svc = _setup_worker(model=model)
    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "role": "user", "content": "moderate budget"}
    ]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT,
        released_at=MOMENT,
    )
    outbox.save_event(event)

    res = worker.process_one(event)
    assert res.status == OutboxStatus.SUCCEEDED
    assert res.prompt_version == "2026-09-07.v1"
    assert res.schema_version == "2026-09-07.v1"
    assert res.token_usage == TokenUsage(
        prompt_tokens=42, completion_tokens=15, total_tokens=57
    )
    assert res.cost_evidence == CostEvidence(
        estimated_cost_usd=0.00012, model_name="test-model"
    )


def test_worker_delegates_to_background_recorder_record_sync():
    """Worker must delegate to BackgroundMemoryRecorder.record_sync (the approved seam)."""
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

    from backend.memory.write_pipeline.background_recorder import (
        BackgroundMemoryRecorder,
        BackgroundRecordResult,
        ShadowCandidate,
    )
    from backend.memory.write_pipeline.models import DecisionOutcome

    class FakeRecorder:
        """Minimal recorder implementing record_sync — the narrow BackgroundMemoryRecorder seam."""

        def __init__(self):
            self.calls = []

        def record_sync(
            self,
            candidate: ShadowCandidate,
            source_outbox_id=None,
            source_message_id=None,
            conversation_id=None,
            fence=None,
        ) -> BackgroundRecordResult:
            self.calls.append((candidate, fence))
            return BackgroundRecordResult(
                status="recorded",
                candidate_id=candidate.candidate_id,
                decision_outcome=DecisionOutcome.SHADOW,
                operation=MemoryOperation.NOOP,
                reason="shadow_valid_unpromoted",
                write_result=None,
            )

    fake_recorder = FakeRecorder()
    worker, outbox, uow, _, conv_svc = _setup_worker(
        model=model, recorder=fake_recorder
    )

    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "role": "user", "content": "window seat"}
    ]

    event = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT,
        released_at=MOMENT,
    )
    outbox.save_event(event)

    res = worker.process_one(event)
    assert res.status == OutboxStatus.SUCCEEDED
    assert len(fake_recorder.calls) == 1
    recorded_candidate, recorded_fence = fake_recorder.calls[0]
    assert recorded_candidate.canonical_key == "travel.preference.flight"
    # The worker must bind the commit to the observed lease and epoch.
    assert recorded_fence.conversation_id == "conv_1"
    assert recorded_fence.expected_epoch == 0
    assert recorded_fence.outbox_id == "cout_1"
    assert recorded_fence.lease_owner == "test_worker_1"


def test_worker_aborts_when_mark_succeeded_fails():
    worker, outbox, uow, model, conv_svc = _setup_worker()

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
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT,
        released_at=MOMENT,
    )
    outbox.save_event(event)

    # Force mark_succeeded to return False
    outbox.mark_succeeded = lambda *args, **kwargs: False

    res = worker.process_one(event)
    assert res.status == OutboxStatus.CANCELLED
    assert res.reason is WorkerReason.MARK_SUCCEEDED_FAILED_LEASE_LOST


def test_worker_reports_fenced_write_as_obsolete():
    """A delete landing after extraction must not be recorded as success."""
    from backend.memory.write_pipeline.models import (
        Authority,
        MemoryCandidate,
        MemoryScope,
        SensitivityBand,
    )
    from backend.memory.write_pipeline.uow import FenceReason, FencedWriteError

    class FencingRecorder:
        def record_sync(self, *args, **kwargs):
            # A typed reason, not a sentence (ADR 0033). A conversation-shaped
            # reason is the one case where cancelling the conversation's other
            # work is justified, so the worker's response to it is what this test
            # pins.
            raise FencedWriteError(FenceReason.CONVERSATION_NOT_ACTIVE)

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
    worker, outbox, uow, _, conv_svc = _setup_worker(
        model=model, recorder=FencingRecorder()
    )

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
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT,
        released_at=MOMENT,
    )
    outbox.save_event(event)

    res = worker.process_one(event)
    assert res.reason is WorkerReason.FENCED_BY_SOURCE_MOVE
    assert res.status == OutboxStatus.CANCELLED
    # The *result* is CANCELLED — this worker is finished with the event — but the
    # row is deliberately left LEASED. Cancelling the row would be a terminal state
    # the worker holds no authority to write (ADR 0033), and it would remove the
    # event from the only recovery path it has: reclaim on lease expiry.
    assert outbox.get_event("cout_1").status == OutboxStatus.LEASED
    assert len(uow.applied_changes) == 0


# --- ADR 0033: a fence stops the worker; it does not cancel -------------------


class _CountingOutboxRepository(InMemoryOutboxRepository):
    """Records cancellation calls, so a fence's blast radius can be asserted.

    The worker's response to a fence is the whole subject of ADR 0033, and "it
    cancelled nothing" can only be asserted by counting the calls rather than
    inferring it from the resulting row states.
    """

    def __init__(self):
        super().__init__()
        self.cancel_calls: list[dict] = []

    def cancel_events(self, conversation_id, reason, now=None, lease_owner=None):
        self.cancel_calls.append(
            {
                "conversation_id": conversation_id,
                "reason": reason,
                "lease_owner": lease_owner,
            }
        )
        return super().cancel_events(
            conversation_id, reason, now=now, lease_owner=lease_owner
        )


def _fenced_worker(reason, *, outbox=None):
    """A worker whose recorder fences every write with `reason`."""
    from backend.memory.write_pipeline.models import (
        Authority,
        MemoryCandidate,
        MemoryScope,
        SensitivityBand,
    )
    from backend.memory.write_pipeline.uow import FencedWriteError

    class _FencingRecorder:
        def record_sync(self, *args, **kwargs):
            raise FencedWriteError(reason)

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
    worker, outbox_repo, uow, _, conv_svc = _setup_worker(
        model=FakeExtractionModel(candidates=[candidate]),
        outbox=outbox,
        recorder=_FencingRecorder(),
    )
    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "role": "user", "content": "I like quiet hotels."}
    ]
    return worker, outbox_repo, uow


def _two_turn_events(outbox):
    """Turn 1's event, which the worker holds, and turn 2's, still queued."""
    held = OutboxEvent(
        outbox_id="cout_1",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT,
        released_at=MOMENT,
    )
    later = OutboxEvent(
        outbox_id="cout_2",
        conversation_id="conv_1",
        message_id="msg_2",
        owner_user_id="owner_1",
        event_type="memory.extract.conversation_range",
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT + timedelta(seconds=1),
        released_at=MOMENT,
    )
    outbox.save_event(held)
    outbox.save_event(later)
    outbox.claim_event(
        "cout_1", lease_owner="test_worker_1", lease_duration_seconds=30.0
    )
    return held


@pytest.mark.parametrize("reason", list(FenceReason))
def test_a_fence_never_cancels_the_conversations_other_events(reason):
    """The load-bearing regression, over the whole reason vocabulary.

    A `FencedWriteError` used to trigger `cancel_events`, which cancels every
    `PENDING` row of the conversation. One of the six causes is "this worker lost
    its lease" — a fact about one worker's tenure, not about the conversation's
    validity. Turn 2's and turn 3's extraction died for it, permanently and
    silently: `CANCELLED` is a legitimate terminal state, indistinguishable from a
    deliberate cancellation.

    Parametrized over every member so a future reason cannot be added without
    deciding its blast radius, and so re-adding an unconditional call anywhere in
    the fence path fails here.
    """
    outbox = _CountingOutboxRepository()
    worker, outbox, uow = _fenced_worker(reason, outbox=outbox)
    held = _two_turn_events(outbox)

    result = worker.process_one(held)

    assert result.status == OutboxStatus.CANCELLED
    assert result.reason is WorkerReason.FENCED_BY_SOURCE_MOVE
    assert outbox.cancel_calls == [], (
        "a fenced write must stop, not cancel: the worker holds no authority to "
        "cancel work it does not hold"
    )
    assert outbox.get_event("cout_2").status == OutboxStatus.PENDING, (
        "a later turn's extraction must survive an earlier turn's fence"
    )
    assert outbox.get_event("cout_1").status == OutboxStatus.LEASED, (
        "the fenced event must stay LEASED so it stays reclaimable on expiry, "
        "rather than being cancelled"
    )
    assert len(uow.applied_changes) == 0


def test_a_lost_lease_does_not_cancel_a_later_turns_extraction():
    """The defect as the review found it, with its own narrative.

    Turn 1's lease expired while its worker was extracting. Under the old
    behaviour the worker's fence cancelled turn 2's queued extraction as well.
    """
    outbox = _CountingOutboxRepository()
    worker, outbox, _ = _fenced_worker(FenceReason.LEASE_LOST, outbox=outbox)
    held = _two_turn_events(outbox)

    worker.process_one(held)

    assert outbox.get_event("cout_2").status == OutboxStatus.PENDING
    assert outbox.cancel_calls == []


def test_the_worker_refuses_a_foreign_event_even_if_a_claim_hands_it_over():
    """The defence-in-depth layer, reached through the *batch* path.

    The faithful double cannot produce this input — it filters the family, as
    production does — so this uses the deliberately permissive one. That is the
    whole reason that double exists: a layer reachable only by a claim path that
    should not exist is still worth having, and worth testing, because the day the
    filter is wrong is the day this layer is the only thing left.
    """
    from backend.memory.write_pipeline.outbox import (
        PermissiveInMemoryOutboxRepository,
    )

    outbox = PermissiveInMemoryOutboxRepository()
    worker, outbox, uow, model, conv_svc = _setup_worker(outbox=outbox)
    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "role": "user", "content": "I like quiet hotels."}
    ]
    foreign = OutboxEvent(
        outbox_id="cout_foreign",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="agent.resume",
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT,
        released_at=MOMENT,
    )
    outbox.save_event(foreign)

    # The permissive double claims it, exactly as an unfiltered claim would, and
    # the batch reports the refusal rather than a result.
    results = worker.run_batch(limit=10)

    assert len(results) == 1, "the permissive claim handed the event over"
    assert results[0].reason is WorkerReason.WRONG_EVENT_FAMILY, (
        "and the worker refused it rather than extracting from it"
    )
    assert model.calls == [], "the foreign event never reached the model"
    assert len(uow.applied_changes) == 0


# --- lease economics: renew before paying, not after --------------------------


class _RenewalRecordingRepository(InMemoryOutboxRepository):
    """Records renewals and delegates to the faithful double."""

    def __init__(self):
        super().__init__()
        self.renew_calls: list[str] = []

    def renew_lease(
        self, outbox_id, lease_owner, lease_duration_seconds, now=None
    ):
        self.renew_calls.append(outbox_id)
        return super().renew_lease(
            outbox_id, lease_owner, lease_duration_seconds, now=now
        )


class _RenewalRefusingRepository(InMemoryOutboxRepository):
    """A repository that will not extend the lease, for the abandon path."""

    def __init__(self):
        super().__init__()
        self.renew_calls: list[str] = []

    def renew_lease(
        self, outbox_id, lease_owner, lease_duration_seconds, now=None
    ):
        self.renew_calls.append(outbox_id)
        return False


def _leased_event(outbox, *, remaining_seconds: float):
    """One event leased to this worker with a controlled amount of lease left.

    The worker's default lease is 30s, so half of it — the headroom it insists on
    before a model call — is 15s. A `remaining_seconds` below that must trigger a
    renewal; one above it must not.
    """
    event = OutboxEvent(
        outbox_id="cout_lease",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type=MEMORY_EXTRACT_EVENT_TYPE,
        payload={"conversation_id": "conv_1"},
        status=OutboxStatus.LEASED,
        lease_owner="test_worker_1",
        lease_until=datetime.now(timezone.utc) + timedelta(seconds=remaining_seconds),
        released_at=MOMENT,
        created_at=MOMENT,
    )
    outbox.save_event(event)
    return event


def _worker_with(outbox, model):
    worker, _, uow, model, conv_svc = _setup_worker(outbox=outbox, model=model)
    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "role": "user", "content": "I like quiet hotels."}
    ]
    return worker, uow, model


def test_the_lease_is_renewed_before_a_model_call_with_little_time_left():
    """The batch is claimed up front and processed serially.

    So the last event of a batch of ten can reach its model call with almost none of
    its lease left. The fence protects correctness — a late write is refused — but
    not cost: the provider is paid, and *then* the worker discovers the lease is
    gone. Renewing before the call is what stops paying for discarded work.
    """
    outbox = _RenewalRecordingRepository()
    model = FakeExtractionModel()
    worker, _, _ = _worker_with(outbox, model)
    event = _leased_event(outbox, remaining_seconds=5.0)

    worker.process_one(event)

    assert outbox.renew_calls == ["cout_lease"], "the lease was extended first"
    assert len(model.calls) == 1, "and the extraction still ran"


def test_a_lease_with_plenty_of_time_left_is_not_renewed():
    """The control: renewing on every event would be a write per event for nothing."""
    outbox = _RenewalRecordingRepository()
    model = FakeExtractionModel()
    worker, _, _ = _worker_with(outbox, model)
    event = _leased_event(outbox, remaining_seconds=300.0)

    worker.process_one(event)

    assert outbox.renew_calls == [], "no renewal was needed"
    assert len(model.calls) == 1


def test_an_unrenewable_lease_abandons_before_paying_the_provider():
    """Stop rather than spend: the fence would refuse the write anyway."""
    outbox = _RenewalRefusingRepository()
    model = FakeExtractionModel()
    worker, uow, _ = _worker_with(outbox, model)
    event = _leased_event(outbox, remaining_seconds=5.0)

    result = worker.process_one(event)

    assert outbox.renew_calls == ["cout_lease"], "it asked"
    assert model.calls == [], "and did not spend"
    assert result.reason is WorkerReason.LEASE_RENEWAL_FAILED
    assert len(uow.applied_changes) == 0
    # Left LEASED so it stays reclaimable, not cancelled.
    assert outbox.get_event("cout_lease").status == OutboxStatus.LEASED


# --- The event family boundary, second layer ----------------------------------


def test_a_foreign_event_family_is_refused_before_any_work():
    """The claim filters in SQL; the worker refuses anyway, and first.

    The in-memory double deliberately does not model the claim filter, so this is
    the only place the second layer can be exercised — which is precisely why the
    double does not model it. A double that filtered would hide the path this
    check exists to catch.

    Checked before the lease is taken, so a future claim path that forgets the
    filter cannot lease an event this worker would then extract from the wrong
    payload.
    """
    worker, outbox, uow, model, conv_svc = _setup_worker()

    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "role": "user", "content": "I like quiet hotels."}
    ]
    foreign = OutboxEvent(
        outbox_id="cout_foreign",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="agent.resume",
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT,
        released_at=MOMENT,
    )
    outbox.save_event(foreign)

    result = worker.process_one(foreign)

    assert result.reason is WorkerReason.WRONG_EVENT_FAMILY
    assert model.calls == [], "a foreign event must not reach the extraction model"
    assert len(uow.applied_changes) == 0

    # Untouched. It is not obsolete — it belongs to another consumer, so it must
    # stay exactly as queued: not leased, not cancelled, not dead-lettered.
    stored = outbox.get_event("cout_foreign")
    assert stored.status == OutboxStatus.PENDING
    assert stored.lease_owner is None
    assert stored.attempt_count == 0


def test_a_foreign_event_is_not_counted_as_processed_work():
    """`run_batch` must not report it as a claim this worker acted on.

    The result carries the event's own status rather than `CANCELLED`, because
    "this worker is finished with it" would be false: another consumer still has
    to handle it.
    """
    worker, outbox, _, model, conv_svc = _setup_worker()
    conv_svc.conversations["conv_1"] = {
        "conversation_id": "conv_1",
        "owner_user_id": "owner_1",
        "retention_state": "active",
    }
    conv_svc.messages["conv_1"] = [
        {"message_id": "msg_1", "role": "user", "content": "x"}
    ]
    foreign = OutboxEvent(
        outbox_id="cout_foreign",
        conversation_id="conv_1",
        message_id="msg_1",
        owner_user_id="owner_1",
        event_type="summary.generate",
        payload={"conversation_id": "conv_1"},
        created_at=MOMENT,
        released_at=MOMENT,
    )
    outbox.save_event(foreign)

    result = worker.process_one(foreign)

    assert result.status is OutboxStatus.PENDING, (
        "the event's own status, so the result does not claim it was resolved"
    )
    assert model.calls == []


# --- ADR 0027: only finished messages may reach the extraction model ----------


def _load_with(conv_svc, messages):
    worker, *_ = _setup_worker(conv_service=conv_svc)
    conv_svc.messages["conv_1"] = messages
    return worker._load_messages("conv_1", "owner_1")


def test_load_messages_excludes_a_pending_assistant_row():
    """The defect: a half-written turn must not reach the model.

    Before this filter, `_load_messages` returned the `pending` assistant row,
    whose content is the empty placeholder, and handed it to the extraction model
    as if it were a real turn.
    """
    conv_svc = FakeConversationService()
    loaded = _load_with(
        conv_svc,
        [
            {"message_id": "m1", "sequence": 1, "role": "user",
             "content": "I prefer quiet hotels", "status": "complete"},
            {"message_id": "m2", "sequence": 2, "role": "assistant",
             "content": "", "status": "pending"},
        ],
    )
    assert [m["message_id"] for m in loaded] == ["m1"]


def test_load_messages_excludes_a_failed_assistant_row():
    conv_svc = FakeConversationService()
    loaded = _load_with(
        conv_svc,
        [
            {"message_id": "m1", "sequence": 1, "role": "user",
             "content": "hello", "status": "complete"},
            {"message_id": "m2", "sequence": 2, "role": "assistant",
             "content": "", "status": "failed"},
        ],
    )
    assert [m["message_id"] for m in loaded] == ["m1"]


def test_load_messages_keeps_completed_rows_and_the_sequence_filter():
    conv_svc = FakeConversationService()
    worker, *_ = _setup_worker(conv_service=conv_svc)
    conv_svc.messages["conv_1"] = [
        {"message_id": "m1", "sequence": 1, "role": "user",
         "content": "first", "status": "complete"},
        {"message_id": "m2", "sequence": 2, "role": "assistant",
         "content": "reply", "status": "complete"},
        {"message_id": "m3", "sequence": 3, "role": "user",
         "content": "third", "status": "complete"},
    ]
    loaded = worker._load_messages("conv_1", "owner_1", after_sequence=1)
    assert [m["message_id"] for m in loaded] == ["m2", "m3"]


def test_load_messages_treats_an_absent_status_as_complete():
    """Consistency with `Message.__post_init__`, which coerces absent to COMPLETE.

    Applying a stricter rule here would make the same message complete to the
    repository and not-complete to the worker. Reachable only through a test
    double: a persisted message always carries a coerced status.
    """
    conv_svc = FakeConversationService()
    loaded = _load_with(
        conv_svc,
        [{"message_id": "m1", "sequence": 1, "role": "user", "content": "hello"}],
    )
    assert [m["message_id"] for m in loaded] == ["m1"]


def test_load_messages_accepts_an_enum_status():
    """A real `Message` carries the enum member, not a bare string."""
    from backend.conversations.models import MessageStatus

    conv_svc = FakeConversationService()
    loaded = _load_with(
        conv_svc,
        [
            {"message_id": "m1", "sequence": 1, "role": "user",
             "content": "hello", "status": MessageStatus.COMPLETE},
            {"message_id": "m2", "sequence": 2, "role": "assistant",
             "content": "", "status": MessageStatus.PENDING},
        ],
    )
    assert [m["message_id"] for m in loaded] == ["m1"]


def test_load_messages_honours_the_upper_bound():
    """A per-turn event must not read later turns.

    Without the bound, a turn-1 event claimed after turn 2 was written read turn
    2's messages and attributed them to turn 1's provenance.
    """
    conv_svc = FakeConversationService()
    worker, *_ = _setup_worker(conv_service=conv_svc)
    conv_svc.messages["conv_1"] = [
        {"message_id": "m1", "sequence": 1, "role": "user",
         "content": "one", "status": "complete"},
        {"message_id": "m2", "sequence": 2, "role": "assistant",
         "content": "reply", "status": "complete"},
        {"message_id": "m3", "sequence": 3, "role": "user",
         "content": "two", "status": "complete"},
        {"message_id": "m4", "sequence": 4, "role": "assistant",
         "content": "reply two", "status": "complete"},
    ]

    loaded = worker._load_messages("conv_1", "owner_1", after_sequence=0, until_sequence=2)

    assert [m["message_id"] for m in loaded] == ["m1", "m2"], (
        "the read stops at the turn's own assistant row"
    )


def test_load_messages_without_an_upper_bound_reads_to_the_end():
    """The bound is optional; omitting it preserves the previous behaviour."""
    conv_svc = FakeConversationService()
    worker, *_ = _setup_worker(conv_service=conv_svc)
    conv_svc.messages["conv_1"] = [
        {"message_id": "m1", "sequence": 1, "role": "user",
         "content": "one", "status": "complete"},
        {"message_id": "m3", "sequence": 3, "role": "user",
         "content": "two", "status": "complete"},
    ]

    loaded = worker._load_messages("conv_1", "owner_1", after_sequence=0)

    assert [m["message_id"] for m in loaded] == ["m1", "m3"]
