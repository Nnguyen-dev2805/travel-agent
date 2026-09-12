# Authenticated Chat-Only PostgreSQL Clean Break

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-10 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Destructive removal of application-owned SQLite, Workspace, Planner, anonymous compatibility Chat, legacy Memory, and user-facing Memory management; replacement with authenticated standalone Chat on PostgreSQL |
| Related issue | Repository-owner approved exception: interactive clean-break redesign on 2026-09-10 |
| Superseded document | None until approval; Section 20 lists proposed supersession |

## Summary

This specification defines a deliberate clean break before the Single-Step
Context Agent is implemented. The mounted product becomes an authenticated
standalone Chat application backed by PostgreSQL. Workspace and Planner concepts
are removed from runtime, source, frontend, configuration, tests, and current
architecture. The application-owned SQLite store and schema registry are
removed. Legacy SQLite Memory and the separate Memory Manager/control API are
removed.

The refactor preserves the RAG subsystem, authentication and owner isolation,
standalone conversation contracts, PostgreSQL conversation/message/outbox
capability, and the reusable V2 background Memory domain. It does not implement
adaptive routing, V2 Memory Read, automatic activation, or the agent execution
model. Those features start from the smaller verified baseline produced here.

This is a breaking change. Compatibility with Workspace URLs, Planner URLs,
legacy Memory URLs, anonymous Chat, SQLite data files, and the Memory Manager UI
is intentionally not preserved.

## Terminology and Boundary

“Remove SQLite” means removing SQLite owned directly by this application:

- `APP_DB_PATH` and deprecated workspace database configuration;
- application schema registry and `sqlite3` repository implementations;
- application tables for Workspace, Conversation, legacy Memory, and Planner;
- application tests/evaluators whose subject is those SQLite adapters.

It does not mean replacing Chroma solely because Chroma may use SQLite inside
its own persistence implementation. Chroma is an RAG/vector-store dependency,
not the application relational source of truth. Replacing Chroma requires a
separate retrieval-storage decision and is outside this clean break.

“Remove user Memory management” means removing the current separate UI and
public explicit-control contract:

- no Memory Manager drawer;
- no public list/remember/correct/forget/toggle/expand/confirm Memory endpoints;
- no explicit Memory command parsing in this cleanup release.

It does not authorize orphaning private data. Conversation/account retention
operations must still invalidate or delete dependent evidence, pending outbox
work, active versions, summaries, episodes, and search projections when those
records exist. A future approved Chat command design may reintroduce explicit
Memory controls without restoring the removed Memory Manager.

## Current-State Evidence

| Evidence | Current behavior | Required change |
| --- | --- | --- |
| `backend/app/main.py:214-221` | Eight routers are mounted, including Workspace, legacy Memory, Memory Controls, and Planner | Mount only health, authenticated Chat/conversations, and authenticated operations |
| `backend/app/api/chat.py:66-121` | Chat resolves SQLite legacy Memory and workspace owner lookup | Remove legacy Memory integration; inject PostgreSQL conversation runtime |
| `backend/app/api/conversations.py:66-92` | Routes construct SQLite conversation and workspace repositories | Replace with owner-scoped PostgreSQL construction from one composition root |
| `backend/app/api/workspaces.py` | Workspace creation/list/deletion is public product behavior | Delete route, schemas, module, frontend, and tests |
| `backend/app/api/planner.py` | Planner state routes are mounted and workspace-scoped | Delete route, schemas, module, frontend, and tests |
| `backend/app/api/memory.py` | Legacy extraction/promotion uses SQLite and Workspace | Delete legacy route, models, services, persistence, evaluation, and tests |
| `backend/app/api/memory_controls.py` | Separate user-facing Memory commands/list/delete/preview use PostgreSQL | Delete public route/schema/UI and command-specific implementation |
| `backend/security/dependencies.py` | `AUTH_REQUIRED=false` creates a compatibility principal | Remove compatibility mode; protected routes always require a valid principal |
| `backend/observability/readiness.py` | Readiness probes application SQLite schema | Replace with PostgreSQL connectivity/migration readiness |
| `frontend/src/App.jsx` | Chat is gated by active Workspace and exposes Memory Manager | Replace Workspace state with owner-scoped conversation state; remove Memory UI |
| `backend/conversations/postgres_repository.py` | PostgreSQL adapter supports owned conversations, messages, and outbox intent | Make it the only mounted conversation adapter |
| `backend/memory/write_pipeline/` | V2 domain, policy, resolver, PostgreSQL UoW, outbox, worker, extraction, and evaluation exist | Preserve background-relevant modules; remove user-control-specific surface |

Fresh pre-design evidence on `feature/agent-memory`:

- Memory Write and conversation-focused unit tests passed before the merge.
- Bound Chat integration failed at the legacy Workspace create route because
  `ConversationCreate.owner_user_id` was omitted.
- PostgreSQL integration was partially skipped when PostgreSQL was unavailable;
  required PostgreSQL verification must not skip after this change.

## Users and Actors

1. An authenticated user who owns and chats in multiple standalone
   conversations.
2. The synchronous Chat application that persists turns and generates RAG
   responses.
3. A background Memory worker that may later process durable extraction events.
4. An operator responsible for PostgreSQL migration, backup, readiness,
   cutover, rollback, and legacy-data disposal.

## Assumptions

1. `feature/agent-memory` is not serving production traffic during this clean
   break. If it is, implementation stops for a traffic and compatibility plan.
2. Existing application SQLite data is development or synthetic unless the
   required read-only inventory proves otherwise. Any user-valued row blocks
   disposal until the owner selects export, quarantine, or migration.
3. PostgreSQL is available in local development and CI for every required
   integration check; skipped database checks cannot satisfy acceptance.
4. Chroma remains the RAG vector-store adapter for this change.
5. The local bearer-token registry remains the authentication adapter; identity
   provider integration and token expiry are separate work.
6. No approved external consumer requires removed Workspace, Planner, legacy
   Memory, or Memory Controls URLs. Evidence of one stops implementation for a
   compatibility decision.

## Problem Statement

The repository currently has incompatible product models and persistence
generations at once:

```text
Workspace-first product + SQLite application state + legacy Memory
and
standalone owner conversation + PostgreSQL V2 Memory/outbox
```

This makes Chat ownership, outbox capture, Memory provenance, readiness,
evaluation, and frontend navigation ambiguous. Continuing agent and Memory work
on this base would multiply compatibility branches and produce more modules
without a coherent mounted behavior.

The clean break establishes one product container—an authenticated
conversation—and one relational authority—PostgreSQL—before adaptive context
orchestration is added.

## Goals

1. Require authentication for every Chat, conversation, history, and operations
   request other than the liveness endpoint.
2. Let an authenticated user start Chat immediately without creating a
   Workspace.
3. Support multiple standalone conversations owned directly by the principal.
4. Use PostgreSQL for conversation, message, and transactional outbox state.
5. Preserve message-before-generation ordering and controlled partial-failure
   behavior.
6. Remove every application runtime dependency on `sqlite3`, `APP_DB_PATH`, and
   the application SQLite schema registry.
7. Remove Workspace, Planner, legacy Memory, and Memory Manager behavior from
   backend, frontend, tests, configuration, and current architecture.
8. Preserve reusable V2 background Memory contracts and PostgreSQL persistence
   without exposing user-facing Memory management.
9. Produce a smaller verified baseline for the Single-Step Context Agent.
10. Preserve historical design evidence by marking it superseded rather than
    deleting governance history.

## Non-Goals

1. Adaptive selection among no tool, RAG, Memory, or both.
2. Dialogue reference resolution, ActionRouter, ContextPlanner, or ContextArbiter.
3. V2 Memory Read/Use in Chat.
4. Inferred Memory auto-activation.
5. Explicit Memory commands inside the main Chat.
6. Booking, payment, itinerary generation, or external action tools.
7. Replanning or an agent loop.
8. pgvector or Chroma replacement.
9. A distributed queue.
10. Migration of Workspace, Planner, or legacy SQLite Memory into active V2
    product state.

## Alternatives Considered

### Alternative A: Unmount Legacy Features but Keep Their Source and SQLite

This minimizes immediate deletion and eases rollback. It leaves hundreds of
legacy imports/tests, two persistence generations, misleading architecture, and
ongoing accidental coupling. Rejected because the repository owner explicitly
selected a clean break and the retained source would continue to burden agent
and Memory development.

### Alternative B: Dual-Write SQLite and PostgreSQL During Migration

This can support a live gradual cutover. It introduces cross-store atomicity,
reconciliation, conflict authority, rollback direction, and duplicate-write
failure modes without evidence of production traffic requiring them. Rejected.

### Alternative C: Authenticated PostgreSQL Clean Break

Inventory legacy data, build the PostgreSQL replacement, cut over once, then
delete the legacy source and disposable state. This loses old URL compatibility
but produces the smallest honest runtime and one storage authority. Selected.

## Target Product Surface

### Mounted HTTP Surface

| Route | Authentication | Purpose |
| --- | --- | --- |
| `GET /health` | Public | Process liveness only; no dependency detail |
| `GET /api/v1/ops/readiness` | Required | Controlled PostgreSQL, RAG, model, and migration readiness |
| `POST /api/v1/chat` | Required | Create or continue one owner-scoped conversation turn |
| `POST /api/v1/conversations` | Required | Explicitly create a standalone conversation when desired |
| `GET /api/v1/conversations` | Required | List the principal's conversations |
| `GET /api/v1/conversations/{conversation_id}` | Required | Read one owned conversation |
| `GET /api/v1/conversations/{conversation_id}/messages` | Required | Read paginated owned message history |
| `DELETE /api/v1/conversations/{conversation_id}` | Required | Delete/tombstone a conversation and propagate retention |

Direct public message append is removed. User messages enter through `/chat`,
and assistant/tool messages remain application-owned. This prevents callers
from forging transcript roles or bypassing message/outbox semantics.

### Removed HTTP Surface

1. Every `/workspaces` route.
2. Every `/workspaces/{id}/planner` route.
3. Every legacy `/workspaces/{id}/.../memory` extraction/promotion route.
4. Every `/memory/controls` route.
5. Workspace-scoped conversation create/list routes.

Removed routes return normal unmounted `404`; no compatibility proxy or redirect
is added.

## Target Frontend Surface

Unauthenticated state renders only the login experience and cannot send a Chat
request. Successful authentication loads the principal's conversation list.

Frontend state is reduced to:

```text
principal/authentication
conversations
activeConversationId
messages
chat loading/error state
```

The following are deleted:

```text
workspaces and activeWorkspace
CreateTripModal and Workspace services
PlannerPanel, itinerary components, and Planner services
MemoryManager, MemoryConfirmation, and Memory services
Workspace/Planner/Memory buttons, modals, drawers, and local-storage keys
```

New Chat starts an empty local view. The first accepted `/chat` request may
create the conversation and returns its ID; explicit `POST /conversations` is
available for clients that need creation before the first message.

## Authentication Contract

1. `AUTH_REQUIRED` and unauthenticated compatibility behavior are removed.
2. `require_principal` always requires `Authorization: Bearer <token>`.
3. Missing, malformed, or unknown credentials return content-free `401` before
   storage, RAG, Memory, or model work. Token expiry is not claimed while the
   retained local token adapter has no expiry contract.
4. `get_optional_principal` and `AuthMode.COMPATIBILITY` are removed unless a
   remaining non-product test proves a distinct authenticated use.
5. Owner identifiers come only from the authenticated principal.
6. Request bodies and query strings cannot select another owner.
7. Wildcard CORS is prohibited; only configured explicit origins are accepted.
8. Liveness remains public and reports no credential, database, model, path, or
   tenant detail.

The current local token registry may remain as the authentication adapter for
this milestone. Replacing it with an external identity provider is a separate
decision.

## Components and Dependency Direction

### RuntimeContainer

A single composition module owns process-scoped PostgreSQL engine/pool creation
and constructs:

- `PostgresConversationRepository`;
- `ConversationService` without Workspace dependency;
- `ConversationOrchestrator`;
- outbox repository capability;
- PostgreSQL readiness probe.

FastAPI routes depend on provider interfaces from this module. They do not
construct SQLite or PostgreSQL adapters independently.

### Conversation Domain

The domain contains no `workspace_id` concept after the clean break.

```text
Conversation
  conversation_id
  owner_user_id
  title
  retention_state
  created_at
  updated_at
```

The service requires an authenticated owner for create, get, list, append,
history, and delete. It never resolves ownership through a Workspace.

### PostgreSQL Conversation Adapter

The adapter owns:

- conversation CRUD and owner-scoped reads;
- per-conversation message sequence allocation;
- user-message plus outbox atomicity;
- assistant-message persistence;
- retention transitions;
- pagination;
- controlled concurrency errors.

### ConversationOrchestrator

The cleanup preserves a fixed RAG generation path. For this milestone it:

1. resolves or creates the authenticated conversation;
2. persists the user message and optional background extraction intent;
3. calls RAG generation;
4. persists the assistant message;
5. returns explicit persistence metadata.

Adaptive RAG and agent routing are intentionally deferred.

### BackgroundMemoryRecorder

The worker must not depend on `MemoryCommandService` after user-control removal.
A narrow background interface records a validated shadow candidate through the
existing policy/resolver/UoW seams. It exposes no remember, correct, inspect,
toggle, preview, confirmation, expansion, or user-initiated delete methods.

### Preserved V2 Modules

Preserve modules that serve background Memory and future Read/Use:

- registry and immutable models;
- secret detection;
- policy and resolver;
- Memory UoW and PostgreSQL adapter;
- outbox state and worker;
- structured extraction model adapter;
- focused non-legacy background evaluation.

Command-only types, parser branches, preview state, confirmation tokens, direct
delete helpers, UI response events, HTTP schemas, routes, and tests are removed.

Dependency direction remains:

```text
HTTP/worker adapters
-> application interfaces
-> pure conversation and Memory domain
<- PostgreSQL/model/RAG adapters
```

No domain module imports FastAPI, SQLAlchemy, a provider SDK, or frontend code.

## PostgreSQL Data Contract

Existing Alembic history is append-only. Do not rewrite revisions that may have
been applied elsewhere. Add a clean-break revision that:

1. ensures `conversations.owner_user_id` is populated and `NOT NULL`;
2. removes `conversations.workspace_id` and its indexes/constraints;
3. removes the PostgreSQL `workspaces` compatibility table after dependency
   checks;
4. preserves `messages` and `conversation_outbox` foreign keys;
5. preserves V2 Memory tables needed by background formation;
6. adds owner/retention/index constraints required by standalone list/history;
7. upgrades and downgrades safely in an isolated database.

No Planner PostgreSQL schema is introduced. A clean database may pass through
historical migrations before the clean-break revision removes compatibility
objects; final-schema verification, not intermediate presence, defines success.

## Chat and Outbox Data Flow

### First Message Without Conversation ID

```text
authenticated principal
-> create owner conversation
-> transaction: append user message + optional extraction outbox intent
-> RAG generation
-> append assistant message
-> response with conversation ID and persistence state
```

### Existing Conversation

```text
authenticated principal + conversation ID
-> owner/retention validation
-> transaction: append user message + optional extraction outbox intent
-> RAG generation
-> append assistant message
-> response
```

Outbox capture remains behind the background extraction gate until the worker
runtime is separately approved. When enabled, the message and intent must commit
together. Chat never waits for Memory extraction.

### Conversation Deletion

```text
authenticated owner delete
-> make conversation immediately non-readable
-> cancel pending/leased extraction work by deletion epoch/fencing
-> invalidate dependent Memory evidence
-> recompute or suspend any version whose support is no longer valid
-> remove/rebuild derived summary/vector projections
-> complete governed hard-delete or tombstone policy
```

The cleanup must not claim complete Memory deletion if downstream V2 records are
not yet wired. It must either implement the propagation transaction or fail
closed and keep the delete endpoint gated until propagation is proven.

## Deletion Inventory

### Backend Source to Delete

1. `backend/workspaces/`.
2. `backend/planner/`.
3. Workspace and Planner route/schema modules.
4. Legacy Memory route, model, policy, extraction, promotion, repository,
   service, SQLite persistence, and legacy evaluation modules outside
   `backend/memory/write_pipeline/`.
5. All application SQLite repository adapters and
   `backend/storage/schema_registry.py`.
6. Workspace-dependent privacy deletion service; replace only the conversation
   retention behavior required by this spec.
7. Workspace authorization helpers and compatibility-principal branches.
8. Memory Controls route/schema and command-specific implementation.
9. `backend/memory/write_pipeline/evaluation/sqlite_inventory.py` after its
   final inventory report and disposal decision are recorded.

### Frontend Source to Delete

1. Workspace services/components/state.
2. Planner services/components/state.
3. Memory Manager services/components/state.
4. Tests whose only subject is the removed UI.

### Tests and Evaluation

Delete tests that assert removed product behavior. Port—not delete—tests that
protect still-required invariants:

- authentication and owner isolation;
- message ordering and pagination;
- user-message-before-generation ordering;
- message/outbox atomicity;
- content-free errors and log redaction;
- retention/deletion propagation;
- RAG fallback and citation behavior;
- background Memory policy, extraction, retry, and idempotency.

Security, observability, and evaluation runners must use PostgreSQL fakes or an
isolated migrated PostgreSQL database instead of silently retaining SQLite.

### Configuration and Data

Remove:

- `APP_DB_PATH`, `WORKSPACE_DB_PATH`, and default SQLite path helpers;
- `AUTH_REQUIRED` compatibility flag;
- Workspace/Planner/legacy-Memory environment settings;
- application SQLite volumes and generated database files;
- documentation instructing users to initialize or inspect application SQLite.

Before deleting any local database file, inventory table names and row counts
without printing content. If any non-synthetic or user-valued data exists, stop
for an explicit disposal/export decision. Empty or synthetic development state
may be removed under this approved clean break.

## Failure and Recovery

| Failure | Required behavior |
| --- | --- |
| Missing/invalid credential | `401`; no storage, retrieval, or model work |
| Foreign/missing conversation | Indistinguishable content-free `404` |
| PostgreSQL unavailable before user append | Controlled `500/503`; no model call |
| Outbox insert fails | User-message transaction rolls back |
| RAG/model fails after user commit | User message/outbox remain; no assistant persistence claim |
| Assistant append fails after generation | Return generated reply only when the contract explicitly marks `persisted=false` |
| Schema revision missing | Readiness not ready; protected runtime fails closed |
| Worker unavailable | Chat remains available; durable events accumulate only when capture is enabled |
| Conversation delete cannot propagate | Delete fails closed; no false success |
| Legacy URL called | Unmounted `404`; no compatibility forwarding |
| SQLite path/file still present | Boundary verification fails; no completion claim |

## Security and Privacy

1. Authentication is mandatory for all owner-scoped behavior.
2. Application owner checks and PostgreSQL RLS are defense in depth.
3. Credentials and assembled DSNs never enter logs, errors, reports, or settings
   representations.
4. Raw messages, prompts, Memory evidence, and retrieved documents do not enter
   controlled error bodies.
5. RAG documents and future Memory are untrusted data, never instructions.
6. Removing the Memory Manager does not remove deletion obligations.
7. Conversation deletion and account-level retention remain privacy lifecycle
   requirements even without per-Memory controls.
8. Public liveness reveals no dependency state; authenticated readiness uses
   controlled reason codes.
9. CORS is explicit and non-wildcard.
10. PostgreSQL tests cover cross-owner denial at application and RLS layers.

## Observability and Operations

Readiness reports controlled status for:

- application process;
- PostgreSQL connectivity and Alembic revision;
- model provider configuration;
- RAG vector store presence;
- background capture/worker gate state.

It does not probe SQLite or create storage as a side effect. Logs and metrics
identify conversation, message, request, and failure class using governed IDs
and reason codes without content.

Required operational evidence:

1. PostgreSQL migration round trip.
2. Pool configuration and exhaustion behavior.
3. Backup/restore rehearsal for conversation/message/outbox and V2 Memory.
4. Pending outbox visibility when workers are stopped.
5. Rollback instructions that do not restore writes to SQLite.

## Capacity, Latency, and Cost

This cleanup targets 1,000 registered users but makes no claim about concurrent
load without a workload model. Before rollout, verification records peak test
requests per second, concurrent conversations, connection-pool utilization,
message/outbox transaction latency, error rate, and database size.

1. PostgreSQL pool size and timeout are explicit configuration with safe
   defaults and no credential logging.
2. The message/outbox transaction adds no model call and has a measured p95
   budget of 100 ms in the controlled local integration environment.
3. Conversation list/history queries are indexed by owner, conversation, and
   sequence and are tested at representative row counts.
4. This cleanup adds no query-understanding, Memory-read, embedding, or agent
   model cost.
5. RAG/model latency and token behavior remain the characterized baseline; a
   statistically meaningful regression attributable to persistence wiring
   blocks rollout.
6. Outbox accumulation while the worker is disabled has an operator-visible row
   count and oldest-event age; unbounded silent growth is not accepted.

## Compatibility and Migration

This is a clean cutover, not dual-write migration.

```text
old runtime off
-> PostgreSQL migrations
-> authenticated Chat runtime on
-> verification
-> legacy source/data removal
```

Do not dual-write SQLite and PostgreSQL. Do not read SQLite as fallback. Do not
proxy removed URLs. Before cutover, inspect legacy data; after cutover,
PostgreSQL is authoritative.

Historical docs and ADRs remain for audit. Current architecture, development,
README, security, runbook, and roadmap docs must state the new mounted behavior
and identify removed capabilities.

## Rollout Sequence

1. Add failing target-architecture boundary tests.
2. Add/verify final PostgreSQL schema migration.
3. Remove Workspace dependency from conversation domain/service.
4. Introduce the RuntimeContainer and PostgreSQL conversation wiring.
5. Add standalone conversation routes and auto-create Chat behavior.
6. Make authentication unconditional and update frontend login gating.
7. Replace SQLite readiness and evaluation fixtures.
8. Remove Workspace and Planner backend/frontend surfaces.
9. Remove legacy Memory backend/evaluation surfaces.
10. Remove Memory Manager/control API and split background recording from command
    service.
11. Remove application SQLite adapters, schema registry, configuration, and
    approved disposable data.
12. Update canonical documentation and run complete verification.

Deletion happens after each replacement behavior is green, even though the
approved result is a clean break. This keeps failures attributable and rollback
reviewable.

## Rollback

1. Before data cutover, rollback is branch/worktree abandonment.
2. After PostgreSQL migration but before traffic, downgrade only in an isolated
   environment after proving no dependent rows exist.
3. After traffic, rollback uses application release rollback against the
   forward-compatible PostgreSQL schema; it does not restore SQLite writes.
4. Before deleting any user-valued SQLite file, create an owner-approved export
   or recoverable quarantine artifact.
5. Restore PostgreSQL from a tested backup for destructive database failure.
6. Removed Workspace, Planner, legacy Memory, and Memory Manager behavior may be
   restored only by a separately approved design, not an emergency hidden flag.

## Testing and Verification

### Static Boundaries

1. No mounted or production backend source imports `sqlite3`, an application
   SQLite repository, Workspace, Planner, legacy Memory, or Memory Controls.
2. No frontend source imports Workspace, Planner, or Memory Manager modules.
3. No `APP_DB_PATH`, `WORKSPACE_DB_PATH`, or `AUTH_REQUIRED` compatibility flag
   remains in product configuration.
4. The only allowed `sqlite` references are historical docs, the completed
   inventory report, or third-party Chroma internals explicitly allowlisted by
   path; no application Python inventory or adapter remains after completion.

### Authentication

1. Every protected route rejects missing/malformed/invalid credentials.
2. No compatibility principal is created.
3. Cross-owner create/read/list/history/delete is denied without enumeration.
4. Wildcard CORS fails configuration validation.

### PostgreSQL Conversation Runtime

1. Empty upgrade, downgrade, and re-upgrade pass.
2. Final schema contains no Workspace compatibility table/column.
3. Auto-create and explicit-create standalone conversations pass.
4. User message and outbox are atomic.
5. Message order, pagination, owner scope, and retention pass.
6. Chat user-write failure prevents RAG/model invocation.
7. Assistant-write failure is represented honestly.
8. Required PostgreSQL tests run with zero required skips.

### Removed Surface

1. Workspace, Planner, legacy Memory, and Memory Controls URLs return `404`.
2. Frontend build contains no route, button, drawer, modal, or service for those
   capabilities.
3. Anonymous users cannot render or invoke Chat.
4. Historical behavior tests are removed only when an explicit replacement or
   removal assertion covers their intent.

### Full Verification

Run freshly on the exact change set:

```text
Python compileall
backend unit tests
PostgreSQL migration and integration tests with required services running
frontend lint, tests, and production build
Docker Compose validation
static forbidden-import/config scans
Git diff and untracked-file review
```

Any required skip, conflict marker, dirty generated database, or failing check
blocks completion.

## Acceptance Criteria

1. The exact spec, required ADRs, and implementation plan are approved before
   deletion begins.
2. Mounted product routes match the target surface exactly.
3. Anonymous Chat is impossible at backend and frontend boundaries.
4. An authenticated owner can create, list, continue, read history, and delete
   multiple standalone conversations without a Workspace.
5. PostgreSQL is the only application relational source of truth.
6. User message and extraction intent commit atomically when capture is enabled.
7. Chat preserves generation and partial-persistence behavior without legacy
   Memory retrieval.
8. Workspace, Planner, legacy Memory, and user-facing Memory management are
   absent from runtime and source delivery.
9. Background V2 Memory domain/persistence remains importable and its retained
   tests pass without command-service dependencies.
10. Readiness, security, observability, and evaluation no longer depend on
    application SQLite.
11. Required PostgreSQL tests execute without skips and full verification passes.
12. Legacy data receives an explicit inventory-backed disposal or quarantine
    decision before deletion.
13. Canonical documentation distinguishes removed behavior, retained V2
    capability, and future Single-Step Context Agent work.
14. No Git delivery occurs before repository-owner review of the verified change
    set.

## Proposed Supersession

After approval and verified implementation, this clean-break design supersedes
the mounted-target portions of:

1. `2026-09-03-trip-workspace-foundation-design.md`.
2. `2026-09-04-conversation-persistence-design.md` where it requires Workspace
   and SQLite.
3. `2026-09-04-shadow-memory-extraction-design.md`.
4. `2026-09-04-memory-retrieval-design.md` for legacy SQLite retrieval.
5. `2026-09-05-trip-planner-state-design.md`.
6. `2026-09-06-frontend-workspace-rebuild-design.md`.
7. `2026-09-07-risk-based-memory-control-amendment.md` for the currently mounted
   user-control surface; its risk rules remain historical input to any future
   Chat command design.

The documents remain in the repository as historical evidence. Supersession
does not occur merely because this specification is in review.

## Required ADRs

1. Authenticated Chat-only product container and removal of Workspace/Planner.
2. PostgreSQL-only application relational persistence and SQLite retirement.
3. Removal of the public Memory management surface while preserving background
   Memory and privacy deletion obligations.
4. Standalone conversation ownership, route contract, and auto-create behavior.
5. Clean-break migration, data disposal, and rollback authority.

Existing ADRs 0011 through 0014 remain relevant where they do not require a
removed surface. ADR 0017 remains historical authority for the old control
surface until this spec and its superseding ADR are approved and implemented.

## Approval Record

Version 0.1 is in review. Approval authorizes preparation of the required ADRs
and an implementation plan. It does not authorize source deletion, database
migration, data disposal, staging, commit, push, merge, release, or deployment.
