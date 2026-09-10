# AI Memory Core Engineering Design

| Field | Value |
| --- | --- |
| Status | Draft |
| Version | 0.1 |
| Date | 2026-09-09 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Core AI-engineering problems, architecture, solutions, evaluation, and staged learning path for an agent Memory system |
| Related issue | Repository-owner approved exception: interactive Memory architecture learning session |
| Superseded document | Re-scopes the Draft Memory Read Pipeline V1.5 exploration; approved Write Pipeline artifacts remain authoritative for their implemented scope |

## Operating Rule

This is the active living spec after the 2026-09-09 scope reset. The objective
is to learn and implement the important AI Memory problems with production-
minded correctness, not to reproduce every platform, product, or distributed-
systems concern of a company deployment. Every phase must produce an
understandable behavior, explicit invariants, failure evidence, and evaluation
before breadth is added.

No implementation plan or new runtime code is authorized while this spec is
Draft or In Review.

## Objective

Build and understand a complete AI Memory loop:

```text
Write -> Consolidate -> Store -> Read -> Use -> Evaluate
```

“Complete” means these responsibilities connect end to end and can be
evaluated. It does not mean implementing every Memory type, key, scaling
mechanism, UI, or operational feature at once.

## Six Core AI Memory Problems

### 1. Write: when and what to remember

Resolve whether a message carries durable value; extract facts/preferences;
normalize key/value; choose user or conversation scope; distinguish explicit
from inferred evidence; block sensitive/prohibited content; preserve exact
provenance.

Selected direction:

```text
deterministic safety filter
-> structured model extraction
-> registry validation
-> immutable evidence and candidate
```

### 2. Consolidation: how new evidence changes known state

Resolve duplicate, reinforcement, correction, contradiction, temporary
exception, staleness, forgetting, authority, and time.

Selected direction:

```text
canonical assertion identity
-> current-version lookup
-> bounded relationship classification only when deterministic comparison cannot decide
-> deterministic typed resolver
-> ADD | REINFORCE | SUPERSEDE | ADD_EXCEPTION | PENDING_CONFLICT | NOOP | REJECT
```

### 3. Store: how Memory truth is represented

Keep source evidence, candidate proposal, policy decision, stable assertion,
and immutable versions distinct. PostgreSQL is canonical; retrieval indexes are
rebuildable projections only when evidence requires them.

```text
evidence -> candidate -> decision -> assertion -> version
```

### 4. Read: when and what to retrieve

Determine whether the request needs Memory; hard-filter owner/lifecycle/
sensitivity; select relevant state; resolve current-turn, conversation, and
user precedence; abstain on uncertainty; exclude Shadow/Pending/deleted state.

Selected direction:

```text
rule-first relevance
-> bounded model classification only when ambiguous
-> deterministic eligibility and effective-state resolution
-> current turn > conversation > user
-> select or abstain
```

### 5. Use: how Memory influences the agent

Provide compact canonical context, preserve instruction authority, enforce
token budget, treat preferences as soft by default, honor current requests, and
prevent raw evidence or Memory text from becoming prompt instructions or
citations.

Initial context shape:

```json
{
  "key": "travel.preference.hotel_atmosphere",
  "value": "quiet",
  "scope": "user",
  "influence": "soft_preference"
}
```

### 6. Evaluate: how to prove Memory helps

Measure extraction, normalization, conflict resolution, retrieval precision/
recall, correct abstention, generation-use correctness, over-personalization,
knowledge update/forgetting, privacy leakage, latency, and cost separately.
Hard privacy/correctness failures cannot be averaged away by answer quality.

## Minimal Production-minded Concerns

Only concerns that directly protect Memory correctness are in the initial
critical path:

1. PostgreSQL transaction boundaries.
2. Idempotent writes and retries.
3. Transactional outbox for inferred background writes.
4. Direct owner isolation.
5. Graceful no-Memory fallback.
6. Content-safe structured tracing.
7. Feature gating.
8. Correct delete/forget propagation.

Each is implemented only far enough to prove its Memory invariant. Detailed
foreground turn scheduling, streaming transport, multi-host autoscaling,
operator quarantine tooling, percentage rollout, and rich product UI are
deferred platform/product work.

## Initial Semantic Slice

The first complete loop executes one key:

```text
travel.preference.hotel_atmosphere
quiet | lively | central | secluded
```

Active scopes are user and conversation. The key is single-valued and ordinary
personal. It is a soft preference, not a hard constraint.

## Roadmap

### Stage A: Finish and understand the Semantic Write vertical slice

**Purpose:** create trustworthy canonical state before reading it.

Deliver:

1. Registry and immutable domain contracts.
2. Evidence/candidate/decision/assertion/version representation.
3. Deterministic conflict resolver.
4. Sensitivity/prohibited-content policy.
5. PostgreSQL Unit of Work and idempotency.
6. Explicit low-risk write and background `SHADOW` extraction.
7. Write evaluation and failure tests.

Exit gate:

- One explicit hotel-atmosphere preference commits correctly.
- Background inference creates no active version.
- Duplicate delivery creates no duplicate logical Memory.
- Conflict/update/delete behavior passes the truth table.
- Prohibited and cross-owner durable writes are zero.
- The integrated repository tests are green; intermediate child checkpoints
  alone do not complete the stage.

Learning outcome: explain every transition from user evidence to current
semantic state and every deterministic/model authority boundary.

### Stage B: Build the Semantic Read and Use vertical slice

**Purpose:** turn the same trusted state into useful personalization.

Deliver:

1. Rule-first relevance with one bounded classifier for ambiguous requests.
2. Owner/lifecycle/sensitivity eligibility.
3. Deterministic effective state: current turn, conversation, then user.
4. Explicit abstention reasons.
5. One canonical `MemoryContext` item with a small token budget.
6. Safe prompt-authority contract and no-Memory fallback.
7. Retrieval/non-use/use evaluation.

Exit gate:

- Hotel requests use the effective preference appropriately.
- Irrelevant requests abstain.
- Current-turn and conversation overrides beat the user default without
  mutating it.
- Shadow, pending, deleted, sensitive, and foreign Memory are never used.
- Memory failure preserves a controlled answer without Memory.
- Paired evaluation shows appropriate soft influence without material answer
  regression or over-personalization.

Learning outcome: explain why a Memory was selected, why another was excluded,
and how selected state changed or did not change generation.

### Stage C: Close and evaluate the end-to-end loop

**Purpose:** establish that Write and Read work together over updates, not only
in isolated tests.

Scenarios:

1. Explicit save -> next relevant turn uses Memory.
2. Irrelevant turn -> correct non-use.
3. Correction -> old value stops influencing answers.
4. Conversation exception -> local value wins; global default survives.
5. Delete/disable -> subsequent reads exclude the value.
6. Provider/read failure -> no-Memory fallback.
7. Repeated inferred evidence -> Shadow only in the first policy phase.

Exit gate: versioned end-to-end report with per-stage metrics, largest failures,
latency/cost, hard safety counts, environment, exact change set, and limitations.

Learning outcome: diagnose whether a failure belongs to extraction,
consolidation, persistence, retrieval, context assembly, or generation use.

### Stage D: Prove semantic generality with three representative shapes

Add only after Stage C passes:

1. A second single-valued key.
2. A set-valued key.
3. A conditional preference.

Purpose: prove registry/cardinality/resolver/read interfaces generalize without
opening 10-15 keys. If a new shape requires scattered special cases, return to
module design before adding breadth.

### Stage E: Conversation Summary Memory

Design separately after semantic generality. Focus on compression, salience,
information loss, refresh/invalidation, current-turn consistency, and summary
evaluation. Do not treat a summary as a set of verified semantic facts.

### Stage F: Episodic Memory

Design separately after Summary or when a concrete experience-reuse behavior
requires it. Focus on episode qualification, scenario/action/outcome structure,
temporal retrieval, provenance, and future usefulness. Do not duplicate every
conversation as an episode.

## Current Project Position

The project is inside Stage A. The Write Pipeline has approved architecture and
child plans, but implementation is still being executed and reviewed in linked
worktrees. Child-level tests or pure-domain completion do not establish a
finished Write Pipeline; PostgreSQL integration, runtime flows, evaluation,
review resolution, and final full verification remain required.

Read/Use design may continue in documentation, but Read runtime implementation
must not begin against an unstable or non-integrated Write contract.

## Explicitly Deferred

1. Foreground per-conversation FIFO/Turn aggregate.
2. SSE replay and token-stream publication protocol.
3. Foreground worker lease/fencing and cancellation orchestration.
4. Operator quarantine command surface.
5. Percentage rollout cohorts and complex deployment automation.
6. Redis or cross-turn Memory cache.
7. Vector retrieval for the first semantic key.
8. Conversation Summary and Episodic implementation before semantic gates pass.
9. Broad UI product polish beyond the minimum Memory controls already governed
   by approved Write artifacts.

These remain useful production topics and may be studied in an appendix, but
they are not implementation dependencies for the core AI Memory learning path.

## Design and Implementation Gates

1. Finish the current Write Pipeline under its approved specs/plans.
2. Approve this core architecture spec after its remaining decisions are
   resolved.
3. Produce a small Read/Use design section and evaluation protocol governed by
   this core scope.
4. Approve an implementation plan that decomposes Stage B/C into reviewable
   vertical tasks.
5. Implement, review, and verify one task at a time.
6. Do not begin Stage D/E/F merely because Stage B code exists; the preceding
   evaluation gate must pass.

## Working Glossary

| Term | Meaning |
| --- | --- |
| Evidence | Immutable source observation with provenance |
| Candidate | Structured proposed memory before policy authority |
| Decision | Immutable policy outcome for a candidate |
| Assertion | Stable semantic identity for owner, scope, key, subject, and condition |
| Version | Immutable value/lifecycle revision of an assertion |
| Shadow | Valid inferred candidate/evidence that is not active or retrievable |
| Effective Memory | The one eligible value selected after current-turn/conversation/user precedence |
| Abstention | Governed choice to provide no Memory context |
| Memory Context | Small canonical data supplied to generation below current user authority |
| Use correctness | Whether generation applies selected Memory appropriately |

## Open Decisions

1. Which exact Stage-A child outputs are mandatory before Stage B design may
   move from Draft to In Review?
2. What is the smallest Stage-B evaluation corpus that still covers bilingual
   relevance, abstention, override, lifecycle, and use correctness?
3. Which three representative semantic keys should Stage D use?

## Approval Record

Not approved. The repository owner approved the scope reset and six-problem
learning direction on 2026-09-09. Exact architecture and later implementation
plans retain separate approval gates.
