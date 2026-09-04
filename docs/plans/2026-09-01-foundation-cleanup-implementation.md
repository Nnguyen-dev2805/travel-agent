# Foundation Cleanup Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence.

**Goal:** Make Travel Agent's local, Docker, and CI foundation honest,
repeatable, and ready for later RAG, evaluation, workspace, memory, and
operations milestones.

**Architecture:** Implement the approved honest foundation baseline from R0
without changing RAG quality behavior, storage architecture, deployment
architecture, authentication, memory, or planner state. Use root
`requirements.txt` as the Python dependency source of truth, keep Docker
Compose as a development-stack contract, and separate health readiness from
chat/model/data readiness.

**Tech Stack:** Python 3.11, FastAPI, pytest, Docker Compose, Node 18,
React/Vite, ESLint 8, Vitest, GitHub Actions, Markdown governance docs.

**Spec:** [Foundation Cleanup Design](../specs/2026-09-01-foundation-cleanup-design.md),
version 0.1.

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-09-01 |
| Approved specification | [Foundation Cleanup Design](../specs/2026-09-01-foundation-cleanup-design.md), version 0.1 |
| Execution owner | Coding agent under repository-owner review |
| Decision owner | Repository owner |
| Scope | R0 implementation for command honesty, CI behavior, local setup repeatability, safe environment examples, dependency ownership, Docker install hygiene, frontend lint/test support, documentation alignment, roadmap status, and Infrastructure and Operations learning track |
| Verification | `git status --short --untracked-files=all`; `python -m compileall backend`; `pytest backend/tests`; `cd frontend && npm ci`; `cd frontend && npm run lint`; `cd frontend && npm run test`; `cd frontend && npm run build`; `docker compose config`; Stage A Docker health smoke when Docker access is available; targeted `rg` documentation and CI checks |

## Global Constraints

1. Do not improve or claim RAG retrieval quality, answer groundedness,
   citation quality, chunking strategy, prompt quality, or evaluation
   thresholds in R0.
2. Do not implement trip workspaces, user identity, conversation persistence,
   long-term memory, short-term memory, planner state, or memory retrieval.
3. Do not add production hosting, cloud infrastructure, deployment automation,
   container publishing, release automation, authentication, authorization,
   dashboards, alerting, or incident automation.
4. Keep the default baseline verification path free of required secrets,
   external model calls, crawler runs, Hugging Face model downloads, Chroma
   population, and network-dependent RAG checks after dependencies are
   installed.
5. Keep Stage A health independent from `GITHUB_TOKEN`, populated Chroma data,
   a downloaded embedding model, and external model calls.
6. Treat Stage B chat readiness as opt-in and document secrets, provider
   access, retrieval data, and network access as prerequisites.
7. Preserve `.env` as untracked local state and commit placeholders only in
   `.env.example`.
8. Preserve unrelated user work and never stage, commit, push, open a pull
   request, merge, tag, publish, delete branches, delete Docker volumes, or
   rewrite Git history without explicit repository-owner authorization.
9. Stop and return to design if implementation discovers a new storage
   boundary, trust boundary, deployment commitment, architecture dependency,
   or data migration requirement.
10. Keep documentation, commands, and CI behavior consistent with each other.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `.env.example` | Safe local environment contract with placeholders only | Approved R0 spec and current backend/frontend env usage |
| `requirements.txt` | Canonical Python dependency source of truth for R0 | Current duplicated dependency ranges |
| `backend/requirements.txt` | Compatibility pointer for backend-local install commands | Canonical root `requirements.txt` |
| `backend/Dockerfile` | Backend development image install path and Uvicorn startup contract | Canonical root `requirements.txt` and current backend import path |
| `frontend/package.json` | Frontend scripts and dev dependency declaration | Existing React/Vite/Vitest/ESLint stack |
| `frontend/package-lock.json` | Resolved frontend dependency graph after adding test support | `frontend/package.json` |
| `frontend/.eslintrc.cjs` | ESLint 8 configuration for the current React/Vite source | Existing ESLint plugins |
| `frontend/vite.config.js` | Vite/Vitest configuration that keeps Docker host binding in Dockerfile and tests local | Existing Vite config |
| `frontend/src/services/api.test.js` | Deterministic frontend service test that proves Vitest runs | `frontend/src/services/api.js` |
| `frontend/src/App.jsx` | Remove unused Sidebar prop passed by the current app shell | Frontend lint baseline |
| `frontend/src/components/Sidebar.jsx` | Remove unused Sidebar prop from component signature | Frontend lint baseline |
| `.github/workflows/ci.yml` | Honest CI command execution with no success-producing test masks | Backend and frontend command contracts |
| `README.md` | Top-level quick-start and readiness boundary when changed by R0 | Updated development guide |
| `DEVELOPMENT.md` | Canonical local setup, command taxonomy, expected outcomes, and verification ledger | R0 command behavior and Docker/env contracts |
| `docs/runbooks/local-development.md` | Recovery guidance for local setup, Docker, env, port, dependency, and test failures | R0 command behavior |
| `docs/learning/engineering-curriculum.md` | Infrastructure and Operations learning track | R0 learning requirements |
| `docs/roadmap/master-roadmap.md` | R0 milestone status and evidence pointer only | Approved R0 spec and plan |
| `docs/plans/README.md` | Plan index entry for this plan | This implementation plan |
| `docs/plans/2026-09-01-foundation-cleanup-implementation.md` | The approved execution contract and completion record | Approved R0 spec |

## Task 1: Baseline Snapshot and Roadmap Start State

**Files:**

- Read: `docs/specs/2026-09-01-foundation-cleanup-design.md`
- Read: `DEVELOPMENT.md`
- Read: `.github/workflows/ci.yml`
- Read: `docker-compose.yml`
- Modify: `docs/roadmap/master-roadmap.md`
- Modify: `docs/plans/2026-09-01-foundation-cleanup-implementation.md`

**Interfaces:**

- Consumes: approved R0 spec version 0.1 and current repository state.
- Produces: an R0 execution baseline and a roadmap status that says R0 is being
  implemented.

- [x] **Step 1: Confirm clean task boundary**

Run:

```bash
git status --short --untracked-files=all
```

Expected: only the approved R0 spec and this R0 plan are modified or
untracked. If unrelated files appear, read them before editing any overlapping
path and report the risk.

- [x] **Step 2: Mark R0 as in progress**

In `docs/roadmap/master-roadmap.md`, update only the `R0` row:

```markdown
| `R0` | Foundation Cleanup | In progress | `D4` | Tooling fixes, CI honesty, env examples, dependency hygiene | Basic checks fail honestly and setup is repeatable | Approved R0 spec and implementation plan; verification pending |
```

Do not change the `D4` row in this task. The `D4` status inconsistency remains
a known roadmap metadata issue unless the repository owner approves a separate
evidence-backed correction.

- [x] **Step 3: Mark this plan as approved only after owner approval**

After the repository owner explicitly approves this exact plan, change this
plan's metadata from `Status | In Review` to `Status | Approved` and update
the completion record to say plan approval was granted on `2026-09-01`.

Expected before implementation: the plan status is `Approved`; without that
status, stop.

- [x] **Step 4: Review checkpoint**

Review: R0 roadmap row and plan metadata.

Expected: R0 status is `In progress`; no other roadmap milestone status is
changed.

## Task 2: Environment and Command Contract Documentation

**Files:**

- Modify: `.env.example`
- Modify: `DEVELOPMENT.md`
- Modify: `README.md`
- Modify: `docs/runbooks/local-development.md`

**Interfaces:**

- Consumes: current env usage from `backend/app/config.py` and
  `frontend/src/services/api.js`.
- Produces: safe environment placeholders and a command taxonomy used by CI,
  agents, and reviewers.

- [x] **Step 1: Write safe environment placeholders**

Replace the empty `.env.example` with:

```dotenv
# Travel Agent local environment example.
# Copy to .env only for local development. Never commit real secrets.

# Required only for Stage B chat readiness and external model-provider calls.
GITHUB_TOKEN=

# Backend model selection for external model-provider calls.
LLM_MODEL=gpt-4o-mini

# Browser-to-backend origin used by the Vite frontend.
VITE_API_URL=http://localhost:8000
```

Do not add real tokens, private values, user data, or variables that current
code does not read.

- [x] **Step 2: Update development command taxonomy**

In `DEVELOPMENT.md`, add or replace the command taxonomy so it contains these
claim boundaries:

| Category | Command | Claim |
| --- | --- | --- |
| Backend static check | `python -m compileall backend` | Python source imports and compiles |
| Backend tests | `pytest backend/tests` | Backend tests pass or fail honestly |
| Frontend install | `npm ci` from `frontend/` | Frontend dependencies match lockfile |
| Frontend lint | `npm run lint` from `frontend/` | ESLint checks pass or fail honestly |
| Frontend tests | `npm run test` from `frontend/` | Vitest checks pass or fail honestly |
| Frontend build | `npm run build` from `frontend/` | Vite production bundle builds |
| Compose config | `docker compose config` | Compose file is syntactically valid |
| Stage A smoke | `docker compose up --build` plus `curl -fsS http://localhost:8000/health` | Dev stack starts and health responds |
| Stage B chat readiness | documented opt-in chat request | Chat path can reach retrieval and model provider |

State explicitly that Stage A does not prove RAG answer quality and Stage B is
not part of default CI.

- [x] **Step 3: Align README quick-start**

In `README.md`, keep the top-level quick-start short and point detailed setup
to `DEVELOPMENT.md`. Make sure it says:

1. Stage A uses Docker Compose and checks `/health`.
2. Stage B chat requires local `.env`, `GITHUB_TOKEN`, provider access,
   retrieval data, and network access.
3. RAG and memory quality claims require later evaluation milestones.

- [x] **Step 4: Update local recovery runbook**

In `docs/runbooks/local-development.md`, add recovery entries for:

1. Docker socket unavailable.
2. Backend port `8000` already in use.
3. Frontend port `5173` already in use.
4. Missing `.env` or missing `GITHUB_TOKEN` during Stage B.
5. Frontend lint configuration failure.
6. Frontend test environment failure.
7. Dependency install failure.
8. Sandbox-specific Docker or port-binding limitation.

Each entry must name the symptom, likely cause, first diagnostic command, and
safe recovery action.

- [x] **Step 5: Verify documentation and env contract**

Run:

```bash
rg -n "GITHUB_TOKEN|LLM_MODEL|VITE_API_URL|Stage A|Stage B|python -m compileall backend|pytest backend/tests|npm ci|npm run lint|npm run test|docker compose config" .env.example README.md DEVELOPMENT.md docs/runbooks/local-development.md
```

Expected: every R0 command and env variable appears in the owning document.

- [x] **Step 6: Review checkpoint**

Review: `.env.example`, quick-start text, command taxonomy, and runbook
entries.

Expected: docs contain no real secrets and no claim that health checks prove
RAG quality.

## Task 3: Python Dependency and Backend Docker Hygiene

**Files:**

- Modify: `requirements.txt`
- Modify: `backend/requirements.txt`
- Modify: `backend/Dockerfile`
- Modify: `DEVELOPMENT.md`

**Interfaces:**

- Consumes: current duplicated Python dependency ranges.
- Produces: root-owned Python dependency policy and a backend Dockerfile with
  one explicit dependency install path.

- [x] **Step 1: Keep root requirements canonical**

Keep the existing dependency set in `requirements.txt` as the R0 source of
truth. Preserve the existing ranges unless a verification failure proves a
specific package bound must change.

Expected canonical dependencies remain:

```text
fastapi>=0.110.0
uvicorn[standard]>=0.28.0
pydantic>=2.6.0
python-dotenv>=1.0.0
openai>=1.0.0
chromadb>=0.4.24
sentence-transformers>=2.2.2
beautifulsoup4>=4.12.0
lxml>=5.0.0
pytest>=8.0.0
httpx>=0.27.0
```

- [x] **Step 2: Convert backend requirements to a compatibility pointer**

Replace `backend/requirements.txt` with:

```text
# Backend-local compatibility file.
# The R0 dependency source of truth is the repository root requirements.txt.
-r ../requirements.txt
```

This keeps `pip install -r backend/requirements.txt` useful from the repository
root and documents that dependency ownership lives at the root.

- [x] **Step 3: Remove duplicate Docker installs**

Update `backend/Dockerfile` so it:

1. Installs and upgrades `pip`.
2. Installs CPU-only `torch` before requirements, preserving the current
   CPU-only intent.
3. Copies only root `requirements.txt` for dependency install.
4. Runs `pip install --no-cache-dir -r requirements.txt`.
5. Does not install `backend/requirements.txt`.
6. Does not run ad hoc `pip install fastapi uvicorn pydantic openai
   python-dotenv`.
7. Keeps `CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0",
   "--port", "8000"]`.

- [x] **Step 4: Document Python dependency ownership**

In `DEVELOPMENT.md`, add a short dependency policy:

```markdown
Python dependency source of truth: `requirements.txt` at the repository root.
`backend/requirements.txt` exists only as a compatibility pointer for backend
local workflows. Docker and CI install Python dependencies from the root file
once.
```

- [x] **Step 5: Verify backend static and test commands**

Run:

```bash
python -m compileall backend
pytest backend/tests
```

Expected: both commands return real exit statuses. If pytest fails because of
existing application defects, capture the failing tests and do not hide the
failure.

- [x] **Step 6: Review checkpoint**

Review: dependency files, Dockerfile install section, and backend command
output.

Expected: one Python dependency owner is visible and backend verification
results are honest.

## Task 4: Frontend Lint and Test Baseline

**Files:**

- Create: `frontend/.eslintrc.cjs`
- Create: `frontend/src/services/api.test.js`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/vite.config.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/Sidebar.jsx`
- Modify: `DEVELOPMENT.md`

**Interfaces:**

- Consumes: existing `frontend/src/services/api.js`, `frontend/vite.config.js`,
  and current React/Vite package setup.
- Produces: working ESLint config and at least one deterministic Vitest test
  that requires no backend, secret, browser session, or external network call.

- [x] **Step 1: Add jsdom test dependency**

From `frontend/`, run:

```bash
npm install --save-dev jsdom@^24.1.1
```

Expected: `frontend/package.json` and `frontend/package-lock.json` update with
`jsdom` in `devDependencies`. The selected version line must stay compatible
with Node 18.

- [x] **Step 2: Create ESLint configuration**

Create `frontend/.eslintrc.cjs`:

```javascript
module.exports = {
  root: true,
  env: {
    browser: true,
    es2020: true,
    node: true,
  },
  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', 'node_modules'],
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: {
      jsx: true,
    },
  },
  plugins: ['react-refresh'],
  rules: {
    'react/react-in-jsx-scope': 'off',
    'react/prop-types': 'off',
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
  },
  settings: {
    react: {
      version: 'detect',
    },
  },
}
```

- [x] **Step 3: Create frontend API service test**

Create `frontend/src/services/api.test.js`:

```javascript
import { describe, expect, it, vi, beforeEach } from 'vitest'
import axios from 'axios'
import { sendChatMessage } from './api'

vi.mock('axios')

describe('sendChatMessage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('posts the user message to the chat API', async () => {
    axios.post.mockResolvedValueOnce({
      data: {
        reply: 'Xin chao',
        model: 'test-model',
        citations: [],
      },
    })

    const result = await sendChatMessage('Plan a Da Nang trip')

    expect(axios.post).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/chat',
      { message: 'Plan a Da Nang trip' },
    )
    expect(result.reply).toBe('Xin chao')
    expect(result.model).toBe('test-model')
    expect(result.citations).toEqual([])
  })

  it('surfaces backend detail errors', async () => {
    axios.post.mockRejectedValueOnce({
      response: {
        data: {
          detail: 'Message content cannot be empty.',
        },
      },
    })

    await expect(sendChatMessage('   ')).rejects.toThrow(
      'Message content cannot be empty.',
    )
  })
})
```

- [x] **Step 4: Run frontend checks**

From `frontend/`, run:

```bash
npm ci
npm run lint
npm run test
npm run build
```

Expected: commands return real exit statuses. If any command fails, capture the
specific failure and fix only failures within R0 scope.

- [x] **Step 5: Document frontend baseline**

In `DEVELOPMENT.md`, update the frontend command status table so `npm ci`,
`npm run lint`, `npm run test`, and `npm run build` describe the current
verified outcome from this task.

- [x] **Step 6: Review checkpoint**

Review: lint config, test file, package manifest, lockfile diff, and frontend
command output.

Expected: frontend checks are honest and deterministic.

## Task 5: CI Honesty

**Files:**

- Modify: `.github/workflows/ci.yml`
- Modify: `DEVELOPMENT.md`

**Interfaces:**

- Consumes: backend and frontend command contracts from Tasks 2 through 4.
- Produces: CI workflow that fails when required backend or frontend commands
  fail.

- [x] **Step 1: Remove backend test mask**

In `.github/workflows/ci.yml`, replace:

```yaml
pytest backend/tests/ || echo "No backend tests found yet, skipping..."
```

with:

```yaml
pytest backend/tests
```

- [x] **Step 2: Remove frontend test mask**

In `.github/workflows/ci.yml`, replace:

```yaml
npm test || echo "Frontend tests completed or skipped."
```

with:

```yaml
npm run test
```

- [x] **Step 3: Align dependency installation**

Make backend CI install Python dependencies from root `requirements.txt` once:

```yaml
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Remove the extra unpinned backend `pip install pytest httpx fastapi pydantic
uvicorn openai python-dotenv` line.

Make frontend CI use lockfile installation:

```yaml
npm ci
```

- [x] **Step 4: Add explicit CI command order**

Keep or add CI steps in this order:

1. Checkout.
2. Set up Python 3.11.
3. Install Python dependencies.
4. `python -m compileall backend`.
5. `pytest backend/tests`.
6. Set up Node 18.
7. `npm ci` in `frontend/`.
8. `npm run lint` in `frontend/`.
9. `npm run test` in `frontend/`.
10. `npm run build` in `frontend/`.

Do not add Stage B model calls to CI.

- [x] **Step 5: Prove no success-producing test masks remain**

Run:

```bash
rg -n "\\|\\| echo|continue-on-error|No backend tests found|Frontend tests completed or skipped" .github/workflows/ci.yml
```

Expected: no matches.

- [x] **Step 6: Review checkpoint**

Review: workflow diff and local command parity.

Expected: CI commands match the documented baseline and fail honestly.

## Task 6: Docker and Stage A Smoke Contract

**Files:**

- Modify: `docker-compose.yml`
- Modify: `backend/Dockerfile`
- Modify: `frontend/Dockerfile`
- Modify: `DEVELOPMENT.md`
- Modify: `docs/runbooks/local-development.md`

**Interfaces:**

- Consumes: existing Compose service names, ports, Dockerfiles, and Stage A
  health requirement.
- Produces: documented Docker development-stack behavior with health readiness
  separated from chat/model/data readiness.

- [x] **Step 1: Keep Docker Compose development scope explicit**

Review `docker-compose.yml` and keep the current service purpose:

1. Backend development service on port `8000`.
2. Frontend Vite development service on port `5173`.
3. Backend `.env` loading.
4. Frontend `VITE_API_URL=http://localhost:8000`.
5. Local source and data mounts.

Only change Compose if verification proves current syntax or environment
contract is inconsistent with R0.

- [x] **Step 2: Keep frontend Dockerfile honest**

Review `frontend/Dockerfile`. If it remains a development image, document that
it runs `npm run dev -- --host 0.0.0.0` and does not represent production
serving. Do not convert it to a production image in R0.

- [x] **Step 3: Validate Compose syntax**

Run:

```bash
docker compose config
```

Expected: valid rendered Compose configuration. If Docker is unavailable in
the execution environment, report that as an environment limitation and keep
the command as required local evidence.

- [x] **Step 4: Run Stage A smoke when Docker access is available**

Run:

```bash
docker compose up --build
```

In another terminal, run:

```bash
curl -fsS http://localhost:8000/health
```

Expected response:

```json
{"status":"ok","service":"Vietnam Travel Agent API"}
```

Then stop the stack with:

```bash
docker compose down
```

If Docker access requires platform approval or fails due to sandbox socket
limitations, report that precisely.

- [x] **Step 5: Document Stage A versus Stage B**

In `DEVELOPMENT.md`, state:

1. Stage A proves the local development stack starts and `/health` responds.
2. Stage A does not prove retrieval data exists.
3. Stage A does not prove external model-provider credentials work.
4. Stage A does not prove RAG answer quality.
5. Stage B chat readiness is opt-in and requires prerequisites.

- [x] **Step 6: Review checkpoint**

Review: Compose/Dockerfile diffs, Stage A evidence, and documented readiness
boundaries.

Expected: Docker remains a development stack and no production deployment
claim is introduced.

## Task 7: Infrastructure and Operations Learning Track

**Files:**

- Modify: `docs/learning/engineering-curriculum.md`
- Modify: `DEVELOPMENT.md`

**Interfaces:**

- Consumes: R0 spec learning-track requirements and actual R0 command
  contract.
- Produces: a dedicated learning track and evidence journal format.

- [x] **Step 1: Add track map row**

In `docs/learning/engineering-curriculum.md`, add a `Infrastructure and
Operations` row to the Track Map:

```markdown
| Infrastructure and Operations | Docker, CI, env contracts, dependencies, command evidence, local recovery | `R0`, `R8`, `R10` |
```

- [x] **Step 2: Add learning track section**

Add a `### Infrastructure and Operations` section with:

1. Why it matters in Travel Agent.
2. Practice exercises for CI honesty, Stage A stack drawing, dependency
   ownership, baseline command classification, runbook update, and evidence
   journal writing.
3. Evidence to keep: approved R0 spec and plan, command output summaries, CI
   workflow diff, `.env.example`, dependency ownership note, Stage A/Stage B
   taxonomy, and one evidence journal entry.
4. Beginner, competent, and senior signals.

- [x] **Step 3: Add evidence journal format**

Add this journal format either under the new track or under the curriculum
usage section:

```markdown
### Evidence Journal Entry

| Field | Entry |
| --- | --- |
| Date | 2026-09-01 |
| Milestone | R0 Foundation Cleanup |
| Environment | Local shell, Docker, CI, or sandbox |
| Command or review | Exact command or review method |
| Result | Passed, failed, skipped, or blocked |
| Failure class | Current-state defect, regression, environment limitation, or expected opt-in prerequisite |
| Evidence summary | Short factual result |
| Next action | Repair, document, defer, or return to design |
```

- [x] **Step 4: Link learning track from development guide**

In `DEVELOPMENT.md`, add a short pointer from R0 command evidence to the
Infrastructure and Operations track.

- [x] **Step 5: Review checkpoint**

Review: curriculum row, learning track, and journal format.

Expected: the repository owner can use R0 to learn practical infrastructure
and operations reasoning without bypassing approval gates.

## Task 8: Final R0 Verification and Completion Notes

**Files:**

- Modify: `DEVELOPMENT.md`
- Modify: `docs/plans/2026-09-01-foundation-cleanup-implementation.md`
- Modify: `docs/roadmap/master-roadmap.md`

**Interfaces:**

- Consumes: all completed R0 tasks.
- Produces: final verification evidence and a review-ready change-set summary.

- [x] **Step 1: Run repository status**

Run:

```bash
git status --short --untracked-files=all
```

Expected: changed and untracked files match this plan's File Responsibility
Map. Investigate any extra path before continuing.

- [x] **Step 2: Run backend verification**

Run:

```bash
python -m compileall backend
pytest backend/tests
```

Expected: both commands finish with honest exit statuses. Passing is preferred.
If either fails, the final report must name the failing command and summarize
the failure.

- [x] **Step 3: Run frontend verification**

From `frontend/`, run:

```bash
npm ci
npm run lint
npm run test
npm run build
```

Expected: all commands finish with honest exit statuses. Passing is preferred.
If a command fails, the final report must name the failing command and
summarize the failure.

- [x] **Step 4: Run CI mask review**

Run:

```bash
rg -n "\\|\\| echo|continue-on-error|No backend tests found|Frontend tests completed or skipped" .github/workflows/ci.yml
```

Expected: no matches.

- [x] **Step 5: Run secret and placeholder review**

Run:

```bash
rg -n "ghp_|github_pat_|sk-|BEGIN PRIVATE KEY|password=|token=" .env.example README.md DEVELOPMENT.md docs/runbooks/local-development.md docs/learning/engineering-curriculum.md .github/workflows/ci.yml
```

Expected: no real-looking secrets. `GITHUB_TOKEN=` in `.env.example` is
allowed because it is an empty placeholder.

- [x] **Step 6: Run Docker verification**

Run:

```bash
docker compose config
```

Expected: valid rendered Compose configuration.

When Docker access is available, run Stage A smoke:

```bash
docker compose up --build
curl -fsS http://localhost:8000/health
docker compose down
```

Expected: health returns `{"status":"ok","service":"Vietnam Travel Agent API"}`.
If Docker access is blocked by sandbox or platform permissions, record it as a
verification limitation.

- [x] **Step 7: Run documentation marker review**

Run:

```bash
rg -n "TO""DO|TB""D|FIX""ME|PLACE""HOLDER|\\[Ex""act|\\[Fea""ture|\\[Obser""vable|\\[Deci""sion|\\[Ver""sion|\\[YY""YY" README.md DEVELOPMENT.md docs/runbooks/local-development.md docs/learning/engineering-curriculum.md
```

Expected: no unresolved drafting markers in changed docs. Template examples in
unchanged governance files are outside this check.

- [x] **Step 8: Run whitespace review**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [x] **Step 9: Update completion record**

In this plan, update `## Completion Record` with:

1. Plan approval date.
2. Execution date.
3. Commands run.
4. Pass/fail/skipped summary.
5. Known limitations.
6. Whether owner change-set review is still pending.

Do not mark the plan `Completed` until the repository owner accepts the R0
change set.

- [x] **Step 10: Prepare owner review summary**

Prepare a final response that includes:

1. Changed files.
2. Verification commands and outcomes.
3. Any skipped checks and why.
4. Any generated or untracked files.
5. R0 limitations.
6. Next gate: repository-owner change-set review.

Expected: the owner can decide whether to accept the R0 change set.

## Package Verification

The final implementation must run or explicitly report each command:

```bash
git status --short --untracked-files=all
python -m compileall backend
pytest backend/tests
cd frontend && npm ci
cd frontend && npm run lint
cd frontend && npm run test
cd frontend && npm run build
rg -n "\\|\\| echo|continue-on-error|No backend tests found|Frontend tests completed or skipped" .github/workflows/ci.yml
rg -n "ghp_|github_pat_|sk-|BEGIN PRIVATE KEY|password=|token=" .env.example README.md DEVELOPMENT.md docs/runbooks/local-development.md docs/learning/engineering-curriculum.md .github/workflows/ci.yml
docker compose config
git diff --check
```

Stage A Docker health smoke must be attempted when Docker access is available:

```bash
docker compose up --build
curl -fsS http://localhost:8000/health
docker compose down
```

The final report must classify every non-pass as one of:

1. Current-state defect.
2. Regression introduced by R0.
3. Environment limitation.
4. Expected opt-in prerequisite.
5. Out-of-scope future milestone.

## Rollback

Rollback is file-level and non-destructive:

1. Restore `.github/workflows/ci.yml` if honest checks block work for a reason
   outside approved R0 scope.
2. Restore `requirements.txt`, `backend/requirements.txt`, and
   `backend/Dockerfile` if the dependency ownership policy breaks backend
   installation.
3. Restore `frontend/package.json`, `frontend/package-lock.json`,
   `frontend/.eslintrc.cjs`, and `frontend/src/services/api.test.js` if the
   frontend baseline introduces unrelated failures.
4. Restore `docker-compose.yml`, `backend/Dockerfile`, or
   `frontend/Dockerfile` if Stage A startup regresses.
5. Restore `README.md`, `DEVELOPMENT.md`,
   `docs/runbooks/local-development.md`,
   `docs/learning/engineering-curriculum.md`, and
   `docs/roadmap/master-roadmap.md` if the documentation contract proves
   inaccurate.

Rollback must preserve unrelated user changes, local `.env`, local Chroma
data, generated data, Docker volumes, branches, commits, and history unless the
repository owner explicitly authorizes a destructive operation.

## Completion Record

Version 0.1 was approved by the repository owner on 2026-09-01. Implementation
ran on 2026-09-01 in the current repository checkout on branch
`feature/agent-memory`.

Verification summary:

1. `git status --short --untracked-files=all`: completed; changed and
   untracked files match the R0 file responsibility map after the map was
   updated for the frontend lint/test files actually touched.
2. `python -m compileall backend`: failed honestly because the current host
   shell has no `python` command.
3. `pytest backend/tests`: failed honestly because the current host shell has
   no `pytest` command.
4. `python3 -m compileall backend`: passed on host Python 3.14.5 as a local
   source-compile fallback; CI remains configured for Python 3.11.
5. `python3 -m pytest backend/tests`: failed honestly because pytest is not
   installed in the current host Python.
6. `npm install --save-dev jsdom@^24.1.1`: passed after approved network access
   to the npm registry; npm reported 3 moderate, 4 high, and 1 critical audit
   findings.
7. `npm ci`: passed from `frontend/`.
8. `npm run lint`: passed from `frontend/`.
9. `npm run test`: passed from `frontend/` with 1 test file and 2 tests.
10. `npm run build`: passed from `frontend/` and built 342 modules.
11. CI mask review found no success-producing backend or frontend test masks in
    `.github/workflows/ci.yml`.
12. Secret scan found no real-looking secrets in the checked R0 files.
13. `docker compose config`: passed.
14. `docker compose up --build`: blocked by missing Docker daemon/socket at
    `~/.docker/run/docker.sock`; Stage A health smoke could not be completed in
    this environment.
15. Documentation marker review and `git diff --check` passed.

Known limitations:

1. Backend pytest did not run in the current host environment because Python
   test dependencies are unavailable there.
2. Stage A Docker health smoke did not run because the Docker daemon/socket is
   unavailable.
3. npm audit findings were recorded but not remediated because audit fixes can
   change dependency versions and require a separate reviewed change.
4. `D4` roadmap status inconsistency remains intentionally unresolved because
   R0 did not approve a separate metadata correction.

The repository owner accepted the R0 change set on 2026-09-01. Git staging,
commit, push, pull request creation, merge, tag, release, production
deployment, and destructive cleanup remain outside the approval boundary unless
the repository owner explicitly requests one of those actions.
