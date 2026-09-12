"""Migration 20260912_01: the runtime role can observe backlog age, not just depth.

Readiness used queue *depth* as the memory pipeline's health, which is the wrong
question in both directions. Depth cannot tell "busy" from "stalled", and the
runtime role cannot read `conversation_outbox` at all — it is protected by a tenant
policy that role cannot satisfy. That is why the count exists as a `SECURITY
DEFINER` function, and why these two do.

A `SECURITY DEFINER` function runs with its owner's privileges, so its `EXECUTE`
grant is the whole security boundary. These tests pin that boundary rather than the
function bodies: `travel_app` may call them, and `PUBLIC` may not.
"""

from pathlib import Path

import pytest
import sqlalchemy as sa

from backend.tests.integration.pg_dsn import (
    migration_dsn,
    require,
    runtime_dsn,
)

pytestmark = pytest.mark.skipif(
    not migration_dsn(),
    reason="isolated PG unavailable: set PG_TEST_DSN to a disposable database",
)

AGE_FUNCTION = "oldest_ready_outbox_event_age_seconds"
DEAD_LETTER_FUNCTION = "dead_letter_outbox_event_count"
COUNT_FUNCTION = "ready_outbox_event_count"

OWNER = "backlog_signals_owner"


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
        alembic_config(str(migrations), require(migration_dsn(), "PG_TEST_DSN")), "head"
    )
    return admin_engine


@pytest.fixture()
def runtime_engine():
    from backend.storage.postgres import create_engine

    engine = create_engine(require(runtime_dsn(), "PG_RUNTIME_TEST_DSN"))
    yield engine
    engine.dispose()


def _acl(engine, function: str) -> list[str]:
    """The function's ACL entries, as strings.

    Returned as a list rather than joined text: an entry for `travel_agent` reads
    `travel_agent=X/travel_agent`, which *contains* the substring `=X/`. A PUBLIC
    entry is an element that *starts* with `=X/`, so the distinction matters.
    """
    with engine.connect() as connection:
        raw = connection.execute(
            sa.text("SELECT proacl FROM pg_proc WHERE proname = :f"),
            {"f": function},
        ).scalar()
    return [str(entry) for entry in (raw or [])]


def _seed_outbox_event(
    runtime_engine,
    admin_engine,
    *,
    released: bool,
    age_seconds: int,
    status: str = "pending",
) -> None:
    """A real conversation whose outbox event is reshaped for the signal under test.

    Built through the service and the repository rather than by inserting rows
    directly, so the foreign keys to `conversations` and `messages` are satisfied by
    real parents instead of guessed ids.
    """
    from backend.conversations.models import (
        MEMORY_EXTRACT_EVENT_TYPE,
        MessageRole,
        MessageSource,
        OutboxIntent,
    )
    from backend.conversations.postgres_repository import (
        PostgresConversationRepository,
    )
    from backend.conversations.service import ConversationService

    repo = PostgresConversationRepository(runtime_engine)
    service = ConversationService(conversation_repository=repo)
    conversation, _, _ = service.create_conversation_with_initial_turn(
        owner_user_id=OWNER,
        title="backlog age probe",
        content="first",
        role=MessageRole.USER,
        source=MessageSource.UI,
    )
    repo.append_turn(
        conversation_id=conversation.conversation_id,
        owner_user_id=OWNER,
        user_content="quiet hotels",
        outbox_event=OutboxIntent(
            event_type=MEMORY_EXTRACT_EVENT_TYPE,
            payload={"conversation_id": conversation.conversation_id},
        ),
    )
    with admin_engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE conversation_outbox SET "
                "created_at = now() - make_interval(secs => :age), "
                "released_at = CASE WHEN :released THEN now() ELSE NULL END, "
                "status = :status "
                "WHERE conversation_id = :c"
            ),
            {
                "age": age_seconds,
                "released": released,
                "status": status,
                "c": conversation.conversation_id,
            },
        )


@pytest.mark.parametrize("function", [AGE_FUNCTION, DEAD_LETTER_FUNCTION])
def test_the_runtime_role_may_execute_the_signal(schema, runtime_engine, function):
    """Behavioural, through the real role: the grant works, not just exists."""
    with runtime_engine.connect() as connection:
        value = connection.execute(sa.text(f"SELECT public.{function}()")).scalar()

    assert isinstance(value, int)
    assert value >= 0


@pytest.mark.parametrize("function", [AGE_FUNCTION, DEAD_LETTER_FUNCTION])
def test_public_may_not_execute_the_signal(schema, admin_engine, function):
    """The security boundary of a `SECURITY DEFINER` function is its grant.

    A function whose `proacl` is NULL keeps PostgreSQL's default of `EXECUTE` to
    `PUBLIC`, which would let any role that can connect call it. The migration
    revokes that explicitly; this asserts the revocation landed, by looking for an
    element that starts with `=X/` (an empty grantee, meaning PUBLIC) rather than
    trusting the migration.
    """
    entries = _acl(admin_engine, function)

    assert entries, (
        f"{function} has a NULL proacl, which means PUBLIC keeps EXECUTE by default"
    )
    assert not any(entry.startswith("=X/") for entry in entries), (
        f"{function} still grants EXECUTE to PUBLIC: {entries}"
    )
    assert any(entry.startswith("travel_app=X/") for entry in entries), (
        f"{function} does not grant EXECUTE to travel_app: {entries}"
    )


def test_an_empty_queue_reports_an_age_of_zero(schema, runtime_engine):
    """`min(created_at)` is NULL on an empty queue; the function must not return NULL.

    A NULL would arrive as `None` and be coerced to 0 by the container, which would
    hide a broken function behind a plausible value. Asserted at the database.
    """
    with runtime_engine.connect() as connection:
        age = connection.execute(sa.text(f"SELECT public.{AGE_FUNCTION}()")).scalar()

    assert age == 0


def test_the_age_and_count_agree_on_what_ready_means(schema, admin_engine, runtime_engine):
    """Two functions that disagree about "ready" would be worse than one.

    Both use `status = 'pending' AND released_at IS NOT NULL`, so an empty queue
    must report both zero. This is the invariant a future edit to either predicate
    would break.
    """
    with runtime_engine.connect() as connection:
        age = connection.execute(sa.text(f"SELECT public.{AGE_FUNCTION}()")).scalar()
        count = connection.execute(sa.text(f"SELECT public.{COUNT_FUNCTION}()")).scalar()

    assert (age, count) == (0, 0), (
        "an empty queue must be both zero-age and zero-depth"
    )


def test_a_stale_unreleased_event_does_not_raise_the_age(schema, runtime_engine, admin_engine):
    """An unreleased event is not claimable (ADR 0027), so it is not backlog.

    Counting it would report a stall that no worker is allowed to drain.
    """
    _seed_outbox_event(
        runtime_engine, admin_engine, released=False, age_seconds=7200
    )

    with admin_engine.connect() as connection:
        age = connection.execute(sa.text(f"SELECT public.{AGE_FUNCTION}()")).scalar()

    assert age == 0, "an unreleased event is blocked, not backlog"


def test_a_released_stale_event_raises_the_age(schema, runtime_engine, admin_engine):
    """The signal the readiness probe needs: a claimable event nobody has taken."""
    _seed_outbox_event(runtime_engine, admin_engine, released=True, age_seconds=7200)

    with admin_engine.connect() as connection:
        age = connection.execute(sa.text(f"SELECT public.{AGE_FUNCTION}()")).scalar()

    assert age >= 7200, f"a two-hour-old claimable event must report its age, got {age}"


def test_dead_letters_are_counted(schema, runtime_engine, admin_engine):
    _seed_outbox_event(
        runtime_engine,
        admin_engine,
        released=True,
        age_seconds=0,
        status="dead_letter",
    )

    with admin_engine.connect() as connection:
        count = connection.execute(
            sa.text(f"SELECT public.{DEAD_LETTER_FUNCTION}()")
        ).scalar()

    assert count == 1


def test_the_migration_is_reversible(schema, admin_engine):
    """Both directions, against the real database, as ADR 0022 requires."""
    from alembic import command

    from backend.storage.postgres import alembic_config

    migrations = (
        Path(__file__).resolve().parent.parent.parent / "storage" / "migrations"
    )
    config = alembic_config(str(migrations), require(migration_dsn(), "PG_TEST_DSN"))

    command.downgrade(config, "20260911_06")
    with admin_engine.connect() as connection:
        remaining = connection.execute(
            sa.text(
                "SELECT count(*) FROM pg_proc WHERE proname IN (:a, :d)"
            ),
            {"a": AGE_FUNCTION, "d": DEAD_LETTER_FUNCTION},
        ).scalar()
    assert remaining == 0, "downgrade must drop both functions"

    command.upgrade(config, "head")
    with admin_engine.connect() as connection:
        restored = connection.execute(
            sa.text("SELECT count(*) FROM pg_proc WHERE proname IN (:a, :d)"),
            {"a": AGE_FUNCTION, "d": DEAD_LETTER_FUNCTION},
        ).scalar()
    assert restored == 2
