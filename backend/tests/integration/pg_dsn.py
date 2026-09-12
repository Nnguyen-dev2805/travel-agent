"""PostgreSQL DSN resolution for the integration suite.

Two roles, two needs, one variable each — because a single variable cannot
satisfy both.

* **Runtime role** (least-privilege, e.g. `travel_app`): `NOSUPERUSER`,
  `NOBYPASSRLS`. Only a connection without `BYPASSRLS` is subject to row-level
  security, so a test that proves tenant isolation must use this role. A
  superuser connection silently bypasses every policy, so such a test passes
  whether or not the policy exists. `assert_rls_enforced` checks this rather
  than trusting the environment.

* **Migration role** (DDL-capable, e.g. `travel_agent`): the migration tests run
  `DROP SCHEMA public CASCADE` and `alembic upgrade`/`downgrade`, which the
  runtime role is deliberately not granted.

Resolution order:

    migration_dsn()  ->  PG_TEST_DSN only, never PG_DSN. No fallback: see the
                         function docstring. The database name must end in
                         `_test` or collection fails loudly.
    runtime_dsn()    ->  PG_RUNTIME_TEST_DSN, then PG_TEST_DSN
    worker_dsn()     ->  PG_WORKER_TEST_DSN, else the migration DSN with the
                         worker role's credentials substituted

Pointing both variables at one role makes one of the two suites lie: a DDL role
makes the isolation assertions vacuous, and a least-privilege role cannot run
the migration tests at all. This mirrors production, where `PG_DSN` is the
bootstrap superuser and the application connects as the runtime role.

**The worker role is a third identity** (ADR 0028). It is also
`NOSUPERUSER NOBYPASSRLS`, but it carries a policy that admits it to the
cross-owner outbox queue. It therefore cannot stand in for either of the other
two: the migration role would bypass the policy, and the runtime role is refused
by it.
"""

import os

import sqlalchemy as sa

#: Test-only credential for the worker role. The migration creates
#: `travel_worker` NOLOGIN on purpose; `docker/postgres/init-app-role.sh`
#: provisions the real credential in a deployment, and this suite provisions the
#: same thing locally so the claim boundary can be proved against the real role.
WORKER_TEST_PASSWORD = "worker-password-dev-only"

WORKER_ROLE = "travel_worker"


def _assert_disposable(dsn: str) -> str:
    """Refuse a schema-dropping DSN that does not name a disposable database.

    Belt and braces. The fallback that made this dangerous is gone, but a
    `PG_TEST_DSN` aimed at a real database would still have six modules drop its
    schema, so the name is checked too. A database whose name does not end in
    `_test` is not recognisably disposable and is refused loudly at collection.
    """
    from sqlalchemy.engine import make_url

    name = make_url(dsn).database or ""
    if not name.endswith("_test"):
        raise RuntimeError(
            f"Refusing to use {name!r} as the schema-dropping test database: its "
            "name does not end in '_test', so it is not recognisably disposable. "
            "Point PG_TEST_DSN at a throwaway database."
        )
    return dsn


def migration_dsn() -> str | None:
    """The DDL-capable DSN: migrations and `DROP SCHEMA public CASCADE`.

    **Deliberately no fallback to `PG_DSN`.** This value drives
    `DROP SCHEMA public CASCADE` in six modules, and `.env.example` documents
    `PG_DSN` as the real development database (`.../travel_agent`). Falling back
    to it meant that a developer who set `PG_DSN` and ran the suite without
    `PG_TEST_DSN` would silently drop their own development schema. With the
    fallback removed, the DDL tests skip when `PG_TEST_DSN` is unset — the
    documented single-DSN convenience is not worth a destructive surprise.
    """
    raw = os.environ.get("PG_TEST_DSN")
    if not raw:
        return None
    return _assert_disposable(raw)


def runtime_dsn() -> str | None:
    """The least-privilege DSN: the only role subject to row-level security."""
    return os.environ.get("PG_RUNTIME_TEST_DSN") or os.environ.get("PG_TEST_DSN")


def worker_dsn() -> str | None:
    """The worker DSN: claims a cross-owner queue under a least-privilege role.

    Derived from the migration DSN so a single-variable setup still works; the
    host, port and database are the same and only the credentials differ.
    """
    explicit = os.environ.get("PG_WORKER_TEST_DSN")
    if explicit:
        return explicit
    base = migration_dsn()
    if not base:
        return None
    from sqlalchemy.engine import make_url

    url = make_url(base)
    return url.set(
        username=WORKER_ROLE, password=WORKER_TEST_PASSWORD
    ).render_as_string(hide_password=False)


def ensure_worker_login(engine: sa.Engine, password: str = WORKER_TEST_PASSWORD) -> None:
    """Give the worker role a login credential, as the bootstrap script does.

    The migration creates the role `NOLOGIN` deliberately. `ALTER ROLE ... PASSWORD`
    is a utility statement and takes no bind parameter, so the password is
    interpolated; it is a module constant for a disposable test database, never
    caller input.
    """
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                f"ALTER ROLE {WORKER_ROLE} WITH LOGIN NOSUPERUSER NOBYPASSRLS "
                f"NOCREATEDB NOCREATEROLE NOREPLICATION "
                f"PASSWORD '{password}'"
            )
        )


def require(dsn: str | None, variable: str) -> str:
    """Return `dsn`, or fail loudly.

    The module-level skip guard covers collection. Reaching here without a DSN
    means the address vanished mid-run, which must not be mistaken for a pass.
    """
    if not dsn:
        raise RuntimeError(
            f"{variable} is required for this PostgreSQL integration test. "
            "The module-level skipif guards collection; reaching here means "
            "the database address vanished mid-run."
        )
    return dsn


def assert_rls_enforced(engine: sa.Engine, variable: str) -> None:
    """Refuse to run an isolation assertion on a role that bypasses RLS.

    A `SUPERUSER` or `BYPASSRLS` role ignores every policy, so an isolation test
    written against one passes whether or not the policy exists — the exact
    false confidence this suite exists to prevent. The role is therefore
    inspected rather than assumed.
    """
    with engine.connect() as connection:
        superuser, bypass_rls = connection.execute(
            sa.text(
                "SELECT rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = CURRENT_USER"
            )
        ).one()

    if superuser or bypass_rls:
        raise RuntimeError(
            f"{variable} connects as a role with rolsuper={superuser} "
            f"rolbypassrls={bypass_rls}. Row-level security is not enforced for "
            "that role, so tenant-isolation assertions made through it are "
            "vacuous. Point it at the least-privilege runtime role."
        )
