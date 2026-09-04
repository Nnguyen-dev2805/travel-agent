"""Context assembly mapping structured retrieval evidence to a generation context."""

from __future__ import annotations

from typing import Sequence

from backend.rag.contracts import CitationEvidence, ContextBundle, RetrievalResult

EMPTY_CONTEXT_PLACEHOLDER = "Không tìm thấy tài liệu liên quan."


class ContextAssembler:
    """Assembles retrieval evidence into the legacy prompt context and citations.

    Preserves the characterized legacy formatting exactly: numbered
    ``[Nguồn {i}: {title}]\\n{text}`` blocks joined by ``\\n\\n---\\n\\n``, a
    fixed placeholder for zero results, and title-grouped citations where the
    later URL wins, chunk ids accumulate per title in appearance order, and
    items missing title or URL contribute no citation. There is deliberately
    no score threshold: insufficient evidence means zero results only.
    """

    def assemble(self, results: Sequence[RetrievalResult]) -> ContextBundle:
        """Build a ContextBundle from ordered retrieval results.

        Args:
            results: Ordered retrieval evidence selected for generation.

        Returns:
            ContextBundle with the legacy prompt context, the evidence tuple
            in input order, grouped citations, and insufficient_evidence set
            only when results is empty.
        """
        selected = list(results)
        if not selected:
            return ContextBundle(
                prompt_context=EMPTY_CONTEXT_PLACEHOLDER,
                evidence=(),
                citations=(),
                insufficient_evidence=True,
            )

        context_parts: list[str] = []
        # title -> (url, [chunk_id, ...]); dict order = first title appearance.
        citations_map: dict[str, tuple[str, list[str]]] = {}

        for idx, item in enumerate(selected, 1):
            context_parts.append(f"[Nguồn {idx}: {item.title}]\n{item.text}")

            if item.url and item.title:
                if item.title in citations_map:
                    _previous_url, evidence_ids = citations_map[item.title]
                    evidence_ids.append(item.chunk_id)
                    # Later URL wins for the whole title group.
                    citations_map[item.title] = (item.url, evidence_ids)
                else:
                    citations_map[item.title] = (item.url, [item.chunk_id])

        citations = tuple(
            CitationEvidence(title=title, url=url, evidence_ids=tuple(evidence_ids))
            for title, (url, evidence_ids) in citations_map.items()
        )

        return ContextBundle(
            prompt_context="\n\n---\n\n".join(context_parts),
            evidence=tuple(selected),
            citations=citations,
            insufficient_evidence=False,
        )
