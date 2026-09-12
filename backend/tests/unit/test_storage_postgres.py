"""Unit tests for PostgreSQL DSN resolution and Compose wiring contracts.

Pins the privileged-source precedence reviewers asked for: migrations must
prefer the superuser `PG_DSN`, and the Compose backend must connect as the
least-privilege `travel_app` role over the in-network `db` host — never as
the bootstrap superuser on localhost.
"""

import re
from pathlib import Path

import pytest

from backend.storage.postgres import (
    require_migration_privilege,
    resolve_migration_dsn,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


def test_pg_dsn_wins_over_everything():
    assert (
        resolve_migration_dsn("pg_dsn_super", "configured_url", "database_url")
        == "pg_dsn_super"
    )


def test_configured_url_beats_database_url():
    assert (
        resolve_migration_dsn(None, "configured_url", "database_url")
        == "configured_url"
    )


def test_database_url_is_last_resort():
    assert resolve_migration_dsn(None, None, "database_url") == "database_url"
    assert resolve_migration_dsn("", "  ", "  database_url  ") == "database_url"


def test_blank_everything_fails_closed():
    with pytest.raises(RuntimeError, match="PG_DSN"):
        resolve_migration_dsn(None, None, None)
    with pytest.raises(RuntimeError, match="PG_DSN"):
        resolve_migration_dsn("", "   ", " ")


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _ScalarConnection:
    def __init__(self, value=None, error=None):
        self._value = value
        self._error = error
        self.statements = []

    def execute(self, stmt, params=None):
        self.statements.append(str(stmt))
        if self._error is not None:
            raise self._error
        return _ScalarResult(self._value)


def test_migration_privilege_accepts_superuser():
    require_migration_privilege(_ScalarConnection(value=True))


def test_migration_privilege_rejects_app_role():
    with pytest.raises(RuntimeError, match="non-superuser"):
        require_migration_privilege(_ScalarConnection(value=False))


def test_migration_privilege_rejects_unknown_flag():
    with pytest.raises(RuntimeError, match="non-superuser"):
        require_migration_privilege(_ScalarConnection(value=None))


def test_migration_privilege_propagates_connection_errors():
    with pytest.raises(ConnectionError, match="gone"):
        require_migration_privilege(_ScalarConnection(error=ConnectionError("gone")))


def _find_compose_file() -> Path | None:
    """Locate docker-compose.yml from the test file upward, if present."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        compose = candidate / "docker-compose.yml"
        if compose.is_file():
            return compose
    return None


def test_compose_backend_uses_app_role_on_db_host():
    """The Compose backend DATABASE_URL must name travel_app@db:5432."""
    compose_path = _find_compose_file()
    assert compose_path is not None, (
        "docker-compose.yml must be present to pin the backend DSN wiring"
    )
    compose = compose_path.read_text(encoding="utf-8")
    match = re.search(r"-\s*DATABASE_URL=(\S+)", compose)
    assert match is not None, "backend DATABASE_URL is not set in Compose"
    url = match.group(1)
    assert "travel_app:" in url, f"backend must connect as travel_app, got: {url}"
    assert "@db:5432/" in url, f"backend must use the in-network db host, got: {url}"
    assert "travel_agent:password@localhost" not in url, (
        "backend must not use the bootstrap superuser on localhost"
    )
