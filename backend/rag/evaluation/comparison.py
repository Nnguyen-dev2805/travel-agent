"""Comparison compatibility, D5 gates, and uncertainty metadata for the R2 harness.

Baseline and candidate are experiment roles assigned at comparison time; core
comparison logic holds no collection-name or role assumptions (ADR 0001).
Incompatible runs produce ``INVALID``; valid-but-weak evidence produces
``INCONCLUSIVE``; a real gate violation on valid evidence produces ``FAIL``.
No synthetic favorable conclusions are produced from invalid evidence.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from backend.rag.evaluation.dataset import (
    BENCHMARK_REQUIRED_MANDATORY_SLICES,
    REQUIRED_PRIMARY_K,
    REQUIRED_RETRIEVAL_K_VALUES,
    REQUIRED_SCORE_SEMANTICS,
)
from backend.rag.evaluation.models import DatasetRole, ResultState

# Predeclared uncertainty contract (Task 3 Step 8); fixed seed keeps intervals
# deterministic for the same input evidence.
BOOTSTRAP_MIN_EXAMPLES = 30
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260901

# D5 hard gates (Global Constraints; exact thresholds, not config-driven).
HIT5_MAX_DECLINE = 0.01
MRR5_MAX_DECLINE = 0.01
NDCG5_MAX_DECLINE = 0.01
MANDATORY_SLICE_HIT5_MAX_DECLINE = 0.03
GROUNDEDNESS_MINIMUM = 4.0
GROUNDEDNESS_MAX_DECLINE = 0.10
CORRECTNESS_MINIMUM = 4.0
CORRECTNESS_MAX_DECLINE = 0.10

PRIMARY_METRIC = "hit@5"

# Gate comparisons use a tiny epsilon so machine float error never flips an
# exact-threshold boundary, while a real (even tiny) decline still fails.
GATE_FLOAT_TOLERANCE = 1e-9

# Governed per-example retrieval metrics required from every eligible record.
REQUIRED_PAIRED_METRICS: tuple[str, ...] = ("hit@5", "mrr@5", "ndcg@5")

# Comparison-contract fields that must match for a governed paired delta.
_REQUIRED_MATCH_FIELDS: tuple[str, ...] = (
    "dataset_id",
    "dataset_version",
    "dataset_role",
    "manifest_id",
    "manifest_version",
    "relevance_contract",
    "primary_k",
    "retrieval_k_values",
    "score_semantics",
    "mandatory_slices",
)

# Candidate behavior differences that are recorded as candidate changes, not
# measurement mismatches (per plan Task 3 Step 7).
_CANDIDATE_CHANGE_FIELDS: tuple[str, ...] = (
    "runtime_adapter",
    "prompt_id",
    "config_id",
)


def _example_slice_labels(record: Mapping[str, Any]) -> tuple[str, ...]:
    """Frozen per-example slice labels from the dataset contract.

    Example records carry ``slices`` exactly as the Task 2 dataset contract
    defines it: a list of slice IDs, possibly empty. A legacy singular
    ``slice`` string is accepted so evidence serialized before this contract
    alignment stays reviewable, but ``slices`` is authoritative.
    """
    slices_value = record.get("slices")
    if isinstance(slices_value, (list, tuple)):
        return tuple(str(item) for item in slices_value)
    legacy = record.get("slice")
    if isinstance(legacy, str) and legacy.strip():
        return (legacy,)
    return ()


def _example_slice_identity(record: Mapping[str, Any]) -> tuple[str, ...]:
    """Frozen classification used for cross-run membership agreement."""
    return tuple(sorted(_example_slice_labels(record)))


def _string_sequence_identity(value: Any) -> tuple[str, ...]:
    """Order-insensitive identity for frozen string-label sequences."""
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(sorted(str(item) for item in value))


@dataclass(frozen=True)
class ComparisonResult:
    """Final governed comparison outcome under the D5 protocol."""

    state: ResultState
    paired_deltas: dict[str, float]
    slice_deltas: dict[str, dict[str, float]]
    failed_gates: tuple[str, ...]
    candidate_changes: dict[str, Any]
    uncertainty: dict[str, Any]
    reason: str


def _pair_metric_records(
    baseline_examples: Sequence[Mapping[str, Any]],
    candidate_examples: Sequence[Mapping[str, Any]],
    required_metrics: Sequence[str] = REQUIRED_PAIRED_METRICS,
) -> dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] | str:
    """Join eligible baseline/candidate records by example ID.

    Returns a mapping of example ID to its paired records, or a string naming
    the validity problem: missing required metrics on an eligible record make
    the comparison invalid instead of silently dropping the pair.
    """
    baseline_by_id = {
        str(record["example_id"]): record for record in baseline_examples
    }
    paired: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for record in candidate_examples:
        if not record.get("eligible"):
            continue
        example_id = str(record["example_id"])
        baseline_record = baseline_by_id.get(example_id)
        if baseline_record is None or not baseline_record.get("eligible"):
            continue
        for metric in required_metrics:
            if (
                record.get("metrics", {}).get(metric) is None
                or baseline_record.get("metrics", {}).get(metric) is None
            ):
                return (
                    f"eligible example '{example_id}' is missing required "
                    f"metric '{metric}'"
                )
        paired[example_id] = (baseline_record, record)
    return paired


def _eligible_example_ids(
    example_records: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Sorted unique eligible example IDs.

    The contract requires the same eligible set, not the same serialization
    order. Duplicate eligible IDs are a validity error independent per side
    and are reported separately from a set mismatch.
    """
    ids: list[str] = [
        str(record["example_id"])
        for record in example_records
        if record.get("eligible")
    ]
    return tuple(sorted(set(ids)))


def _has_duplicate_eligible_ids(
    example_records: Sequence[Mapping[str, Any]],
) -> bool:
    ids = [
        str(record["example_id"])
        for record in example_records
        if record.get("eligible")
    ]
    return len(ids) != len(set(ids))


def _judge_identity(judge_config: Any) -> Any:
    if not judge_config:
        return None
    return (
        judge_config.get("model"),
        judge_config.get("prompt_id"),
        judge_config.get("rubric_id"),
        judge_config.get("schema_version"),
        judge_config.get("temperature"),
    )


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_nonempty_string_record_field(record: Mapping[str, Any], field: str) -> bool:
    return _is_nonempty_string(record.get(field))


def _valid_positive_int_sequence(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and bool(value)
        and all(
            isinstance(item, int) and not isinstance(item, bool) and item > 0
            for item in value
        )
    )


def _valid_string_sequence(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and bool(value)
        and all(_is_nonempty_string(item) for item in value)
        and len(set(value)) == len(value)
    )


def _valid_example_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )


def _valid_judge_config(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, Mapping):
        return False
    if not all(
        _is_nonempty_string(value.get(field))
        for field in ("model", "prompt_id", "rubric_id")
    ):
        return False
    schema_version = value.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version < 1
    ):
        return False
    temperature = value.get("temperature")
    return (
        isinstance(temperature, (int, float))
        and not isinstance(temperature, bool)
        and math.isfinite(float(temperature))
    )


def _append_structural_mismatches(
    mismatches: list[str],
    side: str,
    record: Mapping[str, Any],
    examples: Sequence[Mapping[str, Any]],
) -> None:
    """Reject malformed contract/evidence structure before comparison logic."""
    for field in (
        "dataset_id",
        "dataset_version",
        "manifest_id",
        "manifest_version",
        "relevance_contract",
    ):
        if not _is_nonempty_string(record.get(field)):
            mismatches.append(f"{side}_{field}_invalid")

    dataset_role = record.get("dataset_role")
    if dataset_role not in {role.value for role in DatasetRole}:
        mismatches.append(f"{side}_dataset_role_invalid")

    primary_k = record.get("primary_k")
    if (
        not isinstance(primary_k, int)
        or isinstance(primary_k, bool)
        or primary_k != REQUIRED_PRIMARY_K
    ):
        mismatches.append(f"{side}_primary_k_invalid")

    retrieval_k_values = record.get("retrieval_k_values")
    if not _valid_positive_int_sequence(retrieval_k_values):
        mismatches.append(f"{side}_retrieval_k_values_invalid")
    elif (
        primary_k not in retrieval_k_values
        or not REQUIRED_RETRIEVAL_K_VALUES.issubset(set(retrieval_k_values))
    ):
        mismatches.append(f"{side}_retrieval_k_values_invalid")

    if record.get("score_semantics") != REQUIRED_SCORE_SEMANTICS:
        mismatches.append(f"{side}_score_semantics_invalid")

    eligible_count = record.get("eligible_count")
    if (
        not isinstance(eligible_count, int)
        or isinstance(eligible_count, bool)
        or eligible_count < 0
    ):
        mismatches.append(f"{side}_eligible_count_invalid")

    for count_field in ("invalid_count", "skipped_count", "judge_valid_count", "judge_invalid_count"):
        if count_field not in record:
            continue
        value = record.get(count_field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            mismatches.append(f"{side}_{count_field}_invalid")

    if record.get("state") == ResultState.PASS.value:
        invalid_count = record.get("invalid_count", 0)
        if (
            isinstance(invalid_count, int)
            and not isinstance(invalid_count, bool)
            and invalid_count > 0
        ):
            mismatches.append(f"{side}_invalid_evidence")
        judge_invalid_count = record.get("judge_invalid_count", 0)
        if (
            isinstance(judge_invalid_count, int)
            and not isinstance(judge_invalid_count, bool)
            and judge_invalid_count > 0
        ):
            mismatches.append(f"{side}_judge_invalid_evidence")

    mandatory_slices = record.get("mandatory_slices")
    # Mandatory slices follow the Task 2 contract: a unique non-empty string
    # list, possibly empty for non-benchmark dataset roles. Benchmark roles
    # must govern the frozen D5 slices.
    role_is_benchmark = record.get("dataset_role") == "benchmark"
    if not isinstance(mandatory_slices, (list, tuple)) or not all(
        _is_nonempty_string(item) for item in mandatory_slices
    ) or len(set(mandatory_slices)) != len(mandatory_slices):
        mismatches.append(f"{side}_mandatory_slices_invalid")
    elif role_is_benchmark and (
        not mandatory_slices
        or not BENCHMARK_REQUIRED_MANDATORY_SLICES.issubset(set(mandatory_slices))
    ):
        mismatches.append(f"{side}_mandatory_slices_missing")

    if not _valid_judge_config(record.get("judge_config")):
        mismatches.append(f"{side}_judge_config_invalid")

    answer_metrics = record.get("answer_metrics")
    if answer_metrics is not None and not isinstance(answer_metrics, Mapping):
        mismatches.append(f"{side}_answer_metrics_invalid")

    slice_metrics = record.get("slice_metrics")
    if not isinstance(slice_metrics, Mapping):
        mismatches.append(f"{side}_slice_metrics_invalid")

    countable_examples = True
    actual_eligible_count = 0
    for index, example in enumerate(examples):
        prefix = f"{side}_example_{index}"
        if not isinstance(example, Mapping):
            mismatches.append(f"{prefix}_invalid")
            countable_examples = False
            continue
        if not _is_nonempty_string(example.get("example_id")):
            mismatches.append(f"{prefix}_example_id_invalid")
        eligible = example.get("eligible")
        if not isinstance(eligible, bool):
            mismatches.append(f"{prefix}_eligible_invalid")
            countable_examples = False
        elif eligible:
            actual_eligible_count += 1
        expected_document_ids = example.get("expected_document_ids")
        if (
            not isinstance(expected_document_ids, (list, tuple))
            or not expected_document_ids
            or not all(_is_nonempty_string(item) for item in expected_document_ids)
        ):
            mismatches.append(f"{prefix}_expected_document_ids_invalid")

        expected_source_urls = example.get("expected_source_urls")
        if (
            not isinstance(expected_source_urls, (list, tuple))
            or not all(_is_nonempty_string(item) for item in expected_source_urls)
        ):
            mismatches.append(f"{prefix}_expected_source_urls_invalid")

        if "slices" in example:
            slices = example.get("slices")
            if (
                not isinstance(slices, (list, tuple))
                or not all(_is_nonempty_string(item) for item in slices)
                or len(set(slices)) != len(slices)
            ):
                mismatches.append(f"{prefix}_slices_invalid")

        metrics = example.get("metrics")
        if not isinstance(metrics, Mapping):
            mismatches.append(f"{prefix}_metrics_invalid")
        else:
            invalid_evidence_count = metrics.get("invalid_evidence_count")
            if invalid_evidence_count is not None:
                if (
                    isinstance(invalid_evidence_count, bool)
                    or not isinstance(invalid_evidence_count, int)
                    or invalid_evidence_count < 0
                ):
                    mismatches.append(f"{prefix}_invalid_evidence_count_invalid")
                elif eligible is True and invalid_evidence_count > 0:
                    mismatches.append(f"{prefix}_invalid_evidence")

    if (
        countable_examples
        and isinstance(eligible_count, int)
        and not isinstance(eligible_count, bool)
        and eligible_count >= 0
        and eligible_count != actual_eligible_count
    ):
        mismatches.append(f"{side}_eligible_count_mismatch")


def validate_comparison_contract(
    baseline_record: Mapping[str, Any],
    baseline_examples: Sequence[Mapping[str, Any]],
    candidate_record: Mapping[str, Any],
    candidate_examples: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Return the sorted list of comparison-contract mismatches.

    Judge identity is only required to match when either side carries judged
    metrics; candidate behavior differences (``runtime_adapter``, ``prompt_id``,
    ``config_id``) are never mismatches.
    """
    mismatches: list[str] = []

    if not isinstance(baseline_record, Mapping):
        mismatches.append("baseline_record_invalid")
    if not isinstance(candidate_record, Mapping):
        mismatches.append("candidate_record_invalid")
    if not _valid_example_sequence(baseline_examples):
        mismatches.append("baseline_examples_invalid")
    if not _valid_example_sequence(candidate_examples):
        mismatches.append("candidate_examples_invalid")
    if mismatches:
        return tuple(sorted(set(mismatches)))

    _append_structural_mismatches(
        mismatches, "baseline", baseline_record, baseline_examples
    )
    _append_structural_mismatches(
        mismatches, "candidate", candidate_record, candidate_examples
    )
    if mismatches:
        return tuple(sorted(set(mismatches)))

    for field in _REQUIRED_MATCH_FIELDS:
        if baseline_record.get(field) != candidate_record.get(field):
            mismatches.append(field)

    if _eligible_example_ids(baseline_examples) != _eligible_example_ids(
        candidate_examples
    ):
        mismatches.append("eligible_examples")

    # Duplicate eligible IDs invalidate the affected side independently; both
    # sides duplicating the same IDs is still invalid evidence.
    if _has_duplicate_eligible_ids(baseline_examples):
        mismatches.append("baseline_duplicate_example_ids")
    if _has_duplicate_eligible_ids(candidate_examples):
        mismatches.append("candidate_duplicate_example_ids")

    # The frozen mandatory-slice contract and its minimum are part of the
    # comparison contract. Structural shape and benchmark-role coverage are
    # checked per side in _append_structural_mismatches; here only the
    # cross-run agreement of the declared contract is enforced.
    if baseline_record.get("mandatory_slices") != candidate_record.get(
        "mandatory_slices"
    ):
        mismatches.append("mandatory_slices")
    if baseline_record.get("min_examples_per_slice") != candidate_record.get(
        "min_examples_per_slice"
    ):
        mismatches.append("min_examples_per_slice")
    for side, record in (
        ("baseline", baseline_record),
        ("candidate", candidate_record),
    ):
        minimum = record.get("min_examples_per_slice")
        if (
            not isinstance(minimum, int)
            or isinstance(minimum, bool)
            or minimum < 1
        ):
            mismatches.append(f"{side}_min_examples_per_slice_invalid")

    # The candidate must explicitly reference the exact baseline run it is
    # compared against; an unnamed or wrong baseline cannot anchor deltas.
    # Both sides need a real run identity: a baseline with an empty run_id
    # gives the comparison no governed anchor even when the reference matches.
    if not _is_nonempty_string_record_field(baseline_record, "run_id"):
        mismatches.append("baseline_run_id_invalid")
    if not _is_nonempty_string_record_field(candidate_record, "run_id"):
        mismatches.append("candidate_run_id_invalid")
    if candidate_record.get("baseline_run_id") != baseline_record.get("run_id"):
        mismatches.append("baseline_run_id")

    # A governed comparison requires both runs to be protocol-valid.
    if baseline_record.get("state") != ResultState.PASS.value:
        mismatches.append("baseline_state")
    if candidate_record.get("state") != ResultState.PASS.value:
        mismatches.append("candidate_state")

    baseline_judge = _judge_identity(baseline_record.get("judge_config"))
    candidate_judge = _judge_identity(candidate_record.get("judge_config"))
    if baseline_judge is not None or candidate_judge is not None:
        if baseline_judge != candidate_judge:
            mismatches.append("judge_config")
        for side, record, examples in (
            ("baseline", baseline_record, baseline_examples),
            ("candidate", candidate_record, candidate_examples),
        ):
            judge_invalid_count = record.get("judge_invalid_count")
            if judge_invalid_count is not None:
                if (
                    isinstance(judge_invalid_count, bool)
                    or not isinstance(judge_invalid_count, int)
                    or judge_invalid_count < 0
                ):
                    mismatches.append(f"{side}_judge_invalid_count_invalid")
                elif judge_invalid_count > 0:
                    mismatches.append(f"{side}_judge_invalid_evidence")
            for example in examples:
                if example.get("eligible") is not True:
                    continue
                example_id = example.get("example_id", "?")
                judge_valid = example.get("judge_valid")
                if judge_valid is False:
                    mismatches.append(f"{side}_judge_invalid:{example_id}")
                elif judge_valid is not True:
                    mismatches.append(f"{side}_judge_evidence_missing:{example_id}")
    else:
        # Judge-based scores without a frozen judge contract are not
        # governed evidence: answer metrics require judge identity on both
        # sides, so this comparison cannot anchor D5 answer gates.
        if (
            baseline_record.get("answer_metrics") is not None
            or candidate_record.get("answer_metrics") is not None
        ):
            mismatches.append("answer_metrics_requires_judge_config")

    # Slice membership is frozen evidence under the same dataset version:
    # relabeling an example between runs changes who governs its regression,
    # so both sides must agree on each eligible example's classification.
    baseline_slices = {
        str(record["example_id"]): _example_slice_identity(record)
        for record in baseline_examples
        if record.get("eligible")
    }
    baseline_expected_documents = {
        str(record["example_id"]): _string_sequence_identity(
            record.get("expected_document_ids")
        )
        for record in baseline_examples
        if record.get("eligible")
    }
    baseline_expected_sources = {
        str(record["example_id"]): _string_sequence_identity(
            record.get("expected_source_urls")
        )
        for record in baseline_examples
        if record.get("eligible")
    }
    for record in candidate_examples:
        if not record.get("eligible"):
            continue
        example_id = str(record["example_id"])
        if baseline_slices.get(example_id) != _example_slice_identity(record):
            mismatches.append(f"slice_membership:{example_id}")
        if baseline_expected_documents.get(example_id) != _string_sequence_identity(
            record.get("expected_document_ids")
        ):
            mismatches.append(f"expected_document_ids:{example_id}")
        if baseline_expected_sources.get(example_id) != _string_sequence_identity(
            record.get("expected_source_urls")
        ):
            mismatches.append(f"expected_source_urls:{example_id}")

    return tuple(sorted(set(mismatches)))


def _require_finite(value: Any, description: str) -> float:
    """Require a real JSON-style numeric value and reject NaN/inf evidence."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"Invalid governed value for {description}; expected a numeric score, "
            "not a coercible string or boolean."
        )
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(
            f"Non-finite (NaN/inf) governed value for {description}; "
            "non-finite evidence is invalid, never a favorable score."
        )
    return number


def _require_nonnegative_integer(value: Any, description: str) -> int:
    """Require a non-negative integer metadata count without coercion."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"Invalid {description}; expected a non-negative integer."
        )
    return value


def _require_unit_interval(value: Any, description: str) -> float:
    """Require a numeric aggregate metric in the closed [0,1] interval."""
    number = _require_finite(value, description)
    if not 0.0 <= number <= 1.0:
        raise ValueError(
            f"Governed value for {description} is outside the valid [0,1] range."
        )
    return number


def _require_retrieval_metric(value: Any, metric: str, description: str) -> float:
    """Validate one governed per-example retrieval metric under D5."""
    number = _require_finite(value, description)
    if not 0.0 <= number <= 1.0:
        raise ValueError(
            f"Governed metric '{metric}' for {description} is outside the "
            "valid [0,1] range."
        )
    if metric.startswith("hit@") and number not in (0.0, 1.0):
        raise ValueError(
            f"Governed metric '{metric}' for {description} must be binary 0 or 1."
        )
    return number


def _require_answer_score(value: Any, description: str) -> float:
    """Validate an answer-quality score/mean under the fixed D5 1..5 rubric."""
    number = _require_finite(value, description)
    if not 1.0 <= number <= 5.0:
        raise ValueError(
            f"Governed answer value for {description} is outside the valid 1..5 range."
        )
    return number


def _paired_delta(
    paired: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any]]],
    metric: str,
) -> float | None:
    """Mean per-example candidate minus baseline for one metric.

    Only validated eligible pairs are consumed; ineligible records never
    affect governed deltas. Non-finite values raise: they are invalid.
    """
    deltas: list[float] = []
    for baseline_record, candidate_record in paired.values():
        candidate_value = candidate_record.get("metrics", {}).get(metric)
        baseline_value = baseline_record.get("metrics", {}).get(metric)
        if candidate_value is None or baseline_value is None:
            continue
        deltas.append(
            _require_retrieval_metric(
                candidate_value, metric, f"candidate {metric}"
            )
            - _require_retrieval_metric(
                baseline_value, metric, f"baseline {metric}"
            )
        )
    if not deltas:
        return None
    return sum(deltas) / len(deltas)


def _bootstrap_interval(
    paired: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any]]],
    metric: str,
) -> dict[str, Any] | None:
    """Deterministic paired bootstrap percentile interval for one metric delta."""
    paired_values: list[tuple[float, float]] = []
    for baseline_record, candidate_record in paired.values():
        candidate_value = candidate_record.get("metrics", {}).get(metric)
        baseline_value = baseline_record.get("metrics", {}).get(metric)
        if candidate_value is None or baseline_value is None:
            continue
        paired_values.append(
            (
                _require_retrieval_metric(
                    baseline_value, metric, f"baseline {metric}"
                ),
                _require_retrieval_metric(
                    candidate_value, metric, f"candidate {metric}"
                ),
            )
        )

    if len(paired_values) < BOOTSTRAP_MIN_EXAMPLES:
        return None

    rng = random.Random(BOOTSTRAP_SEED)
    n = len(paired_values)
    deltas: list[float] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample_deltas = []
        for _ in range(n):
            baseline_value, candidate_value = paired_values[rng.randrange(n)]
            sample_deltas.append(candidate_value - baseline_value)
        deltas.append(sum(sample_deltas) / n)
    deltas.sort()

    def _percentile(p: float) -> float:
        index = min(int(p * (len(deltas) - 1) + 0.5), len(deltas) - 1)
        return deltas[index]

    return {
        "low": round(_percentile(0.025), 6),
        "high": round(_percentile(0.975), 6),
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED,
    }


def _build_uncertainty(
    paired: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any]]],
    candidate_record: Mapping[str, Any],
) -> dict[str, Any]:
    paired_n = len(paired)
    if paired_n < BOOTSTRAP_MIN_EXAMPLES:
        return {
            "uncertainty_status": "not_applicable_n_lt_30",
            "paired_n": paired_n,
            "confidence_intervals": {},
        }
    intervals: dict[str, Any] = {}
    for metric in (PRIMARY_METRIC, "mrr@5", "ndcg@5"):
        interval = _bootstrap_interval(paired, metric)
        if interval is not None:
            intervals[metric] = interval
    return {
        "uncertainty_status": "bootstrap_paired",
        "paired_n": paired_n,
        "confidence_intervals": intervals,
    }


def compare_runs(
    baseline_record: Mapping[str, Any],
    baseline_examples: Sequence[Mapping[str, Any]],
    candidate_record: Mapping[str, Any],
    candidate_examples: Sequence[Mapping[str, Any]],
) -> ComparisonResult:
    """Compare a candidate run against a baseline run under the D5 protocol."""
    mismatches = validate_comparison_contract(
        baseline_record, baseline_examples, candidate_record, candidate_examples
    )

    if mismatches:
        return ComparisonResult(
            state=ResultState.INVALID,
            paired_deltas={},
            slice_deltas={},
            failed_gates=(),
            candidate_changes={},
            uncertainty={},
            reason=f"Incompatible comparison contract: {', '.join(mismatches)}",
        )

    # Join eligible pairs once; every governed metric consumes only these.
    paired = _pair_metric_records(baseline_examples, candidate_examples)
    if isinstance(paired, str):
        return ComparisonResult(
            state=ResultState.INVALID,
            paired_deltas={},
            slice_deltas={},
            failed_gates=(),
            candidate_changes={},
            uncertainty={},
            reason=f"Missing required paired evidence: {paired}",
        )

    # A governed comparison requires at least one paired primary-metric
    # example; zero eligible pairs cannot support PASS.
    if not paired:
        return ComparisonResult(
            state=ResultState.INVALID,
            paired_deltas={},
            slice_deltas={},
            failed_gates=(),
            candidate_changes={},
            uncertainty={},
            reason="No eligible paired examples; empty evidence cannot PASS.",
        )

    paired_deltas: dict[str, float] = {}
    for metric in (PRIMARY_METRIC, "mrr@5", "ndcg@5"):
        try:
            delta = _paired_delta(paired, metric)
        except ValueError as error:
            return ComparisonResult(
                state=ResultState.INVALID,
                paired_deltas={},
                slice_deltas={},
                failed_gates=(),
                candidate_changes={},
                uncertainty={},
                reason=str(error),
            )
        if delta is not None:
            paired_deltas[metric] = round(delta, 6)

    slice_deltas: dict[str, dict[str, float]] = {}
    failed_gates: list[str] = []

    # Retrieval gates read the raw delta; only the persisted result value is
    # rounded. Rounding before gating would widen the tolerance to 5e-7.
    raw_deltas: dict[str, float] = {}
    for metric in (PRIMARY_METRIC, "mrr@5", "ndcg@5"):
        try:
            raw_deltas[metric] = _paired_delta(paired, metric)
        except ValueError:
            raw_deltas[metric] = None  # already handled above as INVALID

    for metric, max_decline in (
        (PRIMARY_METRIC, HIT5_MAX_DECLINE),
        ("mrr@5", MRR5_MAX_DECLINE),
        ("ndcg@5", NDCG5_MAX_DECLINE),
    ):
        delta = raw_deltas.get(metric)
        if delta is not None and -delta > max_decline + GATE_FLOAT_TOLERANCE:
            failed_gates.append(metric)

    # Mandatory-slice gates iterate the declared contract, not whichever
    # slices happen to have metrics; a missing slice is invalid evidence,
    # never a silently skipped gate.
    declared_slices = candidate_record.get("mandatory_slices") or ()
    candidate_slice_metrics = candidate_record.get("slice_metrics", {})
    baseline_slice_metrics = baseline_record.get("slice_metrics", {})
    missing_slices = [
        slice_name
        for slice_name in declared_slices
        if slice_name not in candidate_slice_metrics
        or slice_name not in baseline_slice_metrics
    ]
    if missing_slices:
        return ComparisonResult(
            state=ResultState.INVALID,
            paired_deltas=paired_deltas,
            slice_deltas=slice_deltas,
            failed_gates=(),
            candidate_changes={},
            uncertainty={},
            reason=(
                "Mandatory slices missing slice metrics: "
                + ", ".join(sorted(missing_slices))
            ),
        )

    # Slice gates derive from paired per-example evidence, so a stale or
    # wrong run-record slice aggregate can never hide a regression. The
    # run-record slice eligible_count must also be present for the minimum.
    paired_by_slice: dict[str, list[tuple[float, float]]] = {
        slice_name: [] for slice_name in declared_slices
    }
    for baseline_example, candidate_example in paired.values():
        # Both sides agree on this example's frozen classification (checked in
        # the contract), so either side's labels describe the same membership.
        example_slices = _example_slice_labels(candidate_example)
        for slice_name in example_slices:
            if slice_name in paired_by_slice:
                paired_by_slice[slice_name].append(
                    (
                            _require_retrieval_metric(
                                baseline_example.get("metrics", {}).get(PRIMARY_METRIC),
                                PRIMARY_METRIC,
                                f"baseline {PRIMARY_METRIC}",
                            ),
                            _require_retrieval_metric(
                                candidate_example.get("metrics", {}).get(PRIMARY_METRIC),
                                PRIMARY_METRIC,
                                f"candidate {PRIMARY_METRIC}",
                            ),
                    )
                )

    for slice_name in declared_slices:
        recorded_eligible = candidate_slice_metrics[slice_name].get(
            "eligible_count"
        )
        if recorded_eligible is None:
            return ComparisonResult(
                state=ResultState.INVALID,
                paired_deltas=paired_deltas,
                slice_deltas=slice_deltas,
                failed_gates=(),
                candidate_changes={},
                uncertainty={},
                reason=(
                    f"Mandatory slice '{slice_name}' is missing "
                    "eligible_count; the slice minimum cannot be applied "
                    "without it."
                ),
            )
        baseline_recorded = baseline_slice_metrics[slice_name].get(
            "eligible_count"
        )
        if baseline_recorded is None:
            return ComparisonResult(
                state=ResultState.INVALID,
                paired_deltas=paired_deltas,
                slice_deltas=slice_deltas,
                failed_gates=(),
                candidate_changes={},
                uncertainty={},
                reason=(
                    f"Mandatory slice '{slice_name}' is missing "
                    "eligible_count on the baseline side; the slice minimum "
                    "cannot be applied without it."
                ),
            )
        recorded_hit = candidate_slice_metrics[slice_name].get("hit@5")
        baseline_recorded_hit = baseline_slice_metrics[slice_name].get("hit@5")
        if recorded_hit is None or baseline_recorded_hit is None:
            return ComparisonResult(
                state=ResultState.INVALID,
                paired_deltas=paired_deltas,
                slice_deltas=slice_deltas,
                failed_gates=(),
                candidate_changes={},
                uncertainty={},
                reason=(
                    f"Mandatory slice '{slice_name}' is missing a required "
                    "hit@5 value in run-record slice metrics; missing "
                    "evidence is invalid, not a gate pass."
                ),
            )
        try:
            _require_nonnegative_integer(
                recorded_eligible,
                f"eligible_count for candidate mandatory slice '{slice_name}'",
            )
            _require_nonnegative_integer(
                baseline_recorded,
                f"eligible_count for baseline mandatory slice '{slice_name}'",
            )
            _require_unit_interval(
                recorded_hit, f"hit@5 for candidate mandatory slice '{slice_name}'"
            )
            _require_unit_interval(
                baseline_recorded_hit,
                f"hit@5 for baseline mandatory slice '{slice_name}'",
            )
        except ValueError as error:
            return ComparisonResult(
                state=ResultState.INVALID,
                paired_deltas=paired_deltas,
                slice_deltas=slice_deltas,
                failed_gates=(),
                candidate_changes={},
                uncertainty={},
                reason=str(error),
            )

        slice_pairs = paired_by_slice[slice_name]
        if not slice_pairs:
            return ComparisonResult(
                state=ResultState.INVALID,
                paired_deltas=paired_deltas,
                slice_deltas=slice_deltas,
                failed_gates=(),
                candidate_changes={},
                uncertainty={},
                reason=(
                    f"Mandatory slice '{slice_name}' has no paired examples; "
                    "aggregate slice metrics cannot be verified against "
                    "per-example evidence."
                ),
            )

        try:
            baseline_mean = sum(
                _require_retrieval_metric(
                    pair[0], PRIMARY_METRIC, f"baseline {PRIMARY_METRIC}"
                )
                for pair in slice_pairs
            ) / len(slice_pairs)
            candidate_mean = sum(
                _require_retrieval_metric(
                    pair[1], PRIMARY_METRIC, f"candidate {PRIMARY_METRIC}"
                )
                for pair in slice_pairs
            ) / len(slice_pairs)
        except ValueError as error:
            return ComparisonResult(
                state=ResultState.INVALID,
                paired_deltas=paired_deltas,
                slice_deltas=slice_deltas,
                failed_gates=(),
                candidate_changes={},
                uncertainty={},
                reason=str(error),
            )
        delta = candidate_mean - baseline_mean
        slice_deltas[slice_name] = {"hit@5": round(delta, 6)}
        if -delta > MANDATORY_SLICE_HIT5_MAX_DECLINE + GATE_FLOAT_TOLERANCE:
            failed_gates.append(f"mandatory_slice_hit@5:{slice_name}")

    # D5 answer-quality gates: mean >= 4.0 and decline <= 0.10 per dimension.
    # Judged runs are not retrieval-only: a frozen judge contract without
    # answer evidence on both sides is invalid. One-sided answer evidence is
    # likewise invalid rather than a silent gate skip.
    baseline_answer = baseline_record.get("answer_metrics")
    candidate_answer = candidate_record.get("answer_metrics")
    judged_run = (
        baseline_record.get("judge_config") is not None
        or candidate_record.get("judge_config") is not None
    )
    if judged_run and baseline_answer is None and candidate_answer is None:
        return ComparisonResult(
            state=ResultState.INVALID,
            paired_deltas=paired_deltas,
            slice_deltas=slice_deltas,
            failed_gates=(),
            candidate_changes={},
            uncertainty={},
            reason=(
                "Runs declare a judge contract but carry no answer-quality "
                "evidence on either side; required answer evidence is missing."
            ),
        )
    if (baseline_answer is None) != (candidate_answer is None):
        return ComparisonResult(
            state=ResultState.INVALID,
            paired_deltas=paired_deltas,
            slice_deltas=slice_deltas,
            failed_gates=(),
            candidate_changes={},
            uncertainty={},
            reason=(
                "Answer-quality evidence exists on only one side; "
                "groundedness/correctness gates cannot be governed."
            ),
        )
    if baseline_answer is not None and candidate_answer is not None:
        for dimension, minimum, max_decline in (
            ("mean_groundedness", GROUNDEDNESS_MINIMUM, GROUNDEDNESS_MAX_DECLINE),
            ("mean_correctness", CORRECTNESS_MINIMUM, CORRECTNESS_MAX_DECLINE),
        ):
            candidate_mean = candidate_answer.get(dimension)
            baseline_mean = baseline_answer.get(dimension)
            if candidate_mean is None or baseline_mean is None:
                return ComparisonResult(
                    state=ResultState.INVALID,
                    paired_deltas=paired_deltas,
                    slice_deltas=slice_deltas,
                    failed_gates=(),
                    candidate_changes={},
                    uncertainty={},
                    reason=(
                        f"Required answer dimension '{dimension}' is missing "
                        "from one side; missing evidence is invalid."
                    ),
                )
            try:
                candidate_number = _require_answer_score(candidate_mean, dimension)
                baseline_number = _require_answer_score(baseline_mean, dimension)
            except ValueError as error:
                return ComparisonResult(
                    state=ResultState.INVALID,
                    paired_deltas=paired_deltas,
                    slice_deltas=slice_deltas,
                    failed_gates=(),
                    candidate_changes={},
                    uncertainty={},
                    reason=str(error),
                )
            if candidate_number < minimum:
                failed_gates.append(f"{dimension}_minimum")
            decline = baseline_number - candidate_number
            if decline > max_decline + GATE_FLOAT_TOLERANCE:
                failed_gates.append(f"{dimension}_decline")

    candidate_changes = {
        field: candidate_record.get(field)
        for field in _CANDIDATE_CHANGE_FIELDS
        if candidate_record.get(field) != baseline_record.get(field)
    }

    uncertainty = _build_uncertainty(paired, candidate_record)

    # D5 state resolution: invalid evidence never becomes favorable.
    if failed_gates:
        state = ResultState.FAIL
        reason = f"Gate regression on valid evidence: {', '.join(failed_gates)}"
    else:
        # The manifest minimum applies to mandatory slices only; extra
        # diagnostic slices below the minimum do not block a decision. The
        # count comes from paired evidence, not the recorded claim, so a
        # stale eligible_count cannot bypass INCONCLUSIVE.
        below_minimum = []
        min_required = candidate_record.get("min_examples_per_slice")
        if min_required is not None:
            for slice_name in declared_slices:
                if len(paired_by_slice[slice_name]) < min_required:
                    below_minimum.append(slice_name)
        if below_minimum:
            state = ResultState.INCONCLUSIVE
            reason = (
                "Eligible mandatory slices below manifest minimum: "
                + ", ".join(sorted(below_minimum))
            )
        else:
            state = ResultState.PASS
            reason = "All applicable D5 gates pass on valid evidence."

    return ComparisonResult(
        state=state,
        paired_deltas=paired_deltas,
        slice_deltas=slice_deltas,
        failed_gates=tuple(failed_gates),
        candidate_changes=candidate_changes,
        uncertainty=uncertainty,
        reason=reason,
    )
