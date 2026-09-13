"""Stage-1 understanding/action metrics and the planner rollout gate.

`spec:873-875` requires the understanding/action layer to report intent
precision/recall, a durable-action false-positive rate, and clarification
correctness. `plan v0.7:482-493` adds context-mode evaluation and the
false-`NONE` rate, and makes the latter a hard gate.

Four properties this module exists to keep:

1. **Correctness is exact.** A reading that proposes the *wrong* durable action
   is a mistake, not a success, so `expected EXPLICIT_REMEMBER, observed
   EXPLICIT_FORGET` counts as neither a true positive nor a correct reading.
2. **The approved set is a governance artifact, not a caller argument.** The gate
   is bound to a **manifest file**: its content is hashed, its fixture IDs must
   match the evaluated examples exactly, and its `grounding_required_fixture_ids`
   — not a per-example flag — defines the false-`NONE` denominator. An earlier
   version accepted an object the caller built, so declaring a set was treated as
   being the set; twenty ad-hoc examples with an invented ID concluded the gate.
3. **Evidence must be sufficient.** A set below `MIN_APPROVED_GROUNDING_FIXTURES`
   cannot conclude.
4. **Missing evidence is `INCONCLUSIVE`, never `PASS`** (`spec:915`). A rate that
   cannot be computed is `None` with a stated reason, not `0.0`.

Reading the manifest file is deliberate I/O: it is the only way to make the
approved set something the caller cannot fabricate in-process.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

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
class ApprovedFixtureManifest:
    """An approved Stage-1 dataset, as read from its manifest file.

    Produced by `load_approved_manifest`; `compute_stage1_metrics` re-reads the
    file and requires this value to match, so a hand-built manifest with invented
    IDs cannot stand in for an approved one.
    """

    fixture_set_id: str
    fixture_ids: frozenset[str]
    grounding_required_fixture_ids: frozenset[str]
    digest: str
    path: str


@dataclass(frozen=True)
class StageOneExample:
    """One evaluated turn: what was expected, and what Stage 1 produced.

    `fixture_id` binds the example to the approved manifest. Whether the fixture
    requires grounding is **not** carried here — it comes from the manifest, so a
    caller cannot shrink the false-`NONE` denominator.
    """

    fixture_id: str
    expected_interaction_mode: InteractionMode
    observed_interaction_mode: InteractionMode
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
    evaluated_grounding_required: int
    interaction_mode_accuracy: float | None
    intent_precision: float | None
    intent_recall: float | None
    durable_action_false_positive_rate: float | None
    clarification_correctness: float | None
    context_mode_accuracy: float | None
    false_none_rate: float | None


def _digest_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_approved_manifest(path: Path) -> ApprovedFixtureManifest | None:
    """Read an approved manifest, or return `None` when there is not one.

    A missing file is not an error — it is the honest state of a repository that
    has not adopted an approved dataset yet, and the caller turns it into
    `INCONCLUSIVE`.
    """
    path = Path(path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fixture_ids = frozenset(payload["fixture_ids"])
        grounding_ids = frozenset(payload["grounding_required_fixture_ids"])
        fixture_set_id = str(payload["fixture_set_id"])
    except (KeyError, TypeError, ValueError):
        return None
    return ApprovedFixtureManifest(
        fixture_set_id=fixture_set_id,
        fixture_ids=fixture_ids,
        grounding_required_fixture_ids=grounding_ids,
        digest=_digest_of(path),
        path=str(path),
    )


def _is_durable(mode: InteractionMode) -> bool:
    return mode in DURABLE_ACTION_MODES


def compute_stage1_metrics(
    examples: list[StageOneExample],
    manifest: ApprovedFixtureManifest | None = None,
) -> StageOneMetrics:
    """Compute the Stage-1 metrics, or report why they cannot be computed.

    Returns `INCONCLUSIVE` unless all of these hold: an approved manifest exists
    and still matches its file, the evaluated fixture IDs are exactly the
    approved ones, and the set meets the sufficiency floor. Only then is a rate
    meaningful.
    """
    if not examples:
        return _inconclusive("no evaluated fixtures were supplied", 0, 0)
    if manifest is None:
        return _inconclusive(
            "no approved fixture manifest was supplied, so these examples are "
            "ad-hoc evidence and cannot conclude the gate",
            len(examples),
            0,
        )

    # Re-derive from the file. A manifest object the caller built — with invented
    # IDs, or a borrowed digest — will not match what the file actually says.
    verified = load_approved_manifest(Path(manifest.path))
    if verified is None or verified != manifest:
        return _inconclusive(
            "the approved fixture manifest could not be verified against its file",
            len(examples),
            0,
        )

    evaluated_ids = frozenset(example.fixture_id for example in examples)
    if evaluated_ids != verified.fixture_ids:
        return _inconclusive(
            "the evaluated set does not match the approved manifest "
            f"({len(evaluated_ids)} fixtures evaluated, "
            f"{len(verified.fixture_ids)} approved)",
            len(examples),
            0,
        )

    grounding_required = verified.grounding_required_fixture_ids
    if len(grounding_required) < MIN_APPROVED_GROUNDING_FIXTURES:
        return _inconclusive(
            "the approved manifest is below the sufficiency floor of "
            f"{MIN_APPROVED_GROUNDING_FIXTURES} grounding-required fixtures",
            len(examples),
            len(grounding_required),
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
        == (example.fixture_id in grounding_required)
    )
    false_none = sum(
        1
        for example in examples
        if example.fixture_id in grounding_required
        and example.proposed_context_mode is ContextMode.NONE
    )

    return StageOneMetrics(
        state=GateState.CONCLUSIVE,
        reason=(
            f"the evaluated set matches approved manifest "
            f"'{verified.fixture_set_id}' and meets the sufficiency floor"
        ),
        evaluated=len(examples),
        evaluated_grounding_required=len(grounding_required),
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


def _inconclusive(
    reason: str, evaluated: int, evaluated_grounding_required: int
) -> StageOneMetrics:
    return StageOneMetrics(
        state=GateState.INCONCLUSIVE,
        reason=reason,
        evaluated=evaluated,
        evaluated_grounding_required=evaluated_grounding_required,
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
