"""Grant minimum required DELETE privilege and RLS policy for travel_worker on memory_outbox.

Revision ID: 20260915_01
Revises: 20260914_02
Create Date: 2026-09-15

Task 11 / ADR 0038 / Plan v0.18:
Bounded memory_outbox cleanup is a worker maintenance pass pruning only pending projection intent
(event_type = 'memory.write.committed' AND status = 'pending').
travel_worker receives:
1. GRANT SELECT, DELETE ON memory_outbox TO travel_worker
2. Permissive RLS policies scoped strictly to (event_type = 'memory.write.committed' AND status = 'pending')
   for SELECT and DELETE, so worker maintenance cannot see or prune non-projection or non-pending rows.
"""

import logging

from alembic import context, op
import sqlalchemy as sa

logger = logging.getLogger("alembic.runtime.migration")

revision = "20260915_01"
down_revision = "20260914_02"
branch_labels = None
depends_on = None

WORKER_ROLE = "travel_worker"
MEMORY_OUTBOX_TABLE = "memory_outbox"
PRUNE_DELETE_POLICY = "worker_memory_outbox_prune"
PRUNE_SELECT_POLICY = "worker_memory_outbox_select"
RLS_PREDICATE = "event_type = 'memory.write.committed' AND status = 'pending'"


def _is_offline_mode() -> bool:
    try:
        return context.is_offline_mode()
    except Exception:
        return False


def _existing_policies(bind, table: str) -> set[str]:
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT policyname FROM pg_policies "
                "WHERE schemaname = 'public' AND tablename = :t"
            ),
            {"t": table},
        ).fetchall()
    }


def upgrade() -> None:
    # 1. Grant minimum required SELECT and DELETE privileges
    op.execute(
        sa.text(f"GRANT SELECT, DELETE ON {MEMORY_OUTBOX_TABLE} TO {WORKER_ROLE}")
    )

    # 2. Add worker-specific permissive RLS policies on memory_outbox
    if not _is_offline_mode():
        bind = op.get_bind()
        existing = _existing_policies(bind, MEMORY_OUTBOX_TABLE)
        if PRUNE_SELECT_POLICY not in existing:
            op.execute(
                sa.text(
                    f"CREATE POLICY {PRUNE_SELECT_POLICY} ON {MEMORY_OUTBOX_TABLE} "
                    f"FOR SELECT TO {WORKER_ROLE} USING ({RLS_PREDICATE})"
                )
            )
        if PRUNE_DELETE_POLICY not in existing:
            op.execute(
                sa.text(
                    f"CREATE POLICY {PRUNE_DELETE_POLICY} ON {MEMORY_OUTBOX_TABLE} "
                    f"FOR DELETE TO {WORKER_ROLE} USING ({RLS_PREDICATE})"
                )
            )
    else:
        op.execute(
            sa.text(
                f"CREATE POLICY {PRUNE_SELECT_POLICY} ON {MEMORY_OUTBOX_TABLE} "
                f"FOR SELECT TO {WORKER_ROLE} USING ({RLS_PREDICATE})"
            )
        )
        op.execute(
            sa.text(
                f"CREATE POLICY {PRUNE_DELETE_POLICY} ON {MEMORY_OUTBOX_TABLE} "
                f"FOR DELETE TO {WORKER_ROLE} USING ({RLS_PREDICATE})"
            )
        )

    logger.info("migration 20260915_01: granted SELECT, DELETE and maintenance RLS on memory_outbox to travel_worker")


def downgrade() -> None:
    op.execute(
        sa.text(f"DROP POLICY IF EXISTS {PRUNE_DELETE_POLICY} ON {MEMORY_OUTBOX_TABLE}")
    )
    op.execute(
        sa.text(f"DROP POLICY IF EXISTS {PRUNE_SELECT_POLICY} ON {MEMORY_OUTBOX_TABLE}")
    )
    op.execute(
        sa.text(f"REVOKE SELECT, DELETE ON {MEMORY_OUTBOX_TABLE} FROM {WORKER_ROLE}")
    )
    logger.info("migration 20260915_01 downgraded: revoked SELECT, DELETE and dropped maintenance RLS on memory_outbox")
