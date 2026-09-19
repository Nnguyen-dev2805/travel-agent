"""Stage 4 Background Semantic Formation, Activation, and Outbox Bound Integration Tests.

Verifies on live PostgreSQL:
1. Default rollout: Background semantic extraction stays SHADOW (zero active versions).
2. Multi-turn conversation-scope agreement: Promotes to ACTIVE with >= 2 agreeing turns when flag enabled.
3. Multi-conversation user-scope agreement: Promotes to ACTIVE with >= 3 evidence items across >= 2 conversations.
4. Post-forget resurrection protection: Unresolved conflict or prior revocation prevents resurrection.
5. Outbox maintenance pass: Bounded pruning of expired pending projection events without touching canonical memory rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence
import pytest
import sqlalchemy as sa

from backend.conversations.models import (
    Conversation,
    MEMORY_EXTRACT_EVENT_TYPE,
    MessageDraft,
    MessageRole,
    MessageSource,
)
from backend.conversations.postgres_repository import (
    PostgresConversationRepository,
    set_tenant,
)
from backend.conversations.service import ConversationService
from backend.memory.activation import MemoryActivationPolicy
from backend.memory.commit_coordinators import BackgroundMemoryCommit
from backend.memory.lifecycle import MemoryLifecyclePolicy, RetentionAssignmentPolicy
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingOutcome,
    SourceHandlingReason,
    SourceHandlingRecord,
)
from backend.memory.write_pipeline.background_recorder import (
    BackgroundMemoryRecorder,
)
from backend.memory.write_pipeline.models import (
    Authority,
    DecisionOutcome,
    MemoryCandidate,
    MemoryScope,
    SensitivityBand,
    VersionStatus,
    assertion_identity,
    new_candidate_id,
    new_evidence_id,
)
from backend.memory.write_pipeline.outbox import (
    OutboxStatus,
    PostgresOutboxRepository,
)
from backend.memory.write_pipeline.postgres import (
    PostgresMemoryUnitOfWork,
    load_source_handling,
    record_source_handling,
)
from backend.memory.write_pipeline.worker import MemoryOutboxWorker
from backend.tests.integration.pg_dsn import (
    migration_dsn,
    require,
    runtime_dsn,
)

requires_pg = pytest.mark.skipif(
    not runtime_dsn(),
    reason="isolated PG unavailable: set PG_RUNTIME_TEST_DSN (least-privilege role)",
)
pytestmark = requires_pg

OWNER = "user_stage4_e2e"
MOMENT = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)


def _evaluated_gate(_canonical_key: str) -> bool:
    """Per-key promotion gate for the Stage-4 slice.

    R5 requires a conclusive evaluation per semantic key/type, and the recorder's
    default is fail-closed (`False` for every key). These tests exercise the
    activation thresholds for `hotel_atmosphere`, so they state that this key has
    been evaluated rather than inheriting it.
    """
    return True


def _source_handling_loader(engine):
    """Load the persisted source-handling authority record for one outbox event."""
    return lambda owner, outbox_id, family: load_source_handling(
        engine, owner, outbox_id, family
    )


class DeterministicModel:
    """Deterministic model adapter stub for integration tests."""

    def __init__(self, candidates: Sequence[MemoryCandidate] | None = None) -> None:
        self._candidates = list(candidates) if candidates is not None else []
        self.last_token_usage = None
        self.last_cost_evidence = None

    def set_candidates(self, candidates: Sequence[MemoryCandidate]) -> None:
        self._candidates = list(candidates)

    def extract(
        self,
        messages: Sequence[Any],
        owner_user_id: str,
        conversation_id: str,
        evidence_ids: Sequence[str] = (),
    ) -> list[MemoryCandidate]:
        res = []
        for c in self._candidates:
            res.append(
                MemoryCandidate(
                    candidate_id=new_candidate_id(),
                    evidence_ids=evidence_ids or (new_evidence_id(),),
                    owner_user_id=owner_user_id,
                    scope=c.scope,
                    conversation_id=conversation_id,
                    canonical_key=c.canonical_key,
                    normalized_value=c.normalized_value,
                    display_text=c.display_text,
                    authority=c.authority,
                    sensitivity=c.sensitivity,
                    observed_at=MOMENT,
                    confidence=c.confidence,
                )
            )
        return res


@pytest.fixture()
def ddl_engine():
    from backend.storage.postgres import create_engine

    engine = create_engine(require(migration_dsn(), "PG_TEST_DSN"))
    yield engine
    engine.dispose()


@pytest.fixture()
def migrated(ddl_engine):
    from alembic import command
    from backend.storage.postgres import alembic_config

    migrations = (
        Path(__file__).resolve().parent.parent.parent / "storage" / "migrations"
    )
    command.upgrade(
        alembic_config(str(migrations), require(migration_dsn(), "PG_TEST_DSN")),
        "head",
    )
    yield ddl_engine


@pytest.fixture()
def clean(ddl_engine, migrated):
    with ddl_engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE memory_write_idempotency, memory_outbox, "
                "memory_events, memory_decisions, memory_evidence, "
                "memory_candidates, memory_versions, memory_assertions, "
                "memory_source_handling, messages, conversations CASCADE"
            )
        )
    yield ddl_engine


def test_stage4_background_e2e_shadow_by_default(clean):
    """Positive source handling event is processed, but remains SHADOW by default rollout flag."""
    conv_repo = PostgresConversationRepository(clean)
    conv_svc = ConversationService(conversation_repository=conv_repo)

    cid = "cv_stage4_shadow_1"
    conv_repo.create(
        Conversation(
            conversation_id=cid,
            owner_user_id=OWNER,
            title="Stage 4 Test",
            created_at=MOMENT,
            updated_at=MOMENT,
        )
    )
    msg_id = "ms_s4_shadow_1"
    conv_repo.append_message(
        MessageDraft(
            conversation_id=cid,
            role=MessageRole.USER,
            content="I prefer quiet boutique hotels.",
            source=MessageSource.UI,
            created_at=MOMENT,
        ),
        message_id=msg_id,
        owner_user_id=OWNER,
        outbox_event={
            "event_type": MEMORY_EXTRACT_EVENT_TYPE,
            "payload": {"conversation_id": cid},
        },
    )

    outbox_repo = PostgresOutboxRepository(clean)
    events = outbox_repo.claim_batch(
        lease_owner="test_worker_s4",
        lease_duration_seconds=30.0,
        limit=10,
    )
    assert len(events) >= 1
    event = next(e for e in events if e.conversation_id == cid)

    sh_record = SourceHandlingRecord(
        source_outbox_id=event.outbox_id,
        source_message_id=msg_id,
        family=MemoryFamily.SEMANTIC,
        outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
        recorded_at=MOMENT,
    )
    record_source_handling(clean, OWNER, sh_record)

    candidate_template = MemoryCandidate(
        candidate_id="mc_s4_1",
        evidence_ids=("mev_s4_1",),
        owner_user_id=OWNER,
        scope=MemoryScope.USER,
        conversation_id=cid,
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        display_text="prefers quiet hotels",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=MOMENT,
        confidence=0.95,
    )
    model = DeterministicModel([candidate_template])

    commit_coordinator = BackgroundMemoryCommit(
        engine=clean,
        memory_write_store=PostgresMemoryUnitOfWork(clean),
    )
    recorder = BackgroundMemoryRecorder(
        uow_factory=lambda: PostgresMemoryUnitOfWork(clean),
        commit_coordinator=commit_coordinator,
        inferred_activation_enabled=False,  # Default rollout
        source_handling_loader=lambda owner, outbox_id, family: load_source_handling(
            clean, owner, outbox_id, family
        ),
    )

    worker = MemoryOutboxWorker(
        outbox_repo=outbox_repo,
        model_adapter=model,
        conversation_service=conv_svc,
        recorder=recorder,
        worker_id="test_worker_s4",
        source_handling_loader=_source_handling_loader(clean),
    )

    res = worker.process_one(event)

    assert res.status == OutboxStatus.SUCCEEDED
    assert res.candidates_count == 1

    with clean.connect() as conn:
        set_tenant(conn, OWNER)
        ev_count = conn.scalar(
            sa.text(
                "SELECT count(*) FROM memory_evidence WHERE owner_user_id = :owner AND conversation_id = :cid"
            ),
            {"owner": OWNER, "cid": cid},
        )
        assert ev_count == 1

        dec_row = conn.execute(
            sa.text(
                "SELECT outcome, reason FROM memory_decisions WHERE owner_user_id = :owner"
            ),
            {"owner": OWNER},
        ).fetchone()
        assert dec_row is not None
        assert dec_row[0] == "shadow"
        assert dec_row[1] == "shadow_valid_unpromoted"
        assert res.decision == DecisionOutcome.SHADOW

        active_versions = conn.scalar(
            sa.text(
                "SELECT count(*) FROM memory_versions WHERE owner_user_id = :owner AND status = 'active'"
            ),
            {"owner": OWNER},
        )
        assert active_versions == 0


def test_stage4_multi_turn_promotes_conversation_scope_when_enabled(clean):
    """Conversation-scope memory promotes to ACTIVE when 2 agreeing turns occur."""
    conv_repo = PostgresConversationRepository(clean)
    conv_svc = ConversationService(conversation_repository=conv_repo)

    cid = "cv_stage4_conv_scope"
    conv_repo.create(
        Conversation(
            conversation_id=cid,
            owner_user_id=OWNER,
            title="Conversation Scope Test",
            created_at=MOMENT,
            updated_at=MOMENT,
        )
    )

    # Turn 1
    msg1_id = "ms_s4_turn_1"
    conv_repo.append_message(
        MessageDraft(
            conversation_id=cid,
            role=MessageRole.USER,
            content="I want a quiet hotel for this trip.",
            source=MessageSource.UI,
            created_at=MOMENT,
        ),
        message_id=msg1_id,
        owner_user_id=OWNER,
        outbox_event={
            "event_type": MEMORY_EXTRACT_EVENT_TYPE,
            "payload": {"conversation_id": cid},
        },
    )

    outbox_repo = PostgresOutboxRepository(clean)
    events1 = outbox_repo.claim_batch(
        lease_owner="test_worker_s4",
        lease_duration_seconds=30.0,
        limit=10,
    )
    event1 = next(e for e in events1 if e.conversation_id == cid)

    record_source_handling(
        clean,
        OWNER,
        SourceHandlingRecord(
            source_outbox_id=event1.outbox_id,
            source_message_id=msg1_id,
            family=MemoryFamily.SEMANTIC,
            outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
            reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
            recorded_at=MOMENT,
        ),
    )

    cand_conv = MemoryCandidate(
        candidate_id="mc_s4_conv",
        evidence_ids=("mev_s4_c1",),
        owner_user_id=OWNER,
        scope=MemoryScope.CONVERSATION,
        conversation_id=cid,
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        display_text="prefers quiet hotels for this trip",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=MOMENT,
        confidence=0.95,
    )
    model = DeterministicModel([cand_conv])

    commit_coordinator = BackgroundMemoryCommit(
        engine=clean,
        memory_write_store=PostgresMemoryUnitOfWork(clean),
    )
    recorder = BackgroundMemoryRecorder(
        uow_factory=lambda: PostgresMemoryUnitOfWork(clean),
        commit_coordinator=commit_coordinator,
        inferred_activation_enabled=True,  # Activation enabled
        type_evaluation_gate=_evaluated_gate,
        source_handling_loader=lambda owner, outbox_id, family: load_source_handling(
            clean, owner, outbox_id, family
        ),
    )

    worker = MemoryOutboxWorker(
        outbox_repo=outbox_repo,
        model_adapter=model,
        conversation_service=conv_svc,
        recorder=recorder,
        worker_id="test_worker_s4",
        source_handling_loader=_source_handling_loader(clean),
    )

    # Process Turn 1: 1 turn is not enough for conversation scope (needs 2 turns)
    res1 = worker.process_one(event1)
    assert res1.status == OutboxStatus.SUCCEEDED

    with clean.connect() as conn:
        set_tenant(conn, OWNER)
        v_count_turn1 = conn.scalar(
            sa.text(
                "SELECT count(*) FROM memory_versions WHERE owner_user_id = :owner AND status = 'active'"
            ),
            {"owner": OWNER},
        )
        assert v_count_turn1 == 0

    # Turn 2: Second user message in the same conversation confirming quiet atmosphere
    msg2_id = "ms_s4_turn_2"
    conv_repo.append_message(
        MessageDraft(
            conversation_id=cid,
            role=MessageRole.USER,
            content="Make sure it's really quiet, no street noise.",
            source=MessageSource.UI,
            created_at=MOMENT,
        ),
        message_id=msg2_id,
        owner_user_id=OWNER,
        outbox_event={
            "event_type": MEMORY_EXTRACT_EVENT_TYPE,
            "payload": {"conversation_id": cid},
        },
    )

    events2 = outbox_repo.claim_batch(
        lease_owner="test_worker_s4",
        lease_duration_seconds=30.0,
        limit=10,
    )
    event2 = next(e for e in events2 if e.message_id == msg2_id)

    record_source_handling(
        clean,
        OWNER,
        SourceHandlingRecord(
            source_outbox_id=event2.outbox_id,
            source_message_id=msg2_id,
            family=MemoryFamily.SEMANTIC,
            outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
            reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
            recorded_at=MOMENT,
        ),
    )

    # Process Turn 2: Now 2 agreeing turns exist in conversation!
    res2 = worker.process_one(event2)
    assert res2.status == OutboxStatus.SUCCEEDED

    # Verify ACTIVE version row now exists in PostgreSQL!
    with clean.connect() as conn:
        set_tenant(conn, OWNER)
        row = conn.execute(
            sa.text(
                "SELECT v.status, a.scope, a.scope_id, v.normalized_value "
                "FROM memory_versions v "
                "JOIN memory_assertions a ON v.assertion_id = a.assertion_id "
                "WHERE v.owner_user_id = :owner AND v.status = 'active'"
            ),
            {"owner": OWNER},
        ).fetchone()
        assert row is not None
        assert row[0] == "active"
        assert row[1] == "conversation"
        assert row[2] == cid
        assert row[3] == "quiet"


def test_stage4_multi_conversation_promotes_user_scope_when_enabled(clean):
    """User-scope memory promotes to ACTIVE when >= 3 evidence items across >= 2 conversations occur."""
    conv_repo = PostgresConversationRepository(clean)
    conv_svc = ConversationService(conversation_repository=conv_repo)

    cid1 = "cv_stage4_user_1"
    cid2 = "cv_stage4_user_2"
    conv_repo.create(Conversation(conversation_id=cid1, owner_user_id=OWNER, title="Conv 1", created_at=MOMENT, updated_at=MOMENT))
    conv_repo.create(Conversation(conversation_id=cid2, owner_user_id=OWNER, title="Conv 2", created_at=MOMENT, updated_at=MOMENT))

    cand_user = MemoryCandidate(
        candidate_id="mc_s4_usr",
        evidence_ids=("mev_s4_u1",),
        owner_user_id=OWNER,
        scope=MemoryScope.USER,
        conversation_id=cid1,
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        display_text="prefers quiet hotels",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=MOMENT,
        confidence=0.95,
    )
    model = DeterministicModel([cand_user])

    commit_coordinator = BackgroundMemoryCommit(
        engine=clean,
        memory_write_store=PostgresMemoryUnitOfWork(clean),
    )
    recorder = BackgroundMemoryRecorder(
        uow_factory=lambda: PostgresMemoryUnitOfWork(clean),
        commit_coordinator=commit_coordinator,
        inferred_activation_enabled=True,
        type_evaluation_gate=_evaluated_gate,
        source_handling_loader=lambda owner, outbox_id, family: load_source_handling(
            clean, owner, outbox_id, family
        ),
    )
    outbox_repo = PostgresOutboxRepository(clean)
    worker = MemoryOutboxWorker(
        outbox_repo=outbox_repo,
        model_adapter=model,
        conversation_service=conv_svc,
        recorder=recorder,
        worker_id="test_worker_s4",
        source_handling_loader=_source_handling_loader(clean),
    )

    # 1. Turn 1 in Conversation 1
    m1_id = "ms_s4_u1"
    conv_repo.append_message(
        MessageDraft(conversation_id=cid1, role=MessageRole.USER, content="Quiet please.", source=MessageSource.UI, created_at=MOMENT),
        message_id=m1_id, owner_user_id=OWNER, outbox_event={"event_type": MEMORY_EXTRACT_EVENT_TYPE, "payload": {"conversation_id": cid1}},
    )
    e1 = next(e for e in outbox_repo.claim_batch("test_worker_s4", 30.0, 10) if e.message_id == m1_id)
    record_source_handling(clean, OWNER, SourceHandlingRecord(
        source_outbox_id=e1.outbox_id, source_message_id=m1_id,
        family=MemoryFamily.SEMANTIC, outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE, recorded_at=MOMENT,
    ))
    worker.process_one(e1)

    # 2. Turn 2 in Conversation 1
    m2_id = "ms_s4_u2"
    conv_repo.append_message(
        MessageDraft(conversation_id=cid1, role=MessageRole.USER, content="Still quiet please.", source=MessageSource.UI, created_at=MOMENT),
        message_id=m2_id, owner_user_id=OWNER, outbox_event={"event_type": MEMORY_EXTRACT_EVENT_TYPE, "payload": {"conversation_id": cid1}},
    )
    e2 = next(e for e in outbox_repo.claim_batch("test_worker_s4", 30.0, 10) if e.message_id == m2_id)
    record_source_handling(clean, OWNER, SourceHandlingRecord(
        source_outbox_id=e2.outbox_id, source_message_id=m2_id,
        family=MemoryFamily.SEMANTIC, outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE, recorded_at=MOMENT,
    ))
    worker.process_one(e2)

    # At this point: 2 evidence items, but only 1 conversation -> still SHADOW
    with clean.connect() as conn:
        set_tenant(conn, OWNER)
        v_count = conn.scalar(sa.text("SELECT count(*) FROM memory_versions WHERE owner_user_id = :owner AND status = 'active'"), {"owner": OWNER})
        assert v_count == 0

    # 3. Turn 1 in Conversation 2 (3rd evidence item across 2nd conversation)
    m3_id = "ms_s4_u3"
    conv_repo.append_message(
        MessageDraft(conversation_id=cid2, role=MessageRole.USER, content="Quiet hotels only.", source=MessageSource.UI, created_at=MOMENT),
        message_id=m3_id, owner_user_id=OWNER, outbox_event={"event_type": MEMORY_EXTRACT_EVENT_TYPE, "payload": {"conversation_id": cid2}},
    )
    e3 = next(e for e in outbox_repo.claim_batch("test_worker_s4", 30.0, 10) if e.message_id == m3_id)
    record_source_handling(clean, OWNER, SourceHandlingRecord(
        source_outbox_id=e3.outbox_id, source_message_id=m3_id,
        family=MemoryFamily.SEMANTIC, outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE, recorded_at=MOMENT,
    ))
    worker.process_one(e3)

    # Verified: now 3 evidence items across 2 conversations -> ACTIVE!
    with clean.connect() as conn:
        set_tenant(conn, OWNER)
        row = conn.execute(
            sa.text(
                "SELECT v.status, a.scope, a.scope_id "
                "FROM memory_versions v "
                "JOIN memory_assertions a ON v.assertion_id = a.assertion_id "
                "WHERE v.owner_user_id = :owner AND v.status = 'active'"
            ),
            {"owner": OWNER},
        ).fetchone()
        assert row is not None
        assert row[0] == "active"
        assert row[1] == "user"
        assert row[2] == OWNER


def test_stage4_post_forget_resurrection_fails_closed(clean):
    """A revoked or unresolved conflict assertion cannot be resurrected by background inference."""
    aid = "ast_stage4_conflict"

    cand = MemoryCandidate(
        candidate_id="mc_s4_resurrect",
        evidence_ids=("mev_s4_r1",),
        owner_user_id=OWNER,
        scope=MemoryScope.USER,
        conversation_id="cv_resurrect",
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        display_text="prefers quiet hotels",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=MOMENT,
        confidence=0.95,
    )
    ident = assertion_identity(cand)

    with clean.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO memory_assertions "
                "(assertion_id, owner_user_id, scope, scope_id, canonical_key, "
                "subject_key, condition_fingerprint, has_unresolved_conflict, created_at, updated_at) "
                "VALUES (:aid, :owner, :scope, :scope_id, :ck, :sk, :fp, true, :now, :now)"
            ),
            {
                "aid": aid,
                "owner": OWNER,
                "scope": ident.scope.value,
                "scope_id": ident.scope_id,
                "ck": ident.canonical_key,
                "sk": ident.subject_key,
                "fp": ident.condition_fingerprint,
                "now": MOMENT,
            },
        )

    recorder = BackgroundMemoryRecorder(
        uow_factory=lambda: PostgresMemoryUnitOfWork(clean),
        inferred_activation_enabled=True,
        type_evaluation_gate=_evaluated_gate,
    )

    # The positive source-handling precondition, stated explicitly. The gate
    # refuses an absent record (`UNHANDLED` grants nothing, `ADR 0038:59`), so a
    # test that omits it measures the gate rather than the behaviour it means to
    # assert.
    from backend.memory.source_handling import (
        MemoryFamily,
        SourceHandlingOutcome,
        SourceHandlingReason,
        SourceHandlingRecord,
    )

    positive_handling = SourceHandlingRecord(
        source_outbox_id="cout_resurrect",
        source_message_id="ms_resurrect",
        family=MemoryFamily.SEMANTIC,
        outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
        recorded_at=MOMENT,
    )

    res = recorder._prepare_core(
        cand,
        source_outbox_id="cout_resurrect",
        source_message_id="ms_resurrect",
        source_handling_record=positive_handling,
    )

    assert res.target_status == VersionStatus.SHADOW
    assert "unresolved_conflict" in res.reason

    with clean.connect() as conn:
        set_tenant(conn, OWNER)
        v_count = conn.scalar(
            sa.text(
                "SELECT count(*) FROM memory_versions WHERE owner_user_id = :owner AND status = 'active'"
            ),
            {"owner": OWNER},
        )
        assert v_count == 0


def test_stage4_outbox_maintenance_bounds_outbox_without_deleting_canonical_memory(clean):
    """Worker maintenance pass prunes expired pending projection outbox events in bounded batches without deleting canonical memory."""
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(days=45)

    # 1. Insert 10 eligible stale pending projection events (memory.write.committed, pending, 45 days old)
    with clean.begin() as conn:
        for i in range(10):
            conn.execute(
                sa.text(
                    "INSERT INTO memory_outbox "
                    "(outbox_id, owner_user_id, event_type, payload, status, created_at) "
                    "VALUES (:oid, :owner, 'memory.write.committed', '{}', 'pending', :created_at)"
                ),
                {"oid": f"outbox_proj_stale_{i}", "owner": OWNER, "created_at": old_time},
            )

        # 2. Insert 3 non-stale pending projection events (only 5 days old)
        for i in range(3):
            conn.execute(
                sa.text(
                    "INSERT INTO memory_outbox "
                    "(outbox_id, owner_user_id, event_type, payload, status, created_at) "
                    "VALUES (:oid, :owner, 'memory.write.committed', '{}', 'pending', :created_at)"
                ),
                {"oid": f"outbox_proj_recent_{i}", "owner": OWNER, "created_at": now - timedelta(days=5)},
            )

        # 3. Insert 3 stale SUCCEEDED projection events (status succeeded, must NOT be deleted by maintenance)
        for i in range(3):
            conn.execute(
                sa.text(
                    "INSERT INTO memory_outbox "
                    "(outbox_id, owner_user_id, event_type, payload, status, created_at) "
                    "VALUES (:oid, :owner, 'memory.write.committed', '{}', 'succeeded', :created_at)"
                ),
                {"oid": f"outbox_proj_succeeded_{i}", "owner": OWNER, "created_at": old_time},
            )

        # 4. Insert 3 stale conversation extraction events (different event_type, must NOT be deleted by maintenance)
        for i in range(3):
            conn.execute(
                sa.text(
                    "INSERT INTO memory_outbox "
                    "(outbox_id, owner_user_id, event_type, payload, status, created_at) "
                    "VALUES (:oid, :owner, 'memory.extract.conversation_range', '{}', 'pending', :created_at)"
                ),
                {"oid": f"outbox_extract_stale_{i}", "owner": OWNER, "created_at": old_time},
            )

        # 5. Insert canonical memory rows
        conn.execute(
            sa.text(
                "INSERT INTO memory_assertions "
                "(assertion_id, owner_user_id, scope, scope_id, canonical_key, subject_key, condition_fingerprint, created_at, updated_at) "
                "VALUES ('ast_canonical', :owner, 'user', 'global', 'travel.preference.hotel_atmosphere', 'self', '', :now, :now)"
            ),
            {"owner": OWNER, "now": now},
        )
        conn.execute(
            sa.text(
                "INSERT INTO memory_versions "
                "(version_id, assertion_id, owner_user_id, normalized_value, value_payload, authority, sensitivity, status, valid_from, retention_mode, created_at) "
                "VALUES ('ver_canonical', 'ast_canonical', :owner, 'quiet', '{\"normalized_value\": \"quiet\", \"display_text\": \"quiet\"}', 'repeated_inference', 'ordinary_personal', 'active', :now, 'user_durable', :now)"
            ),
            {"owner": OWNER, "now": now},
        )
        conn.execute(
            sa.text(
                "INSERT INTO memory_evidence "
                "(evidence_id, assertion_id, owner_user_id, conversation_id, source_message_id, display_text, authority, observed_at, created_at) "
                "VALUES ('ev_canonical', 'ast_canonical', :owner, 'cv_1', 'ms_1', 'quiet hotels', 'repeated_inference', :now, :now)"
            ),
            {"owner": OWNER, "now": now},
        )
        conn.execute(
            sa.text(
                "INSERT INTO memory_decisions "
                "(decision_id, candidate_id, assertion_id, owner_user_id, outcome, reason, decided_at, created_at) "
                "VALUES ('dec_canonical', 'cand_1', 'ast_canonical', :owner, 'shadow', 'valid', :now, :now)"
            ),
            {"owner": OWNER, "now": now},
        )

    uow = PostgresMemoryUnitOfWork(clean)
    worker = MemoryOutboxWorker(
        outbox_repo=PostgresOutboxRepository(clean),
        model_adapter=DeterministicModel(),
        conversation_service=ConversationService(PostgresConversationRepository(clean)),
        recorder=BackgroundMemoryRecorder(uow_factory=lambda: uow),
        worker_id="test_maint_worker",
        source_handling_loader=_source_handling_loader(clean),
        maintenance_cleaner=lambda cutoff, batch_size: uow.prune_projection_outbox(
            retention_cutoff=cutoff, batch_size=batch_size
        ),
        retention_days=30,
        cleanup_batch_size=6,  # Bounded to 6
    )

    # First maintenance pass: bounds prune to 6 rows
    pruned1 = worker.run_maintenance_pass()
    assert pruned1 == 6

    # Second maintenance pass: prunes the remaining 4 rows
    pruned2 = worker.run_maintenance_pass()
    assert pruned2 == 4

    # Third pass: nothing left to prune
    pruned3 = worker.run_maintenance_pass()
    assert pruned3 == 0

    # Verify:
    # 1. Non-matching outbox rows (3 recent pending, 3 succeeded, 3 extract) remain
    with clean.connect() as conn:
        remaining_outbox = conn.scalar(sa.text("SELECT count(*) FROM memory_outbox"))
        assert remaining_outbox == 9  # 3 + 3 + 3

        # 2. Canonical memory rows must NEVER be deleted by maintenance!
        assert conn.scalar(sa.text("SELECT count(*) FROM memory_assertions WHERE assertion_id = 'ast_canonical'")) == 1
        assert conn.scalar(sa.text("SELECT count(*) FROM memory_versions WHERE version_id = 'ver_canonical'")) == 1
        assert conn.scalar(sa.text("SELECT count(*) FROM memory_evidence WHERE evidence_id = 'ev_canonical'")) == 1
        assert conn.scalar(sa.text("SELECT count(*) FROM memory_decisions WHERE decision_id = 'dec_canonical'")) == 1
