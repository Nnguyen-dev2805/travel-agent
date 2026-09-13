"""Task 4 review fix 2: the Stage-1 gate must be evidence-based and exact.

Three defects this file pins:

1. **Exact interaction-mode correctness was not measured.** A reading that
   proposed the *wrong* durable action counted as correct, so `expected REMEMBER,
   observed FORGET` scored as a true positive. Correctness is now exact equality.
2. **Ad-hoc fixtures could conclude the gate.** A single example, or a handful
   invented at the call site, made the state `CONCLUSIVE`. A fixture set now has
   to be *declared approved* and *sufficient*, and the evaluated set has to match
   that declaration.
3. **`spec:915`** — missing required evidence is `INCONCLUSIVE`, never `PASS`.

No test here touches a database, a model, HTTP, or the network.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.memory.write_pipeline.evaluation.stage1_metrics import (
    MIN_APPROVED_GROUNDING_FIXTURES,
    ApprovedFixtureSet,
    GateState,
    StageOneExample,
    compute_stage1_metrics,
    planner_enforcement_permitted,
)
from backend.orchestration.turn_models import ContextMode, InteractionMode

APPROVED = ApprovedFixtureSet(
    fixture_set_id="stage1-understanding-v0.1",
    grounding_required_count=MIN_APPROVED_GROUNDING_FIXTURES,
)


def _example(
    *,
    expected: InteractionMode = InteractionMode.NORMAL_QUERY,
    observed: InteractionMode = InteractionMode.NORMAL_QUERY,
    grounding_required: bool = True,
    proposed: ContextMode = ContextMode.RAG_ONLY,
    expected_clarification: bool = False,
    observed_clarification: bool = False,
) -> StageOneExample:
    return StageOneExample(
        expected_interaction_mode=expected,
        observed_interaction_mode=observed,
        grounding_required=grounding_required,
        proposed_context_mode=proposed,
        expected_needs_clarification=expected_clarification,
        observed_needs_clarification=observed_clarification,
    )


def _approved_set(overrides: dict[int, StageOneExample] | None = None):
    """A set that matches `APPROVED` exactly, all normal queries by default."""
    overrides = overrides or {}
    return [
        overrides.get(index, _example())
        for index in range(MIN_APPROVED_GROUNDING_FIXTURES)
    ]


# ---------------------------------------------------------------------------
# Evidence sufficiency
# ---------------------------------------------------------------------------


def test_no_fixtures_is_inconclusive():
    metrics = compute_stage1_metrics([], approved=APPROVED)

    assert metrics.state is GateState.INCONCLUSIVE
    assert metrics.false_none_rate is None
    assert planner_enforcement_permitted(metrics) is False


def test_undeclared_fixtures_are_inconclusive_however_good_they_look():
    """Ad-hoc examples cannot make the gate conclusive by being perfect."""
    metrics = compute_stage1_metrics(_approved_set(), approved=None)

    assert metrics.state is GateState.INCONCLUSIVE
    assert "approved" in metrics.reason
    assert planner_enforcement_permitted(metrics) is False


def test_a_single_fixture_cannot_conclude_the_gate():
    metrics = compute_stage1_metrics(
        [_example()],
        approved=ApprovedFixtureSet(fixture_set_id="ad-hoc", grounding_required_count=1),
    )

    assert metrics.state is GateState.INCONCLUSIVE
    assert planner_enforcement_permitted(metrics) is False


def test_a_declared_set_below_the_sufficiency_floor_is_inconclusive():
    metrics = compute_stage1_metrics(
        [_example() for _ in range(3)],
        approved=ApprovedFixtureSet(fixture_set_id="tiny", grounding_required_count=3),
    )

    assert metrics.state is GateState.INCONCLUSIVE
    assert "sufficien" in metrics.reason or "floor" in metrics.reason


def test_an_evaluated_set_that_does_not_match_the_approved_set_is_inconclusive():
    """Partial or substituted evidence is not the approved evidence."""
    metrics = compute_stage1_metrics(
        [_example() for _ in range(MIN_APPROVED_GROUNDING_FIXTURES - 1)],
        approved=APPROVED,
    )

    assert metrics.state is GateState.INCONCLUSIVE
    assert planner_enforcement_permitted(metrics) is False


def test_a_matching_sufficient_approved_set_concludes():
    metrics = compute_stage1_metrics(_approved_set(), approved=APPROVED)

    assert metrics.state is GateState.CONCLUSIVE
    assert metrics.false_none_rate == 0.0
    assert metrics.interaction_mode_accuracy == 1.0
    assert planner_enforcement_permitted(metrics) is True


# ---------------------------------------------------------------------------
# Exact interaction-mode correctness
# ---------------------------------------------------------------------------


def test_the_wrong_durable_action_is_not_a_true_positive():
    """`expected REMEMBER, observed FORGET` is a mistake, not a success."""
    examples = _approved_set(
        {
            0: _example(
                expected=InteractionMode.EXPLICIT_REMEMBER,
                observed=InteractionMode.EXPLICIT_FORGET,
            ),
            1: _example(
                expected=InteractionMode.EXPLICIT_REMEMBER,
                observed=InteractionMode.EXPLICIT_REMEMBER,
            ),
        }
    )

    metrics = compute_stage1_metrics(examples, approved=APPROVED)

    # One exact match out of two durable expectations.
    assert metrics.intent_recall == pytest.approx(0.5)
    # Both were proposed as durable; only one was the right one.
    assert metrics.intent_precision == pytest.approx(0.5)
    assert metrics.durable_action_false_positive_rate == pytest.approx(0.5)
    assert metrics.interaction_mode_accuracy < 1.0


def test_interaction_mode_accuracy_counts_exact_matches_only():
    examples = _approved_set(
        {
            0: _example(observed=InteractionMode.EXPLICIT_REMEMBER),
            1: _example(observed=InteractionMode.AMBIGUOUS),
        }
    )

    metrics = compute_stage1_metrics(examples, approved=APPROVED)

    expected = (MIN_APPROVED_GROUNDING_FIXTURES - 2) / MIN_APPROVED_GROUNDING_FIXTURES
    assert metrics.interaction_mode_accuracy == pytest.approx(expected)


def test_rates_are_none_when_their_denominator_is_empty():
    """A number over nothing is an invention; `None` says so."""
    metrics = compute_stage1_metrics(_approved_set(), approved=APPROVED)

    assert metrics.intent_precision is None
    assert metrics.intent_recall is None
    assert metrics.durable_action_false_positive_rate is None


# ---------------------------------------------------------------------------
# The false-NONE gate
# ---------------------------------------------------------------------------


def test_a_grounding_required_query_proposed_none_is_a_false_none():
    examples = _approved_set({0: _example(proposed=ContextMode.NONE)})

    metrics = compute_stage1_metrics(examples, approved=APPROVED)

    assert metrics.false_none_rate == pytest.approx(
        1 / MIN_APPROVED_GROUNDING_FIXTURES
    )
    assert planner_enforcement_permitted(metrics) is False


def test_a_clarification_turn_proposed_none_is_not_a_false_none():
    """A turn that only asks does not answer, so it needs no grounding.

    The set carries the approved 20 grounding-required fixtures plus one
    clarification turn, which is outside the false-`NONE` denominator.
    """
    examples = _approved_set() + [
        _example(
            expected=InteractionMode.AMBIGUOUS,
            observed=InteractionMode.AMBIGUOUS,
            grounding_required=False,
            proposed=ContextMode.NONE,
            expected_clarification=True,
            observed_clarification=True,
        )
    ]

    metrics = compute_stage1_metrics(examples, approved=APPROVED)

    assert metrics.state is GateState.CONCLUSIVE
    assert metrics.false_none_rate == 0.0
    assert planner_enforcement_permitted(metrics) is True


def test_enforcement_is_denied_while_the_gate_is_inconclusive():
    assert planner_enforcement_permitted(
        compute_stage1_metrics([], approved=APPROVED)
    ) is False
    assert planner_enforcement_permitted(
        compute_stage1_metrics(_approved_set(), approved=None)
    ) is False


def test_the_metrics_are_frozen():
    metrics = compute_stage1_metrics(_approved_set(), approved=APPROVED)

    with pytest.raises(dataclasses.FrozenInstanceError):
        metrics.state = GateState.INCONCLUSIVE  # type: ignore[misc]
