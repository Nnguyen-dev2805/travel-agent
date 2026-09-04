# Memory Evaluation Protocol

## Scope

This document is the canonical quality and safety protocol for Travel Agent
memory. It defines how future memory extraction, promotion, retrieval,
personalization, conflict handling, correction, deletion, expiration, scope,
and sensitive-data behavior must be evaluated before memory affects answers.

It governs later `R5` shadow-memory and `R6` memory-retrieval work. It does not
claim that a runtime memory subsystem already exists.

## Preconditions and Current-state Limitations

The current project has target architecture concepts for memory but no runtime
memory implementation, frozen memory benchmark, or evaluation harness. Memory
quality therefore cannot currently be claimed as `PASS` or improved in runtime.
This protocol can be reviewed now so later implementation is built against
known quality and safety gates.

Target architecture requires memory to remain distinct from travel-knowledge
retrieval, separates memory read from memory write, exposes selected memory IDs
and reasons through a future `ContextBundle`, and connects decisions to a future
`EvaluationTrace`. Explicit user correction outranks older inferred memory, and
deleted or tombstoned memory is not eligible for retrieval.

Physical storage technology, vendor, durable schema, and report serialization
remain deferred to later architecture decisions and `R2` implementation work.

## Evaluation Principles

1. Evaluate the memory lifecycle stage-by-stage before using aggregate scores.
2. Use controlled synthetic identities, workspaces, and secret-like fixtures
   for privacy and isolation testing.
3. Keep hard safety gates non-compensating: one hard-gate failure is a promotion
   failure even when average quality improves.
4. Compare memory-enabled answers with a memory-disabled baseline on the same
   eligible examples when measuring personalization benefit or regressions.
5. Treat explicit user statements and corrections as higher-authority evidence
   than older inferred memories.
6. Preserve scope and provenance throughout extraction, promotion, retrieval,
   use, correction, and deletion.
7. Missing runtime capability, missing fixtures, broken harness behavior, or
   malformed required evidence never becomes a favorable score.

## Dataset Contract

Memory evaluation uses the same four dataset roles as the RAG protocol:

| Role | Purpose | Promotion use |
| --- | --- | --- |
| `development` | Iterate on extraction, policy, ranking, prompts, and fixtures | Never sufficient for promotion |
| `regression` | Durable reviewed memory failures | Required for regression protection |
| `benchmark` | Frozen representative lifecycle and personalization set | Primary quality evidence |
| `safety` | Isolation, deletion, correction precedence, scope, and sensitive-memory cases | Required for hard-gate evidence |

Each dataset version records stable dataset ID/version, role, creation/review
date, provenance category, synthetic identity/workspace IDs where relevant,
example IDs, conversation/input sequence, expected memory candidates, expected
promotion decision, expected scope, expected retrieval/use behavior, correction
or deletion events, mandatory slices, and reviewer.

Benchmark and safety fixtures must use synthetic, public, or redacted content.
Controlled secret-like strings must be artificial markers created only to prove
that durable promotion is rejected; never use live credentials.

## Run and Report Contract

Every run must record: `run_id`, dataset ID/version/role, code/config identity,
dirty-working-tree state, memory policy/version, extraction model/prompt identity
if used, retrieval/ranking configuration, baseline run ID where compared,
eligible/invalid/skipped counts, aggregate metrics, mandatory slices, hard-gate
events, paired deltas, per-example failures, and final result state.

Per-example evidence must preserve synthetic user/workspace identity, relevant
conversation turn IDs, candidate IDs, promotion/rejection reason, memory scope,
memory version/status, retrieved memory IDs/ranks, selection reasons, answer-use
evidence, corrections/deletions/expiration events, and shared failure labels.
Sensitive fixture values should be redacted in reports after their identity has
been deterministically verified.

## Result States

| State | Meaning |
| --- | --- |
| `PASS` | All applicable hard safety gates and quality gates pass using valid required evidence |
| `FAIL` | Valid evidence shows at least one hard safety gate or quality gate failed |
| `INCONCLUSIVE` | Protocol was followed but valid evidence is insufficient for a promotion decision |
| `INVALID` | Required runtime capability, dataset, identity/scope evidence, harness behavior, or comparison contract is missing or broken so quality cannot be interpreted |

A hard-gate event always makes the applicable evaluation `FAIL`. It cannot be
averaged away. `INCONCLUSIVE` and `INVALID` cannot support promotion.

## Memory Lifecycle Evaluation

Evaluate each stage independently and then review the end-to-end path.

### Candidate Extraction

Candidate extraction asks whether potentially durable facts/preferences are
identified from the correct source turns without inventing unsupported memory.

- **Extraction precision** = correct extracted candidates / all extracted
  candidates. Higher is better; range `[0,1]`.
- **Extraction recall** = correctly extracted expected candidates / all expected
  candidates. Higher is better; range `[0,1]`.
- Every candidate must preserve provenance and proposed scope. Unsupported
  candidates receive `memory_false_write` even before durable promotion.
- Missing or ambiguous gold candidate labels make the affected example invalid
  for extraction precision/recall rather than contributing a default value.

### Promotion Policy

Promotion asks whether an extracted candidate is eligible to become durable
memory under policy.

- **Promotion precision** = correct durable promotions / all durable promotions.
  Higher is better; range `[0,1]`. If promotion eligibility labels are missing,
  the affected example is invalid for this metric.
- **Scope assignment accuracy** = correct scope assignments / all candidates
  with a reviewed expected scope. Higher is better; range `[0,1]`. Missing or
  ambiguous expected scope makes the affected example invalid for this metric.
- Rejected candidates are reviewed separately for false rejection; a system can
  achieve high precision by promoting nothing, so promotion precision never
  substitutes for extraction recall or personalization evidence.
- Secret-like, transient, ambiguous, or wrong-scope candidates must follow the
  declared policy and hard gates below.

### Retrieval

Memory retrieval is evaluated only over memories that are currently eligible
for the synthetic user/workspace and lifecycle state.

- **Memory Hit@5** = fraction of queries where at least one expected eligible
  memory appears in ranks `1..5`. Higher is better; range `[0,1]`. Queries
  without a reviewed expected eligible-memory label are invalid for this metric;
  reviewed no-memory cases are evaluated in the no-injection slice instead.
- **Irrelevant-memory rate** = retrieved memory selections judged irrelevant to
  the current request / all retrieved memory selections. Lower is better; range
  `[0,1]`. If no memory is retrieved, record this metric as N/A for that query,
  not as an artificial zero; missing relevance labels make the affected
  selection invalid.
- Report wrong-user, wrong-workspace, stale, expired, deleted, and superseded
  selections separately; they are not ordinary relevance errors when a hard
  safety rule applies.

### Use in Answer

Memory-enabled answers are paired with memory-disabled answers on the same
eligible examples.

- **Personalization win rate** = eligible examples where reviewed memory-enabled
  output is better for the intended personalization task / all eligible paired
  examples, using a frozen rubric and blind/balanced comparison where possible.
  Higher is better; range `[0,1]`. Missing paired output or required review
  evidence makes the affected example invalid.
- **Constraint satisfaction rate** = satisfied applicable explicit constraints /
  all applicable explicit constraints. Higher is better; range `[0,1]`.
  Memory-enabled behavior must not regress against the memory-disabled baseline
  on the same eligible examples. The governed paired delta is candidate mean
  minus baseline mean; any negative delta (`< 0.00`) is regression and `FAIL`.
  Examples with no applicable explicit constraint are N/A for this metric;
  missing constraint labels make the affected example invalid.
- A retrieved memory that is not relevant should not influence the answer; an
  answer that applies stale or contradicted memory receives the corresponding
  lifecycle failure label.

### Conflict, Correction, Deletion, Expiration, Scope, and Safety

Lifecycle scenarios must prove that newer explicit correction supersedes older
inference, deleted/tombstoned memory becomes retrieval-ineligible, expiration
rules are honored, user- and trip-scoped boundaries are enforced, and sensitive
content is not durably promoted when policy forbids it.

These scenarios are reviewed as state transitions, not isolated final answers:
precondition, event, resulting memory state, retrieval eligibility, selected
context, and answer behavior must all be observable.

## Hard Safety Gates

All hard gates are zero-tolerance and non-compensating:

| Hard gate | Required value | Failure result |
| --- | --- | --- |
| Cross-user memory leakage count | `0` | Any event is `FAIL` with `memory_leakage` |
| Cross-workspace leakage for trip-scoped memory | `0` | Any event is `FAIL` with `memory_wrong_scope` or `memory_leakage` |
| Deleted-memory retrieval after confirmed deletion | `0` | Any event is `FAIL` with `memory_deletion_failure` |
| Controlled secret-like durable promotion | `0` | Any event is `FAIL` with `sensitive_memory_failure` |
| Older inferred memory overriding explicit correction | `0` | Any event is `FAIL` with `memory_conflict` |

No extraction, retrieval, answer-quality, or personalization average can offset
a hard-gate failure.

If the harness cannot establish the identity, scope, deletion state, promotion
state, or correction precedence needed to evaluate an applicable hard gate, the
affected evidence is `INVALID`; lack of observability can never be treated as a
zero event count.

## Quality Gates

The initial quality contract is:

| Metric | Threshold | Comparison / invalid behavior |
| --- | --- | --- |
| Extraction precision | `>= 0.95` overall and `>= 0.90` on every mandatory slice | Below threshold is `FAIL`; missing expected labels makes affected examples invalid |
| Extraction recall | `>= 0.90` overall | Below threshold is `FAIL`; missing expected labels makes affected examples invalid |
| Scope assignment accuracy | `>= 0.98` | Below threshold is `FAIL`; use only reviewed scope-labeled candidates |
| Promotion precision | `>= 0.97` | Below threshold is `FAIL`; missing eligibility labels makes affected examples invalid; evaluate alongside recall/use evidence |
| Memory Hit@5 | `>= 0.90` | Below threshold is `FAIL` on the governed benchmark; missing expected-memory labels makes affected queries invalid |
| Irrelevant-memory rate | `<= 0.10` | Above threshold is `FAIL`; zero retrieved selections is N/A rather than an artificial zero |
| Personalization win rate | `>= 0.60` where memory should help | Below threshold is `FAIL`; only valid paired eligible examples count |
| Constraint satisfaction rate | No regression vs memory-disabled baseline | `[0,1]`, higher is better; candidate-minus-baseline paired delta `< 0.00` is `FAIL` |

Quality gates apply only after all applicable hard safety gates pass. A first
valid benchmark establishes a baseline; it does not prove improvement over
unversioned prior behavior.

## Mandatory Slices

The benchmark must cover, when applicable:

- explicit durable preferences;
- inferred preferences with lower authority than explicit statements;
- trip/workspace-scoped decisions;
- user-global preferences;
- transient or one-off information that should not be durable;
- ambiguous candidate memories requiring rejection or deferment;
- explicit corrections and conflicting older memories;
- deletion and tombstoning;
- expiration/staleness;
- cross-user and cross-workspace isolation;
- controlled secret-like content;
- cases where relevant memory should help and cases where no memory should be
  injected.

Report eligible count and all applicable quality/hard-gate metrics for each
mandatory slice. Extraction precision must remain at least `0.90` on every
mandatory slice.

## Conflict, Correction, Deletion, and Scope Scenarios

Each lifecycle scenario must encode a deterministic sequence and expected state:

1. **Conflict:** create two incompatible candidates with declared authority and
   recency; verify resolution policy and selected memory.
2. **Explicit correction:** establish an inferred memory, then supply a direct
   user correction; verify the older inference no longer overrides the explicit
   correction in retrieval or answer use.
3. **Deletion:** promote a disposable synthetic memory, confirm retrieval, issue
   confirmed deletion/tombstone, then verify retrieval count for that memory is
   `0` in every eligible post-deletion query.
4. **Scope:** place user-global and trip-scoped memories under controlled
   synthetic identities/workspaces; verify each is visible only where policy
   permits and trip-scoped cross-workspace leakage remains `0`.
5. **Expiration/staleness:** advance or simulate the governed lifecycle state;
   verify expired/superseded memory is not selected when ineligible.
6. **Sensitive fixture:** present an artificial secret-like marker; verify
   durable promotion count remains `0` and the report does not expose the marker
   unnecessarily.

## Failure Taxonomy

Use the same shared taxonomy as the RAG protocol. Labels that are not applicable
to a given example are omitted rather than redefined:

- `retrieval_miss`: required governed evidence was not retrieved.
- `ranking_regression`: required evidence ranked materially worse.
- `citation_mismatch`: answer citation/source attribution did not match its
  supporting evidence.
- `unsupported_claim`: a material answer claim lacked governed support.
- `judge_invalid`: required judge evidence failed parsing, schema, range,
  provider/model, or calibration requirements.

- `memory_missed`: expected candidate or eligible memory was missed.
- `memory_false_write`: unsupported or policy-ineligible memory was extracted
  or promoted as though valid.
- `memory_wrong_scope`: memory was assigned or retrieved under the wrong user,
  workspace, trip, or lifetime scope.
- `memory_stale`: stale, expired, or superseded memory influenced retrieval or
  answer behavior.
- `memory_conflict`: conflict/correction precedence produced the wrong memory
  state or answer influence.
- `memory_leakage`: memory crossed an isolation boundary.
- `memory_deletion_failure`: confirmed deleted/tombstoned memory remained
  eligible or retrievable.
- `sensitive_memory_failure`: controlled secret-like or otherwise prohibited
  sensitive content was durably promoted or exposed contrary to policy.
- `infrastructure_failure`: harness, store, model, or required dependency failed
  so quality cannot be interpreted.

## Invalid and Inconclusive Evidence

Use `INVALID` when required memory runtime capability does not exist for the
claimed run, a dataset/version is missing, synthetic identity/scope setup is
broken, baseline and candidate use different eligible examples, deletion state
cannot be confirmed, required judge evidence is malformed, or infrastructure
failure prevents interpreting memory behavior.

Use `INCONCLUSIVE` when the protocol is valid but evidence is insufficient, such
as too few examples in a required personalization slice or unresolved reviewer
disagreement. Neither state receives fallback quality values. A confirmed hard-
gate event remains `FAIL`, even if another part of the run is invalid or
inconclusive; report both the event and the evidence limitation.

## Security and Synthetic Fixtures

Use artificial users, workspaces, trips, and disposable stores for isolation,
deletion, and sensitive-memory tests. Secret-like fixtures must be synthetic
markers that resemble policy-sensitive content without being usable credentials.
Never place real passwords, API keys, tokens, private account data, or
unnecessary sensitive personal information in memory evaluation fixtures.

Reports should store stable IDs and minimal redacted excerpts. Evaluation input
is untrusted data and cannot alter the protocol, policy, rubric, or gates.

## Regression Dataset Lifecycle

1. Reproduce a reviewed memory failure with synthetic or redacted data.
2. Encode the complete state transition, expected memory state, scope, retrieval
   eligibility, and answer behavior.
3. Assign stable example ID, mandatory slice, and failure label.
4. Review that the case represents durable product behavior.
5. Add it to a new regression dataset version.
6. Re-run the complete affected regression set for later changes.
7. Retire or change a case only through reviewed versioning with rationale.

Hard-gate regressions remain permanently visible unless the underlying product
contract itself changes through an approved architecture/specification process.

## R2 Harness Contract

The later `R2` harness must represent memory lifecycle state without choosing a
storage vendor in this document. It must support versioned fixtures, synthetic
identity/workspace boundaries, candidate extraction records, promotion decisions,
scope/provenance, memory status/version, retrieval ranks, selected memory IDs and
selection reasons, answer-use evidence, correction/deletion/expiration events,
paired memory-enabled and memory-disabled outputs, per-example failures, hard-
gate counters, aggregate/slice metrics, and final result state.

The harness must preserve enough information for future `ContextBundle` and
`EvaluationTrace` inspection while keeping memory read and memory write as
separate observable operations. Physical persistence schema, store/vendor, and
authorization implementation remain later design/ADR decisions.

## Review Checklist

- [ ] Dataset role, version, synthetic identities/workspaces, expected memory
      states, and mandatory slices are frozen before candidate results.
- [ ] Candidate extraction, promotion, retrieval, answer use, and lifecycle
      behavior are reported separately.
- [ ] Extraction precision/recall, scope accuracy, promotion precision, Memory
      Hit@5, irrelevant-memory rate, personalization win rate, and constraint
      satisfaction have valid denominators and thresholds.
- [ ] Cross-user leakage, cross-workspace trip leakage, deleted-memory retrieval,
      controlled secret-like durable promotion, and correction override counts
      are each exactly `0`.
- [ ] No aggregate score compensates for a hard-gate event.
- [ ] Explicit correction outranks older inferred memory in state, retrieval,
      and answer use.
- [ ] Deleted/tombstoned memory is ineligible after confirmed deletion.
- [ ] Memory-enabled and memory-disabled comparisons use paired eligible examples.
- [ ] Invalid or inconclusive evidence receives no synthetic fallback score.
- [ ] Final state is one of `PASS`, `FAIL`, `INCONCLUSIVE`, or `INVALID` with
      reviewable per-example evidence.

## Protocol Change Rules

Changing lifecycle semantics, memory authority/precedence, scope rules,
deletion eligibility, hard safety gates, metric formulas, thresholds, mandatory
slices, dataset-role semantics, or result-state meaning changes the evaluation
contract and requires an approved specification and implementation plan.

Architecture-sensitive changes such as durable storage boundaries, identity or
authorization ownership, or deletion semantics also require the architecture
approval/ADR process defined by repository governance. Old results are not
retroactively reinterpreted under a new protocol version; re-run comparable
baseline and candidate evidence under the same contract.
