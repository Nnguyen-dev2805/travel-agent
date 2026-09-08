"""Owned conversations with workspace backfill.

Revision ID: 20260907_01
Revises: None
Create: 2026-09-07

Conversations gain a direct `owner_user_id` (nullable at first) beside
the optional workspace association, per ADR 0011. Legacy rows inherit
their owner from the parent workspace; rows that cannot resolve an
owner fail the migration instead of inventing one. The owner column
goes NOT NULL only after every row resolves.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260907_01"
down_revision = None
branch_labels = None
depends_on = None


def _existing_tables(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def _existing_indexes(bind, table: str) -> set:
    return {index["name"] for index in sa.inspect(bind).get_indexes(table)}


def _enable_tenant_rls(connection, table: str, owner_check: str | None = None) -> None:
    check = owner_check or "owner_user_id = current_setting('app.tenant', true)"
    connection.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    connection.execute(
        sa.text(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL TO PUBLIC "
            f"USING ({check}) "
            f"WITH CHECK ({check})"
        )
    )


_MESSAGE_OWNER_CHECK = (
    "EXISTS (SELECT 1 FROM conversations AS parent "
    "WHERE parent.conversation_id = messages.conversation_id "
    "AND parent.owner_user_id = current_setting('app.tenant', true))"
)


def create_tables(op) -> None:
    """Create conversation-era tables, skipping whatever already exists.

    The skip logic lets tests stage pre-backfill shapes and then run
    the real `upgrade()` over them; production upgrades simply create
    everything in one pass.
    """
    bind = op.get_bind()
    existing = _existing_tables(bind)
    if "workspaces" not in existing:
        op.create_table(
            "workspaces",
            sa.Column("workspace_id", sa.Text(), primary_key=True),
            sa.Column("owner_user_id", sa.Text(), nullable=False),
        )
    if "conversations" not in existing:
        op.create_table(
            "conversations",
            sa.Column("conversation_id", sa.Text(), primary_key=True),
            sa.Column("owner_user_id", sa.Text(), nullable=True),
            sa.Column("workspace_id", sa.Text(), nullable=True),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column(
                "retention_state",
                sa.Text(),
                nullable=False,
                server_default="active",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "messages" not in existing:
        op.create_table(
            "messages",
            sa.Column("message_id", sa.Text(), primary_key=True),
            sa.Column(
                "conversation_id",
                sa.Text(),
                sa.ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("role", sa.Text(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("source", sa.Text(), nullable=False),
            sa.Column("trace_visibility", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("conversation_id", "sequence"),
        )
    if "conversation_outbox" not in existing:
        op.create_table(
            "conversation_outbox",
            sa.Column("outbox_id", sa.Text(), primary_key=True),
            sa.Column(
                "conversation_id",
                sa.Text(),
                sa.ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("message_id", sa.Text(), nullable=False),
            sa.Column("owner_user_id", sa.Text(), nullable=False),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column(
                "payload",
                JSONB(),
                nullable=False,
                server_default="{}",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    indexes = _existing_indexes(bind, "conversations")
    if "idx_conversations_owner" not in indexes:
        op.create_index("idx_conversations_owner", "conversations", ["owner_user_id"])
    indexes = _existing_indexes(bind, "conversations")
    if "idx_conversations_workspace" not in indexes:
        op.create_index(
            "idx_conversations_workspace", "conversations", ["workspace_id"]
        )
    if "idx_messages_conversation" not in _existing_indexes(bind, "messages"):
        op.create_index(
            "idx_messages_conversation",
            "messages",
            ["conversation_id", "sequence"],
        )
    if "idx_conversation_outbox_conversation" not in _existing_indexes(
        bind, "conversation_outbox"
    ):
        op.create_index(
            "idx_conversation_outbox_conversation",
            "conversation_outbox",
            ["conversation_id"],
        )


def backfill_conversation_owners(connection) -> None:
    """Assign every legacy conversation its workspace owner.

    Rules, all fail-closed:
    - owner NULL + workspace set: inherit the workspace owner; a
      missing workspace aborts the migration.
    - owner NULL + workspace NULL: no source exists, so no owner may
      be invented; abort the migration.
    - owner set + workspace set with a different workspace owner:
      mismatch; abort the migration.
    - owner set otherwise: already governed; untouched.
    """
    rows = connection.execute(
        sa.text(
            "SELECT conversation_id, owner_user_id, workspace_id FROM conversations"
        )
    ).mappings()
    owners = {
        row["workspace_id"]: row["owner_user_id"]
        for row in connection.execute(
            sa.text("SELECT workspace_id, owner_user_id FROM workspaces")
        ).mappings()
    }
    for row in rows:
        conversation_id = row["conversation_id"]
        owner = row["owner_user_id"]
        workspace_id = row["workspace_id"]
        if owner is None:
            if workspace_id is None:
                raise RuntimeError(
                    "Conversation backfill has no owner source: "
                    f"conversation '{conversation_id}' names no workspace."
                )
            if workspace_id not in owners:
                raise RuntimeError(
                    "Conversation backfill hit a missing workspace: "
                    f"conversation '{conversation_id}'."
                )
            connection.execute(
                sa.text(
                    "UPDATE conversations SET owner_user_id = :owner "
                    "WHERE conversation_id = :conversation"
                ),
                {"owner": owners[workspace_id], "conversation": conversation_id},
            )
        elif workspace_id is not None and owners.get(workspace_id) != owner:
            raise RuntimeError(
                "Conversation backfill hit an owner mismatch: "
                f"conversation '{conversation_id}'."
            )


def enforce_owner_not_null(op) -> None:
    """Make direct ownership mandatory once every row resolves."""
    op.alter_column(
        "conversations",
        "owner_user_id",
        existing_type=sa.Text(),
        nullable=False,
    )


def upgrade() -> None:
    create_tables(op)
    backfill_conversation_owners(op.get_bind())
    enforce_owner_not_null(op)
    bind = op.get_bind()
    for table in (
        "workspaces",
        "conversations",
        "conversation_outbox",
    ):
        _enable_tenant_rls(bind, table)
    # Messages carry no owner of their own; they follow the parent
    # conversation, so the policy joins to it for both reads and writes.
    _enable_tenant_rls(bind, "messages", _MESSAGE_OWNER_CHECK)


def downgrade() -> None:
    op.drop_table("conversation_outbox")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("workspaces")
