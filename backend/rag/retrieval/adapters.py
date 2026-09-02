"""Adapter mapping raw Chroma vector-store results to runtime evidence contracts."""

from __future__ import annotations

from typing import Any

from backend.rag.contracts import RetrievalResult


def map_chroma_result(item: dict[str, Any]) -> RetrievalResult:
    """Map one ChromaVectorStore.search_similar() result item to a RetrievalResult.

    Resolves document_id from metadata, title from metadata, and url from
    metadata["url"] with legacy fallback to metadata["source_url"]. Preserves
    text and score from the current vector-store result shape.

    Raises:
        ValueError: When governed chunk or document identity is missing or
            blank, rather than fabricating an identity.
    """
    chunk_id = str(item.get("chunk_id") or "").strip()
    if not chunk_id:
        raise ValueError(
            "Chroma result is missing governed chunk identity ('chunk_id')."
        )

    metadata = item.get("metadata") or {}
    document_id = str(metadata.get("document_id") or "").strip()
    if not document_id:
        raise ValueError(
            "Chroma result is missing governed document identity ('document_id')."
        )

    url = str(metadata.get("url") or metadata.get("source_url") or "")
    score = item.get("score")

    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=document_id,
        title=str(metadata.get("title") or ""),
        url=url,
        score=float(score) if score is not None else None,
        text=str(item.get("text") or ""),
    )
