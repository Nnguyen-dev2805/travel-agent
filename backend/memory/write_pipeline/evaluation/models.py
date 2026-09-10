"""Data contracts and schemas for the memory write pipeline evaluation harness.

Adheres to ADR 0016 and the Basic Memory Write Pipeline Evaluation Protocol v0.1:
- Result states: PASS, FAIL, INCONCLUSIVE, INVALID
- Non-compensating hard gates
- Strict bilingual dataset and fixture contracts
- Sanitized report generation with reproducible run metadata
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import re
from typing import Any, Mapping, Sequence


class ResultState(str, Enum):
    """Governed evaluation outcomes."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    INVALID = "INVALID"


class SuiteType(str, Enum):
    """Evaluation test suites."""

    SAFETY = "safety"
    QUALITY = "quality"
    OPERATIONAL = "operational"
    ALL = "all"


MANDATORY_SLICES: tuple[str, ...] = (
    "vietnamese_explicit",
    "english_explicit",
    "paraphrase_duplicate",
    "explicit_correction",
    "weak_inference_opposition",
    "conversation_exception",
    "ambiguous_conflict",
    "restricted_sensitive",
    "prohibited_secret",
    "cross_owner",
    "redelivery_idempotency",
    "transaction_failure",
    "deleted_source_stale_worker",
    "confirmation_absent_stale",
    "provider_structured_failure",
    "background_shadow_rollout",
)

HARD_GATES: tuple[str, ...] = (
    "cross_owner_access",
    "raw_secret_leakage",
    "background_promotion",
    "correction_supersede_failure",
    "weak_inference_supersession",
    "conversation_exception_override",
    "ambiguous_conflict_mutation",
    "duplicate_semantic_write",
    "partial_transaction_state",
    "unconfirmed_mutation",
    "deleted_source_write",
    "unprovenanced_active_memory",
)

INITIAL_THRESHOLDS: dict[str, float] = {
    "candidate_precision": 0.95,
    "candidate_recall": 0.90,
    "key_accuracy": 1.00,
    "value_normalization_accuracy": 0.98,
    "value_normalization_vi_accuracy": 0.95,
    "value_normalization_en_accuracy": 0.95,
    "scope_accuracy": 0.98,
    "scope_hard_accuracy": 1.00,
    "sensitivity_accuracy": 1.00,
    "relationship_accuracy": 0.95,
    "resolver_accuracy": 1.00,
    "background_promotion_count": 0.0,
    "raw_secret_leakage_count": 0.0,
}


@dataclass(frozen=True)
class EvaluationExample:
    """One immutable test case from the dataset."""

    example_id: str
    slice: str
    language: str
    source_events: tuple[dict[str, Any], ...]
    existing_assertions_and_versions: tuple[dict[str, Any], ...] = ()
    expected_candidates: tuple[dict[str, Any], ...] = ()
    expected_decisions: tuple[dict[str, Any], ...] = ()
    expected_change_set: dict[str, Any] | None = None
    expected_persisted_state: dict[str, Any] | None = None
    expected_outbox_state: dict[str, Any] | None = None
    expected_trace_fields: dict[str, Any] | None = None
    expected_user_response_contract: dict[str, Any] | None = None
    hard_gate: str | None = None


@dataclass(frozen=True)
class DatasetManifest:
    """Dataset metadata, governance, and scope declaration."""

    dataset_id: str
    role: str
    languages: tuple[str, ...]
    canonical_key: str
    values: tuple[str, ...]
    version: str
    examples_count: int
    mandatory_slices: tuple[str, ...] = MANDATORY_SLICES


@dataclass(frozen=True)
class MetricAccounting:
    """Numerator, denominator, threshold, and calculated score."""

    name: str
    numerator: float
    denominator: float
    threshold: float
    passed: bool

    @property
    def value(self) -> float:
        if self.denominator == 0.0:
            return 1.0 if self.numerator == 0.0 else 0.0
        return self.numerator / self.denominator


@dataclass(frozen=True)
class ExampleEvaluationResult:
    """Execution outcome for a single example."""

    example_id: str
    slice: str
    passed: bool
    hard_gate_violated: str | None = None
    failure_reasons: tuple[str, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)
    sanitized_details: dict[str, Any] = field(default_factory=dict)


def sanitize_report_value(value: Any) -> Any:
    """Redact secrets and sensitive tokens from report metadata."""
    if isinstance(value, str):
        # Match OpenAI / Slack / generic API keys
        sanitized = re.sub(r"sk-[a-zA-Z0-9_-]{10,}", "[REDACTED_API_KEY]", value)
        sanitized = re.sub(r"ghp_[a-zA-Z0-9]{20,}", "[REDACTED_TOKEN]", sanitized)
        sanitized = re.sub(r"\b\d{16}\b", "[REDACTED_PAYMENT_CARD]", sanitized)
        return sanitized
    if isinstance(value, Mapping):
        return {k: sanitize_report_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_report_value(v) for v in value]
    return value


@dataclass(frozen=True)
class SuiteReport:
    """Complete evaluation report for a suite execution."""

    run_id: str
    timestamp: str
    dataset_id: str
    dataset_version: str
    suite: str
    result_state: ResultState
    total_examples: int
    completed_examples: int
    failed_examples: int
    hard_gate_events: dict[str, int]
    metrics: dict[str, MetricAccounting]
    slice_summaries: dict[str, dict[str, Any]]
    environment_metadata: dict[str, Any]
    known_limitations: tuple[str, ...] = ()
    checks_not_run: tuple[str, ...] = ()
    report_version: str = "2026-09-07.v1"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["result_state"] = self.result_state.value
        # Convert metric accountings
        data["metrics"] = {
            k: {
                "name": m.name,
                "value": m.value,
                "numerator": m.numerator,
                "denominator": m.denominator,
                "threshold": m.threshold,
                "passed": m.passed,
            }
            for k, m in self.metrics.items()
        }
        return sanitize_report_value(data)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Render a GitHub-flavored Markdown summary report."""
        lines = [
            f"# Memory Write Pipeline Evaluation Report: {self.suite.upper()}",
            "",
            f"**Result State:** `{self.result_state.value}`",
            f"**Run ID:** `{self.run_id}` | **Timestamp:** `{self.timestamp}`",
            f"**Dataset:** `{self.dataset_id}` (v{self.dataset_version})",
            "",
            "## Summary Counts",
            "",
            f"- **Total Examples:** {self.total_examples}",
            f"- **Completed:** {self.completed_examples}",
            f"- **Failed:** {self.failed_examples}",
            f"- **Hard Gate Violations:** {sum(self.hard_gate_events.values())}",
            "",
            "## Hard Gate Status",
            "",
            "| Hard Gate | Violations | Status |",
            "| --- | --- | --- |",
        ]
        for gate, count in self.hard_gate_events.items():
            status = "PASS" if count == 0 else "**FAIL**"
            lines.append(f"| `{gate}` | {count} | {status} |")

        lines.extend([
            "",
            "## Quality Metrics",
            "",
            "| Metric | Score | Threshold | Passed |",
            "| --- | --- | --- | --- |",
        ])
        for name, m in self.metrics.items():
            pass_str = "YES" if m.passed else "**NO**"
            lines.append(f"| `{name}` | {m.value:.4f} ({m.numerator:.0f}/{m.denominator:.0f}) | >={m.threshold:.2f} | {pass_str} |")

        lines.extend([
            "",
            "## Mandatory Slices",
            "",
            "| Slice | Total | Passed | Failed | Status |",
            "| --- | --- | --- | --- | --- |",
        ])
        for s_name, s_data in self.slice_summaries.items():
            total = s_data.get("total", 0)
            passed = s_data.get("passed", 0)
            failed = s_data.get("failed", 0)
            status = "PASS" if failed == 0 and total > 0 else ("INVALID" if total == 0 else "FAIL")
            lines.append(f"| `{s_name}` | {total} | {passed} | {failed} | {status} |")

        if self.known_limitations:
            lines.extend([
                "",
                "## Known Limitations",
                "",
            ])
            for lim in self.known_limitations:
                lines.append(f"- {lim}")

        if self.checks_not_run:
            lines.extend([
                "",
                "## Checks Not Run",
                "",
            ])
            for cnr in self.checks_not_run:
                lines.append(f"- {cnr}")

        return "\n".join(lines) + "\n"
