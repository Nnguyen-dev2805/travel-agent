# Memory Retrieval Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence.

**Goal:** Build backend-only R6 memory retrieval that promotes eligible R5
memory candidates into answer-eligible records and uses them in bound chat turns
only behind a default-off feature gate.

**Architecture:** `backend/memory/` owns promotion, memory records, retrieval
policy, storage, and memory evaluation. Answer-eligible records live in a new
`memory_records` schema module at version 1, leaving R5's `memory` module at
version 1. `ConversationOrchestrator` calls memory retrieval only when enabled
and composes selected memory with travel RAG prompt context through a narrow
RAGService seam. `backend/rag` remains independent from `backend.memory`.

**Tech Stack:** Python 3.11+ baseline, FastAPI, Pydantic, standard-library
`sqlite3`, pytest, Markdown, existing shared schema registry, existing backend
test layout.

**Spec:** [Memory Retrieval Design](../specs/2026-09-04-memory-retrieval-design.md), version 0.1 (In Review)

| Field | Value |
| --- | --- |
| Status | In Review |
| Plan version | 0.1 |
| Date | 2026-09-04 |
| Approved specification | Pending approval: [Memory Retrieval Design](../specs/2026-09-04-memory-retrieval-design.md), version 0.1 |
| Governing ADRs | Pending acceptance: [ADR 0007](../adr/0007-feature-gated-memory-retrieval-and-context-boundary.md) |
| Plan approval | Pending repository-owner approval |
| Execution owner | Implementation worker agent in an isolated worktree after gates pass |
| Decision owner | Repository owner |
| Scope | Runtime milestone R6 - memory record contracts, promotion, retrieval, feature-gated orchestration integration, API/evaluation traces, tests, reports, and docs |
| Verification | `./.venv/bin/python -m pytest backend/tests`, `./.venv/bin/python -m compileall backend`, import-boundary `grep` checks, R6 memory evaluation report validation, `git diff --check`, `git status --short --untracked-files=all` |

## Global Constraints

1. Do not implement R6 source code until R5 is delivered, ADR 0007 is accepted,
   the R6 spec is approved, and this plan is approved by the repository owner.
2. Execute R6 on `feature/agent-memory` at an owner-approved integration base
   that includes R5 implementation and R5 verification evidence.
3. `MEMORY_RETRIEVAL_ENABLED` defaults to false. With the feature gate disabled,
   chat behavior must remain R4/R5 behavior.
4. No frontend work. Do not modify `frontend/`.
5. No authentication, authorization, account model, tenant isolation,
   production privacy claim, production database, ORM, migration framework,
   vector memory store, Chroma memory write, model-provider dependency, planner
   state, deletion API, memory edit UI, or public request toggle.
6. Never log raw message content, candidate text, memory text, evidence
   summary, prompt fragments, conversation title, or substrings of those values.
7. Tests use temporary databases and deterministic fakes. They must not require
   a model provider, embedding model, Chroma data, Docker, or network access.
8. Preserve `GET /health`, every workspace route, every conversation route, and
   both bound and unbound chat response contracts.
9. `backend/rag`, including RAG evaluation, must not import `backend.memory` or
   memory API modules. `backend/memory` must not import `backend.rag` or
   `backend.orchestration`.
10. Memory retrieval fixtures must be tracked under
    `docs/evaluation/fixtures/memory/`, not under Git-ignored `data/`.
11. If R6 is executed in a linked worktree, use the primary tree virtual
    environment by absolute path when `.venv` is absent, and symlink only
    `data/processed` if the full existing backend suite requires it. Never
    symlink `docs`, `.venv`, `backend`, `frontend`, `data`, `data/chromadb`, or
    `data/evaluation`; never force-add ignored `data/` paths.
12. Do not modify `backend/memory/extraction.py`, `backend/memory/policy.py`, or
    the R5 `PolicyReason` vocabulary. R5 extraction and policy behavior is
    governed by the approved R5 spec and ADR 0006; widening what becomes
    promotable is an R5 change, not an R6 change.
13. Do not modify `backend/storage/schema_registry.py`. R6 registers the new
    `memory_records` module through the existing registry API and relies on ADR
    0004 fail-closed behavior unchanged.
14. The implementation worker must not stage, commit, push, merge, rebase, tag,
    release, delete branches, or perform destructive cleanup unless the
    repository owner asks for that exact Git action.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/memory/models.py` | Add R6 memory record, promotion, retrieval, and trace contracts while preserving R5 candidate contracts | R5 implementation, R6 spec |
| `backend/memory/repository.py` | Add memory record, promotion run, and retrieval event repository protocols | Memory models |
| `backend/memory/sqlite_repository.py` | Add `memory_records` schema module version 1 tables and queries while preserving R5 `memory` schema version 1 | Shared schema registry, R5 memory schema |
| `backend/memory/promotion.py` | Candidate-to-record eligibility, duplicate detection, and skip reasons | Memory repository, R5 candidates |
| `backend/memory/retrieval.py` | Scope, lifecycle, correction, and deterministic lexical ranking | Memory repository |
| `backend/memory/service.py` | Promotion and retrieval use cases | Promotion, retrieval, repository |
| `backend/orchestration/memory_context.py` | Compose selected memory text with RAG prompt context without changing RAG ownership | Memory retrieval output, RAG `ContextBundle` |
| `backend/orchestration/conversation_orchestrator.py` | Feature-gated memory retrieval and response metadata for bound chat | Conversation service, RAG service, memory service |
| `backend/rag/generation/rag_service.py` | Add a narrow injectable travel-context seam for orchestration memory composition without memory imports | RAG retriever, assembler, generator |
| `backend/app/config.py` | Add `MEMORY_RETRIEVAL_ENABLED`, `MEMORY_PROMOTION_MIN_CONFIDENCE`, and `MEMORY_MAX_SELECTED` to `Settings` following the existing `os.getenv` pattern, with the gate defaulting to false | Existing settings module |
| `backend/app/schemas/chat.py` | Optional memory response metadata when feature gate is enabled, omitted entirely when absent | Orchestrator output |
| `backend/app/api/chat.py` | Wire optional memory service/settings into orchestrator dependency construction | App settings, memory service |
| `backend/app/schemas/memory.py` | Add promotion and retrieval inspection schemas if not already present | Memory models |
| `backend/app/api/memory.py` | Add backend-only promotion and inspection routes | Memory service |
| `backend/memory/evaluation/models.py` | R6 retrieval and A/B report value objects | Memory evaluation protocol |
| `backend/memory/evaluation/runner.py` | Paired memory-disabled and memory-enabled evaluation runner | Memory service, deterministic fakes |
| `backend/memory/evaluation/cli.py` | R6 memory evaluation command | Evaluation runner |
| `backend/tests/unit/test_memory_records.py` | Memory record and trace model tests | Memory models |
| `backend/tests/unit/test_memory_promotion.py` | Promotion eligibility and skip reason tests | Promotion |
| `backend/tests/unit/test_memory_retrieval.py` | Scope, lifecycle, correction, and ranking tests | Retrieval |
| `backend/tests/unit/test_sqlite_memory_records.py` | `memory_records` schema version 1 and temporary database tests | SQLite adapter |
| `backend/tests/unit/test_memory_context.py` | Memory/RAG prompt composition tests | Orchestration context helper |
| `backend/tests/unit/test_memory_retrieval_evaluation_runner.py` | R6 evaluation state and hard-gate tests | Evaluation runner |
| `backend/tests/integration/test_chat_memory_retrieval.py` | Feature-gate-off compatibility and feature-gate-on bound chat tests | FastAPI app, orchestrator |
| `backend/tests/integration/test_memory_promotion_api.py` | Promotion route tests with temporary database | FastAPI app |
| `docs/evaluation/fixtures/memory/r6-retrieval-v0.1/manifest.json` | Tracked fixture manifest for R6 retrieval evaluation | Memory evaluation protocol |
| `docs/evaluation/fixtures/memory/r6-retrieval-v0.1/examples.jsonl` | Tracked synthetic examples for R6 retrieval evaluation | Memory evaluation protocol |
| `docs/reports/memory/r6-retrieval-v0.1.md` | Human-readable R6 evaluation report | Evaluation run |
| `docs/reports/memory/r6-retrieval-v0.1.json` | Machine-readable R6 evaluation report | Evaluation run |
| `.env.example` | Add the three R6 memory variables as commented placeholders with the gate off | Implemented settings |
| `ARCHITECTURE.md` | Current-state gateway update after R6 implementation | Implemented behavior |
| `DEVELOPMENT.md` | Local R6 commands, env flags, and limitations; add the three R6 variables to the `## Environment` table | Implemented behavior |
| `docs/architecture/current-state.md` | Current-state update after R6 implementation | Implemented behavior |
| `docs/architecture/data-model.md` | Mark R6 memory records implemented and lifecycle limits | Implemented contracts |
| `docs/roadmap/master-roadmap.md` | R6 status and evidence update | Completion evidence |
| `docs/plans/README.md` | Plan index status update | This plan |

## Task 1: Approval Gates, R5 Evidence, and Baseline

**Files:**

- Read: R5 spec, R5 plan, R5 report, ADR 0006, ADR 0007, this spec, this plan,
  roadmap
- Modify: this plan, `docs/plans/README.md`,
  `docs/roadmap/master-roadmap.md`

**Interfaces:**

- Consumes: R5 delivered change set, R5 report, owner approvals for ADR 0007,
  R6 spec, and this plan
- Produces: recorded execution base and baseline evidence

- [ ] **Step 1: Confirm hard gates**

Confirm:

- R5 status is delivered or owner-accepted on the selected integration base.
- R5 report exists and is not `FAIL` or `INVALID`.
- ADR 0007 status is `Accepted`.
- R6 spec status is `Approved`.
- This plan status is `Approved`.

Stop before source edits if any gate is missing.

- [ ] **Step 2: Inspect clean worktree**

Run: `git status --short --branch --untracked-files=all`

Expected: no unrelated changes overlap R6 paths. If dirty files overlap, read
them before deciding whether to continue.

- [ ] **Step 3: Record baseline tests**

Run: `./.venv/bin/python -m pytest backend/tests -q`

Expected: existing suite passes. Record exact count and duration in this plan.

- [ ] **Step 4: Mark execution start**

Update this plan status to `In Progress`, update the plan index to
`In Progress`, and update roadmap `R6` from `Blocked by gate` to `In progress`
only after the gates and baseline pass.

- [ ] **Step 5: Review checkpoint**

Review: gate evidence, baseline output, and worktree status.

Expected: no source file has changed before the gate and baseline are recorded.

## Task 2: Memory Record Contracts

**Files:**

- Modify: `backend/memory/models.py`
- Test: `backend/tests/unit/test_memory_records.py`

**Interfaces:**

- Produces:
  - `MemoryRecord`
  - `MemoryRecordStatus`
  - `MemoryPromotionRun`
  - `MemoryPromotionResult`
  - `MemorySelection`
  - `MemorySelectionTrace`
  - `generate_memory_record_id()`
  - `generate_memory_promotion_run_id()`

- [ ] **Step 1: Write failing model tests**

Cover identifier prefixes `mem_` and `mpr_`, UTC timestamps, status vocabulary,
scope and `scope_id` invariants, text length, confidence range, promoted
sensitivity labels, optional expiration, and no blank required identifiers.

- [ ] **Step 2: Run model tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_records.py -q`

Expected: tests fail because R6 contracts do not exist.

- [ ] **Step 3: Implement contracts**

Extend the memory model module without changing R5 candidate vocabularies except
where the approved R6 spec requires additive exports.

- [ ] **Step 4: Run model tests for GREEN**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_records.py -q`

Expected: all model tests pass.

- [ ] **Step 5: Review checkpoint**

Review: R5 candidate contracts still pass, and R6 record contracts match the
spec exactly.

## Task 3: SQLite Record Store and Repository Protocols

**Files:**

- Modify: `backend/memory/repository.py`
- Modify: `backend/memory/sqlite_repository.py`
- Test: `backend/tests/unit/test_sqlite_memory_records.py`

**Interfaces:**

- Produces repository methods for creating promotion runs, creating memory
  records, listing records by scope, writing retrieval events, and rejecting
  unexpected schema versions.

- [ ] **Step 1: Write failing repository tests**

Cover empty database initialization with R5 `memory` schema version 1 plus
`memory_records` schema version 1, coexistence with existing R5 candidate
tables, fail-closed behavior for unexpected `memory_records` versions, record
uniqueness, lifecycle filtering, and temporary database isolation.

- [ ] **Step 2: Run repository tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_memory_records.py -q`

Expected: tests fail because R6 repository methods and schema do not exist.

- [ ] **Step 3: Implement repository and schema**

Add explicit `memory_records` schema module version 1 tables and indexes. Do not
change the R5 `memory` module version. Do not introduce a general migration
framework. Do not write memory data to Chroma or `data/evaluation`.

- [ ] **Step 4: Run repository tests for GREEN**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_memory_records.py -q`

Expected: all repository tests pass.

- [ ] **Step 5: Review checkpoint**

Review: schema ownership remains under `backend/memory/`, all tests use temp
databases, R5 candidate persistence still works, and ADR 0004 fail-closed
registry behavior remains unchanged.

## Task 4: Promotion Policy

**Files:**

- Create: `backend/memory/promotion.py`
- Modify: `backend/memory/service.py`
- Test: `backend/tests/unit/test_memory_promotion.py`
- Test: `backend/tests/integration/test_memory_promotion_api.py`

**Interfaces:**

- Produces:
  - `MemoryPromotionPolicy.promote_candidates(...)`
  - service method for workspace or conversation promotion
  - optional backend-only promotion route

- [ ] **Step 1: Write failing promotion tests**

Cover promotion of the three reasons that have an R5 producer
(`supported_preference` at `user` scope, `supported_constraint` at `workspace`
scope, `explicit_correction` at `user` scope), rejected candidate skip,
needs-user-action skip, invalid provenance skip, low confidence skip at `0.75`,
secret/sensitive/unsafe skip, duplicate skip, scope mapping, and the governed
promotion reason codes.

Also cover the two allow-list reasons with no R5 producer. Construct
`supported_profile_fact` and `supported_trip_decision` candidates directly as
contract fixtures, assert promotion accepts them, and assert with the real
`RuleBasedMemoryExtractor` plus `MemoryPolicy` that no fixture message yields an
`accepted` candidate carrying either reason. That keeps the allow-list
forward-compatible without claiming coverage R5 cannot produce.

Cover correction supersession in all three target cases: zero targets leaves
`supersedes_memory_id` absent, one target records that id and marks the target
`superseded`, and multiple targets mark every target `superseded` while
recording the oldest id by the `(created_at, source_sequence)` age key and the
`correction_supersedes_multiple` trace reason. Also assert a correction never
suppresses a record in a different `scope_id`, and that a `user`-scope
correction raised in one conversation can supersede a `user`-scope record
created in another.

- [ ] **Step 2: Run promotion tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_promotion.py backend/tests/integration/test_memory_promotion_api.py -q`

Expected: tests fail because promotion does not exist.

- [ ] **Step 3: Implement promotion**

Implement candidate-to-record promotion with controlled skip reasons and counts.
Derive `supersedes_memory_id` only from scope identity and the
`(created_at, source_sequence)` age key as the spec requires; never from text
similarity or a model. Return identifiers and counts only; do not log raw
content.

- [ ] **Step 4: Run promotion tests for GREEN**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_promotion.py backend/tests/integration/test_memory_promotion_api.py -q`

Expected: all promotion tests pass.

- [ ] **Step 5: Review checkpoint**

Review: R6 does not reinterpret rejected R5 candidates, does not promote any
secret-like fixture content, and does not modify `backend/memory/extraction.py`
or `backend/memory/policy.py` to widen promotion coverage.

## Task 5: Retrieval Policy and Context Composition

**Files:**

- Create: `backend/memory/retrieval.py`
- Create: `backend/orchestration/memory_context.py`
- Test: `backend/tests/unit/test_memory_retrieval.py`
- Test: `backend/tests/unit/test_memory_context.py`

**Interfaces:**

- Produces:
  - `MemoryRetrievalService.select_memories(...)`
  - deterministic lexical ranking
  - memory prompt section composer

- [ ] **Step 1: Write failing retrieval tests**

Cover user, workspace, and conversation scope; cross-workspace isolation;
cross-user isolation; status filtering; expiration filtering; correction
precedence; max-selected limit; and no eligible memory.

- [ ] **Step 2: Write failing context tests**

Cover memory prompt section formatting, no memory-as-citation behavior,
preserved RAG citations, and no raw source message leakage.

- [ ] **Step 3: Run retrieval/context tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_retrieval.py backend/tests/unit/test_memory_context.py -q`

Expected: tests fail because retrieval and context composition do not exist.

- [ ] **Step 4: Implement retrieval and composition**

Implement deterministic selection and a controlled memory context section that
the orchestrator can combine with the existing RAG prompt context.

- [ ] **Step 5: Run retrieval/context tests for GREEN**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_retrieval.py backend/tests/unit/test_memory_context.py -q`

Expected: all retrieval and context tests pass.

- [ ] **Step 6: Review checkpoint**

Review: memory context is separate from travel citations and RAG still has no
memory imports.

## Task 6: Feature-gated Chat Integration

**Files:**

- Modify: `backend/orchestration/conversation_orchestrator.py`
- Modify: `backend/rag/generation/rag_service.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/schemas/chat.py`
- Modify: `backend/app/api/chat.py`
- Test: `backend/tests/integration/test_chat_memory_retrieval.py`

**Interfaces:**

- Consumes: memory retrieval service, context composer, and RAGService
  travel-context seam
- Produces: feature-gated memory selection during bound chat turns

- [ ] **Step 1: Write failing integration tests**

Cover:

- feature gate disabled preserves response schema and does not call memory;
- feature gate disabled omits the `memory` key entirely, rather than returning
  `memory: null`;
- gate default is off when no environment variable is set;
- unbound chat skips memory even when the gate is enabled;
- bound chat with eligible memory selects IDs/reasons and preserves travel
  citations;
- out-of-scope or inactive memory is not selected.

- [ ] **Step 2: Run integration tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/integration/test_chat_memory_retrieval.py -q`

Expected: tests fail because chat integration does not exist.

- [ ] **Step 3: Implement feature-gated integration**

Add the three R6 settings to `backend/app/config.py` using the existing
`os.getenv` pattern, with `MEMORY_RETRIEVAL_ENABLED` defaulting to false. Add a
narrow `RAGService` seam that exposes travel retrieval context and generation
through injectable RAG-owned dependencies, then wire memory settings and service
construction through existing dependency patterns. Keep the public request body
free of a memory override. Extend the existing chat response serializer so an
absent `memory` object is omitted entirely.

- [ ] **Step 4: Run integration tests for GREEN**

Run: `./.venv/bin/python -m pytest backend/tests/integration/test_chat_memory_retrieval.py -q`

Expected: all integration tests pass.

- [ ] **Step 5: Review checkpoint**

Review: feature-gate-off behavior is unchanged and selected memory metadata is
controlled.

## Task 7: R6 Evaluation Harness and Report

**Files:**

- Modify: `backend/memory/evaluation/models.py`
- Modify: `backend/memory/evaluation/runner.py`
- Modify: `backend/memory/evaluation/cli.py`
- Create: `docs/evaluation/fixtures/memory/r6-retrieval-v0.1/manifest.json`
- Create: `docs/evaluation/fixtures/memory/r6-retrieval-v0.1/examples.jsonl`
- Create: `docs/reports/memory/r6-retrieval-v0.1.md`
- Create: `docs/reports/memory/r6-retrieval-v0.1.json`
- Test: `backend/tests/unit/test_memory_retrieval_evaluation_runner.py`

**Interfaces:**

- Produces paired memory-disabled and memory-enabled evaluation outputs.

- [ ] **Step 1: Write failing evaluation tests**

Cover valid report output, selected memory IDs/reasons, memory Hit@5,
irrelevant-memory rate, hard-gate zero counts, `INCONCLUSIVE` answer-quality
state when no provider-backed judge is configured, and `INVALID` for malformed
fixtures.

- [ ] **Step 2: Run evaluation tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_retrieval_evaluation_runner.py -q`

Expected: tests fail because R6 evaluation paths do not exist.

- [ ] **Step 3: Implement evaluation runner and fixtures**

Create synthetic tracked fixtures covering mandatory memory retrieval slices:
explicit preferences, inferred preferences, workspace decisions, user-global
preferences, transient info, ambiguous candidates, corrections, deletion or
tombstone ineligibility, staleness, cross-scope isolation, secret-like content,
and relevant memory help.

- [ ] **Step 4: Run R6 evaluation**

Run: `./.venv/bin/python -m backend.memory.evaluation.cli run-retrieval --suite r6-retrieval-v0.1`

Expected: JSON and Markdown reports are written under `docs/reports/memory/`.
If no answer judge is configured, answer-quality fields are `INCONCLUSIVE` and
no personalization win claim is made.

- [ ] **Step 5: Run evaluation tests for GREEN**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_retrieval_evaluation_runner.py -q`

Expected: all evaluation tests pass.

- [ ] **Step 6: Review checkpoint**

Review: report numbers match JSON artifacts, hard gates are visible, and no raw
message or memory content is leaked beyond controlled synthetic fixture text.

## Task 8: Documentation and Boundary Verification

**Files:**

- Modify: `ARCHITECTURE.md`
- Modify: `DEVELOPMENT.md`
- Modify: `.env.example`
- Modify: `docs/architecture/current-state.md`
- Modify: `docs/architecture/data-model.md`
- Modify: `docs/roadmap/master-roadmap.md`
- Modify: `docs/plans/README.md`
- Modify: this plan

**Interfaces:**

- Consumes: completed source changes and fresh verification
- Produces: truthful current-state documentation and final handoff evidence

- [ ] **Step 1: Update documentation**

Document:

- feature gate name and default-off behavior, including the three R6 variables
  in the `DEVELOPMENT.md` `## Environment` table and as commented
  `.env.example` placeholders;
- R6 implemented modules and routes or commands;
- the `memory_records` schema module alongside the unchanged R5 `memory` module;
- RAG independence from memory;
- promotion coverage limits: `profile_fact` and `decision` memory reach R6 only
  through seeded fixtures, and `personal` sensitivity is not promoted;
- correction supersession behavior, including ambiguous-target suppression;
- evaluation limitations and report path;
- roadmap R6 status and evidence.

- [ ] **Step 2: Run import-boundary checks**

Run:

```text
grep -R "backend.memory" -n backend/rag
grep -R "from backend.memory\\|import backend.memory" -n backend/rag
grep -R "backend.rag\\|backend.orchestration" -n backend/memory
grep -R "chromadb" -n backend/memory
```

Expected: all commands return no matches. The final command proves no memory
Chroma dependency.

- [ ] **Step 3: Run full backend verification**

Run:

```text
./.venv/bin/python -m pytest backend/tests -q
./.venv/bin/python -m compileall backend
git diff --check
git status --short --untracked-files=all
```

Expected: tests pass, compileall exits 0, whitespace check is clean, and status
contains only intentional R6 files.

- [ ] **Step 4: Scope review**

Review changed files against the File Responsibility Map. Confirm no frontend,
auth, vector memory, deletion API, planner state, Chroma memory writes,
unapproved RAG dependency, or Git delivery action entered the change set.

Confirm `backend/memory/extraction.py`, `backend/memory/policy.py`, and
`backend/storage/schema_registry.py` are unchanged.

Run: `git diff --stat -- backend/memory/extraction.py backend/memory/policy.py backend/storage/schema_registry.py`

Expected: no output, proving R5 extraction, R5 policy, and the ADR 0004 registry
were not modified to make R6 easier.

- [ ] **Step 5: Mark completion**

Update this plan status to `Completed`, update the plan index, and update
roadmap `R6` to `Accepted in working tree` only after repository-owner review
accepts the change set. Do not mark `Delivered` until Git delivery occurs.

- [ ] **Step 6: Review checkpoint**

Return a READY_FOR_OWNER packet with changed files, verification evidence,
limitations, R6 report paths, feature-gate state, and remaining delivery gate.

## Package Verification

Run these checks freshly before handoff:

```text
./.venv/bin/python -m pytest backend/tests -q
./.venv/bin/python -m compileall backend
grep -R "backend.memory" -n backend/rag
grep -R "from backend.memory\\|import backend.memory" -n backend/rag
grep -R "backend.rag\\|backend.orchestration" -n backend/memory
grep -R "chromadb" -n backend/memory
git diff --stat -- backend/memory/extraction.py backend/memory/policy.py backend/storage/schema_registry.py
./.venv/bin/python -m backend.memory.evaluation.cli run-retrieval --suite r6-retrieval-v0.1
git diff --check
git status --short --untracked-files=all
```

Expected:

1. backend tests pass;
2. compileall exits 0;
3. RAG import-boundary checks return no matches;
4. memory reverse-boundary and Chroma checks return no matches;
5. R5 extraction, R5 policy, and the shared schema registry are unchanged;
6. R6 evaluation report is present and internally consistent;
7. Git status contains only intentional R6 files;
8. no Git delivery command has been run by the implementation worker.

## Rollback

Set `MEMORY_RETRIEVAL_ENABLED=false` to restore R4/R5 answer behavior. Code
rollback removes R6 memory promotion, retrieval, orchestration composition,
routes or commands, tests, fixtures, and documentation updates. Existing local
memory records remain inert if no answer path reads them. Do not delete user
local databases unless the repository owner explicitly requests that exact
cleanup.

## Completion Record

Version 0.1 is in review. Implementation is blocked until R5 delivery evidence
exists and the repository owner explicitly accepts ADR 0007, approves the R6
spec, and approves this plan.
