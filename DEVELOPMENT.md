# Development

## Scope

This guide covers normal local development for the current Travel Agent
prototype. It documents setup paths, environment names, command effects, known
side effects, and the verification status recorded for this repository state.

Deployment, incident recovery, production operations, final architecture,
security policy, and RAG or memory evaluation protocols are owned by their
canonical docs and later runtime milestones.

## Toolchain Status

| Tool | Configured | Verified | Supported policy |
| --- | --- | --- | --- |
| Python | Python 3.11 in `backend/Dockerfile` and CI | R0 runs `python -m compileall backend` and `pytest backend/tests` as honest checks | Python 3.11 is the R0 baseline |
| Node.js | Node 18 in `frontend/Dockerfile` and CI | R0 runs `npm ci`, `npm run lint`, `npm run test`, and `npm run build` as honest checks | Node 18 is the R0 baseline |
| Docker Compose | Backend and frontend services in `docker-compose.yml` | R0 requires `docker compose config`; Stage A smoke requires Docker socket access | Development stack only |
| FastAPI/Uvicorn | Backend image starts `backend.app.main:app` on port 8000 | Stage A health checks `/health` | Health does not prove chat or RAG quality |
| Vite | Frontend dev server configured on port 5173 | Frontend build and test commands are R0 checks | Development server only |

Configured means the value is present in checked-in configuration. Verified
means the command was run for this document and recorded in the ledger.

## Environment

The checked-in `.env.example` file is a safe placeholder file. Copy it to a
local untracked `.env` only when a local workflow needs environment values.

| Name | Used by | Required for | Sensitive | Notes |
| --- | --- | --- | --- | --- |
| `GITHUB_TOKEN` | Backend settings and external model client | Stage B external generation | Yes | Placeholder only; do not commit real values |
| `LLM_MODEL` | Backend settings | Selecting the external model | No secret by itself | Defaults to `gpt-4o-mini` |
| `VITE_API_URL` | Frontend API client and Docker Compose frontend service | Browser-to-backend API origin | No secret by itself | Defaults to `http://localhost:8000` |
| `DATABASE_URL` | Backend settings, SQLAlchemy engine, runtime container, Alembic | PostgreSQL relational persistence | No secret by default (local dev) | Defaults to `postgresql+psycopg://travel_agent:password@localhost:5433/travel_agent`. Per ADR 0018, PostgreSQL 16 is the sole database; historical `APP_DB_PATH` and `WORKSPACE_DB_PATH` are retired. |
| `PG_TEST_DSN` | Integration test runner | Isolated PostgreSQL integration tests | No secret by default (local dev) | Connection string for disposable test database, e.g. `postgresql+psycopg://travel_agent:password@localhost:5433/travel_agent`. Required for integration tests to run with zero skips. |
| `MEMORY_RETRIEVAL_ENABLED` | Backend settings and chat orchestration | Enabling R6 memory retrieval for bound chat turns | No secret by itself | Defaults to `false`. With it disabled, chat behavior remains R4/R5 behavior |
| `MEMORY_PROMOTION_MIN_CONFIDENCE` | Backend settings and promotion policy | Minimum candidate confidence eligible for promotion | No secret by itself | Defaults to `0.75` |
| `MEMORY_MAX_SELECTED` | Backend settings and memory retrieval | Maximum memory records selected per bound chat turn | No secret by itself | Defaults to `5` |
| `MEMORY_WRITE_PIPELINE_ENABLED` | Backend settings and write pipeline | Enabling basic semantic memory write pipeline (Child Plan 6) | No secret by itself | Defaults to `false`. Safe opt-in rollout gate |
| `MEMORY_SHADOW_EXTRACT_ENABLED` | Backend settings and background worker | Enabling shadow candidate extraction worker | No secret by itself | Defaults to `false`. Hot-path decoupled worker gate |
| `MEMORY_WRITE_EVAL_FIXTURES_PATH` | Backend settings and evaluation harness | Evaluation benchmark fixtures path | No secret by itself | Defaults to `docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1` |

Do not print, paste, or commit real credential values in logs, examples,
issues, screenshots, terminal output, or documentation.

## Dependency Ownership

Python dependency source of truth: `requirements.txt` at the repository root.
`backend/requirements.txt` exists only as a compatibility pointer for backend
local workflows. Docker and CI install Python dependencies from the root file
once.

Frontend dependency source of truth: `frontend/package.json` plus
`frontend/package-lock.json`. Use `npm ci` for repeatable local and CI
installation after the lockfile exists.

## Recommended Path: Docker Compose & PostgreSQL

PostgreSQL 16 is the sole relational database per ADR 0018. Start the PostgreSQL service using Docker Compose:

```bash
docker compose up -d db
```

Verify that PostgreSQL is healthy on port `5433` (mapped from container port 5432):

```bash
docker compose ps db
```

Run Alembic migrations to bring the database schema to the clean-break head (`20260910_01`):

```bash
DATABASE_URL="postgresql+psycopg://travel_agent:password@localhost:5433/travel_agent" poetry run alembic upgrade head
```

Then start the complete development stack (backend, frontend, and database):

```bash
docker compose up --build
```

Expected effect: builds backend and frontend development images if needed,
installs image dependencies, starts the backend on port 8000, and starts the
frontend Vite dev server on port 5173.

Known writes and side effects:

- Docker image and container state may be created or updated.
- Backend and frontend bind mounts expose local `backend/`, `frontend/`, and
  `data/` paths to the containers.
- Backend startup may create or open local Chroma state under the mounted data
  path.
- The Hugging Face cache is mounted from `~/.cache/huggingface`.
- Image builds and dependency installation may use the network.

Stop the stack with:

```bash
docker compose down
```

## Alternative Path: Host Processes

Host process commands are useful when iterating on one side of the stack. They
depend on locally installed Python, Node.js, and project dependencies.

Backend from the repository root:

```bash
python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend from `frontend/`:

```bash
npm ci
npm run dev
```

`npm ci` writes `node_modules/` from the lockfile and may use the network.

## Readiness Stages

### Stage A: Startup and Health

Stage A proves only local startup and the health route:

```bash
curl --fail --silent --show-error http://localhost:8000/health
```

A successful health response does not prove credential validity, model-provider
access, retrieval data availability, retrieval quality, answer groundedness,
memory behavior, or end-to-end chat readiness.

### Stage B: RAG Chat Readiness

Stage B is the real chat path. Before using `/api/v1/chat`, verify:

- local `.env` exists when external model credentials are needed;
- `GITHUB_TOKEN` or the configured model-provider credential is available;
- network access to the configured external model provider is acceptable;
- the embedding model is present locally or first-use download is acceptable;
- Chroma contains useful travel data;
- the current request path logs a message prefix;
- the external model request contains the user message and retrieved travel
  context.

The minimal public chat request body still contains only:

```json
{
  "message": "Where should I go in Hanoi?"
}
```

Since `R4` the body also accepts an optional `conversation_id`, documented under
[Binding a Chat Turn to a Conversation](#binding-a-chat-turn-to-a-conversation).
There is still no implemented user, trip, or memory identifier in this bounded
request contract.

### Standalone Authenticated Conversations

Per ADR 0018, ADR 0019, ADR 0021, and ADR 0022, legacy Workspace, Planner, and legacy shadow memory routes and SQLite stores have been cleanly retired. The conversation subsystem provides standalone conversations owned directly by `owner_user_id` and backed by PostgreSQL 16.

Mounted conversation routes under `/api/v1`:

| Method and path | Purpose |
| --- | --- |
| `POST /api/v1/conversations` | Create a new standalone conversation for the authenticated user |
| `GET /api/v1/conversations` | List conversations owned by the authenticated user, newest updated first |
| `GET /api/v1/conversations/{conversation_id}` | Retrieve one conversation (returns `404` if not found or cross-owner) |
| `DELETE /api/v1/conversations/{conversation_id}` | Soft-delete one conversation (tombstones record, hidden from listings) |
| `GET /api/v1/conversations/{conversation_id}/messages` | Return `{"messages": [...], "next_cursor": ...}` in `sequence` ascending order |

All endpoints require a Bearer token:

```bash
curl --fail --silent --show-error \
  --request POST http://localhost:8000/api/v1/conversations \
  --header 'Authorization: Bearer dev-token-alpha' \
  --header 'Content-Type: application/json' \
  --data '{"title":"Da Nang Trip"}'
```

List owned conversations:

```bash
curl --fail --silent --show-error \
  http://localhost:8000/api/v1/conversations \
  --header 'Authorization: Bearer dev-token-alpha'
```

Read message history:

```bash
curl --fail --silent --show-error \
  'http://localhost:8000/api/v1/conversations/cv_example/messages?limit=50' \
  --header 'Authorization: Bearer dev-token-alpha'
```

Rules:
1. **Mandatory Bearer Authentication**: Every request requires a valid Bearer token. Historical `AUTH_REQUIRED=false` compatibility mode has been removed.
2. **Cross-Owner Isolation**: Accessing another owner's conversation returns a content-free `404 Not Found` without disclosing existence.
3. **Identifier Prefixes**: Conversation IDs are server-assigned with prefix `cv_`, message IDs with `ms_`.
4. **PostgreSQL Persistence**: Stored in PostgreSQL with row-level security policies and transactional atomicity.

### Authenticated Chat Turn and Conversation Lifecycle

The `POST /api/v1/chat` endpoint handles conversation turns with automatic lifecycle management:

1. **First turn (Conversation Auto-Creation)**: If `conversation_id` is omitted, the orchestrator auto-creates an owned conversation (`cv_...`) and returns its identifier in the response `conversation.conversation_id`:
   ```bash
   curl --fail --silent --show-error \
     --request POST http://localhost:8000/api/v1/chat \
     --header 'Authorization: Bearer dev-token-alpha' \
     --header 'Content-Type: application/json' \
     --data '{"message":"Recommend hotels in Da Nang"}'
   ```
2. **Subsequent turns (Conversation Continuation)**: Supply the returned `conversation_id` to continue the conversation in sequential order:
   ```bash
   curl --fail --silent --show-error \
     --request POST http://localhost:8000/api/v1/chat \
     --header 'Authorization: Bearer dev-token-alpha' \
     --header 'Content-Type: application/json' \
     --data '{"message":"Prefer quiet boutique options", "conversation_id":"cv_example"}'
   ```
3. **Decoupled Outbox Capture**: After each turn, the orchestrator captures memory extraction candidates to `conversation_outbox` asynchronously via `BackgroundMemoryRecorder`, keeping the chat turn fast and non-blocking.

### Basic Semantic Memory Write Pipeline

The basic semantic memory write pipeline (ADR 0020) manages versioned assertions, authority ranking, row locking, and idempotent commits against PostgreSQL:

```bash
python3 -m backend.memory.write_pipeline.evaluation.cli run-scenarios
```

### Local Ops Readiness

`/health` answers liveness only: it stays `{status, service}` and never
proves model, RAG, storage, memory, or planner readiness. Ops readiness is
the diagnostic surface:

```bash
curl --fail --silent --show-error http://localhost:8000/health
curl --fail --silent --show-error http://localhost:8000/api/v1/ops/readiness
./.venv/bin/python -m backend.observability.evaluation.cli run-readiness --suite r8-operational-readiness-v0.1
```

Rules:

1. Every response carries an `X-Request-ID` header for local correlation;
   it is not authentication.
2. Readiness is read-only: it never creates databases, Chroma state, or
   schema, and never calls a model provider.
3. Logs and readiness output carry ids, reason codes, counts, and timings
   only: no prompts, messages, answers, secrets, paths, or stack traces.
4. A `degraded`, `not_ready`, or `unknown` component names its reason code;
   follow the runbook routing in `docs/runbooks/local-development.md`
   before any destructive recovery.

### Local Auth and Security Verification

Bearer token authentication is mandatory for all `/api/v1` endpoints (except `/health`). Historical `AUTH_REQUIRED=false` compatibility mode has been removed per ADR 0019.

Tokens are configured via `LOCAL_AUTH_TOKENS_JSON` or local test tokens:

```bash
curl --fail --silent --show-error http://localhost:8000/api/v1/conversations \
  -H "Authorization: Bearer <owner-token>"

LOCAL_AUTH_TOKENS_JSON='{"owner_a":"secret-alpha-token","owner_b":"secret-beta-token"}' \
  python -m backend.security.evaluation.cli run-security --suite r9-security-privacy-v0.1
```

Rules:
1. Tokens live in the environment only; never commit, log, or paste them.
2. Cross-owner requests return generic, content-free `404 Not Found` responses.
3. Tombstoned records remain in PostgreSQL for audit and are hidden from normal API access.

## Command Contract

| Category | Working directory | Command | Claim | Writes | Network | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Backend static check | repository root | `python -m compileall backend` in CI; `python3 -m compileall backend` on hosts without `python` | Python source imports and compiles | Python cache files | No expected external call | `python3` verified-pass; `python` unavailable in current shell |
| Backend tests | repository root | `pytest backend/tests` in CI; `python3 -m pytest backend/tests` when pytest is installed as a module | Backend tests pass or fail honestly | Test and Python caches | No expected external call for normal tests | host pytest unavailable in current shell |
| Frontend install | `frontend/` | `npm ci` | Dependencies match lockfile | `node_modules/`, npm cache | Yes when cache is cold | verified-pass |
| Frontend lint | `frontend/` | `npm run lint` | ESLint checks pass or fail honestly | No expected source writes | No expected external call after install | verified-pass |
| Frontend tests | `frontend/` | `npm run test` | Vitest checks pass or fail honestly | Test caches | No expected external call after install | verified-pass |
| Frontend build | `frontend/` | `npm run build` | Vite production bundle builds | `frontend/dist/` | No expected external call after install | verified-pass |
| Compose config | repository root | `docker compose config` | Compose file is syntactically valid | No expected source writes | No expected external call | verified-pass |
| Stage A smoke | repository root | `docker compose up --build` plus `curl --fail --silent --show-error http://localhost:8000/health` | Dev stack starts and health responds | Docker state, mounted app/data paths, possible Chroma state | Possible during image build or dependency install | blocked by missing Docker daemon/socket in current environment |
| Stage B chat readiness | repository root | opt-in chat request to `/api/v1/chat` | Chat path can reach retrieval and model provider | Possible logs/cache/data state | Yes | Opt-in, not default CI |
| PostgreSQL tests | repository root | `DATABASE_URL=... PG_TEST_DSN=... pytest backend/tests/ -v` | All unit, boundary, and integration tests pass with zero skips | Test caches | Isolated PostgreSQL on port 5433 | Verified-pass (807 passed, 0 skipped) |
| Boundary checks | repository root | `pytest backend/tests/boundaries/ -v` | Clean-break architectural sentinels pass | Test caches | No expected external call | Verified-pass (5 passed) |
| Authenticated conversation routes | repository root | `curl` requests to `/api/v1/conversations` with `Authorization: Bearer` | Conversations and messages created and read under PostgreSQL | PostgreSQL database | No expected external call | Requires Bearer token |
| Authenticated chat turn | repository root | `POST /api/v1/chat` with `Authorization: Bearer` | Auto-creates or continues conversation, persists turn to PG | PostgreSQL database | Calls model provider | Verified-pass |
| Semantic memory write evaluation | repository root | `python3 -m backend.memory.write_pipeline.evaluation.cli run-scenarios` | Full write pipeline evaluation report | Markdown and JSON reports | No expected external call | Deterministic; writes reports only |
| Local ops readiness | repository root | `curl` requests to `/health` and `/api/v1/ops/readiness` | Liveness plus component diagnostics (PostgreSQL, Alembic head, Chroma, Model) | No expected source writes | No expected external call | Requires Bearer token for readiness |
| Local security evaluation | repository root | `LOCAL_AUTH_TOKENS_JSON='{...}' python -m backend.security.evaluation.cli run-security --suite r9-security-privacy-v0.1` | Security report with zero-tolerance gates | Markdown and JSON reports | No expected external call | Deterministic; writes reports only |
| RAG and memory evaluation | repository root | later approved evaluation command | Approved metric-specific quality claim | Evaluation outputs | Depends on later plan | Future milestone |

## Opt-in Data and Model Operations

Crawling, ETL, indexing, embedding model downloads, model-dependent chat
readiness, and model-dependent evaluation are opt-in operations. They can
mutate local data, populate Chroma, write cache files, use network access, call
external services, or incur provider-side usage.

Do not run these operations inside R0 default verification. Run them only under
the approved task that owns their inputs, side effects, and evidence.

## Common Setup Symptoms

| Symptom | Meaning | Next check |
| --- | --- | --- |
| `/health` responds but chat fails | Backend health is narrower than Stage B readiness | Check credential, network, model, and Chroma prerequisites |
| Frontend says it cannot connect to FastAPI | Browser cannot reach the backend origin | Check backend port 8000 and `VITE_API_URL` |
| Chat returns little or irrelevant context | Chroma may be empty or low quality for the query | Inspect data/indexing readiness in a separate approved RAG task |
| First chat is slow | Embedding model or cache access may be occurring | Confirm whether model download/cache use is acceptable |
| CI is green | CI commands completed, not proof of RAG quality | Read the exact workflow steps and exit statuses |
| Docker fails in a sandbox | Docker socket or localhost access may be blocked by the environment | Retry only with approved host access or record the limitation |
| PostgreSQL connection fails | Database container is stopped or port 5433 is blocked | Run `docker compose up -d db` and verify `docker compose ps db` |
| Alembic revision mismatch | Database schema is behind head revision | Run `poetry run alembic upgrade head` to apply migrations up to `20260910_01` |
| API returns `401 Unauthorized` | Missing or invalid Bearer token | Include a valid `Authorization: Bearer <token>` header on all `/api/v1` requests |
| Conversation route returns `404` | Conversation does not exist or belongs to another owner | Verify conversation ID; cross-owner requests return 404 to prevent enumeration |
| Conversation history returns `422` | The `limit` is outside `1` to `200` | Re-read the page with a valid limit |
| Historical `APP_DB_PATH` or `WORKSPACE_DB_PATH` referenced | Configuration using deprecated SQLite variables | Remove SQLite variables; configure `DATABASE_URL` pointing to PostgreSQL |

When normal setup has already failed and the problem needs diagnosis or
recovery, use the
[Local Development Recovery Runbook](docs/runbooks/local-development.md). It
owns broken-stack recovery, while this guide remains the canonical normal setup
path.

For the learning path behind these operational habits, use the Infrastructure
and Operations track in
[Engineering Curriculum](docs/learning/engineering-curriculum.md).

## Known Tooling Boundaries

- Docker Stage A requires Docker socket access outside the normal Codex
  sandbox when the sandbox cannot reach the host Docker daemon.
- The current host shell has `python3` but no `python` command and no installed
  pytest module. CI remains configured to use Python 3.11 through
  `actions/setup-python`.
- `npm install --save-dev jsdom@^24.1.1` reported npm audit findings: 3
  moderate, 4 high, and 1 critical vulnerability. R0 records the finding but
  does not run automated audit fixes because dependency remediation requires a
  separate reviewed change when it changes versions or behavior.
- `docker compose down` can leave a network in use if pre-existing orphan
  containers still attach to it. Do not remove orphan resources without an
  approved cleanup decision.
- Stage B chat readiness is intentionally not part of default CI because it can
  require secrets, network access, local model/cache state, and populated
  Chroma data.
- RAG and memory quality are not established by R0 checks. They require the
  approved evaluation protocols and later runtime milestones.

## Verification Ledger

| Date | Command | Working directory | Environment | Result | Limitation |
| --- | --- | --- | --- | --- | --- |
| 2026-08-31 | `rg -n '"(dev\|build\|lint\|preview\|test)"' frontend/package.json` | repository root | local shell | verified-pass | Proves script names only, not command success |
| 2026-08-31 | `rg -n 'FROM python:3\.11\|FROM node:18\|uvicorn\|ports:\|volumes:' backend/Dockerfile frontend/Dockerfile docker-compose.yml` | repository root | local shell | verified-pass | Proves configured values only |
| 2026-08-31 | `rg -n 'OPENAI\|API\|MODEL\|CHROMA\|DATA\|CACHE\|GITHUB\|VITE' backend/app/config.py frontend/src/services/api.js .env.example` | repository root | local shell | verified-pass | `.env.example` had no values at that time |
| 2026-08-31 | `docker compose up --build` | repository root | Codex sandbox | verified-fail | Docker socket access was denied at `~/.docker/run/docker.sock`; rerun outside the sandbox was required |
| 2026-08-31 | `docker compose up --build` | repository root | escalated local shell | verified-pass | Built frontend and backend images in 919.4s; backend Uvicorn started on port 8000 and frontend Vite started on port 5173; Docker warned about pre-existing orphan containers |
| 2026-08-31 | `curl --fail --silent --show-error http://localhost:8000/health` | repository root | Codex sandbox | verified-fail | Sandbox could not connect to localhost port 8000 while the Docker stack was running |
| 2026-08-31 | `curl --fail --silent --show-error http://localhost:8000/health` | repository root | escalated local shell | verified-pass | Returned `{"status":"ok","service":"Vietnam Travel Agent API"}` and backend logged `GET /health HTTP/1.1` 200 |
| 2026-08-31 | `docker compose down` | repository root | escalated local shell | verified-pass | Removed `travel_agent_frontend` and `travel_agent_backend`; network remained in use because pre-existing orphan containers were not removed |
| 2026-08-31 | `docker compose ps --all` | repository root | escalated local shell | verified-pass | Confirmed pre-existing orphan containers `travel_agent_db` and `travel_agent_outbox_worker` remained outside Package 2 cleanup scope |
| 2026-09-01 | `python -m compileall backend` | repository root | local shell | verified-fail | `python` command was not found in the current host shell |
| 2026-09-01 | `pytest backend/tests` | repository root | local shell | verified-fail | `pytest` command was not found in the current host shell |
| 2026-09-01 | `python3 -m compileall backend` | repository root | local shell, Python 3.14.5 | verified-pass | Host fallback proves source compilation only; CI remains Python 3.11 |
| 2026-09-01 | `python3 -m pytest backend/tests` | repository root | local shell, Python 3.14.5 | verified-fail | No pytest module is installed in the current host Python |
| 2026-09-01 | `npm install --save-dev jsdom@^24.1.1` | `frontend/` | escalated local shell | verified-pass | Required network access to npm registry; npm reported 8 audit vulnerabilities |
| 2026-09-01 | `npm ci` | `frontend/` | local shell | verified-pass | Installed 484 packages from lockfile |
| 2026-09-01 | `npm run lint` | `frontend/` | local shell | verified-pass | ESLint completed with 0 errors |
| 2026-09-01 | `npm run test` | `frontend/` | local shell | verified-pass | Vitest ran 1 file and 2 tests |
| 2026-09-01 | `npm run build` | `frontend/` | local shell | verified-pass | Vite built 342 modules and wrote `frontend/dist/` |
| 2026-09-01 | `rg -n "\\|\\| echo|continue-on-error|No backend tests found|Frontend tests completed or skipped" .github/workflows/ci.yml` | repository root | local shell | verified-pass | No success-producing test masks found |
| 2026-09-01 | `docker compose config` | repository root | local shell | verified-pass | Rendered Compose configuration without needing Docker daemon access |
| 2026-09-01 | `docker compose up --build` | repository root | local shell | blocked | Docker daemon/socket was unavailable at `~/.docker/run/docker.sock` |

## Local RAG Evaluation

Retrieval-only evaluation is local and does not require a provider:

```bash
python3 -m backend.rag.evaluation.cli preflight \
  --dataset data/evaluation/benchmark/rag-v0.1 \
  --config data/evaluation/configs/rag-structured-candidate-v0.1.json \
  --mode retrieval
python3 -m backend.rag.evaluation.cli run \
  --dataset data/evaluation/benchmark/rag-v0.1 \
  --config data/evaluation/configs/rag-structured-candidate-v0.1.json \
  --mode retrieval \
  --output-dir data/evaluation/runs
```

Full answer/judge evaluation is opt-in and may require `GITHUB_TOKEN`, provider
access, the embedding model, and populated Chroma data:

```bash
python3 -m backend.rag.evaluation.cli run \
  --dataset data/evaluation/benchmark/rag-v0.1 \
  --config data/evaluation/configs/rag-structured-candidate-v0.1.json \
  --mode full \
  --output-dir data/evaluation/runs
python3 -m backend.rag.evaluation.cli compare \
  --baseline data/evaluation/runs/<baseline-run-id> \
  --candidate data/evaluation/runs/<candidate-run-id> \
  --output data/evaluation/runs/<candidate-run-id>/comparison.json
```

Preconditions:

- The evaluation benchmark dataset exists (see `docs/evaluation/rag-evaluation.md`).
- Chroma data is populated for the configured collection
  (`vietnam_travel_parent_child`) before `preflight`/`run` in `retrieval` or
  `full` mode.
- Run from the primary working tree (nearest `data/` directory), or otherwise
  make `data/` available to the working tree. A linked worktree without `data/`
  creates an empty Chroma store and produces misleading retrieval results.
- Full mode additionally requires the configured judge/provider environment.

## Local Memory Evaluation

Shadow evaluation is local and deterministic. It requires no provider,
embedding model, Chroma data, or Docker:

```bash
python -m backend.memory.evaluation.cli run-shadow \
  --fixture docs/evaluation/fixtures/memory/r5-shadow-v0.1/manifest.json \
  --output-dir docs/reports/memory
```

The command replays the tracked synthetic fixtures end to end through the
real stores and service, then writes `r5-shadow-v0.1.md` and
`r5-shadow-v0.1.json` with the result state (`PASS`, `FAIL`,
`INCONCLUSIVE`, or `INVALID`), metric values, mandatory-slice evidence, and
applicable hard-gate counts. Fixture source files stay tracked under
`docs/evaluation/fixtures/memory/`; reports carry identifiers and codes
only, never message content or candidate text.

## Local Memory Write Pipeline Evaluation

The basic semantic memory write pipeline evaluation harness (Child Plan 6 / ADR 0016 / ADR 0017)
evaluates the deterministic write path against 22 required scenarios across 16 mandatory slices
with 12 non-compensating hard gates.

1. **Validate Dataset:**
   ```bash
   python3 -m backend.memory.write_pipeline.evaluation.cli validate-dataset \
     --dataset docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1
   ```

2. **Preflight Checks:**
   ```bash
   python3 -m backend.memory.write_pipeline.evaluation.cli preflight \
     --dataset docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1
   ```

3. **Run Evaluation Suites:**
   ```bash
   # Run all suites (safety, quality, operational)
   python3 -m backend.memory.write_pipeline.evaluation.cli run \
     --dataset docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1 \
     --suite all \
     --output-dir docs/reports/memory-write-pipeline/candidate

   # Or run specific suite: --suite safety | quality | operational
   ```

4. **Compare Reports (Non-regression Gating):**
   ```bash
   python3 -m backend.memory.write_pipeline.evaluation.cli compare \
     --baseline docs/reports/memory-write-pipeline/baseline/quality-report.json \
     --candidate docs/reports/memory-write-pipeline/candidate/quality-report.json \
     --output-dir docs/reports/memory-write-pipeline
   ```
