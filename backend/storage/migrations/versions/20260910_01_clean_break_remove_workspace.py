"""Clean break: remove workspace association and table.

Revision ID: 20260910_01
Revises: 20260907_03
Create: 2026-09-10

Per ADR 0018, ADR 0019, ADR 0021, and ADR 0022:
- Remove workspace_id column, index, and foreign keys from conversations.
- Drop workspaces table completely.
- Enforce conversations.owner_user_id NOT NULL.
- Add performance and ownership indexes:
  - idx_conversations_owner_created_at on (owner_user_id, created_at DESC)
  - idx_conversations_id_owner on (conversation_id, owner_user_id)
"""

from alembic import context, op
import sqlalchemy as sa

revision = "20260910_01"
down_revision = "20260907_03"
branch_labels = None
depends_on = None


def _is_offline_mode() -> bool:
    try:
        return context.is_offline_mode()
    except Exception:
        return False


def _existing_tables(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def _existing_indexes(bind, table: str) -> set:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table)}


def _existing_columns(bind, table: str) -> set:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def _enable_tenant_rls(bind, table: str, owner_check: str | None = None) -> None:
    check = owner_check or "owner_user_id = current_setting('app.tenant', true)"
    bind.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    bind.execute(
        sa.text(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL TO PUBLIC "
            f"USING ({check}) "
            f"WITH CHECK ({check})"
        )
    )


def upgrade() -> None:
    if _is_offline_mode():
        op.drop_index("idx_conversations_workspace", table_name="conversations")
        op.drop_column("conversations", "workspace_id")
        op.drop_table("workspaces")
        op.alter_column(
            "conversations",
            "owner_user_id",
            existing_type=sa.Text(),
            nullable=False,
        )
        op.create_index(
            "idx_conversations_owner_created_at",
            "conversations",
            ["owner_user_id", sa.text("created_at DESC")],
        )
        op.create_index(
            "idx_conversations_id_owner",
            "conversations",
            ["conversation_id", "owner_user_id"],
        )
        return

    bind = op.get_bind()
    tables = _existing_tables(bind)

    if "conversations" in tables:
        inspector = sa.inspect(bind)
        # 1. Drop foreign key constraints on conversations.workspace_id if any exist
        for fk in inspector.get_foreign_keys("conversations"):
            if "workspace_id" in fk.get("constrained_columns", []):
                fk_name = fk.get("name")
                if fk_name:
                    op.drop_constraint(fk_name, "conversations", type_="foreignkey")

        # 2. Drop index on conversations.workspace_id if present
        conv_indexes = _existing_indexes(bind, "conversations")
        if "idx_conversations_workspace" in conv_indexes:
            op.drop_index("idx_conversations_workspace", table_name="conversations")

        # 3. Drop column workspace_id from conversations
        conv_columns = _existing_columns(bind, "conversations")
        if "workspace_id" in conv_columns:
            op.drop_column("conversations", "workspace_id")

        # 4. Ensure conversations.owner_user_id is NOT NULL
        conv_cols_info = {col["name"]: col for col in inspector.get_columns("conversations")}
        if "owner_user_id" in conv_cols_info and conv_cols_info["owner_user_id"].get("nullable", True):
            op.alter_column(
                "conversations",
                "owner_user_id",
                existing_type=sa.Text(),
                nullable=False,
            )

        # 5. Add index on (owner_user_id, created_at DESC) for list queries
        conv_indexes = _existing_indexes(bind, "conversations")
        if "idx_conversations_owner_created_at" not in conv_indexes:
            op.create_index(
                "idx_conversations_owner_created_at",
                "conversations",
                ["owner_user_id", sa.text("created_at DESC")],
            )

        # 6. Add index on (conversation_id, owner_user_id) for ownership checks
        if "idx_conversations_id_owner" not in conv_indexes:
            op.create_index(
                "idx_conversations_id_owner",
                "conversations",
                ["conversation_id", "owner_user_id"],
            )

    # 7. Drop workspaces table if present (ensuring no leftover FK dependencies)
    if "workspaces" in tables:
        inspector = sa.inspect(bind)
        for tbl in tables:
            if tbl == "workspaces":
                continue
            for fk in inspector.get_foreign_keys(tbl):
                if fk.get("referred_table") == "workspaces":
                    fk_name = fk.get("name")
                    if fk_name:
                        op.drop_constraint(fk_name, tbl, type_="foreignkey")
        op.drop_table("workspaces")


def downgrade() -> None:
    if _is_offline_mode():
        op.drop_index("idx_conversations_id_owner", table_name="conversations")
        op.drop_index("idx_conversations_owner_created_at", table_name="conversations")
        op.create_table(
            "workspaces",
            sa.Column("workspace_id", sa.Text(), primary_key=True),
            sa.Column("owner_user_id", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            "conversations",
            sa.Column("workspace_id", sa.Text(), nullable=True),
        )
        op.create_index(
            "idx_conversations_workspace",
            "conversations",
            ["workspace_id"],
        )
        return

    bind = op.get_bind()
    tables = _existing_tables(bind)

    # 1. Drop newly created indexes
    if "conversations" in tables:
        conv_indexes = _existing_indexes(bind, "conversations")
        if "idx_conversations_id_owner" in conv_indexes:
            op.drop_index("idx_conversations_id_owner", table_name="conversations")
        if "idx_conversations_owner_created_at" in conv_indexes:
            op.drop_index("idx_conversations_owner_created_at", table_name="conversations")

    # 2. Re-create workspaces table with minimal schema
    if "workspaces" not in tables:
        op.create_table(
            "workspaces",
            sa.Column("workspace_id", sa.Text(), primary_key=True),
            sa.Column("owner_user_id", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        _enable_tenant_rls(bind, "workspaces")

    # 3. Re-add workspace_id as nullable text column to conversations
    if "conversations" in tables:
        conv_columns = _existing_columns(bind, "conversations")
        if "workspace_id" not in conv_columns:
            op.add_column(
                "conversations",
                sa.Column("workspace_id", sa.Text(), nullable=True),
            )
        conv_indexes = _existing_indexes(bind, "conversations")
        if "idx_conversations_workspace" not in conv_indexes:
            op.create_index(
                "idx_conversations_workspace",
                "conversations",
                ["workspace_id"],
            )
