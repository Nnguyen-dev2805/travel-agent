"""Add leasing, retry, and status tracking to conversation_outbox.

Revision ID: 20260907_03
Revises: 20260907_02
Create: 2026-09-07

Supports transactional outbox worker leasing per ADR 0014:
- status (pending, leased, succeeded, dead_letter, cancelled)
- attempt_count
- lease_owner
- lease_until
- last_error
- next_attempt_after
- updated_at
"""

from alembic import op
import sqlalchemy as sa

revision = "20260907_03"
down_revision = "20260907_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_outbox",
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
    )
    op.add_column(
        "conversation_outbox",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "conversation_outbox",
        sa.Column("lease_owner", sa.Text(), nullable=True),
    )
    op.add_column(
        "conversation_outbox",
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversation_outbox",
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "conversation_outbox",
        sa.Column("next_attempt_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversation_outbox",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_conversation_outbox_status",
        "conversation_outbox",
        ["status", "next_attempt_after", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_conversation_outbox_status", table_name="conversation_outbox")
    op.drop_column("conversation_outbox", "updated_at")
    op.drop_column("conversation_outbox", "next_attempt_after")
    op.drop_column("conversation_outbox", "last_error")
    op.drop_column("conversation_outbox", "lease_until")
    op.drop_column("conversation_outbox", "lease_owner")
    op.drop_column("conversation_outbox", "attempt_count")
    op.drop_column("conversation_outbox", "status")
