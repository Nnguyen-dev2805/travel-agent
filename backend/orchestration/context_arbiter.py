"""Context arbiter governing admission, precedence, and projection to GenerationContext.

Governed by Plan v0.15, Spec v0.7, and ADR 0039:
- Owns precedence, bounded context admission, and projection from source-specific
  records into a source-neutral final-generation contract.
- ContextMode.NONE: ContextSufficiency.NOT_REQUIRED, empty citations, empty prompt.
- ContextMode.RAG_ONLY: Preserves legacy top_k=4 travel context and citations.
  Maps ContextBundle.insufficient_evidence=True to ContextSufficiency.INSUFFICIENT.
- ContextMode.MEMORY_ONLY: Bounded structured Memory (<= 8 items), 0 travel citations.
  Empty selection maps to ContextSufficiency.INSUFFICIENT.
- ContextMode.BOTH: Complete bounded RAG context + bounded structured Memory context.
  Does not reserve an arbitrary percentage or drop travel evidence.
  Citations remain travel citations only.
- Never copies raw RetrievalResult.text or raw Memory evidence as instruction channels.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.generation.contracts import (
    ContextSufficiency,
    GenerationCitation,
    GenerationContext,
)
from backend.memory.context import (
    EpisodeContextComposer,
    MemoryContextComposer,
    WorkingContextComposer,
)
from backend.memory.read_models import MemorySelection
from backend.orchestration.turn_models import ContextMode
from backend.rag.contracts import ContextBundle


class ContextArbiter:
    """Arbitrates context sources into a source-neutral GenerationContext."""

    TRAVEL_HEADER: str = "=== CẨM NANG DU LỊCH THAM KHẢO ==="

    def __init__(
        self,
        memory_composer: Optional[MemoryContextComposer] = None,
        episode_composer: Optional[EpisodeContextComposer] = None,
        working_composer: Optional[WorkingContextComposer] = None,
    ) -> None:
        self._memory_composer = memory_composer or MemoryContextComposer()
        self._episode_composer = episode_composer or EpisodeContextComposer()
        self._working_composer = working_composer or WorkingContextComposer()

    def arbitrate(
        self,
        mode: ContextMode,
        rag_bundle: Optional[ContextBundle] = None,
        memory_selection: Optional[MemorySelection] = None,
        current_memory_override_keys: tuple[str, ...] = (),
        episodic_selection: Optional[Any] = None,
        working_selection: Optional[Any] = None,
    ) -> GenerationContext:
        """Project source records into GenerationContext according to the planned mode."""
        if mode is ContextMode.NONE:
            return GenerationContext(
                prompt_context="",
                citations=(),
                sufficiency=ContextSufficiency.NOT_REQUIRED,
            )

        if mode is ContextMode.RAG_ONLY:
            if rag_bundle is None or rag_bundle.insufficient_evidence:
                return GenerationContext(
                    prompt_context="",
                    citations=(),
                    sufficiency=ContextSufficiency.INSUFFICIENT,
                )
            citations = tuple(
                GenerationCitation(title=c.title, url=c.url)
                for c in rag_bundle.citations
            )
            prompt_context = f"{self.TRAVEL_HEADER}\n{rag_bundle.prompt_context.strip()}"
            return GenerationContext(
                prompt_context=prompt_context,
                citations=citations,
                sufficiency=ContextSufficiency.SUFFICIENT,
            )

        if mode is ContextMode.MEMORY_ONLY:
            admitted = self._admit_memory(memory_selection, current_memory_override_keys)
            if not admitted:
                return GenerationContext(
                    prompt_context="",
                    citations=(),
                    sufficiency=ContextSufficiency.INSUFFICIENT,
                )
            admitted_selection = MemorySelection(
                selected=admitted,
                abstention_reason=memory_selection.abstention_reason if memory_selection else None,
            )
            prompt_context = self._memory_composer.compose(admitted_selection)
            prompt_context = self._with_episodes(
                self._with_working(prompt_context, working_selection),
                episodic_selection,
            )
            return GenerationContext(
                prompt_context=prompt_context,
                citations=(),  # Memory is never a travel citation
                sufficiency=ContextSufficiency.SUFFICIENT,
            )

        if mode is ContextMode.BOTH:
            # BOTH requires travel knowledge grounding plus user memory.
            # Missing planned context returns INSUFFICIENT; no implicit mode downgrade.
            if rag_bundle is None or rag_bundle.insufficient_evidence:
                return GenerationContext(
                    prompt_context="",
                    citations=(),
                    sufficiency=ContextSufficiency.INSUFFICIENT,
                )

            admitted = self._admit_memory(memory_selection, current_memory_override_keys)
            if not admitted:
                return GenerationContext(
                    prompt_context="",
                    citations=(),
                    sufficiency=ContextSufficiency.INSUFFICIENT,
                )

            citations = tuple(
                GenerationCitation(title=c.title, url=c.url)
                for c in rag_bundle.citations
            )
            rag_part = f"{self.TRAVEL_HEADER}\n{rag_bundle.prompt_context.strip()}"
            admitted_selection = MemorySelection(
                selected=admitted,
                abstention_reason=memory_selection.abstention_reason if memory_selection else None,
            )
            mem_part = self._memory_composer.compose(admitted_selection).strip()
            # The Memory-side ladder is composed in precedence order first —
            # working state, then soft preferences, then episodes — and only then
            # joined to the travel context, which is retrieval evidence rather
            # than a tier of that ladder.
            mem_side = self._with_episodes(
                self._with_working(mem_part, working_selection),
                episodic_selection,
            )
            combined_prompt = f"{rag_part}\n\n{mem_side}"

            return GenerationContext(
                prompt_context=combined_prompt,
                citations=citations,
                sufficiency=ContextSufficiency.SUFFICIENT,
            )

        raise ValueError(f"Unsupported ContextMode: {mode}")

    def _with_working(self, prompt_context: str, working_selection: Any) -> str:
        """Prepend the governed Working Memory block.

        **Prepending is the precedence rule, not formatting.** `spec:1043-1052`
        puts "current conversation working state / temporary override" above
        user-scoped soft preferences and above episodes/summaries, so working state
        is composed before the Memory block rather than appended after it — which
        is the opposite of the episodic block, and the reason the two cannot share
        one helper.

        Working state never becomes a citation: an open state is context, not
        travel evidence.
        """
        if working_selection is None or not getattr(
            working_selection, "selected", ()
        ):
            return prompt_context
        block = self._working_composer.compose(working_selection)
        if not block:
            return prompt_context
        return f"{block}\n\n{prompt_context}" if prompt_context else block

    def _with_episodes(self, prompt_context: str, episodic_selection: Any) -> str:
        """Append the governed episodic block, last.

        Last is the precedence rule, not an accident: episodes sit below the
        current request, verified hard constraints and user-scoped soft
        preferences, so they are appended after the Memory block rather than
        interleaved with it. Episodes never become citations — a recorded event is
        context, not travel evidence.
        """
        if episodic_selection is None or not getattr(
            episodic_selection, "selected", ()
        ):
            return prompt_context
        block = self._episode_composer.compose(episodic_selection)
        if not block:
            return prompt_context
        return f"{prompt_context}\n\n{block}" if prompt_context else block

    def _admit_memory(
        self,
        memory_selection: Optional[MemorySelection],
        current_memory_override_keys: tuple[str, ...],
    ) -> tuple:
        """Filter out overridden keys and enforce admission bound (max 8 records)."""
        if memory_selection is None or not memory_selection.selected:
            return ()
        override_set = set(current_memory_override_keys)
        filtered = [
            item
            for item in memory_selection.selected
            if item.canonical_key not in override_set
        ]
        return tuple(filtered[:8])
