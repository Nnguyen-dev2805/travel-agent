"""Task 4: Stage-1 understanding/action metrics and the planner rollout gate.

`spec:873-875` requires the understanding/action layer to report intent
precision/recall, a durable-action false-positive rate, and clarification
correctness. `plan v0.7:482-493` adds context-mode evaluation and the
**false-`NONE` rate**, and makes the last one a hard gate: zero false-`NONE` on a
conclusive approved fixture set before planner enforcement may be enabled.

The rule these tests exist to protect is `spec:915`: **missing required evidence
is `INCONCLUSIVE`, never `PASS`**. A metric that cannot be computed must say so,
because an absent number silently read as zero is how a rollout gate gets
satisfied by having no data.

No test here touches a database, a model, HTTP, or the network.
"""

from __future__ import annotations

import pytest

from backend.memory.write_pipeline.evaluation.stage1_metrics import (
    GateState,
    StageOneExample,
    compute_stage1_metrics,
    planner_enforcement_permitted,
)
from backend.orchestration.turn_models import ContextMode, InteractionMode


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


def test_a_perfect_fixture_set_is_conclusive():
    metrics = compute_stage1_metrics(
        [
            _example(),
            _example(
                expected=InteractionMode.EXPLICIT_REMEMBER,
                observed=InteractionMode.EXPLICIT_REMEMBER,
            ),
        ]
    )

    assert metrics.state is GateState.CONCLUSIVE
    assert metrics.false_none_rate == 0.0
    assert metrics.intent_precision == 1.0
    assert metrics.intent_recall == 1.0


def test_precision_is_undefined_when_nothing_was_predicted_positive():
    """`None`, not `0.0` and not `1.0`.

    A set with no durable prediction has no precision: reporting zero would read
    as total failure and reporting one as perfection, and both are inventions.
    """
    metrics = compute_stage1_metrics([_example(), _example()])

    assert metrics.intent_precision is None
    assert metrics.durable_action_false_positive_rate is None
    assert metrics.false_none_rate == 0.0


def test_no_fixtures_is_inconclusive_not_a_pass():
    """The rule that matters: absence of evidence is not evidence of quality."""
    metrics = compute_stage1_metrics([])

    assert metrics.state is GateState.INCONCLUSIVE
    assert metrics.false_none_rate is None
    assert metrics.intent_precision is None


def test_a_set_without_grounding_required_fixtures_is_inconclusive():
    """The false-`NONE` denominator must not be empty for the gate to conclude."""
    metrics = compute_stage1_metrics([_example(grounding_required=False)])

    assert metrics.state is GateState.INCONCLUSIVE
    assert metrics.false_none_rate is None
    assert "grounding" in metrics.reason


def test_a_grounding_required_query_proposed_none_is_a_false_none():
    metrics = compute_stage1_metrics(
        [_example(grounding_required=True, proposed=ContextMode.NONE)]
    )

    assert metrics.state is GateState.CONCLUSIVE
    assert metrics.false_none_rate == 1.0


def test_a_clarification_turn_proposed_none_is_not_a_false_none():
    """A turn that only asks does not answer, so it needs no grounding."""
    metrics = compute_stage1_metrics(
        [
            _example(),
            _example(
                expected=InteractionMode.AMBIGUOUS,
                observed=InteractionMode.AMBIGUOUS,
                grounding_required=False,
                proposed=ContextMode.NONE,
                expected_clarification=True,
                observed_clarification=True,
            ),
        ]
    )

    assert metrics.false_none_rate == 0.0


def test_intent_precision_and_recall_are_computed_from_the_confusion():
    metrics = compute_stage1_metrics(
        [
            # one true positive
            _example(
                expected=InteractionMode.EXPLICIT_REMEMBER,
                observed=InteractionMode.EXPLICIT_REMEMBER,
            ),
            # one false positive: predicted an action that was not there
            _example(
                expected=InteractionMode.NORMAL_QUERY,
                observed=InteractionMode.EXPLICIT_FORGET,
            ),
            # one false negative: missed an action
            _example(
                expected=InteractionMode.EXPLICIT_FORGET,
                observed=InteractionMode.NORMAL_QUERY,
            ),
        ]
    )

    assert metrics.intent_precision == pytest.approx(0.5)
    assert metrics.intent_recall == pytest.approx(0.5)


def test_the_durable_action_false_positive_rate_counts_only_durable_modes():
    metrics = compute_stage1_metrics(
        [
            _example(),
            _example(
                expected=InteractionMode.NORMAL_QUERY,
                observed=InteractionMode.EXPLICIT_REMEMBER,
            ),
        ]
    )

    assert metrics.durable_action_false_positive_rate == pytest.approx(1.0)


def test_clarification_correctness_tracks_the_flag():
    metrics = compute_stage1_metrics(
        [
            _example(expected_clarification=True, observed_clarification=True),
            _example(expected_clarification=False, observed_clarification=False),
            _example(expected_clarification=True, observed_clarification=False),
        ]
    )

    assert metrics.clarification_correctness == pytest.approx(2 / 3)


def test_context_mode_accuracy_tracks_the_proposal():
    metrics = compute_stage1_metrics(
        [
            _example(grounding_required=True, proposed=ContextMode.RAG_ONLY),
            _example(grounding_required=True, proposed=ContextMode.NONE),
        ]
    )

    assert metrics.context_mode_accuracy == pytest.approx(0.5)


def test_enforcement_is_denied_while_the_gate_is_inconclusive():
    metrics = compute_stage1_metrics([])

    assert planner_enforcement_permitted(metrics) is False


def test_enforcement_is_denied_while_any_false_none_exists():
    metrics = compute_stage1_metrics(
        [_example(grounding_required=True, proposed=ContextMode.NONE)]
    )

    assert metrics.false_none_rate == 1.0
    assert planner_enforcement_permitted(metrics) is False


def test_enforcement_is_permitted_only_on_a_conclusive_zero_false_none_set():
    metrics = compute_stage1_metrics([_example(), _example()])

    assert planner_enforcement_permitted(metrics) is True


def test_the_metrics_are_frozen():
    import dataclasses

    metrics = compute_stage1_metrics([_example()])

    with pytest.raises(dataclasses.FrozenInstanceError):
        metrics.state = GateState.INCONCLUSIVE  # type: ignore[misc]
