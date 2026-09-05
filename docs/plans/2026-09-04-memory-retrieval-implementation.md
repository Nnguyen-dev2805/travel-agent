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

**Spec:** [Memory Retrieval Design](../specs/2026-09-04-memory-retrieval-design.md), version 0.1 (Approved)

| Field | Value |
| --- | --- |
| Status | In Progress |
| Plan version | 0.1 |
| Date | 2026-09-04 |
| Approved specification | [Memory Retrieval Design](../specs/2026-09-04-memory-retrieval-design.md), version 0.1 (Approved 2026-09-05) |
| Governing ADRs | [ADR 0007](../adr/0007-feature-gated-memory-retrieval-and-context-boundary.md) (Accepted 2026-09-05) |
| Plan approval | Repository owner approved implementation plan version 0.1 in conversation on 2026-09-05, together with approval of R6 spec version 0.1 and acceptance of ADR 0007 |
| Execution owner | Implementation worker agent in an isolated worktree |
| Decision owner | Repository owner |
| Scope | Runtime milestone R6 - memory record contracts, promotion, retrieval, feature-gated orchestration integration, API/evaluation traces, tests, reports, and docs |
| Verification | `./.venv/bin/python -m pytest backend/tests`, `./.venv/bin/python -m compileall backend`, import-boundary `grep` checks, R6 memory evaluation report validation, `git diff --check`, `git status --short --untracked-files=all` |

## Global Constraints

1. Every approval gate in Task 1 Step 1 is satisfied as of 2026-09-05. The
   worker still re-confirms each one before editing source, because a stale gate
   claim is exactly the failure this step exists to catch.
2. Execute R6 on `feature/agent-memory` at the owner-approved integration base
   `89496eb`, which includes R5 implementation and R5 verification evidence.
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

- [x] **Step 1: Confirm hard gates**

Gates re-read from sources on 2026-09-05 and all hold: R5 delivered at
`89496eb` (ancestor of this worktree HEAD `c5c958e`, source-identical —
`git diff 89496eb HEAD -- backend/` empty); `docs/reports/memory/
r5-shadow-v0.1.json` is `PASS` (13 eligible, 0 invalid); ADR 0007
`Accepted`; R6 spec v0.1 `Approved`; this plan v0.1 `Approved`.

Re-read each source of truth and confirm the recorded state still holds. Do not
trust this table alone; it records the state at approval time.

| Gate | Expected | Recorded at approval |
| --- | --- | --- |
| R5 delivery | Delivered or owner-accepted on the integration base | Delivered at `89496eb` on `feature/agent-memory` |
| R5 report | Exists and is not `FAIL` or `INVALID` | `docs/reports/memory/r5-shadow-v0.1.md` is `PASS` |
| ADR 0007 | `Accepted` | Accepted 2026-09-05 |
| R6 spec | `Approved` | Approved 2026-09-05, version 0.1 |
| This plan | `Approved` | Approved 2026-09-05, version 0.1 |

Stop before source edits if any gate no longer holds.

- [x] **Step 2: Inspect clean worktree**

Worktree `r6-retrieval` verified isolated (`git-dir != git-common-dir`),
`git status` clean, `.worktrees` ignored, `data/processed` symlinked per
Global Constraint 11 (invisible to `git status`).

Run: `git status --short --branch --untracked-files=all`

Expected: no unrelated changes overlap R6 paths. If dirty files overlap, read
them before deciding whether to continue.

- [x] **Step 3: Record baseline tests**

Baseline in this worktree (primary `.venv` by absolute path):
`834 passed, 1 warning in 22.20s` — exactly the recorded `89496eb`
figure, so no investigation was needed.

Run: `./.venv/bin/python -m pytest backend/tests -q`

Expected: existing suite passes. The base `89496eb` measured `834 passed` with
`compileall` exit `0` on 2026-09-05. Record the exact count and duration
observed by this execution in this plan; investigate any difference before
continuing.

- [x] **Step 4: Mark execution start**

Plan status, plan index, and roadmap R6 moved to `In Progress`. Note: the
roadmap cell read `Ready for handoff`, not `Blocked by gate` as this step
anticipated; the transition intent (execution started) is identical.

Update this plan status to `In Progress`, update the plan index to
`In Progress`, and update roadmap `R6` from `Blocked by gate` to `In progress`
only after the gates and baseline pass.

- [x] **Step 5: Review checkpoint**

Review: gate evidence, baseline output, and worktree status.

Expected: no source file has changed before the gate and baseline are recorded.

Checkpoint: only this plan, `docs/plans/README.md`, and
`docs/roadmap/master-roadmap.md` changed (the Task 1 file scope); no
`backend/` source changed before baseline.

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

- [x] **Step 1: Write failing model tests**

Cover identifier prefixes `mem_` and `mpr_`, UTC timestamps, status vocabulary,
scope and `scope_id` invariants, text length, confidence range, promoted
sensitivity labels, optional expiration, and no blank required identifiers.

- [x] **Step 2: Run model tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_records.py -q`

Expected: tests fail because R6 contracts do not exist.

- [x] **Step 3: Implement contracts**

Extend the memory model module without changing R5 candidate vocabularies except
where the approved R6 spec requires additive exports.

- [x] **Step 4: Run model tests for GREEN**

GREEN: `18 passed` (`backend/tests/unit/test_memory_records.py`).

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_records.py -q`

Expected: all model tests pass.

- [x] **Step 5: Review checkpoint**

Review: R5 candidate contracts still pass, and R6 record contracts match the
spec exactly.

Checkpoint: R5 code untouched (only appended section + merged import/exports);
two R6-scoped model decisions documented in code because the approved spec
leaves them open — `MemorySelectionReason` holds exactly the two retrieval
rule 9 paths, and `MemorySelectionTrace` is the persisted retrieval event;
`scope_id` is bound to its scope owner inside the contract.

## Task 3: SQLite Record Store and Repository Protocols

**Files:**

- Modify: `backend/memory/repository.py`
- Modify: `backend/memory/sqlite_repository.py`
- Test: `backend/tests/unit/test_sqlite_memory_records.py`

**Interfaces:**

- Produces repository methods for creating promotion runs, creating memory
  records, listing records by scope, writing retrieval events, and rejecting
  unexpected schema versions.

- [x] **Step 1: Write failing repository tests**

Cover empty database initialization with R5 `memory` schema version 1 plus
`memory_records` schema version 1, coexistence with existing R5 candidate
tables, fail-closed behavior for unexpected `memory_records` versions, record
uniqueness, lifecycle filtering, and temporary database isolation.

- [x] **Step 2: Run repository tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_memory_records.py -q`

Expected: tests fail because R6 repository methods and schema do not exist.

- [x] **Step 3: Implement repository and schema**

Add explicit `memory_records` schema module version 1 tables and indexes. Do not
change the R5 `memory` module version. Do not introduce a general migration
framework. Do not write memory data to Chroma or `data/evaluation`.

- [x] **Step 4: Run repository tests for GREEN**

GREEN: `11 passed` (`backend/tests/unit/test_sqlite_memory_records.py`;
`18 passed` for Task 2 models alongside).

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_memory_records.py -q`

Expected: all repository tests pass.

- [x] **Step 5: Review checkpoint**

Review: schema ownership remains under `backend/memory/`, all tests use temp
databases, R5 candidate persistence still works, and ADR 0004 fail-closed
registry behavior remains unchanged.

Checkpoint: `mark_records_superseded` added beyond the letter of the Task 3
interface list because the approved Correction Supersession rule requires
persisting target status flips and the interface has no update operation —
without it Task 4 cannot implement approved behavior. `MemorySelectionReason`
holds exactly the two retrieval rule 9 paths and `MemorySelectionTrace` is
the persisted retrieval event; both were unspecified in the spec and are
documented as R6-scoped decisions in code.

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

- [x] **Step 1: Write failing promotion tests**

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

- [x] **Step 2: Run promotion tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_promotion.py backend/tests/integration/test_memory_promotion_api.py -q`

Expected: tests fail because promotion does not exist.

- [x] **Step 3: Implement promotion**

Implement candidate-to-record promotion with controlled skip reasons and counts.
Derive `supersedes_memory_id` only from scope identity and the
`(created_at, source_sequence)` age key as the spec requires; never from text
similarity or a model. Return identifiers and counts only; do not log raw
content.

- [x] **Step 4: Run promotion tests for GREEN**

GREEN: `18 passed` (`test_memory_promotion.py` + `test_memory_promotion_api.py`).

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_promotion.py backend/tests/integration/test_memory_promotion_api.py -q`

Expected: all promotion tests pass.

- [x] **Step 5: Review checkpoint**

Review: R6 does not reinterpret rejected R5 candidates, does not promote any
secret-like fixture content, and does not modify `backend/memory/extraction.py`
or `backend/memory/policy.py` to widen promotion coverage.

Checkpoint: `MemoryService` gained only an additive `promotion_policy`
dependency (existing constructor calls unaffected); seven test-setup bugs
fixed (fixture message ids must match candidate provenance, mismatch needs
an existing workspace); the promotion route reuses the R5 `get_memory_service`
dependency and static error details.

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

- [x] **Step 1: Write failing retrieval tests**

Cover user, workspace, and conversation scope; cross-workspace isolation;
cross-user isolation; status filtering; expiration filtering; correction
precedence; max-selected limit; and no eligible memory.

- [x] **Step 2: Write failing context tests**

Cover memory prompt section formatting, no memory-as-citation behavior,
preserved RAG citations, and no raw source message leakage.

- [x] **Step 3: Run retrieval/context tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_retrieval.py backend/tests/unit/test_memory_context.py -q`

Expected: tests fail because retrieval and context composition do not exist.

- [x] **Step 4: Implement retrieval and composition**

Implement deterministic selection and a controlled memory context section that
the orchestrator can combine with the existing RAG prompt context.

- [x] **Step 5: Run retrieval/context tests for GREEN**

GREEN: `13 passed` (`test_memory_retrieval.py` + `test_memory_context.py`).

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_retrieval.py backend/tests/unit/test_memory_context.py -q`

Expected: all retrieval and context tests pass.

- [x] **Step 6: Review checkpoint**

Review: memory context is separate from travel citations and RAG still has no
memory imports.

Checkpoint: composer takes selection contracts only (a narrower dependency
than the plan's `ContextBundle` column, same behavior — orchestration still
passes travel context alongside in Task 6); two test-setup bugs fixed
(zero-overlap fixtures select nothing by rule 9, tie order needs distinct
timestamps); a speculative `rank_records` helper was deleted before GREEN.

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

- [x] **Step 1: Write failing integration tests**

Cover:

- feature gate disabled preserves response schema and does not call memory;
- feature gate disabled omits the `memory` key entirely, rather than returning
  `memory: null`;
- gate default is off when no environment variable is set;
- unbound chat skips memory even when the gate is enabled;
- bound chat with eligible memory selects IDs/reasons and preserves travel
  citations;
- out-of-scope or inactive memory is not selected.

- [x] **Step 2: Run integration tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/integration/test_chat_memory_retrieval.py -q`

Expected: tests fail because chat integration does not exist.

- [x] **Step 3: Implement feature-gated integration**

Add the three R6 settings to `backend/app/config.py` using the existing
`os.getenv` pattern, with `MEMORY_RETRIEVAL_ENABLED` defaulting to false. Add a
narrow `RAGService` seam that exposes travel retrieval context and generation
through injectable RAG-owned dependencies, then wire memory settings and service
construction through existing dependency patterns. Keep the public request body
free of a memory override. Extend the existing chat response serializer so an
absent `memory` object is omitted entirely.

- [x] **Step 4: Run integration tests for GREEN**

GREEN: `8 passed` (`test_chat_memory_retrieval.py`).

Run: `./.venv/bin/python -m pytest backend/tests/integration/test_chat_memory_retrieval.py -q`

Expected: all integration tests pass.

- [x] **Step 5: Review checkpoint**

Review: feature-gate-off behavior is unchanged and selected memory metadata is
controlled.

Checkpoint: R4 boundary tests caught an orchestrator `backend.workspaces`
import from the first implementation — restructured so the app-layer
provider owns workspace resolution and returns `None`/owner-or-`None`,
keeping the R4 import boundary green with no test edits. Gate-off and
unbound turns still call `generate_answer` (existing R4/RAG tests
untouched); only gate-on bound turns use the new RAG seam. Retrieval
failure degrades to `skipped` with an error log instead of failing the
turn. Settings use an `_env_flag` helper so parsing is unit-testable
(Pydantic evaluates defaults at import time).

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

- [x] **Step 1: Write failing evaluation tests**

Cover valid report output, selected memory IDs/reasons, memory Hit@5,
irrelevant-memory rate, hard-gate zero counts, `INCONCLUSIVE` answer-quality
state when no provider-backed judge is configured, and `INVALID` for malformed
fixtures.

- [x] **Step 2: Run evaluation tests for RED**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_retrieval_evaluation_runner.py -q`

Expected: tests fail because R6 evaluation paths do not exist.

- [x] **Step 3: Implement evaluation runner and fixtures**

Create synthetic tracked fixtures covering mandatory memory retrieval slices:
explicit preferences, inferred preferences, workspace decisions, user-global
preferences, transient info, ambiguous candidates, corrections, deletion or
tombstone ineligibility, staleness, cross-scope isolation, secret-like content,
and relevant memory help.

- [x] **Step 4: Run R6 evaluation**

Report `r6-retrieval-v0.1` (`docs/reports/memory/`): **PASS** over 20
eligible examples; promotion precision, scope accuracy, and Hit@5 `1.0`,
irrelevant rate `0.0`, applicable hard gates `0` events; personalization
and constraint delta `INCONCLUSIVE` without a provider-backed judge, per
the limitation accepted at approval time.

Run: `./.venv/bin/python -m backend.memory.evaluation.cli run-retrieval --suite r6-retrieval-v0.1`

Expected: JSON and Markdown reports are written under `docs/reports/memory/`.
If no answer judge is configured, answer-quality fields are `INCONCLUSIVE` and
no personalization win claim is made.

- [x] **Step 5: Run evaluation tests for GREEN**

GREEN: `12 passed` (`test_memory_retrieval_evaluation_runner.py`).

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_memory_retrieval_evaluation_runner.py -q`

Expected: all evaluation tests pass.

- [x] **Step 6: Review checkpoint**

Review: report numbers match JSON artifacts, hard gates are visible, and no raw
message or memory content is leaked beyond controlled synthetic fixture text.

Checkpoint: every example replays in its own isolated database (a shared DB
let user-scope records leak across examples and masked a real design
question); supersession fixtures use a separate earlier conversation because
re-extracting the same message in a new candidate is a new promotion unit by
the approved duplicate rule; per-example DBs keep cross-scope measurement to
explicit foreign seeds; `decide` checks quality FAILs before missing-evidence
INCONCLUSIVE so absent evidence never masks a failure.

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

- [x] **Step 1: Update documentation**

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

- [x] **Step 2: Run import-boundary checks**

All four plan greps return no matches: RAG imports no memory, RAG has no
`from`/`import backend.memory`, memory imports no RAG or orchestration, and
memory has no Chroma dependency.

Run:

```text
grep -R "backend.memory" -n backend/rag
grep -R "from backend.memory\\|import backend.memory" -n backend/rag
grep -R "backend.rag\\|backend.orchestration" -n backend/memory
grep -R "chromadb" -n backend/memory
```

Expected: all commands return no matches. The final command proves no memory
Chroma dependency.

- [x] **Step 3: Run full backend verification**

`914 passed`, `compileall` exit `0`, `git diff --check` clean, status holds
only intentional R6 files (`834` baseline + `80` R6: 29 Task 2-3, 31 Task
4-5, 8 Task 6, 12 Task 7).

Run:

```text
./.venv/bin/python -m pytest backend/tests -q
./.venv/bin/python -m compileall backend
git diff --check
git status --short --untracked-files=all
```

Expected: tests pass, compileall exits 0, whitespace check is clean, and status
contains only intentional R6 files.

- [x] **Step 4: Scope review**

Change set holds only File Responsibility Map files: no frontend, auth,
vector memory, deletion API, planner state, Chroma memory writes,
unapproved RAG dependency, or Git delivery action. `git diff --stat` on
`backend/memory/extraction.py`, `backend/memory/policy.py`, and
`backend/storage/schema_registry.py` is empty.

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

- [x] **Step 6: Review checkpoint**

Return a READY_FOR_OWNER packet with changed files, verification evidence,
limitations, R6 report paths, feature-gate state, and remaining delivery gate.

Step 5 (mark `Completed` / `Accepted in working tree`) is intentionally
left unchecked: it requires repository-owner review acceptance first. No
`code-reviewer` subagent exists in this runtime, so review below is
implementer self-review against the spec/plan checklists plus fresh
verification; the owner review carries acceptance.

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

Plan version 0.1 was approved by the repository owner in conversation on
2026-09-05, together with approval of R6 spec version 0.1 and acceptance of ADR
0007. Implementation is authorized for an isolated worker following this plan.

No Git staging, commit, push, merge, release, or destructive cleanup is
authorized by approval of this file. Execution evidence, the recorded baseline,
and the final change set belong in this plan and in the repository-owner review
that follows.
