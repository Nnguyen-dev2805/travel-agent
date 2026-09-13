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
        """Record the rollout request.

        The default is the safe one: a caller that forgets to pass the flag gets
        shadow behaviour. The value is **recorded, not applied** — see
        `enforcement_enabled`.
        """
        self._enforcement_requested = enforcement_enabled

    @property
    def enforcement_requested(self) -> bool:
        """The configured rollout value, as passed by the composition root."""
        return self._enforcement_requested

    @property
    def enforcement_enabled(self) -> bool:
        """Whether authoritative planner execution is active. Always `False` here.

        Enforcement means the orchestrator executes the *effective* plan instead
        of the baseline. Stage 1 has no such executor — `handle_turn` always calls
        the RAG path — so enforcement cannot be active, and a plan that reported
        the proposal as effective would describe execution that never happens.
        Task 10 owns authoritative execution, and it is gated on a conclusive
        zero-false-`NONE` fixture set.
        """
        return False

    def plan(self, understanding: TurnUnderstandingResult) -> ContextPlan:
        """Return the proposed and effective context modes for one turn.

        A turn that only asks for clarification does not answer, so it needs no
        grounding and proposes `NONE`. Every other reading proposes `RAG_ONLY`,
        which is what the current baseline actually does — Stage 1 has no
        grounded alternative to propose.

        `effective` describes what will actually execute. Stage 1 always runs the
        RAG-only baseline, so the proposal is never adopted and `is_shadow` is
        always `True`. That is the honest contract: a field named "effective" must
        not describe a mode nothing runs.
        """
        return ContextPlan(
            proposed=self._propose(understanding),
            effective=ContextMode.RAG_ONLY,
        )

    @staticmethod
    def _propose(understanding: TurnUnderstandingResult) -> ContextMode:
        """The Stage-1 proposal, restricted to the reachable modes."""
        if (
            understanding.interaction_mode is InteractionMode.AMBIGUOUS
            or understanding.needs_clarification
        ):
            return ContextMode.NONE
        return ContextMode.RAG_ONLY
