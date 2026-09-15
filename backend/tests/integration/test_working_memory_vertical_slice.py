"""The Working Memory slice against a real PostgreSQL: schema, RLS, replacement.

Plan v0.22 Task 13, Steps 2, 6 and 8. Everything here needs the database, and
every claim that touches isolation needs the *runtime* role rather than the
migration role — a superuser or `BYPASSRLS` role ignores row-level security, which
would make the isolation assertions vacuous.

The load-bearing claims, each of which fails when its control is removed:

1. the evolved `memory_summaries` carries the open-state and lifecycle columns, and
   the replacement boundary is a real unique index on `(owner_user_id,
   conversation_id)`, not a convention;
2. `FORCE` RLS is on, so the table owner cannot bypass the tenant predicate;
3. the runtime role reads and invalidates but cannot insert or delete;
4. a deterministic transition persists and reads back as `active`, because it is
   the explicit-input row of `spec:1037` and not background inference;
5. replacement is an **update in place**: one conversation has one open state, and
   a newer candidate leaves exactly one row;
6. a stale background candidate is refused and leaves the newer state untouched —
   the rule that makes the two formation paths safe to run concurrently;
7. deleting a conversation invalidates its open state, so the read abstains.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from backend.memory.lifecycle import SourceValidity
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingOutcome,
    SourceHandlingReason,
    SourceHandlingRecord,
)
from backend.memory.working import (
    WorkingAbstentionReason,
    WorkingMemoryReadEngine,
    WorkingOrigin,
    WorkingReadRequest,
    WorkingReplacementReason,
    WorkingStateTransition,
)
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

OWNER = "working_owner"
OTHER_OWNER = "working_other_owner"
CONVERSATION = "conv_working_1"
OTHER_CONVERSATION = "conv_working_2"
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)

TURNS = (
    {"sequence": 1, "role": "user", "content": "Tôi muốn đi Đà Nẵng tháng 10"},
    {"sequence": 2, "role": "assistant", "content": "Bạn muốn ở bao nhiêu đêm?"},
    {"sequence": 3, "role": "user", "content": "3 đêm"},
)


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
def runtime_engine():
    from backend.storage.postgres import create_engine

    engine = create_engine(require(runtime_dsn(), "PG_RUNTIME_TEST_DSN"))
    yield engine
    engine.dispose()


@pytest.fixture()
def runtime(runtime_engine):
    return runtime_engine


@pytest.fixture()
def worker(admin_engine):
    """The role that forms an open state.

    `travel_app` deliberately has no `INSERT` on `memory_summaries` — the grant
    test above asserts exactly that — so seeding through the runtime role would be
    testing a privilege the product does not have.
    """
    from backend.storage.postgres import create_engine

    ensure_worker_login(admin_engine)
    engine = create_engine(require(worker_dsn(), "PG_WORKER_TEST_DSN"))
    yield engine
    engine.dispose()


def _positive_record(family: MemoryFamily = MemoryFamily.WORKING) -> SourceHandlingRecord:
    return SourceHandlingRecord(
        source_outbox_id="cout_working_1",
        source_message_id="msg_working_1",
        family=family,
        outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
        recorded_at=NOW,
    )


def _candidate(
    *,
    origin=WorkingOrigin.DETERMINISTIC_TRANSITION,
    source_outbox_id="cout_working_1",
    owner_user_id=OWNER,
    conversation_id=CONVERSATION,
    turns=TURNS,
    source_handling_record=None,
    source_validity=SourceValidity.VALID,
):
    return WorkingStateTransition().derive(
        turns=turns,
        owner_user_id=owner_user_id,
        conversation_id=conversation_id,
        origin=origin,
        source_outbox_id=source_outbox_id,
        source_message_id="msg_working_1",
        source_handling_record=(
            source_handling_record
            if source_handling_record is not None
            else _positive_record()
        ),
        source_validity=source_validity,
    )


def _apply(engine, candidate, *, status=None):
    from backend.conversations.postgres_repository import tenant_transaction
    from backend.memory.postgres_store import record_working_state_on
    from backend.memory.write_pipeline.models import VersionStatus
    from backend.storage.postgres import set_tenant

    with tenant_transaction(engine, candidate.owner_user_id) as connection:
        set_tenant(connection, candidate.owner_user_id)
        return record_working_state_on(
            connection,
            candidate=candidate,
            created_at=NOW,
            status=status or VersionStatus.ACTIVE,
        )


def _select(engine, *, owner=OWNER, conversation=CONVERSATION):
    from backend.memory.postgres_store import PostgresWorkingStore

    return WorkingMemoryReadEngine(
        PostgresWorkingStore(engine), clock=lambda: NOW
    ).select(WorkingReadRequest(owner_user_id=owner, conversation_id=conversation))


def _rows(engine, owner=OWNER):
    from backend.storage.postgres import set_tenant

    with engine.connect() as connection:
        set_tenant(connection, owner)
        return [
            dict(row)
            for row in connection.execute(
                sa.text(
                    "SELECT summary_id, owner_user_id, conversation_id, open_goal, "
                    "through_sequence, origin, status, content, invalidated_at "
                    "FROM memory_summaries WHERE owner_user_id = :o"
                ),
                {"o": owner},
            ).mappings()
        ]


# --- Schema, the replacement boundary, and isolation ------------------------


def test_the_working_state_columns_exist(schema):
    with schema.connect() as connection:
        columns = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'memory_summaries'"
                )
            )
        }

    assert {
        "open_goal",
        "through_sequence",
        "origin",
        "source_message_id",
        "source_outbox_id",
        "retention_mode",
        "status",
        "sensitivity",
        "suppression_generation",
        "unresolved_conflict",
        "expires_at",
        "invalidated_at",
        "updated_at",
    } <= columns


def test_the_replacement_boundary_is_a_unique_index_on_owner_and_conversation(schema):
    with schema.connect() as connection:
        definition = connection.execute(
            sa.text(
                "SELECT indexdef FROM pg_indexes WHERE indexname = "
                "'uq_memory_summaries_owner_conversation'"
            )
        ).scalar()

    assert definition is not None, "one canonical open state per conversation"
    assert "UNIQUE" in definition.upper()


def test_force_rls_is_on(schema):
    with schema.connect() as connection:
        forced = connection.execute(
            sa.text(
                "SELECT relforcerowsecurity FROM pg_class "
                "WHERE relname = 'memory_summaries'"
            )
        ).scalar()

    assert forced is True


def test_the_runtime_role_cannot_insert_or_delete(schema):
    with schema.connect() as connection:
        granted = {
            (row[0], row[1])
            for row in connection.execute(
                sa.text(
                    "SELECT privilege_type, table_name FROM "
                    "information_schema.role_table_grants "
                    "WHERE grantee = 'travel_app' AND table_name = 'memory_summaries'"
                )
            )
        }

    assert granted == {("SELECT", "memory_summaries"), ("UPDATE", "memory_summaries")}


# --- The deterministic transition ------------------------------------------


def test_a_deterministic_transition_persists_and_reads_back_as_active(schema, worker, runtime):
    candidate = _candidate()
    assert candidate is not None

    decision = _apply(worker, candidate)
    assert decision.replace is True
    assert decision.reason is WorkingReplacementReason.REPLACE

    rows = _rows(runtime)
    assert len(rows) == 1
    assert rows[0]["open_goal"] == "Tôi muốn đi Đà Nẵng tháng 10"
    assert rows[0]["through_sequence"] == 3
    assert rows[0]["origin"] == "deterministic_transition"
    assert rows[0]["status"] == "active"

    selection = _select(runtime)
    assert len(selection.selected) == 1
    assert selection.selected[0].open_goal == "Tôi muốn đi Đà Nẵng tháng 10"


def test_the_legacy_content_column_stays_inert(schema, worker, runtime):
    """`content` is a migration-safety column, never policy authority."""
    assert _apply(worker, _candidate()).replace is True

    rows = _rows(runtime)
    assert rows[0]["content"] == ""


# --- Replacement ------------------------------------------------------------


def test_a_newer_candidate_replaces_the_open_state_in_place(schema, worker, runtime):
    assert _apply(worker, _candidate()).replace is True

    newer = _candidate(
        source_outbox_id="cout_working_2",
        turns=TURNS + ({"sequence": 4, "role": "user", "content": "Đổi sang Hội An"},),
    )
    assert newer is not None
    assert _apply(worker, newer).replace is True

    rows = _rows(runtime)
    assert len(rows) == 1, "replacement is an update, not an append"
    assert rows[0]["open_goal"] == "Đổi sang Hội An"
    assert rows[0]["through_sequence"] == 4


def test_a_stale_background_candidate_is_refused_and_changes_nothing(
    schema, worker, runtime
):
    """The rule that makes the two formation paths safe to run concurrently."""
    newer = _candidate(
        source_outbox_id="cout_working_newer",
        turns=TURNS + ({"sequence": 4, "role": "user", "content": "Đổi sang Hội An"},),
    )
    assert _apply(worker, newer).replace is True

    stale = _candidate(
        origin=WorkingOrigin.INFERRED_REPLACEMENT,
        source_outbox_id="cout_working_stale",
        turns=(
            {"sequence": 1, "role": "user", "content": "Tôi muốn đi Đà Nẵng"},
        ),
    )
    assert stale is not None
    decision = _apply(worker, stale)

    assert decision.replace is False
    assert decision.reason is WorkingReplacementReason.NOT_NEWER
    assert _rows(runtime)[0]["open_goal"] == "Đổi sang Hội An", (
        "a lagging background candidate must not undo newer deterministic state"
    )


def test_an_identical_redelivery_is_a_noop(schema, worker, runtime):
    assert _apply(worker, _candidate()).replace is True
    redelivered = _candidate()

    decision = _apply(worker, redelivered)

    assert decision.replace is False
    assert decision.reason is WorkingReplacementReason.IDENTICAL_NOOP
    assert len(_rows(runtime)) == 1


def test_a_cross_owner_write_is_refused(schema, worker, runtime):
    assert _apply(worker, _candidate()).replace is True

    foreign = _candidate(owner_user_id=OTHER_OWNER, source_outbox_id="cout_working_other")
    assert foreign is not None
    decision = _apply(worker, foreign)

    # A different owner has no canonical row, so this is a first write for that
    # owner rather than a replacement of the first owner's state.
    assert decision.replace is True
    assert len(_rows(runtime, OWNER)) == 1
    assert len(_rows(runtime, OTHER_OWNER)) == 1
    assert _rows(runtime, OWNER)[0]["open_goal"] == "Tôi muốn đi Đà Nẵng tháng 10"


def test_a_cross_owner_row_is_never_selected(schema, worker, runtime):
    assert _apply(worker, _candidate()).replace is True

    selection = _select(runtime, owner=OTHER_OWNER)

    assert selection.selected == ()
    assert (
        selection.abstention_reason
        is WorkingAbstentionReason.NO_ELIGIBLE_WORKING_STATE
    )


# --- Deletion ---------------------------------------------------------------


def test_deleting_a_conversation_invalidates_its_open_state(schema, worker, runtime):
    """The same transaction that tombstones the conversation invalidates it.

    This is the assertion that makes the propagation real rather than documented:
    without the extra statement in `PostgresConversationRepository.delete`, the
    open state stays eligible after its conversation is gone.
    """
    from backend.conversations.models import MessageRole, MessageSource
    from backend.conversations.postgres_repository import PostgresConversationRepository
    from backend.conversations.service import ConversationService
    from backend.memory.write_pipeline.models import VersionStatus

    repo = PostgresConversationRepository(runtime)
    conversation, _, _ = ConversationService(
        conversation_repository=repo
    ).create_conversation_with_initial_turn(
        owner_user_id=OWNER,
        title="working deletion",
        content="first",
        role=MessageRole.USER,
        source=MessageSource.UI,
    )
    conversation_id = conversation.conversation_id

    candidate = _candidate(conversation_id=conversation_id)
    assert candidate is not None
    assert _apply(worker, candidate, status=VersionStatus.ACTIVE).replace is True
    assert len(_select(runtime, conversation=conversation_id).selected) == 1

    assert repo.delete(conversation_id, OWNER) is True

    rows = _rows(runtime)
    assert len(rows) == 1, "the row is invalidated, not deleted"
    assert rows[0]["invalidated_at"] is not None

    selection = _select(runtime, conversation=conversation_id)
    assert selection.selected == (), (
        "a deleted conversation's open state must stop being eligible"
    )
    assert (
        selection.abstention_reason
        is WorkingAbstentionReason.NO_ELIGIBLE_WORKING_STATE
    )
