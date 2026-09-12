"""ADR 0027 and ADR 0028: who may claim, and only once the turn is terminal.

These tests run against the isolated disposable PostgreSQL addressed by
`PG_TEST_DSN` (DDL role), `PG_RUNTIME_TEST_DSN` (least-privilege runtime role)
and, for the claim boundary, the worker role resolved by `worker_dsn()`. When
the DSNs are unset the module skips distinctly rather than pretending to be green.

Two defects are covered here, and they are independent.

**ADR 0027 — when an event becomes claimable.** Phase one committed the user
message, the `pending` assistant row and a claimable outbox event together, so a
worker could claim the event while generation was still running, and the
failure-path cancellation could not undo a claim that had already happened.

**ADR 0028 — who may claim it.** `conversation_outbox` carries a tenant policy
and is not force-enabled, so it binds every role except its owner. The runtime
role bound no tenant on the claim path and therefore saw zero rows: the queue
read as empty rather than unreadable. The worker role now carries a policy that
admits it to the queue, and every read that follows a claim is tenant-bound.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from backend.storage.postgres import ALEMBIC_HEAD
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

MIGRATIONS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "storage" / "migrations"
)

OWNER = "readiness_owner"
WORKER = "readiness_worker"
MOMENT = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)


def _alembic_config(dsn: str) -> Config:
    from backend.storage.postgres import alembic_config

    return alembic_config(str(MIGRATIONS_DIR), dsn)


@pytest.fixture(scope="module")
def admin_engine():
    from backend.storage.postgres import create_engine

    engine = create_engine(require(migration_dsn(), "PG_TEST_DSN"))
    yield engine
    engine.dispose()


@pytest.fixture()
def schema(admin_engine):
    """A fresh schema at head, so each test starts from the real migration state."""
    from alembic import command

    with admin_engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    command.upgrade(_alembic_config(require(migration_dsn(), "PG_TEST_DSN")), "head")
    return admin_engine


@pytest.fixture()
def runtime_engine():
    """The least-privilege role, which is the one the application actually uses."""
    from backend.storage.postgres import create_engine

    engine = create_engine(require(runtime_dsn(), "PG_RUNTIME_TEST_DSN"))
    yield engine
    engine.dispose()


@pytest.fixture()
def worker_engine(admin_engine):
    """The worker role, which carries the cross-owner claim policy.

    The migration creates `travel_worker` `NOLOGIN` on purpose; the credential is
    provisioned here the same way `docker/postgres/init-app-role.sh` provisions it
    in a deployment, so the boundary is proved against the real role rather than a
    stand-in.
    """
    from backend.storage.postgres import create_engine

    ensure_worker_login(admin_engine)
    engine = create_engine(require(worker_dsn(), "PG_WORKER_TEST_DSN"))
    yield engine
    engine.dispose()


def _repository(engine):
    from backend.conversations.postgres_repository import PostgresConversationRepository

    return PostgresConversationRepository(engine)


def _service(engine):
    from backend.conversations.service import ConversationService

    return ConversationService(conversation_repository=_repository(engine))


def _outbox(engine):
    from backend.memory.write_pipeline.outbox import PostgresOutboxRepository

    return PostgresOutboxRepository(engine)


def _new_conversation(service):
    from backend.conversations.models import MessageRole, MessageSource

    conversation, _, _ = service.create_conversation_with_initial_turn(
        owner_user_id=OWNER,
        title="readiness probe",
        content="first",
        role=MessageRole.USER,
        source=MessageSource.UI,
    )
    return conversation


def _append_turn(repo, conversation_id: str, content: str):
    from backend.conversations.models import OutboxIntent

    return repo.append_turn(
        conversation_id=conversation_id,
        owner_user_id=OWNER,
        user_content=content,
        outbox_event=OutboxIntent(
            event_type="memory.extract.conversation_range",
            payload={"conversation_id": conversation_id},
        ),
    )


def _outbox_row(engine, conversation_id: str):
    with engine.connect() as connection:
        return connection.execute(
            sa.text(
                "SELECT status, released_at, payload FROM conversation_outbox "
                "WHERE conversation_id = :c"
            ),
            {"c": conversation_id},
        ).fetchone()


def _claim(engine) -> list:
    """Claim through the real repository, normalised to a list for assertions.

    `claim_batch` returns a `Sequence`, so comparing it to `[]` would fail for a
    reason that has nothing to do with the gate.

    The engine decides the identity, and that is the point of the parameter. The
    ADR 0027 gate tests pass the DDL role so they isolate the gate; the ADR 0028
    boundary tests pass the worker or runtime engine, where the policy itself is
    what is under test.
    """
    return list(
        _outbox(engine).claim_batch(
            lease_owner=WORKER,
            lease_duration_seconds=30.0,
            limit=10,
        )
    )


# 1. Allocation must write a blocked event.


def test_allocation_writes_a_blocked_event(schema, runtime_engine):
    service = _service(runtime_engine)
    repo = _repository(runtime_engine)
    conversation = _new_conversation(service)

    _append_turn(repo, conversation.conversation_id, "I prefer quiet hotels")

    row = _outbox_row(schema, conversation.conversation_id)
    assert row is not None
    assert row[0] == "pending"
    assert row[1] is None, "a newly allocated event must be blocked"


# 2. The defect: a blocked event must not be claimable while the turn is unfinished.


def test_a_blocked_event_is_not_claimable_while_the_turn_is_pending(
    schema, runtime_engine
):
    service = _service(runtime_engine)
    repo = _repository(runtime_engine)
    conversation = _new_conversation(service)

    _, pending = _append_turn(repo, conversation.conversation_id, "quiet hotels")

    with schema.connect() as connection:
        status = connection.execute(
            sa.text("SELECT status FROM messages WHERE message_id = :m"),
            {"m": pending.message_id},
        ).scalar()
    assert status == "pending", "precondition: the assistant row is still pending"

    assert _claim(schema) == [], (
        "a worker must not be able to claim an event whose turn is unfinished"
    )


# 3. Completion releases the event, in the same transaction.


def test_completing_the_turn_releases_the_event(schema, runtime_engine):
    service = _service(runtime_engine)
    repo = _repository(runtime_engine)
    conversation = _new_conversation(service)

    _, pending = _append_turn(repo, conversation.conversation_id, "quiet hotels")
    repo.complete_turn(
        conversation_id=conversation.conversation_id,
        message_id=pending.message_id,
        owner_user_id=OWNER,
        content="Here are some quiet hotels.",
    )

    row = _outbox_row(schema, conversation.conversation_id)
    assert row[1] is not None, "a completed turn must release its event"

    claimed = _claim(schema)
    assert len(claimed) == 1
    assert claimed[0].conversation_id == conversation.conversation_id


# 4. Release is idempotent: a second completion must not move the timestamp.


def test_release_is_idempotent(schema, runtime_engine):
    service = _service(runtime_engine)
    repo = _repository(runtime_engine)
    conversation = _new_conversation(service)

    _, pending = _append_turn(repo, conversation.conversation_id, "quiet hotels")
    repo.complete_turn(
        conversation_id=conversation.conversation_id,
        message_id=pending.message_id,
        owner_user_id=OWNER,
        content="first reply",
    )
    first = _outbox_row(schema, conversation.conversation_id)[1]

    repo.complete_turn(
        conversation_id=conversation.conversation_id,
        message_id=pending.message_id,
        owner_user_id=OWNER,
        content="second reply",
    )
    second = _outbox_row(schema, conversation.conversation_id)[1]

    assert first == second, "a repeat completion must not move the release time"


# 5. Failure cancels, and the event is never claimable.


def test_failing_the_turn_cancels_and_never_releases(schema, runtime_engine):
    service = _service(runtime_engine)
    repo = _repository(runtime_engine)
    conversation = _new_conversation(service)

    _, pending = _append_turn(repo, conversation.conversation_id, "quiet hotels")
    repo.fail_turn(conversation.conversation_id, pending.message_id, OWNER)

    row = _outbox_row(schema, conversation.conversation_id)
    assert row[0] == "cancelled"
    assert row[1] is None, "a cancelled event must not be released"
    assert _claim(schema) == []


# 6. Allocation stamps the cursor, so a turn reads its own range only.


def test_allocation_stamps_the_cursor(schema, runtime_engine):
    service = _service(runtime_engine)
    repo = _repository(runtime_engine)
    conversation = _new_conversation(service)

    user_message, _ = _append_turn(repo, conversation.conversation_id, "quiet hotels")

    payload = _outbox_row(schema, conversation.conversation_id)[2]
    assert payload["after_sequence"] == user_message.sequence - 1, (
        "the event must bound the worker's read to this turn"
    )


# 7. The worker's read filter, against real persisted rows.


def test_worker_read_excludes_non_terminal_rows(schema, runtime_engine):
    from backend.memory.write_pipeline.worker import MemoryOutboxWorker

    service = _service(runtime_engine)
    repo = _repository(runtime_engine)
    conversation = _new_conversation(service)

    _, pending = _append_turn(repo, conversation.conversation_id, "quiet hotels")

    worker = MemoryOutboxWorker.__new__(MemoryOutboxWorker)
    worker._conversation_service = service

    loaded = worker._load_messages(conversation.conversation_id, OWNER)
    assert pending.message_id not in [m["message_id"] for m in loaded], (
        "a pending assistant row must not reach the extraction model"
    )
    assert all(m.get("content") for m in loaded), (
        "no empty placeholder may reach the extraction model"
    )

    # After completion the same read includes the finished reply.
    repo.complete_turn(
        conversation_id=conversation.conversation_id,
        message_id=pending.message_id,
        owner_user_id=OWNER,
        content="Here are some quiet hotels.",
    )
    loaded_after = worker._load_messages(conversation.conversation_id, OWNER)
    assert pending.message_id in [m["message_id"] for m in loaded_after]


# 8. A leased event whose turn is unfinished is not reclaimable on lease expiry.


def test_a_blocked_event_is_not_reclaimable_after_lease_expiry(schema, runtime_engine):
    """The gate applies to the lease-expiry branch too, not only to `pending`."""
    service = _service(runtime_engine)
    repo = _repository(runtime_engine)
    conversation = _new_conversation(service)
    _append_turn(repo, conversation.conversation_id, "quiet hotels")

    # Force the row into the shape a pre-fix worker could have left behind.
    with schema.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE conversation_outbox SET status = 'leased', "
                "lease_owner = :o, lease_until = :u WHERE conversation_id = :c"
            ),
            {
                "o": "stale_worker",
                "u": datetime.now(timezone.utc) - timedelta(minutes=5),
                "c": conversation.conversation_id,
            },
        )

    assert _claim(schema) == [], (
        "an unfinished turn's event must stay invisible even after a lease expires"
    )


# 9. The single-event claim path is gated too, not only the batch path.


def test_claim_event_requires_the_gate(schema, runtime_engine):
    """`claim_event` and `claim_batch` must agree; a gate on one alone is a hole."""
    service = _service(runtime_engine)
    repo = _repository(runtime_engine)
    conversation = _new_conversation(service)

    _, pending = _append_turn(repo, conversation.conversation_id, "quiet hotels")
    outbox_repo = _outbox(schema)

    with schema.connect() as connection:
        outbox_id = connection.execute(
            sa.text(
                "SELECT outbox_id FROM conversation_outbox WHERE conversation_id = :c"
            ),
            {"c": conversation.conversation_id},
        ).scalar()

    assert (
        outbox_repo.claim_event(
            outbox_id=outbox_id,
            lease_owner=WORKER,
            lease_duration_seconds=30.0,
        )
        is None
    ), "a blocked event must not be claimable through claim_event either"

    repo.complete_turn(
        conversation_id=conversation.conversation_id,
        message_id=pending.message_id,
        owner_user_id=OWNER,
        content="Here are some quiet hotels.",
    )

    claimed = outbox_repo.claim_event(
        outbox_id=outbox_id,
        lease_owner=WORKER,
        lease_duration_seconds=30.0,
    )
    assert claimed is not None, "a released event is claimable through claim_event"


# 10. ADR 0028: the claim boundary. Who may claim, and what may be read after.


def _released_event(runtime_engine, schema):
    """One conversation with a completed turn, so its event is released."""
    service = _service(runtime_engine)
    repo = _repository(runtime_engine)
    conversation = _new_conversation(service)
    _, pending = _append_turn(repo, conversation.conversation_id, "quiet hotels")
    repo.complete_turn(
        conversation_id=conversation.conversation_id,
        message_id=pending.message_id,
        owner_user_id=OWNER,
        content="Here are some quiet hotels.",
    )
    assert _outbox_row(schema, conversation.conversation_id)[1] is not None, (
        "the turn completed, so the event must be released"
    )
    return conversation


def test_the_worker_role_claims_a_released_event(schema, runtime_engine, worker_engine):
    """The defect this replaces: the worker claimed nothing, under any role.

    Before ADR 0028 the claim returned `()` for every least-privilege role,
    because `conversation_outbox` binds a tenant policy the claim path cannot
    satisfy. The worker role carries a policy that admits it to the queue.
    """
    _released_event(runtime_engine, schema)

    claimed = _claim(worker_engine)
    assert len(claimed) == 1, (
        "the worker role must claim a released event across owners"
    )
    assert claimed[0].owner_user_id == OWNER
    assert claimed[0].status.value == "leased"


def test_the_runtime_role_cannot_claim_an_outbox_event(schema, runtime_engine):
    """The API role must not be able to drain the queue. This is the boundary.

    Asserted, not merely tolerated: `travel_app` holds no policy admitting it to
    `conversation_outbox`, so the claim is refused by the database rather than by
    a convention in the application.
    """
    _released_event(runtime_engine, schema)

    assert _claim(runtime_engine) == [], (
        "the runtime role holds no policy admitting it to conversation_outbox"
    )
    with runtime_engine.connect() as connection:
        visible = connection.execute(
            sa.text("SELECT count(*) FROM conversation_outbox")
        ).scalar()
    assert visible == 0


def test_the_worker_role_cannot_claim_an_unreleased_event(
    schema, runtime_engine, worker_engine
):
    """ADR 0027's gate still applies to the worker; ADR 0028 did not relax it."""
    service = _service(runtime_engine)
    repo = _repository(runtime_engine)
    conversation = _new_conversation(service)
    _append_turn(repo, conversation.conversation_id, "quiet hotels")

    assert _outbox_row(schema, conversation.conversation_id)[1] is None
    assert _claim(worker_engine) == [], (
        "an unreleased event must stay invisible to the worker too"
    )


def test_the_worker_role_cannot_read_a_transcript_without_binding_a_tenant(
    schema, runtime_engine, worker_engine
):
    """The cross-owner grant is confined to the queue, not extended to content.

    `conversations` and `messages` are force-enabled, so the worker is subject to
    their tenant policy and reads nothing until it binds `app.tenant`.
    """
    _new_conversation(_service(runtime_engine))

    with worker_engine.connect() as connection:
        assert (
            connection.execute(sa.text("SELECT count(*) FROM messages")).scalar()
            == 0
        )
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM conversations")
            ).scalar()
            == 0
        )


def test_the_worker_role_reads_the_claimed_owners_transcript_once_bound(
    schema, runtime_engine, worker_engine
):
    """Binding the claimed owner is what makes the transcript readable."""
    from backend.storage.postgres import require_tenant_context, set_tenant

    conversation = _new_conversation(_service(runtime_engine))

    with worker_engine.connect() as connection:
        with connection.begin():
            set_tenant(connection, OWNER)
            assert require_tenant_context(connection) == OWNER
            own = connection.execute(
                sa.text("SELECT count(*) FROM messages WHERE conversation_id = :c"),
                {"c": conversation.conversation_id},
            ).scalar()
    assert own >= 1, "the claimed owner's transcript is readable once bound"

    with worker_engine.connect() as connection:
        with connection.begin():
            set_tenant(connection, "some_other_owner")
            foreign = connection.execute(
                sa.text("SELECT count(*) FROM messages WHERE conversation_id = :c"),
                {"c": conversation.conversation_id},
            ).scalar()
    assert foreign == 0, "binding a different tenant reads nothing"


# 11. The migration reaches the expected head.


def test_migration_head_is_the_latest_revision(schema):
    from alembic.migration import MigrationContext

    with schema.connect() as connection:
        heads = MigrationContext.configure(connection).get_current_heads()
    assert heads == (ALEMBIC_HEAD,)
    # Pinned so an accidental change to the constant without a matching
    # migration fails here rather than silently reporting readiness for a
    # revision the database is not on.
    #
    # Bumped by 20260912_01 (backlog-age and dead-letter signals) and by
    # 20260912_02, which narrowed the worker's outbox UPDATE to the claim
    # path's eight columns. See `test_postgres_migrations.py` for the grant
    # assertions.
    assert ALEMBIC_HEAD == "20260912_02"


# 12. ADR 0030: claiming is serialised per conversation.
#
# Before this, two workers selecting *different* rows of one conversation locked
# different rows and never blocked, so both claimed. `active_lease_exists` is a
# read-time predicate and `FOR UPDATE SKIP LOCKED` locks only the rows selected.


def _two_released_events(runtime_engine, schema):
    """One conversation with two completed turns, so two events are released."""
    service = _service(runtime_engine)
    repo = _repository(runtime_engine)
    conversation = _new_conversation(service)
    for text in ("first turn", "second turn"):
        _, pending = _append_turn(repo, conversation.conversation_id, text)
        repo.complete_turn(
            conversation_id=conversation.conversation_id,
            message_id=pending.message_id,
            owner_user_id=OWNER,
            content="a reply",
        )
    with schema.connect() as connection:
        ready = connection.execute(
            sa.text(
                "SELECT count(*) FROM conversation_outbox WHERE conversation_id = :c "
                "AND status = 'pending' AND released_at IS NOT NULL"
            ),
            {"c": conversation.conversation_id},
        ).scalar()
    assert ready == 2, f"expected two released events, found {ready}"
    return conversation


def test_the_claim_lock_is_exclusive_across_transactions(schema, worker_engine):
    """The mechanism itself, with the claim path out of the way."""
    from backend.memory.write_pipeline.outbox import PostgresOutboxRepository

    repo = PostgresOutboxRepository(worker_engine)
    first = worker_engine.connect()
    second = worker_engine.connect()
    t1, t2 = first.begin(), second.begin()
    try:
        held = repo._lock_conversations(first, ["conv_alpha", "conv_beta"])
        contested = repo._lock_conversations(second, ["conv_alpha", "conv_beta"])

        assert held == ["conv_alpha", "conv_beta"], "the first transaction holds both"
        assert contested == [], "a second transaction cannot take a held lock"
    finally:
        t1.rollback()
        first.close()
        t2.rollback()
        second.close()


def test_a_conversation_under_an_advisory_lock_is_not_claimed(
    schema, runtime_engine, worker_engine
):
    """A conversation another transaction is claiming is skipped, not doubled."""
    from backend.memory.write_pipeline.outbox import PostgresOutboxRepository

    conversation = _two_released_events(runtime_engine, schema)
    cid = conversation.conversation_id

    holder = worker_engine.connect()
    tx = holder.begin()
    acquired = holder.execute(
        sa.text("SELECT pg_try_advisory_xact_lock(hashtextextended(:c, 0))"),
        {"c": cid},
    ).scalar()
    assert acquired is True, "the probe transaction took the lock"

    blocked = list(
        PostgresOutboxRepository(worker_engine).claim_batch(
            lease_owner="blocked_worker",
            lease_duration_seconds=30.0,
            limit=10,
        )
    )
    assert blocked == [], "a conversation under another transaction's lock is skipped"

    tx.commit()
    holder.close()

    after = list(
        PostgresOutboxRepository(worker_engine).claim_batch(
            lease_owner="next_worker",
            lease_duration_seconds=30.0,
            limit=10,
        )
    )
    assert len(after) == 1, "once the lock is released the conversation is claimable"
