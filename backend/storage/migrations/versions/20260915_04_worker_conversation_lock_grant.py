"""Grant `travel_worker` the row lock its commit fence already takes.

Revision ID: 20260915_04
Revises: 20260915_03
Create: 2026-09-15

Plan v0.22 Task 13, Execution preconditions. The background path reuses
`BackgroundMemoryCommit`, whose first step is the conversation fence: it locks the
conversation row and compares `deletion_epoch` before writing anything. That lock
is `SELECT ... FOR UPDATE`, and PostgreSQL refuses every row-locking mode to a role
holding only `SELECT`:

    FOR UPDATE      -> permission denied
    FOR NO KEY UPDATE -> permission denied
    FOR SHARE       -> permission denied
    FOR KEY SHARE   -> permission denied
    plain SELECT    -> allowed

`travel_worker` has held only `SELECT` on `conversations` since `20260911_04`, so
the fence has never been takeable by the role that is supposed to take it. This is
a pre-existing gap rather than a Working Memory one — the semantic background path
has the same problem, and the Task-11/Task-12 integration tests worked around it by
running the coordinator on the migration role. Working around it is not a fix: it
means the production worker cannot reach its own commit path at all, which makes
"the background path is production-reachable" untrue.

**Column-level, not table-level.** `SELECT ... FOR UPDATE` needs `UPDATE` privilege
on the table, and a column-level grant satisfies it while a table-level grant would
let the worker rewrite any conversation column. The lock reads exactly
`retention_state` and `deletion_epoch` (`conversations/postgres_repository.py`,
`lock_conversation_on`), so those two columns are the whole of what it needs. This
was verified against PostgreSQL 16 rather than assumed: with only these two columns
granted, `SELECT conversation_id FROM conversations FOR UPDATE` succeeds as
`travel_worker`, and it fails with `SELECT` alone.

This revision adds no table, no policy, and no new authority. It removes a
privilege *deficit* that made the existing fence unreachable, and it does not
widen what the worker can write: it can lock a conversation row, and it still
cannot change a conversation's title, status, or any column the tombstone path
owns beyond the epoch it must read.
"""

from alembic import context, op
import sqlalchemy as sa

revision = "20260915_04"
down_revision = "20260915_03"
branch_labels = None
depends_on = None

CONVERSATIONS_TABLE = "conversations"
WORKER_ROLE = "travel_worker"

#: The columns the conversation fence reads while holding the lock. Nothing else.
LOCK_COLUMNS = ("retention_state", "deletion_epoch")


def _is_offline_mode() -> bool:
    try:
        return context.is_offline_mode()
    except Exception:
        return False


def _granted_columns(bind) -> set[str]:
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.column_privileges "
                "WHERE grantee = :grantee AND table_name = :table "
                "AND privilege_type = 'UPDATE'"
            ),
            {"grantee": WORKER_ROLE, "table": CONVERSATIONS_TABLE},
        )
    }


def _grant() -> None:
    columns = ", ".join(LOCK_COLUMNS)
    op.execute(
        sa.text(
            f"GRANT UPDATE ({columns}) ON {CONVERSATIONS_TABLE} TO {WORKER_ROLE}"
        )
    )


def upgrade() -> None:
    if _is_offline_mode():
        _grant()
        return

    bind = op.get_bind()
    if set(LOCK_COLUMNS) <= _granted_columns(bind):
        return
    _grant()


def downgrade() -> None:
    if _is_offline_mode():
        return

    bind = op.get_bind()
    if not _granted_columns(bind):
        return

    columns = ", ".join(LOCK_COLUMNS)
    op.execute(
        sa.text(
            f"REVOKE UPDATE ({columns}) ON {CONVERSATIONS_TABLE} FROM {WORKER_ROLE}"
        )
    )
