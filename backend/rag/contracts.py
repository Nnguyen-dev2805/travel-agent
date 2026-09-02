"""Runtime-owned evidence value contracts for the RAG path.

These contracts are owned by the online RAG runtime per ADR 0001. They must
not import anything from the evaluation subsystem; evaluation is a one-way
consumer of these types.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalResult:
    """One retrieved travel-knowledge evidence item with stable identity.

    chunk_id and document_id are governed identity and must be non-empty at
    adapter boundaries. title and url are optional human-display values and
    may be empty strings. score may be None when a backend exposes none.
    """

    chunk_id: str
    document_id: str
    title: str
    url: str
    score: float | None
    text: str


@dataclass(frozen=True)
class CitationEvidence:
    """A projected citation linked back to its supporting retrieval evidence."""

    title: str
    url: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ContextBundle:
    """Generation context assembled from selected retrieval evidence."""

    prompt_context: str
    evidence: tuple[RetrievalResult, ...]
    citations: tuple[CitationEvidence, ...]
    insufficient_evidence: bool


@dataclass(frozen=True)
class GeneratedAnswer:
    """Generated answer with citations traceable to retrieval evidence."""

    reply: str
    model: str
    citations: tuple[CitationEvidence, ...]
