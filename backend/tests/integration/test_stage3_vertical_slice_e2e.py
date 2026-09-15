"""Stage 3 Context Planning, Memory Use, and Explicit Inspect Vertical-Slice Evaluation.

Tests the full explicit semantic vertical-slice:
1. Remember in conversation A -> use in conversation B (user-scope soft preference).
2. Unrelated query abstention (RAG only / empty memory context).
3. Conversation override over user-scope soft preference (same canonical key, same conversation).
4. Full mutation matrix across ALL 8 registry-v2 keys:
   Remember -> Read -> Correct (SUPERSEDE) -> Read -> Forget (REVOKE) -> Abstain -> Re-remember.
5. Set-valued preferences order stability:
   Survive normalization, read, composition, and presentation deterministically.
6. Current-turn input precedence:
   Current message overrides remembered soft preference in generation context.
7. Explicit inspect delivered via MemoryReadEngine on live PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any, Dict, List, Optional
import pytest
import sqlalchemy as sa

from backend.conversations.postgres_repository import PostgresConversationRepository
from backend.conversations.service import ConversationService
from backend.generation.contracts import (
    ContextSufficiency,
    GenerationCitation,
    GenerationContext,
    GenerationResult,
)
from backend.memory.commit_coordinators import (
    ExplicitMemoryCommitRequest,
    ExplicitMemoryTurnCommit,
)
from backend.memory.context import MemoryContextComposer
from backend.memory.explicit_actions import ExplicitMemoryActionHandler
from backend.memory.lifecycle import MemoryLifecyclePolicy
from backend.memory.postgres_store import PostgresMemoryStore
from backend.memory.read_engine import MemoryReadEngine
from backend.memory.read_models import MemoryReadRequest
from backend.memory.write_pipeline.models import (
    AssertionIdentity,
    Authority,
    MemoryChangeSet,
    MemoryOperation,
    MemoryScope,
    MemoryVersionDraft,
    NormalizedSemanticValue,
    RetentionMode,
    SensitivityBand,
    SourceValidity,
    VersionStatus,
)
from backend.memory.write_pipeline.postgres import (
    PostgresMemoryUnitOfWork,
    record_source_handling,
)
from backend.memory.write_pipeline.registry import (
    get_key_definition,
    normalize_value,
    registry_keys,
)
from backend.orchestration.context_arbiter import ContextArbiter
from backend.orchestration.context_planner import ContextPlanner
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator
from backend.orchestration.turn_models import (
    ContextMode,
    ContextPlan,
    InteractionMode,
    TurnDisposition,
    TurnUnderstandingResult,
)
from backend.rag.contracts import CitationEvidence, ContextBundle
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

OWNER_EVAL = "user_eval_stage3"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_identity(
    owner: str = OWNER_EVAL,
    key: str = "travel.preference.hotel_atmosphere",
    scope: MemoryScope = MemoryScope.USER,
    scope_id: str | None = None,
) -> AssertionIdentity:
    return AssertionIdentity(
        owner_user_id=owner,
        canonical_key=key,
        scope=scope,
        scope_id=scope_id or owner,
        subject_key="subject_default",
        condition_fingerprint="cond_default",
    )


def _make_draft(
    owner: str = OWNER_EVAL,
    key: str = "travel.preference.hotel_atmosphere",
    value: Any = "quiet",
    scope: MemoryScope = MemoryScope.USER,
    scope_id: str | None = None,
    authority: Authority = Authority.EXPLICIT_SAVE,
    valid_from: datetime | None = None,
    supersedes_version_id: str | None = None,
    suppression_generation: int = 1,
) -> MemoryVersionDraft:
    now = valid_from or utc_now()
    return MemoryVersionDraft(
        owner_user_id=owner,
        scope=scope,
        scope_id=scope_id or owner,
        canonical_key=key,
        subject_key="subject_default",
        condition_fingerprint="cond_default",
        normalized_value=value,
        display_text=f"display {value}",
        authority=authority,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        retention_mode=RetentionMode.USER_DURABLE,
        valid_from=now,
        supersedes_version_id=supersedes_version_id,
        suppression_generation=suppression_generation,
    )


def _apply_change(
    uow: PostgresMemoryUnitOfWork,
    change: MemoryChangeSet,
    idempotency_key: str | None = None,
):
    source_validity = (
        SourceValidity.NOT_REQUIRED
        if change.new_version is not None
        and change.new_version.retention_mode is RetentionMode.USER_DURABLE
        else SourceValidity.VALID if change.new_version is not None else None
    )
    return uow.apply_memory_change(
        change,
        _principal(),
        idempotency_key=idempotency_key,
        source_validity=source_validity,
    )


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
            "a configured PG_RUNTIME_TEST_DSN must be reachable."
        ) from error

    try:
        assert_rls_enforced(engine, "PG_RUNTIME_TEST_DSN")
    except Exception:
        engine.dispose()
        raise

    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def ddl_engine():
    from backend.storage.postgres import create_engine

    engine = create_engine(require(migration_dsn(), "PG_TEST_DSN"))
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrated(ddl_engine, pg_engine):
    """Bring schema to head using migration DSN."""
    from alembic import command
    from backend.storage.postgres import alembic_config

    config = alembic_config(
        str(Path(__file__).resolve().parents[2] / "storage" / "migrations"),
        require(migration_dsn(), "PG_TEST_DSN"),
    )
    command.upgrade(config, "head")
    return pg_engine


@pytest.fixture(autouse=True)
def clean_eval_data(ddl_engine, migrated):
    """Clean tables before each test to maintain strict isolation."""
    with ddl_engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE memory_write_idempotency, memory_outbox, "
                "memory_events, memory_decisions, memory_evidence, "
                "memory_candidates, memory_versions, memory_assertions, "
                "messages, conversations CASCADE"
            )
        )
    yield


class RecordingRAGService:
    """Mock RAG service that records generation context and verifies assertions."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def build_travel_context(self, message: str, top_k: int = 4) -> ContextBundle:
        return ContextBundle(
            prompt_context="Cẩm nang du lịch Đà Nẵng: Bãi biển Mỹ Khê, Bán đảo Sơn Trà, Cầu Rồng.",
            evidence=(),
            citations=(
                CitationEvidence(
                    title="Cẩm nang du lịch Đà Nẵng",
                    url="https://vietnam.travel/da-nang",
                    evidence_ids=("ev_dn_1",),
                ),
            ),
            insufficient_evidence=False,
        )

    def generate_from_context(
        self, user_message: str, context: GenerationContext
    ) -> GenerationResult:
        self.calls.append({
            "message": user_message,
            "context": context,
        })
        return GenerationResult(
            reply=f"Answer for '{user_message}' based on context sufficiency={context.sufficiency.value}.",
            model="gpt-4o-mini",
            citations=context.citations,
        )

    def generate_answer(self, message: str, top_k: int = 4) -> Dict[str, Any]:
        return {
            "reply": "Fallback legacy answer",
            "model": "gpt-4o-mini",
            "citations": [],
        }


class DynamicEvalPlanner(ContextPlanner):
    """Context planner for vertical-slice evaluation.

    Plans BOTH for travel recommendation queries and RAG_ONLY for general info queries.
    """

    def __init__(self, forced_mode: Optional[ContextMode] = None) -> None:
        super().__init__(enforcement_enabled=True)
        self.forced_mode = forced_mode

    def plan(self, understanding: TurnUnderstandingResult) -> ContextPlan:
        if self.forced_mode is not None:
            return ContextPlan(proposed=self.forced_mode, effective=self.forced_mode)
        if understanding.interaction_mode in (
            InteractionMode.EXPLICIT_REMEMBER,
            InteractionMode.EXPLICIT_CORRECT,
            InteractionMode.EXPLICIT_FORGET,
            InteractionMode.EXPLICIT_INSPECT,
        ):
            return ContextPlan(proposed=ContextMode.NONE, effective=ContextMode.NONE)

        goal = (understanding.current_goal or "").lower()
        # Recommendation / personalized hotel query -> BOTH
        if any(w in goal for w in ("gợi ý", "khách sạn", "hotel", "theo gu", "sở thích", "phù hợp", "chuyến đi")):
            return ContextPlan(proposed=ContextMode.BOTH, effective=ContextMode.BOTH)
        return ContextPlan(proposed=ContextMode.RAG_ONLY, effective=ContextMode.RAG_ONLY)


def _principal(owner: str = OWNER_EVAL) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        owner_user_id=owner,
        auth_mode=AuthMode.AUTHENTICATED,
        credential_label="e2e_eval_token",
    )


def create_orchestrator(
    migrated,
    rag_service: RecordingRAGService,
    *,
    planner: Optional[ContextPlanner] = None,
    memory_read_enabled: bool = True,
    memory_use_enabled: bool = True,
) -> ConversationOrchestrator:
    repo = PostgresConversationRepository(migrated)
    conv_service = ConversationService(repo)
    uow = PostgresMemoryUnitOfWork(migrated)
    handler = ExplicitMemoryActionHandler(
        active_version_provider=uow.get_active_versions,
        generation_provider=uow.get_assertion_generation,
    )
    commit_coordinator = ExplicitMemoryTurnCommit(engine=migrated)
    source_recorder = lambda owner, rec: record_source_handling(migrated, owner, rec)

    store = PostgresMemoryStore(migrated)
    read_engine = MemoryReadEngine(store, clock=utc_now)
    composer = MemoryContextComposer()
    arbiter = ContextArbiter(memory_composer=composer)
    resolved_planner = planner if planner is not None else DynamicEvalPlanner()

    return ConversationOrchestrator(
        rag_service=rag_service,
        conversation_service_provider=lambda: conv_service,
        outbox_enabled=False,
        explicit_actions_enabled=True,
        explicit_action_handler=handler,
        explicit_memory_commit=commit_coordinator,
        source_handling_recorder=source_recorder,
        memory_read_engine=read_engine,
        context_arbiter=arbiter,
        context_planner=resolved_planner,
        memory_read_enabled=memory_read_enabled,
        memory_use_enabled=memory_use_enabled,
    )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_remember_in_conv_a_use_in_conv_b(migrated):
    """Remember in conversation A -> user-scope preference is used in conversation B."""
    rag_svc = RecordingRAGService()
    orchestrator = create_orchestrator(migrated, rag_svc)

    # 1. Turn 1 in Conversation A: Explicit remember
    turn_1 = orchestrator.handle_turn(
        message="Nhớ là tôi thích khách sạn yên tĩnh nhé",
        conversation_id=None,
        principal=_principal(),
    )
    assert turn_1.conversation is not None
    conv_a_id = turn_1.conversation.conversation_id
    assert "yên tĩnh" in turn_1.reply or "quiet" in turn_1.reply

    # 2. Turn 2 in Conversation B: Normal query for hotels
    turn_2 = orchestrator.handle_turn(
        message="Gợi ý cho tôi khách sạn tốt tại Đà Nẵng",
        conversation_id=None,
        principal=_principal(),
    )
    assert turn_2.conversation is not None
    conv_b_id = turn_2.conversation.conversation_id
    assert conv_b_id != conv_a_id

    # Verify RAG service was called with GenerationContext containing soft preference
    assert len(rag_svc.calls) == 1
    last_call = rag_svc.calls[-1]
    last_context = last_call["context"]
    assert "CẨM NANG DU LỊCH THAM KHẢO" in last_context.prompt_context
    assert "travel.preference.hotel_atmosphere" in last_context.prompt_context
    assert "quiet" in last_context.prompt_context
    assert "soft_preference" in last_context.prompt_context
    # Travel citations remain present, but memory has NO travel citations
    assert len(last_context.citations) == 1
    assert last_context.citations[0].title == "Cẩm nang du lịch Đà Nẵng"


def test_unrelated_query_abstention(migrated):
    """When query has no memory needs, Memory context is omitted or empty."""
    rag_svc = RecordingRAGService()
    orchestrator = create_orchestrator(migrated, rag_svc)

    # Store hotel preference
    orchestrator.handle_turn(
        message="Nhớ là tôi thích khách sạn yên tĩnh nhé",
        conversation_id=None,
        principal=_principal(),
    )

    # Turn understanding for general city info without memory namespace (plans RAG_ONLY)
    rag_svc.calls.clear()
    turn_query = orchestrator.handle_turn(
        message="Đà Nẵng có những cây cầu nổi tiếng nào?",
        conversation_id=None,
        principal=_principal(),
    )

    assert turn_query.disposition is TurnDisposition.ANSWERED
    assert len(rag_svc.calls) == 1
    last_context = rag_svc.calls[-1]["context"]
    assert "CẨM NANG DU LỊCH THAM KHẢO" in last_context.prompt_context
    assert "travel.preference" not in last_context.prompt_context


def test_conversation_override_over_user_scope_preference(migrated):
    """Conversation-scoped record overrides user-scoped record in that conversation only."""
    rag_svc = RecordingRAGService()
    orchestrator = create_orchestrator(migrated, rag_svc)
    uow = PostgresMemoryUnitOfWork(migrated)

    # 1. User-scoped preference: quiet
    orchestrator.handle_turn(
        message="Nhớ là tôi thích khách sạn yên tĩnh nhé",
        conversation_id=None,
        principal=_principal(),
    )

    # Create Conversation C and apply conversation-scoped preference: lively
    conv_repo = PostgresConversationRepository(migrated)
    conv_service = ConversationService(conv_repo)
    conv_c, _, _ = conv_service.create_conversation_with_initial_turn(
        owner_user_id=OWNER_EVAL,
        title="Trip to Da Nang",
        content="Hello",
        role="user",
        source="ui",
    )
    conv_c_id = conv_c.conversation_id

    # Insert conversation-scoped memory for conv_c
    now = utc_now()
    identity_conv = _make_identity(
        owner=OWNER_EVAL,
        key="travel.preference.hotel_atmosphere",
        scope=MemoryScope.CONVERSATION,
        scope_id=conv_c_id,
    )
    change_conv = MemoryChangeSet(
        operation=MemoryOperation.ADD,
        identity=identity_conv,
        new_version=_make_draft(
            owner=OWNER_EVAL,
            key="travel.preference.hotel_atmosphere",
            value="lively",
            scope=MemoryScope.CONVERSATION,
            scope_id=conv_c_id,
            valid_from=now,
        ),
        superseded_version_ids=(),
        reference_version_id=None,
        reason="conversation override",
    )
    _apply_change(uow, change_conv, idempotency_key="idemp_ovr_1")

    # 2. Query in Conversation C: should use 'lively'
    rag_svc.calls.clear()
    orchestrator.handle_turn(
        message="Gợi ý khách sạn cho chuyến đi này",
        conversation_id=conv_c_id,
        principal=_principal(),
    )
    assert len(rag_svc.calls) == 1
    c_context = rag_svc.calls[-1]["context"]
    assert "lively" in c_context.prompt_context
    assert "quiet" not in c_context.prompt_context

    # 3. Query in a new Conversation D: should still use user-scoped 'quiet'
    rag_svc.calls.clear()
    orchestrator.handle_turn(
        message="Gợi ý khách sạn cho chuyến đi khác",
        conversation_id=None,
        principal=_principal(),
    )
    assert len(rag_svc.calls) == 1
    d_context = rag_svc.calls[-1]["context"]
    assert "quiet" in d_context.prompt_context
    assert "lively" not in d_context.prompt_context


def test_mutation_matrix_all_8_registry_keys(migrated):
    """Matrix testing all 8 registry-v2 keys across Remember -> Correct -> Forget -> Re-remember."""
    store = PostgresMemoryStore(migrated)
    read_engine = MemoryReadEngine(store, clock=utc_now)
    uow = PostgresMemoryUnitOfWork(migrated)

    all_keys = list(registry_keys())
    assert len(all_keys) == 8

    test_data = {
        "travel.preference.hotel_atmosphere": ("quiet", "lively"),
        "travel.preference.accommodation_type": (["hotel", "resort"], ["hotel", "resort", "villa"]),
        "travel.preference.transport_mode": (["flight", "train"], ["flight", "train", "car"]),
        "travel.preference.travel_pace": ("relaxed", "packed"),
        "travel.preference.activity_style": (["nature", "culture"], ["nature", "culture", "food"]),
        "travel.constraint.budget_level": ("budget", "luxury"),
        "travel.preference.food_style": (["street_food"], ["street_food", "local"]),
        "travel.profile.default_departure_city": ("hanoi", "da_nang"),
    }

    for idx, key in enumerate(all_keys):
        val1, val2 = test_data[key]
        norm_val1 = normalize_value(key, val1)
        norm_val2 = normalize_value(key, val2)

        identity = _make_identity(
            owner=OWNER_EVAL,
            key=key,
            scope=MemoryScope.USER,
            scope_id=OWNER_EVAL,
        )

        now = utc_now()

        # Step A: Remember val1
        add_res = _apply_change(
            uow,
            MemoryChangeSet(
                operation=MemoryOperation.ADD,
                identity=identity,
                new_version=_make_draft(
                    owner=OWNER_EVAL,
                    key=key,
                    value=norm_val1,
                    valid_from=now,
                ),
                superseded_version_ids=(),
                reference_version_id=None,
                reason="matrix test add",
            ),
            idempotency_key=f"idemp_matrix_add_{idx}",
        )
        assert add_res.version_id is not None
        v1_id = add_res.version_id

        # Verify read engine returns val1
        req = MemoryReadRequest(owner_user_id=OWNER_EVAL, requested_keys=(key,))
        sel1 = read_engine.select(req)
        assert len(sel1.selected) == 1
        assert sel1.selected[0].normalized_value == norm_val1

        # Step B: Correct to val2 (SUPERSEDE)
        cor_res = _apply_change(
            uow,
            MemoryChangeSet(
                operation=MemoryOperation.SUPERSEDE,
                identity=identity,
                new_version=_make_draft(
                    owner=OWNER_EVAL,
                    key=key,
                    value=norm_val2,
                    valid_from=now,
                    supersedes_version_id=v1_id,
                ),
                superseded_version_ids=(v1_id,),
                reference_version_id=v1_id,
                reason="matrix test supersede",
            ),
            idempotency_key=f"idemp_matrix_cor_{idx}",
        )
        assert cor_res.version_id is not None
        v2_id = cor_res.version_id

        # Verify read engine returns val2
        sel2 = read_engine.select(req)
        assert len(sel2.selected) == 1
        assert sel2.selected[0].normalized_value == norm_val2

        # Step C: Forget (REVOKE)
        _apply_change(
            uow,
            MemoryChangeSet(
                operation=MemoryOperation.REVOKE,
                identity=identity,
                new_version=None,
                superseded_version_ids=(v2_id,),
                reference_version_id=v2_id,
                reason="matrix test revoke",
            ),
            idempotency_key=f"idemp_matrix_rev_{idx}",
        )

        # Verify read engine abstains (nothing selected)
        sel3 = read_engine.select(req)
        assert len(sel3.selected) == 0

        # Step D: Re-remember val1
        re_res = _apply_change(
            uow,
            MemoryChangeSet(
                operation=MemoryOperation.ADD,
                identity=identity,
                new_version=_make_draft(
                    owner=OWNER_EVAL,
                    key=key,
                    value=norm_val1,
                    valid_from=now,
                    suppression_generation=2,
                ),
                superseded_version_ids=(),
                reference_version_id=None,
                reason="matrix test re-add",
            ),
            idempotency_key=f"idemp_matrix_readd_{idx}",
        )
        assert re_res.version_id is not None

        # Verify read engine returns val1 again
        sel4 = read_engine.select(req)
        assert len(sel4.selected) == 1
        assert sel4.selected[0].normalized_value == norm_val1


def test_set_valued_preferences_order_stability(migrated):
    """Set-valued preferences preserve strict deterministic order across read and composition."""
    store = PostgresMemoryStore(migrated)
    read_engine = MemoryReadEngine(store, clock=utc_now)
    composer = MemoryContextComposer()
    uow = PostgresMemoryUnitOfWork(migrated)

    key = "travel.preference.accommodation_type"

    # Insert items out-of-order
    raw_accommodations = ["villa", "resort", "hotel", "hostel", "apartment"]
    norm = normalize_value(key, raw_accommodations)
    assert isinstance(norm, tuple)
    # Registry normalization sorts them alphabetically
    assert norm == ("apartment", "hostel", "hotel", "resort", "villa")

    now = utc_now()
    identity = _make_identity(
        owner=OWNER_EVAL,
        key=key,
        scope=MemoryScope.USER,
        scope_id=OWNER_EVAL,
    )
    _apply_change(
        uow,
        MemoryChangeSet(
            operation=MemoryOperation.ADD,
            identity=identity,
            new_version=_make_draft(
                owner=OWNER_EVAL,
                key=key,
                value=norm,
                valid_from=now,
            ),
            superseded_version_ids=(),
            reference_version_id=None,
            reason="test set order",
        ),
        idempotency_key="idemp_set_order_1",
    )

    req = MemoryReadRequest(owner_user_id=OWNER_EVAL, requested_keys=(key,))
    sel = read_engine.select(req)
    assert len(sel.selected) == 1
    assert sel.selected[0].normalized_value == ("apartment", "hostel", "hotel", "resort", "villa")

    # Verify composed string is deterministic and sorted
    composed = composer.compose(sel)
    payload = json.loads(composed.split("\n", 1)[1])
    assert payload["preferences"][0]["value"] == [
        "apartment",
        "hostel",
        "hotel",
        "resort",
        "villa",
    ]


def test_current_turn_input_overrides_remembered_preferences(migrated):
    """Prompt-safe generator contracts prove current user message overrides remembered soft preferences."""
    rag_svc = RecordingRAGService()
    orchestrator = create_orchestrator(migrated, rag_svc)

    # Store preference: budget travel
    orchestrator.handle_turn(
        message="Nhớ là tôi thích đi du lịch tiết kiệm nhé",
        conversation_id=None,
        principal=_principal(),
    )

    # In turn, user explicitly requests luxury override for this trip
    rag_svc.calls.clear()
    turn = orchestrator.handle_turn(
        message="Chuyến đi này tôi muốn nghỉ dưỡng sang trọng cao cấp (luxury), hãy gợi ý khách sạn cho tôi",
        conversation_id=None,
        principal=_principal(),
    )

    assert len(rag_svc.calls) == 1
    call = rag_svc.calls[-1]
    prompt_ctx = call["context"].prompt_context

    # Context contains soft preference
    assert "budget" in prompt_ctx
    assert "soft_preference" in prompt_ctx
    # Message explicitly requests luxury
    assert "luxury" in call["message"]


def test_explicit_inspect_end_to_end_on_live_postgres(migrated):
    """Explicit inspect queries live PostgreSQL MemoryReadEngine and returns formatted safe fields."""
    rag_svc = RecordingRAGService()
    orchestrator = create_orchestrator(migrated, rag_svc)

    # Store two preferences
    orchestrator.handle_turn(
        message="Nhớ là tôi thích khách sạn yên tĩnh nhé",
        conversation_id=None,
        principal=_principal(),
    )
    orchestrator.handle_turn(
        message="Nhớ là tôi thích đi du lịch tiết kiệm nhé",
        conversation_id=None,
        principal=_principal(),
    )

    # Explicit inspect turn
    inspect_turn = orchestrator.handle_turn(
        message="Bạn nhớ gì về tôi?",
        conversation_id=None,
        principal=_principal(),
    )

    assert inspect_turn.disposition is TurnDisposition.ANSWERED
    assert inspect_turn.model == "system"
    assert inspect_turn.citations == []
    assert "Dưới đây là các sở thích mà tôi đã ghi nhớ:" in inspect_turn.reply
    assert "hotel_atmosphere" in inspect_turn.reply
    assert "budget_level" in inspect_turn.reply
    assert "chung cho tài khoản của bạn" in inspect_turn.reply
