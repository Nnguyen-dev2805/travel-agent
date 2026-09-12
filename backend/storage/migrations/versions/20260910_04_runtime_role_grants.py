"""Least-privilege runtime role and table grants.

Revision ID: 20260910_04
Revises: 20260910_03
Create: 2026-09-10

Per the clean-break review findings, `FORCE ROW LEVEL SECURITY` alone does
not protect a deployment whose application connects as the bootstrap
superuser: superusers and `BYPASSRLS` roles bypass every policy, forced or
not. This revision separates the roles:

- `travel_app`: the only role the backend runtime may use. It is
  `NOSUPERUSER`/`NOBYPASSRLS` (verified below), owns nothing, and receives
  exactly the DML the product surface needs on the application tables
  (including `SELECT` on `alembic_version`, which the ops readiness probe
  reads to verify the migration head).
- The migration/bootstrap superuser keeps owning the schema and running
  Alembic; it must never appear in a runtime `DATABASE_URL`.

The role is created `NOLOGIN` here when provisioning scripts have not made
it yet; `docker/postgres/init-app-role.sh` (and production ops) grant
`LOGIN` with the real credential. Grants are idempotent and future tables
inherit them through default privileges, so re-running this revision is
safe. Downgrade revokes the grants and leaves role lifecycle to ops.
"""

from alembic import context, op
import sqlalchemy as sa

revision = "20260910_04"
down_revision = "20260910_03"
branch_labels = None
depends_on = None

APP_ROLE = "travel_app"


def _is_offline_mode() -> bool:
    try:
        return context.is_offline_mode()
    except Exception:
        return False


def upgrade() -> None:
    # APP_ROLE is a module constant, never caller input, so interpolation
    # here is safe: DO blocks cannot take bind parameters.
    op.execute(
        sa.text(
            f"DO $do$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN "
            f"CREATE ROLE {APP_ROLE} NOSUPERUSER NOBYPASSRLS "
            f"NOCREATEDB NOCREATEROLE NOREPLICATION NOLOGIN; "
            f"END IF; END $do$"
        )
    )
    # Belt and braces: a pre-existing role keeps no bypass, whatever made it.
    op.execute(sa.text("ALTER ROLE travel_app NOSUPERUSER NOBYPASSRLS"))
    op.execute(sa.text("GRANT USAGE ON SCHEMA public TO travel_app"))
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE, DELETE "
            "ON ALL TABLES IN SCHEMA public TO travel_app"
        )
    )
    op.execute(
        sa.text(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO travel_app"
        )
    )


def downgrade() -> None:
    if _is_offline_mode():
        op.execute(
            sa.text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "REVOKE ALL ON TABLES FROM travel_app"
            )
        )
        op.execute(sa.text("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM travel_app"))
        op.execute(sa.text("REVOKE USAGE ON SCHEMA public FROM travel_app"))
        return

    bind = op.get_bind()
    roles = {
        row[0]
        for row in bind.execute(sa.text("SELECT rolname FROM pg_roles")).fetchall()
    }
    if APP_ROLE in roles:
        op.execute(
            sa.text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "REVOKE ALL ON TABLES FROM travel_app"
            )
        )
        op.execute(sa.text("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM travel_app"))
        op.execute(sa.text("REVOKE USAGE ON SCHEMA public FROM travel_app"))
