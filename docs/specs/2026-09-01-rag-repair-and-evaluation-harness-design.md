# RAG Repair and Evaluation Harness Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-01 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Runtime milestones R1 RAG Repair and Baseline plus R2 Evaluation Harness, delivered in lockstep under the accepted D5 evaluation contract |
| Parent design | [Architecture Baseline Design](./2026-08-31-architecture-baseline-design.md), version 0.1; [Roadmap and Learning Design](./2026-08-31-roadmap-and-learning-design.md), version 0.1; [Evaluation Protocols Design](./2026-08-31-evaluation-protocols-design.md), version 0.1 |
| Depends on | [Foundation Cleanup Design](./2026-09-01-foundation-cleanup-design.md), version 0.1, accepted change set; [RAG Evaluation Protocol](../evaluation/rag-evaluation.md) |
| Architecture approval | Repository owner approved the combined R1/R2 design in conversation on 2026-09-01 |
| Implementation plan | [RAG Repair and Evaluation Harness Implementation Plan](../plans/2026-09-01-rag-repair-and-evaluation-harness-implementation.md), version 0.1 (Approved) |
| Related issue | None - combined R1/R2 design and specification drafting were authorized by the repository owner in this conversation |
| Superseded document | None |

## Summary

R1 and R2 will be implemented as one coordinated engineering change because a
RAG repair is not trustworthy without a frozen baseline and a repeatable
evaluation harness, while an evaluation harness is most useful when exercised
against the real RAG path rather than an abstract demo.

The selected design first freezes the current runtime RAG configuration as the
initial baseline, then introduces a config-driven evaluation harness and clear
runtime boundaries for retrieval, context assembly, generation, and evidence.
The refactored RAG path becomes a candidate that must be evaluated against the
frozen baseline using the accepted D5 protocol. The first valid baseline run
describes current quality only; it cannot support an improvement claim.

The current runtime collection `vietnam_travel_parent_child` is the initial
baseline retrieval collection because it is what `RAGService` actually uses.
The legacy `vietnam_travel_knowledge` fixed-size collection remains available
as a diagnostic comparator, but it does not define the baseline role merely
because the old evaluator names it `baseline`.

Approval of version 0.1 authorizes drafting and accepting the required ADR and,
after that architecture record is accepted, preparing an R1/R2 implementation
plan. It does not authorize source edits, dataset creation, model calls,
benchmark execution, dependency changes, or Git delivery.

## Current-state Evidence

Current-state claims are based on Codebase Memory MCP Verify-tier evidence and
direct source/document reads performed during the approved design session. The
graph project was `Users-tnhatnguyendev2805-Documents-Projects-travel-agent`,
generation `2026-09-01T01:46:47Z`, with 1303 nodes and 2445 edges. Coverage
reported `no_recorded_issue` with matching metadata for the material RAG,
evaluator, test, architecture, roadmap, and evaluation-protocol paths. This is
a best-effort coverage signal, not proof of semantic completeness.

| Evidence | Current fact relevant to R1/R2 |
| --- | --- |
| [`backend/rag/generation/rag_service.py`](../../backend/rag/generation/rag_service.py) | `RAGService` defaults to collection `vietnam_travel_parent_child`, uses embedding model `BAAI/bge-m3`, performs retrieval and context/citation assembly inside `generate_answer`, and calls the configured model with temperature `0.7` and `max_tokens=800`. The chat route currently calls it with `top_k=4`. |
| [`backend/app/api/chat.py`](../../backend/app/api/chat.py) | The current chat path calls `RAGService.generate_answer` and returns the public response fields `reply`, `model`, and `citations`. |
| [`backend/rag/evaluation/evaluator.py`](../../backend/rag/evaluation/evaluator.py) | The legacy evaluator hard-codes `vietnam_travel_knowledge` as `baseline_store` and `vietnam_travel_parent_child` as `parent_child_store`, computes retrieval metrics at K values `1, 3, 5, 10, 20`, and references evaluation files that are not currently present. |
| [`backend/rag/evaluation/llm_judge_evaluator.py`](../../backend/rag/evaluation/llm_judge_evaluator.py) | The legacy judge compares the two hard-coded retrieval strategies. On JSON parse failure it fabricates scores favoring the parent-child arm. D5 forbids synthetic fallback evidence. |
| [`backend/tests/unit/test_evaluator.py`](../../backend/tests/unit/test_evaluator.py) | Existing unit tests cover metric helpers and basic hit/no-hit behavior, but not dataset schemas, run compatibility, judge validity, result states, artifacts, or the full harness lifecycle. |
| [RAG Evaluation Protocol](../evaluation/rag-evaluation.md) | D5 requires frozen comparison contracts, `K=5` as primary retrieval K, separate retrieval and answer evaluation, validated judge evidence, mandatory slices, explicit failure taxonomy, and final states `PASS`, `FAIL`, `INCONCLUSIVE`, or `INVALID`. |
| [Target Architecture](../architecture/target-state.md) | The target design separates knowledge retrieval from generation and requires selected evidence to remain inspectable for later evaluation and memory work. |
| [Target Data Model](../architecture/data-model.md) | `ContextBundle`, `RetrievalChunk`, and `EvaluationTrace` are future seams for representing what generation saw and how quality evidence is recorded. |
| [Master Roadmap](../roadmap/master-roadmap.md) | The runtime order explicitly pairs `R1` and `R2`; R1 needs a trustworthy baseline and R2 needs a real RAG flow to evaluate. |

Direct filesystem inspection during the design session found no
`data/evaluation/` directory and no `docs/reports/` directory. Therefore no
current evaluator output may be treated as a repository-reviewable frozen
baseline.

Codebase Memory tracing showed `chat_endpoint` as the only current repository
caller of `RAGService.generate_answer`. Inside that method, embedding, vector
retrieval, context assembly, citation mapping, model access, and response
formatting are coupled together. R1 may separate those concerns while
preserving the public chat response contract.

## Context

Travel Agent is moving from an early RAG prototype toward a workspace-first
travel agent with trip state and memory. Later memory quality will be difficult
to interpret if the project cannot first answer these questions reliably:

1. Which evidence was retrieved for a request?
2. Which evidence was actually passed to generation?
3. Which source supports a citation or factual claim?
4. Did a candidate improve retrieval, answer quality, or neither?
5. Did a failed judge, missing index, or broken provider invalidate the run?
6. Can another engineer reproduce the comparison from recorded configuration?

The existing evaluator contains useful metric code but is organized around two
named Chroma collections instead of a reusable experiment contract. The online
RAG path also hides retrieval, context assembly, generation, and evidence inside
one method. R1 and R2 therefore establish the first production-oriented quality
loop:

```text
freeze current behavior -> measure baseline -> make candidate change ->
measure candidate -> inspect failures -> accept/reject -> add regressions
```

## Users

1. **Repository owner:** needs evidence that explains current RAG quality and
   whether a later change genuinely improves it.
2. **AI engineer:** needs reusable datasets, run configuration, per-example
   evidence, metrics, and failure analysis.
3. **Coding agent:** needs a deterministic contract that prevents convenient
   metric, dataset, K, prompt, or baseline changes after seeing results.
4. **Reviewer:** needs machine-readable artifacts and a concise human report
   traceable to code revision, dataset version, configuration, and examples.
5. **Future memory engineer:** needs an evaluation lifecycle whose shared
   contracts can later support memory evaluation without coupling memory to
   RAG-specific collection names.

## Problem Statement

The repository has measurement utilities but not yet a trustworthy evaluation
system. Three problems block disciplined RAG iteration.

First, the word `baseline` currently means different things in runtime and
evaluation. Runtime uses `vietnam_travel_parent_child`, while the legacy
evaluator labels `vietnam_travel_knowledge` as baseline. A baseline must be a
frozen run identity, not a hard-coded collection nickname.

Second, runtime RAG does not expose stable evidence contracts. Retrieval items,
prompt context, citations, and final answer formatting are assembled inside one
method. That makes it difficult to test retrieval independently, reproduce the
exact context passed to a model, or explain citation failures.

Third, the evaluator cannot yet provide valid promotion evidence. Required
datasets are absent, result artifacts are not governed by a run schema, judge
errors can become synthetic favorable scores, and tests do not cover full-run
validity or comparison behavior.

R1/R2 must convert these pieces into a measurable engineering loop without
prematurely changing embeddings, vector database technology, provider choice,
or public API shape.

## Goals

1. Freeze the current runtime RAG configuration as the first reviewable RAG
   baseline before candidate RAG behavior changes.
2. Create a versioned RAG evaluation dataset policy with `development`,
   `regression`, `benchmark`, and `safety` roles.
3. Build one local evaluation harness that accepts baseline/candidate run
   configuration instead of hard-coding strategy or collection names.
4. Preserve retrieval and answer-quality evaluation as separate layers under
   the D5 protocol.
5. Standardize retrieved evidence so chunk identity, document identity, source,
   score semantics, and text remain traceable through context and generation.
6. Separate retrieval, context assembly, generation, metric calculation, judge
   validation, comparison, and artifact writing into independently testable
   responsibilities.
7. Preserve the external `/api/v1/chat` response contract while making internal
   citations traceable to retrieved evidence.
8. Represent insufficient evidence explicitly instead of encouraging
   unsupported generation when no usable retrieval evidence exists.
9. Remove synthetic judge fallback scoring from governed evaluation.
10. Produce machine-readable per-example/run artifacts and human-readable
    baseline/comparison reports.
11. Classify failures using the accepted D5 taxonomy so durable failures can
    become reviewed regression examples.
12. Make the harness lifecycle reusable later for memory evaluation without
    implementing memory metrics in R2 v0.1.

## Non-goals

1. R1/R2 does not implement trip workspaces, conversation persistence, memory
   extraction, memory retrieval, long-term memory, short-term memory, or planner
   state.
2. It does not replace Chroma, `BAAI/bge-m3`, or the configured model provider
   unless baseline evidence and a separately approved candidate scope justify
   that change.
3. It does not require a hosted experiment-tracking platform, hosted vector
   database, tracing vendor, or external evaluation SaaS.
4. It does not redesign authentication, privacy policy, retention, deployment,
   production observability, or public release infrastructure.
5. It does not claim that the first frozen baseline is good, bad, improved, or
   production-ready merely because the run is valid.
6. It does not promote `vietnam_travel_knowledge` to canonical baseline status;
   that collection remains a comparator or diagnostic configuration.
7. It does not introduce a heuristic retrieval score threshold for abstention
   without reviewed benchmark evidence and a predeclared candidate contract.
8. It does not change the public chat response fields `reply`, `model`, and
   `citations` in version 0.1.
9. It does not stage, commit, push, open a pull request, merge, tag, publish, or
   alter Git history.

## Assumptions

1. The current parent-child runtime collection and embedding model are
   available locally when the baseline is executed.
2. Benchmark labels can be created from public, synthetic, or reviewed redacted
   travel data without private user data.
3. A valid retrieval benchmark can be created before any quality-improvement
   claim is attempted.
4. The current external model provider may be nondeterministic even when known
   generation parameters are recorded; the harness must record that limitation
   rather than imply bit-for-bit reproducibility.
5. The current chat API contract can remain stable while internal RAG code is
   decomposed.
6. R2 can define generic run, example, state, and artifact contracts without
   implementing future memory-specific metrics.
7. Existing retrieval metric functions may be reused after characterization if
   they satisfy D5 definitions; legacy names and invalid fallbacks are not
   authoritative.
8. If implementation discovers that a storage, provider, public API, deployment,
   or trust boundary must change, work stops and returns to architecture review.

## Selected Approach

Use a **lockstep R1/R2 baseline-first architecture**.

1. Freeze the current runtime RAG configuration before changing candidate
   behavior.
2. Introduce a config-driven R2 runner capable of baseline-only and paired
   baseline/candidate execution.
3. Create and validate the benchmark schema before any governed run.
4. Use the same retrieval/context/generation contracts from online RAG and the
   evaluation harness; the harness calls service/module contracts directly and
   does not evaluate by scraping the HTTP route.
5. Refactor `RAGService` into a thin orchestration/compatibility boundary over
   retrieval, context assembly, generation, and response projection.
6. Standardize retrieval evidence and retain identity through context,
   citations, per-example records, and reports.
7. Repair judge validity before judge output is allowed to influence a run.
8. Run and freeze the first valid baseline.
9. Evaluate the refactored RAG path as a candidate against that baseline using
   the same frozen benchmark and comparison contract.
10. Treat the structural refactor as a no-regression candidate unless it meets
    a predeclared D5 improvement criterion.

## Alternatives Considered

### Alternative A: Clean up only the existing evaluator

Keep `RAGEvaluator` and `LLMJudgeEvaluator`, add missing files, remove the
fallback, and continue comparing the two existing Chroma collections.

This is initially smaller but preserves the wrong abstraction: collection names
define experiment roles, the evaluator stays detached from the actual runtime
baseline, and later memory work would need another evaluation system. Rejected.

### Alternative B: Build a generic evaluation framework before touching RAG

Design a domain-neutral experiment platform first and later adapt RAG and memory
to it.

This maximizes theoretical reuse but creates interfaces without enough pressure
from real current product behavior and delays the baseline the roadmap needs.
Rejected as premature abstraction.

### Alternative C: R1 and R2 in lockstep under one evaluation contract

Freeze the real current RAG as baseline, build only the generic contracts
required by D5, exercise them immediately against RAG, and retain extension
seams for memory. Selected.

## User and System Flows

### Flow 1: Create the first frozen baseline

1. Validate the benchmark manifest and every eligible example before retrieval.
2. Resolve the baseline run configuration to the current runtime identity.
3. Record code revision and dirty-working-tree state.
4. Retrieve enough results to compute governed retrieval metrics at
   `K = 1, 3, 5, 10, 20`; `K=5` is primary.
5. For answer-quality evaluation, preserve the current runtime generation
   configuration, including context `top_k=4`, current prompt identity,
   configured model, temperature `0.7`, and `max_tokens=800`, unless direct
   pre-run characterization proves current behavior differs.
6. Generate answers only when the answer layer is enabled and provider
   preconditions are satisfied.
7. Validate deterministic checks and judge output independently.
8. Persist per-example evidence and aggregate metrics.
9. Produce `PASS`, `FAIL`, `INCONCLUSIVE`, or `INVALID` according to D5.
10. Mark the run as the first frozen baseline only if it is protocol-valid.
11. Publish a baseline report stating explicitly that baseline creation alone
    is not an improvement claim.

### Flow 2: Evaluate a RAG candidate

1. Freeze candidate config, dataset version, primary metrics, K values, slices,
   generation config, judge contract, thresholds, and baseline run ID before
   candidate results are inspected.
2. Reject incompatible comparisons for governed metrics.
3. Run candidate retrieval and optional generation on the same eligible examples.
4. Compute per-example and aggregate candidate metrics.
5. Join candidate results to baseline results by stable `example_id`.
6. Calculate paired deltas overall and by mandatory slice.
7. Apply D5 no-regression and improvement gates.
8. Emit failure labels and representative examples.
9. Produce a comparison report with no synthetic scores.

### Flow 3: Turn a real failure into regression evidence

1. Identify a failure through benchmark, reviewed manual testing, or later
   product evidence.
2. Reproduce it with public, synthetic, or redacted content.
3. Assign stable example ID, expected evidence, slice, and failure label.
4. Review that the expected behavior is durable product behavior.
5. Add the case through a new regression dataset version.
6. Re-run affected comparisons and link the run evidence in review.

### Flow 4: Online chat after RAG decomposition

1. `/api/v1/chat` validates the user message as it does today.
2. RAG orchestration asks the retrieval component for structured evidence.
3. The context assembler converts selected evidence into generation context
   while retaining provenance.
4. If no usable evidence exists, context carries an explicit
   insufficient-evidence condition; v0.1 does not invent a score threshold.
5. The generation component calls the configured model provider.
6. Internal citation records point back to retrieved evidence.
7. The API adapter returns compatible `reply`, `model`, and `citations` fields.

## Components and Dependency Direction

The architecture defines responsibilities, not final Python filenames. The
implementation plan will map these boundaries to the smallest changes that fit
the existing repository.

### Online RAG responsibilities

| Component | Responsibility | Allowed dependencies |
| --- | --- | --- |
| RAG orchestration | Coordinate retrieval, context assembly, generation, and response projection | Retrieval contract, context assembler, generation contract |
| Retrieval component | Embed query and retrieve structured travel evidence | Embedding adapter, vector-store adapter |
| Context assembler | Select/format retrieved evidence for generation while retaining provenance | Retrieval result contract |
| Generation component | Call configured model using a supplied context bundle | Model-provider adapter, prompt configuration |
| Response projection | Preserve public chat response shape and project internal evidence to user citations | Generated result, citation records |

### Evaluation responsibilities

| Component | Responsibility | Allowed dependencies |
| --- | --- | --- |
| Dataset validator | Load manifest/examples and enforce role/version/schema/eligibility rules | Structured dataset contracts |
| Run-config resolver | Resolve behavior identities without hard-coded experiment roles | Config schema, runtime adapters |
| Evaluation runner | Execute retrieval-only or retrieval-plus-generation runs | Dataset validator, runtime contracts, metrics, artifact writer |
| Retrieval metrics | Compute Hit@K, MRR@K, nDCG@K and diagnostics | Per-example retrieval evidence |
| Answer evaluator | Run deterministic checks and optional validated judge scoring | Generated answer, governed evidence/reference, judge adapter |
| Judge adapter | Call configured judge and validate output contract | Model-provider adapter, frozen judge config |
| Comparator/gates | Join compatible runs, compute deltas/slices, apply D5 rules | Valid run artifacts |
| Artifact writer | Persist run summary, per-example records, errors, and reports | Validated result objects |

Required dependency direction:

```text
HTTP API -> RAG orchestration -> retrieval -> embedder/vector store
                            -> context assembly
                            -> generation -> model provider

Evaluation runner -> same retrieval/context/generation contracts
                  -> metrics/judge/comparator -> artifacts
```

The online API must not depend on the evaluation runner. Evaluation code may
depend on stable runtime contracts, but runtime behavior must not depend on
benchmark files, judge availability, or evaluation artifacts.

## Behavioral and Data Contracts

### Retrieval result contract

Each retrieval item exposed across the RAG/evaluation boundary must contain at
least:

| Field | Requirement |
| --- | --- |
| `chunk_id` | Stable retrieved-chunk identity when available; missing identity invalidates metrics that require chunk identity |
| `document_id` | Stable source-document identity used by document-level relevance contracts |
| `title` | Human-readable source title when available |
| `url` | Canonical source URL when available |
| `score` | Numeric retrieval value when the backend exposes one |
| `text` | Text selected for context or evaluation |

Run configuration must record score semantics, including whether lower distance
or higher similarity is better. Evaluation logic must not compare raw scores
across incompatible score semantics.

Adapter-specific Chroma metadata may remain internal, but governed metrics and
context assembly must not require callers to understand Chroma's raw dictionary
shape.

### Context and citation contract

Context assembly must preserve a stable link from every selected context item
to its retrieval result. Internal citation evidence must identify the
supporting retrieval item or source even though the public response continues
to expose the existing citation projection.

The system must distinguish:

1. retrieved evidence,
2. evidence selected into generation context,
3. sources projected into the response citation list,
4. sources actually referenced by an answer when that can be determined.

The harness must retain enough information to classify `citation_mismatch` and
`unsupported_claim` without guessing from aggregate metrics.

When retrieval returns no usable items, context assembly must produce an
explicit insufficient-evidence state. Version 0.1 does not define a score-based
abstention threshold; adding one is a candidate behavior change requiring
benchmark justification.

### Dataset layout

Repository-reviewed datasets live under:

```text
data/evaluation/
├── development/
├── regression/
├── benchmark/
└── safety/
```

Each dataset version has a manifest plus JSONL examples. Exact filenames are an
implementation-plan detail; the logical contract is fixed here.

Dataset manifest fields must include at least:

| Field | Meaning |
| --- | --- |
| `dataset_id` | Stable dataset family identity |
| `version` | Immutable reviewed dataset version |
| `role` | `development`, `regression`, `benchmark`, or `safety` |
| `domain` | `rag` for this milestone |
| `created_at` | Creation timestamp/date |
| `reviewed_at` | Date the version became reviewable for its declared role |
| `reviewer` | Reviewer identity or repository role that accepted labels/version |
| `provenance` | Public, synthetic, or redacted source description |
| `intended_population` | Product/query population represented by the dataset |
| `inclusion_exclusion_rules` | Frozen rules governing membership in this version |
| `relevance_contract` | How expected retrieval evidence is interpreted |
| `mandatory_slices` | Slice names required by D5 for this benchmark version |

Each example must include at least:

| Field | Requirement |
| --- | --- |
| `example_id` | Stable unique ID within the dataset family |
| `question` | User-style travel query |
| `dataset_role` | Must agree with manifest role |
| `category` or `slice` | At least one reviewable classification; benchmark examples must support mandatory-slice reporting |
| expected evidence | At least one governed relevance signal such as expected `document_id`, expected evidence identity/text, or expected source URL |
| `reference_answer` | Required only when the selected answer-scoring method needs a reference; otherwise explicit absence is valid |

The validator must reject examples missing data required by the selected metrics
instead of silently converting missing labels into zeros.

### Initial benchmark v0.1 slices

The first RAG benchmark must support all D5 mandatory slices:

1. single-source factual lookup,
2. multi-evidence synthesis,
3. ambiguous or underspecified queries,
4. source/citation-sensitive queries,
5. long-tail or difficult retrieval queries.

The benchmark manifest freezes examples and slice assignments before candidate
results are inspected. Development examples may evolve; benchmark changes create
a new version.

### Run configuration contract

A run configuration identifies behavior, not experiment role. It must capture:

1. stable `config_id` and version,
2. collection/index identity,
3. embedding model identity,
4. retrieval K settings and score semantics,
5. generation context `top_k`, prompt version/identity, model identity,
   temperature, token limit, and other material sampling settings,
6. judge model/prompt/rubric/schema/sampling settings when judge evidence is
   enabled,
7. feature flags that materially affect the evaluated path.

`baseline` and `candidate` are labels assigned when comparing run artifacts;
they must not be encoded as collection-name assumptions in evaluation core.

### Frozen baseline configuration

The initial baseline must characterize current online RAG behavior before
candidate repair changes. At specification time the known identity is:

| Property | Frozen baseline intent |
| --- | --- |
| Retrieval collection | `vietnam_travel_parent_child` |
| Embedding model | `BAAI/bge-m3` |
| Retrieval evaluation | Retrieve enough results for `K=1,3,5,10,20`; primary comparison `K=5` |
| Generation context | Preserve current runtime `top_k=4` for baseline answer characterization |
| Generation model | Current configured `LLM_MODEL`, recorded with provider/model identity |
| Generation sampling | Preserve current runtime settings including temperature `0.7` and `max_tokens=800`, unless pre-run characterization proves otherwise |
| Prompt | Current runtime prompt frozen by version/hash or another reviewable identity |

Provider output may remain nondeterministic. The run must record sampling
settings and provider/model identity; near-threshold valid evidence that cannot
support a stable decision may be `INCONCLUSIVE` rather than being interpreted
favorably.

The fixed-size `vietnam_travel_knowledge` configuration may be run as a
diagnostic comparator after the baseline contract is frozen. Its legacy name
does not make it the canonical baseline.

### Run artifact contract

Generated machine-readable artifacts live under a dedicated run directory,
conceptually:

```text
data/evaluation/runs/<run_id>/
├── run.json
└── examples.jsonl
```

Whether generated run directories are committed by default is an implementation
plan decision based on repository size and privacy. A reviewed human baseline
or comparison report belongs under `docs/reports/` and may reference the
machine-readable `run_id`.

`run.json` must record at least:

1. `run_id`, start/end time, and final state,
2. dataset ID/version/role, manifest identity, and eligible/invalid/skipped counts,
3. code revision and dirty-working-tree state,
4. run-config identity and material retrieval/generation settings,
5. judge configuration and judge-validity counts when applicable,
6. baseline run ID for candidate comparisons,
7. aggregate metrics and mandatory-slice metrics,
8. paired deltas, applicable uncertainty estimates, and gate decisions,
9. timing/error summaries,
10. failure counts by D5 taxonomy.

Each `examples.jsonl` record must preserve enough evidence for review:

1. `example_id` and slice/category,
2. eligibility and invalidity reason when applicable,
3. governed expected relevance/reference labels used by selected metrics,
4. retrieved evidence in ranked order with stable identities,
5. generation-context evidence identities when answer evaluation is enabled,
6. answer output and projected citations when enabled,
7. retrieval metrics and per-example metric contributions,
8. answer-quality checks/scores and judge validity when enabled,
9. failure labels,
10. timing/errors for the example.

Artifacts prefer stable IDs and minimal necessary excerpts. They must not copy
credentials, tokens, or unnecessary sensitive content.

### Comparison contract

A candidate comparison is valid only when baseline and candidate share a
compatible frozen contract for each governed metric. At minimum:

1. same benchmark dataset ID/version and eligible examples,
2. same relevance contract,
3. same primary K and metric definitions,
4. same mandatory-slice definitions,
5. same answer-quality rubric and judge contract for judge-based deltas,
6. generation differences treated as predeclared candidate behavior rather than
   hidden measurement changes.

The harness must refuse or mark `INVALID` a comparison that tries to calculate
a governed delta across incompatible contracts.

## R1 Runtime Repair Contract

R1 may change internal RAG structure and candidate behavior only after the
baseline identity and benchmark contract are frozen.

Required R1 repairs are:

1. standardize retrieval output behind the retrieval result contract,
2. separate retrieval from context assembly,
3. separate context assembly from model-provider generation,
4. preserve evidence identity from retrieval through internal citations,
5. make empty/insufficient evidence explicit,
6. keep the current public chat response schema compatible,
7. make the runtime path callable by the evaluation harness without HTTP,
8. avoid changing embedding model, vector-store technology, or model provider
   solely as part of structural cleanup.

R1 may retain `RAGService` as a compatibility/orchestration facade. The plan
should prefer the smallest module changes that create clear ownership and
testability.

## R2 Harness Contract

R2 must support:

1. **baseline-only run:** produces a protocol-valid frozen run artifact without
   claiming improvement;
2. **paired comparison:** evaluates a candidate against an explicitly named,
   compatible baseline run.

The harness must support retrieval-only execution without external model calls.
Answer-quality execution is optional at command time but required before making
answer-quality claims.

Evaluation core must not contain hard-coded baseline/candidate collection names.
Adapter/config layers may refer to concrete current collections.

The harness must remain extensible to later memory evaluation through shared
run, dataset, result-state, artifact, and comparison contracts. R2 v0.1 does not
implement memory-specific write/read/use metrics.

## Testing and Evaluation

### Test layers

1. **Dataset schema tests:** valid manifests/examples load; role mismatches,
   duplicate IDs, missing required relevance labels, and invalid enum values
   fail explicitly.
2. **Metric unit tests:** Hit@K, MRR@K, nDCG@K and diagnostics match D5 formulas
   on deterministic fixtures, including no-hit and multiple-relevant cases.
3. **Retrieval contract tests:** Chroma/raw results map to stable retrieval
   result objects with preserved IDs/source data and score semantics.
4. **Context/citation tests:** selected evidence remains traceable through
   context assembly and response projection.
5. **Judge validation tests:** malformed JSON, missing fields, invalid enums,
   out-of-range scores, provider failures, and total mismatches produce
   `judge_invalid`; no synthetic score is emitted.
6. **Run-validity tests:** missing dataset/index, incompatible comparison,
   provider failure, and invalid judge evidence produce the correct D5 state.
7. **Artifact tests:** run summary and per-example records contain required
   fields and can be reloaded for comparison.
8. **Harness integration test:** deterministic local fixtures execute a full
   retrieval-only baseline/candidate comparison without network access.
9. **RAG compatibility tests:** chat still returns compatible `reply`, `model`,
   and `citations` through a stubbed provider.
10. **Baseline preflight:** the real baseline command validates dataset/index
    preconditions before expensive or external work.

### Governed metrics

Primary retrieval metrics are:

1. Hit@5,
2. MRR@5,
3. nDCG@5.

Diagnostic retrieval metrics include K values `1`, `3`, `10`, and `20`,
Precision@K, source URL hit, relevant chunk count, and unique document count
where labels make those metrics valid.

Answer-quality dimensions remain the D5 six-dimension rubric:

1. groundedness,
2. answer relevance,
3. correctness,
4. completeness,
5. practical usefulness,
6. clarity.

### Initial gates

The implementation must apply the accepted D5 gates without weakening them in
code or run configuration:

1. Hit@5 decline no greater than `0.01` absolute,
2. MRR@5 decline no greater than `0.01` absolute,
3. nDCG@5 decline no greater than `0.01` absolute,
4. mandatory-slice Hit@5 decline no greater than `0.03` unless a trade-off was
   preapproved,
5. mean groundedness at least `4.0/5.0` and decline no greater than `0.10`,
6. mean correctness at least `4.0/5.0` and decline no greater than `0.10`,
7. an improvement claim requires at least `0.02` absolute gain on a
   predeclared primary metric or an equivalent reviewed predeclared benefit.

The first valid baseline run cannot support an improvement claim by itself.

## Errors and Edge Cases

1. **Benchmark missing or malformed:** run is `INVALID`; an empty benchmark is
   never success.
2. **Required relevance label missing:** affected example/metric is invalid;
   missing labels are not zero scores.
3. **Baseline run missing:** paired candidate comparison is `INVALID`.
4. **Comparison contract incompatible:** governed delta is `INVALID`.
5. **Chroma collection/index unavailable:** record `infrastructure_failure`;
   required retrieval evaluation cannot pass.
6. **Embedding model unavailable:** record infrastructure failure; do not
   substitute dummy evaluation evidence.
7. **Generation provider unavailable:** retrieval-only results may remain valid,
   but required answer-quality evidence is invalid and no answer-quality claim
   may be made.
8. **Judge parse/schema/provider failure:** emit `judge_invalid` and no score.
9. **No retrieved evidence:** emit `retrieval_miss` when expected evidence exists;
   generation receives explicit insufficient-evidence state.
10. **Citation cannot map to retrieved evidence:** emit `citation_mismatch`.
11. **Material unsupported answer claim:** emit `unsupported_claim`.
12. **Near-threshold stochastic evidence:** use `INCONCLUSIVE` when valid
    evidence is insufficient for a stable decision.
13. **Dirty working tree:** record it explicitly; the future plan may require a
    clean tree for canonical benchmark evidence.
14. **Duplicate example IDs:** dataset validation fails before execution.
15. **Expected URL absent for URL-specific diagnostic:** record N/A rather than
    zero, consistent with D5.

## Failure and Recovery

| Failure | Required behavior | Recovery |
| --- | --- | --- |
| Dataset validation failure | Stop before retrieval; final state `INVALID` | Correct data under a reviewed version; never mutate a frozen benchmark silently |
| Retrieval/index failure | Record `infrastructure_failure`; do not interpret quality | Restore required index/config and rerun under the same contract |
| Generation provider failure | Preserve valid retrieval evidence; invalidate required answer layer | Restore provider access and rerun under the same contract |
| Judge invalid | Preserve answer/retrieval artifacts, emit no synthetic score | Fix judge/provider/schema problem and rerun affected judge evidence |
| Candidate regression | Final state `FAIL` with failing metrics/slices/examples | Diagnose, repair candidate, add durable regression cases after review, rerun |
| Contract mismatch | Refuse governed paired delta | Re-run both sides under a compatible contract or revise protocol through review |
| Artifact write failure | Run cannot be canonical because evidence is incomplete | Repair local artifact storage and rerun |

## Security and Privacy

1. Evaluation datasets use public, synthetic, or reviewed redacted data by
   default.
2. Evaluation content and retrieved documents are untrusted data and cannot
   modify judge rules, thresholds, system configuration, or approval state.
3. Secrets, tokens, private credentials, and unnecessary personal data must not
   appear in datasets, committed prompts/reports, run artifacts, or logs.
4. Run artifacts prefer stable IDs and minimal necessary excerpts.
5. Provider errors must be sanitized before persistence if they may contain
   request headers or credentials.
6. Future memory evaluation must add scope/privacy rules from the memory
   protocol; R2 generic contracts do not weaken those future gates.

## Observability and Operations

Every run must be diagnosable locally without a hosted observability system. At
minimum, structured logging or equivalent records must include:

1. `run_id`,
2. dataset ID/version/role,
3. config ID,
4. example ID during per-example execution,
5. current stage: validation, retrieval, generation, judge, metrics, comparison,
   or artifact write,
6. stage timings,
7. sanitized error category,
8. final result state.

The harness should print a concise terminal summary and point to persisted
artifacts/reports. Normal logs must not dump entire retrieved documents or
prompt payloads unless an explicit safe debug mode is approved.

Production alerting, telemetry backends, and dashboards belong to later `R8`.

## Capacity, Latency, and Cost

R1/R2 optimizes for trustworthy local evaluation, not high-throughput benchmark
infrastructure.

1. Retrieval-only runs must work without external LLM calls and are the default
   fast feedback loop.
2. Answer/judge calls are opt-in because they may require network access, rate
   limits, quotas, or paid provider usage.
3. Run metadata records per-stage timing and provider usage when available.
4. Development may support sample/limit mode; benchmark promotion evidence must
   run the full eligible frozen benchmark.
5. Parallelism, caching, batching, and hosted experiment infrastructure remain
   optimizations unless needed for correctness.

## Compatibility and Staged Migration

R1/R2 migration proceeds in evidence-preserving stages:

1. **Characterize legacy behavior:** preserve current runtime configuration and
   add characterization tests before refactoring.
2. **Introduce contracts beside legacy code:** add dataset/run/result contracts
   and test them without changing online behavior.
3. **Repair measurement validity:** remove synthetic judge fallback and validate
   judge evidence.
4. **Create benchmark v0.1:** review and freeze dataset identity/slices.
5. **Create frozen baseline:** evaluate the current runtime configuration and
   save canonical baseline evidence.
6. **Refactor RAG as candidate:** separate retrieval/context/generation while
   preserving public chat compatibility.
7. **Compare candidate to baseline:** apply D5 gates and inspect failures.
8. **Retire legacy evaluator assumptions:** only after the new harness has tests
   and reviewable evidence; useful metric helpers may remain reused.

At no point may old hard-coded `baseline_store` naming be silently reinterpreted
as the frozen R1 baseline.

## Rollout and Migration

The implementation plan must order work so the first baseline is captured
before candidate behavior changes. If structural changes are required merely to
make the harness callable before baseline capture, they must be behavior-
preserving and covered by characterization tests; any material behavior change
requires a new baseline snapshot before continuing.

The chat endpoint remains compatible throughout migration. Internal contracts
may coexist with legacy `RAGService.generate_answer` until comparison proves
the new path valid.

No database migration is required. Existing Chroma data is read, not rewritten,
for baseline evidence.

## Rollback

1. Candidate runtime modules can be reverted to the pre-R1 path while retaining
   the R2 harness and valid baseline evidence.
2. A failed candidate does not invalidate a valid frozen baseline.
3. A broken new harness implementation can be reverted without modifying
   existing Chroma collections.
4. Frozen benchmark versions are never rewritten to improve rollback results;
   corrections create a new dataset version.
5. Accepted review reports follow normal repository history rather than silent
   mutation.

## Required ADRs

Before implementation-plan approval, create and accept one ADR for the durable
module boundary introduced here:

1. **ADR 0001 - Separate Online RAG Execution from Config-driven Evaluation.**
   Record that online RAG owns retrieval/context/generation contracts, R2
   evaluates through those contracts without becoming a runtime dependency, and
   baseline/candidate roles are assigned by run configuration/artifact rather
   than hard-coded collection names.

The ADR must not choose a hosted evaluation vendor, replace Chroma, or decide
future memory storage.

## Engineering Learning Outcomes

During implementation and review, the repository owner should be able to
explain and demonstrate:

1. why a baseline is a frozen experiment contract rather than the oldest model,
2. why development, regression, benchmark, and safety datasets have different
   roles,
3. why retrieval quality and answer quality must be measured separately,
4. how Hit@K, MRR@K, and nDCG@K reveal different ranking behavior,
5. why per-example evidence matters more than one aggregate score during
   debugging,
6. how product code and evaluation code remain separate while reusing runtime
   contracts,
7. why invalid evidence must remain invalid instead of becoming a default score,
8. how frozen configs, code revision, dataset version, and run IDs make an AI
   experiment reviewable,
9. how failure taxonomy turns one-off bugs into regression tests,
10. how to distinguish a no-regression refactor from a real quality improvement
    claim.

## Acceptance Criteria

R1/R2 v0.1 is acceptable only when all applicable criteria are met with fresh
evidence from the approved implementation plan:

1. A reviewed RAG benchmark dataset v0.1 exists under the governed dataset
   layout with stable manifest/version and all D5 mandatory slices represented.
2. Dataset validation rejects missing/incompatible fields required by selected
   metrics before run execution.
3. The current runtime parent-child configuration is recorded and executed as
   the first protocol-valid frozen baseline; its report does not claim
   improvement.
4. Retrieval baseline evidence reports Hit@5, MRR@5, nDCG@5 plus applicable
   diagnostics at K values `1`, `3`, `10`, and `20`.
5. Answer baseline evidence, when executed, reports the six D5 dimensions with
   validated evidence and explicit invalid counts.
6. Every canonical run records dataset/version/role, code revision and dirty
   state, retrieval/model/index identities, generation config, judge config,
   timings/errors, per-example evidence, aggregate metrics, slices, failures,
   and final state.
7. Evaluation core accepts configurable run identities and contains no
   assumption that `vietnam_travel_knowledge` or `vietnam_travel_parent_child`
   is inherently baseline or candidate.
8. The harness supports retrieval-only local execution without external model
   calls.
9. The harness compares compatible runs by stable example ID and reports paired
   aggregate and mandatory-slice deltas plus D5-required uncertainty estimates
   when applicable.
10. Incompatible comparison contracts are rejected or marked `INVALID` and do
    not produce governed deltas.
11. The legacy synthetic LLM-judge fallback is removed from governed execution;
    malformed/provider/schema/range errors produce `judge_invalid` and no
    synthetic score or winner.
12. RAG retrieval returns the standardized evidence contract with traceable
    chunk/document/source identity.
13. Retrieval, context assembly, and generation are independently testable and
    the evaluation harness can call the same contracts without HTTP.
14. Internal citation evidence can be traced to retrieved evidence and citation
    mismatch can be represented per example.
15. Empty retrieval produces explicit insufficient-evidence behavior without a
    newly invented score threshold.
16. `/api/v1/chat` preserves public `reply`, `model`, and `citations` fields.
17. Harness tests cover dataset validity, metrics, judge validity, run states,
    artifact schema, comparison compatibility, and one end-to-end deterministic
    retrieval-only comparison.
18. RAG tests cover structured retrieval mapping, context/citation provenance,
    insufficient evidence, and public response compatibility.
19. A human-readable baseline report exists under `docs/reports/` and points to
    the exact frozen run/config/dataset identity used.
20. A candidate RAG comparison applies accepted D5 no-regression gates; any
    improvement claim additionally satisfies the predeclared D5 improvement
    requirement.
21. Durable failures selected for regression protection are added only through
    reviewed regression dataset versioning.
22. No new vector database, embedding model, model provider, hosted evaluation
    service, or production observability platform is introduced without a
    separately approved scope change.
23. The required ADR is accepted before implementation-plan approval.
24. Git delivery remains repository-owner controlled.

## Verification Expectations for the Future Plan

The future implementation plan must define exact commands and include fresh
evidence for at least:

1. dataset/schema validation,
2. unit tests for metrics and judge validation,
3. RAG contract and citation-provenance tests,
4. deterministic retrieval-only harness integration tests,
5. artifact reload/comparison tests,
6. current chat compatibility tests,
7. a baseline preflight verifying required collection/model/data identity,
8. the full frozen baseline run,
9. the paired candidate run,
10. D5 gate evaluation and final result state,
11. `git diff --check`, repository status, and complete change-set review,
    including untracked files.

Checks requiring external provider access must be separated from deterministic
local checks and reported explicitly when they cannot run.

## Specification Approval Record

Version 0.1 is **Approved**. Architecture direction and specification version
0.1 were approved by the repository owner on 2026-09-01.

This approval authorizes drafting the required ADR and, after that ADR is
reviewed and accepted, preparing the R1/R2 implementation plan. It does not
authorize implementation.
