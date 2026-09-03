"""Runtime adapters and preflight checks for governed R2 evaluation.

Per the approved RAG repair plan (Task 4 Step 6 & 7):
- CurrentRuntimeAdapter wraps the existing RAGService / ChromaVectorStore / VectorEmbedder.
- Uses RecordingVectorStoreProxy to capture the exact ranked evidence used by RAGService.generate_answer().
- Preflight validates dataset, run config, index existence/count, embedding model, and credentials.
- Missing index, model, or credentials produce infrastructure_failure rather than dummy fallbacks.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

from backend.app.config import settings
from backend.rag.contracts import CitationEvidence, GeneratedAnswer, RetrievalResult
from backend.rag.embedding import VectorEmbedder
from backend.rag.embedding.embedder import HAS_SENTENCE_TRANSFORMERS
from backend.rag.evaluation.dataset import load_dataset, validate_run_config
from backend.rag.evaluation.models import EvaluationDataset, RunConfig
from backend.rag.generation import RAGService
from backend.rag.retrieval import ChromaVectorStore
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


class CurrentRuntimeAdapter:
    """Connects the evaluation runner to the current RAG baseline runtime."""

    def __init__(
        self,
        config: RunConfig,
        embedder: Any = None,
        vector_store: Any = None,
        rag_service: Any = None,
    ) -> None:
        self.config = config
        self.embedder = embedder or VectorEmbedder(model_name=config.embedding_model)
        self.vector_store = vector_store or ChromaVectorStore(
            collection_name=config.collection_name
        )
        self._rag_service = rag_service

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
        """Generate answer via current RAGService while recording exact retrieved evidence."""
        rag = self._rag_service or RAGService(collection_name=self.config.collection_name)
        rag.embedder = self.embedder

        proxy = RecordingVectorStoreProxy(self.vector_store)
        rag.vector_store = proxy

        response = rag.generate_answer(question, top_k=top_k)
        evidence = tuple(map_chroma_result(item) for item in proxy.last_results)

        citations_list: list[CitationEvidence] = []
        for raw_c in response.get("citations", []):
            c_title = str(raw_c.get("title") or "")
            c_url = str(raw_c.get("url") or "")
            matching_ids = tuple(
                item.chunk_id
                for item in evidence
                if (c_url and item.url == c_url) or (c_title and item.title == c_title)
            )
            citations_list.append(
                CitationEvidence(
                    title=c_title,
                    url=c_url,
                    evidence_ids=matching_ids,
                )
            )

        answer = GeneratedAnswer(
            reply=str(response.get("reply") or ""),
            model=str(response.get("model") or self.config.generation_model),
            citations=tuple(citations_list),
        )
        return answer, evidence


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
