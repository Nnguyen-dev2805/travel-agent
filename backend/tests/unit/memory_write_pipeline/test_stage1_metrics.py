"""Task 4 round-3 fix 2: the manifest's trust root must not be a caller argument.

The previous version hashed the file but still accepted any `manifest` the caller
built, and `load_approved_manifest` accepted any path. So:

```python
manifest = load_approved_manifest("/tmp/totally-unapproved.json")
compute_stage1_metrics(twenty_matching_examples, manifest=manifest)
```

returned `CONCLUSIVE → false_none_rate=0.0 → planner_enforcement_permitted=True`.
Having *a* manifest is not the same as having an *approved* one.

Two things changed:

1. The manifest is read from a fixed governed path
   (`docs/evaluation/fixtures/agent-memory/stage1-manifest.json`), and
   `compute_stage1_metrics` takes **no manifest argument** at all, so there is
   nothing for a caller to substitute. Tests exercise the conclusive path by
   patching the module constant, which is a test seam and not a production API.
2. The manifest must carry an explicit **approval record** (`approved_by`,
   `approved_on`), so an accidental file at the governed path does not qualify.

Duplicate fixture IDs are also rejected: membership compared `frozenset`s, so 21
examples with one repeated ID satisfied a 20-ID manifest.

`spec:915` still governs: missing required evidence is `INCONCLUSIVE`, never
`PASS`.

No test here touches a database, a model, HTTP, or the network.
"""

from __future__ import annotations

import dataclasses
import inspect
import json

import pytest

from backend.memory.write_pipeline.evaluation import stage1_metrics
from backend.memory.write_pipeline.evaluation.stage1_metrics import (
    MIN_APPROVED_GROUNDING_FIXTURES,
    GateState,
    StageOneExample,
    compute_stage1_metrics,
    load_approved_manifest,
    planner_enforcement_permitted,
)
from backend.orchestration.turn_models import ContextMode, InteractionMode

TOTAL = MIN_APPROVED_GROUNDING_FIXTURES + 2
GROUNDING_IDS = [f"fixture-{index:03d}" for index in range(MIN_APPROVED_GROUNDING_FIXTURES)]
OTHER_IDS = [
    f"fixture-{index:03d}" for index in range(MIN_APPROVED_GROUNDING_FIXTURES, TOTAL)
]


def _write_manifest(tmp_path, *, approved=True, fixture_ids=None, grounding_ids=None):
    payload = {
        "fixture_set_id": "stage1-understanding-v0.1",
        "fixture_ids": fixture_ids if fixture_ids is not None else GROUNDING_IDS + OTHER_IDS,
        "grounding_required_fixture_ids": (
            grounding_ids if grounding_ids is not None else GROUNDING_IDS
        ),
    }
    if approved:
        payload["approved_by"] = "repository-owner"
        payload["approved_on"] = "2026-09-13"
    path = tmp_path / "stage1-manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def governed_manifest(tmp_path, monkeypatch):
    """A genuine manifest at the governed path, with an approval record."""

    def _install(**kwargs):
        path = _write_manifest(tmp_path, **kwargs)
        monkeypatch.setattr(stage1_metrics, "APPROVED_MANIFEST_PATH", path)
        return path

    return _install


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
    return [
        _example(fixture_id, **overrides.get(fixture_id, {}))
        for fixture_id in GROUNDING_IDS + OTHER_IDS
    ]


# ---------------------------------------------------------------------------
# The trust root is fixed
# ---------------------------------------------------------------------------


def test_the_metrics_take_no_manifest_argument():
    """There must be nothing for a caller to substitute.

    A `manifest` parameter — however hashed — is a caller-supplied trust root, so
    an arbitrary file could be presented as the approved set.
    """
    parameters = inspect.signature(compute_stage1_metrics).parameters

    assert "manifest" not in parameters
    assert list(parameters) == ["examples"]


def test_a_caller_supplied_path_is_not_part_of_the_api():
    """`load_approved_manifest` reads the governed path, not an argument."""
    parameters = inspect.signature(load_approved_manifest).parameters

    assert "path" not in parameters


def test_the_governed_manifest_path_is_inside_the_repository():
    assert stage1_metrics.APPROVED_MANIFEST_PATH.parts[-3:] == (
        "fixtures",
        "agent-memory",
        "stage1-manifest.json",
    )
    assert "docs" in stage1_metrics.APPROVED_MANIFEST_PATH.parts


# ---------------------------------------------------------------------------
# Evidence sufficiency
# ---------------------------------------------------------------------------


def test_no_examples_is_inconclusive(governed_manifest):
    governed_manifest()

    metrics = compute_stage1_metrics([])

    assert metrics.state is GateState.INCONCLUSIVE
    assert planner_enforcement_permitted(metrics) is False


def test_no_manifest_at_the_governed_path_is_inconclusive(tmp_path, monkeypatch):
    """Twenty perfect examples with no approved manifest cannot conclude."""
    monkeypatch.setattr(
        stage1_metrics, "APPROVED_MANIFEST_PATH", tmp_path / "absent.json"
    )

    metrics = compute_stage1_metrics(_approved_examples())

    assert metrics.state is GateState.INCONCLUSIVE
    assert planner_enforcement_permitted(metrics) is False


def test_a_manifest_without_an_approval_record_is_inconclusive(
    tmp_path, monkeypatch
):
    """A file at the governed path is not automatically approved."""
    path = _write_manifest(tmp_path, approved=False)
    monkeypatch.setattr(stage1_metrics, "APPROVED_MANIFEST_PATH", path)

    assert load_approved_manifest() is None

    metrics = compute_stage1_metrics(_approved_examples())

    assert metrics.state is GateState.INCONCLUSIVE


def test_duplicate_fixture_ids_are_rejected(governed_manifest):
    """Membership compared sets, so a repeated ID satisfied a 20-ID manifest."""
    governed_manifest()
    examples = _approved_examples() + [_example(GROUNDING_IDS[0])]

    metrics = compute_stage1_metrics(examples)

    assert metrics.state is GateState.INCONCLUSIVE
    assert planner_enforcement_permitted(metrics) is False


def test_an_example_outside_the_manifest_is_inconclusive(governed_manifest):
    governed_manifest()
    examples = _approved_examples()
    examples[0] = _example("fixture-not-approved")

    metrics = compute_stage1_metrics(examples)

    assert metrics.state is GateState.INCONCLUSIVE


def test_a_partial_set_is_inconclusive(governed_manifest):
    governed_manifest()

    metrics = compute_stage1_metrics(_approved_examples()[:-1])

    assert metrics.state is GateState.INCONCLUSIVE


def test_a_manifest_below_the_sufficiency_floor_is_inconclusive(
    tmp_path, monkeypatch
):
    few = GROUNDING_IDS[:3]
    path = _write_manifest(tmp_path, fixture_ids=few, grounding_ids=few)
    monkeypatch.setattr(stage1_metrics, "APPROVED_MANIFEST_PATH", path)

    metrics = compute_stage1_metrics([_example(i) for i in few])

    assert metrics.state is GateState.INCONCLUSIVE


def test_a_genuine_approved_manifest_with_matching_examples_concludes(
    governed_manifest,
):
    governed_manifest()

    metrics = compute_stage1_metrics(_approved_examples())

    assert metrics.state is GateState.CONCLUSIVE
    assert metrics.false_none_rate == 0.0
    assert metrics.interaction_mode_accuracy == 1.0
    assert planner_enforcement_permitted(metrics) is True


# ---------------------------------------------------------------------------
# The denominator is the manifest's
# ---------------------------------------------------------------------------


def test_the_grounding_denominator_comes_from_the_manifest(governed_manifest):
    governed_manifest()

    metrics = compute_stage1_metrics(_approved_examples())

    assert metrics.evaluated_grounding_required == len(GROUNDING_IDS)


def test_a_grounding_required_query_proposed_none_is_a_false_none(
    governed_manifest,
):
    governed_manifest()
    examples = _approved_examples(
        **{GROUNDING_IDS[0]: {"proposed_context_mode": ContextMode.NONE}}
    )

    metrics = compute_stage1_metrics(examples)

    assert metrics.false_none_rate == pytest.approx(1 / len(GROUNDING_IDS))
    assert planner_enforcement_permitted(metrics) is False


# ---------------------------------------------------------------------------
# Exact correctness
# ---------------------------------------------------------------------------


def test_the_wrong_durable_action_is_not_a_true_positive(governed_manifest):
    governed_manifest()
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

    metrics = compute_stage1_metrics(examples)

    assert metrics.intent_recall == pytest.approx(0.5)
    assert metrics.intent_precision == pytest.approx(0.5)
    assert metrics.durable_action_false_positive_rate == pytest.approx(0.5)
    assert metrics.interaction_mode_accuracy < 1.0


def test_rates_are_none_when_their_denominator_is_empty(governed_manifest):
    governed_manifest()

    metrics = compute_stage1_metrics(_approved_examples())

    assert metrics.intent_precision is None
    assert metrics.intent_recall is None
    assert metrics.durable_action_false_positive_rate is None


def test_the_metrics_are_frozen(governed_manifest):
    governed_manifest()
    metrics = compute_stage1_metrics(_approved_examples())

    with pytest.raises(dataclasses.FrozenInstanceError):
        metrics.state = GateState.INCONCLUSIVE  # type: ignore[misc]
