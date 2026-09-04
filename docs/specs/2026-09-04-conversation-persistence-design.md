# Conversation Persistence Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-04 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Runtime milestone R4 - conversation and message contracts, shared local application store, orchestration seam, optional chat conversation binding, and minimal backend routes for appending and inspecting conversation records |
| Parent design | [Architecture Baseline Design](./2026-08-31-architecture-baseline-design.md), version 0.1; [Roadmap and Learning Design](./2026-08-31-roadmap-and-learning-design.md), version 0.1 |
| Depends on | R3 accepted change set merged at `2f632e2`; [Trip Workspace Foundation Design](./2026-09-03-trip-workspace-foundation-design.md), version 0.1; [ADR 0002](../adr/0002-trip-workspace-as-primary-product-container.md); [ADR 0003](../adr/0003-local-sqlite-workspace-storage-boundary-for-r3.md); [Target-state Architecture](../architecture/target-state.md); [Data Model](../architecture/data-model.md); [Security Policy](../../SECURITY.md); [Memory Evaluation](../evaluation/memory-evaluation.md) |
| Architecture approval | Repository owner approved R4 spec version 0.1 in conversation on 2026-09-04, after confirming every design decision in a structured design interview on the same date |
| Implementation plan | [Conversation Persistence Implementation Plan](../plans/2026-09-04-conversation-persistence-implementation.md), version 0.1 |
| Related issue | None - R4 specification drafting was authorized by the repository owner in conversation on 2026-09-04 |
| Superseded document | None |

## Summary

R4 makes conversations and messages durable so that later milestones have a
place to attach provenance. It adds a `backend/conversations/` module, promotes
the R3 workspace database into one shared local application store with a
per-module schema registry, introduces the first `Conversation Orchestrator`
seam named by the target architecture, and lets `POST /api/v1/chat` optionally
bind a turn to a conversation.

The design is deliberately narrow in three ways. Message content is stored but
never logged and never deleted by R4. `owner_user_id` remains the local
development scope label established by R3, so R4 adds no authentication. The
frontend is out of scope, which means R4 delivers the capability to persist a
turn without yet persisting real browser traffic.

Everything R4 adds is additive at the public boundary. A client that sends only
`{"message": "..."}` receives a byte-for-byte identical response to the one it
receives today.

## Current-state Evidence

Verified against the repository at `2f632e2` on branch `feature/agent-memory`,
with `447 passed` from `./.venv/bin/python -m pytest backend/tests`.

| Claim | Evidence |
| --- | --- |
| The chat contract carries one field in and three fields out | `backend/app/schemas/chat.py` defines `ChatRequest(message: str)` and `ChatResponse(reply, model, citations)` |
| The chat route calls RAG directly with no coordination layer | `backend/app/api/chat.py:18` posts to `/chat`, resolves a process-global `RAGService`, and calls `generate_answer` |
| RAG generation is already decomposed into three modules | `backend/rag/generation/rag_service.py:41` is a 35-line facade calling `KnowledgeRetriever.retrieve`, `ContextAssembler.assemble` (`backend/rag/generation/context.py:23`), and `LLMGenerator.generate` (`backend/rag/generation/llm.py:54`) |
| Evaluation consumes the three RAG stages directly, not the facade | `backend/rag/evaluation/runtime.py:105` and `:183` construct `KnowledgeRetriever`, `ContextAssembler`, and `LLMGenerator` themselves |
| No conversation, message, or user record exists anywhere | `backend/` contains no conversation or message module, schema, route, or table |
| The workspace store owns one table behind one interface | `backend/workspaces/sqlite_repository.py:37` defines `TABLE_NAME = "trip_workspaces"`; `backend/workspaces/repository.py:32` defines the `WorkspaceRepository` protocol |
| Workspace schema version lives in `PRAGMA user_version` | `backend/workspaces/sqlite_repository.py:36` sets `SCHEMA_VERSION = 1`; `:160` reads the pragma; `:165` writes it |
| The workspace adapter already fails closed on version mismatch | `backend/workspaces/sqlite_repository.py:170` raises with `Refusing to migrate automatically.` |
| SQLite foreign-key enforcement is not enabled | `backend/workspaces/sqlite_repository.py` contains no `PRAGMA foreign_keys`; SQLite leaves enforcement off per connection by default |
| The database path is resolved in exactly one place | `backend/app/config.py:20` defines `WORKSPACE_DB_PATH`; `backend/app/api/workspaces.py:52` is the single construction site |
| Workspace list ordering is already deterministic | `backend/workspaces/sqlite_repository.py:78` orders by `updated_at DESC, created_at DESC, workspace_id ASC` and excludes `deleted` |
| The browser keeps conversation state in volatile memory only | `frontend/src/App.jsx:10` holds `const [messages, setMessages] = useState([])` with no `localStorage` or `sessionStorage` write |
| The target architecture names the missing coordination layer | [Target-state Architecture](../architecture/target-state.md) line 45 records the `Conversation Orchestrator` current baseline as "Current chat route calls RAG directly" |
| Conversation storage technology is an explicitly open question | [Target-state Architecture](../architecture/target-state.md) line 266 asks "Which storage technology owns users, workspaces, conversations, messages, itinerary versions, and memory records?" |
| Conversation summary belongs to the memory layer, not to storage | [Target-state Architecture](../architecture/target-state.md) line 89 lists "Conversation summary" as a memory layer updated from conversation events |
| Conversation and message fields are already specified conceptually | [Data Model](../architecture/data-model.md) lines 161 and 174 define both entities |
| `trace_visibility` has a purpose but no vocabulary | [Data Model](../architecture/data-model.md) line 180 defines it only as "Whether the message can be used in evaluation traces" |
| Message content is classified as user content requiring an approved lifecycle | [Security Policy](../../SECURITY.md) line 76 classifies "Chat text, itinerary preferences, future workspace or conversation content" as `User content` |
| Full conversation logging is forbidden by default | [Security Policy](../../SECURITY.md) line 86 states that full prompt, conversation, retrieved content, or model-output logging is not the default |
| A durable user-data store must name six lifecycle properties | [Security Policy](../../SECURITY.md) line 140 enumerates purpose and owner, access and scope, retention trigger, deletion mechanism and resulting state, derived-copy behavior, and verification evidence |
| Numeric retention periods may not be invented yet | [Security Policy](../../SECURITY.md) line 150 states "Do not invent a numeric retention period before a concrete store and lifecycle owner exist" |
| Missing provenance makes memory evidence invalid rather than passing | [Memory Evaluation](../evaluation/memory-evaluation.md) lines 194 to 197 state that when the harness cannot establish identity, scope, deletion state, promotion state, or correction precedence, the affected evidence is `INVALID`, and that lack of observability can never be treated as a zero event count |
| The milestone gate and required evidence are already recorded | [Master Roadmap](../roadmap/master-roadmap.md) line 79 sets the `R4` exit gate as "Messages persist with retention and privacy boundaries named" with "Integration tests and storage rollback evidence" |

## Context

R3 established `TripWorkspace` as the primary product container and proved that
a local SQLite adapter behind a repository interface is reviewable, testable,
and honest about its limits. It deliberately stopped there: no conversation, no
message, no memory, no planner state.

Every milestone after R3 needs message provenance before it can be evaluated.
`MemoryCandidate.source_message_id` and `MemoryRecord.provenance` in the data
model both point at a message. `ItineraryVersion.created_from_message_id` points
at a message. `EvaluationTrace` records `message_id` and `response_message_id`.
Without a message store these fields have no referent, and the memory
evaluation protocol treats unestablished provenance as `INVALID` evidence rather
than as a pass.

R4 is therefore the smallest change that unblocks R5 through R7. It is also the
first milestone that must store substantial user-authored text, which raises the
privacy stakes above R3: a workspace title is a short label, while message
content is the user's own words.

Two architectural questions that R3 was allowed to defer now come due. The
first is which store owns conversations, given that `PRAGMA user_version`
provides exactly one version slot per SQLite file and R3 already claimed it. The
second is where coordination lives once a single request has to both persist a
turn and generate an answer, because the target architecture assigns that job to
a `Conversation Orchestrator` that does not yet exist.

## Users

1. The repository owner, who needs durable conversation state before designing
   memory extraction and who reviews every change against approved governance.
2. A local developer or automated test, which creates conversations and appends
   messages through backend routes without a browser.
3. Later runtime milestones `R5`, `R6`, and `R7`, which consume `message_id`,
   `conversation_id`, and `workspace_id` as provenance and scope.
4. The evaluation harness from `R2`, which must remain completely independent of
   conversation modules while continuing to measure RAG quality.
5. A future browser client, which will read and write conversations once
   frontend work is separately approved.

## Problem Statement

The application can answer one question at a time and forget it immediately.
Nothing records what the user asked, what the assistant replied, or in which
order. The browser holds the visible transcript in volatile React state, so a
page reload destroys it, and the backend never sees a conversation identifier at
all.

This blocks the product roadmap at a specific point. Memory extraction cannot
cite the message a preference came from. Planner decisions cannot reference the
turn that produced them. Evaluation traces cannot link a score to a request.
Each of those milestones would otherwise have to invent its own provenance
scheme, and the memory safety gates that depend on scope and correction
precedence would be unmeasurable.

Two secondary problems make this worse if left unaddressed. The R3 storage
boundary cannot accept a second module without a version collision, so any
milestone that adds a table has to solve schema versioning first. And the chat
route currently owns both request validation and direct RAG invocation, so any
milestone that adds a second concern to a chat turn has nowhere to put it except
inside the route handler or inside the RAG module, both of which violate an
established boundary.

R4 must solve all three without overstating maturity. A local SQLite file is not
a production data platform. A caller-supplied `owner_user_id` is not
authentication. Storing a message is not a retention policy.

## Goals

1. Define `Conversation` and `Message` as durable runtime records scoped to an
   existing `TripWorkspace`.
2. Add a `backend/conversations/` module with value contracts, a repository
   interface, a local SQLite adapter, and a service that owns validation,
   identity, ordering, and timestamps.
3. Promote the R3 workspace database into one shared local application store
   whose schema version is tracked per module rather than per file.
4. Keep the shared store safe against an older build by leaving a sentinel that
   makes a pre-R4 workspace adapter fail closed rather than write into an R4
   database.
5. Introduce a `Conversation Orchestrator` module that coordinates conversation
   persistence with RAG generation, so neither the route handler nor the RAG
   module gains the other's responsibility.
6. Let `POST /api/v1/chat` accept an optional `conversation_id` and, when
   present, persist the user turn and the assistant turn with explicit success
   or failure reporting.
7. Preserve the existing chat contract exactly for any caller that does not send
   `conversation_id`, and preserve `GET /health` and every R3 workspace route
   unchanged.
8. Add minimal routes for creating a conversation, inspecting a conversation,
   listing conversations in a workspace, appending a message, and reading
   message history with deterministic order and cursor pagination.
9. Guarantee that message order is a stored fact rather than a timestamp
   coincidence, because later provenance depends on turn order.
10. Prevent a public caller from forging an assistant turn, so that memory
    extraction in `R5` cannot be poisoned through the public API.
11. Name every privacy and retention property required by the security policy
    without inventing a numeric retention period or implementing deletion.
12. Keep `backend/rag`, `backend/rag/evaluation`, and `backend/workspaces` free
    of any dependency on conversation or orchestration modules.
13. Provide deterministic unit and integration tests that need no model
    provider, embedding model, Chroma data, Docker, or network access.
14. Define what "storage rollback evidence" means for this repository, since the
    roadmap requires it and no prior milestone has defined it.
15. Update canonical documentation so R4 behavior is discoverable and maturity
    language stays honest.

## Non-goals

1. No user authentication, authorization, sessions, OAuth, tenant isolation, or
   collaboration membership. `owner_user_id` remains a local development scope
   label.
2. No frontend work. The browser client is not modified, so the visible
   transcript remains volatile and real browser traffic remains unpersisted.
3. No conversation summarization. The `summary` field in the data model gets no
   column and no producer in R4.
4. No message or conversation update, edit, archive, deletion, tombstoning,
   redaction, sharing, import, export, or full-text search.
5. No memory record, memory candidate, itinerary version, trip decision,
   planner operation, or evaluation trace persistence.
6. No production database, ORM, migration framework, secret manager, deployment
   topology, or observability vendor selection.
7. No change to RAG retrieval behavior, prompt content, generation parameters,
   citation mapping, Chroma collections, embedding models, evaluation metrics,
   benchmark datasets, or R1/R2 baseline artifacts.
8. No request body size limit, rate limit, or abuse control.
9. No numeric retention period, scheduled expiry, or background cleanup job.
10. No claim of production readiness, privacy compliance, or public API safety.
11. No stage, commit, push, PR, merge, tag, release, or history rewrite.

## Assumptions

1. The R3 change set is merged and green before R4 implementation starts, and
   the merge commit `2f632e2` with `447 passed` is the integration base.
2. A Python standard-library `sqlite3` adapter remains sufficient for local
   development and deterministic tests through R4.
3. Conversation and message records can use server-generated opaque identifiers
   rather than caller-supplied identifiers, matching the R3 identity rule.
4. A caller-supplied `owner_user_id` remains acceptable at the workspace level
   because R4 still makes no authorization claim, and conversations inherit
   scope from their workspace rather than carrying their own owner label.
5. Storing message content in a local SQLite file is acceptable for development
   because R4 names its lifecycle properties and forbids content logging, and
   because the routes are not publicly exposed.
6. Message ordering within one conversation can be represented by a stored
   monotonic integer without requiring a distributed sequence service.
7. The shared store can create its schema on first use without a general
   migration framework, as ADR 0003 already accepted for R3.
8. Extending the chat response with an additive object is acceptable to the
   repository owner because the R3-frozen fields keep their exact names, types,
   and values, and the new object is absent unless the caller opts in.
9. If implementation discovers that authentication, production storage,
   deletion semantics, summarization, a breaking chat change, or frontend work
   is required to complete R4, work stops and returns to design.

## Selected Approach

R4 adds a backend-only conversation foundation on a shared local application
store, coordinated by a new orchestration seam.

Four decisions define the approach.

**One store, versioned per module.** The R3 database is promoted from a
workspace-specific file to a shared local application database at
`APP_DB_PATH`, defaulting to `data/app/travel_agent.sqlite3`. Schema version
moves out of `PRAGMA user_version` and into a `schema_versions` table keyed by
module name, so a second module no longer collides with the first. The pragma is
not abandoned: R4 writes a sentinel value into it precisely so an older build
recognizes the file as incompatible.

**A new module owning conversation domain rules.** `backend/conversations/`
mirrors the R3 module shape with value contracts, a repository interface, a
SQLite adapter, and a service. It depends on `backend/workspaces/` in one
direction only, to verify that a conversation's parent workspace exists.

**A real orchestration seam.** `backend/orchestration/` receives the first
`ConversationOrchestrator`. It depends on both `backend/conversations/` and
`backend/rag/`, and nothing depends on it except the chat route. This keeps the
route thin, as R3 required, and keeps the RAG module unaware that conversations
exist.

**Additive chat binding.** `POST /api/v1/chat` accepts an optional
`conversation_id`. When absent, the request and response are exactly what they
are today. When present, the orchestrator persists the user turn before
generation, persists the assistant turn after generation, and reports the
outcome in an additive `conversation` object so a persistence failure is never
silent.

Message content is stored, never logged, and never deleted by R4. Ordering is a
stored `sequence` integer rather than an inferred timestamp comparison, because
later provenance depends on turn order being a fact.

## Alternatives Considered

### Alternative A: Keep `PRAGMA user_version` in one shared file

The conversation module could reuse the R3 file and the existing pragma.

SQLite provides one `user_version` slot per database file, and R3 already sets
it to `1`. A second module would either overwrite the workspace version or have
to encode two versions into one integer. Both make the fail-closed check at
`backend/workspaces/sqlite_repository.py:170` unreliable, which is the exact
safety property R3 was careful to establish. Rejected.

### Alternative B: One SQLite file per module

Each module could own a private database file with its own pragma, leaving R3
completely untouched.

This is the cheapest option today and its zero-touch property is genuinely
valuable, because R3 has just merged. It also loses little in R4 specifically:
foreign keys are not enforced in the current adapter, R4 implements no workspace
deletion so orphan rows cannot occur, and a service-level existence check gives
better error semantics than an integrity violation.

It was rejected on trajectory rather than on R4 mechanics. `R5` memory, `R6`
memory retrieval, and `R7` planner state each need storage before `R9` and `R10`.
Committing to one file per module now produces four or five local databases, each
with an independent version slot to keep consistent, and each unable to
participate in a single transaction with the others. The `updated_at` bump this
design requires when appending a message already spans two tables, and keeping
that atomic is simpler in one file.

### Alternative C: One shared file with a per-module schema registry

The shared file records each module's schema version in a `schema_versions`
table, so modules coexist without contending for one pragma.

This costs a bounded refactor of R3: the version read and write inside
`_initialize_schema`, three tests that assert version behavior directly, the
setting rename with a deprecated alias, and the documentation references. In
exchange it scales to `R5` and `R7` without further storage redesign, keeps
cross-table transactions available, and preserves the fail-closed guarantee by
leaving a sentinel in the pragma for older builds. Selected.

### Alternative D: Adopt a production database and migration framework now

R4 could introduce Postgres, an ORM, and migrations.

ADR 0003 rejected this for R3 because the project lacks authentication,
deployment readiness, retention policy, backup and restore policy, and
production operations ownership. Every one of those conditions is still unmet at
`2f632e2`. Adopting production storage here would create more architecture
surface than R4 can honestly validate, and it would couple a storage migration
to a provenance milestone. Rejected.

### Alternative E: Persist inside the chat route handler

The chat route could call the conversation service directly around its existing
RAG call.

This is the smallest diff, but it puts orchestration policy into a route
handler. R3 Goals item 8 requires that normalization, validation, identity, time,
and storage access live behind a module rather than in a route. It also gives the
route two distinct failure domains to reconcile inline, which is precisely the
logic that later milestones will need to extend for memory reads and trace
writes. Rejected.

### Alternative F: Persist inside `RAGService`

`RAGService` already coordinates retrieval, context assembly, and generation, so
it could also persist the turn.

`RAGService` lives in `backend/rag/`. Giving it knowledge of conversation
storage is the same coupling that ADR 0002 rule 4 forbids between RAG and
workspace modules, and it would put a storage dependency inside the module that
`backend/rag/evaluation/runtime.py` consumes. Evaluation must stay independent of
product state. Rejected.

### Alternative G: A dedicated orchestration module

A new `backend/orchestration/` module depends on both the conversation module
and the RAG module, and the chat route delegates to it.

This is the layer the target architecture already names, whose recorded baseline
is "Current chat route calls RAG directly". `RAGService` is a 35-line facade
after `85ee61c`, so wrapping it is thin. The cost is one more module and one more
seam. Selected.

### Alternative H: Require `conversation_id` on every chat request

Chat could make `conversation_id` mandatory, which is simpler to reason about
than an optional binding.

This breaks the R3-frozen chat contract, requires a superseding ADR, and breaks
the current browser client immediately, even though the frontend is out of R4
scope. An optional field achieves the same provenance capability while keeping
existing callers byte-for-byte compatible. Rejected.

## User and System Flows

### Flow 1: Create a conversation in a workspace

1. A caller sends `POST /api/v1/workspaces/{workspace_id}/conversations` with an
   optional `title`.
2. FastAPI validates the JSON shape through the request schema.
3. The conversation service trims the title, verifies through the workspace
   repository interface that `workspace_id` exists, generates a `cv_` identity,
   and sets `created_at` and `updated_at` to one UTC moment.
4. The repository persists the record with `retention_state` `active`.
5. The API returns `201 Created` with the conversation record.

### Flow 2: Inspect one conversation

1. A caller sends `GET /api/v1/conversations/{conversation_id}`.
2. The service loads the record by identifier.
3. A missing record returns `404`; a found record returns the conversation
   response.

### Flow 3: List conversations in a workspace

1. A caller sends `GET /api/v1/workspaces/{workspace_id}/conversations`.
2. The service verifies the workspace exists and returns `404` when it does not.
3. The repository returns conversations for that workspace ordered by
   `updated_at` descending, then `created_at` descending, then `conversation_id`
   ascending, excluding `deleted` records.
4. The API returns `{"conversations": [ ... ]}`, an empty array when the
   workspace has none.

### Flow 4: Append a message directly

1. A caller sends `POST /api/v1/conversations/{conversation_id}/messages` with
   `role`, `content`, and optional `source` and `trace_visibility`.
2. The API rejects `assistant` and `tool` roles with `422`, because those roles
   are writable only through the orchestrator.
3. The service verifies the conversation exists, generates an `ms_` identity, and
   sets `created_at`.
4. Inside one immediate transaction the repository resolves the next `sequence`
   for that conversation, inserts the message, and bumps the conversation's
   `updated_at`.
5. The API returns `201 Created` with the message record including its
   `sequence`.

### Flow 5: Read message history

1. A caller sends `GET /api/v1/conversations/{conversation_id}/messages` with
   optional `after_message_id` and `limit`.
2. The service verifies the conversation exists and resolves the cursor to that
   message's `sequence`, returning `422` when the cursor does not belong to the
   conversation.
3. The repository returns up to `limit` messages with a greater `sequence`,
   ordered by `sequence` ascending.
4. The API returns `{"messages": [ ... ], "next_cursor": ...}`, where
   `next_cursor` is the last returned `message_id` when more records may exist
   and `null` otherwise.

### Flow 6: Chat without a conversation

1. A caller sends `POST /api/v1/chat` with only `message`.
2. The route delegates to the orchestrator, which performs no persistence.
3. The response contains exactly `reply`, `model`, and `citations`, with no
   `conversation` object, identical to current behavior.

### Flow 7: Chat bound to a conversation

1. A caller sends `POST /api/v1/chat` with `message` and `conversation_id`.
2. The orchestrator verifies the conversation exists, returning `404` when it
   does not.
3. The orchestrator persists the user message with `role` `user` and `source`
   `ui` before any model call. A persistence failure returns `500` and no model
   call is made.
4. The orchestrator calls the existing RAG path unchanged and receives `reply`,
   `model`, and `citations`.
5. The orchestrator persists the assistant message with `role` `assistant` and
   `source` `model`.
6. The API returns the generated answer plus a `conversation` object carrying
   `conversation_id`, `user_message_id`, `assistant_message_id`, and `persisted`.
   When the assistant write failed, `persisted` is `false` and
   `assistant_message_id` is `null`, and the reply is still returned.

### Flow 8: Existing workspace and health behavior

1. `GET /health` remains the Stage A health route with unchanged semantics.
2. Every R3 workspace route keeps its path, request shape, response shape, and
   status codes.
3. RAG retrieval, generation, and the R2 evaluation harness are unchanged and
   gain no conversation dependency.

## Components and Dependency Direction

| Module | Responsibility | Allowed dependencies |
| --- | --- | --- |
| Shared schema registry | Create and read the `schema_versions` table, resolve a module's version, and fail closed on an unsupported version or a legacy pragma value | Standard library, `sqlite3` |
| Conversation contracts | `Conversation` and `Message` value objects, role, source, trace-visibility, and retention vocabularies, validation helpers, identity generation | Standard library only |
| Conversation repository interface | Storage interface and repository error types used by the service and by tests | Conversation contracts |
| SQLite conversation repository | Schema version 1 initialization, `sequence` allocation, parameterized SQL, cursor reads, row mapping | Conversation contracts, repository interface, shared schema registry, `sqlite3`, `pathlib` |
| Conversation service | Create, get, list, append, and history use cases; input normalization; workspace existence verification; timestamps | Conversation contracts, conversation repository interface, workspace repository interface |
| Conversation orchestrator | Coordinate conversation persistence with RAG generation for one chat turn, and report persistence outcome | Conversation service, RAG service facade |
| Conversation API schemas | Public request and response JSON shapes for conversation and message routes | Pydantic, conversation contracts |
| Conversation API routes | Map HTTP requests and errors to service calls, enforce the public role restriction, emit minimal logs | FastAPI, conversation schemas, conversation service |
| Chat route | Validate the chat request and delegate one turn to the orchestrator | FastAPI, chat schemas, conversation orchestrator |
| Application wiring | Include the conversation router under `settings.API_V1_STR` and resolve `APP_DB_PATH` | FastAPI app, conversation router, settings |

Required dependency direction:

```text
FastAPI conversation routes -> ConversationService -> ConversationRepository interface
                                                      -> SQLite adapter -> shared schema registry
                            ConversationService     -> WorkspaceRepository interface

FastAPI chat route -> ConversationOrchestrator -> ConversationService
                                               -> RAGService

backend/workspaces  -> no dependency on conversation or orchestration modules
backend/rag         -> no dependency on conversation or orchestration modules
Evaluation harness  -> no dependency on conversation or orchestration modules
```

The one-way rule between conversations and workspaces mirrors the one-way
evidence seam that ADR 0001 established between the RAG runtime and evaluation.
A future milestone that needs a workspace module to read conversation state
requires a separate approved design.

`sqlite3` and table DDL may appear only in
`backend/workspaces/sqlite_repository.py`,
`backend/conversations/sqlite_repository.py`, and the shared schema registry
module. `APP_DB_PATH` may appear only in `backend/app/config.py` and at the
dependency construction sites in `backend/app/api/workspaces.py` and
`backend/app/api/conversations.py`.

## Behavioral and Data Contracts

### Conversation record

| Field | Type | Constraints and defaults |
| --- | --- | --- |
| `conversation_id` | string | Server-generated opaque string beginning with `cv_`; never accepted from caller input; duplicate generation retried once, then a controlled infrastructure error |
| `workspace_id` | string | Required; must reference an existing workspace at creation time |
| `title` | string or absent | Optional trimmed string, maximum 120 characters; blank normalizes to absent |
| `retention_state` | enum | One of `active`, `summarized`, `archived`, `deletion_requested`, `deleted`. R4 creates `active` only and implements no transition |
| `created_at` | UTC ISO timestamp | Server-generated |
| `updated_at` | UTC ISO timestamp | Server-generated; bumped when a message is appended |

### Message record

| Field | Type | Constraints and defaults |
| --- | --- | --- |
| `message_id` | string | Server-generated opaque string beginning with `ms_`; never accepted from caller input |
| `conversation_id` | string | Required; must reference an existing conversation |
| `sequence` | integer | Server-assigned, monotonic within one conversation, starting at `1`; unique per conversation |
| `role` | enum | One of `user`, `assistant`, `tool`, `system_event`. The public append route accepts only `user` and `system_event` |
| `content` | string | Required, non-empty after trimming. No maximum length in R4 |
| `source` | enum | One of `ui`, `tool`, `model`, `system`, `import`; defaults to `ui` on the public route and is set to `model` for orchestrator-written assistant turns |
| `trace_visibility` | enum | One of `excluded`, `included`; defaults to `excluded` |
| `created_at` | UTC ISO timestamp | Server-generated |

`content` deliberately carries no maximum length, which departs from the R3 rule
that every text field is bounded. The chat route already accepts an unbounded
`message`, so imposing a storage limit would turn requests that succeed today
into failures once a conversation is bound. Request size limiting belongs at the
API boundary and is recorded as a known gap rather than solved here.

Message records carry no `retention_state` of their own. A message follows the
lifecycle of its parent conversation, so a future deletion milestone has exactly
one place to express intent.

### Schema

```sql
CREATE TABLE IF NOT EXISTS schema_versions (
    module  TEXT PRIMARY KEY,
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL,
    title           TEXT,
    retention_state TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversations_workspace
ON conversations (workspace_id, updated_at DESC, created_at DESC, conversation_id ASC);

CREATE TABLE IF NOT EXISTS messages (
    message_id       TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL,
    sequence         INTEGER NOT NULL,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    source           TEXT NOT NULL,
    trace_visibility TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    UNIQUE (conversation_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
ON messages (conversation_id, sequence ASC);
```

The workspace module registers `('workspaces', 1)` and the conversation module
registers `('conversations', 1)`. There is no `summary` column: populating it
requires a model call, and the target architecture assigns conversation summary
to the memory layer, so it is deferred with the rest of memory work.

`UNIQUE (conversation_id, sequence)` is defense in depth rather than the primary
ordering mechanism. Sequence allocation runs inside a `BEGIN IMMEDIATE`
transaction that reads `MAX(sequence)` and inserts, which serializes writers on
one local database. The constraint exists so that a future concurrent writer
fails loudly instead of silently duplicating a turn position.

### Repository interfaces

```python
class ConversationRepository(Protocol):
    def create(self, conversation: Conversation) -> Conversation: ...
    def get(self, conversation_id: str) -> Conversation | None: ...
    def list_by_workspace(self, workspace_id: str) -> tuple[Conversation, ...]: ...
    def append_message(self, message: MessageDraft) -> Message: ...
    def list_messages(
        self, conversation_id: str, after_sequence: int | None, limit: int
    ) -> tuple[Message, ...]: ...
```

`MessageDraft` carries every message field except `sequence`, because sequence
is assigned by the adapter inside the write transaction rather than by the
caller.

### Routes

| Method and path | Success | Errors |
| --- | --- | --- |
| `POST /api/v1/workspaces/{workspace_id}/conversations` | `201` with the conversation record | `404` when the workspace does not exist; `422` for validation failures; `500` for storage failure |
| `GET /api/v1/workspaces/{workspace_id}/conversations` | `200` with `{"conversations": [ ... ]}` | `404` when the workspace does not exist; `500` for storage failure |
| `GET /api/v1/conversations/{conversation_id}` | `200` with the conversation record | `404` when absent; `500` for storage failure |
| `POST /api/v1/conversations/{conversation_id}/messages` | `201` with the message record | `404` when the conversation does not exist; `422` for validation failures and for a restricted role; `500` for storage failure |
| `GET /api/v1/conversations/{conversation_id}/messages` | `200` with `{"messages": [ ... ], "next_cursor": ...}` | `404` when the conversation does not exist; `422` for an invalid cursor or limit; `500` for storage failure |

Conversation collection routes are nested under a workspace so that scope is a
structural property of the path rather than a validation step a future change
could forget. Single-item routes are flat because `conversation_id` is globally
unique, matching the R3 precedent of `GET /api/v1/workspaces/{workspace_id}`.

Message reads use cursor pagination with `after_message_id` and `limit`, where
`limit` defaults to `50` and is capped at `200`. Messages are ordered by
`sequence` ascending, which is the reading order of a conversation and the
opposite direction from the R3 newest-first list. That inversion is intentional:
a workspace list is a chooser, while a message list is a transcript.

Conversation lists are not paginated in R4, matching the R3 decision to defer
pagination until a real listing pressure exists.

### Create conversation request

```json
{
  "title": "Da Nang food plan"
}
```

### Append message request

```json
{
  "role": "user",
  "content": "Nên đi Đà Nẵng vào tháng mấy?",
  "source": "ui",
  "trace_visibility": "excluded"
}
```

### Message response

```json
{
  "message_id": "ms_example",
  "conversation_id": "cv_example",
  "sequence": 1,
  "role": "user",
  "content": "Nên đi Đà Nẵng vào tháng mấy?",
  "source": "ui",
  "trace_visibility": "excluded",
  "created_at": "2026-09-04T00:00:00Z"
}
```

### Chat contract

The request gains one optional field:

```json
{
  "message": "Nên đi Đà Nẵng vào tháng mấy?",
  "conversation_id": "cv_example"
}
```

When `conversation_id` is absent the response is exactly the current contract:

```json
{
  "reply": "...",
  "model": "gpt-4o-mini",
  "citations": [{ "title": "...", "url": "..." }]
}
```

When `conversation_id` is present the response adds one object and changes
nothing else:

```json
{
  "reply": "...",
  "model": "gpt-4o-mini",
  "citations": [{ "title": "...", "url": "..." }],
  "conversation": {
    "conversation_id": "cv_example",
    "user_message_id": "ms_user_example",
    "assistant_message_id": "ms_assistant_example",
    "persisted": true
  }
}
```

`reply`, `model`, and `citations` keep their exact names, types, and values in
both cases. The `conversation` object is absent, not null, when the caller does
not opt in, so existing clients observe no difference.

### Settings

`APP_DB_PATH` defaults to `data/app/travel_agent.sqlite3`. `WORKSPACE_DB_PATH`
is retained as a deprecated alias: when it is set and `APP_DB_PATH` is not, the
alias value is used and a deprecation warning is logged once. This keeps an
existing local environment working without silently ignoring its configuration.

## Errors and Edge Cases

1. Creating a conversation under a `workspace_id` that does not exist returns
   `404` and writes no record.
2. A `title` longer than 120 characters returns `422`.
3. A blank `title` normalizes to absent rather than failing.
4. Appending a message with blank or whitespace-only `content` returns `422` and
   writes no record.
5. Appending a message with `role` `assistant` or `tool` through the public route
   returns `422`, naming the restriction without echoing message content.
6. Appending a message with an unknown `role`, `source`, or `trace_visibility`
   value returns `422`.
7. Appending a message to a `conversation_id` that does not exist returns `404`
   and writes no record.
8. Reading history with an `after_message_id` that does not exist, or that
   belongs to a different conversation, returns `422` rather than silently
   returning the whole transcript.
9. Reading history with a `limit` below `1` or above `200` returns `422`.
10. Reading history for a conversation with no messages returns an empty
    `messages` array and a `null` `next_cursor`.
11. A duplicate generated `conversation_id` or `message_id` is retried once; a
    second collision returns a controlled infrastructure error.
12. A `sequence` collision inside the write transaction is retried once; a second
    collision returns a controlled infrastructure error rather than reordering or
    overwriting a turn.
13. Chat with a `conversation_id` that does not exist returns `404` before any
    model call.
14. Chat where the user-message write fails returns `500` and makes no model
    call, so the caller is never charged for an unrecorded turn.
15. Chat where generation fails returns the existing generation error behavior,
    and the already-persisted user message remains as provenance.
16. Chat where the assistant-message write fails returns `200` with the reply and
    `persisted` set to `false` with a `null` `assistant_message_id`, so a
    persistence gap is visible rather than silent.
17. Opening the shared database with `PRAGMA user_version` set to a value other
    than `0` or the R4 sentinel, and without a `schema_versions` table, fails
    closed with a controlled storage error and no automatic migration.
18. A `schema_versions` row whose version exceeds the version this build supports
    fails closed with a controlled storage error.
19. A stored row whose `role`, `source`, `trace_visibility`, or `retention_state`
    is outside the governed vocabulary fails closed through a repository error
    rather than being coerced.
20. SQLite open, schema, or write failure returns `500` with a controlled message
    that exposes no filesystem path, SQL text, or user content.
21. Existing chat errors, workspace errors, RAG behavior, and evaluation behavior
    remain governed by R1, R2, and R3.

## Security and Privacy

Message content is user content under the security policy classification, which
requires minimization, an approved store, and an approved lifecycle. R4 accepts
the store and names the lifecycle without implementing deletion.

1. Never log message `content`, conversation `title`, or any substring of either.
   Logs carry `conversation_id`, `message_id`, `sequence`, `role`, counts, route
   or action names, and failure classes only.
2. The existing chat route logs a prefix of the user message. R4 does not extend
   that behavior to the conversation module and does not add a second content
   log. Removing the existing prefix log is recorded as a known gap owned by a
   security-hardening milestone.
3. `trace_visibility` defaults to `excluded`, so no persisted message becomes
   evaluation input without an explicit decision. This is default-deny, matching
   the policy that full conversation logging is not the default.
4. HTTP error details never echo message content, conversation titles, database
   paths, SQL text, or credentials.
5. `owner_user_id` remains a local development scope label owned by the workspace
   record. Conversations inherit scope from their workspace and carry no owner
   field of their own, so R4 introduces no second, weaker identity surface.
6. R4 claims no cross-user or cross-workspace isolation beyond deterministic
   repository filtering. Conversation and message routes are unauthenticated and
   must not be exposed publicly.
7. Secrets, credentials, and tokens must never be stored in conversation or
   message fields, fixtures, logs, or documentation examples. Tests use synthetic
   Vietnamese and English travel text only.
8. The local database file is developer state. It must not be committed, and it
   must not be deleted without the repository owner naming the exact path.

The six lifecycle properties required before a durable user-data store is used
are named here:

| Property | R4 position |
| --- | --- |
| Purpose and decision owner | Provide message provenance for later memory, planner, and trace milestones. Decision owner is the repository owner |
| Access and scope | Local backend process only. Scope is `workspace_id` then `conversation_id`. No authentication, no authorization, no public exposure |
| Retention trigger | Not defined numerically. R4 defines the `retention_state` vocabulary and creates `active` records only. A numeric period requires a concrete store owner and a later approved design |
| Deletion mechanism and resulting state | Named, not implemented. Conversation-level deletion will move `retention_state` to `deletion_requested` and then to `deleted`, with message rows following the parent conversation. Hard deletion versus tombstoning is a security-hardening decision |
| Backup, replica, cache, and derived-copy behavior | None exists. There is no backup, replica, cache, export, or derived copy of the local database in R4. Evaluation artifacts contain no conversation data |
| Verification evidence | Deletion behavior cannot be verified in R4 because it is not implemented. R4 verifies instead that no deletion path exists, that listing excludes `deleted`, and that content never reaches logs |

## Observability and Operations

Expected log events, all content-free:

1. Conversation created: route or action, `conversation_id`, `workspace_id`.
2. Conversation retrieved: route or action, `conversation_id`.
3. Conversation list requested: route or action, `workspace_id`, count.
4. Message appended: route or action, `conversation_id`, `message_id`,
   `sequence`, `role`.
5. Message history requested: route or action, `conversation_id`, count, whether
   a cursor was supplied.
6. Chat turn persisted: `conversation_id`, `user_message_id`,
   `assistant_message_id`, `persisted`.
7. Chat turn persistence degraded: `conversation_id`, the stage that failed, and
   the failure class, without content.
8. Storage failure: failure class and route or action only.
9. Schema registry initialization: module name and version.
10. Deprecated alias used: one warning naming `WORKSPACE_DB_PATH` without its
    value.

The development guide must document `APP_DB_PATH`, its default path, the
deprecated alias behavior, the five conversation routes, the optional chat field,
and the statement that local SQLite is not production storage readiness. R4 must
not change Stage A health semantics to imply conversation readiness.

## Testing and Evaluation

1. Conversation and message contract tests: identity prefixes, vocabularies,
   trimming, title bound, non-empty content, timezone-aware UTC timestamps, and
   the absence of a caller-settable identity or sequence.
2. Shared schema registry tests: fresh initialization, module version isolation,
   unsupported version fails closed, legacy `PRAGMA user_version` value fails
   closed, and R4 writes the sentinel.
3. Workspace regression tests: the existing R3 workspace suite continues to pass
   against the registry-based store, including the three tests that assert
   version behavior, rewritten to assert registry semantics and the sentinel.
4. Conversation service tests with an in-memory fake repository and a fake
   workspace repository: workspace existence enforcement, invalid input writing
   no record, identity retry then fail closed, and ordering delegated to the
   repository rather than recomputed.
5. SQLite conversation repository tests using temporary database paths: schema
   creation, create, get, list ordering, append, sequence allocation starting at
   `1` and incrementing per conversation independently, sequence uniqueness,
   `updated_at` bump on append, cursor reads, limit bounds, and fail-closed row
   mapping.
6. Cross-table transaction test: a failed message insert leaves the parent
   conversation's `updated_at` unchanged.
7. Route integration tests for all five conversation routes, including the
   restricted-role rejection, invalid cursor, limit bounds, and the guarantee
   that error bodies contain no submitted content.
8. Chat compatibility tests: a request without `conversation_id` returns exactly
   `reply`, `model`, and `citations` with no `conversation` key, and an empty
   message still returns `400`.
9. Chat binding tests with a fake RAG service and a temporary database: user
   message persisted before generation, assistant message persisted after,
   `persisted` true on success, `500` with no model call when the user write
   fails, and `persisted` false with a returned reply when the assistant write
   fails.
10. Import-boundary tests proving `backend/rag`, the evaluation modules, and
    `backend/workspaces` import no conversation or orchestration module.
11. Containment check proving `sqlite3` and table DDL appear only in the two
    repository adapters and the schema registry, and that `APP_DB_PATH` appears
    only in settings and the two dependency construction sites.
12. Storage rollback tests as defined in the Rollback section.
13. Compile and full backend test commands from the implementation plan.

R4 requires no RAG benchmark execution and no memory evaluation run. It adds no
metric to the R2 harness. The R1/R2 accepted change set is the prerequisite
evidence, and the memory evaluation protocol becomes measurable only after
provenance exists, which is what R4 provides.

## Data Flow and Lifecycle

Creation. A conversation is created explicitly through its route, never
implicitly by a chat request. A chat request with an unknown `conversation_id`
fails rather than creating one, so a typo cannot silently fragment a transcript.

Mutation. Conversation rows are mutated in exactly one way in R4: `updated_at`
advances when a message is appended. Titles are not editable, retention states do
not transition, and message rows are immutable after insert. Message ordering is
assigned once, inside the write transaction, and never recomputed.

Access. Reads are scoped structurally. Conversations are listed under a
workspace; messages are listed under a conversation. Listing excludes `deleted`
conversations, which has no effect in R4 because no record reaches that state,
and exists so a later deletion milestone cannot leak removed records through an
unchanged list route.

Retention. Every record is created `active` and stays `active`. The vocabulary
admits `summarized`, `archived`, `deletion_requested`, and `deleted`, none of
which has a producer in R4. `summarized` is reserved for the memory milestone
that introduces conversation summaries.

Deletion. Not implemented. Message rows have no independent retention state
precisely so that a future deletion decision is expressed once, on the parent
conversation, and cannot leave orphaned message state behind.

Provenance handoff. `conversation_id` and `message_id` are the stable
identifiers that `R5` memory candidates, `R6` selected memories, `R7` itinerary
versions and trip decisions, and a future evaluation trace will reference. R4
freezes their format and their generation ownership so those milestones do not
need to renegotiate identity.

## Failure and Recovery

| Failure | R4 behavior |
| --- | --- |
| Conversation or message validation fails | Controlled client validation error, no record written |
| Parent workspace absent | `404`, no record written |
| Parent conversation absent | `404`, no record written |
| Cursor invalid or foreign to the conversation | `422`, no partial page returned |
| Generated identity collides twice | Controlled infrastructure error, no partial write |
| Sequence collides twice | Controlled infrastructure error, no turn reordered or overwritten |
| Database directory absent | The adapter creates the directory under the configured path |
| Schema absent | The registry initializes module version 1 and writes the sentinel pragma |
| Schema version unsupported, or legacy pragma value present | Fail closed with a controlled storage error and no automatic migration |
| Message insert fails mid-transaction | Transaction rolls back; conversation `updated_at` unchanged; controlled `500` |
| Chat user-message write fails | `500` before any model call; the caller is not charged for an unrecorded turn |
| Chat generation fails | Existing generation error behavior; the persisted user message survives as provenance |
| Chat assistant-message write fails | `200` with the reply and `persisted` false; the gap is reported, never hidden |
| RAG or model provider fails | Unchanged from R1 and R2; conversation routes have no RAG dependency |
| An older pre-R4 build opens an R4 database | The sentinel pragma triggers the existing fail-closed path, so the older build refuses the file instead of writing into it |

## Capacity, Latency, and Cost

R4 is local development infrastructure with no production service objectives.
Minimum expectations:

1. Tests use temporary databases and in-memory fakes with no external service,
   no model provider, no embedding model, and no network access.
2. Conversation and message routes construct no RAG, embedding, Chroma, or
   model-provider client.
3. Create, get, list, append, and history are simple indexed SQLite operations.
   Both indexes match their query's ordering so no sort step is required.
4. Cursor pagination bounds the history response at 200 records, so a long
   transcript cannot produce an unbounded payload.
5. Chat with a bound conversation adds two local writes to a request already
   dominated by an external model call, so the added latency is not the
   significant term.
6. Documentation must not claim production scalability, durability, concurrency
   safety beyond a single local process, backup, or restore behavior.

Later production planning must define database capacity, backup, restore,
retention, concurrency, and migration budgets before public deployment. R4
settles none of them.

## Compatibility and Staged Migration

1. `GET /health` remains the Stage A health route with unchanged semantics.
2. `POST /api/v1/chat` remains available; `message` remains the only required
   field; `conversation_id` is optional and additive.
3. The chat response keeps `reply`, `model`, and `citations` with unchanged
   names, types, and values. The `conversation` object appears only when the
   caller supplies `conversation_id`.
4. Every R3 workspace route keeps its path, request shape, response shape,
   ordering, and status codes.
5. RAG retrieval, prompt content, generation parameters, citation mapping, Chroma
   collections, embedding models, evaluation metrics, and R1/R2 benchmark
   artifacts are unchanged.
6. The workspace repository interface and `TripWorkspace` contract are unchanged.
   Only the workspace adapter's version bookkeeping changes.
7. `WORKSPACE_DB_PATH` continues to work as a deprecated alias, so an existing
   local environment is not broken by the rename.
8. A database created by R3 is not adopted. The new default path is a new file,
   so the common case requires no migration at all.
9. Offline crawling, ETL, indexing, and evaluation runs remain opt-in
   state-changing operations outside default verification.

## Rollout and Migration

1. Approve this specification.
2. Accept ADR 0004 and ADR 0005.
3. Approve an implementation plan naming exact files, tests, documentation
   updates, verification commands, and rollback steps.
4. Implement the shared schema registry and migrate the workspace adapter's
   version bookkeeping onto it, keeping the R3 workspace suite green.
5. Implement conversation contracts and the repository interface test-first.
6. Implement the conversation service and SQLite adapter test-first, including
   sequence allocation and the `updated_at` bump.
7. Implement conversation API schemas and routes test-first, including the
   restricted-role rule.
8. Implement the orchestrator and the optional chat binding test-first, with
   compatibility tests proving the unbound path is unchanged.
9. Update canonical documentation.
10. Run fresh package verification, then return the change set for
    repository-owner review.

There is no conversation data to migrate, because R4 creates the first
conversation store. A database file created during R3 development remains on disk
untouched at its original path; it is local development state, and deleting it
requires an explicit repository-owner decision naming that exact path.

## Rollback

The roadmap requires storage rollback evidence for R4, and no earlier milestone
defined that term. R4 defines it as three separable layers.

**Code rollback.** Removing the conversation module, orchestration module,
conversation routes and schemas, the optional chat field, and the settings change
restores the R3 contract exactly. Evidence is the chat compatibility test proving
a `message`-only request returns exactly three fields, plus the boundary and
containment checks proving no residual dependency.

**Schema rollback.** This is the layer that needs deliberate design, because
abandoning `PRAGMA user_version` would otherwise make an R4 database look
uninitialized to an older build: it would read `user_version` as `0`, run its
`CREATE TABLE IF NOT EXISTS`, and set the pragma to `1`, writing into a database
it does not understand. R4 prevents that by writing a sentinel value into
`PRAGMA user_version` alongside the `schema_versions` table. A pre-R4 workspace
adapter reads the sentinel, finds it different from its expected `1`, and takes
the existing fail-closed path at
`backend/workspaces/sqlite_repository.py:170`, refusing to migrate. No change to
R3's fail-closed logic is required; only the sentinel value must be chosen.
Evidence is a test that opens an R4 database with the pre-R4 version check and
asserts a controlled storage error.

**Data rollback.** The local database file is developer state. R4 creates no
backup, replica, or export, so there is nothing to reconcile. Removing a
database file is never a default recovery step and requires the repository owner
to name the exact path and confirm recoverability.

Before owner acceptance, the entire change set can be withdrawn through normal
reviewed history without touching unrelated local data, Chroma state, R1/R2
evaluation artifacts, or the R3 workspace database.

After owner acceptance, replacing SQLite, adding a migration framework, changing
conversation route contracts, changing the chat contract, or introducing deletion
semantics each require a new approved specification and plan.

## Acceptance Criteria

1. This specification is approved at version 0.1 before any source edit.
2. ADR 0004 and ADR 0005 are accepted before an implementation plan is approved.
3. An implementation plan is approved before any source edit.
4. A shared schema registry records module versions independently, and the
   workspace module and conversation module coexist in one database file without
   version contention.
5. R4 writes the sentinel `PRAGMA user_version` value, and a pre-R4 workspace
   version check rejects an R4 database with a controlled storage error.
6. Opening a database with an unsupported registry version, or with a legacy
   pragma value and no registry, fails closed without automatic migration.
7. The conversation module exposes stable `Conversation` and `Message` contracts
   and a repository interface covering create, get, list, append, and history.
8. `POST /api/v1/workspaces/{workspace_id}/conversations` returns `201` with a
   server-generated `cv_` identity, and `404` when the workspace does not exist.
9. `GET /api/v1/conversations/{conversation_id}` returns the record or `404`.
10. `GET /api/v1/workspaces/{workspace_id}/conversations` returns
    `{"conversations": [ ... ]}` scoped to that workspace in deterministic
    newest-first order, excluding `deleted` records.
11. `POST /api/v1/conversations/{conversation_id}/messages` returns `201` with a
    server-assigned `sequence`, and rejects `assistant` and `tool` roles with
    `422`.
12. `sequence` starts at `1` per conversation, increments independently per
    conversation, is unique per conversation, and is never supplied by a caller.
13. Appending a message advances the parent conversation's `updated_at` in the
    same transaction, and a failed insert leaves it unchanged.
14. `GET /api/v1/conversations/{conversation_id}/messages` returns messages in
    `sequence` ascending order with working cursor pagination, a default limit of
    `50`, a maximum of `200`, and `422` for an invalid cursor or limit.
15. Invalid create, append, and history inputs fail before any storage write.
16. A chat request without `conversation_id` returns exactly `reply`, `model`,
    and `citations`, with no `conversation` key.
17. A chat request with a valid `conversation_id` persists the user turn before
    generation and the assistant turn after it, and reports
    `conversation.persisted` truthfully, including `false` with a returned reply
    when the assistant write fails.
18. A chat request with an unknown `conversation_id` returns `404` before any
    model call, and a failed user-message write returns `500` before any model
    call.
19. Logs and error bodies contain no message content, conversation title,
    database path, SQL text, or credential value.
20. `GET /health` and every R3 workspace route remain contract-compatible, and
    the R3 workspace test suite passes unchanged in intent.
21. `backend/rag`, the evaluation modules, and `backend/workspaces` import no
    conversation or orchestration module.
22. `sqlite3` and table DDL appear only in the two repository adapters and the
    schema registry; `APP_DB_PATH` appears only in settings and the two
    dependency construction sites.
23. The six security-policy lifecycle properties are named, no numeric retention
    period is introduced, and no deletion path exists.
24. Tests cover contracts, registry, service, persistence, routes, chat
    compatibility, chat binding, boundaries, and storage rollback, with no model
    provider, embedding model, Chroma data, or network access required.
25. Documentation names the five routes, the optional chat field, `APP_DB_PATH`
    and its deprecated alias, the no-authentication limitation, the deferred
    frontend, and the production-readiness boundary.
26. Final verification includes the full backend suite, `compileall`, boundary
    and containment checks, storage rollback evidence, `git diff --check`, and a
    repository status review including untracked file contents.

## Required ADRs

1. **ADR 0004: Shared Local Application Store and Per-module Schema Registry.**
   Records that one local SQLite file holds all relational product records for
   the prototype, that schema versions are tracked per module in a
   `schema_versions` table rather than in `PRAGMA user_version`, that the pragma
   carries a sentinel so older builds fail closed, and that this narrows but does
   not supersede ADR 0003. ADR 0003 remains `Accepted`: its core decision that
   SQLite is a local adapter rather than a production commitment is unchanged.
2. **ADR 0005: Conversation Orchestration Seam and Optional Chat Conversation
   Binding.** Records that a `backend/orchestration/` module owns coordination
   between conversation persistence and RAG generation, that the chat route
   delegates rather than orchestrating, that `backend/rag` and the evaluation
   harness must never depend on conversation or orchestration modules, that
   `conversation_id` is optional and additive on the chat contract, and that
   assistant and tool turns are writable only through the orchestrator.

If the implementation plan proposes authentication, authorization, a production
database, an ORM, a migration framework, conversation summarization, deletion
semantics, a required chat field, or frontend work, additional ADRs and a
returned design review are required before implementation.

## Approval Record

| Version | Approver role | Date | Authorization boundary |
| --- | --- | --- | --- |
| 0.1 | Repository owner | 2026-09-04 | Approved. Every design decision in this document was confirmed by the repository owner during a structured design interview on 2026-09-04, including the explicit decision to defer all frontend work. This approval authorizes writing ADR 0004 and ADR 0005 and drafting an implementation plan. It does not authorize source edits, which require an approved implementation plan, and it does not authorize any Git delivery action |

