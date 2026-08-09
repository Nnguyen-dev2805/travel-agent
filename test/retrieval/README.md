# Retrieval Benchmark Tests

This folder is for retrieval-only benchmark scripts and reports.

Reranking requires a TEI cross-encoder endpoint on Modal:

```env
RERANKER_ENABLED=true
TEI_RERANK_URL=https://your-modal-reranker-app.modal.run/rerank
RERANKER_CANDIDATE_K=20
```

The reranker is applied after dense or hybrid retrieval. It receives candidate
chunks, calls TEI `/rerank`, then returns the final top-k by cross-encoder score.
