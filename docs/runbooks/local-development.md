# Local Development Recovery Runbook

## Scope

Use this runbook only after the normal setup and startup path in the
[Development Guide](../../DEVELOPMENT.md) has failed. The Development Guide owns
installation, environment setup, normal Docker Compose startup, host-process
startup, and routine verification. This runbook owns diagnosis and recovery of
an already-broken local stack.

The current stack is development-only. Its backend normally uses port 8000, its
frontend uses port 5173, Docker Compose injects the local `.env` into the
backend, and local travel-knowledge state may exist under `data/chromadb`.

## Safety Rules

1. Diagnose before changing state.
2. Prefer read-only checks, then process/container restart, then rebuild state.
3. Treat `data/`, especially `data/chromadb`, as persistent project data.
4. Do not print `.env`, token values, full prompts, or private user content while
   collecting evidence.
5. Do not remove unrelated containers, networks, volumes, caches, or data just
   because they appear stale.
6. Persistent-data deletion is never a default recovery step.
7. Stop if recovery would require a code/configuration change outside the
   approved task, a destructive Git operation, or an unreviewed data migration.

Action classes used below:

- **Read-only diagnostic:** inspects local state without intentionally changing it.
- **Process/container lifecycle:** starts, stops, or restarts current processes or containers.
- **Local cache/rebuild state:** rebuilds replaceable images/dependencies/cache state.
- **Persistent project data:** changes durable project data and requires a separate explicit recovery decision.

## Triage Sequence

Start with the smallest failing boundary:

```bash
docker info
docker compose ps --all
curl --fail --silent --show-error http://localhost:8000/health
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

These are read-only diagnostics. Do not jump directly to rebuilds or data
cleanup. Record which check first fails, then use the matching section below.

## Docker Daemon or Socket Failure

**Symptom:** `docker compose` cannot connect to the daemon or reports socket
permission/access errors.

**Diagnostic:** run `docker info`. This is read-only and distinguishes a Docker
daemon/socket problem from an application problem.

**Impact:** the Compose stack cannot be inspected or managed; it does not by
itself prove backend, data, or source corruption.

**Reversible recovery:** start or restore access to the local Docker runtime
using the host's normal Docker application/service controls, then rerun
`docker info` and `docker compose ps --all`. This is process/container
lifecycle state outside repository files.

**Verify:** Docker reports server information and Compose can list project
services.

**Stop:** if fixing socket ownership/permissions requires privileged filesystem
changes you do not understand, stop and review the host setup instead of
changing repository files or deleting Docker state.

## Port Conflicts

**Symptom:** backend or frontend startup reports that port 8000 or 5173 is
already in use, or the browser reaches an unexpected service.

**Diagnostic:** use the read-only checks:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
docker compose ps --all
```

**Impact:** only the conflicting listener is established; do not assume the
conflicting process belongs to this project.

**Reversible recovery:** if the listener is a confirmed Travel Agent process or
container, stop that specific process/service through its normal lifecycle
control, then restart only the intended Travel Agent service. Do not terminate
an unknown process by PID merely because it owns the port.

**Verify:** the expected service owns the port and `/health` succeeds for the
backend.

**Stop:** if the listener is unrelated or its owner is unclear, choose a
separately approved local-port change instead of killing it.

## Backend Health Failure

**Symptom:** `GET /health` fails, returns a non-success status, or cannot connect.

**Diagnostic:** inspect service state and bounded recent logs:

```bash
docker compose ps --all
docker compose logs --tail=100 backend
curl --fail --silent --show-error http://localhost:8000/health
```

Logs are diagnostic evidence; redact any user content or secret-like value
before preserving them.

**Impact:** process health is failing. This does not yet establish a Chroma,
model-provider, or RAG-quality failure.

**Reversible recovery:** restart only the backend service:

```bash
docker compose restart backend
```

This is process/container lifecycle state.

**Verify:** rerun `/health`, then use the Development Guide's Stage B checks
only when chat readiness is the actual target.

**Stop:** if startup fails because source, dependency, configuration, or data
contracts need modification, return to a governed implementation task.

## Frontend-to-Backend Connectivity Failure

**Symptom:** the frontend runs but reports that it cannot reach FastAPI.

**Diagnostic:** first prove backend reachability independently, then inspect the
configured frontend origin without exposing `.env`:

```bash
curl --fail --silent --show-error http://localhost:8000/health
rg -n 'VITE_API_URL|localhost:8000' docker-compose.yml frontend/src
docker compose logs --tail=100 frontend
```

**Impact:** usually browser/frontend-to-API routing; a successful backend health
check means the backend process itself is reachable from the host.

**Reversible recovery:** restart the frontend service if its process is stale:

```bash
docker compose restart frontend
```

**Verify:** reload the client and confirm it reaches the expected backend
origin. A successful health check still does not prove chat/model readiness.

**Stop:** if the fix requires changing public origins, CORS, proxying, or
deployment topology, that is not local recovery and needs approved design work.

## Missing Model Credential

**Symptom:** Stage A health works but model-dependent chat fails with a missing
or rejected credential.

**Diagnostic:** check presence without printing the value:

```bash
test -n "${GITHUB_TOKEN:-}" && printf 'GITHUB_TOKEN is set\n' || printf 'GITHUB_TOKEN is not set\n'
```

This is a read-only shell-state check. Do not run `cat .env`, `env`, or another
command that may expose unrelated secrets in review evidence.

**Impact:** external generation may fail while local process health remains OK.

**Reversible recovery:** provide the credential through the normal local secret
path described by the Development Guide. Do not commit it or paste it into a
runbook, issue, screenshot, or log.

**Verify:** rerun the smallest approved model-dependent smoke check without
recording the token value.

**Stop:** if the credential may be leaked or unexpectedly invalidated, use the
[Incident Response Runbook](./incident-response.md) rather than repeatedly
reusing it.

## External Model or Network Failure

**Symptom:** credential presence is established but generation times out,
returns provider/network errors, or model availability is degraded.

**Diagnostic:** inspect bounded backend logs, then check DNS/connectivity only
if network diagnostics are allowed in the current environment:

```bash
docker compose logs --tail=100 backend
nslookup models.inference.ai.azure.com
```

The DNS lookup is an external-network diagnostic and may be recorded by local or
network infrastructure. It does not mutate repository or hosting settings.

**Impact:** model-dependent Stage B readiness is degraded; `/health` may still
pass because health is narrower than chat readiness.

**Reversible recovery:** retry only after confirming the provider/network fault
is transient and the retry will not create unsafe cost or rate pressure. Restart
the backend only when local connection/process state is suspected.

**Verify:** run the approved model-dependent smoke check and record success or
the provider failure class, not full user content.

**Stop:** suspected provider compromise, credential misuse, repeated unexplained
failures, or required provider changes route to incident/governed design work.

## Chroma or Local Data-state Problems

**Symptom:** chat starts but retrieval is empty, inconsistent, or fails while
local process health remains available.

**Diagnostic:** inspect the known Chroma path and backend logs without mutating
the store:

```bash
ls -la data/chromadb
find data/chromadb -maxdepth 2 -type f -print
docker compose logs --tail=100 backend
```

**Impact:** local travel-knowledge retrieval may be unavailable or invalid. The
current Chroma store is travel knowledge, not user/trip memory.

**Reversible recovery:** first confirm whether the expected dataset/index was
ever created and whether the configured path is correct. Indexing and embedding
operations are opt-in and state-changing; run them only under the approved RAG
workflow that owns their inputs and verification.

**Verify:** use the approved RAG readiness/evaluation check after the store is
restored. Process health alone is insufficient.

**Stop:** do not delete or recreate `data/chromadb` as a troubleshooting shortcut.
If integrity is uncertain, preserve the state and route recovery through the
incident or approved data/indexing workflow.

## Stale Containers and Networks

**Symptom:** Compose reports stale/orphan resources, expected services conflict
with old containers, or teardown does not remove a network because other
containers still use it.

**Diagnostic:** inventory before acting:

```bash
docker compose ps --all
docker ps -a --filter name=travel_agent_
docker network ls
```

**Impact:** stale resources may be unrelated to the current Compose definition.
Earlier verification observed pre-existing `travel_agent_db` and
`travel_agent_outbox_worker` containers; their existence is not permission to
remove them.

**Reversible recovery:** restart or recreate only the services owned by the
current Compose file when their ownership is clear:

```bash
docker compose restart backend frontend
```

**Verify:** `docker compose ps --all` shows the intended current services and
the backend health check succeeds.

**Stop:** do not use broad orphan, volume, or network cleanup when ownership is
unclear. Identify the resource owner and approved scope first.

## Dependency or Image Rebuild Problems

**Symptom:** Compose build fails, an image is stale, or installed dependencies
do not match the current Dockerfile/package files.

**Diagnostic:** read the build error first and identify which stage/package
failed. Inspect current image/service state with `docker compose ps --all`.

**Impact:** replaceable local build/cache state may be inconsistent; this does
not imply persistent project data is corrupt.

**Reversible recovery:** rebuild the current project images:

```bash
docker compose build backend frontend
```

This changes local image/build state but not repository files or persistent
project data.

**Verify:** start through the normal Development Guide flow and rerun Stage A.

**Stop:** if recovery requires changing dependency versions, lockfiles,
Dockerfiles, or base images, return to a governed code/dependency change rather
than editing them ad hoc.

## Persistent-data Recovery Boundary

Persistent project data includes at least the bind-mounted `data/` tree and the
known Chroma path `data/chromadb`. It is outside the default cleanup path.

Before any destructive persistent-data action, a separate approved recovery
decision must identify the exact target, establish that the data is backed up or
reproducibly regenerable, describe impact on derived/replicated state, and define
post-recovery verification. Unrelated volumes, directories, containers, and
data must not be removed.

This runbook intentionally provides no persistent-data deletion command. If
deletion becomes necessary, document the exact resource and recoverability
evidence in the governing incident or data-recovery plan before execution.

## Evidence to Record

Record the smallest useful evidence set:

- timestamp and failing boundary;
- command/check name and exit/result state;
- affected component or resource identifier;
- redacted error class or short excerpt;
- recovery action and its action class;
- verification result after recovery.

Do not preserve `.env` contents, token values, full prompts, full conversations,
or unnecessary private data.

## Escalation and Stop Conditions

Stop local recovery and return to governed work when the next action would:

- modify source, dependencies, Docker/Compose configuration, or environment
  contracts;
- delete persistent project data or an unowned Docker resource;
- require a production/cloud/provider architecture choice;
- expose or rotate a credential because compromise is suspected;
- mask a repeatable RAG/data-integrity failure instead of diagnosing it;
- perform destructive Git or repository delivery actions.

Security or integrity incidents route to
[Incident Response](./incident-response.md). Public deployment questions route
to [Deployment Readiness](./deployment.md).
