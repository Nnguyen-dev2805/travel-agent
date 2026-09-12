"""Integration tests for PostgreSQL migrations and the PG conversation adapter.

Every test runs against an ISOLATED disposable PostgreSQL (dedicated
container and database, never user data) addressed by the `PG_TEST_DSN`
environment variable, e.g.
`postgresql+psycopg://travel_test:travel-test-pw@127.0.0.1:55433/travel_test`.
When the variable is unset the module skips distinctly via `requires_pg`
instead of pretending to be green. No test migrates real user data: none
exists in this flow.
"""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

from backend.storage.postgres import ALEMBIC_HEAD
from backend.tests.integration.pg_dsn import migration_dsn, require

requires_pg = pytest.mark.skipif(
    not migration_dsn(),
    reason="isolated PG unavailable: set PG_TEST_DSN to a disposable database",
)
pytestmark = requires_pg

MIGRATIONS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "storage" / "migrations"
)

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)

EXPECTED_TABLES = frozenset(
    {
        "conversations",
        "messages",
        "conversation_outbox",
        "memory_assertions",
        "memory_versions",
        "memory_evidence",
        "memory_candidates",
        "memory_decisions",
        "memory_events",
        "memory_outbox",
        "memory_write_idempotency",
        "memory_summaries",
        "memory_episodes",
        "memory_deletion_ledger",
    }
)
OWNER_TABLES = EXPECTED_TABLES


def _test_dsn() -> str:
    """The DDL-capable DSN: this module drops and rebuilds the schema."""
    return require(migration_dsn(), "PG_TEST_DSN")


def _alembic_config(dsn: str) -> Config:
    from backend.storage.postgres import alembic_config

    return alembic_config(str(MIGRATIONS_DIR), dsn)


def _load_revision(name: str):
    path = MIGRATIONS_DIR / "versions" / name
    spec = importlib.util.spec_from_file_location("revision_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pg_engine():
    from backend.storage.postgres import create_engine

    engine = create_engine(_test_dsn())
    try:
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
    except Exception as error:
        engine.dispose()
        raise RuntimeError(
            f"isolated PG unreachable: {type(error).__name__}; "
            "a configured PG_TEST_DSN must be reachable, not skipped."
        ) from error
    yield engine
    engine.dispose()


@pytest.fixture()
def fresh_db(pg_engine):
    with pg_engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    yield pg_engine


def _current_revision(engine) -> str | None:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_heads()


def _table_names(engine) -> frozenset:
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).fetchall()
    return frozenset(row[0] for row in rows)


def _upgrade_to_head(engine, dsn: str) -> None:
    from alembic import command

    command.upgrade(_alembic_config(dsn), "head")


def _stage_nullable_tables(engine) -> None:
    """Create rev-01 tables WITHOUT running backfill or NOT NULL."""
    revision = _load_revision("20260907_01_owned_conversations.py")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        revision.create_tables(Operations(context))


# 1. Empty upgrade reaches head with every table present.


def test_empty_upgrade_reaches_head_with_all_tables(fresh_db, pg_engine):
    _upgrade_to_head(pg_engine, _test_dsn())

    assert EXPECTED_TABLES <= _table_names(pg_engine)
    assert _current_revision(pg_engine) == (ALEMBIC_HEAD,)


# 2. Owned-conversation backfill assigns workspace owners.


def test_backfill_assigns_workspace_owners(fresh_db, pg_engine):
    from alembic import command

    command.stamp(_alembic_config(_test_dsn()), "base")
    _stage_nullable_tables(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workspaces (workspace_id, owner_user_id) "
                "VALUES ('tw_w1', 'owner_a')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO conversations "
                "(conversation_id, owner_user_id, workspace_id, title, "
                "retention_state, created_at, updated_at) VALUES "
                "('cv_l1', NULL, 'tw_w1', NULL, 'active', :at, :at), "
                "('cv_l2', NULL, 'tw_w1', 'Trip', 'active', :at, :at)"
            ),
            {"at": MOMENT},
        )

    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        owners = {
            row[0]: row[1]
            for row in connection.execute(
                sa.text("SELECT conversation_id, owner_user_id FROM conversations")
            ).fetchall()
        }
    assert owners == {"cv_l1": "owner_a", "cv_l2": "owner_a"}
    with pg_engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    "INSERT INTO conversations "
                    "(conversation_id, owner_user_id, title, "
                    "retention_state, created_at, updated_at) VALUES "
                    "('cv_null', NULL, NULL, 'active', :at, :at)"
                ),
                {"at": MOMENT},
            )


# 3. Backfill fails closed on a missing workspace.


def test_backfill_missing_workspace_fails_upgrade(fresh_db, pg_engine):
    from alembic import command

    command.stamp(_alembic_config(_test_dsn()), "base")
    _stage_nullable_tables(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO conversations "
                "(conversation_id, owner_user_id, workspace_id, title, "
                "retention_state, created_at, updated_at) VALUES "
                "('cv_orphan', NULL, 'tw_missing', NULL, 'active', :at, :at)"
            ),
            {"at": MOMENT},
        )

    with pg_engine.connect() as connection:
        staged = connection.execute(
            sa.text(
                "SELECT count(*) FROM conversations WHERE conversation_id = 'cv_orphan'"
            )
        ).scalar()
    assert staged == 1, (
        "the orphan row must exist before the upgrade is attempted, or the "
        "upgrade fails for a reason other than the missing workspace this test "
        "is about — which is exactly what a bare `raises(Exception)` accepted"
    )

    with pytest.raises(RuntimeError, match="missing workspace"):
        _upgrade_to_head(pg_engine, _test_dsn())

    assert _current_revision(pg_engine) != ("20260910_01",)
    with pg_engine.connect() as connection:
        nullable = connection.execute(
            sa.text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'conversations' "
                "AND column_name = 'owner_user_id'"
            )
        ).scalar()
    assert nullable == "YES"


# 4. Backfill fails closed on an owner mismatch.


def test_backfill_owner_mismatch_fails_upgrade(fresh_db, pg_engine):
    from alembic import command

    command.stamp(_alembic_config(_test_dsn()), "base")
    _stage_nullable_tables(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workspaces (workspace_id, owner_user_id) "
                "VALUES ('tw_w1', 'owner_a')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO conversations "
                "(conversation_id, owner_user_id, workspace_id, title, "
                "retention_state, created_at, updated_at) VALUES "
                "('cv_skewed', 'owner_b', 'tw_w1', NULL, 'active', :at, :at)"
            ),
            {"at": MOMENT},
        )

    with pg_engine.connect() as connection:
        staged = connection.execute(
            sa.text(
                "SELECT count(*) FROM conversations WHERE conversation_id = 'cv_skewed'"
            )
        ).scalar()
    assert staged == 1, (
        "the skewed row must exist before the upgrade is attempted, or the "
        "upgrade fails for a reason other than the owner mismatch this test is "
        "about"
    )

    with pytest.raises(RuntimeError, match="owner mismatch"):
        _upgrade_to_head(pg_engine, _test_dsn())

    assert _current_revision(pg_engine) != ("20260910_01",)


# 5. Constraints, indexes, and RLS are present and functional.


def test_one_active_version_constraint_rejects_duplicates(fresh_db, pg_engine):
    _upgrade_to_head(pg_engine, _test_dsn())
    assertion_id = "mas_test_assertion"
    with pg_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO memory_assertions "
                "(assertion_id, owner_user_id, scope, scope_id, canonical_key, "
                "subject_key, condition_fingerprint, created_at, updated_at) "
                "VALUES (:aid, 'owner_a', 'user', 'owner_a', "
                "'travel.preference.hotel_atmosphere', 'self', "
                "'e3b0c44298fc1c149afbf4c8996fb924', :at, :at)"
            ),
            {"aid": assertion_id, "at": MOMENT},
        )
        connection.execute(
            sa.text(
                "INSERT INTO memory_versions "
                "(version_id, assertion_id, owner_user_id, normalized_value, "
                "value_payload, authority, sensitivity, status, valid_from, "
                "created_at) VALUES ('mem_first', :aid, 'owner_a', 'quiet', "
                '\'{"normalized_value": "quiet", "display_text": "q"}\', '
                "'explicit_save', "
                "'ordinary_personal', 'active', :at, :at)"
            ),
            {"aid": assertion_id, "at": MOMENT},
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    "INSERT INTO memory_versions "
                    "(version_id, assertion_id, owner_user_id, normalized_value, "
                    "value_payload, authority, sensitivity, status, valid_from, "
                    "created_at) VALUES ('mem_second', :aid, 'owner_a', 'lively', "
                    '\'{"normalized_value": "lively", "display_text": "l"}\', '
                    "'explicit_save', "
                    "'ordinary_personal', 'active', :at, :at)"
                ),
                {"aid": assertion_id, "at": MOMENT},
            )


def test_assertion_identity_uniqueness_rejects_duplicates(fresh_db, pg_engine):
    _upgrade_to_head(pg_engine, _test_dsn())
    with pg_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO memory_assertions "
                "(assertion_id, owner_user_id, scope, scope_id, canonical_key, "
                "subject_key, condition_fingerprint, created_at, updated_at) "
                "VALUES ('mas_first', 'owner_a', 'user', 'owner_a', "
                "'travel.preference.hotel_atmosphere', 'self', "
                "'e3b0c44298fc1c149afbf4c8996fb924', :at, :at)"
            ),
            {"at": MOMENT},
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    "INSERT INTO memory_assertions "
                    "(assertion_id, owner_user_id, scope, scope_id, canonical_key, "
                    "subject_key, condition_fingerprint, created_at, updated_at) "
                    "VALUES ('mas_second', 'owner_a', 'user', 'owner_a', "
                    "'travel.preference.hotel_atmosphere', 'self', "
                    "'e3b0c44298fc1c149afbf4c8996fb924', :at, :at)"
                ),
                {"at": MOMENT},
            )


def test_rls_is_enabled_with_tenant_policies(fresh_db, pg_engine):
    _upgrade_to_head(pg_engine, _test_dsn())
    with pg_engine.connect() as connection:
        without_rls = set(OWNER_TABLES) - {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND rowsecurity = true"
                )
            ).fetchall()
        }
        policy_tables = {
            row[0]
            for row in connection.execute(
                sa.text("SELECT tablename FROM pg_policies")
            ).fetchall()
        }
    assert without_rls == set()
    assert OWNER_TABLES <= policy_tables


def test_governed_indexes_are_present(fresh_db, pg_engine):
    _upgrade_to_head(pg_engine, _test_dsn())
    with pg_engine.connect() as connection:
        names = {
            row[0]
            for row in connection.execute(
                sa.text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            ).fetchall()
        }
    for expected in (
        "uq_memory_versions_current",
        "uq_memory_assertions_identity",
        "idx_memory_versions_assertion",
        "idx_memory_evidence_assertion",
        "idx_memory_decisions_assertion",
        "idx_memory_outbox_status",
        "idx_conversations_owner",
        "idx_messages_conversation",
    ):
        assert expected in names


def test_rls_enforces_tenant_isolation(fresh_db, pg_engine):
    _upgrade_to_head(pg_engine, _test_dsn())
    with pg_engine.begin() as connection:
        connection.execute(sa.text("DROP ROLE IF EXISTS test_app"))
        connection.execute(sa.text("CREATE ROLE test_app NOLOGIN"))
        connection.execute(sa.text("GRANT USAGE ON SCHEMA public TO test_app"))
        connection.execute(
            sa.text("GRANT ALL ON ALL TABLES IN SCHEMA public TO test_app")
        )
        connection.execute(
            sa.text(
                "INSERT INTO conversations "
                "(conversation_id, owner_user_id, title, "
                "retention_state, created_at, updated_at) VALUES "
                "('cv_a', 'owner_a', NULL, 'active', :at, :at), "
                "('cv_b', 'owner_b', NULL, 'active', :at, :at)"
            ),
            {"at": MOMENT},
        )
    with pg_engine.connect() as connection:
        connection.execute(sa.text("SET ROLE test_app"))
        try:
            connection.execute(sa.text("SET app.tenant = 'owner_a'"))
            visible = {
                row[0]
                for row in connection.execute(
                    sa.text("SELECT conversation_id FROM conversations")
                ).fetchall()
            }
            assert visible == {"cv_a"}
            with pytest.raises(sa.exc.DBAPIError):
                connection.execute(
                    sa.text(
                        "INSERT INTO conversations "
                        "(conversation_id, owner_user_id, title, "
                        "retention_state, created_at, updated_at) VALUES "
                        "('cv_forged', 'owner_b', NULL, 'active', :at, :at)"
                    ),
                    {"at": MOMENT},
                )
        finally:
            connection.rollback()
            connection.execute(sa.text("RESET ROLE"))


# 6. Downgrade removes everything; re-upgrade restores it.


def test_downgrade_then_reupgrade_round_trip(fresh_db, pg_engine):
    from alembic import command

    _upgrade_to_head(pg_engine, _test_dsn())
    command.downgrade(_alembic_config(_test_dsn()), "base")

    assert EXPECTED_TABLES.isdisjoint(_table_names(pg_engine))

    _upgrade_to_head(pg_engine, _test_dsn())
    assert EXPECTED_TABLES <= _table_names(pg_engine)


def test_force_rls_applies_to_conversation_tables(fresh_db, pg_engine):
    """The table owner is also subject to tenant policies on the product surface."""
    _upgrade_to_head(pg_engine, _test_dsn())
    with pg_engine.connect() as connection:
        forced = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT relname FROM pg_class "
                    "WHERE relnamespace = 'public'::regnamespace "
                    "AND relforcerowsecurity = true"
                )
            ).fetchall()
        }
    assert {"conversations", "messages"} <= forced


def test_runtime_role_cannot_bypass_rls(fresh_db, pg_engine):
    """The least-privilege runtime role owns nothing and bypasses nothing."""
    _upgrade_to_head(pg_engine, _test_dsn())
    with pg_engine.connect() as connection:
        row = (
            connection.execute(
                sa.text(
                    "SELECT rolsuper, rolbypassrls, rolcanlogin "
                    "FROM pg_roles WHERE rolname = 'travel_app'"
                )
            )
            .mappings()
            .fetchone()
        )
    assert row is not None, "migration must ensure the travel_app role exists"
    assert row["rolsuper"] is False
    assert row["rolbypassrls"] is False


def test_deletion_epoch_defaults_to_zero(fresh_db, pg_engine):
    _upgrade_to_head(pg_engine, _test_dsn())
    with pg_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO conversations "
                "(conversation_id, owner_user_id, title, "
                "retention_state, created_at, updated_at) VALUES "
                "('cv_epoch', 'owner_a', NULL, 'active', :at, :at)"
            ),
            {"at": MOMENT},
        )
        epoch = connection.execute(
            sa.text(
                "SELECT deletion_epoch FROM conversations "
                "WHERE conversation_id = 'cv_epoch'"
            )
        ).scalar()
    assert int(epoch) == 0
    assert _current_revision(pg_engine) == (ALEMBIC_HEAD,)


# 8. Server-owned turn status on messages (ADR 0023).


def _seed_status_conversation(engine, conversation_id: str = "cv_status") -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO conversations "
                "(conversation_id, owner_user_id, title, retention_state, "
                "created_at, updated_at) VALUES "
                "(:cid, 'owner_a', NULL, 'active', :at, :at)"
            ),
            {"cid": conversation_id, "at": MOMENT},
        )


def _insert_message(
    engine,
    *,
    status: str | None = None,
    content: str = "reply",
    message_id: str = "ms_status",
    sequence: int = 1,
) -> None:
    """Insert one message, optionally overriding the server-owned fields."""
    columns = [
        "message_id",
        "conversation_id",
        "sequence",
        "role",
        "content",
        "source",
        "trace_visibility",
        "created_at",
    ]
    params: dict = {
        "message_id": message_id,
        "conversation_id": "cv_status",
        "sequence": sequence,
        "role": "assistant",
        "content": content,
        "source": "model",
        "trace_visibility": "excluded",
        "created_at": MOMENT,
    }
    if status is not None:
        columns.append("status")
        params["status"] = status
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO messages (" + ", ".join(columns) + ") VALUES ("
                + ", ".join(":" + name for name in columns) + ")"
            ),
            params,
        )


def _stage_a_pending_row_then_round_trip(engine) -> None:
    """Reproduce the production path that creates a complete row with no content.

    A turn in flight when the process died leaves a `pending` row with empty
    content. Downgrading to `20260910_04` drops the status column; upgrading
    again re-adds it with `DEFAULT 'complete'`, which relabels that row as a
    complete reply. This is exactly the rollback ADR 0023's plan documents, and
    it is how the violation is reachable.
    """
    from alembic import command

    _upgrade_to_head(engine, _test_dsn())
    _seed_status_conversation(engine)
    _insert_message(engine, status="pending", content="")
    command.downgrade(_alembic_config(_test_dsn()), "20260910_04")
    _upgrade_to_head(engine, _test_dsn())


def test_message_status_column_is_not_null_with_a_complete_default(fresh_db, pg_engine):
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT column_default, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'messages' AND column_name = 'status'"
            )
        ).fetchone()

    assert row is not None, "the status column must exist after upgrading to head"
    assert row[1] == "NO"
    assert "complete" in str(row[0])


def test_existing_messages_are_backfilled_to_complete(fresh_db, pg_engine):
    """A row written without a status takes the column default."""
    _upgrade_to_head(pg_engine, _test_dsn())
    _seed_status_conversation(pg_engine)
    _insert_message(pg_engine)

    with pg_engine.connect() as connection:
        status = connection.execute(
            sa.text("SELECT status FROM messages WHERE message_id = 'ms_status'")
        ).scalar()

    assert status == "complete"


def test_status_check_constraint_rejects_unknown_values(fresh_db, pg_engine):
    _upgrade_to_head(pg_engine, _test_dsn())
    _seed_status_conversation(pg_engine)

    with pytest.raises(IntegrityError):
        _insert_message(pg_engine, status="banana")


def test_status_check_constraint_accepts_every_governed_value(fresh_db, pg_engine):
    _upgrade_to_head(pg_engine, _test_dsn())
    _seed_status_conversation(pg_engine)

    for index, status in enumerate(("pending", "complete", "failed")):
        with pg_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO messages "
                    "(message_id, conversation_id, sequence, role, content, source, "
                    "trace_visibility, created_at, status) VALUES "
                    "(:mid, 'cv_status', :seq, 'assistant', 'reply', 'model', "
                    "'excluded', :at, :status)"
                ),
                {
                    "mid": f"ms_{status}",
                    "seq": index + 1,
                    "at": MOMENT,
                    "status": status,
                },
            )

    with pg_engine.connect() as connection:
        found = {
            row[0]
            for row in connection.execute(sa.text("SELECT status FROM messages"))
        }

    assert found == {"pending", "complete", "failed"}


def test_downgrade_removes_the_column_the_index_and_the_constraint(
    fresh_db, pg_engine
):
    """The downgrade must be a real inverse, not a NotImplementedError."""
    from alembic import command

    _upgrade_to_head(pg_engine, _test_dsn())
    command.downgrade(_alembic_config(_test_dsn()), "20260910_04")

    with pg_engine.connect() as connection:
        column = connection.execute(
            sa.text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'messages' AND column_name = 'status'"
            )
        ).scalar()
        index = connection.execute(
            sa.text(
                "SELECT count(*) FROM pg_indexes "
                "WHERE indexname = 'idx_messages_conversation_status'"
            )
        ).scalar()
        constraint = connection.execute(
            sa.text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conname = 'ck_messages_status'"
            )
        ).scalar()

    assert column == 0
    assert index == 0
    assert constraint == 0


def test_status_column_does_not_weaken_rls_on_messages(fresh_db, pg_engine):
    """A new column inherits the table policy; FORCE must still be in place."""
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        forced = connection.execute(
            sa.text(
                "SELECT relforcerowsecurity FROM pg_class WHERE relname = 'messages'"
            )
        ).scalar()

    assert forced is True


def test_alembic_head_matches_the_declared_constant(fresh_db, pg_engine):
    """Catches both directions of drift: a head bump without a migration, and a
    migration without the head bump."""
    _upgrade_to_head(pg_engine, _test_dsn())

    assert _current_revision(pg_engine) == (ALEMBIC_HEAD,)


# 7. PG conversation adapter round trip over the migrated schema.


def test_pg_adapter_owned_conversation_round_trip(fresh_db, pg_engine):
    from backend.conversations.models import Conversation, MessageDraft
    from backend.conversations.postgres_repository import (
        PostgresConversationRepository,
    )

    _upgrade_to_head(pg_engine, _test_dsn())
    repository = PostgresConversationRepository(pg_engine)

    standalone = repository.create(
        Conversation(
            conversation_id="cv_solo",
            owner_user_id="owner_a",
            title="Solo",
            created_at=MOMENT,
            updated_at=MOMENT,
        )
    )
    assert standalone.owner_user_id == "owner_a"
    assert repository.get("cv_solo", "owner_a") == standalone
    assert repository.get("cv_missing", "owner_a") is None

    first = repository.append_message(
        MessageDraft(
            conversation_id="cv_solo",
            role="user",
            content="hello",
            created_at=MOMENT,
        ),
        "ms_first",
        "owner_a",
    )
    second = repository.append_message(
        MessageDraft(
            conversation_id="cv_solo",
            role="user",
            content="again",
            created_at=MOMENT,
        ),
        "ms_second",
        "owner_a",
        outbox_event={"event_type": "test.message", "payload": {}},
    )
    assert (first.sequence, second.sequence) == (1, 2)
    assert [
        item.message_id
        for item in repository.list_messages("cv_solo", "owner_a", None, 10)
    ] == [
        "ms_first",
        "ms_second",
    ]
    assert [item.conversation_id for item in repository.list_by_owner("owner_a")] == [
        "cv_solo"
    ]
    with pg_engine.connect() as connection:
        outbox = connection.execute(
            sa.text(
                "SELECT event_type FROM conversation_outbox "
                "WHERE conversation_id = 'cv_solo'"
            )
        ).fetchall()
    assert [row[0] for row in outbox] == ["test.message"]


# 9. The status/content invariant is enforced by the schema (ADR 0025).


def test_complete_with_empty_content_is_rejected(fresh_db, pg_engine):
    """The one combination the constraint forbids."""
    _upgrade_to_head(pg_engine, _test_dsn())
    _seed_status_conversation(pg_engine)

    with pytest.raises(IntegrityError):
        _insert_message(pg_engine, status="complete", content="")


def test_whitespace_only_content_is_schema_valid(fresh_db, pg_engine):
    """`length(content) > 0` is the predicate, so whitespace passes.

    Recorded because it is a deliberate limit: the model strips and rejects a
    blank reply, and the constraint does not duplicate that rule. A `complete`
    row of whitespace is schema-valid and model-invalid, which is the same
    asymmetry this migration closed for the empty case only.
    """
    _upgrade_to_head(pg_engine, _test_dsn())
    _seed_status_conversation(pg_engine)

    _insert_message(pg_engine, status="complete", content="   ")

    with pg_engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM messages WHERE message_id = 'ms_status'")
            ).scalar()
            == 1
        )


def test_pending_and_failed_may_still_be_empty(fresh_db, pg_engine):
    """The constraint must not over-reach: both non-complete states stay valid."""
    _upgrade_to_head(pg_engine, _test_dsn())
    _seed_status_conversation(pg_engine)

    for index, status in enumerate(("pending", "failed")):
        _insert_message(
            pg_engine,
            status=status,
            content="",
            message_id=f"ms_{status}",
            sequence=index + 1,
        )

    with pg_engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM messages WHERE content = ''")
            ).scalar()
            == 2
        )


def test_non_complete_rows_may_carry_content(fresh_db, pg_engine):
    _upgrade_to_head(pg_engine, _test_dsn())
    _seed_status_conversation(pg_engine)

    _insert_message(pg_engine, status="failed", content="partial", message_id="ms_p")


def test_upgrade_repairs_a_pending_row_relabelled_by_a_round_trip(fresh_db, pg_engine):
    _stage_a_pending_row_then_round_trip(pg_engine)

    with pg_engine.connect() as connection:
        status = connection.execute(
            sa.text("SELECT status FROM messages WHERE message_id = 'ms_status'")
        ).scalar()

    assert status == "failed", "a complete row with no content is not a reply"


def test_repaired_conversation_loads_through_the_repository(fresh_db, pg_engine):
    """Before the repair this raised `ConversationStorageError`, so the whole
    conversation was unreadable, not just the offending row."""
    from backend.conversations.postgres_repository import (
        PostgresConversationRepository,
    )

    _stage_a_pending_row_then_round_trip(pg_engine)

    messages = PostgresConversationRepository(pg_engine).list_messages(
        "cv_status", "owner_a", after_sequence=None, limit=100
    )

    assert [(message.role.value, message.status.value) for message in messages] == [
        ("assistant", "failed")
    ]


def test_complete_with_empty_content_is_zero_after_a_round_trip(fresh_db, pg_engine):
    """Package verification check 7, on a database that has been through the
    operation that used to break it."""
    _stage_a_pending_row_then_round_trip(pg_engine)

    with pg_engine.connect() as connection:
        assert (
            connection.execute(
                sa.text(
                    "SELECT count(*) FROM messages "
                    "WHERE status = 'complete' AND content = ''"
                )
            ).scalar()
            == 0
        )


def test_downgrade_drops_the_constraint_and_does_not_reverse_the_repair(
    fresh_db, pg_engine
):
    """The one-way effect, pinned. A rollback must report the repair, not undo it."""
    from alembic import command

    _stage_a_pending_row_then_round_trip(pg_engine)
    command.downgrade(_alembic_config(_test_dsn()), "20260911_01")

    with pg_engine.connect() as connection:
        constraint = connection.execute(
            sa.text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conname = 'ck_messages_complete_has_content'"
            )
        ).scalar()
        status = connection.execute(
            sa.text("SELECT status FROM messages WHERE message_id = 'ms_status'")
        ).scalar()

    assert constraint == 0, "downgrade drops the constraint"
    assert status == "failed", "downgrade does NOT reverse the one-way repair"


def test_the_invariant_still_holds_after_a_full_round_trip(fresh_db, pg_engine):
    """Upgrade, downgrade, upgrade: the constraint is back and still enforced."""
    from alembic import command

    _upgrade_to_head(pg_engine, _test_dsn())
    command.downgrade(_alembic_config(_test_dsn()), "20260910_04")
    _upgrade_to_head(pg_engine, _test_dsn())
    _seed_status_conversation(pg_engine)

    with pytest.raises(IntegrityError):
        _insert_message(pg_engine, status="complete", content="")


# --- ADR 0027: the outbox turn-readiness release gate -------------------------


def _insert_outbox_event(
    engine,
    *,
    outbox_id: str,
    status: str,
    lease_owner: str | None = None,
    lease_until=None,
) -> None:
    """Insert one outbox row in the shape the pre-gate schema allowed."""
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO conversation_outbox "
                "(outbox_id, conversation_id, message_id, owner_user_id, "
                " event_type, payload, status, attempt_count, lease_owner, "
                " lease_until, created_at, updated_at) VALUES "
                "(:oid, 'cv_status', 'ms_status', 'owner_a', "
                " 'memory.extract.conversation_range', '{}'::jsonb, :status, 0, "
                " :lo, :lu, :at, :at)"
            ),
            {
                "oid": outbox_id,
                "status": status,
                "lo": lease_owner,
                "lu": lease_until,
                "at": MOMENT,
            },
        )


def test_release_gate_adds_a_nullable_column_and_an_index(fresh_db, pg_engine):
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        column = connection.execute(
            sa.text(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'conversation_outbox' "
                "AND column_name = 'released_at'"
            )
        ).fetchone()
        index = connection.execute(
            sa.text(
                "SELECT indexname FROM pg_indexes WHERE tablename = "
                "'conversation_outbox' AND indexname = 'idx_conversation_outbox_ready'"
            )
        ).fetchone()

    assert column is not None, "the release gate column exists"
    assert column[0] == "timestamp with time zone"
    assert column[1] == "YES", "the column is nullable; a default would auto-release"
    assert index is not None, "the claim path index exists"


def test_release_gate_backfill_releases_every_pre_existing_row(fresh_db, pg_engine):
    """Every row written before the gate is released, including `leased` ones.

    A `leased` row left blocked would be permanently unreclaimable, because the
    claim query's lease-expiry branch also requires the gate.
    """
    from alembic import command

    # Stop one revision short of the gate, seed rows in the pre-gate shape, then
    # upgrade so the backfill is the thing under test.
    command.upgrade(_alembic_config(_test_dsn()), "20260911_02")
    _seed_status_conversation(pg_engine)
    _insert_message(pg_engine, status="complete", content="reply")
    _insert_outbox_event(pg_engine, outbox_id="cout_pending", status="pending")
    _insert_outbox_event(
        pg_engine,
        outbox_id="cout_leased",
        status="leased",
        lease_owner="stale_worker",
        lease_until=MOMENT,
    )

    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        rows = dict(
            connection.execute(
                sa.text(
                    "SELECT outbox_id, released_at FROM conversation_outbox "
                    "WHERE outbox_id IN ('cout_pending', 'cout_leased')"
                )
            ).fetchall()
        )

    assert rows["cout_pending"] is not None, "a pre-existing pending row is released"
    assert rows["cout_leased"] is not None, (
        "a pre-existing leased row must be released too, or lease expiry can never "
        "reclaim it"
    )


def test_release_gate_downgrade_removes_the_column_and_the_index(fresh_db, pg_engine):
    from alembic import command

    _upgrade_to_head(pg_engine, _test_dsn())
    command.downgrade(_alembic_config(_test_dsn()), "20260911_02")

    with pg_engine.connect() as connection:
        column = connection.execute(
            sa.text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'conversation_outbox' "
                "AND column_name = 'released_at'"
            )
        ).scalar()
        index = connection.execute(
            sa.text(
                "SELECT count(*) FROM pg_indexes WHERE tablename = "
                "'conversation_outbox' AND indexname = 'idx_conversation_outbox_ready'"
            )
        ).scalar()

    assert column == 0, "downgrade drops the column"
    assert index == 0, "downgrade drops the index"


# --- ADR 0028: the worker role and the outbox claim boundary ------------------


def test_the_worker_role_is_least_privilege(fresh_db, pg_engine):
    """A superuser or BYPASSRLS worker would make every tenant policy decorative."""
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = 'travel_worker'"
            )
        ).fetchone()

    assert row is not None, "the worker role exists"
    assert row[0] is False, "the worker must not be a superuser"
    assert row[1] is False, "BYPASSRLS would defeat the forced tenant policies"


def test_the_worker_grants_are_the_enumerated_minimum(fresh_db, pg_engine):
    """Exactly the claim path and the transcript read. Nothing else.

    This single assertion covers the three things that must *not* be granted: no
    `INSERT`/`DELETE` on the outbox, no privilege on `alembic_version`, and no
    privilege on any `memory_*` table beyond the write path below.
    """
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT table_name, privilege_type "
                "FROM information_schema.role_table_grants "
                "WHERE grantee = 'travel_worker'"
            )
        ).fetchall()

    granted = {(row[0], row[1]) for row in rows}
    # Migration 20260912_02 narrowed the outbox UPDATE to its columns, so the
    # table-level grant set loses `("conversation_outbox", "UPDATE")`: a
    # column-level grant does not appear in `role_table_grants`, and the
    # narrowed surface is asserted by the column test below instead.
    assert granted == {
        # The queue read and the transcript read (ADR 0028 / migration
        # 20260911_04, narrowed by 20260912_02).
        ("conversation_outbox", "SELECT"),
        ("conversations", "SELECT"),
        ("messages", "SELECT"),
        # The write path (ADR 0029 / migration 20260911_06). Extended when the
        # worker was mounted; see `test_the_worker_memory_grants_are_the_derived_minimum`
        # for why each verb is there.
        ("memory_assertions", "SELECT"),
        ("memory_assertions", "INSERT"),
        ("memory_assertions", "UPDATE"),
        ("memory_versions", "SELECT"),
        ("memory_versions", "INSERT"),
        ("memory_versions", "UPDATE"),
        ("memory_evidence", "INSERT"),
        ("memory_decisions", "INSERT"),
        ("memory_events", "INSERT"),
        ("memory_outbox", "INSERT"),
        ("memory_write_idempotency", "SELECT"),
        ("memory_write_idempotency", "INSERT"),
        ("memory_write_idempotency", "UPDATE"),
    }, f"unexpected worker grant set: {sorted(granted)}"


def test_the_worker_outbox_update_is_column_scoped(fresh_db, pg_engine):
    """The claim path writes eight columns, and the grant admits exactly those.

    Migration 20260912_02 narrowed the table-wide `UPDATE` of 20260911_04 to
    the columns the worker's statements actually touch: the lease lifecycle
    (`status`, `lease_owner`, `lease_until`), the retry lifecycle
    (`attempt_count`, `next_attempt_after`, `last_error`), the mutation
    timestamp (`updated_at`), and the release gate (`released_at`, written by
    the runtime role inside the turn transaction and never by the worker — but
    the write path reserves it for the claim transaction's commit, so it stays
    enumerated).

    The property under test: an `UPDATE` naming any other column fails with a
    privilege error, so a future claim path that grows the footprint must grow
    the grant explicitly, in a reviewed migration.
    """
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT column_name "
                "FROM information_schema.role_column_grants "
                "WHERE grantee = 'travel_worker' "
                "AND table_name = 'conversation_outbox' "
                "AND privilege_type = 'UPDATE'"
            )
        ).fetchall()

    columns = {row[0] for row in rows}
    assert columns == {
        "status",
        "lease_owner",
        "lease_until",
        "attempt_count",
        "next_attempt_after",
        "last_error",
        "updated_at",
        "released_at",
    }, f"unexpected worker outbox UPDATE column set: {sorted(columns)}"


def test_no_default_privileges_were_granted_to_the_worker(fresh_db, pg_engine):
    """A default privilege would expose a future table to the worker silently."""
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        rows = connection.execute(
            sa.text("SELECT defaclacl::text FROM pg_default_acl")
        ).fetchall()

    offenders = [row[0] for row in rows if "travel_worker" in (row[0] or "")]
    assert offenders == [], (
        "the worker must receive a new table's privilege deliberately, not by default"
    )


def test_the_worker_claim_policies_are_role_scoped_and_leave_the_tenant_policy_alone(
    fresh_db, pg_engine
):
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT policyname, cmd, roles::text FROM pg_policies "
                "WHERE schemaname = 'public' AND tablename = 'conversation_outbox'"
            )
        ).fetchall()

    by_name = {row[0]: (row[1], row[2]) for row in rows}
    assert by_name["tenant_isolation"] == ("ALL", "{public}"), (
        "the existing tenant policy must be untouched"
    )
    assert by_name["worker_outbox_claim"] == ("SELECT", "{travel_worker}")
    assert by_name["worker_outbox_lease"] == ("UPDATE", "{travel_worker}")


def test_the_ready_count_function_is_bounded(fresh_db, pg_engine):
    """Parameterless, scalar, definer-owned, and callable only by the runtime role."""
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT p.prosecdef, pg_get_function_result(p.oid), "
                "pg_get_function_arguments(p.oid) "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public' "
                "AND p.proname = 'ready_outbox_event_count'"
            )
        ).fetchone()
        acl = connection.execute(
            sa.text(
                "SELECT grantee, privilege_type FROM "
                "information_schema.routine_privileges "
                "WHERE routine_name = 'ready_outbox_event_count'"
            )
        ).fetchall()

    assert row is not None, "the counting function exists"
    assert row[0] is True, "SECURITY DEFINER is what lets it read past the policy"
    assert row[1] == "bigint", "it returns a count, never a row"
    assert row[2] == "", "a parameter would widen the interface"

    executors = {r[0] for r in acl if r[1] == "EXECUTE"}
    assert "travel_app" in executors, "the readiness probe runs as the runtime role"
    assert "travel_worker" not in executors, "the worker does not count the queue"
    assert "PUBLIC" not in executors, "PUBLIC must not be able to call it"


def test_the_ready_count_counts_only_released_events(fresh_db, pg_engine):
    """An unreleased event is not claimable, so counting it would overstate."""
    _upgrade_to_head(pg_engine, _test_dsn())
    _seed_status_conversation(pg_engine)
    _insert_message(pg_engine, status="complete", content="reply")
    _insert_outbox_event(pg_engine, outbox_id="cout_blocked", status="pending")
    _insert_outbox_event(pg_engine, outbox_id="cout_ready", status="pending")

    with pg_engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE conversation_outbox SET released_at = :at "
                "WHERE outbox_id = 'cout_ready'"
            ),
            {"at": MOMENT},
        )
        counted = connection.execute(
            sa.text("SELECT ready_outbox_event_count()")
        ).scalar()

    assert counted == 1, (
        "only the released event is claimable, so only it may be counted"
    )


def test_the_worker_revision_downgrades_cleanly(fresh_db, pg_engine):
    from alembic import command

    _upgrade_to_head(pg_engine, _test_dsn())
    command.downgrade(_alembic_config(_test_dsn()), "20260911_03")

    with pg_engine.connect() as connection:
        policies = connection.execute(
            sa.text(
                "SELECT count(*) FROM pg_policies WHERE tablename = "
                "'conversation_outbox' AND policyname LIKE 'worker_%'"
            )
        ).scalar()
        function = connection.execute(
            sa.text(
                "SELECT count(*) FROM pg_proc "
                "WHERE proname = 'ready_outbox_event_count'"
            )
        ).scalar()
        grants = connection.execute(
            sa.text(
                "SELECT count(*) FROM information_schema.role_table_grants "
                "WHERE grantee = 'travel_worker'"
            )
        ).scalar()

    assert policies == 0, "downgrade drops the claim policies"
    assert function == 0, "downgrade drops the counting function"
    assert grants == 0, "downgrade revokes the enumerated grants"


def test_the_worker_revision_round_trips(fresh_db, pg_engine):
    from alembic import command

    _upgrade_to_head(pg_engine, _test_dsn())
    command.downgrade(_alembic_config(_test_dsn()), "20260911_03")
    command.upgrade(_alembic_config(_test_dsn()), "head")

    with pg_engine.connect() as connection:
        roles = connection.execute(
            sa.text("SELECT count(*) FROM pg_roles WHERE rolname = 'travel_worker'")
        ).scalar()
        policies = connection.execute(
            sa.text(
                "SELECT count(*) FROM pg_policies WHERE tablename = "
                "'conversation_outbox' AND policyname LIKE 'worker_%'"
            )
        ).scalar()

    assert roles == 1, "the role survives a downgrade; ops owns its lifecycle"
    assert policies == 2, "re-upgrading restores both claim policies"


# --- the runtime role's privileges are enumerated, not blanket ---------------


def test_the_runtime_role_grants_are_the_enumerated_minimum(fresh_db, pg_engine):
    """`ON ALL TABLES` gave the runtime DELETE, INSERT and UPDATE everywhere.

    Measured before this revision, `travel_app` held full DML on every table
    including `alembic_version`, and an `ALTER DEFAULT PRIVILEGES` entry exposed
    every future table automatically.
    """
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT table_name, privilege_type FROM "
                "information_schema.role_table_grants WHERE grantee = 'travel_app'"
            )
        ).fetchall()

    granted = {(row[0], row[1]) for row in rows}
    assert granted == {
        ("alembic_version", "SELECT"),
        ("conversations", "SELECT"),
        ("conversations", "INSERT"),
        ("conversations", "UPDATE"),
        ("messages", "SELECT"),
        ("messages", "INSERT"),
        ("messages", "UPDATE"),
        ("conversation_outbox", "SELECT"),
        ("conversation_outbox", "INSERT"),
        ("conversation_outbox", "UPDATE"),
        ("memory_evidence", "SELECT"),
        ("memory_evidence", "UPDATE"),
    }, f"unexpected runtime grant set: {sorted(granted)}"


def test_the_runtime_role_cannot_write_the_migration_head(fresh_db, pg_engine):
    """`alembic_version` is migration authority, not application state.

    The readiness probe reads it to report the revision, so a runtime able to
    rewrite it could make the probe report a revision the database is not on.
    """
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        privileges = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT privilege_type FROM "
                    "information_schema.role_table_grants "
                    "WHERE table_name = 'alembic_version' AND grantee = 'travel_app'"
                )
            )
        }

    assert privileges == {"SELECT"}


def test_no_default_privileges_were_granted_to_the_runtime_role(fresh_db, pg_engine):
    """A default privilege exposes a future table without anyone deciding to."""
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        rows = connection.execute(
            sa.text("SELECT defaclacl::text FROM pg_default_acl")
        ).fetchall()

    offenders = [row[0] for row in rows if "travel_app" in (row[0] or "")]
    assert offenders == []


def test_the_runtime_role_revision_round_trips(fresh_db, pg_engine):
    from alembic import command

    _upgrade_to_head(pg_engine, _test_dsn())
    command.downgrade(_alembic_config(_test_dsn()), "20260911_04")

    with pg_engine.connect() as connection:
        restored = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT privilege_type FROM "
                    "information_schema.role_table_grants "
                    "WHERE table_name = 'alembic_version' AND grantee = 'travel_app'"
                )
            )
        }
    assert restored == {"SELECT", "INSERT", "UPDATE", "DELETE"}, (
        "downgrade restores what 20260910_04 left behind"
    )

    command.upgrade(_alembic_config(_test_dsn()), "head")
    with pg_engine.connect() as connection:
        narrowed = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT privilege_type FROM "
                    "information_schema.role_table_grants "
                    "WHERE table_name = 'alembic_version' AND grantee = 'travel_app'"
                )
            )
        }
    assert narrowed == {"SELECT"}


# --- the worker role's Memory privileges are derived, not blanket -------------


def test_the_worker_memory_grants_are_the_derived_minimum(fresh_db, pg_engine):
    """Every verb here comes from a statement the unit of work issues.

    ADR 0028 withheld every Memory table from the worker because it was not
    mounted. This revision grants exactly what its write path uses, so a future
    read it does not yet perform fails loudly rather than silently succeeding.
    """
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT table_name, privilege_type FROM "
                "information_schema.role_table_grants "
                "WHERE grantee = 'travel_worker' AND table_name LIKE 'memory\\_%'"
            )
        ).fetchall()

    granted = {(row[0], row[1]) for row in rows}
    assert granted == {
        ("memory_assertions", "SELECT"),
        ("memory_assertions", "INSERT"),
        ("memory_assertions", "UPDATE"),
        ("memory_versions", "SELECT"),
        ("memory_versions", "INSERT"),
        ("memory_versions", "UPDATE"),
        ("memory_evidence", "INSERT"),
        ("memory_decisions", "INSERT"),
        ("memory_events", "INSERT"),
        ("memory_outbox", "INSERT"),
        ("memory_write_idempotency", "SELECT"),
        ("memory_write_idempotency", "INSERT"),
        ("memory_write_idempotency", "UPDATE"),
    }, f"unexpected worker memory grant set: {sorted(granted)}"


def test_the_worker_has_no_privilege_on_the_migration_head(fresh_db, pg_engine):
    _upgrade_to_head(pg_engine, _test_dsn())

    with pg_engine.connect() as connection:
        privileges = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT privilege_type FROM "
                    "information_schema.role_table_grants "
                    "WHERE table_name = 'alembic_version' AND grantee = 'travel_worker'"
                )
            )
        }

    assert privileges == set(), "the worker does not check or change the head"


def test_the_worker_memory_grants_round_trip(fresh_db, pg_engine):
    from alembic import command

    _upgrade_to_head(pg_engine, _test_dsn())
    command.downgrade(_alembic_config(_test_dsn()), "20260911_05")

    with pg_engine.connect() as connection:
        remaining = connection.execute(
            sa.text(
                "SELECT count(*) FROM information_schema.role_table_grants "
                "WHERE grantee = 'travel_worker' AND table_name LIKE 'memory\\_%'"
            )
        ).scalar()
    assert remaining == 0, "downgrade revokes every Memory grant"

    command.upgrade(_alembic_config(_test_dsn()), "head")
    with pg_engine.connect() as connection:
        restored = connection.execute(
            sa.text(
                "SELECT count(*) FROM information_schema.role_table_grants "
                "WHERE grantee = 'travel_worker' AND table_name LIKE 'memory\\_%'"
            )
        ).scalar()
    assert restored == 13
