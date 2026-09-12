"""The DDL test DSN must not be able to point at a real database.

`migration_dsn()` drives `DROP SCHEMA public CASCADE` in six integration modules.
It used to fall back to `PG_DSN`, which `.env.example` documents as the real
development database, so a developer who set `PG_DSN` and ran the suite without
`PG_TEST_DSN` would drop their own schema. These tests pin both halves of the
fix: no fallback, and a name that must be recognisably disposable.
"""

import pytest

from backend.tests.integration import pg_dsn


def test_migration_dsn_has_no_fallback_to_pg_dsn(monkeypatch):
    monkeypatch.delenv("PG_TEST_DSN", raising=False)
    monkeypatch.setenv("PG_DSN", "postgresql+psycopg://u:p@db:5433/travel_agent")

    assert pg_dsn.migration_dsn() is None, (
        "PG_DSN is the real development database; falling back to it would let "
        "the suite drop the developer's own schema"
    )


def test_migration_dsn_refuses_a_database_that_is_not_disposable(monkeypatch):
    monkeypatch.setenv("PG_TEST_DSN", "postgresql+psycopg://u:p@db:5433/travel_agent")

    with pytest.raises(RuntimeError, match="not recognisably disposable"):
        pg_dsn.migration_dsn()


def test_migration_dsn_accepts_a_disposable_database(monkeypatch):
    dsn = "postgresql+psycopg://u:p@db:5433/travel_test"
    monkeypatch.setenv("PG_TEST_DSN", dsn)

    assert pg_dsn.migration_dsn() == dsn


def test_runtime_dsn_still_falls_back_to_the_test_dsn(monkeypatch):
    """Both of its variables are test variables, so the fallback is safe."""
    dsn = "postgresql+psycopg://u:p@db:5433/travel_test"
    monkeypatch.delenv("PG_RUNTIME_TEST_DSN", raising=False)
    monkeypatch.setenv("PG_TEST_DSN", dsn)

    assert pg_dsn.runtime_dsn() == dsn
