"""Stage-1 understanding/action metrics and the planner rollout gate.

`spec:873-875` requires the understanding/action layer to report intent
precision/recall, a durable-action false-positive rate, and clarification
correctness. `plan v0.7:482-493` adds context-mode evaluation and the
false-`NONE` rate, and makes the latter a hard gate.

Three properties this module exists to keep:

1. **Correctness is exact.** A reading that proposes the *wrong* durable action
   is a mistake, not a success, so `expected EXPLICIT_REMEMBER, observed
   EXPLICIT_FORGET` counts as neither a true positive nor a correct reading.
2. **Evidence must be approved and sufficient.** A perfect handful of examples
   invented at the call site cannot conclude the gate: the set has to be
   declared approved, meet a sufficiency floor, and the evaluated examples have
   to match the declaration.
3. **Missing evidence is `INCONCLUSIVE`, never `PASS`** (`spec:915`). A rate that
   cannot be computed is `None` with a stated reason, not `0.0`, because an
   absent number silently read as zero is how a rollout gate gets satisfied by
   having no data.

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

#: The minimum number of approved grounding-required fixtures before the Stage-1
#: gate may conclude. Zero false-`NONE` out of a handful of examples is not
#: evidence of anything, and `plan v0.7:489-493` requires a *conclusive* set
#: before enforcement. This floor is a policy value recorded in one place; an
#: owner-approved dataset specification should replace it.
MIN_APPROVED_GROUNDING_FIXTURES = 20


class GateState(str, Enum):
    """Whether a fixture set can support a rollout decision at all."""

    CONCLUSIVE = "conclusive"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ApprovedFixtureSet:
    """The approved Stage-1 dataset: its identity and its required size.

    Declaring the set is how a caller asserts the evidence is approved. The
    metrics then verify the evaluated examples actually match that declaration,
    so a partial run or a substitute set cannot be presented as the approved one.
    """

    fixture_set_id: str
    grounding_required_count: int


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
    interaction_mode_accuracy: float | None
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
    approved: ApprovedFixtureSet | None = None,
) -> StageOneMetrics:
    """Compute the Stage-1 metrics, or report why they cannot be computed.

    Returns `INCONCLUSIVE` unless all of these hold: an approved set is declared,
    it meets the sufficiency floor, and the evaluated grounding-required count
    matches the declaration exactly. Only then is a rate meaningful.
    """
    grounding_required = [example for example in examples if example.grounding_required]

    if not examples:
        return _inconclusive("no evaluated fixtures were supplied", 0)
    if approved is None:
        return _inconclusive(
            "no approved fixture set was declared, so these examples are ad-hoc "
            "evidence and cannot conclude the gate",
            len(examples),
        )
    if approved.grounding_required_count < MIN_APPROVED_GROUNDING_FIXTURES:
        return _inconclusive(
            "the declared approved set is below the sufficiency floor of "
            f"{MIN_APPROVED_GROUNDING_FIXTURES} grounding-required fixtures",
            len(examples),
        )
    if len(grounding_required) != approved.grounding_required_count:
        return _inconclusive(
            "the evaluated set does not match the approved fixture set "
            f"({len(grounding_required)} grounding-required fixtures evaluated, "
            f"{approved.grounding_required_count} approved)",
            len(examples),
        )

    # Exact equality, not "both durable": the wrong action is not a success.
    true_positives = sum(
        1
        for example in examples
        if _is_durable(example.expected_interaction_mode)
        and example.observed_interaction_mode is example.expected_interaction_mode
    )
    predicted_durable = sum(
        1 for example in examples if _is_durable(example.observed_interaction_mode)
    )
    expected_durable = sum(
        1 for example in examples if _is_durable(example.expected_interaction_mode)
    )
    exact_matches = sum(
        1
        for example in examples
        if example.observed_interaction_mode is example.expected_interaction_mode
    )
    clarification_correct = sum(
        1
        for example in examples
        if example.expected_needs_clarification == example.observed_needs_clarification
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
        reason=(
            f"the evaluated set matches approved fixture set "
            f"'{approved.fixture_set_id}' and meets the sufficiency floor"
        ),
        evaluated=len(examples),
        interaction_mode_accuracy=exact_matches / len(examples),
        intent_precision=(
            true_positives / predicted_durable if predicted_durable else None
        ),
        intent_recall=true_positives / expected_durable if expected_durable else None,
        durable_action_false_positive_rate=(
            (predicted_durable - true_positives) / predicted_durable
            if predicted_durable
            else None
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
        interaction_mode_accuracy=None,
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
    return metrics.state is GateState.CONCLUSIVE and metrics.false_none_rate == 0.0
