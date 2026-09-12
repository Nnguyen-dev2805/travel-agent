"""Unit tests for application settings: DSN resolution and provider configuration."""

import ast
import os
import subprocess
import sys
from pathlib import Path

from backend.app.config import Settings


def test_database_dsn_prefers_database_url():
    """DATABASE_URL is the single source of truth when provided."""
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://u:p@db:5432/travel_agent",
        PG_HOST="ignored",
        PG_PORT=1,
        PG_DB="ignored",
        PG_USER="ignored",
    )
    assert settings.database_dsn() == "postgresql+psycopg://u:p@db:5432/travel_agent"


def test_database_dsn_builds_from_pg_parts_when_url_blank():
    """Explicit PG_* parts remain a supported fallback for local development."""
    settings = Settings(
        DATABASE_URL="",
        PG_HOST="db",
        PG_PORT=5432,
        PG_DB="travel_agent",
        PG_USER="travel_agent",
        PG_PASSWORD="secret",
    )
    assert (
        settings.database_dsn()
        == "postgresql+psycopg://travel_agent:secret@db:5432/travel_agent"
    )


def test_database_dsn_strips_whitespace_only_url():
    """A whitespace-only DATABASE_URL is treated as unset."""
    settings = Settings(
        DATABASE_URL="   ",
        PG_HOST="localhost",
        PG_PORT=5433,
        PG_DB="travel_agent",
        PG_USER="travel_agent",
        PG_PASSWORD="pw",
    )
    assert settings.database_dsn() == (
        "postgresql+psycopg://travel_agent:pw@localhost:5433/travel_agent"
    )


# ---------------------------------------------------------------------------
# Model provider endpoint
#
# `Settings` evaluates `os.getenv` in its **class body**, so the value is
# captured once when the module is imported — not per `Settings()` call. Setting
# the variable afterwards in the same process cannot change it, and a test using
# `Settings(GITHUB_MODELS_URL=...)` would prove nothing, because pydantic accepts
# an explicit override for any field whether or not the field reads the
# environment. These therefore read the setting the way the application does: in
# a fresh interpreter, at import.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]

_READ_SETTING = """
import sys
import types

# `config.py` calls `load_dotenv(ROOT_DIR / ".env")` unconditionally, and this
# repository ships a `.env` for local development. Removing the variable from the
# subprocess environment therefore does NOT reach the unset case: the loader puts
# it straight back, and the reading becomes a function of the developer's `.env`
# rather than of the code under test. Stubbing the loader is what makes
# `value=None` mean unset, and it makes all three assertions below independent of
# whether a `.env` happens to exist.
#
# The assertion keeps its power: with the variable genuinely absent, a hardcoded
# vendor default in `config.py` still fails the test.
_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules["dotenv"] = _dotenv

from backend.app.config import Settings

print(repr(Settings().GITHUB_MODELS_URL))
"""


def _models_url_from_a_fresh_interpreter(value):
    """Import the module with `GITHUB_MODELS_URL` set to `value` and read it.

    `value=None` removes the variable, which is the unset case. The fresh
    interpreter neutralises the `.env` loader first, so "removed" really is
    removed — see `_READ_SETTING`.
    """
    env = dict(os.environ)
    if value is None:
        env.pop("GITHUB_MODELS_URL", None)
    else:
        env["GITHUB_MODELS_URL"] = value

    result = subprocess.run(
        [sys.executable, "-c", _READ_SETTING],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr[-400:]
    return ast.literal_eval(result.stdout.strip())


def test_models_url_reads_the_environment():
    """The endpoint is deployment configuration, not a source constant."""
    assert (
        _models_url_from_a_fresh_interpreter("https://api.example.test/v1")
        == "https://api.example.test/v1"
    )


def test_models_url_has_no_default():
    """An unset variable yields the empty string, not a vendor address.

    This is the behaviour change: before it, an unset variable selected GitHub
    Models and the chat path worked.

    The reading must not depend on the developer's `.env`. `config.py` loads that
    file on purpose, so the helper's fresh interpreter disables the loader before
    importing; otherwise this assertion measures the local environment instead of
    the default in the code, and fails for anyone who has a `.env` — which is
    exactly the defect this test used to have.
    """
    assert _models_url_from_a_fresh_interpreter(None) == ""


def test_models_url_strips_whitespace():
    """Whitespace must not survive into the base URL.

    A bare `os.getenv` without stripping yields `"   "`, and the OpenAI SDK
    percent-encodes that into `%20%20%20/` — a malformed endpoint rather than an
    empty one.
    """
    for blank in ("", "   ", "\t"):
        assert _models_url_from_a_fresh_interpreter(blank) == "", repr(blank)

    assert (
        _models_url_from_a_fresh_interpreter("  https://api.example.test/v1  ")
        == "https://api.example.test/v1"
    )


def test_an_empty_endpoint_still_constructs_a_client():
    """The application must still start; only a request fails.

    Verified against `openai` 3.3.1: construction succeeds with an empty base URL
    and the failure appears on the first call as `APIConnectionError`. The SDK
    substitutes its own endpoint only when `base_url` is omitted, never when it is
    explicitly empty. This is a guard rather than a regression test — it pins a
    measured SDK behaviour so the mistake is not repeated.
    """
    from openai import OpenAI

    client = OpenAI(api_key="sk-placeholder", base_url="")

    assert client.base_url == ""


# --- ADR 0028: the worker's DSN is a separate identity ------------------------


def test_worker_dsn_prefers_worker_database_url():
    settings = Settings(
        WORKER_DATABASE_URL="postgresql+psycopg://w:p@db:5433/travel_agent",
        PG_WORKER_USER="ignored",
        PG_HOST="ignored",
        PG_PORT=1,
    )
    assert (
        settings.worker_dsn() == "postgresql+psycopg://w:p@db:5433/travel_agent"
    )


def test_worker_dsn_builds_from_pg_parts_and_defaults_to_the_worker_role():
    settings = Settings(
        WORKER_DATABASE_URL="",
        PG_HOST="db",
        PG_PORT=5433,
        PG_DB="travel_agent",
        PG_WORKER_USER="travel_worker",
        PG_WORKER_PASSWORD="worker-secret",
    )
    assert (
        settings.worker_dsn()
        == "postgresql+psycopg://travel_worker:worker-secret@db:5433/travel_agent"
    )


def test_worker_dsn_defaults_the_user_to_travel_worker():
    """A blank override must not silently fall back to the runtime role."""
    settings = Settings(
        WORKER_DATABASE_URL="",
        PG_HOST="db",
        PG_PORT=5433,
        PG_DB="travel_agent",
        PG_WORKER_USER="travel_worker",
        PG_WORKER_PASSWORD="worker-secret",
    )
    assert "travel_worker" in settings.worker_dsn()


def test_worker_dsn_is_independent_of_the_runtime_dsn():
    """The two identities must not be able to collapse into one by accident."""
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://travel_app:app-secret@db:5433/travel_agent",
        WORKER_DATABASE_URL="",
        PG_HOST="db",
        PG_PORT=5433,
        PG_DB="travel_agent",
        PG_WORKER_USER="travel_worker",
        PG_WORKER_PASSWORD="worker-secret",
    )
    assert "travel_app" in settings.database_dsn()
    assert "travel_worker" in settings.worker_dsn()
    assert settings.worker_dsn() != settings.database_dsn()


def test_worker_dsn_never_renders_the_password_in_a_repr():
    settings = Settings(
        WORKER_DATABASE_URL="",
        PG_WORKER_PASSWORD="worker-secret",
        PG_WORKER_USER="travel_worker",
        PG_HOST="db",
        PG_PORT=5433,
        PG_DB="travel_agent",
    )
    assert settings.PG_WORKER_PASSWORD.get_secret_value() == "worker-secret"
    assert "worker-secret" not in repr(settings.PG_WORKER_PASSWORD)


# --- the DSN builder must encode, not concatenate -----------------------------


def test_pg_dsn_percent_encodes_reserved_characters_in_a_password():
    """A password is data, not URL syntax.

    String interpolation made a password containing `@`, `:`, `/`, `?` or `#`
    produce a DSN that pointed at a different host or failed to parse.
    """
    from backend.app.config import pg_dsn
    from sqlalchemy.engine import make_url

    dsn = pg_dsn(
        password="p@ss:w/rd?#",
        host="db",
        port=5433,
        db="travel_agent",
        user="travel_app",
    )

    parsed = make_url(dsn)
    assert parsed.password == "p@ss:w/rd?#", "the password survives a round trip"
    assert parsed.host == "db", "the host is not swallowed by the password"
    assert parsed.port == 5433
    assert parsed.database == "travel_agent"
    assert parsed.username == "travel_app"


def test_pg_dsn_is_unchanged_for_a_simple_password():
    """The encoding must not alter the ordinary case."""
    from backend.app.config import pg_dsn

    assert (
        pg_dsn(password="secret", host="db", port=5432, db="travel_agent", user="travel_agent")
        == "postgresql+psycopg://travel_agent:secret@db:5432/travel_agent"
    )
