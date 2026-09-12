"""ADR 0032: the database clock is the sole authority for lease validity.

These tests run against the isolated disposable PostgreSQL addressed by
`PG_TEST_DSN` (DDL role), `PG_RUNTIME_TEST_DSN` (least-privilege runtime role) and
the worker role resolved by `worker_dsn()`. When the DSNs are unset the module skips
distinctly rather than pretending to be green.

The defect these cover: `process_one` captured `now = utc_now()` once at entry and
reused it for every terminal mutation, including three `mark_failed` calls that run
*after* an unbounded model call. The repository compared `lease_until` against that
caller-supplied value, so a lease that had already expired was reported as held. The
party being judged was choosing the clock.

Two consequences are asserted here, and they are different:

1. **A stale timestamp cannot extend a lease.** An expired lease is refused by
   `mark_succeeded`, refused by `mark_failed`, and reclaimed by `claim_batch` — all
   judged by `now()` in the statement that reads the row.
2. **A caller cannot supply a time authority at all.** The `now` parameter is gone
   from the Postgres repository, so this is structural rather than conventional.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

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

OWNER = "lease_authority_owner"
WORKER_ONE = "lease_worker_one"
WORKER_TWO = "lease_worker_two"


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

    from backend.storage.postgres import alembic_config

    with admin_engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    migrations = (
        Path(__file__).resolve().parent.parent.parent / "storage" / "migrations"
    )
    command.upgrade(
        alembic_config(str(migrations), require(migration_dsn(), "PG_TEST_DSN")), "head"
    )
    return admin_engine


@pytest.fixture()
def runtime_engine():
    from backend.storage.postgres import create_engine

    engine = create_engine(require(runtime_dsn(), "PG_RUNTIME_TEST_DSN"))
    yield engine
    engine.dispose()


@pytest.fixture()
def worker_engine(admin_engine):
    """The worker role, which carries the cross-owner claim policy."""
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


def _released_event(runtime_engine):
    """One conversation whose turn is complete, so its outbox event is released."""
    from backend.conversations.models import (
        MessageRole,
        MessageSource,
        OutboxIntent,
    )

    service = _service(runtime_engine)
    repo = _repository(runtime_engine)
    conversation, _, _ = service.create_conversation_with_initial_turn(
        owner_user_id=OWNER,
        title="lease authority",
        content="first",
        role=MessageRole.USER,
        source=MessageSource.UI,
    )
    _, pending = repo.append_turn(
        conversation_id=conversation.conversation_id,
        owner_user_id=OWNER,
        user_content="quiet hotels",
        outbox_event=OutboxIntent(
            event_type="memory.extract.conversation_range",
            payload={"conversation_id": conversation.conversation_id},
        ),
    )
    repo.complete_turn(
        conversation_id=conversation.conversation_id,
        message_id=pending.message_id,
        owner_user_id=OWNER,
        content="Here are some quiet hotels.",
    )
    return conversation


def _claim(engine, owner: str, duration: float = 30.0):
    return list(
        _outbox(engine).claim_batch(
            lease_owner=owner, lease_duration_seconds=duration, limit=10
        )
    )


def _outbox_id(engine, conversation_id: str) -> str:
    with engine.connect() as connection:
        return connection.execute(
            sa.text(
                "SELECT outbox_id FROM conversation_outbox WHERE conversation_id = :c"
            ),
            {"c": conversation_id},
        ).scalar()


def _row(engine, outbox_id: str):
    with engine.connect() as connection:
        return connection.execute(
            sa.text(
                "SELECT status, lease_owner, lease_until, attempt_count, last_error "
                "FROM conversation_outbox WHERE outbox_id = :o"
            ),
            {"o": outbox_id},
        ).mappings().fetchone()


def _expire(engine, outbox_id: str) -> None:
    """Expire a lease by moving its window into the past, using database time.

    Deliberately a direct `UPDATE` rather than a fabricated timestamp passed to the
    repository: after ADR 0032 there is no parameter through which a caller can say
    what "now" is, so a test that wants an expired lease must change the row.
    """
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE conversation_outbox SET lease_until = now() - interval '5 minutes' "
                "WHERE outbox_id = :o"
            ),
            {"o": outbox_id},
        )


# --- 1. The window is written by the database ---------------------------------


def test_the_lease_window_is_the_requested_duration(schema, runtime_engine, worker_engine):
    """`make_interval` arithmetic must actually run server-side.

    A `func.make_interval(secs=…)` call renders `=` notation, which PostgreSQL
    rejects; this asserts the interval is real rather than assuming the expression
    compiled.
    """
    conversation = _released_event(runtime_engine)
    claimed = _claim(worker_engine, WORKER_ONE, duration=30.0)
    assert len(claimed) == 1

    with worker_engine.connect() as connection:
        remaining = connection.execute(
            sa.text(
                "SELECT EXTRACT(EPOCH FROM (lease_until - now())) "
                "FROM conversation_outbox WHERE conversation_id = :c"
            ),
            {"c": conversation.conversation_id},
        ).scalar()

    assert 28.0 <= float(remaining) <= 30.0, (
        f"a 30s lease must be about 30s from database now(), not {remaining}"
    )


# --- 2. A stale timestamp cannot extend a lease -------------------------------


def test_an_expired_lease_is_refused_by_mark_succeeded(
    schema, runtime_engine, worker_engine
):
    """The defect: an expired lease was reported as held."""
    conversation = _released_event(runtime_engine)
    claimed = _claim(worker_engine, WORKER_ONE)
    outbox_id = claimed[0].outbox_id
    _expire(schema, outbox_id)

    succeeded = _outbox(worker_engine).mark_succeeded(
        outbox_id, lease_owner=WORKER_ONE
    )

    assert succeeded is False, "an expired lease must not be able to commit success"
    assert _row(worker_engine, outbox_id)["status"] == "leased"


def test_an_expired_lease_is_refused_by_mark_failed(schema, runtime_engine, worker_engine):
    """`mark_failed` had the same hole and a longer window: it runs after the model."""
    from backend.memory.write_pipeline.outbox import OutboxStatus

    conversation = _released_event(runtime_engine)
    claimed = _claim(worker_engine, WORKER_ONE)
    outbox_id = claimed[0].outbox_id
    _expire(schema, outbox_id)

    returned = _outbox(worker_engine).mark_failed(
        outbox_id,
        lease_owner=WORKER_ONE,
        error_message="transient",
        retryable=True,
        max_attempts=3,
        backoff_seconds=5.0,
    )

    assert returned is OutboxStatus.LEASED, (
        "a caller that lost the lease must be told the truth, not overwrite the row"
    )
    row = _row(worker_engine, outbox_id)
    assert row["status"] == "leased"
    assert row["lease_owner"] == WORKER_ONE, "the row must be untouched"
    assert row["last_error"] != "transient", "the failure must not be recorded"


def test_an_expired_lease_is_reclaimed(schema, runtime_engine, worker_engine):
    """Expiry must still be the recovery path — the fix must not freeze the row."""
    _released_event(runtime_engine)
    claimed = _claim(worker_engine, WORKER_ONE)
    assert len(claimed) == 1
    _expire(schema, claimed[0].outbox_id)

    reclaimed = _claim(worker_engine, WORKER_TWO)
    assert len(reclaimed) == 1
    assert reclaimed[0].lease_owner == WORKER_TWO


def test_a_live_lease_is_not_reclaimed(schema, runtime_engine, worker_engine):
    """The complement: the fix must not make every lease look expired."""
    _released_event(runtime_engine)
    claimed = _claim(worker_engine, WORKER_ONE, duration=30.0)
    assert len(claimed) == 1

    assert _claim(worker_engine, WORKER_TWO) == []


def test_a_foreign_holder_cannot_mark_succeeded(schema, runtime_engine, worker_engine):
    """Identity, not only the window: a peer must not commit another's work."""
    _released_event(runtime_engine)
    claimed = _claim(worker_engine, WORKER_ONE)
    outbox_id = claimed[0].outbox_id

    assert (
        _outbox(worker_engine).mark_succeeded(outbox_id, lease_owner=WORKER_TWO) is False
    )
    assert _row(worker_engine, outbox_id)["status"] == "leased"


def test_a_live_lease_can_be_marked_succeeded(schema, runtime_engine, worker_engine):
    """The positive path, so the refusal tests above cannot pass vacuously."""
    _released_event(runtime_engine)
    claimed = _claim(worker_engine, WORKER_ONE)
    outbox_id = claimed[0].outbox_id

    assert _outbox(worker_engine).mark_succeeded(outbox_id, lease_owner=WORKER_ONE) is True
    row = _row(worker_engine, outbox_id)
    assert row["status"] == "succeeded"
    assert row["lease_owner"] is None


# --- 3. A caller cannot supply a time authority -------------------------------


def test_claim_batch_does_not_accept_a_caller_supplied_time(
    schema, runtime_engine, worker_engine
):
    """Structural, not conventional: there is no argument to pass.

    Asserted rather than assumed, because re-adding the parameter would silently
    restore the defect this module exists to prevent.
    """
    with pytest.raises(TypeError):
        _outbox(worker_engine).claim_batch(
            lease_owner=WORKER_ONE,
            lease_duration_seconds=30.0,
            now=datetime.now(timezone.utc),
        )


def test_mark_succeeded_does_not_accept_a_caller_supplied_time(
    schema, runtime_engine, worker_engine
):
    with pytest.raises(TypeError):
        _outbox(worker_engine).mark_succeeded(
            "cout_irrelevant", lease_owner=WORKER_ONE, now=datetime.now(timezone.utc)
        )


def test_mark_failed_does_not_accept_a_caller_supplied_time(
    schema, runtime_engine, worker_engine
):
    with pytest.raises(TypeError):
        _outbox(worker_engine).mark_failed(
            "cout_irrelevant",
            lease_owner=WORKER_ONE,
            error_message="x",
            retryable=True,
            now=datetime.now(timezone.utc),
        )


def test_claim_event_does_not_accept_a_caller_supplied_time(
    schema, runtime_engine, worker_engine
):
    with pytest.raises(TypeError):
        _outbox(worker_engine).claim_event(
            outbox_id="cout_irrelevant",
            lease_owner=WORKER_ONE,
            lease_duration_seconds=30.0,
            now=datetime.now(timezone.utc),
        )


# --- 4. The fence judges the same window, by the same clock -------------------


def test_the_fence_judges_the_lease_window_against_database_time(
    schema, runtime_engine, worker_engine
):
    """The write fence is the authority a memory write is bound to.

    `check_outbox_lease` used to accept a `now` and its only caller omitted it, so
    it fell back to `datetime.now(timezone.utc)` — an application clock again. The
    window is now judged by `now()` in the statement that reads the row, so a
    worker whose lease expired during extraction is fenced out.
    """
    from backend.conversations.postgres_repository import check_outbox_lease

    _released_event(runtime_engine)
    claimed = _claim(worker_engine, WORKER_ONE)
    outbox_id = claimed[0].outbox_id

    with schema.begin() as connection:
        ok, reason = check_outbox_lease(connection, outbox_id, WORKER_ONE)
    assert ok is True, f"a live lease must pass the fence, got {reason!r}"
    assert reason is None

    _expire(schema, outbox_id)

    with schema.begin() as connection:
        ok, reason = check_outbox_lease(connection, outbox_id, WORKER_ONE)
    assert ok is False, "an expired lease must be fenced out"
    assert reason is not None and "expire" in reason.lower()


def test_the_fence_refuses_a_foreign_holder(schema, runtime_engine, worker_engine):
    """Identity as well as window: the fence is the boundary, not a formality."""
    from backend.conversations.postgres_repository import check_outbox_lease

    _released_event(runtime_engine)
    claimed = _claim(worker_engine, WORKER_ONE)
    outbox_id = claimed[0].outbox_id

    with schema.begin() as connection:
        ok, reason = check_outbox_lease(connection, outbox_id, WORKER_TWO)
    assert ok is False
    assert reason is not None and "lost" in reason.lower()


def test_the_fence_does_not_accept_a_caller_supplied_time():
    """Structural: the fence cannot be handed a time authority it does not own.

    Asserted rather than assumed, because re-adding the parameter would restore
    the defect while leaving every behavioural test green — the caller would
    simply pass a helpful value.
    """
    import inspect

    from backend.conversations.postgres_repository import check_outbox_lease
    from backend.memory.write_pipeline.postgres import PostgresMemoryUnitOfWork

    assert "now" not in inspect.signature(check_outbox_lease).parameters, (
        "check_outbox_lease must judge the window itself, from database time"
    )
    assert "now" not in inspect.signature(
        PostgresMemoryUnitOfWork._check_fence
    ).parameters, "_check_fence must not forward a caller-supplied time to the fence"
