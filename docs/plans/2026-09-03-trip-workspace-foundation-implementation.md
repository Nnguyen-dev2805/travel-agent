# Trip Workspace Foundation Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as local execution evidence. The coordinating agent owns dispatch,
> review, and verification orchestration only unless the repository owner
> explicitly asks that agent to code.

**Goal:** Add the R3 backend trip workspace foundation so local workspace
records can be created, retrieved, and listed behind stable contracts while the
existing health, chat, RAG, and evaluation contracts remain compatible.

**Architecture:** Implement a backend-only workspace module with explicit
contracts, a repository interface, a local SQLite adapter, a small service
layer, and FastAPI routes mounted beside chat under `/api/v1`. `TripWorkspace`
is the primary product container per ADR 0002. SQLite is a local R3 adapter
behind the repository boundary per ADR 0003.

**Tech Stack:** Python 3.11 baseline, FastAPI, Pydantic, standard-library
`sqlite3`, pytest, existing repository settings pattern, existing backend test
layout, Markdown architecture and development documentation.

**Spec:** [Trip Workspace Foundation Design](../specs/2026-09-03-trip-workspace-foundation-design.md),
version 0.1 (Approved).

**ADRs:**
[ADR 0002: Trip Workspace as Primary Product Container](../adr/0002-trip-workspace-as-primary-product-container.md)
(Accepted);
[ADR 0003: Local SQLite Workspace Storage Boundary for R3](../adr/0003-local-sqlite-workspace-storage-boundary-for-r3.md)
(Accepted).

| Field | Value |
| --- | --- |
| Status | In Progress |
| Plan version | 0.2 |
| Date | 2026-09-03 |
| Amended | 2026-09-03; see [Amendment Record](#amendment-record) |
| Approved specification | [Trip Workspace Foundation Design](../specs/2026-09-03-trip-workspace-foundation-design.md), version 0.1 |
| Execution owner | Coordinating agent, explicitly authorized by the repository owner to implement R3 inside an isolated linked worktree, under repository-owner change-set review |
| Decision owner | Repository owner |
| Scope | R3 backend workspace contracts, local SQLite storage boundary, minimal workspace routes, focused tests, and documentation updates |
| Verification | Targeted pytest per task; full backend suite; compile check; import-boundary check for RAG/evaluation to workspace; route contract checks; `git diff --check`; `git status --short --untracked-files=all`; tracked/untracked change-set review. Exact interpreter and search commands are fixed by [Verification Toolchain](#verification-toolchain) |

## Global Constraints

1. Do not begin source implementation until this plan is approved by the
   repository owner.
2. The coordinating agent may update governance Markdown, dispatch implementation
   workers, review change sets, and run/read verification. It must not make R3
   source or test implementation edits unless the repository owner explicitly
   asks it to code. The repository owner granted that explicit authorization on
   2026-09-03, scoped to implementation inside an isolated linked worktree. Every
   other constraint in this section still binds the coordinating agent.
3. Execute R3 source work only on a workspace state that includes the accepted
   R1/R2 change set or an explicitly approved integration base. If R1/R2 is not
   present, stop before source edits and return for owner direction.
4. Preserve `GET /health` behavior.
5. Preserve `POST /api/v1/chat` request shape: `message` only.
6. Preserve `POST /api/v1/chat` response shape: `reply`, `model`, and
   `citations`.
7. Do not add authentication, authorization, sessions, collaboration, memory,
   conversation persistence, planner state, itinerary versions, deletion
   semantics, production database infrastructure, an ORM, or a migration
   framework.
8. Treat `owner_user_id` as a local development scope label only. Do not describe
   it as tenant isolation, authentication, authorization, or a verified user.
9. Keep route handlers free of SQL, table DDL, SQLite path creation, and direct
   SQLite connection management.
10. Keep RAG and evaluation modules independent from workspace modules in R3.
11. Do not store workspace records in Chroma or any vector database.
12. Unit and integration tests must use temporary SQLite database paths and must
    not depend on developer-local database state.
13. Logs and errors must avoid full user-entered workspace content, secrets, and
    credentials.
14. Do not create, delete, or clean persistent local workspace database files
    outside explicit test temp directories unless the repository owner names the
    exact path and approves that action.
15. Preserve unrelated user work. Do not stage, commit, push, open a pull
    request, merge, tag, publish, delete branches, or rewrite history without an
    explicit repository-owner request for that exact Git action.

## Verification Toolchain

Plan version `0.1` wrote every verification command as `python3 -m pytest ...` and
every static check as `rg -n ...`. Neither runs in the current execution
environment. This section fixes the exact commands so the recorded evidence names
what actually ran.

| Concern | v0.1 command | v0.2 command | Environment evidence |
| --- | --- | --- | --- |
| Test runner | `python3 -m pytest` | `./.venv/bin/python -m pytest` | Host `python3` is 3.14.5 and reports `No module named pytest`; `./.venv/bin/python` is 3.14.5 with `pytest 9.1.1` and runs the existing suite green |
| Static search | `rg -n` | `grep -rn -E` / `grep -n -E` | `command -v rg` returns nothing on this machine; `/usr/bin/grep` is present |

Rules:

1. The substitution changes only the tool that executes a check. It must not
   change, narrow, or weaken what any check proves.
2. Every per-task command block in this plan inherits this substitution. The
   [Package Verification](#package-verification) block is written in substituted
   form and is the canonical command list.
3. The completion record must report the exact substituted commands that ran, not
   the v0.1 command text.
4. Installing `pytest` into the host interpreter or installing `ripgrep` is out of
   scope for R3. Neither is required to satisfy any acceptance criterion.
5. If a required check cannot run under either form, stop and report it rather
   than substituting weaker evidence.

### Worktree execution environment

Source implementation runs in the isolated linked worktree
`.worktrees/r3-workspace` on branch `r3-trip-workspace`. `git worktree add`
checks out tracked files only, so two Git-ignored paths the verification commands
depend on are absent there. Both were resolved without changing any source or
test file:

| Absent in worktree | Why it matters | Resolution |
| --- | --- | --- |
| `.venv` | `./.venv/bin/python` does not resolve from the worktree | Invoke the primary tree interpreter by absolute path: `/Users/tnhatnguyendev2805/Documents/Projects/travel-agent/.venv/bin/python`. The interpreter and site-packages come from the primary tree; `backend/` is collected from the worktree |
| `data/processed/` | `backend/tests/unit/test_chunker.py:7` reads `data/processed/vietnam_travel_raw.jsonl` and fails without it | Symlink only `data/processed` into the worktree. `data/chromadb` and `data/evaluation` are deliberately not linked so no test can write into R1/R2 baseline artifacts |

Recorded worktree baseline before any R3 change: `269 passed` in about 21
seconds, identical to the primary tree. That is the comparison baseline for
[Package Verification](#package-verification).

`docs/` is also absent from the worktree because it is Git-ignored. Governance
Markdown and every `docs/` documentation update in Task 5 are therefore edited in
the primary tree; tracked root documents are edited in the worktree.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/workspaces/__init__.py` | Export stable workspace contracts and service/repository entry points | Workspace modules |
| `backend/workspaces/models.py` | Runtime workspace value objects, create/list inputs, status enums, validation helpers | Approved spec, ADR 0002 |
| `backend/workspaces/repository.py` | Storage interface and workspace repository error types | `backend/workspaces/models.py`, ADR 0003 |
| `backend/workspaces/sqlite_repository.py` | Local SQLite schema version 1 initialization and create/get/list persistence adapter | Repository interface, backend settings, ADR 0003 |
| `backend/workspaces/service.py` | Workspace use cases and input normalization before persistence | Workspace models and repository interface |
| `backend/app/schemas/workspaces.py` | Public API request/response schemas for workspace routes | Workspace models, approved route contract |
| `backend/app/api/workspaces.py` | FastAPI workspace routes, dependency construction, HTTP errors, minimal logging | API schemas, workspace service, SQLite adapter |
| `backend/app/main.py` | Mount workspace router under `settings.API_V1_STR` beside chat | Existing route registration pattern |
| `backend/app/config.py` | Add `WORKSPACE_DB_PATH` setting with local default | ADR 0003, existing settings pattern |
| `backend/tests/unit/test_workspace_models.py` | Contract and validation tests for workspace value objects | Workspace models |
| `backend/tests/unit/test_workspace_service.py` | Service normalization, duplicate/error mapping, and no-storage-write invalid input tests | Workspace service and fake repository |
| `backend/tests/unit/test_sqlite_workspace_repository.py` | SQLite schema initialization and repository persistence tests using temp paths | SQLite adapter |
| `backend/tests/integration/test_workspace_api.py` | Workspace route create/get/list/error tests with isolated temporary database | FastAPI app, route dependency override or temp settings |
| `backend/tests/integration/test_api.py` | Existing health/chat compatibility assertions | Existing API tests |
| `DEVELOPMENT.md` | Local workspace API and `WORKSPACE_DB_PATH` development notes | Implemented route/config behavior |
| `ARCHITECTURE.md` | Architecture gateway note for R3 workspace runtime component | Accepted ADRs and implemented module |
| `docs/architecture/current-state.md` | Current-state backend map after R3 implementation | Implemented workspace module/routes |
| `docs/architecture/data-model.md` | Mark `TripWorkspace` fields implemented in R3 and keep future records conceptual | Workspace contracts |
| `docs/roadmap/master-roadmap.md` | R3 status/evidence update only | Completed verification evidence |
| `docs/plans/README.md` | Plan index entry and status lifecycle updates | This plan |
| `docs/plans/2026-09-03-trip-workspace-foundation-implementation.md` | Approved execution contract and completion record | Approved spec, ADR 0002, ADR 0003 |

## Task 1: Confirm Base State and Mark Worker Execution Start

**Files:**

- Read: `docs/specs/2026-09-03-trip-workspace-foundation-design.md`
- Read: `docs/adr/0002-trip-workspace-as-primary-product-container.md`
- Read: `docs/adr/0003-local-sqlite-workspace-storage-boundary-for-r3.md`
- Read: `docs/plans/2026-09-03-trip-workspace-foundation-implementation.md`
- Read: `docs/roadmap/master-roadmap.md`
- Modify after approval only: `docs/plans/2026-09-03-trip-workspace-foundation-implementation.md`
- Modify after approval only: `docs/plans/README.md`
- Modify after approval only: `docs/roadmap/master-roadmap.md`

**Interfaces:**

- Consumes: approved R3 spec, accepted ADR 0002, accepted ADR 0003, repository
  owner plan approval, current R1/R2 status.
- Produces: plan status transition to `In Progress` and a confirmed execution
  base.

- [x] **Step 1: Verify approval gates**

Confirm this plan says `Approved`, ADR 0002 and ADR 0003 say `Accepted`, and
the R1/R2 accepted change set is present in the execution workspace or the owner
has explicitly approved an integration base.

Plan version `0.2` requires its own repository-owner re-approval before source
implementation begins. Version `0.1` approval does not carry forward, because
version `0.2` changes the workspace contract vocabulary.

Run:

```bash
git status --short --untracked-files=all
```

Expected: no unrelated changes overlap R3 affected paths. If overlapping work
exists, inspect it and stop before editing.

- [x] **Step 2: Mark execution start**

Update this plan and the plan index from `Approved` to `In Progress`, carrying
plan version `0.2`. Update only the R3 row in
`docs/roadmap/master-roadmap.md` to show implementation in progress, citing the
approved spec, ADRs, and plan version `0.2`.

- [x] **Step 3: Review checkpoint**

Review: plan status, roadmap status, and Git status.

Expected: governance state permits source implementation and no unrelated work
is at risk.

## Task 2: Add Workspace Contracts Test-first

**Files:**

- Create: `backend/workspaces/__init__.py`
- Create: `backend/workspaces/models.py`
- Create: `backend/workspaces/repository.py`
- Create: `backend/tests/unit/test_workspace_models.py`

**Interfaces:**

- Consumes: R3 minimal workspace field contract.
- Produces:
  - `PlanningStatus` enum with R3 statuses `idea`, `planning`, `booked`,
    `active`, `completed`, `cancelled`, and `archived`.
  - `RetentionState` enum with R3 states `active`, `archived`,
    `deletion_requested`, and `deleted`. R3 creates records as `active` only and
    implements no transition into the other states.
  - `DateWindow(start_date: date | None, end_date: date | None)`.
  - `WorkspaceCreate(owner_user_id: str, title: str, destination_scope: str | None, date_window: DateWindow | None, planning_status: PlanningStatus | None)`.
  - `WorkspaceListFilter(owner_user_id: str)`.
  - `TripWorkspace(workspace_id: str, owner_user_id: str, title: str, destination_scope: str | None, date_window: DateWindow | None, planning_status: PlanningStatus, retention_state: RetentionState, created_at: datetime, updated_at: datetime)`.
  - `WorkspaceRepository` protocol with `create`, `get`, and `list_by_owner`.
  - Repository error types for duplicate identity and storage failure.

- [x] **Step 1: Write failing model and interface tests**

Cover:

1. `workspace_id` must be generated by storage/service, not accepted from create
   request input.
2. generated IDs must be strings prefixed with `tw_`;
3. `owner_user_id` and `title` are stripped and cannot be empty, and `title` is
   at most 120 characters;
4. `destination_scope` is optional; when present it is stripped and is at most
   160 characters;
5. date window permits missing start/end but rejects `end_date < start_date`;
6. default `planning_status` is `idea`;
7. default `retention_state` is `active`;
8. an unknown `planning_status` value is rejected;
9. timestamps are timezone-aware UTC datetimes;
10. public model exports are importable from `backend.workspaces`.

Run:

```bash
./.venv/bin/python -m pytest backend/tests/unit/test_workspace_models.py
```

Expected: tests fail because the module does not exist yet.

- [x] **Step 2: Implement contracts**

Implement the smallest contract layer that makes the tests pass. Use standard
library dataclasses or Pydantic consistently with the local backend style. Do
not import FastAPI, SQLite, RAG, Chroma, model-provider, or evaluation modules.

- [x] **Step 3: Run task verification**

Run:

```bash
./.venv/bin/python -m pytest backend/tests/unit/test_workspace_models.py
./.venv/bin/python -m compileall backend/workspaces
```

Expected: tests pass and compile succeeds.

- [x] **Step 4: Review checkpoint**

Review: model names, validation behavior, imports, default states, and ID
format.

Expected: the contract layer is storage-agnostic and route-agnostic.

## Task 3: Add Workspace Service and SQLite Repository Test-first

**Files:**

- Create: `backend/workspaces/service.py`
- Create: `backend/workspaces/sqlite_repository.py`
- Create: `backend/tests/unit/test_workspace_service.py`
- Create: `backend/tests/unit/test_sqlite_workspace_repository.py`
- Modify: `backend/app/config.py`

**Interfaces:**

- Consumes: workspace contracts and repository protocol.
- Produces:
  - `WorkspaceService.create_workspace(input: WorkspaceCreate) -> TripWorkspace`.
  - `WorkspaceService.get_workspace(workspace_id: str) -> TripWorkspace | None`.
  - `WorkspaceService.list_workspaces(owner_user_id: str) -> tuple[TripWorkspace, ...]`.
  - `SQLiteWorkspaceRepository(db_path: Path)`.
  - settings field `WORKSPACE_DB_PATH`, defaulting to `data/workspaces/travel_agent_workspaces.sqlite3`.

- [x] **Step 1: Write failing service tests**

Use a fake repository to prove:

1. invalid owner, title, destination-scope, date-window, and planning-status
   inputs fail before repository writes;
2. create returns repository-created workspace;
3. get returns `None` for missing workspace;
4. list requires a non-empty owner scope label;
5. list returns repository order without route-layer mutation;
6. a duplicate generated `workspace_id` is retried exactly once, and a second
   collision surfaces a controlled infrastructure error rather than a partial
   write;
7. service does not import FastAPI, RAG, Chroma, model-provider, or evaluation
   modules.

Run:

```bash
./.venv/bin/python -m pytest backend/tests/unit/test_workspace_service.py
```

Expected: tests fail before implementation.

- [x] **Step 2: Write failing SQLite repository tests**

Use `tmp_path` database files to prove:

1. parent directory and schema version 1 initialize safely, recording the version
   through `PRAGMA user_version = 1` or a dedicated metadata table;
2. an existing database reporting an incompatible schema version fails closed
   with a controlled storage error and does not silently migrate;
3. create persists normalized workspace fields and server-generated `tw_` ID;
4. get returns the exact stored workspace;
5. missing get returns `None`;
6. list by owner excludes other owner labels;
7. list by owner orders by `updated_at` descending, then `created_at`
   descending, then `workspace_id` ascending;
8. invalid persisted date/state values fail closed through repository errors;
9. tests do not read or write the default developer database path.

Run:

```bash
./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_workspace_repository.py
```

Expected: tests fail before implementation.

- [x] **Step 3: Implement service, SQLite adapter, and config**

Implement the storage boundary in `backend/workspaces/sqlite_repository.py`.
Use parameterized SQL, context-managed connections, UTC ISO timestamp storage,
and one table for R3 workspace records. Keep schema initialization local to the
adapter and avoid a general migration framework.

Add `WORKSPACE_DB_PATH` to `backend/app/config.py` using the existing settings
style and repository root path. Do not change RAG/provider settings.

- [x] **Step 4: Run task verification**

Run:

```bash
./.venv/bin/python -m pytest backend/tests/unit/test_workspace_service.py backend/tests/unit/test_sqlite_workspace_repository.py
./.venv/bin/python -m compileall backend/workspaces backend/app/config.py
```

Expected: tests pass and compile succeeds.

- [x] **Step 5: Review checkpoint**

Review: SQL stays inside the SQLite adapter, temp-path tests are isolated,
timestamps are UTC, no workspace record is stored in Chroma, and
`owner_user_id` is still a scope label only.

Expected: service and repository can be reviewed independently from FastAPI.

## Task 4: Add Workspace API Routes Test-first

**Files:**

- Create: `backend/app/schemas/workspaces.py`
- Create: `backend/app/api/workspaces.py`
- Create: `backend/tests/integration/test_workspace_api.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/integration/test_api.py`

**Interfaces:**

- Consumes: workspace service and repository adapter.
- Produces:
  - `POST /api/v1/workspaces` returns `201` and a workspace response.
  - `GET /api/v1/workspaces/{workspace_id}` returns workspace response or
    `404`.
  - `GET /api/v1/workspaces?owner_user_id=<value>` returns a
    `{"workspaces": [...]}` object, never a bare array. The array is scoped to the
    requested owner label and ordered by `updated_at` descending, then
    `created_at` descending, then `workspace_id` ascending.

- [x] **Step 1: Write failing route tests**

Use an isolated temporary SQLite database through route dependency override or
an equivalent test-local construction. Cover:

1. successful create returns `201`, generated `tw_` ID, normalized fields,
   default `planning_status` `idea`, default `retention_state` `active`, and
   timestamps;
2. get returns the created workspace;
3. get missing workspace returns `404`;
4. list requires `owner_user_id`;
5. list returns the `{"workspaces": [...]}` object shape, excludes other owner
   labels, and applies the governed ordering;
6. invalid create inputs return `422` and create no record, covering blank owner,
   blank title, `title` over 120 characters, `destination_scope` over 160
   characters, unknown `planning_status`, and `end_date` earlier than
   `start_date`;
7. route errors do not echo full user-entered title or destination text;
8. health endpoint remains unchanged;
9. chat endpoint still rejects empty `message` as before.

Run:

```bash
./.venv/bin/python -m pytest backend/tests/integration/test_workspace_api.py backend/tests/integration/test_api.py
```

Expected: new route tests fail before implementation; existing health/chat tests
continue to describe the compatibility contract.

- [x] **Step 2: Implement schemas and routes**

Implement request and response schemas in `backend/app/schemas/workspaces.py`.
Implement the router in `backend/app/api/workspaces.py`. Keep logging minimal
and avoid logging full user-entered content. Convert validation/storage misses
to appropriate HTTP errors without exposing secrets or local paths.

Mount the router in `backend/app/main.py` with `prefix=settings.API_V1_STR`,
matching the existing chat route registration pattern.

- [x] **Step 3: Run task verification**

Run:

```bash
./.venv/bin/python -m pytest backend/tests/integration/test_workspace_api.py backend/tests/integration/test_api.py
./.venv/bin/python -m compileall backend/app backend/workspaces
```

Expected: workspace routes pass, health/chat compatibility passes, compile
succeeds.

- [x] **Step 4: Review checkpoint**

Review: public API shape, HTTP status codes, response field names, dependency
construction, and absence of RAG/Chroma/model-provider work in workspace routes.

Expected: R3 routes are minimal and mounted beside chat without coupling chat to
workspace.

## Task 5: Add Documentation Updates

**Files:**

- Modify: `DEVELOPMENT.md`
- Modify: `ARCHITECTURE.md`
- Modify: `docs/architecture/current-state.md`
- Modify: `docs/architecture/data-model.md`
- Modify: `docs/roadmap/master-roadmap.md`
- Modify: `docs/plans/2026-09-03-trip-workspace-foundation-implementation.md`
- Modify: `docs/plans/README.md`

**Interfaces:**

- Consumes: implemented R3 behavior and verification evidence.
- Produces: accurate local development, architecture, data model, roadmap, and
  plan-status documentation.

- [x] **Step 1: Update local development docs**

Document:

1. `WORKSPACE_DB_PATH` default path;
2. the three workspace endpoints;
3. example local requests that do not include secrets;
4. explicit no-auth limitation for `owner_user_id`;
5. local SQLite is not production storage readiness.

- [x] **Step 2: Update architecture docs**

Update architecture gateway/current-state/data-model docs to say R3 implements
the minimal `TripWorkspace` runtime record and local SQLite adapter. Keep
conversation, memory, planner state, itinerary versions, deletion semantics,
production database, and auth as future work.

- [x] **Step 3: Update roadmap and plan state**

Update R3 roadmap status with implementation evidence only after verification
passes. Do not mark R4 or later milestones started. Move this plan and plan
index to `Completed` only after package verification and owner change-set
review evidence are ready.

- [x] **Step 4: Run documentation checks**

Run:

```bash
grep -n -E "tenant isolation|authenticated user|authorization control|production ready|production database" DEVELOPMENT.md ARCHITECTURE.md docs/architecture/current-state.md docs/architecture/data-model.md docs/roadmap/master-roadmap.md docs/plans/2026-09-03-trip-workspace-foundation-implementation.md
```

Expected: any matches are reviewed and either removed or clearly framed as
future/non-goal language.

- [x] **Step 5: Review checkpoint**

Review: docs match implemented behavior and do not overclaim production,
security, memory, planner, or chat-workspace behavior.

Expected: documentation supports R3 review without opening new scope.

## Task 6: Run Package Verification and Scope Review

**Files:**

- Read: all changed tracked and untracked R3 files.
- Modify: `docs/plans/2026-09-03-trip-workspace-foundation-implementation.md`
  completion record after verification.
- Modify: `docs/plans/README.md` status after verification.
- Modify: `docs/roadmap/master-roadmap.md` R3 evidence after verification.

**Interfaces:**

- Consumes: completed source and docs from Tasks 1-5.
- Produces: final review evidence for repository-owner change-set review.

- [x] **Step 1: Run full backend tests**

Run:

```bash
./.venv/bin/python -m pytest backend/tests
```

Expected: all backend tests pass. The pre-implementation baseline on this
execution base was `269 passed` in about 21 seconds, so the post-implementation
count must be `269` plus the new R3 tests with no pre-existing test turning red.
If integration tests require unavailable external model or Chroma state, stop and
report the exact failing command and reason instead of substituting weaker
evidence.

- [x] **Step 2: Run compile verification**

Run:

```bash
./.venv/bin/python -m compileall backend
```

Expected: compile succeeds.

- [x] **Step 3: Run import-boundary checks**

Run:

```bash
grep -rn -E "backend\.workspaces|app\.api\.workspaces|app\.schemas\.workspaces" backend/rag
grep -n -E "backend\.workspaces|app\.api\.workspaces|app\.schemas\.workspaces" backend/tests/unit/test_evaluation_*.py backend/tests/integration/test_rag_evaluation_flow.py
```

Expected: no matches from either command; `grep` exit status `1` with empty output
is the passing result. If a test needs a workspace fixture later, that is out of
scope for R3 and requires review.

Run:

```bash
grep -rn -E "sqlite3|CREATE TABLE|WORKSPACE_DB_PATH" backend/app backend/workspaces
```

Expected: `sqlite3` and `CREATE TABLE` appear only in
`backend/workspaces/sqlite_repository.py`. `WORKSPACE_DB_PATH` may additionally
appear in `backend/app/config.py`, which defines it, and at the single dependency
construction site in `backend/app/api/workspaces.py`. Any other match is a
boundary violation and must be fixed, not explained.

- [x] **Step 4: Run API contract checks**

Run targeted tests that prove:

```bash
./.venv/bin/python -m pytest backend/tests/integration/test_workspace_api.py backend/tests/integration/test_api.py
```

Expected: workspace routes pass and existing health/chat compatibility remains
unchanged.

- [x] **Step 5: Run diff and status checks**

Run:

```bash
git diff --check
git status --short --untracked-files=all
```

Expected: no whitespace errors; all changed and untracked files are reviewed.
Remember `docs/` may be ignored local governance evidence, so inspect relevant
doc files directly even when Git status is clean.

- [x] **Step 6: Complete scope review**

Compare all changed files against the approved spec, ADR 0002, ADR 0003, and
this plan. Confirm:

1. R3 implements only workspace contracts, local SQLite storage, minimal routes,
   tests, and docs;
2. no auth, memory, planner, conversation persistence, itinerary versioning,
   deletion semantics, ORM, migration framework, production database, or UI work
   was added;
3. chat, health, RAG, and evaluation compatibility evidence is fresh;
4. local database files are not accidentally included in the delivery change
   set.

- [x] **Step 7: Prepare owner review handoff**

Record the exact verification commands and outcomes in this plan completion
record. Summarize changed files, evidence, limitations, and remaining Git
delivery gate for repository-owner review.

Expected: the repository owner can review and decide whether to accept the R3
change set. Do not stage, commit, push, or open a PR unless explicitly asked.

## Package Verification

Run these commands freshly after implementation, from the isolated
implementation worktree. They are written in the substituted form fixed by
[Verification Toolchain](#verification-toolchain) and are the canonical command
list for this plan:

```bash
./.venv/bin/python -m pytest backend/tests/unit/test_workspace_models.py
./.venv/bin/python -m pytest backend/tests/unit/test_workspace_service.py
./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_workspace_repository.py
./.venv/bin/python -m pytest backend/tests/integration/test_workspace_api.py backend/tests/integration/test_api.py
./.venv/bin/python -m pytest backend/tests
./.venv/bin/python -m compileall backend
grep -rn -E "backend\.workspaces|app\.api\.workspaces|app\.schemas\.workspaces" backend/rag
grep -n -E "backend\.workspaces|app\.api\.workspaces|app\.schemas\.workspaces" backend/tests/unit/test_evaluation_*.py backend/tests/integration/test_rag_evaluation_flow.py
grep -rn -E "sqlite3|CREATE TABLE|WORKSPACE_DB_PATH" backend/app backend/workspaces
git diff --check
git status --short --untracked-files=all
```

Expected package result:

1. all workspace unit and integration tests pass;
2. the full backend suite reports the pre-implementation `269 passed` plus the new
   R3 tests, with no previously passing test turning red, or any unavailable
   external dependency is named with exact failure output;
3. compile succeeds;
4. both RAG/evaluation import-boundary greps return no matches, meaning `grep`
   exit status `1` with empty output;
5. `sqlite3` and `CREATE TABLE` appear only in
   `backend/workspaces/sqlite_repository.py`, and `WORKSPACE_DB_PATH` appears only
   in `backend/app/config.py` and the single dependency construction site;
6. no whitespace errors exist;
7. tracked and untracked implementation files are reviewed against approved
   scope;
8. ignored `docs/` governance files are inspected directly and reported;
9. no local SQLite database file created during testing appears in the delivery
   change set.

## Rollback

Before owner acceptance, rollback removes the R3 workspace module, workspace
routes, config setting, tests, and documentation edits through normal reviewed
Git history. It must preserve unrelated work, R1/R2 evaluation artifacts,
Chroma state, and any local database files not explicitly approved for deletion.

If a test or local run creates a SQLite database at `WORKSPACE_DB_PATH`, treat
it as local development state. Do not delete it unless the repository owner
names the exact path and approves deletion after recoverability is understood.

After owner acceptance, replacing SQLite, changing workspace route contracts,
adding deletion semantics, adding auth, or coupling chat to workspace requires a
new approved spec and plan. A production storage replacement also requires a
new ADR or superseding ADR for ADR 0003.

## Amendment Record

Version `0.2` was drafted by the coordinating agent on 2026-09-03 at the
repository owner's request, after preflight review found that version `0.1`
contradicted the approved specification and specified verification commands that
cannot run in this environment. The repository owner approved version `0.2` on
2026-09-03 via the conversation phrase
`Approve R3 implementation plan v0.2`. That approval opened the gate that
version `0.1` approval could not carry, because version `0.2` changed the
workspace contract vocabulary.

### Contract corrections, resolving plan-versus-spec conflicts

Authority order places the approved specification above this plan, and
[Data Model](../architecture/data-model.md) agrees with the specification on every
point below. Version `0.1` was the outlier in all three cases.

| Item | v0.1 said | v0.2 says | Governing source |
| --- | --- | --- | --- |
| `PlanningStatus` values | `draft`, `active`, `archived` | `idea`, `planning`, `booked`, `active`, `completed`, `cancelled`, `archived` | Spec `:307`; data-model `:114` |
| `planning_status` default | `draft` | `idea` | Spec `:329-330`, `:480` |
| `RetentionState` values | `active`, `retained` | `active`, `archived`, `deletion_requested`, `deleted` | Spec `:308`; data-model `:117` |
| `destination_scope` | required, non-empty | optional, stripped when present, max 160 characters | Spec `:305`, `:329` |
| `title` length | unstated | max 120 characters | Spec `:304`, `:384` |

The value `retained` appears in no other repository artifact and was removed.

### Under-specification closed

Version `0.1` was silent where the specification is explicit. These are additions,
not changes of intent:

1. **List response shape.** The list route returns `{"workspaces": [...]}`, never a
   bare array, per spec `:339-360`.
2. **List ordering.** `updated_at` descending, then `created_at` descending, then
   `workspace_id` ascending, per spec `:362-363`.
3. **Duplicate ID retry.** The service retries a generated-ID collision exactly
   once, then surfaces a controlled infrastructure error, per spec `:391`. A test
   now covers it.
4. **Incompatible schema version.** The SQLite adapter fails closed rather than
   migrating silently, per spec `:489-493`. A test now covers it.
5. **Invalid-input status code.** Create validation failures return `422`, per spec
   `:380-387`, replacing the looser `4xx`.

### Verification commands

All `python3 -m pytest` commands became `./.venv/bin/python -m pytest`, and all
`rg -n` commands became `grep` equivalents. The reasons, evidence, and rules are
recorded in [Verification Toolchain](#verification-toolchain). Nothing about what
each check proves was changed or weakened.

### Execution owner

The repository owner explicitly authorized the coordinating agent to implement R3
directly, inside an isolated linked worktree, on 2026-09-03. Global Constraint 2
records that grant. Constraint 15 and the Git-delivery boundary are unchanged: no
staging, commit in the primary tree, push, pull request, merge, tag, or release
without a separate explicit owner instruction.

### Not changed

Scope, non-goals, the six tasks and their order, the layering rules, all fifteen
global constraints beyond the Constraint 2 authorization note, the rollback
contract, and the R1/R2 integration-base requirement are unchanged from version
`0.1`.

### Reconstruction after local `docs/` loss

On 2026-09-03, after Tasks 1 through 4 had been executed and verified, the local
`docs/` tree lost content when a `docs` symlink was replaced by a real directory.
Sixteen Markdown files disappeared, including the approved version `0.2` of this
plan; this file reverted to its version `0.1` text and its checkbox state reset.

Version `0.2` was reconstructed on the same day at the repository owner's request
from the approved specification, the accepted ADRs, and the R3 source and tests
already present in `.worktrees/r3-workspace`. Every contract statement above was
re-derived from the specification rather than from memory, and each row cites its
governing specification line.

The reconstruction changed no source file. The implemented enums, defaults, list
response shape, ordering, retry behavior, and schema-version handling in
`.worktrees/r3-workspace` already matched this version and were re-verified after
reconstruction. Checkbox state for Tasks 1 through 4 was restored to reflect work
that had actually run, with its recorded evidence in the completion record.

Unrelated to R3, sixteen local governance documents remain lost, including six
agent-tooling specifications dated 2026-09-02 and 2026-09-03 and the
`docs/reports/rag/` baseline report. They were not recoverable from Git history,
the system trash, or local snapshots. That loss is outside R3 scope and is
reported to the repository owner as a separate matter.

## Completion Record

Plan version 0.1 was approved by the repository owner on 2026-09-03 via the
conversation phrase `Approve R3 implementation plan v0.1`. The repository owner
also approved the current workspace as the R3 integration base via the
conversation phrase `Approve current workspace as R3 integration base` after
accepting the R1/R2 change set via `Accept R1/R2 change set; proceed with R3`.

Plan version 0.2 was approved by the repository owner on 2026-09-03 via the
conversation phrase `Approve R3 implementation plan v0.2`, after the coordinating
agent drafted the amendment recorded in
[Amendment Record](#amendment-record). Version 0.1 approval did not carry forward
because the workspace contract vocabulary changed.

### Execution environment

Implementation runs in the isolated linked worktree `.worktrees/r3-workspace` on
branch `r3-trip-workspace`, based on `6076d9e`. The primary working tree remains
untouched: `git status --short --untracked-files=all` there is empty and `HEAD`
remains `6076d9e` on `feature/agent-memory`.

Interpreter: `/Users/tnhatnguyendev2805/Documents/Projects/travel-agent/.venv/bin/python`
(Python 3.14.5, pytest 9.1.1), invoked by absolute path because the worktree has
no `.venv`. Static searches use `grep`. See
[Verification Toolchain](#verification-toolchain).

Recorded worktree baseline before any R3 change: `269 passed` in about 21 seconds.

### Task evidence

| Task | Result | Evidence |
| --- | --- | --- |
| Task 1 | Complete | Approval gates verified: plan v0.2 approved, ADR 0002 `Accepted`, ADR 0003 `Accepted`, spec v0.1 `Approved`, R1/R2 integration base approved, primary `git status` empty. Plan, plan index, and the roadmap R3 row moved to `In Progress` |
| Task 2 | Complete | RED: `test_workspace_models.py` failed with `ModuleNotFoundError: No module named 'backend.workspaces'`. GREEN: `50 passed`. `compileall backend/workspaces` succeeded |
| Task 3 | Complete | RED: both service and SQLite repository test modules failed collection before implementation. GREEN: `59 passed` across `test_workspace_service.py` and `test_sqlite_workspace_repository.py`. `compileall backend/workspaces backend/app/config.py` succeeded |
| Task 4 | Complete | RED: `test_workspace_api.py` failed to import `backend.app.api.workspaces`. GREEN: `37 passed` across `test_workspace_api.py` and `test_api.py`. `compileall backend/app backend/workspaces` succeeded |
| Task 5 | Complete | `DEVELOPMENT.md` and `ARCHITECTURE.md` updated in the worktree; `docs/architecture/current-state.md`, `docs/architecture/data-model.md`, `docs/roadmap/master-roadmap.md`, this plan, and `docs/plans/README.md` updated in the primary tree. Documentation grep reviewed; every match frames the no-auth and non-production boundary explicitly |
| Task 6 | Complete | Fresh package verification recorded below |

### Task 6 package verification

Run freshly in `.worktrees/r3-workspace` after Task 5:

| Command | Result |
| --- | --- |
| `./.venv/bin/python -m pytest backend/tests` | `413 passed` in about 22 seconds |
| `./.venv/bin/python -m compileall backend` | exit `0` |
| `grep -rn -E "backend\.workspaces\|app\.api\.workspaces\|app\.schemas\.workspaces" backend/rag` | exit `1`, no matches |
| `grep -n -E "backend\.workspaces\|app\.api\.workspaces\|app\.schemas\.workspaces" backend/tests/unit/test_evaluation_*.py backend/tests/integration/test_rag_evaluation_flow.py` | exit `1`, no matches |
| `grep -rn -E "sqlite3\|CREATE TABLE\|WORKSPACE_DB_PATH" backend/app backend/workspaces` | `sqlite3` and `CREATE TABLE` only in `backend/workspaces/sqlite_repository.py`; `WORKSPACE_DB_PATH` only in `backend/app/config.py` and the single dependency construction site in `backend/app/api/workspaces.py` |
| `./.venv/bin/python -m pytest backend/tests/integration/test_workspace_api.py backend/tests/integration/test_api.py` | `37 passed` |
| `git diff --check` | exit `0`, no whitespace errors |
| `git status --short --untracked-files=all` | 4 modified, 11 untracked; no database file present |

The suite total is the recorded `269` baseline plus `144` new R3 tests. No
previously passing test turned red.

A live route smoke check through `TestClient` with a temporary database confirmed
`POST` `201`, `GET` `200`, missing `GET` `404`, list `200` returning the
`{"workspaces": [...]}` object, list without `owner_user_id` `422`, unknown
`planning_status` `422`, `GET /health` `200`, and empty-message chat `400`. The
default developer database at `WORKSPACE_DB_PATH` was never created.

### Change set

Worktree `.worktrees/r3-workspace`, branch `r3-trip-workspace`, base `6076d9e`.

| File | Change | Requirement satisfied |
| --- | --- | --- |
| `backend/workspaces/models.py` | New, 312 lines | Workspace contracts, planning and retention vocabularies, validation, `tw_` identity, UTC timestamps |
| `backend/workspaces/repository.py` | New, 55 lines | Storage interface and repository error types |
| `backend/workspaces/sqlite_repository.py` | New, 305 lines | Local SQLite adapter, schema version 1, fail-closed version check |
| `backend/workspaces/service.py` | New, 102 lines | Create, get, and list use cases with one identity retry |
| `backend/workspaces/__init__.py` | New, 55 lines | Public exports |
| `backend/app/schemas/workspaces.py` | New, 92 lines | Request and response JSON shapes, list object wrapper |
| `backend/app/api/workspaces.py` | New, 153 lines | Three routes, dependency construction, controlled HTTP errors, minimal logging |
| `backend/app/config.py` | +8 lines | `WORKSPACE_DB_PATH` setting |
| `backend/app/main.py` | +2 lines | Workspace router mounted under `settings.API_V1_STR` |
| `backend/tests/unit/test_workspace_models.py` | New, 402 lines | Contract and validation coverage |
| `backend/tests/unit/test_workspace_service.py` | New, 325 lines | Service behavior, retry, no-write-on-invalid coverage |
| `backend/tests/unit/test_sqlite_workspace_repository.py` | New, 421 lines | Schema, persistence, ordering, fail-closed coverage |
| `backend/tests/integration/test_workspace_api.py` | New, 327 lines | Route, error, and chat compatibility coverage |
| `DEVELOPMENT.md` | +59 lines | Workspace routes, `WORKSPACE_DB_PATH`, no-auth and non-production limits |
| `ARCHITECTURE.md` | +53, -4 lines | Workspace components, trust boundary, invariants, gaps, local workspace flow |

`docs/architecture/current-state.md`, `docs/architecture/data-model.md`,
`docs/roadmap/master-roadmap.md`, `docs/plans/README.md`, and this plan changed in
the primary tree. They are Git-ignored local governance evidence and are not part
of the Git delivery change set.

### Scope review

R3 added workspace contracts, local SQLite storage, three routes, tests, and
documentation only. No authentication, authorization, session, collaboration,
memory, conversation persistence, planner state, itinerary versioning, deletion
semantics, ORM, migration framework, production database, or UI work was added.
Chat, health, RAG, and evaluation compatibility evidence is fresh. No local
database file appears in the change set.

Two review notes:

1. The routes use integer HTTP status literals rather than `fastapi.status`
   constants, because the installed Starlette 1.6.0 emits a deprecation warning
   for `HTTP_422_UNPROCESSABLE_ENTITY`. Response codes are unchanged.
2. `backend/app/main.py` and `backend/app/config.py` were reduced to the minimum
   R3 diff after an initial edit introduced incidental reformatting. The final
   diff is 2 added lines in `main.py` and 8 in `config.py`.

### Remaining gates

Repository-owner change-set review has not occurred. Git delivery remains under
repository-owner control; nothing has been staged, committed, pushed, or opened as
a pull request. The plan moves to `Completed` only after the owner accepts this
change set.
