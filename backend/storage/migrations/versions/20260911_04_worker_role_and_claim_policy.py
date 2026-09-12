"""The background worker claims through a role-scoped policy on the outbox.

Revision ID: 20260911_04
Revises: 20260911_03
Create: 2026-09-11

ADR 0028. `conversation_outbox` carries ``ENABLE ROW LEVEL SECURITY`` with the
policy ``owner_user_id = current_setting('app.tenant', true)`` and is **not**
force-enabled, so PostgreSQL applies that policy to every role except the table
owner. The runtime role ``travel_app`` is not the owner and binds no tenant on
the claim path, so it sees zero outbox rows. Measured before this revision:
``claim_batch`` returned 1 as the migration role and 0 as ``travel_app``, and
``count_ready_outbox_events()`` returned 1 and 0 respectively — a silent zero
that reported the queue as empty rather than unreadable.

A worker must discover work before it knows whose work it is, so the cross-owner
read cannot be removed; it can only be bounded. This revision bounds it.

``travel_worker``
    A dedicated role, ``NOSUPERUSER NOBYPASSRLS``, owning nothing. It is created
    ``NOLOGIN`` here and granted ``LOGIN`` with a real credential by
    ``docker/postgres/init-app-role.sh``, matching the ``travel_app`` pattern.

``GRANT SELECT, UPDATE ON conversation_outbox`` and
``GRANT SELECT ON conversations, messages``
    Enumerated per table on purpose. There is **no** ``GRANT ... ON ALL TABLES``
    and **no** ``ALTER DEFAULT PRIVILEGES`` entry, so a future table is not
    silently exposed to the worker. The worker receives nothing on
    ``alembic_version``: it does not check the migration head.

``worker_outbox_claim`` / ``worker_outbox_lease``
    Two permissive policies, ``SELECT`` and ``UPDATE`` respectively, both scoped
    ``TO travel_worker`` and both ``USING (true)``. Permissive policies are
    OR-ed, so for ``travel_worker`` the union admits every row while for every
    other role the union is exactly the existing ``tenant_isolation`` policy,
    unchanged.

    No policy is added to ``conversations``, ``messages``, or any Memory table.
    ``conversations`` and ``messages`` are force-enabled, so the worker reads
    them only after binding ``app.tenant`` to the claimed row's
    ``owner_user_id`` — the binding that ``tenant_transaction`` already performs.

``ready_outbox_event_count()``
    A parameterless ``SECURITY DEFINER`` function returning ``bigint``, granted
    ``EXECUTE`` to ``travel_app`` and revoked from ``PUBLIC``. It is the smallest
    interface that lets the runtime role observe queue depth without row access:
    it cannot return a row, a payload, or an owner. It counts events that are
    ``pending`` **and** released, because under ADR 0027 an unreleased event is
    not claimable, so counting it would overstate the queue. ``search_path`` is
    pinned and the table fully qualified, so the definer's privileges cannot be
    redirected through a caller-controlled path.

``downgrade`` drops both policies, drops the function, and revokes the
enumerated grants. The role itself is left to operations, matching
``20260910_04``. No table is altered and no row is written, so neither direction
requires data repair.
"""

import logging

from alembic import context, op
import sqlalchemy as sa

logger = logging.getLogger("alembic.runtime.migration")

revision = "20260911_04"
down_revision = "20260911_03"
branch_labels = None
depends_on = None

WORKER_ROLE = "travel_worker"
APP_ROLE = "travel_app"
COUNT_FUNCTION = "ready_outbox_event_count"
SELECT_POLICY = "worker_outbox_claim"
UPDATE_POLICY = "worker_outbox_lease"
OUTBOX_TABLE = "conversation_outbox"
READ_TABLES = ("conversations", "messages")


def _is_offline_mode() -> bool:
    try:
        return context.is_offline_mode()
    except Exception:
        return False


def _existing_roles(bind) -> set:
    return {
        row[0]
        for row in bind.execute(sa.text("SELECT rolname FROM pg_roles")).fetchall()
    }


def _existing_policies(bind, table: str) -> set:
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
    # The role name is a module constant, never caller input, and DO blocks
    # cannot take bind parameters.
    op.execute(
        sa.text(
            f"DO $do$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{WORKER_ROLE}') THEN "
            f"CREATE ROLE {WORKER_ROLE} NOSUPERUSER NOBYPASSRLS "
            f"NOCREATEDB NOCREATEROLE NOREPLICATION NOLOGIN; "
            f"END IF; END $do$"
        )
    )
    # Belt and braces: a pre-existing role keeps no bypass, whatever made it.
    op.execute(sa.text(f"ALTER ROLE {WORKER_ROLE} NOSUPERUSER NOBYPASSRLS"))

    op.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {WORKER_ROLE}"))

    # Enumerated grants. Deliberately not `ON ALL TABLES`, and deliberately no
    # `ALTER DEFAULT PRIVILEGES`, so a future table is not silently exposed.
    op.execute(
        sa.text(f"GRANT SELECT, UPDATE ON {OUTBOX_TABLE} TO {WORKER_ROLE}")
    )
    for table in READ_TABLES:
        op.execute(sa.text(f"GRANT SELECT ON {table} TO {WORKER_ROLE}"))

    if not _is_offline_mode():
        bind = op.get_bind()
        existing = _existing_policies(bind, OUTBOX_TABLE)
        if SELECT_POLICY not in existing:
            op.execute(
                sa.text(
                    f"CREATE POLICY {SELECT_POLICY} ON {OUTBOX_TABLE} "
                    f"FOR SELECT TO {WORKER_ROLE} USING (true)"
                )
            )
        if UPDATE_POLICY not in existing:
            op.execute(
                sa.text(
                    f"CREATE POLICY {UPDATE_POLICY} ON {OUTBOX_TABLE} "
                    f"FOR UPDATE TO {WORKER_ROLE} USING (true) WITH CHECK (true)"
                )
            )
    else:
        for policy, command in (
            (SELECT_POLICY, "FOR SELECT"),
            (UPDATE_POLICY, "FOR UPDATE"),
        ):
            check = "true" if command == "FOR SELECT" else "true) WITH CHECK (true"
            op.execute(
                sa.text(
                    f"CREATE POLICY {policy} ON {OUTBOX_TABLE} "
                    f"{command} TO {WORKER_ROLE} USING ({check})"
                )
            )

    # Parameterless, scalar, read-only. `search_path` is pinned and the table is
    # fully qualified so the definer's privileges cannot be redirected.
    op.execute(
        sa.text(
            f"CREATE OR REPLACE FUNCTION public.{COUNT_FUNCTION}() "
            f"RETURNS bigint "
            f"LANGUAGE sql "
            f"SECURITY DEFINER "
            f"SET search_path = pg_catalog, public "
            f"AS $fn$ "
            f"SELECT count(*) FROM public.{OUTBOX_TABLE} "
            f"WHERE status = 'pending' AND released_at IS NOT NULL "
            f"$fn$"
        )
    )
    op.execute(
        sa.text(f"REVOKE ALL ON FUNCTION public.{COUNT_FUNCTION}() FROM PUBLIC")
    )
    op.execute(
        sa.text(f"GRANT EXECUTE ON FUNCTION public.{COUNT_FUNCTION}() TO {APP_ROLE}")
    )


def downgrade() -> None:
    for policy in (SELECT_POLICY, UPDATE_POLICY):
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy} ON {OUTBOX_TABLE}"))

    op.execute(sa.text(f"DROP FUNCTION IF EXISTS public.{COUNT_FUNCTION}()"))

    if _is_offline_mode():
        op.execute(
            sa.text(f"REVOKE ALL ON {OUTBOX_TABLE} FROM {WORKER_ROLE}")
        )
        for table in READ_TABLES:
            op.execute(sa.text(f"REVOKE ALL ON {table} FROM {WORKER_ROLE}"))
        op.execute(sa.text(f"REVOKE USAGE ON SCHEMA public FROM {WORKER_ROLE}"))
        return

    bind = op.get_bind()
    if WORKER_ROLE in _existing_roles(bind):
        op.execute(sa.text(f"REVOKE ALL ON {OUTBOX_TABLE} FROM {WORKER_ROLE}"))
        for table in READ_TABLES:
            op.execute(sa.text(f"REVOKE ALL ON {table} FROM {WORKER_ROLE}"))
        op.execute(sa.text(f"REVOKE USAGE ON SCHEMA public FROM {WORKER_ROLE}"))
