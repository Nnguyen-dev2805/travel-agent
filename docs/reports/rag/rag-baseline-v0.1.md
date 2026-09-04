# RAG Baseline Report — `rag-current-runtime-v0.1`

> **Recreation note:** This report was recreated on 2026-09-03 from the canonical
> run artifact `data/evaluation/runs/rag-rag-current-runtime-v0.1-20260903T111946Z-6076d9e/run.json`
> after an accidental loss of the local `docs/` working tree. All metrics below
> were cross-checked mechanically against that artifact at recreation time. The
> original report (reviewed 2026-09-03) contained identical numbers derived from
> the same canonical run.

## Scope and Provenance

| Field | Value |
| --- | --- |
| Dataset | `travel-agent-rag-benchmark` v0.1 (role: `benchmark`, domain: `rag`) |
| Relevance contract | `document_id_binary_v1` |
| Run ID | `rag-rag-current-runtime-v0.1-20260903T111946Z-6076d9e` |
| Code revision | `6076d9ee271a6f1b69f1ed83b40b74ec8db287f4` |
| Working-tree state at execution | **Dirty** — disclosed: the run executed inside the `task-5` worktree where the only delta was an untracked `docs` symlink (shared-docs convenience link); tracked code was byte-identical to `6076d9e` |
| Mode | Retrieval-only (no provider calls; no answer layer) |
| Run state | `PASS` (0 errors, 0 failed gates) |
| Examples | 25 eligible / 0 invalid / 0 skipped |
| Started / completed (UTC) | 2026-09-03T11:19:46Z → 2026-09-03T11:19:56Z (10.31 s) |
| Uncertainty status | `not_applicable_n_lt_30` |

## Resolved Configuration

| Field | Resolved value |
| --- | --- |
| `config_id` | `rag-current-runtime-v0.1` |
| `config_version` | `0.1` |
| `runtime_adapter` | `current_runtime` |
| `collection_name` | `vietnam_travel_parent_child` |
| `embedding_model` | `BAAI/bge-m3` |
| `retrieval_k_values` | 1, 3, 5, 10, 20 |
| `primary_k` | 5 |
| `score_semantics` | `higher_is_better_similarity` |
| `generation_context_top_k` | 4 (recorded; unused in retrieval-only mode) |
| `generation_model` | `gpt-4o-mini` (recorded; unused in retrieval-only mode) |
| `prompt_id` | `legacy-rag-service-inline-prompt-v1` (recorded; unused in retrieval-only mode) |
| `temperature` | 0.7 (recorded; unused in retrieval-only mode) |
| `max_tokens` | 800 (recorded; unused in retrieval-only mode) |
| Judge config | none (retrieval-only mode constructs no judge) |

## Overall Retrieval Metrics (n=25)

| Metric | K=1 | K=3 | K=5 | K=10 | K=20 |
| --- | --- | --- | --- | --- | --- |
| Hit rate | 0.04 | 0.16 | **0.24** | 0.28 | 0.56 |
| MRR | 0.04 | 0.0867 | **0.1047** | 0.1087 | 0.1278 |
| nDCG | 0.04 | 0.0955 | **0.1282** | 0.1353 | 0.2011 |
| Precision | 0.04 | 0.08 | 0.08 | 0.056 | 0.06 |
| Source-URL hit | 0.04 | 0.16 | 0.24 | 0.28 | 0.56 |
| Unique docs | 1.0 | 2.56 | 4.04 | 7.28 | 13.24 |

## Per-Slice Retrieval Metrics

| Slice | n | Hit@5 | Hit@20 | MRR@5 | nDCG@5 |
| --- | --- | --- | --- | --- | --- |
| `single_source_factual` | 5 | 0.20 | 0.40 | 0.067 | 0.10 |
| `multi_evidence_synthesis` | 5 | 0.20 | 1.00 | 0.10 | 0.077 |
| `ambiguous_underspecified` | 5 | 0.00 | 0.00 | 0.00 | 0.00 |
| `source_citation_sensitive` | 5 | 0.00 | 0.60 | 0.00 | 0.00 |
| `long_tail_difficult` | 5 | 0.80 | 0.80 | 0.357 | 0.464 |

## Judge Validity

Full answer mode did not run. `answer_metrics: null`, `judge_valid_count: 0`,
`judge_invalid_count: 0`. No provider prerequisites were available at execution
time; per plan Step 10 this limitation is recorded and no fabricated scores are
substituted. No answer-quality claims are made by this report.

## Failures

| Failure label | Count |
| --- | --- |
| `retrieval_miss` | **19 / 25** |

Weak retrieval overall; `ambiguous_underspecified` and
`source_citation_sensitive` score 0.00 across every recorded K, so ranking
fails entirely on those slices — not merely at primary K.

## Synthetic-Score Verification

Deterministic audit: `answer_metrics` is `null`, all judge counters are 0, and
`errors`/`failed_gates` are empty — **zero synthetic answer scores present**.

## Frozen-Baseline Statement

**This run establishes the frozen baseline and does not by itself demonstrate improvement.**

## Limitations

1. **Retrieval-only.** No generation/judge layer ran; no answer-quality evidence
   exists for this baseline.
2. **Small dataset (n=25).** `uncertainty_status = not_applicable_n_lt_30`;
   metrics are descriptive, not statistically certain.
3. **Dirty working tree at execution.** Disclosed above; tracked code was
   byte-identical to the recorded revision.
4. **Report is a recreation.** Original was lost with the accidental `docs/`
   deletion; metrics are mechanically cross-checked against the canonical
   `run.json`, but the original prose was not preserved.
5. **Single runtime, single snapshot.** One run, one code revision; no variance
   information.

## Canonical Artifacts

- Machine summary: `data/evaluation/runs/rag-rag-current-runtime-v0.1-20260903T111946Z-6076d9e/run.json`
- Per-example evidence: `data/evaluation/runs/rag-rag-current-runtime-v0.1-20260903T111946Z-6076d9e/examples.jsonl` (25 lines)
- Frozen dataset: `data/evaluation/benchmark/rag-v0.1/` (manifest + 25 examples)
- Baseline config: `data/evaluation/configs/rag-current-runtime-v0.1.json`
- Candidate config (predeclared): `data/evaluation/configs/rag-structured-candidate-v0.1.json`

