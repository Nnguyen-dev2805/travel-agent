"""Evaluate dense and hybrid retrieval against a benchmark JSONL dataset."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.config import settings
from backend.rag.embedding import VectorEmbedder
from backend.rag.reranking import TEICrossEncoderReranker
from backend.rag.retrieval import ChromaVectorStore, ElasticsearchBM25Store, HybridRetriever

DEFAULT_DATASET = ROOT_DIR / "data" / "evaluation" / "datasets" / "retrieval_benchmark_generated.jsonl"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "test" / "retrieval" / "reports"
DEFAULT_K_VALUES = [1, 3, 5, 10, 20]

logger = logging.getLogger("retrieval_benchmark_eval")


def load_jsonl(path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("query"):
                records.append(item)
            if limit is not None and len(records) >= limit:
                break
    return records


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_id_list(value: Any) -> Set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, Iterable):
        return {str(item) for item in value if str(item)}
    return {str(value)}


def benchmark_relevance_sets(query_item: Dict[str, Any]) -> Dict[str, Set[str]]:
    chunk_ids = (
        normalize_id_list(query_item.get("relevant_chunk_ids"))
        | normalize_id_list(query_item.get("relevant_child_ids"))
        | normalize_id_list(query_item.get("source_chunk_id"))
    )
    parent_ids = (
        normalize_id_list(query_item.get("relevant_parent_ids"))
        | normalize_id_list(query_item.get("source_parent_id"))
    )
    document_ids = (
        normalize_id_list(query_item.get("relevant_document_ids"))
        | normalize_id_list(query_item.get("source_document_id"))
    )
    return {
        "chunk_ids": chunk_ids,
        "parent_ids": parent_ids,
        "document_ids": document_ids,
    }


def result_ids(result: Dict[str, Any]) -> Dict[str, str]:
    metadata = result.get("metadata") or {}
    return {
        "chunk_id": str(
            result.get("chunk_id")
            or metadata.get("child_id")
            or metadata.get("chunk_id")
            or ""
        ),
        "parent_id": str(metadata.get("parent_id") or ""),
        "document_id": str(metadata.get("document_id") or metadata.get("doc_id") or ""),
    }


def is_relevant(result: Dict[str, Any], rel: Dict[str, Set[str]]) -> bool:
    ids = result_ids(result)
    if rel["chunk_ids"]:
        return ids["chunk_id"] in rel["chunk_ids"]
    if rel["parent_ids"] and ids["parent_id"] in rel["parent_ids"]:
        return True
    if rel["document_ids"] and ids["document_id"] in rel["document_ids"]:
        return True
    return False


def dcg_at_k(relevance: Sequence[int], k: int) -> float:
    return sum(rel / math.log2(rank + 1) for rank, rel in enumerate(relevance[:k], start=1))


def ndcg_at_k(relevance: Sequence[int], total_relevant: int, k: int) -> float:
    if total_relevant <= 0:
        return 0.0
    ideal = [1] * min(total_relevant, k)
    ideal_dcg = dcg_at_k(ideal, k)
    return dcg_at_k(relevance, k) / ideal_dcg if ideal_dcg else 0.0


def reciprocal_rank(relevance: Sequence[int], k: int) -> float:
    for rank, rel in enumerate(relevance[:k], start=1):
        if rel:
            return 1.0 / rank
    return 0.0


def compute_metrics(
    query_item: Dict[str, Any],
    retriever_name: str,
    results: List[Dict[str, Any]],
    k_values: List[int],
) -> Dict[str, Any]:
    rel_sets = benchmark_relevance_sets(query_item)
    relevance = [1 if is_relevant(result, rel_sets) else 0 for result in results]
    total_relevant = max(
        len(rel_sets["chunk_ids"]) or len(rel_sets["parent_ids"]) or len(rel_sets["document_ids"]),
        1,
    )

    row: Dict[str, Any] = {
        "query_id": query_item.get("query_id"),
        "query": query_item.get("query"),
        "retriever": retriever_name,
        "intent": ",".join(query_item.get("intent") or []),
        "province": query_item.get("province", ""),
        "difficulty": query_item.get("difficulty", ""),
        "retrieved_count": len(results),
        "relevant_total": total_relevant,
        "first_relevant_rank": next((idx for idx, rel in enumerate(relevance, start=1) if rel), None),
        "top_title": ((results[0].get("metadata") or {}).get("title") if results else ""),
        "top_chunk_id": (result_ids(results[0])["chunk_id"] if results else ""),
    }

    for k in k_values:
        relevant_at_k = sum(relevance[:k])
        row[f"hit@{k}"] = 1 if relevant_at_k > 0 else 0
        row[f"recall@{k}"] = relevant_at_k / total_relevant if total_relevant else 0.0
        row[f"precision@{k}"] = relevant_at_k / k if k else 0.0
        row[f"mrr@{k}"] = reciprocal_rank(relevance, k)
        row[f"ndcg@{k}"] = ndcg_at_k(relevance, total_relevant, k)
        row[f"relevant@{k}"] = relevant_at_k

    return row


def summarize(rows: List[Dict[str, Any]], k_values: List[int]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["retriever"])].append(row)

    summary: List[Dict[str, Any]] = []
    for retriever, group_rows in sorted(grouped.items()):
        record: Dict[str, Any] = {
            "retriever": retriever,
            "query_count": len(group_rows),
        }
        for k in k_values:
            for metric in ("hit", "recall", "precision", "mrr", "ndcg"):
                key = f"{metric}@{k}"
                values = [float(row.get(key) or 0.0) for row in group_rows]
                record[key] = round(mean(values), 4) if values else 0.0
        summary.append(record)
    return summary


class RetrievalBenchmarkRunner:
    def __init__(
        self,
        retrievers: List[str],
        candidate_k: int,
        k_values: List[int],
        rerank: bool = False,
    ) -> None:
        self.retrievers = retrievers
        self.candidate_k = candidate_k
        self.k_values = k_values
        self.max_k = max(k_values)
        self.rerank = rerank
        self.embedder = VectorEmbedder()
        self.vector_store = ChromaVectorStore(collection_name=settings.RAG_COLLECTION_NAME)
        self.bm25_store: Optional[ElasticsearchBM25Store] = None
        self.hybrid_retriever: Optional[HybridRetriever] = None
        self.reranker: Optional[TEICrossEncoderReranker] = None

        base_retrievers = [self.base_retriever_name(retriever) for retriever in retrievers]

        if "bm25" in base_retrievers or "hybrid" in base_retrievers:
            self.bm25_store = ElasticsearchBM25Store(
                url=settings.ELASTICSEARCH_URL,
                index_name=settings.ELASTICSEARCH_INDEX,
                username=settings.ELASTICSEARCH_USERNAME,
                password=settings.ELASTICSEARCH_PASSWORD,
                api_key=settings.ELASTICSEARCH_API_KEY,
                verify_certs=settings.ELASTICSEARCH_VERIFY_CERTS,
                request_timeout=settings.ELASTICSEARCH_REQUEST_TIMEOUT,
            )

        if "hybrid" in base_retrievers:
            if self.bm25_store is None:
                raise RuntimeError("BM25 store was not initialized.")
            self.hybrid_retriever = HybridRetriever(
                vector_store=self.vector_store,
                bm25_store=self.bm25_store,
                candidate_k=candidate_k,
                rrf_k=settings.HYBRID_RRF_K,
                dense_weight=settings.HYBRID_DENSE_WEIGHT,
                bm25_weight=settings.HYBRID_BM25_WEIGHT,
            )

        if self.rerank or any(retriever.endswith("_rerank") for retriever in retrievers):
            self.reranker = TEICrossEncoderReranker(
                rerank_url=settings.TEI_RERANK_URL,
                timeout_seconds=settings.RERANKER_TIMEOUT_SECONDS,
                max_text_chars=settings.RERANKER_MAX_TEXT_CHARS,
                batch_size=settings.RERANKER_BATCH_SIZE,
                raw_scores=settings.RERANKER_RAW_SCORES,
            )

    @staticmethod
    def base_retriever_name(retriever: str) -> str:
        return retriever[:-7] if retriever.endswith("_rerank") else retriever

    def search(self, query: str, query_embedding: Optional[List[float]], retriever: str) -> List[Dict[str, Any]]:
        base_retriever = self.base_retriever_name(retriever)
        should_rerank = self.rerank or retriever.endswith("_rerank")
        retrieval_k = max(self.max_k, settings.RERANKER_CANDIDATE_K) if should_rerank else self.max_k

        if base_retriever == "dense":
            if query_embedding is None:
                raise RuntimeError("Dense retrieval requires a query embedding.")
            results = self.vector_store.search_similar(query_embedding, top_k=retrieval_k)
        elif base_retriever == "bm25":
            if self.bm25_store is None:
                raise RuntimeError("BM25 store was not initialized.")
            results = self.bm25_store.search(query, top_k=retrieval_k)
        elif base_retriever == "hybrid":
            if query_embedding is None:
                raise RuntimeError("Hybrid retrieval requires a query embedding.")
            if self.hybrid_retriever is None:
                raise RuntimeError("Hybrid retriever was not initialized.")
            results = self.hybrid_retriever.search(
                query,
                query_embedding,
                top_k=retrieval_k,
                candidate_k=self.candidate_k,
            )
        else:
            raise ValueError(f"Unsupported retriever: {retriever}")

        if should_rerank:
            if self.reranker is None:
                raise RuntimeError("Reranker was not initialized.")
            return self.reranker.rerank(query, results, top_k=self.max_k, fail_open=True)

        return results

    def evaluate(self, queries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        metric_rows: List[Dict[str, Any]] = []
        for index, query_item in enumerate(queries, start=1):
            query = str(query_item.get("query") or "").strip()
            if not query:
                continue

            logger.info("[%s/%s] Evaluating query_id=%s", index, len(queries), query_item.get("query_id"))
            query_embedding = None
            if any(self.base_retriever_name(retriever) in ("dense", "hybrid") for retriever in self.retrievers):
                query_embedding = self.embedder.embed_query(query)

            for retriever in self.retrievers:
                results = self.search(query, query_embedding, retriever)
                metric_rows.append(compute_metrics(query_item, retriever, results, self.k_values))

        return metric_rows


def parse_k_values(raw: str) -> List[int]:
    values = sorted({int(item.strip()) for item in raw.split(",") if item.strip()})
    if not values:
        raise ValueError("At least one k value is required.")
    return values


def parse_retrievers(raw: str) -> List[str]:
    values = [item.strip().lower() for item in raw.split(",") if item.strip()]
    allowed = {"bm25", "dense", "hybrid", "bm25_rerank", "dense_rerank", "hybrid_rerank"}
    invalid = [item for item in values if item not in allowed]
    if invalid:
        raise ValueError(f"Unsupported retrievers: {invalid}. Allowed: {sorted(allowed)}")
    return values or ["dense", "hybrid"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate dense and hybrid retrieval against generated benchmark JSONL.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--k-values", default="1,3,5,10,20")
    parser.add_argument("--retrievers", default="dense,hybrid", help="Comma-separated: bm25,dense,hybrid,dense_rerank,hybrid_rerank")
    parser.add_argument("--candidate-k", type=int, default=settings.HYBRID_CANDIDATE_K)
    parser.add_argument("--rerank", action="store_true", help="Apply TEI cross-encoder reranking to every selected retriever.")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    args = parse_args()
    k_values = parse_k_values(args.k_values)
    retrievers = parse_retrievers(args.retrievers)

    queries = load_jsonl(args.dataset, limit=args.limit)
    logger.info("Loaded %s benchmark queries from %s.", len(queries), args.dataset)

    runner = RetrievalBenchmarkRunner(
        retrievers=retrievers,
        candidate_k=args.candidate_k,
        k_values=k_values,
        rerank=args.rerank,
    )
    metric_rows = runner.evaluate(queries)
    summary_rows = summarize(metric_rows, k_values)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "query_metrics.csv", metric_rows)
    write_csv(args.output_dir / "summary_metrics.csv", summary_rows)
    write_json(
        args.output_dir / "summary_metrics.json",
        {
            "dataset": str(args.dataset),
            "query_count": len(queries),
            "retrievers": retrievers,
            "k_values": k_values,
            "candidate_k": args.candidate_k,
            "rerank": args.rerank,
            "summary": summary_rows,
        },
    )

    print(json.dumps(summary_rows, ensure_ascii=False, indent=2))
    logger.info("Reports written to %s.", args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
