"""Deterministic artifact serialization for R2 evaluation runs.

Writes ``run.json`` and ``examples.jsonl`` with stable, reviewable identity:
sorted JSON keys, UTF-8, trailing newline. Secrets are rejected before any
write; retrieved excerpts are bounded. Evaluation-owned module: online runtime
must not import this.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.rag.evaluation.dataset import (
    BENCHMARK_REQUIRED_MANDATORY_SLICES,
    REQUIRED_PRIMARY_K,
    REQUIRED_RETRIEVAL_K_VALUES,
    REQUIRED_SCORE_SEMANTICS,
)
from backend.rag.evaluation.models import DatasetRole, ResultState

RUN_ARTIFACT_NAME = "run.json"
EXAMPLES_ARTIFACT_NAME = "examples.jsonl"

MAX_EVIDENCE_EXCERPT_CHARS = 500

# Governed run-record identity required by the D5 run/report contract
# (plan Task 3 Step 4). Artifacts without these fields are not reviewable.
# Comparison-critical fields (mandatory_slices, relevance_contract, states,
# deltas, uncertainty, gates) anchor later D5 compatibility/gate checks.
REQUIRED_RUN_RECORD_FIELDS: tuple[str, ...] = (
    "run_id",
    "started_at",
    "completed_at",
    "state",
    "dataset_id",
    "dataset_version",
    "dataset_role",
    "manifest_id",
    "manifest_version",
    "relevance_contract",
    "eligible_count",
    "invalid_count",
    "skipped_count",
    "code_revision",
    "dirty_working_tree",
    "config_id",
    "config_version",
    "runtime_adapter",
    "collection_name",
    "embedding_model",
    "retrieval_k_values",
    "primary_k",
    "score_semantics",
    "generation_context_top_k",
    "generation_model",
    "prompt_id",
    "temperature",
    "max_tokens",
    "judge_config",
    "judge_valid_count",
    "judge_invalid_count",
    "baseline_run_id",
    "mandatory_slices",
    "min_examples_per_slice",
    "aggregate_metrics",
    "slice_metrics",
    "paired_deltas",
    "uncertainty",
    "gate_decisions",
    "failed_gates",
    "timing",
    "errors",
    "failure_counts",
)

REQUIRED_EXAMPLE_RECORD_FIELDS: tuple[str, ...] = (
    "example_id",
    "eligible",
    "slices",
    "expected_document_ids",
    "expected_source_urls",
    "ranked_evidence_ids",
    "ranked_evidence",
    "context_evidence_ids",
    "answer",
    "reference_answer",
    "citations",
    "metrics",
    "judge_valid",
    "failure_labels",
    "timing_seconds",
    "errors",
)

_SECRET_MARKER_TOKENS = ("ghp_", "github_pat_", "sk-", "Bearer ")


@dataclass(frozen=True)
class RunArtifact:
    """Reloaded run artifacts for comparison and review."""

    run_record: dict[str, Any]
    example_records: tuple[dict[str, Any], ...]
    run_dir: Optional[Path] = None



def _configured_secret_values() -> list[str]:
    """Collect real secret values from the process environment."""
    values: list[str] = []
    for name in _SECRET_ENV_NAMES:
        value = os.getenv(name, "")
        if value and len(value) >= 8:
            values.append(value)
    return values


def _assert_no_secrets(value: Any) -> None:
    """Reject values containing configured credentials or secret markers."""
    if isinstance(value, str):
        for secret in _configured_secret_values():
            if secret and secret in value:
                raise ValueError(
                    "Refusing to persist artifacts containing a configured "
                    "secret value."
                )
        for marker in _SECRET_MARKER_TOKENS:
            if marker in value:
                raise ValueError(
                    "Refusing to persist artifacts containing a credential "
                    f"marker ('{marker}')."
                )
    elif isinstance(value, Mapping):
        for item in value.values():
            _assert_no_secrets(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_secrets(item)


def _bound_excerpts(value: Any) -> Any:
    """Recursively bound evidence text excerpts to the persisted maximum."""
    if isinstance(value, Mapping):
        bounded: dict[str, Any] = {}
        for key, item in value.items():
            if key == "text" and isinstance(item, str):
                bounded[key] = item[:MAX_EVIDENCE_EXCERPT_CHARS]
            else:
                bounded[key] = _bound_excerpts(item)
        return bounded
    if isinstance(value, list):
        return [_bound_excerpts(item) for item in value]
    if isinstance(value, tuple):
        return [_bound_excerpts(item) for item in value]
    return value


def _assert_finite_numbers(value: Any) -> None:
    """Reject non-finite numeric values (NaN/inf) before persistence.

    Non-finite evidence is invalid evidence; it must never serialize into an
    artifact or silently flow into a later comparison.
    """
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(
            "Refusing to persist artifacts containing non-finite numeric "
            "values (NaN/inf); non-finite evidence is invalid evidence."
        )
    if isinstance(value, Mapping):
        for item in value.values():
            _assert_finite_numbers(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_finite_numbers(item)


def _require_number_in_range(
    value: Any,
    *,
    field: str,
    minimum: float,
    maximum: float,
    binary: bool = False,
    integer: bool = False,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"'{field}' must be numeric, not a coercible string or boolean."
        )
    if integer and not isinstance(value, int):
        raise ValueError(f"'{field}' must be an integer.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"'{field}' must be finite; NaN/inf are invalid evidence.")
    if not minimum <= number <= maximum:
        raise ValueError(
            f"'{field}' must be within the valid range [{minimum:g},{maximum:g}]."
        )
    if binary and number not in (0.0, 1.0):
        raise ValueError(f"'{field}' must be binary 0 or 1.")


def _metric_cutoff(name: str) -> int:
    """Parse K from a governed metric name such as ``unique_docs@5``."""
    try:
        raw_k = name.rsplit("@", 1)[1]
        k = int(raw_k)
    except (IndexError, ValueError) as error:
        raise ValueError(f"Metric '{name}' must declare an integer @K cutoff.") from error
    if k < 0:
        raise ValueError(f"Metric '{name}' must declare a non-negative @K cutoff.")
    return k


def _assert_metric_mapping(metrics: Any, *, per_example: bool) -> None:
    if not isinstance(metrics, Mapping):
        raise ValueError("'metrics' must be an object.")
    for name, value in metrics.items():
        if value is None:
            continue
        if name.startswith("hit@"):
            _require_number_in_range(
                value,
                field=name,
                minimum=0.0,
                maximum=1.0,
                binary=per_example,
            )
        elif name.startswith(("mrr@", "ndcg@", "precision@")):
            _require_number_in_range(
                value, field=name, minimum=0.0, maximum=1.0
            )
        elif name.startswith("source_url_hit@"):
            _require_number_in_range(
                value,
                field=name,
                minimum=0.0,
                maximum=1.0,
                binary=per_example,
            )
        elif name.startswith(("relevant_chunks@", "unique_docs@")):
            k = _metric_cutoff(name)
            _require_number_in_range(
                value,
                field=name,
                minimum=0.0,
                maximum=float(k),
                integer=per_example,
            )


def _assert_answer_metrics(answer_metrics: Any) -> None:
    if answer_metrics is None:
        return
    if not isinstance(answer_metrics, Mapping):
        raise ValueError("'answer_metrics' must be an object when present.")
    for name, value in answer_metrics.items():
        if value is None:
            continue
        if name.startswith("mean_"):
            _require_number_in_range(
                value, field=name, minimum=1.0, maximum=5.0
            )


def _require_nonempty_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{field}' must be a non-empty string.")


def _require_nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"'{field}' must be a non-negative integer.")
    return value


def _assert_judge_config(judge_config: Any) -> None:
    if judge_config is None:
        return
    if not isinstance(judge_config, Mapping):
        raise ValueError("'judge_config' must be a JSON object when present.")
    for field in ("model", "prompt_id", "rubric_id"):
        _require_nonempty_string(judge_config.get(field), f"judge_config.{field}")
    schema_version = judge_config.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version < 1
    ):
        raise ValueError("'judge_config.schema_version' must be an integer at least 1.")
    temperature = judge_config.get("temperature")
    if (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not math.isfinite(float(temperature))
    ):
        raise ValueError("'judge_config.temperature' must be a finite number.")


def _assert_run_record_schema(run_record: Mapping[str, Any]) -> None:
    """Reject run records missing governed identity fields.

    Fields whose legitimate value is ``None`` (``judge_config`` and
    ``baseline_run_id`` for baseline-only retrieval runs) require presence,
    not non-None values.
    """
    if not isinstance(run_record, Mapping):
        raise ValueError("Run record must be a JSON object.")
    optional_none_fields = {"judge_config", "baseline_run_id"}
    missing = [
        field
        for field in REQUIRED_RUN_RECORD_FIELDS
        if field not in run_record
        or (run_record[field] is None and field not in optional_none_fields)
    ]
    if missing:
        raise ValueError(
            "Run record is missing required governed fields: "
            + ", ".join(sorted(missing))
        )

    for field in (
        "run_id",
        "dataset_id",
        "dataset_version",
        "dataset_role",
        "manifest_id",
        "manifest_version",
        "relevance_contract",
    ):
        _require_nonempty_string(run_record[field], field)

    dataset_role = run_record["dataset_role"]
    allowed_dataset_roles = {role.value for role in DatasetRole}
    if dataset_role not in allowed_dataset_roles:
        raise ValueError(
            "'dataset_role' must be one of the governed dataset roles: "
            + ", ".join(sorted(allowed_dataset_roles))
            + "."
        )

    state = run_record["state"]
    allowed_states = {state.value for state in ResultState}
    if state not in allowed_states:
        raise ValueError(
            "'state' must be one of the governed result states: "
            + ", ".join(sorted(allowed_states))
            + "."
        )

    for count_field in (
        "eligible_count",
        "invalid_count",
        "skipped_count",
        "judge_valid_count",
        "judge_invalid_count",
    ):
        _require_nonnegative_integer(run_record[count_field], count_field)

    if state == ResultState.PASS.value and run_record["invalid_count"] > 0:
        raise ValueError(
            "A PASS run cannot report invalid examples; invalid required evidence "
            "must not become favorable promotion evidence."
        )
    if state == ResultState.PASS.value and run_record["judge_invalid_count"] > 0:
        raise ValueError(
            "A PASS run cannot report judge-invalid evidence; required judge "
            "failure must produce INVALID rather than favorable evidence."
        )

    mandatory_slices = run_record["mandatory_slices"]
    # Mandatory slices follow the Task 2 dataset contract: a list of unique
    # non-empty strings, possibly empty for non-benchmark roles.
    if (
        not isinstance(mandatory_slices, (list, tuple))
        or not all(isinstance(item, str) and item.strip() for item in mandatory_slices)
        or len(set(mandatory_slices)) != len(mandatory_slices)
    ):
        raise ValueError(
            "'mandatory_slices' must be a sequence of unique non-empty strings."
        )
    if dataset_role == "benchmark":
        # The frozen benchmark v0.1 contract: every run on a benchmark-role
        # dataset must govern all five D5 mandatory slices. Non-benchmark
        # roles follow the Task 2 contract and may declare none.
        missing_slices = sorted(
            BENCHMARK_REQUIRED_MANDATORY_SLICES - set(mandatory_slices)
        )
        if missing_slices:
            raise ValueError(
                "Benchmark-role run records must govern all frozen v0.1 "
                f"mandatory slices; missing {missing_slices}."
            )

    primary_k = run_record["primary_k"]
    if (
        not isinstance(primary_k, int)
        or isinstance(primary_k, bool)
        or primary_k != REQUIRED_PRIMARY_K
    ):
        raise ValueError(
            f"'primary_k' must be {REQUIRED_PRIMARY_K} under the frozen D5 contract."
        )

    retrieval_k_values = run_record["retrieval_k_values"]
    if (
        not isinstance(retrieval_k_values, (list, tuple))
        or not retrieval_k_values
        or not all(
            isinstance(item, int) and not isinstance(item, bool) and item > 0
            for item in retrieval_k_values
        )
        or primary_k not in retrieval_k_values
        or not REQUIRED_RETRIEVAL_K_VALUES.issubset(set(retrieval_k_values))
    ):
        raise ValueError(
            "'retrieval_k_values' must be a non-empty sequence of positive integers "
            "containing primary_k and all frozen D5 K values "
            f"{sorted(REQUIRED_RETRIEVAL_K_VALUES)}."
        )

    score_semantics = run_record["score_semantics"]
    if score_semantics != REQUIRED_SCORE_SEMANTICS:
        raise ValueError(
            f"'score_semantics' must be '{REQUIRED_SCORE_SEMANTICS}' under the "
            "frozen v0.1 retrieval contract."
        )

    mandatory_slices = run_record["mandatory_slices"]

    minimum = run_record["min_examples_per_slice"]
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
        raise ValueError("'min_examples_per_slice' must be an integer at least 1.")

    aggregate_metrics = run_record.get("aggregate_metrics")
    if aggregate_metrics is not None:
        _assert_metric_mapping(aggregate_metrics, per_example=False)

    slice_metrics = run_record.get("slice_metrics")
    if not isinstance(slice_metrics, Mapping):
        raise ValueError("'slice_metrics' must be an object.")
    for slice_name, metrics in slice_metrics.items():
        if not isinstance(metrics, Mapping):
            raise ValueError(f"Slice metrics for '{slice_name}' must be an object.")
        eligible_count = metrics.get("eligible_count")
        if eligible_count is not None:
            if (
                isinstance(eligible_count, bool)
                or not isinstance(eligible_count, int)
                or eligible_count < 0
            ):
                raise ValueError(
                    f"Slice '{slice_name}' eligible_count must be a non-negative integer."
                )
        _assert_metric_mapping(metrics, per_example=False)

    _assert_answer_metrics(run_record.get("answer_metrics"))
    _assert_judge_config(run_record.get("judge_config"))

    # Answer scores are judge-based evidence: a run record carrying them
    # without a valid frozen judge contract cannot anchor the D5
    # groundedness/correctness gates, so it is rejected rather than becoming
    # valid promotion evidence.
    if run_record.get("answer_metrics") is not None and not _has_valid_judge_config(
        run_record.get("judge_config")
    ):
        raise ValueError(
            "'answer_metrics' requires a valid 'judge_config'; judge-based "
            "scores without a frozen judge contract are not governed evidence."
        )


def _has_valid_judge_config(judge_config: Any) -> bool:
    """Whether the judge contract carries a complete frozen identity."""
    if not isinstance(judge_config, Mapping):
        return False
    try:
        for field in ("model", "prompt_id", "rubric_id"):
            _require_nonempty_string(judge_config.get(field), f"judge_config.{field}")
    except ValueError:
        return False
    schema_version = judge_config.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version < 1
    ):
        return False
    temperature = judge_config.get("temperature")
    return (
        isinstance(temperature, (int, float))
        and not isinstance(temperature, bool)
        and math.isfinite(float(temperature))
    )


_SECRET_ENV_NAMES = ("GITHUB_TOKEN",)


def _assert_example_record_schema(record: Mapping[str, Any]) -> None:
    """Reject example records missing governed fields.

    ``judge_valid`` is legitimately ``None`` for retrieval-only runs, so its
    presence (not non-None value) is what the schema requires. Eligible
    records must also carry at least one reviewable classification
    (``slices`` or ``category``) for mandatory-slice reporting.
    """
    if not isinstance(record, Mapping):
        raise ValueError("Example record must be a JSON object.")
    missing = [
        field
        for field in REQUIRED_EXAMPLE_RECORD_FIELDS
        if field not in record
    ]
    if missing:
        raise ValueError(
            f"Example record '{record.get('example_id', '?')}' is missing "
            "required governed fields: " + ", ".join(sorted(missing))
        )
    if not isinstance(record["eligible"], bool):
        raise ValueError(
            f"Example record '{record.get('example_id', '?')}' field 'eligible' must be boolean."
        )

    expected_document_ids = record["expected_document_ids"]
    if (
        not isinstance(expected_document_ids, (list, tuple))
        or not expected_document_ids
        or not all(
            isinstance(item, str) and item.strip() for item in expected_document_ids
        )
    ):
        raise ValueError(
            f"Example record '{record.get('example_id', '?')}' field "
            "'expected_document_ids' must be a non-empty list of non-empty strings."
        )

    expected_source_urls = record["expected_source_urls"]
    if (
        not isinstance(expected_source_urls, (list, tuple))
        or not all(
            isinstance(item, str) and item.strip() for item in expected_source_urls
        )
    ):
        raise ValueError(
            f"Example record '{record.get('example_id', '?')}' field "
            "'expected_source_urls' must be a list of non-empty strings."
        )

    if record.get("eligible"):
        has_classification = bool(
            record.get("slices")
        ) or bool(
            record.get("category")
        )
        if not has_classification:
            raise ValueError(
                f"Eligible example record '{record.get('example_id', '?')}' "
                "must declare at least one reviewable classification: "
                "'slices' or 'category'."
            )
    record_slices = record.get("slices")
    if record_slices is not None:
        if (
            not isinstance(record_slices, (list, tuple))
            or not all(isinstance(item, str) and item.strip() for item in record_slices)
            or len(set(record_slices)) != len(record_slices)
        ):
            raise ValueError(
                f"Example record '{record.get('example_id', '?')}' field "
                "'slices' must be a list of unique non-empty strings when present."
            )
    judge_valid = record.get("judge_valid")
    if judge_valid is not None and not isinstance(judge_valid, bool):
        raise ValueError(
            f"Example record '{record.get('example_id', '?')}' field "
            "'judge_valid' must be boolean or null."
        )
    invalid_evidence_count = record.get("metrics", {}).get("invalid_evidence_count")
    if invalid_evidence_count is not None:
        _require_nonnegative_integer(
            invalid_evidence_count,
            f"example[{record.get('example_id', '?')}].metrics.invalid_evidence_count",
        )
    ranked_evidence = record.get("ranked_evidence")

    if not isinstance(ranked_evidence, (list, tuple)):
        raise ValueError(
            f"Example record '{record.get('example_id', '?')}' field "
            "'ranked_evidence' must be a list."
        )
    reference_answer = record.get("reference_answer")
    if reference_answer is not None and not isinstance(reference_answer, str):
        raise ValueError(
            f"Example record '{record.get('example_id', '?')}' field "
            "'reference_answer' must be a string or null."
        )
    _assert_metric_mapping(record["metrics"], per_example=True)



def _assert_run_evidence_consistency(
    run_record: Mapping[str, Any],
    example_records: Sequence[Mapping[str, Any]],
) -> None:
    """Require run-level counts/aggregates to agree with persisted examples."""
    actual_eligible_count = sum(
        1 for record in example_records if record.get("eligible") is True
    )
    if run_record["eligible_count"] != actual_eligible_count:
        raise ValueError(
            "'eligible_count' does not match eligible example evidence: "
            f"recorded {run_record['eligible_count']}, actual {actual_eligible_count}."
        )

    actual_judge_valid_count = sum(
        1 for record in example_records if record.get("judge_valid") is True
    )
    actual_judge_invalid_count = sum(
        1 for record in example_records if record.get("judge_valid") is False
    )
    has_explicit_judge_evidence = actual_judge_valid_count + actual_judge_invalid_count > 0
    if has_explicit_judge_evidence or run_record.get("judge_config") is not None:
        if run_record["judge_valid_count"] != actual_judge_valid_count:
            raise ValueError(
                "'judge_valid_count' does not match per-example judge evidence: "
                f"recorded {run_record['judge_valid_count']}, "
                f"actual {actual_judge_valid_count}."
            )
        if run_record["judge_invalid_count"] != actual_judge_invalid_count:
            raise ValueError(
                "'judge_invalid_count' does not match per-example judge evidence: "
                f"recorded {run_record['judge_invalid_count']}, "
                f"actual {actual_judge_invalid_count}."
            )

    eligible_records = [
        record for record in example_records if record.get("eligible") is True
    ]
    if (
        run_record.get("state") == ResultState.PASS.value
        and run_record.get("answer_metrics") is not None
    ):
        missing_judge_evidence = [
            str(record.get("example_id", "?"))
            for record in eligible_records
            if record.get("judge_valid") is not True
        ]
        if missing_judge_evidence:
            raise ValueError(
                "A PASS judged run requires valid per-example judge evidence "
                "for every eligible example; missing judge evidence for: "
                + ", ".join(sorted(missing_judge_evidence))
                + "."
            )

    if run_record.get("state") == ResultState.PASS.value:
        invalid_retrieval_examples = [
            str(record.get("example_id", "?"))
            for record in eligible_records
            if record.get("metrics", {}).get("invalid_evidence_count", 0) > 0
        ]
        if invalid_retrieval_examples:
            raise ValueError(
                "A PASS run cannot contain invalid retrieval evidence; "
                "invalid_evidence_count is positive for: "
                + ", ".join(sorted(invalid_retrieval_examples))
                + "."
            )

    aggregate_metrics = run_record.get("aggregate_metrics")
    if not isinstance(aggregate_metrics, Mapping):
        return

    governed_prefixes = (
        "hit@",
        "mrr@",
        "ndcg@",
        "precision@",
        "relevant_chunks@",
        "unique_docs@",
        "source_url_hit@",
    )
    for metric_name, recorded_value in aggregate_metrics.items():
        if metric_name == "example_count":
            expected_value: Any = len(eligible_records)
        elif metric_name == "invalid_evidence_count":
            expected_value = sum(
                record.get("metrics", {}).get("invalid_evidence_count", 0)
                for record in eligible_records
            )
        elif metric_name.startswith(governed_prefixes):
            values = [
                record.get("metrics", {}).get(metric_name)
                for record in eligible_records
                if record.get("metrics", {}).get(metric_name) is not None
            ]
            expected_value = sum(values) / len(values) if values else None
        else:
            continue

        if recorded_value is None and expected_value is None:
            continue
        if recorded_value is None or expected_value is None:
            raise ValueError(
                f"Aggregate metric '{metric_name}' does not match per-example "
                "evidence."
            )
        if (
            isinstance(recorded_value, bool)
            or not isinstance(recorded_value, (int, float))
            or isinstance(expected_value, bool)
            or not isinstance(expected_value, (int, float))
            or not math.isclose(
                float(recorded_value), float(expected_value), rel_tol=0.0, abs_tol=1e-9
            )
        ):
            raise ValueError(
                f"Aggregate metric '{metric_name}' does not match per-example "
                f"evidence: recorded {recorded_value}, actual {expected_value}."
            )


def _serialize_json(value: Any) -> str:
    """Deterministic JSON text: sorted keys, UTF-8-safe, trailing newline.

    ``allow_nan=False`` is a final guard: non-finite values must have been
    rejected before serialization.
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"


def write_run_artifacts(
    output_dir: Path,
    run_record: Mapping[str, Any],
    example_records: Sequence[Mapping[str, Any]],
) -> None:
    """Persist one run's summary and per-example records deterministically.

    Raises:
        ValueError: When any value contains a configured secret value or a
            credential marker, before any file is written.
    """
    run_payload = dict(run_record)
    examples_payload = [dict(record) for record in example_records]

    _assert_run_record_schema(run_payload)
    for record in examples_payload:
        _assert_example_record_schema(record)
    _assert_run_evidence_consistency(run_payload, examples_payload)

    _assert_no_secrets(run_payload)
    _assert_no_secrets(examples_payload)
    _assert_finite_numbers(run_payload)
    _assert_finite_numbers(examples_payload)

    examples_payload = [_bound_excerpts(record) for record in examples_payload]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_path = output_dir / RUN_ARTIFACT_NAME
    examples_path = output_dir / EXAMPLES_ARTIFACT_NAME

    run_path.write_text(_serialize_json(run_payload), encoding="utf-8")
    examples_path.write_text(
        "".join(_serialize_json(record) for record in examples_payload),
        encoding="utf-8",
    )


def load_run_artifact(run_dir: Path) -> RunArtifact:
    """Reload persisted run artifacts for comparison or review.

    Raises:
        ValueError: When required artifact files are missing or malformed.
    """
    run_dir = Path(run_dir)
    run_path = run_dir / RUN_ARTIFACT_NAME
    if not run_path.is_file() and run_dir.is_dir():
        children_with_run = [
            sub
            for sub in run_dir.iterdir()
            if sub.is_dir() and (sub / RUN_ARTIFACT_NAME).is_file()
        ]
        if len(children_with_run) == 1:
            run_dir = children_with_run[0]
            run_path = run_dir / RUN_ARTIFACT_NAME

    examples_path = run_dir / EXAMPLES_ARTIFACT_NAME

    if not run_path.is_file():
        raise ValueError(f"Missing run artifact file: {run_path}")

    if not examples_path.is_file():
        raise ValueError(f"Missing run examples artifact file: {examples_path}")

    try:
        run_record = json.loads(run_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in run artifact: {run_path}") from error

    example_records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        examples_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            parsed_record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Invalid JSON on run example line {line_number}: {examples_path}"
            ) from error
        if not isinstance(parsed_record, Mapping):
            raise ValueError(
                f"Run example line {line_number} must contain a JSON object: "
                f"{examples_path}"
            )
        example_records.append(dict(parsed_record))

    try:
        _assert_run_record_schema(run_record)
        for record in example_records:
            _assert_example_record_schema(record)
        _assert_run_evidence_consistency(run_record, example_records)
        _assert_finite_numbers(run_record)
        _assert_finite_numbers(example_records)
    except ValueError as error:
        raise ValueError(f"Persisted run artifact fails schema review: {error}") from error

    return RunArtifact(
        run_record=run_record,
        example_records=tuple(example_records),
        run_dir=run_dir,
    )
