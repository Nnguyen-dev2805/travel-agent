"""Integration tests for PostgreSQL migrations and the PG conversation adapter.

Every test runs against an ISOLATED disposable PostgreSQL (dedicated
container and database, never user data) addressed by the `PG_TEST_DSN`
environment variable, e.g.
`postgresql+psycopg://travel_test:travel-test-pw@127.0.0.1:55433/travel_test`.
When the variable is unset the module skips distinctly instead of
pretending to be green. No test migrates real user data: none exists in
this flow.
"""

import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

MIGRATIONS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "storage" / "migrations"
)
MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)

EXPECTED_TABLES = frozenset(
    {
        "workspaces",
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
    dsn = os.environ.get("PG_TEST_DSN")
    if not dsn:
        pytest.skip("isolated PG unavailable: set PG_TEST_DSN to a disposable database")
    return dsn


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
        pytest.skip(f"isolated PG unreachable: {type(error).__name__}")
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
    assert _current_revision(pg_engine) == ("20260907_02",)


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
                    "(conversation_id, owner_user_id, workspace_id, title, "
                    "retention_state, created_at, updated_at) VALUES "
                    "('cv_null', NULL, 'tw_w1', NULL, 'active', :at, :at)"
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

    with pytest.raises(Exception):
        _upgrade_to_head(pg_engine, _test_dsn())

    assert _current_revision(pg_engine) != ("20260907_02",)
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

    with pytest.raises(Exception):
        _upgrade_to_head(pg_engine, _test_dsn())

    assert _current_revision(pg_engine) != ("20260907_02",)


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
                "(conversation_id, owner_user_id, workspace_id, title, "
                "retention_state, created_at, updated_at) VALUES "
                "('cv_a', 'owner_a', NULL, NULL, 'active', :at, :at), "
                "('cv_b', 'owner_b', NULL, NULL, 'active', :at, :at)"
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
                        "(conversation_id, owner_user_id, workspace_id, title, "
                        "retention_state, created_at, updated_at) VALUES "
                        "('cv_forged', 'owner_b', NULL, NULL, 'active', :at, :at)"
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
    assert _current_revision(pg_engine) == ("20260907_02",)


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
            workspace_id=None,
            title="Solo",
            created_at=MOMENT,
            updated_at=MOMENT,
        )
    )
    assert standalone.owner_user_id == "owner_a"
    assert standalone.workspace_id is None
    assert repository.get("cv_solo") == standalone
    assert repository.get("cv_missing") is None

    first = repository.append_message(
        MessageDraft(
            conversation_id="cv_solo",
            role="user",
            content="hello",
            created_at=MOMENT,
        ),
        "ms_first",
    )
    second = repository.append_message(
        MessageDraft(
            conversation_id="cv_solo",
            role="user",
            content="again",
            created_at=MOMENT,
        ),
        "ms_second",
        outbox_event={"event_type": "test.message", "payload": {}},
    )
    assert (first.sequence, second.sequence) == (1, 2)
    assert [
        item.message_id for item in repository.list_messages("cv_solo", None, 10)
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
