"""The Memory worker claims one event family, and only one.

`conversation_outbox` is a single queue with a single `event_type` column. The
Memory worker's claim path filtered on release, status, lease expiry, retry time,
debounce and the conversation lock — never on the family — and `process_one`
accepted whatever it was handed.

That is harmless while exactly one family exists. It stops being harmless the
moment a second one does: the Agent architecture this repository is heading toward
introduces `agent.resume`, `summary.generate`, `memory.reprocess` and others, and
a Memory worker that claims one of those will extract a conversation range from an
event that is not one. The failure is silent — the event simply disappears from the
queue with a plausible-looking success.

Two layers are asserted here, and they are different:

1. **The claim is bounded in SQL**, so the wrong family never leaves the queue.
2. **The worker refuses it anyway**, so a future claim path that forgets the filter
   cannot turn into a wrong extraction.

Layer 2 is the defense-in-depth half and is proved in
`backend/tests/unit/memory_write_pipeline/test_worker.py`, because the in-memory
double deliberately does not model the claim filter — a double that did would hide
the very path layer 2 exists to catch.
"""

from pathlib import Path

import pytest
import sqlalchemy as sa

from backend.conversations.models import MEMORY_EXTRACT_EVENT_TYPE
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

OWNER = "event_family_owner"
WORKER = "event_family_worker"
OTHER_FAMILY = "agent.resume"


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


@pytest.fixture()
def worker_engine(admin_engine):
    from backend.storage.postgres import create_engine

    ensure_worker_login(admin_engine)
    engine = create_engine(require(worker_dsn(), "PG_WORKER_TEST_DSN"))
    yield engine
    engine.dispose()


def _released_event(runtime_engine, event_type: str, title: str):
    """A conversation whose turn is complete, so its event is released."""
    from backend.conversations.models import (
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
        title=title,
        content="first",
        role=MessageRole.USER,
        source=MessageSource.UI,
    )
    _, pending = repo.append_turn(
        conversation_id=conversation.conversation_id,
        owner_user_id=OWNER,
        user_content="quiet hotels",
        outbox_event=OutboxIntent(
            event_type=event_type,
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


def _claim(engine, owner: str = WORKER):
    from backend.memory.write_pipeline.outbox import PostgresOutboxRepository

    return list(
        PostgresOutboxRepository(engine).claim_batch(
            lease_owner=owner, lease_duration_seconds=30.0, limit=10
        )
    )


def test_an_event_of_another_family_is_never_claimed(schema, runtime_engine, worker_engine):
    """The defect: the claim did not look at `event_type` at all."""
    conversation = _released_event(runtime_engine, OTHER_FAMILY, "agent work")

    # The event is genuinely released and claimable in every other respect, so a
    # pass here cannot be an accident of the gate.
    with schema.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT status, released_at FROM conversation_outbox "
                "WHERE conversation_id = :c"
            ),
            {"c": conversation.conversation_id},
        ).fetchone()
    assert row[0] == "pending"
    assert row[1] is not None, "the event must be released for this test to mean anything"

    assert _claim(worker_engine) == [], (
        "the Memory worker must not claim an event of another family"
    )


def test_the_memory_family_is_still_claimed(schema, runtime_engine, worker_engine):
    """The complement: the filter must not block the family it exists for."""
    _released_event(runtime_engine, MEMORY_EXTRACT_EVENT_TYPE, "memory work")

    claimed = _claim(worker_engine)
    assert len(claimed) == 1
    assert claimed[0].event_type == MEMORY_EXTRACT_EVENT_TYPE


def test_a_mixed_queue_claims_only_the_memory_family(
    schema, runtime_engine, worker_engine
):
    """Both families queued at once: the worker takes one and leaves the other."""
    memory = _released_event(runtime_engine, MEMORY_EXTRACT_EVENT_TYPE, "memory work")
    other = _released_event(runtime_engine, OTHER_FAMILY, "agent work")

    claimed = _claim(worker_engine)

    assert [event.conversation_id for event in claimed] == [memory.conversation_id]
    assert all(event.event_type == MEMORY_EXTRACT_EVENT_TYPE for event in claimed)

    # The other family is untouched — still pending, not cancelled, not leased.
    with schema.connect() as connection:
        status = connection.execute(
            sa.text(
                "SELECT status FROM conversation_outbox WHERE conversation_id = :c"
            ),
            {"c": other.conversation_id},
        ).scalar()
    assert status == "pending", (
        "an unclaimed event of another family must be left exactly as it was"
    )


def test_claim_event_also_refuses_another_family(schema, runtime_engine, worker_engine):
    """`claim_event` and `claim_batch` must agree; a filter on one alone is a hole."""
    from backend.memory.write_pipeline.outbox import PostgresOutboxRepository

    conversation = _released_event(runtime_engine, OTHER_FAMILY, "agent work")
    with schema.connect() as connection:
        outbox_id = connection.execute(
            sa.text(
                "SELECT outbox_id FROM conversation_outbox WHERE conversation_id = :c"
            ),
            {"c": conversation.conversation_id},
        ).scalar()

    claimed = PostgresOutboxRepository(worker_engine).claim_event(
        outbox_id=outbox_id, lease_owner=WORKER, lease_duration_seconds=30.0
    )

    assert claimed is None
