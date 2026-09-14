# Agent Memory Target Architecture

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.4 |
| Date | 2026-09-12 |
| Last amended | 2026-09-13 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Chat-first, PostgreSQL-backed Agent Memory covering turn understanding, explicit/inferred write, consolidation, lifecycle, read, use, evaluation, and multi-conversation behavior |
| Related issue | Repository-owner approved exception: interactive Memory architecture redesign on 2026-09-12 |
| Superseded document | [Unified Multi-Conversation Agent Memory Architecture](./2026-09-10-unified-multi-conversation-agent-memory-architecture.md), superseded by approved v0.2 on 2026-09-12 |

## Summary

This document is the replacement target architecture for Agent Memory. It is
written from the repository's current PostgreSQL Chat baseline rather than from
the older Workspace/SQLite transition state.

The product remains chat-first. A user turn may be:

1. a normal query;
2. an explicit Memory action such as remember/correct/forget/inspect; or
3. evidence for asynchronous inferred Memory.

Models may interpret uncertain semantics, but deterministic application policy
owns authorization, lifecycle transitions, persistence, and read eligibility.

The target supports four governed Memory families — semantic, episodic, working,
and procedural — across multiple conversations. User-derived semantic, episodic,
and working Memory are tenant-owned canonical PostgreSQL state. Procedural Memory
is a system-owned family with a separate publication/configuration boundary; it
is not another tenant Memory scope. Full-text/vector indexes are optional
rebuildable projections.

The first implementation target is deliberately narrower than the full taxonomy:
prove one complete explicit semantic vertical slice before enabling inferred
activation or adding more Memory families.

## Current State

Verified current baseline:

| Evidence | Implemented behavior | Architectural consequence |
| --- | --- | --- |
| `backend/app/main.py` | Mounted runtime exposes health, ops, Chat, and conversations; public Memory-management routers are absent | Explicit Memory returns through Chat; do not restore the removed Memory Manager/API |
| `backend/app/runtime_container.py` | Mounted Chat uses `PostgresConversationRepository` through one runtime composition root | PostgreSQL is already the conversation source of truth |
| `backend/conversations/postgres_repository.py` | Turn completion/failure releases or cancels outbox work; deletion uses a deletion epoch fence | Turn readiness and source validity are existing correctness primitives |
| `backend/orchestration/conversation_orchestrator.py` | `TurnOutcome` already names the aggregate result returned by one Chat turn | Agent-result semantics need a distinct `TurnDisposition`, not a second `TurnOutcome` type |
| `backend/memory/write_pipeline/runtime.py` | Memory worker runs as a separate service/process | Background Memory remains operationally separate from API Chat |
| `backend/memory/write_pipeline/models.py` | Existing lifecycle has no product-level `REVOKE`/`REVOKED` | Explicit forget/no-resurrection still needs a first-class contract |
| `backend/memory/write_pipeline/postgres.py` | Memory changes commit atomically inside the Memory UoW | Explicit action acknowledgement requires a higher application transaction boundary |
| `backend/memory/write_pipeline/registry.py` | Current registry proves one semantic preference slice | Target generality must grow by evaluated vertical slices, not free-form keys |
| ADR 0020 | Separate public Memory management was intentionally removed | Chat-native explicit Memory is the allowed future direction |

The v0.2 baseline below was approved on 2026-09-12. The v0.3 dialogue-state
responsibility refinement and the v0.4 source-handling proposal/authority
clarification were approved by the repository owner on 2026-09-13. Target
behavior remains unimplemented until its governing implementation plan and
staged verification are satisfied.

## Problem Statement

The repository has useful Memory components but no single target contract for:

```text
understand
-> route
-> write/form
-> consolidate
-> lifecycle/activate
-> store
-> read
-> use
-> evaluate
```

Without one contract, the system can fail in ways that are hard to notice:

- an ordinary statement becomes a permanent preference;
- old background work resurrects a Memory after explicit forget;
- conversation deletion either removes too much or leaves stale inference alive;
- an `ACTIVE` row is treated as automatically readable;
- Memory commits while the user sees a failed acknowledgement;
- missing handling state is interpreted as background permission;
- Memory is injected whenever it exists instead of when it is relevant.

## Goals

1. Interpret context-dependent user turns into typed, non-authoritative semantics.
2. Route each turn deterministically into normal query, explicit Memory action,
   or clarification.
3. Support Chat-native remember, correct, forget, and inspect.
4. Support conversation and user scopes across multiple conversations.
5. Support semantic, episodic, and working tenant Memory plus system-owned
   procedural Memory through a separate publication boundary.
6. Separate provenance authority, scope, retention, sensitivity, lifecycle, and
   response-time precedence.
7. Make durable explicit writes high-precision and deterministic at the
   authorization boundary.
8. Keep inferred formation asynchronous and non-blocking.
9. Prevent post-forget resurrection at formation, activation, and read.
10. Select Memory only when lifecycle-eligible and relevant to the current turn.
11. Preserve tenant isolation, idempotency, source validity, deletion
    propagation, trace privacy, and operational recovery.
12. Require evaluation before inferred Memory becomes active.

## Non-goals

1. Restoring Workspace/Planner as a requirement for Chat.
2. Restoring the removed Memory Manager or public Memory-control routes.
3. Building an unbounded autonomous agent loop.
4. Adding booking/payment/external side-effect tools in this architecture.
5. Letting an LLM choose SQL, durable authorization, retention, deletion, or
   activation directly.
6. Treating embeddings, raw transcripts, summaries, or model confidence as
   canonical truth.
7. Introducing a distributed queue before PostgreSQL-outbox limits are measured.
8. Multi-region active-active Memory consistency.
9. A graph database as canonical Memory storage.
10. Bulk account-wide Memory management/export/toggles in the first vertical
    slice; those controls need a separate approved design.

## Alternatives Considered

### A. One Memory Agent Owns Everything

One model classifies intent, extracts Memory, chooses mutations, retrieves
context, and invokes storage tools.

Benefit: fastest prototype and maximum language flexibility.

Rejected because the same probabilistic component becomes interpretation,
authorization, lifecycle, and persistence authority. Durable false-positive
writes then become difficult to prevent and evaluate.

### B. Generic Framework Memory as Canonical Lifecycle

Adopt one framework's generic Memory objects, promotion rules, and vector
retrieval as the source of truth.

Benefit: less bespoke code and faster breadth.

Rejected as canonical architecture because Travel Agent has application-specific
scope, retention, deletion, no-resurrection, source-validity, and procedural
publication rules. Frameworks may still be used behind adapters/projections.

### C. Typed Bounded Turn + Governed Memory Lifecycle

Use typed turn understanding, deterministic action authority, PostgreSQL
canonical state, family-specific activation, shared lifecycle predicates, and
conservative read/use.

Selected because high-risk decisions have explicit owners and testable seams,
while models remain available where deterministic interpretation is weak.

## Core Domain Dimensions

These dimensions are independent.

### Authority

Answers: **how strong is the provenance?**

```text
EXPLICIT_SAVE
EXPLICIT_STATEMENT
REPEATED_INFERENCE
```

Authority does not imply lifetime.

### Scope

Answers: **where may this Memory influence behavior?**

```text
conversation
user
```

Conversation scope may override a user default in the current conversation
without rewriting that default.

`agent` is deliberately **not** a tenant Memory scope. Procedural Memory is a
system-owned family published through a separately governed versioned
configuration/policy boundary. It must not be represented by inventing a
sentinel `owner_user_id` or weakening tenant RLS on user Memory tables.

### Retention

Answers: **what must remain true for this Memory to stay eligible?**

```text
CONVERSATION_BOUND
SOURCE_BOUND
USER_DURABLE
```

| Origin | Typical retention | Meaning |
| --- | --- | --- |
| Corroborated explicit remember/correct at user scope | `USER_DURABLE` | Value may survive source-conversation deletion; deleted-source evidence becomes inaccessible |
| Plain statement without durable-save speech act | `SOURCE_BOUND` or `CONVERSATION_BOUND` | Explicit statement does not automatically become permanent account state |
| Background inferred user Memory | `SOURCE_BOUND` | Eligibility depends on sufficient valid independent evidence |
| Conversation-local state/override | `CONVERSATION_BOUND` | Ends with conversation deletion/expiry |

`retention_mode` is assigned by policy when a Memory version is written and is
persisted with that version. Read-time code must not re-derive retention from
authority/origin, because a later policy version must not silently reinterpret
historical Memory.

Time-based validity is a separate input. A Memory may persist an optional
`expires_at`; when present, `now >= expires_at` makes it effectively expired.
`CONVERSATION_BOUND` and `SOURCE_BOUND` validity are not encoded by mutating
`expires_at` when a source disappears. They are evaluated from retention and
provenance/source validity.

### Sensitivity

Classification is monotonic: deterministic/registry policy sets a floor; model
classification may only raise it.

Initial long-term rollout persists only `ordinary_personal` user-derived Memory.
`contextually_sensitive`, `restricted`, and `prohibited_secret` are no-store for
durable user Memory until a separate approved policy changes that boundary.
Prohibited secrets are rejected before Memory-model exposure.

### Lifecycle

Target vocabulary must distinguish at least:

```text
SHADOW / PENDING
ACTIVE
SUPERSEDED
REVOKED
REJECTED
EXPIRED
```

`EXPIRED` may be an effective lifecycle result derived from persisted
`expires_at`; correctness does not depend on a periodic sweeper changing every
row. A later sweeper may clean indexes/storage, but read/write eligibility must
already fail correctly without it.

## Memory Families

| Family | Representative types | Typical scope | Main use |
| --- | --- | --- | --- |
| Semantic | preference, profile fact, constraint, relationship | User/conversation | Personalization and constraints |
| Episodic | experience, completed action, decision, feedback | Conversation; governed user generalization | Relevant past events/reasons |
| Working | summary, open goal, temporary override, unresolved question | Conversation | Continuity under context limits |
| Procedural | response policy, tool workflow, planning strategy | System-owned publication boundary | Agent behavior; not tenant/user-writable |

Semantic Memory is not semantic search. Vector similarity is only a retrieval
technique.

## Dialogue State and Turn Understanding

### DialogueStateResolver

Turns such as `"tiếp tục đi"`, `"cái đầu tiên"`, or `"giữ cái đó nhưng đổi
ngày"` depend on prior context.

`DialogueStateResolver` deterministically assembles ephemeral dialogue context
from eligible recent-turn rows. Its Stage-1 responsibility is structural:
retain delivered user/assistant turns in stored sequence order, expose the
latest user and assistant turns, and fail closed if rows from more than one
conversation are supplied. It does not infer topic, referents, goal, intent, or
clarification semantics.

`TurnUnderstanding` owns semantic interpretation of the current message against
that structural context. It derives active topic, referents, current goal,
pending clarification, and similar short-lived semantic dependencies. This
keeps transcript reconstruction deterministic while giving language
interpretation one owner.

Once Working Memory exists in Stage 5, eligible Working Memory becomes an
additional governed input to dialogue-state reconstruction. It supplements
recent-turn context; it does not transfer semantic-interpretation ownership out
of `TurnUnderstanding`. Stage 1 does not depend on a Memory family that has not
yet been implemented.

`DialogueState` is reconstructed and discarded. It is not a second durable
Working Memory store.

**Decision and trade-off.** Keeping `DialogueStateResolver` structural gives the
system one deterministic place for transcript eligibility, ordering, and
conversation isolation, and one semantic owner in `TurnUnderstanding`. This
reduces duplicate language heuristics and makes state reconstruction easy to
test without a model. The trade-off is that `TurnUnderstanding` carries more of
the semantic workload and cannot rely on pre-interpreted topic/referent fields.
If multiple future consumers need reusable semantic dialogue state, that should
be introduced as a separately approved typed semantic contract rather than by
silently moving interpretation back into the resolver.

### TurnUnderstanding

```python
understand_turn(message, dialogue_state) -> TurnSemantics
```

Governed output includes:

```text
interaction_mode:
  normal_query | explicit_remember | explicit_correct |
  explicit_forget | explicit_inspect | ambiguous
topics
entities
current_assertions
current_overrides
memory_namespaces_needed
temporal_context
needs_clarification
reason_codes
```

Resolution order:

```text
deterministic safety checks
-> high-precision explicit/domain rules
-> bounded structured model classification when unresolved
-> closed-schema validation
-> deterministic escalation/final semantics
```

The model may interpret semantics. It cannot authorize durable mutation, lower
sensitivity, activate Memory, choose SQL, or select a database operation.

### TurnDisposition

`MessageStatus` and agent reasoning outcome are orthogonal dimensions with
constrained valid combinations. `MessageStatus` continues to describe
persistence completeness (`PENDING`, `COMPLETE`, `FAILED`). `TurnDisposition`
describes what the bounded agentic turn achieved:

```text
ANSWERED
NEEDS_CLARIFICATION
INCOMPLETE
EXECUTION_FAILED
```

The existing aggregate `TurnOutcome` remains the Chat-orchestrator return type
and carries the disposition. For example, a fully persisted assistant message
asking a focused clarification has `MessageStatus.COMPLETE` and
`TurnDisposition.NEEDS_CLARIFICATION`. `TurnDisposition` must not be modeled as
another storage status.

`TurnDisposition` is finalized only when the turn reaches a terminal message
status. A `PENDING` assistant row has no finalized disposition, and a persisted
`MessageStatus.FAILED` row cannot be paired with `TurnDisposition.ANSWERED`.
`MessageStatus.COMPLETE` may carry `ANSWERED`, `NEEDS_CLARIFICATION`,
`INCOMPLETE`, or `EXECUTION_FAILED`; in the last case the completed assistant
message reports an execution/context limitation rather than a persistence
failure.

For the first implementation, `TurnDisposition` remains an internal application
contract carried by `TurnOutcome`; it is not added to the public Chat response
schema. A future UI/API contract may expose it only through a separately
approved change.

## Action Routing and Explicit Intent

`ActionRouter` is pure application logic:

```text
NORMAL_QUERY
EXPLICIT_MEMORY_ACTION
NEEDS_CLARIFICATION
```

Durable mutation additionally passes `ExplicitIntentGate`, which must
deterministically corroborate a speech act such as remember/correct/forget.

A model may parse the payload after that gate; classifier output alone never
authorizes durable personal state.

Model-assisted explicit parsing is bounded by all of the following:

1. at most one structured parsing call for one explicit action;
2. a hard timeout;
3. fail-closed behavior on timeout, malformed output, or provider failure;
4. closed registry validation of every proposed key/value/scope; and
5. treatment of parsed content as untrusted data, never as instructions.

A model result outside the registry cannot become durable state. Concrete
latency SLO numbers are measured in the implementation/evaluation plan before
enablement rather than invented in this architecture document.

This intentionally optimizes durable explicit writes for precision before
recall: missing one save is recoverable; inventing permanent state may affect
many future conversations.

`explicit_inspect` is read-only and does not require the durable-mutation gate,
but still obeys owner/lifecycle/sensitivity read policy. Turn Understanding may
recognize this mode before the Memory read path is enabled, but the capability
is not delivered until Stage 3; before then it returns a controlled
`INCOMPLETE`/capability-unavailable outcome rather than fabricated Memory state.

## Bounded Agentic Turn

The synchronous path is agentic but bounded:

```text
inspect dialogue state
-> understand turn
-> choose action/context plan
-> enforce policy
-> execute one context/tool phase
-> observe
-> answer
```

There is no unbounded plan-act-observe loop. One context/tool phase is allowed
per turn. Memory Read and RAG may run in parallel inside that phase because both
are read-only context sources.

If one phase cannot safely satisfy the request, return the appropriate
`TurnDisposition` (`INCOMPLETE`, `NEEDS_CLARIFICATION`, or
`EXECUTION_FAILED`) instead of false success.

## Source Handling

Background Memory must not infer permission from absence.

Stage 1 separates a non-authoritative orchestration proposal from the durable
family-specific authority record. `MemoryFamily` is one closed vocabulary:

```text
SEMANTIC
EPISODIC
WORKING
PROCEDURAL
```

Task 5 may produce background-handling proposals only for `SEMANTIC`; the other
families become operational only in their separately evaluated stages.

Orchestration produces a typed proposal without needing storage-owned outbox
identity:

```text
SourceHandlingProposal(
  source_message_id,
  family,
  outcome,
  reason_code,
)

SourceHandlingProposalOutcome:
  BACKGROUND_ELIGIBLE
  BACKGROUND_BLOCKED

SourceHandlingReason:
  EXPLICIT_ACTION
  BACKGROUND_POLICY_ELIGIBLE
  AMBIGUOUS_INTENT
  SENSITIVE_BLOCKED
```

The mapping is closed: `BACKGROUND_POLICY_ELIGIBLE` may propose
`BACKGROUND_ELIGIBLE`; explicit action, ambiguous intent, and sensitive/prohibited
source handling propose `BACKGROUND_BLOCKED`. The proposal is evidence about the
current turn only. It never grants worker authority and it does not fabricate or
query a `source_outbox_id`.

The authoritative durable contract is the family-specific record:

```text
SourceHandlingRecord(
  source_outbox_id,
  source_message_id,
  family,
  outcome,
  reason_code,
  recorded_at,
)
```

The governed authoritative outcomes are:

```text
BACKGROUND_ELIGIBLE
EXPLICIT_APPLIED
EXPLICIT_REFUSED
EXPLICIT_NOOP
FORGET_APPLIED
FORGET_REFUSED
```

`UNHANDLED` is deliberately **not** an outcome enum member. It is the semantic
state created by absence of a persisted `SourceHandlingRecord`; absence never
means permission. A blocked proposal likewise cannot be reinterpreted as
background permission merely because no record has been persisted yet.

The stable uniqueness boundary is `(source_outbox_id, family)`. Background
formation may process a family only after a persisted positive
`BACKGROUND_ELIGIBLE` record. Binding the actual `source_outbox_id` belongs to
the Stage-2 transaction/persistence seam, where storage identity is available;
Stage 1 must not widen the Conversation API or query storage solely to obtain an
outbox identifier for a proposal.

## Components and Responsibilities

| Component | Owns | Must not own |
| --- | --- | --- |
| `ChatApplication` | One bounded synchronous turn: state resolution, routing, context planning, generation, terminal state | Background extraction lifecycle |
| `ConversationStore` | Messages, turn allocation/completion, outbox capture/release/cancellation, deletion fence, transaction-aware guarded turn transition | Memory semantics |
| `DialogueStateResolver` | Deterministic structural dialogue context from one conversation: eligible recent turns, stored ordering, latest user/assistant turns, later eligible Working Memory input | Semantic interpretation or durable Memory |
| `TurnUnderstanding` | Typed semantic interpretation of the current message against `DialogueState`, including topic/referent/goal/clarification semantics | Mutation authority or transcript persistence |
| `ActionRouter` | Deterministic branch selection | Tool execution or persistence |
| `ExplicitIntentGate` | High-precision authorization of remember/correct/forget speech acts | Key/value parsing, SQL, lifecycle effect |
| `SourceHandlingPolicy` | Pure family-specific typed proposal and positive-background gate semantics | Outbox identity lookup, persistence, worker formation, or durable mutation authority |
| `ExplicitMemoryActionHandler` | Registry/scope/retention/sensitivity/conflict validation and typed change proposal | Transaction commit |
| `ExplicitMemoryTurnCommit` | API-owned transaction for atomic explicit Memory + acknowledgement + source-handling + guarded terminal turn commit | Semantic interpretation |
| `BackgroundMemoryCommit` | Worker-owned transaction for fenced background semantic effect + source-event completion | Explicit/API-turn authority |
| `MemoryFormationEngine` | Background extraction into immutable evidence/candidates | Direct activation |
| `MemoryConsolidationEngine` | Duplicate/reinforce/correct/conflict relation and governed change | Persistence side effects |
| `MemoryActivationPolicy` | Family/type-specific activation decision | Retrieval ranking |
| `MemoryLifecyclePolicy` | Shared eligibility predicates used by write, formation, activation, and read | Relevance scoring or transaction authority |
| `MemoryWriteStore` | PostgreSQL canonical Memory mutation primitives on a caller-owned transaction/connection | Transaction ownership or prompt composition |
| `MemoryStore` | PostgreSQL canonical tenant-scoped Memory rows/state | Semantic lifecycle eligibility, relevance, precedence, ranking, or prompt composition |
| `MemoryReadEngine` | Eligibility, relevance, precedence, conflict exclusion, selection/abstention | Raw prompt injection |
| `ContextPlanner` / `ContextArbiter` / `MemoryContextComposer` | Source plan, deterministic admission/budget, controlled context | Canonical Memory state |
| `MemoryWorkerRuntime` | Claim/lease/retry/fence/backoff/dead-letter/shutdown | API-turn authority |
| `MemoryEvaluation` | Datasets, metrics, promotion gates, regressions | Runtime self-promotion |

`ExplicitMemoryTurnCommit` is the critical API transaction seam. A successful
explicit action must commit, in one idempotent application transaction:

1. Memory evidence/decision/lifecycle effect;
2. stable semantic idempotency result;
3. family-specific `SourceHandlingRecord`;
4. deterministic assistant acknowledgement row; and
5. terminal outbox/turn state.

No durable mutation may become visible if the acknowledgement did not commit.
Conversation and Memory adapters therefore need transaction-aware primitives on
a caller-owned shared connection rather than independently committing nested
transactions. The Conversation side must preserve the existing guarded
`pending -> terminal` transition and `TransitionResult.applied` semantics; the
Memory side must expose an equivalent `apply_on(connection, ...)` mutation seam.
The coordinator must not bypass either domain's idempotency/concurrency guard by
issuing ad hoc SQL.

Background writes use a distinct `BackgroundMemoryCommit` transaction owner.
The two commit owners share the same pure lifecycle/consolidation domain and the
same `MemoryWriteStore`; execution mode does not enter `MemoryLifecyclePolicy`.

The common transaction primitives are deliberately smaller than the two
coordinators:

```text
bind tenant
-> lock/validate conversation + deletion_epoch
-> [worker only: lock/validate outbox lease]
-> memory assertion/version rows
```

The canonical lock order is therefore:

```text
conversation -> outbox (worker only) -> memory rows
```

No path may acquire these shared locks in reverse order. Tenant binding and the
conversation fence are shared primitives; outbox lease authority exists only on
the background path. This keeps transaction authority separate from Memory
lifecycle semantics without duplicating the common fence rule.

Retry identity is derived from stable semantic inputs — owner, source message,
action family, canonical assertion identity, scope, and target generation — not
from random candidate IDs or generated acknowledgement text.

`MemoryLifecyclePolicy` centralizes source validity, retention, suppression
generation, temporal expiry, lifecycle status, scope, and sensitivity
eligibility. It is pure domain policy: it does not know whether the caller is an
API transaction or a worker transaction. These rules must not be independently
reimplemented in write, activation, and read.

`MemoryStore` may enforce physical storage predicates and tenant isolation, but
it returns storage-scoped rows rather than deciding semantic readability.
Lifecycle eligibility remains owned by `MemoryLifecyclePolicy`; relevance,
precedence, ranking, and abstention remain owned by `MemoryReadEngine`.

`ContextPlanner` proposes only `none | rag_only | memory_only | both`.
`ContextArbiter` is deterministic final authority over admitted sources and
budget; `MemoryContextComposer` emits typed context, never raw evidence as
instructions.

Dependency direction:

```text
HTTP / worker adapters
-> application workflow
-> pure domain contracts/policies
-> storage/model ports
<- PostgreSQL/model-provider adapters
```

Domain modules do not import FastAPI, SQLAlchemy, provider SDKs, frontend code,
or RAG implementations.

## Data Flow

### Normal Query

1. Authenticate and resolve/create owner-scoped conversation.
2. Allocate durable turn + extraction outbox intent.
3. Reconstruct deterministic structural `DialogueState` from the current conversation.
4. Interpret the current message against that state and produce validated `TurnSemantics`.
5. Route `NORMAL_QUERY`.
6. ContextPlanner chooses among the source modes enabled for the current stage.
7. Execute Memory/RAG reads; `both` may run in parallel.
8. ContextArbiter admits/rejects evidence and enforces budget.
9. Compose controlled context and generate response.
10. Terminal normal-turn transaction stores family-specific source handling and
    completes/releases or fails/cancels the turn/outbox together.

Background Memory never blocks the response.

### Explicit Remember / Correct / Forget

1. Allocate source turn/outbox intent.
2. Resolve dialogue + typed semantics.
3. Route `EXPLICIT_MEMORY_ACTION`.
4. ExplicitIntentGate corroborates mutating speech act.
5. Apply safety/secret policy before Memory-model exposure.
6. Parse/normalize payload with at most one bounded closed-schema model call if
   deterministic normalization is insufficient; timeout/invalid output means no
   durable write.
7. Validate registry, scope, retention, sensitivity, current assertion state.
8. Resolve typed lifecycle change.
9. `ExplicitMemoryTurnCommit` binds the tenant, validates the conversation
   fence, and atomically commits Memory effect, idempotency, source handling,
   acknowledgement, and the guarded terminal turn/outbox transition on one
   connection.

If step 9 fails, all explicit Memory effects roll back.

### Background Formation

1. Claim only a released event with positive family-specific
   `BACKGROUND_ELIGIBLE`.
2. Revalidate owner, source retention, deletion epoch, lease/fence, message,
   and suppression generation.
3. Load governed transcript range only.
4. Reject secrets/prohibited content before extraction model.
5. Extract closed-schema candidates.
6. Validate registry/sensitivity/scope/retention.
7. Persist immutable evidence/candidate state as allowed.
8. Consolidate against current assertion state.
9. Apply lifecycle + family activation policy.
10. Shadow rollout records quality evidence without active versions.
11. Active inferred versions require a separately approved evaluation gate.
12. `BackgroundMemoryCommit` binds the tenant, validates the conversation fence
    then worker lease fence, and commits semantic effect plus source-event
    completion with stable idempotency.

### Read and Use

Eligibility is one governed predicate. Conceptually:

```text
lifecycle_status == ACTIVE
AND temporal_valid(expires_at)
AND source_valid(retention_mode, provenance)
AND suppression_generation_is_current
AND sensitivity/scope/type/conflict policy passes
```

The ordered read pipeline applies that predicate before ranking:

```text
owner/tenant
-> lifecycle eligibility
-> sensitivity
-> source/retention validity
-> suppression generation
-> scope
-> family/type relevance
-> temporal validity
-> conflict exclusion
-> ranking/budget
-> selection or abstention
```

`ACTIVE` is necessary but not sufficient. Active state identifies the current
version, not automatic readability or selection.

Memory context is structured, for example:

```json
{
  "preferences": [
    {
      "key": "travel.preference.hotel_atmosphere",
      "value": "quiet",
      "scope": "user",
      "influence": "soft_preference"
    }
  ]
}
```

Memory is not a citation and does not override system/developer policy or the
current user's explicit request.

Every committed semantic Memory effect emits the same governed downstream
`memory_outbox` record through `MemoryWriteStore`, regardless of whether the
producer is the explicit API path or background worker path. That outbox is an
integration/projection boundary, not canonical Memory state. The current
repository has a producer but no runtime consumer; before write volume is
enabled broadly, an approved consumer, bounded retention, or cleanup policy must
prevent unbounded pending-row growth. The owning stage is decided by the later
ADR/implementation plan, not assumed here.

## Consolidation and Conflict

Relation vocabulary:

```text
new | duplicate | reinforcement | correction | contradiction |
temporary_exception | stale | unrelated | uncertain
```

Deterministic identity/authority/time/scope/value/generation comparisons run
first. A model may classify only unresolved relation semantics. The resolver
alone emits governed effects such as:

```text
ADD | REINFORCE | SUPERSEDE | ADD_EXCEPTION |
PENDING_CONFLICT | REJECT | NOOP | REVOKE
```

Equal-authority unresolved contradiction becomes `PENDING_CONFLICT` and is
excluded from use.

## Explicit Forget and Suppression

Product-level `forget` is lifecycle, not privacy erasure.

Target contract:

```text
MemoryOperation.REVOKE
VersionStatus.REVOKED
assertion.suppression_generation
```

Example:

```text
generation 1: ACTIVE quiet
-> user forgets
generation 1: REVOKED
suppression_generation = 2

old generation-1 candidate arrives later
-> cannot form/activate/read

user explicitly remembers again
-> generation 2 may become ACTIVE after normal validation
```

Suppression is checked at formation/write, activation, and read.

`memory_deletion_ledger` remains a privacy/retention deletion artifact and is not
repurposed as product-forget history.

## Retention and Conversation Deletion

Deleting a conversation always invalidates evidence sourced from it.

Then retention determines the result:

1. `CONVERSATION_BOUND`: becomes ineligible with the conversation.
2. `SOURCE_BOUND`: re-evaluate activation using remaining valid independent
   evidence; if requirements fail, Memory becomes ineligible.
3. `USER_DURABLE`: value survives, but deleted-source text/evidence becomes
   inaccessible through read, inspect, trace, prompt, or citation.

Conversation/source invalidation is evaluated through provenance and retention,
not by rewriting every affected version's `expires_at`. Conversation deletion
must therefore remain bounded by the conversation/source invalidation mechanism
rather than requiring O(number-of-Memory-rows) expiry updates for correctness.

## Type-Specific Activation

| Type | Explicit input | Inferred input |
| --- | --- | --- |
| Semantic preference/profile, conversation scope | Activate after governed validation | At least two independent agreeing user turns, no unresolved conflict |
| Semantic preference/profile, user scope | Corroborated durable save may activate | At least three independent evidence items across at least two conversations, no unresolved conflict |
| Constraint | Explicit ordinary constraint may activate when unambiguous | Shadow until policy-specific evidence and impact gates pass |
| Relationship | Explicit ordinary relation may activate | Grounded entity resolution + repeated evidence when ambiguous |
| Episode | Explicit grounded event may activate | One grounded event may suffice only when actor/event/time/provenance validate |
| Working state | Deterministic conversation transition | Summary/open-state replacement after source-consistency checks |
| Procedural | Not user-writable | Separate offline evaluation/publication only |

Retries/re-extraction of one source never increase support. Model confidence is
not a truth probability.

## Response-time Precedence

```text
system/developer policy
> current user request
> verified hard constraints
> current conversation working state / temporary override
> user-scoped soft preferences/profile
> episodes/summaries
```

Current request may suppress soft Memory for one response without silently
mutating durable state.

## System Invariants

1. Tenant isolation applies to every tenant user-Memory write, read, inspect,
   inference, and projection path. System-owned procedural publication is a
   separate boundary and cannot weaken that isolation.
2. PostgreSQL is canonical relational state; SQLite/vector index is not truth.
3. Model output alone never authorizes durable mutation or activation.
4. Durable explicit remember/correct/forget requires deterministic intent
   corroboration.
5. Explicit mutation + idempotency + source handling + acknowledgement + terminal
   effect commits atomically.
6. A `SourceHandlingProposal` is non-authoritative; missing persisted
   `SourceHandlingRecord` is `UNHANDLED`, never background permission, and only a
   persisted `BACKGROUND_ELIGIBLE` record grants background formation.
7. Evidence/committed decisions are append-auditable, not silently rewritten.
8. One source cannot count as multiple independent evidence items.
9. Authority, scope, retention, sensitivity, lifecycle, and response precedence
   remain independent dimensions.
10. Product forget uses revoke/suppression, not privacy-deletion history.
11. Stale generations cannot form, activate, or read after forget.
12. `ACTIVE` does not imply readable/selected.
13. Current user intent may override soft Memory without rewriting it.
14. Raw evidence/untrusted instructions do not enter model context by default.
15. Traces/logs are content-safe by default.
16. Inferred Memory stays shadow until evaluation is conclusive and passes.
17. Tenant user-Memory runtime paths processing shared/real user data use
    non-superuser, non-`BYPASSRLS` roles; privileged-role escape is limited to an
    explicitly declared local-disposable environment with no real user data.
18. `retention_mode` is persisted at write time; optional `expires_at` and
    source validity remain separate eligibility inputs.
19. Explicit and background commits share tenant/conversation fencing and the
    lock order `conversation -> outbox (worker only) -> memory`; lifecycle policy
    does not branch on execution mode.
20. Model-assisted explicit parsing cannot create a key/value/scope outside the
    registry and fails closed on timeout/invalid output.
21. `MessageStatus` and `TurnDisposition` remain distinct constrained contracts;
    aggregate `TurnOutcome` carries the disposition without turning it into
    storage status.

## Failure and Recovery

The architecture fails closed at authority/lifecycle boundaries and degrades
gracefully at optional-context boundaries:

| Failure class | Required behavior |
| --- | --- |
| Authentication/owner mismatch | Content-free not-found/unauthorized; no model or Memory access |
| Turn/outbox allocation failure | Roll back turn; no generation |
| Understanding invalid/timeout | Safe normal-query or clarification fallback; never infer durable explicit authority |
| Explicit gate/payload/policy failure | No mutation; clarify only when useful |
| Failure inside explicit commit | Roll back Memory, acknowledgement, source handling, and terminal effect together |
| Explicit turn transition already won by another writer | Do not claim/store the losing acknowledgement or Memory effect; return/recover through the existing guarded transition semantics |
| Retry | Replay the same semantic result; never duplicate Memory |
| Missing positive source handling / deleted source / lost fence | No background semantic commit |
| Forget racing delayed work | Suppression generation wins |
| Unresolved contradiction | Pending conflict and abstention for that identity |
| Memory read unavailable | Continue without Memory when safe |
| Required RAG unavailable | Report limitation/incomplete result rather than fabricate grounding |
| Required evaluation unavailable | `INCONCLUSIVE`, never `PASS` |

## Security and Privacy

1. Owner identity comes from authenticated principal, never request payload.
2. Application checks and PostgreSQL RLS both enforce owner scope.
3. API and worker retain isolated least-privilege database roles. Any runtime
   that holds shared/real user data refuses privileged execution; an explicit
   environment class gates the local-disposable exception at startup.
4. Prohibited secrets are rejected before Memory-model exposure/persistence.
5. Sensitivity may escalate but never downgrade deterministic/registry floor.
6. Retrieved Memory is untrusted data, not instructions.
7. Procedural Memory has separate system-owned publication authority and does
   not reuse tenant `MemoryScope` or weaken tenant RLS.
8. Inspect exposes governed Memory state, not unrestricted raw evidence.
9. Deleted-source content cannot reappear through read, prompt, inspect, trace,
   summaries, projections, or citations.
10. Product forget and privacy erasure remain distinct operations.
11. `TraceVisibility` governs whether persisted messages may become evaluation
    trace input. Operational-log safety is a separate redaction/closed-field
    boundary; neither substitutes for the other.

## Observability and Capacity

Tracing and metrics are content-safe by default. Record IDs, reason codes,
latency, model/prompt-schema version, token/cost metadata, lifecycle outcomes,
read abstention/selection, worker retry/fence state, and rollback/replay counts.
Do not log raw messages, Memory values, evidence, or secrets by default.

Governed evaluation/trace records may additionally carry closed non-content
fields such as `interaction_mode` and `TurnDisposition` when needed to compute
intent/clarification metrics. This does not imply that every operational log
event carries those fields; operational logging remains subject to its own
closed-field/redaction contract.

Initial scale target is approximately 1,000 registered users, not 1,000
simultaneous model calls. Measure actual concurrency/queue behavior.

A distributed queue is introduced only after measured PostgreSQL-outbox limits
justify it.

## Testing and Evaluation

Evaluation is split by responsibility rather than one aggregate "Memory
accuracy" number:

| Layer | Required evidence |
| --- | --- |
| Understanding/action | Intent precision/recall, durable-action false-positive rate, clarification correctness |
| Formation | Extraction/normalization precision/recall, secret/sensitivity blocking |
| Consolidation/lifecycle | Conflict correctness, revoke/suppression, temporal update, source deletion |
| Read/use | Retrieval precision/recall, correct abstention, precedence, over-personalization, prompt-injection resistance |
| Runtime | RLS isolation, idempotency, transaction rollback, worker fence/lease, latency, cost |

The end-to-end suite must at minimum prove cross-conversation remember/use,
unrelated-query abstention, conversation override, correction, forget with no
resurrection, re-remember as a new generation, source-deletion retention,
shadow-before-promotion, worker retry idempotency, explicit commit rollback, and
procedural non-writability from ordinary Chat.

Runtime verification also proves:

- the caller-owned explicit transaction preserves the existing guarded terminal
  turn transition and cannot commit a losing acknowledgement/Memory effect;
- both commit owners use the same tenant/conversation fence and canonical lock
  order, while only the worker requires the outbox lease fence;
- time expiry and source/retention invalidation fail independently;
- privileged roles are rejected in declared shared environments;
- `TurnDisposition` does not alter the `MessageStatus` storage contract; and
- downstream `memory_outbox` growth is bounded by its approved consumer or
  retention/cleanup policy before broad enablement.

Required PostgreSQL scenarios do not count as passed when skipped.

Zero-tolerance failures:

1. cross-owner mutation/selection;
2. prohibited-secret Memory-model exposure;
3. classifier-only durable mutation;
4. background extraction without positive source handling;
5. post-forget resurrection;
6. unresolved-conflict use;
7. non-atomic explicit mutation/acknowledgement;
8. non-idempotent semantic duplication;
9. deleted-source leakage.
10. privileged-role execution against shared/real user data.
11. registry-invalid model output becoming durable explicit Memory.

Missing required evidence => `INCONCLUSIVE`, never `PASS`.

## Staged Migration

The authenticated PostgreSQL Chat baseline, turn-readiness outbox barrier,
separate worker runtime, RLS/credential isolation, and removed public Memory
surface are prerequisites, not future stages. Before these stages become release
gates, CI must import the repository correctly and required PostgreSQL
integration jobs must receive an explicit disposable test DSN; a skipped or
uncollectable integration suite is not verification. Shared-environment startup
must also have an explicit environment classification so privileged-role
rejection is enforceable rather than conventional.

### Stage 1 — Turn Understanding and Source Handling

Add DialogueStateResolver, TurnUnderstanding, `TurnDisposition`, ActionRouter,
ContextPlanner contract, ExplicitIntentGate, and family-specific
`SourceHandlingProposal` plus the pure record/gate contract. Stage 1 does not
persist source handling and does not obtain `source_outbox_id`; proposals remain
non-authoritative. Stage 1 DialogueState uses recent turns only and remains a
deterministic structural context contract; TurnUnderstanding owns semantic
topic/referent/goal/clarification interpretation. The planner exposes the final
source-mode vocabulary but only `none|rag_only` are reachable until Memory Read
exists. Harden operational redaction/trace boundaries before new Memory traces
are enabled. Evaluate semantics before enabling new durable explicit behavior.
`explicit_inspect` may be recognized here but remains an internal unavailable
capability until Stage 3.

### Stage 2 — Explicit Semantic Write/Store Lifecycle

Add persisted retention modes, optional temporal expiry, `REVOKE`/`REVOKED`,
suppression generation, persisted family-specific `SourceHandlingRecord`,
binding of actual `(source_outbox_id, family)` identity at the storage/transaction
seam, `MemoryLifecyclePolicy`, Chat-native mutating semantic actions,
transaction-aware
Conversation/Memory write seams, shared tenant/conversation fence primitives,
`ExplicitMemoryTurnCommit`, and `BackgroundMemoryCommit`. Prove canonical lock
ordering, guarded turn completion, remember/correct/forget/re-remember,
write-time/source/suppression eligibility, deletion, idempotency, and failure
atomicity. `explicit_inspect` is still not delivered in this stage.

### Stage 3 — Semantic Read and Use

Extend the Stage-2 `MemoryLifecyclePolicy` across read eligibility, add the exact
structured `MemoryReadEngine`, and deliver Chat-native `explicit_inspect` through
that governed read path. Expand the existing ContextPlanner so
`memory_only|both` become reachable, add ContextArbiter and
MemoryContextComposer, and prove the full explicit semantic vertical slice
before inferred activation.

### Stage 4 — Background Semantic Formation/Activation

Use the existing worker with positive source handling, stable semantic
idempotency, source validity, suppression checks, and shadow-first rollout.
Active inference requires a separately approved conclusive evaluation gate.

### Stage 5 — Episodic and Working Memory

Add one evaluated vertical slice at a time, including formation, retention,
consolidation, read/use, deletion, failure, and evaluation. Once Working Memory
exists and passes its gate, eligible Working Memory becomes an additional input
to `DialogueStateResolver`; recent turns remain the immediate structural
dialogue source and `TurnUnderstanding` remains the semantic interpreter.

### Stage 6 — Secondary Retrieval Projections

Add PostgreSQL full-text/pgvector only where exact structured lookup is
insufficient. Projections remain downstream of owner/lifecycle/sensitivity
filters and are rebuildable.

### Stage 7 — Procedural Publication

Add separate offline evaluation-approved system versioned configuration/policy
publication. It is a Memory family at the AI-architecture level, not a tenant
`MemoryScope`; ordinary Chat cannot write it and tenant RLS is not weakened to
store it.

## Rollout and Rollback

Independent rollout gates:

1. Turn Understanding/ActionRouter shadow observation;
2. explicit Chat Memory;
3. Memory Read;
4. Memory prompt use;
5. background capture;
6. per-type inferred activation;
7. episode/summary/vector projections;
8. procedural publication.

Rollback rules:

- disable use before read;
- disable inferred activation while preserving safe shadow evidence;
- stop new worker claims while preserving reclaimable work;
- disable explicit actions without restoring the removed Memory Manager/API;
- never clear revoke/suppression state as rollback;
- never reactivate revoked/superseded versions;
- never reintroduce SQLite as source of truth.

## Required ADRs

Existing accepted constraints include ADR 0012, 0013, 0014, 0020, 0023, 0027,
0029, and the accepted worker lease/fence/credential decisions.

The target architecture requires ADRs for:

1. Chat-native Memory actions + deterministic explicit-intent authority + atomic
   `ExplicitMemoryTurnCommit`, `BackgroundMemoryCommit`, transaction-aware
   Conversation/Memory store seams, shared fencing, and canonical lock order.
2. Retention + `REVOKE`/`REVOKED` + suppression generation + re-remember.
3. Positive family-specific source handling + inferred activation authority.
4. Memory Read/Use authority + ContextPlanner/Arbiter + projection boundary.
5. System-owned procedural Memory publication outside tenant Memory scope/RLS.

ADR 0017 remains historical risk input; ADR 0020 superseded its public control
surface. The metadata chain across ADR 0015/0017/0020 should be reconciled as a
documentation defect while drafting the replacement ADRs; that cleanup does not
change the target semantics defined here.

## Acceptance Criteria

Implementation planning may start only after repository-owner approval of this
exact version and acceptance of the required ADRs.

The target architecture must preserve these outcomes:

1. authenticated PostgreSQL-only standalone Chat remains the baseline;
2. Workspace/SQLite/separate Memory Manager are not reintroduced;
3. `DialogueStateResolver` is a deterministic one-conversation structural
   context assembler, while Turn Understanding is the typed, non-authoritative
   owner of semantic topic/referent/goal/clarification interpretation;
4. durable explicit mutations require deterministic speech-act corroboration;
5. explicit Memory mutation + ack + source handling + idempotency commit atomically;
6. authority/scope/retention/sensitivity/lifecycle/response precedence remain
   distinct;
7. forget prevents stale resurrection at formation, activation, and read;
8. background extraction requires a persisted positive family-specific
   `BACKGROUND_ELIGIBLE` record; a proposal or missing record is insufficient;
9. only lifecycle-eligible relevant active Memory enters controlled context;
10. explicit semantic end-to-end behavior passes before inferred activation;
11. each additional Memory family arrives as an evaluated vertical slice;
12. required PostgreSQL integration verification runs without required skips;
13. zero-tolerance gates pass and missing required evidence is `INCONCLUSIVE`;
14. migration/recovery/deletion operations are documented before production enablement.
15. explicit commit preserves the guarded conversation terminal transition and
    background/explicit paths follow one canonical lock order;
16. procedural Memory is system-owned publication state, not a tenant scope;
17. persisted retention, temporal expiry, and source validity cannot silently
    reinterpret one another;
18. shared-environment runtime cannot bypass tenant isolation with a privileged
    database role;
19. `TurnDisposition` is evaluated as a distinct reasoning dimension whose
    finalized values obey the valid-combination constraints with persisted
    `MessageStatus`, and remains internal to `TurnOutcome` in the first rollout;
20. downstream `memory_outbox` has an approved bounded lifecycle before broad
    Memory-write enablement.

## Relationship to the 2026-09-10 Proposal

The 2026-09-10 Unified Multi-Conversation Agent Memory Architecture is frozen as
a historical proposal and is superseded by this approved v0.2. It must not be
used in parallel as implementation authority.

The approval transition is:

1. the 2026-09-10 proposal is marked `Superseded` and points here;
2. the spec index identifies this document as the approved canonical target;
3. required ADRs are drafted and reviewed against this architecture;
4. all required ADRs must be `Accepted` before staged implementation plans are
   written; and
5. implementation still requires approval of the exact implementation plan.

Architecture approval alone does not authorize implementation of this target.

## Approval Record

Version 0.2 was **Approved on 2026-09-12 by the repository owner**.

Version 0.3 was **Approved on 2026-09-13 by the repository owner**. It narrows
the responsibility boundary discovered during Task-3 review:
`DialogueStateResolver` owns deterministic structural context assembly and
conversation isolation; `TurnUnderstanding` owns semantic
topic/referent/goal/clarification interpretation. Version 0.3 supersedes v0.2 as
the prior approved architecture record for this program.

Version 0.4 was **Approved on 2026-09-13 by the repository owner**. It clarifies
the Task-5/Stage-2 authority boundary without changing ADR 0038: orchestration
produces a typed, non-authoritative `SourceHandlingProposal`; the persisted
`SourceHandlingRecord` is the authority object; absence is `UNHANDLED`; only a
persisted `BACKGROUND_ELIGIBLE` record grants background formation; and actual
`source_outbox_id` binding stays at the later storage/transaction seam. Version
0.4 supersedes v0.3 as the current approved architecture record.

## References

1. [Authenticated Chat-Only PostgreSQL Clean Break](./2026-09-10-authenticated-chat-postgresql-clean-break-design.md).
2. [Atomic Chat Turn and Memory Write Pipeline Correctness](./2026-09-11-atomic-chat-turn-and-memory-correctness-design.md).
3. [Memory Worker Runtime](./2026-09-12-memory-worker-runtime-design.md).
4. [AI Memory Core Engineering Design](./2026-09-09-ai-memory-core-engineering-design.md).
5. [ADR 0020: Removal of Public Memory Management Surface](../adr/0020-removal-of-public-memory-management-surface.md).
6. [ADR 0027: Outbox Event Released Only When Turn Terminal](../adr/0027-outbox-event-released-only-when-turn-terminal.md).
7. [ADR 0029: The Memory Worker Runs as Its Own Service](../adr/0029-the-memory-worker-runs-as-its-own-service.md).
8. LangMem, “Long-term Memory in LLM Applications”: <https://langchain-ai.github.io/langmem/concepts/conceptual_guide/>.
9. Packer et al., “MemGPT: Towards LLMs as Operating Systems”: <https://arxiv.org/abs/2310.08560>.
10. Chhikara et al., “Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory”: <https://arxiv.org/abs/2504.19413>.
