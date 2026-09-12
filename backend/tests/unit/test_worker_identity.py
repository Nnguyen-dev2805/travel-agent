"""ADR 0032: a lease is held by an identity that identifies a process.

`mark_failed`, `mark_succeeded` and `cancel_events(lease_owner=…)` all key on
`holder == lease_owner`. `WORKER_ID` defaulted to the constant
`"memory_worker_1"`, so two replicas started from the same configuration were
indistinguishable: one worker's lease loss could clear or cancel the other's row.
The defect appears the first time the worker is scaled horizontally, which is the
ordinary deployment rather than an exotic one.

**These tests spawn an interpreter, and they must.** `backend/app/config.py`
evaluates `os.getenv` in the `Settings` class body, so the value is captured once
at import. A `monkeypatch.setenv(...)` followed by `Settings()` returns the
import-time value and asserts nothing; and `Settings(WORKER_ID=...)` proves nothing
either, because pydantic accepts an explicit override whether or not the field
reads the environment. The only faithful read is the one the application performs —
in a fresh interpreter, at import, with a controlled environment.
"""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# Print the setting alongside the child's own hostname and pid, so the derivation
# can be asserted exactly rather than by shape.
_READ = (
    "import os, socket;"
    "from backend.app.config import Settings;"
    "print(repr((Settings().WORKER_ID, socket.gethostname(), os.getpid())))"
)

OLD_CONSTANT = "memory_worker_1"


def _read(value: str | None) -> tuple[str, str, int]:
    """Import `Settings` in a fresh interpreter and return its resolved identity."""
    env = dict(os.environ)
    if value is None:
        env.pop("WORKER_ID", None)
    else:
        env["WORKER_ID"] = value
    result = subprocess.run(
        [sys.executable, "-c", _READ],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr[-500:]
    return ast.literal_eval(result.stdout.strip())


def test_an_unset_worker_id_is_derived_from_the_process():
    worker_id, hostname, pid = _read(None)

    assert worker_id == f"{hostname}-{pid}", (
        "an unset WORKER_ID must identify the process, not a shared constant"
    )
    assert worker_id != OLD_CONSTANT


def test_an_explicit_worker_id_is_honoured():
    """An operator may choose a stable identity and owns its uniqueness."""
    worker_id, _, _ = _read("worker-alpha")
    assert worker_id == "worker-alpha"


def test_a_blank_worker_id_falls_back_to_the_derived_identity():
    """`os.getenv` returns an empty string for a present-but-blank variable.

    A bare `os.getenv("WORKER_ID", default)` would return `""` here, and `""` as a
    lease owner is worse than the constant: every blank-configured replica would
    share one identity.
    """
    worker_id, hostname, pid = _read("")
    assert worker_id == f"{hostname}-{pid}"
    assert worker_id != ""


def test_a_whitespace_worker_id_falls_back_to_the_derived_identity():
    worker_id, hostname, pid = _read("   ")
    assert worker_id == f"{hostname}-{pid}"


def test_two_processes_do_not_share_a_derived_identity():
    """The property that matters: `holder == lease_owner` must separate replicas.

    This is the defect. Under the old constant default, both reads below returned
    `memory_worker_1` and the assertion failed.
    """
    first, _, _ = _read(None)
    second, _, _ = _read(None)

    assert first != second, (
        "two worker processes must not share a lease owner identity, or one "
        "replica's lease loss can cancel the other's work"
    )


@pytest.mark.parametrize("value", [None, "", "   "])
def test_no_configuration_yields_an_empty_lease_owner(value):
    worker_id, _, _ = _read(value)
    assert worker_id.strip() != ""


def test_the_worker_constructor_has_no_default_identity():
    """A second copy of the constant lived in `MemoryOutboxWorker.__init__`.

    `Settings.WORKER_ID` was fixed first, but the constructor still defaulted to
    `"memory_worker_1"`, so a caller that omitted it reintroduced the collision the
    ADR removes. Asserted structurally because the failure is silent: the worker
    runs, and two replicas simply share a lease owner.
    """
    import inspect

    from backend.memory.write_pipeline.worker import MemoryOutboxWorker

    parameter = inspect.signature(MemoryOutboxWorker.__init__).parameters["worker_id"]
    assert parameter.default is inspect.Parameter.empty, (
        "the lease owner identity must be supplied, not defaulted"
    )


def test_no_module_still_carries_the_constant_as_live_code():
    """The constant may survive only in comments explaining what it was.

    Walks the AST rather than grepping, because a grep cannot tell a live string
    literal from a docstring or a comment — and a comment describing the old
    default is exactly what should remain.
    """
    import ast

    repo_root = pathlib.Path(__file__).resolve().parents[3]
    offenders = []
    for path in (repo_root / "backend").rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))

        # Docstrings are `Expr(Constant(str))` as the first statement of a scope.
        docstrings = set()
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(body, list) and body:
                first = body[0]
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    docstrings.add(id(first.value))

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and node.value == OLD_CONSTANT
                and id(node) not in docstrings
            ):
                offenders.append(f"{path.relative_to(repo_root)}:{node.lineno}")

    assert offenders == [], f"the old shared constant is still live code: {offenders}"
