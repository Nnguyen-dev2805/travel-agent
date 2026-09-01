# Foundation Cleanup Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-01 |
| Change class | Level 2 - Feature Spec |
| Decision owner | Repository owner |
| Scope | Runtime milestone R0 - foundation cleanup, CI honesty, local setup repeatability, environment examples, dependency hygiene, verification command contracts, and Infrastructure and Operations learning track |
| Parent design | [Documentation System Design](./2026-08-30-documentation-system-design.md), version 0.1; [Roadmap and Learning Design](./2026-08-31-roadmap-and-learning-design.md), version 0.1; [Operations and Security Design](./2026-08-31-operations-and-security-design.md), version 0.1 |
| Depends on | Documentation foundation packages `D0` through `D7`, with the roadmap `D4` status inconsistency called out in Current-state Evidence; [Evaluation Protocols Design](./2026-08-31-evaluation-protocols-design.md), version 0.1 for later RAG and memory quality gates |
| Implementation plan | [Foundation Cleanup Implementation Plan](../plans/2026-09-01-foundation-cleanup-implementation.md), version 0.1 (Completed; owner change set accepted) |
| Implementation state | Accepted in working tree; Git delivery not authorized |
| Related issue | None - R0 foundation cleanup was requested by the repository owner in this conversation |
| Superseded document | None |

## Summary

R0 establishes a truthful, repeatable engineering foundation before Travel
Agent continues into RAG repair, evaluation harness work, trip workspaces,
memory, planner state, observability, privacy hardening, or release readiness.

The selected approach is a conservative foundation cleanup. It will make the
default local and CI checks fail honestly, document which commands prove which
claims, provide safe environment examples, reduce dependency ambiguity, align
host and Docker startup expectations, and add an Infrastructure and Operations
learning track to the engineering curriculum.

R0 is not a RAG-quality milestone. It may expose current RAG and test failures,
but it must not hide them or claim quality improvement. Later `R1` and `R2`
own RAG repair and repeatable evaluation.

Approval of version 0.1 authorizes preparation of the R0 implementation plan
only. It does not authorize runtime edits, dependency changes, CI edits, Docker
changes, curriculum edits, Git staging, commit, push, pull request creation, or
release activity.

## Current-state Evidence

Current-state claims are based on Codebase Memory MCP Tier 2 verification for
structural code orientation, direct file reads for documentation and
configuration, and the recorded verification ledger in
[Development Guide](../../DEVELOPMENT.md). Codebase Memory reported generation
`2026-08-31T15:04:28Z` for project
`Users-tnhatnguyendev2805-Documents-Projects-travel-agent`. Coverage reported
no recorded issue for the material backend, configuration, workflow, Docker,
dependency, roadmap, and documentation paths cited here. It reported partial
parsing for [frontend/src/App.jsx](../../frontend/src/App.jsx) line 76, which
was read directly before relying on that file.

| Evidence | Current fact relevant to R0 |
| --- | --- |
| [Master Roadmap](../roadmap/master-roadmap.md) | `R0` is the first runtime milestone and exists to fix tooling, CI honesty, environment examples, and dependency hygiene before `R1`, `R2`, `R3`, and later memory work. |
| [Development Guide](../../DEVELOPMENT.md) | Stage A Docker health smoke is recorded as verified-pass only in an escalated local shell; sandbox Docker socket access failed. Frontend build is verified-pass, while frontend lint and test are recorded as verified-fail. |
| [Development Guide](../../DEVELOPMENT.md) | Current CI masks backend pytest and frontend test failures. The guide also records that `.env.example` has no values and that host backend startup from the documented root command remains an investigation target. |
| [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | Backend pytest uses `pytest backend/tests/ || echo "No backend tests found yet, skipping..."` and frontend tests use `npm test || echo "Frontend tests completed or skipped."`, so failing tests can become green CI steps. |
| [.env.example](../../.env.example) | The file exists but is empty, so new contributors and agents cannot discover safe environment placeholders from the repository. |
| [requirements.txt](../../requirements.txt) and [backend/requirements.txt](../../backend/requirements.txt) | The root and backend Python requirement files currently duplicate the same dependency ranges, including FastAPI, Uvicorn, ChromaDB, sentence-transformers, pytest, and HTTPX. |
| [backend/Dockerfile](../../backend/Dockerfile) | The backend image installs root requirements, backend requirements, and then installs several packages again with an unpinned `pip install fastapi uvicorn pydantic openai python-dotenv`; it also installs CPU-only PyTorch separately. |
| [frontend/package.json](../../frontend/package.json) | Frontend scripts include `dev`, `build`, `lint`, `preview`, and `test`; ESLint dependencies exist, but the repository currently lacks a working lint configuration and Vitest requires additional test-environment support. |
| [frontend/Dockerfile](../../frontend/Dockerfile) | The frontend container installs with `npm install` and runs the Vite dev server rather than a production preview or static serving contract. |
| [docker-compose.yml](../../docker-compose.yml) | Compose starts backend and frontend dev services with local source/data mounts, frontend port `5173`, backend port `8000`, `.env` loading for backend, and `VITE_API_URL=http://localhost:8000` for frontend. |
| [backend/app/main.py](../../backend/app/main.py) | FastAPI startup pre-warms `RAGService`, which can touch embedding and vector-store setup during application startup, but startup catches exceptions and logs a warning. |
| [backend/app/api/chat.py](../../backend/app/api/chat.py) and [backend/rag/generation/rag_service.py](../../backend/rag/generation/rag_service.py) | `/api/v1/chat` strips a message, calls `RAGService.generate_answer`, retrieves context, and then calls an external chat completion client that requires `GITHUB_TOKEN`. |
| [backend/rag/embedding/embedder.py](../../backend/rag/embedding/embedder.py) | The embedder lazily loads `BAAI/bge-m3` through sentence-transformers when available and has a deterministic dummy fallback if sentence-transformers is missing. |
| [frontend/src/services/api.js](../../frontend/src/services/api.js) | The browser client posts to `${VITE_API_URL || "http://localhost:8000"}/api/v1/chat`. |
| [docs/learning/engineering-curriculum.md](../learning/engineering-curriculum.md) | The curriculum already covers repository workflow, Git, codebase reading, architecture, testing, RAG, memory, evaluation, observability, security, product, and release practice, but it does not yet provide a dedicated Infrastructure and Operations track for Docker, CI, dependency, environment, and runbook discipline. |

The roadmap currently says `D4` is `In progress` while later documentation
packages `D5`, `D6`, and `D7` are accepted. R0 may include a narrow roadmap
metadata correction only if the implementation plan identifies the exact
accepted Package 4 evidence and the repository owner approves that correction
as part of the change set.

## Context

Travel Agent has moved from documentation-system setup into runtime milestone
work. The next runtime work will depend on local commands, CI status, Docker
startup, dependency installation, environment examples, and test boundaries
being trustworthy. If these foundations are unreliable, later RAG, memory, and
planner changes can appear healthy while actually relying on masked failures,
unrepeatable setup, or undocumented secrets.

AI coding agents can now produce large diffs quickly, so this project needs a
foundation that makes system behavior inspectable. The repository owner also
wants to learn senior infrastructure and operations thinking in this project,
not just feature coding. R0 therefore treats local setup, CI honesty, Docker
contracts, dependency ownership, and operational verification as both an
engineering milestone and a learning milestone.

## Users

1. **Repository owner:** needs to run and review the project with honest
   evidence, understand why checks fail, and learn practical infrastructure and
   operations habits.
2. **Coding agent:** needs deterministic commands and environment contracts so
   it can verify changes without hiding failures or inventing readiness claims.
3. **Future contributor:** needs repeatable setup instructions, safe
   placeholders, and clear check commands before opening issues or pull
   requests.
4. **Reviewer:** needs CI and local verification to represent actual status
   rather than best-effort shell fallbacks.
5. **Future operator:** needs a clean boundary between health, chat readiness,
   model-provider readiness, data readiness, and quality evaluation.

## Problem Statement

The repository currently has useful documentation and an early runnable
prototype, but its runtime foundation is not yet trustworthy enough for later
RAG and memory work. CI can pass while tests fail. Local environment examples
do not name required variables. Dependency declarations are duplicated and
partly reinstalled ad hoc in Docker. Frontend lint and test commands are known
to fail. Docker Compose starts development services, but command purpose,
health readiness, and chat/model readiness are not yet separated into a clean
verification contract.

This matters now because `R1`, `R2`, `R3`, and later memory milestones depend
on evidence. If R0 does not establish honest checks first, later improvements
can be measured on top of broken or ambiguous setup.

## Goals

1. Make backend, frontend, Docker, and CI verification fail honestly by default
   when the underlying command fails.
2. Define a small command contract that separates static checks, unit tests,
   integration tests, Stage A health smoke, Stage B chat readiness, and later
   evaluation.
3. Make local setup repeatable enough for the repository owner, a coding agent,
   and a future contributor to reproduce the same baseline behavior.
4. Provide a safe `.env.example` that documents required and optional variables
   without committing secrets or implying that model-provider calls are free or
   always available.
5. Reduce Python dependency ambiguity by establishing one approved dependency
   ownership policy for root, backend, and Docker usage.
6. Repair or explicitly gate frontend lint and test commands so they either
   pass honestly or fail with a real actionable reason.
7. Align documented host and Docker startup commands with the actual import
   paths, ports, and service expectations.
8. Preserve a default no-secret, no-model-call baseline check path for local
   and CI verification.
9. Add an Infrastructure and Operations learning track that teaches Docker,
   CI, environment variables, dependencies, command contracts, runbooks,
   failure diagnosis, and evidence journals through R0 work.
10. Leave the repository ready for `R1` and `R2` to repair and evaluate RAG on
    top of honest foundation checks.

## Non-goals

1. R0 does not improve RAG retrieval quality, answer groundedness, citation
   quality, chunking strategy, prompt quality, or evaluation thresholds.
2. It does not build the `R2` evaluation harness or claim model-answer quality.
3. It does not implement trip workspaces, user identity, conversation
   persistence, long-term memory, short-term memory, planner state, or memory
   retrieval.
4. It does not select a production hosting provider, add cloud infrastructure,
   deploy the application, publish containers, or create release automation.
5. It does not add authentication, authorization, user-data deletion semantics,
   telemetry pipelines, dashboards, alerting, or production incident automation.
6. It does not require external model calls, crawler runs, Hugging Face model
   downloads, Chroma population, or network-dependent RAG checks in the default
   baseline verification path.
7. It does not remove or rewrite large RAG modules except where a narrow change
   is required to keep startup, health, tests, or command contracts honest.
8. It does not stage, commit, push, open a pull request, merge, tag, publish a
   release, or alter Git history.

## Assumptions

1. The repository owner wants R0 to prioritize trustworthy engineering evidence
   over feature velocity.
2. The repository owner will create or select the Git branch before Git
   delivery work, and Git staging, commit, push, and pull request actions remain
   owner-controlled unless explicitly requested.
3. Python 3.11 and Node 18 remain the initial supported runtime versions for
   R0 unless implementation investigation proves a stronger reason to change
   them.
4. Docker Compose remains the default Stage A local stack for R0.
5. Stage A health must not require `GITHUB_TOKEN`, populated Chroma data, a
   downloaded embedding model, or an external model call.
6. Stage B chat readiness may require secrets, model-provider access, travel
   data, Chroma state, and network access, so it must be opt-in and documented
   separately from Stage A.
7. Dependency lockfile policy is not yet mature enough for full production
   release guarantees; R0 can establish dependency ownership and CI installation
   hygiene without claiming reproducible release builds.
8. R0 can update documentation and scripts to expose existing failures, but any
   newly discovered architecture boundary, storage decision, or deployment
   commitment stops the work and returns to design.

## Selected Approach

Use an **honest foundation baseline**:

1. Keep R0 as a Level 2 feature spec because it changes tooling, CI behavior,
   local setup contracts, documentation, and learning workflow, but it does not
   introduce a new storage system, protocol, deployment architecture, trust
   boundary, or hard-to-reverse subsystem.
2. Define command categories before fixing scripts so each check has a clear
   claim boundary.
3. Remove CI failure masks and make CI report true command outcomes.
4. Prefer deterministic local checks that do not require secrets, model calls,
   dataset refresh, or populated vector state.
5. Treat Docker Compose as a development-stack contract for R0, not production
   infrastructure.
6. Establish one Python dependency ownership policy and make Docker follow it
   without redundant ad hoc installs.
7. Keep frontend lint and tests small, local, and honest; install or configure
   only the minimum support required for the current React/Vite app.
8. Update documentation at the same time as command behavior so future agents
   know what each check proves.
9. Add the Infrastructure and Operations learning track to the curriculum with
   R0-specific exercises and evidence artifacts.

## Alternatives Considered

### Full infrastructure redesign now

This would introduce production container strategy, deployment environments,
observability stack, secrets management, release automation, and stronger
runtime architecture decisions immediately. It is rejected for R0 because the
repository first needs honest local and CI evidence. Larger deployment and
operations decisions belong to later milestones such as `R8`, `R9`, and `R10`.

### RAG repair before foundation cleanup

This would start with retrieval, prompt, vector-store, or evaluation changes.
It is rejected because current checks can hide failures and setup is not
repeatable enough. RAG repair needs an honest baseline and belongs to `R1`
after R0.

### Documentation-only cleanup

This would update README, development notes, and curriculum without changing
CI, dependencies, scripts, or setup behavior. It is rejected because R0's exit
gate requires basic checks to fail honestly and setup to be repeatable.

### Strict production reproducibility immediately

This would require locked dependency graphs, SBOM generation, container
publishing, vulnerability scanning gates, and release-grade build promotion.
It is rejected for R0 because it would expand scope into release readiness and
operations maturity. R0 may prepare the path, but `R10` owns public release
confidence.

## User and System Flows

### New local developer setup

1. The developer reads [README](../../README.md) and
   [Development Guide](../../DEVELOPMENT.md).
2. The developer copies safe environment placeholders from `.env.example`
   into a local untracked `.env` only when they need Stage B or external model
   behavior.
3. The developer runs the default dependency installation commands documented
   for backend and frontend.
4. The developer runs baseline static and test commands.
5. The developer starts Stage A through Docker Compose and confirms `/health`.
6. The developer runs Stage B chat readiness only after intentionally providing
   required secrets, data, and network access.

### Pull request or owner review

1. CI installs backend and frontend dependencies using the approved dependency
   policy.
2. CI runs backend checks, frontend checks, and any documented smoke checks
   within their safe environment boundaries.
3. A failing command fails CI instead of being converted into an echo message.
4. The reviewer compares CI output with local verification evidence and the
   approved implementation plan.
5. Any new failure is reported as evidence rather than hidden as a pass.

### Coding agent verification

1. The agent reads the governing spec and implementation plan.
2. The agent selects the exact command category needed for the claim it wants
   to make.
3. The agent runs commands freshly and reports actual exit status and output
   summary.
4. The agent does not claim RAG answer quality from health checks, build
   checks, or masked CI.
5. The agent stops at missing approval, unexpected architecture impact,
   required network access, missing secrets, or failing verification.

### Infrastructure and Operations learning loop

1. The repository owner studies the R0 learning track before or during the
   implementation review.
2. Each R0 change includes one small operational lesson: command purpose,
   failure mode, recovery step, or evidence boundary.
3. The owner records a short evidence journal entry after verification.
4. Later milestones reuse the same rhythm for evaluation, observability,
   security, deployment, and release readiness.

## Behavioral and Data Contracts

### Command categories

| Category | Purpose | Secret required | External network expected after dependencies are installed | Quality claim allowed |
| --- | --- | --- | --- | --- |
| Static backend check | Validate Python import/compile or style contract selected by the implementation plan | No | No | Code health only |
| Backend unit tests | Validate isolated backend behavior and deterministic RAG utilities | No | No | Tested component behavior only |
| Backend integration tests | Validate local API, vector store, or service integration with explicit local fixtures | No by default | No by default | Local integration behavior only |
| Frontend lint | Validate React/Vite source style and common bugs | No | No | Frontend static correctness only |
| Frontend tests | Validate deterministic UI or service behavior | No | No | Tested frontend behavior only |
| Frontend build | Validate production bundle compilation | No | No after npm install | Buildability only |
| Stage A smoke | Validate local Docker stack can start and backend health route responds | No | Possible during image build or dependency install only | Runtime health only |
| Stage B chat readiness | Validate chat path with configured model provider and prepared retrieval state | Yes | Yes | Connectivity/readiness only, not quality |
| RAG and memory evaluation | Validate answer, retrieval, grounding, memory, or planner quality | May be required by later plan | May be required by later plan | Only the metric claim defined by the approved evaluation protocol |

### Environment contract

R0 must make `.env.example` a safe, non-secret reference for local development.
It must document at least:

1. `GITHUB_TOKEN` as required only for external model-provider calls.
2. `LLM_MODEL` as the model selection value used by backend settings.
3. `VITE_API_URL` as the frontend browser-to-backend origin.
4. Any Chroma, data, embedding, logging, or test variables that the R0
   implementation plan proves are actually read by current code or scripts.

The file must not include real secrets, private tokens, sensitive user data, or
claims that external provider use is free, guaranteed, or production-ready.

### Dependency ownership contract

R0 must choose and document one Python dependency ownership policy. Acceptable
policies include:

1. A single backend-owned requirements file with root commands pointing to it.
2. A root-owned requirements file with backend and Docker explicitly reusing it.
3. A documented split between runtime and development requirements if the
   implementation plan proves the extra files are needed.

Whichever policy is approved in the implementation plan must remove silent
duplicate installation paths from Docker and CI. R0 does not need to introduce
a production lockfile unless the implementation plan separately justifies it.

### Startup and readiness contract

R0 must keep `/health` usable as the Stage A readiness check. Stage A must not
depend on successful RAG prewarm, model-provider credentials, populated Chroma,
or a live external model call.

R0 must document the difference between:

1. Server process started.
2. Health route responding.
3. Chat route reachable.
4. Retrieval data available.
5. External model provider configured.
6. RAG answer quality measured.

### Documentation contract

R0 must update the canonical documents that own the changed behavior:

1. `DEVELOPMENT.md` for setup, commands, expected outcomes, and known failure
   recovery.
2. `README.md` only if the quick-start or top-level status changes.
3. `docs/runbooks/local-development.md` if recovery actions change.
4. `docs/learning/engineering-curriculum.md` for the Infrastructure and
   Operations learning track.
5. `docs/roadmap/master-roadmap.md` only for approved milestone status or
   metadata corrections.

## Errors and Edge Cases

1. **Docker socket unavailable:** local Docker smoke checks must report the
   platform access failure and must not be treated as application failure.
2. **Ports already in use:** Stage A guidance must identify frontend port
   `5173` and backend port `8000` conflicts as local environment issues with a
   recovery path.
3. **Missing `.env`:** Stage A health should still run; Stage B chat readiness
   must fail with an actionable missing-credential message.
4. **Missing or empty Chroma data:** Stage A health must not depend on
   retrieval results; Stage B must disclose retrieval-data readiness as a
   separate precondition.
5. **Embedding model download unavailable:** default checks must avoid
   requiring a model download; checks that need model access must be opt-in.
6. **Frontend lint configuration missing or incompatible:** `npm run lint`
   must fail honestly until fixed, then stay covered by CI.
7. **Frontend test environment missing:** `npm run test` must fail honestly
   until the required test environment is installed or configured.
8. **CI dependency install succeeds but tests fail:** CI must fail the workflow
   instead of converting the failure to a success log line.
9. **Roadmap status inconsistency:** metadata corrections must be narrow,
   evidence-backed, and approved as part of R0 or a separate documentation
   correction.
10. **Sandbox-specific failures:** verification reports must distinguish
    sandbox constraints from repository defects.

## Security and Privacy

R0 must keep secrets and sensitive data out of committed files, command output,
documentation examples, CI logs, and verification evidence. `.env.example`
must contain placeholders only. `.env` must remain untracked.

Default checks must avoid external model calls and avoid sending user prompts,
retrieved context, logs, traces, credentials, or local data to external
providers. Stage B and later evaluation commands may require secrets or network
access only when the implementation plan documents those preconditions and the
operator intentionally opts in.

R0 must not change user-data retention, memory storage, authentication,
authorization, vulnerability reporting, or privacy policy. If implementation
discovers that a foundation change affects a trust boundary, work stops and
returns to design.

## Observability and Operations

R0 must make operational status easier to reason about without adding a full
observability stack. It should define:

1. Which command proves dependency installation, static correctness, unit
   behavior, buildability, container startup, and health readiness.
2. Which logs are useful for startup, health, missing environment variables,
   and model-provider configuration failures.
3. Which runbook owns recovery for local setup, Docker issues, missing secrets,
   and failing checks.
4. Which failures are expected current-state defects and which failures are new
   regressions.
5. How the repository owner records one short evidence journal entry for the
   Infrastructure and Operations learning track.

R0 does not add dashboards, alerting, distributed tracing, log aggregation,
service-level objectives, incident automation, deployment promotion, or
production monitoring. Those belong to later operations milestones.

## Infrastructure and Operations Learning Track

R0 must add a dedicated learning track to
[Engineering Curriculum](../learning/engineering-curriculum.md). The track must
teach practical senior engineering habits through this repository rather than
abstract theory.

Minimum learning objectives:

1. Explain the difference between local development, CI, Docker development
   stack, deployment, release, and production operations.
2. Read a CI workflow and identify whether commands fail honestly.
3. Understand how dependency ownership affects reproducibility,
   maintainability, Docker build time, and security review.
4. Understand environment-variable contracts, secret placeholders, and why
   secrets must not appear in source, logs, or examples.
5. Separate health readiness, chat readiness, data readiness, model-provider
   readiness, and quality evaluation.
6. Diagnose common local-stack failures using evidence: port conflict, Docker
   socket denial, missing env, dependency install failure, test environment
   failure, and stale generated artifacts.
7. Write an evidence journal entry that records command, environment, result,
   failure classification, and next action.

Minimum practice exercises:

1. Inspect the CI workflow and mark every command that can hide a failure.
2. Draw the Stage A local stack: browser, frontend, backend, health route,
   data mount, and environment file.
3. Compare `requirements.txt`, `backend/requirements.txt`, backend Docker
   installs, and CI installs, then state the approved dependency owner.
4. Run the baseline verification commands and classify each result as pass,
   expected current failure, environment failure, or regression.
5. Update one runbook entry after a real failed local command.
6. Write a short evidence journal entry for the R0 change set.

Minimum evidence artifacts:

1. The approved R0 spec and implementation plan.
2. Local command output summaries with exit status.
3. CI workflow diff and resulting behavior.
4. Safe environment example.
5. Dependency ownership note.
6. Stage A and Stage B command taxonomy.
7. One evidence journal entry in the curriculum or the implementation review
   notes, as selected by the implementation plan.

## Testing and Evaluation

R0 verification must be command-based and must not rely on visual confidence or
manual optimism. The implementation plan must select exact commands, but the
minimum expected verification areas are:

1. Repository status before and after the change:
   `git status --short --untracked-files=all`.
2. Backend static/import check, such as `python -m compileall backend`, or a
   stricter approved equivalent.
3. Backend test command, expected to run from the documented working directory
   and fail honestly if tests fail.
4. Frontend dependency install command selected by the implementation plan.
5. `npm run lint` from `frontend/`.
6. `npm run test` from `frontend/`.
7. `npm run build` from `frontend/`.
8. CI workflow review proving failure masks were removed.
9. Docker Compose configuration or Stage A smoke check selected by the
   implementation plan.
10. Documentation link and marker review for the changed docs.

R0 does not require RAG evaluation, LLM-as-judge evaluation, memory evaluation,
planner evaluation, or external model answer checks. If any of those checks are
run voluntarily, they must be reported as exploratory and must not become R0
acceptance evidence unless the approved implementation plan includes them.

## Rollout and Migration

R0 should roll out in small, reviewable stages:

1. Confirm baseline failures and command ownership.
2. Fix CI honesty and command contracts.
3. Fix or gate frontend lint/test support.
4. Clean dependency ownership and Docker install behavior.
5. Fill safe environment examples.
6. Align setup documentation and runbook recovery notes.
7. Add the Infrastructure and Operations learning track.
8. Run full R0 verification.
9. Return the change set to repository-owner review before any Git delivery.

R0 should avoid data migrations. If generated files such as frontend build
output, test caches, Python caches, Chroma data, or local Docker state are
created during verification, the implementation report must identify them and
leave unrelated ignored state untouched unless cleanup is explicitly approved.

## Rollback

Rollback should be file-level and non-destructive:

1. Restore the previous CI workflow if honest checks block work for reasons
   outside R0 scope.
2. Restore previous dependency manifests if the selected ownership policy
   breaks installation.
3. Restore previous Docker files or Compose settings if Stage A startup
   regresses.
4. Restore previous frontend lint/test configuration if the selected support
   path causes unrelated failures.
5. Restore documentation changes if the command contract proves inaccurate.

Rollback must not delete user work, local `.env`, Chroma data, generated data,
Docker volumes, branches, commits, or history without explicit repository-owner
authorization.

## Acceptance Criteria

1. R0 has an approved implementation plan that maps each spec requirement to
   exact files, commands, and rollback steps.
2. CI no longer masks backend or frontend test failures with success-producing
   shell fallbacks.
3. The repository has a documented baseline command contract that separates
   static checks, tests, builds, Stage A health, Stage B chat readiness, and
   later evaluation.
4. `.env.example` contains safe placeholders and descriptions for variables
   proven to be used by current code or R0 scripts.
5. Python dependency ownership is documented and Docker/CI follow the approved
   policy without silent duplicate runtime installs.
6. Frontend lint, test, and build commands either pass honestly or fail with
   documented actionable current-state reasons that are visible in CI.
7. Backend checks and tests run from the documented working directory and fail
   honestly when broken.
8. Stage A health smoke can be run without model-provider credentials and does
   not claim RAG answer quality.
9. Stage B chat readiness is documented as opt-in with explicit prerequisites
   for secrets, provider access, retrieval data, and network access.
10. `DEVELOPMENT.md`, local runbook guidance, and README quick-start content
    remain consistent with the actual commands.
11. The engineering curriculum contains a dedicated Infrastructure and
    Operations learning track with objectives, exercises, and evidence
    artifacts tied to R0.
12. Verification evidence reports actual commands, exit status summaries,
    failures, skipped checks, sandbox limitations, and untracked files.
13. No secrets, credentials, tokens, sensitive user data, or private local
    values are committed or printed as evidence.
14. The final change-set review identifies changed files, evidence, remaining
    limitations, and the next Git delivery gate.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-09-01. Approval
authorizes preparation of the R0 Foundation Cleanup implementation plan only.
Runtime implementation, dependency edits, CI edits, Docker edits, curriculum
edits, documentation updates outside this specification, and Git delivery
require the next approval gates.
