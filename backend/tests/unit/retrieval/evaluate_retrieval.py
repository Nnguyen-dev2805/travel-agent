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
from backend.rag.query_understanding import (
    ParsedQuery,
    QueryFilters,
    QwenQueryParser,
    apply_metadata_bonus,
    build_query_filters,
)
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


def json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if value not in (None, "") else ""


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
    metadata_context: Optional[Dict[str, Any]] = None,
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
    if metadata_context:
        row.update(metadata_context)

    for k in k_values:
        relevant_at_k = sum(relevance[:k])
        row[f"hit@{k}"] = 1 if relevant_at_k > 0 else 0
        row[f"recall@{k}"] = relevant_at_k / total_relevant if total_relevant else 0.0
        row[f"precision@{k}"] = relevant_at_k / k if k else 0.0
        row[f"mrr@{k}"] = reciprocal_rank(relevance, k)
        row[f"ndcg@{k}"] = ndcg_at_k(relevance, total_relevant, k)
        row[f"relevant@{k}"] = relevant_at_k

    return row


def build_ranking_trace(
    query_item: Dict[str, Any],
    retriever_name: str,
    results: List[Dict[str, Any]],
    metadata_context: Optional[Dict[str, Any]] = None,
    top_n: int = 5,
) -> Dict[str, Any]:
    """Build an audit record containing the original query and top-n results."""
    rel_sets = benchmark_relevance_sets(query_item)
    top_results: List[Dict[str, Any]] = []

    for rank, result in enumerate(results[:top_n], start=1):
        metadata = result.get("metadata") or {}
        ids = result_ids(result)
        top_results.append(
            {
                "rank": rank,
                "chunk_id": ids["chunk_id"],
                "parent_id": ids["parent_id"],
                "document_id": ids["document_id"],
                "title": metadata.get("title", ""),
                "url": metadata.get("url", ""),
                "heading": metadata.get("heading", ""),
                "locations": metadata.get("locations", ""),
                "category": metadata.get("category", ""),
                "score": result.get("score"),
                "retriever": result.get("retriever", retriever_name),
                "reranker": result.get("reranker"),
                "rerank_score": result.get("rerank_score"),
                "rerank_rank": result.get("rerank_rank"),
                "rerank_error": result.get("rerank_error"),
                "pre_rerank_score": result.get("pre_rerank_score"),
                "pre_rerank_retriever": result.get("pre_rerank_retriever"),
                "is_relevant": is_relevant(result, rel_sets),
                "text_preview": str(result.get("text") or "")[:500],
            }
        )

    trace = {
        "query_id": query_item.get("query_id"),
        "query": query_item.get("query"),
        "retriever": retriever_name,
        "top_n": top_n,
        "benchmark_query": query_item,
        "expected": {
            "relevant_chunk_ids": sorted(rel_sets["chunk_ids"]),
            "relevant_parent_ids": sorted(rel_sets["parent_ids"]),
            "relevant_document_ids": sorted(rel_sets["document_ids"]),
            "gold_facts": query_item.get("gold_facts", []),
        },
        "top_results": top_results,
    }
    if metadata_context:
        trace["metadata_filter"] = metadata_context
    return trace


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
        candidate_counts = [
            float(row["metadata_candidate_count"])
            for row in group_rows
            if row.get("metadata_candidate_count") not in (None, "")
        ]
        candidate_ratios = [
            float(row["metadata_candidate_ratio"])
            for row in group_rows
            if row.get("metadata_candidate_ratio") not in (None, "")
        ]
        if candidate_counts:
            record["avg_metadata_candidate_count"] = round(mean(candidate_counts), 2)
        if candidate_ratios:
            record["avg_metadata_candidate_ratio"] = round(mean(candidate_ratios), 4)
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
        metadata_filter: bool = False,
        metadata_bonus: bool = False,
        metadata_parser_fail_open: bool = False,
    ) -> None:
        self.retrievers = retrievers
        self.candidate_k = candidate_k
        self.k_values = k_values
        self.max_k = max(k_values)
        self.rerank = rerank
        self.metadata_filter = metadata_filter
        self.metadata_bonus = metadata_bonus
        self.metadata_parser_fail_open = metadata_parser_fail_open
        self.embedder = VectorEmbedder()
        self.vector_store = ChromaVectorStore(collection_name=settings.RAG_COLLECTION_NAME)
        self.bm25_store: Optional[ElasticsearchBM25Store] = None
        self.hybrid_retriever: Optional[HybridRetriever] = None
        self.reranker: Optional[TEICrossEncoderReranker] = None
        self.query_parser: Optional[QwenQueryParser] = None
        self.total_chunks = self.vector_store.count()

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

        if self.metadata_filter:
            self.query_parser = QwenQueryParser(
                base_url=settings.QUERY_PARSER_BASE_URL,
                api_key=settings.QUERY_PARSER_API_KEY,
                model=settings.QUERY_PARSER_MODEL,
                timeout_seconds=settings.QUERY_PARSER_TIMEOUT_SECONDS,
            )

    @staticmethod
    def base_retriever_name(retriever: str) -> str:
        return retriever[:-7] if retriever.endswith("_rerank") else retriever

    def parse_query_metadata(self, query: str) -> ParsedQuery:
        if not self.metadata_filter or self.query_parser is None:
            return ParsedQuery(raw_query=query, parser="disabled")
        try:
            return self.query_parser.parse(query)
        except Exception as err:
            if not self.metadata_parser_fail_open:
                raise RuntimeError(
                    f"Metadata parser failed for query={query!r}. "
                    "Check QUERY_PARSER_BASE_URL / Modal vLLM server, or pass "
                    "--metadata-parser-fail-open to continue with language-only fallback."
                ) from err
            logger.warning("Metadata parser failed for query=%r: %s", query, err)
            return ParsedQuery(
                raw_query=query,
                language=settings.QUERY_PARSER_DEFAULT_LANGUAGE,
                parser="fallback_after_parse_error",
            )

    def build_metadata_context(
        self,
        parsed_query: ParsedQuery,
        query_filters: Optional[QueryFilters],
        raw_query_filters: Optional[QueryFilters] = None,
        raw_candidate_count: Optional[int] = None,
        minimum_prefilter_candidates: Optional[int] = None,
        fallback_reason: str = "",
    ) -> Dict[str, Any]:
        if not self.metadata_filter or query_filters is None:
            return {
                "metadata_filter_enabled": False,
                "metadata_candidate_count": "",
                "metadata_candidate_ratio": "",
            }

        chroma_where = query_filters.chroma_where()
        elasticsearch_filters = query_filters.elasticsearch_filters()
        candidate_count = self.count_chroma_candidates(chroma_where)
        candidate_ratio = candidate_count / self.total_chunks if self.total_chunks else 0.0
        raw_filters = raw_query_filters or query_filters
        raw_chroma_where = raw_filters.chroma_where()
        raw_elasticsearch_filters = raw_filters.elasticsearch_filters()
        raw_count = raw_candidate_count if raw_candidate_count is not None else candidate_count

        return {
            "metadata_filter_enabled": True,
            "metadata_prefilter_applied": bool(chroma_where or elasticsearch_filters),
            "metadata_candidate_count": candidate_count,
            "metadata_candidate_ratio": round(candidate_ratio, 6),
            "metadata_raw_candidate_count": raw_count,
            "metadata_raw_candidate_ratio": round(raw_count / self.total_chunks, 6) if self.total_chunks else 0.0,
            "metadata_minimum_prefilter_candidates": minimum_prefilter_candidates or "",
            "metadata_prefilter_fallback_reason": fallback_reason,
            "metadata_total_chunks": self.total_chunks,
            "parsed_language": parsed_query.language or "",
            "parsed_locations": ", ".join(parsed_query.locations),
            "expanded_locations": ", ".join(raw_filters.location_cities),
            "parsed_regions": ", ".join(parsed_query.regions),
            "parsed_category": ", ".join(parsed_query.category),
            "parsed_topic": parsed_query.topic or "",
            "parsed_entity_type": ", ".join(parsed_query.entity_type),
            "parsed_content_type": parsed_query.content_type or "",
            "parsed_content_type_required": parsed_query.content_type_required,
            "parser_confidence": parsed_query.confidence,
            "parser": parsed_query.parser,
            "chroma_where": json_cell(chroma_where),
            "elasticsearch_filters": json_cell(elasticsearch_filters),
            "raw_chroma_where": json_cell(raw_chroma_where),
            "raw_elasticsearch_filters": json_cell(raw_elasticsearch_filters),
        }

    def count_chroma_candidates(self, chroma_where: Optional[Dict[str, Any]]) -> int:
        if not chroma_where:
            return self.total_chunks

        try:
            matches = self.vector_store.collection.get(where=chroma_where, include=[])
        except (TypeError, ValueError):
            matches = self.vector_store.collection.get(where=chroma_where, include=["metadatas"])
        return len(matches.get("ids") or [])

    def minimum_prefilter_candidates(self) -> int:
        return max(self.candidate_k, self.max_k, settings.RERANKER_CANDIDATE_K)

    def resolve_metadata_prefilter(
        self,
        query_filters: Optional[QueryFilters],
    ) -> tuple[Optional[QueryFilters], int, int, str]:
        if not self.metadata_filter or query_filters is None:
            return query_filters, self.total_chunks, self.total_chunks, ""

        chroma_where = query_filters.chroma_where()
        elasticsearch_filters = query_filters.elasticsearch_filters()
        raw_candidate_count = self.count_chroma_candidates(chroma_where)
        if not chroma_where and not elasticsearch_filters:
            return query_filters, raw_candidate_count, raw_candidate_count, ""

        minimum_candidates = self.minimum_prefilter_candidates()
        if raw_candidate_count < minimum_candidates:
            reason = f"candidate_count {raw_candidate_count} < k_candidate {minimum_candidates}"
            return QueryFilters(), raw_candidate_count, self.total_chunks, reason

        return query_filters, raw_candidate_count, raw_candidate_count, ""

    def search(
        self,
        query: str,
        query_embedding: Optional[List[float]],
        retriever: str,
        query_filters: Optional[QueryFilters] = None,
        parsed_query: Optional[ParsedQuery] = None,
    ) -> List[Dict[str, Any]]:
        base_retriever = self.base_retriever_name(retriever)
        should_rerank = self.rerank or retriever.endswith("_rerank")
        retrieval_k = max(self.max_k, settings.RERANKER_CANDIDATE_K) if should_rerank else self.max_k
        chroma_where = query_filters.chroma_where() if query_filters else None
        elasticsearch_filters = query_filters.elasticsearch_filters() if query_filters else None

        if base_retriever == "dense":
            if query_embedding is None:
                raise RuntimeError("Dense retrieval requires a query embedding.")
            results = self.vector_store.search_similar(query_embedding, top_k=retrieval_k, where=chroma_where)
        elif base_retriever == "bm25":
            if self.bm25_store is None:
                raise RuntimeError("BM25 store was not initialized.")
            results = self.bm25_store.search(query, top_k=retrieval_k, filters=elasticsearch_filters)
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
                filters=elasticsearch_filters,
                chroma_where=chroma_where,
            )
        else:
            raise ValueError(f"Unsupported retriever: {retriever}")

        if should_rerank:
            if self.reranker is None:
                raise RuntimeError("Reranker was not initialized.")
            reranked = self.reranker.rerank(query, results, top_k=self.max_k, fail_open=True)
            if self.metadata_bonus and parsed_query is not None:
                return apply_metadata_bonus(
                    reranked,
                    parsed_query,
                    cross_encoder_weight=settings.METADATA_BONUS_CROSS_ENCODER_WEIGHT,
                    metadata_weight=settings.METADATA_BONUS_WEIGHT,
                    top_k=self.max_k,
                )
            return reranked

        return results

    def evaluate(self, queries: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        metric_rows: List[Dict[str, Any]] = []
        ranking_trace_rows: List[Dict[str, Any]] = []
        for index, query_item in enumerate(queries, start=1):
            query = str(query_item.get("query") or "").strip()
            if not query:
                continue

            logger.info("[%s/%s] Evaluating query_id=%s", index, len(queries), query_item.get("query_id"))
            parsed_query = self.parse_query_metadata(query)
            query_filters = (
                build_query_filters(parsed_query, default_language=settings.QUERY_PARSER_DEFAULT_LANGUAGE)
                if self.metadata_filter
                else None
            )
            active_query_filters, raw_candidate_count, active_candidate_count, fallback_reason = (
                self.resolve_metadata_prefilter(query_filters)
            )
            metadata_context = self.build_metadata_context(
                parsed_query,
                active_query_filters,
                raw_query_filters=query_filters,
                raw_candidate_count=raw_candidate_count,
                minimum_prefilter_candidates=self.minimum_prefilter_candidates(),
                fallback_reason=fallback_reason,
            )
            if self.metadata_filter:
                logger.info(
                    "[%s/%s] Metadata candidates: %s/%s raw=%s; locations=%s; expanded=%s; fallback=%s",
                    index,
                    len(queries),
                    metadata_context["metadata_candidate_count"],
                    metadata_context["metadata_total_chunks"],
                    raw_candidate_count,
                    metadata_context["parsed_locations"] or "-",
                    metadata_context["expanded_locations"] or "-",
                    metadata_context["metadata_prefilter_fallback_reason"] or "-",
                )
            query_embedding = None
            if any(self.base_retriever_name(retriever) in ("dense", "hybrid") for retriever in self.retrievers):
                query_embedding = self.embedder.embed_query(query)

            for retriever in self.retrievers:
                results = self.search(query, query_embedding, retriever, active_query_filters, parsed_query)
                metric_rows.append(compute_metrics(query_item, retriever, results, self.k_values, metadata_context))
                ranking_trace = build_ranking_trace(query_item, retriever, results, metadata_context, top_n=5)
                if any(item.get("is_relevant") for item in ranking_trace["top_results"]):
                    ranking_trace_rows.append(ranking_trace)

        return metric_rows, ranking_trace_rows


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
    parser.add_argument(
        "--metadata-filter",
        action="store_true",
        help="Parse each query with Qwen and apply language/content_type/location metadata filters before retrieval.",
    )
    parser.add_argument(
        "--metadata-bonus",
        action="store_true",
        help="After reranking, apply FinalScore = cross_encoder_weight * CrossEncoder + metadata_weight * Metadata.",
    )
    parser.add_argument(
        "--metadata-parser-fail-open",
        action="store_true",
        help="Continue with language-only fallback if Qwen metadata parsing fails.",
    )
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
        metadata_filter=args.metadata_filter,
        metadata_bonus=args.metadata_bonus,
        metadata_parser_fail_open=args.metadata_parser_fail_open,
    )
    metric_rows, ranking_trace_rows = runner.evaluate(queries)
    summary_rows = summarize(metric_rows, k_values)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "query_metrics.csv", metric_rows)
    write_csv(args.output_dir / "summary_metrics.csv", summary_rows)

    top5_by_method: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in ranking_trace_rows:
        top5_by_method[str(item.get("retriever") or "unknown")].append(item)

    top5_files: Dict[str, Dict[str, Any]] = {}
    for method, rows in sorted(top5_by_method.items()):
        output_path = args.output_dir / f"top5_rankings_{method}.json"
        write_json(output_path, rows)
        top5_files[method] = {
            "path": str(output_path),
            "records": len(rows),
        }

    write_json(
        args.output_dir / "top5_rankings.json",
        {
            "description": "Index of per-method top-5 hit ranking files. Each per-method file only contains query/method cases with at least one relevant result in top 5.",
            "files": top5_files,
        },
    )
    write_json(
        args.output_dir / "summary_metrics.json",
        {
            "dataset": str(args.dataset),
            "query_count": len(queries),
            "retrievers": retrievers,
            "k_values": k_values,
            "candidate_k": args.candidate_k,
            "rerank": args.rerank,
            "metadata_filter": args.metadata_filter,
            "metadata_bonus": args.metadata_bonus,
            "metadata_parser_fail_open": args.metadata_parser_fail_open,
            "top5_rankings_index_path": str(args.output_dir / "top5_rankings.json"),
            "top5_rankings_by_method": top5_files,
            "top5_hit_records": len(ranking_trace_rows),
            "summary": summary_rows,
        },
    )

    print(json.dumps(summary_rows, ensure_ascii=False, indent=2))
    logger.info("Reports written to %s.", args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
