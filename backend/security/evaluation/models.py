"""Security evaluation report contracts for milestone R9.

Reports carry identifiers, gate evidence, and controlled failure labels
only: never token values, raw user content, secrets, prompts, answers,
provider payloads, filesystem paths, or stack traces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SecurityEvaluationError(Exception):
    """The security evaluation harness cannot run or score a suite."""


class SecurityResultState(str, Enum):
    """Governed security evaluation outcome vocabulary."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    INVALID = "INVALID"


@dataclass(frozen=True)
class SecurityGateScore:
    """One evaluated zero-tolerance gate with its event count."""

    gate: str
    applicable: bool
    passed: bool
    events: int = 0


@dataclass(frozen=True)
class SecurityExampleScore:
    """Per-example security evidence without raw content."""

    example_id: str
    slice: str
    failures: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SecurityReport:
    """One deterministic security/privacy evaluation outcome."""

    dataset_id: str
    dataset_version: str
    result_state: SecurityResultState
    eligible_examples: int
    gates: tuple[SecurityGateScore, ...]
    per_example: tuple[SecurityExampleScore, ...]

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
            "environment": {
                "evaluation": "local-synthetic",
                "auth_required": True,
            },
        }
