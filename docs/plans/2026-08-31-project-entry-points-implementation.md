# Project Entry Points Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the approved Package 2 root entry points so a new reader can
understand Travel Agent, start the current prototype honestly, and navigate to
the right governance, development, and architecture documents.

**Architecture:** `README.md` becomes the short product and repository gateway.
`DEVELOPMENT.md` owns normal setup, command side effects, and the verification
ledger. `ARCHITECTURE.md` owns only the implemented high-level online and
offline flows, with planned memory and trip workspaces labeled as future
direction.

**Tech Stack:** Markdown, repository-relative links, Mermaid fenced diagrams
where supported, POSIX shell, `rg`, `find`, `npm`, Docker Compose, Python 3.11
configuration, Node 18 configuration, FastAPI, Vite, Chroma, and Codebase
Memory evidence checks.

**Spec:** [Project Entry Points Design](../specs/2026-08-31-project-entry-points-design.md),
approved version 0.1.

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-08-31 |
| Approved specification | [Project Entry Points Design](../specs/2026-08-31-project-entry-points-design.md), version 0.1 |
| Execution owner | Coding agent after explicit plan approval |
| Decision owner | Repository owner |
| Scope | `README.md`, `DEVELOPMENT.md`, `ARCHITECTURE.md`, and approved routing and traceability updates only |
| Verification | Deterministic document checks, link checks, source/config evidence checks, Stage A startup and health smoke, and owner change-set review |

## Global Constraints

1. Do not execute this plan until the repository owner explicitly approves this
   exact plan.
2. Create exactly these Package 2 root files:
   - `README.md`
   - `DEVELOPMENT.md`
   - `ARCHITECTURE.md`
3. Modify only these existing files:
   - `AGENTS.md`
   - `CONTRIBUTING.md`
   - `docs/specs/2026-08-30-documentation-system-design.md`
   - `docs/specs/2026-08-31-project-entry-points-design.md`
   - `docs/specs/README.md`
   - `docs/plans/README.md`
   - `docs/plans/2026-08-31-project-entry-points-implementation.md`
4. Do not modify source code, tests, dependencies, CI, data files, runtime
   configuration, Dockerfiles, Git hooks, Git configuration, or GitHub settings.
5. Do not create Package 3-7 files, `LICENSE`, `SECURITY.md`, `CHANGELOG.md`,
   `THIRD_PARTY_NOTICES.md`, runbooks, evaluation documents, GitHub templates,
   or detailed architecture files.
6. Write repository artifacts in English.
7. Keep current behavior and future direction visibly separate.
8. Do not claim license, CI, test, coverage, security, production readiness,
   RAG quality, memory, authentication, trip workspaces, or SLO support without
   fresh evidence and an approved artifact that owns the claim.
9. The default quick start must not crawl, index, download a model, or make a
   paid or external model call. Disclose local startup writes before commands
   that may create or open Chroma state.
10. Stage B chat commands remain opt-in and may be listed as not run unless the
    repository owner gives execution-time permission for credentials, network,
    model download, data mutation, or paid external model calls.
11. Use Codebase Memory at Verify tier for material current architecture claims
    and call coverage checks for every relied-on code path.
12. Use `rg` and direct file reads for configuration, scripts, Dockerfiles,
    workflow files, and Markdown verification.
13. Preserve unrelated user changes and do not read, edit, stage, delete, or
    reference `a.txt`.
14. Do not create or switch branches, stage, commit, push, open a PR, merge, or
    release. The repository owner retains those actions.
15. Use `apply_patch` for manual file creation and edits.
16. Stop if verification contradicts the approved spec, a command has
    materially different side effects than documented, or a required link target
    does not exist.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `README.md` | Product identity, maturity, minimal Stage A quick start, limitations, and repository navigation | Approved Package 2 spec; source/config evidence |
| `DEVELOPMENT.md` | Toolchain status, setup paths, environment variables, command side effects, verification ledger, and common setup symptoms | Approved Package 2 spec; package scripts; Docker and backend configuration; verification commands |
| `ARCHITECTURE.md` | Current high-level component map, online request flow, offline data flow, trust boundaries, invariants, known gaps, and approved future-direction links | Approved Package 2 spec; Codebase Memory evidence; exact source/config reads |
| `AGENTS.md` | Add task-triggered routing pointers to the new development and architecture gateways | Existing agent routing model; Package 2 root docs |
| `CONTRIBUTING.md` | Replace Package 1's interim development-guide notice with a link to `DEVELOPMENT.md` | Existing contribution workflow; new development guide |
| `docs/specs/2026-08-30-documentation-system-design.md` | Keep derived-spec traceability current | Approved Package 0 design; Package 2 status |
| `docs/specs/2026-08-31-project-entry-points-design.md` | Link the implementation plan and preserve approval metadata | Approved Package 2 spec; this plan |
| `docs/specs/README.md` | Keep the specification index current | Package 2 spec status |
| `docs/plans/README.md` | Keep the plan index current | This Package 2 plan |
| `docs/plans/2026-08-31-project-entry-points-implementation.md` | Track execution checkbox state, verification evidence, and completion record | Approved Package 2 spec and owner plan approval |

## Task 1: Create the README Gateway

**Files:**

- Create: `README.md`
- Read: `docs/specs/2026-08-31-project-entry-points-design.md`
- Read: `backend/app/api/chat.py`
- Read: `backend/app/schemas/chat.py`
- Read: `frontend/src/services/api.js`
- Read: `docker-compose.yml`
- Read: `.env.example`

**Interfaces:**

- Consumes: approved README content contract from the Package 2 spec and
  current command/config evidence.
- Produces: a short root gateway linked by `AGENTS.md`, `CONTRIBUTING.md`, and
  future repository readers.

- [x] **Step 1: Confirm execution is authorized**

Run:

```bash
rg -n '^\| Status \| Approved \|$|Approve Package 2 spec version 0\.1' \
  docs/specs/2026-08-31-project-entry-points-design.md
rg -n '^\| Status \| Approved \|$' \
  docs/plans/2026-08-31-project-entry-points-implementation.md
```

Expected: the spec reports `Approved` and the plan reports `Approved`. Stop if
the plan remains `In Review`.

- [x] **Step 2: Write the README structure**

Create `README.md` with these top-level sections in this order:

```markdown
# Travel Agent

## Current Status
## What Works Today
## Quick Start
## Stage B: RAG Chat Readiness
## Repository Map
## Documentation
## Known Limitations
```

The first paragraph describes Travel Agent as an early open-source travel
assistant prototype using retrieval-augmented generation. It states that
evaluated trip planning, trip workspaces, and layered memory are planned
direction, not implemented behavior.

- [x] **Step 3: Add the minimal quick start**

The quick start includes a Stage A path only:

```bash
docker compose up --build
curl http://localhost:8000/health
```

Document before the commands that this may build images, install dependencies,
start local containers, and create or open local Chroma state through backend
startup. Document that Stage A does not prove retrieval quality, model access,
credentials, or end-to-end chat readiness.

- [x] **Step 4: Add Stage B readiness and limitations**

State that real chat can require:

- a configured external model credential,
- network access to the model provider,
- local embedding model availability or first-use download,
- populated Chroma data,
- and acceptance that the external model request contains the user message and
  retrieved travel context.

State that the current public chat request contains only `message`, with no
user, trip, conversation, or memory identifier.

- [x] **Step 5: Add navigation links**

Include links to existing files only:

- `DEVELOPMENT.md`
- `ARCHITECTURE.md`
- `CONTRIBUTING.md`
- `AGENTS.md`
- `docs/specs/README.md`
- `docs/plans/README.md`
- `docs/adr/README.md`

Do not link to Package 3 detailed architecture files, runbooks, evaluation
documents, roadmap, license, security policy, changelog, or GitHub templates.

- [x] **Step 6: Verify Task 1**

Run:

```bash
test -f README.md
rg -n '^## (Current Status|What Works Today|Quick Start|Stage B: RAG Chat Readiness|Repository Map|Documentation|Known Limitations)$' README.md
rg -n 'trip workspaces|layered memory|planned direction|not implemented behavior|/health|external model request|retrieved travel context' README.md
rg -n 'LICENSE|SECURITY\.md|CHANGELOG\.md|docs/architecture/current-state\.md|docs/evaluation|docs/runbooks|\.github' README.md
```

Expected: file test succeeds; required headings and maturity terms are present;
the final search returns no matches.

## Task 2: Create the Development Guide

**Files:**

- Create: `DEVELOPMENT.md`
- Read: `backend/Dockerfile`
- Read: `frontend/Dockerfile`
- Read: `docker-compose.yml`
- Read: `backend/requirements.txt`
- Read: `frontend/package.json`
- Read: `frontend/vite.config.js`
- Read: `backend/app/config.py`
- Read: `.github/workflows/ci.yml`
- Read: `.env.example`

**Interfaces:**

- Consumes: current toolchain, scripts, environment names, Docker paths, and
  Package 2 verification requirements.
- Produces: the canonical normal-development guide and verification ledger.

- [x] **Step 1: Write the development guide structure**

Create `DEVELOPMENT.md` with these top-level sections in this order:

```markdown
# Development

## Scope
## Toolchain Status
## Environment
## Recommended Path: Docker Compose
## Alternative Path: Host Processes
## Stage A: Startup and Health
## Stage B: RAG Chat Readiness
## Commands
## Opt-in Data and Model Operations
## Common Setup Symptoms
## Known Tooling Gaps
## Verification Ledger
```

- [x] **Step 2: Add toolchain and environment facts**

The Toolchain Status table separates `Configured`, `Verified`, and
`Supported policy`. Record Python 3.11 and Node 18 as configured from Docker
files. Record support policy as unknown. Record command verification status
only from fresh execution in this plan, using `not-run` until executed.

The Environment table includes variable names, purpose, requiredness, and
sensitivity. Include no real secret values. State that `.env.example` is
currently empty and is not complete setup guidance.

- [x] **Step 3: Document commands with side effects**

Group commands by working directory:

- repository root: `docker compose up --build`, `docker compose down`
- backend: `python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`,
  `pytest`
- frontend: `npm install`, `npm run dev`, `npm run build`, `npm run lint`,
  `npm run test`, `npm run preview`

For each command, state expected effect, local writes, network use, and current
verification result. Commands that were not run remain `not-run`.

- [x] **Step 4: Add Stage A and Stage B boundaries**

Stage A documents frontend/backend startup and `/health` inspection. Stage B
documents credential, network, embedding model, data, Chroma, and external
model payload prerequisites. Crawling, ETL, indexing, model download, and
model-dependent evaluation are opt-in and excluded from the default quick
start.

- [x] **Step 5: Execute allowed documentation verification commands**

Run these read-only provenance commands and record their results in the ledger:

```bash
rg -n '"(dev|build|lint|preview|test)"' frontend/package.json
rg -n 'FROM python:3\.11|FROM node:18|uvicorn|ports:|volumes:' backend/Dockerfile frontend/Dockerfile docker-compose.yml
rg -n 'OPENAI|API|MODEL|CHROMA|DATA|CACHE' backend/app/config.py frontend/src/services/api.js .env.example
```

Expected: commands exit 0 when matching configured facts. If a command exits 1
because no matches exist, record `verified-fail` only for the claimed fact it
was supposed to prove.

- [x] **Step 6: Verify Task 2**

Run:

```bash
test -f DEVELOPMENT.md
rg -n '^## (Scope|Toolchain Status|Environment|Recommended Path: Docker Compose|Alternative Path: Host Processes|Stage A: Startup and Health|Stage B: RAG Chat Readiness|Commands|Opt-in Data and Model Operations|Common Setup Symptoms|Known Tooling Gaps|Verification Ledger)$' DEVELOPMENT.md
rg -n 'configured|verified|supported policy|not-run|verified-pass|verified-fail|empty|masked CI|message prefix|external model request' DEVELOPMENT.md
rg -n 'real key|sk-|Bearer [A-Za-z0-9]|OPENAI_API_KEY=.*[^ ]' DEVELOPMENT.md
```

Expected: file test succeeds; required headings and ledger vocabulary are
present; the secret-pattern search returns no matches.

## Task 3: Create the Architecture Gateway

**Files:**

- Create: `ARCHITECTURE.md`
- Read: `backend/app/main.py`
- Read: `backend/app/api/chat.py`
- Read: `backend/app/api/health.py`
- Read: `backend/app/schemas/chat.py`
- Read: `backend/rag/generation/rag_service.py`
- Read: `backend/rag/embedding/embedder.py`
- Read: `backend/rag/retrieval/vector_store.py`
- Read: `backend/rag/indexing.py`
- Read: `frontend/src/services/api.js`
- Read: `docker-compose.yml`
- Read: `.github/workflows/ci.yml`

**Interfaces:**

- Consumes: Package 2 architecture content contract and Verify-tier source
  evidence.
- Produces: root architecture gateway for contributors and coding agents.

- [x] **Step 1: Reconfirm material source coverage**

Use Codebase Memory Verify tier to check coverage for these code paths:

```text
backend/app/main.py
backend/app/api/chat.py
backend/app/api/health.py
backend/app/schemas/chat.py
backend/rag/generation/rag_service.py
backend/rag/embedding/embedder.py
backend/rag/retrieval/vector_store.py
backend/rag/indexing.py
```

Expected: every relied-on path reports no recorded coverage issue and matching
filesystem metadata, or every reported missed range is read directly before
being used.

- [x] **Step 2: Write the architecture structure**

Create `ARCHITECTURE.md` with these top-level sections in this order:

```markdown
# Architecture

## Scope
## Current Components
## Online Request Flow
## Offline Data Flow
## Trust Boundaries
## Current Invariants
## Known Gaps
## Future Direction
## Architecture Change Rules
```

- [x] **Step 3: Document implemented components**

List only implemented or configured components: React/Vite client, FastAPI API,
RAG generation service, embedder, local Chroma vector store, offline
preprocessing/indexing, local data/model cache, and external model service.
Do not list PostgreSQL, workers, identity, trip projects, or agent memory as
current components.

- [x] **Step 4: Document online and offline flows**

Online flow: browser message posts to `/api/v1/chat`, backend strips and logs a
message prefix, process-global RAG service embeds the query, Chroma retrieval
returns context, generation sends user message plus retrieved travel context to
the configured external model endpoint, and the response returns reply, model,
and citations.

Offline flow: source data is cleaned, chunked, embedded, and upserted into
persistent Chroma collections. Label this flow opt-in and state-changing.

- [x] **Step 5: Document boundaries, invariants, and gaps**

Trust boundaries include browser-to-local API, local process-to-model provider,
local files/model cache/vector store, and untrusted retrieved text. Invariants
include one-message request contract, local persistent vector storage, and
health being narrower than chat readiness.

Known gaps include no user/trip/conversation/memory identifier in the bounded
chat request, no implemented agent memory, no production security or SLO claim,
permissive local CORS, message-prefix logging, masked CI tests, and no current
multi-service data platform.

- [x] **Step 6: Verify Task 3**

Run:

```bash
test -f ARCHITECTURE.md
rg -n '^## (Scope|Current Components|Online Request Flow|Offline Data Flow|Trust Boundaries|Current Invariants|Known Gaps|Future Direction|Architecture Change Rules)$' ARCHITECTURE.md
rg -n 'React/Vite|FastAPI|Chroma|embed|/api/v1/chat|retrieved travel context|message prefix|opt-in|state-changing|permissive local CORS' ARCHITECTURE.md
rg -n 'PostgreSQL|worker|trip project|agent memory|implemented memory|production-ready|SLO' ARCHITECTURE.md
```

Expected: file test succeeds; required headings and current facts are present.
The final search may match only in explicitly labeled future-direction or known
gap text, never as current implemented components.

## Task 4: Update Routing and Traceability

**Files:**

- Modify: `AGENTS.md`
- Modify: `CONTRIBUTING.md`
- Modify: `docs/specs/2026-08-30-documentation-system-design.md`
- Modify: `docs/specs/2026-08-31-project-entry-points-design.md`
- Modify: `docs/specs/README.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/plans/2026-08-31-project-entry-points-implementation.md`

**Interfaces:**

- Consumes: created Package 2 root files and existing governance indexes.
- Produces: discoverable routing from root docs to the new Package 2 entry
  points.

- [x] **Step 1: Update `AGENTS.md` routing**

Add task-triggered routing rows for:

- local development, setup, commands, environment, or toolchain -> `DEVELOPMENT.md`
- architecture overview, system flow, trust boundary, or current component map
  -> `ARCHITECTURE.md`

Do not change approval gates, Git safety, codebase discovery rules, or
verification rules.

- [x] **Step 2: Update `CONTRIBUTING.md`**

Replace the interim Package 1 development-guide notice with a link to
`DEVELOPMENT.md`. Preserve contribution ownership, branch/Git language, review
workflow, and approval gates.

- [x] **Step 3: Update spec and plan indexes**

Ensure:

- Package 2 spec status is `Approved` in `docs/specs/README.md`.
- Package 2 plan status is `In Progress` during implementation and
  `Completed` only after verification passes.
- Package 0 derived-spec metadata points to Package 2 as approved.
- Package 2 spec links this plan.
- This plan checkbox state reflects executed steps.

- [x] **Step 4: Verify Task 4**

Run:

```bash
rg -n 'DEVELOPMENT\.md|ARCHITECTURE\.md' AGENTS.md CONTRIBUTING.md
rg -n 'Project Entry Points Design.*Approved|Project Entry Points Implementation Plan.*In Progress|Project Entry Points Implementation Plan.*Completed' docs/specs/README.md docs/plans/README.md docs/specs/2026-08-30-documentation-system-design.md
rg -n 'Implementation plan .*2026-08-31-project-entry-points-implementation\.md' docs/specs/2026-08-31-project-entry-points-design.md
```

Expected: new routing links resolve; Package 2 metadata is consistent with the
actual execution state; no unrelated governance wording changed.

## Task 5: Run Package Verification and Self-review

**Files:**

- Read: all changed Package 2 files
- Modify: `docs/plans/2026-08-31-project-entry-points-implementation.md`
- Modify: `docs/plans/README.md`

**Interfaces:**

- Consumes: outputs from Tasks 1-4.
- Produces: final verification evidence, completed plan status, and a bounded
  change set ready for repository-owner review.

- [x] **Step 1: Inspect the complete change set**

Run:

```bash
git status --short --untracked-files=all
git diff -- AGENTS.md CONTRIBUTING.md docs/specs/README.md docs/plans/README.md docs/specs/2026-08-30-documentation-system-design.md docs/specs/2026-08-31-project-entry-points-design.md docs/plans/2026-08-31-project-entry-points-implementation.md
```

For untracked Package 2 root files, read them directly:

```bash
sed -n '1,260p' README.md
sed -n '1,360p' DEVELOPMENT.md
sed -n '1,320p' ARCHITECTURE.md
```

Expected: only approved Package 2 files and approved routing/metadata edits are
in scope. `a.txt` remains uninspected and untouched.

- [x] **Step 2: Check links and anchors**

Run:

```bash
rg -o '\]\(([^)#]+)(#[^)]+)?\)' README.md DEVELOPMENT.md ARCHITECTURE.md AGENTS.md CONTRIBUTING.md docs/specs/2026-08-31-project-entry-points-design.md docs/plans/2026-08-31-project-entry-points-implementation.md
```

For every repository-relative link target returned by the command, run
`test -e` from the linking file's directory. Expected: every live target exists.

- [x] **Step 3: Run Markdown quality checks**

Run:

```bash
rg -n '[[:blank:]]+$' README.md DEVELOPMENT.md ARCHITECTURE.md AGENTS.md CONTRIBUTING.md docs/specs/README.md docs/plans/README.md docs/specs/2026-08-30-documentation-system-design.md docs/specs/2026-08-31-project-entry-points-design.md docs/plans/2026-08-31-project-entry-points-implementation.md
rg -n 'T''ODO|T''BD|F''IXME|X''XX|P''LACEHOLDER|\x3c[^>]+\x3e' README.md DEVELOPMENT.md ARCHITECTURE.md AGENTS.md CONTRIBUTING.md docs/specs/README.md docs/plans/README.md docs/specs/2026-08-30-documentation-system-design.md docs/specs/2026-08-31-project-entry-points-design.md docs/plans/2026-08-31-project-entry-points-implementation.md
find README.md DEVELOPMENT.md ARCHITECTURE.md AGENTS.md CONTRIBUTING.md docs/specs docs/plans -name '*.md' -print
```

Expected: trailing-whitespace and drafting-marker searches return no matches
in Package 2 deliverables. Template placeholder tokens in approved workflow
indexes are allowed only inside explicit templates.

- [x] **Step 4: Run unsupported-claim checks**

Run:

```bash
rg -n 'production-ready|production ready|secure by default|SLO|SLA|tested|passing CI|coverage|licensed under|MIT|Apache|memory is implemented|trip workspace is implemented|authenticated|tenant' README.md DEVELOPMENT.md ARCHITECTURE.md
```

Expected: no unsupported claims. Matches are acceptable only when explicitly
describing absence, unknown status, future direction, or limitations.

- [x] **Step 5: Run Stage A smoke path**

Run the documented Stage A command only after confirming no secret values are
needed:

```bash
docker compose up --build
```

In a separate shell, run:

```bash
curl http://localhost:8000/health
```

Then stop the stack:

```bash
docker compose down
```

Expected: if the environment permits Docker and dependency downloads, `/health`
returns a health response and the DEVELOPMENT ledger records
`verified-pass`. If Docker, network, or dependency resolution is unavailable,
record `not-run` or `verified-fail` with the exact limitation and stop for owner
review if this violates the approved spec acceptance criteria.

- [x] **Step 6: Run optional command checks without side effects**

Run only commands that do not require credentials, paid calls, crawling,
indexing, or model downloads:

```bash
npm run build
npm run lint
npm run test -- --run
```

Expected: record each result in DEVELOPMENT. Do not change frontend source,
dependencies, lint config, tests, or CI to repair failures under Package 2.

- [x] **Step 7: Final self-review against acceptance criteria**

Review all 12 Package 2 acceptance criteria in the approved spec and record the
result in this plan's Completion Record. Expected: every accepted criterion is
either met with evidence or explicitly blocked with a reason requiring owner
review.

- [x] **Step 8: Mark plan completed after evidence passes**

If and only if required verification passes or owner-approved limitations are
recorded, update this plan status to `Completed`, update the plan index to
`Completed`, and write the Completion Record with date, verification summary,
changed files, and remaining repository-owner change-set review gate.

## Package Verification

Execution must produce fresh evidence for:

1. Complete change set including untracked files.
2. Relative link resolution for every live Package 2 link.
3. Markdown trailing whitespace, drafting markers, heading structure, and fence
   balance.
4. Unsupported maturity, security, license, CI, test, evaluation, memory,
   workspace, and production-readiness claims.
5. Codebase Memory coverage for every material source path used in
   `ARCHITECTURE.md`.
6. Command provenance from package scripts, Dockerfiles, Docker Compose,
   backend configuration, frontend configuration, `.env.example`, and CI.
7. Stage A startup and `/health` smoke, or an explicit owner-reviewed blocker.
8. No Stage B chat, crawling, indexing, model download, or paid external model
   call unless separately authorized at execution time.
9. Exact plan checkbox state and metadata matching actual execution state.

## Rollback

Before Git delivery, rollback removes only:

1. `README.md`
2. `DEVELOPMENT.md`
3. `ARCHITECTURE.md`
4. Package 2 routing edits in `AGENTS.md`
5. Package 2 interim notice replacement in `CONTRIBUTING.md`
6. Package 2 status and traceability edits in spec and plan indexes

Rollback must use `apply_patch` or another non-destructive file edit method and
must not touch `a.txt`, source code, data, tests, dependencies, CI, Git history,
or unrelated untracked files.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-08-31 via the exact
conversation phrase `Approve Package 2 implementation plan`. Approval
authorizes implementation of Package 2 only.

## Completion Record

Implementation completed on 2026-08-31 after the Stage A smoke rerun passed in
an escalated local shell.

Self-review on 2026-08-31:

1. Root files `README.md`, `DEVELOPMENT.md`, and `ARCHITECTURE.md` exist.
2. README separates current RAG behavior from planned memory and trip
   workspaces.
3. README and DEVELOPMENT document Stage A, and the rerun verified
   `docker compose up --build` plus backend `/health` in an escalated local
   shell. The normal sandboxed Docker and localhost checks still fail due
   Docker socket and local port access limits.
4. DEVELOPMENT contains host and Docker paths, environment variable names,
   command effects, side effects, known gaps, and a dated verification ledger.
5. The default quick start excludes crawling, indexing, model download, and paid
   external model calls; local Docker and Chroma side effects are disclosed.
6. ARCHITECTURE maps the current online and offline flows without presenting
   planned memory, identity, trip workspaces, workers, or data-platform work as
   current components.
7. Current-state material claims cite source or configuration paths; Codebase
   Memory coverage for material code paths returned `no_recorded_issue` and
   `metadata_match` at generation `2026-08-31T00:12:09Z`.
8. Configured, verified, supported, failed, and not-run states are separated in
   DEVELOPMENT.
9. Local Markdown links resolve and Markdown fence counts are balanced.
10. `AGENTS.md` and `CONTRIBUTING.md` routing changes are limited to Package 2.
11. Documentation checks pass, frontend build passes, frontend lint/test fail
    with recorded tooling causes, and Stage A Docker/health smoke passes in an
    escalated local shell. `docker compose down` removed the Stage A frontend
    and backend containers; the project network remained in use because
    pre-existing orphan containers were outside Package 2 scope.
12. The exact change set was accepted by the repository owner on 2026-08-31 via
    the conversation phrase `accept change set`. Package 2 plan execution is
    completed, but Git delivery remains under repository-owner control.

Remaining gate: repository-owner Git delivery decision before any stage,
commit, push, PR, merge, or release action.
