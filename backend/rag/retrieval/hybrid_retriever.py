"""Hybrid dense + BM25 retrieval using reciprocal rank fusion."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.rag.retrieval.elasticsearch_bm25 import ElasticsearchBM25Store
from backend.rag.retrieval.vector_store import ChromaVectorStore


class HybridRetriever:
    """Combine Chroma dense retrieval with Elasticsearch BM25 via weighted RRF."""

    def __init__(
        self,
        vector_store: ChromaVectorStore,
        bm25_store: ElasticsearchBM25Store,
        candidate_k: int = 30,
        rrf_k: int = 60,
        dense_weight: float = 0.65,
        bm25_weight: float = 0.35,
    ) -> None:
        self.vector_store = vector_store
        self.bm25_store = bm25_store
        self.candidate_k = candidate_k
        self.rrf_k = rrf_k
        self.dense_weight = dense_weight
        self.bm25_weight = bm25_weight

    @staticmethod
    def _result_key(result: Dict[str, Any]) -> str:
        metadata = result.get("metadata") or {}
        return str(result.get("chunk_id") or metadata.get("child_id") or metadata.get("chunk_id"))

    def search(
        self,
        query_text: str,
        query_embedding: List[float],
        top_k: int = 4,
        candidate_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return fused dense and BM25 search results."""
        limit = max(candidate_k or self.candidate_k, top_k)
        dense_results = self.vector_store.search_similar(query_embedding, top_k=limit)
        bm25_results = self.bm25_store.search(query_text, top_k=limit)

        fused: Dict[str, Dict[str, Any]] = {}

        for source_name, weight, results in (
            ("dense", self.dense_weight, dense_results),
            ("bm25", self.bm25_weight, bm25_results),
        ):
            for rank, result in enumerate(results, start=1):
                key = self._result_key(result)
                if not key:
                    continue
                if key not in fused:
                    fused[key] = {
                        "result": dict(result),
                        "score": 0.0,
                        "dense_rank": None,
                        "bm25_rank": None,
                        "dense_score": None,
                        "bm25_score": None,
                    }

                fused[key]["score"] += weight * (1.0 / (self.rrf_k + rank))
                fused[key][f"{source_name}_rank"] = rank
                fused[key][f"{source_name}_score"] = result.get("score")

                # Prefer dense payload if available because it comes directly from Chroma.
                if source_name == "dense":
                    fused[key]["result"] = dict(result)

        ranked = sorted(
            fused.values(),
            key=lambda item: (
                item["score"],
                -(item["dense_rank"] or 10**9),
                -(item["bm25_rank"] or 10**9),
            ),
            reverse=True,
        )

        final_results: List[Dict[str, Any]] = []
        for item in ranked[:top_k]:
            result = dict(item["result"])
            result.update(
                {
                    "score": round(float(item["score"]), 6),
                    "retriever": "hybrid_bm25_dense_rrf",
                    "dense_rank": item["dense_rank"],
                    "bm25_rank": item["bm25_rank"],
                    "dense_score": item["dense_score"],
                    "bm25_score": item["bm25_score"],
                }
            )
            final_results.append(result)

        return final_results
