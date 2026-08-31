# Development

## Scope

This guide covers normal local development for the current Travel Agent
prototype. It documents setup paths, environment names, command effects, known
side effects, and the verification status recorded for this repository state.

Deployment, incident recovery, production operations, final architecture,
security policy, and RAG or memory evaluation protocols are owned by later
approved documentation packages.

## Toolchain Status

| Tool | Configured | Verified | Supported policy |
| --- | --- | --- | --- |
| Python | Python 3.11 in `backend/Dockerfile` and CI | Docker Stage A built the backend image and `/health` smoke verified-pass in an escalated local shell | Unknown |
| Node.js | Node 18 in `frontend/Dockerfile` and CI | Docker Stage A built the frontend image; `npm run build` verified-pass; lint and test verified-fail | Unknown |
| Docker Compose | Backend and frontend services in `docker-compose.yml` | verified-pass in an escalated local shell; sandbox access to the Docker socket fails | Unknown |
| FastAPI/Uvicorn | Backend image starts `backend.app.main:app` on port 8000 | Health smoke verified-pass on port 8000 in an escalated local shell | Unknown |
| Vite | Frontend dev server configured on port 5173 | Vite dev server started through Docker Compose; build verified-pass | Unknown |

Configured means the value is present in checked-in configuration. Verified
means the command was run for this document and recorded in the ledger.
Supported policy is unknown until a later approved foundation package defines
the support matrix.

## Environment

The checked-in `.env.example` file is currently empty and is not complete setup
guidance.

| Name | Used by | Required for | Sensitive | Notes |
| --- | --- | --- | --- | --- |
| `GITHUB_TOKEN` | Backend settings and external model client | Stage B external generation | Yes | Name only; do not commit real values |
| `LLM_MODEL` | Backend settings | Selecting the external model | No secret by itself | Defaults to `gpt-4o-mini` |
| `VITE_API_URL` | Frontend API client and Docker Compose frontend service | Browser-to-backend API origin | No secret by itself | Defaults to `http://localhost:8000` in code |

Do not print, paste, or commit real credential values in logs, examples,
issues, or documentation.

## Recommended Path: Docker Compose

Use this path for Stage A startup and health inspection:

```bash
docker compose up --build
```

Expected effect: builds backend and frontend images if needed, installs image
dependencies, starts the backend on port 8000, and starts the frontend on port
5173.

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
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The documented command is kept as a current investigation target, not a verified
pass. The backend Docker command uses `backend.app.main:app`, and direct host
execution may require an adjusted working directory or module path.

Frontend from `frontend/`:

```bash
npm install
npm run dev
```

`npm install` writes `node_modules/` and may update lock data depending on the
npm version and current dependency state.

## Stage A: Startup and Health

Stage A proves only local startup and the health route:

```bash
curl http://localhost:8000/health
```

A successful health response does not prove credential validity, model-provider
access, retrieval quality, populated Chroma data, or end-to-end chat readiness.

## Stage B: RAG Chat Readiness

Stage B is the real chat path. Before using `/api/v1/chat`, verify:

- `GITHUB_TOKEN` or the configured model-provider credential is available.
- Network access to the configured external model provider is acceptable.
- The embedding model is present locally or first-use download is acceptable.
- Chroma contains useful travel data.
- The current request path logs a message prefix.
- The external model request contains the user message and retrieved travel
  context.

The current public chat request body contains only:

```json
{
  "message": "Where should I go in Hanoi?"
}
```

There is no implemented user, trip, conversation, or memory identifier in this
bounded request contract.

## Commands

| Working directory | Command | Expected effect | Writes | Network | Status |
| --- | --- | --- | --- | --- | --- |
| repository root | `docker compose up --build` | Build and start frontend/backend containers | Docker state, mounted app/data paths, possible Chroma state | Possible during build and dependency install | verified-pass |
| repository root | `curl --fail --silent --show-error http://localhost:8000/health` | Inspect backend health after Stage A startup | No expected source writes | No expected external call | verified-pass |
| repository root | `docker compose down` | Stop and remove Compose containers and network when no orphan containers keep it in use | Docker state | No expected external call | verified-pass |
| repository root | `python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` | Start backend host process if import path is valid | Python cache and possible Chroma state | Possible on model/cache access | not-run |
| repository root | `pytest` | Run Python tests discovered from root | Test caches | No expected external call for normal unit tests | not-run |
| `frontend/` | `npm install` | Install frontend dependencies | `node_modules/`, npm cache, possible lock metadata | Yes | not-run |
| `frontend/` | `npm run dev` | Start Vite development server | Vite cache | No expected external call after dependencies exist | not-run |
| `frontend/` | `npm run build` | Build frontend production assets | `frontend/dist/` | No expected external call after dependencies exist | verified-pass |
| `frontend/` | `npm run lint` | Run ESLint | No expected source writes | No expected external call after dependencies exist | verified-fail |
| `frontend/` | `npm run test` | Run Vitest | Test caches | No expected external call after dependencies exist | verified-fail |
| `frontend/` | `npm run preview` | Serve built frontend output | No expected source writes | No expected external call after dependencies exist | not-run |

## Opt-in Data and Model Operations

Crawling, ETL, indexing, embedding model downloads, and model-dependent
evaluation are opt-in operations. They can mutate local data, populate Chroma,
write cache files, use network access, or call external services. They are not
part of the default quick start.

Do not run these operations inside a documentation-only change unless the
repository owner gives execution-time permission and the verification record
captures the side effects.

## Common Setup Symptoms

| Symptom | Meaning | Next check |
| --- | --- | --- |
| `/health` responds but chat fails | Backend health is narrower than Stage B readiness | Check credential, network, model, and Chroma prerequisites |
| Frontend says it cannot connect to FastAPI | Browser cannot reach the backend origin | Check backend port 8000 and `VITE_API_URL` |
| Chat returns little or irrelevant context | Chroma may be empty or low quality for the query | Inspect data/indexing readiness in a separate approved RAG task |
| First chat is slow | Embedding model or cache access may be occurring | Confirm whether model download/cache use is acceptable |
| CI appears green while tests are broken | Current CI masks backend and frontend test failures with shell fallbacks | Run local checks directly and read exit codes |

When normal setup has already failed and the problem needs diagnosis or
recovery, use the
[Local Development Recovery Runbook](docs/runbooks/local-development.md). It
owns broken-stack recovery, while this guide remains the canonical normal setup
path.

## Known Tooling Gaps

- `.env.example` is empty.
- Current CI masks backend pytest and frontend test failures, so a green CI run
  is not proof that tests pass.
- Docker Stage A requires Docker socket access outside the normal Codex
  sandbox. The sandboxed attempt failed with Docker socket permission denied;
  the escalated local-shell rerun passed.
- `docker compose down` removed the Stage A frontend and backend containers,
  but the project network remained in use because pre-existing orphan
  containers `travel_agent_db` and `travel_agent_outbox_worker` were still
  present. They were not removed under this documentation-only package.
- Frontend lint currently fails because ESLint cannot find a configuration
  file.
- Frontend tests currently fail because `jsdom` is missing and Vitest attempts
  to bind a WebSocket server on a port blocked by the sandbox.
- The host backend command in this guide is not yet verified for the current
  module layout.
- No approved support policy exists yet for Python, Node.js, Docker, dependency
  versions, or operating systems.
- No approved Stage B smoke check was run for this documentation package.

## Verification Ledger

| Date | Command | Working directory | Environment | Result | Limitation |
| --- | --- | --- | --- | --- | --- |
| 2026-08-31 | `rg -n '"(dev\|build\|lint\|preview\|test)"' frontend/package.json` | repository root | local shell | verified-pass | Proves script names only, not command success |
| 2026-08-31 | `rg -n 'FROM python:3\.11\|FROM node:18\|uvicorn\|ports:\|volumes:' backend/Dockerfile frontend/Dockerfile docker-compose.yml` | repository root | local shell | verified-pass | Proves configured values only |
| 2026-08-31 | `rg -n 'OPENAI\|API\|MODEL\|CHROMA\|DATA\|CACHE\|GITHUB\|VITE' backend/app/config.py frontend/src/services/api.js .env.example` | repository root | local shell | verified-pass | `.env.example` has no values and produced no matches |
| 2026-08-31 | `docker compose up --build` | repository root | Codex sandbox | verified-fail | Docker socket access was denied at `~/.docker/run/docker.sock`; rerun outside the sandbox was required |
| 2026-08-31 | `docker compose up --build` | repository root | escalated local shell | verified-pass | Built frontend and backend images in 919.4s; backend Uvicorn started on port 8000 and frontend Vite started on port 5173; Docker warned about pre-existing orphan containers |
| 2026-08-31 | `curl --fail --silent --show-error http://localhost:8000/health` | repository root | Codex sandbox | verified-fail | Sandbox could not connect to localhost port 8000 while the Docker stack was running |
| 2026-08-31 | `curl --fail --silent --show-error http://localhost:8000/health` | repository root | escalated local shell | verified-pass | Returned `{"status":"ok","service":"Vietnam Travel Agent API"}` and backend logged `GET /health HTTP/1.1` 200 |
| 2026-08-31 | `docker compose down` | repository root | escalated local shell | verified-pass | Removed `travel_agent_frontend` and `travel_agent_backend`; network remained in use because pre-existing orphan containers were not removed |
| 2026-08-31 | `docker compose ps --all` | repository root | escalated local shell | verified-pass | Confirmed pre-existing orphan containers `travel_agent_db` and `travel_agent_outbox_worker` remained outside Package 2 cleanup scope |
| 2026-08-31 | `npm run build` | `frontend/` | local shell | verified-pass | Vite built 342 modules and wrote `frontend/dist/` |
| 2026-08-31 | `npm run lint` | `frontend/` | local shell | verified-fail | ESLint could not find a configuration file |
| 2026-08-31 | `npm run test -- --run` | `frontend/` | local shell | verified-fail | `jsdom` dependency missing; Vitest also hit sandbox `EPERM` binding WebSocket port 24678 |
