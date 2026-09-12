"""Enforce tenant isolation on the mounted conversation surface.

Revision ID: 20260910_02
Revises: 20260910_01
Create: 2026-09-10

Per the clean-break review findings:

1. Add `deletion_epoch` to `conversations` (0 by default, bumped on every
   tombstone) so background workers can fence stale outbox leases.
2. `FORCE ROW LEVEL SECURITY` on `conversations` and `messages`.

`ENABLE` alone lets the table owner bypass policies, and the application
connects as the table owner, so `ENABLE` was decorative on the mounted
product surface. Every `PostgresConversationRepository` read and write now
binds `app.tenant` inside its transaction, so forcing the policy makes the
database enforce the same owner scope the application predicate checks.

`conversation_outbox` and the memory tables keep `ENABLE` (with policies):
their production writes happen inside the tenant-bound conversation
transactions, while direct background/test access stays unchanged.
"""

from alembic import context, op
import sqlalchemy as sa

revision = "20260910_02"
down_revision = "20260910_01"
branch_labels = None
depends_on = None

_FORCED_TABLES = ("conversations", "messages")


def _is_offline_mode() -> bool:
    try:
        return context.is_offline_mode()
    except Exception:
        return False


def _existing_tables(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def _existing_columns(bind, table: str) -> set:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    if _is_offline_mode():
        op.add_column(
            "conversations",
            sa.Column(
                "deletion_epoch", sa.Integer(), nullable=False, server_default="0"
            ),
        )
        for table in _FORCED_TABLES:
            op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        return

    bind = op.get_bind()
    tables = _existing_tables(bind)

    if "conversations" in tables:
        if "deletion_epoch" not in _existing_columns(bind, "conversations"):
            op.add_column(
                "conversations",
                sa.Column(
                    "deletion_epoch",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
            )

    for table in _FORCED_TABLES:
        if table in tables:
            bind.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))


def downgrade() -> None:
    if _is_offline_mode():
        for table in _FORCED_TABLES:
            op.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
        op.drop_column("conversations", "deletion_epoch")
        return

    bind = op.get_bind()
    tables = _existing_tables(bind)

    for table in _FORCED_TABLES:
        if table in tables:
            bind.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))

    if "conversations" in tables:
        if "deletion_epoch" in _existing_columns(bind, "conversations"):
            op.drop_column("conversations", "deletion_epoch")
