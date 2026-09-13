"""The context source plan for one bounded turn, and its rollout gate.

`ContextPlanner` owns the source plan using the closed vocabulary
`none | rag_only | memory_only | both` (`ADR 0039:54-66`). Stage 1 exposes the
whole vocabulary and can only *propose* two of the values: `memory_only` and
`both` require governed Memory Read, which does not exist yet.

The planner is **shadow-only** in Stage 1 (`plan v0.7:444-450`). It records what
it would choose, and the effective mode stays the existing `RAG_ONLY` baseline
while `CONTEXT_PLANNER_ENFORCEMENT_ENABLED` is false. That separation is the
reason `ContextPlan` carries `proposed` and `effective` as two fields rather than
one: a single field would make "proposed NONE" indistinguishable from "skipped
retrieval", and those are the two things the rollout contract must never
conflate.

Planning is pure: no retrieval, no Memory, no provider call.
"""

from __future__ import annotations

from backend.orchestration.turn_models import (
    ContextMode,
    ContextPlan,
    InteractionMode,
    TurnUnderstandingResult,
)


class ContextPlanner:
    """Propose a context source plan, and report what will actually execute."""

    def __init__(self, enforcement_enabled: bool = False) -> None:
        """Bind the rollout gate.

        The default is the safe one: a caller that forgets to pass the flag gets
        shadow behaviour, never enforcement. That matters because enforcement is
        only permitted after the zero-false-`NONE` hard gate is conclusive, and a
        default that enforced would silently pre-empt that gate.
        """
        self._enforcement_enabled = enforcement_enabled

    @property
    def enforcement_enabled(self) -> bool:
        """Whether this planner's proposal is authoritative.

        Exposed so the composition root's wiring is inspectable: an inert rollout
        flag is indistinguishable from a working one unless the gate state can be
        read back. `False` means every plan is shadow evidence.
        """
        return self._enforcement_enabled

    def plan(self, understanding: TurnUnderstandingResult) -> ContextPlan:
        """Return the proposed and effective context modes for one turn.

        A turn that only asks for clarification does not answer, so it needs no
        grounding and proposes `NONE`. Every other reading proposes `RAG_ONLY`,
        which is what the current baseline actually does — Stage 1 has no
        grounded alternative to propose.

        While enforcement is off the effective mode is `RAG_ONLY` regardless of
        the proposal, so a `NONE` proposal is recorded as shadow evidence and
        cannot skip retrieval.
        """
        proposed = self._propose(understanding)
        effective = proposed if self._enforcement_enabled else ContextMode.RAG_ONLY
        return ContextPlan(proposed=proposed, effective=effective)

    @staticmethod
    def _propose(understanding: TurnUnderstandingResult) -> ContextMode:
        """The Stage-1 proposal, restricted to the reachable modes."""
        if (
            understanding.interaction_mode is InteractionMode.AMBIGUOUS
            or understanding.needs_clarification
        ):
            return ContextMode.NONE
        return ContextMode.RAG_ONLY
