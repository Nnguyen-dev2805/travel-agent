"""Server-owned turn status on messages.

Revision ID: 20260911_01
Revises: 20260910_04
Create: 2026-09-11

ADR 0023 makes a chat turn one unit of work with a two-phase write: the user
message and a placeholder assistant row commit together in a single transaction
under one parent-row lock, and the assistant row is filled in after generation.
That requires a server-owned status on `messages`, so a half-written turn is
visible instead of indistinguishable from a complete one.

- `pending`: allocated, generation in flight. Transient by design; a row that
  stays `pending` is an operational signal, not a valid steady state.
- `complete`: carries the message content. This is the default, so every
  pre-existing row is backfilled to `complete` and an older application
  instance that does not know about the column keeps writing valid rows.
- `failed`: generation failed. Carries no generated content and no provider
  error string; the reason stays in the event stream, content-free.

The index serves the operational queries the specification requires: the
steady-state `pending` count, and filtering a conversation's rows by status.

`messages` is `FORCE`d for row-level security (revision 20260910_02). A new
column inherits the table's existing policy, so no policy change is required;
`test_force_rls_applies_to_conversation_tables` asserts that FORCE is still in
place after this revision runs.

Downgrade is a real inverse: it drops the index, the constraint and the column.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260911_01"
down_revision = "20260910_04"
branch_labels = None
depends_on = None

INDEX_NAME = "idx_messages_conversation_status"
CONSTRAINT_NAME = "ck_messages_status"


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="complete",
        ),
    )
    op.create_check_constraint(
        CONSTRAINT_NAME,
        "messages",
        "status IN ('pending', 'complete', 'failed')",
    )
    op.create_index(
        INDEX_NAME,
        "messages",
        ["conversation_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="messages")
    op.drop_constraint(CONSTRAINT_NAME, "messages", type_="check")
    op.drop_column("messages", "status")
