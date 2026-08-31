# Evaluation Protocols Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-08-31 |
| Change class | Level 2 - Feature Spec |
| Decision owner | Repository owner |
| Scope | Documentation Package 5 - RAG and memory evaluation protocols |
| Parent design | [Documentation System Design](./2026-08-30-documentation-system-design.md), version 0.1 |
| Depends on | [Architecture Baseline Design](./2026-08-31-architecture-baseline-design.md), version 0.1; [Roadmap and Learning Design](./2026-08-31-roadmap-and-learning-design.md), version 0.1 |
| Implementation plan | [Evaluation Protocols Implementation Plan](../plans/2026-08-31-evaluation-protocols-implementation.md), version 0.1 (Completed; owner change set accepted) |
| Related issue | None - specification drafting was authorized by the repository owner in this conversation |
| Superseded document | None |

## Summary

Package 5 defines how Travel Agent will measure RAG quality and future memory
quality before runtime work is allowed to claim improvement. It will create two
canonical protocol documents:

1. `docs/evaluation/rag-evaluation.md`
2. `docs/evaluation/memory-evaluation.md`

The selected approach uses one shared evaluation contract with separate RAG
and memory protocols. Both protocols use versioned datasets, explicit metric
definitions, fixed comparison rules, failure taxonomies, reproducible run
metadata, and promotion gates. RAG evaluation starts from the evaluator code
already present in the repository. Memory evaluation is defined before the
memory runtime exists so extraction, promotion, retrieval, personalization,
conflict, scope, and privacy behavior can later be built against known gates.

Approval of version 0.1 authorizes preparation of a Package 5 implementation
plan only. It does not authorize creation of the two protocol files, runtime
evaluation code, dataset generation, model calls, RAG repair, memory
implementation, dependency changes, data migration, or Git delivery.

## Current-state Evidence

Codebase Memory was checked at Verify tier for the current evaluation and
architecture paths. The graph project was
`Users-tnhatnguyendev2805-Documents-Projects-travel-agent`, generation
`2026-08-31T06:44:24Z`, with 856 nodes and 2003 edges. Coverage for the relied-on
paths returned `no_recorded_issue` with matching metadata. This remains a
best-effort index signal, not proof of semantic completeness. Material source
and documentation were also read directly.

| Evidence | Current fact relevant to Package 5 |
| --- | --- |
| [`backend/rag/evaluation/evaluator.py`](../../backend/rag/evaluation/evaluator.py) | A retrieval benchmark compares `baseline_fixed_1000ch` with `semantic_parent_child` and computes Hit, MRR, nDCG, Precision, relevant-chunk count, unique-document count, and source-URL hit at configured K values. Relevance is currently binary exact document-ID matching. |
| [`backend/rag/evaluation/llm_judge_evaluator.py`](../../backend/rag/evaluation/llm_judge_evaluator.py) | An LLM judge compares baseline and parent-child retrieved contexts on correctness, faithfulness, relevance, completeness, practical usefulness, and clarity. The judge uses a fixed JSON prompt and temperature 0. |
| [`backend/tests/unit/test_evaluator.py`](../../backend/tests/unit/test_evaluator.py) | Unit coverage exists for reciprocal rank, nDCG, hit behavior, source-URL hit, and one precision calculation. |
| [Target Architecture](../architecture/target-state.md) | The target system requires evaluation traces connecting request context, selected memories and retrieval chunks, outputs, quality signals, and safety signals. |
| [Target Data Model](../architecture/data-model.md) | `ContextBundle` and `EvaluationTrace` are defined as future seams for inspecting what generation saw and recording reproducible scores and failures. |
| [Master Roadmap](../roadmap/master-roadmap.md) | `D5` is the prerequisite evaluation package for RAG repair and memory quality claims; later runtime milestones depend on these protocols. |

Direct filesystem inspection found no `data/evaluation/` or `docs/reports/`
files in the current working tree. The current evaluator therefore references
default benchmark, checkpoint, and report paths that are not presently backed
by reviewable repository files. Package 5 must describe this as a current gap;
it must not claim the existing benchmarks are runnable or reproducible.

The current LLM judge also contains a parse-error fallback that fabricates
default scores favoring the parent-child strategy. That behavior is unsuitable
as promotion evidence. Package 5 must require invalid judge outputs to be
reported as invalid evaluation evidence rather than converted into synthetic
quality scores.

## Context

Travel Agent is moving from an early RAG prototype toward a workspace-first
travel assistant with layered memory. RAG retrieval already has evaluation
code, but the repository does not yet have a canonical evaluation protocol,
frozen datasets, result interpretation rules, or quality gates. Future memory
work has architecture concepts but no runtime and no benchmark.

Without a protocol, a new retrieval strategy or memory feature could appear to
improve quality because its author changed the dataset, judge prompt, K value,
metric definition, or sample after seeing failures. The project also needs to
distinguish ordinary quality regressions from hard failures such as
cross-workspace memory leakage, remembering secret-like content, or continuing
to retrieve a deleted memory.

Package 5 makes evaluation a product contract rather than a one-off report.

## Users

1. **Repository owner:** needs evidence that a change improved the system and a
   clear explanation of failures before approving promotion.
2. **AI engineer:** needs stable datasets, metrics, slices, and comparison rules
   for RAG and memory experiments.
3. **Coding agent:** needs explicit gates so it cannot select convenient
   evaluation criteria after implementation.
4. **Reviewer:** needs enough run metadata and failure examples to reproduce or
   challenge a quality claim.
5. **Future operator:** needs invalid, degraded, and failed evaluations to be
   distinguishable from successful runs.

## Problem Statement

The repository has measurement code but no governed measurement system. The
retrieval evaluator embeds important assumptions directly in code, such as
exact document-ID relevance and fixed strategy names. The LLM judge depends on
an external model and currently substitutes favorable scores when parsing
fails. Referenced benchmark files are absent from the working tree.

Future memory is more difficult to evaluate than retrieval alone. A memory can
be factually true but unsafe to store, correctly stored but assigned to the
wrong trip, relevant but stale, or successfully retrieved but harmful when a
newer user correction should override it. A single accuracy score cannot cover
these failure modes.

Package 5 must define a reproducible evaluation lifecycle that separates
retrieval, generation, memory writing, memory reading, memory use, privacy, and
regression behavior.

## Goals

1. Define one canonical evaluation lifecycle shared by RAG and memory work.
2. Define versioned dataset roles and rules that prevent benchmark tuning and
   train-test leakage.
3. Define RAG retrieval and answer-quality metrics with exact interpretation.
4. Define memory extraction, promotion, retrieval, use, conflict, scope,
   deletion, and privacy metrics before memory implementation begins.
5. Define hard safety gates separately from quality-improvement gates.
6. Define valid, invalid, inconclusive, passed, and failed result states.
7. Require reproducible run metadata and per-example failure evidence.
8. Define how LLM-as-judge evidence is validated and when human review is
   required.
9. Establish a regression-dataset lifecycle so real failures become durable
   tests after review.
10. Keep Package 5 documentation-only and leave evaluation harness code to the
    later `R2` runtime milestone.

## Non-goals

1. Package 5 does not repair RAG retrieval or change chunking, embeddings,
   Chroma collections, prompts, generation, or model providers.
2. It does not implement the evaluation harness, create benchmark datasets,
   generate judge labels, download models, or execute external model calls.
3. It does not implement memory extraction, memory persistence, trip
   workspaces, conversation persistence, context assembly, or planner state.
4. It does not establish final security policy, retention duration,
   authentication, authorization, or incident response; Package 6 owns those
   policies.
5. It does not choose a production tracing, experiment-tracking, database, or
   model-evaluation vendor.
6. It does not claim the current evaluator outputs are trustworthy until the
   required datasets exist and the protocol-validity checks pass.
7. It does not change source code, tests, dependencies, CI, Docker,
   environment files, persistent Chroma data, or Git history.

## Assumptions

1. Evaluation is a prerequisite to quality-improvement claims, not a report
   generated after a feature has already been accepted.
2. RAG and memory need separate task metrics but can share dataset versioning,
   run metadata, result states, failure taxonomy, and reporting rules.
3. Exact document-ID matching is useful as one retrieval signal but is not a
   complete measure of answer quality.
4. LLM judges are noisy measurement instruments and cannot silently replace
   deterministic checks or human review for critical failures.
5. Memory safety requires hard zero-tolerance gates for cross-scope leakage,
   deleted-memory retrieval, and secret-like durable memory in controlled test
   cases.
6. Synthetic or carefully redacted fixtures are sufficient for initial privacy
   and scope evaluation; real sensitive user data is not required.
7. The first trustworthy frozen RAG baseline will be established by a later
   runtime evaluation milestone after the protocol and harness exist.
8. Numeric quality thresholds may be tightened through a separately reviewed
   protocol revision when baseline distributions are known; they must not be
   relaxed inside an experiment to make a candidate pass.

If an assumption is rejected, Package 5 returns to specification review before
an implementation plan is prepared.

## Selected Approach

Use a shared evaluation contract with two domain protocols:

1. `rag-evaluation.md` owns retrieval quality, answer quality, citations,
   groundedness, judge use, dataset slices, comparison rules, and RAG promotion
   gates.
2. `memory-evaluation.md` owns memory write quality, read quality, use quality,
   conflicts, corrections, scope isolation, deletion, sensitive-content
   handling, and memory promotion gates.
3. Both protocols use the same dataset roles, run identity fields, result-state
   vocabulary, regression lifecycle, review evidence, and reporting shape.
4. The protocols define the contract that the later `R2` Evaluation Harness
   must implement. The current evaluator code is treated as legacy executable
   evidence to preserve and improve, not as the protocol itself.

This approach is selected because RAG and memory share evaluation discipline
but fail in materially different ways. One giant scorecard would hide memory
safety failures, while two unrelated systems would create duplicated and
inconsistent experiment rules.

## Alternatives Considered

### Alternative A: Document only the existing evaluator behavior

This would be fast and would closely match current code. It is rejected because
the current evaluator has missing datasets, incomplete answer-quality coverage,
and an unsafe judge fallback. It also provides no usable path for memory.

### Alternative B: One combined RAG-and-memory score

A single weighted score would be easy to rank. It is rejected because a high
retrieval or personalization score could hide a critical privacy or scope
failure. Hard gates must remain visible and non-compensating.

### Alternative C: Shared evaluation contract plus separate RAG and memory
protocols

This adds two canonical documents but preserves domain-specific metrics while
keeping experiment discipline consistent. It is the selected approach.

## Common Evaluation Lifecycle

Every future governed evaluation follows this lifecycle:

1. Identify the change under evaluation and the approved spec or experiment.
2. Select an immutable dataset version and named dataset role.
3. Record baseline and candidate configuration before running the candidate.
4. Run deterministic checks before any LLM judge.
5. Run task-specific metrics over the same eligible examples for baseline and
   candidate.
6. Run judge-based scoring only when the protocol requires it.
7. Mark invalid examples and infrastructure failures separately from quality
   failures.
8. Aggregate overall metrics and required slices.
9. Apply hard gates first, then no-regression gates, then improvement gates.
10. Review the largest failures and critical examples, not only aggregate
    means.
11. Produce a result with one terminal state: `PASS`, `FAIL`, `INCONCLUSIVE`, or
    `INVALID`.
12. Promote reviewed production failures into a regression dataset when they
    represent a durable behavior requirement.

## Dataset Contract

Both protocols must define these dataset roles:

| Dataset role | Purpose | May tune against it? | Stability |
| --- | --- | --- | --- |
| Development set | Fast iteration and debugging | Yes | Mutable with review |
| Regression set | Preserve previously fixed failures and hard invariants | No per-change tuning after failure is admitted | Append-only by reviewed cases, versioned |
| Benchmark set | Compare candidate against a frozen baseline | No | Immutable within a version |
| Safety set | Scope, deletion, sensitive-memory, and adversarial invariants | No | Immutable within a version except reviewed additions |

Every dataset version must record at least:

1. Stable dataset identifier and version.
2. Creation or approval date.
3. Provenance category for each example.
4. Intended dataset role.
5. Query or scenario category and required slices.
6. Expected evidence, expected behavior, or labeled rubric as applicable.
7. Whether the example contains synthetic, public, or redacted content.
8. Any exclusions required for a specific metric.

Query IDs and scenario IDs must be unique inside a dataset version. Duplicate,
missing, malformed, or label-incomplete examples make the affected metric
invalid until resolved.

## Run and Report Contract

Every future evaluation run must be reproducible enough to compare two runs.
The report must record:

1. `run_id` and timestamp.
2. Dataset identifier, version, and eligible example count.
3. Baseline and candidate identifiers.
4. Code revision or working-tree identifier when available.
5. Retrieval configuration: embedding model, collection or index identity,
   chunking strategy, filters, and K values when applicable.
6. Generation configuration: model, prompt or prompt version, temperature, and
   relevant decoding parameters.
7. Judge configuration: model, prompt or rubric version, temperature, and
   schema version.
8. Random seed or an explicit statement that the component is not seeded.
9. Completed, failed, skipped, and invalid example counts.
10. Overall metrics and mandatory slice metrics.
11. Hard-gate outcomes.
12. Largest regressions and representative failure examples.
13. Known limitations and checks that did not run.

Missing required run metadata makes a comparison `INVALID` for promotion even
if individual scores were produced.

## Result States

| State | Meaning |
| --- | --- |
| `PASS` | All hard gates and required no-regression gates pass, required evidence is valid, and the change satisfies its declared improvement target. |
| `FAIL` | Evidence is valid but at least one required quality, safety, or no-regression gate fails. |
| `INCONCLUSIVE` | Evidence is valid enough to inspect but sample size, judge disagreement, variance, or effect size is insufficient to support the requested conclusion. |
| `INVALID` | Required data, configuration, outputs, schemas, run metadata, or infrastructure evidence is missing or corrupted, so quality cannot be judged. |

Infrastructure errors, missing judge responses, JSON parse errors, empty
collections, absent datasets, and partial result files must never be converted
into favorable metric values.

## RAG Evaluation Protocol Requirements

The RAG protocol must separate retrieval evaluation from answer evaluation.

### Retrieval metrics

The protocol must preserve and define the semantics of the current metrics:

1. **Hit@K:** whether at least one labeled relevant document appears in top K.
2. **MRR@K:** reciprocal rank of the first relevant result within K.
3. **nDCG@K:** ranking quality under the declared relevance labels.
4. **Precision@K:** relevant retrieved units divided by K under the protocol's
   declared denominator rule.
5. **Source URL Hit@K:** whether an expected source URL appears in top K after
   defined URL normalization.
6. **Relevant chunk count:** diagnostic count, not a standalone promotion
   metric.
7. **Unique document count:** diversity diagnostic, not evidence of relevance by
   itself.

The protocol must state when exact document-ID matching is used and when graded
or multi-document relevance labels are required. A result cannot silently mix
binary and graded relevance definitions under the same metric name.

Primary retrieval comparison K is `K=5`. `K=1`, `K=3`, `K=10`, and `K=20` are
diagnostic slices unless an approved experiment names another primary K before
the run.

### Answer-quality metrics

RAG answer evaluation must include:

1. **Groundedness / citation support:** factual answer claims are supported by
   retrieved evidence.
2. **Answer relevance:** the answer addresses the user's travel need.
3. **Correctness:** supported claims do not contradict the labeled reference or
   source evidence available to the evaluator.
4. **Completeness:** important requested parts are covered without requiring
   irrelevant verbosity.
5. **Practical usefulness:** advice is actionable for the declared scenario.
6. **Clarity:** presentation is understandable and internally coherent.

`faithfulness` in legacy judge output maps to groundedness for reporting, but
the protocol should prefer the term `groundedness` when judging whether claims
are supported by supplied evidence.

### RAG quality gates

Until a trustworthy frozen baseline exists, the first valid benchmark run
creates the baseline and cannot itself prove improvement. After that baseline
is frozen, a candidate may pass only when all applicable rules hold:

1. Required deterministic checks have zero schema or accounting errors.
2. Overall `Hit@5`, `MRR@5`, and `nDCG@5` each decline by no more than `0.01`
   absolute from the frozen baseline.
3. No mandatory category or URL-group slice declines by more than `0.03`
   absolute on `Hit@5` unless the experiment specification explicitly accepts
   that trade-off before the run.
4. Mean groundedness on the answer-quality benchmark is at least `4.0/5.0` and
   does not decline by more than `0.10` from baseline.
5. Mean correctness is at least `4.0/5.0` and does not decline by more than
   `0.10` from baseline.
6. A claimed RAG improvement must improve at least one predeclared primary
   metric by `0.02` absolute or more, or produce a reviewed task-level benefit
   of equivalent importance without violating the no-regression gates.
7. Any citation fabrication, unsupported high-impact travel claim, or invalid
   judge substitution triggers failure or human review according to the
   protocol severity rubric.

These are initial engineering promotion thresholds, not research claims of
statistical significance. The protocol must also report paired deltas and, when
the sample is large enough, bootstrap confidence intervals so the repository
owner can distinguish a stable change from sampling noise.

## LLM-as-a-Judge Contract

LLM judges are secondary measurement tools. The RAG protocol must require:

1. Fixed judge model, prompt or rubric version, temperature, and output schema
   within one comparison.
2. Blind ordering or randomized A/B position when pairwise comparisons are
   used, with position recorded for later bias analysis.
3. Strict schema validation and bounded score ranges.
4. Recalculation of any declared overall score from component scores rather
   than trusting an inconsistent model-provided total.
5. Parse failure, missing fields, out-of-range values, and model errors recorded
   as invalid judge evidence.
6. No synthetic fallback score when the judge fails.
7. A calibration sample reviewed by a human before judge scores are used as a
   release or promotion gate.
8. Human review of critical disagreements, large candidate wins, privacy
   failures, and examples with low judge confidence or repeated instability.

The protocol must distinguish judge availability from system quality. An
unavailable judge can make a run `INVALID` or `INCONCLUSIVE`; it cannot make the
candidate better or worse by assumption.

## Memory Evaluation Protocol Requirements

Memory evaluation must treat the memory lifecycle as separate measurable
stages. A later implementation cannot claim "memory accuracy" from one blended
score.

### Stage 1: Candidate extraction

Measure whether interactions produce the right candidate memories.

Required metrics:

1. Candidate precision, recall, and F1 by memory type.
2. Content accuracy against the scenario label.
3. Scope classification accuracy: user, trip, conversation, evaluation-only,
   or not-memory.
4. Stable-versus-ephemeral classification accuracy.
5. Duplicate candidate rate.

### Stage 2: Promotion policy

Measure whether candidates are accepted, rejected, expired, or routed for user
action correctly.

Required metrics:

1. Promotion precision: promoted records that should be durable.
2. Promotion recall for required stable preferences, trip constraints, and
   explicit decisions.
3. False durable-memory rate for ephemeral or unsupported statements.
4. Sensitive-content rejection rate.
5. Conflict detection rate.
6. Correct scope assignment rate.

### Stage 3: Retrieval

Measure whether the right existing memories are selected for a new turn.

Required metrics:

1. Memory Hit@K or Recall@K over labeled relevant memory IDs.
2. MRR@K or nDCG@K when ranking order matters.
3. Irrelevant-memory rate in the selected context.
4. Stale-memory selection rate.
5. Superseded-memory selection rate.
6. Cross-user and cross-workspace leakage count.
7. Deleted-memory retrieval count.

Primary memory-retrieval K is `K=5` unless the implementing context budget
requires a smaller predeclared value.

### Stage 4: Use in the answer

Measure whether retrieved memory improves the user outcome rather than merely
appearing in context.

Required comparisons:

1. Same scenario with correct memory available versus memory disabled.
2. Same scenario with relevant versus irrelevant or stale memory.
3. Same scenario before and after an explicit user correction.

Required metrics:

1. Personalization win rate on scenarios where memory should help.
2. Memory-use precision: used memories are relevant to the current request.
3. Constraint satisfaction rate.
4. Contradiction rate against current trip state or explicit user correction.
5. Groundedness or attribution of claims that depend on remembered context.

### Stage 5: Conflict, correction, deletion, and safety

The safety set must contain controlled scenarios for:

1. New explicit correction overriding an older inferred preference.
2. Trip-scoped preference not leaking to another trip.
3. User-scoped preference being available across appropriate trips.
4. Rejected option remaining decision evidence without becoming a positive
   preference.
5. Secret-like or highly sensitive content that must not be promoted by the
   test policy.
6. Deleted or tombstoned memory no longer being retrievable.
7. Stale or expired memory losing eligibility.
8. Conflicting memories requiring deterministic precedence or review.

### Memory hard gates

The following gates are non-compensating. One failing example fails the
candidate for promotion until investigated:

1. Cross-user memory leakage count: `0`.
2. Cross-workspace leakage where the memory is trip-scoped: `0`.
3. Deleted-memory retrieval count after deletion is confirmed: `0`.
4. Secret-like candidate promoted in the controlled safety set: `0`.
5. Explicit correction overridden by an older inferred memory: `0`.

### Memory quality gates

After hard gates pass, initial promotion thresholds are:

1. Candidate extraction precision: at least `0.95` overall and `0.90` on every
   mandatory memory-type slice.
2. Candidate extraction recall for explicit stable preferences, constraints,
   and decisions: at least `0.90` overall.
3. Correct scope assignment: at least `0.98` overall.
4. Promotion precision: at least `0.97` overall.
5. Memory retrieval Hit@5: at least `0.90` on labeled positive scenarios.
6. Irrelevant-memory rate in selected context: at most `0.10`.
7. Personalization win rate: at least `0.60` on scenarios where the gold label
   says memory should materially help, with no hard-gate failure.
8. Constraint satisfaction must not decline from the memory-disabled baseline.

These thresholds are intentionally stricter for memory writing and scope than
for subjective answer preference because a bad durable memory can affect many
future turns.

## Mandatory Evaluation Slices

Aggregates must be accompanied by slices that expose different failure modes.

RAG slices include at least:

1. Query category or travel intent.
2. Source or URL group when source labels exist.
3. Single-document versus multi-document answer need.
4. Fact lookup versus planning or recommendation need.
5. Cases with no adequate corpus evidence.

Memory slices include at least:

1. Stable preference.
2. Trip constraint.
3. Explicit trip decision.
4. Episodic reason or rejection.
5. Ephemeral statement that should not become durable memory.
6. Correction or conflict.
7. Sensitive or secret-like candidate.
8. Cross-trip scope.
9. Deletion or expiration.

The protocol may add slices, but a candidate cannot omit a mandatory slice
because it performs poorly there.

## Failure Taxonomy

Both protocol documents must use shared failure labels where applicable:

| Failure label | Meaning |
| --- | --- |
| `retrieval_miss` | Required evidence was not retrieved. |
| `ranking_regression` | Relevant evidence exists but ranking materially worsened. |
| `citation_mismatch` | Citation points to evidence that does not support the claim. |
| `unsupported_claim` | Answer contains a factual claim unsupported by available evidence. |
| `judge_invalid` | Judge output is missing, malformed, inconsistent, or out of range. |
| `memory_missed` | A labeled useful memory candidate or retrieval was missed. |
| `memory_false_write` | A statement was promoted when it should not become durable memory. |
| `memory_wrong_scope` | Memory was stored or retrieved at the wrong scope. |
| `memory_stale` | Stale, expired, or superseded memory influenced context or output. |
| `memory_conflict` | Conflicting memory was not detected or resolved by policy. |
| `memory_leakage` | Memory crossed a user or workspace boundary. |
| `memory_deletion_failure` | Deleted memory remained eligible or retrievable. |
| `sensitive_memory_failure` | Controlled sensitive or secret-like content violated the promotion policy. |
| `infrastructure_failure` | Evaluation could not complete because required infrastructure failed. |

Per-example reports must retain enough identifiers and sanitized evidence to
trace each failure without copying unnecessary sensitive content.

## Behavioral and Data Contracts

Package 5 documents protocol contracts only. The later `R2` harness must be
able to consume or produce concepts equivalent to:

| Concept | Required responsibility |
| --- | --- |
| Dataset manifest | Version, role, provenance, slices, schema, and content hash or equivalent immutable identity |
| Evaluation example | Stable ID, input, expected evidence or behavior, slice labels, and exclusions |
| Run manifest | Baseline/candidate configuration, dataset identity, environment metadata, and judge configuration |
| Per-example result | Retrieval, answer, memory, judge, failure, latency, and validity fields that apply to the example |
| Aggregate result | Overall and slice metrics, deltas, gates, counts, and terminal state |
| Failure record | Failure label, affected example, sanitized evidence, and review status |
| Regression case | Reviewed failure promoted into a durable regression dataset version |

Exact JSON or storage schemas are deferred to the `R2` implementation spec as
long as they can represent the protocol without losing information.

## Errors and Edge Cases

1. **Dataset missing:** run is `INVALID`; do not substitute a development set.
2. **Empty retrieval collection:** report infrastructure or data failure and do
   not interpret all misses as candidate quality.
3. **Baseline and candidate use different eligible examples:** comparison is
   `INVALID` unless the protocol explicitly defines paired missing-data rules.
4. **Judge response is malformed:** mark judge evidence invalid; never create
   fallback scores.
5. **External model unavailable:** deterministic metrics may remain usable, but
   any required judge gate becomes `INVALID` or `INCONCLUSIVE`.
6. **Duplicate IDs or changed labels inside one dataset version:** dataset is
   invalid until versioned and corrected.
7. **Benchmark inspected and tuned repeatedly:** create a new benchmark version
   or independent holdout before making a generalization claim.
8. **Metric improves only in aggregate:** mandatory slice regression can still
   fail promotion.
9. **Safety hard gate fails once:** do not average it away.
10. **Memory runtime does not exist:** memory protocol can be reviewed, but no
    memory quality claim is runnable until the required runtime milestone and
    harness exist.

## Security and Privacy

Package 5 defines evaluation-specific safeguards without replacing Package 6:

1. Use synthetic, public, or explicitly redacted examples by default.
2. Never put live credentials, tokens, private account data, or unnecessary
   sensitive personal data in benchmark fixtures, judge prompts, reports, or
   traces.
3. Sensitive-memory tests must use controlled synthetic examples that exercise
   the policy without containing real secrets.
4. Cross-user and cross-workspace isolation tests must use artificial identities
   and isolated test stores.
5. Deletion tests must run against disposable test data and must verify that a
   deleted or tombstoned record is no longer eligible for retrieval.
6. Reports must avoid reproducing full private conversations when a stable ID,
   redacted excerpt, or failure label is sufficient.
7. Retrieved external content remains untrusted evidence and cannot change the
   evaluation instructions or judge rubric.

Package 6 will later define final secret handling, privacy, retention,
authorization, incident response, and public security policy.

## Observability and Operations

Package 5 adds no runtime telemetry. The protocols must define what the later
evaluation harness records so failures are diagnosable:

1. Run start and completion state.
2. Dataset and configuration identities.
3. Per-stage timing when available: embedding, retrieval, context assembly,
   generation, memory extraction, memory retrieval, and judge call.
4. Invalid and skipped example counts with reasons.
5. External dependency failures without exposing secret values.
6. Gate decisions and the metric or example responsible for a failure.

Operational alerting, retention, dashboards, and incident procedures remain
Package 6 and later runtime scope.

## Testing and Evaluation of Package 5 Documentation

Package 5 implementation verification is documentation-focused:

1. Confirm both protocol files exist only after implementation-plan approval.
2. Confirm protocol definitions match the current evaluator where compatibility
   is claimed and clearly mark target behavior that is not implemented.
3. Confirm the RAG protocol identifies missing current dataset/report artifacts
   and the unsafe judge fallback as current limitations.
4. Confirm every metric used as a gate has an explicit definition, direction,
   unit, comparison basis, and threshold or hard invariant.
5. Confirm RAG and memory protocols share the same result-state and dataset-role
   vocabulary.
6. Confirm memory hard gates cannot be compensated by aggregate quality scores.
7. Confirm invalid infrastructure or judge output cannot become favorable
   scores.
8. Resolve all repository-relative links.
9. Check Markdown headings, fenced-code blocks, trailing whitespace, duplicate
   terms, and drafting markers.
10. Compare the complete change set, including untracked files, with the
    approved Package 5 scope.

Package 5 does not run the current evaluator as acceptance evidence because its
required benchmark artifacts are absent and protocol fixes are not yet
implemented.

## Rollout and Migration

Package 5 documentation rolls out in this order:

1. Approve this specification.
2. Prepare and approve a Package 5 implementation plan.
3. Create `docs/evaluation/rag-evaluation.md`.
4. Create `docs/evaluation/memory-evaluation.md`.
5. Apply only the routing, roadmap, and traceability updates named in the
   approved plan.
6. Run deterministic documentation verification and current-state evidence
   review.
7. Stop for repository-owner review of the exact Package 5 change set.

After Package 5 is accepted, later runtime work proceeds separately:

1. `R0` fixes foundation and tooling honesty.
2. `R2` implements the repeatable evaluation harness against these protocols.
3. `R1` establishes a trustworthy RAG baseline and repairs retrieval under the
   RAG gates.
4. `R5` measures shadow memory extraction before memory affects answers.
5. `R6` enables memory retrieval only after extraction and safety gates pass.

No runtime milestone is authorized by Package 5 approval.

## Rollback

Before Git delivery, Package 5 documentation rollback removes only:

1. `docs/evaluation/rag-evaluation.md`.
2. `docs/evaluation/memory-evaluation.md`.
3. Package 5 traceability edits in `docs/specs/README.md` and, after a plan is
   created, `docs/plans/README.md`.
4. Package 5 roadmap or routing edits explicitly created by the approved plan.
5. The Package 5 implementation plan if it was created for this package.

Rollback must not modify current evaluator source, tests, data, Chroma state,
dependencies, Docker state, accepted Package 0-4 content outside explicit
Package 5 traceability fields, or Git history.

## Acceptance Criteria

Package 5 implementation is acceptable only when:

1. `docs/evaluation/rag-evaluation.md` exists and is the canonical RAG
   evaluation protocol.
2. `docs/evaluation/memory-evaluation.md` exists and is the canonical memory
   evaluation protocol.
3. The RAG protocol separates retrieval metrics from answer-quality metrics.
4. The RAG protocol defines dataset roles, primary K, metric semantics,
   baseline comparison rules, LLM-judge validation, quality gates, failure
   labels, and result interpretation.
5. The memory protocol separately evaluates candidate extraction, promotion,
   retrieval, answer use, conflict, correction, deletion, scope, and safety.
6. Cross-user leakage, trip-scope leakage, deleted-memory retrieval,
   secret-like promotion, and explicit-correction override failures are hard
   non-compensating gates.
7. Both protocols define development, regression, benchmark, and safety
   dataset roles with versioning and anti-leakage rules.
8. Both protocols use `PASS`, `FAIL`, `INCONCLUSIVE`, and `INVALID` consistently.
9. Missing datasets, infrastructure failures, and malformed judge output cannot
   produce favorable fallback scores.
10. Result reports require enough run metadata, aggregate metrics, slices,
    deltas, and per-example failures to support review.
11. Current-state limitations are stated accurately and target behavior is not
    presented as implemented behavior.
12. Package 5 creates no evaluation harness code, benchmark data, runtime memory
    code, RAG repair, dependencies, CI, Docker, environment, persistent data,
    or Git delivery changes.
13. All repository-relative links resolve and deterministic Markdown checks
    pass.
14. The repository owner approves Package 5 spec version 0.1 before an
    implementation plan is prepared.
15. The repository owner later accepts the exact Package 5 implementation
    change set before any Git delivery action.

## Verification

The Package 5 implementation plan must include:

1. Codebase Memory Verify-tier checks for current evaluator and architecture
   source paths cited by the protocol documents.
2. Direct source reads for every material claim about implemented evaluation
   behavior.
3. Direct filesystem checks for referenced datasets, checkpoints, reports, and
   protocol files.
4. A metric-definition review that verifies name, formula, direction, primary
   slice, threshold, and invalid-data behavior for every gate.
5. A judge-contract review proving no documented path converts parse or model
   failure into favorable scores.
6. A memory hard-gate review proving zero-tolerance failures remain visible and
   non-compensating.
7. Link resolution, trailing-whitespace, drafting-marker, heading, and
   fenced-code-block checks.
8. A final scope review using `git status --short --untracked-files=all` plus
   direct reads or read-only no-index diffs for untracked files.

## Approval Record

Specification drafting was authorized by the repository owner on 2026-08-31
via the exact conversation phrase `Approve Package 5 spec drafting`.

Version 0.1 was approved by the repository owner on 2026-08-31 via the exact
conversation phrase `Approve Package 5 spec version 0.1`. This approval
authorizes preparation of the Package 5 implementation plan only. It does not
authorize creating the protocol files, runtime changes, source changes,
benchmark generation, model calls, dependency changes, CI changes, data
operations, Git staging, commit, push, PR, merge, or release.
