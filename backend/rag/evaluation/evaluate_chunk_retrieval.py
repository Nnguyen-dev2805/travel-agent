"""Evaluate retrieval quality for Standard chunks vs Semantic Parent-Child chunks.

The testset `document_user_query_testset_en.json` is generated from source
documents and contains one expected document per query. This evaluator therefore
scores retrieval at document level: a retrieved chunk is relevant when its
`document_id` equals `expected_document_id`.

Metrics include:
    - hit@k / recall@k: expected document appears in top-k retrieved chunks.
    - mrr@k: reciprocal rank of the first chunk from the expected document.
    - ndcg@k: binary nDCG using chunks from the expected document as relevant.
    - precision@k: fraction of top-k chunks from the expected document.
    - relevant_chunks@k: number of top-k chunks from the expected document.
    - unique_docs@k: number of unique documents represented in top-k.

Run examples:
    python -m backend.rag.evaluation.evaluate_chunk_retrieval --limit 50
    python -m backend.rag.evaluation.evaluate_chunk_retrieval --retrievers dense hybrid --k-values 1 3 5 10 20
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.rag.retrieval.baseline_retrievers import RetrieverConfig, build_retrievers


DEFAULT_TESTSET_PATH = Path("data/evaluation/document_user_query_testset_en.json")
DEFAULT_OUTPUT_DIR = Path("report/evaluate/retrieval_chunk_comparison")
DEFAULT_MODEL_ID = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_STANDARD_INDEX = Path("data/indexes/paraphrase-multilingual-MiniLM-L12-v2_standard_rag")
DEFAULT_SEMANTIC_INDEX = Path("data/indexes/paraphrase-multilingual-MiniLM-L12-v2_semantic_parent_child")


@dataclass(frozen=True)
class RetrievalRun:
    """A retrieval configuration to evaluate."""

    chunk_strategy: str
    retriever_name: str
    index_dir: Path


def configure_runtime() -> None:
    """Keep SentenceTransformers on PyTorch and print UTF-8 safely on Windows."""

    os.environ["TRANSFORMERS_NO_TF"] = "1"
    os.environ["USE_TF"] = "0"
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def load_json(path: Path) -> Any:
    """Load UTF-8 JSON with BOM tolerance."""

    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_testset(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    """Load the document-derived English query testset."""

    data = load_json(path)
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("queries") or data.get("results") or data.get("data") or []
    else:
        raise ValueError(f"Unsupported testset JSON shape: {path}")

    if not isinstance(rows, list):
        raise ValueError(f"Could not find a list of queries in: {path}")
    if limit is not None:
        rows = rows[:limit]
    return rows


def normalize_url(url: Any) -> str:
    """Normalize URL for equality checks."""

    return str(url or "").strip().rstrip("/").lower()


def get_query_text(row: dict[str, Any]) -> str:
    """Extract the English query string from one test row."""

    for key in ("question", "query_en", "question_en", "query"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def reciprocal_rank(ranks: list[int], k: int) -> float:
    """Return reciprocal rank for the first relevant result within k."""

    for rank in ranks:
        if rank <= k:
            return 1.0 / rank
    return 0.0


def dcg_at_k(relevance: list[int], k: int) -> float:
    """Compute binary DCG@k."""

    total = 0.0
    for index, rel in enumerate(relevance[:k], start=1):
        if rel:
            total += 1.0 / math.log2(index + 1)
    return total


def ndcg_at_k(relevance: list[int], k: int) -> float:
    """Compute binary nDCG@k."""

    relevant_total = sum(1 for value in relevance if value)
    if relevant_total == 0:
        return 0.0
    ideal_relevant = [1] * min(relevant_total, k)
    ideal_dcg = dcg_at_k(ideal_relevant, k)
    if ideal_dcg == 0:
        return 0.0
    return dcg_at_k(relevance, k) / ideal_dcg


def source_url_hit(results: list[dict[str, Any]], expected_url: str, k: int) -> int:
    """Return 1 when expected source URL appears in top-k."""

    if not expected_url:
        return 0
    for item in results[:k]:
        if normalize_url(item.get("source_url")) == expected_url:
            return 1
    return 0


def metric_values_for_query(
    row: dict[str, Any],
    results: list[dict[str, Any]],
    k_values: list[int],
) -> dict[str, Any]:
    """Compute retrieval metrics for one query and one run."""

    expected_document_id = str(row.get("expected_document_id") or "")
    expected_url = normalize_url(row.get("expected_source_url"))
    relevance = [1 if str(item.get("document_id") or "") == expected_document_id else 0 for item in results]
    relevant_ranks = [rank for rank, value in enumerate(relevance, start=1) if value]
    first_rank = relevant_ranks[0] if relevant_ranks else None

    metrics: dict[str, Any] = {
        "first_relevant_rank": first_rank,
        "top1_document_id": results[0].get("document_id") if results else None,
        "top1_document_title": results[0].get("document_title") if results else None,
        "top1_source_url": results[0].get("source_url") if results else None,
        "top1_chunk_id": results[0].get("chunk_id") if results else None,
        "retrieved_count": len(results),
    }

    for k in k_values:
        top_k = results[:k]
        relevant_count = sum(relevance[:k])
        unique_docs = {str(item.get("document_id") or "") for item in top_k if item.get("document_id")}
        metrics[f"hit@{k}"] = 1 if relevant_count > 0 else 0
        metrics[f"recall@{k}"] = 1 if relevant_count > 0 else 0
        metrics[f"mrr@{k}"] = reciprocal_rank(relevant_ranks, k)
        metrics[f"ndcg@{k}"] = ndcg_at_k(relevance, k)
        metrics[f"precision@{k}"] = relevant_count / k if k else 0.0
        metrics[f"relevant_chunks@{k}"] = relevant_count
        metrics[f"unique_docs@{k}"] = len(unique_docs)
        metrics[f"source_url_hit@{k}"] = source_url_hit(results, expected_url, k)

    return metrics


def compact_result(item: dict[str, Any]) -> dict[str, Any]:
    """Keep enough result metadata for auditing failures without huge text fields."""

    return {
        "rank": item.get("rank"),
        "score": item.get("score"),
        "retriever": item.get("retriever"),
        "chunk_id": item.get("chunk_id"),
        "document_id": item.get("document_id"),
        "document_title": item.get("document_title"),
        "source_url": item.get("source_url"),
        "language": item.get("language"),
        "word_count": item.get("word_count"),
        "matched_sources": item.get("matched_sources"),
        "text_preview": " ".join(str(item.get("source_text") or "").split())[:280],
    }


def build_retriever_for_run(
    run: RetrievalRun,
    model_id: str,
    registry_path: Path,
    device: str,
):
    """Build and select the requested retriever for one run."""

    dense, bm25, hybrid = build_retrievers(
        RetrieverConfig(
            registry_path=registry_path,
            model_id=model_id,
            index_dir=run.index_dir,
            device=device,
        )
    )
    retrievers = {"dense": dense, "bm25": bm25, "hybrid": hybrid}
    return retrievers[run.retriever_name]


def search_with_retriever(retriever: Any, retriever_name: str, query: str, top_k: int, candidate_k: int) -> list[dict[str, Any]]:
    """Search using a dense, BM25, or hybrid retriever."""

    if retriever_name == "hybrid":
        return retriever.search(query, top_k=top_k, candidate_k=candidate_k)
    return retriever.search(query, top_k=top_k)


def evaluate_run(
    run: RetrievalRun,
    queries: list[dict[str, Any]],
    k_values: list[int],
    model_id: str,
    registry_path: Path,
    device: str,
    candidate_k: int,
    include_results: bool,
) -> list[dict[str, Any]]:
    """Evaluate one retrieval run over all queries."""

    max_k = max(k_values)
    search_k = max(max_k, candidate_k)
    retriever = build_retriever_for_run(run, model_id, registry_path, device)
    rows: list[dict[str, Any]] = []
    started = time.time()

    for index, query_row in enumerate(queries, start=1):
        query = get_query_text(query_row)
        if not query:
            continue
        results = search_with_retriever(
            retriever=retriever,
            retriever_name=run.retriever_name,
            query=query,
            top_k=max_k,
            candidate_k=search_k,
        )
        metrics = metric_values_for_query(query_row, results, k_values)
        row = {
            "query_id": query_row.get("query_id") or f"query_{index:05d}",
            "question": query,
            "chunk_strategy": run.chunk_strategy,
            "retriever": run.retriever_name,
            "expected_document_id": query_row.get("expected_document_id"),
            "expected_document_title": query_row.get("expected_document_title"),
            "expected_source_url": query_row.get("expected_source_url"),
            "query_type": query_row.get("query_type"),
            "category": query_row.get("category"),
            "url_group": query_row.get("url_group"),
            "source_domain": query_row.get("source_domain"),
            **metrics,
        }
        if include_results:
            row["top_results"] = [compact_result(item) for item in results]
        rows.append(row)

        if index % 100 == 0:
            elapsed = round(time.time() - started, 1)
            print(f"{run.chunk_strategy}/{run.retriever_name}: {index}/{len(queries)} queries in {elapsed}s")

    return rows


def mean_metric(rows: list[dict[str, Any]], metric: str) -> float:
    """Mean of a numeric metric over rows."""

    values = [float(row[metric]) for row in rows if isinstance(row.get(metric), (int, float))]
    return mean(values) if values else 0.0


def summarize_run(rows: list[dict[str, Any]], k_values: list[int]) -> dict[str, Any]:
    """Aggregate metrics for one chunk strategy + retriever run."""

    if not rows:
        return {}
    summary: dict[str, Any] = {
        "chunk_strategy": rows[0]["chunk_strategy"],
        "retriever": rows[0]["retriever"],
        "query_count": len(rows),
    }
    metric_names = ["first_relevant_rank"]
    for k in k_values:
        metric_names.extend(
            [
                f"hit@{k}",
                f"recall@{k}",
                f"mrr@{k}",
                f"ndcg@{k}",
                f"precision@{k}",
                f"relevant_chunks@{k}",
                f"unique_docs@{k}",
                f"source_url_hit@{k}",
            ]
        )
    for metric in metric_names:
        values = [row.get(metric) for row in rows if isinstance(row.get(metric), (int, float))]
        if values:
            summary[metric] = round(mean(float(value) for value in values), 6)
    no_hit_count = sum(1 for row in rows if not row.get(f"hit@{max(k_values)}"))
    summary[f"miss_count@{max(k_values)}"] = no_hit_count
    return summary


def summarize_by_group(
    rows: list[dict[str, Any]],
    group_field: str,
    k_values: list[int],
) -> list[dict[str, Any]]:
    """Aggregate run metrics by query metadata group."""

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            str(row.get("chunk_strategy") or ""),
            str(row.get("retriever") or ""),
            str(row.get(group_field) or "unknown"),
        )
        grouped[key].append(row)

    output: list[dict[str, Any]] = []
    for (chunk_strategy, retriever, group_value), group_rows in sorted(grouped.items()):
        record = {
            "chunk_strategy": chunk_strategy,
            "retriever": retriever,
            group_field: group_value,
            "query_count": len(group_rows),
        }
        for k in k_values:
            for metric in (f"hit@{k}", f"mrr@{k}", f"ndcg@{k}", f"precision@{k}"):
                record[metric] = round(mean_metric(group_rows, metric), 6)
        output.append(record)
    return output


def compare_strategies(per_query_rows: list[dict[str, Any]], k_values: list[int]) -> list[dict[str, Any]]:
    """Compare standard vs semantic per query for the same retriever."""

    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in per_query_rows:
        key = (str(row["retriever"]), str(row["query_id"]), str(row["chunk_strategy"]))
        by_key[key] = row

    comparisons: list[dict[str, Any]] = []
    retrievers = sorted({str(row["retriever"]) for row in per_query_rows})
    query_ids = sorted({str(row["query_id"]) for row in per_query_rows})
    for retriever in retrievers:
        for query_id in query_ids:
            standard = by_key.get((retriever, query_id, "standard"))
            semantic = by_key.get((retriever, query_id, "semantic_parent_child"))
            if not standard or not semantic:
                continue
            record = {
                "query_id": query_id,
                "retriever": retriever,
                "question": standard.get("question"),
                "query_type": standard.get("query_type"),
                "category": standard.get("category"),
                "url_group": standard.get("url_group"),
                "expected_document_id": standard.get("expected_document_id"),
                "expected_document_title": standard.get("expected_document_title"),
                "standard_first_relevant_rank": standard.get("first_relevant_rank"),
                "semantic_first_relevant_rank": semantic.get("first_relevant_rank"),
            }
            for k in k_values:
                for metric_prefix in ("hit", "mrr", "ndcg", "precision"):
                    metric = f"{metric_prefix}@{k}"
                    standard_value = standard.get(metric)
                    semantic_value = semantic.get(metric)
                    record[f"standard_{metric}"] = standard_value
                    record[f"semantic_{metric}"] = semantic_value
                    if isinstance(standard_value, (int, float)) and isinstance(semantic_value, (int, float)):
                        record[f"{metric}_delta_semantic_minus_standard"] = round(
                            float(semantic_value) - float(standard_value),
                            6,
                        )
            max_k = max(k_values)
            delta = record.get(f"hit@{max_k}_delta_semantic_minus_standard")
            record[f"winner_hit@{max_k}"] = (
                "semantic_parent_child" if delta and delta > 0 else "standard" if delta and delta < 0 else "tie"
            )
            comparisons.append(record)
    return comparisons


def top_failures(rows: list[dict[str, Any]], max_k: int, limit: int = 200) -> list[dict[str, Any]]:
    """Return miss cases for auditing."""

    failures = [row for row in rows if not row.get(f"hit@{max_k}")]
    return failures[:limit]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write list of dict rows to CSV with UTF-8 BOM for Excel compatibility."""

    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key == "top_results":
                continue
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write rows as JSONL."""

    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    """Render a compact Markdown table."""

    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        values = [str(row.get(column, "")) for column in columns]
        values = [value.replace("|", "\\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_markdown_report(path: Path, summary_rows: list[dict[str, Any]], comparison_rows: list[dict[str, Any]], k_values: list[int]) -> None:
    """Write human-readable retrieval comparison report."""

    max_k = max(k_values)
    win_counts = Counter(row.get(f"winner_hit@{max_k}") for row in comparison_rows)
    lines = [
        "# Chunk Retrieval Evaluation",
        "",
        "## Summary",
        "",
        f"- Compared query rows: {len(comparison_rows)} per retriever/strategy pair",
        f"- Main ground truth: `expected_document_id`",
        f"- Primary metric: `hit@{max_k}` / `recall@{max_k}` document-level",
        "",
        "## Run Metrics",
        "",
        markdown_table(
            summary_rows,
            [
                "chunk_strategy",
                "retriever",
                "query_count",
                "hit@1",
                f"hit@{max_k}",
                f"mrr@{max_k}",
                f"ndcg@{max_k}",
                f"precision@{max_k}",
                f"miss_count@{max_k}",
            ],
        ),
        "",
        f"## Winner Counts By hit@{max_k}",
        "",
        json.dumps(dict(win_counts), ensure_ascii=False, indent=2),
        "",
        "## Notes",
        "",
        "- `hit@k` and `recall@k` are identical here because each query has one expected document.",
        "- `precision@k` is chunk-level and can be biased by chunk granularity; use it as a secondary signal.",
        "- `unique_docs@k` helps identify whether a retriever spreads results across many documents or stays concentrated.",
        "- Semantic parent-child retrieval is still evaluated by child chunk hits mapped back to `document_id`.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="Evaluate retrieval for Standard vs Semantic Parent-Child chunks.")
    parser.add_argument("--testset", type=Path, default=DEFAULT_TESTSET_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--registry", type=Path, default=Path("configs/embedding_models.json"))
    parser.add_argument("--standard-index", type=Path, default=DEFAULT_STANDARD_INDEX)
    parser.add_argument("--semantic-index", type=Path, default=DEFAULT_SEMANTIC_INDEX)
    parser.add_argument("--device", default=os.getenv("RAG_EMBEDDING_DEVICE", "cpu"))
    parser.add_argument("--retrievers", nargs="+", default=["dense", "bm25", "hybrid"], choices=["dense", "bm25", "hybrid"])
    parser.add_argument("--k-values", nargs="+", type=int, default=[1, 3, 5, 10, 20])
    parser.add_argument("--candidate-k", type=int, default=80)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--include-results", action="store_true", help="Store compact top-k retrieved chunks in JSONL.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force HuggingFace/Transformers offline mode. Use when the embedding model is already cached locally.",
    )
    return parser.parse_args()


def main() -> int:
    """Run retrieval evaluation."""

    configure_runtime()
    args = parse_args()
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    k_values = sorted(set(args.k_values))
    queries = load_testset(args.testset, args.limit)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    runs = [
        RetrievalRun("standard", retriever_name, args.standard_index)
        for retriever_name in args.retrievers
    ] + [
        RetrievalRun("semantic_parent_child", retriever_name, args.semantic_index)
        for retriever_name in args.retrievers
    ]

    all_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for run in runs:
        print(f"Evaluating {run.chunk_strategy}/{run.retriever_name} on {len(queries)} queries")
        rows = evaluate_run(
            run=run,
            queries=queries,
            k_values=k_values,
            model_id=args.model_id,
            registry_path=args.registry,
            device=args.device,
            candidate_k=args.candidate_k,
            include_results=args.include_results,
        )
        all_rows.extend(rows)
        summary_rows.append(summarize_run(rows, k_values))

    comparison_rows = compare_strategies(all_rows, k_values)

    write_csv(args.output_dir / "summary_by_run.csv", summary_rows)
    write_csv(args.output_dir / "per_query_metrics.csv", all_rows)
    write_csv(args.output_dir / "strategy_comparison_by_query.csv", comparison_rows)
    write_csv(args.output_dir / "summary_by_query_type.csv", summarize_by_group(all_rows, "query_type", k_values))
    write_csv(args.output_dir / "summary_by_category.csv", summarize_by_group(all_rows, "category", k_values))
    write_csv(args.output_dir / "summary_by_url_group.csv", summarize_by_group(all_rows, "url_group", k_values))
    write_csv(args.output_dir / f"top_failures_at_{max(k_values)}.csv", top_failures(all_rows, max(k_values)))

    if args.include_results:
        write_jsonl(args.output_dir / "per_query_metrics_with_results.jsonl", all_rows)

    payload = {
        "testset": str(args.testset),
        "query_count": len(queries),
        "k_values": k_values,
        "retrievers": args.retrievers,
        "standard_index": str(args.standard_index),
        "semantic_index": str(args.semantic_index),
        "summary_by_run": summary_rows,
        "winner_counts": {
            f"hit@{max(k_values)}": dict(Counter(row.get(f"winner_hit@{max(k_values)}") for row in comparison_rows))
        },
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown_report(args.output_dir / "retrieval_evaluation_report.md", summary_rows, comparison_rows, k_values)

    print(f"Saved retrieval evaluation to: {args.output_dir}")
    print(json.dumps(payload["winner_counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
