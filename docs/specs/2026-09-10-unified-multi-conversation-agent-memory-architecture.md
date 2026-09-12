# Unified Multi-Conversation Agent Memory Architecture

| Field | Value |
| --- | --- |
| Status | In Review |
| Version | 0.2 Draft |
| Date | 2026-09-11 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Chat-first, PostgreSQL-backed, multi-conversation agent Memory with typed turn understanding, explicit chat commands, background formation, consolidation, activation, read, use, and evaluation |
| Related issue | Repository-owner approved exception: interactive architecture redesign on 2026-09-10 |
| Superseded document | None until approval; Section 18 defines the proposed staged supersession |

## Summary

This specification replaces the current collection of disconnected legacy and
V2 Memory capabilities with one chat-first architecture. Users interact through
normal conversations. The same chat surface supports normal tasks and explicit
remember, correct, forget, and inspect commands. Background workers form
inferred memories without blocking chat.

The architecture supports multiple conversations and four governed Memory
families: semantic, episodic, working, and procedural. The families share an
auditable evidence-to-decision lifecycle but do not share one activation or
retrieval policy. PostgreSQL is the only relational source of truth for the
mounted Chat and Memory runtime. Vector indexes are rebuildable projections,
never lifecycle authority.

Implementation is staged by complete vertical behavior, not by creating all
tables or extractors first. Each stage must demonstrate write, storage, read,
use, failure behavior, and evaluation for its governed family before the next
family enters the mounted runtime.

## Context

The existing repository contains two Memory generations:

1. Legacy SQLite extraction, promotion, records, and Chat retrieval.
2. V2 PostgreSQL semantic write contracts, policy, resolver, unit of work,
   explicit controls, outbox worker, model adapter, and focused evaluation.

The V2 domain package is substantial, but the mounted Chat still uses SQLite
conversation and Memory repositories. The PostgreSQL conversation adapter and
worker are capabilities rather than a composed runtime. V2 writes are not read
by Chat. Explicit commands live in a separate Memory Manager instead of the
primary conversation. Consequently the repository cannot demonstrate one
complete `chat -> form -> consolidate -> recall -> use` behavior.

Modern agent-memory systems commonly distinguish thread-scoped state from
cross-thread long-term storage, semantic/episodic/procedural families, and
hot-path from background formation. This specification applies those concepts
with application-specific authority and evaluation rather than adopting a
framework's storage model verbatim.

## Current-State Evidence

| Evidence | Verified behavior | Architectural consequence |
| --- | --- | --- |
| `backend/app/main.py:214-221` | Chat, workspace, conversation, legacy Memory, Memory Controls, operations, and planner routers are all mounted | The public product surface is wider than the new chat-first objective |
| `backend/app/api/chat.py:66-121` | Chat resolves SQLite legacy Memory and SQLite-backed conversation dependencies; all three Memory gates default false | Mounted Chat does not consume V2 PostgreSQL Memory |
| `backend/app/api/conversations.py:66-92` | Conversation service constructs SQLite adapters | PostgreSQL message/outbox capability is disconnected |
| `backend/app/api/memory_controls.py:67-115` | Explicit V2 controls are mounted behind a false-by-default gate and create a PostgreSQL UoW lazily | Explicit V2 write exists but is a separate, gated surface |
| `backend/conversations/postgres_repository.py` | PostgreSQL message append supports a conversation outbox intent | Atomic capture capability exists |
| `backend/memory/write_pipeline/` | Registry, immutable models, secret detector, policy, resolver, PostgreSQL UoW, outbox, worker, model adapter, command service, and evaluation exist | Preserve and generalize the proven domain seams |
| `backend/memory/write_pipeline/worker.py:430-492` | Candidate commit precedes separate source-event completion; retry key includes random candidate ID | Exactly-once semantic effect is not guaranteed |
| `frontend/src/components/memory/MemoryManager.jsx:89-108` | Explicit commands are submitted through a separate drawer and omit conversation provenance by default | Move explicit commands into Chat and require source-message provenance |
| Fresh unit verification on 2026-09-10 | `202 passed` in `backend/tests/unit/memory_write_pipeline` | Pure V2 modules have strong focused coverage |
| Fresh PostgreSQL-focused verification on 2026-09-10 | `3 passed, 35 skipped` without the required PostgreSQL environment | Runtime database claims remain unproven locally |
| Fresh bound-Chat verification on 2026-09-10 | Fails because `ConversationCreate` requires an omitted `owner_user_id` | Conversation ownership migration must precede Memory integration |
| ADR 0027 outbox turn-readiness barrier (2026-09-11) | `released_at` gate added to `conversation_outbox`; `complete_turn` / `fail_turn` atomically release or cancel; claim predicates require the gate; worker transcript excludes non-terminal rows | Prevents extraction over an incomplete turn when the worker is mounted |

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
8. Automatic import of legacy SQLite Memory into active V2 state.

## Alternatives Considered

### Alternative A: Expand the Current One-Key Pipeline in Place

Add more keys and conditionals to the existing command service, worker, and
legacy retrieval path. This reuses code quickly but preserves two stores, two
lifecycles, route-level dependency construction, and disconnected read/write
semantics. Rejected because every new type multiplies the existing ambiguity.

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
6. **Lifecycle** — only `active` versions are eligible; `pending`, `shadow`,
   `rejected`, `superseded`, or `expired` rows are excluded before ranking.

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

Turn Understanding is not background Memory extraction. It supports routing
and current-turn behavior. Background formation may inspect a bounded transcript
range and existing Memory state without delaying the current response.

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
`append_user_message_with_outbox(...) -> PersistedMessage`. PostgreSQL hides
message sequence allocation, transaction boundaries, and outbox insertion.

### TurnUnderstanding

Produces typed semantics without side effects. It may use internal deterministic
and model-classifier adapters hidden behind its interface.

### MemoryCommandHandler

Consumes explicit actions plus the persisted source message. It validates the
registry, applies sensitivity and risk policy, resolves conflicts, and asks the
Memory UoW to commit. Success is reported only after commit.

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

### MemoryStore

PostgreSQL is canonical for evidence, candidates, decisions, assertions,
versions, lifecycle events, idempotency, and outbox state. Mutations are atomic,
owner-scoped, version-checked, and append-auditable.

### MemoryReadEngine

Consumes principal, conversation, TurnSemantics, and budget. It performs owner,
lifecycle, sensitivity, scope, temporal, conflict, relevance, ranking, and
budget filtering. It returns a typed selection or abstention.

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
2. Commit the user message and one extraction outbox event atomically.
3. Interpret the persisted turn into `TurnSemantics`.
4. Read eligible Memory using the typed semantics.
5. Compose bounded Memory and travel context.
6. Generate the response.
7. Persist the assistant message.
8. Return response text, citations, conversation persistence state, and
   controlled Memory selection metadata.

Chat never waits for background formation. Turn Understanding or Memory Read
failure degrades to a normal no-Memory answer and emits a controlled reason.

### Explicit Command in Chat

1. Persist the source message and outbox intent.
2. Turn Understanding identifies an explicit action.
3. The command handler validates one typed proposal against registry, risk,
   sensitivity, ownership, and current versions.
4. Low-risk single ordinary remember/correct/forget commits synchronously.
5. Bulk deletion or scope expansion produces a preview and one-time
   confirmation challenge in Chat.
6. Restricted or prohibited content is refused without semantic persistence or
   a Memory-model call.
7. The assistant communicates the committed result; controlled UI metadata may
   render a compact saved/removed state separately.
8. The background worker checks source-message handling state and does not form
   a duplicate inferred candidate from a completed explicit action.

### Background Formation

1. Claim one pending event with a bounded lease.
2. Revalidate owner, conversation retention, deletion epoch, source message,
   and prior explicit handling.
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

## Type-Specific Activation Policy

| Type | Explicit ordinary input | Inferred input |
| --- | --- | --- |
| Preference/profile fact, conversation scope | Direct active write after validation | Active after two independent user turns agree, no unresolved conflict |
| Preference/profile fact, user scope | Direct active write after validation | Active after three independent evidence items across at least two conversations, no unresolved conflict |
| Constraint | Direct active write when ordinary and unambiguous | Remains shadow unless two independent items agree and policy classifies it non-sensitive and non-high-impact |
| Relationship | Direct active write when ordinary | Requires two grounded evidence items; uncertain entity resolution remains pending |
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

Uncertain or equally authoritative contradiction is pending and excluded from
read selection. Destructive supersession requires stronger/newer authority or
an explicit correction.

## Read and Use Contract

Read order is:

```text
owner
-> active lifecycle
-> allowed sensitivity
-> current source validity
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
5. Every active user-derived version resolves to at least one valid evidence
   item; type-specific activation may require more.
6. Every user-derived record carries `owner_user_id`, scope, type, sensitivity,
   authority, lifecycle, and provenance.
7. Conversation-scope rows carry the owning conversation ID.
8. User-scope inference records cross-conversation evidence without exposing one
   conversation to another user.
9. Summary and vector indexes are rebuildable projections.
10. Message and extraction intent commit atomically.
11. Reprocessing the same source and canonical effect is idempotent.
12. Deleted, superseded, pending, rejected, expired, or shadow state is not
    answer-eligible.

## Errors and Edge Cases

| Condition | Required behavior |
| --- | --- |
| Unknown/foreign conversation | Content-free not-found response; no model call |
| Message/outbox transaction failure | Roll back both; no Chat model call |
| Turn Understanding timeout/invalid output | Fall back to normal query semantics; emit controlled reason |
| Explicit command ambiguity | Ask one focused clarification; no mutation |
| Memory read unavailable | Generate without Memory; return `skipped` metadata |
| Chat generation failure | User message/outbox remain durable; no assistant message is claimed persisted |
| Assistant persistence failure | Return generated answer with explicit persistence gap |
| Memory provider transient failure | Retry with bounded backoff; Chat remains unaffected |
| Permanent invalid model output | Dead-letter or invalid decision; no active version |
| Lease lost before commit | Do not commit semantic effect |
| Completion fails after semantic commit | Stable idempotency makes redelivery a no-op |
| Unresolved contradiction | Persist pending decision; abstain on the affected identity |
| Source deleted before processing | Cancel event and prevent activation |
| Secret/prohibited content | No Memory model call and no semantic evidence/candidate persistence |

## Security and Privacy

1. Authenticated owner identity comes from the principal, never request payload.
2. Application checks and PostgreSQL RLS both enforce owner scope.
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
10. Explicit forget and retention deletion propagate to answer eligibility,
    pending work, derived summaries, and vector projections.

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
2. Registry validation for every family/type/scope combination.
3. Type-specific activation truth tables.
4. Consolidation relation and resolver truth tables.
5. Read eligibility, precedence, relevance, budget, and abstention.
6. Context formatting and prompt-injection resistance.

### PostgreSQL Integration

1. Migration upgrade/downgrade/re-upgrade.
2. Message/outbox atomicity.
3. RLS and cross-owner denial.
4. One-current-version constraints.
5. Stable idempotent redelivery.
6. Concurrent same-identity writes and different-owner parallelism.
7. Deletion propagation and projection cleanup.

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

### Quality Gates

Measure per type and aggregate:

- intent-mode precision/recall;
- extraction and normalization precision/recall;
- activation precision and false-activation rate;
- conflict-resolution correctness;
- retrieval precision/recall and correct abstention;
- generation-use correctness and over-personalization;
- temporal update/forgetting correctness;
- privacy leakage;
- p50/p95 latency and token/model cost.

Privacy leakage, cross-owner selection, prohibited-secret Memory-model exposure,
unresolved-conflict use, and non-idempotent semantic duplication are
zero-tolerance gates.

## Compatibility and Staged Migration

### Stage 1: Chat and PostgreSQL Conversation Foundation

Mount Chat, conversation history, operations, and health only. Support multiple
standalone owner-scoped conversations. Commit messages and outbox intents in
PostgreSQL. Keep Memory read/use disabled.

### Stage 2: Turn Understanding and Explicit Semantic Memory

Move ordinary remember/correct/forget/inspect actions into Chat. Complete
semantic preference/profile/constraint behavior through V2 PostgreSQL. Remove
the Memory Manager from the mounted frontend.

### Stage 3: Background Semantic Formation

Deploy the worker runtime, stable idempotency, consolidation, and type-specific
activation. Enable shadow capture first, then active inference only after its
quality gates pass.

### Stage 4: V2 Read and Use

Replace SQLite retrieval with the Memory Read and Context Composer modules.
Enable exact structured retrieval first and pgvector episode/summary projection
only after projection tests pass.

### Stage 5: Episodic and Working Memory

Add episode, feedback, goal, temporary override, and summary vertical slices.
Each type must pass its end-to-end and quality gates before rollout.

### Stage 6: Procedural Publication

Add the separate evaluation-approved publication workflow. It remains disabled
for user chat mutations.

### Stage 7: Legacy Removal

Inventory SQLite without reading raw content into reports. If data is disposable,
archive or delete it only with owner approval. If retention is required, import
legacy rows as quarantined evidence and never auto-activate them. Remove SQLite
runtime imports, configuration, adapters, and compatibility tests only after
PostgreSQL replacement verification passes.

## Rollout

Independent gates control:

1. PostgreSQL Chat persistence.
2. Explicit chat commands.
3. Background capture.
4. Per-type activation.
5. V2 read.
6. V2 prompt use.
7. Summary and episode projections.
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

Rollback does not reactivate deleted/superseded Memory or copy V2 state back to
SQLite.

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
5. ADR 0017: risk-based Memory controls.
6. ADR 0027: outbox turn-readiness barrier — an outbox event is released only
   when its turn reaches a terminal status (`complete` or `failed`).

New decisions required before implementation:

1. Unified Memory family, scope, lifecycle, and activation authority.
2. Typed Turn Understanding and non-authoritative model boundary.
3. Chat-first PostgreSQL runtime composition and staged SQLite retirement.
4. Structured-plus-vector retrieval projection and Memory Use authority.
5. System-owned procedural Memory publication boundary.
6. Chat-first integration of ADR 0017's accepted risk-based control rules.

## Acceptance Criteria

1. The specification and required ADRs are approved before implementation.
2. Mounted Chat creates and continues multiple owner-scoped standalone
   conversations without Workspace or SQLite.
3. Every accepted user message commits exactly one durable extraction intent in
   the same PostgreSQL transaction.
4. Turn Understanding produces only governed typed output and cannot mutate
   Memory.
5. Explicit ordinary actions work inside Chat with source-message provenance and
   committed-result acknowledgment.
6. Every listed Memory family has at least one complete, evaluated vertical
   behavior before the architecture is called complete.
7. Type-specific activation policies enforce the evidence table in this spec.
8. Only eligible active Memory reaches controlled context; current user intent
   overrides soft Memory.
9. Background processing is non-blocking, retry-safe, deletion-aware, and
   idempotent by semantic effect.
10. PostgreSQL integration verification runs without required skips.
11. End-to-end evaluation passes every zero-tolerance gate.
12. No mounted runtime module imports or constructs a SQLite repository after
    Stage 7.
13. Legacy data is disposed of or quarantined according to a reviewed inventory;
    it is never auto-activated.
14. Operations documentation proves migration, backup, restore, worker recovery,
    feature rollback, and safe deletion.

## Approval Record

Version 0.1 is in review. Approval authorizes preparation of the required ADRs
and staged implementation plans only. It does not authorize runtime edits,
database migration, SQLite deletion, dependency changes, or Git delivery.

## Changelog

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
5. `docs/architecture/raw-input-codegraph-flow.md`.
