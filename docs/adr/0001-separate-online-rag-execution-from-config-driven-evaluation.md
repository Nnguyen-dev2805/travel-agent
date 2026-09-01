# ADR 0001: Separate Online RAG Execution from Config-driven Evaluation

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-01 |
| Decision owners | Repository owner |
| Scope | Dependency direction between online RAG execution and the R1/R2 evaluation subsystem |
| Governing spec | [RAG Repair and Evaluation Harness Design](../specs/2026-09-01-rag-repair-and-evaluation-harness-design.md), version 0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

Travel Agent currently has two related but incorrectly coupled concerns.

The online chat path depends on `RAGService`, which currently owns embedding,
retrieval, context assembly, generation, citation projection, and response
formatting in one execution path. Separately, the legacy evaluation code owns
hard-coded Chroma collections named `baseline_store` and `parent_child_store`.
That naming conflicts with the real online runtime, which already uses
`vietnam_travel_parent_child` as its current retrieval collection.

R1 and R2 need a durable boundary before implementation because future quality
work must be able to answer two different questions independently:

1. What behavior does the product execute online?
2. How do we evaluate a frozen behavior as a baseline or candidate?

If evaluation roles are encoded into runtime modules or collection names, then a
collection rename, retrieval strategy change, or later memory experiment can
silently redefine what "baseline" means. If runtime code depends on benchmark
or judge infrastructure, product behavior can also become coupled to tooling
that must remain optional outside evaluation.

The approved R1/R2 specification therefore requires one architecture decision
covering module ownership and dependency direction.

## Decision

Adopt the following boundary:

```text
HTTP/API
   |
   v
Online RAG orchestration
   |----> Retrieval contract ----> embedder/vector-store adapters
   |----> Context assembly
   |----> Generation contract ----> model-provider adapter
   `----> Response/citation projection

Evaluation runner
   |----> calls the same approved runtime contracts
   |----> dataset validation
   |----> metrics / judge validation / comparison gates
   `----> evaluation artifacts and reports
```

The decision has four rules.

1. **Online RAG owns product execution contracts.** Retrieval, context assembly,
   generation, and citation/evidence projection are runtime responsibilities.
   Evaluation may call these contracts, but it does not own them.
2. **Evaluation is not a runtime dependency.** The online API and RAG execution
   path must not depend on benchmark datasets, evaluation runners, judges,
   comparison gates, or evaluation artifacts.
3. **Baseline and candidate are experiment roles, not collection identities.**
   They are assigned by run configuration and run artifacts. Core evaluation
   logic must not treat `vietnam_travel_knowledge`,
   `vietnam_travel_parent_child`, or any future collection name as inherently
   baseline or candidate.
4. **Shared contracts stop at behavior boundaries.** Evaluation may reuse the
   same retrieval/context/generation interfaces and result objects needed to
   reproduce product behavior, while evaluation-specific schemas, metrics,
   validity states, judges, and artifact writers remain outside online runtime
   dependencies.

This ADR does not prescribe final Python filenames or class names. The
implementation plan may map these responsibilities onto the existing repository
with the smallest practical refactor, provided the dependency direction above is
preserved.

## Alternatives

### Alternative A: Keep the legacy evaluator as a two-collection comparison tool

The existing evaluator could remain centered on a hard-coded
`vietnam_travel_knowledge` baseline and `vietnam_travel_parent_child` candidate.

This is smaller initially, but it makes experiment roles accidental properties
of collection names, does not represent the current online runtime correctly,
and does not provide a reusable boundary for later RAG or memory experiments.
It is rejected.

### Alternative B: Make online RAG depend on the evaluation abstraction

The product path could execute through a generic experiment/evaluation layer so
both product and benchmark runs share one top-level framework.

This maximizes apparent reuse but reverses dependency direction. Product
availability would become coupled to datasets, judges, metrics, artifact
schemas, or experiment concepts that are not required to answer a user request.
It is rejected.

### Alternative C: Duplicate RAG execution inside the evaluation harness

The evaluator could independently implement embedding, retrieval, context
assembly, prompt construction, and generation.

This avoids runtime/evaluation imports but creates two behavior implementations.
They can drift, causing the harness to measure a path different from the product
path. It is rejected.

## Consequences

### Positive

1. The current runtime can be frozen as a baseline without redefining baseline
   around an old evaluator variable name.
2. Runtime behavior and evaluation tooling remain independently testable.
3. The harness can measure the same retrieval/context/generation contracts used
   by the product without scraping the HTTP API.
4. Evaluation failures, judge outages, or missing benchmark files cannot become
   online runtime dependencies.
5. Future candidate strategies can be compared by configuration instead of by
   adding hard-coded strategy branches to evaluation core.
6. Later memory evaluation can reuse run/dataset/result concepts without forcing
   memory storage or memory logic into RAG runtime modules.

### Negative

1. R1 requires a small internal decomposition of the current monolithic
   `RAGService` path or compatible facades around it.
2. Runtime result contracts become more explicit and therefore require schema
   ownership, tests, and migration discipline.
3. The evaluation harness must resolve configuration and adapters instead of
   directly instantiating two known Chroma collections.
4. Some legacy evaluator code and naming will need characterization, migration,
   or retirement after the new path is proven.

## Migration

1. Characterize current online RAG behavior before material candidate changes.
2. Introduce structured runtime contracts beside existing behavior and preserve
   the public chat response fields `reply`, `model`, and `citations`.
3. Build evaluation configuration around behavior identity rather than baseline
   or candidate collection names.
4. Freeze the first valid baseline using the current online runtime identity,
   including `vietnam_travel_parent_child` and the governed D5 contract.
5. Refactor/decompose the RAG path as a candidate while preserving public API
   compatibility.
6. Compare the candidate to the frozen baseline using the same eligible examples
   and governed metrics.
7. Retire legacy hard-coded baseline/candidate assumptions only after the new
   harness and compatibility tests provide replacement evidence.

Rollback preserves the frozen baseline and evaluation artifacts. A rejected RAG
candidate may revert to the pre-R1 runtime implementation without requiring the
new evaluation subsystem to be removed.

## Validation

The implementation plan must provide fresh evidence that:

1. online API modules do not import or require evaluation-runner, judge,
   benchmark, comparison-gate, or evaluation-artifact modules;
2. the evaluation harness can call the same retrieval/context/generation
   contracts used by online RAG without going through HTTP;
3. evaluation core can run baseline/candidate configurations without hard-coded
   collection-role assumptions;
4. the current public chat response remains compatible;
5. retrieval evidence identity survives through context and citation projection;
6. deterministic retrieval-only evaluation works without external LLM calls;
7. malformed judge evidence becomes `judge_invalid` instead of a synthetic
   quality score;
8. a frozen baseline and a compatible candidate can be compared under the D5
   result-state and gate contract.

## References

1. [RAG Repair and Evaluation Harness Design](../specs/2026-09-01-rag-repair-and-evaluation-harness-design.md), version 0.1 (Approved).
2. [RAG Evaluation Protocol](../evaluation/rag-evaluation.md).
3. [Target Architecture](../architecture/target-state.md).
4. [Target Data Model](../architecture/data-model.md).
