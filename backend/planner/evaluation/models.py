"""Planner evaluation report contracts for milestone R7.

Reports carry identifiers, gate evidence, and controlled failure labels
only: never itinerary text, decision statements, or message content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PlannerEvaluationError(Exception):
    """The planner evaluation harness cannot run or score a suite."""


class PlannerResultState(str, Enum):
    """Governed planner evaluation outcome vocabulary."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    INVALID = "INVALID"


@dataclass(frozen=True)
class PlannerGateScore:
    """One evaluated planner gate with its pass state."""

    gate: str
    applicable: bool
    passed: bool
    events: int = 0


@dataclass(frozen=True)
class PlannerExampleScore:
    """Per-example planner evidence without raw content."""

    example_id: str
    slice: str
    failures: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PlannerStateReport:
    """One deterministic planner state evaluation outcome."""

    dataset_id: str
    dataset_version: str
    result_state: PlannerResultState
    eligible_examples: int
    gates: tuple[PlannerGateScore, ...]
    per_example: tuple[PlannerExampleScore, ...]

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
            "environment": {"planner_schema": "planner_state@1"},
        }
