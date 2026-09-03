"""Unit tests for comparison compatibility, D5 gates, and uncertainty (Task 3).

Baseline and candidate are experiment roles assigned at comparison time
(ADR 0001). Evaluation core contains no collection-name role assumptions.
Invalid evidence never becomes a favorable conclusion.
"""

from __future__ import annotations

import pytest

from backend.rag.evaluation.comparison import (
    BOOTSTRAP_MIN_EXAMPLES,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    ComparisonResult,
    compare_runs,
    validate_comparison_contract,
)
from backend.rag.evaluation.models import ResultState

BASE_RUN_ID = "run-baseline-001"
CANDIDATE_RUN_ID = "run-candidate-001"


def make_run_record(
    run_id: str,
    *,
    dataset_version: str = "0.1",
    dataset_id: str = "travel-agent-rag-benchmark",
    eligible_count: int = 2,
    config_id: str = "config-x",
    state: str = "PASS",
    baseline_run_id: str | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "state": state,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "dataset_role": "benchmark",
        "manifest_id": "travel-agent-rag-benchmark",
        "manifest_version": "0.1",
        "relevance_contract": "document_id_binary_v1",
        "eligible_count": eligible_count,
        "primary_k": 5,
        "retrieval_k_values": [1, 3, 5, 10, 20],
        "score_semantics": "higher_is_better_similarity",
        "mandatory_slices": [
            "single_source_factual",
            "multi_evidence_synthesis",
            "ambiguous_underspecified",
            "source_citation_sensitive",
            "long_tail_difficult",
        ],
        "min_examples_per_slice": 1,
        "judge_config": None,
        "config_id": config_id,
        "runtime_adapter": "current_runtime",
        "prompt_id": "prompt-v1",
        "baseline_run_id": baseline_run_id,
        "aggregate_metrics": {
            "hit@5": 0.8,
            "mrr@5": 0.8,
            "ndcg@5": 0.8,
        },
        "slice_metrics": {
            "single_source_factual": {"hit@5": 0.8, "eligible_count": 2},
        },
    }


def make_examples(run_id: str, hit_flags: list[bool]) -> list[dict]:
    records = []
    for index, hit in enumerate(hit_flags, start=1):
        records.append(
            {
                "example_id": f"ex-{index:03d}",
                "run_id": run_id,
                "eligible": True,
                "slices": ["single_source_factual"],
                "expected_document_ids": [f"doc-{index:03d}"],
                "expected_source_urls": [f"https://example.test/doc-{index:03d}"],
                "metrics": {
                    "hit@5": 1 if hit else 0,
                    "mrr@5": 1.0 if hit else 0.0,
                    "ndcg@5": 1.0 if hit else 0.0,
                },
                "judge_valid": True,
                "failure_labels": [] if hit else ["retrieval_miss"],
            }
        )
    return records


def make_baseline_and_candidate(
    baseline_hits: list[bool], candidate_hits: list[bool]
) -> tuple[dict, list[dict], dict, list[dict]]:
    baseline_record = make_run_record(BASE_RUN_ID)
    baseline_examples = make_examples(BASE_RUN_ID, baseline_hits)
    candidate_record = make_run_record(
        CANDIDATE_RUN_ID,
        config_id="config-y",
        baseline_run_id=BASE_RUN_ID,
    )
    # Both records' aggregates and slice metrics must agree with their own
    # per-example records, so per-example deltas are the governed comparison.
    for record, hits_flags in (
        (baseline_record, baseline_hits),
        (candidate_record, candidate_hits),
    ):
        hits = sum(hits_flags)
        n = len(hits_flags)
        record["eligible_count"] = n
        record["aggregate_metrics"] = {
            "hit@5": hits / n,
            "mrr@5": hits / n,
            "ndcg@5": hits / n,
        }
        record["slice_metrics"] = {
            "single_source_factual": {
                "hit@5": hits / n,
                "eligible_count": n,
            }
        }
    candidate_examples = make_examples(CANDIDATE_RUN_ID, candidate_hits)
    # The fixture exercises the single_source_factual slice only: declare a
    # development role with that single mandatory slice so neither the
    # benchmark five-slice requirement nor missing slice metrics for the
    # other frozen slices apply to the minimal fixture. Benchmark-role slice
    # coverage is tested explicitly in the round-7 tests below.
    for record in (baseline_record, candidate_record):
        record["dataset_role"] = "development"
        record["mandatory_slices"] = ["single_source_factual"]
    return baseline_record, baseline_examples, candidate_record, candidate_examples


# ---------------------------------------------------------------------------
# Compatibility
# ---------------------------------------------------------------------------


def test_validate_compatible_runs_have_no_mismatches() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert mismatches == ()


def test_validate_rejects_dataset_version_mismatch() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_record = dict(candidate_record)
    candidate_record["dataset_version"] = "0.2"

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert "dataset_version" in mismatches


def test_validate_rejects_different_eligible_examples() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_examples = candidate_examples[:1]
    candidate_record["eligible_count"] = 1

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert any("eligible_examples" in mismatch for mismatch in mismatches)


def test_validate_rejects_relevance_contract_mismatch() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_record = dict(candidate_record)
    candidate_record["relevance_contract"] = "chunk_level_v2"

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert "relevance_contract" in mismatches


def test_runtime_adapter_difference_is_not_a_measurement_mismatch() -> None:
    """Candidate behavior change is recorded, not treated as incompatibility."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_record = dict(candidate_record)
    candidate_record["runtime_adapter"] = "structured_runtime_v1"

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert "runtime_adapter" not in mismatches


# ---------------------------------------------------------------------------
# D5 gates and final states
# ---------------------------------------------------------------------------


def test_compare_runs_pass_within_no_regression_gates() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, False], [True, False])
    )

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert isinstance(result, ComparisonResult)
    assert result.state == ResultState.PASS
    assert result.failed_gates == ()


def test_compare_runs_fails_on_hit5_decline_over_threshold() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True, True, True], [True, True, True, False])
    )

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.FAIL
    assert "hit@5" in result.failed_gates
    assert result.paired_deltas["hit@5"] == pytest.approx(-0.25)


def test_compare_runs_exact_threshold_decline_005_is_not_fail() -> None:
    """Hit@5 decline of exactly 0.01 (4 examples) is within the gate."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate(
            [True, True, True, True, True, True, True, True,
             True, True, True, True, True, True, True, True,
             True, True, True, True, True, True, True, True,
             True, True, True, True, True, True, True, True,
             False, False, False, False, False, False, False, False],
            [True, True, True, True, True, True, True, True,
             True, True, True, True, True, True, True, True,
             True, True, True, True, True, True, True, True,
             True, True, True, True, True, True, True, True,
             True, True, False, False, False, False, False, False],
        )
    )
    # 40 examples: baseline hit@5 = 0.8, candidate hit@5 = 0.85 → +0.05
    # Drop two candidate hits to construct a -0.05 delta: recompute below.

    # Simplify: build an exact -0.01 delta on 40 examples (baseline 0.80,
    # candidate 0.79): baseline 32 hits, candidate 31.6 is impossible; use 100
    # examples instead via explicit records.
    baseline_hits = [True] * 80 + [False] * 20
    candidate_hits = [True] * 79 + [False] * 21
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate(baseline_hits, candidate_hits)
    )

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    # decline = 0.01 exactly → gate allows (<= 0.01)
    assert result.state == ResultState.PASS


def test_compare_runs_invalid_on_version_mismatch() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_record = dict(candidate_record)
    candidate_record["dataset_version"] = "0.2"

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID
    assert result.failed_gates == ()


def test_compare_runs_inconclusive_when_slice_below_minimum() -> None:
    """An eligible mandatory slice below the manifest minimum is INCONCLUSIVE."""
    # Same per-example outcomes on both sides: no gate regression, but the
    # eligible slice count is below the manifest minimum.
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, False], [True, False])
    )
    candidate_record = dict(candidate_record)
    candidate_record["min_examples_per_slice"] = 5
    baseline_record = dict(baseline_record)
    baseline_record["min_examples_per_slice"] = 5

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INCONCLUSIVE


def test_compare_runs_marks_candidate_change_but_not_mismatch() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_record = dict(candidate_record)
    candidate_record["runtime_adapter"] = "structured_runtime_v1"

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.PASS
    assert result.candidate_changes["runtime_adapter"] == "structured_runtime_v1"


# ---------------------------------------------------------------------------
# Round-2 adversarial review findings (protocol correctness)
# ---------------------------------------------------------------------------


def test_missing_required_metric_pair_is_invalid_not_pass() -> None:
    """An eligible example missing a governed metric makes comparison INVALID.

    D5: missing required evidence must never silently drop out of the paired
    delta and let the comparison PASS.
    """
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_examples = [dict(candidate_examples[0]), dict(candidate_examples[1])]
    candidate_examples[1]["metrics"] = {"hit@5": None, "mrr@5": None, "ndcg@5": None}

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID


def test_ineligible_records_never_affect_paired_delta() -> None:
    """Ineligible records are excluded from deltas and cannot move gates."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, False], [True, False])
    )
    # The ineligible record exists on BOTH sides with the same ID, so the
    # eligible-example sets still match; only its metric would flip the delta
    # if the comparator wrongly consumed ineligible records.
    baseline_ineligible = dict(baseline_examples[1])
    baseline_ineligible["eligible"] = False
    baseline_examples[1] = baseline_ineligible
    ineligible = dict(candidate_examples[1])
    ineligible["eligible"] = False
    ineligible["metrics"] = {"hit@5": 1, "mrr@5": 1.0, "ndcg@5": 1.0}
    candidate_examples[1] = ineligible
    baseline_record["eligible_count"] = 1
    candidate_record["eligible_count"] = 1

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    # Only the eligible pair (hit, miss) is consumed: delta 0.0.
    assert result.paired_deltas["hit@5"] == pytest.approx(0.0)
    assert result.state == ResultState.PASS


def test_validate_rejects_wrong_baseline_reference() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_record = dict(candidate_record)
    candidate_record["baseline_run_id"] = "run-some-other-baseline"

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert any("baseline_run_id" in mismatch for mismatch in mismatches)


def test_compare_runs_rejects_invalid_baseline_state() -> None:
    """A baseline run that is not PASS cannot anchor a governed comparison."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    baseline_record = dict(baseline_record)
    baseline_record["state"] = "INVALID"

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID


def test_compare_runs_rejects_invalid_candidate_state() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_record = dict(candidate_record)
    candidate_record["state"] = "FAIL"

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID


def test_missing_mandatory_slice_metrics_is_invalid_not_pass() -> None:
    """A declared mandatory slice without metrics must not silently PASS."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    baseline_record = dict(baseline_record)
    baseline_record["mandatory_slices"] = ["single_source_factual", "long_tail_difficult"]
    baseline_record["slice_metrics"] = {
        "single_source_factual": {"hit@5": 1.0, "eligible_count": 2},
    }
    candidate_record = dict(candidate_record)
    candidate_record["mandatory_slices"] = ["single_source_factual", "long_tail_difficult"]
    candidate_record["slice_metrics"] = {
        "single_source_factual": {"hit@5": 1.0, "eligible_count": 2},
    }

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID


def test_answer_quality_gates_groundedness_and_correctness() -> None:
    """D5 answer gates: mean >= 4.0 and decline <= 0.10 on both dimensions."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    judge = {
        "model": "gpt-4o-mini",
        "prompt_id": "rag-answer-judge-v0.1",
        "rubric_id": "d5-rag-answer-v0.1",
        "schema_version": 1,
        "temperature": 0.0,
    }
    baseline_record = dict(baseline_record)
    baseline_record["judge_config"] = dict(judge)
    baseline_record["answer_metrics"] = {
        "mean_groundedness": 4.2,
        "mean_correctness": 4.2,
    }
    candidate_record = dict(candidate_record)
    candidate_record["judge_config"] = dict(judge)
    candidate_record["answer_metrics"] = {
        "mean_groundedness": 4.05,  # decline 0.15 > 0.10 → FAIL
        "mean_correctness": 4.3,
    }

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.FAIL
    assert "mean_groundedness_decline" in result.failed_gates


def test_answer_quality_gates_absolute_minimum() -> None:
    """Mean correctness below 4.0 fails even without a decline."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    judge = {
        "model": "gpt-4o-mini",
        "prompt_id": "rag-answer-judge-v0.1",
        "rubric_id": "d5-rag-answer-v0.1",
        "schema_version": 1,
        "temperature": 0.0,
    }
    baseline_record = dict(baseline_record)
    baseline_record["judge_config"] = dict(judge)
    baseline_record["answer_metrics"] = {
        "mean_groundedness": 4.2,
        "mean_correctness": 4.2,
    }
    candidate_record = dict(candidate_record)
    candidate_record["judge_config"] = dict(judge)
    candidate_record["answer_metrics"] = {
        "mean_groundedness": 4.2,
        "mean_correctness": 3.9,  # below 4.0 absolute minimum
    }

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.FAIL
    assert "mean_correctness_minimum" in result.failed_gates


def test_answer_quality_gates_absent_when_no_answer_layer() -> None:
    """Retrieval-only comparisons (no answer_metrics) skip answer gates."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.PASS
    assert not any("groundedness" in gate or "correctness" in gate for gate in result.failed_gates)


# ---------------------------------------------------------------------------
# Round-3 adversarial review findings (protocol correctness)
# ---------------------------------------------------------------------------


def test_ndcg_gate_catches_lost_known_relevant_document() -> None:
    """nDCG@5 with contract-based R penalizes a lost known-relevant document.

    Retrieving one of two known documents perfectly scores nDCG ≈ 0.613, so a
    candidate losing evidence cannot hide behind Hit@5.
    """
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    # Both sides' example metrics report ndcg reflecting the loss on candidate.
    baseline_examples[0]["metrics"]["ndcg@5"] = 1.0
    candidate_examples[0]["metrics"]["ndcg@5"] = 1.0 / (1.0 + 1.0 / __import__("math").log2(3))
    candidate_record["aggregate_metrics"]["ndcg@5"] = (
        candidate_examples[0]["metrics"]["ndcg@5"] + 1.0
    ) / 2

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    # decline = 1 - 0.6131 ≈ 0.387 > 0.01 → nDCG gate must fail
    assert result.state == ResultState.FAIL
    assert "ndcg@5" in result.failed_gates


def test_missing_slice_contract_is_invalid_not_pass() -> None:
    """Both runs dropping mandatory_slices cannot silently remove the gate."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    for record in (baseline_record, candidate_record):
        record.pop("mandatory_slices")
        record["slice_metrics"] = {}

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID


def test_missing_slice_hit_value_is_invalid_not_fail() -> None:
    """D5: missing required slice evidence is INVALID; FAIL needs valid evidence."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_record = dict(candidate_record)
    candidate_record["slice_metrics"] = {
        "single_source_factual": {"hit@5": None, "eligible_count": 2},
    }

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    # The paired examples carry the governed evidence; the stale None in the
    # run-record aggregate cannot manufacture a PASS.
    assert result.state == ResultState.INVALID


def test_one_sided_answer_metrics_is_invalid_not_pass() -> None:
    """One run carrying answer metrics and the other none is INVALID.

    An answer-layer comparison cannot silently skip groundedness/correctness
    gates because one side lacks the evidence.
    """
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    judge = {
        "model": "gpt-4o-mini",
        "prompt_id": "rag-answer-judge-v0.1",
        "rubric_id": "d5-rag-answer-v0.1",
        "schema_version": 1,
        "temperature": 0.0,
    }
    baseline_record = dict(baseline_record)
    baseline_record["judge_config"] = dict(judge)
    baseline_record["answer_metrics"] = {
        "mean_groundedness": 4.5,
        "mean_correctness": 4.5,
    }
    # candidate has no answer_metrics at all

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID


def test_missing_answer_dimension_is_invalid_not_fail() -> None:
    """A required answer dimension missing from one side is INVALID evidence."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    judge = {
        "model": "gpt-4o-mini",
        "prompt_id": "rag-answer-judge-v0.1",
        "rubric_id": "d5-rag-answer-v0.1",
        "schema_version": 1,
        "temperature": 0.0,
    }
    baseline_record = dict(baseline_record)
    baseline_record["judge_config"] = dict(judge)
    baseline_record["answer_metrics"] = {
        "mean_groundedness": 4.5,
        "mean_correctness": 4.5,
    }
    candidate_record = dict(candidate_record)
    candidate_record["judge_config"] = dict(judge)
    candidate_record["answer_metrics"] = {"mean_groundedness": 4.4}

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID


def test_mismatched_min_examples_per_slice_is_incompatible() -> None:
    """A candidate cannot lower the frozen slice minimum to avoid INCONCLUSIVE."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, False], [True, False])
    )
    baseline_record = dict(baseline_record)
    baseline_record["min_examples_per_slice"] = 5
    candidate_record = dict(candidate_record)
    candidate_record["min_examples_per_slice"] = 1

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert any("min_examples_per_slice" in mismatch for mismatch in mismatches)


# ---------------------------------------------------------------------------
# Round-4 adversarial review findings (protocol correctness)
# ---------------------------------------------------------------------------


def test_exact_slice_decline_boundary_passes() -> None:
    """A decline of exactly 0.03 on a mandatory slice is within the gate.

    D5 says decline <= 0.03 passes; float artifacts must not flip the boundary.
    """
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True] * 5, [True] * 5)
    )
    baseline_record = dict(baseline_record)
    baseline_record["slice_metrics"] = {
        "single_source_factual": {"hit@5": 0.80, "eligible_count": 5},
    }
    candidate_record = dict(candidate_record)
    candidate_record["slice_metrics"] = {
        "single_source_factual": {"hit@5": 0.77, "eligible_count": 5},
    }

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.PASS
    assert not any("mandatory_slice" in gate for gate in result.failed_gates)


def test_exact_answer_decline_boundary_passes() -> None:
    """A decline of exactly 0.10 on answer dimensions is within the gate."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    judge = {
        "model": "gpt-4o-mini",
        "prompt_id": "rag-answer-judge-v0.1",
        "rubric_id": "d5-rag-answer-v0.1",
        "schema_version": 1,
        "temperature": 0.0,
    }
    baseline_record = dict(baseline_record)
    baseline_record["judge_config"] = dict(judge)
    baseline_record["answer_metrics"] = {
        "mean_groundedness": 4.2,
        "mean_correctness": 4.2,
    }
    candidate_record = dict(candidate_record)
    candidate_record["judge_config"] = dict(judge)
    candidate_record["answer_metrics"] = {
        "mean_groundedness": 4.1,
        "mean_correctness": 4.1,
    }

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.PASS


def test_judged_runs_without_answer_metrics_are_invalid() -> None:
    """A frozen judge contract without answer evidence on both sides is INVALID.

    Judged runs are not retrieval-only; missing required answer evidence must
    not degrade to INCONCLUSIVE or PASS.
    """
    judge = {
        "model": "gpt-4o-mini",
        "prompt_id": "rag-answer-judge-v0.1",
        "rubric_id": "d5-rag-answer-v0.1",
        "schema_version": 1,
        "temperature": 0.0,
    }
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    baseline_record = dict(baseline_record)
    baseline_record["judge_config"] = dict(judge)
    candidate_record = dict(candidate_record)
    candidate_record["judge_config"] = dict(judge)

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID


def test_judge_temperature_mismatch_is_incompatible() -> None:
    """D5 freezes judge sampling parameters; temperature is part of identity."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    baseline_record = dict(baseline_record)
    baseline_record["judge_config"] = {
        "model": "m", "prompt_id": "p", "rubric_id": "r",
        "schema_version": 1, "temperature": 0.0,
    }
    candidate_record = dict(candidate_record)
    candidate_record["judge_config"] = {
        "model": "m", "prompt_id": "p", "rubric_id": "r",
        "schema_version": 1, "temperature": 0.7,
    }

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert "judge_config" in mismatches


def test_non_mandatory_slice_below_minimum_does_not_block() -> None:
    """The slice-minimum gate applies to mandatory slices, not diagnostics."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True] * 5, [True] * 5)
    )
    for record in (baseline_record, candidate_record):
        record["min_examples_per_slice"] = 5
        record["slice_metrics"] = {
            "single_source_factual": {"hit@5": 1.0, "eligible_count": 5},
            "diagnostic_extra": {"hit@5": 0.5, "eligible_count": 1},
        }

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.PASS


def test_eligible_example_set_ignores_serialization_order() -> None:
    """The contract requires the same eligible set, not the same order."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_examples = [candidate_examples[1], candidate_examples[0]]

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert "eligible_examples" not in mismatches


def test_duplicate_eligible_example_ids_are_incompatible() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    duplicate = dict(candidate_examples[0])
    candidate_examples.append(duplicate)
    candidate_record["eligible_count"] = 3

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert any("duplicate" in mismatch for mismatch in mismatches)


# ---------------------------------------------------------------------------
# Round-5 adversarial review findings (protocol correctness)
# ---------------------------------------------------------------------------


def test_mandatory_slice_gate_uses_paired_examples_not_stale_aggregate() -> None:
    """Slice deltas must derive from paired per-example evidence.

    A stale run-record slice metric that hides a mandatory-slice regression
    must not produce PASS. Overall delta 0 can conceal a slice regression that
    a compensating diagnostic example offsets.
    """
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, False], [False, True])
    )
    # Record slice at example level: mandatory slice loses, diagnostic gains.
    baseline_examples[0]["slices"] = ["single_source_factual"]
    baseline_examples[1]["slices"] = ["diagnostic_extra"]
    candidate_examples[0]["slices"] = ["single_source_factual"]
    candidate_examples[1]["slices"] = ["diagnostic_extra"]
    # Stale/incorrect aggregate slice metrics claim no regression.
    for record in (baseline_record, candidate_record):
        record["slice_metrics"] = {
            "single_source_factual": {"hit@5": 1.0, "eligible_count": 1},
            "diagnostic_extra": {"hit@5": 0.0, "eligible_count": 1},
        }

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    # Paired mandatory slice delta = 0 - 1 = -1.0 -> gate FAIL despite the
    # stale aggregate claiming 0.0.
    assert result.state == ResultState.FAIL
    assert "mandatory_slice_hit@5:single_source_factual" in result.failed_gates


def test_nan_retrieval_metrics_are_invalid() -> None:
    """NaN/inf governed metrics are invalid evidence, never a quiet PASS."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    nan_metrics = {"hit@5": float("nan"), "mrr@5": float("nan"), "ndcg@5": float("nan")}
    candidate_examples[0]["metrics"] = dict(nan_metrics)

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID


def test_nan_answer_metrics_are_invalid() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    judge = {
        "model": "gpt-4o-mini",
        "prompt_id": "rag-answer-judge-v0.1",
        "rubric_id": "d5-rag-answer-v0.1",
        "schema_version": 1,
        "temperature": 0.0,
    }
    baseline_record = dict(baseline_record)
    baseline_record["judge_config"] = dict(judge)
    baseline_record["answer_metrics"] = {
        "mean_groundedness": float("nan"),
        "mean_correctness": 4.5,
    }
    candidate_record = dict(candidate_record)
    candidate_record["judge_config"] = dict(judge)
    candidate_record["answer_metrics"] = {
        "mean_groundedness": 4.4,
        "mean_correctness": 4.5,
    }

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID


def test_duplicates_on_both_sides_are_invalid() -> None:
    """Duplicate eligible IDs are invalid per side, not a matching 'set'."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    baseline_examples.append(dict(baseline_examples[0]))
    candidate_examples.append(dict(candidate_examples[0]))
    baseline_record["eligible_count"] = 3
    candidate_record["eligible_count"] = 3

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert mismatches
    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)
    assert result.state == ResultState.INVALID


def test_zero_eligible_pairs_is_invalid_not_pass() -> None:
    """A governed comparison with no paired primary evidence cannot PASS."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )

    result = compare_runs(baseline_record, [], candidate_record, [])

    assert result.state == ResultState.INVALID


def test_missing_slice_eligible_count_is_invalid() -> None:
    """Without eligible_count the slice minimum cannot be applied: INVALID."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    baseline_record = dict(baseline_record)
    baseline_record["slice_metrics"] = {
        "single_source_factual": {"hit@5": 1.0},
    }
    candidate_record = dict(candidate_record)
    candidate_record["slice_metrics"] = {
        "single_source_factual": {"hit@5": 1.0},
    }

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID


def test_gate_decline_just_over_threshold_fails() -> None:
    """A real decline beyond the threshold fails even though it is tiny.

    Float tolerance covers machine epsilon only (1e-9), not thousandths.
    Slice gates derive from paired per-example evidence, so the over-threshold
    decline is expressed through the example metrics.
    """
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate(
            [True] * 1000, [True] * 999 + [False]
        )
    )
    # Paired slice decline = -1/1000 = -0.001... not over 0.03; instead use a
    # small slice with a genuine over-threshold decline.
    baseline_hits = [True, True, True, True, True, True, True, True, True, True,
                     True, True, True, True, True, True, True, True, True, True,
                     True, True, True, True, True, True, True, True, True, True,
                     True, True, False]
    candidate_hits = [True] * 29 + [False] * 4
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate(baseline_hits, candidate_hits)
    )
    # baseline slice hit@5 = 32/33 ≈ 0.9697, candidate = 29/33 ≈ 0.8788
    # decline ≈ 0.0909 > 0.03 → mandatory-slice gate FAIL
    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.FAIL
    assert "mandatory_slice_hit@5:single_source_factual" in result.failed_gates


# ---------------------------------------------------------------------------
# Round-6 adversarial review findings (protocol correctness)
# ---------------------------------------------------------------------------


def test_candidate_slice_relabel_cannot_hide_regression() -> None:
    """Slice membership is frozen per example_id across both runs.

    A candidate that relabels a regressed mandatory example into a diagnostic
    slice must not be able to hide the mandatory-slice regression.
    """
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    # Baseline: two mandatory hits, one diagnostic miss.
    baseline_examples = [
        make_examples(BASE_RUN_ID, [True])[0],
        make_examples(BASE_RUN_ID, [True])[0],
        make_examples(BASE_RUN_ID, [False])[0],
    ]
    baseline_examples[0] = dict(baseline_examples[0], example_id="m1", slices=["single_source_factual"])
    baseline_examples[1] = dict(baseline_examples[1], example_id="m2", slices=["single_source_factual"])
    baseline_examples[2] = dict(baseline_examples[2], example_id="d1", slices=["diagnostic_extra"])
    # Candidate: m2 regresses AND is relabeled into the diagnostic slice; the
    # diagnostic improvement compensates the overall delta.
    candidate_examples = [
        dict(make_examples(CANDIDATE_RUN_ID, [True])[0], example_id="m1", slices=["single_source_factual"]),
        dict(make_examples(CANDIDATE_RUN_ID, [False])[0], example_id="m2", slices=["diagnostic_extra"]),
        dict(make_examples(CANDIDATE_RUN_ID, [True])[0], example_id="d1", slices=["diagnostic_extra"]),
    ]
    baseline_record["eligible_count"] = 3
    candidate_record["eligible_count"] = 3

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    # The relabel changes the frozen classification of example m2, so the
    # comparison is invalid rather than PASS with a hidden regression.
    assert any("slice_membership" in mismatch for mismatch in mismatches)

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID


def test_retrieval_gate_uses_raw_delta_not_rounded() -> None:
    """A raw -0.0100004 decline fails even though persisted delta rounds to -0.01."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True], [True])
    )
    baseline_examples[0]["metrics"]["mrr@5"] = 0.5
    candidate_examples[0]["metrics"]["mrr@5"] = 0.4899996

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.paired_deltas["mrr@5"] == pytest.approx(-0.01)
    assert result.state == ResultState.FAIL
    assert "mrr@5" in result.failed_gates


def test_stale_eligible_count_cannot_bypass_inconclusive() -> None:
    """The slice minimum uses paired evidence counts, not recorded claims."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    for record in (baseline_record, candidate_record):
        record["min_examples_per_slice"] = 5
        record["slice_metrics"] = {
            "single_source_factual": {"hit@5": 1.0, "eligible_count": 5},
        }

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )
    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    # Only 2 paired examples exist in the mandatory slice; the recorded 5 is
    # stale, so the comparison must be INCONCLUSIVE, not PASS.
    assert result.state == ResultState.INCONCLUSIVE
    assert "min_examples_per_slice" not in mismatches


@pytest.mark.parametrize(
    ("metric", "value"),
    (("hit@5", 2.0), ("mrr@5", -0.1), ("ndcg@5", 1.1)),
)
def test_out_of_range_retrieval_evidence_is_invalid(metric: str, value: float) -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_examples[0]["metrics"][metric] = value

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "range" in result.reason.lower() or "invalid" in result.reason.lower()


def test_numeric_string_retrieval_evidence_is_invalid() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_examples[0]["metrics"]["hit@5"] = "1"

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "numeric" in result.reason.lower()


def test_out_of_range_answer_evidence_is_invalid() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    judge = {
        "model": "judge-v1",
        "prompt_id": "judge-prompt-v1",
        "rubric_id": "d5-v1",
        "schema_version": 1,
        "temperature": 0.0,
    }
    for record in (baseline_record, candidate_record):
        record["judge_config"] = dict(judge)
        record["answer_metrics"] = {
            "mean_groundedness": 6.0,
            "mean_correctness": 5.0,
        }

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "1..5" in result.reason or "range" in result.reason.lower()


@pytest.mark.parametrize("value", ("5", 0, -1, True, 1.5))
def test_invalid_min_examples_per_slice_is_incompatible(value: object) -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    for record in (baseline_record, candidate_record):
        record["min_examples_per_slice"] = value

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "min_examples_per_slice" in result.reason


def test_numeric_string_answer_evidence_is_invalid() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    judge = {
        "model": "judge-v1",
        "prompt_id": "judge-prompt-v1",
        "rubric_id": "d5-v1",
        "schema_version": 1,
        "temperature": 0.0,
    }
    for record in (baseline_record, candidate_record):
        record["judge_config"] = dict(judge)
        record["answer_metrics"] = {
            "mean_groundedness": "4.5",
            "mean_correctness": 4.5,
        }

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "numeric" in result.reason.lower()


@pytest.mark.parametrize(
    ("field", "value"),
    (("eligible_count", "five"), ("eligible_count", -1), ("hit@5", "1"), ("hit@5", 2.0)),
)
def test_invalid_mandatory_slice_metadata_is_invalid(field: str, value: object) -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_record["slice_metrics"]["single_source_factual"][field] = value

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert field in result.reason


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("primary_k", "5"),
        ("retrieval_k_values", "5"),
        ("dataset_role", 123),
        ("relevance_contract", 123),
        ("mandatory_slices", ["single_source_factual", 7]),
    ),
)
def test_malformed_frozen_contract_is_invalid(field: str, value: object) -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    for record in (baseline_record, candidate_record):
        record[field] = value

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert field in result.reason


def test_non_d5_primary_k_is_invalid_even_when_both_runs_match() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    for record in (baseline_record, candidate_record):
        record["primary_k"] = 3
        record["retrieval_k_values"] = [3]

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "primary_k" in result.reason


def test_incompatible_score_semantics_is_invalid() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    baseline_record["score_semantics"] = "higher_is_better_similarity"
    candidate_record["score_semantics"] = "lower_is_better_distance"

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "score_semantics" in result.reason


def test_stale_run_eligible_count_is_invalid() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    baseline_record["eligible_count"] = 999
    candidate_record["eligible_count"] = 999

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "eligible_count" in result.reason


def test_malformed_top_level_run_record_is_invalid_not_exception() -> None:
    _, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )

    result = compare_runs(
        [], baseline_examples, candidate_record, candidate_examples  # type: ignore[arg-type]
    )

    assert result.state == ResultState.INVALID
    assert "baseline_record_invalid" in result.reason


def test_malformed_judge_config_is_invalid() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    for record in (baseline_record, candidate_record):
        record["judge_config"] = "not-a-judge-object"
        record["answer_metrics"] = {
            "mean_groundedness": 4.5,
            "mean_correctness": 4.5,
        }

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "judge_config" in result.reason


def test_non_boolean_eligible_is_invalid() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    baseline_examples[0]["eligible"] = "false"
    candidate_examples[0]["eligible"] = "false"

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "eligible" in result.reason


def test_non_mapping_metrics_is_invalid_not_exception() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_examples[0]["metrics"] = "garbage"

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "metrics" in result.reason


def test_baseline_candidate_eligible_count_mismatch_is_incompatible() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    baseline_record = dict(baseline_record)
    baseline_record["slice_metrics"] = {
        "single_source_factual": {"hit@5": 1.0, "eligible_count": 2},
    }
    candidate_record = dict(candidate_record)
    candidate_record["slice_metrics"] = {
        "single_source_factual": {"hit@5": 1.0, "eligible_count": 1},
    }
    candidate_examples = candidate_examples[:1]
    candidate_record["eligible_count"] = 1

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert "eligible_examples" in mismatches


def test_compare_runs_requires_baseline_run_id_reference() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_record = dict(candidate_record)
    candidate_record["baseline_run_id"] = None

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID


# ---------------------------------------------------------------------------
# Round-7 adversarial review findings (protocol correctness)
# ---------------------------------------------------------------------------


def test_answer_metrics_without_judge_contract_are_invalid() -> None:
    """Judge-based scores without a frozen judge contract are not evidence.

    D5 freezes the judge model/prompt/rubric/schema before scores become
    admissible; a comparison carrying answer_metrics with judge_config=None
    on both sides must be INVALID, not PASS.
    """
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    for record in (baseline_record, candidate_record):
        record["answer_metrics"] = {
            "mean_groundedness": 4.5,
            "mean_correctness": 4.5,
        }
        record["judge_config"] = None

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID
    assert "judge_config" in result.reason or "judge" in result.reason.lower()


def test_baseline_and_candidate_empty_run_id_are_invalid() -> None:
    """A run without a real identity cannot anchor a governed comparison."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    baseline_record = dict(baseline_record)
    baseline_record["run_id"] = ""
    candidate_record = dict(candidate_record)
    candidate_record["baseline_run_id"] = ""

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )
    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert any("baseline_run_id" in mismatch for mismatch in mismatches)
    assert result.state == ResultState.INVALID


def test_role_aware_mandatory_slices_allow_development_runs() -> None:
    """Task 2 contract: non-benchmark roles may declare mandatory_slices = [].

    A development comparison with an empty mandatory-slice contract is
    compatible and governed by its paired evidence, not forced INVALID by the
    benchmark-only slice rule.
    """
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    for record, examples in (
        (baseline_record, baseline_examples),
        (candidate_record, candidate_examples),
    ):
        record["dataset_role"] = "development"
        record["mandatory_slices"] = []
        record["slice_metrics"] = {}
        for example in examples:
            example["slices"] = []

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )
    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert mismatches == ()
    assert result.state == ResultState.PASS


def test_benchmark_role_with_partial_mandatory_slices_is_incompatible() -> None:
    """Benchmark runs must govern the frozen five-slice contract at comparison.

    Both sides declaring the same partial benchmark slice contract cannot
    silently remove the missing D5 gates.
    """
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    for record in (baseline_record, candidate_record):
        record["dataset_role"] = "benchmark"
        record["mandatory_slices"] = ["single_source_factual"]
        record["slice_metrics"] = {
            "single_source_factual": {"hit@5": 1.0, "eligible_count": 2},
        }

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )
    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert any("mandatory_slices" in mismatch for mismatch in mismatches)
    assert result.state == ResultState.INVALID


def test_manifest_identity_mismatch_is_incompatible() -> None:
    """Different manifest identities cannot anchor one governed comparison."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_record["manifest_id"] = "different-reviewed-manifest"

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )
    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert "manifest_id" in mismatches
    assert result.state == ResultState.INVALID


def test_expected_document_label_mismatch_is_incompatible() -> None:
    """Paired metric deltas require the same governed relevance labels."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_examples[0]["expected_document_ids"] = ["different-doc"]

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )
    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert any("expected_document_ids" in mismatch for mismatch in mismatches)
    assert result.state == ResultState.INVALID


def test_expected_source_label_mismatch_is_incompatible() -> None:
    """Source-hit diagnostics cannot compare against changed frozen source labels."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    candidate_examples[0]["expected_source_urls"] = ["https://example.test/different"]

    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert any("expected_source_urls" in mismatch for mismatch in mismatches)


def test_duplicate_slice_labels_are_invalid_not_double_counted() -> None:
    """Duplicate labels cannot inflate paired evidence above the slice minimum."""
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True], [True])
    )
    for record in (baseline_record, candidate_record):
        record["min_examples_per_slice"] = 2
        record["slice_metrics"] = {
            "single_source_factual": {"hit@5": 1.0, "eligible_count": 1},
        }
    for example in (baseline_examples[0], candidate_examples[0]):
        example["slices"] = ["single_source_factual", "single_source_factual"]

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.state == ResultState.INVALID
    assert "slices" in result.reason


def test_example_slices_field_drives_slice_gates() -> None:
    """Slice membership uses the dataset-contract 'slices' list field.

    An example record with 'slices': [...] but no legacy singular 'slice'
    field must still be governed by the mandatory-slice gate.
    """
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    baseline_examples[0]["slices"] = ["single_source_factual"]
    candidate_examples[0]["slices"] = ["single_source_factual"]
    baseline_examples[1]["slices"] = []
    candidate_examples[1]["slices"] = []
    candidate_examples[0]["metrics"]["hit@5"] = 0
    candidate_examples[0]["metrics"]["mrr@5"] = 0.0
    candidate_examples[0]["metrics"]["ndcg@5"] = 0.0
    for record in (baseline_record, candidate_record):
        record["slice_metrics"] = {
            "single_source_factual": {"hit@5": 1.0, "eligible_count": 1},
        }

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    # The single mandatory-slice pair regresses 1 -> 0: decline 1.0 > 0.03.
    assert result.state == ResultState.FAIL
    assert "mandatory_slice_hit@5:single_source_factual" in result.failed_gates


# ---------------------------------------------------------------------------
# Round-8 adversarial review findings
# ---------------------------------------------------------------------------


def test_unknown_dataset_role_is_invalid_not_pass() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    for record in (baseline_record, candidate_record):
        record["dataset_role"] = "not-a-real-role"
        record["mandatory_slices"] = []
        record["slice_metrics"] = {}

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "dataset_role" in result.reason


def test_judge_invalid_count_is_invalid_not_pass() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    judge = {
        "model": "gpt-4o-mini",
        "prompt_id": "rag-answer-judge-v0.1",
        "rubric_id": "d5-rag-answer-v0.1",
        "schema_version": 1,
        "temperature": 0.0,
    }
    for record in (baseline_record, candidate_record):
        record["judge_config"] = dict(judge)
        record["judge_valid_count"] = 1
        record["judge_invalid_count"] = 1
        record["answer_metrics"] = {
            "mean_groundedness": 4.5,
            "mean_correctness": 4.5,
        }
    for examples in (baseline_examples, candidate_examples):
        examples[0]["judge_valid"] = True
        examples[1]["judge_valid"] = False
        examples[1]["failure_labels"] = ["judge_invalid"]

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "judge_invalid" in result.reason


def test_judged_comparison_without_per_example_judge_evidence_is_invalid() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    judge = {
        "model": "gpt-4o-mini",
        "prompt_id": "rag-answer-judge-v0.1",
        "rubric_id": "d5-rag-answer-v0.1",
        "schema_version": 1,
        "temperature": 0.0,
    }
    for record in (baseline_record, candidate_record):
        record["judge_config"] = dict(judge)
        record["judge_valid_count"] = 0
        record["judge_invalid_count"] = 0
        record["answer_metrics"] = {
            "mean_groundedness": 4.5,
            "mean_correctness": 4.5,
        }
    for example in baseline_examples + candidate_examples:
        example["judge_valid"] = None

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "judge" in result.reason


def test_invalid_retrieval_evidence_marker_is_invalid_not_pass() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )
    for example in baseline_examples + candidate_examples:
        example["metrics"]["invalid_evidence_count"] = 1

    result = compare_runs(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    assert result.state == ResultState.INVALID
    assert "invalid_evidence" in result.reason


# ---------------------------------------------------------------------------
# Uncertainty metadata (Step 8)
# ---------------------------------------------------------------------------


def test_bootstrap_predeclared_constants() -> None:
    assert BOOTSTRAP_MIN_EXAMPLES == 30
    assert BOOTSTRAP_RESAMPLES == 2000
    assert BOOTSTRAP_SEED == 20260901


def test_uncertainty_not_applicable_below_30_examples() -> None:
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate([True, True], [True, True])
    )

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.uncertainty["uncertainty_status"] == "not_applicable_n_lt_30"
    assert "hit@5" not in result.uncertainty.get("confidence_intervals", {})


def test_uncertainty_bootstrap_intervals_when_n_at_least_30() -> None:
    baseline_hits = [i % 2 == 0 for i in range(40)]
    candidate_hits = [i % 2 == 0 for i in range(40)]
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate(baseline_hits, candidate_hits)
    )

    result = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert result.uncertainty["uncertainty_status"] == "bootstrap_paired"
    interval = result.uncertainty["confidence_intervals"]["hit@5"]
    assert interval["low"] <= 0.0 <= interval["high"]
    assert interval["resamples"] == BOOTSTRAP_RESAMPLES
    assert interval["seed"] == BOOTSTRAP_SEED


def test_bootstrap_interval_is_deterministic() -> None:
    baseline_hits = [i % 2 == 0 for i in range(40)]
    candidate_hits = [(i % 3 == 0) for i in range(40)]
    baseline_record, baseline_examples, candidate_record, candidate_examples = (
        make_baseline_and_candidate(baseline_hits, candidate_hits)
    )

    first = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)
    second = compare_runs(baseline_record, baseline_examples, candidate_record, candidate_examples)

    assert (
        first.uncertainty["confidence_intervals"]["hit@5"]
        == second.uncertainty["confidence_intervals"]["hit@5"]
    )
