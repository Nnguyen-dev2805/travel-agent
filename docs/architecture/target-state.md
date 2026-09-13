# Target-state Architecture

## Status and Authority

This document summarizes the **approved future architecture** for Travel Agent.
It does not describe implemented behavior and does not by itself prove that a
stage is complete.

The canonical authority chain is:

1. [Agent Memory Target Architecture](../specs/2026-09-12-agent-memory-target-architecture-design.md) v0.2 — Approved.
2. ADRs [0036](../adr/0036-chat-native-memory-actions-and-transaction-coordinators.md), [0037](../adr/0037-memory-retention-revocation-and-suppression.md), [0038](../adr/0038-positive-source-handling-and-inferred-activation-authority.md), [0039](../adr/0039-memory-read-use-authority-and-retrieval-projections.md), and [0040](../adr/0040-system-owned-procedural-memory-publication-boundary.md) — Accepted.
3. [Agent Memory Target Architecture Implementation Plan](../plans/2026-09-12-agent-memory-target-architecture-implementation.md) v0.5 — Approved 2026-09-13.

Use [Current-state Architecture](current-state.md) for behavior that exists now
and [Data Model](data-model.md) for cross-domain target entities and lifecycle
relationships.

## Baseline That Must Remain True

The target starts from authenticated standalone Chat backed by PostgreSQL. It
must not reintroduce Workspace as a product container, Planner as a mounted
runtime surface, SQLite as canonical relational state, or the removed public
Memory Manager/API.

PostgreSQL remains canonical for tenant conversation and Memory state. Chroma
remains travel-knowledge retrieval infrastructure. Any future Memory full-text
or vector index is a rebuildable projection, never lifecycle authority.

## Target Principles

1. Keep synchronous agent behavior bounded to one turn and one context/tool
   phase rather than an unbounded autonomous loop.
2. Let models interpret uncertain semantics, but keep authorization, lifecycle,
   persistence, deletion/suppression, activation, and read eligibility under
   deterministic application policy.
3. Keep Memory and RAG as separate domains. RAG supplies travel knowledge;
   Memory supplies governed personal/context state.
4. Treat explicit user Memory actions differently from background inference.
5. Make product forget a first-class lifecycle operation with suppression, not
   a synonym for privacy erasure.
6. Persist provenance/retention/lifecycle facts instead of reconstructing them
   from current policy at read time.
7. Fail closed at authority and lifecycle boundaries; degrade without Memory
   when Memory is optional and unavailable.
8. Introduce additional Memory families only as evaluated vertical slices.

## Product Boundary

The product container is authenticated standalone Chat. A user owns multiple
independent conversations through `owner_user_id`; there is no active
`TripWorkspace` parent.

One user turn may be:

- a normal query;
- an explicit Memory action (`remember`, `correct`, `forget`, `inspect`); or
- evidence that may later be processed asynchronously for inferred Memory.

Conversation-scoped state may override a user-scoped default for the current
conversation without rewriting the user-scoped value.

## Bounded Agentic Turn

The target synchronous flow is:

```text
request + authenticated principal
-> resolve ephemeral dialogue state
-> understand the turn
-> choose action and context plan
-> enforce deterministic policy
-> execute one read/tool phase
   -> Memory Read when requested
   -> RAG when requested
-> arbitrate structured context
-> generate/acknowledge
-> commit the terminal turn
```

`DialogueStateResolver` reconstructs short-lived referents, topic, current goal,
and pending clarification. `TurnUnderstanding` returns typed but
non-authoritative semantics. `ActionRouter` chooses normal query, explicit
Memory action, or clarification. `ContextPlanner` selects `none`, `rag_only`,
`memory_only`, or `both` as stages make those modes available.

`TurnDisposition` describes the reasoning outcome (`ANSWERED`,
`NEEDS_CLARIFICATION`, `INCOMPLETE`, `EXECUTION_FAILED`) and remains distinct
from persisted `MessageStatus`. It stays internal to `TurnOutcome` in the first
rollout.

## Target Module Boundaries

| Component | Owns | Must not own |
| --- | --- | --- |
| Chat application/orchestration | One bounded synchronous turn, routing, context planning, generation, terminal result | Background Memory lifecycle |
| Conversation store | Conversation/message persistence, deletion epoch, outbox allocation/release, guarded terminal transition | Memory semantics |
| DialogueStateResolver | Ephemeral current-turn referents/topic/goal | Durable Memory |
| TurnUnderstanding | Typed semantic interpretation | Durable mutation authority |
| ExplicitIntentGate | High-precision corroboration of remember/correct/forget speech acts | Key/value parsing or persistence |
| ExplicitMemoryActionHandler | Registry, scope, retention, sensitivity, conflict validation and typed proposal | Transaction ownership |
| ExplicitMemoryTurnCommit | Atomic API-side explicit Memory effect + acknowledgement + source handling + guarded terminal transition | Semantic interpretation |
| BackgroundMemoryCommit | Fenced worker-side background Memory effect + source-event completion | Explicit Chat authority |
| MemoryFormationEngine | Background evidence/candidate formation | Direct activation |
| MemoryConsolidationEngine | Duplicate/reinforce/correction/conflict resolution | Storage transaction ownership |
| MemoryLifecyclePolicy | Shared formation/write/activation/read eligibility predicates | Relevance ranking |
| MemoryReadEngine | Eligible/relevant Memory selection | RAG retrieval |
| ContextArbiter / MemoryContextComposer | Precedence, bounded Memory context, prompt-safe structured projection | Canonical Memory storage |
| RAG domain | Travel-document retrieval and citation evidence | Personal Memory authority |
| Procedural publication | Offline evaluated, versioned system behavior | Tenant/user writable Memory |

## Memory Families

| Family | Ownership | Typical scope | Rollout rule |
| --- | --- | --- | --- |
| Semantic | Tenant/user-derived | user or conversation | First complete explicit vertical slice |
| Episodic | Tenant/user-derived | conversation; governed user generalization | Later evaluated slice |
| Working | Tenant/user-derived | conversation | Later evaluated slice; may feed dialogue-state reconstruction after its gate |
| Procedural | System-owned | separate publication boundary | Offline evaluation and repository-owner approved publication only |

Procedural Memory is not represented with a fake tenant owner and does not
weaken tenant RLS.

## Independent Memory Dimensions

Every user-derived Memory decision keeps these dimensions separate:

- **Authority:** `EXPLICIT_SAVE`, `EXPLICIT_STATEMENT`, `REPEATED_INFERENCE`.
- **Scope:** `conversation` or `user`.
- **Retention:** `CONVERSATION_BOUND`, `SOURCE_BOUND`, `USER_DURABLE`.
- **Sensitivity:** deterministic registry/policy floor that a model may only
  raise, never lower.
- **Lifecycle:** at least `SHADOW/PENDING`, `ACTIVE`, `SUPERSEDED`, `REVOKED`,
  `REJECTED`, and effective `EXPIRED`.
- **Response precedence:** current request and verified hard constraints outrank
  soft durable personalization.

`ACTIVE` is necessary but not sufficient for answer-time use.

## Explicit Memory Write Path

Explicit `remember`, `correct`, and `forget` require deterministic speech-act
corroboration before any model-assisted payload parsing. Parsing is bounded,
closed-schema, registry-validated, and fail-closed.

The API-side commit owner atomically persists the Memory effect together with:

1. semantic idempotency result;
2. family-specific `SourceHandlingRecord`;
3. deterministic acknowledgement; and
4. guarded terminal turn/outbox transition.

The model never chooses SQL, persistence operation, retention, activation, or
suppression behavior.

## Background Inference Path

Background formation is asynchronous through the existing worker/outbox model.
Absence of a source-handling record means `UNHANDLED`, never permission.
Formation for a family requires a positive family-specific
`BACKGROUND_ELIGIBLE` outcome.

Inferred Memory is shadow-first. Activation thresholds depend on family/type and
require independent evidence; retries or repeated extraction of one source do
not increase support. Missing or inconclusive evaluation keeps inferred Memory
non-answer-eligible.

## Consolidation, Forget, and Re-remember

The consolidation vocabulary includes new, duplicate, reinforcement,
correction, contradiction, temporary exception, stale, unrelated, and uncertain.
Deterministic identity/authority/time/scope/value/generation comparisons run
before any bounded semantic classifier.

Governed effects include `ADD`, `REINFORCE`, `SUPERSEDE`, `ADD_EXCEPTION`,
`PENDING_CONFLICT`, `REJECT`, `NOOP`, and `REVOKE`.

Product forget uses `REVOKE`/`REVOKED` and advances an assertion suppression
generation. Delayed work from an older generation cannot form, activate, or
read. A later explicit re-remember creates state in the current generation; it
does not reactivate the revoked version.

## Read and Use Boundary

Memory Read applies, in order:

```text
owner/scope filter
-> lifecycle + retention + source-validity + suppression eligibility
-> relevance
-> precedence/conflict exclusion
-> bounded ranking/selection
```

Memory is projected into generation as structured, prompt-safe data. Raw source
evidence is excluded by default. Memory is not a citation channel and retrieved
Memory text is never treated as instructions.

RAG and Memory may execute in parallel as independent read-only context sources.
Orchestration projects both into a neutral generation input; neither domain
imports the other's canonical records.

## Conversation Deletion and Source Validity

Conversation deletion always invalidates evidence sourced from that
conversation. Resulting Memory eligibility depends on persisted retention:

- `CONVERSATION_BOUND`: becomes ineligible with the conversation;
- `SOURCE_BOUND`: re-evaluate support from remaining valid independent evidence;
- `USER_DURABLE`: normalized value may survive, but deleted-source content must
  not reappear through read, inspect, prompt, trace, summary, projection, or
  citation.

Time expiry, source validity, retention, and suppression remain independent.

## Staged Delivery

| Stage | Target |
| --- | --- |
| 1 | Turn understanding, dialogue state, routing, context-planner contract, explicit intent gate, positive source handling, telemetry hardening |
| 2 | Explicit Semantic Memory write/store lifecycle, retention, revoke/suppression, dual commit coordinators, eight-key registry v2 |
| 3 | Semantic Memory Read/Use, explicit inspect, context arbitration |
| 4 | Background semantic formation and per-type inferred activation after conclusive gates |
| 5 | Evaluated Episodic and Working Memory slices |
| 6 | Optional full-text/vector projection only when structured retrieval is insufficient |
| 7 | System-owned procedural publication |

The approved execution source is plan v0.5; this document intentionally does not
repeat task-level file lists or verification commands.

## Rollout and Rollback

Capabilities enable independently: understanding shadow observation, explicit
Memory, read, prompt use, background capture, inferred activation, additional
families/projections, then procedural publication.

Rollback disables higher-authority consumers before lower layers. It never
clears revoke/suppression history, reactivates superseded/revoked versions,
restores SQLite as truth, or restores the removed public Memory Manager/API.

## Explicitly Removed from the Target

The following are historical architecture, not future product direction:

- `TripWorkspace` as the primary product container;
- Workspace-scoped Planner routes/state;
- SQLite application persistence;
- a separate public Memory management surface;
- unbounded autonomous planning loops;
- vector search as canonical Memory truth.
