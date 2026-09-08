# Memory Write Pipeline Architecture Design

| Field | Value |
| --- | --- |
| Status | Draft |
| Version | 0.1 |
| Date | 2026-09-07 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Production-oriented conversation and memory write architecture for approximately 1,000 authenticated users |
| Related issue | Repository-owner approved exception: interactive architecture design session on 2026-09-07 |
| Superseded document | None; this proposal may supersede parts of the approved R4-R6 conversation and memory designs only after explicit architecture approval |

## Document State and Approval Boundary

This document is a living design record produced during the repository-owner
grilling session. It records confirmed direction, proposed defaults, rejected
shortcuts, research evidence, and unresolved decisions. `Draft` means that no
runtime, schema, storage, dependency, migration, or user-interface change is
authorized.

The repository owner has not yet answered the complete decision frontier. Items
marked `Proposed` are recommendations, not approved behavior. ADRs will be
prepared only after this architecture design reaches `In Review` and receives
explicit architecture approval.

### Living-spec recording policy

This file is the canonical living specification for the Write Memory design
session. Every material question and resulting design choice must be recorded
here before implementation planning. A decision entry is incomplete unless it
captures:

1. the problem and decision identifier;
2. the viable alternatives considered;
3. the selected approach and current approval state;
4. the reason for selecting it;
5. positive and negative trade-offs;
6. dependencies on earlier decisions;
7. consequences for contracts, data, runtime, privacy, operations, migration,
   and verification;
8. remaining uncertainty or the evidence required to reopen the decision.

Questions may remain in the open frontier, but they must not be silently
resolved by implementation. Confirmed decisions remain linked through the
decision dependency map below so a reader can reconstruct how the target system
works rather than reading a disconnected list of choices.

### How to read this specification without treating it as one backlog

This document contains three different horizons. A confirmed target decision is
not automatically part of the next implementation change:

| Horizon | Meaning | Reader action |
| --- | --- | --- |
| Current focus | The one capability and learning objective being designed or implemented now | Understand, test, review, and complete this before expanding scope |
| Next capability | The smallest dependent vertical slice unblocked by current evidence | Keep visible, but do not implement early |
| Recorded target constraint | A production decision that prevents future architectural dead ends | Preserve in interfaces and tests only when relevant; do not build it merely because it is documented |

The architecture is intentionally more complete than any one implementation
plan. Implementation plans must select one bounded capability slice and list
every target decision that is explicitly deferred. No plan may translate the
entire decision ledger into one change set.

## Summary

The target is a production-oriented, ChatGPT-like conversation experience in
which an authenticated user can start a standalone chat immediately. A
workspace or project is optional and deferred. The memory system must provide
continuity, cross-conversation personalization, and reusable experience while
keeping conversation summaries, semantic profile memory, episodic memory,
authoritative product state, travel knowledge, and evaluation evidence
separate.

The target write architecture is governed rather than fully autonomous:

```text
source event
-> eligibility and secret filtering
-> immutable evidence
-> structured candidate extraction
-> deterministic validation and sensitivity escalation
-> related-assertion lookup
-> semantic relationship classification
-> deterministic conflict resolution
-> policy decision or user action
-> atomic assertion/version/evidence commit
-> transactional index outbox
-> background derived indexing
-> privacy-safe trace and evaluation
```

The write path prioritizes precision, provenance, scoped authority, atomicity,
selective forgetting, and recovery over maximum recall. Model output may
propose candidates and classify semantic relationships, but it does not own
authorization, sensitivity downgrades, lifecycle transitions, or persistence.

## Current-state Evidence

The current repository provides useful foundations but does not implement this
target architecture:

1. `backend/memory/models.py` owns candidates, records, scope, sensitivity,
   lifecycle vocabulary, provenance fields, and selection traces.
2. `backend/memory/extraction.py` contains a deterministic rule-based extractor
   over controlled Vietnamese and English marker phrases.
3. `backend/memory/policy.py` separates extraction from candidate disposition.
4. `backend/memory/promotion.py` separates candidate assessment from storage.
5. `backend/memory/repository.py` defines the memory persistence interface, and
   `backend/memory/sqlite_repository.py` is the current local adapter.
6. `backend/orchestration/conversation_orchestrator.py` performs feature-gated
   answer-time memory selection for bound conversations.
7. `backend/privacy/deletion.py` hides deletion-requested workspaces and
   transitions active memory records.
8. R5 and R6 offline evaluation measure candidate extraction, promotion,
   retrieval, scope, correction, secret, and deletion-retrieval gates.

Material gaps relevant to this proposal:

1. A standalone chat is unbound and not persisted. `Conversation` currently
   requires a workspace and inherits owner scope from it.
2. Extraction and promotion are manually triggered; ordinary chat messages do
   not close an automatic write loop.
3. `trace_visibility` controls both evaluation eligibility and memory candidate
   acceptance, coupling two different consent decisions.
4. Correction targeting has no canonical semantic key and can supersede
   unrelated records in the same scope.
5. Duplicate detection is tied to one source candidate rather than semantic
   assertion identity.
6. Record creation, supersession, promotion-run persistence, and derived-index
   signaling are not one atomic transaction.
7. `NEEDS_USER_ACTION` has no complete user-facing transition path.
8. Deletion does not yet prove erasure or invalidation of every candidate, run,
   trace, summary, index, cache, or inactive record carrying derived data.
9. Online chat does not persist `MemorySelectionTrace`; current callers are
   evaluation and repository tests.
10. Retrieval is lexical only, and created records currently receive no expiry.

## Users

1. An authenticated traveler who starts and continues standalone conversations.
2. The same traveler returning in a separate conversation and expecting useful
   continuity and personalization.
3. A future project/workspace user; workspace scope is reserved but inactive in
   the first target increments.
4. Operators who investigate memory quality, privacy, cost, latency, retries,
   and deletion.
5. Repository owners who approve model, policy, schema, rollout, and evaluation
   changes.

Guest identity and anonymous durable memory are excluded from the current
target.

## Problem Statement

The current prototype proves candidate extraction, policy, promotion, and
lexical retrieval, but it does not offer a production-shaped write system. It
cannot yet create standalone persistent chats, aggregate independent evidence,
represent canonical facts and versions, distinguish conflicts from scoped
exceptions, classify contextual sensitivity safely, commit related mutations
atomically, prevent stale jobs from resurrecting deleted data, or let users
inspect and operate their memories.

A persistent write error has a larger blast radius than one incorrect answer:
the error can influence many later conversations. Retrieval improvements cannot
compensate for incorrect, over-broad, sensitive, unscoped, or stale records.

## Goals

1. Preserve conversational continuity without replaying unbounded raw history.
2. Personalize answers across conversations from governed semantic memory.
3. Retain high-value experience and outcomes as episodic memory.
4. Let an authenticated user start a persistent chat without first creating a
   workspace.
5. Keep user, conversation, and future workspace scopes explicit.
6. Keep source evidence immutable and every derived object traceable.
7. Make semantic identity, cardinality, authority, time, and conflict behavior
   deterministic and testable.
8. Keep secrets and prohibited payment/authentication data out of memory,
   embeddings, logs, and evaluation artifacts.
9. Support background extraction without blocking chat latency.
10. Make writes idempotent, transactional, retryable, and deletion-safe.
11. Provide user operations to inspect, correct, delete, and control memory;
    exact sequencing remains under discussion.
12. Define component and end-to-end evaluation gates before default-on
    auto-promotion.
13. Support approximately 1,000 authenticated users without introducing a
    distributed event platform or graph database before evidence requires one.

## Non-goals

1. A workspace is not required for standalone chat in the first target flow.
2. Workspace collaboration, membership, and project-scoped memory behavior are
   not defined here; the vocabulary may be reserved for compatibility.
3. Travel knowledge does not become user memory.
4. Current trip dates, budget, itinerary, and booking state do not become
   authoritative user-profile memory.
5. The model does not write SQL or directly activate, update, supersede, or
   delete memory records.
6. A graph database, Kafka, a dedicated vector database, and learned promotion
   policies are not default requirements for approximately 1,000 users.
7. A raw evidence score is not represented as a calibrated probability.
8. Passing retrieval mechanics does not imply that personalization quality
   passed.

## Target Memory Taxonomy

| Logical layer | Persistence | Ownership | Purpose |
| --- | --- | --- | --- |
| Working context | One request only | Context assembly | Bounded inputs selected for one model call |
| Conversation summary | Durable, versioned, rebuildable | Conversation module | Compress one conversation while preserving unsummarized recent turns |
| Semantic profile memory | Durable, versioned | Memory module | Stable facts and preferences usable across conversations |
| Episodic memory | Durable selected spans | Memory module | Reusable situations, actions, outcomes, reasons, and feedback |
| Product state | Durable and authoritative | Conversation now; workspace/planner when applicable | Conversation identity and future trip/project state |
| Travel knowledge | Durable external corpus | RAG/knowledge module | Cited external travel facts |
| Evaluation trace | Bounded evidence | Evaluation/observability module | Explain write, selection, answer, quality, safety, latency, and cost |

Only conversation summary, semantic profile memory, and episodic memory are
durable memory types. Working context is assembled and discarded. Product
state, travel knowledge, and evaluation traces remain separate ownership
domains.

## Confirmed and Proposed Decision Ledger

| ID | Decision | State | Rationale | Accepted cost or risk |
| --- | --- | --- | --- | --- |
| D01 | Target continuity, personalization, and learning from experience together | Confirmed direction | These are the three product outcomes requested by the repository owner | Each outcome requires separate evaluation and may not ship in the same increment |
| D02 | Design all three durable memory types, with separate implementation plans and quality gates | Confirmed direction | Preserves one coherent architecture without one unreviewable change set | More governance artifacts and staged migration work |
| D03 | User messages and later verified product events may propose memory; assistant, tool, and external content cannot directly create user memory | Confirmed direction | Prevents authority laundering and memory poisoning | Some useful facts require explicit user evidence or verified product events |
| D04 | Use governed hybrid automation rather than review-everything or unconstrained autonomous writes | Confirmed direction | Minimizes interruption while retaining policy and safety | Requires evidence aggregation, category-specific gates, and rollback controls |
| D05 | `POST /chat` without `conversation_id` creates and persists a standalone conversation | Confirmed direction | Delivers ChatGPT-like immediate chat | Changes the R4 compatibility and persistence contract |
| D06 | Conversation owns `owner_user_id` directly and carries optional `workspace_id` | Confirmed direction | Supports authenticated standalone conversations without a hidden workspace | Requires schema migration and owner backfill for existing conversations |
| D07 | Keep `user`, `conversation`, and reserved `workspace` scope vocabulary; execute user and conversation scopes first | Confirmed direction | Avoids another taxonomy migration while deferring workspace behavior | Reserved values require tests preventing premature use |
| D08 | Remove guest/anonymous durable memory from current scope | Confirmed direction | Cross-conversation memory requires authoritative identity | Anonymous continuity is unavailable |
| D09 | Implement Semantic Profile, then Conversation Summary, then Episodic Memory | Confirmed direction | Semantic facts provide the clearest first correctness surface | Full product promise arrives incrementally |
| D10 | Normal authenticated chats read and contribute to user memory by default | Confirmed direction | Cross-conversation personalization otherwise has no effect | User control and transparent deletion become release requirements |
| D11 | Keep read and write flags internally separate even when both default on | Proposed | Enables evaluation, rollback, and future temporary/no-learning modes | Adds configuration combinations to test |
| D12 | User memory inspection, correction, deletion, and controls belong in the target implementation | Confirmed direction | The repository owner reversed the earlier deferral after reviewing privacy, trust, and UX implications | UI, command, authorization, deletion, and lifecycle scope increase |
| D13 | Target approximately 1,000 authenticated users | Confirmed direction | Provides an explicit capacity planning horizon | Production claims still require measured SLOs and operational evidence |
| D14 | Support Vietnamese and English first | Confirmed direction | Matches current product content and controlled extractor evidence | Open multilingual support is deferred |
| D15 | Use hybrid episodic qualification: deterministic outcome events plus background model extraction for residual cases | Confirmed direction | Balances precision, recall, auditability, latency, and cost | Requires event contracts, model evaluation, deduplication, and background jobs |
| D16 | Keep ambiguous conflict pending until relevant rather than interrupting unrelated work | Confirmed direction | Preserves user focus and avoids destructive guessing | Some records remain unresolved and require retrieval-time handling |
| D17 | Update conversation summaries on token threshold, idle, or before truncation | Confirmed direction | Avoids per-message cost and prevents context overflow | Summary freshness and race handling must be observable |
| D18 | Use deterministic guards, structured model extraction, then deterministic validation/policy | Confirmed direction | Uses model semantics without granting persistence authority | More stages, versions, and failure modes |
| D19 | Treat `3 evidence events across 2 conversations` as a temporary diversity floor, not calibrated confidence | Confirmed direction | Raw counts ignore source strength, negative evidence, correlation, scope, and time | Requires an evidence ledger and later calibration |
| D20 | Use sensitivity bands `ordinary_personal`, `contextually_sensitive`, `restricted`, and `prohibited_secret` | Confirmed direction | Separates ordinary owner-linked data from heightened and prohibited risks | Classification is contextual and requires escalation rules |
| D21 | Model canonical semantic memory as evidence, assertion, and immutable versions | Confirmed direction | Separates source truth, stable identity, and changing values | Adds schema and query complexity |
| D22 | Let a model classify semantic relation; use a deterministic resolver for lifecycle mutations | Confirmed direction | A model can understand paraphrase, while authority, time, scope, and cardinality remain testable | Relationship errors must be contained and measured |
| D23 | Use PostgreSQL as lifecycle source of truth, a transactional outbox, database-backed workers, GIN full-text first, and optional pgvector projection later | Confirmed direction | Sufficient for the 1,000-user target with lower operational complexity than Kafka or a separate vector service | Replaces the local-only SQLite adapter and requires migration/operations work |
| D24 | Implement the canonical-key registry as a versioned, code-reviewed artifact projected into PostgreSQL | Confirmed direction | Keeps semantic identity reviewable and deploy-versioned while allowing efficient runtime queries | Registry changes require code review, migration discipline, and evaluation-version updates |
| D25 | Define `single`, `set`, or `structured` cardinality per canonical key | Confirmed direction | Conflict and merge behavior differ by domain field and cannot be one global rule | The registry and resolver must test each cardinality class |
| D26 | Define authority as a per-key matrix instead of one global numeric rank | Confirmed direction | Users own preference truth while verified systems may own transactional status | More policy configuration and per-key tests are required |
| D27 | Build ordinary personal memory first, then user controls, then restricted durable memory | Confirmed direction | Restricted cross-conversation data requires inspection, correction, deletion, purpose, and protected handling | Restricted personalization ships later than ordinary preference memory |
| D28 | Map uncertain or invalid relationship classification to `PENDING_CONFLICT` without destructive mutation | Confirmed direction | Preserves current truth and contains model uncertainty | Pending conflicts require aging, metrics, and later resolution paths |
| D29 | Never infer `accepted` or `success` from silence, chat closure, or topic change | Confirmed direction | Avoids fabricated outcomes and low-quality episodic learning | Some useful but implicit outcomes will not become episodes |
| D30 | Record every material Write Memory design choice in this living spec with alternatives, trade-offs, rationale, dependencies, consequences, and verification impact | Confirmed direction | The repository owner requires the implementation to remain understandable after delivery | The specification grows and must be curated to avoid duplication and contradiction |
| D31 | Limit the first canonical-key catalog to approximately 10-15 core travel keys with a governed extension path | Confirmed direction | A small catalog lets every key receive explicit value, cardinality, sensitivity, authority, conflict, and evaluation contracts | Some useful preferences remain unknown/quarantined until the catalog is deliberately extended |
| D32 | Store a typed normalized value as canonical data and a separate display text for model and user presentation | Confirmed direction | Typed values make equality, conflict, filtering, migration, and evaluation deterministic without forcing user-facing language into enums | Normalization and display rendering become versioned responsibilities |
| D33 | Identify a semantic assertion by owner, scope type/id, canonical key, subject, and condition fingerprint | Confirmed direction | Semantic identity must not depend on phrasing or embedding similarity | Every field needs normalization and uniqueness semantics |
| D34 | Define structured condition fields per canonical key in the registry | Confirmed direction | Conditions and exceptions must be comparable and indexable | Free-form nuance outside the schema is held or requires a registry extension |
| D35 | Keep `MemoryCandidate` immutable and record policy, review, and promotion outcomes as immutable `MemoryDecision` entries | Confirmed direction | Preserves what the extractor proposed and how later actors decided without full event sourcing | Current mutable candidate-status contracts require migration and callers must resolve the latest applicable decision |
| D36 | Use candidate outcomes `INVALID`, `REJECTED`, `SHADOW`, `HELD_SENSITIVE`, `PENDING_CONFLICT`, `ROUTED_TO_PRODUCT_STATE`, and `PROMOTED` | Confirmed direction | Separates schema/extractor failure, policy rejection, observation, holds, routing, and durable promotion | More vocabulary and transition tests than one mutable accepted/rejected flag |
| D37 | Use memory-version states `ACTIVE`, `SUPERSEDED`, `EXPIRED`, `RETRACTED`, `DELETION_REQUESTED`, and `DELETED` | Confirmed direction | Supersession, time expiry, epistemic withdrawal, and privacy deletion have different meaning and recovery | Read, delete, migration, and reporting paths must handle every state explicitly |
| D38 | Provide dedicated Memory Manager UI and natural-language memory commands through one `MemoryCommandHandler` | Confirmed direction | Gives discoverable controls and conversational convenience without duplicating policy or persistence logic | Both surfaces and all command variants require consistent authorization, confirmation, error, and accessibility behavior |
| D39 | Require confirmation for every user-initiated memory action | Superseded by D75-D78 | This was the repository owner's initial safety choice | Replaced before implementation because it created unnecessary friction for clear, low-risk, reversible actions |
| D40 | Conversation deletion cascades to summaries and episodes, invalidates sole-source inferred memory, recomputes multi-source assertions, preserves only independently confirmed saved memory, and blocks stale jobs | Confirmed direction | Prevents deleted conversations from continuing to influence personalization while respecting independent user intent | Requires provenance dependency tracking, recomputation, deletion epochs, and derived-index verification |
| D41 | Store immutable conversation-summary versions plus an active pointer | Confirmed direction | Enables rollback, rebuild, source-range audit, and safe use with unsummarized messages | Consumes additional storage and requires summary-version lifecycle management |
| D42 | Represent one episodic record as a selected source span with typed situation, intent, actions/options, outcome, reason, authority, sensitivity, event time, status, and extractor version | Confirmed direction | One conversation may contain zero or multiple reusable experiences and must not be duplicated wholesale | Episode extraction, span boundaries, structured payloads, and retention require separate evaluation |
| D43 | Use normalized PostgreSQL tables for events, candidates, decisions, evidence, assertions, versions, outbox, summaries, episodes, and deletion evidence | Confirmed direction | Each concept has different identity, lifecycle, constraints, retention, and query behavior | More tables and joins than one generic memory document |
| D44 | Store `owner_user_id` on every owner-scoped memory row and enforce provenance-owner consistency | Confirmed direction | Simplifies authorization, deletion, RLS, partitioning, and incident investigation | Duplicates owner identity and requires composite constraints preventing mismatch |
| D45 | Use typed relational columns for identity, lifecycle, authority, sensitivity, time, and indexes, with registry-validated JSONB for typed value and condition payloads | Confirmed direction | Preserves queryable invariants while supporting different value shapes across keys | Requires schema validation and controlled JSON migrations |
| D46 | Preserve prefixed text identifiers such as `mem_` and `mc_` during the migration | Confirmed direction | Maintains API, logs, fixtures, and operator recognition without dual public/internal identities | Text keys are larger and less locality-friendly than native ordered UUIDs, accepted for the stated scale |
| D47 | Enforce assertion identity and one applicable current single-valued version with PostgreSQL uniqueness/exclusion constraints | Confirmed direction | Database invariants close races that Python pre-checks cannot | Constraint design and temporal overlap semantics require careful migrations and tests |
| D48 | Use PostgreSQL `READ COMMITTED`, assertion-row locking, database constraints, and bounded retry rather than global `SERIALIZABLE` or distributed locks | Confirmed direction | Serializes only contended assertion slots and keeps concurrency understandable | Callers must handle unique/serialization conflicts and re-resolve from current state |
| D49 | Expose one transaction-scoped `MemoryUnitOfWork` and `apply_memory_change` seam | Confirmed direction | Keeps transaction ownership in one deep module and prevents routes/workers from composing partial writes | The current repository interface must be reshaped and tests must cross the unit-of-work seam |
| D50 | Use a PostgreSQL transactional outbox as the initial asynchronous queue | Confirmed direction | Commits canonical state and durable work intent atomically without Kafka or Redis coordination | Database cleanup, leases, retries, and queue observability become application responsibilities |
| D51 | Accept at-least-once delivery and require idempotent consumers | Confirmed direction | External model calls and worker crashes make end-to-end exactly-once unrealistic | Every handler needs durable idempotency identities and replay tests |
| D52 | Run work in parallel across independent owners/conversations while serializing summary, episode, and semantic mutation by their natural identity | Confirmed direction | Preserves throughput without racing on one conversation or assertion | Partition keys, leases, and hot-key behavior must be monitored |
| D53 | Classify failures as transient, permanent, or uncertain; use bounded exponential backoff with jitter and dead-letter terminal handling | Confirmed direction | Avoids infinite retry and distinguishes operator action from model uncertainty | Exact budgets and recovery procedures require SLO decisions |
| D54 | Update full-text/vector indexes asynchronously from outbox events and revalidate owner, lifecycle, and version against PostgreSQL before use | Confirmed direction | Keeps canonical lifecycle atomic and makes search projections rebuildable | Read paths must tolerate and measure temporary index lag |
| D55 | Use SQLAlchemy Core, Alembic, a PostgreSQL driver, and connection pooling rather than a full ORM or handwritten migration system | Confirmed direction | Fits existing domain models while adding transaction composition, schema history, and pooling | Introduces dependencies and requires team familiarity with Core and Alembic |
| D56 | Enforce authorization in application modules and PostgreSQL row-level security | Confirmed direction | Provides defense in depth against a missing owner predicate | Requires safe tenant-context setup, pooling reset discipline, and fail-closed RLS tests |
| D57 | Use PostgreSQL in development, integration testing, and production; retain SQLite only as a migration-era legacy adapter | Confirmed direction | Prevents environment-specific SQL, locking, migration, and transaction behavior from drifting | Local setup becomes heavier and tests require isolated PostgreSQL state |
| D58 | Inspect existing R5/R6 SQLite data before choosing disposal or quarantined-evidence import; never migrate it directly to active V2 memory | Confirmed direction | Legacy rows lack the new key, authority, evidence, sensitivity, and conflict semantics | Migration cannot be finalized until the data inventory is performed |
| D59 | Use an initial capacity envelope of 1,000 registered accounts, 200 daily active users, 50 concurrent chat turns, 10 steady and 50 burst background jobs per second | Confirmed starting target | Converts the ambiguous 1,000-user goal into a load-testable planning assumption | Values are not production claims and must be revised from observed traffic |
| D60 | Persist source events per message but debounce normal extraction by conversation idle, maximum wait, or unsummarized threshold; explicit memory actions use their own confirmed path | Confirmed direction | Reduces model cost and duplicate extraction without starving continuously active conversations | Introduces scheduling state and delayed memory availability |
| D61 | Use outbox states `PENDING`, `LEASED`, `SUCCEEDED`, `DEAD_LETTER`, and `CANCELLED` | Confirmed direction | Represents claiming, success, retry exhaustion, and deletion/supersession cancellation explicitly | More transitions and operational queries than a processed boolean |
| D62 | Claim a job in a short transaction with `lease_owner` and `lease_until`, then call models outside the transaction and revalidate before commit | Confirmed direction | Avoids holding database transactions and locks during external latency | Requires lease expiry, duplicate work tolerance, and stale-result rejection |
| D63 | Configure retry policy per job type and failure class | Confirmed direction | Database conflicts, provider throttling, invalid schemas, deleted sources, and semantic uncertainty require different recovery | More policy configuration and testing |
| D64 | Use separate typed handlers on one shared outbox/lease runtime before splitting deployments | Confirmed direction | Preserves module-specific contracts and metrics without premature service sprawl | One process initially carries several handler dependencies |
| D65 | Put structured extraction behind a `MemoryExtractionModel` interface independent from RAG generation | Confirmed direction | Pins schema, prompt, model, timeout, token, and provider evidence at the memory seam | Adds a model adapter and separate evaluation surface |
| D66 | When the extraction model is unavailable, let chat succeed and retry background work; do not silently fall back to lower-quality auto-promotion | Confirmed direction | Availability degradation cannot weaken durable-memory correctness | Memory freshness is delayed during provider outages |
| D67 | Permit one bounded structured-output repair attempt, then record `INVALID` instead of salvaging partial payloads | Confirmed direction | Prevents missing sensitivity, scope, provenance, or key fields from becoming durable state | Some recoverable partial outputs are discarded and model cost may double once |
| D68 | Persist provider, model, prompt, output schema, extractor, and policy versions on derived artifacts | Confirmed direction | Makes replay, comparison, rollback, and re-evaluation possible after model change | Increases metadata and migration obligations |
| D69 | Apply deterministic filtering, conversation debounce, new-range-only input, token bounds, idempotent caching, quotas, priority, and per-version cost telemetry | Confirmed direction | Controls background model cost without placing extraction on the chat hot path | Quotas and delayed low-priority work can reduce recall/freshness |
| D70 | Keep canonical decision/evidence trace in the memory transaction and fail closed when it cannot persist; external metrics/log export fails open | Confirmed direction | A durable memory must have a durable reason, while monitoring outages must not corrupt valid state | Canonical trace availability becomes part of the write-path availability target |
| D71 | Deletion increments a deletion epoch, cancels pending work, and requires every leased worker to recheck the epoch before commit | Confirmed direction | Prevents background resurrection while preserving content-free cancellation evidence | Every handler must carry and validate deletion context |
| D72 | Prioritize deletion, explicit confirmed actions, truncation-blocking summary, normal extraction, episodic residual extraction, then consolidation/re-embedding, with starvation protection | Confirmed direction | Aligns capacity with safety and user-visible urgency | Scheduler complexity and fairness metrics are required |
| D73 | Adopt the proposed initial hot-path, background freshness, queue-age, deletion-cleanup, and zero-leak engineering objectives | Confirmed starting target | Gives load, recovery, and observability work testable budgets before real traffic exists | Budgets are provisional and may be wrong until measured |
| D74 | Execute the architecture through learning-oriented vertical slices, beginning with one pure-domain canonical key before PostgreSQL, workers, model extraction, or broad UI | Confirmed direction | Proves the core semantic model and teaches the implementation through small tests before production mechanics multiply the state space | Delays visible breadth and requires resisting pressure to implement already-recorded target constraints early |
| D75 | Commit an explicit low-risk `remember` request directly after deterministic validation and show a small application-owned `Memory Saved` event | Confirmed direction | The user command already expresses intent; a second confirmation is redundant | Incorrect command classification would commit without a second prompt, so eligibility, key, value, scope, and sensitivity checks remain hard requirements |
| D76 | Keep memory mutation UI state separate from the generated assistant response | Confirmed direction | The application, not the model, knows whether the canonical transaction committed | The UI must reconcile two independent outputs and never render saved state from model text |
| D77 | Do not persist contextually sensitive, restricted, or prohibited information as durable memory in the focused scope and do not interrupt the user to request permission | Confirmed direction | Simplifies the first safety boundary and avoids review friction before protected handling exists | Cross-conversation accessibility, allergy, exact-location, and other sensitive personalization are unavailable |
| D78 | Require preview and one-time confirmation only for bulk deletion and conversation-to-user scope expansion | Confirmed direction | These operations have broad or widened future impact that merits a second step | Confirmation-token lifecycle remains necessary for a small high-risk subset |
| D79 | Resolve clear duplicate, correction, temporal update, or scoped exception deterministically; keep unclear same-key contradictions as `PENDING_CONFLICT` and ask only when the preference becomes relevant | Confirmed direction | Preserves current-task focus and prevents destructive guessing | Pending conflict needs expiry/aging and can delay profile convergence |
| D80 | Treat `SHADOW` as a valid low-risk candidate/evidence state that lacks promotion authority; invalid, rejected, sensitive, prohibited, and ambiguous-conflict outcomes remain distinct | Confirmed direction | Enables evaluation and evidence accumulation without influencing answers | Shadow storage, retention, re-evaluation, and later promotion gates add lifecycle work |

## Decision Dependency Map

The decisions compose in this order:

| Layer | Depends on | Governing decisions | Resulting responsibility |
| --- | --- | --- | --- |
| Product entry | Product goals and authenticated identity | D01, D05, D06, D08, D13 | A user starts a persistent owned conversation without a required workspace |
| Scope | Direct conversation ownership | D06, D07, D10 | User and conversation scopes execute now; workspace remains reserved |
| Memory taxonomy and delivery | Product outcomes and scope | D01, D02, D09, D14, D15, D17 | Semantic, summary, and episodic work share architecture but ship through separate gates |
| Semantic identity | Memory taxonomy | D21, D24, D25 | Evidence supports one stable assertion whose immutable values follow registry cardinality |
| Evidence and authority | Semantic identity and trusted sources | D03, D19, D26 | Independent positive and negative evidence is aggregated under key-specific source authority |
| Sensitivity and user rights | Identity, evidence, and product UX | D04, D12, D20, D27 | Ordinary memory may automate; restricted memory waits for protected user-control capability; secrets are prohibited |
| Semantic conflict | Key, cardinality, evidence, authority, scope, and time | D16, D21, D22, D25, D26, D28 | A bounded classifier labels meaning; a deterministic resolver produces a typed non-destructive change set |
| Episodic qualification | Trusted events, sensitivity, and outcome evidence | D03, D15, D18, D29 | Deterministic events and a background model find episodes, but no outcome is invented from silence |
| Runtime and persistence | All domain and policy decisions | D18, D21, D22, D23, D24-D29 | PostgreSQL commits canonical state and an outbox atomically; workers create rebuildable projections |
| Rollout and understanding | Evaluation and repository governance | D02, D19, D23, D30 | Each capability has a separate approved plan, quality gate, rollback, and documented rationale |
| User operation | Semantic identity, user rights, and deletion | D12, D27, D35-D40 | UI and natural-language commands share one handler; immutable decisions and explicit confirmations lead to the same atomic commit path |
| Summary and episode records | Conversation ownership and trusted outcomes | D15, D17, D29, D41, D42 | Summaries version one conversation; episodes select only evidence-bearing spans with verified outcomes |
| Relational integrity | Semantic identity, lifecycle, and tenancy | D43-D49 | Normalized owner-scoped rows, typed columns, JSONB payloads, constraints, row locks, and one unit of work protect canonical mutations |
| Asynchronous execution | Relational integrity and failure policy | D50-D54 | An outbox provides at-least-once work; idempotent partitioned workers retry boundedly and update rebuildable indexes |
| Database operations | Capacity and tenant boundary | D55-D58 | SQLAlchemy Core/Alembic target PostgreSQL in every active environment with app authorization plus RLS and an evidence-gated legacy migration |

Reading the table from top to bottom yields the runtime dependency direction:
identity constrains scope; scope and taxonomy constrain semantic keys; keys and
cardinality define candidate comparison; evidence and authority constrain
promotion; sensitivity constrains automation; the conflict resolver produces a
change set; PostgreSQL atomically commits it; workers update derived indexes;
evaluation decides whether a gated behavior may advance.

## Current Focus and Learning Path

### Objective correction

The immediate objective is not to implement every confirmed production
decision. It is to prove and understand the smallest unit on which the rest of
the architecture depends:

> one canonical semantic preference key moving from user evidence through
> deterministic resolution into a versioned assertion, with tests explaining
> every state transition.

PostgreSQL, outbox workers, model extraction, summary, episodic memory, broad
key catalogs, and production UI are recorded target constraints. They are not
prerequisites for learning or proving the pure domain behavior.

### Learning slice L0: read the existing implementation

Trace one controlled example through the current source without editing:

```text
source message
-> RuleBasedMemoryExtractor
-> MemoryPolicy
-> MemoryCandidate
-> MemoryPromotionPolicy
-> MemoryRecord
-> MemoryRetrievalService
-> memory context
```

The learner must be able to explain which module owns extraction, policy,
promotion, persistence, retrieval, and context, and identify where current
correction and transaction behavior becomes unsafe.

### Learning slice L1: one pure-domain key

Use only:

```text
canonical key: travel.preference.hotel_atmosphere
cardinality: single
values: quiet | lively | central | secluded
sensitivity: ordinary_personal
allowed scope: user and conversation
authority: explicit save, explicit statement, repeated inference
```

No database, HTTP route, external model, worker, or UI belongs in this slice.
Tests construct values directly and prove:

1. a new preference produces `ADD`;
2. a paraphrase of the same normalized value produces `REINFORCE`;
3. a stronger explicit correction produces `SUPERSEDE`;
4. a weaker inference cannot supersede an explicit version;
5. a conversation-specific value produces `ADD_EXCEPTION` rather than deleting
   the user default;
6. an ambiguous equal-authority contradiction produces `PENDING_CONFLICT`;
7. the change set contains all evidence and version transitions but performs no
   storage side effect.

The educational output is the ability to explain `Evidence -> Assertion ->
Version -> ChangeSet` from tests, not merely a green test count.

### Learning slice L2: expand the registry

Add one example of each cardinality and sensitivity behavior:

```text
single: travel.preference.travel_pace
set: travel.preference.preferred_cuisines
structured/conditional: travel.preference.seat
restricted: travel.accessibility.mobility (held, never promoted in this slice)
prohibited: authentication/payment secret (rejected before candidate)
```

This proves that the registry removes conditionals from generic resolver code.
Only after L1 and L2 pass should the first canonical catalog be completed.

### Capability slices after the pure domain

| Slice | Capability demonstrated | Production decisions introduced | What the learner should understand |
| --- | --- | --- | --- |
| L3 | Persist one explicit semantic change | PostgreSQL tables, unit of work, constraints, migration | Why atomic evidence/assertion/version/outbox state matters |
| L4 | Operate memory as a user | Command handler, confirmation, Memory Manager, deletion | How UI and natural language share policy without duplicating mutation logic |
| L5 | Produce shadow candidates asynchronously | Event capture, outbox, lease, retries, model adapter, sensitivity | Why at-least-once delivery and idempotency are paired |
| L6 | Aggregate repeated evidence | Independence, positive/negative evidence, calibration dataset | Why `3/2` is a diversity floor rather than probability |
| L7 | Maintain conversation continuity | Summary versions, scheduling, source ranges, fallback | How derived summaries remain rebuildable and non-authoritative |
| L8 | Learn from outcomes | Deterministic episodic events, residual model extraction, span provenance | Why a conversation is an envelope rather than automatically an episode |
| L9 | Improve retrieval | GIN baseline, optional pgvector experiment, canonical revalidation | Why an index is a projection rather than source of truth |
| L10 | Prove the 1,000-user target | Load, failure injection, recovery, privacy, deletion, cost, SLO evidence | Why production readiness is measured behavior, not architecture vocabulary |

Each slice receives its own specification or bounded approved scope,
implementation plan, test-first implementation, review, fresh verification,
and owner handoff. The next slice does not begin merely because its target
decision already appears in this architecture document.

## Semantic Key Expansion Phases

This table is the canonical expansion roadmap for semantic keys. It does not
authorize a later phase merely because the earlier phase passes; every phase
receives its own bounded specification, implementation plan, evaluation gate,
and repository-owner approval.

| Phase | Scope | Why this order | Accepted trade-off | Entry gate | Exit evidence |
| --- | --- | --- | --- | --- | --- |
| 1 — One complete key | `travel.preference.hotel_atmosphere` with `quiet`, `lively`, `central`, `secluded`; user/conversation scope; ordinary personal only | Proves the complete trigger, extraction, normalization, policy, conflict, version, persistence, Shadow, UI-event, and evaluation flow with one understandable domain | Product coverage is intentionally narrow | Focused spec, ADRs, evaluation, and child plans approved | Add/reinforce/supersede/exception/pending/reject/no-op, atomicity, idempotency, isolation, safety, and learning walkthrough pass |
| 2 — Cardinality representatives | Add one single-valued key, one set-valued key, and one structured/conditional key; proposed examples are travel pace, preferred cuisines, and seat preference | Proves the registry actually contains per-key differences instead of hiding key-specific conditionals in generic resolver code | Still not a complete travel preference catalog | Phase 1 change set reviewed and focused gates pass | Single replacement, set member add/remove, condition exception, normalization, and migration tests pass |
| 3 — Core travel registry | Expand through a reviewed catalog of approximately 10-15 ordinary-personal travel keys | Adds useful personalization only after the generic model is proven across cardinality classes | Each new key requires labels, normalizers, authority, sensitivity, conflict, bilingual fixtures, and maintenance | Phase 2 registry/resolver architecture passes and the catalog/data-dictionary spec is approved | Per-key and aggregate extraction/policy/conflict gates pass with no hard safety regression |
| 4 — Sensitive/restricted capability | Introduce only separately approved protected categories such as accessibility or allergy when purpose and product value justify them | Sensitive persistence requires controls beyond ordinary preference memory | Delivery is delayed; until then sensitive facts may help only inside the current conversation and are not durable | Memory Manager, inspect/correct/delete/disable, protected storage, retention, encryption, and threat-model gates pass | Explicit-purpose consent, access, erasure, no-prompt/no-inference rules, leakage tests, and category-specific evaluation pass |

Phase 1 is the only semantic-key implementation currently authorized by the
approved focused plan. Phases 2-4 are recorded target work and remain outside
the current change set.

## Evidence Aggregation for Inferred Preferences

### Problem

A fixed count such as three supporting events from two conversations is easy to
explain but is not a calibrated confidence estimate. Evidence can be weak,
correlated, duplicated, stale, opposed, or derived from a source without user
authority.

### Proposed evidence record

```text
evidence_id
owner_user_id
conversation_id
source_event_id
source_message_id
canonical_key
normalized_value
polarity: support | oppose | neutral
source_type
authority
event_time
ingestion_time
extractor_version
policy_version
sensitivity_band
context_fingerprint
```

### Proposed aggregation

```text
evidence_score = aggregate(
  authority_weight,
  source_reliability,
  independence_factor,
  context_diversity,
  recency_or_validity,
  positive_and_negative_polarity
)
```

The score is an explainable policy feature, not a probability. Correlated
events share a capped contribution. Assistant repetition, model paraphrase, and
multiple candidates from one source do not create independent user evidence.

### Alternatives and trade-offs

| Alternative | Benefits | Costs | Proposed disposition |
| --- | --- | --- | --- |
| Fixed `3/2` threshold | Simple, deterministic, easy to test | Uncalibrated; treats weak and strong evidence equally | Keep only as a shadow/early-rollout minimum diversity gate |
| Weighted evidence ledger | Explainable; supports source, authority, polarity, time, and diversity | Weights remain heuristic until outcomes exist | Recommended initial production design |
| Beta-Binomial or Bayesian posterior | Can produce an interpretable posterior under suitable assumptions | Independence and exchangeability assumptions are often false | Consider for narrowly defined binary keys after evidence semantics stabilize |
| Supervised promotion classifier | Learns feature interactions | Requires enough labeled outcomes, drift controls, and rollback | Defer until the deterministic system produces trustworthy labels |
| Model self-reported confidence | Cheap extra feature | Not calibrated and vulnerable to prompt/model drift | Never use as the sole gate |

### Proposed rollout

1. Record evidence and outcomes while inferred candidates remain shadow-only.
2. Evaluate precision, false-promotion rate, coverage, correction rate, and
   deletion rate by key, language, source, and model/policy version.
3. Calibrate thresholds on user- and time-separated held-out data.
4. Permit auto-promotion only for low-risk keys whose measured precision passes
   an approved gate.
5. Recalibrate when extractor, prompt, policy, or model versions change.

## Sensitive-data Model

Every memory linked to an authenticated owner is personal data. The current
`none` label must not imply non-personal data; the proposed replacement is
`ordinary_personal`, meaning no heightened sensitivity was identified.

### Proposed bands

| Band | Travel examples | Proposed default treatment |
| --- | --- | --- |
| `ordinary_personal` | Hotel style, travel pace, preferred transport, seat preference, language, broad cuisine preference | Governed personalization; explicit low-risk statements may become eligible for auto-promotion |
| `contextually_sensitive` | Exact future dates and locations, live itinerary, accommodation address, named companions, minors, emergency contacts, detailed budget or travel pattern | Prefer conversation scope and limited retention; do not infer into user scope |
| `restricted` | Health, allergy, medication, disability/accessibility, religion, biometrics, passport/government identity, precise financial/loyalty identifiers | No inferred promotion; explicit purpose, protected handling, review, retention, and deletion controls required before durable cross-conversation use |
| `prohibited_secret` | Passwords, OTP/recovery codes, API/OAuth/session tokens, private keys, raw payment credentials, PAN, CVV/CVC, PIN, full-track data | Detect and redact before extraction; never persist, embed, log, or place in evaluation artifacts |

### Contextual escalation

Sensitivity is determined from key, value, explanation, subject, precision,
time, and combinations:

```text
"vegetarian by preference" -> ordinary personal candidate
"kosher because I am Jewish" -> restricted religious inference
"gluten-free because of celiac disease" -> restricted health information
"wheelchair assistance" -> restricted accessibility need without inferring diagnosis
exact hotel + future dates -> contextually sensitive location pattern
```

### Proposed classification algorithm

```text
deterministic secret/DLP detector
-> canonical-key minimum sensitivity
-> contextual structured classifier
-> deterministic escalation policy
-> final sensitivity = highest applicable band
```

A model may escalate sensitivity but cannot downgrade the minimum assigned by a
deterministic detector or the key registry. Prohibited content is rejected
before a candidate, embedding, log field, or model prompt is created whenever
the transport boundary can detect it.

### Alternatives and trade-offs

| Alternative | Benefits | Costs | Proposed disposition |
| --- | --- | --- | --- |
| Rules/regex only | Deterministic and cheap | Misses contextual and indirect disclosure | Use for secrets and hard minimums only |
| Model classifier only | Understands context | Can under-classify, drift, and leak content to a provider | Rejected as sole authority |
| Key-level sensitivity only | Easy to audit | Cannot distinguish preference from health/religion explanation | Rejected as complete solution |
| Layered classification and escalation | Combines deterministic guarantees with semantic context | More implementation and evaluation work | Recommended |

## Semantic Conflict Model

### Conflict is not merely different text

Two items may be:

1. exact or semantic duplicates;
2. compatible members of a set;
3. a true temporal supersession;
4. a narrower scoped or conditional exception;
5. an unresolved contradiction;
6. unrelated despite embedding similarity.

A true conflict requires the same owner and canonical assertion identity,
overlapping scope/condition and effective interval, and incompatible normalized
values. Similarity retrieves comparison candidates; it does not authorize a
lifecycle mutation.

### Proposed canonical model

```text
MemoryEvidence (immutable source observations)
        |
        v
MemoryAssertion (owner + scope + canonical key + condition)
        |
        v
MemoryVersion (immutable value and lifecycle revisions)
```

The key registry defines value schema, cardinality, allowed scopes, minimum
sensitivity, allowed authorities, temporal mode, default retention, and
conflict strategy.

### Proposed algorithm

```text
1. Normalize the candidate key and value.
2. Load active and recent historical assertions for the same owner and key.
3. Filter to overlapping scope, condition, subject, and effective interval.
4. Use deterministic equality and set rules first.
5. When semantic comparison remains necessary, ask the relationship classifier
   for exactly one typed relation:
   SAME | COMPATIBLE | CONTRADICTION | TEMPORAL_UPDATE |
   SCOPE_EXCEPTION | UNRELATED | UNCERTAIN.
6. Validate the relation against key cardinality and allowed transitions.
7. Apply deterministic authority, scope, and temporal precedence.
8. Produce one typed change set:
   ADD | REINFORCE | MERGE_SET_ITEM | SUPERSEDE | ADD_EXCEPTION |
   RETRACT | DELETE | NOOP | PENDING_CONFLICT.
9. Atomically persist evidence, assertion/version changes, candidate outcome,
   policy trace, and index-outbox event.
10. At read time, exclude unresolved or stale versions unless the request asks
    for historical or transition evidence.
```

### Proposed precedence

```text
explicit save or correction
> explicit user statement
> user-confirmed inference
> repeated behavior inference
> single inference
> assistant/tool/external assertion (zero user-preference authority)
```

This ordering is key-specific. A verified booking provider may be authoritative
for booking status, while the user remains authoritative for future travel
preference.

Scope specificity affects selection rather than destructive mutation. A
conversation exception may shadow a user default for that conversation without
superseding the default globally.

The temporal model separates:

1. valid/effective time: when a fact is true in the travel domain;
2. transaction/system time: when the system learned or changed it.

### Conflict examples

| Existing | Candidate | Resolution |
| --- | --- | --- |
| `hotel_atmosphere=quiet` | semantic paraphrase of quiet | `REINFORCE` and attach evidence |
| `preferred_cuisines={japanese}` | `thai` for a set-valued key | `MERGE_SET_ITEM` |
| `hotel_atmosphere=quiet` | explicit "now I prefer lively" in same scope | `SUPERSEDE` with a new version |
| user default `quiet` | conversation-specific `lively` | `ADD_EXCEPTION`; do not supersede user default |
| explicit confirmed `quiet` | weak inferred `lively` | retain confirmed version; hold inference as conflict evidence |
| two same-authority values without correction/time clarity | incompatible value | `PENDING_CONFLICT`; ask only when the preference becomes relevant |

### Alternatives and trade-offs

| Alternative | Benefits | Costs | Proposed disposition |
| --- | --- | --- | --- |
| Latest write wins | Simple and fast | Incorrect for late-arriving history, inference, and scope exceptions | Rejected |
| Model-owned CRUD | Handles language nuance | Non-deterministic destructive authority and weak reproducibility | Rejected |
| ADD-only bank with read-time resolution | Non-destructive and easy to ingest | Ghost/stale facts remain easy to retrieve; read path becomes complex | Viable baseline, not sufficient alone |
| Typed deterministic resolver with model relationship classification | Semantic flexibility plus testable lifecycle authority | Requires key registry, versions, relationship evaluation, and atomic change sets | Recommended |
| Temporal graph as source of truth | Powerful relationship and temporal queries | Operational and evaluation complexity exceeds current measured need | Defer until relational design fails measured multi-hop requirements |

## Episodic Qualification

### Alternatives

| Alternative | Benefits | Costs |
| --- | --- | --- |
| Every conversation becomes an episode | Maximum recall and simple provenance | Duplicates the conversation store, increases privacy footprint, noise, token cost, and retrieval distraction |
| Deterministic product events only | High precision, auditability, and low cost | Misses subtle but useful experience |
| Model salience only | Finds nuanced experiences | Subjective, costly, model-version-sensitive, and vulnerable to invented outcomes |
| Hybrid deterministic events plus background model residual extraction | Balances precision, recall, auditability, latency, and cost | Requires an event vocabulary, worker lifecycle, deduplication, and evaluation |

### Preferred hybrid algorithm

1. Keep conversation messages and verified product events as canonical source
   evidence; do not copy every conversation into an episode.
2. Deterministically qualify high-value events such as explicit acceptance,
   rejection, reason, correction, task success/failure, booking outcome, or
   completed multi-step decision.
3. Run an asynchronous structured model pass over residual conversation spans
   after idle or closure.
4. Require structured `situation`, `intent`, `actions/options`, `outcome`,
   `reason`, `source_message_ids`, and `event_time` fields.
5. Never infer `accepted` or `success` from silence, topic change, or assistant
   assertion.
6. Apply deterministic sensitivity, scope, authority, and provenance policy.
7. Deduplicate on source event, episode type, extractor version, and normalized
   outcome identity.
8. Store a selected span with exact source boundaries; one conversation may
   produce zero, one, or multiple episodes.
9. Route stable facts found inside an episode to semantic evidence rather than
   using the episode as the canonical profile value.

## Components and Dependency Direction

| Module or adapter | Interface responsibility | Viable implementation choices | Selected or proposed design |
| --- | --- | --- | --- |
| Conversation module | Own standalone conversation, owner, optional workspace, messages, ordering, retention | Hidden default workspace; separate standalone entity; optional workspace association | Direct owner plus optional workspace |
| Event capture | Atomically record eligible source events for background processing | Synchronous call; cron scan; database outbox; external broker | Transactional outbox |
| Evidence module | Store immutable support/opposition observations | JSON blob; normalized relational rows; event log | Normalized PostgreSQL rows |
| Key registry | Define canonical key, value schema, cardinality, scopes, sensitivity floor, authority and conflict policy | Code enum; database-editable registry; ontology | Versioned code-reviewed registry projected into storage |
| Extractor | Produce structured candidates only | Rules; structured model; hybrid | Deterministic guards plus structured model extraction |
| Sensitivity classifier | Assign a non-downgradable band | Regex/DLP; key-only; model-only; layered | Layered deterministic minimum plus contextual escalation |
| Relationship classifier | Compare candidate meaning with existing assertions | Deterministic equality only; model classification; embeddings only | Deterministic first, bounded model classification when needed |
| Conflict resolver | Produce typed lifecycle change sets | Latest-wins; model CRUD; ADD-only; typed resolver; temporal graph | Typed deterministic resolver |
| Write policy | Apply versioned promotion and holding rules | Hard-coded branches; declarative table; learned classifier | Versioned deterministic policy with measured thresholds |
| Atomic committer | Persist related lifecycle mutations | Multiple repository methods; one transactional command | One transaction-scoped `apply_memory_change` interface |
| Worker runtime | Claim, retry, defer, and dead-letter jobs | Cron; database queue; Redis queue; Kafka | PostgreSQL-backed worker for the 1,000-user target |
| Canonical store | Own lifecycle and tenant isolation | SQLite; PostgreSQL; document store; graph database | PostgreSQL |
| Search projection | Find related assertions and later serve read-path recall | SQL lookup; GIN full-text; pgvector; external vector store | Key/relational lookup plus GIN first; pgvector after evaluation |
| Trace/evaluation module | Record decisions, versions, latency, cost, failures, and outcomes | Logs only; relational trace; external observability backend | Privacy-safe relational evidence with operational export later |
| Memory Manager | Let users inspect, correct, delete, and configure memory | Chat commands; settings UI; dedicated manager; all three | Dedicated manager plus natural-language commands through one command handler |

Allowed dependency direction:

```text
conversation write
-> event capture interface
-> outbox adapter

worker
-> extractor interface
-> candidate validator
-> sensitivity interface
-> relationship classifier interface
-> write policy and conflict resolver
-> atomic memory repository interface
-> PostgreSQL adapter
-> index outbox

user memory command
-> Memory Manager/application interface
-> same write policy and atomic repository path
```

No route, worker, extractor, or model adapter writes memory tables directly.
Every write path crosses the same policy and atomic commit seam.

## Selected PostgreSQL and Execution Baseline

### Logical tables

| Table | Canonical responsibility | Important constraints |
| --- | --- | --- |
| `memory_events` | Immutable eligible source-event envelope and processing identity | Unique source-event identity; owner and source lifecycle must resolve |
| `memory_candidates` | Immutable structured extractor proposal | Unique extractor-version/candidate identity; no mutable active authority |
| `memory_decisions` | Immutable policy, classifier, confirmation, routing, and promotion decisions | References candidate and actor/version; only allowed outcome vocabulary |
| `memory_evidence` | Immutable support, opposition, or neutral observation for one key/value | Owner/source consistency; deduplicated context fingerprint |
| `memory_assertions` | Stable semantic identity for owner, scope, key, subject, and condition | Unique normalized assertion identity |
| `memory_versions` | Immutable assertion values and lifecycle history | One applicable current version for a single-valued assertion; valid interval constraints |
| `memory_outbox` | Durable work and derived-index intent committed with canonical state | Unique idempotency identity; lease and terminal-state constraints |
| `conversation_summary_versions` | Immutable summaries over explicit message-sequence bounds | One active pointer/version per conversation; non-overstated source range |
| `episodic_records` | Selected experience spans with verified outcomes and provenance | Owner/conversation consistency; source-span and outcome requirements |
| `deletion_ledger` | Privacy-deletion intent, propagation, verification, and completion evidence | Monotonic deletion epoch; no completion before required derived checks |

The table names are descriptive target names, not yet frozen SQL identifiers.
Exact columns, foreign keys, partitioning, indexes, and migration names remain
plan-level only after the schema decisions in later rounds are approved.

### Typed columns and JSONB payloads

Relational columns own fields used for authorization, joins, constraints,
lifecycle, time, and common filtering. Registry-validated JSONB holds values
whose shape legitimately varies by key. This is selected over all-relational
tables, which would require a table or nullable-column matrix per key, and over
all-JSONB storage, which would weaken database constraints and operational
queries.

```text
typed columns:
  owner_user_id, conversation_id, scope_type, scope_id,
  canonical_key, subject_key, condition_fingerprint,
  authority, sensitivity, status,
  valid_from, valid_until, system timestamps, version

registry-validated JSONB:
  normalized_value, structured_condition,
  episodic actions/options, bounded decision metadata
```

Display text is separate derived presentation data. It never defines assertion
identity or conflict equality.

### Transaction and locking algorithm

```text
1. Begin one MemoryUnitOfWork transaction under READ COMMITTED.
2. Resolve the authenticated owner and deletion epoch.
3. Insert-or-resolve the normalized assertion identity.
4. Lock the assertion row with SELECT ... FOR UPDATE.
5. Reload current versions and re-run deterministic resolution on fresh state.
6. Insert evidence and the immutable decision.
7. Insert the new immutable version and close/supersede prior versions when the
   typed change set requires it.
8. Insert the outbox event for derived indexing or follow-up work.
9. Commit all rows or none.
10. On a retryable constraint or transaction conflict, restart from step 1 with
    bounded retry and the same idempotency identity.
```

Global `SERIALIZABLE` is rejected because unrelated users and keys need not
conflict. Redis/distributed locks are rejected because PostgreSQL already owns
the assertion transaction and adding a second lock authority creates failure
and expiry coordination. No-lock latest-write-wins is rejected because it can
silently lose corrections and evidence.

### At-least-once outbox processing

The canonical transaction writes an outbox row; workers claim available rows
with PostgreSQL locking that skips rows leased by other workers. Delivery is
at-least-once. A crash after a model call or commit may cause redelivery, so
idempotency is an invariant rather than an optimization.

```text
idempotency identity:
  source_event_id
  + extractor_or_policy_version
  + operation_type
  + canonical_candidate_identity
```

Exactly-once is rejected because the system cannot atomically commit one local
PostgreSQL transaction with an external model-provider response. At-most-once
is rejected because a crash may permanently lose extraction, summary,
deletion, or indexing work.

### Worker isolation and failure classes

Work may run concurrently across unrelated identities, but natural mutation
keys serialize:

```text
summary work  -> conversation_id
episode work  -> conversation_id + source span
semantic work -> assertion identity
deletion work -> owner or conversation deletion epoch
```

Transient failures retry with bounded exponential backoff and jitter. Permanent
contract failures produce a terminal decision/trace without retry. Semantic
uncertainty becomes `PENDING_CONFLICT`, not a rapid retry loop. Exhausted
transient work moves to dead-letter state with operator-visible evidence.

### Canonical store and derived search

PostgreSQL is the lifecycle authority. Structured key lookup and GIN full-text
are selected first. A later pgvector projection is permitted only after
evaluation demonstrates incremental value. Search results from any projection
must be revalidated against PostgreSQL owner, active version, sensitivity, and
deletion state before context assembly.

This accepts temporary index lag and additional revalidation queries in return
for atomic lifecycle correctness and rebuildable search state. A vector store
or graph database must never become a second, independently mutable lifecycle
authority.

### Access layer and tenant enforcement

SQLAlchemy Core and Alembic are selected over a full ORM because the repository
already owns explicit domain objects and needs transaction/query control rather
than identity-map behavior. They are selected over handwritten migrations to
provide ordered, reviewable schema evolution. PostgreSQL connection pooling is
required, but exact driver, pool size, timeouts, and deployment ownership remain
open.

Application authorization remains primary. PostgreSQL row-level security is
defense in depth: a missing application predicate must fail closed when tenant
context is absent. Connection checkout/checkin must set and clear tenant
context safely so a pooled connection cannot leak the previous owner's scope.

### Environment and legacy migration

PostgreSQL is the active development, integration-test, and production target.
SQLite remains only as a migration-era legacy adapter. Keeping SQLite for normal
development is rejected because SQL, locking, constraints, migrations, and
transaction behavior would diverge from production.

Before migration planning, inspect the actual R5/R6 database:

1. no real data to retain -> treat it as disposable prototype state;
2. real data must be retained -> import as quarantined legacy evidence;
3. never convert existing rows directly into active V2 assertions because they
   lack the approved canonical key, authority, evidence, sensitivity, and
   conflict semantics.

## User and System Flows

### Standalone first turn

```text
authenticated POST /chat without conversation_id
-> create owned standalone conversation
-> append user message and memory outbox event atomically
-> answer without waiting for background extraction
-> append assistant response
-> return conversation_id
```

### Explicit memory statement

```text
user says a low-risk explicit preference
-> source message and event persist
-> background structured extraction
-> ordinary-personal classification
-> canonical key/value validation
-> conflict resolver
-> policy-controlled auto-promotion after rollout gate
-> user-facing work continues without a blocking modal
```

### Explicit save or correction

```text
user says "remember" or explicitly corrects a preference
-> create independent user-memory action evidence
-> validate and classify
-> resolve the canonical assertion
-> present the exact proposed memory mutation for confirmation
-> apply only after explicit confirmation
-> commit the new version atomically
-> acknowledge briefly in the normal assistant response
```

### Inferred preference

```text
behavioral signal
-> immutable evidence
-> correlation and diversity checks
-> aggregate evidence score
-> shadow candidate until evaluation gate passes
-> future low-risk promotion only when policy threshold and safety gates pass
```

### User memory operation

```text
inspect/search/correct/delete/configure command
-> authenticate owner
-> resolve canonical assertion and sources
-> present the exact operation and scope for confirmation
-> stop without mutation when confirmation is absent or refused
-> apply versioned or privacy deletion operation
-> update indexes and traces through the same transaction/outbox path
```

System-generated shadow candidates are observations, not user-initiated memory
actions, so they do not create a confirmation prompt. Confirmation is required
when a user command would create, correct, delete, enable, disable, or otherwise
mutate durable memory behavior. The exact conversational and UI confirmation
contract remains open; the accepted trade-off is higher friction in exchange
for explicit mutation awareness.

### Conversation deletion

```text
tombstone conversation immediately
-> block raw and derived retrieval
-> delete conversation summary and episodes
-> invalidate sole-source inferred assertions
-> remove deleted support and recompute multi-source assertions
-> preserve an explicitly managed memory only when independent user-action
   evidence proves the intent to retain it
-> prevent stale jobs from committing through deletion/version checks
-> verify derived index removal before final deletion state
```

## Candidate, Decision, Assertion, and Version Lifecycle

`MemoryCandidate` is immutable. Extraction writes what the extractor proposed;
later policy, model-classification, user-confirmation, and promotion outcomes do
not rewrite that evidence. Each evaluation appends an immutable
`MemoryDecision` whose outcome is one of:

```text
INVALID
REJECTED
SHADOW
HELD_SENSITIVE
PENDING_CONFLICT
ROUTED_TO_PRODUCT_STATE
PROMOTED
```

`INVALID` means the extractor or schema contract failed before a valid
candidate existed. `REJECTED` means a valid candidate was deliberately refused
by policy. `SHADOW` means evidence is retained for evaluation but has no answer
authority. Holds and pending conflicts remain unavailable to normal retrieval.
`PROMOTED` points to the committed assertion and version identifiers.

The latest applicable decision determines the candidate's operational view,
but the complete decision history remains auditable. This is selected over a
mutable `candidate.status`, which loses decision history, and over full event
sourcing, which adds broader replay and projection complexity than the target
currently needs.

Confirmed assertion/version lifecycle:

```text
ACTIVE
-> SUPERSEDED
-> EXPIRED
-> RETRACTED
-> DELETION_REQUESTED
-> DELETED

ACTIVE | PENDING_CONFLICT -> ACTIVE after deterministic resolution
```

`MemoryAssertion` provides stable identity. Immutable `MemoryVersion` rows carry
the values and lifecycle states. Privacy deletion is distinct from epistemic
retraction and ordinary supersession; every read, delete, migration, and report
path must handle the six states explicitly.

Conversation summaries use immutable versions and one active pointer. A summary
version owns `conversation_id`, source-sequence bounds, model and prompt
versions, creation time, and lifecycle state. Episodic records own a selected
message span plus typed situation, intent, actions/options, outcome, reason,
source events, event time, authority, sensitivity, lifecycle state, and
extractor version. Neither summary nor episode contains chain-of-thought.

## Atomicity, Idempotency, and Concurrency

One semantic-memory transaction must:

1. lock or revision-check the assertion slot;
2. record accepted evidence;
3. insert or update the assertion identity;
4. insert the new immutable version;
5. close or invalidate the previous version when required;
6. transition the candidate outcome;
7. record the policy/promotion outcome;
8. insert the derived-index outbox event;
9. commit all changes or none.

Idempotency derives from source event, extractor version, canonical key/value,
and operation kind. Duplicate delivery must return the prior result rather than
creating another record.

Concurrent writers use assertion version checks or row locking and bounded
retry. A partial unique constraint should enforce one current version for a
single-valued assertion and condition. A deletion epoch prevents queued jobs
from recreating data after deletion.

## Failure and Recovery

| Failure | Target behavior |
| --- | --- |
| Secret detector matches | Redact and reject before model, candidate, embedding, log, or evaluation persistence |
| Extractor unavailable | Chat succeeds; outbox job retries without duplicate candidates |
| Extractor returns invalid schema | Reject/invalid trace; no canonical mutation |
| Relationship classifier uncertain | `PENDING_CONFLICT`; no destructive mutation |
| Atomic commit conflict | Retry from current assertion version; never partially apply |
| Worker crashes after commit | Idempotent retry returns the committed result |
| Worker crashes before commit | Lease expires and another worker retries |
| Derived indexing fails | Canonical state remains valid; index outbox retries |
| Conversation is deleted during extraction | Deletion epoch causes commit rejection and cleanup |
| Summary generation fails | Keep prior summary and unsummarized messages; retry background |
| Trace persistence fails | Write path follows the approved fail-closed/degraded policy; exact choice remains open |

## Security and Privacy

1. Authenticate owner identity before every source, candidate, assertion,
   version, summary, episode, trace, and user-control operation.
2. Enforce owner scope in queries and repository constraints; future PostgreSQL
   row-level security may provide defense in depth.
3. Treat external content, tool output, assistant output, retrieved knowledge,
   and generated summaries as untrusted derived data.
4. Separate memory-write consent from evaluation-trace visibility.
5. Reject secrets and raw payment credentials before extraction.
6. Keep restricted data out of durable cross-conversation memory until its
   protected storage and user-control design is approved.
7. Store exact provenance while minimizing raw content in operational traces.
8. Delete or rebuild every derived summary, episode, assertion support edge,
   search projection, cache, and queued job affected by source deletion.
9. Test memory poisoning, cross-owner access, stale-job resurrection, and
   deletion verification as hard gates.

## Observability and Operations

Required evidence includes:

1. source events captured, skipped, and duplicated;
2. extraction latency, model/prompt/schema version, token use, and cost;
3. candidate counts by key, language, sensitivity, authority, and outcome;
4. evidence-score distribution and promotion coverage;
5. relationship-classification outcomes and uncertainty;
6. conflict operation counts and unresolved-conflict age;
7. transaction conflicts, retries, worker lease expiry, dead-letter count, and
   oldest job age;
8. index freshness and rebuild status;
9. deletion propagation and verification latency;
10. user corrections, deletions, disables, and post-promotion regret rate;
11. cross-owner, secret, and memory-poisoning gate events.

No raw secret, credential, payment value, or unrestricted conversation content
belongs in operational telemetry.

## Testing and Evaluation

### Component evaluation

1. Secret and sensitivity classification precision/recall by band.
2. Candidate extraction precision/recall/F1 by canonical key and language.
3. Relationship classification confusion matrix for duplicate, compatible,
   contradiction, temporal update, scoped exception, unrelated, and uncertain.
4. Typed resolver truth-table tests for authority, cardinality, scope, and time.
5. Idempotency, transaction rollback, retry, and concurrency tests.
6. Deletion cascade, index removal, and resurrection-prevention tests.
7. Summary faithfulness, coverage, update, and rebuild tests.
8. Episodic qualification precision, outcome correctness, and no-silence
   inference tests.

### End-to-end evaluation

1. No-memory, recent-history, lexical-memory, hybrid-memory, and oracle-context
   baselines.
2. Personalization win rate and constraint adherence.
3. Multi-conversation reasoning, knowledge update, temporal reasoning, and
   abstention.
4. Current versus historical fact accuracy.
5. Irrelevant-memory robustness and context-token efficiency.
6. Cross-owner leakage, poisoning, sensitive promotion, and deleted-memory
   retrieval hard gates.
7. p50/p95/p99 write and background completion latency, throughput, storage
   growth, provider cost, and worker recovery.

Auto-promotion remains shadow-only until exact quality thresholds and a labeled
evaluation set are approved.

## Capacity, Latency, and Cost

The target supports approximately 1,000 authenticated users. This target does
not yet define request rate, active-conversation concurrency, messages per day,
retention, model pricing, or availability objectives; those values remain
required before an SLO or infrastructure-size claim.

Proposed baseline:

1. PostgreSQL owns canonical conversation and memory state.
2. A transactional outbox and database-backed workers handle asynchronous
   extraction, summary, episode, consolidation, deletion, and indexing work.
3. GIN full-text and structured key lookup precede optional pgvector.
4. Chat does not wait for model-backed memory extraction.
5. Explicit user memory actions use the same policy and atomic commit path and
   may receive synchronous acknowledgement only after commit.
6. Kafka, a graph database, and a separate vector service require measured
   evidence that PostgreSQL-based operation cannot satisfy approved goals.

## Alternatives Considered

### Hidden Default Workspace

Every user could receive an invisible workspace so existing conversation
foreign keys remain unchanged.

Benefits: smaller migration and reuse of current scope resolution.

Costs: turns an implementation workaround into a false product concept, makes
standalone memory appear workspace-scoped, complicates future project semantics,
and preserves unnecessary coupling. Not recommended.

### Fully Autonomous Model-owned Memory

A model could choose what to remember and directly issue add, update, and
delete operations.

Benefits: high flexibility and less deterministic policy code.

Costs: non-deterministic destructive authority, difficult evaluation,
uncalibrated confidence, privacy and poisoning exposure, and weak rollback.
Rejected.

### Review Every Candidate

Every candidate could require explicit user approval.

Benefits: strong user awareness and low silent false-promotion risk.

Costs: review fatigue and interruption of travel tasks. Rejected as the normal
flow; retain review only for selected sensitive, ambiguous, or high-impact
operations.

### PostgreSQL plus Rebuildable Search Projections

PostgreSQL could own conversations, evidence, assertions, versions, candidates,
jobs, and outbox state. Full-text and optional vector indexes remain derived.

Benefits: transactional integrity, familiar operations, owner scoping, and
sufficient capacity for the stated target without distributed coordination.

Costs: migration from SQLite, database operations, worker lifecycle, and later
vector index maintenance. Proposed.

### Temporal Graph Source of Truth

A graph store could own semantic relationships and temporal facts.

Benefits: native relationship traversal and expressive temporal/multi-hop
queries.

Costs: another lifecycle authority, cross-store transactions, harder deletion,
more operational surface, and no current local benchmark proving need. Deferred.

## Compatibility and Staged Migration

Confirmed delivery structure; exact package specifications and implementation
plans remain future approval artifacts:

1. `W0` — complete this architecture design, glossary, threat model, evaluation
   protocol, required ADRs, and capacity assumptions.
2. `W1` — standalone owned conversation migration, optional workspace, and
   first-turn persistence.
3. `W2` — PostgreSQL foundation, code-reviewed key registry projection,
   evidence/assertion/version schema, ordinary-personal sensitivity guards, and
   atomic explicit semantic writes.
4. `W3` — Memory Manager commands and UI for inspection, correction, deletion,
   read/write control, provenance explanation, and complete ordinary-memory
   deletion.
5. `W4` — transactional outbox, database-backed workers, background shadow
   extraction, weighted evidence aggregation, relationship classification,
   deterministic conflict resolution, and write traces.
6. `W5` — protected restricted-memory capability after user controls, including
   explicit purpose, confirmation, retention, access, encryption, and deletion
   verification.
7. `W6` — conversation summary versioning and runtime use.
8. `W7` — hybrid episodic qualification and episodic retrieval evaluation.
9. `W8` — measured low-risk inferred auto-promotion and bounded consolidation.
10. `W9` — GIN/hybrid read improvements and optional pgvector experiment.
11. `W10` — production readiness evidence for approximately 1,000 users,
   including load, recovery, retention, deletion, security, observability, and
   cost gates.

Existing R5/R6 records must not silently become active V2 assertions. A future
migration plan must choose between disposable local data and quarantined legacy
evidence after inspecting real stored-data requirements.

## Rollback

Each implementation package requires an independent rollback boundary. General
principles:

1. Preserve current `/health` and chat compatibility until the owning package
   explicitly changes and tests it.
2. Keep new write and read behavior behind independently controllable server
   gates during migration.
3. Do not dual-write without an explicit reconciliation and cutover plan.
4. Treat search indexes as rebuildable projections.
5. Preserve legacy data as inert/quarantined evidence until deletion or
   migration is explicitly approved.
6. Never roll back a privacy deletion by resurrecting source or derived data.

## Open Decision Frontier

The following decisions remain unresolved and must not be inferred from this
draft:

1. Exact auto-promotion precision, coverage, calibration, and rollback gates.
2. The first canonical-key catalog, normalizers, value schemas, conditions,
   per-key cardinality, and registry-version migration rules.
3. The exact per-key authority matrix and how verified product events gain
   authority without allowing assistant or external-content laundering.
4. Exact evidence weights, correlation caps, negative-evidence behavior,
   recency/validity treatment, and aggregation thresholds.
5. Which `contextually_sensitive` and `restricted` travel categories will be
   supported after W3, plus purpose, retention, encryption, and reconfirmation
   rules for each.
6. Exact relationship-classifier model, prompt, strict schema, candidate-pair
   retrieval, uncertainty threshold, latency/cost budget, and model-change
   evaluation gate.
7. The complete deterministic resolver table for equal-authority updates,
   retractions, conditions, effective intervals, set-member changes, and
   pending-conflict aging.
8. Final episodic event vocabulary, span selection, salience threshold,
   retention, deduplication identity, and residual-model budget.
9. Exact Memory Manager user flows, API contracts, confirmation timing,
   cancellation, undo semantics, source explanation, bulk operations, and
   accessibility requirements.
10. PostgreSQL hosting, migration, backup, restore, encryption, row-level
    security, connection pooling, and disaster-recovery decisions.
11. Worker implementation, lease duration, concurrency, retry, backoff,
    dead-letter, scheduling, replay, and operational ownership.
12. Traffic, message volume, retention, latency, availability, recovery, and
    provider-cost budgets for the 1,000-user target.
13. Exact compatibility treatment for existing R5/R6 local data and whether
    legacy records are disposable, quarantined, or migrated as evidence.
14. Whether this proposal supersedes ADRs 0002, 0004, 0005, 0006, 0007, and
    0010 in whole or only in named parts.

## Glossary

| Term | Meaning in this design |
| --- | --- |
| Working context | Ephemeral, token-bounded inputs assembled for one model call |
| Conversation summary | Versioned, rebuildable compression of one conversation |
| Semantic memory | Durable facts and preferences represented through assertions and versions |
| Episodic memory | Selected evidence-bearing experience with situation, action, outcome, and reason |
| Evidence | Immutable user or verified product observation supporting or opposing a candidate/assertion |
| Candidate | Extracted proposal that has no durable answer authority by itself |
| Memory decision | Immutable policy, classifier, user, or promotion outcome attached to a candidate |
| Assertion | Stable identity for owner, scope, canonical key, and optional condition |
| Version | Immutable assertion value and lifecycle revision over an effective interval |
| Canonical key | Registry-owned semantic identity such as `travel.preference.hotel_atmosphere` |
| Cardinality | Whether a key is single-valued, set-valued, or structured |
| Condition fingerprint | Deterministic identity for a registry-defined scoped or contextual exception |
| Authority | Strength assigned to a source for a particular key and operation |
| Evidence score | Explainable aggregate policy feature; not a calibrated probability |
| Conflict | Incompatible values for the same assertion identity over overlapping scope, condition, and effective time |
| Scoped exception | Narrower value that shadows a broader default without superseding it |
| Valid time | Period when a value applies in the travel domain |
| System time | Period when the system stored or believed a value |
| Relationship classifier | Bounded model or deterministic module that labels semantic relation without mutating lifecycle state |
| Conflict resolver | Deterministic module that applies authority, scope, time, cardinality, and policy to produce a typed change set |
| Promotion | Policy-controlled transition from candidate/evidence into an active assertion version |
| Retraction | Epistemic withdrawal because evidence is no longer sufficient; distinct from privacy deletion |
| Supersession | Replacement by a newer applicable version while history and evidence remain |
| Privacy deletion | Removal/invalidation of source and derived data according to deletion policy |
| Transactional outbox | Event row committed with canonical state so background work cannot be silently lost |
| Derived index | Rebuildable full-text, vector, graph, or cache projection that is not lifecycle authority |
| Shadow mode | Candidate/evidence processing that cannot influence user answers or active memory |

## Required ADRs

After architecture approval, prepare proposed ADRs for:

1. Authenticated standalone conversations with direct owner identity and an
   optional workspace association.
2. Evidence/assertion/version ownership and PostgreSQL as canonical memory
   storage.
3. Governed model-assisted extraction and deterministic write-policy authority.
4. Sensitivity classification, prohibited-memory boundary, and user-control
   requirements.
5. Canonical key, cardinality, temporal semantics, and conflict resolution.
6. Transactional outbox, worker ownership, idempotency, and derived-index
   consistency.
7. Conversation summary and hybrid episodic-memory ownership.
8. Memory evaluation, rollout gates, and production-readiness evidence.

## References

1. [Current-state Architecture](../architecture/current-state.md)
2. [Target-state Architecture](../architecture/target-state.md)
3. [Shadow Memory Extraction Design](./2026-09-04-shadow-memory-extraction-design.md)
4. [Memory Retrieval Design](./2026-09-04-memory-retrieval-design.md)
5. [ADR 0005](../adr/0005-conversation-orchestration-seam-and-optional-chat-binding.md)
6. [ADR 0006](../adr/0006-shadow-memory-candidate-store-and-policy-boundary.md)
7. [ADR 0007](../adr/0007-feature-gated-memory-retrieval-and-context-boundary.md)
8. [ADR 0010](../adr/0010-local-identity-authorization-and-deletion-boundary.md)
9. [NIST SP 800-122](https://doi.org/10.6028/NIST.SP.800-122)
10. [GDPR Articles 4, 5, 9, 16, and 17](https://eur-lex.europa.eu/eli/reg/2016/679)
11. [PCI DSS](https://www.pcisecuritystandards.org/standards/pci-dss/)
12. [W3C PROV-DM](https://www.w3.org/TR/prov-dm/)
13. [LongMemEval](https://proceedings.iclr.cc/paper_files/paper/2025/file/d813d324dbf0598bbdc9c8e79740ed01-Paper-Conference.pdf)
14. [MemoryAgentBench](https://arxiv.org/abs/2507.05257)
15. [Zep temporal-memory architecture](https://arxiv.org/abs/2501.13956)
16. [Generative Agents](https://arxiv.org/abs/2304.03442)
17. [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
18. [PostgreSQL transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html)
19. [Debezium transactional outbox pattern](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)

## Architecture Approval Record

Not approved. Approval requires completion of the open decision frontier,
self-review, explicit repository-owner review of this exact version, and a
separate authorization to prepare implementation plans.
