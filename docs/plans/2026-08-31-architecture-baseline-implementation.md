# Architecture Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the approved Package 3 detailed architecture baseline so
current implementation, target architecture, and conceptual data model are
separate, reviewable, and safe for future implementation planning.

**Architecture:** Package 3 implements documentation only. The root
`ARCHITECTURE.md` remains the high-level gateway; detailed current state,
target state, and data model move into focused files under `docs/architecture/`.
The approved direction is workspace-first layered memory with explicit module
seams and future ADRs before runtime implementation.

**Tech Stack:** Markdown, Mermaid fenced diagrams where useful, Codebase Memory
Verify-tier evidence, `rg`, direct source reads, Ruby link checking, POSIX
shell, FastAPI, React/Vite, Chroma, Python 3.11 configuration, Node 18
configuration, and Docker Compose configuration.

**Spec:** [Architecture Baseline Design](../specs/2026-08-31-architecture-baseline-design.md),
approved version 0.1 with architecture approval.

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-08-31 |
| Approved specification | [Architecture Baseline Design](../specs/2026-08-31-architecture-baseline-design.md), version 0.1 |
| Execution owner | Coding agent after explicit plan approval |
| Decision owner | Repository owner |
| Scope | `docs/architecture/current-state.md`, `docs/architecture/target-state.md`, `docs/architecture/data-model.md`, root architecture routing, and approved traceability updates only |
| Verification | Codebase Memory Verify-tier evidence, direct source reads, deterministic Markdown checks, link checks, unsupported-claim scans, final scope review, and owner change-set review |

## Global Constraints

1. Do not execute this plan until the repository owner explicitly approves this
   exact plan.
2. Create exactly these Package 3 architecture files:
   - `docs/architecture/current-state.md`
   - `docs/architecture/target-state.md`
   - `docs/architecture/data-model.md`
3. Modify only these existing files:
   - `ARCHITECTURE.md`
   - `docs/specs/2026-08-31-architecture-baseline-design.md`
   - `docs/plans/README.md`
   - `docs/plans/2026-08-31-architecture-baseline-implementation.md`
4. Do not modify source code, tests, dependencies, CI, runtime configuration,
   Dockerfiles, data files, Git hooks, Git configuration, GitHub settings,
   Package 4-7 files, ADR files, runbooks, evaluation protocol files, license
   files, security policy files, or changelog files.
5. Write repository artifacts in English.
6. Keep current behavior and target architecture visibly separate.
7. Do not claim memory, trip workspaces, authentication, user accounts,
   production security, tenant isolation, SLOs, production deployment, test
   health, RAG quality, or evaluation quality as implemented behavior.
8. The current request contract remains `message` only until a later approved
   runtime implementation changes it.
9. Use Codebase Memory at Verify tier for material current-state architecture
   claims and call coverage checks for every cited source path.
10. Use direct source reads for every material implemented-behavior claim and
    for non-code configuration.
11. Do not run Stage B chat, crawling, indexing, model downloads, paid external
    model calls, dependency installation, Docker build, or migration commands
    for Package 3 verification.
12. Preserve unrelated user changes. Do not create or switch branches, stage,
    commit, push, open a PR, merge, or release.
13. Use `apply_patch` for manual file creation and edits.
14. Stop if evidence contradicts the approved architecture design, scope
    expands, a required link target is missing, or a new durable runtime
    decision becomes necessary before documentation can proceed.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `docs/architecture/current-state.md` | Detailed evidence-backed baseline of the implemented prototype, current flows, contracts, storage, runtime paths, and gaps | Approved Package 3 design, root architecture gateway, Codebase Memory evidence, direct source reads |
| `docs/architecture/target-state.md` | Proposed target architecture for workspace-first layered memory, module seams, dependency direction, rollout stages, failure handling, and required ADRs | Approved Package 3 design and current-state baseline |
| `docs/architecture/data-model.md` | Conceptual target entities, relationships, memory scopes, retrieval objects, evaluation traces, lifecycle states, and compatibility constraints | Approved Package 3 design and target-state module map |
| `ARCHITECTURE.md` | Keep root gateway concise and route readers to detailed Package 3 architecture documents without duplicating them | New detailed architecture documents |
| `docs/specs/2026-08-31-architecture-baseline-design.md` | Link the Package 3 implementation plan and preserve approval metadata | This plan |
| `docs/plans/README.md` | Keep the implementation plan index current | This plan |
| `docs/plans/2026-08-31-architecture-baseline-implementation.md` | Track execution checkbox state, verification evidence, completion record, and remaining owner gates | Approved Package 3 design and owner plan approval |

## Task 1: Create Detailed Current-state Architecture

**Files:**

- Create: `docs/architecture/current-state.md`
- Read: `ARCHITECTURE.md`
- Read: `docs/specs/2026-08-31-architecture-baseline-design.md`
- Read: `backend/app/main.py`
- Read: `backend/app/api/chat.py`
- Read: `backend/app/api/health.py`
- Read: `backend/app/schemas/chat.py`
- Read: `frontend/src/services/api.js`
- Read: `backend/rag/generation/rag_service.py`
- Read: `backend/rag/embedding/embedder.py`
- Read: `backend/rag/retrieval/vector_store.py`
- Read: `backend/rag/indexing.py`
- Read: `backend/app/config.py`
- Read: `docker-compose.yml`
- Read: `backend/Dockerfile`
- Read: `frontend/Dockerfile`
- Read: `frontend/package.json`
- Read: `.github/workflows/ci.yml`
- Read: `.env.example`

**Interfaces:**

- Consumes: approved Package 3 current-state evidence requirements and current
  source/config evidence.
- Produces: a detailed baseline that later target-state and data-model
  documents can cite as the implemented starting point.

- [x] **Step 1: Confirm plan execution is authorized**

Run:

```bash
rg -n '^\| Status \| Approved \|$|architecture approval|Architecture Baseline Design' docs/specs/2026-08-31-architecture-baseline-design.md
rg -n '^\| Status \| Approved \|$' docs/plans/2026-08-31-architecture-baseline-implementation.md
```

Expected: the spec reports `Approved`, records architecture approval, and the
plan reports `Approved`. Stop if this plan remains `In Review`.

- [x] **Step 2: Refresh Codebase Memory evidence**

Use Codebase Memory with project
`Users-tnhatnguyendev2805-Documents-Projects-travel-agent`:

1. `index_status` for project freshness and parse coverage.
2. `get_architecture` with aspects `overview`, `entry_points`, `routes`,
   `dependencies`, `layers`, and `clusters`.
3. `trace_path` for `chat_endpoint`, direction `outbound`, depth `3`.
4. `trace_path` for `generate_answer`, direction `outbound`, depth `3`.
5. `get_code_snippet` for `chat_endpoint`.
6. `get_code_snippet` for `RAGService.generate_answer`.
7. `get_code_snippet` for `VectorEmbedder`.
8. `get_code_snippet` for `ChromaVectorStore`.
9. `check_index_coverage` for every source and config path cited in this task.

Expected: cited material paths return no recorded coverage issue or every
reported missed range is read directly before use. Record generation timestamp,
project name, and caveat in `current-state.md`.

- [x] **Step 3: Read non-code and source evidence directly**

Run:

```bash
sed -n '1,220p' backend/app/main.py
sed -n '1,220p' backend/app/api/chat.py
sed -n '1,220p' backend/app/api/health.py
sed -n '1,220p' backend/app/schemas/chat.py
sed -n '1,220p' frontend/src/services/api.js
sed -n '1,260p' backend/rag/generation/rag_service.py
sed -n '1,220p' backend/rag/embedding/embedder.py
sed -n '1,260p' backend/rag/retrieval/vector_store.py
sed -n '1,260p' backend/rag/indexing.py
sed -n '1,220p' backend/app/config.py
sed -n '1,220p' docker-compose.yml
sed -n '1,220p' backend/Dockerfile
sed -n '1,220p' frontend/Dockerfile
sed -n '1,220p' frontend/package.json
sed -n '1,220p' .github/workflows/ci.yml
wc -c .env.example
```

Expected: direct reads support the current-state statements; `.env.example`
size is used only to support empty or incomplete setup guidance claims.

- [x] **Step 4: Write `current-state.md`**

Create the document with these top-level sections in this order:

```markdown
# Current-state Architecture

## Scope
## Evidence Basis
## Runtime Components
## Online Chat Flow
## Current Request and Response Contracts
## RAG Module Shape
## Offline Data Preparation
## Local Runtime and Configuration
## Current Data and Persistence
## Current Tests and Verification Signals
## Current Gaps and Risks
## Compatibility Baseline
```

Required content:

1. State that the current system is an early RAG prototype.
2. Cite Codebase Memory project and generation timestamp.
3. List implemented runtime components only.
4. Show the online request path from frontend to FastAPI to RAG to Chroma to
   external model.
5. State that the public chat request contains only `message`.
6. State that current chat response contains `reply`, `model`, and
   `citations`.
7. Separate Stage A health readiness from Stage B chat readiness.
8. Record that there is no implemented memory read/write, trip workspace,
   identity lookup, planner module, or evaluation trace write in the bounded
   online route.
9. Describe offline indexing as opt-in and state-changing.
10. Avoid target architecture requirements except in the gap list.

- [x] **Step 5: Verify Task 1**

Run:

```bash
test -f docs/architecture/current-state.md
rg -n '^## (Scope|Evidence Basis|Runtime Components|Online Chat Flow|Current Request and Response Contracts|RAG Module Shape|Offline Data Preparation|Local Runtime and Configuration|Current Data and Persistence|Current Tests and Verification Signals|Current Gaps and Risks|Compatibility Baseline)$' docs/architecture/current-state.md
rg -n 'early RAG prototype|message|reply|model|citations|Stage A|Stage B|no implemented memory|trip workspace|planner module|evaluation trace' docs/architecture/current-state.md
```

Expected: file exists, all headings are present, and required maturity and
current-gap language is present.

- [x] **Step 6: Review checkpoint**

Review:

```bash
sed -n '1,360p' docs/architecture/current-state.md
```

Expected: every implemented-behavior claim is supported by evidence, and the
document does not describe proposed memory or trip workspaces as current
behavior.

## Task 2: Create Target-state Architecture

**Files:**

- Create: `docs/architecture/target-state.md`
- Read: `docs/specs/2026-08-31-architecture-baseline-design.md`
- Read: `docs/architecture/current-state.md`
- Read: `docs/adr/README.md`

**Interfaces:**

- Consumes: approved Package 3 selected approach and Task 1 current-state
  baseline.
- Produces: target module and flow documentation that future specs, plans, and
  ADRs can use without implying implementation.

- [x] **Step 1: Write `target-state.md`**

Create the document with these top-level sections in this order:

```markdown
# Target-state Architecture

## Scope
## Target Principles
## Product Container: Trip Workspace
## Target Module Map
## Dependency Direction
## Layered Memory Architecture
## Context Assembly Flow
## Trip Planning Flow
## Memory Write and Promotion Flow
## Evaluation and Trace Flow
## Security and Privacy Boundaries
## Failure and Recovery
## Capacity, Latency, and Cost Budgets
## Staged Migration
## Required ADRs
## Open Implementation Questions
```

Required content:

1. State that the document is proposed target architecture, not implemented
   behavior.
2. Define trip workspace as the primary product container for one planned trip.
3. Define modules and interfaces for client experience, backend application,
   conversation orchestrator, workspace, memory, knowledge retrieval, planner,
   generation, evaluation/trace, and storage adapters.
4. Use the words `module`, `interface`, `seam`, and `adapter` consistently.
5. Show dependency direction from UI/routes to orchestration to module
   interfaces to adapters.
6. Keep knowledge retrieval separate from user and trip memory.
7. Define context assembly as evidence-bearing and scoped.
8. Define staged rollout: baseline preservation, workspace scaffolding, shadow
   memory extraction, evaluated memory retrieval, planner state writes.
9. List the required ADRs from the approved design.

- [x] **Step 2: Verify Task 2**

Run:

```bash
test -f docs/architecture/target-state.md
rg -n '^## (Scope|Target Principles|Product Container: Trip Workspace|Target Module Map|Dependency Direction|Layered Memory Architecture|Context Assembly Flow|Trip Planning Flow|Memory Write and Promotion Flow|Evaluation and Trace Flow|Security and Privacy Boundaries|Failure and Recovery|Capacity, Latency, and Cost Budgets|Staged Migration|Required ADRs|Open Implementation Questions)$' docs/architecture/target-state.md
rg -n 'proposed target architecture|not implemented behavior|Trip Workspace|module|interface|seam|adapter|shadow memory extraction|Required ADRs' docs/architecture/target-state.md
```

Expected: file exists, all headings are present, and required target
architecture vocabulary is present.

- [x] **Step 3: Review checkpoint**

Review:

```bash
sed -n '1,420p' docs/architecture/target-state.md
```

Expected: target architecture is concrete enough to guide later implementation
without choosing unapproved storage vendors or claiming runtime behavior.

## Task 3: Create Conceptual Data Model

**Files:**

- Create: `docs/architecture/data-model.md`
- Read: `docs/specs/2026-08-31-architecture-baseline-design.md`
- Read: `docs/architecture/current-state.md`
- Read: `docs/architecture/target-state.md`
- Read: `backend/app/schemas/chat.py`
- Read: `backend/rag/retrieval/vector_store.py`

**Interfaces:**

- Consumes: target-state modules and approved Package 3 entity list.
- Produces: conceptual data model and lifecycle documentation for later storage
  ADRs and implementation specs.

- [x] **Step 1: Write `data-model.md`**

Create the document with these top-level sections in this order:

```markdown
# Data Model

## Scope
## Current Implemented Contracts
## Target Entity Overview
## Relationship Map
## User and Workspace Records
## Conversation and Message Records
## Trip Planning Records
## Memory Records
## Memory Candidate Records
## Knowledge and Retrieval Records
## Context Bundle Records
## Evaluation Trace Records
## Lifecycle and Retention States
## Privacy and Deletion Semantics
## Compatibility With Current Chat
## Deferred Physical Storage Decisions
```

Required content:

1. State that this is a conceptual target model, not a physical database schema.
2. Preserve the current implemented chat request and response contracts.
3. Define target entities for user, trip workspace, conversation, message,
   itinerary version, trip decision, memory record, memory candidate, knowledge
   document, retrieval chunk, context bundle, and evaluation trace.
4. Include relationship diagrams or tables showing user-to-workspace,
   workspace-to-conversation, conversation-to-message,
   message-to-memory-candidate, memory-to-provenance, and
   trace-to-context-bundle relationships.
5. Define memory fields: scope, type, normalized content, provenance,
   confidence, timestamps, retention state, and deletion state.
6. Define scope values at least for user, trip workspace, conversation, global
   knowledge, and evaluation run.
7. Define lifecycle states without choosing a concrete database vendor.
8. State that physical storage ownership is deferred to ADRs.

- [x] **Step 2: Verify Task 3**

Run:

```bash
test -f docs/architecture/data-model.md
rg -n '^## (Scope|Current Implemented Contracts|Target Entity Overview|Relationship Map|User and Workspace Records|Conversation and Message Records|Trip Planning Records|Memory Records|Memory Candidate Records|Knowledge and Retrieval Records|Context Bundle Records|Evaluation Trace Records|Lifecycle and Retention States|Privacy and Deletion Semantics|Compatibility With Current Chat|Deferred Physical Storage Decisions)$' docs/architecture/data-model.md
rg -n 'conceptual target model|not a physical database schema|message|reply|model|citations|MemoryRecord|MemoryCandidate|EvaluationTrace|physical storage ownership is deferred' docs/architecture/data-model.md
```

Expected: file exists, all headings are present, implemented contracts are
preserved, and target entities are covered.

- [x] **Step 3: Review checkpoint**

Review:

```bash
sed -n '1,460p' docs/architecture/data-model.md
```

Expected: data model is explicit enough to support later ADRs and Package 5
evaluation work while remaining vendor-neutral.

## Task 4: Update Routing, Traceability, and Final Verification

**Files:**

- Modify: `ARCHITECTURE.md`
- Modify: `docs/specs/2026-08-31-architecture-baseline-design.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/plans/2026-08-31-architecture-baseline-implementation.md`
- Read: `docs/architecture/current-state.md`
- Read: `docs/architecture/target-state.md`
- Read: `docs/architecture/data-model.md`

**Interfaces:**

- Consumes: completed Package 3 architecture files.
- Produces: discoverable routing from the root gateway and current plan status
  metadata for owner review.

- [x] **Step 1: Update root architecture gateway**

Modify `ARCHITECTURE.md` only to add a concise routing section or paragraph
that points to these files after they exist:

1. `docs/architecture/current-state.md`
2. `docs/architecture/target-state.md`
3. `docs/architecture/data-model.md`

Expected: root `ARCHITECTURE.md` remains a concise gateway and does not
duplicate the detailed Package 3 documents.

- [x] **Step 2: Update traceability metadata**

Modify:

1. `docs/specs/2026-08-31-architecture-baseline-design.md` so
   `Implementation plan` links to
   `../plans/2026-08-31-architecture-baseline-implementation.md`, version 0.1,
   with status `(Approved; In Progress)` only during execution and
   `(Approved; Completed)` after final verification passes.
2. `docs/plans/README.md` so the Plan Index contains the Package 3 row.
3. This plan's `Status` and checkbox state to match actual execution.

Expected: metadata reflects actual execution state and does not imply Git
delivery.

- [x] **Step 3: Run link checks**

Run:

```bash
ruby -e 'missing=[]; ARGV.each do |f|; dir=File.dirname(f); File.read(f).scan(/\[[^\]]+\]\(([^)]+)\)/).flatten.each do |href|; path=href.split("#",2)[0]; next if path.empty? || path =~ /^[a-z][a-z0-9+.-]*:/ || path.start_with?("mailto:"); target=File.expand_path(path, dir); missing.push("#{f} -> #{href}") unless File.exist?(target); end; end; if missing.empty?; puts "all local markdown links resolve"; else; puts missing; exit 1; end' ARCHITECTURE.md docs/architecture/current-state.md docs/architecture/target-state.md docs/architecture/data-model.md docs/specs/2026-08-31-architecture-baseline-design.md docs/plans/2026-08-31-architecture-baseline-implementation.md docs/plans/README.md
```

Expected: `all local markdown links resolve`.

- [x] **Step 4: Run Markdown quality checks**

Run:

```bash
rg -n '[[:blank:]]+$' ARCHITECTURE.md docs/architecture/current-state.md docs/architecture/target-state.md docs/architecture/data-model.md docs/specs/2026-08-31-architecture-baseline-design.md docs/plans/2026-08-31-architecture-baseline-implementation.md docs/plans/README.md
rg -n 'T''ODO|T''BD|F''IXME|X''XX|P''LACEHOLDER|\x3c[^>]+\x3e' ARCHITECTURE.md docs/architecture/current-state.md docs/architecture/target-state.md docs/architecture/data-model.md docs/specs/2026-08-31-architecture-baseline-design.md docs/plans/2026-08-31-architecture-baseline-implementation.md docs/plans/README.md
awk 'BEGIN { bad=0 } /^```/ { fences[FILENAME]++ } END { for (f in fences) { if (fences[f] % 2) { print f ": odd fence count"; bad=1 } } if (!bad) print "markdown fence counts balanced"; exit bad }' ARCHITECTURE.md docs/architecture/current-state.md docs/architecture/target-state.md docs/architecture/data-model.md docs/specs/2026-08-31-architecture-baseline-design.md docs/plans/2026-08-31-architecture-baseline-implementation.md docs/plans/README.md
```

Expected: trailing-whitespace and drafting-marker searches return no matches;
fence check reports balanced counts.

- [x] **Step 5: Run unsupported-claim checks**

Run:

```bash
rg -n 'production-ready|production ready|secure by default|SLO|SLA|tested|passing CI|coverage|licensed under|MIT|Apache|memory is implemented|trip workspace is implemented|authenticated|tenant' ARCHITECTURE.md docs/architecture/current-state.md docs/architecture/target-state.md docs/architecture/data-model.md docs/specs/2026-08-31-architecture-baseline-design.md
```

Expected: no unsupported claims. Matches are acceptable only when explicitly
describing absence, unknown status, future direction, or limitations.

- [x] **Step 6: Run final scope review**

Run:

```bash
git status --short --untracked-files=all
sed -n '1,360p' docs/architecture/current-state.md
sed -n '1,420p' docs/architecture/target-state.md
sed -n '1,460p' docs/architecture/data-model.md
sed -n '1,220p' ARCHITECTURE.md
```

Expected: only approved Package 3 files and approved routing/metadata edits are
new or changed for this package. Source, tests, dependencies, CI, runtime
configuration, data, Git state, and unrelated files remain untouched.

- [x] **Step 7: Final self-review against acceptance criteria**

Review all 12 Package 3 acceptance criteria in the approved design and record
the result in this plan's Completion Record.

Expected: every accepted criterion is met with evidence or execution stops
with the exact blocker.

- [x] **Step 8: Mark plan completed after evidence passes**

If and only if required verification passes, update this plan status to
`Completed`, update the plan index to `Completed`, update the spec
implementation-plan field to `(Approved; Completed)`, and write the Completion
Record with date, verification summary, changed files, and remaining
repository-owner change-set review gate.

## Package Verification

Execution must produce fresh evidence for:

1. Complete change set including untracked files.
2. Codebase Memory project, generation, traces, snippets, and coverage for
   every material current-state source path.
3. Direct source reads for material current-state claims.
4. Relative link resolution for every live Package 3 link.
5. Markdown trailing whitespace, drafting markers, heading structure, and fence
   balance.
6. Unsupported maturity, security, license, CI, test, evaluation, memory,
   workspace, authentication, tenant-isolation, SLO, and production-readiness
   claims.
7. Exact plan checkbox state and metadata matching actual execution state.
8. No Stage B chat, crawling, indexing, model download, paid external model
   call, dependency installation, Docker build, migration, or runtime source
   change.
9. Repository-owner review of the exact Package 3 change set before Git
   delivery.

## Rollback

Before Git delivery, rollback removes only:

1. `docs/architecture/current-state.md`
2. `docs/architecture/target-state.md`
3. `docs/architecture/data-model.md`
4. Package 3 routing edits in `ARCHITECTURE.md`
5. Package 3 traceability edits in
   `docs/specs/2026-08-31-architecture-baseline-design.md`
6. Package 3 plan index edits in `docs/plans/README.md`
7. `docs/plans/2026-08-31-architecture-baseline-implementation.md`

Rollback must use `apply_patch` or another non-destructive file edit method and
must not touch source code, tests, dependencies, CI, data, runtime
configuration, Git history, accepted Package 0-2 files, or unrelated untracked
files.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-08-31 via the exact
conversation phrase `Approve Package 3 implementation plan`. Approval
authorizes implementation of Package 3 documentation only. It does not
authorize runtime changes, source changes, ADR creation, data migration,
dependency changes, Git staging, commit, push, PR, merge, or release.

## Completion Record

Completed on 2026-08-31.

Changed files:

1. Added `docs/architecture/current-state.md`.
2. Added `docs/architecture/target-state.md`.
3. Added `docs/architecture/data-model.md`.
4. Updated `ARCHITECTURE.md` to route readers to the detailed Package 3
   architecture documents.
5. Updated `docs/specs/2026-08-31-architecture-baseline-design.md` to record
   this implementation plan as approved and completed.
6. Updated `docs/plans/README.md` to mark the Package 3 plan completed.
7. Updated this plan's status, task checklist, and completion record.

Verification summary:

1. Codebase Memory was used at Verify tier for current-state architecture
   evidence. The selected graph project was
   `Users-tnhatnguyendev2805-Documents-Projects-travel-agent`, generation
   `2026-08-31T03:52:54Z`, with exact traces, snippets, direct source reads,
   and index coverage checks recorded during execution.
2. `docs/architecture/current-state.md` records the implemented prototype,
   current chat request and response contracts, RAG flow, storage, runtime
   configuration, tests, gaps, and compatibility baseline without claiming
   unimplemented memory, workspace, planner, authentication, tenant isolation,
   production readiness, or CI maturity.
3. `docs/architecture/target-state.md` records the proposed workspace-first
   target architecture, layered-memory flow, interfaces, adapter boundaries,
   evaluation flow, security and privacy boundaries, staged migration, required
   ADRs, and open implementation questions as target design rather than
   implemented behavior.
4. `docs/architecture/data-model.md` records the conceptual target model for
   users, trip workspaces, conversations, plans, memory records, retrieval
   records, context bundles, evaluation traces, lifecycle states, deletion
   semantics, and deferred physical storage decisions.
5. Local Markdown link checks resolved all Package 3 links.
6. Markdown quality checks found no trailing whitespace, no drafting markers,
   and balanced fenced-code blocks.
7. Unsupported-claim scanning produced only acceptable matches that describe
   absence, limits, target responsibility, or verification evidence rather than
   implemented maturity.
8. Final scope review showed only approved documentation, routing, and
   traceability files in scope for this package; no source, test, dependency,
   CI, data, runtime configuration, migration, Docker, indexing, crawling, or
   model-download work was performed.

Acceptance criteria review:

1. The root architecture gateway links to the detailed architecture documents.
2. The current-state document identifies implemented components and flows with
   evidence-backed caveats.
3. The current request and response contract is preserved as `message` in and
   `reply`, `model`, and `citations` out.
4. The current-state document records that memory, trip workspace, planner, and
   evaluation trace behavior are not implemented in the online path.
5. The target-state document defines a workspace-first architecture for travel
   planning.
6. The target-state document defines layered memory, context assembly, memory
   write and promotion, and evaluation trace flows.
7. The target-state document defines module boundaries, dependency direction,
   and adapter responsibilities.
8. The target-state document lists required ADRs before runtime implementation.
9. The data-model document defines the conceptual model and relationships for
   trip workspaces, memory, retrieval, context bundles, and evaluation traces.
10. The data-model document preserves compatibility with the existing chat
    contract and defers physical storage decisions.
11. The implementation stayed within approved Package 3 documentation scope.
12. Repository-owner change-set review was accepted before Git delivery.

Repository-owner change-set review was accepted on 2026-08-31 via the exact
conversation phrase `accept Package 3 change set`.

Remaining gate: Git delivery remains with the repository owner.
