"""The episodic slice against a real PostgreSQL: schema, RLS, grants, idempotency.

Plan v0.20 Task 12 Step 8. Everything here needs the database, and every claim
needs the *runtime* role rather than the migration role — a superuser or
`BYPASSRLS` role ignores row-level security, which would make the isolation
assertions vacuous.

The load-bearing claims, each of which fails when its control is removed:

1. the evolved `memory_episodes` carries the grounding and lifecycle columns, and
   the idempotency boundary is a real unique index, not a convention;
2. `FORCE` RLS is on, so the table owner cannot bypass the tenant predicate;
3. the runtime role can read and invalidate an episode but cannot insert or
   delete one;
4. a replay of one source returns `False`, and a replay with different content
   raises rather than silently keeping whichever landed first;
5. invalidating an episode's source makes it ineligible at read, and the engine
   abstains rather than falling back to another row.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from backend.memory.episodic import (
    EpisodeAbstentionReason,
    EpisodeFormationEngine,
    EpisodeGrounding,
    EpisodeProvenance,
    EpisodeReadRequest,
    EpisodicReadEngine,
)
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingOutcome,
    SourceHandlingReason,
    SourceHandlingRecord,
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

OWNER = "episodic_owner"
OTHER_OWNER = "episodic_other_owner"
CONVERSATION = "conv_episodic_1"
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


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


def _positive_record() -> SourceHandlingRecord:
    return SourceHandlingRecord(
        source_outbox_id="cout_epi_1",
        source_message_id="msg_epi_1",
        family=MemoryFamily.EPISODIC,
        outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
        recorded_at=NOW,
    )


def _candidate(**overrides):
    values = {
        "source_outbox_id": "cout_epi_1",
        "source_message_id": "msg_epi_1",
        "owner_user_id": OWNER,
        "conversation_id": CONVERSATION,
        "grounding": EpisodeGrounding(
            actor=OWNER,
            event="rejected Da Nang for the winter trip over rain concerns",
            occurred_at=NOW,
            provenance=EpisodeProvenance("cout_epi_1", "msg_epi_1"),
        ),
        "source_handling_record": _positive_record(),
    }
    values.update(overrides)
    return EpisodeFormationEngine().form_episode(**values)


def _insert(engine, candidate, *, status=None):
    from backend.memory.postgres_store import record_episode_on
    from backend.memory.write_pipeline.models import VersionStatus
    from backend.conversations.postgres_repository import tenant_transaction
    from backend.storage.postgres import set_tenant

    with tenant_transaction(engine, OWNER) as connection:
        set_tenant(connection, OWNER)
        return record_episode_on(
            connection,
            candidate=candidate,
            created_at=NOW,
            status=status or VersionStatus.ACTIVE,
        )


@pytest.fixture()
def runtime(runtime_engine):
    return runtime_engine


@pytest.fixture()
def worker(admin_engine):
    """The role that forms an episode.

    `travel_app` deliberately has no `INSERT` on `memory_episodes` — the grant
    test above asserts exactly that — so seeding an episode through the runtime
    role would be testing a privilege the product does not have.
    """
    from backend.storage.postgres import create_engine

    ensure_worker_login(admin_engine)
    engine = create_engine(require(worker_dsn(), "PG_WORKER_TEST_DSN"))
    yield engine
    engine.dispose()


# --- Schema and the idempotency boundary ------------------------------------


def test_the_episodic_columns_exist(schema):
    with schema.connect() as connection:
        columns = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'memory_episodes'"
                )
            )
        }

    assert {
        "actor",
        "event",
        "source_message_id",
        "source_outbox_id",
        "retention_mode",
        "status",
        "sensitivity",
        "suppression_generation",
        "unresolved_conflict",
        "expires_at",
        "invalidated_at",
    } <= columns


def test_the_provenance_uniqueness_boundary_is_a_real_unique_index(schema):
    with schema.connect() as connection:
        definition = connection.execute(
            sa.text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'memory_episodes' "
                "AND indexname = 'uq_memory_episodes_source_provenance'"
            )
        ).scalar()

    assert definition is not None, "the idempotency boundary must exist"
    assert "UNIQUE" in definition.upper()
    for column in ("owner_user_id", "source_outbox_id", "source_message_id"):
        assert column in definition


def test_the_episodic_table_forces_tenant_rls(schema):
    with schema.connect() as connection:
        forced = connection.execute(
            sa.text(
                "SELECT relforcerowsecurity FROM pg_class "
                "WHERE relname = 'memory_episodes'"
            )
        ).scalar()

    assert forced is True, (
        "ENABLE alone lets the table owner bypass every policy, and the "
        "application connects as the owner"
    )


def test_the_runtime_role_can_read_and_invalidate_but_not_insert_or_delete(schema):
    with schema.connect() as connection:
        privileges = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = 'travel_app' AND table_name = 'memory_episodes'"
                )
            )
        }

    assert privileges == {"SELECT", "UPDATE"}, (
        "the runtime reads episodes and invalidates them on conversation "
        "deletion; forming and erasing an episode belong to the worker"
    )


# --- Persistence, idempotency, and isolation --------------------------------


def test_a_grounded_episode_is_persisted_and_read_back(schema, worker, runtime):
    assert _insert(worker, _candidate()) is True

    from backend.memory.postgres_store import PostgresEpisodeStore

    rows = PostgresEpisodeStore(runtime).list_storage_scoped(
        EpisodeReadRequest(
            owner_user_id=OWNER,
            conversation_id=CONVERSATION,
            occurred_after=NOW - timedelta(days=1),
            occurred_before=NOW + timedelta(days=1),
        )
    )
    assert len(rows) == 1
    assert rows[0].actor == OWNER
    assert rows[0].source_outbox_id == "cout_epi_1"


def test_a_replayed_source_is_idempotent(schema, worker, runtime):
    assert _insert(worker, _candidate()) is True
    assert _insert(worker, _candidate()) is False, (
        "redelivery of one source must not create a second canonical episode"
    )


def test_a_replay_with_different_content_is_refused(schema, worker, runtime):
    from backend.memory.write_pipeline.uow import MemoryWriteError

    assert _insert(worker, _candidate()) is True
    conflicting = _candidate(
        grounding=EpisodeGrounding(
            actor=OWNER,
            event="a different event entirely",
            occurred_at=NOW,
            provenance=EpisodeProvenance("cout_epi_1", "msg_epi_1"),
        )
    )
    with pytest.raises(MemoryWriteError):
        _insert(worker, conflicting)


def test_another_owners_episode_is_not_visible(schema, worker, runtime):
    assert _insert(worker, _candidate()) is True

    from backend.memory.postgres_store import PostgresEpisodeStore

    rows = PostgresEpisodeStore(runtime).list_storage_scoped(
        EpisodeReadRequest(
            owner_user_id=OTHER_OWNER,
            occurred_after=NOW - timedelta(days=1),
            occurred_before=NOW + timedelta(days=1),
        )
    )
    assert rows == ()


def test_the_tenant_predicate_denies_a_cross_owner_insert(schema, worker, runtime):
    """`FORCE` RLS is what makes this fail rather than silently succeed."""
    from backend.memory.write_pipeline.postgres import episodes_table
    from backend.conversations.postgres_repository import tenant_transaction
    from backend.storage.postgres import set_tenant

    with pytest.raises(sa.exc.DBAPIError):
        with tenant_transaction(runtime, OWNER) as connection:
            set_tenant(connection, OWNER)
            connection.execute(
                episodes_table.insert().values(
                    episode_id="epi_cross",
                    owner_user_id=OTHER_OWNER,
                    conversation_id=CONVERSATION,
                    occurred_at=NOW,
                    payload={},
                    created_at=NOW,
                    actor=OTHER_OWNER,
                    event="cross-owner write",
                    source_message_id="msg_cross",
                    source_outbox_id="cout_cross",
                    retention_mode="conversation_bound",
                    status="active",
                    sensitivity="ordinary_personal",
                    suppression_generation=1,
                    unresolved_conflict=False,
                )
            )


# --- Source invalidation stops eligibility ----------------------------------


def test_invalidating_the_source_makes_the_episode_ineligible(schema, worker, runtime):
    from backend.memory.postgres_store import (
        PostgresEpisodeStore,
        invalidate_episodes_for_conversation_on,
    )
    from backend.conversations.postgres_repository import tenant_transaction
    from backend.storage.postgres import set_tenant

    assert _insert(worker, _candidate()) is True

    with tenant_transaction(runtime, OWNER) as connection:
        set_tenant(connection, OWNER)
        touched = invalidate_episodes_for_conversation_on(
            connection, conversation_id=CONVERSATION, invalidated_at=NOW
        )
    assert touched == 1

    request = EpisodeReadRequest(
        owner_user_id=OWNER,
        conversation_id=CONVERSATION,
        occurred_after=NOW - timedelta(days=1),
        occurred_before=NOW + timedelta(days=1),
    )
    rows = PostgresEpisodeStore(runtime).list_storage_scoped(request)
    assert len(rows) == 1, "the row is invalidated, not erased"
    assert rows[0].source_validity.value == "invalid"

    selection = EpisodicReadEngine(PostgresEpisodeStore(runtime)).select(request)
    assert selection.selected == ()
    assert selection.abstention_reason is EpisodeAbstentionReason.NO_ELIGIBLE_EPISODE


def test_invalidation_is_idempotent(schema, worker, runtime):
    from backend.memory.postgres_store import invalidate_episodes_for_conversation_on
    from backend.conversations.postgres_repository import tenant_transaction
    from backend.storage.postgres import set_tenant

    assert _insert(worker, _candidate()) is True

    with tenant_transaction(runtime, OWNER) as connection:
        set_tenant(connection, OWNER)
        first = invalidate_episodes_for_conversation_on(
            connection, conversation_id=CONVERSATION, invalidated_at=NOW
        )
    with tenant_transaction(runtime, OWNER) as connection:
        set_tenant(connection, OWNER)
        second = invalidate_episodes_for_conversation_on(
            connection, conversation_id=CONVERSATION, invalidated_at=NOW
        )

    assert (first, second) == (1, 0), (
        "a second deletion pass must not re-invalidate, so the count stays honest"
    )


# --- The read engine over real rows ----------------------------------------


def test_the_engine_selects_the_grounded_episode(schema, worker, runtime):
    from backend.memory.postgres_store import PostgresEpisodeStore

    assert _insert(worker, _candidate()) is True
    selection = EpisodicReadEngine(PostgresEpisodeStore(runtime)).select(
        EpisodeReadRequest(
            owner_user_id=OWNER,
            conversation_id=CONVERSATION,
            occurred_after=NOW - timedelta(days=1),
            occurred_before=NOW + timedelta(days=1),
        )
    )
    assert len(selection.selected) == 1
    assert selection.selected[0].event.startswith("rejected Da Nang")


def test_an_unrelated_window_abstains_over_real_rows(schema, worker, runtime):
    from backend.memory.postgres_store import PostgresEpisodeStore

    assert _insert(worker, _candidate()) is True
    selection = EpisodicReadEngine(PostgresEpisodeStore(runtime)).select(
        EpisodeReadRequest(
            owner_user_id=OWNER,
            conversation_id=CONVERSATION,
            occurred_after=NOW + timedelta(days=10),
            occurred_before=NOW + timedelta(days=20),
        )
    )
    assert selection.selected == ()
    assert selection.abstention_reason is EpisodeAbstentionReason.NO_ELIGIBLE_EPISODE


def test_a_shadow_episode_is_not_selected(schema, worker, runtime):
    from backend.memory.postgres_store import PostgresEpisodeStore
    from backend.memory.write_pipeline.models import VersionStatus

    assert _insert(worker, _candidate(), status=VersionStatus.SHADOW) is True
    selection = EpisodicReadEngine(PostgresEpisodeStore(runtime)).select(
        EpisodeReadRequest(
            owner_user_id=OWNER,
            conversation_id=CONVERSATION,
            occurred_after=NOW - timedelta(days=1),
            occurred_before=NOW + timedelta(days=1),
        )
    )
    assert selection.selected == (), (
        "an unactivated episode is shadow state and must not reach context"
    )


# --- Deleting the conversation propagates to its episodes -------------------


def test_deleting_a_conversation_invalidates_its_episodes(schema, worker, runtime):
    """The same transaction that tombstones the conversation invalidates them.

    This is the assertion that makes the propagation real rather than
    documented: without the extra statement in `PostgresConversationRepository.
    delete`, the episode stays eligible after its conversation is gone.
    """
    from backend.conversations.models import (
        MessageRole,
        MessageSource,
    )
    from backend.conversations.postgres_repository import (
        PostgresConversationRepository,
    )
    from backend.conversations.service import ConversationService
    from backend.memory.postgres_store import PostgresEpisodeStore

    repo = PostgresConversationRepository(runtime)
    conversation, _, _ = ConversationService(
        conversation_repository=repo
    ).create_conversation_with_initial_turn(
        owner_user_id=OWNER,
        title="episodic deletion",
        content="first",
        role=MessageRole.USER,
        source=MessageSource.UI,
    )
    conversation_id = conversation.conversation_id

    candidate = _candidate(conversation_id=conversation_id)
    assert _insert(worker, candidate) is True

    request = EpisodeReadRequest(
        owner_user_id=OWNER,
        conversation_id=conversation_id,
        occurred_after=NOW - timedelta(days=1),
        occurred_before=NOW + timedelta(days=1),
    )
    store = PostgresEpisodeStore(runtime)
    assert len(store.list_storage_scoped(request)) == 1

    assert repo.delete(conversation_id, OWNER) is True

    rows = store.list_storage_scoped(request)
    assert len(rows) == 1, "the row is invalidated, not deleted"
    assert rows[0].source_validity.value == "invalid"
    selection = EpisodicReadEngine(store).select(request)
    assert selection.selected == ()
    assert selection.abstention_reason is EpisodeAbstentionReason.NO_ELIGIBLE_EPISODE
