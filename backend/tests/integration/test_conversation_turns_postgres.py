"""Integration tests for the two-phase chat turn against real PostgreSQL.

ADR 0023 makes a chat turn one unit of work: the user message and a placeholder
assistant row are allocated together in one transaction under one parent-row
lock, and the assistant row is filled in afterwards. These tests exercise that
contract against the real adapter, because the in-memory double used by
`test_chat_conversation_binding.py` implements its own scoping and cannot prove
anything about the transaction, the lock, or row-level security.

Kept separate from that module on purpose: its docstring promises "no external
models, network, or live databases are required", and that promise is load-bearing
for anyone reading it.

Every test runs against the ISOLATED disposable PostgreSQL addressed by
`PG_RUNTIME_TEST_DSN` (least-privilege role, so row-level security actually
applies). Schema setup uses the DDL-capable `PG_TEST_DSN`.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import sqlalchemy as sa

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

OWNER = "user_turn_owner"
OTHER_OWNER = "user_turn_other"


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


@pytest.fixture
def service(migrated):
    """The real use-case layer over the real adapter."""
    from backend.conversations.postgres_repository import (
        PostgresConversationRepository,
    )
    from backend.conversations.service import ConversationService

    return ConversationService(
        conversation_repository=PostgresConversationRepository(migrated)
    )


def _empty_conversation(service, owner: str = OWNER) -> str:
    """An active conversation with no messages, so sequences start at 1."""
    return service.create_conversation(owner, title="turns").conversation_id


def _history(service, conversation_id: str, owner: str = OWNER):
    from backend.conversations.models import MessageHistoryQuery

    return service.list_messages(
        MessageHistoryQuery(conversation_id=conversation_id), owner
    )


def test_append_turn_writes_both_rows_in_one_transaction(service):
    from backend.conversations.models import MessageRole, MessageStatus

    conversation_id = _empty_conversation(service)

    user_message, pending = service.append_turn(conversation_id, OWNER, "next")

    assert user_message.role is MessageRole.USER
    assert user_message.status is MessageStatus.COMPLETE
    assert pending.role is MessageRole.ASSISTANT
    assert pending.status is MessageStatus.PENDING
    assert pending.sequence == user_message.sequence + 1

    stored = _history(service, conversation_id)
    assert [(row.role.value, row.status.value) for row in stored] == [
        ("user", "complete"),
        ("assistant", "pending"),
    ]


def test_append_turn_allocates_both_sequences_together(service):
    """Turn adjacency is the invariant: a user row is followed by its own reply."""
    conversation_id = _empty_conversation(service)

    service.append_turn(conversation_id, OWNER, "first")
    service.append_turn(conversation_id, OWNER, "second")

    stored = _history(service, conversation_id)
    assert [row.sequence for row in stored] == [1, 2, 3, 4]
    assert [row.role.value for row in stored] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_complete_turn_is_idempotent(service):
    from backend.conversations.models import MessageStatus

    conversation_id = _empty_conversation(service)
    _, pending = service.append_turn(conversation_id, OWNER, "q")

    first = service.complete_turn(conversation_id, pending.message_id, OWNER, "a")
    second = service.complete_turn(
        conversation_id, pending.message_id, OWNER, "different"
    )

    assert first.message.content == "a"
    assert second.message.content == "a"
    assert second.message.status is MessageStatus.COMPLETE
    # The fact the caller must branch on. The row says `complete`, so a status-only
    # check accepts it — but this call is not the one that wrote the reply, and the
    # generated content it carried is nowhere.
    assert first.applied is True
    assert second.applied is False


def test_fail_turn_does_not_overwrite_a_completed_row(service):
    from backend.conversations.models import MessageStatus

    conversation_id = _empty_conversation(service)
    _, pending = service.append_turn(conversation_id, OWNER, "q")
    service.complete_turn(conversation_id, pending.message_id, OWNER, "a")

    result = service.fail_turn(conversation_id, pending.message_id, OWNER)

    assert result.message.status is MessageStatus.COMPLETE
    assert result.message.content == "a"
    assert result.applied is False, (
        "failing an already-completed row applies nothing"
    )


def test_fail_turn_stores_no_content(service):
    """A failed turn must not carry a partial reply or a provider error string."""
    from backend.conversations.models import MessageStatus

    conversation_id = _empty_conversation(service)
    _, pending = service.append_turn(
        conversation_id, OWNER, "q", assistant_placeholder="partial reply"
    )

    result = service.fail_turn(conversation_id, pending.message_id, OWNER)

    assert result.message.status is MessageStatus.FAILED
    assert result.message.content == ""
    assert result.applied is True


def test_fail_turn_is_idempotent(service):
    from backend.conversations.models import MessageStatus

    conversation_id = _empty_conversation(service)
    _, pending = service.append_turn(conversation_id, OWNER, "q")

    first = service.fail_turn(conversation_id, pending.message_id, OWNER)
    second = service.fail_turn(conversation_id, pending.message_id, OWNER)

    assert first.message.status is MessageStatus.FAILED
    assert second.message.status is MessageStatus.FAILED
    assert first.applied is True
    assert second.applied is False


def test_complete_turn_fails_closed_on_a_deleted_conversation(service):
    from backend.conversations.service import ConversationNotFoundError

    conversation_id = _empty_conversation(service)
    _, pending = service.append_turn(conversation_id, OWNER, "q")
    service.delete_conversation(conversation_id, OWNER)

    with pytest.raises(ConversationNotFoundError):
        service.complete_turn(conversation_id, pending.message_id, OWNER, "a")


def test_fail_turn_fails_closed_on_a_deleted_conversation(service):
    from backend.conversations.service import ConversationNotFoundError

    conversation_id = _empty_conversation(service)
    _, pending = service.append_turn(conversation_id, OWNER, "q")
    service.delete_conversation(conversation_id, OWNER)

    with pytest.raises(ConversationNotFoundError):
        service.fail_turn(conversation_id, pending.message_id, OWNER)


def test_append_turn_rejects_a_cross_owner_call(service):
    from backend.conversations.service import ConversationNotFoundError

    conversation_id = _empty_conversation(service, owner=OTHER_OWNER)

    with pytest.raises(ConversationNotFoundError):
        service.append_turn(conversation_id, OWNER, "q")


def _pending_outbox_count(engine, conversation_id: str, owner: str = OWNER) -> int:
    """Count pending extraction events, bound to the tenant.

    `conversation_outbox` is row-level-secured, so a connection that does not
    bind `app.tenant` sees nothing at all — the count would be a silent zero and
    the assertion would pass for the wrong reason.
    """
    from backend.conversations.postgres_repository import tenant_transaction

    with tenant_transaction(engine, owner) as connection:
        return connection.execute(
            sa.text(
                "SELECT count(*) FROM conversation_outbox "
                "WHERE conversation_id = :cid AND status = 'pending'"
            ),
            {"cid": conversation_id},
        ).scalar()


def test_fail_turn_cancels_the_turn_outbox_event(service, migrated):
    """A turn with no reply must not cause extraction over an unanswered range."""
    from backend.conversations.models import OutboxIntent

    conversation_id = _empty_conversation(service)
    _, pending = service.append_turn(
        conversation_id,
        OWNER,
        "q",
        outbox_event=OutboxIntent(
            event_type="memory.extract.conversation_range",
            payload={"conversation_id": conversation_id},
        ),
    )
    assert _pending_outbox_count(migrated, conversation_id) == 1

    service.fail_turn(conversation_id, pending.message_id, OWNER)

    assert _pending_outbox_count(migrated, conversation_id) == 0


def test_complete_turn_leaves_the_outbox_event_pending(service, migrated):
    """Cancellation is conditional on failure, not unconditional."""
    from backend.conversations.models import OutboxIntent

    conversation_id = _empty_conversation(service)
    _, pending = service.append_turn(
        conversation_id,
        OWNER,
        "q",
        outbox_event=OutboxIntent(
            event_type="memory.extract.conversation_range",
            payload={"conversation_id": conversation_id},
        ),
    )

    service.complete_turn(conversation_id, pending.message_id, OWNER, "a")

    assert _pending_outbox_count(migrated, conversation_id) == 1


def test_append_turn_rejects_blank_content(service):
    from backend.conversations.models import ConversationValidationError

    conversation_id = _empty_conversation(service)

    with pytest.raises(ConversationValidationError):
        service.append_turn(conversation_id, OWNER, "   ")


def test_concurrent_turns_preserve_adjacency(service, migrated):
    """The parent-row lock serialises allocation, so pairs cannot interleave."""
    from backend.conversations.models import MessageRole
    from backend.conversations.postgres_repository import (
        PostgresConversationRepository,
    )
    from backend.conversations.service import ConversationService

    conversation_id = _empty_conversation(service)
    errors: list[BaseException] = []

    def send(index: int) -> None:
        # A separate service over the same engine: two requests, two sessions.
        local = ConversationService(
            conversation_repository=PostgresConversationRepository(migrated)
        )
        try:
            local.append_turn(conversation_id, OWNER, f"m{index}")
        except BaseException as error:  # noqa: BLE001 - asserted below
            errors.append(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(send, range(2)))

    assert errors == [], f"concurrent turns raised: {errors}"

    stored = _history(service, conversation_id)
    assert [row.sequence for row in stored] == list(range(1, len(stored) + 1))
    assert [row.role.value for row in stored] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    for user in [row for row in stored if row.role is MessageRole.USER]:
        following = next(row for row in stored if row.sequence == user.sequence + 1)
        assert following.role is MessageRole.ASSISTANT
