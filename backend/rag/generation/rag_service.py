"""RAG Generation Service facade connecting retrieval, context, and generation.

Runtime milestone R6 and Task 10:
- `build_travel_context()` returns the RAG-owned `ContextBundle`.
- `generate_from_context()` consumes neutral `GenerationContext` and returns neutral `GenerationResult`.
- `generate_answer()` remains the backward-compatible dictionary facade.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union

from backend.generation.contracts import (
    ContextSufficiency,
    GenerationCitation,
    GenerationContext,
    GenerationResult,
)
from backend.observability.events import emit_event
from backend.observability.models import (
    EventComponent,
    EventName,
    EventResult,
)
from backend.rag.contracts import ContextBundle
from backend.rag.generation.context import ContextAssembler
from backend.rag.generation.llm import LLMGenerator
from backend.rag.retrieval import KnowledgeRetriever

logger = logging.getLogger("travel_agent_rag_service")

DEFAULT_COLLECTION_NAME = "vietnam_travel_parent_child"
DEFAULT_TOP_K = 4


class RAGService:
    """Orchestrates retrieval, context assembly, and LLM answer generation.

    A thin facade over KnowledgeRetriever, ContextAssembler, and LLMGenerator.
    Dependencies are injectable for tests; when omitted, production defaults
    construct each stage from the module-level defaults.
    """

    def __init__(
        self,
        retriever: Optional[KnowledgeRetriever] = None,
        context_assembler: Optional[ContextAssembler] = None,
        generator: Optional[LLMGenerator] = None,
        top_k: int = DEFAULT_TOP_K,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        self.retriever = retriever or KnowledgeRetriever(
            top_k=top_k, collection_name=collection_name
        )
        self.context_assembler = context_assembler or ContextAssembler()
        self.generator = generator or LLMGenerator()
        self.top_k = top_k

    def warm(self) -> None:
        """Load the embedding model now rather than on the first user query."""
        self.retriever.embedder.warm()

    def generate_answer(
        self, user_message: str, top_k: Optional[int] = None
    ) -> Dict[str, Any]:
        """Retrieve relevant context and generate a source-cited response.

        Backward-compatible facade returning a dictionary with 'reply', 'model',
        and 'citations'. Projects RAG ContextBundle into GenerationContext and
        delegates to generate_from_context.
        """
        bundle = self.build_travel_context(user_message, top_k=top_k)
        sufficiency = (
            ContextSufficiency.INSUFFICIENT
            if bundle.insufficient_evidence
            else ContextSufficiency.SUFFICIENT
        )
        citations = tuple(
            GenerationCitation(title=c.title, url=c.url)
            for c in bundle.citations
        )
        gen_context = GenerationContext(
            prompt_context=f"=== CẨM NANG DU LỊCH THAM KHẢO ===\n{bundle.prompt_context}",
            citations=citations,
            sufficiency=sufficiency,
        )
        result = self.generate_from_context(user_message, gen_context)
        return {
            "reply": result.reply,
            "model": result.model,
            "citations": [
                {"title": c.title, "url": c.url}
                for c in result.citations
            ],
        }

    def build_travel_context(
        self, user_message: str, top_k: Optional[int] = None
    ) -> ContextBundle:
        """Embed the query, retrieve travel evidence, and assemble context."""
        user_text = user_message.strip()
        if not user_text:
            raise ValueError("User message content cannot be empty.")

        resolved_top_k = top_k if top_k is not None else self.top_k

        results = self.retriever.retrieve(user_text, top_k=resolved_top_k)
        bundle = self.context_assembler.assemble(results)
        emit_event(
            EventName.RAG_RETRIEVAL_COMPLETED,
            EventComponent.RAG,
            EventResult.SUCCESS,
            counters={"evidence": len(results), "top_k": resolved_top_k},
        )
        return bundle

    def generate_from_context(
        self, user_message: str, context: GenerationContext
    ) -> GenerationResult:
        """Generate a response from a neutral GenerationContext.

        Returns a source-neutral GenerationResult.
        """
        if not isinstance(context, GenerationContext):
            raise TypeError(
                f"context must be a GenerationContext, got {type(context).__name__}; "
                "ContextBundle compatibility is restricted to generate_answer()."
            )

        user_text = user_message.strip()
        if not user_text:
            raise ValueError("User message content cannot be empty.")

        try:
            generated = self.generator.generate(user_text, context)
        except Exception as error:
            emit_event(
                EventName.MODEL_CALL_FAILED,
                EventComponent.MODEL_PROVIDER,
                EventResult.FAILURE,
                failure_class=type(error).__name__,
                reason_code="generation_failed",
            )
            raise

        emit_event(
            EventName.MODEL_CALL_COMPLETED,
            EventComponent.MODEL_PROVIDER,
            EventResult.SUCCESS,
            counters={"citations": len(generated.citations)},
        )

        return generated
