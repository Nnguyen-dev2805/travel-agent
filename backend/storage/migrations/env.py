"""Alembic migration environment for the memory write path.

The database address comes from the PG_DSN environment variable and
overrides the credential-free placeholder in alembic.ini, so no secret
is ever committed. Migrations run inside one transaction per revision.
"""

import os

from alembic import context

from backend.storage.postgres import resolve_migration_dsn

config = context.config


def _dsn() -> str:
    """Resolve the migration DSN from the privileged source first.

    `PG_DSN` (bootstrap superuser) wins so schema work never runs with the
    least-privilege runtime role by accident. An explicitly configured
    `sqlalchemy.url` (tests, one-off runs) comes next, then `DATABASE_URL`
    as a convenience for privileged local setups. The placeholder in
    `alembic.ini` is intentionally blank and never a live address.
    """
    return resolve_migration_dsn(
        os.environ.get("PG_DSN"),
        config.get_main_option("sqlalchemy.url"),
        os.environ.get("DATABASE_URL"),
    )


def run_migrations_offline() -> None:
    """Run migrations without a live connection (SQL emission only)."""
    context.configure(
        url=_dsn(), literal_binds=True, dialect_opts={"paramstyle": "named"}
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the live isolated database."""
    from sqlalchemy import create_engine

    from backend.storage.postgres import require_migration_privilege

    engine = create_engine(_dsn(), pool_pre_ping=True)
    # Privilege check on a SEPARATE connection: executing anything on the
    # migration connection first would autobegin an outer transaction, and
    # Alembic's begin_transaction would then nest as a savepoint whose
    # commit is rolled back on close — silently dropping every revision.
    with engine.connect() as check_connection:
        require_migration_privilege(check_connection)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
