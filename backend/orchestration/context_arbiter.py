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

from typing import Optional

from backend.generation.contracts import (
    ContextSufficiency,
    GenerationCitation,
    GenerationContext,
)
from backend.memory.context import MemoryContextComposer
from backend.memory.read_models import MemorySelection
from backend.orchestration.turn_models import ContextMode
from backend.rag.contracts import ContextBundle


class ContextArbiter:
    """Arbitrates context sources into a source-neutral GenerationContext."""

    TRAVEL_HEADER: str = "=== CẨM NANG DU LỊCH THAM KHẢO ==="

    def __init__(self, memory_composer: Optional[MemoryContextComposer] = None) -> None:
        self._memory_composer = memory_composer or MemoryContextComposer()

    def arbitrate(
        self,
        mode: ContextMode,
        rag_bundle: Optional[ContextBundle] = None,
        memory_selection: Optional[MemorySelection] = None,
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
            if memory_selection is None or not memory_selection.selected:
                return GenerationContext(
                    prompt_context="",
                    citations=(),
                    sufficiency=ContextSufficiency.INSUFFICIENT,
                )
            prompt_context = self._memory_composer.compose(memory_selection)
            return GenerationContext(
                prompt_context=prompt_context,
                citations=(),  # Memory is never a travel citation
                sufficiency=ContextSufficiency.SUFFICIENT,
            )

        if mode is ContextMode.BOTH:
            # BOTH requires travel knowledge grounding plus user memory
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

            rag_part = f"{self.TRAVEL_HEADER}\n{rag_bundle.prompt_context.strip()}"
            mem_part = ""
            if memory_selection is not None and memory_selection.selected:
                mem_part = self._memory_composer.compose(memory_selection).strip()

            combined_prompt = f"{rag_part}\n\n{mem_part}" if mem_part else rag_part

            return GenerationContext(
                prompt_context=combined_prompt,
                citations=citations,
                sufficiency=ContextSufficiency.SUFFICIENT,
            )

        raise ValueError(f"Unsupported ContextMode: {mode}")
