"""The worker role receives exactly the Memory privileges its write path uses.

Revision ID: 20260911_06
Revises: 20260911_05
Create: 2026-09-12

ADR 0028 created ``travel_worker`` and gave it the queue; migration
``20260911_05`` deliberately withheld every Memory table from it, because the
worker was not mounted and unused privileges are a liability. It is mounted now,
so it needs the privileges its write path actually issues — and no others.

**Derived, not guessed.** Each verb below comes from a statement the unit of work
issues in ``backend/memory/write_pipeline/postgres.py``:

    memory_assertions           SELECT, INSERT, UPDATE  resolve, insert, FOR UPDATE lock
    memory_versions             SELECT, INSERT, UPDATE  read locked, insert, supersede
    memory_evidence             INSERT                append immutable evidence
    memory_decisions            INSERT                append the decision
    memory_events               INSERT                append the trace event
    memory_outbox               INSERT                append the memory outbox row
    memory_write_idempotency    SELECT, INSERT, UPDATE  lookup, reserve, fill

**No DELETE anywhere**, and no privilege on ``alembic_version``. ``conversations``
and ``messages`` were already granted by ``20260911_04``.

The privilege set is intentionally narrow enough that a future read the worker
does not yet perform fails loudly here rather than silently succeeding. The
milestone that adds that read grants it deliberately, by the rule ADR 0028
records.
"""

import logging

from alembic import context, op
import sqlalchemy as sa

logger = logging.getLogger("alembic.runtime.migration")

revision = "20260911_06"
down_revision = "20260911_05"
branch_labels = None
depends_on = None

WORKER_ROLE = "travel_worker"
SCHEMA = "public"

#: Table -> the verbs the unit of work issues, derived from its statements.
WORKER_MEMORY_GRANTS: dict[str, tuple[str, ...]] = {
    "memory_assertions": ("SELECT", "INSERT", "UPDATE"),
    "memory_versions": ("SELECT", "INSERT", "UPDATE"),
    "memory_evidence": ("INSERT",),
    "memory_decisions": ("INSERT",),
    "memory_events": ("INSERT",),
    "memory_outbox": ("INSERT",),
    "memory_write_idempotency": ("SELECT", "INSERT", "UPDATE"),
}


def _is_offline_mode() -> bool:
    try:
        return context.is_offline_mode()
    except Exception:
        return False


def _public_tables(bind) -> set[str]:
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relkind = 'r'"
            ),
            {"schema": SCHEMA},
        ).fetchall()
    }


def upgrade() -> None:
    if _is_offline_mode():
        for table, verbs in WORKER_MEMORY_GRANTS.items():
            op.execute(
                sa.text(f"GRANT {', '.join(verbs)} ON {table} TO {WORKER_ROLE}")
            )
        return

    bind = op.get_bind()
    present = _public_tables(bind)

    granted: list[str] = []
    for table, verbs in WORKER_MEMORY_GRANTS.items():
        if table not in present:
            continue
        op.execute(sa.text(f"GRANT {', '.join(verbs)} ON {table} TO {WORKER_ROLE}"))
        granted.append(table)

    logger.info(
        "worker memory grants applied to %s of %s table(s)",
        len(granted),
        len(WORKER_MEMORY_GRANTS),
    )


def downgrade() -> None:
    if _is_offline_mode():
        for table in WORKER_MEMORY_GRANTS:
            op.execute(sa.text(f"REVOKE ALL ON {table} FROM {WORKER_ROLE}"))
        return

    bind = op.get_bind()
    present = _public_tables(bind)
    for table in WORKER_MEMORY_GRANTS:
        if table in present:
            op.execute(sa.text(f"REVOKE ALL ON {table} FROM {WORKER_ROLE}"))
