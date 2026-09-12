"""Credential isolation: each process holds only its own role's database key.

ADR 0034. The boundary ADR 0029 declared was enforced by nothing. Both Compose
services carried `env_file: .env`, so the worker received `DATABASE_URL` — the API's
`travel_app` credential — and the API would have received `WORKER_DATABASE_URL` had
it been present in that file. The leak was symmetric and silent: adding a key to
`.env` widened both processes at once, with no failure and no test.

These tests pin the guard that makes a violation fatal. They deliberately assert on
the *key* named in the message, not merely that an error was raised: a guard that
raised while naming the wrong key would send an operator to fix the wrong variable.
"""

from __future__ import annotations

import asyncio
import pathlib
import re

import pytest
import yaml

from backend.app import main
from backend.app.config import (
    CredentialIsolationError,
    assert_credential_isolation,
)
from backend.memory.write_pipeline import runtime

API_URL = "postgresql+psycopg://travel_app:app-secret-sentinel@db:5432/travel_agent"
WORKER_URL = "postgresql+psycopg://travel_worker:worker-secret-sentinel@db:5432/travel_agent"


def _named_keys(message: str) -> set[str]:
    """Return the environment-variable-shaped tokens a message names.

    Tokenised rather than substring-matched on purpose: `WORKER_DATABASE_URL`
    contains `DATABASE_URL`, so `"DATABASE_URL" in message` would pass even if the
    guard named the wrong key — and a guard that names the wrong key sends an
    operator to fix the wrong variable.
    """
    return set(re.findall(r"[A-Z][A-Z_]{3,}", message))


def test_worker_rejects_the_api_database_key():
    """The defect: the worker must never hold the API's credential."""
    with pytest.raises(CredentialIsolationError) as excinfo:
        assert_credential_isolation(
            "worker",
            {"WORKER_DATABASE_URL": WORKER_URL, "DATABASE_URL": API_URL},
        )

    named = _named_keys(str(excinfo.value))
    assert "DATABASE_URL" in named
    assert "WORKER_DATABASE_URL" not in named, (
        "the guard must name the offending key, not the role's own key"
    )


def test_api_rejects_the_worker_database_key():
    """The reverse direction: the leak was symmetric, so the guard must be too."""
    with pytest.raises(CredentialIsolationError) as excinfo:
        assert_credential_isolation(
            "api",
            {"DATABASE_URL": API_URL, "WORKER_DATABASE_URL": WORKER_URL},
        )

    named = _named_keys(str(excinfo.value))
    assert "WORKER_DATABASE_URL" in named
    assert "DATABASE_URL" not in named


@pytest.mark.parametrize(
    ("role", "own_key", "own_value"),
    [
        ("api", "DATABASE_URL", API_URL),
        ("worker", "WORKER_DATABASE_URL", WORKER_URL),
    ],
)
def test_each_role_accepts_its_own_key_alone(role, own_key, own_value):
    """A correct environment must not be refused."""
    assert_credential_isolation(role, {own_key: own_value})


def test_an_unrelated_key_is_accepted():
    """Only the other role's database credential is forbidden."""
    assert_credential_isolation(
        "worker",
        {
            "WORKER_DATABASE_URL": WORKER_URL,
            "GITHUB_TOKEN": "gh_sentinel",
            "LLM_MODEL": "deepseek-v4.1-flash",
            "MEMORY_WRITE_PIPELINE_ENABLED": "false",
        },
    )


def test_an_empty_environment_is_accepted():
    """Absent configuration is not a boundary violation; resolution fails elsewhere."""
    assert_credential_isolation("api", {})
    assert_credential_isolation("worker", {})


def test_unknown_role_is_rejected():
    """A typo must not silently disable the guard."""
    with pytest.raises(ValueError) as excinfo:
        assert_credential_isolation("workre", {})
    assert "workre" in str(excinfo.value)


def test_the_message_names_no_credential_value():
    """A boundary error is logged, and a log is less protected than the database."""
    with pytest.raises(CredentialIsolationError) as excinfo:
        assert_credential_isolation(
            "worker",
            {"WORKER_DATABASE_URL": WORKER_URL, "DATABASE_URL": API_URL},
        )

    message = str(excinfo.value)
    assert "app-secret-sentinel" not in message
    assert "worker-secret-sentinel" not in message


def test_reads_the_process_environment_by_default(monkeypatch):
    """The real call sites pass no mapping, so the default path must work."""
    monkeypatch.setenv("WORKER_DATABASE_URL", WORKER_URL)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert_credential_isolation("worker")

    monkeypatch.setenv("DATABASE_URL", API_URL)
    with pytest.raises(CredentialIsolationError):
        assert_credential_isolation("worker")


# --- Entry-point wiring -------------------------------------------------------
#
# The guard only matters if a process actually calls it, and calls it before it
# connects. Both assertions below are behavioural rather than source-inspection:
# each one observes whether a connection attempt was reached.


def _enter_lifespan():
    """Drive the API's real lifespan, with the container replaced.

    `RuntimeContainer` is stubbed so that a run in which the guard does *not*
    fire fails on the stub rather than pre-warming an embedding model — a red
    test has to be fast and unambiguous, not merely red.
    """

    class _ExplodingContainer:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError(
                "the lifespan reached RuntimeContainer; the isolation guard did not run first"
            )

    async def _run():
        async with main.lifespan(main.app):
            pass

    return _ExplodingContainer, _run


def test_the_api_lifespan_refuses_a_leaked_worker_credential(monkeypatch):
    monkeypatch.setenv("WORKER_DATABASE_URL", WORKER_URL)
    stub, run = _enter_lifespan()
    monkeypatch.setattr(main, "RuntimeContainer", stub)

    with pytest.raises(CredentialIsolationError):
        asyncio.run(run())


def test_the_api_lifespan_proceeds_when_the_environment_is_isolated(monkeypatch):
    """The guard must not block a correct environment."""
    monkeypatch.delenv("WORKER_DATABASE_URL", raising=False)
    stub, run = _enter_lifespan()
    monkeypatch.setattr(main, "RuntimeContainer", stub)

    with pytest.raises(AssertionError, match="reached RuntimeContainer"):
        asyncio.run(run())


def test_the_worker_main_refuses_a_leaked_api_credential(monkeypatch):
    """`main` fails closed and, crucially, never builds an engine."""
    monkeypatch.setenv("DATABASE_URL", API_URL)
    monkeypatch.setenv("WORKER_DATABASE_URL", WORKER_URL)

    reached: list[str] = []
    monkeypatch.setattr(runtime, "create_engine", lambda dsn: reached.append(dsn))

    assert runtime.main([]) == 1
    assert reached == [], "the guard must run before any connection is attempted"


def test_the_worker_main_reaches_the_engine_when_the_environment_is_isolated(monkeypatch):
    """The complement: the guard is not simply blocking every worker start."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("WORKER_DATABASE_URL", WORKER_URL)

    reached: list[str] = []
    monkeypatch.setattr(runtime, "create_engine", lambda dsn: reached.append(dsn))

    # `main` returns 1 because the recorder hands `build_worker` a `None` engine.
    assert runtime.main([]) == 1
    assert len(reached) == 1, "an isolated worker must get as far as building its engine"


# --- The Compose boundary -----------------------------------------------------
#
# Read statically from the file rather than from `docker compose config`, so the
# regression guard runs without a Docker daemon. The defect these pin is not a
# value but a *mechanism*: `env_file` injects every key, so re-adding it silently
# widens both processes at once — which is exactly how the boundary was lost.

COMPOSE_PATH = pathlib.Path(__file__).resolve().parents[3] / "docker-compose.yml"


def _service(name: str) -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))["services"][name]


@pytest.mark.parametrize("service", ["backend", "worker"])
def test_no_service_injects_the_whole_env_file(service):
    assert "env_file" not in _service(service), (
        f"{service} must declare its variables explicitly; `env_file` hands the "
        "process every key in the file, including the other role's credential"
    )


def test_the_worker_allow_list_excludes_the_api_credential():
    joined = " ".join(_service("worker")["environment"])
    assert "WORKER_DATABASE_URL" in joined
    assert not re.search(r"(?<!WORKER_)DATABASE_URL", joined), (
        "the worker must not be handed the API's database credential"
    )
    assert "LOCAL_AUTH_TOKENS_JSON" not in joined, (
        "auth material belongs to the API process, not the worker"
    )


def test_the_api_allow_list_excludes_the_worker_credential():
    joined = " ".join(_service("backend")["environment"])
    assert "DATABASE_URL" in joined
    assert "WORKER_DATABASE_URL" not in joined
