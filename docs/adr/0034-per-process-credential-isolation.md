# ADR 0034: Each Process Receives Only the Credential Its Role Requires

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-12 |
| Decision owners | Repository owner |
| Scope | Where each process's database credential lives, what determines which variables reach a process, and what enforces the boundary |
| Governing spec | [Worker Authority: Credential, Lease Time, and Fence Semantics](../specs/2026-09-12-worker-authority-credential-lease-fence-design.md) v0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

ADR 0029 made the background Memory worker its own process so that one process would
not hold two database identities, and stated the requirement in the deployment file
itself (`docker-compose.yml:66-69`):

```yaml
    environment:
      # Only the worker credential. This service must never receive
      # DATABASE_URL, which names the API's `travel_app` role.
      - WORKER_DATABASE_URL=postgresql+psycopg://travel_worker:...@db:5432/...
    env_file:
      - path: .env
        required: false
```

The comment is not true. `env_file: .env` injects every key in that file into the
container, and `.env` contains `DATABASE_URL`:

```
$ cut -d= -f1 .env
GITHUB_MODELS_URL
GITHUB_TOKEN
LLM_MODEL
LOCAL_AUTH_TOKENS_JSON
DATABASE_URL
```

So the worker process holds both credentials: `WORKER_DATABASE_URL`, which is correct,
and `DATABASE_URL`, which is the API's. The backend service is configured the same way
(`:44-46`), so the leak is symmetric — adding `WORKER_DATABASE_URL` to `.env` would
hand the API the worker's credential just as readily.

The severity today is bounded, and it is worth stating precisely rather than
overstating. `worker_dsn()` (`backend/app/config.py:145-170`) has no fallback to
`DATABASE_URL`: it returns an explicit `WORKER_DATABASE_URL`, or assembles a DSN from
`PG_*` with the worker password. The worker builds its engine from it
(`backend/memory/write_pipeline/runtime.py:161`). So the worker does **not** currently
connect as `travel_app`. This is a latent boundary defect, not an active wrong-role
connection — and it becomes active the moment any code in the worker's import graph
resolves the API DSN, which nothing prevents.

What makes this architecture rather than configuration is the mechanism. The boundary
ADR 0029 declared is enforced by nothing: it holds because of the current contents of
one file, and it is widened silently — with no failure, no warning, and no test — by
adding a key to that file. A boundary whose only enforcement is that nobody has
broken it yet is documentation.

## Decision

**Each process receives only the credential its role requires, declared as an explicit
allow-list, and a process refuses to start if the other role's database credential is
present in its environment.**

Specifically:

1. Neither the `backend` nor the `worker` service declares `env_file`. Each declares
   an explicit `environment:` list, and values are supplied by Compose interpolation
   of `.env` (`${VAR}` / `${VAR:-default}`) — the mechanism the backend service
   already uses for `APP_DB_PASSWORD` (`docker-compose.yml:43`). `.env` remains the
   place values live; it stops deciding which keys a container receives.
2. The worker's list contains `WORKER_DATABASE_URL` and the model and Memory-gate
   settings. It does not contain `DATABASE_URL`.
3. The backend's list contains `DATABASE_URL`, the model settings, and the auth
   settings. It does not contain `WORKER_DATABASE_URL`.
4. `assert_credential_isolation(role)` takes the role the process is running as and
   the environment mapping, and raises when the other role's database key is present.
   The error names the key, never a value.
5. It is called from the two process entry points only — the API lifespan and the
   worker's `main`. It is **not** called from `RuntimeContainer.__init__`,
   `build_worker`, or the FastAPI request dependency, so constructing these objects in
   a test does not require a curated environment.
6. There is no bypass flag. `ALLOW_PRIVILEGED_DB_ROLE` already exists for local
   development and is documented as weakening tenant isolation; a second escape hatch
   on a boundary this decision exists to enforce would reproduce that pattern.

The allow-list and the guard are selected **together**. The allow-list makes the
intended environment explicit and reviewable in one place; the guard makes a
deviation from it fatal. Either alone leaves the boundary unenforced in a way that
matters.

## Alternatives Considered

### Two per-service environment files

**Approach.** Keep `env_file`, and split it: `.env.backend` and `.env.worker`, each
containing only its own keys, with each service pointing at the right one.

**Benefits.** No change to how Compose injects variables, so no interpolation
escaping questions. Preserves the distinction between an absent key and an empty one,
which interpolation blurs. Immediately familiar to anyone reading the current file.

**Costs.** The boundary is not visible in `docker-compose.yml` — a reviewer must open
two files and diff them to see what each process receives. A key placed in the wrong
file is a silent leak, which is the failure mode being fixed. And it binds Compose
only: a `docker run`, a systemd unit, or a shell with both variables exported is
unaffected, and nothing fails.

**Rejected because.** It moves the leak rather than making it visible, and it leaves
the boundary enforced by one deployment tool.

### Compose allow-list only, with no startup guard

**Approach.** Do the per-service `environment:` allow-lists and stop there.

**Benefits.** The smallest change. No new production code path, so nothing new to get
wrong at startup and nothing new to test.

**Costs.** The only evidence that the boundary holds is a reading of
`docker-compose.yml`. Nothing fails if the worker is started another way with
`DATABASE_URL` exported, and the boundary cannot be asserted in a unit test, because
it is a property of a YAML file rather than of the program.

**Rejected because.** A boundary that does not fail closed outside one deployment tool
is documentation. The guard is what makes the boundary testable and
mechanism-independent — and it is the combination, not the guard alone, that is
selected.

### Docker secrets or an external secret store

**Approach.** Move credentials out of the environment entirely, into Compose secrets
or a managed secret store, and mount them per service.

**Benefits.** Credentials are not in the process environment at all, so they cannot
leak through an environment dump, a crash report, or a child process. Per-service
scoping is inherent.

**Costs.** New deployment infrastructure and a new failure mode for every operator.
It also does not remove the need for a per-service allow-list, because a secret that
is mounted into both services is the same leak with a longer name.

**Rejected for now, not dismissed.** It is the right destination for a deployed
system and a poor first step, because it changes the deployment story for every
operator to fix a defect that an allow-list and a guard close today. It becomes the
right answer when there is a secret store to use, and that trigger is recorded here so
the choice can be revisited rather than rediscovered.

### Make the guard a warning instead of a startup failure

**Approach.** Log a warning when the other role's credential is present, and continue.

**Benefits.** No process can be prevented from starting by a leaked variable, so a
misconfigured environment degrades rather than halts.

**Costs.** A warning in a log is not read, and the process then runs with a credential
it must never use. The boundary's failure mode becomes invisible, which is exactly the
state this ADR is written to leave behind.

**Rejected because.** This is a trust boundary. The correct response to a boundary
violation at startup is to refuse to start, where the operator is looking.

## Consequences

**Positive.**

- Neither process holds the other's database credential, and adding a key to `.env` no
  longer widens both at once.
- The boundary is assertable in a unit test, so it can regress only with a failing
  test rather than silently.
- The boundary holds under any deployment mechanism, not only Compose, because the
  guard is in the program.
- The intended environment for each service is stated in one reviewable place.

**Negative.**

- Every variable a service needs must now be listed. A key that was reaching a
  container implicitly will stop doing so, and the service fails visibly on first use
  rather than silently at the point where it mattered.
- The distinction between an absent variable and an empty one changes for interpolated
  keys. The plan must verify this explicitly for `GITHUB_TOKEN` and
  `LOCAL_AUTH_TOKENS_JSON`, whose absence has different meaning from their emptiness.
- A developer whose shell exports both variables can no longer start the worker
  locally without unsetting one. That is intended, but it is friction, and it is the
  reason there is no bypass: a bypass would be used.
- The guard is a new startup failure mode, so a misconfigured environment that used to
  start now does not.

**Neutral.**

- `.env` keeps its contents and its role as the value source. Only which keys reach a
  container changes.
- No credential value is added to any log, error, or document; the guard names keys.
- `worker_dsn()` and `database_dsn()` are unchanged; this decision is about what
  reaches the environment, not how a DSN is assembled.
- No schema change, no migration, no `ALEMBIC_HEAD` movement.

## References

1. [ADR 0028: The background worker claims through a role-scoped policy, and binds a tenant after the claim](./0028-worker-role-and-outbox-claim-boundary.md)
2. [ADR 0029: The background memory worker runs as its own service under its own role](./0029-the-memory-worker-runs-as-its-own-service.md)
3. [Worker Role and Tenant-Bound Outbox Claim](../specs/2026-09-11-worker-role-tenant-bound-outbox-claim-design.md)
4. [Worker Authority: Credential, Lease Time, and Fence Semantics](../specs/2026-09-12-worker-authority-credential-lease-fence-design.md) — governing specification
5. [Security Policy](../../SECURITY.md) — the repository's trust-boundary and secrets rules
