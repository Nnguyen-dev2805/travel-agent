"""Alembic migration environment for the memory write path.

The database address comes from the PG_DSN environment variable and
overrides the credential-free placeholder in alembic.ini, so no secret
is ever committed. Migrations run inside one transaction per revision.
"""

import os

from alembic import context

config = context.config


def _dsn() -> str:
    dsn = os.environ.get("PG_DSN") or config.get_main_option("sqlalchemy.url")
    if not dsn:
        raise RuntimeError(
            "Set PG_DSN to a PostgreSQL address before running migrations."
        )
    return dsn


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

    engine = create_engine(_dsn(), pool_pre_ping=True)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
