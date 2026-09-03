"""Automated RAG Evaluation & Benchmark Comparison Framework."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple, Set

from backend.rag.embedding import VectorEmbedder
from backend.rag.retrieval import ChromaVectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("rag_evaluator")

ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_JSON_TESTSET = ROOT_DIR / "data" / "evaluation" / "datasets" / "retrieval_benchmark_1405_testset.json"
DEFAULT_JSONL_TESTSET = ROOT_DIR / "data" / "evaluation" / "datasets" / "llm_judge_500_queries.jsonl"
REPORTS_DIR = ROOT_DIR / "docs" / "reports" / "retrieval_chunk_comparison"
REPORT_MARKDOWN_PATH = REPORTS_DIR / "retrieval_chunk_comparison_metrics.md"
K_VALUES = [1, 3, 5, 10, 20]


def normalize_url(url: Any) -> str:
    """Normalize URL string for exact comparison."""
    if not url or not isinstance(url, str):
        return ""
    return url.strip().rstrip("/")


def reciprocal_rank(relevant_ranks: List[int], k: int) -> float:
    """Compute Reciprocal Rank for the first relevant result within top-k."""
    for rank in relevant_ranks:
        if rank <= k:
            return 1.0 / rank
    return 0.0


def dcg_at_k(relevance: List[int], k: int) -> float:
    """Compute binary DCG@k."""
    total = 0.0
    for index, rel in enumerate(relevance[:k], start=1):
        if rel:
            total += 1.0 / math.log2(index + 1)
    return total


def ndcg_at_k(relevance: List[int], k: int) -> float:
    """Compute binary nDCG@k."""
    relevant_total = sum(1 for val in relevance if val)
    if relevant_total == 0:
        return 0.0
    ideal_relevant = [1] * min(relevant_total, k)
    ideal_dcg = dcg_at_k(ideal_relevant, k)
    if ideal_dcg == 0:
        return 0.0
    return dcg_at_k(relevance, k) / ideal_dcg


def source_url_hit(results: List[Dict[str, Any]], expected_url: str, k: int) -> int:
    """Return 1 when expected source URL appears in top-k."""
    if not expected_url:
        return 0
    for item in results[:k]:
        meta = item.get("metadata") or {}
        item_url = item.get("source_url") or meta.get("source_url") or meta.get("url")
        if normalize_url(item_url) == expected_url:
            return 1
    return 0


class RAGEvaluator:
    """Evaluates and compares RAG Retrieval Performance between Baseline and Parent-Child strategies."""

    def __init__(
        self,
        eval_path: Optional[Path] = None,
        baseline_store: Optional[ChromaVectorStore] = None,
        parent_child_store: Optional[ChromaVectorStore] = None,
    ) -> None:
        self.eval_path = eval_path or (DEFAULT_JSON_TESTSET if DEFAULT_JSON_TESTSET.exists() else DEFAULT_JSONL_TESTSET)
        self.embedder = VectorEmbedder(model_name="BAAI/bge-m3")
        self._baseline_store = baseline_store
        self._parent_child_store = parent_child_store

    @property
    def baseline_store(self) -> ChromaVectorStore:
        if self._baseline_store is None:
            self._baseline_store = ChromaVectorStore(collection_name="vietnam_travel_knowledge")
        return self._baseline_store

    @property
    def parent_child_store(self) -> ChromaVectorStore:
        if self._parent_child_store is None:
            self._parent_child_store = ChromaVectorStore(collection_name="vietnam_travel_parent_child")
        return self._parent_child_store


    def load_eval_queries(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Load evaluation queries from JSON or JSONL testset."""
        queries: List[Dict[str, Any]] = []
        if not self.eval_path.exists():
            logger.warning(f"Eval dataset file not found at {self.eval_path}.")
            return queries

        if self.eval_path.suffix == ".json":
            with self.eval_path.open("r", encoding="utf-8") as f:
                raw_data = json.load(f)
                items = raw_data if isinstance(raw_data, list) else [raw_data]
                for raw in items:
                    q_text = raw.get("question") or raw.get("query") or raw.get("user_query") or raw.get("text")
                    if not q_text:
                        continue
                    queries.append({
                        "query_id": raw.get("query_id") or f"q_{len(queries)+1}",
                        "question": q_text,
                        "query_type": raw.get("query_type", "general"),
                        "category": raw.get("category", "Uncategorized"),
                        "url_group": raw.get("url_group", "unknown"),
                        "expected_document_id": str(raw.get("expected_document_id") or raw.get("document_id") or ""),
                        "expected_document_title": raw.get("expected_document_title") or raw.get("title") or "",
                        "expected_source_url": raw.get("expected_source_url") or raw.get("source_url") or "",
                        "expected_keywords": raw.get("expected_keywords") or raw.get("locations") or [],
                    })
                    if limit is not None and len(queries) >= limit:
                        break
        else:
            with self.eval_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    raw = json.loads(line)
                    q_text = raw.get("question") or raw.get("query") or raw.get("user_query") or raw.get("text")
                    if not q_text:
                        continue
                    queries.append({
                        "query_id": raw.get("query_id") or f"q_{len(queries)+1}",
                        "question": q_text,
                        "query_type": raw.get("query_type", "general"),
                        "category": raw.get("category", "Uncategorized"),
                        "url_group": raw.get("url_group", "unknown"),
                        "expected_document_id": str(raw.get("expected_document_id") or raw.get("document_id") or ""),
                        "expected_document_title": raw.get("expected_document_title") or raw.get("title") or "",
                        "expected_source_url": raw.get("expected_source_url") or raw.get("source_url") or "",
                        "expected_keywords": raw.get("expected_keywords") or raw.get("locations") or [],
                    })
                    if limit is not None and len(queries) >= limit:
                        break
        return queries

    def compute_query_metrics(
        self,
        query_item: Dict[str, Any],
        results: List[Dict[str, Any]],
        chunk_strategy: str,
        k_values: List[int] = K_VALUES,
    ) -> Dict[str, Any]:
        """Compute all 7 evaluation metrics across k_values for one query."""
        expected_doc_id = str(query_item.get("expected_document_id") or "")
        expected_url = normalize_url(query_item.get("expected_source_url"))

        relevance: List[int] = []
        for item in results:
            meta = item.get("metadata") or {}
            doc_id = str(meta.get("document_id") or meta.get("doc_id") or meta.get("id") or "")
            # Strict 1-Tier Match: Exact Document ID matching
            if expected_doc_id and doc_id and doc_id == expected_doc_id:
                relevance.append(1)
            else:
                relevance.append(0)

        relevant_ranks = [rank for rank, val in enumerate(relevance, start=1) if val]
        first_rank = relevant_ranks[0] if relevant_ranks else None

        metrics: Dict[str, Any] = {
            "query_id": query_item.get("query_id"),
            "question": query_item.get("question"),
            "query_type": query_item.get("query_type"),
            "category": query_item.get("category"),
            "url_group": query_item.get("url_group"),
            "expected_document_id": expected_doc_id,
            "expected_document_title": query_item.get("expected_document_title"),
            "chunk_strategy": chunk_strategy,
            "first_relevant_rank": first_rank,
            "retrieved_count": len(results),
        }

        for k in k_values:
            top_k = results[:k]
            relevant_count = sum(relevance[:k])
            unique_docs: Set[str] = set()
            for item in top_k:
                meta = item.get("metadata") or {}
                d_id = str(meta.get("document_id") or meta.get("id") or "")
                if d_id:
                    unique_docs.add(d_id)

            metrics[f"hit@{k}"] = 1 if relevant_count > 0 else 0
            metrics[f"mrr@{k}"] = reciprocal_rank(relevant_ranks, k)
            metrics[f"ndcg@{k}"] = ndcg_at_k(relevance, k)
            metrics[f"precision@{k}"] = relevant_count / k if k > 0 else 0.0
            metrics[f"relevant_chunks@{k}"] = relevant_count
            metrics[f"unique_docs@{k}"] = len(unique_docs)
            metrics[f"source_url_hit@{k}"] = source_url_hit(results, expected_url, k)

        return metrics

    def evaluate_benchmark(
        self, sample_limit: Optional[int] = None, k_values: List[int] = K_VALUES
    ) -> Dict[str, Any]:
        """Run full evaluation benchmark measuring 7 metrics across k_values and export CSV reports."""
        queries = self.load_eval_queries(limit=sample_limit)
        max_k = max(k_values)
        logger.info(f"Loaded {len(queries)} queries for benchmark evaluation (max_k={max_k}).")

        all_query_metrics: List[Dict[str, Any]] = []

        for idx, q_item in enumerate(queries, 1):
            q_text = q_item["question"]
            if not q_text:
                continue

            q_embed = self.embedder.embed_query(q_text)

            # 1. Baseline Search
            b_results = self.baseline_store.search_similar(q_embed, top_k=max_k)
            b_metrics = self.compute_query_metrics(q_item, b_results, chunk_strategy="baseline_fixed_1000ch", k_values=k_values)
            all_query_metrics.append(b_metrics)

            # 2. Parent-Child Search
            pc_results = self.parent_child_store.search_similar(q_embed, top_k=max_k)
            pc_metrics = self.compute_query_metrics(q_item, pc_results, chunk_strategy="semantic_parent_child", k_values=k_values)
            all_query_metrics.append(pc_metrics)

        # Export CSVs and generate markdown report
        summary_data = self.export_reports(all_query_metrics, k_values=k_values)
        return summary_data

    def export_reports(
        self, all_query_metrics: List[Dict[str, Any]], k_values: List[int] = K_VALUES
    ) -> Dict[str, Any]:
        """Aggregate metrics and export CSV breakdown reports."""
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        # 1. Summary By Run (Baseline vs Parent-Child)
        summary_by_run: List[Dict[str, Any]] = []
        for strategy in ["baseline_fixed_1000ch", "semantic_parent_child"]:
            rows = [r for r in all_query_metrics if r["chunk_strategy"] == strategy]
            q_count = len(rows) if rows else 1
            record: Dict[str, Any] = {"chunk_strategy": strategy, "query_count": q_count}
            for k in k_values:
                for metric in ("hit", "mrr", "ndcg", "precision", "relevant_chunks", "unique_docs", "source_url_hit"):
                    m_key = f"{metric}@{k}"
                    vals = [r[m_key] for r in rows if m_key in r]
                    record[m_key] = round(mean(vals), 4) if vals else 0.0
            summary_by_run.append(record)

        self._write_csv(REPORTS_DIR / "summary_by_run.csv", summary_by_run)

        # 2. Summary By Category
        summary_by_category = self._aggregate_by_group(all_query_metrics, "category", k_values)
        self._write_csv(REPORTS_DIR / "summary_by_category.csv", summary_by_category)

        # 3. Summary By URL Group
        summary_by_url_group = self._aggregate_by_group(all_query_metrics, "url_group", k_values)
        self._write_csv(REPORTS_DIR / "summary_by_url_group.csv", summary_by_url_group)

        # 4. Top Failures at Top-20 (Hit@20 == 0)
        top_failures = [r for r in all_query_metrics if r.get("hit@20") == 0]
        self._write_csv(REPORTS_DIR / "top_failures_at_20.csv", top_failures[:200])

        summary_dict = {
            "queries_count": len(all_query_metrics) // 2,
            "reports_directory": str(REPORTS_DIR),
            "runs": summary_by_run,
        }

        self.generate_report(summary_by_run, len(all_query_metrics) // 2)
        return summary_dict

    def _aggregate_by_group(
        self, rows: List[Dict[str, Any]], group_field: str, k_values: List[int]
    ) -> List[Dict[str, Any]]:
        """Aggregate query metrics by metadata group field."""
        grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for r in rows:
            key = (r["chunk_strategy"], str(r.get(group_field) or "unknown"))
            grouped[key].append(r)

        output: List[Dict[str, Any]] = []
        for (strategy, g_val), group_rows in sorted(grouped.items()):
            rec: Dict[str, Any] = {
                "chunk_strategy": strategy,
                group_field: g_val,
                "query_count": len(group_rows),
            }
            for k in k_values:
                for metric in ("hit", "mrr", "ndcg", "precision"):
                    m_key = f"{metric}@{k}"
                    vals = [r[m_key] for r in group_rows if m_key in r]
                    rec[m_key] = round(mean(vals), 4) if vals else 0.0
            output.append(rec)
        return output

    def _write_csv(self, path: Path, rows: List[Dict[str, Any]]) -> None:
        """Write list of dicts to CSV with UTF-8 encoding."""
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames = list(rows[0].keys())
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Exported CSV report to {path}")

    def generate_report(self, summary_by_run: List[Dict[str, Any]], total_queries: int) -> None:
        """Generate Markdown benchmark metrics report."""
        REPORT_MARKDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)

        b_run = next((r for r in summary_by_run if r["chunk_strategy"] == "baseline_fixed_1000ch"), {})
        pc_run = next((r for r in summary_by_run if r["chunk_strategy"] == "semantic_parent_child"), {})

        lines = [
            "# Báo Cáo Đánh Giá Chi Tiết Retrieval RAG: Baseline vs Parent-Child Strategy",
            "",
            "## 1. Kết Quả Đo Đạc Tổng Thể (7 Chỉ Số trên các Mức K)",
            "",
            f"Tập dữ liệu kiểm thử: `{self.eval_path.name}` ({total_queries} test queries)",
            "",
            "### 📌 1.1. Bảng So Sánh Hit Rate & MRR",
            "",
            "| Mức K | Hit Rate (Baseline) | Hit Rate (Parent-Child) | Hit Rate Gain | MRR (Baseline) | MRR (Parent-Child) | MRR Gain |",
            "|---|:---:|:---:|:---:|:---:|:---:|:---:|",
        ]

        for k in K_VALUES:
            b_hit = b_run.get(f"hit@{k}", 0.0) * 100
            b_mrr = b_run.get(f"mrr@{k}", 0.0)

            pc_hit = pc_run.get(f"hit@{k}", 0.0) * 100
            pc_mrr = pc_run.get(f"mrr@{k}", 0.0)

            delta_hit = round(pc_hit - b_hit, 2)
            delta_mrr = round(pc_mrr - b_mrr, 4)

            lines.append(
                f"| **K={k}** | {b_hit:.2f}% | **{pc_hit:.2f}%** | **+{delta_hit}%** | {b_mrr:.4f} | **{pc_mrr:.4f}** | **+{delta_mrr:.4f}** |"
            )

        lines.extend([
            "",
            "### 📌 1.2. Bảng So Sánh NDCG & Precision",
            "",
            "| Mức K | NDCG (Baseline) | NDCG (Parent-Child) | NDCG Gain | Precision (Baseline) | Precision (Parent-Child) | Precision Gain |",
            "|---|:---:|:---:|:---:|:---:|:---:|:---:|",
        ])

        for k in K_VALUES:
            b_ndcg = b_run.get(f"ndcg@{k}", 0.0)
            b_prec = b_run.get(f"precision@{k}", 0.0) * 100

            pc_ndcg = pc_run.get(f"ndcg@{k}", 0.0)
            pc_prec = pc_run.get(f"precision@{k}", 0.0) * 100

            delta_ndcg = round(pc_ndcg - b_ndcg, 4)
            delta_prec = round(pc_prec - b_prec, 2)

            lines.append(
                f"| **K={k}** | {b_ndcg:.4f} | **{pc_ndcg:.4f}** | **+{delta_ndcg:.4f}** | {b_prec:.2f}% | **{pc_prec:.2f}%** | **+{delta_prec}%** |"
            )

        lines.extend([
            "",
            "## 2. Báo Cáo Xuất CSV Chi Tiết",
            "",
            f"Tất cả các file báo cáo CSV chi tiết đã được tự động lưu vào thư mục: `{REPORTS_DIR}`",
            "",
            "1. **`summary_by_run.csv`**: Bảng tổng hợp đầy đủ 7 metric trên 5 mức K.",
            "2. **`summary_by_category.csv`**: Phân tích hiệu năng theo từng danh mục bài viết (`Nightlife`, `Food`, `Beach`...).",
            "3. **`summary_by_url_group.csv`**: Phân tích hiệu năng theo nhóm đường dẫn (`things-to-do`, `plan-your-trip`...).",
            "4. **`top_failures_at_20.csv`**: Danh sách các câu hỏi bị thất bại (Hit@20 = 0) để phục vụ công tác audit dữ liệu.",
        ])

        REPORT_MARKDOWN_PATH.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Benchmark markdown report generated at {REPORT_MARKDOWN_PATH}")


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description="Automated RAG Evaluation Benchmark with Full Metrics & CSV Export.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of queries to evaluate.")
    parser.add_argument("--dataset", type=str, default=None, help="Path to evaluation dataset.")
    return parser.parse_args()


def main() -> int:
    """CLI Main Entry Point."""
    args = parse_args()
    eval_path = Path(args.dataset) if args.dataset else None
    evaluator = RAGEvaluator(eval_path=eval_path)
    res = evaluator.evaluate_benchmark(sample_limit=args.limit)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
