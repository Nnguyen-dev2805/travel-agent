"""Integration tests proving cross-tenant isolation on the conversation store.

C15: cross-owner isolation was only ever asserted against
`InMemoryConversationRepository`, which implements owner scoping itself, and
tenant binding was "verified" by the substring `"set_config" in statements[0]`
with a fake cursor that hardcoded the owner. Neither would fail if the RLS
policy or the bound GUC name were wrong.

Every test here runs against the ISOLATED disposable PostgreSQL addressed by
`PG_RUNTIME_TEST_DSN`, falling back to `PG_TEST_DSN`. When neither is set the
module skips distinctly instead of pretending to be green. `pg_dsn` owns the
resolution rule for the whole integration suite.

**This module must connect as the LEAST-PRIVILEGE role, not a superuser.** A
superuser or `BYPASSRLS` role bypasses row-level security entirely, so the
isolation assertions would pass whether or not a policy exists. That rule is
checked in `pg_engine` via `assert_rls_enforced` rather than assumed, because a
fallback DSN can quietly hand this module a DDL role. `PG_RUNTIME_TEST_DSN`
exists because `test_postgres_migrations.py` needs a DDL-capable role (it runs
`DROP SCHEMA public CASCADE`) and no single variable can be both.

**A test for a security control must be proven to fail when the control is
removed.** Verified for this module: with `messages` RLS disabled,
`test_owner_a_cannot_read_owner_b_messages` fails; with `conversations` RLS
disabled, both `test_owner_a_cannot_read_owner_b_conversation` and
`test_owner_a_cannot_delete_owner_b_conversation` fail; with all controls
restored, all 8 pass.
"""

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

OWNER_A = "user_tenant_a"
OWNER_B = "user_tenant_b"


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

    # A superuser or BYPASSRLS role ignores every policy, which would make every
    # assertion in this module vacuous. Check the role, do not assume it.
    try:
        assert_rls_enforced(engine, "PG_RUNTIME_TEST_DSN")
    except Exception:
        engine.dispose()
        raise

    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrated(pg_engine):
    """Ensure the schema is at head.

    Migrations use the DDL-capable role, because the runtime role cannot DDL.
    The tests themselves stay on the runtime engine returned by `pg_engine`.
    """
    from alembic import command

    from backend.storage.postgres import alembic_config

    config = alembic_config(
        str(Path(__file__).resolve().parents[2] / "storage" / "migrations"),
        require(migration_dsn(), "PG_TEST_DSN"),
    )
    command.upgrade(config, "head")
    return pg_engine


@pytest.fixture
def repo(migrated):
    """The real adapter — the object whose RLS behaviour is under test."""
    from backend.conversations.postgres_repository import PostgresConversationRepository

    return PostgresConversationRepository(migrated)


@pytest.fixture
def service(migrated):
    """The use-case layer, used only to create fixture data ergonomically."""
    from backend.conversations.postgres_repository import PostgresConversationRepository
    from backend.conversations.service import ConversationService

    return ConversationService(
        conversation_repository=PostgresConversationRepository(migrated)
    )


@pytest.fixture
def tenant_b(service):
    """A conversation and its first user message, both owned by B.

    The first turn now also allocates a pending assistant row; these tests are
    about the conversation and the user message, so the reply slot is dropped.
    """
    from backend.conversations.models import MessageRole, MessageSource

    conversation, message, _pending = service.create_conversation_with_initial_turn(
        owner_user_id=OWNER_B,
        title="tenant-b",
        content="secret for B",
        role=MessageRole.USER,
        source=MessageSource.UI,
    )
    return conversation, message


def test_owner_a_cannot_read_owner_b_conversation(repo, tenant_b):
    conversation, _ = tenant_b

    assert repo.get(conversation.conversation_id, OWNER_A) is None


def test_owner_a_listing_never_returns_owner_b_conversations(repo, tenant_b):
    conversation, _ = tenant_b

    listed = repo.list_by_owner(OWNER_A)

    assert all(row.conversation_id != conversation.conversation_id for row in listed)


def test_owner_a_cannot_read_owner_b_messages(repo, tenant_b):
    conversation, message = tenant_b

    assert repo.get_message(message.message_id, OWNER_A) is None
    assert (
        repo.list_messages(
            conversation.conversation_id, OWNER_A, after_sequence=None, limit=100
        )
        == ()
    )


def test_owner_b_can_still_read_its_own_conversation(repo, tenant_b):
    """Guards against a test that passes only because everything is hidden."""
    conversation, message = tenant_b

    assert repo.get(conversation.conversation_id, OWNER_B) is not None
    assert repo.get_message(message.message_id, OWNER_B) is not None
    own = repo.list_messages(
        conversation.conversation_id, OWNER_B, after_sequence=None, limit=100
    )
    assert len(own) >= 1


def test_owner_a_cannot_delete_owner_b_conversation(repo, tenant_b):
    conversation, _ = tenant_b
    conversation_id = conversation.conversation_id

    repo.delete(conversation_id, OWNER_A)

    # `repo.get` does NOT filter retention state — only `ConversationService`
    # does (`_HIDDEN_RETENTION_VALUES`, service.py:53). Asserting
    # `get(...) is not None` would therefore pass even after a *successful*
    # cross-owner delete, which is how this test passed for the wrong reason
    # until it was proven against a removed control. Assert the tombstone did
    # not happen instead: the deletion epoch only advances on a real delete.
    assert repo.get_deletion_epoch(conversation_id, OWNER_B) == 0


def test_tenant_binding_binds_the_governed_guc_name(migrated):
    """The GUC name is the whole mechanism; a typo silently hides every row."""
    from backend.conversations.postgres_repository import tenant_transaction

    with tenant_transaction(migrated, OWNER_A) as connection:
        bound = connection.execute(
            sa.text("SELECT current_setting('app.tenant', true)")
        ).scalar()

    assert bound == OWNER_A


def test_tenant_binding_is_transaction_local(migrated):
    """A session-level GUC would leak one tenant's rows into the next request."""
    from backend.conversations.postgres_repository import tenant_transaction

    with tenant_transaction(migrated, OWNER_A):
        pass

    with migrated.connect() as connection:
        leftover = connection.execute(
            sa.text("SELECT current_setting('app.tenant', true)")
        ).scalar()

    assert leftover in (None, "")


def test_conversations_table_is_force_rls(migrated):
    """If FORCE is dropped, the table owner bypasses its own policy."""
    with migrated.connect() as connection:
        forced = connection.execute(
            sa.text(
                "SELECT relforcerowsecurity FROM pg_class "
                "WHERE relname = 'conversations'"
            )
        ).scalar()

    assert forced is True
