"""Source-neutral generation contracts.

Governed by Plan v0.15, Spec v0.7, and ADR 0039.
This package owns source-neutral context, citation, sufficiency, and result types
feeding the final generation model.
It imports neither backend.rag, backend.memory, nor backend.orchestration.
"""

from __future__ import annotations

from backend.generation.contracts import (
    ContextSufficiency,
    GenerationCitation,
    GenerationContext,
    GenerationResult,
)

__all__ = [
    "ContextSufficiency",
    "GenerationCitation",
    "GenerationContext",
    "GenerationResult",
]
