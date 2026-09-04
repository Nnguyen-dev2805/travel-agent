"""RAG Generation Service facade connecting retrieval, context, and generation."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

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

    def generate_answer(self, user_message: str, top_k: Optional[int] = None) -> Dict[str, Any]:
        """Retrieve relevant context and generate a source-cited response.

        Args:
            user_message: User query string; stripped before use.
            top_k: Number of relevant chunks to retrieve; overrides the
                constructor default when provided.

        Returns:
            Dictionary containing 'reply', 'model', and 'citations'.
        """
        user_text = user_message.strip()
        if not user_text:
            raise ValueError("User message content cannot be empty.")

        resolved_top_k = top_k if top_k is not None else self.top_k

        logger.info(f"Processing RAG request for: '{user_text[:50]}...'")

        results = self.retriever.retrieve(user_text, top_k=resolved_top_k)
        bundle = self.context_assembler.assemble(results)
        generated = self.generator.generate(user_text, bundle)

        citations_list = [
            {"title": citation.title, "url": citation.url}
            for citation in generated.citations
        ]

        logger.info(f"Successfully generated RAG response with {len(citations_list)} citations.")

        return {
            "reply": generated.reply,
            "model": generated.model,
            "citations": citations_list,
        }
