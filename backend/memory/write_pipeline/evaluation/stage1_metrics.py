"""Stage-1 understanding/action metrics and the planner rollout gate.

`spec:873-875` requires the understanding/action layer to report intent
precision/recall, a durable-action false-positive rate, and clarification
correctness. `plan v0.7:482-493` adds context-mode evaluation and the
false-`NONE` rate, and makes the latter a hard gate.

Five properties this module exists to keep:

1. **Correctness is exact.** A reading that proposes the *wrong* durable action
   is a mistake, not a success, so `expected EXPLICIT_REMEMBER, observed
   EXPLICIT_FORGET` counts as neither a true positive nor a correct reading.
2. **The approved set is a repository artifact, not a caller argument.** The
   manifest is read from a fixed governed path, and `compute_stage1_metrics`
   takes no manifest parameter at all, so there is nothing for a caller to
   substitute. An earlier version hashed the file but still accepted a caller's
   path, so `/tmp/totally-unapproved.json` could conclude the gate.
3. **The manifest carries an approval record.** `approved_by` and `approved_on`
   must be present, so an accidental file at the governed path does not qualify.
4. **Membership is exact and duplicate-free.** The evaluated fixture IDs must
   equal the manifest's, and a repeated ID is refused — comparing sets let 21
   examples with one duplicate satisfy a 20-ID manifest.
5. **Missing evidence is `INCONCLUSIVE`, never `PASS`** (`spec:915`). A rate that
   cannot be computed is `None` with a stated reason, not `0.0`.

Reading the manifest file is deliberate I/O: it is the only way to make the
approved set something a caller cannot fabricate in-process.
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

#: Where an approved Stage-1 dataset must live. Fixed on purpose: a trust root the
#: caller supplies is not a trust root. Changing this path is a repository change
#: a reviewer sees.
APPROVED_MANIFEST_PATH = (
    Path(__file__).resolve().parents[4]
    / "docs"
    / "evaluation"
    / "fixtures"
    / "agent-memory"
    / "stage1-manifest.json"
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
    """An approved Stage-1 dataset, as read from the governed manifest file.

    The approval record is part of the value: a manifest without `approved_by`
    and `approved_on` is not loaded at all.
    """

    fixture_set_id: str
    fixture_ids: frozenset[str]
    grounding_required_fixture_ids: frozenset[str]
    approved_by: str
    approved_on: str
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


def load_approved_manifest() -> ApprovedFixtureManifest | None:
    """Read the manifest at `APPROVED_MANIFEST_PATH`, or return `None`.

    `None` is the honest answer for every way the evidence can be absent or
    unusable: no file, unreadable JSON, missing fields, or no approval record.
    The caller turns that into `INCONCLUSIVE`.
    """
    path = APPROVED_MANIFEST_PATH
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fixture_set_id = str(payload["fixture_set_id"])
        fixture_ids = frozenset(payload["fixture_ids"])
        grounding_ids = frozenset(payload["grounding_required_fixture_ids"])
        approved_by = str(payload["approved_by"]).strip()
        approved_on = str(payload["approved_on"]).strip()
    except (KeyError, TypeError, ValueError):
        return None
    if not approved_by or not approved_on:
        return None
    return ApprovedFixtureManifest(
        fixture_set_id=fixture_set_id,
        fixture_ids=fixture_ids,
        grounding_required_fixture_ids=grounding_ids,
        approved_by=approved_by,
        approved_on=approved_on,
        digest=hashlib.sha256(path.read_bytes()).hexdigest(),
        path=str(path),
    )


def _is_durable(mode: InteractionMode) -> bool:
    return mode in DURABLE_ACTION_MODES


def compute_stage1_metrics(examples: list[StageOneExample]) -> StageOneMetrics:
    """Compute the Stage-1 metrics, or report why they cannot be computed.

    There is no manifest parameter: the approved set is read from the governed
    path, so a caller cannot present a different one.

    Returns `INCONCLUSIVE` unless all of these hold: an approved manifest exists
    with an approval record, the evaluated fixture IDs are exactly the approved
    ones with no duplicates, and the set meets the sufficiency floor.
    """
    if not examples:
        return _inconclusive("no evaluated fixtures were supplied", 0, 0)

    manifest = load_approved_manifest()
    if manifest is None:
        return _inconclusive(
            "no approved fixture manifest is present at "
            f"{APPROVED_MANIFEST_PATH}, so these examples are ad-hoc evidence "
            "and cannot conclude the gate",
            len(examples),
            0,
        )

    evaluated_ids = [example.fixture_id for example in examples]
    if len(set(evaluated_ids)) != len(evaluated_ids):
        return _inconclusive(
            "the evaluated set contains a duplicate fixture id",
            len(examples),
            0,
        )
    if set(evaluated_ids) != manifest.fixture_ids:
        return _inconclusive(
            "the evaluated set does not match the approved manifest "
            f"({len(set(evaluated_ids))} fixtures evaluated, "
            f"{len(manifest.fixture_ids)} approved)",
            len(examples),
            0,
        )

    grounding_required = manifest.grounding_required_fixture_ids
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
            f"'{manifest.fixture_set_id}' and meets the sufficiency floor"
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
