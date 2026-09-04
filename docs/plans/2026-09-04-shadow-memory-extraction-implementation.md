# Shadow Memory Extraction Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence.

**Goal:** Build backend-only R5 shadow memory extraction that persists and
evaluates memory candidates from R4 conversations without changing answers.

**Architecture:** A new `backend/memory/` module owns candidate contracts,
policy, extraction, repository interfaces, service use cases, and a local SQLite
adapter registered in the shared application store. Conversation messages supply
provenance; workspace records supply local scope labels; RAG and RAG evaluation
remain independent. Extraction is manual or evaluation-triggered only, preserving
R4's default-deny `trace_visibility` behavior and leaving chat responses
unchanged.

**Tech Stack:** Python 3.11+ baseline, FastAPI, Pydantic, standard-library
`sqlite3`, pytest, Markdown, existing shared schema registry, existing backend
test layout.

**Spec:** [Shadow Memory Extraction Design](../specs/2026-09-04-shadow-memory-extraction-design.md), version 0.1 (Approved)

| Field | Value |
| --- | --- |
| Status | In Progress |
| Plan version | 0.1 |
| Date | 2026-09-04 |
| Approved specification | [Shadow Memory Extraction Design](../specs/2026-09-04-shadow-memory-extraction-design.md), version 0.1 (Approved 2026-09-04) |
| Governing ADRs | [ADR 0006](../adr/0006-shadow-memory-candidate-store-and-policy-boundary.md) (Accepted 2026-09-04) |
| Plan approval | Repository owner approved implementation plan version 0.1 in conversation on 2026-09-04 |
| Execution owner | Implementation worker agent in an isolated worktree |
| Decision owner | Repository owner |
| Scope | Runtime milestone R5 - memory candidate contracts, shadow extraction, policy, local persistence, inspection routes, evaluation report, tests, and docs |
| Verification | `./.venv/bin/python -m pytest backend/tests`, `./.venv/bin/python -m compileall backend`, import-boundary `grep` checks, memory report validation, `git diff --check`, `git status --short --untracked-files=all` |

## Global Constraints

1. Do not implement R5 source code until this plan, the R5 spec, and ADR 0006
   are explicitly approved by the repository owner.
2. Execute R5 on `feature/agent-memory` at `e590ca6` or a later owner-approved
   integration base that includes R4.
3. R5 is shadow-only. No memory candidate may affect RAG retrieval, context
   assembly, prompts, generated answers, citations, or evaluation of RAG runs.
4. No frontend work. Do not modify `frontend/`.
5. No chat-bound automatic extraction, authentication, authorization, account
   model, tenant isolation, production privacy claim, production database, ORM,
   migration framework, vector memory store, Chroma memory write,
   model-provider dependency, planner state, or deletion API.
6. Never log raw message content, candidate text, evidence summary,
   conversation title, or substrings of those values.
7. Tests use temporary databases and deterministic fakes. They must not require
   a model provider, embedding model, Chroma data, Docker, or network access.
8. Preserve `GET /health`, every workspace route, every conversation route, and
   both bound and unbound chat response contracts.
9. `backend/rag`, including RAG evaluation, must not import `backend.memory` or
   memory API modules.
10. Memory evaluation fixtures must be tracked under
    `docs/evaluation/fixtures/memory/`, not under Git-ignored `data/`.
11. If R5 is executed in a linked worktree, use the primary tree virtual
    environment by absolute path when `.venv` is absent, and symlink only
    `data/processed` if the full existing backend suite requires it. Never
    symlink `docs`, `.venv`, `backend`, `frontend`, `data`, `data/chromadb`, or
    `data/evaluation`; never force-add ignored `data/` paths.
12. The implementation worker must not stage, commit, push, merge, rebase, tag,
    release, delete branches, or perform destructive cleanup unless the
    repository owner asks for that exact Git action.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/memory/__init__.py` | Export stable R5 memory contracts and service entry points | Memory modules |
| `backend/memory/models.py` | Memory candidate, extraction run, vocabularies, identifiers, UTC timestamp validation, text normalization | R5 spec |
| `backend/memory/repository.py` | Repository protocol and controlled error types | Memory models |
| `backend/memory/sqlite_repository.py` | Schema version 1 tables and queries for runs and candidates | Shared schema registry, memory repository |
| `backend/memory/extraction.py` | Extractor protocol and deterministic rule-based extractor | Memory models |
| `backend/memory/policy.py` | Candidate policy and controlled reason decisions | Memory models |
| `backend/memory/service.py` | Run extraction, validate provenance, persist run/candidates, list evidence | Memory repository, conversation repository/service, workspace repository interface |
| `backend/app/schemas/memory.py` | Request/response schemas for memory routes | Pydantic, memory models |
| `backend/app/api/memory.py` | Backend-only HTTP routes and dependency construction | Memory service, schemas, SQLite adapter |
| `backend/app/main.py` | Mount the memory router | Existing app route pattern |
| `backend/memory/evaluation/__init__.py` | Export memory evaluation entry points | Memory evaluation modules |
| `backend/memory/evaluation/models.py` | Memory evaluation report value objects | Memory evaluation protocol |
| `backend/memory/evaluation/runner.py` | Deterministic memory shadow evaluation runner | Memory service/repository interfaces, tracked fixtures |
| `backend/memory/evaluation/cli.py` | Memory-specific CLI command without changing RAG commands | Memory evaluation runner |
| `backend/tests/unit/test_memory_models.py` | Model and vocabulary tests | Memory models |
| `backend/tests/unit/test_memory_policy.py` | Policy decision tests | Memory policy |
| `backend/tests/unit/test_memory_extraction.py` | Deterministic extractor tests | Memory extraction |
| `backend/tests/unit/test_sqlite_memory_repository.py` | SQLite persistence and schema tests | Memory SQLite adapter |
| `backend/tests/unit/test_memory_service.py` | Provenance, counts, and no-content-error tests | Memory service with fakes |
| `backend/tests/unit/test_memory_evaluation_runner.py` | Memory report state and hard-gate tests | Memory evaluation runner |
| `backend/tests/integration/test_memory_api.py` | API route tests with temporary app database | FastAPI app |
| `docs/evaluation/fixtures/memory/r5-shadow-v0.1/manifest.json` | Tracked fixture manifest for R5 shadow evaluation | Memory evaluation protocol |
| `docs/evaluation/fixtures/memory/r5-shadow-v0.1/examples.jsonl` | Tracked synthetic examples for R5 shadow evaluation | Memory evaluation protocol |
| `ARCHITECTURE.md` | Current-state gateway update for R5 | Implemented modules |
| `DEVELOPMENT.md` | Local R5 route/command usage and limitations | Implemented behavior |
| `docs/architecture/current-state.md` | Current-state update after R5 | Implemented modules and routes |
| `docs/architecture/data-model.md` | Mark R5 candidate fields implemented and memory records still conceptual | R5 contracts |
| `docs/roadmap/master-roadmap.md` | R5 status and evidence update | Completion evidence |
| `docs/plans/README.md` | Plan index status update | This plan |

## Task 1: Approval Gates and Baseline

**Files:**

- Read: R5 spec, ADR 0006, this plan, R4 spec, ADR 0004, ADR 0005, roadmap
- Modify: this plan, `docs/plans/README.md`, `docs/roadmap/master-roadmap.md`

**Interfaces:**

- Consumes: owner approval for R5 spec, ADR 0006, and this plan
- Produces: recorded execution base and baseline evidence

- [x] **Step 1: Confirm governance gates**

Confirm:

- R5 spec status is `Approved`.
- ADR 0006 status is `Accepted`.
- This plan status is `Approved`.
- `git rev-parse --short HEAD` is `e590ca6` or a later owner-approved base.

Stop if any gate is missing.

- [x] **Step 2: Record baseline tests**

Run: `./.venv/bin/python -m pytest backend/tests -q`

Expected: existing suite passes. Record exact count and duration in this plan.

Baseline (worktree `r5-shadow-memory` @ `d659b8d`, primary `.venv` by absolute
path, `data/processed` symlinked per Global Constraint 11): `708 passed,
1 warning in 21.18s`. Initial run showed `707 passed, 1 failed`
(`test_loader_real_dataset` missing Git-ignored dataset); resolved by the
approved `data/processed` symlink, which leaves `git status` clean.

- [x] **Step 3: Mark execution start**

Update this plan status to `In Progress`, update the plan index to
`In Progress`, and update roadmap `R5` from `Ready for handoff` to
`In progress` once implementation actually starts.

- [x] **Step 4: Review checkpoint**

Review: status output and baseline evidence.

Expected: no source file has changed before the gate and baseline are recorded.

Checkpoint: only this plan, `docs/plans/README.md`, and
`docs/roadmap/master-roadmap.md` changed (the Task 1 file scope); no
`backend/` source changed before baseline.

## Task 2: Memory Contracts

**Files:**

- Create: `backend/memory/__init__.py`
- Create: `backend/memory/models.py`
- Test: `backend/tests/unit/test_memory_models.py`

**Interfaces:**

- Produces:
  - `MemoryExtractionRun`
  - `MemorySourceMessage`
  - `MemoryCandidate`
  - `MemoryCandidateDraft`
  - `MemoryRunStatus`
  - `MemoryCandidateStatus`
  - `MemoryScope`
  - `MemoryType`
  - `SensitivityLabel`
  - `PolicyReason`
  - `MemoryExtractionTrigger`
  - `generate_memory_run_id()`
  - `generate_memory_candidate_id()`

- [x] **Step 1: Write failing model tests**

Cover identifier prefixes `mer_` and `mc_`, UTC timestamp enforcement, text
normalization, floating-point confidence range `[0.0, 1.0]`, governed enums, run
counter invariants including `invalid_count`, 500-character candidate text
limit, 240-character evidence summary limit, and rejection of blank required
identifiers.

- [x] **Step 2: Run model tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_models.py -q`

Expected: tests fail because `backend.memory.models` does not exist.

- [x] **Step 3: Implement models**

Implement frozen dataclasses and enums only. Do not import conversation,
workspace, RAG, FastAPI, or SQLite from `models.py`.

- [x] **Step 4: Run model tests for GREEN**

GREEN: `30 passed` (`backend/tests/unit/test_memory_models.py`).

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_models.py -q`

Expected: all model tests pass.

- [x] **Step 5: Review checkpoint**

Review: model vocabulary exactly matches the spec and no raw-content logging is
introduced.

Checkpoint: vocabularies match the spec tables byte-for-byte; `models.py`
imports stdlib only (static import test); no logging module imported.

## Task 3: Policy and Deterministic Extraction

**Files:**

- Create: `backend/memory/extraction.py`
- Create: `backend/memory/policy.py`
- Test: `backend/tests/unit/test_memory_extraction.py`
- Test: `backend/tests/unit/test_memory_policy.py`

**Interfaces:**

- Consumes: Task 2 models
- Produces:
  - `MemoryExtractor.extract(messages: Sequence[MemorySourceMessage]) -> tuple[MemoryCandidateDraft, ...]`
  - `RuleBasedMemoryExtractor`
  - `MemoryPolicy.evaluate(draft: MemoryCandidateDraft) -> MemoryCandidateDraft`

- [x] **Step 1: Write failing extractor tests**

Use synthetic user messages with `trace_visibility = included` that cover
durable preference, trip constraint, explicit correction, no-memory signal, and
secret-like content. Assert candidate drafts preserve `source_message_id`,
`conversation_id`, and `workspace_id`. Add a test proving an ordinary R4
chat-bound message with default `trace_visibility = excluded` produces no
accepted candidate.

- [x] **Step 2: Write failing policy tests**

Cover `supported_preference`, `supported_constraint`, `explicit_correction`,
`ambiguous`, `transient`, `wrong_scope`, `low_confidence`, `sensitive`,
`secret_like`, `unsupported`, `system_generated`, and `trace_excluded`. Do not
invent a `system_event` category vocabulary.

- [x] **Step 3: Run policy/extractor tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_extraction.py backend/tests/unit/test_memory_policy.py -q`

Expected: tests fail because modules do not exist.

- [x] **Step 4: Implement deterministic extractor and policy**

Implement a deliberately simple, deterministic extractor for governed fixture
phrases. Keep model-backed extraction out of scope.

- [x] **Step 5: Run policy/extractor tests for GREEN**

GREEN: `62 passed` (models 30 + extraction/policy 32).

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_extraction.py backend/tests/unit/test_memory_policy.py -q`

Expected: all tests pass.

- [x] **Step 6: Review checkpoint**

Review: extractor and policy are separate, and policy can reject or mark
`needs_user_action` without relying on model calls.

Checkpoint: `extraction.py` never assigns `status`/`reason` (tested);
`policy.py` is a pure function over the draft (stdlib `dataclasses` only,
no logging import); one justified Task 2 amendment — `MemoryCandidateDraft`
gained `role`/`source`/`trace_visibility` text copies because
`evaluate(draft)` must enforce `trace_excluded`/`system_generated` from the
draft alone per the approved reason vocabulary.

## Task 4: Memory Repository and SQLite Adapter

**Files:**

- Create: `backend/memory/repository.py`
- Create: `backend/memory/sqlite_repository.py`
- Test: `backend/tests/unit/test_sqlite_memory_repository.py`

**Interfaces:**

- Consumes: Task 2 models, shared schema registry
- Produces:
  - `MemoryRepository`
  - `SQLiteMemoryRepository`
  - `create_run(run: MemoryExtractionRun) -> MemoryExtractionRun`
  - `create_candidates(candidates: Sequence[MemoryCandidate]) -> tuple[MemoryCandidate, ...]`
  - `list_runs(workspace_id: str, conversation_id: str | None = None) -> tuple[MemoryExtractionRun, ...]`
  - `list_candidates(run_id: str | None = None, workspace_id: str | None = None, conversation_id: str | None = None) -> tuple[MemoryCandidate, ...]`

- [x] **Step 1: Write failing repository tests**

Cover schema registration for module `memory` version `1`, run persistence,
candidate persistence, newest-first run ordering, sequence/source ordering for
candidates, controlled duplicate errors, the declared DDL/index/unique
constraints from the spec, cross-run candidate ordering through the parent run
order, and fail-closed schema mismatch.

- [x] **Step 2: Run repository tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_memory_repository.py -q`

Expected: tests fail because repository modules do not exist.

- [x] **Step 3: Implement repository protocol and adapter**

Use only standard-library `sqlite3` in the adapter. Keep SQL and DDL out of
routes, service, policy, extraction, and orchestration modules.

- [x] **Step 4: Run repository tests for GREEN**

GREEN: `16 passed` (`backend/tests/unit/test_sqlite_memory_repository.py`).

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_memory_repository.py -q`

Expected: all repository tests pass.

- [x] **Step 5: Review checkpoint**

Review: no Chroma write, no RAG import, no message content in error strings.

Checkpoint: `sqlite3` appears only in `sqlite_repository.py` plus the shared
registry (boundary grep clean); DDL is verbatim from the spec; controlled
errors carry identifiers and column names only, verified by asserting stored
content absent from error strings.

## Task 5: Memory Service

**Files:**

- Create: `backend/memory/service.py`
- Test: `backend/tests/unit/test_memory_service.py`

**Interfaces:**

- Consumes: Task 2-4 memory contracts, conversation repository/service,
  workspace repository interface
- Produces:
  - `MemoryService.run_conversation_extraction(workspace_id: str, conversation_id: str, trigger: MemoryExtractionTrigger) -> MemoryExtractionRun`
  - `MemoryService.list_runs(workspace_id: str, conversation_id: str | None = None) -> tuple[MemoryExtractionRun, ...]`
  - `MemoryService.list_candidates(workspace_id: str, conversation_id: str | None = None, run_id: str | None = None) -> tuple[MemoryCandidate, ...]`

- [x] **Step 1: Write failing service tests**

Cover missing workspace, missing conversation, workspace/conversation mismatch,
excluded trace visibility, no eligible messages, count accuracy including
`invalid_count`, extraction failure status, and no raw content in exceptions.

- [x] **Step 2: Run service tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_service.py -q`

Expected: tests fail because `MemoryService` does not exist.

- [x] **Step 3: Implement service**

Read messages through an approved conversation boundary, map them into
`MemorySourceMessage`, validate workspace scope, run extractor and policy,
persist run and candidates, and return counts.

- [x] **Step 4: Run service tests for GREEN**

GREEN: `18 passed` (`backend/tests/unit/test_memory_service.py`).

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_service.py -q`

Expected: all service tests pass.

- [x] **Step 5: Review checkpoint**

Review: service enforces provenance before extraction and never writes accepted
candidates when provenance is invalid.

Checkpoint: every provenance failure (missing workspace/conversation,
mismatch, non-active conversation) raises before any write (tested with
empty fake stores); extractor failure persists a `failed` run with the
controlled `extraction_failed` label then raises without content; two test
bugs fixed (unknown filter is 404 per spec, mismatch needs an existing
workspace); candidate-write failure propagates the controlled storage error
because the approved repository interface has no run-update operation —
recorded here as a known limitation for Task 8 review.

## Task 6: API Routes

**Files:**

- Create: `backend/app/schemas/memory.py`
- Create: `backend/app/api/memory.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_memory_api.py`

**Interfaces:**

- Consumes: Task 5 service
- Produces:
  - `POST /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/memory/extractions`
  - `GET /api/v1/workspaces/{workspace_id}/memory/extractions`
  - `GET /api/v1/workspaces/{workspace_id}/memory/candidates`

- [ ] **Step 1: Write failing API tests**

Cover manual trigger success, rejection of caller-supplied `trigger`, missing
workspace/conversation errors, workspace/conversation mismatch, sanitized error
bodies, list runs, list candidates, response counts, and exact route status
codes from the spec.

- [ ] **Step 2: Run API tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/integration/test_memory_api.py -q`

Expected: tests fail because routes are not mounted.

- [ ] **Step 3: Implement schemas and routes**

Map service errors to controlled HTTP responses. Do not include source message
content, candidate text, evidence summary, or conversation title in errors.

- [ ] **Step 4: Run API tests for GREEN**

Run: `./.venv/bin/python -m pytest backend/tests/integration/test_memory_api.py -q`

Expected: all API tests pass.

- [ ] **Step 5: Review checkpoint**

Review: route handlers contain no SQL/DDL/path creation and no memory write is
visible to RAG.

## Task 7: Memory Evaluation Report

**Files:**

- Create: `backend/memory/evaluation/__init__.py`
- Create: `backend/memory/evaluation/models.py`
- Create: `backend/memory/evaluation/runner.py`
- Create: `backend/memory/evaluation/cli.py`
- Create: `docs/evaluation/fixtures/memory/r5-shadow-v0.1/manifest.json`
- Create: `docs/evaluation/fixtures/memory/r5-shadow-v0.1/examples.jsonl`
- Create after run: `docs/reports/memory/r5-shadow-v0.1.md`
- Create after run: `docs/reports/memory/r5-shadow-v0.1.json`
- Test: `backend/tests/unit/test_memory_evaluation_runner.py`

**Interfaces:**

- Consumes: memory repository/service evidence and `docs/evaluation/memory-evaluation.md`
- Produces: deterministic shadow-memory evaluation report

- [ ] **Step 1: Write failing evaluation tests**

Cover result states `PASS`, `FAIL`, `INCONCLUSIVE`, and `INVALID`; hard-gate
failure dominance; invalid evidence behavior; redacted report output.

- [ ] **Step 2: Create synthetic fixtures**

Create tracked benchmark/safety examples under
`docs/evaluation/fixtures/memory/r5-shadow-v0.1/` covering explicit durable
preference, trip constraint, transient detail, ambiguous candidate, explicit
correction, wrong-scope case, excluded trace, ordinary R4 default-excluded chat
message, and controlled secret-like marker.

- [ ] **Step 3: Implement evaluation runner and CLI command**

Add a memory-specific command, for example
`./.venv/bin/python -m backend.memory.evaluation.cli run-shadow --fixture docs/evaluation/fixtures/memory/r5-shadow-v0.1/manifest.json`.
Do not modify existing RAG evaluation commands or result formats.

- [ ] **Step 4: Run evaluation tests**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_evaluation_runner.py -q`

Expected: all memory evaluation tests pass.

- [ ] **Step 5: Run the shadow evaluation**

Run the approved memory evaluation command from the implementation. Expected:
one Markdown report and one machine-readable JSON report under
`docs/reports/memory/`. Fixture source files remain tracked under
`docs/evaluation/fixtures/memory/`.

- [ ] **Step 6: Review checkpoint**

Review: report includes hard safety counts, mandatory slices, invalid evidence,
redacted examples, and the final result state.

## Task 8: Documentation, Boundary Checks, and Handoff

**Files:**

- Modify: `ARCHITECTURE.md`
- Modify: `DEVELOPMENT.md`
- Modify: `docs/architecture/current-state.md`
- Modify: `docs/architecture/data-model.md`
- Modify: `docs/roadmap/master-roadmap.md`
- Modify: `docs/plans/README.md`
- Modify: this plan

**Interfaces:**

- Consumes: completed R5 implementation and verification evidence
- Produces: review packet ready for repository-owner acceptance

- [ ] **Step 1: Update canonical docs**

Document R5 as shadow-only, backend-only, local-development-only, and not used
in answers.

- [ ] **Step 2: Run focused R5 tests**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_models.py backend/tests/unit/test_memory_policy.py backend/tests/unit/test_memory_extraction.py backend/tests/unit/test_sqlite_memory_repository.py backend/tests/unit/test_memory_service.py backend/tests/unit/test_memory_evaluation_runner.py backend/tests/integration/test_memory_api.py -q`

Expected: all focused R5 tests pass.

- [ ] **Step 3: Run full backend tests**

Run: `./.venv/bin/python -m pytest backend/tests -q`

Expected: full backend test suite passes.

- [ ] **Step 4: Compile backend**

Run: `./.venv/bin/python -m compileall backend`

Expected: exit code `0`.

- [ ] **Step 5: Run import-boundary checks**

Run: `grep -rnI -E "backend\.memory|app\.api\.memory|app\.schemas\.memory" backend/rag`

Expected: no output and exit code `1`.

Run: `grep -rnI -E "backend\.memory|app\.api\.memory|app\.schemas\.memory" backend/tests/unit/test_evaluation_*.py backend/tests/integration/test_rag_evaluation_flow.py`

Expected: no output and exit code `1`.

Run: `grep -rnI -E "backend\.rag|backend\.orchestration" backend/memory`

Expected: no output and exit code `1`.

- [ ] **Step 6: Run static Git checks**

Run: `git diff --check`

Expected: no whitespace errors.

Run: `git status --short --untracked-files=all`

Expected: only R5 source, test, docs, and tracked evaluation fixture/report
paths appear. No ignored `data/` fixture, database file, symlink, Chroma
artifact, or unrelated file appears.

- [ ] **Step 7: Review checkpoint**

Prepare the final review packet with changed files, requirement mapping, RED and
GREEN evidence, report path, limitations, and exact remaining Git delivery gate.

## Package Verification

Before returning `READY_FOR_OWNER`, run all commands in Task 8 on the exact
reviewed state. The worker must report actual command output summaries, exit
status, skipped checks, and every limitation.

The package is not complete if:

1. any memory candidate can affect an answer;
2. any raw content appears in logs, HTTP errors, or report excerpts that should
   be redacted;
3. RAG imports memory modules;
4. a test writes to the default developer database;
5. a model provider, network, Docker, Chroma data, or embedding model is needed
   for the default verification suite;
6. the report omits hard safety gate counts or final result state.

## Rollback

Rollback is a normal source revert of the R5 change set before Git delivery.
Remove R5 source modules, tests, route mounts, CLI additions, evaluation
fixtures/reports, and docs updates. Do not delete any user database file unless
the repository owner names the exact path and approves that cleanup.

## Completion Record

This plan version 0.1 was approved by the repository owner in conversation on
2026-09-04 together with approval of R5 spec version 0.1 and acceptance of ADR
0006. Implementation is authorized for an isolated worker following this plan.
No Git staging, commit, push, merge, release, or destructive cleanup is
authorized by approval of this file.
