"""The runtime role receives exactly the Memory privileges its explicit chat path uses.

Revision ID: 20260914_01
Revises: 20260912_03
Create: 2026-09-14

ADR 0036 and Stage 2 Chat-Native Explicit Memory Actions mount explicit Remember,
Correct, and Forget execution directly into the authenticated Chat turn.
The runtime role ``travel_app`` therefore executes the explicit memory commit
coordinator, which applies changes through the write pipeline.

Derived from statements issued by ``PostgresMemoryUnitOfWork`` and
``ExplicitMemoryTurnCommit``:

    memory_assertions           SELECT, INSERT, UPDATE  lookup, insert, FOR UPDATE lock
    memory_versions             SELECT, INSERT, UPDATE  read locked, insert, supersede
    memory_evidence             SELECT, INSERT, UPDATE  insert immutable evidence, invalidation
    memory_decisions            INSERT                  append the decision
    memory_events               INSERT                  append the trace event
    memory_outbox               INSERT                  append memory outbox row
    memory_write_idempotency    SELECT, INSERT, UPDATE  lookup, reserve, fill

No DELETE anywhere. ``conversations``, ``messages``, ``conversation_outbox``, and
``memory_source_handling`` were already granted by earlier migrations.
"""

import logging

from alembic import context, op
import sqlalchemy as sa

logger = logging.getLogger("alembic.runtime.migration")

revision = "20260914_01"
down_revision = "20260912_03"
branch_labels = None
depends_on = None

RUNTIME_ROLE = "travel_app"
SCHEMA = "public"

#: Table -> the verbs the runtime unit of work issues.
RUNTIME_MEMORY_GRANTS: dict[str, tuple[str, ...]] = {
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
        for table, verbs in RUNTIME_MEMORY_GRANTS.items():
            op.execute(
                sa.text(f"GRANT {', '.join(verbs)} ON {table} TO {RUNTIME_ROLE}")
            )
        return

    bind = op.get_bind()
    present = _public_tables(bind)

    granted: list[str] = []
    for table, verbs in RUNTIME_MEMORY_GRANTS.items():
        if table not in present:
            continue
        op.execute(sa.text(f"GRANT {', '.join(verbs)} ON {table} TO {RUNTIME_ROLE}"))
        granted.append(table)

    logger.info(
        "runtime explicit memory grants applied to %s of %s table(s)",
        len(granted),
        len(RUNTIME_MEMORY_GRANTS),
    )


def downgrade() -> None:
    if _is_offline_mode():
        for table, verbs in RUNTIME_MEMORY_GRANTS.items():
            op.execute(sa.text(f"REVOKE {', '.join(verbs)} ON {table} FROM {RUNTIME_ROLE}"))
        return

    bind = op.get_bind()
    present = _public_tables(bind)
    for table, verbs in RUNTIME_MEMORY_GRANTS.items():
        if table in present:
            op.execute(sa.text(f"REVOKE {', '.join(verbs)} ON {table} FROM {RUNTIME_ROLE}"))
