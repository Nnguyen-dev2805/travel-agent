"""Stage-1 understanding/action metrics and the planner rollout gate.

`spec:873-875` requires the understanding/action layer to report intent
precision/recall, a durable-action false-positive rate, and clarification
correctness. `plan v0.7:482-493` adds context-mode evaluation and the
false-`NONE` rate, and makes the latter a hard gate.

Two properties this module exists to keep:

1. **Missing evidence is `INCONCLUSIVE`, never `PASS`** (`spec:915`). A metric
   that cannot be computed is `None` with a stated reason, not `0.0`, because an
   absent number silently read as zero is how a rollout gate gets satisfied by
   having no data.
2. **The gate is a conjunction, not a score.** `planner_enforcement_permitted`
   requires a conclusive state *and* a zero false-`NONE` rate. Nothing else may
   turn enforcement on.

Pure computation: no database, no model, no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.orchestration.turn_models import (
    DURABLE_ACTION_MODES,
    ContextMode,
    InteractionMode,
)


class GateState(str, Enum):
    """Whether a fixture set can support a rollout decision at all."""

    CONCLUSIVE = "conclusive"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class StageOneExample:
    """One evaluated turn: what was expected, and what Stage 1 produced."""

    expected_interaction_mode: InteractionMode
    observed_interaction_mode: InteractionMode
    grounding_required: bool
    proposed_context_mode: ContextMode
    expected_needs_clarification: bool
    observed_needs_clarification: bool


@dataclass(frozen=True)
class StageOneMetrics:
    """The Stage-1 evidence record.

    Every rate is `None` when it could not be computed. `reason` always says why
    the state is what it is, so a reader never has to infer it from a number.
    """

    state: GateState
    reason: str
    evaluated: int
    intent_precision: float | None
    intent_recall: float | None
    durable_action_false_positive_rate: float | None
    clarification_correctness: float | None
    context_mode_accuracy: float | None
    false_none_rate: float | None


def _is_durable(mode: InteractionMode) -> bool:
    return mode in DURABLE_ACTION_MODES


def compute_stage1_metrics(
    examples: list[StageOneExample],
) -> StageOneMetrics:
    """Compute the Stage-1 metrics, or report why they cannot be computed.

    The false-`NONE` denominator is the approved grounding-required fixtures. An
    empty denominator makes the gate inconclusive rather than perfect: zero
    false-`NONE` out of zero fixtures is not evidence that nothing was missed.
    """
    grounding_required = [example for example in examples if example.grounding_required]

    if not examples:
        return _inconclusive("no evaluated fixtures were supplied", 0)
    if not grounding_required:
        return _inconclusive(
            "no approved grounding-required fixture is present, so the "
            "false-NONE rate has no denominator",
            len(examples),
        )

    true_positives = sum(
        1
        for example in examples
        if _is_durable(example.expected_interaction_mode)
        and _is_durable(example.observed_interaction_mode)
    )
    false_positives = sum(
        1
        for example in examples
        if not _is_durable(example.expected_interaction_mode)
        and _is_durable(example.observed_interaction_mode)
    )
    false_negatives = sum(
        1
        for example in examples
        if _is_durable(example.expected_interaction_mode)
        and not _is_durable(example.observed_interaction_mode)
    )
    predicted_durable = true_positives + false_positives

    clarification_correct = sum(
        1
        for example in examples
        if example.expected_needs_clarification
        == example.observed_needs_clarification
    )
    context_mode_correct = sum(
        1
        for example in examples
        if (example.proposed_context_mode is ContextMode.RAG_ONLY)
        == example.grounding_required
    )
    false_none = sum(
        1
        for example in grounding_required
        if example.proposed_context_mode is ContextMode.NONE
    )

    return StageOneMetrics(
        state=GateState.CONCLUSIVE,
        reason="a conclusive fixture set with a non-empty grounding denominator",
        evaluated=len(examples),
        intent_precision=(
            true_positives / predicted_durable if predicted_durable else None
        ),
        intent_recall=(
            true_positives / (true_positives + false_negatives)
            if (true_positives + false_negatives)
            else None
        ),
        durable_action_false_positive_rate=(
            false_positives / predicted_durable if predicted_durable else None
        ),
        clarification_correctness=clarification_correct / len(examples),
        context_mode_accuracy=context_mode_correct / len(examples),
        false_none_rate=false_none / len(grounding_required),
    )


def _inconclusive(reason: str, evaluated: int) -> StageOneMetrics:
    return StageOneMetrics(
        state=GateState.INCONCLUSIVE,
        reason=reason,
        evaluated=evaluated,
        intent_precision=None,
        intent_recall=None,
        durable_action_false_positive_rate=None,
        clarification_correctness=None,
        context_mode_accuracy=None,
        false_none_rate=None,
    )


def planner_enforcement_permitted(metrics: StageOneMetrics) -> bool:
    """Whether `CONTEXT_PLANNER_ENFORCEMENT_ENABLED` may be turned on.

    Both conditions are required: a conclusive set, and zero false-`NONE` on it.
    An inconclusive set yields `False` — never a default approval — because the
    plan's rule is that enforcement stays off while the gate is inconclusive or
    failing (`plan v0.7:489-493`).
    """
    return (
        metrics.state is GateState.CONCLUSIVE
        and metrics.false_none_rate == 0.0
    )
