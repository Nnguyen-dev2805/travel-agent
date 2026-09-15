"""Task 10 Stage 3: ContextPlanner proposals across the full vocabulary and authoritative execution.

Governed by Plan v0.15, Spec v0.7, and ADR 0039:
- Proposes across NONE, RAG_ONLY, MEMORY_ONLY, BOTH.
- While CONTEXT_PLANNER_ENFORCEMENT_ENABLED is False:
  effective stays RAG_ONLY baseline.
- When CONTEXT_PLANNER_ENFORCEMENT_ENABLED is True (or injected enforcement_enabled=True):
  effective matches proposed across all modes (authoritative execution).
- Pure domain planning: reaches no storage, model provider, or network.
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
    mode: InteractionMode = InteractionMode.NORMAL_QUERY,
    *,
    needs_clarification: bool = False,
    memory_namespaces: tuple[str, ...] = (),
    topics: tuple[str, ...] = (),
) -> TurnUnderstandingResult:
    return TurnUnderstandingResult(
        interaction_mode=mode,
        needs_clarification=needs_clarification,
        memory_namespaces_needed=memory_namespaces,
        topics=topics,
        reason_codes=(UnderstandingReason.NO_EXPLICIT_SIGNAL,),
    )


# ---------------------------------------------------------------------------
# Stage 3 Proposals
# ---------------------------------------------------------------------------


def test_a_grounding_required_query_proposes_rag_only():
    plan = ContextPlanner().plan(_reading(InteractionMode.NORMAL_QUERY))
    assert plan.proposed is ContextMode.RAG_ONLY


def test_a_turn_that_only_asks_for_clarification_proposes_none():
    plan = ContextPlanner().plan(
        _reading(InteractionMode.AMBIGUOUS, needs_clarification=True)
    )
    assert plan.proposed is ContextMode.NONE


def test_memory_only_proposed_when_memory_needed_without_travel_topics():
    plan = ContextPlanner().plan(
        _reading(
            InteractionMode.NORMAL_QUERY,
            memory_namespaces=("travel.preference.hotel_atmosphere",),
            topics=(),
        )
    )
    assert plan.proposed is ContextMode.MEMORY_ONLY


def test_both_proposed_when_memory_and_travel_topics_needed():
    plan = ContextPlanner().plan(
        _reading(
            InteractionMode.NORMAL_QUERY,
            memory_namespaces=("travel.preference.hotel_atmosphere",),
            topics=("hotels", "danang"),
        )
    )
    assert plan.proposed is ContextMode.BOTH


# ---------------------------------------------------------------------------
# Rollout Gate & Enforcement
# ---------------------------------------------------------------------------


def test_a_none_proposal_does_not_skip_rag_while_enforcement_is_off():
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


def test_enforcement_on_makes_all_modes_authoritative():
    planner = ContextPlanner(enforcement_enabled=True)
    assert planner.enforcement_requested is True
    assert planner.enforcement_enabled is True

    # NONE
    plan_none = planner.plan(_reading(needs_clarification=True))
    assert plan_none.proposed is ContextMode.NONE
    assert plan_none.effective is ContextMode.NONE
    assert plan_none.is_shadow is False

    # RAG_ONLY
    plan_rag = planner.plan(_reading(InteractionMode.NORMAL_QUERY))
    assert plan_rag.proposed is ContextMode.RAG_ONLY
    assert plan_rag.effective is ContextMode.RAG_ONLY
    assert plan_rag.is_shadow is False

    # MEMORY_ONLY
    plan_mem = planner.plan(
        _reading(memory_namespaces=("travel.preference.hotel_atmosphere",))
    )
    assert plan_mem.proposed is ContextMode.MEMORY_ONLY
    assert plan_mem.effective is ContextMode.MEMORY_ONLY
    assert plan_mem.is_shadow is False

    # BOTH
    plan_both = planner.plan(
        _reading(
            memory_namespaces=("travel.preference.hotel_atmosphere",),
            topics=("danang",),
        )
    )
    assert plan_both.proposed is ContextMode.BOTH
    assert plan_both.effective is ContextMode.BOTH
    assert plan_both.is_shadow is False


def test_the_default_construction_is_the_safe_one():
    plan = ContextPlanner().plan(
        _reading(InteractionMode.AMBIGUOUS, needs_clarification=True)
    )
    assert plan.effective is ContextMode.RAG_ONLY
    assert plan.is_shadow is True


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
