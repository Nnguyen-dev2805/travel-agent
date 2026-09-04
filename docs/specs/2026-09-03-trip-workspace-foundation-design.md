# Trip Workspace Foundation Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-03 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Runtime milestone R3 - trip workspace contracts, local storage boundary, and minimal backend routes for creating and inspecting workspace records |
| Parent design | [Architecture Baseline Design](./2026-08-31-architecture-baseline-design.md), version 0.1; [Roadmap and Learning Design](./2026-08-31-roadmap-and-learning-design.md), version 0.1 |
| Depends on | R1/R2 accepted change set; [Target-state Architecture](../architecture/target-state.md); [Data Model](../architecture/data-model.md); [Security Policy](../../SECURITY.md) |
| Architecture approval | Repository owner approved R3 spec version 0.1 in conversation on 2026-09-03 |
| Implementation plan | [Trip Workspace Foundation Implementation Plan](../plans/2026-09-03-trip-workspace-foundation-implementation.md), version 0.1 (Approved) |
| Related issue | None - R3 specification drafting was authorized by the repository owner in conversation on 2026-09-03 |
| Superseded document | None |

## Summary

R3 introduces the first runtime trip workspace foundation for Travel Agent.
A trip workspace becomes the local product container for one planned trip, with
a stable identifier, owner scope label, title, destination scope, optional date
window, planning status, retention state, and timestamps.

The selected design adds backend workspace contracts and minimal routes for
creating, retrieving, and listing workspace records. It also introduces a local
SQLite-backed repository behind a small workspace repository interface so later
milestones can add conversations, memory, planner state, and evaluation traces
without embedding storage details in route handlers.

R3 does not implement authentication, authorization, collaboration, conversation
persistence, memory, itinerary planning, planner operations, or production
deployment. Because the current system has no authenticated user identity, the
R3 `owner_user_id` is a local development scope label supplied by the caller. It
is not an authorization control and must not be described as tenant isolation.

Approval of version 0.1 authorizes preparing the required ADRs and, after those
ADRs are accepted, preparing an implementation plan. It does not authorize
source edits, database creation, migrations, route changes, frontend changes,
Git delivery, or production-readiness claims.

## Current-state Evidence

Current-state claims are based on repository documents and CodeGraph/source
inspection performed on 2026-09-03. The repository has a `.codegraph/` index,
and CodeGraph was used to inspect the current FastAPI, chat schema, RAG service,
evaluation runtime, and storage-adapter-adjacent code. Markdown documents were
read directly because they are repository governance and architecture evidence.

| Evidence | Current fact relevant to R3 |
| --- | --- |
| [Current-state Architecture](../architecture/current-state.md) | There is no implemented trip workspace, user identity, conversation persistence, planner state, memory store, or evaluation trace store. |
| [Target-state Architecture](../architecture/target-state.md) | The target architecture treats `TripWorkspace` as the primary product container and recommends adding workspace contracts and storage behind interfaces before conversation persistence and memory. |
| [Data Model](../architecture/data-model.md) | The conceptual `TripWorkspace` has `workspace_id`, `owner_user_id`, `title`, `destination_scope`, `date_window`, `planning_status`, `created_at`, `updated_at`, and `retention_state`. |
| [Master Roadmap](../roadmap/master-roadmap.md) | R3 is blocked by `D3`, required ADRs, and `R0`; its deliverables are workspace contracts, storage boundary, and minimal routes. |
| [`backend/app/main.py`](../../backend/app/main.py) | FastAPI currently mounts `/health` and chat routes under `/api/v1`. |
| [`backend/app/api/chat.py`](../../backend/app/api/chat.py) | The chat route accepts one stripped message, logs a message prefix, calls process-global RAG, and returns `reply`, `model`, and `citations`. |
| [`backend/app/schemas/chat.py`](../../backend/app/schemas/chat.py) | The current chat request contains only `message`; it has no user, workspace, conversation, memory, planner, or trace identifier. |
| [Security Policy](../../SECURITY.md) | The bounded backend has no implemented authentication or authorization; user content and future workspace data require minimization and no production claims. |
| [RAG Repair and Evaluation Harness Design](./2026-09-01-rag-repair-and-evaluation-harness-design.md) | R1/R2 must preserve the current chat response contract while introducing evidence contracts; R3 should build on the accepted R1/R2 state rather than racing it. |

The current bounded online path has no workspace lookup and no workspace storage
decision. R3 therefore needs an architecture decision before runtime code can
persist workspace records.

## Context

Travel Agent currently answers one chat message at a time. That is useful for a
RAG prototype, but it is not enough for a travel-planning product because there
is no stable product container for a planned trip.

Future conversation persistence, memory extraction, memory retrieval, itinerary
versions, and planner decisions all need a scope. Without a workspace
foundation, those later records would either become global user facts too early
or get attached directly to chat messages without a durable trip context.

R3 is the first runtime step that moves the product from stateless chat toward a
workspace-first assistant. The step must be deliberately small: create and
inspect workspace records, define storage ownership, and preserve current chat
compatibility. It should not smuggle in memory or planner behavior.

## Users

1. **Traveler:** needs a recognizable container for one planned trip, such as a
   Vietnam family vacation or a weekend in Da Nang.
2. **Repository owner:** needs a reviewable first runtime step after R1/R2 that
   does not blur workspace, memory, planner, and production security concerns.
3. **Backend engineer:** needs a small interface for workspace persistence that
   can be tested without starting the full RAG stack.
4. **Future memory engineer:** needs a trip-scoped owner for memory candidates
   and retrieval, without using global user memory as the default.
5. **Future planner engineer:** needs a workspace identity that itinerary
   versions and decisions can attach to in R7.
6. **Reviewer:** needs tests and schema evidence proving workspace records can
   be created and inspected without changing chat semantics.

## Problem Statement

The current application has no place to attach trip state. The only public chat
request field is `message`, and the only durable local store currently
documented for runtime behavior is Chroma travel knowledge. There is no
relational store, workspace table, conversation table, user store, or planner
state store.

That absence blocks the next product milestones. Conversation persistence needs
a workspace parent. Memory needs user and trip scopes before any memory can be
evaluated safely. Planner decisions need a workspace owner so saved itinerary
state is explicit and reversible.

The first workspace implementation must also avoid overclaiming. A local
`owner_user_id` string can label scope for development and tests, but it cannot
stand in for authentication or authorization. A local SQLite file can provide a
small durable development store, but it is not a production storage
architecture.

## Goals

1. Define `TripWorkspace` as the first implemented product container for one
   planned trip.
2. Add a backend workspace module with a small service interface and repository
   interface.
3. Implement a local SQLite workspace repository using only the Python standard
   library.
4. Add minimal workspace routes under `/api/v1/workspaces` for create, get, and
   list-by-owner inspection.
5. Preserve the existing `/health` and `/api/v1/chat` behavior and response
   contracts.
6. Treat `owner_user_id` as a local development scope label, not as an
   authentication or authorization guarantee.
7. Define workspace lifecycle fields and validation rules without implementing
   deletion, memory, conversation persistence, planner state, or collaboration.
8. Keep route handlers thin by putting normalization, validation, IDs, time, and
   storage access behind a workspace module.
9. Provide deterministic unit and integration tests that require no model
   provider, embedding model, Chroma data, or network access.
10. Update canonical documentation so R3 behavior is discoverable and maturity
    language remains honest.

## Non-goals

1. R3 does not implement user authentication, authorization, sessions, OAuth,
   tenant isolation, or collaboration membership.
2. R3 does not make `/api/v1/chat` require or accept a `workspace_id`.
3. R3 does not persist conversations, messages, memory records, memory
   candidates, itinerary versions, trip decisions, planner operations, or
   evaluation traces.
4. R3 does not implement workspace update, archive, deletion, tombstoning,
   sharing, import, export, search, or pagination.
5. R3 does not select a production database, ORM, migration framework, secret
   manager, deployment topology, or observability vendor.
6. R3 does not modify RAG retrieval, generation, evaluation metrics, Chroma
   collections, embedding models, model-provider settings, or benchmark
   artifacts.
7. R3 does not claim production readiness, privacy compliance, or public API
   safety.
8. R3 does not stage, commit, push, open a pull request, merge, tag, release, or
   rewrite Git history.

## Assumptions

1. R1/R2 has been accepted before R3 implementation starts, so workspace work
   can build on the finalized RAG runtime and evaluation foundation.
2. A Python standard-library SQLite adapter is sufficient for local development
   and deterministic tests in R3.
3. The first workspace routes can remain backend-only; frontend workspace UI can
   be designed in a later milestone.
4. Caller-supplied `owner_user_id` is acceptable as a development scope label
   because R3 makes no authorization claim.
5. Workspace records can use generated opaque IDs rather than user-provided IDs.
6. R3 can create its SQLite schema on startup or first repository use without a
   separate migration tool because production migration is out of scope.
7. If implementation discovers that authentication, production storage,
   conversation persistence, or chat request changes are required, work stops
   and returns to design.

## Selected Approach

Use a **backend-only local SQLite workspace foundation**.

R3 introduces a `backend/workspaces/` module that owns workspace value contracts,
service behavior, repository interface, and a SQLite repository adapter. The
FastAPI layer receives and returns Pydantic schemas, while the workspace service
owns business validation and persistence calls.

The local SQLite database path is configured by a new setting,
`WORKSPACE_DB_PATH`, defaulting to `data/workspaces/travel_agent_workspaces.sqlite3`.
The directory and schema may be created by the SQLite adapter on first use.
Tests must use temporary database paths or in-memory repositories so they do not
touch the developer's local workspace data.

Minimal routes:

1. `POST /api/v1/workspaces` creates a workspace.
2. `GET /api/v1/workspaces/{workspace_id}` retrieves one workspace by ID.
3. `GET /api/v1/workspaces?owner_user_id=<value>` lists workspaces for one
   local development owner label.

This gives later milestones a stable workspace identity without changing the
current chat contract.

## Alternatives Considered

### Alternative A: In-memory workspace repository only

This would be the smallest implementation and would avoid local file state. It
is useful as a test adapter but insufficient as the selected runtime path
because workspace records would disappear on process restart. That would make
the first product container too weak for R4 conversation persistence planning.
Rejected as the default runtime approach.

### Alternative B: Local JSON file store

A JSON file would be easy to inspect and avoids introducing a database file.
However, even simple list/get/create behavior quickly needs atomic writes,
duplicate handling, schema versioning, and corruption handling. Those concerns
would spread file-format details into the repository implementation and tests.
Rejected in favor of SQLite's transactional behavior.

### Alternative C: Local SQLite repository behind an interface

SQLite is available through the Python standard library, supports transactional
writes, is easy to test with temporary files, and is enough for a local
development milestone. Keeping it behind a repository interface avoids coupling
route handlers and future modules to a physical store. Selected.

### Alternative D: Production database or ORM now

Choosing PostgreSQL, an ORM, hosted storage, or a migration framework now would
expand R3 into production storage architecture before authentication,
authorization, deployment topology, and lifecycle requirements are approved.
Rejected as premature.

## User and System Flows

### Flow 1: Create a workspace

1. Caller sends `POST /api/v1/workspaces` with `owner_user_id`, `title`, and
   optional `destination_scope`, `date_window`, and `planning_status`.
2. FastAPI validates JSON shape with the request schema.
3. Workspace service trims strings, applies defaults, validates status and date
   order, generates a workspace ID, and sets timestamps.
4. Repository persists the workspace through the configured adapter.
5. API returns `201 Created` with the created workspace record.

### Flow 2: Inspect one workspace

1. Caller sends `GET /api/v1/workspaces/{workspace_id}`.
2. Workspace service loads by ID.
3. Missing workspace returns `404`.
4. Found workspace returns the public workspace response.

### Flow 3: List workspaces for a development owner label

1. Caller sends `GET /api/v1/workspaces?owner_user_id=<value>`.
2. API rejects a missing or blank `owner_user_id`.
3. Workspace service lists active, archived, and deletion-requested records for
   that owner label, ordered by newest update first.
4. API returns an array of workspace responses.

### Flow 4: Existing chat remains unchanged

1. Browser or caller sends the current `POST /api/v1/chat` request containing
   only `message`.
2. Chat route continues to call RAG exactly as governed by R1/R2.
3. Chat response remains `reply`, `model`, and `citations`.
4. No workspace lookup is performed by the chat route in R3.

## Components and Dependency Direction

| Module | Responsibility | Allowed dependencies |
| --- | --- | --- |
| Workspace contracts | Define workspace value objects, status enums, and repository errors | Standard library only |
| Workspace repository interface | Define the storage interface used by workspace service and tests | Workspace contracts |
| SQLite workspace repository adapter | Persist workspace records in local SQLite and map rows to workspace contracts | Workspace contracts, repository interface, `sqlite3`, `pathlib` |
| Workspace service | Own create/get/list validation, ID generation, timestamping, and repository calls | Workspace contracts and repository interface |
| Workspace API schemas | Define public request/response JSON shapes | Pydantic and workspace contracts |
| Workspace API routes | Map HTTP requests/errors to workspace service calls and responses | FastAPI, schemas, workspace service |
| Application wiring | Include the workspace router under `settings.API_V1_STR` | FastAPI app and workspace router |

Required dependency direction:

```text
FastAPI routes -> WorkspaceService -> WorkspaceRepository interface
                                      -> SQLite adapter

RAG/chat runtime -> no dependency on workspace modules in R3
Evaluation harness -> no dependency on workspace modules in R3
```

R3 must not make online RAG depend on workspace storage. Future milestones may
introduce a conversation orchestrator that depends on workspace and RAG
interfaces after a separate approved design.

## Behavioral and Data Contracts

### Workspace record

The public workspace response contains:

| Field | Requirement |
| --- | --- |
| `workspace_id` | Server-generated opaque string beginning with `tw_` |
| `owner_user_id` | Non-empty caller-provided local development scope label |
| `title` | Non-empty trimmed string, maximum 120 characters |
| `destination_scope` | Optional trimmed string, maximum 160 characters |
| `date_window` | Optional object with `start_date` and `end_date` ISO `YYYY-MM-DD` strings; if both exist, `end_date >= start_date` |
| `planning_status` | One of `idea`, `planning`, `booked`, `active`, `completed`, `cancelled`, `archived` |
| `retention_state` | One of `active`, `archived`, `deletion_requested`, `deleted`; R3 creates records as `active` only |
| `created_at` | UTC ISO timestamp generated by the server |
| `updated_at` | UTC ISO timestamp generated by the server |

### Create request

`POST /api/v1/workspaces` accepts:

```json
{
  "owner_user_id": "local-user",
  "title": "Da Nang family trip",
  "destination_scope": "Da Nang and Hoi An",
  "date_window": {
    "start_date": "2026-12-20",
    "end_date": "2026-12-25"
  },
  "planning_status": "idea"
}
```

Required fields are `owner_user_id` and `title`. If `planning_status` is absent,
it defaults to `idea`. If `date_window` is absent, both date fields are absent.

### Get response

`GET /api/v1/workspaces/{workspace_id}` returns a single workspace record or
`404` when no record exists.

### List response

`GET /api/v1/workspaces?owner_user_id=local-user` returns:

```json
{
  "workspaces": [
    {
      "workspace_id": "tw_example",
      "owner_user_id": "local-user",
      "title": "Da Nang family trip",
      "destination_scope": "Da Nang and Hoi An",
      "date_window": {
        "start_date": "2026-12-20",
        "end_date": "2026-12-25"
      },
      "planning_status": "idea",
      "retention_state": "active",
      "created_at": "2026-09-03T00:00:00Z",
      "updated_at": "2026-09-03T00:00:00Z"
    }
  ]
}
```

List ordering is descending by `updated_at`, then descending by `created_at`,
then `workspace_id` for deterministic ties.

### Repository interface

The workspace service depends on this conceptual interface:

```python
class WorkspaceRepository(Protocol):
    def create(self, workspace: TripWorkspace) -> TripWorkspace: ...
    def get(self, workspace_id: str) -> TripWorkspace | None: ...
    def list_by_owner(self, owner_user_id: str) -> tuple[TripWorkspace, ...]: ...
```

R3 does not expose repository internals to API callers.

## Errors and Edge Cases

1. Blank `owner_user_id` returns HTTP `422` or a controlled validation error
   before storage write.
2. Blank `title` returns HTTP `422` or a controlled validation error before
   storage write.
3. `title` longer than 120 characters returns HTTP `422`.
4. `destination_scope` longer than 160 characters returns HTTP `422`.
5. Unknown `planning_status` returns HTTP `422`.
6. `end_date` earlier than `start_date` returns HTTP `422`.
7. Missing workspace ID on get returns HTTP `404`.
8. SQLite open, schema, or write failure returns HTTP `500` with a controlled
   message that does not expose local filesystem secrets or full SQL text.
9. Duplicate generated workspace ID is retried once by the service; a second
   collision returns a controlled infrastructure error.
10. Existing chat errors and behavior remain governed by the current chat route
    and R1/R2.

## Security and Privacy

Workspace records may contain user content such as trip title, destination,
date window, budget-like wording inside title, or other travel context. R3 must
treat workspace fields as user content for logging and evidence purposes.

R3 rules:

1. Do not log full workspace titles, destination scopes, or date windows by
   default.
2. Prefer workspace IDs, owner scope labels, counts, route names, and failure
   classes in logs and test evidence.
3. Do not store secrets or credentials in workspace fields, fixtures, logs, or
   documentation examples.
4. State clearly that `owner_user_id` is a local development scope label, not an
   authorization mechanism.
5. Do not claim cross-user or cross-workspace isolation beyond deterministic
   repository filtering by `owner_user_id`.
6. Do not expose the current unauthenticated workspace routes publicly.
7. Do not implement deletion semantics beyond recording the `retention_state`
   vocabulary; deletion/tombstoning requires later approved lifecycle work.

## Observability and Operations

R3 adds local operational evidence for workspace routes without introducing a
hosted observability system.

Expected log events:

1. workspace created: record route/action, workspace ID, owner scope label, and
   planning status;
2. workspace retrieved: record route/action and workspace ID;
3. workspace list requested: record route/action, owner scope label, and count;
4. workspace storage failure: record failure class and route/action without
   secret values or full user content.

The development guide must document `WORKSPACE_DB_PATH`, the default local file
path, and the fact that the SQLite file is local development state. R3 must not
change Stage A health semantics to imply workspace readiness unless an explicit
readiness route is separately approved.

## Testing and Evaluation

R3 requires deterministic tests with no network, model provider, Chroma,
embedding model, or Docker dependency.

Required tests:

1. Workspace model tests for enum values, date-window validation, trimming, and
   server-generated IDs.
2. Service tests for create/get/list behavior using an in-memory fake
   repository or temporary SQLite database.
3. SQLite repository tests using a temporary file path, proving schema creation,
   create, get, list ordering, and persistence across repository instances.
4. API integration tests proving `POST /api/v1/workspaces`,
   `GET /api/v1/workspaces/{workspace_id}`, and
   `GET /api/v1/workspaces?owner_user_id=...` behavior.
5. API compatibility tests proving `/api/v1/chat` still accepts only `message`
   and returns only `reply`, `model`, and `citations`.
6. Import-boundary check proving `backend/rag` does not import workspace
   modules in R3.
7. Compile and backend test commands from the implementation plan.

R3 does not require RAG benchmark execution. R1/R2 acceptance remains the
prerequisite evidence that the RAG foundation is ready to build around.

## Data Flow and Lifecycle

Creation:

1. API receives workspace create request.
2. Workspace service validates and normalizes fields.
3. Service generates `workspace_id`, `created_at`, and `updated_at`.
4. SQLite adapter inserts the record into a local table.
5. API returns the created record.

Read:

1. API receives workspace ID or owner scope label.
2. Service queries the repository.
3. API returns one record, a list, or `404`.

Lifecycle:

1. R3 creates records only in `planning_status = "idea"` unless the caller
   provides another allowed planning status.
2. R3 creates records only in `retention_state = "active"`.
3. R3 does not update, archive, delete, tombstone, or hard-delete records.
4. Later lifecycle behavior requires a separate approved spec because it affects
   privacy, retention, and recovery semantics.

SQLite schema versioning:

1. The adapter records a schema version using `PRAGMA user_version = 1` or a
   dedicated metadata table.
2. On first use, the adapter creates the R3 table when absent.
3. If an existing schema has an incompatible version, the adapter fails closed
   with a controlled error rather than silently migrating.

## Failure and Recovery

| Failure | R3 behavior |
| --- | --- |
| Workspace validation fails | Return a controlled client validation error and write no record |
| Workspace ID not found | Return `404` |
| SQLite file path directory is absent | Adapter creates the directory under the configured path |
| SQLite schema is absent | Adapter initializes schema version 1 |
| SQLite schema is incompatible | Fail closed with a controlled storage error |
| SQLite write fails | Return controlled `500`; do not claim the workspace was saved |
| Workspace list has no records | Return an empty `workspaces` array |
| RAG or model provider fails | Unchanged from R1/R2; workspace routes do not depend on RAG |

Recovery follows [Local Development Recovery](../runbooks/local-development.md)
for local environment issues. Destructive deletion of workspace database files
is not a default recovery step and requires an explicit owner decision naming
the target and recoverability.

## Capacity, Latency, and Cost

R3 is local development infrastructure. It does not define production SLOs or
capacity guarantees.

Minimum R3 measurement expectations:

1. Unit and integration tests use small temporary stores and complete without
   external services.
2. Route handlers do not instantiate RAG, embedding, Chroma, or model clients.
3. Workspace create/get/list operations should be simple SQLite operations with
   no intentional network calls.
4. Documentation must avoid claiming production scalability or durability.

Later production planning must define database capacity, backup, restore,
retention, concurrency, and migration budgets before public deployment.

## Compatibility and Staged Migration

R3 must preserve these compatibility facts:

1. `GET /health` remains the Stage A health route.
2. `POST /api/v1/chat` remains available.
3. The chat request remains `message` only.
4. The chat response remains `reply`, `model`, and `citations`.
5. RAG evaluation, Chroma collections, and model-provider configuration remain
   governed by R1/R2.
6. Offline indexing remains opt-in and state-changing.

R3 adds workspace routes beside the chat route rather than changing chat. Future
R4 may attach conversations to workspace IDs. Future R5/R6 may attach memory
candidates and selected memories to workspace IDs. Future R7 may attach
itinerary versions and trip decisions to workspace IDs.

## Rollout and Migration

R3 rollout sequence:

1. Accept this R3 specification.
2. Accept required ADRs for trip workspace container and local workspace storage
   ownership.
3. Approve an implementation plan with exact files, tests, docs, and rollback.
4. Implement workspace module contracts and tests.
5. Implement SQLite repository adapter and tests.
6. Implement FastAPI schemas/routes and route tests.
7. Update development and architecture documentation.
8. Run final verification and owner change-set review.

There is no migration from existing workspace data because no workspace store is
currently implemented. If local prototype database files already exist outside
this design, they are out of scope unless the owner explicitly includes them.

## Rollback

Before owner acceptance, rollback removes the R3 workspace module, workspace
routes, config setting, tests, and documentation edits through normal reviewed
Git history. It must not delete unrelated local data, Chroma state, or R1/R2
evaluation artifacts.

If a local SQLite file was created during R3 testing, it is local development
state. Deleting a material workspace database requires an explicit owner
decision naming the exact path and confirming recoverability.

After owner acceptance, future changes that replace SQLite, add migrations,
change workspace route contracts, or introduce deletion semantics require a new
approved spec and plan.

## Acceptance Criteria

1. R3 spec version 0.1 is approved by the repository owner.
2. Required R3 ADRs are accepted before implementation planning.
3. Implementation plan version 0.1 is approved before source edits begin.
4. Workspace module exposes stable `TripWorkspace` contracts and a repository
   interface with create/get/list behavior.
5. Local SQLite adapter stores workspace records at the configured
   `WORKSPACE_DB_PATH` and initializes schema version 1 safely.
6. `POST /api/v1/workspaces` returns `201` with a server-generated
   `workspace_id` and normalized workspace fields.
7. `GET /api/v1/workspaces/{workspace_id}` returns the matching workspace or
   `404`.
8. `GET /api/v1/workspaces?owner_user_id=<value>` returns only records for that
   owner scope label in deterministic newest-first order.
9. Invalid create/list inputs fail before storage writes.
10. Workspace route logs and errors avoid full user content and secret values.
11. `/health` and `/api/v1/chat` public contracts remain compatible.
12. RAG/evaluation modules do not import workspace modules in R3.
13. Tests cover workspace contracts, service behavior, SQLite persistence,
    workspace routes, and chat compatibility.
14. Documentation names the workspace routes, local DB path, no-auth limitation,
    and production-readiness boundary.
15. Final verification includes backend tests, compile, import-boundary check,
    `git diff --check`, and repository status with untracked files reviewed.

## Required ADRs

1. **ADR 0002: Trip Workspace as Primary Product Container.** This records that
   trip workspace identity owns future conversation, memory, itinerary,
   decision, and trace scope.
2. **ADR 0003: Local SQLite Workspace Storage Boundary for R3.** This records
   why R3 uses a local SQLite adapter behind a repository interface and what it
   does not claim about production storage.

If the implementation plan proposes authentication, authorization, a production
database, an ORM, migration framework, or chat workspace coupling, additional
ADRs are required before implementation.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-09-03 via the
conversation phrase `Approve R3 spec v0.1`. Approval authorizes preparing the
required ADRs and, after those ADRs are accepted, preparing the R3
implementation plan. Implementation may not begin until the required ADRs and
the exact implementation plan are approved.
