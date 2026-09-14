"""Agent Memory lifecycle: retention, revocation, generation, source handling.

Revision ID: 20260912_03
Revises: 20260912_02
Create: 2026-09-14

Three additions, all of which a later read path depends on:

1. `memory_assertions.suppression_generation` — which forget era an assertion is
   in. Starts at `1`; a revoke advances it, and artifacts stamped with an older
   generation can no longer form, activate, or read (`ADR 0037`).
2. `memory_versions.retention_mode`, `expires_at`, `suppression_generation` —
   the per-version lifecycle state. Retention is persisted at write time and is
   **never** re-derived at read time, because a later policy revision must not
   silently reinterpret historical Memory.
3. `memory_source_handling` — the durable authority record for positive
   family-specific source handling (`ADR 0038`). Append-only by grant: no
   product path receives `UPDATE` or `DELETE`.

**The legacy backfill is deliberately conservative.** Existing `conversation`
scope becomes `CONVERSATION_BOUND` and existing `user` scope becomes
`SOURCE_BOUND`. Nothing becomes `USER_DURABLE`: those rows were not created under
the durable-save contract, so promoting them by migration would grant permanent
account retention to state nobody asked to keep.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260912_03"
down_revision = "20260912_02"
branch_labels = None
depends_on = None

SOURCE_HANDLING_TABLE = "memory_source_handling"

#: The roles that read and append authority records. Neither may rewrite one.
_READ_APPEND_ROLES = ("travel_app", "travel_worker")

#: The conservative scope -> retention mapping for rows that predate the column.
_LEGACY_RETENTION_BY_SCOPE = {
    "conversation": "conversation_bound",
    "user": "source_bound",
}


def _existing_tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _existing_columns(bind, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _enable_forced_tenant_rls(table: str) -> None:
    """Force the tenant policy, not merely enable it.

    `ENABLE` alone lets the table owner bypass every policy, and the application
    connects as the owner — so on this authority table `ENABLE` would be
    decorative. Every writer binds `app.tenant` to the owner it is acting for,
    including the worker, which binds the claimed row's owner.
    """
    op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL TO PUBLIC "
            f"USING (owner_user_id = current_setting('app.tenant', true)) "
            f"WITH CHECK (owner_user_id = current_setting('app.tenant', true))"
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    tables = _existing_tables(bind)

    if "memory_assertions" in tables:
        columns = _existing_columns(bind, "memory_assertions")
        if "suppression_generation" not in columns:
            op.add_column(
                "memory_assertions",
                sa.Column(
                    "suppression_generation",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("1"),
                ),
            )
            # Every pre-existing assertion is in the first forget era.
            op.execute(
                sa.text(
                    "UPDATE memory_assertions SET suppression_generation = 1 "
                    "WHERE suppression_generation IS NULL"
                )
            )
            op.create_check_constraint(
                "ck_memory_assertions_suppression_generation",
                "memory_assertions",
                "suppression_generation >= 1",
            )

    if "memory_versions" in tables:
        columns = _existing_columns(bind, "memory_versions")
        if "retention_mode" not in columns:
            # Added nullable, backfilled, then constrained: adding a NOT NULL
            # column with a default would silently assign every legacy row the
            # same retention, which is the decision this backfill exists to make
            # explicitly.
            op.add_column(
                "memory_versions",
                sa.Column("retention_mode", sa.Text(), nullable=True),
            )
            for scope, retention in _LEGACY_RETENTION_BY_SCOPE.items():
                op.execute(
                    sa.text(
                        "UPDATE memory_versions AS v SET retention_mode = :retention "
                        "FROM memory_assertions AS a "
                        "WHERE v.assertion_id = a.assertion_id AND a.scope = :scope"
                    ).bindparams(retention=retention, scope=scope)
                )
            # Anything whose assertion scope is not a tenant scope cannot claim
            # durable retention either; it is source-bound like the rest.
            op.execute(
                sa.text(
                    "UPDATE memory_versions SET retention_mode = 'source_bound' "
                    "WHERE retention_mode IS NULL"
                )
            )
            op.alter_column("memory_versions", "retention_mode", nullable=False)
            op.create_check_constraint(
                "ck_memory_versions_retention_mode",
                "memory_versions",
                "retention_mode IN ('conversation_bound', 'source_bound', "
                "'user_durable')",
            )
        if "expires_at" not in columns:
            op.add_column(
                "memory_versions",
                sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            )
        if "suppression_generation" not in columns:
            op.add_column(
                "memory_versions",
                sa.Column(
                    "suppression_generation",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("1"),
                ),
            )
            # Existing versions are consistent with assertion generation 1.
            op.execute(
                sa.text(
                    "UPDATE memory_versions SET suppression_generation = 1 "
                    "WHERE suppression_generation IS NULL"
                )
            )
            op.create_check_constraint(
                "ck_memory_versions_suppression_generation",
                "memory_versions",
                "suppression_generation >= 1",
            )

    if SOURCE_HANDLING_TABLE not in tables:
        op.create_table(
            SOURCE_HANDLING_TABLE,
            sa.Column("owner_user_id", sa.Text(), nullable=False),
            sa.Column("source_outbox_id", sa.Text(), nullable=False),
            sa.Column("source_message_id", sa.Text(), nullable=False),
            sa.Column("family", sa.Text(), nullable=False),
            sa.Column("outcome", sa.Text(), nullable=False),
            sa.Column("reason_code", sa.Text(), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "source_outbox_id",
                "family",
                name="uq_memory_source_handling_authority",
            ),
        )
        # Indexed for the tenant-scoped read every worker path performs.
        op.create_index(
            "idx_memory_source_handling_owner",
            SOURCE_HANDLING_TABLE,
            ["owner_user_id", "source_outbox_id"],
        )
        op.execute(
            sa.text(
                f"ALTER TABLE {SOURCE_HANDLING_TABLE} "
                "ADD CONSTRAINT ck_memory_source_handling_family "
                "CHECK (family IN ('semantic', 'episodic', 'working', 'procedural'))"
            )
        )
        _enable_forced_tenant_rls(SOURCE_HANDLING_TABLE)
        # Append-only: a product path may read and add authority, never rewrite
        # it. `UPDATE`/`DELETE` are withheld rather than merely unused.
        roles = ", ".join(_READ_APPEND_ROLES)
        op.execute(
            sa.text(
                f"GRANT SELECT, INSERT ON {SOURCE_HANDLING_TABLE} TO {roles}"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _existing_tables(bind)

    if SOURCE_HANDLING_TABLE in tables:
        roles = ", ".join(_READ_APPEND_ROLES)
        op.execute(
            sa.text(f"REVOKE SELECT, INSERT ON {SOURCE_HANDLING_TABLE} FROM {roles}")
        )
        op.execute(
            sa.text(
                f"DROP POLICY IF EXISTS tenant_isolation ON {SOURCE_HANDLING_TABLE}"
            )
        )
        op.drop_index(
            "idx_memory_source_handling_owner", table_name=SOURCE_HANDLING_TABLE
        )
        op.drop_table(SOURCE_HANDLING_TABLE)

    if "memory_versions" in tables:
        columns = _existing_columns(bind, "memory_versions")
        if "suppression_generation" in columns:
            op.drop_constraint(
                "ck_memory_versions_suppression_generation",
                "memory_versions",
                type_="check",
            )
            op.drop_column("memory_versions", "suppression_generation")
        if "expires_at" in columns:
            op.drop_column("memory_versions", "expires_at")
        if "retention_mode" in columns:
            op.drop_constraint(
                "ck_memory_versions_retention_mode",
                "memory_versions",
                type_="check",
            )
            op.drop_column("memory_versions", "retention_mode")

    if "memory_assertions" in tables:
        columns = _existing_columns(bind, "memory_assertions")
        if "suppression_generation" in columns:
            op.drop_constraint(
                "ck_memory_assertions_suppression_generation",
                "memory_assertions",
                type_="check",
            )
            op.drop_column("memory_assertions", "suppression_generation")
