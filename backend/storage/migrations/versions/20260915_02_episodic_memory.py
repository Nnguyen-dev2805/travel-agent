"""Evolve the canonical episodic table into a governed, grounded store.

Revision ID: 20260915_02
Revises: 20260915_01
Create: 2026-09-15

Plan v0.20 Task 12. `memory_episodes` has existed since `20260907_02` as an
empty placeholder — `episode_id`, `owner_user_id`, `conversation_id`,
`occurred_at`, `payload`, `created_at` — created with the rest of the ADR 0012
table set ahead of the milestone that uses it. No code ever wrote to it. It has
no grounding columns, no lifecycle state, no idempotency boundary, and no grants,
so "episodic persistence already exists" was never true.

This revision evolves that table rather than creating a second one, because two
canonical episode stores is the failure mode the plan names explicitly.

**Grounding is NOT NULL with an empty-string default.** `actor`, `event`,
`source_message_id` and `source_outbox_id` are required facts, but the column
cannot be `NOT NULL` without a default on a table that may hold legacy rows.
The default is `''`, which every grounding validator refuses — so a row that
predates this revision is *ineligible*, not silently grounded. The default is a
migration-safety device, never a value the product path writes.

**`status` defaults to `shadow`.** A legacy row must not become answer-eligible
by virtue of a schema change. Only an explicit activation decision moves a row
to `active`.

**`retention_mode` defaults to `conversation_bound`.** Episodes are
conversation-scoped, and `CONVERSATION_BOUND` is the conservative member: it
never silently grants account-durable retention to state nobody asked to keep
(`spec` AC 21).

**`payload` is left alone.** It is not backfilled, and it is not the policy
authority for anything. New rows write typed columns; `payload` may be `{}` and
exists only so the older column does not have to be dropped in the same
revision that starts using the table.
"""

from alembic import context, op
import sqlalchemy as sa

revision = "20260915_02"
down_revision = "20260915_01"
branch_labels = None
depends_on = None

EPISODES_TABLE = "memory_episodes"
SCHEMA = "public"

#: `travel_app` reads episodes for answer context and must be able to mark a
#: row invalidated when its source conversation is deleted, in the same
#: transaction as the tombstone — exactly as it already does for
#: `memory_evidence` (`20260911_05:58`). It never inserts or deletes an episode.
APP_ROLE = "travel_app"
APP_VERBS = ("SELECT", "UPDATE")

#: `travel_worker` forms episodes, reads for idempotency, and writes the
#: activation status transition. No `DELETE`: an episode is revoked, not erased
#: (`ADR 0037`).
WORKER_ROLE = "travel_worker"
WORKER_VERBS = ("SELECT", "INSERT", "UPDATE")

#: Columns added by this revision, with the migration-safety default. A tuple of
#: (name, type, default) where `None` means "nullable, no default".
_ADDED_COLUMNS: tuple[tuple[str, sa.types.TypeEngine, str | None], ...] = (
    ("actor", sa.Text(), "''"),
    ("event", sa.Text(), "''"),
    ("source_message_id", sa.Text(), "''"),
    ("source_outbox_id", sa.Text(), "''"),
    ("retention_mode", sa.Text(), "'conversation_bound'"),
    ("status", sa.Text(), "'shadow'"),
    ("sensitivity", sa.Text(), "'ordinary_personal'"),
    ("suppression_generation", sa.Integer(), "1"),
    ("unresolved_conflict", sa.Boolean(), "false"),
    ("expires_at", sa.DateTime(timezone=True), None),
    ("invalidated_at", sa.DateTime(timezone=True), None),
)

_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    (
        "ck_memory_episodes_retention_mode",
        "retention_mode IN ('user_durable', 'conversation_bound', 'source_bound')",
    ),
    (
        "ck_memory_episodes_status",
        "status IN ('shadow', 'active', 'superseded', 'revoked', 'rejected', 'expired')",
    ),
    (
        "ck_memory_episodes_sensitivity",
        "sensitivity IN ('ordinary_personal', 'contextually_sensitive', "
        "'restricted', 'prohibited_secret')",
    ),
    (
        "ck_memory_episodes_suppression_generation",
        "suppression_generation >= 1",
    ),
)

_TENANT_PREDICATE = (
    "owner_user_id = current_setting('app.tenant', true)"
)


def _is_offline_mode() -> bool:
    try:
        return context.is_offline_mode()
    except Exception:
        return False


def _existing_tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _existing_columns(bind, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _existing_constraints(bind, table: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in sa.inspect(bind).get_check_constraints(table)
    }


def _existing_indexes(bind, table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(bind).get_indexes(table)}


def _force_tenant_rls() -> None:
    """Force the tenant policy on the episodic store.

    `20260907_02` created the policy with `ENABLE` only. `ENABLE` alone lets the
    table owner bypass every policy and the application connects as the owner, so
    on a store that holds one user's recorded events `ENABLE` would be
    decorative. The policy is recreated rather than assumed, so the predicate
    this revision forces is the one written here.
    """
    op.execute(sa.text(f"ALTER TABLE {EPISODES_TABLE} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"DROP POLICY IF EXISTS tenant_isolation ON {EPISODES_TABLE}"
        )
    )
    op.execute(
        sa.text(
            f"CREATE POLICY tenant_isolation ON {EPISODES_TABLE} FOR ALL TO PUBLIC "
            f"USING ({_TENANT_PREDICATE}) WITH CHECK ({_TENANT_PREDICATE})"
        )
    )
    op.execute(sa.text(f"ALTER TABLE {EPISODES_TABLE} FORCE ROW LEVEL SECURITY"))


def _grant() -> None:
    app = ", ".join(APP_VERBS)
    worker = ", ".join(WORKER_VERBS)
    op.execute(
        sa.text(f"GRANT {app} ON {EPISODES_TABLE} TO {APP_ROLE}")
    )
    op.execute(
        sa.text(f"GRANT {worker} ON {EPISODES_TABLE} TO {WORKER_ROLE}")
    )


def upgrade() -> None:
    if _is_offline_mode():
        for name, column_type, default in _ADDED_COLUMNS:
            op.add_column(
                EPISODES_TABLE,
                sa.Column(
                    name,
                    column_type,
                    nullable=default is None,
                    server_default=default,
                ),
            )
        _force_tenant_rls()
        _grant()
        return

    bind = op.get_bind()
    if EPISODES_TABLE not in _existing_tables(bind):
        # A database that never had the placeholder still gets a correct table:
        # the columns below are the whole schema the slice needs, and
        # `20260907_02` is the only reason this is an ALTER at all.
        op.create_table(
            EPISODES_TABLE,
            sa.Column("episode_id", sa.Text(), primary_key=True),
            sa.Column("owner_user_id", sa.Text(), nullable=False),
            sa.Column("conversation_id", sa.Text(), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        for name, column_type, default in _ADDED_COLUMNS:
            op.add_column(
                EPISODES_TABLE,
                sa.Column(
                    name,
                    column_type,
                    nullable=default is None,
                    server_default=default,
                ),
            )

    columns = _existing_columns(bind, EPISODES_TABLE)
    for name, column_type, default in _ADDED_COLUMNS:
        if name in columns:
            continue
        op.add_column(
            EPISODES_TABLE,
            sa.Column(
                name,
                column_type,
                nullable=default is None,
                server_default=default,
            ),
        )

    constraints = _existing_constraints(bind, EPISODES_TABLE)
    for name, predicate in _CHECK_CONSTRAINTS:
        if name in constraints:
            continue
        op.execute(
            sa.text(
                f"ALTER TABLE {EPISODES_TABLE} ADD CONSTRAINT {name} "
                f"CHECK ({predicate})"
            )
        )

    indexes = _existing_indexes(bind, EPISODES_TABLE)
    if "uq_memory_episodes_source_provenance" not in indexes:
        # The idempotency boundary. Redelivery or re-extraction of one source
        # event cannot create a second canonical episode: the constraint backs
        # the race and the writer compares rather than treating a violation as
        # "already done".
        op.create_index(
            "uq_memory_episodes_source_provenance",
            EPISODES_TABLE,
            ["owner_user_id", "source_outbox_id", "source_message_id"],
            unique=True,
        )
    if "idx_memory_episodes_owner_occurred" not in indexes:
        op.create_index(
            "idx_memory_episodes_owner_occurred",
            EPISODES_TABLE,
            ["owner_user_id", "occurred_at"],
        )
    if "idx_memory_episodes_conversation" not in indexes:
        op.create_index(
            "idx_memory_episodes_conversation",
            EPISODES_TABLE,
            ["conversation_id"],
        )

    _force_tenant_rls()
    _grant()


def downgrade() -> None:
    if _is_offline_mode():
        return

    bind = op.get_bind()
    if EPISODES_TABLE not in _existing_tables(bind):
        return

    app = ", ".join(APP_VERBS)
    worker = ", ".join(WORKER_VERBS)
    op.execute(sa.text(f"REVOKE {app} ON {EPISODES_TABLE} FROM {APP_ROLE}"))
    op.execute(sa.text(f"REVOKE {worker} ON {EPISODES_TABLE} FROM {WORKER_ROLE}"))
    op.execute(sa.text(f"ALTER TABLE {EPISODES_TABLE} NO FORCE ROW LEVEL SECURITY"))

    indexes = _existing_indexes(bind, EPISODES_TABLE)
    for name in (
        "uq_memory_episodes_source_provenance",
        "idx_memory_episodes_owner_occurred",
        "idx_memory_episodes_conversation",
    ):
        if name in indexes:
            op.drop_index(name, table_name=EPISODES_TABLE)

    constraints = _existing_constraints(bind, EPISODES_TABLE)
    for name, _ in _CHECK_CONSTRAINTS:
        if name in constraints:
            op.execute(
                sa.text(
                    f"ALTER TABLE {EPISODES_TABLE} DROP CONSTRAINT {name}"
                )
            )

    columns = _existing_columns(bind, EPISODES_TABLE)
    for name, _, _ in reversed(_ADDED_COLUMNS):
        if name in columns:
            op.drop_column(EPISODES_TABLE, name)
