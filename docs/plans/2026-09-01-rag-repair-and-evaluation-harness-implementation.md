# RAG Repair and Evaluation Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Preserve
> checkbox state as review evidence.

**Goal:** Establish a frozen, reviewable RAG baseline and a config-driven local
evaluation harness, then refactor the online RAG path behind structured evidence
contracts and prove the candidate is non-regressing under the accepted D5 gates.

**Architecture:** Implement R2 measurement infrastructure before material R1
runtime behavior changes. Runtime-owned evidence contracts are introduced first;
the harness uses a compatibility adapter to measure the current
`vietnam_travel_parent_child` path, freezes benchmark/config/run evidence, and
only then moves online RAG to retrieval/context/generation modules that implement
the same contracts. Evaluation stays a one-way consumer of runtime contracts,
matching ADR 0001.

**Tech Stack:** Python 3.11 baseline, standard-library dataclasses/JSON/argparse,
FastAPI, pytest, OpenAI-compatible GitHub Models client already used by the
repository, BAAI/bge-m3 embeddings, ChromaDB, Markdown/JSON/JSONL evaluation
artifacts.

**Spec:** [RAG Repair and Evaluation Harness Design](../specs/2026-09-01-rag-repair-and-evaluation-harness-design.md),
version 0.1 (Approved).

**ADR:** [ADR 0001: Separate Online RAG Execution from Config-driven Evaluation](../adr/0001-separate-online-rag-execution-from-config-driven-evaluation.md)
(Accepted).

| Field | Value |
| --- | --- |
| Status | Approved |
| Date | 2026-09-01 |
| Approved specification | [RAG Repair and Evaluation Harness Design](../specs/2026-09-01-rag-repair-and-evaluation-harness-design.md), version 0.1 |
| Execution owner | Coding agent under repository-owner review |
| Decision owner | Repository owner |
| Scope | R1 RAG runtime repair plus R2 evaluation harness, frozen baseline, benchmark v0.1, candidate comparison, reports, and supporting tests/docs |
| Verification | Targeted pytest per task; full `python3 -m pytest backend/tests`; `python3 -m compileall backend`; dataset/config preflight; frozen baseline and candidate runs; D5 comparison; import-boundary grep; `git diff --check`; `git status --short --untracked-files=all`; complete tracked/untracked change-set review |

## Global Constraints

1. The first canonical baseline is the current online RAG identity:
   `vietnam_travel_parent_child`, `BAAI/bge-m3`, generation context `top_k=4`,
   current configured `LLM_MODEL`, temperature `0.7`, and `max_tokens=800`.
2. Retrieval evaluation uses `K=5` as primary and `K=1,3,10,20` as diagnostics.
3. Do not inspect candidate results before benchmark version, eligible examples,
   primary metrics, K values, slices, judge contract, thresholds, and candidate
   config are frozen.
4. The first valid baseline describes current quality only and cannot support an
   improvement claim.
5. Baseline/candidate are experiment roles assigned by run configuration and
   artifact identity, never by Chroma collection name.
6. Preserve the public `/api/v1/chat` response fields `reply`, `model`, and
   `citations`.
7. Do not replace ChromaDB, `BAAI/bge-m3`, the configured model provider, or add
   hosted evaluation/observability infrastructure in R1/R2 v0.1.
8. Retrieval-only evaluation must run without an external LLM call.
9. Judge/provider/parse/schema/range failures produce `judge_invalid`; no
   synthetic score, default winner, or zero-filled quality evidence is allowed.
10. Final result states are exactly `PASS`, `FAIL`, `INCONCLUSIVE`, or `INVALID`.
11. Apply D5 gates exactly: Hit@5/MRR@5/nDCG@5 decline `<= 0.01`, mandatory-slice
    Hit@5 decline `<= 0.03`, mean groundedness `>= 4.0` and decline `<= 0.10`,
    mean correctness `>= 4.0` and decline `<= 0.10`; improvement claims require
    a predeclared primary gain `>= 0.02` or equivalent reviewed benefit.
12. Benchmark, regression, and canonical run artifacts use public, synthetic, or
    reviewed redacted content; never persist secrets, credentials, or unnecessary
    personal data.
13. Generated evidence stores stable IDs and minimal necessary excerpts rather
    than copying whole source documents.
14. A material contract, storage, provider, public API, trust-boundary, or
    dependency-direction change stops execution and returns to specification/ADR
    review.
15. Preserve unrelated user work. Do not stage, commit, push, open a pull request,
    merge, tag, publish, delete branches, or rewrite history without an explicit
    repository-owner request for that exact Git action.
16. Canonical baseline execution must complete before Task 6 changes online RAG
    behavior. If a prerequisite source change is discovered, characterize it as
    behavior-preserving or stop and re-freeze the baseline before proceeding.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/rag/contracts.py` | Runtime-owned retrieval, context, citation, and generated-answer value contracts | Approved spec and ADR 0001 |
| `backend/rag/retrieval/adapters.py` | Convert raw Chroma dictionaries to structured `RetrievalResult` values | `backend/rag/contracts.py`, current Chroma result shape |
| `backend/rag/retrieval/service.py` | Candidate `KnowledgeRetriever` orchestration over embedder and vector store | Runtime contracts, embedder, Chroma adapter |
| `backend/rag/retrieval/__init__.py` | Export stable retrieval runtime interfaces | Retrieval modules |
| `backend/rag/generation/context.py` | Build prompt context while retaining selected evidence and insufficient-evidence state | Runtime contracts |
| `backend/rag/generation/llm.py` | Model-provider generation using supplied `ContextBundle` | Runtime contracts, backend settings, existing OpenAI client |
| `backend/rag/generation/rag_service.py` | Compatibility/orchestration facade preserving public chat result shape | Retriever, context assembler, generator |
| `backend/rag/generation/__init__.py` | Export `RAGService` and stable generation interfaces | Generation modules |
| `backend/rag/evaluation/models.py` | Dataset/run/judge/result-state dataclasses and enums | Standard library, D5 contract |
| `backend/rag/evaluation/dataset.py` | Load and validate versioned manifest + JSONL examples | Evaluation models |
| `backend/rag/evaluation/metrics.py` | Deterministic retrieval metrics and per-example contributions | Runtime retrieval contract, evaluation example contract |
| `backend/rag/evaluation/comparison.py` | Compatibility checks, paired deltas, D5 gates, uncertainty metadata, final comparison state | Evaluation artifacts/models/metrics |
| `backend/rag/evaluation/artifacts.py` | Read/write `run.json`, `examples.jsonl`, and sanitized report inputs | Evaluation models |
| `backend/rag/evaluation/judge.py` | Single-answer D5 judge prompt, provider call, strict schema/range validation | Evaluation models, existing provider settings |
| `backend/rag/evaluation/runtime.py` | Current-runtime baseline adapter and final structured-runtime adapter | Runtime contracts/services |
| `backend/rag/evaluation/runner.py` | Config-driven retrieval/full run lifecycle and failure classification | Dataset, runtime adapters, metrics, judge, artifacts |
| `backend/rag/evaluation/cli.py` | `validate-dataset`, `preflight`, `run`, and `compare` commands | Evaluation runner/comparator |
| `backend/rag/evaluation/evaluator.py` | Thin compatibility entry point to the new CLI/metric exports; no hard-coded experiment roles | New evaluation modules |
| `backend/rag/evaluation/llm_judge_evaluator.py` | Compatibility export for validated judge adapter; removes synthetic fallback | `backend/rag/evaluation/judge.py` |
| `data/evaluation/benchmark/rag-v0.1/manifest.json` | Frozen benchmark identity, provenance, slice contract, review metadata | 281-document processed travel corpus |
| `data/evaluation/benchmark/rag-v0.1/examples.jsonl` | 25 reviewed benchmark examples, five per mandatory D5 slice | Stable corpus document IDs/URLs |
| `data/evaluation/configs/rag-current-runtime-v0.1.json` | Frozen current-runtime baseline behavior/config identity | Current online RAG settings |
| `data/evaluation/configs/rag-structured-candidate-v0.1.json` | Predeclared R1 candidate identity with same model/index settings and structured runtime path | Task 6 design |
| `data/evaluation/runs/<baseline-run-id>/run.json` | Canonical machine-readable baseline summary | Task 5 execution |
| `data/evaluation/runs/<baseline-run-id>/examples.jsonl` | Canonical per-example baseline evidence | Task 5 execution |
| `data/evaluation/runs/<candidate-run-id>/run.json` | Canonical machine-readable candidate summary | Task 7 execution |
| `data/evaluation/runs/<candidate-run-id>/examples.jsonl` | Canonical per-example candidate evidence | Task 7 execution |
| `docs/reports/rag/rag-baseline-v0.1.md` | Human-readable frozen baseline report | Canonical baseline artifact |
| `docs/reports/rag/rag-candidate-v0.1-comparison.md` | Human-readable candidate-vs-baseline D5 comparison | Canonical baseline/candidate artifacts |
| `backend/tests/unit/test_rag_contracts.py` | Runtime value-contract tests | `backend/rag/contracts.py` |
| `backend/tests/unit/test_retrieval_service.py` | Chroma mapping and candidate retriever tests | Retrieval modules |
| `backend/tests/unit/test_context_assembler.py` | Context formatting/provenance/insufficient-evidence tests | `generation/context.py` |
| `backend/tests/unit/test_rag_service.py` | Generator orchestration and public-result compatibility tests | Candidate RAG modules |
| `backend/tests/unit/test_evaluation_dataset.py` | Dataset/config validation tests | Evaluation dataset/models |
| `backend/tests/unit/test_evaluation_metrics.py` | D5 retrieval metric tests | Evaluation metrics |
| `backend/tests/unit/test_evaluation_judge.py` | Judge schema/provider-invalid tests | Evaluation judge |
| `backend/tests/unit/test_evaluation_artifacts.py` | Artifact serialization/sanitization/reload tests | Evaluation artifacts |
| `backend/tests/unit/test_evaluation_comparison.py` | Compatibility, paired delta, gate, state, uncertainty tests | Evaluation comparison |
| `backend/tests/unit/test_evaluation_runner.py` | Baseline/candidate role independence and lifecycle tests | Evaluation runner/runtime adapters |
| `backend/tests/integration/test_rag_evaluation_flow.py` | Deterministic no-network baseline/candidate harness flow | Full evaluation package with fakes |
| `backend/tests/integration/test_api.py` | Preserve `/api/v1/chat` schema through candidate runtime | Chat API + stubbed RAG service |
| `docs/evaluation/rag-evaluation.md` | Add executable command examples without changing accepted D5 thresholds | Implemented CLI |
| `DEVELOPMENT.md` | Local RAG evaluation/preflight commands and provider boundary | Implemented CLI |
| `docs/roadmap/master-roadmap.md` | R1/R2 lifecycle status/evidence only | Execution state |
| `docs/plans/README.md` | Plan index entry | This plan |
| `docs/plans/2026-09-01-rag-repair-and-evaluation-harness-implementation.md` | Approved execution contract and completion record | Approved spec + ADR |

## Task 1: Introduce Runtime-owned Evidence Contracts Without Changing Online Behavior

**Files:**

- Create: `backend/rag/contracts.py`
- Create: `backend/rag/retrieval/adapters.py`
- Create: `backend/tests/unit/test_rag_contracts.py`
- Create: `backend/tests/unit/test_retrieval_service.py`
- Read: `backend/rag/retrieval/vector_store.py`
- Do not modify online `RAGService` in this task.

**Interfaces:**

- Consumes: current `ChromaVectorStore.search_similar()` dictionaries.
- Produces:
  - `RetrievalResult(chunk_id: str, document_id: str, title: str, url: str, score: float | None, text: str)`
  - `CitationEvidence(title: str, url: str, evidence_ids: tuple[str, ...])`
  - `ContextBundle(prompt_context: str, evidence: tuple[RetrievalResult, ...], citations: tuple[CitationEvidence, ...], insufficient_evidence: bool)`
  - `GeneratedAnswer(reply: str, model: str, citations: tuple[CitationEvidence, ...])`
  - `map_chroma_result(item: dict[str, Any]) -> RetrievalResult`

- [ ] **Step 1: Mark execution start only after plan approval**

At execution time, first verify this plan says `Approved`. Then update only its
status to `In Progress` and update `R1`/`R2` rows in
`docs/roadmap/master-roadmap.md` from `Blocked by gate` to `In progress`, citing
this approved spec/ADR/plan as evidence.

Run:

```bash
git status --short --untracked-files=all
```

Expected: only the approved R1/R2 documentation package is modified/untracked;
if unrelated changes overlap an affected path, inspect and stop before overwrite.

- [ ] **Step 2: Write failing contract tests**

Create `backend/tests/unit/test_rag_contracts.py` with at least:

```python
from backend.rag.contracts import ContextBundle, RetrievalResult


def test_context_bundle_keeps_selected_evidence_identity():
    item = RetrievalResult(
        chunk_id="doc-1:child:0001:00",
        document_id="doc-1",
        title="Ha Long",
        url="https://vietnam.travel/ha-long",
        score=0.91,
        text="Evidence text",
    )
    bundle = ContextBundle(
        prompt_context="[Nguồn 1: Ha Long]\nEvidence text",
        evidence=(item,),
        citations=(),
        insufficient_evidence=False,
    )
    assert bundle.evidence[0].chunk_id == "doc-1:child:0001:00"
    assert bundle.insufficient_evidence is False
```

Add a Chroma mapping test to `backend/tests/unit/test_retrieval_service.py`:

```python
from backend.rag.retrieval.adapters import map_chroma_result


def test_map_chroma_result_flattens_provenance():
    result = map_chroma_result({
        "chunk_id": "child-1",
        "text": "source text",
        "score": 0.8,
        "metadata": {
            "document_id": "doc-1",
            "title": "Title",
            "url": "https://example.test/doc-1",
        },
    })
    assert result.chunk_id == "child-1"
    assert result.document_id == "doc-1"
    assert result.title == "Title"
    assert result.url == "https://example.test/doc-1"
    assert result.score == 0.8
```

- [ ] **Step 3: Run tests and confirm red state**

Run:

```bash
python3 -m pytest backend/tests/unit/test_rag_contracts.py backend/tests/unit/test_retrieval_service.py -q
```

Expected: FAIL because `backend.rag.contracts` and the adapter do not exist yet.
If the documented Python environment is not prepared, stop and use the R0 local
setup rather than changing test expectations.

- [ ] **Step 4: Implement immutable runtime value contracts**

Create `backend/rag/contracts.py` using frozen dataclasses. Enforce non-empty
`chunk_id` and `document_id` at adapter boundaries; use empty strings only for
optional human-display `title`/`url`. `score` may be `None` when a backend does
not expose one. Keep these types free of evaluation imports.

- [ ] **Step 5: Implement Chroma mapping**

Create `map_chroma_result()` in `backend/rag/retrieval/adapters.py`. Resolve
`document_id` from `metadata["document_id"]`, `title` from metadata, `url` from
`metadata["url"]` or `metadata["source_url"]`, and preserve `text`/`score` from
the current vector-store result. Raise `ValueError` when governed chunk or
document identity is missing rather than fabricating IDs.

- [ ] **Step 6: Run contract tests green**

Run the same targeted pytest command.

Expected: PASS with no network/model/vector-store access.

- [ ] **Step 7: Review checkpoint**

Review that `backend/rag/contracts.py` imports no evaluation module and that no
online source was modified in Task 1.

Expected: runtime contracts exist, Chroma mapping is deterministic, and current
chat behavior is unchanged.

## Task 2: Implement Dataset, Run-config, and Result-state Validation

**Files:**

- Create: `backend/rag/evaluation/models.py`
- Create: `backend/rag/evaluation/dataset.py`
- Create: `backend/tests/unit/test_evaluation_dataset.py`

**Interfaces:**

- Consumes: a dataset directory containing `manifest.json` + `examples.jsonl`,
  and JSON run config.
- Produces:
  - `DatasetRole`: `development`, `regression`, `benchmark`, `safety`
  - `ResultState`: `PASS`, `FAIL`, `INCONCLUSIVE`, `INVALID`
  - `DatasetManifest`
  - `EvaluationExample`
  - `EvaluationDataset`
  - `JudgeConfig`
  - `RunConfig`
  - `load_dataset(path: Path) -> EvaluationDataset`
  - `load_run_config(path: Path) -> RunConfig`

- [ ] **Step 1: Write failing dataset tests**

Cover a valid manifest/example plus duplicate IDs, role mismatch, unknown slice,
missing `expected_document_ids`, invalid result-state/config enums, and a
retrieval run missing K=5.

Use this exact minimum benchmark example shape in tests:

```json
{
  "example_id": "rag-bench-001",
  "question": "Khi nào nên đến Hạ Long?",
  "dataset_role": "benchmark",
  "category": "planning",
  "slices": ["single_source_factual"],
  "expected_document_ids": ["doc-halong"],
  "expected_source_urls": ["https://vietnam.travel/ha-long"],
  "reference_answer": "Thông tin tham chiếu được review từ source document."
}
```

- [ ] **Step 2: Run dataset tests red**

Run:

```bash
python3 -m pytest backend/tests/unit/test_evaluation_dataset.py -q
```

Expected: FAIL because evaluation contracts/loader do not exist.

- [ ] **Step 3: Implement strict dataclasses/enums**

`DatasetManifest` must expose these fields exactly:

```python
@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    version: str
    role: DatasetRole
    domain: str
    created_at: str
    reviewed_at: str
    reviewer: str
    provenance: str
    intended_population: str
    inclusion_exclusion_rules: str
    relevance_contract: str
    mandatory_slices: tuple[str, ...]
    min_examples_per_slice: int
```

`EvaluationExample` uses `expected_document_ids: tuple[str, ...]`,
`expected_source_urls: tuple[str, ...]`, and `reference_answer: str | None`.
Do not silently coerce missing relevance labels into empty eligible examples.

- [ ] **Step 4: Freeze run-config fields**

`RunConfig` must record at least:

```python
@dataclass(frozen=True)
class RunConfig:
    config_id: str
    version: str
    runtime_adapter: str
    collection_name: str
    embedding_model: str
    retrieval_k_values: tuple[int, ...]
    primary_k: int
    score_semantics: str
    generation_context_top_k: int
    generation_model: str
    prompt_id: str
    temperature: float
    max_tokens: int
    judge: JudgeConfig | None
```

Allow runtime adapters only `current_runtime` and `structured_runtime_v1` in v0.1.
Require `primary_k == 5`, require K values contain `1,3,5,10,20`, and require
`score_semantics == "higher_is_better_similarity"` for the current Chroma
adapter.

- [ ] **Step 5: Implement loader/validator**

`load_dataset()` must validate UTF-8 JSON/JSONL, immutable role agreement,
unique example IDs, mandatory slices, minimum eligible count per mandatory
slice, non-empty expected document IDs for retrieval metrics, and manifest
`domain == "rag"`.

`load_run_config()` validates schema before any embedder, vector store, or model
client is constructed.

- [ ] **Step 6: Run tests green**

Run the Task 2 test command.

Expected: PASS with no external access.

- [ ] **Step 7: Review checkpoint**

Review invalid examples/configs to confirm they raise explicit validation errors
instead of producing scores or empty-success runs.

Expected: dataset/config validity is a hard precondition for evaluation.

## Task 3: Implement Retrieval Metrics, Artifacts, Comparison Compatibility, and D5 Gates

**Files:**

- Create: `backend/rag/evaluation/metrics.py`
- Create: `backend/rag/evaluation/artifacts.py`
- Create: `backend/rag/evaluation/comparison.py`
- Create: `backend/tests/unit/test_evaluation_metrics.py`
- Create: `backend/tests/unit/test_evaluation_artifacts.py`
- Create: `backend/tests/unit/test_evaluation_comparison.py`

**Interfaces:**

- Consumes: validated examples, structured `RetrievalResult` values, and complete
  run artifacts.
- Produces:
  - `compute_retrieval_metrics(example, results, k_values) -> dict[str, float | int | None]`
  - `write_run_artifacts(output_dir, run_record, example_records) -> None`
  - `load_run_artifact(run_dir) -> RunArtifact`
  - `validate_comparison_contract(baseline, candidate) -> tuple[str, ...]`
  - `compare_runs(baseline, candidate) -> ComparisonResult`

- [ ] **Step 1: Move metric expectations into failing focused tests**

Write tests proving:

```python
assert metrics["hit@5"] == 1
assert metrics["mrr@5"] == 0.5      # first relevant result at rank 2
assert 0.0 <= metrics["ndcg@5"] <= 1.0
assert metrics["source_url_hit@5"] == 1
```

Also test multiple relevant documents, no-hit, and absent expected URL. Absent URL
must produce `None` for source-URL diagnostic, not `0`.

- [ ] **Step 2: Run metric tests red**

Run:

```bash
python3 -m pytest backend/tests/unit/test_evaluation_metrics.py -q
```

Expected: FAIL because the new metric module is absent.

- [ ] **Step 3: Implement D5 metric functions**

Use document identity from `RetrievalResult.document_id` as the governed primary
relevance contract. Compute Hit@K, MRR@K, binary nDCG@K, Precision@K, relevant
chunk count, unique document count, and optional source URL hit. Do not embed
strategy names into metric keys.

- [ ] **Step 4: Write failing artifact tests**

Require `run.json` to include run ID/times/state, dataset identity/counts, code
revision + dirty state, config identity/settings, judge validity counts,
baseline run ID when applicable, aggregate/slice metrics, deltas/uncertainty/gate
decisions, timing/errors, and failure counts.

Require each example record to include stable example ID, eligibility, expected
labels, ranked evidence IDs, context evidence IDs when generated, answer/citation
data when generated, metric contributions, judge validity, failure labels, and
timing/errors.

- [ ] **Step 5: Implement deterministic artifact serialization**

Write UTF-8 JSON with sorted keys and trailing newline; JSONL one record per
example. Reject values containing configured secret values before write. Keep
retrieved text excerpts bounded to 500 characters per evidence item in
persisted artifacts.

- [ ] **Step 6: Write failing comparison/gate tests**

Cover these exact outcomes:

```python
# compatible + within no-regression gates
assert result.state == ResultState.PASS

# Hit@5 decline > 0.01
assert result.state == ResultState.FAIL
assert "hit@5" in result.failed_gates

# dataset version mismatch
assert result.state == ResultState.INVALID

# valid comparison but an eligible mandatory slice falls below manifest minimum
assert result.state == ResultState.INCONCLUSIVE
```

- [ ] **Step 7: Implement compatibility and gates**

Compatibility must require same dataset ID/version, eligible example IDs,
relevance contract, primary K/metric definitions, mandatory slices, and same
judge prompt/rubric/schema/model when comparing judged metrics. A candidate
behavior difference such as `runtime_adapter` or prompt ID is recorded as the
candidate change and is not itself a measurement mismatch.

Implement the exact D5 hard gates from Global Constraints. Do not weaken them
through config values.

- [ ] **Step 8: Implement uncertainty metadata**

Predeclare `BOOTSTRAP_MIN_EXAMPLES = 30`, `BOOTSTRAP_RESAMPLES = 2000`, and
`BOOTSTRAP_SEED = 20260901`. When the paired eligible sample is below 30, record
`uncertainty_status = "not_applicable_n_lt_30"` rather than fabricating an
interval. When applicable, compute paired bootstrap intervals for primary metric
deltas using the fixed seed.

- [ ] **Step 9: Run Task 3 tests green**

Run:

```bash
python3 -m pytest \
  backend/tests/unit/test_evaluation_metrics.py \
  backend/tests/unit/test_evaluation_artifacts.py \
  backend/tests/unit/test_evaluation_comparison.py -q
```

Expected: PASS without network or Chroma access.

- [ ] **Step 10: Review checkpoint**

Review metric definitions and all PASS/FAIL/INCONCLUSIVE/INVALID branches
against `docs/evaluation/rag-evaluation.md`.

Expected: aggregate movement can be traced back to per-example contributions and
invalid evidence never becomes a favorable metric.

## Task 4: Build Config-driven Runner and Strict Answer Judge Around the Current Runtime

**Files:**

- Create: `backend/rag/evaluation/judge.py`
- Create: `backend/rag/evaluation/runtime.py`
- Create: `backend/rag/evaluation/runner.py`
- Create: `backend/rag/evaluation/cli.py`
- Modify: `backend/rag/evaluation/evaluator.py`
- Modify: `backend/rag/evaluation/llm_judge_evaluator.py`
- Create: `backend/tests/unit/test_evaluation_judge.py`
- Create: `backend/tests/unit/test_evaluation_runner.py`
- Create: `backend/tests/integration/test_rag_evaluation_flow.py`

**Interfaces:**

- Consumes: validated dataset/run config and current `VectorEmbedder`,
  `ChromaVectorStore`, `RAGService` behavior.
- Produces:
  - `CurrentRuntimeAdapter.retrieve(question, top_k) -> list[RetrievalResult]`
  - `CurrentRuntimeAdapter.generate(question, top_k) -> tuple[GeneratedAnswer, tuple[RetrievalResult, ...]]`
  - `StructuredRuntimeAdapter` with the same retrieve/generate interface, implemented and wired in Task 6
  - `JudgeAdapter.score(question, answer, evidence, reference_answer) -> JudgeResult`
  - `EvaluationRunner.run(dataset, config, mode, output_dir) -> RunArtifact`
  - CLI subcommands `validate-dataset`, `preflight`, `run`, `compare`

- [ ] **Step 1: Write judge-invalid tests first**

Create fake provider responses for malformed JSON, missing one criterion, score
`0`, score `6`, wrong enum/type, empty content, and provider exception. Each case
must return invalid judge evidence with failure label `judge_invalid` and no
numeric dimension scores.

Use the six exact D5 keys:

```python
JUDGE_DIMENSIONS = (
    "groundedness",
    "answer_relevance",
    "correctness",
    "completeness",
    "practical_usefulness",
    "clarity",
)
```

- [ ] **Step 2: Run judge tests red**

Run:

```bash
python3 -m pytest backend/tests/unit/test_evaluation_judge.py -q
```

Expected: FAIL because strict judge code does not exist.

- [ ] **Step 3: Implement a single-answer judge contract**

Do not use pairwise `baseline`/`parent_child` labels. Score one answer at a time
against question, retrieved evidence, and optional reviewed reference answer so
strategy identity is absent from the prompt. Freeze prompt ID
`rag-answer-judge-v0.1`, rubric ID `d5-rag-answer-v0.1`, schema version `1`, and
temperature `0.0` in the run config. Validate JSON object shape and each integer
range 1..5. Recompute any aggregate total locally; never trust a provider total.

- [ ] **Step 4: Remove synthetic fallback from governed execution**

Replace the legacy body of `llm_judge_evaluator.py` with a compatibility export
or thin adapter to the strict judge implementation. `evaluator.py` becomes a
thin compatibility entry point to the new CLI/metric functions. Neither file may
construct `vietnam_travel_knowledge` as an inherent baseline or fabricate judge
scores.

- [ ] **Step 5: Write runner role-independence tests**

Use fakes to prove the same config can be assigned baseline or candidate role by
comparison context and that a collection name does not imply role.

Also prove retrieval-only mode never constructs/calls a model provider.

- [ ] **Step 6: Implement `CurrentRuntimeAdapter` without changing online RAG**

For retrieval, embed the query and call the configured collection, then map raw
results with `map_chroma_result()`.

For answer-baseline characterization, use the existing `RAGService` and a
recording vector-store proxy that delegates `search_similar()` while capturing
the exact ranked raw results used by `generate_answer()`. Map the captured
results into `RetrievalResult` values for the example artifact. Do not copy or
reconstruct the current prompt inside evaluation code.

- [ ] **Step 7: Implement preflight**

`preflight` validates dataset/config first, verifies the configured Chroma
collection exists and `count() > 0`, confirms embedding-model construction, and
for `--mode full` also requires the configured provider credential/model. A
missing index/model/provider is `infrastructure_failure`; do not substitute the
embedder's dummy behavior for canonical evaluation.

- [ ] **Step 8: Implement runner lifecycle**

For each eligible example:

1. retrieve up to `max(retrieval_k_values)` for retrieval metrics;
2. record ranked structured evidence;
3. optionally generate using `generation_context_top_k`;
4. optionally judge the generated answer;
5. compute per-example metrics/failures;
6. aggregate overall and mandatory-slice metrics;
7. persist timing/errors and final state.

Generate run IDs as `rag-<config_id>-<UTC YYYYMMDDTHHMMSSZ>-<git-short-sha>` and
record `git rev-parse HEAD` plus dirty-working-tree boolean.

- [ ] **Step 9: Implement CLI**

Support exactly:

```bash
python3 -m backend.rag.evaluation.cli validate-dataset --dataset <dataset-dir>
python3 -m backend.rag.evaluation.cli preflight --dataset <dataset-dir> --config <config-json> --mode retrieval
python3 -m backend.rag.evaluation.cli run --dataset <dataset-dir> --config <config-json> --mode retrieval --output-dir <dir>
python3 -m backend.rag.evaluation.cli run --dataset <dataset-dir> --config <config-json> --mode full --output-dir <dir>
python3 -m backend.rag.evaluation.cli compare --baseline <run-dir> --candidate <run-dir> --output <report-json>
```

`run` defaults to retrieval-only; full mode must be explicit.

- [ ] **Step 10: Add deterministic integration flow**

`backend/tests/integration/test_rag_evaluation_flow.py` uses fake retrieval and
fake generation/judge adapters with a temporary dataset/output directory. It
must execute one baseline run, one candidate run, reload both artifacts, compare
them, and finish `PASS` without network access.

- [ ] **Step 11: Run Task 4 tests green**

Run:

```bash
python3 -m pytest \
  backend/tests/unit/test_evaluation_judge.py \
  backend/tests/unit/test_evaluation_runner.py \
  backend/tests/integration/test_rag_evaluation_flow.py -q
```

Expected: PASS; no external provider/model/index is required by these tests.

- [ ] **Step 12: Review checkpoint**

Review imports and constructor paths.

Expected: online API/RAG imports no evaluation runner/judge/artifact module;
retrieval-only harness is provider-free; legacy evaluator names no longer assign
experiment roles.

## Task 5: Curate Benchmark v0.1, Freeze Comparison Contract, and Capture the Current-runtime Baseline

**Files:**

- Create: `data/evaluation/benchmark/rag-v0.1/manifest.json`
- Create: `data/evaluation/benchmark/rag-v0.1/examples.jsonl`
- Create: `data/evaluation/configs/rag-current-runtime-v0.1.json`
- Create: `data/evaluation/configs/rag-structured-candidate-v0.1.json`
- Create after canonical execution: `data/evaluation/runs/<baseline-run-id>/run.json`
- Create after canonical execution: `data/evaluation/runs/<baseline-run-id>/examples.jsonl`
- Create: `docs/reports/rag/rag-baseline-v0.1.md`
- Read: `data/processed/vietnam_travel_raw.jsonl`
- Read: `data/processed/vietnam_travel_cleaned.json`

**Interfaces:**

- Consumes: the current 281-document processed travel corpus, Task 4 harness,
  accepted D5 protocol, and current runtime config.
- Produces: frozen benchmark `travel-agent-rag-benchmark` v0.1, predeclared
  baseline/candidate configs, and the first protocol-valid current-runtime run.

- [ ] **Step 1: Inventory corpus identities before writing labels**

Run a read-only script over `data/processed/vietnam_travel_raw.jsonl` that prints
`document_id`, title, URL, and a bounded text excerpt. Confirm the corpus count is
281 unless repository data intentionally changed and that each selected source
has a stable non-empty `document_id` and public URL.

Use `utf-8-sig` when direct reads of
`data/processed/vietnam_travel_cleaned.json` encounter the known BOM.

Expected: selected benchmark sources can be traced to committed/public corpus
metadata; no source label is invented from a filename or title alone.

- [ ] **Step 2: Create the frozen manifest**

Use this contract exactly, filling review date only after the owner review in
Step 5:

```json
{
  "dataset_id": "travel-agent-rag-benchmark",
  "version": "0.1",
  "role": "benchmark",
  "domain": "rag",
  "created_at": "2026-09-01",
  "reviewed_at": "2026-09-01",
  "reviewer": "repository-owner",
  "provenance": "Public Vietnam travel corpus stored under data/processed; questions and reference answers are manually reviewed derivatives of source content.",
  "intended_population": "Vietnam travel information and planning questions supported by the current indexed corpus.",
  "inclusion_exclusion_rules": "Include answerable travel questions with stable source document IDs/URLs; exclude private data, live credentials, unsupported current-event claims, and questions whose reviewed answer requires evidence outside the indexed corpus.",
  "relevance_contract": "document_id_binary_v1",
  "mandatory_slices": [
    "single_source_factual",
    "multi_evidence_synthesis",
    "ambiguous_underspecified",
    "source_citation_sensitive",
    "long_tail_difficult"
  ],
  "min_examples_per_slice": 5
}
```

- [ ] **Step 3: Curate exactly 25 benchmark examples**

Create five examples for each mandatory slice. Every row must have exactly one
primary mandatory slice for unambiguous slice counts, at least one stable
`expected_document_ids` value, the source URL when available, and a manually
reviewed `reference_answer` for full answer-quality mode.

Use IDs `rag-bench-001` through `rag-bench-025`. Do not derive expected document
IDs by running retrieval and choosing what the system returned; labels come from
source review first.

For `multi_evidence_synthesis`, require at least two expected document IDs. For
`source_citation_sensitive`, require at least one expected source URL. For
`ambiguous_underspecified`, write the reference answer to acknowledge ambiguity
rather than inventing user intent. For `long_tail_difficult`, select specific
low-frequency places/topics confirmed in source content.

- [ ] **Step 4: Validate benchmark mechanically**

Run:

```bash
python3 -m backend.rag.evaluation.cli validate-dataset \
  --dataset data/evaluation/benchmark/rag-v0.1
```

Expected: exit 0, 25 eligible examples, five examples in each mandatory slice,
zero duplicate IDs, zero invalid examples.

- [ ] **Step 5: Repository-owner benchmark review gate**

Before any canonical baseline run, present `manifest.json` and all 25 questions,
expected source IDs/URLs, slice labels, and reference answers to the repository
owner.

Expected: explicit owner acceptance of benchmark v0.1. If any label changes,
rerun validation and keep version `0.1` only because candidate results have not
yet been observed. After candidate results exist, any benchmark change creates a
new version.

- [ ] **Step 6: Freeze baseline run config**

Create `data/evaluation/configs/rag-current-runtime-v0.1.json`:

```json
{
  "config_id": "rag-current-runtime-v0.1",
  "version": "0.1",
  "runtime_adapter": "current_runtime",
  "collection_name": "vietnam_travel_parent_child",
  "embedding_model": "BAAI/bge-m3",
  "retrieval_k_values": [1, 3, 5, 10, 20],
  "primary_k": 5,
  "score_semantics": "higher_is_better_similarity",
  "generation_context_top_k": 4,
  "generation_model": "${LLM_MODEL}",
  "prompt_id": "legacy-rag-service-inline-prompt-v1",
  "temperature": 0.7,
  "max_tokens": 800,
  "judge": {
    "model": "${LLM_MODEL}",
    "prompt_id": "rag-answer-judge-v0.1",
    "rubric_id": "d5-rag-answer-v0.1",
    "schema_version": 1,
    "temperature": 0.0
  }
}
```

The config loader resolves `${LLM_MODEL}` from backend settings at preflight and
records the resolved model string in `run.json`; unresolved placeholders are
invalid for execution.

- [ ] **Step 7: Freeze candidate comparison config before candidate results**

Create `data/evaluation/configs/rag-structured-candidate-v0.1.json` with the same
collection, embedding model, K values, generation top_k, model, temperature, and
token limit as the baseline. Set only:

```json
{
  "config_id": "rag-structured-candidate-v0.1",
  "version": "0.1",
  "runtime_adapter": "structured_runtime_v1",
  "prompt_id": "rag-structured-prompt-v1"
}
```

merged with all baseline-equivalent material settings. The candidate prompt
content in Task 6 must preserve the existing non-empty-evidence prompt wording;
`rag-structured-prompt-v1` is a versioned identity for the extracted template,
not permission to tune prompt wording after results.

- [ ] **Step 8: Run baseline retrieval preflight**

Run:

```bash
python3 -m backend.rag.evaluation.cli preflight \
  --dataset data/evaluation/benchmark/rag-v0.1 \
  --config data/evaluation/configs/rag-current-runtime-v0.1.json \
  --mode retrieval
```

Expected: dataset/config valid, `vietnam_travel_parent_child` exists with count
`> 0`, embedding model is usable, no provider credential required.

- [ ] **Step 9: Execute canonical retrieval baseline**

Run:

```bash
python3 -m backend.rag.evaluation.cli run \
  --dataset data/evaluation/benchmark/rag-v0.1 \
  --config data/evaluation/configs/rag-current-runtime-v0.1.json \
  --mode retrieval \
  --output-dir data/evaluation/runs
```

Expected: one new baseline run directory, 25 per-example records, Hit@5/MRR@5/
nDCG@5 plus diagnostics for K=1/3/10/20, mandatory-slice metrics, zero synthetic
answer scores, and a protocol-valid baseline state. No improvement language is
allowed in the report.

- [ ] **Step 10: Execute full answer baseline when provider prerequisites are available**

Preflight first:

```bash
python3 -m backend.rag.evaluation.cli preflight \
  --dataset data/evaluation/benchmark/rag-v0.1 \
  --config data/evaluation/configs/rag-current-runtime-v0.1.json \
  --mode full
```

Then run full mode to a separate canonical run ID. Expected: six D5 dimensions
per valid judged example, explicit judge-invalid counts, and no fabricated score.
If provider access is unavailable, record that limitation and do not make
answer-quality claims; do not substitute a fake provider for canonical evidence.

- [ ] **Step 11: Write baseline report**

Create `docs/reports/rag/rag-baseline-v0.1.md` from canonical run artifacts. It
must state dataset/version, run ID, code revision + dirty state, resolved config,
retrieval metrics overall/by slice, judge-validity counts when full mode ran,
failures, limitations, and the sentence: **“This run establishes the frozen
baseline and does not by itself demonstrate improvement.”**

- [ ] **Step 12: Review checkpoint — baseline freeze**

The repository owner reviews benchmark identity, baseline config, run artifact,
and report before Task 6.

Expected: baseline is explicitly frozen. After this checkpoint, do not edit
benchmark v0.1, baseline config, or canonical baseline artifact to improve a
later candidate result.

## Task 6: Refactor Online RAG to Structured Retrieval, Context, and Generation Contracts

**Files:**

- Create: `backend/rag/retrieval/service.py`
- Modify: `backend/rag/retrieval/__init__.py`
- Create: `backend/rag/generation/context.py`
- Create: `backend/rag/generation/llm.py`
- Modify: `backend/rag/generation/rag_service.py`
- Modify: `backend/rag/generation/__init__.py`
- Create/complete: `backend/tests/unit/test_retrieval_service.py`
- Create: `backend/tests/unit/test_context_assembler.py`
- Create: `backend/tests/unit/test_rag_service.py`
- Modify: `backend/tests/integration/test_api.py`

**Interfaces:**

- Consumes: runtime contracts from Task 1 and the frozen baseline from Task 5.
- Produces:
  - `KnowledgeRetriever.retrieve(query: str, top_k: int) -> list[RetrievalResult]`
  - `ContextAssembler.assemble(results: Sequence[RetrievalResult]) -> ContextBundle`
  - `LLMGenerator.generate(user_message: str, context: ContextBundle) -> GeneratedAnswer`
  - unchanged `RAGService.generate_answer(user_message: str, top_k: int = 4) -> dict[str, Any]`

- [ ] **Step 1: Characterize legacy non-empty behavior before edits**

Write a failing/characterization test that injects deterministic embedder,
vector-store, and fake OpenAI client behavior into the current RAG path. Capture
these invariants:

1. query is stripped and empty input raises `ValueError`;
2. non-empty context lines remain `[Nguồn N: <title>]\n<text>` separated by
   `\n\n---\n\n`;
3. generation uses temperature `0.7`, `max_tokens=800`, configured model;
4. public result keys are exactly `reply`, `model`, `citations`;
5. citation projection de-duplicates by title as current behavior does.

Run the characterization test against pre-refactor code and require PASS before
changing `rag_service.py`.

- [ ] **Step 2: Write failing retriever tests**

Test that `KnowledgeRetriever` calls `embed_query(query)`, requests configured
`top_k`, maps every Chroma item through `map_chroma_result`, and returns ordered
structured evidence.

- [ ] **Step 3: Implement `KnowledgeRetriever`**

Constructor accepts injectable `embedder` and `vector_store` for tests, with
current defaults `VectorEmbedder("BAAI/bge-m3")` and
`ChromaVectorStore("vietnam_travel_parent_child")` when not supplied. Keep
collection selection injectable so evaluation config can choose it without
experiment-role names.

- [ ] **Step 4: Write failing context tests**

For two results, assert exact non-empty prompt context formatting and preserved
evidence order. For zero results:

```python
bundle = assembler.assemble([])
assert bundle.insufficient_evidence is True
assert bundle.evidence == ()
assert bundle.prompt_context == "Không tìm thấy tài liệu liên quan."
```

- [ ] **Step 5: Implement `ContextAssembler`**

Preserve legacy non-empty formatting exactly. Set `insufficient_evidence=True`
only when there are zero usable structured results; do not introduce a score
threshold.

Build citations from selected evidence as `CitationEvidence` and store them in
`ContextBundle.citations`. Multiple chunks from the same title/URL may map to one
public citation while internal `evidence_ids` retain every supporting chunk ID.

- [ ] **Step 6: Write failing generator tests**

For non-empty evidence, assert the exact current system-prompt wording is moved
to one versioned template `PROMPT_ID = "rag-structured-prompt-v1"`, with the
same temperature/token settings.

For insufficient evidence, assert no provider call occurs and the generated
answer is exactly:

```text
Tôi chưa có đủ thông tin trong cẩm nang để trả lời câu hỏi này một cách đáng tin cậy.
```

The returned `model` field remains the configured model identity so the public
schema stays compatible even when the provider is not called.

- [ ] **Step 7: Implement `LLMGenerator`**

Move provider-client construction and model call out of `RAGService`. Keep
current GitHub Models base URL/token behavior. Treat `ContextBundle` as the only
context input and carry `ContextBundle.citations` into `GeneratedAnswer`. Do not
import evaluation code.

- [ ] **Step 8: Rewrite `RAGService` as a thin facade**

Constructor accepts optional retriever/context assembler/generator dependencies
for tests. `generate_answer()` strips input, retrieves, assembles context,
generates, and projects:

```python
{
    "reply": generated.reply,
    "model": generated.model,
    "citations": [
        {"title": citation.title, "url": citation.url}
        for citation in generated.citations
    ],
}
```

Do not expose internal evidence IDs in the public v0.1 API response.

- [ ] **Step 9: Preserve chat API compatibility in integration tests**

Extend `backend/tests/integration/test_api.py` using a stubbed `RAGService` to
assert `/api/v1/chat` returns HTTP 200 with exactly the existing response fields
and preserves empty-message HTTP 400 behavior.

- [ ] **Step 10: Run R1 targeted tests**

Run:

```bash
python3 -m pytest \
  backend/tests/unit/test_rag_contracts.py \
  backend/tests/unit/test_retrieval_service.py \
  backend/tests/unit/test_context_assembler.py \
  backend/tests/unit/test_rag_service.py \
  backend/tests/integration/test_api.py -q
```

Expected: PASS with provider/vector behavior stubbed where appropriate.

- [ ] **Step 11: Wire `StructuredRuntimeAdapter`**

Update `backend/rag/evaluation/runtime.py` so `structured_runtime_v1` constructs
and calls the same `KnowledgeRetriever`, `ContextAssembler`, and `LLMGenerator`
contracts as online RAG. Evaluation must not duplicate prompt/context logic.

- [ ] **Step 12: Review checkpoint — candidate source freeze**

Review the exact Task 6 diff against the frozen baseline and predeclared
candidate config before running candidate evaluation.

Expected: no embedding/vector DB/provider/K tuning; non-empty prompt wording and
public schema remain characterized; explicit zero-evidence behavior is the only
intentional user-visible behavior change. Do not edit the candidate config after
this checkpoint unless results are discarded and a new predeclared candidate ID
is created.

## Task 7: Execute Candidate Evaluation, Apply D5 Gates, and Produce Review Evidence

**Files:**

- Create after execution: `data/evaluation/runs/<candidate-run-id>/run.json`
- Create after execution: `data/evaluation/runs/<candidate-run-id>/examples.jsonl`
- Create: `docs/reports/rag/rag-candidate-v0.1-comparison.md`
- Create only for owner-reviewed durable failures: versioned files under
  `data/evaluation/regression/`
- Modify: `docs/evaluation/rag-evaluation.md`
- Modify: `DEVELOPMENT.md`
- Modify only after passing/accepted evidence: `docs/roadmap/master-roadmap.md`

**Interfaces:**

- Consumes: frozen benchmark/baseline and candidate source/config.
- Produces: candidate run, paired D5 comparison, failure taxonomy, review report,
  and optional reviewed regression dataset version.

- [ ] **Step 1: Run candidate retrieval preflight**

Run:

```bash
python3 -m backend.rag.evaluation.cli preflight \
  --dataset data/evaluation/benchmark/rag-v0.1 \
  --config data/evaluation/configs/rag-structured-candidate-v0.1.json \
  --mode retrieval
```

Expected: same dataset and corpus identity are usable and candidate config is
valid before result generation.

- [ ] **Step 2: Execute canonical candidate retrieval run**

Run:

```bash
python3 -m backend.rag.evaluation.cli run \
  --dataset data/evaluation/benchmark/rag-v0.1 \
  --config data/evaluation/configs/rag-structured-candidate-v0.1.json \
  --mode retrieval \
  --output-dir data/evaluation/runs
```

Expected: 25 eligible examples unless a recorded validity/infrastructure failure
prevents interpretation.

- [ ] **Step 3: Compare candidate retrieval against the frozen baseline**

Run:

```bash
python3 -m backend.rag.evaluation.cli compare \
  --baseline data/evaluation/runs/<baseline-run-id> \
  --candidate data/evaluation/runs/<candidate-run-id> \
  --output data/evaluation/runs/<candidate-run-id>/comparison.json
```

Expected: same example IDs/contract; paired overall/slice deltas; exact D5 gate
decisions; uncertainty status. Because benchmark v0.1 has 25 examples,
`uncertainty_status` should be `not_applicable_n_lt_30` unless the benchmark was
re-versioned and expanded before candidate observation.

- [ ] **Step 4: Stop on `INVALID`, `INCONCLUSIVE`, or `FAIL`**

`INVALID`: repair only infrastructure/harness validity without changing the
frozen comparison contract, then rerun.

`INCONCLUSIVE`: do not promote the candidate. Any benchmark expansion creates a
new reviewed dataset version and requires fresh baseline + candidate runs.

`FAIL`: do not tune against benchmark rows in place. Diagnose per-example
`retrieval_miss`, `ranking_regression`, `citation_mismatch`, or
`unsupported_claim`; return to an approved candidate change before rerun.

Only `PASS` authorizes continuing toward R1 runtime acceptance.

- [ ] **Step 5: Run full candidate answer evaluation when the baseline answer layer exists**

If a protocol-valid full baseline was captured in Task 5, run candidate full
mode with the same judge model/prompt/rubric/schema and compare those runs. Apply
mean groundedness/correctness gates exactly. If no full baseline exists because
provider prerequisites were unavailable, state that answer-quality promotion
was not evaluated and make no answer-quality claim.

- [ ] **Step 6: Review durable failures before regression versioning**

For a failure worth protecting, reproduce it with public/synthetic/redacted
content, define durable expected behavior/source IDs, and present it to the
repository owner. Only after review create a new versioned regression manifest
and JSONL dataset under `data/evaluation/regression/`. Do not silently copy every
benchmark miss into regression data.

- [ ] **Step 7: Write comparison report**

`docs/reports/rag/rag-candidate-v0.1-comparison.md` must include baseline and
candidate run IDs/config IDs, same dataset/version, overall and mandatory-slice
deltas, all failed/passed gates, final state, failure counts/examples, judge
validity if applicable, uncertainty status, and the explicit claim boundary:
**this R1 refactor is a no-regression candidate; no quality-improvement claim is
made unless D5's separate improvement criterion is predeclared and met.**

- [ ] **Step 8: Document executable evaluation workflow**

Update `docs/evaluation/rag-evaluation.md` with the implemented CLI examples for
dataset validation, preflight, retrieval/full run, and compare. Do not alter the
accepted D5 formulas or thresholds.

Update `DEVELOPMENT.md` so retrieval-only evaluation is documented as local/no
provider, while full answer/judge evaluation is opt-in and may require
`GITHUB_TOKEN`, provider access, embedding model, and populated Chroma data.

- [ ] **Step 9: Update roadmap only when evidence supports it**

If the candidate comparison is `PASS` and required deterministic tests pass,
update `R1` and `R2` rows to `Accepted in working tree` only after repository-
owner change-set acceptance. Before that acceptance, keep them `In progress` and
link the run/report evidence.

- [ ] **Step 10: Review checkpoint**

Present retrieval/full comparison reports, per-example failures, and exact gate
state to the repository owner.

Expected: owner can explain why the result is PASS/FAIL/INCONCLUSIVE/INVALID and
trace aggregate changes to examples/evidence before accepting runtime changes.

## Task 8: Package Verification and Repository-owner Change-set Review

**Files:**

- Read/review: every path in the File Responsibility Map that changed.
- Modify after owner acceptance only:
  `docs/plans/2026-09-01-rag-repair-and-evaluation-harness-implementation.md`
- Modify after owner acceptance only: `docs/roadmap/master-roadmap.md`

**Interfaces:**

- Consumes: complete R1/R2 candidate change set and canonical evaluation evidence.
- Produces: verified package evidence and remaining Git-delivery gate.

- [ ] **Step 1: Run all deterministic evaluation/RAG tests**

Run:

```bash
python3 -m pytest \
  backend/tests/unit/test_rag_contracts.py \
  backend/tests/unit/test_retrieval_service.py \
  backend/tests/unit/test_context_assembler.py \
  backend/tests/unit/test_rag_service.py \
  backend/tests/unit/test_evaluation_dataset.py \
  backend/tests/unit/test_evaluation_metrics.py \
  backend/tests/unit/test_evaluation_judge.py \
  backend/tests/unit/test_evaluation_artifacts.py \
  backend/tests/unit/test_evaluation_comparison.py \
  backend/tests/unit/test_evaluation_runner.py \
  backend/tests/integration/test_rag_evaluation_flow.py \
  backend/tests/integration/test_api.py -q
```

Expected: PASS, no required network access.

- [ ] **Step 2: Run full backend regression suite**

Run:

```bash
python3 -m pytest backend/tests -q
```

Expected: PASS. A failure unrelated to R1/R2 is still reported honestly; do not
mask it or remove it from the command.

- [ ] **Step 3: Run static compilation**

Run:

```bash
python3 -m compileall backend
```

Expected: exit 0.

- [ ] **Step 4: Verify ADR dependency direction**

Run:

```bash
rg -n 'backend\.rag\.evaluation' backend/app backend/rag/generation backend/rag/retrieval backend/rag/contracts.py
```

Expected: no runtime import from the evaluation package. Documentation strings
or test-only paths do not count as runtime dependency; inspect every match.

- [ ] **Step 5: Revalidate frozen dataset/configs and canonical runs**

Run dataset validation and preflight again. Reload baseline/candidate artifacts
through the artifact reader and rerun comparison without performing retrieval.

Expected: comparison result and gates exactly match the recorded human report.

- [ ] **Step 6: Scan for synthetic fallback and hard-coded experiment roles**

Run:

```bash
rg -n 'Default fallback score|baseline_store|parent_child_store|winner.*parent_child' backend/rag/evaluation backend/tests
```

Expected: no governed synthetic fallback or hard-coded experiment-role storage
remains. A test fixture may contain strings only when explicitly asserting they
are rejected/unsupported.

- [ ] **Step 7: Run secret/privacy review**

Inspect dataset, run artifacts, reports, and logs for token-shaped values and
unnecessary full-document copies. Confirm run evidence uses bounded excerpts and
stable IDs.

Expected: no `GITHUB_TOKEN` value, API credential, authorization header, or
private user content is persisted.

- [ ] **Step 8: Run repository diff checks**

Run:

```bash
git diff --check
git status --short --untracked-files=all
```

Expected: no whitespace errors; status contains only the approved R1/R2 package
plus its canonical evidence. Review untracked files directly because `git diff`
does not show them.

- [ ] **Step 9: Complete exact change-set review**

Compare every changed/untracked file with the approved spec, ADR, and this plan.
Confirm all 24 spec acceptance criteria have either fresh passing evidence or an
explicit blocking limitation. A required provider-dependent acceptance item that
could not run remains a disclosed limitation; it must not be relabeled PASS.

- [ ] **Step 10: Repository-owner acceptance gate**

Present changed files, test outputs, canonical run IDs, comparison state, failed
or unavailable checks, and rollback path to the repository owner.

Expected: implementation remains `In Progress` until the owner explicitly
accepts the repository change set.

- [ ] **Step 11: Record completion only after owner acceptance**

After explicit owner acceptance, set this plan to `Completed`, update its
completion record, and set R1/R2 roadmap rows to `Accepted in working tree` with
exact report/run evidence. This does not authorize staging, commit, push, PR,
merge, tag, release, or other Git delivery actions.

## Spec Coverage Matrix

| Spec acceptance criterion | Plan evidence |
| --- | --- |
| 1. Reviewed benchmark v0.1 with all mandatory slices | Task 5 Steps 2-5 |
| 2. Dataset validation rejects missing/incompatible fields | Task 2 |
| 3. Current parent-child runtime becomes first frozen baseline | Task 5 Steps 6-12 |
| 4. Hit@5/MRR@5/nDCG@5 plus diagnostics | Tasks 3 and 5 |
| 5. Six answer dimensions with invalid counts when executed | Tasks 4 and 5 |
| 6. Canonical run identity/config/evidence/state fields | Tasks 2-4 |
| 7. Configurable run roles; no collection-name role assumption | Tasks 2 and 4 |
| 8. Retrieval-only mode without external model call | Task 4 |
| 9. Paired deltas, slices, applicable uncertainty | Tasks 3 and 7 |
| 10. Incompatible comparisons become INVALID/no governed delta | Task 3 |
| 11. Synthetic judge fallback removed; `judge_invalid` enforced | Task 4 |
| 12. Structured chunk/document/source retrieval identity | Tasks 1 and 6 |
| 13. Retrieval/context/generation independently testable and shared with evaluation | Task 6 |
| 14. Citation provenance traceable to retrieved evidence | Tasks 1 and 6 |
| 15. Explicit zero-evidence behavior without score threshold | Task 6 |
| 16. Public `reply`/`model`/`citations` compatibility | Task 6 |
| 17. Harness validity/metric/judge/artifact/comparison/integration tests | Tasks 2-4 |
| 18. RAG retrieval/context/provenance/insufficient-evidence/API tests | Tasks 1 and 6 |
| 19. Human-readable frozen baseline report | Task 5 |
| 20. Candidate comparison applies D5 gates and claim boundary | Task 7 |
| 21. Durable failures enter regression only after review/versioning | Task 7 Step 6 |
| 22. No new vector DB/embedder/provider/hosted evaluation/observability system | Global Constraints and Task 6 review |
| 23. Required ADR accepted before plan approval | Plan metadata and ADR link |
| 24. Git delivery remains repository-owner controlled | Global Constraints and Task 8 |

Self-review found no acceptance criterion without an implementing task.

## Package Verification

The final evidence package must contain:

1. benchmark v0.1 validation with 25 examples and five mandatory slices;
2. baseline/candidate run config validation;
3. protocol-valid frozen current-runtime retrieval baseline;
4. answer-quality baseline/candidate evidence when provider prerequisites exist,
   otherwise an explicit no-claim limitation;
5. structured retrieval/context/generation contract tests;
6. no-network evaluation harness integration test;
7. strict `judge_invalid` tests with no synthetic scores;
8. artifact reload and comparison reproducibility;
9. public chat response compatibility;
10. full backend test and compile results;
11. ADR dependency-direction grep;
12. D5 comparison state and gate decisions;
13. `git diff --check`, repository status, and direct review of untracked files.

No single check substitutes for another. In particular, a green unit suite does
not prove benchmark validity, and a PASS retrieval comparison does not prove
answer quality.

## Rollback

1. Preserve frozen benchmark/config/baseline evidence even if the R1 candidate is
   rejected.
2. Revert candidate runtime files to the pre-Task-6 online path without rewriting
   Chroma collections or benchmark history.
3. Keep the R2 harness when safe because a failed RAG candidate does not
   invalidate valid measurement infrastructure.
4. Never edit benchmark v0.1 or baseline artifacts to improve a candidate result;
   corrections create a new dataset/run identity.
5. If new runtime contracts prove unsafe, remove only unaccepted candidate code
   through normal reviewed Git history; do not use destructive reset/clean
   commands without repository-owner authorization.
6. Git delivery remains a separate owner-controlled gate after implementation
   acceptance.

## Completion Record

Plan version 0.1 is **Approved**. The governing R1/R2 specification v0.1 is
Approved, ADR 0001 is Accepted, and the repository owner approved this plan on
2026-09-01.

This approval authorizes execution of Tasks 1-8 in dependency order,
including creation of benchmark/config/run/report artifacts and approved R1/R2
source/test/documentation changes. It does not authorize Git staging, commit,
push, PR creation, merge, tag, release, branch deletion, or history rewriting.

Execution must stop at the explicit benchmark review gate in Task 5, any failed
D5 promotion gate in Task 7, any scope/architecture deviation, or any required
verification failure not resolved by this plan.
