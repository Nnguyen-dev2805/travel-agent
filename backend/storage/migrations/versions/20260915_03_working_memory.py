"""Evolve the canonical working-state table into a governed open-state store.

Revision ID: 20260915_03
Revises: 20260915_02
Create: 2026-09-15

Plan v0.22 Task 13. `memory_summaries` has existed since `20260907_02` as an
empty placeholder — `summary_id`, `owner_user_id`, `conversation_id`, `content`,
`created_at` — created with the rest of the ADR 0012 table set ahead of the
milestone that uses it. No code has ever read or written it.

This revision evolves that table rather than creating a `memory_working` table,
because two canonical working-state stores is the same failure mode Task 12
refused for episodes. The domain contract and every API are named Working
Memory; only the physical table keeps its historical name.

**One row per conversation, not one per source.** Working Memory is a
*replacement*: a conversation has exactly one current open state, and a newer
candidate updates it rather than appending a second row. The uniqueness boundary
is therefore `(owner_user_id, conversation_id)` — a real unique index, not a
convention — so a concurrent writer cannot create a second canonical open state
and the replacement decision cannot be bypassed by racing inserts.

**`open_goal` and `through_sequence` are NOT NULL with migration-safety
defaults.** `''` and `0` are both refused by `validate_working_state`, so a row
that predates this revision is *ineligible* rather than silently usable. The
defaults exist so the column can be added to a table that may hold legacy rows;
they are never values the product path writes.

**`status` defaults to `shadow`.** A legacy row must not become answer-eligible
by virtue of a schema change. Only an explicit activation decision moves a row to
`active`, and an inferred replacement stays shadow until the Working family gate
is conclusive.

**`retention_mode` defaults to `conversation_bound`.** Working state is
conversation-local by definition (`spec:298`), and `CONVERSATION_BOUND` is the
conservative member: it never silently grants account-durable retention to state
nobody asked to keep (`spec` AC 21).

**`content` is left alone.** It is not backfilled, it is not read, and it is not
policy authority. New rows write typed columns; the legacy column exists only so
it does not have to be dropped in the same revision that starts using the table —
exactly the treatment `20260915_02` gave episodic `payload`.

**No `DELETE` for either runtime role.** Working state is revoked or invalidated,
not erased (`ADR 0037`); conversation deletion sets `invalidated_at` in the same
transaction as the tombstone.
"""

from alembic import context, op
import sqlalchemy as sa

revision = "20260915_03"
down_revision = "20260915_02"
branch_labels = None
depends_on = None

SUMMARIES_TABLE = "memory_summaries"
SCHEMA = "public"

#: `travel_app` reads the open state for dialogue reconstruction and must be able
#: to invalidate it when its source conversation is deleted, in the same
#: transaction as the tombstone — exactly as it already does for `memory_evidence`
#: and `memory_episodes`. It never inserts and never deletes.
APP_ROLE = "travel_app"
APP_VERBS = ("SELECT", "UPDATE")

#: `travel_worker` forms an inferred replacement, reads for the replacement
#: decision, and writes the activation status transition. No `DELETE`.
WORKER_ROLE = "travel_worker"
WORKER_VERBS = ("SELECT", "INSERT", "UPDATE")

#: Columns added by this revision, with the migration-safety default. A tuple of
#: (name, type, default) where `None` means "nullable, no default".
_ADDED_COLUMNS: tuple[tuple[str, sa.types.TypeEngine, str | None], ...] = (
    ("open_goal", sa.Text(), "''"),
    ("through_sequence", sa.Integer(), "0"),
    ("origin", sa.Text(), "'deterministic_transition'"),
    ("source_message_id", sa.Text(), "''"),
    ("source_outbox_id", sa.Text(), "''"),
    ("retention_mode", sa.Text(), "'conversation_bound'"),
    ("status", sa.Text(), "'shadow'"),
    ("sensitivity", sa.Text(), "'ordinary_personal'"),
    ("suppression_generation", sa.Integer(), "1"),
    ("unresolved_conflict", sa.Boolean(), "false"),
    ("expires_at", sa.DateTime(timezone=True), None),
    ("invalidated_at", sa.DateTime(timezone=True), None),
    ("updated_at", sa.DateTime(timezone=True), None),
)

_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    (
        "ck_memory_summaries_retention_mode",
        "retention_mode IN ('user_durable', 'conversation_bound', 'source_bound')",
    ),
    (
        "ck_memory_summaries_status",
        "status IN ('shadow', 'active', 'superseded', 'revoked', 'rejected', 'expired')",
    ),
    (
        "ck_memory_summaries_sensitivity",
        "sensitivity IN ('ordinary_personal', 'contextually_sensitive', "
        "'restricted', 'prohibited_secret')",
    ),
    (
        "ck_memory_summaries_suppression_generation",
        "suppression_generation >= 1",
    ),
    (
        "ck_memory_summaries_origin",
        "origin IN ('deterministic_transition', 'inferred_replacement')",
    ),
    (
        "ck_memory_summaries_through_sequence",
        "through_sequence >= 0",
    ),
)

_TENANT_PREDICATE = "owner_user_id = current_setting('app.tenant', true)"


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
    """Force the tenant policy on the working-state store.

    `20260907_02` created the policy with `ENABLE` only. `ENABLE` alone lets the
    table owner bypass every policy and the application connects as the owner, so
    on a store that holds one user's open state `ENABLE` would be decorative. The
    policy is recreated rather than assumed, so the predicate this revision forces
    is the one written here.
    """
    op.execute(sa.text(f"ALTER TABLE {SUMMARIES_TABLE} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {SUMMARIES_TABLE}")
    )
    op.execute(
        sa.text(
            f"CREATE POLICY tenant_isolation ON {SUMMARIES_TABLE} FOR ALL TO PUBLIC "
            f"USING ({_TENANT_PREDICATE}) WITH CHECK ({_TENANT_PREDICATE})"
        )
    )
    op.execute(sa.text(f"ALTER TABLE {SUMMARIES_TABLE} FORCE ROW LEVEL SECURITY"))


def _grant() -> None:
    app = ", ".join(APP_VERBS)
    worker = ", ".join(WORKER_VERBS)
    op.execute(sa.text(f"GRANT {app} ON {SUMMARIES_TABLE} TO {APP_ROLE}"))
    op.execute(sa.text(f"GRANT {worker} ON {SUMMARIES_TABLE} TO {WORKER_ROLE}"))


def _add_columns() -> None:
    for name, column_type, default in _ADDED_COLUMNS:
        op.add_column(
            SUMMARIES_TABLE,
            sa.Column(
                name,
                column_type,
                nullable=default is None,
                server_default=default,
            ),
        )


def upgrade() -> None:
    if _is_offline_mode():
        _add_columns()
        _force_tenant_rls()
        _grant()
        return

    bind = op.get_bind()
    if SUMMARIES_TABLE not in _existing_tables(bind):
        # A database that never had the placeholder still gets a correct table:
        # the columns below are the whole schema the slice needs, and `20260907_02`
        # is the only reason this is an ALTER at all.
        op.create_table(
            SUMMARIES_TABLE,
            sa.Column("summary_id", sa.Text(), primary_key=True),
            sa.Column("owner_user_id", sa.Text(), nullable=False),
            sa.Column("conversation_id", sa.Text(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        _add_columns()

    columns = _existing_columns(bind, SUMMARIES_TABLE)
    for name, column_type, default in _ADDED_COLUMNS:
        if name in columns:
            continue
        op.add_column(
            SUMMARIES_TABLE,
            sa.Column(
                name,
                column_type,
                nullable=default is None,
                server_default=default,
            ),
        )

    constraints = _existing_constraints(bind, SUMMARIES_TABLE)
    for name, predicate in _CHECK_CONSTRAINTS:
        if name in constraints:
            continue
        op.execute(
            sa.text(
                f"ALTER TABLE {SUMMARIES_TABLE} ADD CONSTRAINT {name} "
                f"CHECK ({predicate})"
            )
        )

    indexes = _existing_indexes(bind, SUMMARIES_TABLE)
    if "uq_memory_summaries_owner_conversation" not in indexes:
        # The replacement boundary. One conversation has one current open state,
        # so a second canonical row is a schema violation rather than a state the
        # replacement policy has to reason about.
        op.create_index(
            "uq_memory_summaries_owner_conversation",
            SUMMARIES_TABLE,
            ["owner_user_id", "conversation_id"],
            unique=True,
        )

    _force_tenant_rls()
    _grant()


def downgrade() -> None:
    if _is_offline_mode():
        return

    bind = op.get_bind()
    if SUMMARIES_TABLE not in _existing_tables(bind):
        return

    app = ", ".join(APP_VERBS)
    worker = ", ".join(WORKER_VERBS)
    op.execute(sa.text(f"REVOKE {app} ON {SUMMARIES_TABLE} FROM {APP_ROLE}"))
    op.execute(sa.text(f"REVOKE {worker} ON {SUMMARIES_TABLE} FROM {WORKER_ROLE}"))
    op.execute(sa.text(f"ALTER TABLE {SUMMARIES_TABLE} NO FORCE ROW LEVEL SECURITY"))

    indexes = _existing_indexes(bind, SUMMARIES_TABLE)
    if "uq_memory_summaries_owner_conversation" in indexes:
        op.drop_index(
            "uq_memory_summaries_owner_conversation", table_name=SUMMARIES_TABLE
        )

    constraints = _existing_constraints(bind, SUMMARIES_TABLE)
    for name, _ in _CHECK_CONSTRAINTS:
        if name in constraints:
            op.execute(
                sa.text(f"ALTER TABLE {SUMMARIES_TABLE} DROP CONSTRAINT {name}")
            )

    columns = _existing_columns(bind, SUMMARIES_TABLE)
    for name, _, _ in reversed(_ADDED_COLUMNS):
        if name in columns:
            op.drop_column(SUMMARIES_TABLE, name)
