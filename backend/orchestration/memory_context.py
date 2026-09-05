"""Memory prompt section composition for milestone R6.

The composer turns retrieval selections into one controlled prompt section
that the orchestrator prepends to travel RAG context. It takes selection
contracts only: no repository, no RAG import, no model call. Travel
citations are never touched here, so memory can never become a citation.

An empty selection composes to an empty string, and the orchestrator adds
no memory section at all in that case.
"""

from __future__ import annotations

from typing import Sequence

from backend.memory.models import MemorySelection

MEMORY_SECTION_HEADER = "[Bộ nhớ liên quan]"


def compose_memory_section(selections: Sequence[MemorySelection]) -> str:
    """Format selections as one deterministic memory prompt section."""
    ordered = list(selections)
    if not ordered:
        return ""
    lines = [MEMORY_SECTION_HEADER]
    for selection in ordered:
        lines.append(
            f"- {selection.text} (loại: {selection.memory_type.value}, "
            f"phạm vi: {selection.scope.value})"
        )
    return "\n".join(lines)
