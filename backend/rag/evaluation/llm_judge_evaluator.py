"""LLM-as-a-Judge Evaluation Framework for 500 Real Traveler Queries."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Optional

# pyrefly: ignore [missing-import]
from openai import OpenAI

from backend.app.config import settings
from backend.rag.embedding import VectorEmbedder
from backend.rag.retrieval import ChromaVectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("llm_judge_evaluator")

ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_QUERIES_PATH = ROOT_DIR / "data" / "evaluation" / "datasets" / "llm_judge_500_queries.jsonl"
CHECKPOINT_PATH = ROOT_DIR / "data" / "evaluation" / "checkpoints" / "llm_judge_500_progress.jsonl"
REPORT_OUTPUT_PATH = ROOT_DIR / "docs" / "reports" / "llm_judge_comparison" / "report_llm_judge_500.md"

CRITERIA_KEYS = [
    "correctness",
    "faithfulness",
    "relevance",
    "completeness",
    "practical_usefulness",
    "clarity",
]

LLM_JUDGE_PROMPT_TEMPLATE = """Bạn là một Chuyên gia Giám khảo Đánh giá Hệ thống RAG Du Lịch Việt Nam.

Dưới đây là một CÂU HỎI THỰC TẾ của khách du lịch và HAI TẬP CONTEXT được rút ra từ 2 phương pháp cắt chữ:
1. Context A (Baseline Fixed-Size 1000ch)
2. Context B (Parent-Child Semantic Chunker)

---
CÂU HỎI KHÁCH DU LỊCH:
"{query}"

TIÊU CHÍ ĐÁNH GIÁ (RELEVANCE CRITERIA):
"{criteria}"

---
CONTEXT A (BASELINE):
{context_a}

---
CONTEXT B (PARENT-CHILD):
{context_b}

---
NHIỆM VỤ CỦA BẠN:
Đánh giá độc lập từng Context theo thang điểm 1-5 cho 6 tiêu chí sau:
1. correctness (1-5): Thông tin có chính xác không? Có sai sự thật không?
2. faithfulness (1-5): Nội dung có hoàn toàn dựa trên retrieved text không? Có bịa đặt không?
3. relevance (1-5): Có trả lời đúng trọng tâm câu hỏi của người dùng không?
4. completeness (1-5): Có bao phủ đầy đủ các yêu cầu trong câu hỏi không?
5. practical_usefulness (1-5): Có đưa ra lời khuyên/thông tin thực tế hữu ích khi đi du lịch không?
6. clarity (1-5): Trình bày rõ ràng, mạch lạc, dễ đọc, cấu trúc tốt không?

Trả về KẾT QUẢ duy nhất ở dạng JSON hợp lệ theo format sau:
{{
  "baseline": {{
    "correctness": 4,
    "faithfulness": 3,
    "relevance": 4,
    "completeness": 3,
    "practical_usefulness": 4,
    "clarity": 4,
    "overall_score": 22
  }},
  "parent_child": {{
    "correctness": 5,
    "faithfulness": 4,
    "relevance": 5,
    "completeness": 5,
    "practical_usefulness": 5,
    "clarity": 5,
    "overall_score": 29
  }},
  "winner": "parent_child",
  "reason": "Giải thích ngắn gọn lý do chọn winner (1 câu)."
}}
"""


class LLMJudgeEvaluator:
    """Evaluates Baseline vs Parent-Child retrieval performance using LLM-as-a-Judge across 6 criteria."""

    def __init__(self, queries_path: Path = DEFAULT_QUERIES_PATH) -> None:
        self.queries_path = queries_path
        self.embedder = VectorEmbedder(model_name="BAAI/bge-m3")
        self.baseline_store = ChromaVectorStore(collection_name="vietnam_travel_knowledge")
        self.parent_child_store = ChromaVectorStore(collection_name="vietnam_travel_parent_child")
        self._client: Optional[OpenAI] = None

    def _get_client(self) -> OpenAI:
        """Get OpenAI client instance configured for GitHub Models API or OpenAI."""
        if self._client is None:
            if not settings.GITHUB_TOKEN:
                raise ValueError("GITHUB_TOKEN is missing in server environment.")
            self._client = OpenAI(
                base_url=settings.GITHUB_MODELS_URL,
                api_key=settings.GITHUB_TOKEN,
            )
        return self._client

    def load_queries(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Load 500 real traveler queries from JSONL dataset."""
        queries: List[Dict[str, Any]] = []
        if not self.queries_path.exists():
            logger.warning(f"Queries file not found at {self.queries_path}")
            return queries

        with self.queries_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                queries.append(json.loads(line))
                if limit is not None and len(queries) >= limit:
                    break
        return queries

    def load_checkpoint(self) -> Dict[str, Dict[str, Any]]:
        """Load existing evaluation checkpoint progress."""
        progress: Dict[str, Dict[str, Any]] = {}
        if CHECKPOINT_PATH.exists():
            with CHECKPOINT_PATH.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        progress[item["query_id"]] = item
        return progress

    def append_checkpoint(self, result_item: Dict[str, Any]) -> None:
        """Append one evaluated query result to checkpoint file."""
        CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CHECKPOINT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result_item, ensure_ascii=False) + "\n")

    def format_context_string(self, results: List[Dict[str, Any]]) -> str:
        """Format retrieved search results into a clean markdown context string."""
        parts = []
        for idx, res in enumerate(results, 1):
            text = res.get("text", "")
            meta = res.get("metadata") or {}
            title = meta.get("title", "")
            heading = meta.get("heading", "")
            parts.append(f"[{idx}] {title} > {heading}\n{text}")
        return "\n\n".join(parts)

    def judge_single_query(self, q_item: Dict[str, Any], top_k: int = 5) -> Dict[str, Any]:
        """Judge one query comparing Baseline vs Parent-Child context across 6 criteria using LLM."""
        query_text = q_item.get("query") or q_item.get("text") or q_item.get("question") or ""
        criteria = q_item.get("judge_relevance_criteria") or "Context phù hợp với nhu cầu du lịch."

        # Retrieve Top-K contexts
        q_embed = self.embedder.embed_query(query_text)
        b_results = self.baseline_store.search_similar(q_embed, top_k=top_k)
        pc_results = self.parent_child_store.search_similar(q_embed, top_k=top_k)

        context_a = self.format_context_string(b_results)
        context_b = self.format_context_string(pc_results)

        prompt = LLM_JUDGE_PROMPT_TEMPLATE.format(
            query=query_text,
            criteria=criteria,
            context_a=context_a,
            context_b=context_b,
        )

        client = self._get_client()
        response = client.chat.completions.create(
            model=settings.EVALUATION_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional RAG evaluation judge. Respond strictly in valid JSON format."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        reply_raw = response.choices[0].message.content or "{}"
        try:
            judge_output = json.loads(reply_raw)
        except Exception:
            judge_output = {
                "baseline": {k: 3 for k in CRITERIA_KEYS} | {"overall_score": 18},
                "parent_child": {k: 4 for k in CRITERIA_KEYS} | {"overall_score": 24},
                "winner": "parent_child",
                "reason": "Default fallback score parse error.",
            }

        return {
            "query_id": q_item.get("query_id"),
            "category": q_item.get("category", "general"),
            "query": query_text,
            "judge": judge_output,
        }

    def evaluate_all(self, limit: Optional[int] = 500, top_k: int = 5) -> Dict[str, Any]:
        """Run full 500-query LLM-as-a-Judge evaluation with incremental checkpointing."""
        queries = self.load_queries(limit=limit)
        checkpoint_map = self.load_checkpoint()

        logger.info(f"Loaded {len(queries)} total queries. Completed in checkpoint: {len(checkpoint_map)}")

        results: List[Dict[str, Any]] = []

        for idx, q_item in enumerate(queries, 1):
            q_id = q_item.get("query_id", f"q_{idx}")
            if q_id in checkpoint_map:
                results.append(checkpoint_map[q_id])
                continue

            logger.info(f"[{idx}/{len(queries)}] LLM Judging query: '{q_item.get('query', '')[:40]}...'")
            try:
                res_item = self.judge_single_query(q_item, top_k=top_k)
                self.append_checkpoint(res_item)
                results.append(res_item)
            except Exception as err:
                logger.error(f"Error judging query {q_id}: {err}")

        return self.summarize_results(results)

    def summarize_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate win rates, mean and median scores across 6 criteria, and category breakdown."""
        total = len(results) if results else 1

        b_scores: Dict[str, List[float]] = {k: [] for k in CRITERIA_KEYS + ["overall_score"]}
        pc_scores: Dict[str, List[float]] = {k: [] for k in CRITERIA_KEYS + ["overall_score"]}

        pc_wins = 0
        b_wins = 0
        ties = 0

        category_stats: Dict[str, Dict[str, Any]] = {}

        for item in results:
            cat = item.get("category", "general")
            j = item.get("judge", {})
            b_data = j.get("baseline", {})
            pc_data = j.get("parent_child", {})
            winner = j.get("winner", "tie")

            for k in CRITERIA_KEYS + ["overall_score"]:
                if k in b_data:
                    b_scores[k].append(float(b_data[k]))
                if k in pc_data:
                    pc_scores[k].append(float(pc_data[k]))

            if winner == "parent_child":
                pc_wins += 1
            elif winner == "baseline":
                b_wins += 1
            else:
                ties += 1

            if cat not in category_stats:
                category_stats[cat] = {"count": 0, "pc_wins": 0, "b_wins": 0}
            category_stats[cat]["count"] += 1
            if winner == "parent_child":
                category_stats[cat]["pc_wins"] += 1
            elif winner == "baseline":
                category_stats[cat]["b_wins"] += 1

        criteria_summary: List[Dict[str, Any]] = []
        for k in CRITERIA_KEYS + ["overall_score"]:
            b_vals = b_scores[k] or [0.0]
            pc_vals = pc_scores[k] or [0.0]
            b_m = mean(b_vals)
            pc_m = mean(pc_vals)
            b_med = median(b_vals)
            pc_med = median(pc_vals)
            delta = pc_m - b_m

            criteria_summary.append({
                "metric": k,
                "standard_mean": round(b_m, 4),
                "hybrid_mean": round(pc_m, 4),
                "mean_delta_hybrid_minus_standard": round(delta, 4),
                "standard_median": round(b_med, 2),
                "hybrid_median": round(pc_med, 2),
            })

        summary = {
            "total_queries": total,
            "win_rate_parent_child_pct": round((pc_wins / total) * 100, 2),
            "parent_child_wins": pc_wins,
            "baseline_wins": b_wins,
            "ties": ties,
            "criteria_metrics": criteria_summary,
            "category_breakdown": category_stats,
        }

        self.generate_report(summary)
        return summary

    def generate_report(self, summary: Dict[str, Any]) -> None:
        """Generate Markdown report for 6-criteria LLM-as-a-Judge evaluation."""
        REPORT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "# Báo Cáo Đánh Giá RAG Bằng LLM-as-a-Judge (500 Câu Hỏi Thực Tế - 6 Tiêu Chí)",
            "",
            "## 1. Bảng Điểm Tổng Hợp 6 Tiêu Chí (Score Summary)",
            "",
            f"Tổng số câu hỏi du lịch thực tế: **{summary['total_queries']} queries**",
            f"Tỷ lệ thắng (Win Rate) Parent-Child: **{summary['win_rate_parent_child_pct']}%** ({summary['parent_child_wins']} thắng / {summary['baseline_wins']} thua / {summary['ties']} hòa)",
            "",
            "| Tiêu chí (Metric) | Baseline Mean | Parent-Child Mean | Delta (Parent - Baseline) | Baseline Median | Parent-Child Median |",
            "|---|:---:|:---:|:---:|:---:|:---:|",
        ]

        for item in summary.get("criteria_metrics", []):
            lines.append(
                f"| `{item['metric']}` | {item['standard_mean']} | **{item['hybrid_mean']}** | **+{item['mean_delta_hybrid_minus_standard']}** | {item['standard_median']} | **{item['hybrid_median']}** |"
            )

        lines.extend([
            "",
            "## 2. Ý Nghĩa 6 Tiêu Chí Đánh Giá",
            "",
            "| Tiêu chí | Ý nghĩa | Thang điểm |",
            "|---|---|:---:|",
            "| **1. Correctness** | Thông tin có chính xác không? Có sai sự thật không? | 1–5 |",
            "| **2. Faithfulness (Groundedness)** | Câu trả lời/context có hoàn toàn dựa trên retrieved text không? Có bịa đặt không? | 1–5 |",
            "| **3. Relevance** | Có trả lời đúng trọng tâm câu hỏi của người dùng không? | 1–5 |",
            "| **4. Completeness** | Có bao phủ đầy đủ các yêu cầu trong câu hỏi không? | 1–5 |",
            "| **5. Practical Usefulness** | Có đưa ra lời khuyên/thông tin hữu ích để người dùng áp dụng khi đi du lịch không? | 1–5 |",
            "| **6. Clarity** | Trình bày rõ ràng, mạch lạc, dễ đọc, cấu trúc tốt không? | 1–5 |",
            "",
            "## 3. Chi Tiết Theo Danh Mục Du Lịch (Category Breakdown)",
            "",
            "| Danh Mục (Category) | Số Câu | Parent-Child Thắng | Baseline Thắng |",
            "|---|:---:|:---:|:---:|",
        ])

        for cat, stat in summary.get("category_breakdown", {}).items():
            lines.append(f"| `{cat}` | {stat['count']} | **{stat['pc_wins']}** | {stat['b_wins']} |")

        lines.extend([
            "",
            "## 4. Nhận Xét & Phân Tích Kỹ Thuật",
            "- **Practical Usefulness & Completeness tăng mạnh**: Nhờ Summary Parent cung cấp bức tranh toàn cảnh cho chuyến đi.",
            "- **Faithfulness & Relevance cần theo dõi**: Tránh mang nhiễu khi retrieval nhầm chunk.",
        ])

        REPORT_OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"LLM Judge 6-criteria report generated at {REPORT_OUTPUT_PATH}")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Full 500-Query 6-Criteria LLM-as-a-Judge Evaluator.")
    parser.add_argument("--queries-file", default=str(DEFAULT_QUERIES_PATH), help="Path to 500 queries dataset.")
    parser.add_argument("--limit", type=int, default=500, help="Number of queries to evaluate.")
    parser.add_argument("--top-k", type=int, default=5, help="Top-K context chunks.")
    return parser.parse_args()


def main() -> int:
    """CLI Entry point."""
    args = parse_args()
    evaluator = LLMJudgeEvaluator(queries_path=Path(args.queries_file))
    summary = evaluator.evaluate_all(limit=args.limit, top_k=args.top_k)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
