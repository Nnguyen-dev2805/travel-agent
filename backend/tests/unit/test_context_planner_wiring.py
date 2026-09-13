"""Task 4 review fix 7: the rollout flag must actually reach the planner.

`CONTEXT_PLANNER_ENFORCEMENT_ENABLED` was declared but read by no production
code: the orchestrator may not import `backend.app`, so the planner arrives by
injection, and the composition root passed none. The flag was therefore inert —
an "explicit rollout gate" that nothing consulted.

This file pins the contract in both directions:

- the composition root derives the planner from the setting, so the flag is the
  real switch; and
- the default remains `False`, so nothing about authoritative planner execution
  is enabled by this change.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.runtime_container import RuntimeContainer
from backend.orchestration.context_planner import ContextPlanner
from backend.orchestration.turn_models import (
    ContextMode,
    InteractionMode,
    TurnUnderstandingResult,
    UnderstandingReason,
)


def _settings(enforcement: bool):
    return SimpleNamespace(
        CONTEXT_PLANNER_ENFORCEMENT_ENABLED=enforcement,
        MEMORY_SHADOW_EXTRACT_ENABLED=False,
    )


def _ambiguous_reading() -> TurnUnderstandingResult:
    return TurnUnderstandingResult(
        interaction_mode=InteractionMode.AMBIGUOUS,
        needs_clarification=True,
        reason_codes=(UnderstandingReason.AMBIGUOUS_SPEECH_ACT,),
    )


def test_the_composition_root_derives_the_planner_from_the_setting():
    """The flag is the switch; a container built from it must honour both values."""
    disabled = RuntimeContainer(settings=_settings(False), rag_service=object())
    enabled = RuntimeContainer(settings=_settings(True), rag_service=object())

    assert (
        disabled.conversation_orchestrator(rag_service=object()).context_planner
        .enforcement_enabled
        is False
    )
    assert (
        enabled.conversation_orchestrator(rag_service=object()).context_planner
        .enforcement_enabled
        is True
    )


def test_the_default_setting_leaves_planner_execution_unauthoritative():
    """Fix 7 clarifies the contract; it does not enable authoritative execution.

    With the default in place, a `NONE` proposal is still not adopted, so the
    effective source plan remains the RAG-only baseline.
    """
    container = RuntimeContainer(settings=_settings(False), rag_service=object())
    orchestrator = container.conversation_orchestrator(rag_service=object())

    plan = orchestrator.context_planner.plan(_ambiguous_reading())

    assert plan.proposed is ContextMode.NONE
    assert plan.effective is ContextMode.RAG_ONLY
    assert plan.is_shadow is True


def test_the_planner_exposes_its_gate_state():
    """The contract has to be inspectable, or wiring it cannot be verified."""
    assert ContextPlanner().enforcement_enabled is False
    assert ContextPlanner(enforcement_enabled=True).enforcement_enabled is True


@pytest.mark.parametrize("enforcement", [False, True])
def test_an_orchestrator_built_without_a_planner_stays_shadow(enforcement):
    """A caller that does not inject one gets the safe default, not enforcement."""
    from backend.orchestration.conversation_orchestrator import ConversationOrchestrator

    orchestrator = ConversationOrchestrator(
        rag_service=object(), conversation_service_provider=lambda: object()
    )

    assert orchestrator.context_planner.enforcement_enabled is False
