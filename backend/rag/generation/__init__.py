"""RAG generation package.

Deliberately exports nothing. This module previously re-exported
`ContextAssembler`, `LLMGenerator` and `RAGService` eagerly, so importing *any*
submodule of this package imported `rag_service` -> `VectorEmbedder` ->
`sentence-transformers` -> torch. Importing `backend.rag.generation.llm` to
construct a prompt therefore loaded the whole model runtime, and in a
memory-constrained environment it killed the process outright.

Import from the concrete submodule instead:

    from backend.rag.generation.context import ContextAssembler
    from backend.rag.generation.llm import LLMGenerator
    from backend.rag.generation.rag_service import RAGService

`backend/tests/unit/test_rag_generation_imports.py` fails if that stops holding.
"""
