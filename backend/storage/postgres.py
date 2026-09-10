"""PostgreSQL engine, transaction, and tenant-context helpers.

No product policy lives here: this module opens connections, scopes
transactions at READ COMMITTED, and sets/verifies the `app.tenant`
session marker that row-level-security policies and adapters rely on.
DSNs and passwords must never appear in raised messages or logs.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine as _create_engine
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger("travel_agent_postgres")

TENANT_SETTING = "app.tenant"


class TenantContextError(Exception):
    """No tenant identity is bound to the current transaction."""


def create_engine(dsn: str, *, pool_size: int = 5, pool_timeout: int = 30) -> Engine:
    """Create a psycopg engine with connection liveness checks.

    Raises:
        ValueError: The DSN is blank or the engine cannot be created.
            Messages never carry the DSN itself.
    """
    if not isinstance(dsn, str) or not dsn.strip():
        raise ValueError("A PostgreSQL DSN string is required.")
    try:
        return _create_engine(
            dsn,
            pool_size=pool_size,
            pool_timeout=pool_timeout,
            pool_pre_ping=True,
        )
    except Exception as error:
        logger.error(
            "postgres.engine unavailable failure_class=%s",
            type(error).__name__,
        )
        raise ValueError("Could not create the PostgreSQL engine.") from error


@contextmanager
def transaction(engine: Engine) -> Iterator[Connection]:
    """Yield one connection inside a READ COMMITTED transaction.

    Commits on clean exit and rolls back on any error. `SET LOCAL`
    markers (including the tenant) reset automatically with the
    transaction, so no explicit reset is required.
    """
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="READ COMMITTED")
        with connection.begin():
            yield connection


def set_tenant(connection: Connection, owner_user_id: str) -> None:
    """Bind the tenant marker for the current transaction only."""
    if not isinstance(owner_user_id, str) or not owner_user_id.strip():
        raise TenantContextError("A non-blank tenant identity is required.")
    connection.execute(
        text("SELECT set_config(:name, :value, true)"),
        {"name": TENANT_SETTING, "value": owner_user_id.strip()},
    )


def require_tenant_context(connection: Connection) -> str:
    """Return the bound tenant or fail closed when none is bound."""
    value = connection.execute(
        text("SELECT current_setting(:name, true)"), {"name": TENANT_SETTING}
    ).scalar()
    if not isinstance(value, str) or not value.strip():
        raise TenantContextError(
            "No tenant identity is bound to the current transaction."
        )
    return value.strip()


def alembic_config(script_location: str, dsn: str):
    """Build an Alembic Config for the bundled migrations.

    The DSN travels as a caller-supplied argument (environment in
    practice), never from a committed file. Alembic is imported lazily
    so plain engine users never pay for the migration dependency.
    """
    from alembic.config import Config

    if not isinstance(script_location, str) or not script_location.strip():
        raise ValueError("A migrations script location is required.")
    if not isinstance(dsn, str) or not dsn.strip():
        raise ValueError("A PostgreSQL DSN string is required.")
    config = Config()
    config.set_main_option("script_location", script_location)
    config.set_main_option("sqlalchemy.url", dsn)
    return config
