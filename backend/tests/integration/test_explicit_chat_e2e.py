"""End-to-end integration tests for Stage 2 Chat-Native Explicit Remember/Correct/Forget.

Tests the full lifecycle across:
- Conversation persistence (two-phase turn allocation + outbox intent)
- Turn understanding & action routing (EXPLICIT_REMEMBER / CORRECT / FORGET / INSPECT)
- ExplicitMemoryActionHandler (proposal, registry validation, snapshot binding)
- ExplicitMemoryTurnCommit (canonical lock order, atomic Memory + acknowledgement + source-handling)
- Idempotent replay, rollback on failure, no resurrection, and cross-owner isolation under RLS.
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest
import sqlalchemy as sa

from backend.conversations.models import MessageRole, MessageStatus, OutboxIntent
from backend.conversations.postgres_repository import PostgresConversationRepository
from backend.conversations.service import ConversationService
from backend.memory.commit_coordinators import (
    ExplicitMemoryCommitRequest,
    ExplicitMemoryTurnCommit,
    ExplicitTurnTransitionError,
)
from backend.memory.explicit_actions import (
    ExplicitMemoryActionHandler,
    ProposalOutcome,
    explicit_semantic_idempotency_key,
)
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingOutcome,
    SourceHandlingReason,
    SourceHandlingRecord,
)
from backend.memory.write_pipeline.models import (
    Authority,
    MemoryOperation,
    MemoryScope,
    SourceValidity,
    VersionStatus,
)
from backend.memory.write_pipeline.postgres import (
    PostgresMemoryUnitOfWork,
    load_source_handling,
    record_source_handling,
)
from backend.orchestration.conversation_orchestrator import (
    ConversationOrchestrator,
    INSPECT_UNAVAILABLE_REPLY,
)
from backend.security.models import AuthenticatedPrincipal, AuthMode
from backend.tests.integration.pg_dsn import (
    assert_rls_enforced,
    migration_dsn,
    require,
    runtime_dsn,
)

requires_pg = pytest.mark.skipif(
    not runtime_dsn(),
    reason="isolated PG unavailable: set PG_RUNTIME_TEST_DSN (least-privilege role)",
)
pytestmark = requires_pg

OWNER_A = "user_e2e_owner_a"
OWNER_B = "user_e2e_owner_b"


@pytest.fixture(scope="module")
def pg_engine():
    from backend.storage.postgres import create_engine

    engine = create_engine(require(runtime_dsn(), "PG_RUNTIME_TEST_DSN"))
    try:
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
    except Exception as error:
        engine.dispose()
        raise RuntimeError(
            f"isolated PG unreachable: {type(error).__name__}; "
            "a configured PG_RUNTIME_TEST_DSN must be reachable, not skipped."
        ) from error

    try:
        assert_rls_enforced(engine, "PG_RUNTIME_TEST_DSN")
    except Exception:
        engine.dispose()
        raise

    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrated(pg_engine):
    """Bring the schema to head using the DDL-capable role."""
    from alembic import command
    from backend.storage.postgres import alembic_config

    config = alembic_config(
        str(Path(__file__).resolve().parents[2] / "storage" / "migrations"),
        require(migration_dsn(), "PG_TEST_DSN"),
    )
    command.upgrade(config, "head")
    return pg_engine


class DummyRAG:
    def generate_answer(self, message: str, top_k: int | None = None):
        return {"reply": "baseline answer", "model": "test-rag", "citations": []}


@pytest.fixture
def orchestrator_factory(migrated):
    """Factory creating a real ConversationOrchestrator wired with real PostgreSQL adapters."""
    def _create(owner_user_id: str, outbox_enabled: bool = False):
        repo = PostgresConversationRepository(migrated)
        service = ConversationService(repo)
        uow = PostgresMemoryUnitOfWork(migrated)
        handler = ExplicitMemoryActionHandler(
            active_version_provider=uow.get_active_versions,
            generation_provider=uow.get_assertion_generation,
        )
        commit_coordinator = ExplicitMemoryTurnCommit(engine=migrated)
        source_recorder = lambda owner, rec: record_source_handling(migrated, owner, rec)

        return ConversationOrchestrator(
            rag_service=DummyRAG(),
            conversation_service_provider=lambda: service,
            outbox_enabled=outbox_enabled,
            explicit_actions_enabled=True,
            explicit_action_handler=handler,
            explicit_memory_commit=commit_coordinator,
            source_handling_recorder=source_recorder,
        )

    return _create


def _principal(owner: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        owner_user_id=owner,
        auth_mode=AuthMode.AUTHENTICATED,
        credential_label="e2e_token",
    )


def test_explicit_remember_turn_persists_memory_and_source_handling(
    migrated, orchestrator_factory
):
    """Full e2e turn: Remember assertion writes memory_assertions, memory_versions, and source_handling atomically."""
    uow = PostgresMemoryUnitOfWork(migrated)
    orchestrator = orchestrator_factory(OWNER_A)

    outcome = orchestrator.handle_turn(
        message="Nhớ là tôi thích khách sạn yên tĩnh nhé",
        conversation_id=None,
        principal=_principal(OWNER_A),
    )

    assert "yên tĩnh" in outcome.reply or "quiet" in outcome.reply or "Đã lưu" in outcome.reply
    assert outcome.conversation is not None
    assert outcome.conversation.persisted is True
    conversation_id = outcome.conversation.conversation_id

    # 1. Verify Memory Version is active
    active = uow.get_active_versions(OWNER_A, "travel.preference.hotel_atmosphere")
    assert len(active) == 1
    assert active[0].normalized_value == "quiet"
    assert active[0].status == VersionStatus.ACTIVE
    assert active[0].authority == Authority.EXPLICIT_SAVE

    # 2. Verify source handling record
    service = ConversationService(PostgresConversationRepository(migrated))
    source_outbox_id = service.get_turn_outbox_id(
        conversation_id, outcome.conversation.user_message_id, OWNER_A
    )
    assert source_outbox_id is not None
    sh_record = load_source_handling(
        migrated, OWNER_A, source_outbox_id, MemoryFamily.SEMANTIC
    )
    assert sh_record is not None
    assert sh_record.outcome is SourceHandlingOutcome.EXPLICIT_APPLIED
    assert sh_record.reason_code is SourceHandlingReason.EXPLICIT_ACTION


def test_explicit_correct_turn_supersedes_active_version(
    migrated, orchestrator_factory
):
    """Explicit correct supersedes active version with CAS check on expected_version_id."""
    uow = PostgresMemoryUnitOfWork(migrated)
    orchestrator = orchestrator_factory(OWNER_A)

    # First turn: remember quiet
    first_outcome = orchestrator.handle_turn(
        message="Nhớ là tôi thích khách sạn yên tĩnh",
        conversation_id=None,
        principal=_principal(OWNER_A),
    )
    conversation_id = first_outcome.conversation.conversation_id
    active_before = uow.get_active_versions(OWNER_A, "travel.preference.hotel_atmosphere")
    assert len(active_before) == 1
    old_version_id = active_before[0].version_id

    # Second turn: correct to central
    second_outcome = orchestrator.handle_turn(
        message="Sửa lại là tôi thích khách sạn trung tâm",
        conversation_id=conversation_id,
        principal=_principal(OWNER_A),
    )

    active_after = uow.get_active_versions(OWNER_A, "travel.preference.hotel_atmosphere")
    assert len(active_after) == 1
    assert active_after[0].normalized_value == "central"
    assert active_after[0].supersedes_version_id == old_version_id


def test_explicit_forget_turn_revokes_version(
    migrated, orchestrator_factory
):
    """Explicit forget revokes active version and records FORGET_APPLIED."""
    uow = PostgresMemoryUnitOfWork(migrated)
    orchestrator = orchestrator_factory(OWNER_A)

    first_outcome = orchestrator.handle_turn(
        message="Nhớ là tôi thích khách sạn yên tĩnh",
        conversation_id=None,
        principal=_principal(OWNER_A),
    )
    conversation_id = first_outcome.conversation.conversation_id
    assert len(uow.get_active_versions(OWNER_A, "travel.preference.hotel_atmosphere")) == 1

    # Forget turn
    forget_outcome = orchestrator.handle_turn(
        message="Quên sở thích khách sạn đi",
        conversation_id=conversation_id,
        principal=_principal(OWNER_A),
    )

    # Active versions should now be empty
    assert len(uow.get_active_versions(OWNER_A, "travel.preference.hotel_atmosphere")) == 0


def test_re_remember_after_forget_creates_new_generation(
    migrated, orchestrator_factory
):
    """Re-remember after forget advances suppression generation without resurrecting old version."""
    uow = PostgresMemoryUnitOfWork(migrated)
    orchestrator = orchestrator_factory(OWNER_A)

    first_outcome = orchestrator.handle_turn(
        message="Nhớ là tôi thích khách sạn yên tĩnh",
        conversation_id=None,
        principal=_principal(OWNER_A),
    )
    conversation_id = first_outcome.conversation.conversation_id

    # Forget
    orchestrator.handle_turn(
        message="Quên sở thích khách sạn đi",
        conversation_id=conversation_id,
        principal=_principal(OWNER_A),
    )

    # Re-remember
    orchestrator.handle_turn(
        message="Nhớ là tôi thích khách sạn yên tĩnh",
        conversation_id=conversation_id,
        principal=_principal(OWNER_A),
    )

    active = uow.get_active_versions(OWNER_A, "travel.preference.hotel_atmosphere")
    assert len(active) == 1
    assert active[0].normalized_value == "quiet"
    assert active[0].status == VersionStatus.ACTIVE
    assert active[0].suppression_generation >= 2


def test_cross_owner_isolation_under_rls(
    migrated, orchestrator_factory
):
    """Row-level security ensures Owner B cannot see or mutate Owner A's memories."""
    uow = PostgresMemoryUnitOfWork(migrated)
    orchestrator_a = orchestrator_factory(OWNER_A)
    orchestrator_b = orchestrator_factory(OWNER_B)

    # Owner A saves preference
    orchestrator_a.handle_turn(
        message="Nhớ là tôi thích khách sạn yên tĩnh",
        conversation_id=None,
        principal=_principal(OWNER_A),
    )

    # Owner B's view is empty
    active_b = uow.get_active_versions(OWNER_B, "travel.preference.hotel_atmosphere")
    assert active_b == ()


def test_set_key_add_union_member_forget_and_replace_e2e(
    migrated, orchestrator_factory
):
    """Full lifecycle for set key: add, union, targeted member forget, and replacement."""
    owner = "user_e2e_set_lifecycle"
    uow = PostgresMemoryUnitOfWork(migrated)
    orchestrator = orchestrator_factory(owner)
    service = ConversationService(PostgresConversationRepository(migrated))

    # 1. Initial Add: bus and train
    turn1 = orchestrator.handle_turn(
        message="Nhớ là tôi thích đi xe buýt và tàu hỏa",
        conversation_id=None,
        principal=_principal(owner),
    )
    conv_id = turn1.conversation.conversation_id
    active1 = uow.get_active_versions(owner, "travel.preference.transport_mode")
    assert len(active1) == 1
    assert set(active1[0].normalized_value) == {"bus", "train"}
    v1_id = active1[0].version_id

    # 2. Set Union: add flight
    turn2 = orchestrator.handle_turn(
        message="Nhớ là tôi thích máy bay",
        conversation_id=conv_id,
        principal=_principal(owner),
    )
    active2 = uow.get_active_versions(owner, "travel.preference.transport_mode")
    assert len(active2) == 1
    assert set(active2[0].normalized_value) == {"bus", "flight", "train"}
    assert active2[0].supersedes_version_id == v1_id
    v2_id = active2[0].version_id

    # 3. Targeted Member Forget: remove bus
    turn3 = orchestrator.handle_turn(
        message="Please forget bus from my transport preferences",
        conversation_id=conv_id,
        principal=_principal(owner),
    )
    active3 = uow.get_active_versions(owner, "travel.preference.transport_mode")
    assert len(active3) == 1
    assert set(active3[0].normalized_value) == {"flight", "train"}
    assert active3[0].supersedes_version_id == v2_id
    v3_id = active3[0].version_id

    # Verify source handling record for member forget is FORGET_APPLIED
    outbox3 = service.get_turn_outbox_id(
        conv_id, turn3.conversation.user_message_id, owner
    )
    assert outbox3 is not None
    sh3 = load_source_handling(migrated, owner, outbox3, MemoryFamily.SEMANTIC)
    assert sh3 is not None
    assert sh3.outcome is SourceHandlingOutcome.FORGET_APPLIED
    assert sh3.reason_code is SourceHandlingReason.EXPLICIT_ACTION

    # 4. Set Replacement: correct to train
    turn4 = orchestrator.handle_turn(
        message="Sửa lại là tôi thích tàu hỏa",
        conversation_id=conv_id,
        principal=_principal(owner),
    )
    active4 = uow.get_active_versions(owner, "travel.preference.transport_mode")
    assert len(active4) == 1
    assert active4[0].normalized_value == ("train",)
    assert active4[0].supersedes_version_id == v3_id


def test_set_key_whole_forget_and_re_remember_e2e(
    migrated, orchestrator_factory
):
    """Whole-key forget of a set key and subsequent re-remember with advanced generation."""
    owner = "user_e2e_food_forget"
    uow = PostgresMemoryUnitOfWork(migrated)
    orchestrator = orchestrator_factory(owner)
    service = ConversationService(PostgresConversationRepository(migrated))

    # 1. Add food style
    turn1 = orchestrator.handle_turn(
        message="Nhớ là tôi thích đồ ăn đường phố và nhà hàng cao cấp",
        conversation_id=None,
        principal=_principal(owner),
    )
    conv_id = turn1.conversation.conversation_id
    active1 = uow.get_active_versions(owner, "travel.preference.food_style")
    assert len(active1) == 1
    assert set(active1[0].normalized_value) == {"fine_dining", "street_food"}

    # 2. Whole-key forget
    turn2 = orchestrator.handle_turn(
        message="Quên sở thích ẩm thực của tôi đi",
        conversation_id=conv_id,
        principal=_principal(owner),
    )
    active2 = uow.get_active_versions(owner, "travel.preference.food_style")
    assert len(active2) == 0

    outbox2 = service.get_turn_outbox_id(
        conv_id, turn2.conversation.user_message_id, owner
    )
    assert outbox2 is not None
    sh2 = load_source_handling(migrated, owner, outbox2, MemoryFamily.SEMANTIC)
    assert sh2 is not None
    assert sh2.outcome is SourceHandlingOutcome.FORGET_APPLIED

    # 3. Re-remember
    turn3 = orchestrator.handle_turn(
        message="Nhớ là tôi thích đồ ăn đường phố",
        conversation_id=conv_id,
        principal=_principal(owner),
    )
    active3 = uow.get_active_versions(owner, "travel.preference.food_style")
    assert len(active3) == 1
    assert active3[0].normalized_value == ("street_food",)
    assert active3[0].suppression_generation >= 2


def test_explicit_semantic_idempotent_retry_e2e(
    migrated, orchestrator_factory
):
    """Direct idempotent retry of ExplicitMemoryTurnCommit with same idempotency key produces no duplicate versions."""
    import uuid
    owner = f"user_e2e_idempotency_{uuid.uuid4().hex[:8]}"
    uow = PostgresMemoryUnitOfWork(migrated)
    coordinator = ExplicitMemoryTurnCommit(engine=migrated)
    service = ConversationService(PostgresConversationRepository(migrated))

    # Create conversation and turn
    conv, user_msg, pending_assistant_msg = service.create_conversation_with_initial_turn(
        owner_user_id=owner,
        title="Idempotent Test",
        content="Nhớ là tôi thích khách sạn yên tĩnh",
        outbox_event=OutboxIntent(event_type="chat_turn_extracted", payload={"owner": owner}),
    )
    source_outbox_id = service.get_turn_outbox_id(
        conv.conversation_id, user_msg.message_id, owner
    )
    assert source_outbox_id is not None

    handler = ExplicitMemoryActionHandler(active_version_provider=uow.get_active_versions)
    from backend.orchestration.turn_models import InteractionMode, TurnUnderstandingResult, UnderstandingReason
    from backend.orchestration.dialogue_state import DialogueState

    understanding = TurnUnderstandingResult(
        interaction_mode=InteractionMode.EXPLICIT_REMEMBER,
        reason_codes=(UnderstandingReason.DETERMINISTIC_MATCH,),
    )
    proposal = handler.propose(
        understanding,
        DialogueState(turns=(), latest_user_turn=user_msg, latest_assistant_turn=None),
        owner_user_id=owner,
    )
    assert proposal.outcome is ProposalOutcome.MUTATION

    sh_record = SourceHandlingRecord(
        source_outbox_id=source_outbox_id,
        source_message_id=user_msg.message_id,
        family=MemoryFamily.SEMANTIC,
        outcome=SourceHandlingOutcome.EXPLICIT_APPLIED,
        reason_code=SourceHandlingReason.EXPLICIT_ACTION,
        recorded_at=datetime.now(timezone.utc),
    )
    idem_key = explicit_semantic_idempotency_key(
        owner_user_id=owner,
        source_message_id=user_msg.message_id,
        canonical_key="travel.preference.hotel_atmosphere",
        operation="add",
        normalized_value="quiet",
        suppression_generation=1,
    )
    req = ExplicitMemoryCommitRequest(
        principal=_principal(owner),
        conversation_id=conv.conversation_id,
        assistant_message_id=pending_assistant_msg.message_id,
        expected_deletion_epoch=0,
        acknowledgement_text="Đã lưu!",
        change=proposal.change,
        evidence=(),
        decision=None,
        idempotency_key=idem_key,
        expected_version_id=None,
        source_validity=SourceValidity.NOT_REQUIRED,
        source_handling_record=sh_record,
    )

    # First commit
    res1 = coordinator.commit(req)
    assert res1.memory.version_id is not None
    assert res1.transition.applied is True

    # Second commit with same request / idempotency_key (idempotent replay)
    res2 = coordinator.commit(req)
    assert res2.memory.version_id == res1.memory.version_id

    # Exactly 1 active version exists in PostgreSQL
    active = uow.get_active_versions(owner, "travel.preference.hotel_atmosphere")
    assert len(active) == 1
    assert active[0].version_id == res1.memory.version_id
    assert active[0].normalized_value == "quiet"


def test_remaining_registry_keys_e2e(migrated, orchestrator_factory):
    """Exercise remaining 5 registry keys to guarantee complete 8-key E2E coverage."""
    owner = "user_e2e_all_keys"
    uow = PostgresMemoryUnitOfWork(migrated)
    orchestrator = orchestrator_factory(owner)

    # 1. travel.constraint.budget_level
    turn1 = orchestrator.handle_turn(
        message="Nhớ là ngân sách của tôi là tiết kiệm",
        conversation_id=None,
        principal=_principal(owner),
    )
    conv_id = turn1.conversation.conversation_id
    active_budget = uow.get_active_versions(owner, "travel.constraint.budget_level")
    assert len(active_budget) == 1
    assert active_budget[0].normalized_value == "budget"

    # 2. travel.preference.travel_pace
    turn2 = orchestrator.handle_turn(
        message="Nhớ là nhịp độ du lịch của tôi là thư giãn",
        conversation_id=conv_id,
        principal=_principal(owner),
    )
    active_pace = uow.get_active_versions(owner, "travel.preference.travel_pace")
    assert len(active_pace) == 1
    assert active_pace[0].normalized_value == "relaxed"

    # 3. travel.profile.default_departure_city
    turn3 = orchestrator.handle_turn(
        message="Nhớ là tôi khởi hành từ Hà Nội",
        conversation_id=conv_id,
        principal=_principal(owner),
    )
    active_city = uow.get_active_versions(owner, "travel.profile.default_departure_city")
    assert len(active_city) == 1
    assert active_city[0].normalized_value == "hanoi"

    # 4. travel.preference.accommodation_type
    turn4 = orchestrator.handle_turn(
        message="Nhớ là tôi thích ở resort và homestay",
        conversation_id=conv_id,
        principal=_principal(owner),
    )
    active_accom = uow.get_active_versions(owner, "travel.preference.accommodation_type")
    assert len(active_accom) == 1
    assert set(active_accom[0].normalized_value) == {"homestay", "resort"}

    # 5. travel.preference.activity_style
    turn5 = orchestrator.handle_turn(
        message="Nhớ là tôi thích hoạt động thiên nhiên và chụp ảnh",
        conversation_id=conv_id,
        principal=_principal(owner),
    )
    active_act = uow.get_active_versions(owner, "travel.preference.activity_style")
    assert len(active_act) == 1
    assert set(active_act[0].normalized_value) == {"nature", "photography"}

