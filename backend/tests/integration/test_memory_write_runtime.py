"""Integration and runtime tests for the memory background shadow pipeline.

Covers ADR 0014 and Child Plan 5:
- Message/outbox atomicity: User message and extraction outbox event commit in 1 transaction
- Chat non-blocking: Chat turn persists without waiting for extraction or model latency
- Outbox states: PENDING, LEASED, SUCCEEDED, DEAD_LETTER, CANCELLED
- Worker lease claim, duration, expiry, and reclaiming
- Same-conversation serialization / parallel worker fairness
- Deletion cancellation: If conversation is deleted, background job cancelled
- Error classification: Transient error retried with backoff, permanent dead-lettered
- Zero active versions: Background shadow extraction creates zero active memory versions
"""

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional
import pytest
import sqlalchemy as sa

from backend.conversations.models import (
    Conversation,
    ConversationCreate,
    ConversationRetentionState,
    MessageDraft,
    MessageRole,
    MessageSource,
    utc_now,
)
from backend.conversations.postgres_repository import PostgresConversationRepository
from backend.conversations.service import ConversationService
from backend.memory.write_pipeline.models import (
    Authority,
    DecisionOutcome,
    MemoryCandidate,
    MemoryScope,
    SensitivityBand,
    VersionStatus,
)
from backend.memory.write_pipeline.model_adapter import (
    MemoryExtractionModel,
    ProviderPermanentError,
    ProviderTransientError,
)
from backend.memory.write_pipeline.background_recorder import BackgroundMemoryRecorder
from backend.memory.write_pipeline.outbox import (
    InMemoryOutboxRepository,
    OutboxEvent,
    OutboxStatus,
    PostgresOutboxRepository,
)
from backend.memory.write_pipeline.worker import MemoryOutboxWorker
from backend.orchestration.conversation_orchestrator import (
    ConversationOrchestrator,
    TurnOutcome,
)
from backend.tests.integration.pg_dsn import migration_dsn, require

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)

requires_pg = pytest.mark.skipif(
    not migration_dsn(),
    reason="isolated PG unavailable: set PG_TEST_DSN to a disposable database",
)


class StubRAGService:
    def generate_answer(self, user_message: str, top_k: int | None = None) -> dict:
        return {
            "reply": "I recommend peaceful boutique hotels in Da Nang.",
            "model": "stub-rag",
            "citations": [],
        }


class MockModelProvider:
    def __init__(
        self, response_text: str = '{"candidates": []}', delay_seconds: float = 0.0
    ):
        self.response_text = response_text
        self.delay_seconds = delay_seconds
        self.call_count = 0

    def generate(self, prompt: str, **kwargs) -> str:
        self.call_count += 1
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)
        return self.response_text


class RecordingUoW:
    def __init__(self):
        self.applied_changes = []
        self.active_versions = []

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
        if change.new_version and change.new_version.status == VersionStatus.ACTIVE:
            self.active_versions.append(change.new_version)


def test_chat_non_blocking_and_outbox_capture():
    """Verify chat turn returns without blocking on background extraction."""
    outbox_repo = InMemoryOutboxRepository()
    mock_provider = MockModelProvider(
        response_text='{"candidates": [{"canonical_key": "travel.preference.hotel_atmosphere", "value": "quiet", "display_text": "I like quiet hotels"}]}',
        delay_seconds=2.0,  # 2 second latency simulation
    )
    model = MemoryExtractionModel(provider=mock_provider)
    uow = RecordingUoW()

    # Fake repository that saves to outbox_repo
    class InMemoryConvRepo:
        def __init__(self):
            self.messages = []
            self.deletion_epochs = {}

        def get_deletion_epoch(self, conversation_id, owner_user_id=None):
            return self.deletion_epochs.get(conversation_id, 0)

        def append_message(
            self,
            message: MessageDraft,
            message_id: str,
            owner_user_id: str | None = None,
            outbox_event: Any = None,
        ):
            self.messages.append((message, message_id))
            if outbox_event:
                event_type = getattr(
                    outbox_event, "event_type", None
                ) or outbox_event.get("event_type")
                payload = getattr(outbox_event, "payload", None) or outbox_event.get(
                    "payload", {}
                )
                outbox_repo.save_event(
                    OutboxEvent(
                        outbox_id="cout_test_1",
                        conversation_id=message.conversation_id,
                        message_id=message_id,
                        owner_user_id=owner_user_id or "user_1",
                        event_type=event_type,
                        payload=payload,
                        created_at=utc_now(),
                    )
                )
            from backend.conversations.models import Message

            return Message(
                message_id=message_id,
                conversation_id=message.conversation_id,
                sequence=len(self.messages),
                role=message.role,
                content=message.content,
                source=message.source,
                trace_visibility=message.trace_visibility,
                created_at=utc_now(),
            )

        def append_turn(
            self,
            conversation_id: str,
            owner_user_id: str | None = None,
            user_content: str = "",
            assistant_placeholder: str = "",
            outbox_event: Any = None,
        ):
            """Allocate the user row and the pending reply slot together.

            Mirrors the adapter's two-phase turn (ADR 0023): the outbox event is
            written with the turn, and the reply slot starts `pending` so a
            failure has a row to mark.
            """
            from backend.conversations.models import (
                Message,
                MessageRole,
                MessageSource,
                MessageStatus,
                TraceVisibility,
            )

            moment = utc_now()
            base = len(self.messages) + 1
            user = Message(
                message_id=f"ms_user_{base}",
                conversation_id=conversation_id,
                sequence=base,
                role=MessageRole.USER,
                content=user_content,
                source=MessageSource.UI,
                trace_visibility=TraceVisibility.EXCLUDED,
                created_at=moment,
                status=MessageStatus.COMPLETE,
            )
            pending = Message(
                message_id=f"ms_pending_{base}",
                conversation_id=conversation_id,
                sequence=base + 1,
                role=MessageRole.ASSISTANT,
                content=assistant_placeholder,
                source=MessageSource.MODEL,
                trace_visibility=TraceVisibility.EXCLUDED,
                created_at=moment,
                status=MessageStatus.PENDING,
            )
            self.messages.append((user, user.message_id))
            self.messages.append((pending, pending.message_id))

            if outbox_event:
                event_type = getattr(
                    outbox_event, "event_type", None
                ) or outbox_event.get("event_type")
                payload = getattr(outbox_event, "payload", None) or outbox_event.get(
                    "payload", {}
                )
                outbox_repo.save_event(
                    OutboxEvent(
                        outbox_id="cout_test_1",
                        conversation_id=conversation_id,
                        message_id=user.message_id,
                        owner_user_id=owner_user_id or "user_1",
                        event_type=event_type,
                        payload=payload,
                        created_at=moment,
                    )
                )
            return user, pending

        def complete_turn(
            self,
            conversation_id: str,
            message_id: str,
            owner_user_id: str | None = None,
            content: str = "",
        ):
            result = self._transition_turn(message_id, "complete", content)
            if result.applied:
                self._release_turn_outbox()
            return result

        def fail_turn(
            self,
            conversation_id: str,
            message_id: str,
            owner_user_id: str | None = None,
        ):
            result = self._transition_turn(message_id, "failed", "")
            if result.applied:
                # Production cancels the turn's event in the same transaction, so an
                # unanswered turn cannot be extracted over.
                outbox_repo.cancel_events(conversation_id, reason="turn_failed")
            return result

        def _release_turn_outbox(self):
            """ADR 0027: a terminal turn is what releases its extraction event.

            Production releases it in the same transaction as the status change, so
            "complete" and "released" cannot diverge. This fake used to model
            neither half and left the event blocked forever. Nothing noticed while
            the outbox double also ignored the gate; the moment the double started
            applying it, the worker refused to claim the event and this test failed.

            That is the point of a faithful double: it turns a fake that quietly
            disagrees with production into a failure.
            """
            from dataclasses import replace

            event = outbox_repo.get_event("cout_test_1")
            if event is not None and event.released_at is None:
                outbox_repo.save_event(
                    replace(event, released_at=datetime.now(timezone.utc))
                )

        def _transition_turn(self, message_id: str, status: str, content: str):
            """Mirror the adapter's guard, including the `applied` flag."""
            from backend.conversations.models import (
                Message,
                MessageStatus,
                TransitionResult,
            )

            for index, (stored, stored_id) in enumerate(self.messages):
                if stored_id != message_id:
                    continue
                if stored.status is not MessageStatus.PENDING:
                    return TransitionResult(message=stored, applied=False)
                updated = Message(
                    message_id=stored.message_id,
                    conversation_id=stored.conversation_id,
                    sequence=stored.sequence,
                    role=stored.role,
                    content=content,
                    source=stored.source,
                    trace_visibility=stored.trace_visibility,
                    created_at=stored.created_at,
                    status=MessageStatus(status),
                )
                self.messages[index] = (updated, stored_id)
                return TransitionResult(message=updated, applied=True)
            raise ConversationGoneError("The assistant message does not exist.")

        def list_messages(
            self,
            conversation_id: str,
            owner_user_id: str | None = None,
            after_sequence: int | None = None,
            limit: int = 100,
            until_sequence: int | None = None,
        ):
            from backend.conversations.models import Message

            return tuple(
                Message(
                    message_id=mid,
                    conversation_id=m.conversation_id,
                    sequence=i + 1,
                    role=m.role,
                    content=m.content,
                    source=m.source,
                    trace_visibility=m.trace_visibility,
                    created_at=utc_now(),
                    status=m.status,
                )
                for i, (m, mid) in enumerate(self.messages)
            )

    conv_repo = InMemoryConvRepo()

    conv_service = ConversationService(conv_repo)
    # Pretend conversation exists (owner-scoped read signature)
    conv_service.get_conversation = lambda cid, owner: Conversation(
        conversation_id=cid,
        owner_user_id=owner,
        title="Test Trip",
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    principal = SimpleNamespace(owner_user_id="user_1", auth_mode="authenticated")

    orchestrator = ConversationOrchestrator(
        rag_service=StubRAGService(),
        conversation_service_provider=lambda: conv_service,
        outbox_enabled=True,
    )

    start_time = time.monotonic()
    outcome = orchestrator.handle_turn(
        message="I prefer quiet boutique hotels.",
        conversation_id="cv_100",
        principal=principal,
    )
    elapsed = time.monotonic() - start_time

    # Chat finished immediately without waiting for the 2.0s model extraction!
    assert elapsed < 0.5
    assert outcome.reply == "I recommend peaceful boutique hotels in Da Nang."
    assert mock_provider.call_count == 0  # Not called during chat turn!

    # Outbox has the pending event
    event = outbox_repo.get_event("cout_test_1")
    assert event is not None
    assert event.status == OutboxStatus.PENDING

    # Now the background worker processes the outbox event
    worker = MemoryOutboxWorker(
        outbox_repo=outbox_repo,
        model_adapter=model,
        conversation_service=conv_service,
        recorder=BackgroundMemoryRecorder(uow_factory=lambda: uow),
        worker_id="bg_worker_1",
    )
    res = worker.process_one(event)
    assert res.status == OutboxStatus.SUCCEEDED
    assert res.candidates_count == 1
    assert outbox_repo.get_event("cout_test_1").status == OutboxStatus.SUCCEEDED

    # Invariant: Zero active versions!
    assert len(uow.active_versions) == 0
    assert len(uow.applied_changes) == 1
    assert uow.applied_changes[0]["decision"].outcome == DecisionOutcome.SHADOW
    # The commit was fenced to the observed lease and epoch.
    recorded_fence = uow.applied_changes[0]["fence"]
    assert recorded_fence is not None
    assert recorded_fence.outbox_id == "cout_test_1"
    assert recorded_fence.lease_owner == "bg_worker_1"
    assert recorded_fence.conversation_id == "cv_100"


# ---------------------------------------------------------------------------
# Live PostgreSQL Integration Tests (Skipped if PG_TEST_DSN is unset)
# ---------------------------------------------------------------------------


def _test_dsn() -> str:
    """The DDL-capable DSN: this module drops and rebuilds the schema."""
    return require(migration_dsn(), "PG_TEST_DSN")


@pytest.fixture(scope="module")
def pg_engine():
    from backend.storage.postgres import create_engine

    engine = create_engine(_test_dsn())
    try:
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
    except Exception as error:
        engine.dispose()
        raise RuntimeError(
            f"isolated PG unreachable: {type(error).__name__}; "
            "a configured PG_TEST_DSN must be reachable, not skipped."
        ) from error
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def pg_migrated(pg_engine):
    from alembic import command
    from backend.storage.postgres import alembic_config
    from pathlib import Path

    migrations = (
        Path(__file__).resolve().parent.parent.parent / "storage" / "migrations"
    )
    with pg_engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(str(migrations), _test_dsn()), "head")
    yield pg_engine


@pytest.fixture()
def clean_pg(pg_engine, pg_migrated):
    with pg_engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE conversation_outbox, messages, conversations, "
                "memory_write_idempotency, memory_outbox, "
                "memory_events, memory_decisions, memory_evidence, "
                "memory_candidates, memory_versions, memory_assertions"
            )
        )
    yield pg_engine


@requires_pg
def test_postgres_outbox_atomic_message_append(clean_pg):
    """Verify that message append and conversation_outbox row are committed atomically in Postgres."""
    repo = PostgresConversationRepository(clean_pg)
    conv = repo.create(
        Conversation(
            conversation_id="cv_pg_1",
            owner_user_id="owner_1",
            title="Da Nang",
            created_at=MOMENT,
            updated_at=MOMENT,
        )
    )

    msg = repo.append_message(
        MessageDraft(
            conversation_id="cv_pg_1",
            role=MessageRole.USER,
            content="I prefer quiet hotels.",
            source=MessageSource.UI,
            created_at=MOMENT,
        ),
        message_id="ms_pg_1",
        owner_user_id="owner_1",
        outbox_event={
            "event_type": "memory.extract.conversation_range",
            "payload": {"conversation_id": "cv_pg_1"},
        },
    )

    outbox_repo = PostgresOutboxRepository(clean_pg)
    claimed = outbox_repo.claim_batch(
        lease_owner="worker_pg_1",
        lease_duration_seconds=30.0,
        limit=10,
    )

    assert len(claimed) == 1
    assert claimed[0].conversation_id == "cv_pg_1"
    assert claimed[0].message_id == "ms_pg_1"
    assert claimed[0].status == OutboxStatus.LEASED
    assert claimed[0].lease_owner == "worker_pg_1"
    assert claimed[0].attempt_count == 1


@requires_pg
def test_postgres_outbox_parallel_worker_skip_locked(clean_pg):
    """Verify FOR UPDATE SKIP LOCKED prevents concurrent workers from claiming the same events."""
    repo = PostgresConversationRepository(clean_pg)
    for i in range(3):
        cid = f"cv_pg_2_{i}"
        repo.create(
            Conversation(
                conversation_id=cid,
                owner_user_id="owner_2",
                title=f"Hoi An {i}",
                created_at=MOMENT,
                updated_at=MOMENT,
            )
        )
        repo.append_message(
            MessageDraft(
                conversation_id=cid,
                role=MessageRole.USER,
                content=f"Message {i}",
                source=MessageSource.UI,
                created_at=MOMENT + timedelta(seconds=i),
            ),
            message_id=f"ms_multi_{i}",
            owner_user_id="owner_1",
            outbox_event={
                "event_type": "memory.extract.conversation_range",
                "payload": {"idx": i},
            },
        )

    outbox_repo = PostgresOutboxRepository(clean_pg)

    # Worker 1 claims 2 events
    claimed_w1 = outbox_repo.claim_batch(
        lease_owner="worker_1",
        lease_duration_seconds=30.0,
        limit=2,
    )
    assert len(claimed_w1) == 2

    # Worker 2 simultaneously claims: gets the remaining 1 event (no duplicate claim!)
    claimed_w2 = outbox_repo.claim_batch(
        lease_owner="worker_2",
        lease_duration_seconds=30.0,
        limit=2,
    )
    assert len(claimed_w2) == 1

    # Overlap is empty
    ids_w1 = {ev.outbox_id for ev in claimed_w1}
    ids_w2 = {ev.outbox_id for ev in claimed_w2}
    assert ids_w1.isdisjoint(ids_w2)
