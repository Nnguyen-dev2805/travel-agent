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
| `APP_DB_PATH` | Backend settings, the local workspace adapter, the local conversation adapter, and the local memory adapter | Local trip workspace, conversation, and memory routes | No secret by itself | Defaults to `data/app/travel_agent.sqlite3`; one shared local SQLite file per ADR 0004; local development state only |
| `WORKSPACE_DB_PATH` | Backend settings only | Nothing new; kept so an existing local environment still works | No secret by itself | **Deprecated alias for `APP_DB_PATH`.** Used only when `APP_DB_PATH` is unset, and logs one deprecation warning naming the variable without its value |
| `MEMORY_RETRIEVAL_ENABLED` | Backend settings and chat orchestration | Enabling R6 memory retrieval for bound chat turns | No secret by itself | Defaults to `false`. With it disabled, chat behavior remains R4/R5 behavior |
| `MEMORY_PROMOTION_MIN_CONFIDENCE` | Backend settings and promotion policy | Minimum candidate confidence eligible for promotion | No secret by itself | Defaults to `0.75` |
| `MEMORY_MAX_SELECTED` | Backend settings and memory retrieval | Maximum memory records selected per bound chat turn | No secret by itself | Defaults to `5` |

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

## Recommended Path: Docker Compose

Use this path for Stage A startup and health inspection:

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

### Local Trip Workspace Routes

Milestone `R3` adds three backend-only routes for creating and inspecting local
trip workspace records. They are mounted beside chat under `/api/v1` and do not
change the chat request or response contract.

| Method and path | Purpose |
| --- | --- |
| `POST /api/v1/workspaces` | Create one workspace and return `201` with the stored record |
| `GET /api/v1/workspaces/{workspace_id}` | Return one workspace, or `404` when absent |
| `GET /api/v1/workspaces?owner_user_id=<value>` | Return `{"workspaces": [...]}` for one owner scope label, newest first |

These routes need no credential, embedding model, Chroma data, or network access.
They are independent of Stage B readiness.

Create a workspace locally:

```bash
curl --fail --silent --show-error \
  --request POST http://localhost:8000/api/v1/workspaces \
  --header 'Content-Type: application/json' \
  --data '{"owner_user_id":"local-user","title":"Da Nang family trip","destination_scope":"Da Nang and Hoi An","date_window":{"start_date":"2026-12-20","end_date":"2026-12-25"}}'
```

List workspaces for one owner scope label:

```bash
curl --fail --silent --show-error \
  'http://localhost:8000/api/v1/workspaces?owner_user_id=local-user'
```

Field rules: `owner_user_id` and `title` are required and trimmed; `title` is at
most 120 characters; `destination_scope` is optional and at most 160 characters;
`date_window` bounds are optional but `end_date` must not precede `start_date`;
`planning_status` is one of `idea`, `planning`, `booked`, `active`, `completed`,
`cancelled`, `archived` and defaults to `idea`. `workspace_id`, `retention_state`,
`created_at`, and `updated_at` are server-owned. Invalid input returns `422` and
writes no record.

Two limitations are deliberate and must not be described otherwise:

1. **`owner_user_id` is a local development scope label.** It is not
   authentication, authorization, a verified principal, or tenant isolation.
   Listing filters deterministically by that label and nothing more. Do not
   expose these routes publicly.
2. **The local database is development state.** The SQLite file at `APP_DB_PATH`
   is a local adapter per ADR 0003 and a shared application store per ADR 0004. It
   does not establish a production database, migration framework, backup,
   restore, concurrency, retention, or deletion contract. `R3` implements no
   workspace update, archive, or deletion route.

The adapter creates the parent directory on first use and records `('workspaces',
1)` in the shared `schema_versions` table. If the database records a different
workspace schema version, or carries a store marker this build does not
recognize, the adapter fails closed with a controlled error instead of migrating.
Tests always use temporary database paths and never touch the default developer
database.

### Local Conversation Routes

Milestone `R4` adds five backend-only routes for creating conversations and
appending and reading messages. They are mounted beside chat and workspaces under
`/api/v1` and change neither the chat nor the workspace contract.

| Method and path | Purpose |
| --- | --- |
| `POST /api/v1/workspaces/{workspace_id}/conversations` | Create one conversation and return `201` with the stored record |
| `GET /api/v1/workspaces/{workspace_id}/conversations` | Return `{"conversations": [...]}` for one workspace, newest updated first |
| `GET /api/v1/conversations/{conversation_id}` | Return one conversation, or `404` when absent |
| `POST /api/v1/conversations/{conversation_id}/messages` | Append one message and return `201` with its server-assigned `sequence` |
| `GET /api/v1/conversations/{conversation_id}/messages` | Return `{"messages": [...], "next_cursor": ...}` in `sequence` ascending order |

Like the workspace routes, these need no credential, embedding model, Chroma
data, or network access, and they are independent of Stage B readiness.

Create a conversation under an existing workspace:

```bash
curl --fail --silent --show-error \
  --request POST http://localhost:8000/api/v1/workspaces/tw_example/conversations \
  --header 'Content-Type: application/json' \
  --data '{"title":"Da Nang food plan"}'
```

Append a message:

```bash
curl --fail --silent --show-error \
  --request POST http://localhost:8000/api/v1/conversations/cv_example/messages \
  --header 'Content-Type: application/json' \
  --data '{"role":"user","content":"Nên đi Đà Nẵng vào tháng mấy?"}'
```

Read history with cursor pagination:

```bash
curl --fail --silent --show-error \
  'http://localhost:8000/api/v1/conversations/cv_example/messages?limit=50'
```

Field rules. `title` is optional, trimmed, at most 120 characters, and a blank
title normalizes to absent. `content` is required, trimmed, non-empty, and
deliberately has no maximum length, because the chat route already accepts an
unbounded `message`; request size limiting belongs at the API boundary and is a
known gap. `role` is one of `user`, `assistant`, `tool`, `system_event`, but the
public append route accepts only `user` and `system_event` and returns `422` for
the others. `source` is one of `ui`, `tool`, `model`, `system`, `import` and
defaults to `ui`. `trace_visibility` is `excluded` or `included` and defaults to
`excluded`, so no stored message becomes evaluation input without an explicit
decision. `conversation_id`, `message_id`, `sequence`, `retention_state`,
`created_at`, and `updated_at` are server-owned. History `limit` defaults to `50`
and is capped at `200`; an out-of-range limit, an unknown cursor, or a cursor from
another conversation returns `422`.

Four limitations are deliberate and must not be described otherwise:

1. **These routes are unauthenticated.** Conversations inherit scope from their
   parent workspace, whose `owner_user_id` is a local development scope label.
   `R4` adds no authentication, authorization, sessions, or tenant isolation, and
   claims no cross-user or cross-workspace isolation beyond deterministic
   repository filtering. Do not expose these routes publicly.
2. **Local SQLite is not production storage readiness.** `APP_DB_PATH` is one
   local file for local development. `R4` settles no production database,
   migration framework, backup, restore, concurrency, retention, or deletion
   policy.
3. **The frontend is unchanged, so real browser traffic is not persisted.** `R4`
   delivers the capability to persist a turn; the browser client still holds its
   visible transcript in volatile React state. Frontend work was explicitly
   deferred and requires separate approval.
4. **Nothing is deleted, summarized, or edited.** `R4` creates only `active`
   conversations, implements no retention transition and no deletion path, and
   gives `summary` no column and no producer. Messages are immutable after insert
   and carry no retention state of their own; they follow their parent
   conversation.

Message `content` is user content. It is stored, never logged, and never returned
in an error body. Logs and HTTP error details carry identifiers, sequence
numbers, roles, counts, route or action names, and failure classes only.

### Binding a Chat Turn to a Conversation

`POST /api/v1/chat` accepts an optional `conversation_id`. The field is additive:
a request that omits it behaves exactly as it did before `R4`.

Unbound request and response, unchanged from `R3`:

```json
{ "message": "Nên đi Đà Nẵng vào tháng mấy?" }
```

```json
{ "reply": "...", "model": "gpt-4o-mini", "citations": [] }
```

There is no `conversation` key at all on this path, not even a null one.

Bound request and response:

```json
{ "message": "Nên đi Đà Nẵng vào tháng mấy?", "conversation_id": "cv_example" }
```

```json
{
  "reply": "...",
  "model": "gpt-4o-mini",
  "citations": [],
  "conversation": {
    "conversation_id": "cv_example",
    "user_message_id": "ms_user_example",
    "assistant_message_id": "ms_assistant_example",
    "persisted": true
  }
}
```

The user turn is persisted before any model call, so an unknown `conversation_id`
returns `404` and a failed user-turn write returns `500`, both without calling the
model provider. If generation succeeds but the assistant turn cannot be stored,
the reply is still returned with `persisted` `false` and a `null`
`assistant_message_id`, so a persistence gap is visible rather than silent.

An unbound turn constructs no conversation storage at all, so it cannot be broken
by a storage failure and does not create the local database file.

### Local Memory Routes

`R5` adds backend-only shadow memory extraction. It measures candidates but
never uses them in answers.

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/<workspace_id>/conversations/<conversation_id>/memory/extractions \
  -H 'Content-Type: application/json' -d '{}'
curl 'http://localhost:8000/api/v1/workspaces/<workspace_id>/memory/extractions'
curl 'http://localhost:8000/api/v1/workspaces/<workspace_id>/memory/candidates?run_id=<run_id>'
```

Rules:

1. The trigger route accepts an empty body or `{}` only and always creates a
   `manual` run. Any caller-supplied field returns `422`.
2. Only messages explicitly persisted with `trace_visibility` `included`
   become accepted candidates. Ordinary chat-bound turns stay `excluded` and
   are never accepted.
3. Candidate `text` is excluded from responses. Listings carry identifiers,
   counts, controlled reason codes, sensitivity labels, confidence, and
   redacted summaries only.
4. `accepted` means accepted into the shadow candidate set for evaluation,
   not promoted into answer-eligible memory. There is no retrieval,
   personalization, deletion, or frontend surface.
5. Requires no credential, model, or Chroma state. Writes the local SQLite
   file at `APP_DB_PATH`.

### Local Memory Retrieval

`R6` promotes measured candidates and retrieves records for bound chat
turns, but only when `MEMORY_RETRIEVAL_ENABLED` is true. The gate defaults
to false.

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/<workspace_id>/memory/promotions \
  -H 'Content-Type: application/json' -d '{}'
MEMORY_RETRIEVAL_ENABLED=true python -m uvicorn backend.app.main:app --reload
```

Rules:

1. Promotion accepts only eligible accepted candidates; everything else
   becomes a controlled skip reason. Corrections suppress older same-scope
   records, erring toward forgetting on ambiguity.
2. Gate-off and unbound turns keep exact R4/R5 behavior and resolve no
   memory storage. Gate-on bound turns report selected memory IDs and
   reasons in an additive `memory` object; memory never becomes a citation.
3. Retrieval selects `active`, unexpired, non-sensitive records in matching
   scope only. Deleted, expired, superseded, secret-like, and out-of-scope
   records are never selected.
4. Answer-quality claims stay `INCONCLUSIVE` without a provider-backed
   judge; run the retrieval evaluation command for measured gates.

```bash
python -m backend.memory.evaluation.cli run-retrieval --suite r6-retrieval-v0.1
```

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
| Local workspace routes | repository root | `curl` requests to `/api/v1/workspaces` while the backend runs | Workspace records can be created and inspected locally | Local SQLite file at `APP_DB_PATH` | No expected external call | Requires no credential, model, or Chroma state |
| Local conversation routes | repository root | `curl` requests to `/api/v1/workspaces/{workspace_id}/conversations` and `/api/v1/conversations/...` while the backend runs | Conversations and messages can be created and read locally | Local SQLite file at `APP_DB_PATH` | No expected external call | Requires no credential, model, or Chroma state |
| Bound chat turn | repository root | opt-in chat request to `/api/v1/chat` carrying `conversation_id` | A chat turn is persisted and reports its persistence outcome | Local SQLite file at `APP_DB_PATH`, possible logs/cache state | Yes, because generation still calls the model provider | Opt-in, not default CI |
| Local memory routes | repository root | `curl` requests to `/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/memory/extractions` and `/api/v1/workspaces/{workspace_id}/memory/...` while the backend runs | Shadow candidates can be extracted and inspected locally | Local SQLite file at `APP_DB_PATH` | No expected external call | Requires no credential, model, or Chroma state |
| Local memory evaluation | repository root | `python -m backend.memory.evaluation.cli run-shadow --fixture docs/evaluation/fixtures/memory/r5-shadow-v0.1/manifest.json --output-dir docs/reports/memory` | Shadow report with result state and hard-gate evidence | Markdown and JSON reports | No expected external call | Deterministic; writes reports only |
| Local memory promotion | repository root | `curl` request to `/api/v1/workspaces/{workspace_id}/memory/promotions` while the backend runs | Eligible candidates become active records with skip reasons | Local SQLite file at `APP_DB_PATH` | No expected external call | Requires no credential, model, or Chroma state |
| Local memory retrieval evaluation | repository root | `python -m backend.memory.evaluation.cli run-retrieval --suite r6-retrieval-v0.1` | Retrieval report with paired metrics, hard-gate evidence, and `INCONCLUSIVE` answer-quality fields | Markdown and JSON reports | No expected external call | Deterministic; writes reports only |
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
| Workspace route returns `500` | Local workspace storage could not be opened, initialized, or written | Check that `APP_DB_PATH` is writable and that its recorded workspace schema version matches the running build |
| Workspace list returns an empty array | No record exists for that exact owner scope label | Confirm the `owner_user_id` value; listing filters by exact label after trimming |
| Conversation route returns `404` | The parent workspace or the conversation does not exist | Create the workspace first, then the conversation; a chat request never creates one implicitly |
| Conversation route returns `422` on append | A restricted role, an ungoverned vocabulary value, or blank content was submitted | The public route accepts only `user` and `system_event`; `assistant` and `tool` are written by the orchestrator |
| Conversation history returns `422` | The `limit` is outside `1` to `200`, or the cursor is unknown or belongs to another conversation | Re-read the page with a cursor returned by that same conversation |
| Bound chat returns `persisted` `false` | Generation succeeded but the assistant turn could not be stored | The reply is still valid; check that `APP_DB_PATH` is writable, then re-read history |
| Memory trigger returns `404` | The workspace or conversation does not exist | Create the workspace first, then the conversation; a chat request never creates one implicitly |
| Memory trigger or list returns `409` | The conversation or run does not belong to the requested workspace | Re-check the workspace/conversation/run identifiers; filters never cross workspace scope |
| Memory trigger returns `422` on body | A caller-supplied `trigger` or unknown field was submitted | Send an empty body or `{}`; the route always creates a `manual` run |
| Memory run shows `completed_with_rejections` | At least one candidate was rejected, marked for user action, or invalid | Read the candidate `reason` codes; this is the normal shadow outcome, not a failure |
| Promotion promotes nothing | No eligible accepted candidates, or the same candidates were already promoted | Read the skip reasons; re-promoting is a governed duplicate skip, not a failure |
| Bound chat has no `memory` key | The feature gate is off or the turn is unbound | Set `MEMORY_RETRIEVAL_ENABLED=true` for a bound turn; gate-off behavior is intentionally identical to R4/R5 |
| Bound chat reports `skipped` | Memory storage or retrieval failed for the turn | The reply is still valid RAG output; check that `APP_DB_PATH` is writable, then re-read the trace |
| A deprecation warning names `WORKSPACE_DB_PATH` | `APP_DB_PATH` is unset and the deprecated alias is being honored | Set `APP_DB_PATH` instead; the alias is retained only for compatibility |

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
