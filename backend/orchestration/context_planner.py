"""The context source plan for one bounded turn, and its rollout gate.

`ContextPlanner` owns the source plan using the closed vocabulary
`none | rag_only | memory_only | both` (`ADR 0039:54-66`).
Stage 3 makes `memory_only` and `both` reachable now that governed Memory Read
exists.

When `CONTEXT_PLANNER_ENFORCEMENT_ENABLED` is false, the effective normal-query
source plan stays the existing `RAG_ONLY` baseline, so proposals remain shadow
evidence. When enforcement is enabled, the proposed mode becomes effective.

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
        """Record the rollout request."""
        self._enforcement_requested = enforcement_enabled

    @property
    def enforcement_requested(self) -> bool:
        """The configured rollout value, as passed by the composition root."""
        return self._enforcement_requested

    @property
    def enforcement_enabled(self) -> bool:
        """Whether authoritative planner execution is active in Stage 3."""
        return self._enforcement_requested

    def plan(self, understanding: TurnUnderstandingResult) -> ContextPlan:
        """Return the proposed and effective context modes for one turn."""
        proposed = self._propose(understanding)
        effective = proposed if self.enforcement_enabled else ContextMode.RAG_ONLY
        return ContextPlan(
            proposed=proposed,
            effective=effective,
        )

    @staticmethod
    def _propose(understanding: TurnUnderstandingResult) -> ContextMode:
        """The Stage-3 proposal covering the full approved vocabulary."""
        if (
            understanding.interaction_mode is InteractionMode.AMBIGUOUS
            or understanding.needs_clarification
        ):
            return ContextMode.NONE

        has_memory = bool(understanding.memory_namespaces_needed)
        has_travel_topics = bool(understanding.topics)
        is_normal_query = understanding.interaction_mode is InteractionMode.NORMAL_QUERY

        if has_memory and has_travel_topics:
            return ContextMode.BOTH
        if has_memory and not has_travel_topics:
            return ContextMode.MEMORY_ONLY
        if has_travel_topics or is_normal_query:
            return ContextMode.RAG_ONLY
        return ContextMode.NONE
