"""Task 4: routing is pure logic and the gate is an authorization boundary.

`ActionRouter` chooses a branch; it executes nothing (`spec:367-373`).
`ExplicitIntentGate` decides whether a durable mutation is even permitted, and it
is deliberately **not** another extractor: a model may help parse a payload, but
classification alone can never authorize durable personal state
(`ADR 0036:34-41`, zero-tolerance failure 3 at `spec:905`).

These tests pin the structural reason that holds: the only reading the gate
accepts is one the closed deterministic rules produced. A reading that merely
*looks* explicit — the shape a model or a payload parser would hand back — is
denied.

No test here touches a database, a model, HTTP, or the network.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.orchestration.action_router import ActionRouter, ExplicitIntentGate
from backend.orchestration.turn_models import (
    DURABLE_ACTION_MODES,
    ExplicitIntentDecision,
    InteractionMode,
    RoutingDecision,
    TurnUnderstandingResult,
    UnderstandingReason,
)

ROUTER = ActionRouter()


def _reading(
    mode: InteractionMode,
    *reasons: UnderstandingReason,
    needs_clarification: bool = False,
) -> TurnUnderstandingResult:
    return TurnUnderstandingResult(
        interaction_mode=mode,
        needs_clarification=needs_clarification,
        reason_codes=tuple(reasons),
    )


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_an_ordinary_query_routes_to_the_normal_branch():
    decision = ROUTER.route(
        _reading(InteractionMode.NORMAL_QUERY, UnderstandingReason.NO_EXPLICIT_SIGNAL)
    )

    assert decision is RoutingDecision.NORMAL_QUERY


def test_an_ambiguous_reading_routes_to_clarification():
    decision = ROUTER.route(
        _reading(
            InteractionMode.AMBIGUOUS,
            UnderstandingReason.AMBIGUOUS_SPEECH_ACT,
            needs_clarification=True,
        )
    )

    assert decision is RoutingDecision.NEEDS_CLARIFICATION


def test_a_negated_command_routes_to_clarification_not_to_an_action():
    decision = ROUTER.route(
        _reading(
            InteractionMode.AMBIGUOUS,
            UnderstandingReason.NEGATED_SPEECH_ACT,
            needs_clarification=True,
        )
    )

    assert decision is RoutingDecision.NEEDS_CLARIFICATION


@pytest.mark.parametrize("mode", sorted(DURABLE_ACTION_MODES, key=lambda m: m.value))
def test_a_corroborated_durable_action_routes_to_the_memory_branch(mode):
    decision = ROUTER.route(
        _reading(mode, UnderstandingReason.DETERMINISTIC_MATCH)
    )

    assert decision is RoutingDecision.EXPLICIT_MEMORY_ACTION


@pytest.mark.parametrize("mode", sorted(DURABLE_ACTION_MODES, key=lambda m: m.value))
def test_a_durable_mode_without_deterministic_corroboration_is_not_routed_to_action(mode):
    """The gate is what authorizes, so an uncorroborated mode must not pass.

    This is the shape a classifier or payload parser produces: the right label,
    none of the deterministic evidence.
    """
    decision = ROUTER.route(
        _reading(mode, UnderstandingReason.PARSER_FAILED_CLOSED)
    )

    assert decision is RoutingDecision.NEEDS_CLARIFICATION


def test_inspect_routes_to_the_memory_branch_and_does_not_need_the_gate():
    """Inspect is read-only, so the durable-mutation gate does not apply.

    `spec:397-401` — it is recognized in Stage 1 and returns a controlled
    capability-unavailable outcome until Stage 3.
    """
    decision = ROUTER.route(
        _reading(
            InteractionMode.EXPLICIT_INSPECT,
            UnderstandingReason.DETERMINISTIC_MATCH,
            UnderstandingReason.INSPECT_CAPABILITY_UNAVAILABLE,
        )
    )

    assert decision is RoutingDecision.EXPLICIT_MEMORY_ACTION


def test_routing_is_deterministic():
    reading = _reading(
        InteractionMode.EXPLICIT_REMEMBER, UnderstandingReason.DETERMINISTIC_MATCH
    )

    assert ROUTER.route(reading) is ROUTER.route(reading)


# ---------------------------------------------------------------------------
# The authorization boundary
# ---------------------------------------------------------------------------


def test_the_gate_authorizes_a_corroborated_speech_act():
    decision = ExplicitIntentGate().authorize(
        _reading(
            InteractionMode.EXPLICIT_REMEMBER, UnderstandingReason.DETERMINISTIC_MATCH
        )
    )

    assert isinstance(decision, ExplicitIntentDecision)
    assert decision.authorized is True
    assert decision.reason_code is UnderstandingReason.DETERMINISTIC_MATCH


@pytest.mark.parametrize("mode", sorted(DURABLE_ACTION_MODES, key=lambda m: m.value))
def test_the_gate_denies_a_durable_mode_that_lacks_deterministic_evidence(mode):
    """Model output alone never authorizes a durable write (`ADR 0036:114-118`).

    The reading carries the durable label but not the deterministic reason, which
    is exactly what a classifier would produce. It must be denied.
    """
    decision = ExplicitIntentGate().authorize(
        _reading(mode, UnderstandingReason.PARSER_FAILED_CLOSED)
    )

    assert decision.authorized is False
    assert decision.reason_code is UnderstandingReason.PARSER_FAILED_CLOSED


def test_the_gate_denies_a_reading_that_asked_for_clarification():
    """Ambiguity cannot be resolved into authorization by the gate."""
    decision = ExplicitIntentGate().authorize(
        _reading(
            InteractionMode.EXPLICIT_REMEMBER,
            UnderstandingReason.DETERMINISTIC_MATCH,
            needs_clarification=True,
        )
    )

    assert decision.authorized is False


def test_the_gate_denies_a_non_durable_mode():
    decision = ExplicitIntentGate().authorize(
        _reading(InteractionMode.NORMAL_QUERY, UnderstandingReason.NO_EXPLICIT_SIGNAL)
    )

    assert decision.authorized is False


def test_a_denial_never_reports_no_signal_for_a_reading_that_had_one():
    """The denial reason must describe why, not default to "nothing was there"."""
    decision = ExplicitIntentGate().authorize(
        _reading(
            InteractionMode.EXPLICIT_REMEMBER,
            UnderstandingReason.DETERMINISTIC_MATCH,
            needs_clarification=True,
        )
    )

    assert decision.authorized is False
    assert decision.reason_code is not UnderstandingReason.NO_EXPLICIT_SIGNAL


def test_a_denial_reports_the_readings_own_cause_when_it_has_one():
    decision = ExplicitIntentGate().authorize(
        _reading(InteractionMode.EXPLICIT_FORGET, UnderstandingReason.NEGATED_SPEECH_ACT)
    )

    assert decision.reason_code is UnderstandingReason.NEGATED_SPEECH_ACT


def test_the_gate_denies_when_no_reason_supports_the_speech_act():
    """An empty reason set is not corroboration — it is the absence of evidence."""
    decision = ExplicitIntentGate().authorize(
        _reading(InteractionMode.EXPLICIT_FORGET)
    )

    assert decision.authorized is False


def test_only_the_deterministic_reason_authorizes():
    """Every other reason code, on a durable mode, must be denied.

    This is the closed-vocabulary version of "the model cannot authorize": no
    non-deterministic reason can ever be read as permission, so a future parser
    cannot accidentally acquire authority by adding a new reason code.
    """
    gate = ExplicitIntentGate()
    denying = [
        reason
        for reason in UnderstandingReason
        if reason is not UnderstandingReason.DETERMINISTIC_MATCH
    ]

    for reason in denying:
        decision = gate.authorize(_reading(InteractionMode.EXPLICIT_REMEMBER, reason))
        assert decision.authorized is False, f"{reason} authorized a durable action"


def test_the_router_and_gate_reach_no_model_provider_or_storage():
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
    path = Path(__file__).resolve().parents[3] / "orchestration" / "action_router.py"
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
