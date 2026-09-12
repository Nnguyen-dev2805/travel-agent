"""Invalidate shadow memory evidence when its source conversation is deleted.

Revision ID: 20260910_03
Revises: 20260910_02
Create: 2026-09-10

Per the clean-break review findings, deleting a conversation must propagate
to the memory write pipeline. The conversation adapter already tombstones
the conversation, cancels its pending/leased outbox events, and bumps the
deletion epoch in one transaction; this revision adds the last piece of
that transaction: `memory_evidence.invalidated_at`.

Background extraction writes shadow evidence only and never creates active
versions, so there are no versions to suspend and no projections to
rebuild on this path. Marking the evidence rows invalidated keeps future
resolution, promotion, and audit paths from treating observations from a
deleted conversation as live support.
"""

from alembic import context, op
import sqlalchemy as sa

revision = "20260910_03"
down_revision = "20260910_02"
branch_labels = None
depends_on = None


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
            "memory_evidence",
            sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        )
        return

    bind = op.get_bind()
    if "memory_evidence" not in _existing_tables(bind):
        return
    if "invalidated_at" not in _existing_columns(bind, "memory_evidence"):
        op.add_column(
            "memory_evidence",
            sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if _is_offline_mode():
        op.drop_column("memory_evidence", "invalidated_at")
        return

    bind = op.get_bind()
    if "memory_evidence" not in _existing_tables(bind):
        return
    if "invalidated_at" in _existing_columns(bind, "memory_evidence"):
        op.drop_column("memory_evidence", "invalidated_at")
