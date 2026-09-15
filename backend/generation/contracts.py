"""Source-neutral value contracts for final-answer generation.

Governed by Plan v0.15, Spec v0.7, and ADR 0039:
- GenerationContext deliberately has no travel_evidence, memory_context, or
  Memory/RAG domain types.
- This module imports neither backend.rag, backend.memory, nor backend.orchestration.
- ContextSufficiency.NOT_REQUIRED is distinct from INSUFFICIENT: a turn such
  as ordinary conversation may need no external source at all, whereas a turn
  whose planned grounding source produced nothing must fail/abstain through the
  controlled insufficient-context path.
- GenerationResult is source-neutral; final-answer generation must not return a
  RAG-owned result type.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ContextSufficiency(str, Enum):
    """Sufficiency classification of the assembled generation context."""

    NOT_REQUIRED = "not_required"
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class GenerationCitation:
    """A projected citation for final answer display."""

    title: str
    url: str


@dataclass(frozen=True)
class GenerationContext:
    """Source-neutral generation context feeding the answer generator."""

    prompt_context: str
    citations: tuple[GenerationCitation, ...]
    sufficiency: ContextSufficiency


@dataclass(frozen=True)
class GenerationResult:
    """Source-neutral generation result returned by the answer generator."""

    reply: str
    model: str
    citations: tuple[GenerationCitation, ...]
