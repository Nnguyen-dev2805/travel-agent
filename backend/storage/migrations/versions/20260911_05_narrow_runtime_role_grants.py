"""The runtime role holds only the privileges the mounted surface uses.

Revision ID: 20260911_05
Revises: 20260911_04
Create: 2026-09-12

`20260910_04` granted
``SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public`` to
``travel_app`` plus an ``ALTER DEFAULT PRIVILEGES`` entry. Measured on the live
database, that gave the runtime role full DML on every table — including
``alembic_version``, whose value the readiness probe trusts, so the runtime could
rewrite its own migration head — and exposed every future table automatically.

This revision replaces the blanket grant with the enumerated set the mounted
surface actually uses, and drops the default privilege so a future table is
exposed deliberately rather than silently.

    alembic_version       SELECT                   the readiness probe reads it
    conversations         SELECT, INSERT, UPDATE   deletion is a tombstone
    messages              SELECT, INSERT, UPDATE
    conversation_outbox   SELECT, INSERT, UPDATE   cancellation is a status change
    memory_evidence       SELECT, UPDATE           conversation delete invalidates it

**No ``DELETE`` anywhere.** Every removal in this schema is a status change or a
tombstone, never a row deletion, so the runtime has no use for the verb.

**No privilege on the other ``memory_*`` tables.** The write pipeline's unit of
work and the background recorder are constructed only in tests, and the read path
is not mounted, so the runtime never touches them. The milestone that mounts
either grants what it needs, explicitly — the rule ADR 0028 records for the
worker applies to this role too.

``downgrade`` restores the blanket grant and the default privilege, because that
is what the previous revision left behind.
"""

import logging

from alembic import context, op
import sqlalchemy as sa

logger = logging.getLogger("alembic.runtime.migration")

revision = "20260911_05"
down_revision = "20260911_04"
branch_labels = None
depends_on = None

RUNTIME_ROLE = "travel_app"
SCHEMA = "public"

#: Table -> the verbs the mounted surface actually exercises.
RUNTIME_GRANTS: dict[str, tuple[str, ...]] = {
    "alembic_version": ("SELECT",),
    "conversations": ("SELECT", "INSERT", "UPDATE"),
    "messages": ("SELECT", "INSERT", "UPDATE"),
    "conversation_outbox": ("SELECT", "INSERT", "UPDATE"),
    "memory_evidence": ("SELECT", "UPDATE"),
}

_BLANKET = "SELECT, INSERT, UPDATE, DELETE"


def _is_offline_mode() -> bool:
    try:
        return context.is_offline_mode()
    except Exception:
        return False


def _public_tables(bind) -> list[str]:
    return [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relkind = 'r' ORDER BY c.relname"
            ),
            {"schema": SCHEMA},
        ).fetchall()
    ]


def upgrade() -> None:
    if _is_offline_mode():
        for table, verbs in RUNTIME_GRANTS.items():
            op.execute(sa.text(f"REVOKE ALL ON {table} FROM {RUNTIME_ROLE}"))
            op.execute(
                sa.text(f"GRANT {', '.join(verbs)} ON {table} TO {RUNTIME_ROLE}")
            )
        op.execute(
            sa.text(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA {SCHEMA} "
                f"REVOKE ALL ON TABLES FROM {RUNTIME_ROLE}"
            )
        )
        return

    bind = op.get_bind()
    tables = _public_tables(bind)

    for table in tables:
        op.execute(sa.text(f"REVOKE ALL ON {table} FROM {RUNTIME_ROLE}"))
        verbs = RUNTIME_GRANTS.get(table)
        if verbs:
            op.execute(
                sa.text(f"GRANT {', '.join(verbs)} ON {table} TO {RUNTIME_ROLE}")
            )

    # The default privilege is what made a future table silently accessible.
    # Removed here; a table added later must be granted on purpose.
    op.execute(
        sa.text(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} "
            f"REVOKE ALL ON TABLES FROM {RUNTIME_ROLE}"
        )
    )

    granted = sorted(t for t in tables if t in RUNTIME_GRANTS)
    logger.info(
        "runtime role grants narrowed: %s table(s) enumerated, default privilege removed",
        len(granted),
    )


def downgrade() -> None:
    if _is_offline_mode():
        op.execute(
            sa.text(
                f"GRANT {_BLANKET} ON ALL TABLES IN SCHEMA {SCHEMA} TO {RUNTIME_ROLE}"
            )
        )
        op.execute(
            sa.text(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} "
                f"GRANT {_BLANKET} ON TABLES TO {RUNTIME_ROLE}"
            )
        )
        return

    bind = op.get_bind()
    for table in _public_tables(bind):
        op.execute(
            sa.text(f"GRANT {_BLANKET} ON {table} TO {RUNTIME_ROLE}")
        )
    op.execute(
        sa.text(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} "
            f"GRANT {_BLANKET} ON TABLES TO {RUNTIME_ROLE}"
        )
    )
