"""Operational evaluation report contracts for milestone R8.

Reports carry identifiers, gate evidence, and controlled failure labels
only: never raw user content, secrets, prompts, answers, provider
payloads, filesystem paths, or stack traces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OpsEvaluationError(Exception):
    """The operational evaluation harness cannot run or score a suite."""


class OpsResultState(str, Enum):
    """Governed operational evaluation outcome vocabulary."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    INVALID = "INVALID"


@dataclass(frozen=True)
class OpsGateScore:
    """One evaluated operational gate with its pass state."""

    gate: str
    applicable: bool
    passed: bool
    events: int = 0


@dataclass(frozen=True)
class OpsExampleScore:
    """Per-example operational evidence without raw content."""

    example_id: str
    slice: str
    failures: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class OpsReport:
    """One deterministic operational evaluation outcome."""

    dataset_id: str
    dataset_version: str
    result_state: OpsResultState
    eligible_examples: int
    gates: tuple[OpsGateScore, ...]
    per_example: tuple[OpsExampleScore, ...]

    def to_dict(self) -> dict[str, Any]:
        """Render the machine-readable report payload."""
        return {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "result_state": self.result_state.value,
            "counts": {"eligible_examples": self.eligible_examples},
            "gates": [
                {
                    "gate": gate.gate,
                    "applicable": gate.applicable,
                    "passed": gate.passed,
                    "events": gate.events,
                }
                for gate in self.gates
            ],
            "per_example": [
                {
                    "example_id": item.example_id,
                    "slice": item.slice,
                    "failures": list(item.failures),
                }
                for item in self.per_example
            ],
            "environment": {"evaluation": "local-synthetic"},
        }
