# Project Entry Points Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-08-31 |
| Change class | Level 2 - Feature Spec |
| Decision owner | Repository owner |
| Scope | Documentation Package 2 - project entry points |
| Parent design | [Documentation System Design](./2026-08-30-documentation-system-design.md), version 0.1 |
| Depends on | [Agent Operating System Design](./2026-08-30-agent-operating-system-design.md), version 0.1 |
| Implementation plan | [Project Entry Points Implementation Plan](../plans/2026-08-31-project-entry-points-implementation.md), version 0.1 (Approved; Completed) |
| Related issue | None - approval of version 0.1 records the repository-owner exception for this conversation intake |

## Summary

Package 2 creates three concise project entry points: `README.md`,
`DEVELOPMENT.md`, and `ARCHITECTURE.md`. Together they let a new contributor
identify the product, start the currently implemented prototype, understand its
major runtime path, and reach the correct canonical documentation without
mistaking planned memory or platform work for existing behavior.

The selected approach is evidence-first and maturity-aware. `README.md` remains
a short product and navigation gateway. `DEVELOPMENT.md` owns detailed setup and
normal development commands. `ARCHITECTURE.md` maps only the implemented
high-level system and clearly labels future direction. Executable configuration
remains authoritative for exact dependency and script definitions.

Approval of this specification authorizes preparation of a separate Package 2
implementation plan. It does not authorize creation of the three entry-point
documents or changes to source, dependencies, CI, data, or runtime architecture.

## Parent Decisions

This specification inherits these approved documentation decisions:

1. Root documents are concise gateways; detailed material lives under `docs/`.
2. Every persistent change requires an approved specification and plan.
3. Current facts and proposed target state must be visibly distinct.
4. Executable configuration remains authoritative for cheap-to-discover values.
5. Documentation links point only to files that exist in the same reviewed
   change or already exist.
6. Technical repository documentation is written in English.
7. The repository owner reviews the exact change set and controls Git delivery.
8. Empty or speculative placeholders are not created.

Package 2 may operationalize these decisions but may not change the application
architecture or the documentation ownership model.

## Context and Evidence

Travel Agent is an early RAG prototype, not yet the planned trip-workspace and
memory platform. The current browser flow sends one message to a FastAPI
endpoint, retrieves Chroma records with a local embedding model, and sends the
retrieved context to an OpenAI-compatible chat-completions endpoint. The public
request contract contains only `message`; the bounded active request flow has no
user, trip, conversation, or memory identifier.

The baseline was checked at Codebase Memory Verify tier against generation
`2026-08-30T13:53:30Z`. All cited code and configuration paths reported no
recorded coverage issue and matching filesystem metadata. This is a best-effort
index signal, not proof of semantic completeness. Exact source and configuration
were read for material claims.

| Evidence | Current fact relevant to Package 2 |
| --- | --- |
| [`backend/app/main.py`](../../backend/app/main.py) | FastAPI mounts `/health` and the chat router under `/api/v1`; startup attempts to pre-warm the RAG service but converts failures to warnings. |
| [`backend/app/api/chat.py`](../../backend/app/api/chat.py) | `POST /api/v1/chat` strips one message, logs a prefix of it, uses a process-global RAG service, requests up to four retrieval results, and returns reply, model, and citations. |
| [`backend/app/schemas/chat.py`](../../backend/app/schemas/chat.py) | The request contains only `message`; the response contains `reply`, `model`, and `citations`. |
| [`frontend/src/services/api.js`](../../frontend/src/services/api.js) | The browser posts to `${VITE_API_URL}/api/v1/chat`, defaulting the origin to `http://localhost:8000`. |
| [`backend/rag/generation/rag_service.py`](../../backend/rag/generation/rag_service.py) | Generation embeds the query, searches Chroma, builds context and citations, and calls the configured external model endpoint. |
| [`backend/rag/embedding/embedder.py`](../../backend/rag/embedding/embedder.py) | The configured embedding model is `BAAI/bge-m3` and may be downloaded on first real use. |
| [`backend/rag/retrieval/vector_store.py`](../../backend/rag/retrieval/vector_store.py) | Chroma uses persistent local storage under `data/chromadb` by default. |
| [`backend/rag/indexing.py`](../../backend/rag/indexing.py) | Indexing reads processed or legacy data paths and upserts baseline and parent-child collections. |
| [`docker-compose.yml`](../../docker-compose.yml) | The checked-in stack defines only backend and frontend services and mounts local data and model cache paths. |
| [`backend/Dockerfile`](../../backend/Dockerfile) | The backend image is configured from Python 3.11 and starts Uvicorn on port 8000. |
| [`frontend/Dockerfile`](../../frontend/Dockerfile) | The frontend image is configured from Node 18 and starts the Vite development server on port 5173. |
| [`frontend/package.json`](../../frontend/package.json) | The frontend exposes `dev`, `build`, `lint`, `preview`, and `test` scripts. |
| [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) | Current CI masks backend and frontend test failures, so a green workflow is not evidence that tests pass. |
| [`.env.example`](../../.env.example) | The tracked example is currently empty and cannot be treated as complete environment setup guidance. |

This evidence supports documentation of the current entry path. It does not
certify runtime success, RAG quality, dependency support status, security, or
production readiness. Those claims require their own fresh checks.

## Problem Statement

The repository has approved governance but no project-facing guide answering:

1. What does Travel Agent do today, and what remains planned?
2. What is the smallest honest path to start and inspect the prototype?
3. Which prerequisites make health startup different from a working RAG chat?
4. Which commands are normal development actions, and what do they affect?
5. How do the browser, API, retrieval, model, and local data components connect?
6. Where should contributors go for deeper governance or future architecture?

Without these entry points, contributors must reverse-engineer configuration,
may trigger downloads or data mutation unintentionally, and may interpret the
future memory architecture as implemented behavior.

## Users

1. **New evaluator:** wants to identify product maturity and inspect the smallest
   working surface.
2. **Contributor:** needs reproducible setup, command effects, and repository
   navigation.
3. **Coding agent:** needs task-triggered entry points without loading every
   detailed document.
4. **Reviewer:** needs evidence for documentation claims and a clear line between
   current and target state.
5. **Repository owner:** needs known gaps exposed so later foundation, RAG, and
   memory packages can be prioritized honestly.

## Goals

1. Describe the current product and maturity without marketing overstatement.
2. Provide a minimal, conditional quick start and a detailed development path.
3. Make downloads, credentials, local writes, and external calls explicit before
   they occur.
4. Map the implemented request and data flow at a useful high level.
5. Separate configured versions from versions verified and supported by policy.
6. Route readers to existing governance and workflow documents.
7. Replace Package 1's interim development-guide notice when the guide exists.
8. Provide testable documentation acceptance criteria.

## Non-goals

1. Package 2 does not fix application setup, dependencies, CI, tests, or RAG.
2. It does not implement memory, authentication, trip workspaces, databases,
   workers, migrations, observability, deployment, or security policy.
3. It does not create Package 3 detailed architecture files or describe them as
   available.
4. It does not establish final production topology or durable architecture
   decisions.
5. It does not create `LICENSE`, `SECURITY.md`, runbooks, evaluation protocols,
   GitHub templates, roadmap, or changelog files.
6. It does not make crawling or indexing part of the default quick start.
7. It does not promise that every current command passes.
8. It does not add a package manager, Makefile, lock strategy, or new scripts.

## Assumptions and Constraints

1. The checked-in source and configuration remain the executable baseline until
   a separately approved change updates them.
2. Python 3.11 and Node 18 are current image configuration, not automatically a
   long-term support policy.
3. A health response proves only the health route, not model access, retrieval
   quality, or end-to-end chat readiness.
4. Real chat may require a credential, network access, an embedding-model
   download or cache, and populated Chroma data.
5. Local commands must not print, commit, or document secret values.
6. Package 2 may update existing routing and traceability text needed to make the
   new files discoverable; wider governance edits are out of scope.
7. If verification contradicts a documented command or expands scope, work
   returns to review rather than silently rewriting the contract.

## Selected Approach

Use three entry points with strict ownership:

| Document | Owns | Does not own |
| --- | --- | --- |
| `README.md` | Product identity, current maturity, minimal conditional quick start, limitations, repository map, documentation links | Full environment setup, exhaustive commands, deep architecture, future roadmap |
| `DEVELOPMENT.md` | Toolchain status, host and Docker setup, environment names, normal commands, effects, verification status, common setup troubleshooting | Incident recovery, production deployment, architecture design, generated dependency inventories |
| `ARCHITECTURE.md` | Implemented high-level components, request/data flow, trust boundaries, invariants, known gaps, existing design links | Package 3 detail, target-state commitment, full data model, ADR replacement |

This keeps the first read short while preserving enough operational detail for
repeatable verification.

## Alternatives Considered

### One comprehensive README

Putting setup, architecture, commands, and governance in one file minimizes
navigation but creates a long, rapidly stale document with conflicting owners.
It is rejected.

### Document the intended platform as the main architecture

Leading with PostgreSQL, workers, memory, and trip workspaces would communicate
direction but falsely represent unimplemented components. It is rejected.

### Minimal README with code as the only setup guide

This avoids duplication but leaves side effects, prerequisites, and known gaps
undiscoverable. It is rejected.

### Evidence-backed gateways with progressive disclosure

Three focused entry points make current behavior discoverable, keep exact values
in configuration, and allow later detailed documents to replace only the depth
they own. This is selected.

## Required Artifact Content

### `README.md`

The README must contain:

1. `Travel Agent` as the product name and an accurate one-paragraph description.
2. An explicit early-stage statement: current RAG prototype now; evaluated
   assistant, trip workspaces, and layered memory are direction, not current
   capability.
3. A short capability list limited to behavior evidenced by source.
4. A minimal quick start that distinguishes stack/health startup from RAG chat.
5. Up-front prerequisites and side effects for any quick-start command.
6. Links to `DEVELOPMENT.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`, `AGENTS.md`,
   and existing spec, plan, and ADR indexes.
7. A compact repository map containing only directories a reader needs first.
8. A limitations section covering maturity, data/model prerequisites, current
   stateless request contract, and unverified quality or production claims.

The README must not display a license badge or claim a source license until the
approved open-source package creates `LICENSE`. It must not show a passing CI,
test, coverage, security, or quality badge unsupported by fresh evidence.

### `DEVELOPMENT.md`

The development guide must contain:

1. A toolchain table separating `configured`, `verified`, and `supported-policy`
   status. Unknown support status is written as unknown, not inferred.
2. Host and Docker Compose paths, with one recommended path and explicit
   alternatives.
3. Environment variable names, requiredness, purpose, and sensitivity; no real
   values. It must not treat the empty `.env.example` as complete guidance.
4. A two-stage readiness model:
   - Stage A: frontend/backend startup and `/health` inspection.
   - Stage B: chat readiness with credential, network/model, data, and Chroma
     prerequisites.
5. Commands grouped by working directory and annotated with expected effect,
   writes, network use, and current verification status.
6. Normal commands derived from checked-in configuration: backend start,
   frontend dev/build/lint/test, Docker Compose, and relevant pytest entry
   points.
7. Crawling, ETL, indexing, and model-dependent evaluation in an opt-in section
   with warnings; none belongs to the default quick start.
8. Common development troubleshooting limited to normal setup symptoms. The
   future local runbook remains the owner of diagnosed recovery procedures.
9. Known toolchain gaps, including masked CI tests and any command failures
   reproduced during implementation verification.
10. A verification ledger for commands claimed by the document.

Each ledger row must record exact command, working directory, environment,
date, result as `verified-pass`, `verified-fail`, or `not-run`, and a concise
limitation. Merely finding a script is not a successful verification.

### `ARCHITECTURE.md`

The architecture gateway must contain:

1. Scope and maturity: a current high-level map, not the final architecture.
2. Implemented components and responsibilities: React/Vite client, FastAPI API,
   RAG generation service, embedder, local Chroma store, offline preprocessing
   and indexing, and external model service.
3. The current request flow from browser message through retrieval and model
   generation to citations.
4. The offline data flow from source data through cleaning/chunking/embedding to
   persistent Chroma collections, labeled as opt-in and state-changing.
5. Current trust boundaries: browser-to-local API, local process-to-model
   provider, local files/model cache/vector store, and untrusted retrieved text.
6. Current invariants evidenced by code, including the one-message request
   contract and local persistent vector storage.
7. Known gaps without redesigning them: no identity/trip scope in the bounded
   request contract, no implemented agent memory, no current multi-service data
   platform, permissive local CORS configuration, message-prefix logging, and no
   evidence-backed production security or SLO claim.
8. A clearly labeled future direction paragraph that links only to existing,
   approved artifacts. It must not create links to Package 3 files before they
   exist.
9. Links to relevant specs and ADR workflow, while stating that prose diagrams
   do not replace accepted ADRs.

The document may use a small Mermaid diagram if link and rendering checks cover
it. The written flow remains authoritative if rendering is unavailable.

## Reader and System Flows

### New contributor flow

1. Read README for maturity, capabilities, prerequisites, and limitations.
2. Choose the documented recommended setup path.
3. Open DEVELOPMENT for exact commands and command status.
4. Prove Stage A with the documented health check.
5. Opt into Stage B only after satisfying credential, network/model, and data
   prerequisites.
6. Open ARCHITECTURE before changing cross-module behavior.
7. Follow CONTRIBUTING and approved spec/plan gates before editing.

### Documentation maintenance flow

1. Source or configuration changes identify affected entry-point claims.
2. The governing spec and plan include the canonical document updates.
3. Verification reruns every command whose result is presented as current.
4. Review compares the exact docs against current source and configuration.
5. Stale claims are corrected in the same review unit or explicitly removed.

## Errors and Edge Cases

1. **Health passes but chat fails:** documentation must explain the narrower
   meaning of health and route the reader to Stage B prerequisites.
2. **No credential:** startup may be inspected, but external generation is
   unavailable; no secret value is logged or placed in a command example.
3. **No Chroma data:** chat may retrieve no useful context; docs do not present
   indexing as an automatic or harmless fix.
4. **Embedding model absent:** the first real use may access the network and take
   time; offline behavior is not promised unless verified.
5. **Command exists but fails:** mark `verified-fail`, preserve concise evidence,
   and do not repair it inside Package 2.
6. **Sandbox blocks a command:** mark `not-run` with the reason; do not translate
   it into application failure or success.
7. **Current and target language collide:** rewrite or label the target paragraph
   before review; unqualified future-tense architecture is not acceptable.
8. **A required quick-start check cannot run:** implementation acceptance stops;
   the owner may approve a revised spec, not a silent verification downgrade.

## Security and Privacy

1. Only environment variable names and redacted examples may appear.
2. Credentials, tokens, local `.env` content, user messages, and retrieved
   content must not be copied into verification evidence.
3. External model calls and possible model downloads must be disclosed before a
   command that triggers them.
4. Before Stage B chat use, the entry points must disclose that the external
   model request contains the user's message and retrieved travel context.
5. Crawled and retrieved content is untrusted data, not an instruction source.
6. Local paths and mounted data stores must be described without publishing
   private machine contents.
7. Package 2 must not imply authentication, tenant isolation, data deletion,
   encryption, or production privacy guarantees that are not implemented and
   verified.
8. The entry points must disclose that the current request path logs a message
   prefix and must not describe the current logging behavior as privacy-safe.

## Observability and Operations

Package 2 adds no runtime telemetry or operational behavior. It may document the
existing health route and logs, but must state their limited meaning. Deployment,
incident response, backups, recovery, SLOs, and production monitoring remain
future runbook and architecture work.

## Documentation Verification Strategy

The implementation plan must require fresh verification after all edits:

1. List the exact repository change set with untracked files included.
2. Compare each changed file with this spec and the approved plan.
3. Check relative links and local anchors; every live link must resolve.
4. Check Markdown fence balance, heading hierarchy, duplicate headings, trailing
   whitespace, and unresolved drafting markers.
5. Confirm the three documents stay within their ownership boundaries.
6. Search for unsupported maturity, security, license, CI, test, evaluation, and
   production-readiness claims.
7. Verify every current architecture claim against cited source or
   configuration, using Codebase Memory coverage checks for relied-on code.
8. Verify command provenance against actual scripts, Dockerfiles, dependency
   files, and workflow configuration.
9. Run the minimal startup and health smoke path designated by the approved
   implementation plan.
10. Run only explicitly approved chat or model-dependent smoke checks; they must
    not incur paid calls, downloads, crawling, or indexing without execution-time
    permission.
11. Record exact command, environment, date, exit status, failures, and skipped
    work. One passing check does not imply another passed.

Existing application test or tool failures are evidence to document and route
to a later foundation or RAG specification. Package 2 must not modify code,
dependencies, CI, or test configuration to make its documentation checks pass.

## Rollout and Migration

After specification approval:

1. Prepare and review a separate Package 2 implementation plan.
2. Create `README.md`, `DEVELOPMENT.md`, and `ARCHITECTURE.md` only after plan
   approval.
3. In the same implementation change, add task-triggered pointers for the new
   development and architecture guides to `AGENTS.md`.
4. Replace the interim development-guide paragraph in `CONTRIBUTING.md` with a
   link to `DEVELOPMENT.md` while preserving contribution ownership.
5. Update documentation traceability and lifecycle metadata without changing
   historical reasoning.
6. Run the approved verification matrix.
7. Stop for repository-owner review of the exact change set before Git delivery.

No data, API, schema, runtime, dependency, or deployment migration is included.

## Rollback

Before Git delivery, rollback means removing only the three Package 2 files and
reverting only their owned routing, index, and traceability edits. It must not
use destructive Git commands or disturb unrelated user files.

After delivery, any rollback follows a separately reviewed documentation change
that restores routing links and removes references to unavailable targets in the
same unit. Runtime or data rollback is not applicable because Package 2 changes
no application behavior.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Quick start looks successful while chat is unusable | Separate Stage A health from Stage B chat readiness |
| Documentation copies stale dependency values | Link configuration and record status rather than duplicating inventories |
| Configured versions are presented as supported | Use configured, verified, and supported-policy columns |
| RAG gaps are hidden behind polished prose | Include evidence-backed limitations and avoid quality claims |
| Commands trigger downloads, paid calls, or data mutation | Label side effects and keep such commands opt-in |
| Architecture gateway becomes a target design | Limit it to implemented components and label future direction |
| Green CI is treated as test evidence | Document masked failures and require direct fresh checks |
| Entry points duplicate governance | Link to existing canonical workflow documents |

## Acceptance Criteria

Package 2 implementation is acceptable only when:

1. The three approved root files exist and no unapproved Package 3-7 artifact is
   created.
2. README accurately separates current RAG behavior from future memory and trip
   workspace direction.
3. A new reader can locate prerequisites, start the documented Stage A path, and
   inspect `/health` using commands with fresh recorded status.
4. DEVELOPMENT contains host and Docker paths, environment variable names,
   command effects, side effects, and a dated verification ledger.
5. The default quick start does not crawl, index, download a model, or make a
   paid/external model call; expected local writes from startup, including
   Chroma directory or collection state, are disclosed before execution.
6. ARCHITECTURE maps the implemented online and offline flows and does not
   present planned memory, PostgreSQL, workers, identity, or trip workspaces as
   current components.
7. Every current-state material claim has a reviewable repository source.
8. Configured, verified, supported, failed, and not-run states are not conflated.
9. All live relative links and anchors resolve and no future missing file is
   linked as current documentation.
10. `AGENTS.md` and `CONTRIBUTING.md` routing is updated only as specified.
11. Documentation checks and required smoke checks pass; every optional or
    blocked check is disclosed without false success.
12. The exact change set, including untracked contents, matches this spec and
    the approved plan and is accepted by the repository owner.

## Manual Review Scenarios

The repository owner should be able to answer yes to each scenario:

1. Can a first-time reader explain what works today without assuming memory or
   trip projects already exist?
2. Can the reader distinguish backend health from end-to-end chat readiness?
3. Can the reader identify which commands use network, credentials, model cache,
   or persistent data before running them?
4. Can the reader trace one chat request across the implemented components?
5. Can a contributor find the canonical spec, plan, ADR, contribution,
   development, and architecture guidance in two navigation steps or fewer?
6. Can a reviewer identify every unverified command and known setup limitation
   without reading prior conversation history?

## Approval Record

Version 0.1 was approved by the repository owner on 2026-08-31 via the exact
conversation phrase `Approve Package 2 spec version 0.1`. Approval records the
Package 2 conversation-intake exception in lieu of a linked issue and
authorizes preparation of the Package 2 implementation plan only. It does not
authorize implementation, Git operations, runtime changes, or Package 3 work.
