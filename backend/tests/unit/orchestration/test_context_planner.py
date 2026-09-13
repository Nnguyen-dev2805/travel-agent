"""Task 4: the context planner proposes, and Stage 1 does not act on the proposal.

The Stage-1 rollout contract (`plan v0.7:444-450`) is the whole point of this
file:

```text
planner proposes NONE  !=  production skips RAG
```

The planner exposes the complete approved vocabulary — `NONE`, `RAG_ONLY`,
`MEMORY_ONLY`, `BOTH` — but only `NONE` and `RAG_ONLY` are reachable until
governed Memory Read exists (`ADR 0039:54-66`). While
`CONTEXT_PLANNER_ENFORCEMENT_ENABLED` is false the effective normal-query source
plan stays the existing `RAG_ONLY` baseline, so a `NONE` proposal is recorded as
shadow evidence and changes nothing about answer grounding.

No test here touches a database, a model, HTTP, or the network.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.orchestration.context_planner import ContextPlanner
from backend.orchestration.turn_models import (
    ContextMode,
    ContextPlan,
    InteractionMode,
    TurnUnderstandingResult,
    UnderstandingReason,
)

ROOT_DIR = Path(__file__).resolve().parents[4]

ALL_INTERACTION_MODES = list(InteractionMode)


def _reading(
    mode: InteractionMode, *, needs_clarification: bool = False
) -> TurnUnderstandingResult:
    return TurnUnderstandingResult(
        interaction_mode=mode,
        needs_clarification=needs_clarification,
        reason_codes=(UnderstandingReason.NO_EXPLICIT_SIGNAL,),
    )


# ---------------------------------------------------------------------------
# The proposal
# ---------------------------------------------------------------------------


def test_a_grounding_required_query_proposes_rag_only():
    plan = ContextPlanner().plan(_reading(InteractionMode.NORMAL_QUERY))

    assert plan.proposed is ContextMode.RAG_ONLY


def test_a_turn_that_only_asks_for_clarification_proposes_none():
    """A clarification turn does not answer, so it needs no grounding."""
    plan = ContextPlanner().plan(
        _reading(InteractionMode.AMBIGUOUS, needs_clarification=True)
    )

    assert plan.proposed is ContextMode.NONE


@pytest.mark.parametrize("mode", ALL_INTERACTION_MODES)
def test_stage_one_never_proposes_a_memory_source_mode(mode):
    """`MEMORY_ONLY` and `BOTH` exist in the vocabulary but are unreachable.

    Reachability is a Stage-1 property, not a vocabulary one: the values are
    approved and present, and proposing one would claim a Memory Read path that
    does not exist.
    """
    plan = ContextPlanner().plan(_reading(mode))

    assert plan.proposed in {ContextMode.NONE, ContextMode.RAG_ONLY}


# ---------------------------------------------------------------------------
# The rollout invariant
# ---------------------------------------------------------------------------


def test_a_none_proposal_does_not_skip_rag_while_enforcement_is_off():
    """The load-bearing assertion of the whole Stage-1 rollout.

    A planner that could make production skip retrieval would produce ungrounded
    answers on the authority of a component that has not passed its gate.
    """
    plan = ContextPlanner(enforcement_enabled=False).plan(
        _reading(InteractionMode.AMBIGUOUS, needs_clarification=True)
    )

    assert plan.proposed is ContextMode.NONE
    assert plan.effective is ContextMode.RAG_ONLY
    assert plan.is_shadow is True


def test_enforcement_off_keeps_the_baseline_for_every_reading():
    planner = ContextPlanner(enforcement_enabled=False)

    for mode in ALL_INTERACTION_MODES:
        plan = planner.plan(_reading(mode, needs_clarification=True))
        assert plan.effective is ContextMode.RAG_ONLY, mode


def test_enforcement_cannot_claim_a_mode_stage_one_does_not_execute():
    """A plan must not report as effective something production never runs.

    The orchestrator always calls the RAG baseline, so a plan claiming
    `effective = NONE` would describe execution that does not happen. Requesting
    enforcement is recorded, but it cannot make the contract untrue.
    """
    plan = ContextPlanner(enforcement_enabled=True).plan(
        _reading(InteractionMode.AMBIGUOUS, needs_clarification=True)
    )

    assert plan.proposed is ContextMode.NONE
    assert plan.effective is ContextMode.RAG_ONLY
    assert plan.is_shadow is True


def test_enforcement_is_requested_but_not_active_in_stage_one():
    """The flag is observable without being mistaken for an active behaviour.

    Enforcement needs an executor that runs the effective plan; Stage 1 has none
    (Task 10 owns authoritative execution), so `enforcement_enabled` reports what
    is actually true.
    """
    planner = ContextPlanner(enforcement_enabled=True)

    assert planner.enforcement_requested is True
    assert planner.enforcement_enabled is False


@pytest.mark.parametrize("enforcement", [False, True])
@pytest.mark.parametrize("mode", ALL_INTERACTION_MODES)
def test_the_effective_mode_always_matches_what_executes(enforcement, mode):
    """Whatever is requested, `effective` describes the RAG baseline that runs."""
    plan = ContextPlanner(enforcement_enabled=enforcement).plan(
        _reading(mode, needs_clarification=True)
    )

    assert plan.effective is ContextMode.RAG_ONLY


def test_a_rag_only_proposal_is_not_shadow_under_either_setting():
    for enforcement in (False, True):
        plan = ContextPlanner(enforcement_enabled=enforcement).plan(
            _reading(InteractionMode.NORMAL_QUERY)
        )
        assert plan.effective is ContextMode.RAG_ONLY
        assert plan.is_shadow is False


def test_the_default_construction_is_the_safe_one():
    """A caller that forgets the flag must get the shadow behaviour, not enforcement."""
    plan = ContextPlanner().plan(
        _reading(InteractionMode.AMBIGUOUS, needs_clarification=True)
    )

    assert plan.effective is ContextMode.RAG_ONLY


def test_planning_is_deterministic():
    planner = ContextPlanner()
    reading = _reading(InteractionMode.NORMAL_QUERY)

    assert planner.plan(reading) == planner.plan(reading)


def test_the_plan_is_the_closed_contract():
    plan = ContextPlanner().plan(_reading(InteractionMode.NORMAL_QUERY))

    assert isinstance(plan, ContextPlan)


# ---------------------------------------------------------------------------
# The rollout gate itself
# ---------------------------------------------------------------------------


def test_the_enforcement_flag_defaults_to_false_in_a_spawned_interpreter():
    """`Settings` reads `os.getenv` at import, so only a fresh process proves it.

    An in-process monkeypatch would prove nothing about what a deployment gets
    when the variable is unset.
    """
    code = (
        "import json;"
        "from backend.app.config import settings;"
        "print(json.dumps("
        "settings.CONTEXT_PLANNER_ENFORCEMENT_ENABLED))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=ROOT_DIR,
        check=True,
    )

    assert json.loads(result.stdout) is False


def test_the_enforcement_flag_is_readable_from_the_environment():
    """The gate has to be switchable, or it is a constant pretending to be a gate."""
    code = (
        "import json;"
        "from backend.app.config import settings;"
        "print(json.dumps("
        "settings.CONTEXT_PLANNER_ENFORCEMENT_ENABLED))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=ROOT_DIR,
        check=True,
        env={"CONTEXT_PLANNER_ENFORCEMENT_ENABLED": "true", "PATH": "/usr/bin:/bin"},
    )

    assert json.loads(result.stdout) is True


def test_the_planner_reaches_no_model_provider_or_storage():
    forbidden = (
        "fastapi",
        "sqlalchemy",
        "backend.memory",
        "backend.rag",
        "backend.observability",
        "backend.storage",
        "openai",
        "requests",
        "httpx",
    )
    path = Path(__file__).resolve().parents[3] / "orchestration" / "context_planner.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not [
        module
        for module in imported
        for banned in forbidden
        if module == banned or module.startswith(f"{banned}.")
    ], imported
