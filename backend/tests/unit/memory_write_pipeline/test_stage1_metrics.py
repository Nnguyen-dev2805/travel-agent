"""Task 4 re-review fix 2: the gate must bind to an approved manifest.

The previous version accepted an `ApprovedFixtureSet` object the caller built, so
anyone could write:

```python
compute_stage1_metrics(twenty_ad_hoc_examples,
    approved=ApprovedFixtureSet("totally-unapproved-ad-hoc-id", 20))
```

and get `CONCLUSIVE → false_none_rate=0.0 → planner_enforcement_permitted=True`
while no approved dataset existed. Declaring the set was treated as being the set.

The gate now requires a **manifest file**: a governance artifact whose content is
hashed, whose fixture IDs must match the evaluated examples exactly, and whose
`grounding_required_fixture_ids` — not the caller's per-example flag — defines the
false-`NONE` denominator. A fabricated manifest fails the digest check; a
substituted or partial set fails the membership check.

`spec:915` still governs: missing required evidence is `INCONCLUSIVE`, never
`PASS`.

No test here touches a database, a model, HTTP, or the network.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from backend.memory.write_pipeline.evaluation.stage1_metrics import (
    MIN_APPROVED_GROUNDING_FIXTURES,
    ApprovedFixtureManifest,
    GateState,
    StageOneExample,
    compute_stage1_metrics,
    load_approved_manifest,
    planner_enforcement_permitted,
)
from backend.orchestration.turn_models import ContextMode, InteractionMode

TOTAL = MIN_APPROVED_GROUNDING_FIXTURES + 2
GROUNDING_IDS = [f"fixture-{index:03d}" for index in range(MIN_APPROVED_GROUNDING_FIXTURES)]
OTHER_IDS = [f"fixture-{index:03d}" for index in range(MIN_APPROVED_GROUNDING_FIXTURES, TOTAL)]


def _manifest_file(tmp_path, fixture_ids=None, grounding_ids=None):
    """Write a real manifest file and load it, as a caller must."""
    payload = {
        "fixture_set_id": "stage1-understanding-v0.1",
        "fixture_ids": fixture_ids if fixture_ids is not None else GROUNDING_IDS + OTHER_IDS,
        "grounding_required_fixture_ids": (
            grounding_ids if grounding_ids is not None else GROUNDING_IDS
        ),
    }
    path = tmp_path / "stage1-manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_approved_manifest(path)


def _example(fixture_id: str, **overrides) -> StageOneExample:
    fields = {
        "fixture_id": fixture_id,
        "expected_interaction_mode": InteractionMode.NORMAL_QUERY,
        "observed_interaction_mode": InteractionMode.NORMAL_QUERY,
        "proposed_context_mode": ContextMode.RAG_ONLY,
        "expected_needs_clarification": False,
        "observed_needs_clarification": False,
    }
    fields.update(overrides)
    return StageOneExample(**fields)


def _approved_examples(**overrides) -> list[StageOneExample]:
    """One example per approved fixture, all correct by default."""
    by_id = overrides
    return [
        _example(fixture_id, **by_id.get(fixture_id, {}))
        for fixture_id in GROUNDING_IDS + OTHER_IDS
    ]


# ---------------------------------------------------------------------------
# The fake-approved-set defect
# ---------------------------------------------------------------------------


def test_a_fabricated_manifest_fails_the_digest_check(tmp_path):
    """Declaring an approved set is not the same as having one.

    A hand-built manifest whose file does not contain those IDs must not be
    accepted; otherwise the gate is satisfied by a string the caller invented.
    """
    genuine = _manifest_file(tmp_path)
    fabricated = ApprovedFixtureManifest(
        fixture_set_id="totally-unapproved-ad-hoc-id",
        fixture_ids=frozenset(GROUNDING_IDS + OTHER_IDS),
        grounding_required_fixture_ids=frozenset(GROUNDING_IDS),
        digest=genuine.digest,
        path=genuine.path,
    )

    metrics = compute_stage1_metrics(_approved_examples(), manifest=fabricated)

    assert metrics.state is GateState.INCONCLUSIVE
    assert planner_enforcement_permitted(metrics) is False


def test_no_manifest_is_inconclusive_however_perfect_the_examples(tmp_path):
    """Twenty ad-hoc examples with no approved manifest cannot conclude."""
    metrics = compute_stage1_metrics(_approved_examples(), manifest=None)

    assert metrics.state is GateState.INCONCLUSIVE
    assert "manifest" in metrics.reason
    assert planner_enforcement_permitted(metrics) is False


def test_an_absent_manifest_file_is_inconclusive(tmp_path):
    assert load_approved_manifest(tmp_path / "missing.json") is None

    metrics = compute_stage1_metrics(_approved_examples(), manifest=None)

    assert metrics.state is GateState.INCONCLUSIVE


def test_an_example_outside_the_manifest_is_inconclusive(tmp_path):
    manifest = _manifest_file(tmp_path)
    examples = _approved_examples()
    examples[0] = _example("fixture-not-approved")

    metrics = compute_stage1_metrics(examples, manifest=manifest)

    assert metrics.state is GateState.INCONCLUSIVE
    assert planner_enforcement_permitted(metrics) is False


def test_a_partial_set_is_inconclusive(tmp_path):
    manifest = _manifest_file(tmp_path)

    metrics = compute_stage1_metrics(_approved_examples()[:-1], manifest=manifest)

    assert metrics.state is GateState.INCONCLUSIVE


def test_a_manifest_below_the_sufficiency_floor_is_inconclusive(tmp_path):
    few = GROUNDING_IDS[:3]
    manifest = _manifest_file(tmp_path, fixture_ids=few, grounding_ids=few)

    metrics = compute_stage1_metrics([_example(i) for i in few], manifest=manifest)

    assert metrics.state is GateState.INCONCLUSIVE


def test_a_genuine_manifest_with_matching_examples_concludes(tmp_path):
    manifest = _manifest_file(tmp_path)

    metrics = compute_stage1_metrics(_approved_examples(), manifest=manifest)

    assert metrics.state is GateState.CONCLUSIVE
    assert metrics.false_none_rate == 0.0
    assert metrics.interaction_mode_accuracy == 1.0
    assert planner_enforcement_permitted(metrics) is True


# ---------------------------------------------------------------------------
# The denominator is the manifest's, not the caller's
# ---------------------------------------------------------------------------


def test_the_grounding_denominator_comes_from_the_manifest(tmp_path):
    """A caller cannot shrink the denominator by claiming nothing needs grounding."""
    manifest = _manifest_file(tmp_path)
    examples = _approved_examples()

    metrics = compute_stage1_metrics(examples, manifest=manifest)

    assert metrics.evaluated_grounding_required == len(GROUNDING_IDS)


def test_a_grounding_required_query_proposed_none_is_a_false_none(tmp_path):
    manifest = _manifest_file(tmp_path)
    examples = _approved_examples(
        **{GROUNDING_IDS[0]: {"proposed_context_mode": ContextMode.NONE}}
    )

    metrics = compute_stage1_metrics(examples, manifest=manifest)

    assert metrics.false_none_rate == pytest.approx(1 / len(GROUNDING_IDS))
    assert planner_enforcement_permitted(metrics) is False


# ---------------------------------------------------------------------------
# Exact correctness
# ---------------------------------------------------------------------------


def test_the_wrong_durable_action_is_not_a_true_positive(tmp_path):
    manifest = _manifest_file(tmp_path)
    examples = _approved_examples(
        **{
            GROUNDING_IDS[0]: {
                "expected_interaction_mode": InteractionMode.EXPLICIT_REMEMBER,
                "observed_interaction_mode": InteractionMode.EXPLICIT_FORGET,
            },
            GROUNDING_IDS[1]: {
                "expected_interaction_mode": InteractionMode.EXPLICIT_REMEMBER,
                "observed_interaction_mode": InteractionMode.EXPLICIT_REMEMBER,
            },
        }
    )

    metrics = compute_stage1_metrics(examples, manifest=manifest)

    assert metrics.intent_recall == pytest.approx(0.5)
    assert metrics.intent_precision == pytest.approx(0.5)
    assert metrics.durable_action_false_positive_rate == pytest.approx(0.5)
    assert metrics.interaction_mode_accuracy < 1.0


def test_rates_are_none_when_their_denominator_is_empty(tmp_path):
    manifest = _manifest_file(tmp_path)

    metrics = compute_stage1_metrics(_approved_examples(), manifest=manifest)

    assert metrics.intent_precision is None
    assert metrics.intent_recall is None
    assert metrics.durable_action_false_positive_rate is None


def test_the_metrics_are_frozen(tmp_path):
    manifest = _manifest_file(tmp_path)
    metrics = compute_stage1_metrics(_approved_examples(), manifest=manifest)

    with pytest.raises(dataclasses.FrozenInstanceError):
        metrics.state = GateState.INCONCLUSIVE  # type: ignore[misc]
