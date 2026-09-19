"""Step 4 production flow: the WORKING family is reachable from a real chat turn.

Plan v0.22 Task 13, Step 4. The unit tests prove the shapes; this proves the
production path, on a real PostgreSQL:

    normal chat turn
    -> a working event is written as its own row, separate from the semantic and
       episodic ones
    -> the working event starts `released_at IS NULL`, so it is owed but not
       claimable
    -> orchestration persists `WORKING / BACKGROUND_ELIGIBLE` bound to that event's
       own `source_outbox_id`, before the event can be claimed
    -> `complete_turn()` releases it
    -> the worker claims it and runs the Working branch
    -> with the family gate off, the open state is persisted `shadow`, never
       `active`, and the semantic model adapter is never reached

The negative case is a separate test: with the authority row removed, the worker
must refuse the released event without a single model call and without writing a
row. That is the difference between "the gate is wired" and "the gate is load
bearing".

The commit coordinator runs as `travel_worker`, not on the migration role. That
is the point of `20260915_04`: the fence's `SELECT ... FOR UPDATE` was denied to
the role that is supposed to take it, so the worker could not reach its own commit
path. Running the coordinator as the worker is what makes "the background path is
production-reachable" a claim this suite actually checks.
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
from backend.memory.commit_coordinators import BackgroundMemoryCommit
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
from backend.memory.working import allows_working_formation
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

OWNER = "step4_owner"
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


class Step4Probe:
    """Observes the turn's database state from inside generation.

    The conversation is created before the turn runs so the probe knows its id and
    can read the real rows. A probe that guessed the id, or read with an unbound
    tenant, would report "no event" for a turn that wrote three of them.
    """

    def __init__(self, engine: Any, conversation_id: str) -> None:
        self._engine = engine
        self._conversation_id = conversation_id
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
        self.mid_turn = {
            "outbox": _outbox_rows(self._engine, self._conversation_id),
            "handling": _handling_rows(self._engine),
        }
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

def _principal():
    from backend.security.models import AuthMode, AuthenticatedPrincipal

    return AuthenticatedPrincipal(
        owner_user_id=OWNER,
        auth_mode=AuthMode.AUTHENTICATED,
        credential_label="step4-e2e",
    )


def _orchestrator(engine, probe: Step4Probe) -> ConversationOrchestrator:
    repository = PostgresConversationRepository(engine)
    service = ConversationService(conversation_repository=repository)
    return ConversationOrchestrator(
        rag_service=probe,
        conversation_service_provider=lambda: service,
        # Background capture on: this is the gate that emits every family's event.
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

    if not conversation_id:
        return []
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


def _working_rows(engine) -> list[dict]:
    from backend.storage.postgres import set_tenant

    with engine.connect() as connection:
        set_tenant(connection, OWNER)
        return [
            dict(row)
            for row in connection.execute(
                sa.text(
                    "SELECT open_goal, through_sequence, origin, status "
                    "FROM memory_summaries WHERE owner_user_id = :o"
                ),
                {"o": OWNER},
            ).mappings()
        ]


class _CountingModel:
    """A model adapter that proves whether extraction was reached."""

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, messages, owner_user_id, conversation_id, evidence_ids=()):
        self.calls += 1
        return []


def _worker(engine, model) -> MemoryOutboxWorker:
    return MemoryOutboxWorker(
        outbox_repo=PostgresOutboxRepository(engine),
        model_adapter=model,
        conversation_service=ConversationService(
            conversation_repository=PostgresConversationRepository(engine)
        ),
        recorder=BackgroundMemoryRecorder(
            uow_factory=lambda: PostgresMemoryUnitOfWork(engine)
        ),
        worker_id="step4_worker",
        source_handling_loader=lambda owner, outbox_id, family: load_source_handling(
            engine, owner, outbox_id, family
        ),
        # The deployment flag, left at its default on purpose.
        working_activation_enabled=False,
        working_commit_coordinator=BackgroundMemoryCommit(
            engine=engine,
            memory_write_store=PostgresMemoryUnitOfWork(engine),
        ),
    )


def _run_turn(runtime) -> tuple[str, Step4Probe]:
    """Create the conversation, then run one normal turn inside it."""
    from backend.conversations.models import MessageRole, MessageSource

    service = ConversationService(
        conversation_repository=PostgresConversationRepository(runtime)
    )
    conversation, _, _ = service.create_conversation_with_initial_turn(
        owner_user_id=OWNER,
        title="step4",
        content="Xin chào",
        role=MessageRole.USER,
        source=MessageSource.UI,
    )
    conversation_id = conversation.conversation_id

    probe = Step4Probe(runtime, conversation_id)
    orchestrator = _orchestrator(runtime, probe)
    outcome = orchestrator.handle_turn(
        message="Tôi muốn tìm khách sạn yên tĩnh ở Đà Nẵng",
        conversation_id=conversation_id,
        principal=_principal(),
    )
    assert outcome.reply
    return conversation_id, probe


# --- the positive flow ------------------------------------------------------


def test_a_normal_turn_writes_a_working_event_and_authorizes_it(schema, runtime):
    conversation_id, _ = _run_turn(runtime)

    rows = _outbox_rows(runtime, conversation_id)
    # One row per family, not one shared row with per-family progress state.
    assert [row["event_type"] for row in rows] == [
        MEMORY_EXTRACT_EVENT_TYPE,
        EPISODIC_EXTRACT_EVENT_TYPE,
        WORKING_EXTRACT_EVENT_TYPE,
    ]
    working = next(
        row for row in rows if row["event_type"] == WORKING_EXTRACT_EVENT_TYPE
    )
    assert working["released_at"] is not None, "complete_turn released it"

    handling = _handling_rows(runtime)
    working_authority = [row for row in handling if row["family"] == "working"]
    assert len(working_authority) == 1, handling
    assert working_authority[0]["outcome"] == "background_eligible"
    assert working_authority[0]["source_outbox_id"] == working["outbox_id"], (
        "the record is bound to the working event's own identity, not another "
        "family's"
    )

    assert load_source_handling(
        runtime, OWNER, working["outbox_id"], "working"
    ) is not None
    assert load_source_handling(
        runtime, OWNER, working["outbox_id"], "semantic"
    ) is None, "one family's authority is not another family's"


def test_the_working_event_is_unclaimable_while_it_is_unreleased(schema, runtime):
    """The release gate, observed before `complete_turn` runs.

    `ADR 0027` blocks the event until the turn is terminal. Reading the state from
    inside generation is the only way to see it un-released, and it is what makes
    "authority exists before the source can be consumed" an assertion rather than a
    claim about statement order.
    """
    _, probe = _run_turn(runtime)

    assert probe.mid_turn is not None, "generation ran"
    mid_turn_events = probe.mid_turn["outbox"]
    assert [row["event_type"] for row in mid_turn_events] == [
        MEMORY_EXTRACT_EVENT_TYPE,
        EPISODIC_EXTRACT_EVENT_TYPE,
        WORKING_EXTRACT_EVENT_TYPE,
    ], "every family's event is written in the turn transaction"
    assert all(row["released_at"] is None for row in mid_turn_events), (
        "no event is claimable mid-turn: `complete_turn` is what releases them"
    )
    # The authority records, by contrast, are already written at that instant.
    assert sorted(row["family"] for row in probe.mid_turn["handling"]) == [
        "episodic",
        "working",
    ]


def test_the_worker_runs_the_working_branch_and_persists_a_shadow_state(
    schema, runtime, worker_engine
):
    conversation_id, _ = _run_turn(runtime)

    rows = _outbox_rows(runtime, conversation_id)
    working_outbox_id = next(
        row["outbox_id"]
        for row in rows
        if row["event_type"] == WORKING_EXTRACT_EVENT_TYPE
    )

    model = _CountingModel()
    worker = _worker(worker_engine, model)

    event = PostgresOutboxRepository(worker_engine).claim_event(
        outbox_id=working_outbox_id,
        lease_owner="step4_worker",
        lease_duration_seconds=30.0,
    )
    assert event is not None, "the worker must be able to claim the working event"
    assert MEMORY_FAMILY_BY_EVENT_TYPE[event.event_type].value == "working"

    result = worker.process_one(event)

    # 1. the Working branch handled it, not the semantic extraction path
    assert model.calls == 0, (
        "the working family derives its open state deterministically; the semantic "
        "model adapter must not be reached"
    )
    assert result.status.value == "succeeded"
    assert result.reason.value == "working_recorded"

    # 2. one canonical row, shadow, never active: the family gate is off
    stored = _working_rows(runtime)
    assert len(stored) == 1, stored
    assert stored[0]["origin"] == "inferred_replacement"
    assert stored[0]["status"] == "shadow", stored[0]["status"]
    assert stored[0]["status"] != "active"
    assert stored[0]["through_sequence"] >= 1


def test_without_positive_working_authority_the_worker_refuses(
    schema, runtime, worker_engine
):
    """The negative case: the gate is load bearing, not decorative."""
    conversation_id, _ = _run_turn(runtime)

    rows = _outbox_rows(runtime, conversation_id)
    working_outbox_id = next(
        row["outbox_id"]
        for row in rows
        if row["event_type"] == WORKING_EXTRACT_EVENT_TYPE
    )

    with schema.begin() as connection:
        connection.execute(
            sa.text(
                "DELETE FROM memory_source_handling "
                "WHERE owner_user_id = :o AND family = 'working'"
            ),
            {"o": OWNER},
        )

    assert (
        allows_working_formation(
            load_source_handling(runtime, OWNER, working_outbox_id, "working")
        )
        is False
    )

    model = _CountingModel()
    worker = _worker(worker_engine, model)

    event = PostgresOutboxRepository(worker_engine).claim_event(
        outbox_id=working_outbox_id,
        lease_owner="step4_worker",
        lease_duration_seconds=30.0,
    )
    assert event is not None

    result = worker.process_one(event)

    assert model.calls == 0, "an unauthorized source must not reach a model"
    assert result.reason.value == "source_handling_denied"
    assert _working_rows(runtime) == [], "no open state may be written"
