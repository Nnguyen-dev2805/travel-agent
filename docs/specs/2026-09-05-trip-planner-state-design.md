# Trip Planner State Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.2 |
| Date | 2026-09-05 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Runtime milestone R7 - backend-only planner state records, itinerary versions, trip decisions, operation log, local evaluation, and planner API routes |
| Parent design | [Architecture Baseline Design](./2026-08-31-architecture-baseline-design.md), version 0.1; [Roadmap and Learning Design](./2026-08-31-roadmap-and-learning-design.md), version 0.1 |
| Depends on | R3 delivered workspace container; R4 delivered conversation provenance; R2 accepted evaluation harness and D5 result-state vocabulary; R6 delivered feature-gated memory retrieval on `feature/agent-memory` at `d62b41b`; [ADR 0004](../adr/0004-shared-local-application-store-and-per-module-schema-registry.md); [ADR 0005](../adr/0005-conversation-orchestration-seam-and-optional-chat-binding.md); [ADR 0008](../adr/0008-workspace-owned-planner-state-and-operation-log.md) (Accepted) |
| Architecture approval | Approved by repository owner on 2026-09-05 |
| Implementation plan | [Trip Planner State Implementation Plan](../plans/2026-09-05-trip-planner-state-implementation.md), version 0.2 (Approved) |
| Related issue | None - R7 documentation drafting was authorized by the repository owner in conversation on 2026-09-05 |
| Superseded document | None |

## Summary

R7 adds backend-only trip planner state. It stores immutable itinerary versions,
explicit trip decisions, and append-only planner operations in a new
`backend/planner/` module. R7 does not generate itinerary content with an LLM and
does not let chat silently write planner state. The milestone exists to make
planner writes explicit, reversible, inspectable, and measurable before a later
planner agent or UI depends on them.

## Current-state Evidence

Verified current implementation:

1. `backend/workspaces/` owns `TripWorkspace` records and local SQLite storage.
2. `backend/conversations/` owns persisted conversations, messages, and message
   provenance.
3. `backend/memory/` owns R5 shadow memory and R6 feature-gated memory retrieval.
4. `backend/orchestration/` owns chat turn persistence and optional memory
   context composition.
5. `backend/rag/` remains independent from memory and planner state.
6. `backend/storage/schema_registry.py` registers per-module SQLite schema
   versions.

Verified gaps:

1. No `backend/planner/` package exists.
2. No itinerary version, trip decision, or planner operation table exists.
3. Chat can persist messages and retrieve memory, but it cannot save planner
   state.
4. `docs/architecture/data-model.md` lists `ItineraryVersion` and
   `TripDecision` conceptually. `PlannerOperation` is a new R7 entity, currently
   only implied by the evaluation trace field `planner_operation_ids`.

## Context

The product direction needs an assistant that can help a user plan a trip over
multiple turns. R3 gave the product a trip workspace. R4 gave the workspace
conversation provenance. R5 and R6 gave the system measured memory, but memory
is not a plan: a memory record can say "the user prefers vegetarian food"; a
trip decision says "this Da Nang trip uses vegetarian restaurants"; an itinerary
version says "day 2 contains this dinner stop".

The roadmap requires planner writes to be explicit, reversible, and evaluated.
That requires a dedicated planner state module before an agent or UI can safely
modify trip plans.

## Problem Statement

The current app can answer travel questions and remember selected facts behind a
feature gate, but it cannot persist a trip plan. If a later planner agent edited
state without R7, the repository would have no stable contract for:

1. what itinerary snapshot was saved;
2. what user decision justified it;
3. which operation changed it;
4. how to inspect rejected options;
5. how to prove a failed write did not pretend to save a plan.

## Goals

R7 must:

1. Add planner contracts for itinerary versions, itinerary items, trip
   decisions, and planner operations.
2. Store planner records in the shared local SQLite database under
   `('planner_state', 1)`.
3. Keep planner state separate from memory, RAG, and chat orchestration.
4. Provide backend API routes for explicit planner writes and reads.
5. Make itinerary versions immutable and contiguous within one workspace for
   successful creates.
6. Preserve rejected decisions as first-class evidence.
7. Write one planner operation for every successful state-changing planner use
   case.
8. Provide deterministic local evaluation for versioning, decision lifecycle,
   rejected-option preservation, cross-workspace isolation, operation
   traceability, and no implicit chat writes.

## Non-goals

R7 does not add frontend itinerary UI, authentication, production storage, LLM
itinerary generation, tool calling, booking integrations, maps, pricing,
calendars, external APIs, implicit planner writes from chat, deletion workflows,
vector planner storage, or changes to RAG and memory behavior.

## Assumptions

Implementation must stop if any assumption differs:

1. The selected base includes R6 delivered through `d62b41b` or a later
   repository-owner selected base.
2. The local shared database remains `settings.APP_DB_PATH`.
3. `register_module_schema` can register a new additive module named
   `planner_state` at version `1`.
4. Workspace and conversation repository interfaces remain available for scope
   validation.
5. No authentication layer exists, so R7 can only prove workspace-id isolation,
   not authenticated-user isolation.
6. R7 evaluation uses D5 result-state vocabulary but is a milestone-scoped
   planner evaluation harness, not a new canonical D5 planner protocol.
7. Successful itinerary creates allocate contiguous version numbers by using
   `max(version_number) + 1` at persistence time. Failed or rejected requests do
   not allocate itinerary versions.
8. Every generated id follows the existing repository pattern:
   `prefix + uuid.uuid4().hex`.

## Users and System Flows

Primary users are local developers/tests, a future planner agent, and reviewers.

Create itinerary:

```text
API request -> planner route -> PlannerService validates workspace/conversation
-> PlannerRepository assigns next version -> itinerary row + operation row
-> controlled response
```

Accept itinerary:

```text
API request -> planner route -> PlannerService validates workspace and version
-> repository marks prior accepted workspace versions as superseded
-> selected version becomes accepted -> operation row -> controlled response
```

Record or supersede decision:

```text
API request -> planner route -> PlannerService validates workspace/provenance
-> repository creates decision -> optional same-workspace target is superseded
-> operation row -> controlled response
```

Chat isolation:

```text
chat request -> existing conversation orchestrator -> RAG/memory answer path
-> no PlannerService call -> no planner rows
```

## Alternatives Considered

### A. Separate Planner Module and Operation Log

Selected. This creates `backend/planner/` with domain contracts, repository,
service, API routes, and evaluation. It keeps planner state separate from memory
while giving every successful write durable operation evidence.

### B. Store Planner State as Memory Records

Rejected. Trip decisions and itinerary snapshots have different lifecycle,
provenance, and rollback semantics from remembered user preferences. Conflating
them would make deletion, evaluation, and planner correctness harder.

### C. Store Only the Latest Itinerary

Rejected. It is simpler, but it erases rejected options and older snapshots. The
roadmap requires planner writes to be reversible and evaluated.

### D. Full Event-sourced Planner Store

Rejected for R7. Replaying all planner state from events would be powerful but
too much architecture for the local prototype. R7 stores queryable records plus
an append-only operation log.

## Components and Dependency Direction

```text
backend/app/api/planner.py
↓
backend/planner/service.py
↓
backend/planner/repository.py
↓
backend/planner/sqlite_repository.py
```

Allowed dependencies:

1. `backend/app/api/planner.py` may import planner service, planner SQLite
   repository, workspace SQLite repository, conversation SQLite repository, and
   API schemas.
2. `backend/planner/service.py` may depend on planner, workspace, and
   conversation repository protocols.
3. `backend/planner/sqlite_repository.py` may depend on `sqlite3`,
   `backend.storage.schema_registry`, and planner models.
4. `backend/planner/evaluation/*` may construct planner services over temporary
   SQLite databases and write local report artifacts.

Forbidden dependencies:

1. `backend/planner` must not import `backend.rag`, `backend.memory`, or
   `backend.orchestration`.
2. `backend.rag`, `backend.memory`, and `backend.orchestration` must not import
   `backend.planner` in R7.
3. Chat routes and chat orchestration must not create, modify, or read planner
   state in R7.

## Data Flow and Lifecycle

### Itinerary Lifecycle

| Current | Allowed next | Rule |
| --- | --- | --- |
| New row | `draft`, `proposed` | Only at creation |
| `draft` | `accepted`, `archived` | Direct accept is allowed for local R7 |
| `proposed` | `accepted`, `archived` | Proposed is set at creation in R7; no separate propose route |
| `accepted` | `superseded` | Only when another version in the same workspace is accepted |
| `superseded` | `archived` | Optional cleanup state, never re-accepted |
| `archived` | None | Terminal in R7 |

Accepting a version supersedes prior accepted versions in the same workspace
only. Older itinerary rows remain immutable.

### Decision Lifecycle

| Current | Allowed next | Rule |
| --- | --- | --- |
| New row | `pending`, `accepted`, `rejected` | Only at creation |
| `pending` | `accepted`, `rejected`, `changed` | Local reviewer/user decision |
| `accepted` | `changed` | Marks the accepted decision as changed, not deleted |
| `rejected` | `changed` | Preserves the rejected option while noting it changed |
| `changed` | None | Terminal in R7 |
| `superseded` | None | Terminal in R7 |

`update_decision_status` cannot set `superseded` directly. Supersession happens
only when `record_decision` creates a replacement that cites
`supersedes_decision_id`.

### Operation Lifecycle

Planner operations are append-only. R7 writes operations for successful
state-changing service calls. Validation failures that return `422`, missing
records that return `404`, and conflicts that return `409` do not write
operation rows.

## Storage

R7 uses `APP_DB_PATH` and registers:

```text
('planner_state', 1)
```

Tables:

| Table | Owner | Purpose |
| --- | --- | --- |
| `planner_itinerary_versions` | `backend/planner` | Immutable itinerary snapshots |
| `planner_trip_decisions` | `backend/planner` | Explicit decisions and rejected options |
| `planner_operations` | `backend/planner` | Append-only write provenance |

The adapter must fail closed if `planner_state` exists at an incompatible
version. It must not modify schema module versions for workspaces,
conversations, memory, or memory records.

## Domain Contracts

### Identifiers

| Contract | Prefix | Generator |
| --- | --- | --- |
| `itinerary_version_id` | `itv_` | `itv_` + `uuid.uuid4().hex` |
| `decision_id` | `td_` | `td_` + `uuid.uuid4().hex` |
| `operation_id` | `po_` | `po_` + `uuid.uuid4().hex` |

### ItineraryVersion

| Field | Type | Rule |
| --- | --- | --- |
| `itinerary_version_id` | `str` | Required, prefix `itv_` |
| `workspace_id` | `str` | Required parent workspace id |
| `version_number` | `int` | Positive, contiguous among successful creates within workspace |
| `status` | `ItineraryStatus` | `draft`, `proposed`, `accepted`, `superseded`, or `archived` |
| `title` | `str | None` | Optional, stripped, max 120 characters |
| `summary` | `str | None` | Optional, stripped, max 1000 characters |
| `items` | `tuple[ItineraryItem, ...]` | Structured snapshot content; may be empty for an initial draft |
| `created_from_operation_id` | `str | None` | Optional `po_` id |
| `created_from_message_id` | `str | None` | Optional provenance message id |
| `created_at` | `datetime` | Required UTC timestamp |

### ItineraryItem

| Field | Type | Rule |
| --- | --- | --- |
| `day_index` | `int` | Positive day number |
| `position` | `int` | Positive ordering within the day |
| `item_type` | `ItineraryItemType` | `activity`, `lodging`, `transport`, `meal`, `free_time`, or `note` |
| `title` | `str` | Required, stripped, max 120 characters |
| `location` | `str | None` | Optional, stripped, max 160 characters |
| `start_time` | `str | None` | Optional local `HH:MM` string |
| `end_time` | `str | None` | Optional local `HH:MM` string |
| `notes` | `str | None` | Optional, stripped, max 500 characters |
| `source_decision_ids` | `tuple[str, ...]` | Optional `td_` ids referenced by this item |

### TripDecision

| Field | Type | Rule |
| --- | --- | --- |
| `decision_id` | `str` | Required, prefix `td_` |
| `workspace_id` | `str` | Required parent workspace id |
| `decision_type` | `DecisionType` | `preference`, `constraint`, `booking`, `rejection`, `tradeoff`, or `open_question` |
| `status` | `DecisionStatus` | `pending`, `accepted`, `rejected`, `changed`, or `superseded` |
| `statement` | `str` | Required, stripped, max 500 characters |
| `rationale` | `str | None` | Optional, stripped, max 1000 characters |
| `source_message_id` | `str | None` | Optional provenance message id |
| `supersedes_decision_id` | `str | None` | Optional earlier decision id |
| `created_at` | `datetime` | Required UTC timestamp |
| `updated_at` | `datetime` | Required UTC timestamp, not earlier than `created_at` |

Rejected options remain durable decision evidence.

### PlannerOperation

`PlannerOperation` is a new R7 entity.

| Field | Type | Rule |
| --- | --- | --- |
| `operation_id` | `str` | Required, prefix `po_` |
| `workspace_id` | `str` | Required parent workspace id |
| `conversation_id` | `str | None` | Optional conversation provenance |
| `operation_type` | `PlannerOperationType` | `create_itinerary`, `accept_itinerary`, `archive_itinerary`, `record_decision`, `update_decision_status`, or `supersede_decision` |
| `status` | `PlannerOperationStatus` | `applied` |
| `input_summary` | `str | None` | Optional controlled summary, max 1000 characters |
| `result_itinerary_version_id` | `str | None` | Optional `itv_` id |
| `result_decision_id` | `str | None` | Optional `td_` id |
| `source_message_id` | `str | None` | Optional provenance message id |
| `created_at` | `datetime` | Required UTC timestamp |

## Service Use Cases

`PlannerService` must expose:

1. `create_itinerary_version(workspace_id, draft, conversation_id=None, source_message_id=None) -> ItineraryVersion`
2. `get_itinerary_version(workspace_id, itinerary_version_id) -> ItineraryVersion`
3. `list_itinerary_versions(workspace_id, status=None) -> tuple[ItineraryVersion, ...]`
4. `accept_itinerary_version(workspace_id, itinerary_version_id) -> ItineraryVersion`
5. `archive_itinerary_version(workspace_id, itinerary_version_id) -> ItineraryVersion`
6. `record_decision(workspace_id, draft, conversation_id=None, source_message_id=None) -> TripDecision`
7. `update_decision_status(workspace_id, decision_id, status) -> TripDecision`
8. `list_decisions(workspace_id, status=None, decision_type=None) -> tuple[TripDecision, ...]`
9. `list_operations(workspace_id) -> tuple[PlannerOperation, ...]`

## API Contract

| Method | Path | Behavior |
| --- | --- | --- |
| `POST` | `/workspaces/{workspace_id}/planner/itineraries` | Create a draft or proposed itinerary version |
| `GET` | `/workspaces/{workspace_id}/planner/itineraries` | List versions newest first |
| `GET` | `/workspaces/{workspace_id}/planner/itineraries/{itinerary_version_id}` | Fetch one version scoped to the workspace |
| `POST` | `/workspaces/{workspace_id}/planner/itineraries/{itinerary_version_id}/accept` | Mark one version accepted and supersede prior accepted versions |
| `POST` | `/workspaces/{workspace_id}/planner/itineraries/{itinerary_version_id}/archive` | Archive one version |
| `POST` | `/workspaces/{workspace_id}/planner/decisions` | Record a trip decision; when `supersedes_decision_id` is present, supersede that same-workspace decision |
| `GET` | `/workspaces/{workspace_id}/planner/decisions` | List decisions newest first |
| `PATCH` | `/workspaces/{workspace_id}/planner/decisions/{decision_id}` | Update a decision status using the lifecycle table |
| `GET` | `/workspaces/{workspace_id}/planner/operations` | List operation rows newest first |

## Errors and Edge Cases

1. Blank or invalid identifiers return `422`.
2. Missing workspace returns `404`.
3. Workspace mismatch for itinerary or decision ids returns `404`.
4. Invalid lifecycle transition returns `409`.
5. Directly setting decision status `superseded` through PATCH returns `409`.
6. Superseding a decision from another workspace returns `404`.
7. Storage initialization or SQLite write failure returns a controlled `500`.
8. Request models reject unknown fields with `422`.

## Observability and Operations

Planner logs may include route/action, workspace id, conversation id, itinerary
id, decision id, operation id, counts, status, and failure class. Logs must not
include full itinerary text, decision statements, raw chat messages, prompts,
provider responses, or secrets.

## Evaluation

R7 uses D5 result states but defines a milestone-scoped planner evaluation
harness. It does not create a canonical D5 planner protocol file.

Fixtures and reports:

```text
docs/evaluation/fixtures/planner/r7-state-v0.1/manifest.json
docs/evaluation/fixtures/planner/r7-state-v0.1/examples.jsonl
docs/reports/planner/r7-state-v0.1.json
docs/reports/planner/r7-state-v0.1.md
```

Required slices: `itinerary_versioning`, `decision_lifecycle`,
`rejected_option_preservation`, `cross_workspace_isolation`, and
`operation_traceability`.

Minimum gates:

| Gate | Expectation |
| --- | --- |
| Version continuity | `PASS` only when successful itinerary creates increment by exactly one within each evaluated workspace |
| Single accepted itinerary | `PASS` only when accepting a version supersedes prior accepted versions in that workspace |
| Rejected option preservation | `PASS` only when rejected decisions remain listable |
| Cross-workspace isolation | `PASS` only when ids from another workspace cannot be fetched or mutated through the current workspace route |
| Operation traceability | `PASS` only when every successful evaluated write creates an operation row |
| No implicit chat writes | `PASS` only when bound chat turns do not create planner rows |

Result states: `PASS`, `FAIL`, `INCONCLUSIVE`, and `INVALID`.

## Failure and Recovery

1. Unresolved workspace or conversation provenance fails before planner writes.
2. Multi-row planner writes use SQLite transactions.
3. Incompatible schema versions fail closed.
4. Malformed evaluation fixtures produce `INVALID`.
5. Failed planner gates produce `FAIL`.
6. A blocked full backend run must be disclosed with focused R7 verification.

## Capacity, Latency, and Cost

R7 is local development only. Expected scale is dozens of itinerary versions and
decisions per workspace. No network, model provider, embedding, Chroma, or
external API cost is introduced. Planner service calls should remain single
local SQLite transactions.

## Compatibility and Staged Migration

R7 is additive. It adds `backend/planner/`, registers `planner_state` schema
version `1`, mounts planner routes, adds evaluation fixtures/reports, and
updates current-state docs. R7 must coexist with R3-R6 without changing their
public route contracts or schema module versions.

## Required ADRs

1. [ADR 0008](../adr/0008-workspace-owned-planner-state-and-operation-log.md)
   must be accepted before implementation.

## Testing Requirements

R7 implementation must add focused tests for domain validation, schema
registration, itinerary create/get/list/accept/archive, decision create/list and
status transitions, replacement supersession, operation rows, API success/error
shapes, chat isolation, import boundaries, and planner evaluation reports. Tests
must use temporary SQLite database paths, never developer `APP_DB_PATH`.

## Security and Privacy

R7 planner records are user content. Requirements:

1. No raw full message content in logs.
2. Log only route/action, ids, counts, status, and failure class.
3. No secrets, tokens, provider responses, or hidden prompts in planner rows.
4. No public exposure claim until R9 security work.
5. No deletion semantics beyond lifecycle states named in the contracts.
6. No cross-workspace existence leaks in route errors.

## Rollout and Migration

Rollout sequence:

1. Accept ADR 0008.
2. Approve this spec.
3. Approve the R7 implementation plan.
4. Implement in an isolated worktree.
5. Run R7 evaluation and backend verification.
6. Return READY_FOR_OWNER for review.
7. Mark R7 `Accepted in working tree` only after owner review acceptance.
8. Mark R7 `Delivered` only after Git delivery occurs.

No existing local database migration is required beyond additive table creation.

## Rollback

Rollback removes planner routes, schemas, service, repository, evaluation
commands, fixtures, reports, and documentation references. Existing local
planner rows can remain inert in the shared SQLite file; R7 does not define
production migration or deletion.

## Acceptance Criteria

R7 can be accepted when ADR 0008 is accepted, this spec and its implementation
plan are approved, implementation creates the planned planner contracts/storage
service/API/evaluation/docs, R7 tests and verification pass, import-boundary
checks are clean, the R7 report is internally consistent, and there are no
implicit chat planner writes.

## Approval Record

| Version | Decision owner | Date | Notes |
| --- | --- | --- | --- |
| 0.1 | Repository owner | 2026-09-05 | Drafted for R7 review. External review found missing Level 3 sections, lifecycle ambiguity, incorrect id-generation guidance, and plan-template gaps |
| 0.2 | Repository owner | 2026-09-05 | Approved after review fixes. Adds required Level 3 sections, explicit lifecycle tables, D5 evaluation relationship, `uuid.uuid4().hex` id generation, R2 dependency wording, planner operation entity status, and precise rollout/rollback gates. Approval authorizes accepting ADR 0008 and approving the implementation plan. It does not authorize Git delivery, frontend work, authentication, default planner automation, external booking integrations, or production deployment |
