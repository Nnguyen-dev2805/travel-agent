# Unified Multi-Conversation Agent Memory Architecture

| Field | Value |
| --- | --- |
| Status | Superseded |
| Version | 0.3 Draft |
| Date | 2026-09-12 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Chat-first, PostgreSQL-backed, multi-conversation agent Memory with typed turn understanding, explicit chat commands, background formation, consolidation, activation, read, use, and evaluation |
| Related issue | Repository-owner approved exception: interactive architecture redesign on 2026-09-10 |
| Superseded document | Superseded by [Agent Memory Target Architecture](./2026-09-12-agent-memory-target-architecture-design.md) v0.2 (Approved 2026-09-12) |

> **Superseded on 2026-09-12.** Architecture authority moved to
> [Agent Memory Target Architecture](./2026-09-12-agent-memory-target-architecture-design.md),
> version 0.2 (Approved). This file is retained only as historical proposal
> context and must not be used as implementation authority.

## Summary

This specification defines the target chat-first Memory architecture that grows
from the current PostgreSQL conversation and background-write foundation.
Users interact through normal conversations. The same chat surface supports
normal tasks and explicit remember, correct, forget, and inspect actions.
Background workers form inferred memories without blocking chat.

The architecture supports multiple conversations and four governed Memory
families: semantic, episodic, working, and procedural. The families share an
auditable evidence-to-decision lifecycle but do not share one activation or
retrieval policy. PostgreSQL is the only relational source of truth for the
mounted Chat and Memory runtime. Vector indexes are rebuildable projections,
never lifecycle authority.

Implementation is staged by complete vertical behavior, not by creating all
tables or extractors first. Each stage must demonstrate write, storage, read,
use, failure behavior, and evaluation for its governed family before the next
family enters the mounted runtime. Durable explicit mutation, background
formation, activation, and read share lifecycle rules, but none may infer
authorization from model output or from the absence of an audit record.

## Context

The repository has already completed the PostgreSQL chat clean break and removed
the former public Memory Manager/API surface. The mounted API now composes
standalone owner-scoped conversations through `PostgresConversationRepository`.
The chat orchestrator can atomically capture extraction work in the conversation
outbox, and a separately deployed worker runtime can process released events.

The remaining gap is architectural rather than merely wiring. The current
write domain still represents the first semantic slice, has no product-level
`REVOKE` lifecycle, has no retention contract independent of provenance
authority, and is not composed into a synchronous explicit-Memory Chat action
or a governed Memory Read/Use path. Consequently the repository still cannot
demonstrate the complete target behavior `chat -> understand -> write/form ->
consolidate -> activate -> recall -> use` across multiple Memory families.

Modern agent-memory systems commonly distinguish thread-scoped state from
cross-thread long-term storage, semantic/episodic/procedural families, and
hot-path from background formation. This specification applies those concepts
with application-specific authority and evaluation rather than adopting a
framework's storage model verbatim.

## Current-State Evidence

| Evidence | Verified behavior | Architectural consequence |
| --- | --- | --- |
| `backend/app/main.py:259-262` | Mounted product exposes only health, operations, Chat, and conversation routers; the former public Memory management routers are absent | Explicit Memory must return through the normal Chat flow, not by restoring the removed Memory Manager/API |
| `backend/app/runtime_container.py` | `RuntimeContainer` owns one PostgreSQL engine and constructs `PostgresConversationRepository` for mounted conversations | PostgreSQL is already the conversation source of truth and can host later cross-domain transaction seams |
| `backend/orchestration/conversation_orchestrator.py` | Chat creates a Memory extraction outbox intent only when shadow extraction is enabled | Background formation remains independently gated and does not block Chat |
| `backend/conversations/postgres_repository.py` | Turn completion/failure releases or cancels the associated outbox work; conversation deletion carries a deletion epoch fence | Source validity and turn readiness are existing correctness primitives to preserve |
| `backend/memory/write_pipeline/models.py` | `MemoryOperation` has `ADD`, `REINFORCE`, `SUPERSEDE`, `ADD_EXCEPTION`, `PENDING_CONFLICT`, `REJECT`, `NOOP`; `VersionStatus` has only `ACTIVE` and `SUPERSEDED` | Product-level forget/revocation and suppression generation are not yet represented |
| `backend/memory/write_pipeline/postgres.py` | `PostgresMemoryUnitOfWork` commits Memory changes atomically inside its own transaction and exposes active-version reads | Existing UoW is reusable, but explicit Memory acknowledgement needs a higher application transaction seam spanning conversation and Memory state |
| `backend/memory/write_pipeline/registry.py` | The governed semantic registry still begins with `travel.preference.hotel_atmosphere` and four normalized values | The first slice proves the contract shape; target generality requires registry expansion by evaluated vertical slices rather than free-form keys |
| ADR 0020 | Public Memory Manager/API and command parser were intentionally removed; a future approved Chat command design is explicitly allowed | This design may add Chat-native explicit actions without reintroducing the removed public management surface |
| ADR 0027 and current outbox implementation | An unreleased outbox event is not claimable | Missing source-handling state can safely fail closed instead of being inferred as permission |

## Users and Actors

1. An authenticated user who owns multiple conversations.
2. The synchronous Chat application handling one user turn.
3. A background Memory worker processing durable outbox work.
4. An operator running migrations, workers, evaluation, recovery, and rollout.
5. A governed procedural-memory publisher; normal users cannot assume this role.

## Problem Statement

The system needs one coherent answer to these questions:

1. What does the current turn mean?
2. Is it a normal task or an explicit Memory action?
3. What information is worth proposing as Memory?
4. Which actor or policy may activate, change, or delete it?
5. Which Memory is eligible and relevant for a later turn?
6. How may it influence the agent without becoming an instruction injection?
7. How are conflicts, time, retries, deletion, and model errors handled?
8. How is improvement demonstrated per Memory family and end to end?

A single LLM call or a generic `memories` table cannot safely own all eight
answers. The architecture needs explicit, typed authority seams.

## Goals

1. Let an authenticated user create and continue multiple standalone
   conversations without a workspace.
2. Use PostgreSQL as the only relational source of truth for mounted Chat and
   Memory behavior.
3. Interpret each user turn once into typed, non-authoritative semantics shared
   by explicit control, read planning, and response generation.
4. Support explicit remember, correct, forget, and inspect actions in the main
   Chat surface; no separate Memory Manager is required.
5. Form inferred Memory asynchronously from durable message/outbox events.
6. Support semantic, episodic, working, and system-owned procedural Memory with
   type-specific formation, activation, retrieval, and use policies.
7. Support user and conversation scopes with deterministic precedence.
8. Preserve immutable evidence, decisions, versions, provenance, ownership,
   sensitivity, and temporal validity.
9. Keep model output outside authorization, lifecycle, SQL, and transaction
   authority.
10. Demonstrate quality, abstention, privacy, conflict handling, retry safety,
    latency, and cost through executable evaluation.
11. Separate provenance authority from retention dependency so deleting a source
    does not accidentally erase a deliberately durable save, and a plain user
    statement does not accidentally become permanent account state.
12. Give explicit forget a first-class lifecycle with suppression semantics that
    prevents old evidence, shadow candidates, and delayed workers from
    resurrecting forgotten Memory.
13. Make successful explicit mutation and its user-visible acknowledgement one
    idempotent application commit boundary.

## Non-Goals

1. Workspace or Planner behavior in the mounted chat-first product.
2. A separate Memory management drawer in the first release of this design.
3. Letting user messages directly mutate procedural Memory.
4. Treating raw chat transcripts, vector hits, model confidence, or summaries
   as ground truth.
5. Kafka, RabbitMQ, Redis Streams, or another distributed queue before measured
   PostgreSQL-outbox saturation.
6. Multi-region consistency or active-active deployment.
7. A graph database as canonical storage.
8. Reintroducing SQLite runtime/storage or a legacy Memory import path.

## Alternatives Considered

### Alternative A: Expand the Current One-Key Pipeline in Place

Add more keys and conditionals directly to the current background recorder,
worker, resolver, and first semantic registry without introducing the explicit
Chat, retention, lifecycle, and Read/Use boundaries in this design. This reuses
code quickly but makes each new family depend on one semantic policy shape and
leaves durable user intent, source handling, forget suppression, and read/use
authority implicit. Rejected because every new type would multiply those hidden
contracts rather than prove a reusable architecture.

### Alternative B: One Memory LLM Owns Understanding and Mutation

Call one model on every turn and allow it to classify intent, extract Memory,
choose updates, retrieve context, and invoke persistence tools. This is flexible
but gives probabilistic output too much authority, raises hot-path latency, and
makes failures difficult to attribute or evaluate. Rejected.

### Alternative C: Typed Turn Understanding and a Unified Lifecycle

Use a rule-first, model-assisted Turn Understanding module; pure formation,
policy, consolidation, and activation modules; PostgreSQL persistence; a
separate Read module; and controlled context composition. Share lifecycle
contracts while keeping type-specific policy. Selected because it preserves
deterministic authority and gives each behavior one testable seam.

## Memory Taxonomy

| Family | Governed types | Default scope | Formation | Use |
| --- | --- | --- | --- | --- |
| Semantic | `profile_fact`, `preference`, `constraint`, `relationship` | User or conversation | Explicit or background | Personalization, filtering, and planning constraints |
| Episodic | `experience`, `decision`, `completed_action`, `feedback` | Conversation; user only when explicitly generalized | Primarily background, grounded in events | Relevant past events and examples |
| Working | `conversation_summary`, `open_goal`, `current_plan`, `temporary_override`, `unresolved_question` | Conversation only | Deterministic state transitions or background summarization | Maintain continuity under context limits |
| Procedural | `response_policy`, `tool_workflow`, `planning_strategy` | Agent/application | Governed publisher only | Agent behavior and tool strategy |

Semantic Memory is not semantic search. Semantic Memory stores facts and
meaningful assertions. Semantic search is one optional retrieval technique.

Procedural Memory uses a separate publication pipeline with evaluation and
rollback. User chat may provide feedback evidence, but never a directly
executable instruction or procedural version.

## Authority, Scope, Retention, and Source Dependency

`Authority`, `scope`, and retention answer different questions and must not be
derived from one another:

1. **Authority** answers how strong the provenance is. The existing semantic
   vocabulary remains `EXPLICIT_SAVE`, `EXPLICIT_STATEMENT`, and
   `REPEATED_INFERENCE`.
2. **Scope** answers where the Memory may influence behavior: conversation,
   user, or the separately governed agent/procedural namespace.
3. **Retention mode** answers what the Memory's continued existence depends on.

User-derived Memory uses the following retention vocabulary:

```text
CONVERSATION_BOUND
SOURCE_BOUND
USER_DURABLE
```

The mapping is deliberate rather than inferred from `Authority`:

| Origin | Typical scope | Retention mode | Consequence |
| --- | --- | --- | --- |
| Corroborated `remember` / `correct` command | User | `USER_DURABLE` | Survives conversation deletion, while evidence from the deleted conversation is invalidated |
| Plain explicit statement without a durable-save speech act | User or conversation | `SOURCE_BOUND` or `CONVERSATION_BOUND` | Does not gain account-durable retention merely because the statement is explicit |
| Background inferred user Memory | User | `SOURCE_BOUND` | Remains eligible only while enough independent valid evidence survives |
| Conversation-specific state or override | Conversation | `CONVERSATION_BOUND` | Becomes ineligible when that conversation is deleted or expires |

Procedural Memory is not assigned one of these user-retention modes; its
publication and retirement lifecycle is governed separately.

Conversation deletion has two effects that must remain distinct. It always
invalidates evidence sourced from that conversation. It also revokes
`CONVERSATION_BOUND` state. A `SOURCE_BOUND` user Memory is re-evaluated against
its remaining valid evidence and becomes ineligible if its family/type-specific
activation requirements are no longer satisfied. `USER_DURABLE` state survives
conversation deletion, but it may no longer expose or cite evidence from the
deleted conversation.

## Scope and Precedence

Every Memory carries an owner namespace and one governed scope:

1. `conversation`: valid only in one conversation.
2. `user`: reusable across the owner's conversations.
3. `agent`: system-owned procedural state; never selected from user-owned rows.

At response time, authority precedence is:

```text
system/developer policy
> current user request
> verified hard constraints
> current conversation state and overrides
> user-scoped soft preferences/profile
> retrieved episodes and summaries
```

Current-turn information may suppress an older Memory for the response without
immediately superseding the durable version. Durable correction requires the
relevant consolidation and activation policy.

Retention is not response-time precedence. A `USER_DURABLE` preference can
survive for months and still lose to the current user's request for one turn.
Likewise, a high-authority explicit statement can remain `SOURCE_BOUND` if the
user never asked the system to retain it beyond its source.

## Precedence Resolution

The precedence chain in the previous section is a starting point, not a
sufficient algorithm. When two Memory items conflict, resolution must be
performed **per assertion** across six dimensions:

1. **Authority** — deterministic policy outranks model proposal; explicit user
   correction outranks inferred extraction.
2. **Scope** — conversation-scoped overrides are stronger than user-scoped
   defaults for the current conversation, but weaker for later conversations.
3. **Temporal validity** — an explicit expiration or update timestamp outranks
   an undated item.
4. **Explicitness** — a direct user statement outranks an inference, even when
   the inference carries high model confidence.
5. **Sensitivity** — a higher-sensitivity classification is never demoted by a
   lower-sensitivity item.
6. **Lifecycle** — only `active` versions may continue to lifecycle eligibility;
   `pending`, `shadow`, `rejected`, `revoked`, `superseded`, `expired`,
   suppressed, or stale-generation state is excluded before ranking.

The rule "current request wins" applies **only to soft preferences**. It never
overrides a verified hard constraint, a deterministic policy, or a prohibited
classification. A conflict that remains unresolved after these dimensions is
persisted as `PENDING_CONFLICT` and excluded from read selection until a
consolidation decision resolves it.

## Turn Understanding Interface

`TurnUnderstanding` is a deep module with this external interface:

```python
def understand_turn(
    message: UserMessage,
    context: ConversationContext,
) -> TurnSemantics: ...
```

`TurnSemantics` contains only governed fields:

```text
interaction_mode:
  normal_query | explicit_remember | explicit_correct |
  explicit_forget | explicit_inspect | ambiguous
topics: tuple[Topic, ...]
entities: tuple[EntityReference, ...]
current_assertions: tuple[AssertionProposal, ...]
current_overrides: tuple[OverrideProposal, ...]
memory_namespaces_needed: tuple[MemoryNamespace, ...]
temporal_context: current_turn | current_conversation | durable | unknown
needs_clarification: bool
reason_codes: tuple[TurnReasonCode, ...]
```

The implementation order is:

```text
deterministic prohibited-content detection
-> high-precision explicit-command and domain rules
-> bounded structured model classification only when unresolved
-> closed-schema validation
-> deterministic escalation and final TurnSemantics
```

The model may propose a mode, topic, entity, scope hint, or assertion. It cannot
authenticate, authorize, lower sensitivity, choose a database operation,
activate Memory, or generate SQL.

For durable explicit mutation, model classification is not sufficient. A
high-precision deterministic `ExplicitIntentGate` must corroborate an explicit
speech act such as remember, correct, or forget. The gate authorizes the class
of action, not the semantic payload. A bounded model may still parse or
normalize a complex payload behind that gate, but closed-schema validation and
deterministic policy remain authoritative. If the speech act is absent or the
payload remains ambiguous, the system asks for clarification or performs no
durable mutation.

This asymmetric policy is intentional. Missing a legitimate explicit save is a
recoverable false negative; inventing a durable personal Memory from an ordinary
question or statement is a higher-blast-radius false positive that can affect
later conversations.

A plain statement may still influence the current turn and may later become
background evidence if the completed source receives a positive
`BACKGROUND_ELIGIBLE` record. It does not synchronously create `USER_DURABLE`
state merely because Turn Understanding can extract a preference from it.

Turn Understanding is not background Memory extraction. It supports routing
and current-turn behavior. Background formation may inspect a bounded transcript
range and existing Memory state without delaying the current response.

### Action Routing

`ActionRouter` is a pure application decision seam. It consumes validated
`TurnSemantics` plus deterministic policy results and emits one governed action
class, for example `NORMAL_QUERY`, `EXPLICIT_MEMORY_ACTION`, or
`NEEDS_CLARIFICATION`. It does not call tools and cannot mutate state.

Normal queries proceed to `ContextPlanner`. Explicit Memory actions proceed to
the `ExplicitIntentGate` and Memory action path. This separation prevents the
same probabilistic classification from both interpreting the utterance and
authorizing a durable write.

## Source Handling Contract

Every source message that may be consumed by background Memory formation uses a
typed `SourceHandlingRecord`. The record is per Memory family, never a mixed set
of families and operations:

```text
SourceHandlingRecord(
  source_outbox_id,
  source_message_id,
  family,
  outcome,
  reason_code,
  recorded_at,
)

outcome =
  BACKGROUND_ELIGIBLE |
  EXPLICIT_APPLIED |
  EXPLICIT_REFUSED |
  EXPLICIT_NOOP |
  FORGET_APPLIED |
  FORGET_REFUSED
```

The absence of a record means `UNHANDLED`. It is never interpreted as
background permission. A worker may extract a family only after reading an
explicit positive `BACKGROUND_ELIGIBLE` outcome for that family. An explicit
action records its terminal outcome so the worker cannot form a duplicate
inferred candidate from the same source.

There is at most one terminal handling record for the same
`(source_message_id, family)`. Replaying terminal handling is idempotent: an
identical outcome observes the existing record, while a conflicting terminal
outcome fails closed and requires reconciliation. `source_outbox_id` is retained
for queue correlation but is not the semantic identity of the handling
decision, because retries or future queue migrations must not create a second
decision for the same source and family.

For a normal completed turn, the application records the governed positive
background outcome before the related outbox event becomes claimable. For an
explicit Memory turn, source handling is committed with the explicit action and
acknowledgement. A crash between initial turn allocation and either terminal
commit leaves the record absent and the outbox event unreleased, which is the
fail-closed state.

## Bounded Context Workflow

The synchronous Chat path is a **bounded workflow**, not an unbounded agent
loop. It runs at most one tool phase per turn.

### Phase Semantics

`max_tool_phases = 1` means one phase, not one tool call. Inside that single
phase the system may run Memory Read and RAG Retrieval **in parallel**, because
they are independent projections with no ordering dependency. The phase result
is a `ContextPlan` that the Context Arbiter may accept, modify, or reject based
on deterministic authority rules.

If the bounded phase cannot satisfy the request — for example, because
retrieval is required but the source is unavailable — the response must be
explicitly marked `incomplete` or `needs_follow_up`, not presented as a
successful answer. Hard-stopping at the boundary and returning a false-success
answer is a correctness failure.

### DialogueState and Working Memory

`DialogueState` is an **ephemeral, derivable projection** tied to a
`context_snapshot_sequence`. It is reconstructed on every turn from the
conversation transcript and current Memory selection. It is not persisted and
must not carry durable authority.

`Working Memory` is the **durable, versioned conversation projection**. It
carries a source message range, a prompt/schema version, and an expiry. It is
formed by deterministic or background summarization, not by the current-turn
model.

These two concepts must not duplicate mutable state. If both store
`active_topic` or `pending_action`, precedence and invalidation become
ambiguous. The rule is: DialogueState is read-only to the model; Working Memory
is the only durable projection that may influence later turns.

## Components and Dependency Direction

### ChatApplication

Interface: `handle_turn(principal, message, conversation_id=None) -> TurnResult`.
It owns turn ordering, conversation resolution, Memory read, generation, and
assistant persistence. It depends on interfaces, never concrete database
adapters.

### ConversationStore

Its critical interface is
`append_turn(...) -> TurnAllocation`, followed by terminal completion or failure.
PostgreSQL hides message sequence allocation, transaction boundaries, outbox
insertion, release/cancellation, and deletion fencing.

### TurnUnderstanding

Produces typed semantics without side effects. It may use internal deterministic
and model-classifier adapters hidden behind its interface.

### ActionRouter

Consumes validated `TurnSemantics` and chooses the bounded application branch.
It has no model or persistence authority and never invokes a tool itself.

### ExplicitIntentGate

Corroborates the explicit remember/correct/forget speech act with high-precision
deterministic rules. It may reject or request clarification. A model may help
parse the semantic payload only after this authority gate; classifier output
alone can never authorize durable mutation.

### ExplicitMemoryActionHandler

Consumes explicit actions plus the persisted source message. It validates the
registry, applies sensitivity and risk policy, resolves conflicts, and asks the
explicit-turn commit seam to persist. It produces typed mutation data and a
deterministic acknowledgement; it does not own the database transaction.

### ExplicitMemoryTurnCommit

Application-level unit of work for a successful explicit mutation. In one
PostgreSQL transaction it commits the Memory mutation, evidence/decision rows,
idempotency effect, family-specific `SourceHandlingRecord`, deterministic
assistant acknowledgement, and terminal outbox release/cancellation. It then
returns the committed result. No durable Memory mutation may become visible if
the acknowledgement row did not commit.

The explicit action's idempotency identity is derived from stable semantic
inputs: owner, source message, Memory family, canonical action, and assertion
identity (plus normalized target value when the action changes a value). It must
not depend on a random candidate/decision identifier, acknowledgement wording,
request retry count, or model-generated text. The acknowledgement is rendered
from the committed typed result so a retry cannot describe a different effect.

The existing conversation repository and Memory UoW may be adapted behind this
seam to accept one shared transaction/connection. They must not open independent
nested application transactions for this path.

### MemoryFormationEngine

Consumes a durable outbox event and bounded transcript state. It runs secret
filtering, structured extraction, registry validation, and immutable evidence
and candidate creation. It cannot create active state directly.

### MemoryConsolidationEngine

Compares a candidate with current versions and returns a typed relation and
change proposal. It is deterministic when rules resolve the relation. A bounded
model classifier may return a closed relation enum only for unresolved cases.

### MemoryActivationPolicy

Consumes evidence history, candidate authority, sensitivity, type, scope,
conflicts, and time. It returns an activation decision without persistence.

### MemoryLifecyclePolicy

Owns canonical lifecycle predicates shared by formation, activation, and read:
retention/source validity, suppression state and generation, expiry, lifecycle
status, and scope validity. It exposes operation-specific decisions such as
`can_form`, `can_activate`, and `is_read_eligible`; callers do not reconstruct
these rules themselves.

### MemoryStore

PostgreSQL is canonical for evidence, candidates, decisions, assertions,
versions, lifecycle events, idempotency, and outbox state. Mutations are atomic,
owner-scoped, version-checked, and append-auditable.

### MemoryReadEngine

Consumes principal, conversation, TurnSemantics, and budget. It performs owner,
lifecycle, sensitivity, scope, temporal, conflict, relevance, ranking, and
budget filtering. It returns a typed selection or abstention.

`ACTIVE` is necessary but not sufficient for read eligibility. The engine first
applies `MemoryLifecyclePolicy`; only then does it evaluate relevance,
precedence, ranking, and budget. Lifecycle implementation details do not leak to
the caller through a shallow provenance-policy object.

### ContextPlanner

Consumes the current turn semantics and dialogue state and proposes one bounded
retrieval plan: `none`, `rag_only`, `memory_only`, or `both`. It may use a
bounded classifier for ambiguous relevance, but the deterministic Context
Arbiter retains authority over policy, sensitivity, hard constraints, and
budget.

### MemoryContextComposer

Transforms selected Memory into controlled context. It never includes raw
evidence by default and labels influence as hard constraint, soft preference,
working state, episode, or procedural policy.

### MemoryWorkerRuntime

Runs outside the API process lifecycle. It owns claim, lease, retry, backoff,
dead-letter, cancellation, graceful shutdown, and worker observability. It calls
formation, consolidation, activation, and persistence through their interfaces.

Dependency direction is:

```text
HTTP/worker adapters
-> application modules
-> pure domain interfaces and policies
-> persistence/model interfaces
<- PostgreSQL and model-provider adapters
```

No domain module imports FastAPI, SQLAlchemy, a provider SDK, RAG, or frontend
code.

## Data Flow and Lifecycle

### Normal Chat Turn

1. Authenticate and resolve or create an owner-scoped standalone conversation.
2. Allocate the turn atomically: persist the user message, pending assistant
   row, and one unreleased extraction outbox event.
3. Interpret the persisted turn into `TurnSemantics`.
4. `ActionRouter` selects the normal-query branch.
5. `ContextPlanner` proposes Memory/RAG retrieval; the Context Arbiter applies
   deterministic policy.
6. Read eligible Memory and/or RAG evidence according to the governed plan.
7. Compose bounded context and generate the response.
8. In the terminal turn transaction, persist the assistant response, record the
   family-specific `BACKGROUND_ELIGIBLE` outcomes that apply, and release the
   corresponding outbox event.
9. Return response text, citations, conversation persistence state, and
   controlled Memory selection metadata.

Chat never waits for background formation. Turn Understanding or Memory Read
failure degrades to a normal no-Memory answer and emits a controlled reason.

### Explicit Command in Chat

1. Allocate the turn exactly as for normal Chat; the outbox event remains
   unreleased.
2. Turn Understanding proposes an explicit action and `ActionRouter` selects the
   explicit branch.
3. `ExplicitIntentGate` deterministically corroborates the remember/correct/
   forget speech act. Absence or ambiguity produces clarification/no-write.
4. A bounded parser or model may interpret the payload, but registry,
   sensitivity, ownership, scope, retention, current versions, and resolver
   policy deterministically validate the proposal.
5. Low-risk single ordinary remember/correct/forget produces a typed change and
   deterministic acknowledgement.
6. `ExplicitMemoryTurnCommit` atomically commits the Memory effect, evidence and
   decision, idempotency record, family-specific `SourceHandlingRecord`,
   acknowledgement assistant row, and terminal outbox release/cancellation.
7. Bulk deletion or scope expansion remains a separately governed confirmation
   flow if reintroduced; it is not silently treated as a low-risk single-item
   action.
8. Restricted or prohibited content is refused without durable semantic
   persistence. Prohibited secret handling occurs before any Memory-model call.
9. The worker sees the explicit source-handling outcome and cannot form a
   duplicate inferred candidate from the same source and family.

If the process fails after turn allocation but before step 6, the Memory
mutation has not committed, the acknowledgement is not complete, source
handling is absent, and the outbox remains unreleased. If step 6 commits, both
the mutation and acknowledgement are durable. The architecture therefore
forbids the state "Memory saved but the user was told the turn failed."

### Background Formation

1. Claim one pending event with a bounded lease.
2. Revalidate owner, conversation retention, deletion epoch, source message,
   suppression state, and the positive family-specific source-handling outcome.
3. Load only the governed transcript window.
4. Reject prohibited content before the Memory model.
5. Extract closed-schema candidates.
6. Validate registry and sensitivity; create immutable evidence and candidate.
7. Consolidate against current state.
8. Apply the type-specific activation policy.
9. Commit semantic effect and source-event completion with stable idempotency.

The idempotency identity is derived from source event, canonical assertion
identity, normalized value, and governed operation. It never includes a random
candidate identifier.

## Explicit Forget and Suppression Lifecycle

Product-level `forget` is a Memory lifecycle operation. It is not privacy
erasure, account deletion, or a reuse of `memory_deletion_ledger`.

The target lifecycle adds:

```text
MemoryOperation.REVOKE

VersionStatus:
  ACTIVE
  SUPERSEDED
  REVOKED
```

Each canonical assertion identity also carries a monotonically controlled
generation and suppression state. The exact physical schema is selected by the
implementation plan, but the semantics are fixed:

1. Explicit forget resolves the target assertion, changes its current active
   version to `REVOKED`, advances the assertion generation, and marks the
   identity suppressed.
2. Evidence and candidates created under an older generation can never create
   or reactivate a version in a later generation.
3. While the identity is suppressed, background formation and activation cannot
   silently relearn it. A suppressed observation may be counted only as a
   controlled policy outcome; it is not activation evidence.
4. Read excludes `REVOKED` versions and every version/candidate whose generation
   is stale or whose assertion remains suppressed.
5. A new corroborated explicit `remember` may intentionally clear suppression
   for the current generation and create a new active version from the new
   source. Old evidence remains stale and does not contribute to the new
   generation.
6. Explicit correction supersedes the current active version but does not imply
   privacy deletion of its historical evidence.

The suppression rule is enforced at all three eligibility-changing boundaries:
formation/write, activation, and read. Enforcing it only at read is insufficient
because a delayed shadow candidate could otherwise become active after a forget.

`memory_deletion_ledger` remains reserved for privacy/retention deletion
evidence and propagation. Product forget history is represented by Memory
lifecycle events and generation state, so re-remember does not require deleting
or rewriting privacy audit evidence.

## Type-Specific Activation Policy

| Type | Explicit ordinary input | Inferred input |
| --- | --- | --- |
| Preference/profile fact, conversation scope | Corroborated explicit command may write active after validation; retention remains conversation-bound | Active after two independent user turns agree, no unresolved conflict |
| Preference/profile fact, user scope | Corroborated explicit durable command may write active after validation with `USER_DURABLE` retention | Active after three independent evidence items across at least two conversations, no unresolved conflict; retention is source-bound |
| Constraint | Corroborated explicit command may write active when ordinary and unambiguous | Remains shadow unless two independent items agree and policy classifies it non-sensitive and non-high-impact |
| Relationship | Corroborated explicit command may write active when ordinary | Requires two grounded evidence items; uncertain entity resolution remains pending |
| Episode | Grounded event may be accepted from one explicit source | One grounded source is sufficient only when actor, event, time, and provenance validate; otherwise shadow |
| Working state | Updated by deterministic conversation transitions | Summary/open-state projection may replace the previous projection after source-consistency checks |
| Procedural | Not user-writable | Never activated from Chat; requires offline evaluation and governed publication |

Evidence independence requires distinct source message IDs. Repeated extraction
or retries of the same source never increase support. Model confidence is not a
truth probability and cannot replace evidence requirements.

## Consolidation and Conflict

The common relation vocabulary is:

```text
new | duplicate | reinforcement | correction | contradiction |
temporary_exception | stale | unrelated | uncertain
```

Deterministic identity, authority, timestamp, scope, and value comparisons run
first. A model classifier may only select a relation from the closed vocabulary
when rules cannot decide. The resolver alone creates `ADD`, `REINFORCE`,
`SUPERSEDE`, `ADD_EXCEPTION`, `PENDING_CONFLICT`, `REJECT`, or `NOOP`.
Explicit forget uses the separately authorized `REVOKE` lifecycle operation; a
relation classifier can never invent it.

Uncertain or equally authoritative contradiction is pending and excluded from
read selection. Destructive supersession requires stronger/newer authority or
an explicit correction.

## Read and Use Contract

Read order is:

```text
owner
-> active lifecycle
-> suppression generation
-> retention/source validity
-> allowed sensitivity
-> scope
-> type and namespace relevance
-> temporal validity
-> conflict exclusion
-> ranking and budget
-> selection or abstention
```

Structured exact retrieval is primary for canonical semantic keys and working
state. PostgreSQL full-text/pgvector search is a secondary projection for
free-text episodes and summaries after owner, lifecycle, sensitivity, and scope
filters. Vector similarity never overrides those filters or creates truth.

The composer emits typed context, for example:

```json
{
  "preferences": [
    {
      "key": "travel.preference.hotel_atmosphere",
      "value": "quiet",
      "scope": "user",
      "influence": "soft_preference"
    }
  ],
  "constraints": [],
  "episodes": [],
  "working_state": {}
}
```

Raw source messages, model explanations, hidden confidence, SQL data, and
untrusted instruction text are excluded. Memory is not a citation. The current
request wins over soft Memory.

An `ACTIVE` row is therefore not synonymous with a selected or even readable
Memory. `ACTIVE` identifies the current version for an assertion. Lifecycle
eligibility must still validate suppression, retention/source dependency,
expiry, owner, sensitivity, and scope before relevance and arbitration can
select it.

## Retrieval Planning and Context Engineering

### Retrieval Plans

The planner selects one of four **retrieval plans** for a turn:

| Plan | Meaning |
| --- | --- |
| `none` | No Memory or RAG retrieval; generate from prompt and current request only. |
| `rag_only` | RAG retrieval only; no Memory read. |
| `memory_only` | Memory read only; no RAG retrieval. |
| `both` | Memory read and RAG retrieval in parallel; results are composed, not concatenated. |

The plan is a **starting point**, not a final authority. The Context Arbiter may
override it when policy, sensitivity, or budget constraints require abstention
or a different combination.

### Context-Engineering Operations

Independently of the retrieval plan, the composer performs four
**context-engineering operations**:

1. **Select** — choose which retrieved items enter the context window.
2. **Compress** — summarize or truncate selected items to fit the token budget.
3. **Isolate** — separate hard constraints, soft preferences, episodes, and
   procedural policy so the model receives them with distinct influence labels.
4. **Write** — update working-memory projections (conversation summary, open
   goals) based on the current turn, but never mutate durable semantic or
   episodic Memory inside the hot path.

These operations are **orthogonal** to the retrieval plan. A `both` plan still
requires select, compress, and isolate. A `none` plan may still require write
for working-state maintenance.

### Context Arbiter

The Arbiter is a deterministic module with no model authority. It consumes the
planner's proposal, the budget, the sensitivity classifications, and any policy
conflicts. It emits an `ArbitrationResult` that the composer must follow. The
Arbiter may:

- downgrade `both` to `memory_only` or `rag_only` when one source is prohibited;
- upgrade `none` to `memory_only` when a hard constraint exists;
- reject an item that passed retrieval but fails sensitivity or scope checks;
- emit `ABSTAIN` when no eligible source satisfies the request.

## Working Summary and Episode Formation

Conversation summary formation is triggered when either the unsummarized tail
reaches 20 messages or its measured prompt-token estimate reaches 8,000 tokens.
The summary records its inclusive source range and prompt/schema version. A new
summary supersedes, rather than mutates, the prior projection. The unsummarized
tail remains available for immediate context.

Episode formation groups only events sharing the same owner, conversation,
governed event type, and bounded temporal window. Every episode preserves its
source message IDs and event time. An episode is not promoted merely because a
summary mentions it.

## Behavioral and Data Contracts

1. IDs are opaque, prefixed, non-blank text.
2. All persisted times are timezone-aware UTC.
3. Evidence, decisions, and versions are immutable.
4. Exactly one active version exists per canonical assertion identity.
5. Every active source-bound user-derived version resolves to enough currently
   valid evidence for its family/type-specific activation rule; a deliberately
   `USER_DURABLE` explicit save may survive source deletion without exposing the
   deleted evidence.
6. Every user-derived record carries `owner_user_id`, scope, type, sensitivity,
   authority, retention mode, lifecycle, generation, and provenance where those
   concepts apply.
7. Conversation-scope rows carry the owning conversation ID.
8. User-scope inference records cross-conversation evidence without exposing one
   conversation to another user.
9. Summary and vector indexes are rebuildable projections.
10. Message and extraction intent commit atomically.
11. Reprocessing the same source and canonical effect is idempotent.
12. Deleted, revoked, superseded, pending, rejected, expired, suppressed, stale-
    generation, or shadow state is not answer-eligible.
13. Absence of a `SourceHandlingRecord` is `UNHANDLED`, never background
    permission.
14. A durable explicit mutation requires deterministic speech-act corroboration;
    model output alone cannot authorize it.
15. A successful explicit Memory mutation and its deterministic acknowledgement
    commit atomically and share one idempotent semantic effect.
16. Product-level forget never rewrites or deletes privacy-erasure audit history.

## System Invariants

The following invariants are architecture-level requirements. Each must have at
least one executable test capable of failing when the invariant is violated.

1. **Authenticated ownership:** every user-derived Chat and Memory operation is
   bound to the authenticated principal; request payloads cannot choose the
   owner.
2. **Tenant isolation:** application predicates and PostgreSQL RLS both enforce
   owner isolation. Shared, staging, and production environments with real user
   data use a least-privilege role without superuser or `BYPASSRLS` authority.
3. **No model authorization:** models may interpret or propose semantics, but
   they cannot authenticate, authorize a durable write, lower sensitivity,
   select SQL, or mint a lifecycle operation.
4. **Positive background permission:** background formation requires an explicit
   positive `BACKGROUND_ELIGIBLE` record for the relevant family. Missing state
   fails closed.
5. **Explicit-write precision over recall:** ambiguous or weakly corroborated
   explicit intent degrades to clarification/no-write. Durable false positives
   are never accepted as the cost of higher recall.
6. **Atomic explicit acknowledgement:** no explicit Memory mutation may commit
   without the acknowledgement row and terminal source-handling outcome that
   tell the user what happened.
7. **Retention is independent of authority:** provenance strength never implies
   account-durable retention.
8. **Forget is lifecycle, not erasure:** `REVOKE` and assertion suppression
   prevent use and relearning without repurposing the privacy deletion ledger.
9. **No resurrection:** stale evidence, shadow candidates, delayed workers, or
   retries from an older assertion generation cannot make forgotten Memory
   eligible again.
10. **One lifecycle policy:** formation, activation, and read use the same
    canonical retention/source-validity and suppression semantics, exposed via
    operation-specific policy entry points.
11. **Active is not enough:** read selection requires lifecycle eligibility,
    relevance, precedence, and budget after the version is known to be active.
12. **Current intent wins over soft Memory:** Memory may personalize; it cannot
    silently override the current user's request, deterministic safety policy,
    or verified hard constraint.
13. **Memory is data, not instruction:** retrieved user Memory enters generation
    through controlled typed context and never gains system/developer authority.
14. **Idempotent semantic effects:** retry or redelivery of the same source and
    governed effect cannot create duplicate versions or duplicate acknowledgements.
15. **Deletion propagation:** conversation/account retention deletion invalidates
    dependent evidence, pending work, summaries/episodes, and search projections
    according to retention mode and source validity.
16. **Privacy-safe observability:** default logs/traces contain typed IDs, reason
    codes, controlled counters, model/version metadata, latency, and cost — not
    raw messages, prompts, Memory values, evidence, secrets, or hidden chain of
    thought.
17. **Evaluation before inferred activation:** background-inferred Memory may be
    observed in shadow mode before promotion, but active inferred rollout is
    blocked until the governed evaluation gate is conclusive and passes.

## Errors and Edge Cases

| Condition | Required behavior |
| --- | --- |
| Unknown/foreign conversation | Content-free not-found response; no model call |
| Message/outbox transaction failure | Roll back both; no Chat model call |
| Turn Understanding timeout/invalid output | Fall back to normal query semantics; emit controlled reason |
| Explicit command ambiguity | Ask one focused clarification; no mutation |
| Classifier proposes explicit mutation but deterministic speech-act gate does not corroborate it | No durable mutation; treat as normal/ambiguous according to governed rules |
| Explicit mutation transaction fails | Roll back Memory effect, source-handling record, acknowledgement, and terminal outbox transition together; return failure |
| Crash after turn allocation but before explicit commit | Pending turn remains; no Memory mutation; no source permission; outbox stays unreleased |
| Memory read unavailable | Generate without Memory; return `skipped` metadata |
| Chat generation failure | Transition the pending assistant row to `FAILED`, cancel the turn's unreleased extraction work, and return a controlled failure; never claim a completed assistant reply |
| Assistant completion persistence failure | Do not return the generated answer as a successfully persisted turn; leave the pending row observable/recoverable and return a controlled incomplete/failure result |
| Memory provider transient failure | Retry with bounded backoff; Chat remains unaffected |
| Permanent invalid model output | Dead-letter or invalid decision; no active version |
| Lease lost before commit | Do not commit semantic effect |
| Completion fails after semantic commit | Stable idempotency makes redelivery a no-op |
| Unresolved contradiction | Persist pending decision; abstain on the affected identity |
| Source deleted before processing | Cancel event and prevent activation |
| `SourceHandlingRecord` absent | Treat source/family as `UNHANDLED`; do not extract |
| Forget races delayed shadow activation | Suppression generation wins; stale candidate cannot activate |
| Conversation containing source evidence is deleted | Invalidate that evidence; re-evaluate source-bound Memory; preserve user-durable value without exposing deleted evidence |
| Secret/prohibited content | No Memory model call and no semantic evidence/candidate persistence |

## Security and Privacy

1. Authenticated owner identity comes from the principal, never request payload.
2. Application checks and PostgreSQL RLS both enforce owner scope. Any shared,
   staging, or production deployment containing real user data uses a
   least-privilege runtime role without superuser or `BYPASSRLS`; the concrete
   deployment guard is an implementation/operations choice, not a Memory-domain
   concept.
3. Model output may raise sensitivity but never lower deterministic or registry
   classification.
4. Prohibited authentication/payment secrets are rejected before Memory-model
   exposure and semantic persistence.
5. Chat-model exposure is a separate trust boundary and must not be confused
   with the Memory pre-model filter.
6. Retrieved Memory is treated as untrusted data, not instructions.
7. Procedural Memory has a distinct agent-owned namespace and publication role.
8. Controlled logs, responses, traces, and evaluation reports exclude raw
   message, evidence, prompt, token, and secret content.
9. Explicit inspect returns governed Memory summaries, not raw evidence from
   other conversations.
10. Explicit forget and privacy/retention deletion are distinct operations.
    Forget revokes/suppresses Memory identity; privacy/retention deletion
    propagates to source evidence, pending work, derived summaries, and vector
    projections.
11. A user-durable Memory that survives source deletion must never expose the
    deleted source text through inspect, trace, context, or citation.

## Observability and Operations

Required metrics include:

1. Chat latency with and without Memory.
2. Turn Understanding rule/model/fallback counts and latency.
3. Outbox pending age, claim rate, retry count, dead-letter count, and lease
   loss.
4. Extraction candidate, invalid, shadow, pending, activated, and rejected
   counts by governed type and reason.
5. Read eligible, selected, abstained, filtered, and conflict counts.
6. Memory context token count and generation-use outcomes.
7. PostgreSQL pool saturation, transaction retries, and RLS/owner denials.
8. Summary coverage and unsummarized tail size.
9. Explicit-intent deterministic-gate pass/refuse/clarify counts, plus durable
   explicit-write false-positive findings from evaluation.
10. `SourceHandlingRecord` outcomes by family, including `UNHANDLED` backlog and
    background-eligibility rate.
11. Suppression/revocation counts, stale-generation rejects, and attempted
    post-forget resurrection blocks.
12. Explicit Memory commit latency, rollback count, and idempotent replay count.

API and worker readiness are separate. Worker shutdown stops new claims,
finishes or safely releases leased work, and preserves pending events.

## Capacity, Latency, and Cost

Initial design target is 1,000 registered users, not 1,000 simultaneous model
calls. Capacity must be measured rather than inferred from user count.

1. Message/outbox transaction p95 target: 100 ms excluding network variance.
2. Rule-resolved Turn Understanding p95 target: 20 ms.
3. Model-assisted Turn Understanding has a configured timeout and must keep total
   added p95 under 500 ms before rollout.
4. Memory Read and context composition p95 target: 100 ms at the initial data
   volume.
5. Background model work has no synchronous Chat latency budget but has queue
   age and cost budgets.
6. Every model adapter records provider, model, prompt/schema version, tokens,
   latency, and controlled outcome metadata.

PostgreSQL transactional outbox is selected for this scale. A distributed queue
requires measured queue contention, latency, or operational isolation that the
database design cannot satisfy.

## Testing and Evaluation

### Module Tests

1. Closed TurnSemantics schema, rule precedence, ambiguity, repair, and fallback.
2. Explicit-intent truth table with ordinary questions/statements as negative
   examples; classifier-only output cannot authorize durable mutation.
3. Registry validation for every family/type/scope combination.
4. Authority/scope/retention truth tables, including source deletion with
   `USER_DURABLE`, `SOURCE_BOUND`, and `CONVERSATION_BOUND` state.
5. Type-specific activation truth tables.
6. Consolidation relation and resolver truth tables, including `REVOKE` entry
   only from the explicit authorized lifecycle path.
7. Suppression-generation tests for formation, activation, read, and explicit
   re-remember.
8. `SourceHandlingRecord` tests proving absence is `UNHANDLED` and never
   background permission.
9. Read eligibility, precedence, relevance, budget, and abstention, including an
   `ACTIVE` item rejected by lifecycle policy.
10. Context formatting and prompt-injection resistance.

### PostgreSQL Integration

1. Migration upgrade/downgrade/re-upgrade.
2. Message/outbox atomicity.
3. RLS and cross-owner denial.
4. One-current-version constraints.
5. Stable idempotent redelivery.
6. Concurrent same-identity writes and different-owner parallelism.
7. Deletion propagation and projection cleanup.
8. `ExplicitMemoryTurnCommit` rollback injection at every write boundary proves
   there is no committed Memory mutation without its acknowledgement and
   source-handling outcome.
9. Forget/re-remember concurrency proves stale generations cannot reactivate.
10. Conversation deletion invalidates source evidence while preserving a
    user-durable value without retaining access to deleted source text.

No required PostgreSQL integration test may count as passing when skipped.

### End-to-End Behavior

1. Create two conversations for one owner without a workspace.
2. Explicitly remember an ordinary user preference in conversation A and recall
   it in relevant conversation B.
3. Apply a conversation override without mutating the user preference.
4. Infer a conversation preference from two independent turns, activate it,
   and use it only for relevant queries.
5. Accumulate three independent evidence items across two conversations before
   activating an inferred user preference.
6. Keep shadow, pending, sensitive, deleted, and superseded states out of Chat.
7. Ground one episode, retrieve it for a related question, and abstain for an
   unrelated question.
8. Summarize a long conversation without losing a declared constraint.
9. Refuse a user attempt to write procedural instructions.
10. Recover from worker retry without duplicate semantic effect.
11. Ask an ordinary question such as a hotel preference query and prove no
    durable explicit Memory is created without an explicit speech act.
12. Explicitly remember A, forget A, process delayed pre-forget shadow work, and
    prove A does not return to eligible state.
13. Explicitly re-remember A after forget and prove only the new generation may
    become active.
14. Delete the source conversation for a `SOURCE_BOUND` Memory and prove it is
    re-evaluated against remaining valid evidence; repeat with `USER_DURABLE`
    Memory and prove the value survives without deleted-source exposure.
15. Inject failure after Memory mutation staging but before explicit turn
    completion and prove the transaction leaves neither mutation nor successful
    acknowledgement durable.

### Quality Gates

Measure per type and aggregate:

- intent-mode precision/recall;
- explicit durable-action precision and false-positive rate;
- extraction and normalization precision/recall;
- activation precision and false-activation rate;
- conflict-resolution correctness;
- retrieval precision/recall and correct abstention;
- generation-use correctness and over-personalization;
- temporal update/forgetting correctness;
- privacy leakage;
- p50/p95 latency and token/model cost.

Privacy leakage, cross-owner selection, prohibited-secret Memory-model exposure,
classifier-only durable mutation, missing-source-handling background extraction,
post-forget resurrection, unresolved-conflict use, non-atomic explicit
mutation/acknowledgement, and non-idempotent semantic duplication are
zero-tolerance gates. Any required metric or scenario that cannot be measured is
`INCONCLUSIVE`, never `PASS`.

## Compatibility and Staged Migration

### Baseline Already Established

The current branch already provides authenticated standalone PostgreSQL Chat,
PostgreSQL conversation persistence, the turn-readiness outbox barrier, the
separate Memory worker runtime, and removal of the former public Memory
Manager/API and SQLite mounted runtime. Those completed clean-break decisions are
prerequisites, not future stages of this design.

### Stage 1: Turn Understanding, Action Routing, and Source Handling

Introduce the typed `TurnUnderstanding`, pure `ActionRouter`, bounded
`ContextPlanner`, deterministic `ExplicitIntentGate`, and family-specific
`SourceHandlingRecord`. Preserve current Chat behavior while these seams are
dark/shadow evaluated. No new durable explicit Memory is enabled until the
negative-intent suite proves the authorization boundary.

### Stage 2: Explicit Semantic Memory Lifecycle

Implement retention modes, `REVOKE`/`REVOKED`, assertion generation and
suppression, the Chat-native explicit semantic action handler, and
`ExplicitMemoryTurnCommit`. Start with the governed semantic registry and prove
remember/correct/forget plus re-remember, source deletion, idempotency, and
failure atomicity. Do not restore the removed Memory Manager or public Memory
control routes.

### Stage 3: Semantic Read and Use

Implement `MemoryLifecyclePolicy`, exact structured `MemoryReadEngine`,
`ContextPlanner` Memory/RAG selection, deterministic Context Arbiter, and typed
Memory Context Composer. Prove the complete explicit vertical slice
`remember -> store -> read -> use -> correct/forget -> abstain` before enabling
background-inferred activation.

### Stage 4: Background Semantic Formation and Activation

Run formation/consolidation through the separate worker with positive source
handling, stable semantic idempotency, suppression checks, and source-validity
fences. Observe in shadow first. Active inferred Memory remains disabled until
the governed evaluation is conclusive and passes the false-activation and
privacy gates.

### Stage 5: Episodic and Working Memory Vertical Slices

Add episode, feedback, goal, temporary override, and summary behavior one
vertical slice at a time. Each slice must define formation, retention,
consolidation, read/use, deletion, failure behavior, and evaluation before the
next slice is mounted.

### Stage 6: Secondary Retrieval Projections

Introduce PostgreSQL full-text and/or pgvector only for free-text episodes and
summaries when exact structured lookup is insufficient. These are rebuildable
projections behind lifecycle/owner/sensitivity filters, never canonical Memory
state or activation authority.

### Stage 7: Procedural Publication

Add the separate evaluation-approved procedural publication workflow. It
remains system/agent-owned and cannot be written directly by ordinary user chat.

## Rollout

Independent gates control:

1. Turn Understanding / ActionRouter shadow observation.
2. Explicit Chat Memory actions.
3. Memory Read.
4. Memory prompt use.
5. Background capture.
6. Per-type inferred activation.
7. Summary, episode, full-text, and vector projections.
8. Procedural publication.

Read and use gates remain independently reversible. Shadow observation precedes
active inference. A rollback may stop workers and disable reads while preserving
durable events and versions.

## Rollback

1. Disable Memory prompt use before disabling read.
2. Disable per-type activation while preserving shadow evidence.
3. Stop workers from claiming new events; preserve pending work.
4. Disable explicit mutations while retaining inspect/read if safe.
5. Roll back application wiring before database schema only when compatibility
   has been proven.
6. Never downgrade a schema while rows depend on the newer contract.
7. Restore from tested PostgreSQL backup for destructive storage failure.

Rollback does not reactivate revoked/deleted/superseded Memory or clear
suppression generations. PostgreSQL remains the relational source of truth; no
rollback path reintroduces SQLite.

## Proposed Supersession

After this specification, its required ADRs, and its implementation plans are
approved, this design has normative precedence over conflicting scope in:

1. `2026-09-07-basic-semantic-memory-write-pipeline-design.md` for one-key,
   separate Memory Manager, and background-shadow-only target limitations.
2. `2026-09-04-memory-retrieval-design.md` for SQLite legacy retrieval as the
   mounted target.
3. `2026-09-04-shadow-memory-extraction-design.md` for workspace-coupled legacy
   extraction as the target path.
4. `2026-09-04-conversation-persistence-design.md` for workspace-required SQLite
   conversation persistence.

The previous artifacts remain historical implementation evidence. They are not
deleted, and behavior is not superseded merely by approving this design; staged
replacement requires approved implementation plans and verification.

## Required ADRs

Existing accepted decisions to retain or amend:

1. ADR 0011: authenticated standalone conversations.
2. ADR 0012: versioned semantic Memory in PostgreSQL.
3. ADR 0013: model-assisted extraction and deterministic resolution.
4. ADR 0014: transactional outbox and idempotent workers.
5. ADR 0020: public Memory management removal; future controls return only
   through an approved Chat-native design.
6. ADR 0023: atomic two-phase Chat turn.
7. ADR 0027: outbox turn-readiness barrier — an outbox event is released only
   when its turn reaches a terminal status (`complete` or `failed`).
8. ADR 0029 and subsequent worker-runtime/credential decisions: background
   Memory runs as an operationally separate worker with least-privilege database
   authority.

ADR 0017 is historical input for risk calibration but is not current authority
for a public control surface because ADR 0020 superseded that surface.

New decisions required before implementation:

1. Chat-native Memory actions: typed Turn Understanding, `ActionRouter`,
   deterministic explicit-intent authority, and atomic
   `ExplicitMemoryTurnCommit` acknowledgement semantics.
2. Memory retention and revocation lifecycle: retention modes independent of
   `Authority`, `REVOKE`/`REVOKED`, assertion suppression generation, and
   re-remember semantics.
3. Unified Memory family/scope lifecycle and activation authority, including
   positive `SourceHandlingRecord` semantics.
4. Memory Read/Use authority: lifecycle encapsulation, structured retrieval,
   Context Planner/Arbiter, controlled context, and rebuildable vector/full-text
   projections.
5. System-owned procedural Memory publication boundary.

## Acceptance Criteria

1. The specification and required ADRs are approved before implementation.
2. The approved design preserves the established authenticated PostgreSQL-only
   standalone Chat baseline and does not restore Workspace, SQLite, or the
   removed public Memory management surface.
3. Every accepted user turn allocates its messages and extraction intent with
   the existing turn-readiness barrier; background processing cannot claim the
   source before terminal handling.
4. Turn Understanding produces only governed typed output and cannot mutate
   Memory.
5. A durable explicit remember/correct/forget requires deterministic speech-act
   corroboration; classifier-only authorization is impossible.
6. A successful explicit Memory mutation, idempotency result, family-specific
   source handling, acknowledgement assistant row, and terminal outbox
   transition commit atomically.
7. `Authority`, scope, and retention are independent contracts with executable
   deletion/retention truth tables.
8. Explicit forget produces `REVOKED` state plus assertion suppression; delayed
   or old-generation evidence cannot resurrect the Memory, while a new
   corroborated explicit remember can create a fresh eligible generation.
9. Absence of `SourceHandlingRecord` never permits background extraction.
10. Every listed Memory family has at least one complete, evaluated vertical
   behavior before the architecture is called complete.
11. Type-specific activation policies enforce the evidence table in this spec.
12. Only lifecycle-eligible and relevant active Memory reaches controlled
    context; current user intent
   overrides soft Memory.
13. Background processing is non-blocking, retry-safe, deletion-aware,
    suppression-aware, and
   idempotent by semantic effect.
14. PostgreSQL integration verification runs without required skips.
15. End-to-end evaluation is `PASS` only when every required metric/scenario is
    measured and every zero-tolerance gate passes; missing required evidence is
    `INCONCLUSIVE`.
16. Operations documentation proves migration, backup, restore, worker recovery,
    feature rollback, and safe deletion.

## Approval Record

Version 0.3 is in review. Approval authorizes preparation of the required ADRs
and staged implementation plans only. It does not authorize runtime edits,
database migrations, feature enablement, dependency changes, or Git delivery.

## Changelog

### v0.3 Draft — 2026-09-12

- Rebased **Current-State Evidence** onto the PostgreSQL-only, authenticated
  Chat baseline after ADR 0020 and the worker/outbox remediation work.
- Split provenance `Authority` from `RetentionMode`; defined
  `CONVERSATION_BOUND`, `SOURCE_BOUND`, and `USER_DURABLE` semantics.
- Added family-specific positive `SourceHandlingRecord`; absence is explicitly
  `UNHANDLED` and fail-closed.
- Added deterministic `ExplicitIntentGate` so a model may interpret semantics
  but cannot independently authorize durable personal state.
- Added `ExplicitMemoryTurnCommit` and the invariant that Memory mutation plus
  acknowledgement/source handling commit atomically and idempotently.
- Added explicit `REVOKE`/`REVOKED` lifecycle, assertion suppression generation,
  no-resurrection semantics, and explicit re-remember behavior without
  repurposing `memory_deletion_ledger`.
- Made `ACTIVE` necessary but insufficient for read eligibility and centralized
  lifecycle rules behind `MemoryLifecyclePolicy`.
- Added the architecture-level **System Invariants** section and executable
  failure/evaluation requirements, including `INCONCLUSIVE` when required
  evidence cannot be measured.
- Reordered staged delivery around complete vertical slices from the current
  baseline: understanding/source handling -> explicit semantic write/store ->
  semantic read/use -> background activation -> additional families/projections.

### v0.2 Draft — 2026-09-11

- Added **Precedence Resolution** section: per-assertion resolution across six
  dimensions (authority, scope, temporal validity, explicitness, sensitivity,
  lifecycle). Clarifies that "current request wins" applies only to soft
  preferences.
- Added **Bounded Context Workflow** section: `max_tool_phases=1` semantics,
  parallel Memory+RAG inside one phase, explicit `incomplete` response on
  boundary hit, and the DialogueState / Working Memory distinction.
- Added **Retrieval Planning and Context Engineering** section: four retrieval
  plans (`none|rag_only|memory_only|both`) and four orthogonal
  context-engineering operations (`select|compress|isolate|write`). Introduces
  the Context Arbiter as a deterministic authority module.
- Added ADR 0027 to required decisions.
- Updated Current-State Evidence with the outbox turn-readiness barrier.

## References

1. LangMem, "Long-term Memory in LLM Applications":
   <https://langchain-ai.github.io/langmem/concepts/conceptual_guide/>
2. LangGraph, “Memory overview”:
   <https://langchain-ai.github.io/langgraphjs/how-tos/delete-messages/>
3. Packer et al., “MemGPT: Towards LLMs as Operating Systems”:
   <https://arxiv.org/abs/2310.08560>
4. Chhikara et al., “Mem0: Building Production-Ready AI Agents with Scalable
   Long-Term Memory”: <https://arxiv.org/abs/2504.19413>
5. [Agent Memory Target Architecture](./2026-09-12-agent-memory-target-architecture-design.md),
   the current approved successor specification.
