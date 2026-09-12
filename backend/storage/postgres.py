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

#: Single source of truth for the expected Alembic head revision. The
#: runtime readiness probe and the migration chain both derive from this
#: instead of carrying their own literal, so they cannot drift apart.
ALEMBIC_HEAD = "20260912_02"


class TenantContextError(Exception):
    """No tenant identity is bound to the current transaction."""


class PrivilegedRoleError(RuntimeError):
    """The connected role is a superuser or bypasses row-level security."""


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


def assert_least_privilege_role(
    engine: Engine,
    *,
    allowed: bool,
    context: str = "RuntimeContainer",
) -> None:
    """Reject a superuser or ``BYPASSRLS`` role unless explicitly allowed.

    ``FORCE ROW LEVEL SECURITY`` is decorative for a superuser and for a role
    carrying ``BYPASSRLS``, so a connection that lands on either silently
    disables every tenant policy. Every process that must enforce tenant
    isolation calls this at startup: the API runtime today, and the background
    worker when it is mounted. ``allowed`` comes from
    ``ALLOW_PRIVILEGED_DB_ROLE``, which exists only for throwaway local
    development against a superuser-owned database.

    Raises:
        PrivilegedRoleError: The connected role is a superuser or bypasses RLS.
    """
    if allowed:
        logger.warning(
            "%s starting with a privileged database role "
            "(ALLOW_PRIVILEGED_DB_ROLE=true); tenant RLS is not enforced.",
            context,
        )
        return
    with engine.connect() as connection:
        elevated = connection.execute(
            text(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles "
                "WHERE rolname = CURRENT_USER"
            )
        ).scalar()
    if elevated is True:
        raise PrivilegedRoleError(
            "Refusing to start: the database role is a superuser or "
            "bypasses row-level security. Connect as the least-privilege "
            "application role, or set ALLOW_PRIVILEGED_DB_ROLE=true only "
            "for throwaway local development."
        )


def resolve_migration_dsn(
    pg_dsn: str | None,
    configured_url: str | None,
    database_url: str | None,
) -> str:
    """Resolve the migration DSN from explicit inputs (pure, unit-testable).

    Precedence: `PG_DSN` (bootstrap superuser) first so schema work never
    runs with the least-privilege runtime role by accident, then an
    explicitly configured `sqlalchemy.url` (tests, one-off runs), then
    `DATABASE_URL` as a convenience for privileged local setups.
    """
    for candidate in (pg_dsn, configured_url, database_url):
        if candidate is not None and candidate.strip():
            return candidate.strip()
    raise RuntimeError(
        "Set PG_DSN (superuser, preferred) or DATABASE_URL to a PostgreSQL "
        "address before running migrations."
    )


def require_migration_privilege(connection: Connection) -> None:
    """Fail fast unless the connection runs as a database superuser.

    Schema work (CREATE ROLE, GRANT, FORCE ROW LEVEL SECURITY) requires
    the bootstrap superuser. The least-privilege runtime role must never
    reach migrations — callers run them with PG_DSN instead. Raises
    `RuntimeError` with guidance; propagates connection errors unchanged.
    """
    is_superuser = connection.execute(
        text("SELECT rolsuper FROM pg_roles WHERE rolname = CURRENT_USER")
    ).scalar()
    if is_superuser is not True:
        raise RuntimeError(
            "Refusing to migrate as a non-superuser role. Run Alembic "
            "with PG_DSN pointing at the bootstrap superuser, never "
            "with the least-privilege runtime DATABASE_URL."
        )


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
