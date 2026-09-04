"""Runtime adapters and preflight checks for governed R2 evaluation.

Per the approved RAG repair plan (Task 4 Step 6 & 7 and Task 6 Step 11):
- CurrentRuntimeAdapter and StructuredRuntimeAdapter wire KnowledgeRetriever / ContextAssembler / LLMGenerator.
- RecordingVectorStoreProxy captures the exact ranked evidence feeding generation for the current runtime.
- Preflight validates dataset, run config, index existence/count, embedding model, and credentials.
- Missing index, model, or credentials produce infrastructure_failure rather than dummy fallbacks.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

from backend.app.config import settings
from backend.rag.contracts import GeneratedAnswer, RetrievalResult
from backend.rag.embedding import VectorEmbedder
from backend.rag.embedding.embedder import HAS_SENTENCE_TRANSFORMERS
from backend.rag.evaluation.dataset import load_dataset, validate_run_config
from backend.rag.evaluation.models import EvaluationDataset, RunConfig
from backend.rag.generation.context import ContextAssembler
from backend.rag.generation.llm import LLMGenerator, PROMPT_ID
from backend.rag.retrieval import ChromaVectorStore, KnowledgeRetriever
from backend.rag.retrieval.adapters import map_chroma_result

logger = logging.getLogger("rag_evaluation_runtime")


class RecordingVectorStoreProxy:
    """Delegates Chroma operations while recording exact raw search results."""

    def __init__(self, real_store: Any) -> None:
        self._real_store = real_store
        self.last_results: list[dict[str, Any]] = []

    def search_similar(
        self, query_embedding: list[float], top_k: int = 4
    ) -> list[dict[str, Any]]:
        results = self._real_store.search_similar(query_embedding, top_k=top_k)
        self.last_results = list(results)
        return results

    def count(self) -> int:
        return self._real_store.count()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real_store, name)


ALLOWED_CURRENT_RUNTIME_PROMPTS = frozenset({
    "legacy-rag-service-inline-prompt-v1",
})

# The structured candidate executes the versioned prompt owned by the
# generation module; the allowlist derives from that single source of truth.
ALLOWED_STRUCTURED_RUNTIME_PROMPTS = frozenset({PROMPT_ID})


class CurrentRuntimeAdapter:
    """Connects the evaluation runner to the current RAG baseline runtime."""

    def __init__(
        self,
        config: RunConfig,
        embedder: Any = None,
        vector_store: Any = None,
    ) -> None:
        self.config = config
        self.embedder = embedder or VectorEmbedder(model_name=config.embedding_model)
        self.vector_store = vector_store or ChromaVectorStore(
            collection_name=config.collection_name
        )

        if self.config.runtime_adapter == "current_runtime":
            if self.config.prompt_id not in ALLOWED_CURRENT_RUNTIME_PROMPTS:
                raise ValueError(
                    f"Current runtime adapter executes frozen prompt {sorted(ALLOWED_CURRENT_RUNTIME_PROMPTS)}, "
                    f"but config requested '{self.config.prompt_id}'."
                )
            if abs(self.config.temperature - 0.7) > 1e-4 or self.config.max_tokens != 800:
                raise ValueError(
                    f"Current runtime adapter executes temperature=0.7, max_tokens=800, "
                    f"but config declared temperature={self.config.temperature}, max_tokens={self.config.max_tokens}."
                )
            if self.config.generation_context_top_k != 4:
                raise ValueError(
                    f"Current runtime adapter executes generation_context_top_k=4, "
                    f"but config declared generation_context_top_k={self.config.generation_context_top_k}."
                )
            if self.config.generation_model and self.config.generation_model != settings.LLM_MODEL:
                raise ValueError(
                    f"Current runtime adapter executes settings.LLM_MODEL ('{settings.LLM_MODEL}'), "
                    f"but config declared generation_model '{self.config.generation_model}'. "
                    f"Align environment or configuration to guarantee executed identity."
                )



    def retrieve(self, question: str, top_k: int) -> list[RetrievalResult]:
        """Embed question, query Chroma, and map raw results to RetrievalResult."""
        query_vector = self.embedder.embed_query(question)
        raw_items = self.vector_store.search_similar(query_vector, top_k=top_k)
        return [map_chroma_result(item) for item in raw_items]

    def generate(
        self, question: str, top_k: int
    ) -> tuple[GeneratedAnswer, tuple[RetrievalResult, ...]]:
        """Generate an answer while recording the exact ranked evidence used.

        A RecordingVectorStoreProxy wraps the real store so the KnowledgeRetriever
        path captures every raw search result feeding generation. Retrieval,
        context assembly, and generation reuse the exact online RAG contracts.
        """
        proxy = RecordingVectorStoreProxy(self.vector_store)
        retriever = KnowledgeRetriever(
            embedder=self.embedder,
            vector_store=proxy,
            top_k=top_k,
            collection_name=self.config.collection_name,
        )
        assembler = ContextAssembler()
        generator = LLMGenerator()

        bundle = assembler.assemble(retriever.retrieve(question))
        answer = generator.generate(question, bundle)

        return answer, bundle.evidence


class StructuredRuntimeAdapter:
    """Connects the evaluation runner to the structured RAG candidate runtime.

    Executes the same KnowledgeRetriever / ContextAssembler / LLMGenerator
    contracts as the online facade, identified by the versioned prompt
    rag-structured-prompt-v1 owned by backend.rag.generation.llm. No prompt or
    context logic is duplicated here.
    """

    def __init__(
        self,
        config: RunConfig,
        embedder: Any = None,
        vector_store: Any = None,
    ) -> None:
        self.config = config
        self.embedder = embedder or VectorEmbedder(model_name=config.embedding_model)
        self.vector_store = vector_store or ChromaVectorStore(
            collection_name=config.collection_name
        )

        if self.config.prompt_id not in ALLOWED_STRUCTURED_RUNTIME_PROMPTS:
            raise ValueError(
                f"Structured runtime adapter executes frozen prompt {sorted(ALLOWED_STRUCTURED_RUNTIME_PROMPTS)}, "
                f"but config requested '{self.config.prompt_id}'."
            )
        if abs(self.config.temperature - 0.7) > 1e-4 or self.config.max_tokens != 800:
            raise ValueError(
                f"Structured runtime adapter executes temperature=0.7, max_tokens=800, "
                f"but config declared temperature={self.config.temperature}, max_tokens={self.config.max_tokens}."
            )
        if self.config.generation_context_top_k != 4:
            raise ValueError(
                f"Structured runtime adapter executes generation_context_top_k=4, "
                f"but config declared generation_context_top_k={self.config.generation_context_top_k}."
            )
        if self.config.generation_model and self.config.generation_model != settings.LLM_MODEL:
            raise ValueError(
                f"Structured runtime adapter executes settings.LLM_MODEL ('{settings.LLM_MODEL}'), "
                f"but config declared generation_model '{self.config.generation_model}'. "
                f"Align environment or configuration to guarantee executed identity."
            )

    def retrieve(self, question: str, top_k: int) -> list[RetrievalResult]:
        """Embed question, query Chroma, and map raw results to RetrievalResult."""
        retriever = KnowledgeRetriever(
            embedder=self.embedder,
            vector_store=self.vector_store,
            top_k=top_k,
            collection_name=self.config.collection_name,
        )
        return retriever.retrieve(question)

    def generate(
        self, question: str, top_k: int
    ) -> tuple[GeneratedAnswer, tuple[RetrievalResult, ...]]:
        """Generate an answer through the shared structured contracts."""
        retriever = KnowledgeRetriever(
            embedder=self.embedder,
            vector_store=self.vector_store,
            top_k=top_k,
            collection_name=self.config.collection_name,
        )
        assembler = ContextAssembler()
        generator = LLMGenerator()

        bundle = assembler.assemble(retriever.retrieve(question))
        answer = generator.generate(question, bundle)

        return answer, bundle.evidence


def preflight(
    dataset: EvaluationDataset | str,
    config: RunConfig | Mapping[str, Any] | str,
    mode: str = "retrieval",
) -> None:
    """Pre-run environmental and contract validation before governed execution.

    Raises:
        ValueError: On dataset/config schema errors or infrastructure failures.
    """
    # 1. Dataset validation
    if isinstance(dataset, (str, bytes)):
        from pathlib import Path
        dataset_obj = load_dataset(Path(dataset))
    elif isinstance(dataset, EvaluationDataset):
        dataset_obj = dataset
    else:
        raise ValueError("Invalid dataset type passed to preflight.")

    if not dataset_obj.examples:
        raise ValueError("preflight failed: dataset contains no examples.")

    # 2. Config validation
    mode_normalized = mode.lower().strip()
    if isinstance(config, (str, bytes)):
        from pathlib import Path
        import json
        config_dict = json.loads(Path(config).read_text(encoding="utf-8"))
        config_obj = validate_run_config(config_dict)
    elif isinstance(config, Mapping):
        config_obj = validate_run_config(config)
    elif isinstance(config, RunConfig):
        config_obj = config
    else:
        raise ValueError("Invalid config type passed to preflight.")

    if config_obj.runtime_adapter == "current_runtime":
        if config_obj.prompt_id not in ALLOWED_CURRENT_RUNTIME_PROMPTS:
            raise ValueError(
                f"preflight failed: Current runtime adapter executes frozen prompt "
                f"{sorted(ALLOWED_CURRENT_RUNTIME_PROMPTS)}, but config declared '{config_obj.prompt_id}'."
            )
        if abs(config_obj.temperature - 0.7) > 1e-4 or config_obj.max_tokens != 800:
            raise ValueError(
                f"preflight failed: Current runtime adapter executes temperature=0.7, max_tokens=800, "
                f"but config declared temperature={config_obj.temperature}, max_tokens={config_obj.max_tokens}."
            )
        if config_obj.generation_context_top_k != 4:
            raise ValueError(
                f"preflight failed: Current runtime adapter executes generation_context_top_k=4, "
                f"but config declared generation_context_top_k={config_obj.generation_context_top_k}."
            )
        if mode_normalized == "full":
            if config_obj.generation_model and config_obj.generation_model != settings.LLM_MODEL:
                raise ValueError(
                    f"preflight failed: Current runtime adapter executes settings.LLM_MODEL ('{settings.LLM_MODEL}'), "
                    f"but config declared generation_model '{config_obj.generation_model}'. "
                    f"Align environment or configuration to guarantee executed identity."
                )

    if config_obj.runtime_adapter == "structured_runtime_v1":
        if config_obj.prompt_id not in ALLOWED_STRUCTURED_RUNTIME_PROMPTS:
            raise ValueError(
                f"preflight failed: Structured runtime adapter executes frozen prompt "
                f"{sorted(ALLOWED_STRUCTURED_RUNTIME_PROMPTS)}, but config declared '{config_obj.prompt_id}'."
            )
        if abs(config_obj.temperature - 0.7) > 1e-4 or config_obj.max_tokens != 800:
            raise ValueError(
                f"preflight failed: Structured runtime adapter executes temperature=0.7, max_tokens=800, "
                f"but config declared temperature={config_obj.temperature}, max_tokens={config_obj.max_tokens}."
            )
        if config_obj.generation_context_top_k != 4:
            raise ValueError(
                f"preflight failed: Structured runtime adapter executes generation_context_top_k=4, "
                f"but config declared generation_context_top_k={config_obj.generation_context_top_k}."
            )
        if mode_normalized == "full":
            if config_obj.generation_model and config_obj.generation_model != settings.LLM_MODEL:
                raise ValueError(
                    f"preflight failed: Structured runtime adapter executes settings.LLM_MODEL ('{settings.LLM_MODEL}'), "
                    f"but config declared generation_model '{config_obj.generation_model}'. "
                    f"Align environment or configuration to guarantee executed identity."
                )

    # 3. Embedding model check
    embedder = VectorEmbedder(model_name=config_obj.embedding_model)
    if not HAS_SENTENCE_TRANSFORMERS or embedder.model is None:
        raise ValueError(
            f"infrastructure_failure: SentenceTransformer model '{config_obj.embedding_model}' "
            "is not available or sentence-transformers is not installed. "
            "Dummy embeddings are forbidden in governed evaluation."
        )

    # 4. Chroma index count check
    store = ChromaVectorStore(collection_name=config_obj.collection_name)
    count = store.count()
    if count <= 0:
        raise ValueError(
            f"infrastructure_failure: Chroma collection '{config_obj.collection_name}' "
            f"is missing or empty (count={count}). An indexed corpus is required."
        )

    # 5. Full mode checks (credentials and model)
    if mode_normalized == "full":
        if not settings.GITHUB_TOKEN:
            raise ValueError(
                "infrastructure_failure: GITHUB_TOKEN is missing in environment. "
                "A configured external model credential is required for full mode."
            )
        if not config_obj.judge:
            raise ValueError(
                "preflight failed: RunConfig must declare a judge configuration for full mode."
            )
        if not config_obj.generation_model:
            raise ValueError(
                "preflight failed: RunConfig generation_model is required for full mode."
            )
