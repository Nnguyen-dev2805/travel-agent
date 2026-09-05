# Trip Planner State Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence.

**Goal:** Build backend-only R7 planner state so trip workspaces can persist
itinerary versions, trip decisions, and operation evidence without implicit chat
writes.

**Architecture:** `backend/planner/` owns planner contracts, service use cases,
repository protocol, SQLite adapter, and planner evaluation. FastAPI planner
routes call only `PlannerService`; SQL stays in `SQLitePlannerRepository`.
Planner state uses the shared local SQLite application store through a new
`planner_state` schema module at version 1.

**Tech Stack:** Python 3.11+ baseline for repository compatibility; local
verification may run through the primary-tree `.venv` Python such as 3.14.x.
FastAPI, Pydantic, standard-library `sqlite3`, pytest, Markdown, existing shared
schema registry, existing backend test layout.

**Spec:** [Trip Planner State Design](../specs/2026-09-05-trip-planner-state-design.md), version 0.2 (Approved)

| Field | Value |
| --- | --- |
| Status | Completed |
| Plan version | 0.2 |
| Date | 2026-09-05 |
| Approved specification | [Trip Planner State Design](../specs/2026-09-05-trip-planner-state-design.md), version 0.2, approved by repository owner on 2026-09-05 |
| Governing ADRs | [ADR 0008](../adr/0008-workspace-owned-planner-state-and-operation-log.md) (Accepted) |
| Plan approval | Approved by repository owner on 2026-09-05 |
| Execution owner | Implementation worker agent in an isolated worktree |
| Decision owner | Repository owner |
| Scope | Runtime milestone R7 - planner contracts, SQLite planner repository, service use cases, planner API routes, deterministic evaluation harness, tests, reports, and docs |
| Verification | `./.venv/bin/python -m pytest backend/tests`, `./.venv/bin/python -m compileall backend`, planner import-boundary `grep` checks, R7 planner evaluation report validation, `git diff --check`, `git status --short --untracked-files=all` |

## Approval Gate

Do not implement this plan until all are true:

1. ADR 0008 is accepted.
2. R7 spec version 0.2 is approved.
3. This implementation plan version 0.2 is approved.
4. The selected implementation base includes delivered R6 commits through
   `d62b41b` or a later repository-owner selected base.

## Global Constraints

1. R7 is backend-only.
2. No frontend UI, authentication, authorization, production storage, cloud
   deployment, maps, booking APIs, calendars, external APIs, or LLM itinerary
   generation.
3. No implicit planner writes from chat, memory retrieval, RAG retrieval, or
   model output.
4. `backend/planner` must not import `backend.rag`, `backend.memory`, or
   `backend.orchestration`.
5. `backend.rag`, `backend.memory`, and `backend.orchestration` must not import
   `backend.planner`.
6. FastAPI planner routes must call `PlannerService` only; no SQL, DDL, direct
   SQLite connections, filesystem path resolution beyond dependency construction,
   or business lifecycle decisions in route handlers.
7. SQL and schema registration live only in `backend/planner/sqlite_repository.py`.
8. R7 registers `('planner_state', 1)` and does not change existing schema module
   versions for workspaces, conversations, memory, or memory records.
9. Tests must use temporary SQLite database paths, never developer `APP_DB_PATH`.
10. No raw full message content, itinerary text, decision statement, model
    output, prompt, or provider response in logs.
11. Rejected decisions remain first-class records.
12. Accepting one itinerary supersedes prior accepted versions only inside the
    same workspace.
13. Successful itinerary creates allocate contiguous version numbers per
    workspace; failed and rejected requests do not allocate itinerary versions.
14. Planner ids use `uuid.uuid4().hex` with prefixes `itv_`, `td_`, and `po_`.
15. Git staging, commit, push, PR, merge, release, and destructive cleanup remain
    repository-owner actions unless explicitly requested.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/planner/__init__.py` | Stable package exports | Planner models, service, repository |
| `backend/planner/models.py` | Domain value objects, ids, enums, validation | Workspace/conversation id conventions |
| `backend/planner/repository.py` | Repository protocol and storage errors | Planner models |
| `backend/planner/sqlite_repository.py` | SQLite schema, serialization, transactions | Planner repository protocol, schema registry |
| `backend/planner/service.py` | Workspace-scoped use cases and operation logging | Planner repository, workspace repository, conversation repository |
| `backend/planner/evaluation/__init__.py` | Evaluation exports | Evaluation models and runner |
| `backend/planner/evaluation/models.py` | Evaluation report contracts | D5 result-state vocabulary |
| `backend/planner/evaluation/runner.py` | Deterministic fixture runner | Planner service and SQLite adapter |
| `backend/planner/evaluation/cli.py` | `run-state` CLI command | Evaluation runner |
| `backend/app/schemas/planner.py` | Request and response schemas | Planner models |
| `backend/app/api/planner.py` | Planner API routes and dependency construction | Planner service and SQLite adapters |
| `backend/app/main.py` | Mount planner router | Planner API module |
| `backend/tests/unit/test_planner_models.py` | Contract tests | Planner models |
| `backend/tests/unit/test_sqlite_planner_repository.py` | Storage tests | SQLite planner repository |
| `backend/tests/unit/test_planner_service.py` | Use-case tests | Planner service |
| `backend/tests/integration/test_planner_api.py` | Route tests | FastAPI app and planner service |
| `backend/tests/integration/test_chat_planner_isolation.py` | No implicit planner writes from chat | Chat API and SQLite planner repository |
| `backend/tests/unit/test_planner_evaluation_runner.py` | Evaluation tests | Planner evaluation runner |
| `docs/evaluation/fixtures/planner/r7-state-v0.1/manifest.json` | Fixture manifest | R7 evaluation design |
| `docs/evaluation/fixtures/planner/r7-state-v0.1/examples.jsonl` | Synthetic planner scenarios | R7 evaluation design |
| `docs/reports/planner/r7-state-v0.1.json` | Machine-readable report | R7 evaluation run |
| `docs/reports/planner/r7-state-v0.1.md` | Human-readable report | R7 evaluation run |
| `ARCHITECTURE.md` | Current-state gateway after implementation | Implemented R7 behavior |
| `DEVELOPMENT.md` | Planner API/evaluation commands | Implemented R7 behavior |
| `docs/architecture/current-state.md` | Implemented planner state description | Implemented R7 behavior |
| `docs/architecture/data-model.md` | Implemented planner records | Planner contracts |
| `docs/roadmap/master-roadmap.md` | R7 status and evidence | Owner review and verification |
| `docs/plans/README.md` | Plan index status | This plan |
| `docs/specs/README.md` | Spec index status | R7 spec |

## Task 1: Preflight and Governance Gate

**Files:**
- Read: `AGENTS.md`
- Read: `docs/specs/2026-09-05-trip-planner-state-design.md`
- Read: `docs/adr/0008-workspace-owned-planner-state-and-operation-log.md`
- Read: `docs/plans/2026-09-05-trip-planner-state-implementation.md`
- Modify: `docs/plans/2026-09-05-trip-planner-state-implementation.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/roadmap/master-roadmap.md`

**Interfaces:**
- Consumes: owner approvals for ADR 0008, R7 spec v0.2, and this plan v0.2.
- Produces: implementation worktree with documented base commit and R7 plan
  state moved to `In Progress`.

- [x] **Step 1: Confirm implementation base**

Run:

```text
git status --short --branch --untracked-files=all
git log --oneline -5
```

Expected: implementation worktree is clean and base includes R6 delivery.

- [x] **Step 2: Confirm approval gates**

Expected headers:

```text
ADR 0008: Accepted
R7 spec v0.2: Approved
R7 plan v0.2: Approved
```

Stop if any value is missing.

- [x] **Step 3: Move R7 docs into implementation state**

Update this plan status to `In Progress`, update `docs/plans/README.md`, and
update roadmap `R7` from `Ready for handoff` to `In progress`.

- [x] **Step 4: Run baseline tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_workspace_models.py backend/tests/unit/test_conversation_models.py backend/tests/unit/test_memory_records.py -q
```

Expected: existing workspace, conversation, and memory contracts pass.

- [x] **Step 5: Review checkpoint**

Review: approval gates, base commit, and R7 status edits.

Expected: no source code changed; only governance state moved into
implementation.

## Task 2: Planner Domain Contracts

**Files:**
- Create: `backend/planner/__init__.py`
- Create: `backend/planner/models.py`
- Create: `backend/tests/unit/test_planner_models.py`

**Interfaces:**
- Consumes: R7 domain contracts from the spec.
- Produces: id helpers, enums, `ItineraryItem`, `ItineraryVersion`,
  `TripDecision`, `PlannerOperation`, and `PlannerValidationError`.

- [x] **Step 1: Write failing model tests**

Create tests asserting generated ids use `uuid.uuid4().hex`-style prefixes,
required text is stripped and validated, optional blank text becomes `None`,
version/day/position values are positive, datetimes are UTC, itinerary items are
typed, and decision `updated_at` is not earlier than `created_at`.

- [x] **Step 2: Run RED**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_planner_models.py -q
```

Expected: FAIL because planner models do not exist.

- [x] **Step 3: Implement models**

Implement the dataclasses and enums using the validation style from
`backend/workspaces/models.py` and `backend/conversations/models.py`.

- [x] **Step 4: Export contracts**

Export stable domain classes and id helpers from `backend/planner/__init__.py`.

- [x] **Step 5: Run GREEN**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_planner_models.py -q
```

Expected: PASS.

- [x] **Step 6: Review checkpoint**

Review: model names, enum values, id prefixes, validation errors, and package
exports.

Expected: contracts match the spec and introduce no dependency on RAG, memory,
or orchestration.

## Task 3: Planner Repository and SQLite Adapter

**Files:**
- Create: `backend/planner/repository.py`
- Create: `backend/planner/sqlite_repository.py`
- Create: `backend/tests/unit/test_sqlite_planner_repository.py`

**Interfaces:**
- Consumes: planner domain contracts.
- Produces: `PlannerRepository`, planner storage errors, and
  `SQLitePlannerRepository(db_path: Path | str)`.

- [x] **Step 1: Write failing repository tests**

Tests must cover schema registration, idempotent initialization, fail-closed
schema mismatch, itinerary round trip, per-workspace contiguous version numbers,
accept supersession in the same workspace, archive transitions, decision
round trip, replacement supersession, operation ordering, and cross-workspace
not-found behavior.

- [x] **Step 2: Run RED**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_planner_repository.py -q
```

Expected: FAIL because repository code does not exist.

- [x] **Step 3: Implement repository protocol**

Define protocol methods with explicit tuple returns and no Pydantic dependency.

- [x] **Step 4: Implement SQLite schema**

Create `planner_itinerary_versions`, `planner_trip_decisions`, and
`planner_operations`. Store itinerary `items` as JSON through structured
serialization from domain objects. Register `planner_state` through
`register_module_schema`.

- [x] **Step 5: Implement atomic write helpers**

Use SQLite transactions for itinerary create, itinerary accept, itinerary
archive, decision create/replacement, and decision status update.

- [x] **Step 6: Run GREEN**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_planner_repository.py -q
```

Expected: PASS.

- [x] **Step 7: Review checkpoint**

Review: SQL is isolated to `sqlite_repository.py`, schema version is
`planner_state = 1`, temporary database tests cover failure and transaction
semantics, and existing schema modules are untouched.

Expected: repository methods satisfy the protocol and keep workspace isolation.

## Task 4: Planner Service

**Files:**
- Create: `backend/planner/service.py`
- Create: `backend/tests/unit/test_planner_service.py`

**Interfaces:**
- Consumes: planner repository, workspace repository protocol, conversation
  repository protocol, planner models.
- Produces: `PlannerService` use cases named in the R7 spec.

- [x] **Step 1: Write failing service tests**

Use fakes for planner, workspace, and conversation repositories. Cover missing
workspace, conversation mismatch, create itinerary next-version assignment,
accept supersession, archive conflicts, decision operation evidence,
replacement supersession, invalid lifecycle transitions, and workspace-scoped
list methods.

- [x] **Step 2: Run RED**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_planner_service.py -q
```

Expected: FAIL because service code does not exist.

- [x] **Step 3: Implement service**

Keep validation and lifecycle decisions in `PlannerService`. Routes and SQLite
serialization helpers must not decide business transitions.

- [x] **Step 4: Run GREEN**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_planner_service.py -q
```

Expected: PASS.

- [x] **Step 5: Review checkpoint**

Review: every successful state-changing service method writes one operation row,
invalid requests write no operation rows, and lifecycle transitions match the
spec tables.

Expected: service behavior is explicit, reversible, and workspace-scoped.

## Task 5: Planner API Routes

**Files:**
- Create: `backend/app/schemas/planner.py`
- Create: `backend/app/api/planner.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_planner_api.py`
- Create: `backend/tests/integration/test_chat_planner_isolation.py`

**Interfaces:**
- Consumes: `PlannerService`.
- Produces: R7 planner API routes under `/api/v1/workspaces/{workspace_id}/planner`.

- [x] **Step 1: Write failing API tests**

Tests must cover create/list/get itinerary routes, accept supersession, archive,
create/list/update decision routes, replacement decision supersession, operation
listing, invalid body `422`, missing workspace `404`, cross-workspace `404`, and
bound chat calls creating no planner rows.

- [x] **Step 2: Run RED**

Run:

```text
./.venv/bin/python -m pytest backend/tests/integration/test_planner_api.py backend/tests/integration/test_chat_planner_isolation.py -q
```

Expected: FAIL because routes are not mounted.

- [x] **Step 3: Implement schemas**

Use Pydantic request/response models that mirror the domain contracts. Set
`extra = "forbid"` for write request models.

- [x] **Step 4: Implement routes**

Routes construct `SQLitePlannerRepository`, `SQLiteWorkspaceRepository`, and
`SQLiteConversationRepository` from `settings.APP_DB_PATH`, then call
`PlannerService`. Convert domain errors into controlled HTTP errors from the
spec.

- [x] **Step 5: Mount router**

Include planner router in `backend/app/main.py` under `settings.API_V1_STR`.

- [x] **Step 6: Run GREEN**

Run:

```text
./.venv/bin/python -m pytest backend/tests/integration/test_planner_api.py backend/tests/integration/test_chat_planner_isolation.py -q
```

Expected: PASS.

- [x] **Step 7: Review checkpoint**

Review: route handlers contain no SQL or lifecycle logic, response bodies expose
only controlled planner fields, and chat isolation test proves no implicit
planner write.

Expected: API matches the spec and stays backend-only.

## Task 6: Planner Evaluation Harness

**Files:**
- Create: `backend/planner/evaluation/__init__.py`
- Create: `backend/planner/evaluation/models.py`
- Create: `backend/planner/evaluation/runner.py`
- Create: `backend/planner/evaluation/cli.py`
- Create: `backend/tests/unit/test_planner_evaluation_runner.py`
- Create: `docs/evaluation/fixtures/planner/r7-state-v0.1/manifest.json`
- Create: `docs/evaluation/fixtures/planner/r7-state-v0.1/examples.jsonl`
- Create: `docs/reports/planner/r7-state-v0.1.json`
- Create: `docs/reports/planner/r7-state-v0.1.md`

**Interfaces:**
- Consumes: planner service and repository.
- Produces: `run-state --suite r7-state-v0.1` command and traceable reports.

- [x] **Step 1: Write failing evaluation tests**

Tests must cover report result states, invalid fixture handling, pass/fail gate
calculation, no implicit chat write gate, and report serialization.

- [x] **Step 2: Run RED**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_planner_evaluation_runner.py -q
```

Expected: FAIL because planner evaluation code does not exist.

- [x] **Step 3: Create fixtures**

Create at least 15 synthetic examples across `itinerary_versioning`,
`decision_lifecycle`, `rejected_option_preservation`,
`cross_workspace_isolation`, and `operation_traceability`.

- [x] **Step 4: Implement runner and models**

The runner uses temporary SQLite databases and does not call model providers,
RAG retrieval, Chroma, memory retrieval, or external APIs.

- [x] **Step 5: Implement CLI**

Expose:

```text
./.venv/bin/python -m backend.planner.evaluation.cli run-state --suite r7-state-v0.1
```

- [x] **Step 6: Run GREEN**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_planner_evaluation_runner.py -q
./.venv/bin/python -m backend.planner.evaluation.cli run-state --suite r7-state-v0.1
```

Expected: tests pass and report files are written under `docs/reports/planner/`.

- [x] **Step 7: Review checkpoint**

Review: fixture slices, gate calculations, result-state mapping, report content,
and absence of provider/RAG/memory calls.

Expected: report is deterministic, local, and internally consistent.

## Task 7: Documentation and Boundary Verification

**Files:**
- Modify: `ARCHITECTURE.md`
- Modify: `DEVELOPMENT.md`
- Modify: `docs/architecture/current-state.md`
- Modify: `docs/architecture/data-model.md`
- Modify: `docs/roadmap/master-roadmap.md`
- Modify: `docs/plans/2026-09-05-trip-planner-state-implementation.md`
- Modify: `docs/plans/README.md`

**Interfaces:**
- Consumes: implemented planner API, service, repository, and evaluation report.
- Produces: synchronized current-state and roadmap docs.

- [x] **Step 1: Update current-state architecture docs**

Document `backend/planner/`, planner routes, local SQLite schema module, and the
explicit no-implicit-chat-write boundary.

- [x] **Step 2: Update data model**

Mark `ItineraryVersion` and `TripDecision` as implemented R7 records and add
`PlannerOperation` as a new implemented R7 entity.

- [x] **Step 3: Update development guide**

Add local planner API and evaluation commands. State that R7 is backend-only and
local-development only.

- [x] **Step 4: Update roadmap evidence**

Keep R7 as `In progress` until owner review accepts the implementation change
set. Do not mark `Accepted in working tree` or `Delivered` early.

- [x] **Step 5: Run doc and boundary checks**

Run:

```text
grep -R --include='*.py' -n "from backend.planner\\|import backend.planner" backend/rag backend/memory backend/orchestration
grep -R --include='*.py' -n "from backend.rag\\|import backend.rag\\|from backend.memory\\|import backend.memory\\|from backend.orchestration\\|import backend.orchestration" backend/planner
grep -R --include='*.py' -n "chromadb" backend/planner
git diff --check
```

Expected: each `grep` command exits `1` with no output; `git diff --check`
exits `0`.

- [x] **Step 6: Review checkpoint**

Review: docs describe implemented behavior only, roadmap state is not advanced
past actual review state, and boundary checks are import-specific and ignore
`__pycache__` by using `--include='*.py'`.

Expected: docs and boundaries are ready for package verification.

## Task 8: Package Verification and Handoff

**Files:**
- Modify: `docs/plans/2026-09-05-trip-planner-state-implementation.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/roadmap/master-roadmap.md`

**Interfaces:**
- Consumes: all R7 implementation tasks.
- Produces: READY_FOR_OWNER packet and final local state.

- [x] **Step 1: Run full backend tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests
```

Expected: PASS, or disclose the exact blocked dependency if a known non-R7
external path blocks full execution.

- [x] **Step 2: Run compileall**

Run:

```text
./.venv/bin/python -m compileall backend
```

Expected: exit `0`.

- [x] **Step 3: Run R7 evaluation**

Run:

```text
./.venv/bin/python -m backend.planner.evaluation.cli run-state --suite r7-state-v0.1
```

Expected: `result_state=PASS`.

- [x] **Step 4: Run import-boundary checks**

Run:

```text
grep -R --include='*.py' -n "from backend.planner\\|import backend.planner" backend/rag backend/memory backend/orchestration
grep -R --include='*.py' -n "from backend.rag\\|import backend.rag\\|from backend.memory\\|import backend.memory\\|from backend.orchestration\\|import backend.orchestration" backend/planner
grep -R --include='*.py' -n "chromadb" backend/planner
```

Expected: each command exits `1` with no output.

- [x] **Step 5: Run final Git checks**

Run:

```text
git diff --check
git status --short --untracked-files=all
```

Expected: diff check clean; status contains only intentional R7 files.

- [x] **Step 6: Mark implementation ready for owner review**

Update this plan with verification evidence. Leave plan status `In Progress`
until repository-owner review accepts the change set.

- [x] **Step 7: Review checkpoint**

Review: full change set, verification evidence, report artifacts, and remaining
delivery gate.

Expected: every task output is present, every required check has fresh evidence,
and no Git delivery was performed.

- [x] **Step 8: Return READY_FOR_OWNER packet**

Report changed files, test/evaluation evidence, limitations, import-boundary
evidence, final status, and the remaining Git delivery gate.

## Package Verification

Final verification must include:

```text
./.venv/bin/python -m pytest backend/tests
./.venv/bin/python -m compileall backend
./.venv/bin/python -m backend.planner.evaluation.cli run-state --suite r7-state-v0.1
grep -R --include='*.py' -n "from backend.planner\\|import backend.planner" backend/rag backend/memory backend/orchestration
grep -R --include='*.py' -n "from backend.rag\\|import backend.rag\\|from backend.memory\\|import backend.memory\\|from backend.orchestration\\|import backend.orchestration" backend/planner
grep -R --include='*.py' -n "chromadb" backend/planner
git diff --check
git status --short --untracked-files=all
```

Expected evidence:

1. backend tests pass or non-R7 external blockage is disclosed with focused R7
   tests passing;
2. compileall exits `0`;
3. planner evaluation reports `PASS`;
4. import-boundary checks exit `1` with no output;
5. diff check is clean;
6. final status contains only intentional R7 files.

## Rollback

Rollback removes R7 planner routes, schemas, service, repository, evaluation
commands, fixtures, reports, and documentation references. Existing local
planner rows in a developer SQLite file may remain inert; R7 defines no
production migration, no destructive cleanup, and no history rewrite.

## Completion Record

| Field | Value |
| --- | --- |
| Approval | ADR 0008 accepted, R7 spec v0.2 approved, and plan v0.2 approved by repository owner on 2026-09-05 |
| Execution | Tasks 1-8 done in worktree `r7-planner` (base `3a53dfa`): contracts, repository, service, API routes, evaluation harness, docs, boundary checks, package verification |
| Verification | `pytest backend/tests`: 985 passed + 1 known non-R7 failure (`test_chunker.py::test_loader_real_dataset` needs gitignored `data/processed/vietnam_travel_raw.jsonl` absent from fresh worktrees); `compileall` exit 0; `run-state --suite r7-state-v0.1` result `PASS` over 16 examples with 6/6 gates; import-boundary greps exit 1 with no output; `git diff --check` clean. Review-fix round: operation rows now commit in the same repository transaction as their state change (atomicity tests included); version allocation uses `BEGIN IMMEDIATE`; itinerary creates take `ItineraryVersionDraft` |
| Owner review | Repository owner accepted the R7 change set on 2026-09-05 after the atomicity review round |
| Git delivery | Pending repository-owner action; no push, PR, merge, or release performed |

## Approval Record

| Version | Decision owner | Date | Notes |
| --- | --- | --- | --- |
| 0.1 | Repository owner | 2026-09-05 | Drafted for R7 review. External review found missing plan-template sections, no task review checkpoints, broad boundary grep, lifecycle ambiguity, and version/dependency inconsistencies |
| 0.2 | Repository owner | 2026-09-05 | Approved after review fixes. Adds required review checkpoints, package verification, rollback, completion record, file responsibility dependencies, import-specific boundary checks, Python baseline clarification, and v0.2 spec alignment. Approval authorizes implementation in an isolated worktree only, not Git delivery |
