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
TRAVEL_SECTION_HEADER = "[Ngữ cảnh du lịch]"


def _one_line(text: str) -> str:
    """Collapse embedded line breaks so memory text cannot forge a header.

    A stored memory may legitimately contain newlines, but a newline inside
    a prompt item would let crafted content mimic a section boundary. The
    stored record is unchanged; only its prompt rendering is flattened.
    """
    return " ".join(text.split())


def compose_memory_section(selections: Sequence[MemorySelection]) -> str:
    """Format selections as one deterministic memory prompt section."""
    ordered = list(selections)
    if not ordered:
        return ""
    lines = [MEMORY_SECTION_HEADER]
    for selection in ordered:
        lines.append(
            f"- {_one_line(selection.text)} (loại: {selection.memory_type.value}, "
            f"phạm vi: {selection.scope.value})"
        )
    return "\n".join(lines)


def compose_turn_context(
    travel_context: str, selections: Sequence[MemorySelection]
) -> str:
    """Compose the full generation context for one memory-enabled turn.

    The composer, not the orchestrator, owns prompt shape: the memory
    section first per the approved spec, then the travel section, each
    under an explicit boundary header. Headers mark provenance; they do
    not neutralize injection, which is why memory retrieval stays
    feature-gated and evaluated.
    """
    section = compose_memory_section(selections)
    if not section:
        return travel_context
    return f"{section}\n\n{TRAVEL_SECTION_HEADER}\n{travel_context}"
