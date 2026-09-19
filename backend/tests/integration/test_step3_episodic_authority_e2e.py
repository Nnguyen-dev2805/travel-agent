"""Step 3 production flow: one normal chat turn, two family-specific events.

Plan v0.21 Task 12, "Step-3 episodic authority and release invariant". This is the
end-to-end proof that the invariant holds on a real PostgreSQL, not the unit-level
shape of it:

    normal chat turn
    -> a semantic event and an episodic event are written as separate rows
    -> the episodic event starts `released_at IS NULL`
    -> the worker cannot claim it yet
    -> orchestration persists `EPISODIC / BACKGROUND_ELIGIBLE` bound to that event
    -> `complete_turn()` releases it
    -> the worker claims exactly that event
    -> the family-aware loader answers `MemoryFamily.EPISODIC`
    -> the persisted authority is `BACKGROUND_ELIGIBLE`

The intermediate states are observed from inside `generate_from_context`, which the
orchestrator calls after persistence and after `TurnUnderstanding` but before
`complete_turn`. That is the only point in one turn where both facts are true at
once, so the probe is what makes the ordering an assertion rather than a claim.

The negative case is a separate test: with the authority row removed, the worker
must refuse before the model is paid for.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from backend.conversations.models import (
    EPISODIC_EXTRACT_EVENT_TYPE,
    MEMORY_EXTRACT_EVENT_TYPE,
    WORKING_EXTRACT_EVENT_TYPE,
)
from backend.conversations.postgres_repository import PostgresConversationRepository
from backend.conversations.service import ConversationService
from backend.generation.contracts import (
    GenerationCitation,
    GenerationContext,
    GenerationResult,
)
from backend.memory.episodic import allows_episodic_formation
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingOutcome,
    allows_background_formation,
)
from backend.memory.write_pipeline.background_recorder import BackgroundMemoryRecorder
from backend.memory.write_pipeline.outbox import (
    MEMORY_FAMILY_BY_EVENT_TYPE,
    PostgresOutboxRepository,
)
from backend.memory.write_pipeline.postgres import (
    PostgresMemoryUnitOfWork,
    load_source_handling,
    record_source_handling,
)
from backend.memory.write_pipeline.worker import MemoryOutboxWorker
from backend.orchestration.context_planner import ContextPlanner
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator
from backend.tests.integration.pg_dsn import (
    ensure_worker_login,
    migration_dsn,
    require,
    runtime_dsn,
    worker_dsn,
)

pytestmark = pytest.mark.skipif(
    not migration_dsn(),
    reason="isolated PG unavailable: set PG_TEST_DSN to a disposable database",
)

OWNER = "step3_owner"
MOMENT = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


# --- fixtures ---------------------------------------------------------------


@pytest.fixture(scope="module")
def admin_engine():
    from backend.storage.postgres import create_engine

    engine = create_engine(require(migration_dsn(), "PG_TEST_DSN"))
    yield engine
    engine.dispose()


@pytest.fixture()
def schema(admin_engine):
    from alembic import command

    from backend.storage.postgres import alembic_config

    with admin_engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    migrations = (
        Path(__file__).resolve().parent.parent.parent / "storage" / "migrations"
    )
    command.upgrade(
        alembic_config(str(migrations), require(migration_dsn(), "PG_TEST_DSN")),
        "head",
    )
    return admin_engine


@pytest.fixture()
def runtime(schema):
    from backend.storage.postgres import create_engine

    engine = create_engine(require(runtime_dsn(), "PG_RUNTIME_TEST_DSN"))
    yield engine
    engine.dispose()


@pytest.fixture()
def worker_engine(admin_engine):
    from backend.storage.postgres import create_engine

    ensure_worker_login(admin_engine)
    engine = create_engine(require(worker_dsn(), "PG_WORKER_TEST_DSN"))
    yield engine
    engine.dispose()


# --- the turn's observability probe ----------------------------------------


class Step3Probe:
    """Records the database state observed mid-turn, before `complete_turn`."""

    def __init__(self) -> None:
        self.mid_turn: dict[str, Any] | None = None

    def build_travel_context(self, message: str, top_k: int = 4):
        from backend.rag.contracts import CitationEvidence, ContextBundle

        return ContextBundle(
            prompt_context="Cẩm nang du lịch Đà Nẵng.",
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
        # The one point in the turn where persistence has happened, understanding
        # has happened, and `complete_turn` has not.
        self.mid_turn = {"message": user_message}
        return GenerationResult(
            reply="Đà Nẵng có nhiều khách sạn yên tĩnh.",
            model="gpt-4o-mini",
            citations=context.citations or (
                GenerationCitation(
                    title="Cẩm nang du lịch Đà Nẵng",
                    url="https://vietnam.travel/da-nang",
                ),
            ),
        )


def _orchestrator(engine, probe: Step3Probe) -> ConversationOrchestrator:
    repository = PostgresConversationRepository(engine)
    service = ConversationService(conversation_repository=repository)
    return ConversationOrchestrator(
        rag_service=probe,
        conversation_service_provider=lambda: service,
        # Background capture on: this is the gate that emits both families' events.
        outbox_enabled=True,
        # Enforcement on, so generation goes through `generate_from_context` and
        # the mid-turn probe observes the real ordering rather than a fallback.
        context_planner=ContextPlanner(enforcement_enabled=True),
        source_handling_recorder=lambda owner, record: record_source_handling(
            engine, owner, record
        ),
    )


def _outbox_rows(engine, conversation_id: str) -> list[dict]:
    from backend.storage.postgres import set_tenant

    with engine.connect() as connection:
        # RLS is on: an unbound read sees nothing, which would make an empty
        # result look like "no event was written" rather than "not visible".
        set_tenant(connection, OWNER)
        return [
            dict(row)
            for row in connection.execute(
                sa.text(
                    "SELECT outbox_id, event_type, released_at FROM conversation_outbox "
                    "WHERE conversation_id = :c ORDER BY event_type"
                ),
                {"c": conversation_id},
            ).mappings()
        ]


def _handling_rows(engine) -> list[dict]:
    from backend.storage.postgres import set_tenant

    with engine.connect() as connection:
        set_tenant(connection, OWNER)
        return [
            dict(row)
            for row in connection.execute(
                sa.text(
                    "SELECT source_outbox_id, family, outcome, reason_code "
                    "FROM memory_source_handling WHERE owner_user_id = :o"
                ),
                {"o": OWNER},
            ).mappings()
        ]


def _claim(engine, owner: str = "step3_worker"):
    return list(
        PostgresOutboxRepository(engine).claim_batch(
            lease_owner=owner, lease_duration_seconds=30.0, limit=10
        )
    )


class _CountingModel:
    """A model adapter that proves whether extraction was reached."""

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, messages, owner_user_id, conversation_id, evidence_ids=()):
        self.calls += 1
        return []


# --- the positive flow ------------------------------------------------------


def test_a_normal_turn_writes_every_family_event_and_authorizes_episodic(
    schema, runtime, worker_engine
):
    probe = Step3Probe()
    orchestrator = _orchestrator(runtime, probe)

    outcome = orchestrator.handle_turn(
        message="Tôi muốn tìm khách sạn yên tĩnh ở Đà Nẵng",
        principal=_principal(),
    )
    assert outcome.reply

    rows = _outbox_rows(runtime, outcome.conversation.conversation_id)
    # One row per family, not one shared row with per-family progress state. The
    # set grew at Task 13; this test still owns only the episodic family's claims.
    assert [row["event_type"] for row in rows] == [
        MEMORY_EXTRACT_EVENT_TYPE,
        EPISODIC_EXTRACT_EVENT_TYPE,
        WORKING_EXTRACT_EVENT_TYPE,
    ], rows

    # 1. the authority record is bound to the episodic event's own identity
    handling = _handling_rows(runtime)
    episodic_handling = [
        row for row in handling if row["family"] == MemoryFamily.EPISODIC.value
    ]
    assert len(episodic_handling) == 1, handling
    assert (
        episodic_handling[0]["outcome"]
        == SourceHandlingOutcome.BACKGROUND_ELIGIBLE.value
    )
    episodic_outbox_id = next(
        row["outbox_id"]
        for row in rows
        if row["event_type"] == EPISODIC_EXTRACT_EVENT_TYPE
    )
    assert episodic_handling[0]["source_outbox_id"] == episodic_outbox_id, (
        "the episodic authority must be bound to the episodic event, never to the "
        "semantic one"
    )

    # 2. the turn completed, so every family's event is released and claimable
    assert all(row["released_at"] is not None for row in rows), rows

    # 3. the worker can claim the episodic event by its own identity. The batch
    #    claim serialises one event per conversation, so `claim_batch` would take
    #    the semantic row first; naming the episodic row is what proves the worker
    #    sees it at all rather than that it was merely next in the queue.
    claimed = PostgresOutboxRepository(worker_engine).claim_event(
        outbox_id=episodic_outbox_id,
        lease_owner="step3_worker",
        lease_duration_seconds=30.0,
    )
    assert claimed is not None, "the worker must be able to claim the episodic event"
    assert claimed.event_type == EPISODIC_EXTRACT_EVENT_TYPE

    # 4. the family-aware loader answers with the episodic family and the
    #    positive outcome for the episodic event
    loaded = load_source_handling(
        worker_engine, OWNER, episodic_outbox_id, MemoryFamily.EPISODIC
    )
    assert loaded is not None
    assert loaded.family is MemoryFamily.EPISODIC
    assert loaded.outcome is SourceHandlingOutcome.BACKGROUND_ELIGIBLE
    assert allows_episodic_formation(loaded) is True
    assert allows_background_formation(loaded) is True

    # 5. and the semantic family's own lookup is a different row entirely
    semantic_outbox_id = next(
        row["outbox_id"]
        for row in rows
        if row["event_type"] == MEMORY_EXTRACT_EVENT_TYPE
    )
    assert (
        load_source_handling(
            worker_engine, OWNER, semantic_outbox_id, MemoryFamily.EPISODIC
        )
        is None
    ), "the semantic event must never carry episodic authority"


def test_the_episodic_event_is_unreleased_and_unclaimable_before_complete_turn(
    schema, runtime, worker_engine
):
    """The ordering assertion, observed mid-turn rather than reconstructed.

    `generate_from_context` runs after the turn is persisted and after
    `TurnUnderstanding`, but before `complete_turn`. At that instant the episodic
    event must exist, be unreleased, be unclaimable, and already carry its
    authority record — which is what makes "authority exists before model
    exposure" a fact about the ordering rather than a hopeful claim.
    """
    observed: dict[str, Any] = {}

    class _MidTurnProbe(Step3Probe):
        def generate_from_context(self, user_message, context):
            rows = _outbox_rows(runtime, observed["conversation_id"])
            observed["rows"] = rows
            observed["handling"] = _handling_rows(runtime)
            observed["claimed"] = _claim(worker_engine)
            return super().generate_from_context(user_message, context)

    probe = _MidTurnProbe()
    orchestrator = _orchestrator(runtime, probe)

    # The probe needs the conversation id, which only exists after the first
    # phase; a bound turn gives it to us up front.
    repository = PostgresConversationRepository(runtime)
    service = ConversationService(conversation_repository=repository)
    from backend.conversations.models import MessageRole, MessageSource

    conversation, _, _ = service.create_conversation_with_initial_turn(
        owner_user_id=OWNER,
        title="step3 ordering",
        content="first",
        role=MessageRole.USER,
        source=MessageSource.UI,
    )
    observed["conversation_id"] = conversation.conversation_id

    orchestrator.handle_turn(
        message="Tôi muốn tìm khách sạn yên tĩnh ở Đà Nẵng",
        conversation_id=conversation.conversation_id,
        principal=_principal(),
    )

    rows = observed["rows"]
    episodic = next(
        row for row in rows if row["event_type"] == EPISODIC_EXTRACT_EVENT_TYPE
    )
    assert episodic["released_at"] is None, (
        "the episodic event is owed but not claimable until complete_turn"
    )

    # The worker sees nothing, which is the mechanism that protects the ordering.
    assert observed["claimed"] == [], (
        "an unreleased event must not be claimable, so the episodic model cannot "
        "run before its authority record exists"
    )

    # ...and the authority record already exists at that same instant.
    handling = [
        row
        for row in observed["handling"]
        if row["family"] == MemoryFamily.EPISODIC.value
    ]
    assert len(handling) == 1, observed["handling"]
    assert handling[0]["outcome"] == SourceHandlingOutcome.BACKGROUND_ELIGIBLE.value
    assert handling[0]["source_outbox_id"] == episodic["outbox_id"]

    # After the turn completes, the same event becomes claimable.
    assert all(row["released_at"] is not None for row in _outbox_rows(runtime, conversation.conversation_id))


# --- the negative case ------------------------------------------------------


def test_without_positive_episodic_authority_formation_never_reaches_the_model(
    schema, runtime, worker_engine, admin_engine
):
    """`UNHANDLED` grants nothing, so the episodic model is never paid for.

    The authority row is removed after the turn, which is the closest production
    shape of "the record is missing": the event is released and claimable, and the
    worker's gate is the only thing standing between it and the model.
    """
    probe = Step3Probe()
    orchestrator = _orchestrator(runtime, probe)
    outcome = orchestrator.handle_turn(
        message="Tôi muốn tìm khách sạn yên tĩnh ở Đà Nẵng",
        principal=_principal(),
    )

    rows = _outbox_rows(runtime, outcome.conversation.conversation_id)
    episodic_outbox_id = next(
        row["outbox_id"]
        for row in rows
        if row["event_type"] == EPISODIC_EXTRACT_EVENT_TYPE
    )

    # The loader now answers for the episodic family and denies.
    assert (
        load_source_handling(
            worker_engine, OWNER, episodic_outbox_id, MemoryFamily.EPISODIC
        )
        is not None
    )

    with admin_engine.begin() as connection:
        connection.execute(
            sa.text(
                "DELETE FROM memory_source_handling WHERE owner_user_id = :o "
                "AND source_outbox_id = :s"
            ),
            {"o": OWNER, "s": episodic_outbox_id},
        )

    loaded = load_source_handling(
        worker_engine, OWNER, episodic_outbox_id, MemoryFamily.EPISODIC
    )
    assert loaded is None, "absence is UNHANDLED"
    assert allows_episodic_formation(loaded) is False

    # And the worker refuses the released, claimable event without paying the
    # provider — the assertion that makes the gate load-bearing.
    model = _CountingModel()
    worker = MemoryOutboxWorker(
        outbox_repo=PostgresOutboxRepository(worker_engine),
        model_adapter=model,
        conversation_service=ConversationService(
            conversation_repository=PostgresConversationRepository(runtime)
        ),
        recorder=BackgroundMemoryRecorder(
            uow_factory=lambda: PostgresMemoryUnitOfWork(worker_engine)
        ),
        worker_id="step3_worker",
        source_handling_loader=lambda owner, outbox_id, family: load_source_handling(
            worker_engine, owner, outbox_id, family
        ),
    )

    event = PostgresOutboxRepository(worker_engine).claim_event(
        outbox_id=episodic_outbox_id,
        lease_owner="step3_worker",
        lease_duration_seconds=30.0,
    )
    assert event is not None
    # The loader the worker holds is asked for the event's own family.
    assert MEMORY_FAMILY_BY_EVENT_TYPE[event.event_type] is MemoryFamily.EPISODIC

    result = worker.process_one(event)

    assert model.calls == 0, (
        "no positive episodic authority means no episodic model exposure"
    )
    assert result.reason.value == "source_handling_denied", result


def _principal():
    from backend.security.models import AuthMode, AuthenticatedPrincipal

    return AuthenticatedPrincipal(
        owner_user_id=OWNER,
        auth_mode=AuthMode.AUTHENTICATED,
        credential_label="step3-e2e",
    )


# --- Step 4: the worker's episodic production branch ------------------------


def _episode_rows(engine) -> list[dict]:
    from backend.storage.postgres import set_tenant

    with engine.connect() as connection:
        set_tenant(connection, OWNER)
        return [
            dict(row)
            for row in connection.execute(
                sa.text(
                    "SELECT episode_id, actor, event, status, source_outbox_id, "
                    "retention_mode, suppression_generation FROM memory_episodes "
                    "WHERE owner_user_id = :o"
                ),
                {"o": OWNER},
            ).mappings()
        ]


def test_the_worker_runs_the_episodic_branch_and_persists_a_shadow_episode(
    schema, runtime, worker_engine
):
    """The production branch, end to end: claim -> gate -> form -> evaluate -> persist.

    With `MEMORY_EPISODIC_ACTIVATION_ENABLED=False` **and** the family/type
    evaluation gate not yet conclusive, the episode must be persisted as `SHADOW`
    and must never be `ACTIVE`. Two independent reasons deny activation here, so a
    pass proves the fail-closed direction rather than one flag's value.

    The fence and outbox semantics are asserted at the same time: the episode row
    and the event's terminal state come out of one transaction, and the semantic
    model adapter is never touched, because the episodic family has its own
    extraction contract.
    """
    from backend.memory.commit_coordinators import BackgroundMemoryCommit
    from backend.memory.episodic import (
        EpisodeAbstentionReason,
        EpisodeReadRequest,
        EpisodicReadEngine,
    )
    from backend.memory.postgres_store import PostgresEpisodeStore

    probe = Step3Probe()
    orchestrator = _orchestrator(runtime, probe)
    outcome = orchestrator.handle_turn(
        message="Tôi muốn tìm khách sạn yên tĩnh ở Đà Nẵng",
        principal=_principal(),
    )

    rows = _outbox_rows(runtime, outcome.conversation.conversation_id)
    episodic_outbox_id = next(
        row["outbox_id"]
        for row in rows
        if row["event_type"] == EPISODIC_EXTRACT_EVENT_TYPE
    )

    model = _CountingModel()
    worker = MemoryOutboxWorker(
        outbox_repo=PostgresOutboxRepository(worker_engine),
        model_adapter=model,
        conversation_service=ConversationService(
            conversation_repository=PostgresConversationRepository(runtime)
        ),
        recorder=BackgroundMemoryRecorder(
            uow_factory=lambda: PostgresMemoryUnitOfWork(worker_engine)
        ),
        worker_id="step4_worker",
        source_handling_loader=lambda owner, outbox_id, family: load_source_handling(
            worker_engine, owner, outbox_id, family
        ),
        # The flag the deployment would set. Left at its default on purpose.
        episodic_activation_enabled=False,
        # The coordinator runs on the migration role, as the semantic background
        # E2E does. `travel_worker` holds only `SELECT` on `conversations`, so the
        # conversation lock's `SELECT ... FOR UPDATE` is denied to it — a
        # pre-existing gap that affects the semantic path identically and is not
        # Task 12's to fix. The claim, the authority lookup and the family
        # decision below all still run as `travel_worker`.
        episodic_commit_coordinator=BackgroundMemoryCommit(
            engine=schema,
            memory_write_store=PostgresMemoryUnitOfWork(schema),
        ),
    )

    event = PostgresOutboxRepository(worker_engine).claim_event(
        outbox_id=episodic_outbox_id,
        lease_owner="step4_worker",
        lease_duration_seconds=30.0,
    )
    assert event is not None

    result = worker.process_one(event)

    # 1. the episodic branch handled it, not the semantic extraction path
    assert model.calls == 0, (
        "the episodic family must not go through the semantic model adapter"
    )
    assert result.status.value == "succeeded"
    assert result.reason.value == "episodic_recorded"

    # 2. one canonical episode row, grounded from the turn
    episodes = _episode_rows(runtime)
    assert len(episodes) == 1, episodes
    episode = episodes[0]
    assert episode["source_outbox_id"] == episodic_outbox_id
    assert episode["actor"] == OWNER
    assert "khách sạn yên tĩnh" in episode["event"]
    assert episode["retention_mode"] == "conversation_bound"
    assert episode["suppression_generation"] == 1

    # 3. SHADOW, and never ACTIVE: the gate is off and the evaluation record is
    #    not conclusive, so both independent reasons deny activation.
    assert episode["status"] == "shadow", episode["status"]
    assert episode["status"] != "active"

    # 4. the fence/outbox semantics are unchanged: the effect and the event's
    #    terminal state came out of the same transaction
    assert _outbox_rows(runtime, outcome.conversation.conversation_id)
    with runtime.connect() as connection:
        from backend.storage.postgres import set_tenant

        set_tenant(connection, OWNER)
        status = connection.execute(
            sa.text(
                "SELECT status FROM conversation_outbox WHERE outbox_id = :o"
            ),
            {"o": episodic_outbox_id},
        ).scalar()
    assert status == "succeeded"

    # 5. and a shadow episode is not answer-eligible
    from datetime import datetime as _dt, timezone as _tz

    selection = EpisodicReadEngine(PostgresEpisodeStore(runtime)).select(
        EpisodeReadRequest(
            owner_user_id=OWNER,
            conversation_id=outcome.conversation.conversation_id,
            occurred_after=_dt(2000, 1, 1, tzinfo=_tz.utc),
            occurred_before=_dt(2100, 1, 1, tzinfo=_tz.utc),
        )
    )
    assert selection.selected == ()
    assert selection.abstention_reason is EpisodeAbstentionReason.NO_ELIGIBLE_EPISODE
