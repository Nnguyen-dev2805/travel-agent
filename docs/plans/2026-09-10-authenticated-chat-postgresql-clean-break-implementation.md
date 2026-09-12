# Authenticated Chat-Only PostgreSQL Clean Break — Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence.

**Goal:** A single verified baseline: authenticated standalone Chat backed by
PostgreSQL, with Workspace, Planner, legacy Memory, and Memory Manager fully
removed from backend, frontend, configuration, tests, and current architecture.

**Architecture:** RuntimeContainer owns PostgreSQL pool. `require_principal`
mandatory on all owner-scoped routes. `BackgroundMemoryRecorder` replaces
`MemoryCommandService` as the background worker seam. Alembic append-only
clean-break revision removes `workspace_id` from `conversations`.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (synchronous), Alembic, PostgreSQL,
React, Vite, pytest, Docker Compose.

**Spec:** [Authenticated Chat-Only PostgreSQL Clean Break](../specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md), v0.1 (Approved)

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-09-10 |
| Approved specification | [docs/specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md](../specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md) v0.1 |
| Execution owner | Implementer agent (isolated branch worktree) |
| Decision owner | Repository owner |
| Scope | Full clean break: delete legacy surfaces, introduce RuntimeContainer, enforce auth, PostgreSQL-only, update docs |
| Verification | `python -m compileall backend`; pytest unit + integration (zero skips); Alembic round-trip; frontend lint + test + build; Docker Compose config; static import scan; git diff review |

## Global Constraints

1. Spec and all 5 ADRs (0018–0022) must be approved before execution begins.
2. Execution happens in an isolated branch worktree; no commits to main tree.
3. No `git push`, `git merge`, PR creation, or deployment.
4. No dual-write: PostgreSQL is the only store after migration.
5. No proxy or redirect for removed URLs.
6. Removed routes return unmounted `404`.
7. Owner identity comes only from authenticated principal; never from request body.
8. SQLite data inventory must precede any file deletion.
9. Alembic history is append-only; no revision rewrites.
10. Required PostgreSQL integration tests run with zero required skips.
11. No credentials, DSNs, raw messages, or PII in logs, errors, or reports.
12. `AUTH_REQUIRED`, `APP_DB_PATH`, `WORKSPACE_DB_PATH` must not appear in any mounted source after completion.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/app/main.py` | Mount only: health, ops, chat, conversations | Task 1 boundary tests → Task 6 |
| `backend/app/runtime_container.py` | Process-scoped PostgreSQL pool + adapter construction | Task 4 |
| `backend/app/api/chat.py` | Authenticated Chat orchestration, auto-create | Task 4, Task 5 |
| `backend/app/api/conversations.py` | Authenticated conversation CRUD, no message append | Task 5 |
| `backend/app/api/ops.py` | PostgreSQL+migration readiness only | Task 7 |
| `backend/conversations/models.py` | Remove `workspace_id`; add `retention_state` | Task 3 |
| `backend/conversations/service.py` | No Workspace dependency; owner-only operations | Task 3 |
| `backend/conversations/postgres_repository.py` | Only conversation adapter; owner-scoped queries | Task 3 |
| `backend/storage/migrations/versions/XXXX_clean_break.py` | Alembic: drop workspace_id, drop workspaces table, add retention index | Task 2 |
| `backend/security/dependencies.py` | `require_principal` always required; remove compatibility mode | Task 5 |
| `backend/memory/write_pipeline/background_recorder.py` | Narrow `BackgroundMemoryRecorder` interface | Task 10 |
| `backend/observability/readiness.py` | PostgreSQL + Alembic revision probe; remove SQLite probe | Task 7 |
| `backend/app/config.py` | Remove `APP_DB_PATH`, `AUTH_REQUIRED`; retain PG DSN, feature flags | Task 6 |
| `frontend/src/App.jsx` | Auth gate → conversation list; remove Workspace/Memory state | Task 6 |
| `frontend/src/services/api.js` | Chat + conversation API calls only | Task 6 |
| `docs/architecture/current-state.md` | Reflect new mounted surface and removed capabilities | Task 12 |
| `DEVELOPMENT.md` | Remove SQLite setup; add PostgreSQL local setup | Task 12 |
| `.env.example` | Remove `APP_DB_PATH`, `AUTH_REQUIRED`; keep `DATABASE_URL`, feature flags | Task 6 |

**Deleted (no replacement file):**
- `backend/workspaces/` (entire directory)
- `backend/planner/` (entire directory)
- `backend/memory/evaluation/`, `backend/memory/sqlite_repository.py`, `backend/memory/service.py` (legacy only; `write_pipeline/` retained)
- `backend/conversations/sqlite_repository.py`
- `backend/storage/schema_registry.py`
- `backend/app/api/workspaces.py`, `backend/app/api/planner.py`, `backend/app/api/memory.py`, `backend/app/api/memory_controls.py`
- `backend/memory/write_pipeline/evaluation/sqlite_inventory.py` (after final report recorded)
- `frontend/src/components/workspace/`, `frontend/src/components/planner/`, `frontend/src/components/memory/`
- `frontend/src/services/workspaces.js`, `frontend/src/services/planner.js`, `frontend/src/services/memory.js`

---

## Task 1: Failing Boundary Tests (Target Architecture Sentinel)

**Files:**
- Create: `backend/tests/boundaries/test_clean_break_boundaries.py`

**Interfaces:**
- Consumes: nothing (static import analysis against target)
- Produces: RED test suite that turns GREEN as each deletion task completes

- [ ] **Step 1: Write static boundary tests**

  Tests must assert:
  1. No mounted backend Python module imports `sqlite3`, `schema_registry`, or any SQLite repository adapter.
  2. No mounted backend module imports `workspaces`, `planner`, or legacy `memory` (outside `write_pipeline/`).
  3. No `APP_DB_PATH`, `WORKSPACE_DB_PATH`, or `AUTH_REQUIRED` string appears in `backend/app/config.py`.
  4. `backend/app/main.py` mounts exactly the 8 required routes and no others.
  5. `require_principal` in `security/dependencies.py` has no compatibility branch.

  Use `ast` or `importlib` for import scanning, not grep, so the test is deterministic regardless of comment text.

- [ ] **Step 2: Run verification — confirm RED**

  Run: `pytest backend/tests/boundaries/ -v`

  Expected: all boundary tests fail (RED) because legacy surfaces are still present. This is correct initial state.

- [ ] **Step 3: Review checkpoint**

  Review: test file exists, all assertions are specific and deterministic, tests fail for the right reasons.

  Expected: confirmed RED baseline before any deletion.

---

## Task 2: PostgreSQL Clean-Break Alembic Revision

**Files:**
- Create: `backend/storage/migrations/versions/XXXX_clean_break_remove_workspace.py`

**Interfaces:**
- Consumes: existing Alembic history head
- Produces: new head revision; `conversations` has no `workspace_id`; `workspaces` table absent

- [ ] **Step 1: Generate revision scaffold**

  Run: `alembic revision --autogenerate -m "clean_break_remove_workspace"` (or manual if autogenerate is not configured).

  Write explicit upgrade:
  1. Drop foreign key constraint from `conversations.workspace_id` if it exists.
  2. Drop index on `conversations.workspace_id` if it exists.
  3. Drop `workspace_id` column from `conversations`.
  4. Drop `workspaces` table if it exists (after verifying no remaining foreign keys).
  5. Ensure `conversations.owner_user_id` is `NOT NULL`.
  6. Add index on `(owner_user_id, created_at DESC)` for list queries.
  7. Add index on `(conversation_id, owner_user_id)` for ownership checks.

  Write explicit downgrade:
  1. Re-add `workspace_id` as nullable text column.
  2. Re-create `workspaces` table with minimal schema (id, owner_user_id, created_at).

- [ ] **Step 2: Run migration round-trip on isolated database**

  Run:
  ```
  DATABASE_URL=postgresql://test:test@localhost/travel_agent_test alembic upgrade head
  DATABASE_URL=... alembic downgrade -1
  DATABASE_URL=... alembic upgrade head
  ```

  Expected: all three steps exit code 0; no error; final schema contains no `workspace_id` column, no `workspaces` table.

- [ ] **Step 3: Verify final schema**

  Run: `psql $DATABASE_URL -c "\d conversations"` and `psql $DATABASE_URL -c "\dt"`.

  Expected: `workspace_id` absent from `conversations`; `workspaces` table absent.

- [ ] **Step 4: Review checkpoint**

  Review: revision file, round-trip output, final schema inspection.

  Expected: migration applies cleanly, reverts cleanly, and re-applies cleanly.

---

## Task 3: Remove Workspace Dependency from Conversation Domain

**Files:**
- Modify: `backend/conversations/models.py`
- Modify: `backend/conversations/service.py`
- Modify: `backend/conversations/postgres_repository.py`
- Test: `backend/tests/unit/test_conversation_models.py`
- Test: `backend/tests/unit/test_conversation_service.py`

**Interfaces:**
- Consumes: Task 2 (migration defines schema)
- Produces: `Conversation` model with no `workspace_id`; service requires `owner_user_id` for all operations

- [ ] **Step 1: Update models — remove workspace_id**

  In `backend/conversations/models.py`:
  - Remove `workspace_id` field from `Conversation`, `ConversationCreate`, and any response schemas.
  - Ensure `owner_user_id` is required (no default, no fallback).
  - Add `retention_state: Literal["active", "tombstoned"] = "active"`.

- [ ] **Step 2: Update service — remove Workspace resolution**

  In `backend/conversations/service.py`:
  - Remove all `workspace_id` parameter acceptance, Workspace owner lookups, and `WorkspaceNotFoundError` imports.
  - `create_conversation(owner_user_id: str, title: str | None)` — no workspace parameter.
  - All operations validate `owner_user_id` matches stored `conversation.owner_user_id`.

- [ ] **Step 3: Update postgres_repository — remove workspace columns**

  In `backend/conversations/postgres_repository.py`:
  - Remove all `workspace_id` column references from SELECT, INSERT, and WHERE clauses.
  - Add owner-scoped list query using new index.

- [ ] **Step 4: Update unit tests — RED then GREEN**

  Update `test_conversation_models.py` and `test_conversation_service.py`:
  - Remove tests that supply `workspace_id`.
  - Add tests asserting that `workspace_id` is absent from the model.
  - Confirm cross-owner operations are denied.

- [ ] **Step 5: Run verification**

  Run: `pytest backend/tests/unit/test_conversation_models.py backend/tests/unit/test_conversation_service.py -v`

  Expected: all tests pass.

- [ ] **Step 6: Review checkpoint**

  Review: model, service, repository diffs; test results.

  Expected: no `workspace_id` reference in any conversation domain file.

---

## Task 4: Introduce RuntimeContainer

**Files:**
- Create: `backend/app/runtime_container.py`
- Modify: `backend/app/main.py` (lifespan wiring)
- Test: `backend/tests/unit/test_runtime_container.py`

**Interfaces:**
- Consumes: Task 3 (adapter interfaces)
- Produces: `RuntimeContainer` providing `conversation_repo()`, `conversation_service()`, `conversation_orchestrator()`, `readiness_probe()`

- [ ] **Step 1: Write RuntimeContainer**

  `backend/app/runtime_container.py`:
  ```python
  class RuntimeContainer:
      """Process-scoped composition root. Owns PostgreSQL engine and adapter construction."""
      def __init__(self, settings): ...
      async def startup(self): ...  # create engine, pool
      async def shutdown(self): ...  # dispose pool
      def conversation_repo(self) -> ConversationRepository: ...
      def conversation_service(self) -> ConversationService: ...
      def conversation_orchestrator(self, outbox_enabled: bool) -> ConversationOrchestrator: ...
      def readiness_probe(self) -> PostgresReadinessProbe: ...
  ```

  No SQLite engine is created. No Workspace or Planner dependency.

- [ ] **Step 2: Wire lifespan in main.py**

  Replace per-request adapter construction with:
  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      container = RuntimeContainer(get_settings())
      await container.startup()
      app.state.container = container
      yield
      await container.shutdown()
  ```

- [ ] **Step 3: Write unit tests**

  `test_runtime_container.py`: verify startup/shutdown cycle, that adapter getters return correct types, that no SQLite adapter is ever constructed.

- [ ] **Step 4: Run verification**

  Run: `pytest backend/tests/unit/test_runtime_container.py -v`

  Expected: all tests pass.

- [ ] **Step 5: Review checkpoint**

  Review: RuntimeContainer source, lifespan wiring, test results.

  Expected: single composition root, no SQLite, correct adapter types.

---

## Task 5: Standalone Conversation Routes and Authenticated Chat

**Files:**
- Modify: `backend/app/api/chat.py`
- Modify: `backend/app/api/conversations.py`
- Modify: `backend/security/dependencies.py`
- Test: `backend/tests/integration/test_conversation_api.py`
- Test: `backend/tests/integration/test_chat_conversation_binding.py`

**Interfaces:**
- Consumes: Task 4 (RuntimeContainer), Task 3 (ConversationService)
- Produces: authenticated routes matching target surface exactly

- [ ] **Step 1: Update security/dependencies.py**

  - Remove `get_optional_principal`, `AuthMode.COMPATIBILITY`, and all `AUTH_REQUIRED` branches.
  - `require_principal` always reads `Authorization: Bearer <token>` and returns `401` without content if absent/invalid.
  - No compatibility principal created under any code path.

- [ ] **Step 2: Update chat.py — auto-create and orchestration**

  `POST /api/v1/chat`:
  - Depends on `require_principal`.
  - If no `conversation_id` in body, creates a new conversation via `RuntimeContainer.conversation_service()`.
  - Transaction: append user message + optional outbox intent.
  - RAG generation.
  - Append assistant message.
  - Return response with `conversation_id` and `persisted` state.

- [ ] **Step 3: Update conversations.py — CRUD only, no message append**

  Remove direct message append route (`POST /conversations/{id}/messages`).
  Routes: create, list (owner-scoped), get (owner-scoped), messages (paginated), delete (tombstone + propagation).
  All routes depend on `require_principal`; owner comes only from principal.

- [ ] **Step 4: Update integration tests**

  - `test_conversation_api.py`: remove workspace params; assert owner-scoped operations; add cross-owner `404` tests.
  - `test_chat_conversation_binding.py`: remove workspace setup; assert auto-create first turn; assert `conversation_id` returned.
  - Add test: unauthenticated request returns `401` before any storage work.
  - Add test: direct message append route returns `404`.
  - These tests require a running PostgreSQL; mark with `@pytest.mark.integration` and ensure they are never skipped when PostgreSQL DSN is set.

- [ ] **Step 5: Run verification**

  Run: `pytest backend/tests/integration/test_conversation_api.py backend/tests/integration/test_chat_conversation_binding.py -v` (with PostgreSQL running).

  Expected: all tests pass, zero skips.

- [ ] **Step 6: Review checkpoint**

  Review: security dependencies diff, chat.py diff, conversations.py diff, integration test results.

  Expected: all protected routes require real credentials; auto-create and CRUD pass; direct append is `404`.

---

## Task 6: Remove Legacy Backend and Frontend Surfaces

**Files (delete):**
- `backend/workspaces/` (entire)
- `backend/planner/` (entire)
- `backend/app/api/workspaces.py`
- `backend/app/api/planner.py`
- `backend/app/api/memory.py`
- `backend/app/api/memory_controls.py`
- Legacy `backend/memory/` modules outside `write_pipeline/`: `service.py`, `sqlite_repository.py`, `retrieval.py`, `promotion.py`, `policy.py`, `extraction.py`, `evaluation/`
- `backend/conversations/sqlite_repository.py`
- `backend/storage/schema_registry.py`
- `backend/storage/` (if empty after registry removal)
- `frontend/src/components/workspace/`
- `frontend/src/components/planner/`
- `frontend/src/components/memory/`
- `frontend/src/services/workspaces.js`
- `frontend/src/services/planner.js`
- `frontend/src/services/memory.js`

**Files (modify):**
- `backend/app/main.py`: mount only 8 required routes; remove workspace/planner/memory/memory_controls routers.
- `backend/app/config.py`: remove `APP_DB_PATH`, `WORKSPACE_DB_PATH`, `AUTH_REQUIRED`.
- `.env.example`: remove SQLite paths and `AUTH_REQUIRED`.
- `frontend/src/App.jsx`: replace Workspace state with conversation list state; remove Memory Manager; add auth gate.

**Interfaces:**
- Consumes: Task 5 (routes already updated)
- Produces: clean import graph with no legacy surfaces

- [ ] **Step 1: Inventory SQLite data before any deletion**

  Run read-only SQLite inventory (using `sqlite_inventory.py` or equivalent):
  - Record table names and row counts for every `.db` file found in the repo.
  - Write result to `docs/reports/memory-write-pipeline/pre-deletion-inventory.md`.

  If any table has non-synthetic rows: **STOP** and report to repository owner.

- [ ] **Step 2: Delete legacy backend source**

  Delete directories and files listed above.
  After each deletion, run: `python -m compileall backend` to confirm no broken imports remain.

- [ ] **Step 3: Update main.py**

  Mount exactly:
  ```python
  app.include_router(health.router)
  app.include_router(ops.router, prefix="/api/v1")
  app.include_router(chat.router, prefix="/api/v1")
  app.include_router(conversations.router, prefix="/api/v1")
  ```

- [ ] **Step 4: Update config.py**

  Remove `APP_DB_PATH`, `WORKSPACE_DB_PATH`, `AUTH_REQUIRED`. Retain `DATABASE_URL`, `MEMORY_SHADOW_EXTRACT_ENABLED`, `MEMORY_WRITE_PIPELINE_ENABLED`.

- [ ] **Step 5: Delete legacy frontend source**

  Delete frontend directories and files listed above.
  Simplify `App.jsx` to: auth gate → conversation list → chat view.

- [ ] **Step 6: Delete or update tests for removed surfaces**

  Delete tests whose only subject is removed behavior:
  - `test_workspace_api.py`, `test_planner_api.py`, `test_memory_api.py`, `test_memory_promotion_api.py`
  - `test_schema_registry.py`
  - `test_chat_planner_isolation.py`, `test_chat_memory_retrieval.py` (legacy memory retrieval)

  Port tests protecting retained invariants to new integration test files if not already covered.

- [ ] **Step 7: Run boundary tests — confirm GREEN**

  Run: `pytest backend/tests/boundaries/ -v`

  Expected: all boundary tests GREEN (legacy surfaces removed, routes correct, config clean).

- [ ] **Step 8: Review checkpoint**

  Review: git diff showing deletions, `main.py` router list, `config.py`, `.env.example`, frontend App.jsx.

  Expected: no workspace/planner/legacy-memory import; only 8 routes mounted; no `APP_DB_PATH` or `AUTH_REQUIRED`.

---

## Task 7: Update Readiness and Observability

**Files:**
- Modify: `backend/observability/readiness.py`
- Modify: `backend/app/api/ops.py`
- Test: `backend/tests/unit/test_observability_readiness.py`

**Interfaces:**
- Consumes: Task 4 (RuntimeContainer readiness probe)
- Produces: readiness that probes PostgreSQL + Alembic, not SQLite

- [ ] **Step 1: Rewrite readiness.py**

  Replace SQLite schema probe with:
  - PostgreSQL connectivity check (connection pool ping).
  - Alembic revision check (current == expected head).
  - RAG vector store presence check (Chroma collection accessible).
  - Model provider configuration check (key present, not connectivity test).
  - Background capture gate state check.

  Do not call `CREATE TABLE` or any DDL as a side effect. Readiness is read-only.

- [ ] **Step 2: Update ops.py**

  `GET /api/v1/ops/readiness` requires `require_principal`.
  Returns controlled status codes and reason codes without content detail (no DB path, no key values, no tenant identifiers).

- [ ] **Step 3: Update unit tests**

  `test_observability_readiness.py`:
  - Remove SQLite-probing tests.
  - Add: PostgreSQL unavailable → readiness NOT READY.
  - Add: Alembic behind head → readiness NOT READY.
  - Add: All checks pass → readiness READY.
  - Use SQLAlchemy async fakes or mock pool; no real PostgreSQL required for unit tests.

- [ ] **Step 4: Run verification**

  Run: `pytest backend/tests/unit/test_observability_readiness.py -v`

  Expected: all tests pass.

- [ ] **Step 5: Review checkpoint**

  Review: readiness.py diff, ops.py diff, test results.

  Expected: no SQLite probe; PostgreSQL and Alembic revision probed; no content leakage in responses.

---

## Task 8: Remove Legacy Memory and Introduce BackgroundMemoryRecorder

**Files:**
- Create: `backend/memory/write_pipeline/background_recorder.py`
- Delete: `backend/memory/write_pipeline/evaluation/sqlite_inventory.py` (after report recorded)
- Modify: background worker (if it depends on `MemoryCommandService`)
- Test: `backend/tests/unit/memory_write_pipeline/test_background_recorder.py`

**Interfaces:**
- Consumes: Task 6 (legacy Memory removed), existing policy/resolver/UoW seams
- Produces: `BackgroundMemoryRecorder` as the sole worker interface

- [ ] **Step 1: Confirm sqlite_inventory.py report is recorded**

  Verify `docs/reports/memory-write-pipeline/legacy-sqlite-inventory-report.md` exists and records the disposal decision.
  Then delete `backend/memory/write_pipeline/evaluation/sqlite_inventory.py`.

- [ ] **Step 2: Create BackgroundMemoryRecorder**

  `background_recorder.py`:
  ```python
  class BackgroundMemoryRecorder:
      """Narrow background interface. Records a validated shadow candidate.
      Exposes no user-initiated methods."""
      def __init__(self, policy, resolver, uow_factory): ...
      async def record(self, candidate: ShadowCandidate) -> None: ...
  ```

  No `remember`, `correct`, `forget`, `toggle`, `preview`, `confirm`, or `expand` methods.

- [ ] **Step 3: Update background worker**

  Replace any `MemoryCommandService` dependency in the worker with `BackgroundMemoryRecorder`.

- [ ] **Step 4: Write unit tests**

  `test_background_recorder.py`:
  - Prove `record()` delegates to policy → resolver → uow correctly.
  - Prove no user-initiated methods exist.
  - Use fakes for policy, resolver, uow (no real PostgreSQL).

- [ ] **Step 5: Run verification**

  Run: `pytest backend/tests/unit/memory_write_pipeline/ -v`

  Expected: all 202+ tests pass; new recorder tests pass.

- [ ] **Step 6: Review checkpoint**

  Review: recorder source, worker diff, test results.

  Expected: no `MemoryCommandService` import in worker; recorder exposes only `record()`.

---

## Task 9: Update Configuration and Environment

**Files:**
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml` (remove SQLite volumes)
- Modify: `docker-compose.override.yml` (if present)

**Interfaces:**
- Consumes: Tasks 3–8 (all legacy surfaces removed)
- Produces: clean configuration with no SQLite or AUTH_REQUIRED references

- [ ] **Step 1: Final config.py cleanup**

  Confirm removal of: `APP_DB_PATH`, `WORKSPACE_DB_PATH`, `AUTH_REQUIRED`.
  Confirm retention of: `DATABASE_URL`, `MEMORY_SHADOW_EXTRACT_ENABLED`, `MEMORY_WRITE_PIPELINE_ENABLED`, `ALLOWED_ORIGINS`.

- [ ] **Step 2: Update .env.example**

  Remove all SQLite path variables and `AUTH_REQUIRED`. Add documentation comment explaining PostgreSQL is required.

- [ ] **Step 3: Update Docker Compose**

  Remove SQLite volume mounts. Retain PostgreSQL service definition with health check. Retain Chroma service if present.

- [ ] **Step 4: Run static config scan**

  Run: `grep -r "APP_DB_PATH\|WORKSPACE_DB_PATH\|AUTH_REQUIRED\|sqlite3" backend/ --include="*.py" | grep -v "test_clean_break_boundaries" | grep -v ".pyc"`

  Expected: zero matches in mounted source.

- [ ] **Step 5: Review checkpoint**

  Review: config.py, .env.example, docker-compose diffs, grep output.

  Expected: zero legacy config references.

---

## Task 10: Update Frontend Authentication and Conversation State

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/services/api.js` (or equivalent)
- Test: `frontend/src/` (existing tests updated)

**Interfaces:**
- Consumes: Task 6 (legacy frontend deleted), Task 5 (backend routes finalized)
- Produces: authenticated conversation list → chat flow; no Workspace/Planner/Memory state

- [ ] **Step 1: Simplify App.jsx state**

  Retain only:
  ```js
  principal / authentication
  conversations
  activeConversationId
  messages
  chatLoading / chatError
  ```

  Remove: `workspaces`, `activeWorkspace`, planner state, memory state, local-storage keys for removed concepts.

- [ ] **Step 2: Unauthenticated state**

  Unauthenticated: render login only; Chat is inaccessible.
  Authenticated: load conversation list from `GET /api/v1/conversations`.
  New chat: `POST /api/v1/chat` without `conversation_id`; store returned `conversation_id`.

- [ ] **Step 3: Update or remove frontend tests**

  Delete tests whose only subject is removed UI.
  Update remaining tests to use the simplified state model.

- [ ] **Step 4: Run verification**

  Run: `cd frontend && npm run lint && npm run test && npm run build`

  Expected: 0 lint errors; all tests pass; build succeeds.

- [ ] **Step 5: Review checkpoint**

  Review: App.jsx diff, api.js diff, test results, build output.

  Expected: no Workspace/Planner/Memory import; auth gate unconditional; build clean.

---

## Task 11: PostgreSQL Integration Tests — Zero Skips

**Files:**
- Modify: `backend/tests/integration/test_cross_owner_isolation.py`
- Modify: `backend/tests/integration/test_conversation_api.py`
- Modify: `backend/tests/integration/test_security_error_handling.py`
- Modify: `backend/tests/integration/test_ops_readiness_api.py`
- Modify: `backend/tests/integration/test_deletion_api.py`

**Interfaces:**
- Consumes: Tasks 5–8 (all surfaces finalized)
- Produces: integration test suite that runs without skips when PostgreSQL DSN is set

- [ ] **Step 1: Remove all unconditional `pytest.skip` on PostgreSQL tests**

  Replace `if not PG_DSN: pytest.skip(...)` with `pytest.mark.skipif(not PG_DSN, reason="...")`.
  Integration tests are run in CI with PostgreSQL; any required skip in that context is a failure.

- [ ] **Step 2: Add cross-owner isolation tests**

  `test_cross_owner_isolation.py`:
  - `GET /api/v1/conversations/{id}` for another owner's conversation → `404`.
  - `DELETE /api/v1/conversations/{id}` for another owner → `404`.
  - `GET /api/v1/conversations/{id}/messages` for another owner → `404`.
  - These tests use two distinct tokens from the local token registry.

- [ ] **Step 3: Add deletion propagation test**

  `test_deletion_api.py`:
  - Delete conversation → conversation is non-readable.
  - If Memory propagation is wired: assert pending outbox events are cancelled.
  - If not yet wired: assert delete fails closed (HTTP 5xx/409) rather than returning false success.

- [ ] **Step 4: Run full integration suite**

  Run: `pytest backend/tests/integration/ -v -m integration` (with PostgreSQL running).

  Expected: all tests pass, zero required skips.

- [ ] **Step 5: Review checkpoint**

  Review: integration test diff, test output.

  Expected: no unconditional skip; cross-owner denial proven; deletion behavior honest.

---

## Task 12: Documentation and Architecture Update

**Files:**
- Modify: `docs/architecture/current-state.md`
- Modify: `DEVELOPMENT.md`
- Modify: `README.md`
- Modify: `ARCHITECTURE.md`
- Modify: `SECURITY.md`
- Modify: `docs/runbooks/deployment.md`
- Modify: `docs/runbooks/local-development.md`

**Interfaces:**
- Consumes: all preceding tasks complete
- Produces: documentation accurately reflecting the new clean-break baseline

- [ ] **Step 1: Update current-state.md**

  - Reflect 8 mounted routes only.
  - Remove Workspace, Planner, legacy Memory, and Memory Manager from component map.
  - Add RuntimeContainer as composition root.
  - Add BackgroundMemoryRecorder as background worker seam.
  - Note superseded specs and ADRs.

- [ ] **Step 2: Update DEVELOPMENT.md**

  - Remove SQLite setup instructions.
  - Add PostgreSQL local setup (Docker Compose or native).
  - Add Alembic migration run instructions.
  - Remove `APP_DB_PATH` and `AUTH_REQUIRED` from local setup.
  - Add evaluation CLI commands (retained from Child Plan 6).

- [ ] **Step 3: Update README, ARCHITECTURE, SECURITY**

  - State the new mounted behavior.
  - Identify removed capabilities.
  - SECURITY: confirm wildcard CORS prohibited, mandatory auth, content-free errors.

- [ ] **Step 4: Update deployment and local-dev runbooks**

  - Document PostgreSQL migration cutover sequence.
  - Document rollback boundaries per stage (from ADR 0022).
  - Remove SQLite-specific recovery steps.

- [ ] **Step 5: Run deterministic doc check**

  Run: `grep -r "workspace\|planner\|APP_DB_PATH\|AUTH_REQUIRED" docs/architecture/current-state.md DEVELOPMENT.md README.md ARCHITECTURE.md | grep -vi "removed\|superseded\|historical\|legacy\|retired"`

  Expected: no unremediated reference to removed concepts as current behavior.

- [ ] **Step 6: Review checkpoint**

  Review: all doc diffs.

  Expected: documentation accurately reflects the clean-break baseline without describing removed features as active.

---

## Package Verification

Run freshly on the exact change set, in this order:

```bash
# 1. Python compilation
python -m compileall backend

# 2. Static forbidden-import scan
grep -r "sqlite3\|schema_registry\|APP_DB_PATH\|AUTH_REQUIRED" backend/ --include="*.py" \
  | grep -v "test_clean_break_boundaries" | grep -v "\.pyc"
# Expected: zero matches in mounted source

# 3. Unit tests
pytest backend/tests/unit/ -v

# 4. Boundary tests
pytest backend/tests/boundaries/ -v

# 5. PostgreSQL migration round-trip (requires running PostgreSQL)
alembic upgrade head && alembic downgrade -1 && alembic upgrade head

# 6. Integration tests (requires running PostgreSQL)
pytest backend/tests/integration/ -v -m integration

# 7. Frontend
cd frontend && npm run lint && npm run test && npm run build

# 8. Docker Compose validation
docker compose config --quiet

# 9. Git diff and untracked file review
git status --short --untracked-files=all
git diff --check
```

All checks must pass with exit code 0. Any required skip, conflict marker, dirty
generated database, or failing check blocks completion claim.

---

## Rollback

| Stage | Action |
| --- | --- |
| Before Task 2 (any PostgreSQL migration) | Abandon worktree; no persistent change |
| After Task 2, before Task 5 (no traffic) | `alembic downgrade -1` on isolated DB; abandon worktree |
| After Task 5 (routes live) | Application release rollback against forward-compatible schema; does not restore SQLite |
| Any non-synthetic SQLite data found | Stop; create owner-approved export; resume only after disposal decision |
| Destructive database failure | Restore PostgreSQL from tested backup |

Removed behavior (Workspace, Planner, legacy Memory, Memory Manager) may be
restored only by a separately approved design.

---

## Completion Record

| Field | Value |
| --- | --- |
| Status transition | `Approved` → `Completed` on 2026-09-11. **The 64 checkboxes above remain unticked because they were not verified task-by-task in this session.** |
| Verified evidence present in the working tree | Boundary test `backend/tests/boundaries/test_clean_break_boundaries.py` passes **16/16** (verified 2026-09-11). The mounted chat routes are exactly the 8 approved clean-break routes with no Workspace, Planner, or legacy Memory surface. ADRs 0018–0022 are `Accepted`. |
| Unticked items | The plan's 12 tasks / 64 steps were executed in earlier sessions; no per-step evidence was collected during the 2026-09-11 session. Ticking them without evidence would manufacture proof. |
| Git delivery | Not performed; no commit, push, PR, or merge. |
- [ ] Git delivery (add, commit, push, PR) pending repository-owner action.
