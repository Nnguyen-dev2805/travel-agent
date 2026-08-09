# Retrieval Benchmark Tests

This folder contains CLI scripts for retrieval-only evaluation. It does not call
the answer-generation LLM. It measures whether retrievers return benchmark
gold chunks/documents in top-k.

## Dense + Hybrid

Run a small smoke test:

```powershell
.\.venv312\Scripts\python.exe test\retrieval\evaluate_retrieval.py --limit 5
```

Run the full generated benchmark:

```powershell
.\.venv312\Scripts\python.exe test\retrieval\evaluate_retrieval.py
```

Evaluate only dense search:

```powershell
.\.venv312\Scripts\python.exe test\retrieval\evaluate_retrieval.py --retrievers dense
```

Evaluate only hybrid search:

```powershell
.\.venv312\Scripts\python.exe test\retrieval\evaluate_retrieval.py --retrievers hybrid
```

Outputs:

```text
test/retrieval/reports/query_metrics.csv
test/retrieval/reports/summary_metrics.csv
test/retrieval/reports/summary_metrics.json
```

Metrics:

- `hit@k`
- `recall@k`
- `precision@k`
- `mrr@k`
- `ndcg@k`

Hybrid search requires Elasticsearch to be running and indexed:

```powershell
docker compose up -d elasticsearch
.\.venv312\Scripts\python.exe -m backend.rag.index_elasticsearch --recreate
```
