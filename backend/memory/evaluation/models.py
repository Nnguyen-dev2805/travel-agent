"""Memory shadow evaluation report contracts for milestone R5.

These value objects carry counts, metric values, hard-gate evidence, and the
final result state defined by the memory evaluation protocol. Every field is
a JSON primitive, a tuple of primitives, or a nested contract, so a report
serializes without transformation. No field carries message content,
candidate text, or evidence summaries: per-example evidence is limited to
stable identifiers, slices, counts, and controlled failure labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Tuple


class MemoryEvaluationResult(str, Enum):
    """Final result-state vocabulary from the memory evaluation protocol."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    INVALID = "INVALID"


@dataclass(frozen=True)
class MetricScore:
    """One aggregate metric with its exact numerator and denominator."""

    name: str
    value: float | None
    numerator: int
    denominator: int
    threshold: str


@dataclass(frozen=True)
class SliceScore:
    """Eligible counts and precision for one mandatory slice."""

    slice: str
    eligible_examples: int
    actual: int
    expected: int
    matched: int
    precision: float | None


@dataclass(frozen=True)
class HardGateScore:
    """One zero-tolerance safety gate with its confirmed event count."""

    gate: str
    events: int
    applicable: bool
    passed: bool


@dataclass(frozen=True)
class ExampleScore:
    """Per-example evidence without any content payload."""

    example_id: str
    slice: str
    expected_total: int
    actual_total: int
    matched: int
    failures: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MemoryEvaluationReport:
    """Deterministic R5 shadow evaluation outcome.

    Generated identifiers (`report_id`, run and candidate ids inside the
    evaluation database) are unique per execution; every metric value,
    gate count, and result state is a pure function of the fixture.
    """

    report_id: str
    dataset_id: str
    dataset_version: str
    dataset_role: str
    extractor_id: str
    policy_id: str
    eligible_examples: int
    invalid_examples: int
    skipped_examples: int
    extraction_precision: MetricScore
    extraction_recall: MetricScore
    scope_accuracy: MetricScore
    slices: Tuple[SliceScore, ...] = field(default_factory=tuple)
    hard_gates: Tuple[HardGateScore, ...] = field(default_factory=tuple)
    examples: Tuple[ExampleScore, ...] = field(default_factory=tuple)
    result_state: MemoryEvaluationResult = MemoryEvaluationResult.INVALID
    notes: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MemoryRetrievalReport:
    """Deterministic R6 retrieval evaluation outcome.

    Answer-quality fields stay valueless without a provider-backed judge;
    their thresholds read as not-applicable notes rather than gates. Like
    the R5 report, generated identifiers are unique per execution while
    every metric value, gate count, and result state is a pure function of
    the suite.
    """

    report_id: str
    dataset_id: str
    dataset_version: str
    dataset_role: str
    extractor_id: str
    policy_id: str
    eligible_examples: int
    invalid_examples: int
    skipped_examples: int
    promotion_precision: MetricScore
    scope_accuracy: MetricScore
    hit_at_5: MetricScore
    irrelevant_rate: MetricScore
    personalization_win_rate: MetricScore
    constraint_delta: MetricScore
    slices: Tuple[SliceScore, ...] = field(default_factory=tuple)
    hard_gates: Tuple[HardGateScore, ...] = field(default_factory=tuple)
    examples: Tuple[ExampleScore, ...] = field(default_factory=tuple)
    disabled_run_id: str = ""
    enabled_trace_ids: Tuple[str, ...] = field(default_factory=tuple)
    result_state: MemoryEvaluationResult = MemoryEvaluationResult.INVALID
    notes: Tuple[str, ...] = field(default_factory=tuple)


def retrieval_report_to_dict(report: MemoryRetrievalReport) -> Dict[str, Any]:
    """Render an R6 report as JSON-serializable primitives."""
    return {
        "report_id": report.report_id,
        "dataset": {
            "dataset_id": report.dataset_id,
            "dataset_version": report.dataset_version,
            "dataset_role": report.dataset_role,
        },
        "code_identity": {
            "extractor_id": report.extractor_id,
            "policy_id": report.policy_id,
        },
        "counts": {
            "eligible_examples": report.eligible_examples,
            "invalid_examples": report.invalid_examples,
            "skipped_examples": report.skipped_examples,
        },
        "metrics": {
            "promotion_precision": _metric_to_dict(report.promotion_precision),
            "scope_accuracy": _metric_to_dict(report.scope_accuracy),
            "hit_at_5": _metric_to_dict(report.hit_at_5),
            "irrelevant_rate": _metric_to_dict(report.irrelevant_rate),
            "personalization_win_rate": _metric_to_dict(
                report.personalization_win_rate
            ),
            "constraint_delta": _metric_to_dict(report.constraint_delta),
        },
        "mandatory_slices": [
            {
                "slice": item.slice,
                "eligible_examples": item.eligible_examples,
                "actual": item.actual,
                "expected": item.expected,
                "matched": item.matched,
                "precision": item.precision,
            }
            for item in report.slices
        ],
        "hard_gates": [
            {
                "gate": item.gate,
                "events": item.events,
                "applicable": item.applicable,
                "passed": item.passed,
            }
            for item in report.hard_gates
        ],
        "per_example": [
            {
                "example_id": item.example_id,
                "slice": item.slice,
                "expected_total": item.expected_total,
                "actual_total": item.actual_total,
                "matched": item.matched,
                "failures": list(item.failures),
            }
            for item in report.examples
        ],
        "disabled_run_id": report.disabled_run_id,
        "enabled_trace_ids": list(report.enabled_trace_ids),
        "result_state": report.result_state.value,
        "notes": list(report.notes),
    }


def report_to_dict(report: MemoryEvaluationReport) -> Dict[str, Any]:
    """Render a report as JSON-serializable primitives."""
    return {
        "report_id": report.report_id,
        "dataset": {
            "dataset_id": report.dataset_id,
            "dataset_version": report.dataset_version,
            "dataset_role": report.dataset_role,
        },
        "code_identity": {
            "extractor_id": report.extractor_id,
            "policy_id": report.policy_id,
        },
        "counts": {
            "eligible_examples": report.eligible_examples,
            "invalid_examples": report.invalid_examples,
            "skipped_examples": report.skipped_examples,
        },
        "metrics": {
            "extraction_precision": _metric_to_dict(report.extraction_precision),
            "extraction_recall": _metric_to_dict(report.extraction_recall),
            "scope_accuracy": _metric_to_dict(report.scope_accuracy),
        },
        "mandatory_slices": [
            {
                "slice": item.slice,
                "eligible_examples": item.eligible_examples,
                "actual": item.actual,
                "expected": item.expected,
                "matched": item.matched,
                "precision": item.precision,
            }
            for item in report.slices
        ],
        "hard_gates": [
            {
                "gate": item.gate,
                "events": item.events,
                "applicable": item.applicable,
                "passed": item.passed,
            }
            for item in report.hard_gates
        ],
        "per_example": [
            {
                "example_id": item.example_id,
                "slice": item.slice,
                "expected_total": item.expected_total,
                "actual_total": item.actual_total,
                "matched": item.matched,
                "failures": list(item.failures),
            }
            for item in report.examples
        ],
        "result_state": report.result_state.value,
        "notes": list(report.notes),
    }


def _metric_to_dict(metric: MetricScore) -> Dict[str, Any]:
    return {
        "name": metric.name,
        "value": metric.value,
        "numerator": metric.numerator,
        "denominator": metric.denominator,
        "threshold": metric.threshold,
    }
