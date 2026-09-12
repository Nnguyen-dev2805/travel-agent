# Worker Authority: Credential, Lease Time, and Fence Semantics

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-12 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Which credential each process holds, which clock decides whether an outbox lease is valid, and what a worker may cancel when a write is fenced |
| Related issue | External review findings 1, 2 and 3 (2026-09-12), verified in the third review |
| Superseded document | None. This design tightens what ADR 0014, ADR 0028 and ADR 0029 already built |

## Summary

Three confirmed defects share one property: **a party is exercising authority it
does not own.** Each was re-verified against the working tree, not carried over
from an earlier report.

| Defect | The party exercising borrowed authority | Measured evidence |
| --- | --- | --- |
| The worker holds the API's credential | The worker process holds `DATABASE_URL`, which names `travel_app` | `docker-compose.yml:74` hands `worker` the shared `.env`; `.env` contains `DATABASE_URL` |
| A lease is judged valid by a timestamp the caller supplies | The application decides whether its own lease still holds | `worker.py:152` captures `now`, used at `:363`, `:387`, `:413`; `:430` captures `current_now`, used at `:527` |
| A lost lease cancels a different turn's work | A worker decides that its own lease loss invalidates a whole conversation | `outbox.py:787` cancels every `PENDING` row; `worker.py:498` calls it on any `FencedWriteError` |

Two amplifiers make the second and third defects reachable rather than theoretical:

1. **`WORKER_ID` defaults to the constant `"memory_worker_1"`** (`backend/app/config.py:91`).
   The lease-holder test is `holder == lease_owner`, so two worker replicas sharing
   that default are indistinguishable. Every `cancel_events(lease_owner=…)` call is
   then scoped to *both* of them.
2. **The fence collapses six causes into one exception with a free-text message.**
   `check_conversation_fence` and `check_outbox_lease`
   (`backend/conversations/postgres_repository.py:1116-1166`) return six distinct
   sentences; `_check_fence` (`backend/memory/write_pipeline/postgres.py:514-524`)
   raises `FencedWriteError(err)`. The worker cannot branch on a sentence, so it
   treats a lease loss and a conversation deletion identically.

Severity is bounded today: both Memory gates default `False`, so no worker runs.
The credential leak is currently **inert** — `worker_dsn()`
(`backend/app/config.py:145-170`) has no `DATABASE_URL` fallback, and the worker
builds its engine from it (`backend/memory/write_pipeline/runtime.py:161`). This is
a latent boundary defect, not an active wrong-role connection. It becomes active
the moment any code in the worker's import graph resolves the API DSN, and it is
wrong by construction regardless.

## Context

ADR 0014 established the transactional outbox and its idempotent worker. ADR 0027
added the turn-readiness gate. ADR 0028 gave the worker its own least-privilege
role and a bounded policy on the queue. ADR 0029 made the worker its own process
holding only the `travel_worker` credential, and states the requirement this design
enforces:

> Only the worker credential. This service must never receive `DATABASE_URL`, which
> names the API's `travel_app` role. (`docker-compose.yml:67-68`)

The deployment does not honour its own stated requirement. `docker-compose.yml:74`
attaches `env_file: .env` to the `worker` service, and `.env` contains
`DATABASE_URL`. The reverse direction is unguarded too: any key added to `.env` —
including `WORKER_DATABASE_URL` — is injected into *both* services. The boundary
ADR 0029 declared is currently a comment, not a control.

The lease defects are properties of the worker, which is why they were deferred
until it existed. The memory-worker-runtime design
(`2026-09-12-memory-worker-runtime-design.md`) deliberately scoped them out: it
fixed *which* worker may claim (ADR 0030) and *when* an effect may be written
(ADR 0031), but left the lease's clock and the fence's cancellation authority
untouched. Both are now the last open correctness items in the claim path.

## Users

1. **The repository owner.** They approve a trust boundary and two correctness
   rules, and they need each to be enforceable rather than aspirational.
2. **The operator.** They deploy the worker, scale it, and restart it. They depend
   on a restart or a second replica not destroying queued work.
3. **The authenticated user.** They never see the worker. They depend on memory
   formed from turn 2 not being cancelled because turn 1's lease expired.
4. **The API runtime.** It must not be able to reach the worker's identity, and it
   must not be affected by these changes.

## Problem Statement

**The process boundary is declared but not enforced.** ADR 0029 says the worker
must never receive `DATABASE_URL`. Compose hands it over anyway, and the mechanism
that does so is symmetric — it will hand the API the worker's credential just as
readily. A boundary enforced only by the current contents of one file is not a
boundary: adding a key to `.env` silently widens both processes at once.

**The lease window is judged by the wrong clock.** `process_one` captures `now`
once at entry (`worker.py:152`) and reuses it for every terminal mutation, including
three `mark_failed` calls that occur *after* a model call of unbounded duration. A
lease that expired during extraction is still reported as held, because the
comparison uses the timestamp from before the extraction started. `mark_succeeded`
has the same shape with a shorter window: `current_now` (`:430`) is captured before
the candidate-persistence loop and consumed at `:527` after it. The authority for
"is this lease still mine" must not be a value the party holding the lease chose.

**A lost lease cancels work it has no claim over.** `cancel_events` with a
`lease_owner` cancels that owner's leased rows **and every `PENDING` row of the
conversation** (`outbox.py:787-798`). The worker calls it on *any* `FencedWriteError`
(`worker.py:498`). One of the six causes of that error is "this worker lost its
lease" — a statement about one worker's tenure, not about the conversation's
validity. Turn 1 losing its lease therefore cancels turn 2's and turn 3's
extraction, which was never at fault and will never be re-created.

**Why now.** The review's verdict is design-GO / implement-NO-GO on the Agent
architecture until these are closed. Turn Understanding, the Context Planner and
Memory Read all sit downstream of a worker whose lease and cancellation semantics
are trusted. Closing these is what makes the foundation a floor rather than a
platform to rebuild on.

## Goals

1. Make credential isolation a control, not a comment: neither process's
   environment contains the other's database credential, by construction and under
   every deployment mechanism, not only Compose.
2. Make the database the sole authority for whether an outbox lease is valid, so no
   application timestamp can extend a lease.
3. Make lease ownership identify a *process*, so two replicas cannot be confused
   for one holder.
4. Give a fenced write a typed reason, so a caller can distinguish a lost lease
   from an invalid conversation without parsing a message.
5. Stop a worker that loses its lease from cancelling any event it does not hold,
   and prove that a lease loss leaves every other turn's event intact.
6. Preserve the existing recovery paths: an event whose worker died is still
   reclaimed after lease expiry, and a deleted conversation's events are still
   cancelled atomically by the transaction that deletes it.

## Non-goals

1. **Rewiring the worker counters.** This design introduces the typed reason
   vocabulary that the `lease_lost` counter needs, but does not change
   `WorkerCounters`. The counter currently matches on the literal strings
   `"lease_lost"` and `"The source outbox lease was lost."`
   (`backend/memory/write_pipeline/observability.py:65`) while the worker emits
   `lease_lost_before_commit`, `mark_succeeded_failed_lease_lost` and
   `fenced_by_source_move`; it therefore counts nothing. That is the observability
   change and is specified separately.
2. **Readiness.** `_probe_memory_pipeline` maps a non-empty backlog to `DEGRADED`
   and `backend/app/api/ops.py:46` turns `DEGRADED` into HTTP 503, so queue depth
   is being used as worker health. Separate change.
3. **The `RuntimeContainer` lifecycle.** `get_runtime_container`
   (`backend/app/runtime_container.py:248-254`) builds a production container and
   runs the least-privilege guard, which makes a unit test open a real PostgreSQL
   connection. Separate change; this design must not add a second caller on that
   path.
4. **`event_type` filtering in the claim.** `claim_batch` does not filter on
   `event_type`, and `process_one` never reads it. Separate change, required before
   any second event type exists.
5. **Documentation rebase.** `ALEMBIC_HEAD` is `20260911_06` while eight documents
   still say `20260911_02`, and `ARCHITECTURE.md:72` plus
   `docs/architecture/current-state.md:96` still show a phantom
   `record_turn_async`. Separate change.
6. **Frontend races and `complete_turn` terminal-result checking.** Separate.
7. **Enabling either Memory gate.** Unchanged from the memory-worker-runtime
   design: both stay `False`.
8. **Multi-worker scaling.** Not a goal — but the design must be *correct* for two
   workers, because the `WORKER_ID` defect only appears when there are two.

## Assumptions

1. **`now()` in PostgreSQL is an acceptable clock authority.** Falsifiable: it
   returns transaction start time and is stable for the life of a transaction, so
   every statement in one claim or one fence sees one instant. If a future
   requirement needs per-statement time, it must use `clock_timestamp()` and this
   design's "one instant per transaction" property changes.
2. **A process identity derived from host and pid is stable for that process's
   life.** Falsifiable: the pid does not change while the process runs. Across a
   restart the identity changes, which is intended — the new process must not adopt
   the old one's leases.
3. **`.env` remains the single source of configuration values.** Falsifiable:
   Compose interpolation already reads it for `APP_DB_PASSWORD` and
   `POSTGRES_PASSWORD` (`docker-compose.yml:9-14, 43`). This design changes *which
   keys reach a container*, not where values live.
4. **The delete path already cancels a conversation's events atomically.**
   Falsifiable: ADR 0023/0027 Flow 3 states it and `_cancel_turn_outbox` exists in
   `backend/conversations/postgres_repository.py`. The plan must confirm it by
   observation before the fence-path cancellation is removed.

## User and System Flows

### Flow 1 — a worker process starts

1. The process resolves `worker_dsn()`.
2. It asserts credential isolation: the environment must not contain the API's
   database key.
3. It asserts the connected role is least-privilege
   (`assert_least_privilege_role`, already present at `runtime.py:165`).
4. It resolves a process-unique lease owner identity.
5. It polls. Every claim and every terminal mutation derives its lease window from
   the database clock.

### Flow 2 — a lease expires during extraction

1. The worker claims an event; the database writes `lease_until = now() + interval`.
2. Extraction runs outside any transaction and takes longer than the lease.
3. The worker returns to persist. The fence evaluates the lease against
   `now()` in the write transaction, not against a timestamp captured at step 1.
4. The fence raises `FencedWriteError(LEASE_EXPIRED)`.
5. The worker stops. It cancels **nothing**. The event remains `LEASED` and becomes
   reclaimable when its window closes.

### Flow 3 — a lease is taken by another worker

1. The worker's lease expires and a second worker claims the event.
2. The first worker finishes extraction and attempts to persist.
3. The fence raises `FencedWriteError(LEASE_LOST)`.
4. The first worker stops and cancels nothing. The second worker's lease and every
   `PENDING` event of the conversation are untouched.

### Flow 4 — a conversation is deleted mid-extraction

1. The delete transaction tombstones the conversation, bumps the deletion epoch,
   and cancels the conversation's pending and leased events — atomically.
2. The worker's fence raises `FencedWriteError(CONVERSATION_GONE)`,
   `CONVERSATION_NOT_ACTIVE`, or `DELETION_EPOCH_MOVED`.
3. The worker stops. It cancels nothing, because the transaction that invalidated
   the conversation already did.

### Flow 5 — the operator scales to two replicas

1. Each replica resolves a distinct lease owner identity.
2. `mark_failed` and `mark_succeeded` can only act on a lease whose holder equals
   the caller's identity.
3. A replica that loses a lease can no longer clear or cancel the other's row.

## Behavioral and Data Contracts

### Process credential

**Produces** a per-service environment allow-list.

- Neither the `backend` nor the `worker` service declares `env_file`. Each declares
  an explicit `environment:` list, and values are supplied by Compose
  interpolation of `.env` (`${VAR}` / `${VAR:-default}`), the mechanism the backend
  service already uses for `APP_DB_PASSWORD`.
- The worker's list contains `WORKER_DATABASE_URL` and the model and gate settings.
  It does **not** contain `DATABASE_URL`.
- The backend's list contains `DATABASE_URL`, the model settings, and the auth
  settings. It does **not** contain `WORKER_DATABASE_URL`.
- A process that needs a key not on its list fails visibly at startup, rather than
  silently receiving it.

### Credential isolation guard

**Produces** a startup assertion that makes the boundary testable.

- `assert_credential_isolation(role)` takes the role it is running as and the
  environment mapping, and raises when the *other* role's database key is present.
- It is called from the two process entry points only: the API lifespan and the
  worker's `main`. It is **not** called from `RuntimeContainer.__init__`,
  `build_worker`, or the request dependency, so constructing these objects in a
  test does not require a curated environment.
- There is no bypass flag. A privileged-role escape hatch already exists for local
  development and is documented as weakening RLS; adding a second one for a
  boundary this design exists to enforce would reproduce that mistake.
- The error names the offending key, so the fix is unambiguous.

### Lease time authority

**Produces** a lease window the database owns end to end.

- `lease_until` is written as `now() + make_interval(secs => :lease_seconds)` by the
  statement that leases the row. No application timestamp participates.
- Lease validity is evaluated as `lease_until > now()` **inside the same statement**
  that reads the row, in `claim_batch`, `claim_event`, `mark_succeeded`,
  `mark_failed`, and `check_outbox_lease`.
- `next_attempt_after` is likewise derived from `now()`.
- `now()` is the transaction timestamp, so one claim or one fence observes exactly
  one instant. This is the property that makes a fence meaningful: the write
  transaction cannot see its own lease expire midway through.
- The `now` parameter is **removed** from `PostgresOutboxRepository.claim_batch`,
  `claim_event`, `mark_succeeded`, `mark_failed`, and from `check_outbox_lease`. A
  caller cannot supply a time authority it does not own, and the removal is what
  makes that structural rather than conventional.
- `InMemoryOutboxRepository` keeps an injectable clock, because it exists to make
  unit tests fast. It carries an explicit note that it does not model the
  authority, in the same spirit as its existing note about not modelling the
  release gate.

### Lease ownership identity

**Produces** a lease owner that identifies a process.

- `WORKER_ID` is no longer defaulted to a constant. When unset, it is derived from
  the process: `f"{socket.gethostname()}-{os.getpid()}"`. When set, the configured
  value is used, so an operator who wants stable identity across restarts can have
  it and takes responsibility for uniqueness.
- Consequence: `holder == lease_owner` distinguishes two replicas. This is what
  makes the `cancel_events(lease_owner=…)` scope meaningful.

### Fence reason vocabulary

**Produces** a typed reason on every fenced write.

- A `FenceReason` enum replaces the six free-text messages:

  | Reason | Detected by |
  | --- | --- |
  | `CONVERSATION_GONE` | `check_conversation_fence` — row absent |
  | `CONVERSATION_NOT_ACTIVE` | `check_conversation_fence` — `retention_state != active` |
  | `DELETION_EPOCH_MOVED` | `check_conversation_fence` — stored epoch differs |
  | `OUTBOX_EVENT_GONE` | `check_outbox_lease` — row absent |
  | `LEASE_LOST` | `check_outbox_lease` — not `leased`, or held by another owner |
  | `LEASE_EXPIRED` | `check_outbox_lease` — window closed |

- `check_conversation_fence` and `check_outbox_lease` return the enum, not a
  sentence. Their human-readable text becomes the exception's message, derived from
  the enum, so logging stays readable and branching stops depending on prose.
- `FencedWriteError` carries `reason: FenceReason` as a required attribute.

### Cancellation authority

**Produces** one rule, applied at both detection sites.

- The rule: **cancel a conversation's remaining events only when the cause is a
  property of the conversation, never when it is a property of this worker's
  tenure.**
- Conversation-shaped reasons — `CONVERSATION_GONE`, `CONVERSATION_NOT_ACTIVE`,
  `DELETION_EPOCH_MOVED` — may cancel the conversation's pending and leased events.
- Worker-shaped reasons — `LEASE_LOST`, `LEASE_EXPIRED` — cancel nothing.
- `OUTBOX_EVENT_GONE` cancels nothing: one event's absence says nothing about its
  siblings.
- `FenceReason` exposes this as a single predicate, so the worker branches once and
  no future reason can be added without classifying it.
- **The fence handler in `process_one` cancels nothing at all.** For the
  conversation-shaped reasons, the transaction that made the conversation invalid
  has already cancelled its events (Flow 4), so the call would match zero rows; for
  the worker-shaped reasons it would be destructive. The worker's job after a fence
  is to stop.
- The revalidation path (`worker.py:239, 256, 273`) keeps cancelling, because it is
  the site that *first observes* an invalid conversation — there is no prior
  transaction to have cancelled it. It maps its detections onto the same enum and
  uses the same predicate.

### Worker counters

**Unchanged by this design.** `WorkerCounters` and `record_batch` are not modified.
The typed vocabulary introduced above is the prerequisite for the separate
observability change; wiring it here would mix a correctness fix with a metrics fix
and make both harder to review.

## Errors and Edge Cases

1. **The worker's environment contains `DATABASE_URL`.** Expected: the process
   exits non-zero at startup, naming the key. It does not fall back, warn, or
   continue.
2. **The backend's environment contains `WORKER_DATABASE_URL`.** Expected: the API
   fails to start, naming the key.
3. **A key needed by a process is missing from its allow-list.** Expected: the
   process fails visibly on first use rather than running with a default.
4. **Extraction outlasts the lease, no other worker involved.** Expected:
   `LEASE_EXPIRED`; the worker stops; the event stays `LEASED` and is reclaimed by
   the same worker after the window closes. No cancellation.
5. **Extraction outlasts the lease and a peer claims it.** Expected: `LEASE_LOST`;
   the worker stops; the peer's lease is intact; no `PENDING` event is touched.
6. **Turn 1's lease is lost while turn 2 and turn 3 are `PENDING`.** Expected: both
   remain `PENDING` and are extracted normally. This is the defect's direct
   regression test.
7. **A conversation is deleted during extraction.** Expected: a
   conversation-shaped reason; the worker stops; the events were already cancelled
   by the delete transaction; the count of cancelled rows is unchanged by the
   worker's stop.
8. **The outbox row is deleted out from under the worker.** Expected:
   `OUTBOX_EVENT_GONE`; the worker stops; sibling events are untouched.
9. **Two replicas with an identical configured `WORKER_ID`.** Expected: the
   operator has opted into a shared identity; the behaviour is documented as
   requiring uniqueness. The derived default cannot collide within a host.
10. **A replica restarts and its identity changes.** Expected: its previous leases
    are not adopted; they expire and are reclaimed. Intended.
11. **The database clock is behind the application clock.** Expected: no effect.
    The application clock no longer participates in lease decisions.

## Security and Privacy

1. **Trust boundary.** Two processes, two roles, two credentials. `travel_app`
   cannot claim the cross-owner queue; `travel_worker` cannot serve requests. The
   boundary is enforced by an allow-list plus a startup assertion, so it survives a
   change of deployment mechanism.
2. **Authorization.** `assert_credential_isolation` is a startup control, not a
   request control. It has no runtime bypass.
3. **Data classification.** No contract here reads or carries message content,
   memory content, or prompt bodies. Lease identifiers are opaque strings;
   `conversation_id` already appears in logs.
4. **Privacy.** The derived worker identity is `hostname-pid`, which is operational
   metadata and already implied by container naming. It carries no personal data.
   It does appear in `lease_owner`, so an operator reading the outbox can infer the
   host — already true today via `worker_id`.
5. **Secrets.** No credential value is added to a log, an error message, an
   evidence file, or this document. The isolation guard names a *key*, never a
   value.

## Observability and Operations

1. A fence now logs a typed reason, so a log line can be grouped and alerted on
   without string matching.
2. The operator can distinguish "this worker keeps losing leases" (a lease or
   capacity problem) from "conversations keep being deleted" (a user action) for
   the first time.
3. Startup failure on credential isolation is loud and immediate, which is the
   correct place for a boundary violation to surface — not at the first claim.
4. The runbooks gain a short note: if the worker refuses to start citing
   `DATABASE_URL`, the deployment is injecting the API credential; fix the
   environment rather than unsetting the guard.
5. No new metric, endpoint, or alert is introduced.

## Capacity, Latency, and Cost

1. Replacing an application timestamp with `now()` removes a Python function call
   per terminal mutation. No measurable cost.
2. `make_interval` and `now()` are evaluated server-side; the claim and terminal
   statements gain no round trip.
3. The credential change removes keys from two environments. No runtime cost.
4. No change to poll interval, batch size, or model cost.

## Compatibility and Staged Migration

### Stage 1 — the environment boundary

Change `docker-compose.yml` to per-service allow-lists; add the isolation guard and
its unit tests. Independently deployable and independently reversible: the guard
and the Compose change are consistent with each other and with a single-service
rollback only if both are reverted together. Order: guard first (it is a no-op on a
correct environment), then the allow-lists.

### Stage 2 — lease authority and ownership identity

Move the lease window to `now()`; remove the `now` parameter from the Postgres
repository's claim and terminal methods; derive the worker identity. Requires no
schema change and no migration. A worker running the old code against the new
schema is unaffected, because no column changes.

### Stage 3 — the fence vocabulary and cancellation rule

Introduce `FenceReason`; make the fence handler cancel nothing; apply the predicate
at the revalidation site. Stage 3 depends on Stage 2 only in that both touch the
same call sites; it is otherwise independent.

### Compatibility

1. **No schema change, no migration, `ALEMBIC_HEAD` unchanged.** This is a
   deliberate property: the design closes contract defects without touching the
   data model, so it cannot be confused with the migration-heavy changes that
   preceded it.
2. **No public API change.** The frontend and the chat routes are untouched.
3. **`InMemoryOutboxRepository` diverges further from `PostgresOutboxRepository`.**
   Accepted: it already does not model the release gate, and its purpose is fast
   unit tests. The divergence is documented in the class, not left implicit.
4. **A configured `WORKER_ID` changes meaning** from "a label" to "a required-unique
   identity". Documented in the runbook.

## Failure and Recovery

| Failure | Behaviour | Recovery |
| --- | --- | --- |
| Worker environment leaks the API credential | Process exits non-zero at startup, naming the key | Fix the allow-list; do not unset the guard |
| API environment leaks the worker credential | API fails to start, naming the key | Fix the allow-list |
| Lease expires during extraction | Fence raises `LEASE_EXPIRED`; worker stops; no cancellation | None; the event is reclaimed after the window closes |
| Lease taken by a peer | Fence raises `LEASE_LOST`; worker stops; peer untouched | None; this is the fix |
| Two replicas share a `WORKER_ID` | Operator-introduced; identity is not unique | Set distinct `WORKER_ID`s, or unset it and take the derived default |
| Conversation deleted mid-extraction | Conversation-shaped reason; worker stops | None; the delete transaction already cancelled |
| Outbox row removed out from under the worker | `OUTBOX_EVENT_GONE`; worker stops; siblings untouched | Operator investigates the deletion |
| A staged step is reverted alone | Stages 1 and 3 are each self-consistent; Stage 1's guard and allow-list must move together | Revert both parts of Stage 1 |

## Required ADRs

1. **ADR 0032** — the outbox lease window is evaluated against database time.
   Required: it commits to a clock authority, and it removes a parameter from a
   shared repository interface.
2. **ADR 0033** — a fenced worker stops without cancelling the conversation's other
   events. Required: it decides *where* the authority to cancel lives, which is
   architecture, and it reverses a behaviour the current code deliberately
   implements.
3. **ADR 0034** — each process receives only the credential its role requires.
   Required: it decides where a credential lives and what enforces the boundary.

Three ADRs, not one, because they are three separable commitments: a clock
authority, a cancellation authority, and a credential boundary. A future change to
one must not be read as reopening the others.

## Alternatives Considered

### Alternative A: fresh `utc_now()` at each terminal mutation

**Approach.** Keep the application clock, but re-capture it immediately before each
`mark_failed` and `mark_succeeded` call instead of reusing the value captured at
`process_one` entry.

**Benefits.** A few lines. Keeps the injectable clock, so lease-expiry tests stay
fast unit tests. No SQL change and no interface change.

**Costs.** It narrows the window without removing the class. `lease_until` is still
written from one process's clock and compared against another's, so two replicas on
skewed hosts disagree about the same lease. The property "the party being judged
does not choose the clock" is not achieved.

**Rejected because.** It fixes the symptom the review measured and leaves the
mechanism that produced it. A lease is a coordination primitive between processes;
its authority cannot be a local clock.

### Alternative B: keep `env_file`, use two per-service env files

**Approach.** `.env.backend` and `.env.worker`, each containing only its own keys,
with each service pointing `env_file` at the right one.

**Benefits.** No change to how Compose injects variables. Preserves the distinction
between an absent key and an empty one, which the interpolation approach blurs.
Familiar to anyone who has read the current file.

**Costs.** The boundary is not visible in `docker-compose.yml` — a reviewer must
open two files and diff them to see what each process receives. A key placed in the
wrong file is a silent leak, which is the exact failure mode being fixed. And it
still only binds Compose: a `docker run`, a systemd unit, or a shell with both
exported is unaffected.

**Rejected because.** It moves the leak rather than making it visible, and it leaves
the boundary enforced by one deployment tool.

### Alternative C: Compose allow-list only, no code guard

**Approach.** Do the per-service `environment:` allow-lists and stop there.

**Benefits.** Smallest change. No new production code path, so nothing new to test
or to get wrong at startup.

**Costs.** The only evidence that the boundary holds is a reading of
`docker-compose.yml`. Nothing fails if the worker is started another way with
`DATABASE_URL` exported, and there is no unit test that can assert the boundary,
because the boundary is a property of a YAML file.

**Rejected because.** The owner's own framing is that this is a security boundary,
not a style issue. A boundary that cannot be asserted in a test and does not fail
closed outside one deployment tool is documentation. The guard is what converts it
into a control — and it is the *combination* that is selected, not the guard alone:
the allow-list makes the intended environment explicit, and the guard makes a
deviation from it fatal.

### Alternative D: cancel only the conversation's `PENDING` events on a fence, keeping the `lease_owner` scope

**Approach.** Keep the fence-path cancellation, but restrict it to `PENDING` rows,
so a peer's lease is never cleared.

**Benefits.** Retains the "stop the conversation's future work now instead of
waiting for each lease to expire" behaviour the current code was reaching for.

**Costs.** It still treats one worker's lease loss as a statement about the
conversation. Turn 2 and turn 3 are cancelled because turn 1's worker was slow,
which is the defect, not a mitigation of it. It also adds a second cancellation
policy alongside the revalidation path's.

**Rejected because.** The reason for a fence determines whether cancelling is
justified, and a lease loss does not justify it. Scoping the blast radius is not the
same as having the right authority.

## Current-state Evidence

| Claim | Evidence path | Verified how |
| --- | --- | --- |
| The worker receives `DATABASE_URL` | `docker-compose.yml:44-46`, `:74-76` | Read source; `cut -d= -f1 .env` lists `DATABASE_URL` among its keys |
| `.env` does not contain `WORKER_DATABASE_URL` | `.env` | `cut -d= -f1 .env` — five keys, `WORKER_DATABASE_URL` absent |
| `worker_dsn()` has no API-DSN fallback | `backend/app/config.py:145-170` | Read source: explicit `WORKER_DATABASE_URL`, else assembled from `PG_*` with the worker password |
| The worker builds its engine from `worker_dsn()` | `backend/memory/write_pipeline/runtime.py:161` | Read source |
| The worker asserts the least-privilege role | `backend/memory/write_pipeline/runtime.py:165` | Read source |
| The connection `.env` names is `travel_app`, least-privilege | `.env` via `Settings.database_dsn()` | Ran a query: `current_user='travel_app', rolsuper=False, rolbypassrls=False` |
| `now` is captured once and reused after extraction | `backend/memory/write_pipeline/worker.py:152, 363, 387, 413` | Read source |
| `mark_succeeded` consumes a pre-persistence timestamp | `backend/memory/write_pipeline/worker.py:430, 527` | Read source |
| `holds_lease` trusts the caller's timestamp | `backend/memory/write_pipeline/outbox.py:732-736` | Read source |
| `cancel_events` cancels every `PENDING` row when scoped | `backend/memory/write_pipeline/outbox.py:787-798` | Read source: `status == PENDING` is OR-ed unconditionally |
| The fence handler cancels the conversation's work | `backend/memory/write_pipeline/worker.py:498-503` | Read source |
| The revalidation path also cancels, unscoped | `backend/memory/write_pipeline/worker.py:239, 256, 273` | Read source |
| The fence returns six distinct sentences | `backend/conversations/postgres_repository.py:1116-1166` | Read source |
| The fence raises one exception type carrying a sentence | `backend/memory/write_pipeline/postgres.py:514-524` | Read source |
| The fence is called without a `now`, so it uses the app clock | `backend/memory/write_pipeline/postgres.py:359, 492-496` | Read source |
| `WORKER_ID` defaults to a constant | `backend/app/config.py:91` | Read source: `os.getenv("WORKER_ID", "memory_worker_1")` |
| The counters match on literal strings, not on the worker's reasons | `backend/memory/write_pipeline/observability.py:65` | Read source |
| Both Memory gates default `False` | `backend/app/config.py`; `docker-compose.yml:72-73` | Read source |
| The unit suite is green here but not hermetic | `backend/tests/unit/test_runtime_container.py:248` | Ran the suite: **844 passed**; then with `DATABASE_URL` pointed at a dead port: **1 failed** |

**Not verified.** No worker process has been run against a live queue with these
defects present, so the cancellation defect's impact is reasoned from source and
from the `cancel_events` predicate rather than observed in a running system. The
claim that the delete transaction already cancels a conversation's events is taken
from ADR 0023/0027 and the presence of `_cancel_turn_outbox`; the plan must confirm
it by observation *before* the fence-path cancellation is removed, because that
removal depends on it. `make_interval` is standard PostgreSQL but is not used
anywhere in this repository today. The Compose interpolation approach is in use for
`APP_DB_PASSWORD`, but not yet for a key whose absence must be distinguishable from
an empty value; the plan must verify the absent-versus-empty behaviour for
`GITHUB_TOKEN` and `LOCAL_AUTH_TOKENS_JSON` explicitly rather than assume it. Live
PostgreSQL integration was not re-run for this review.

## Components and Dependency Direction

```text
  +------------------------+          +------------------------+
  | API process            |          | worker process         |
  | role travel_app        |          | role travel_worker     |
  | env: DATABASE_URL      |          | env: WORKER_DATABASE_URL|
  |      NOT WORKER_DB_URL |          |      NOT DATABASE_URL  |
  +-----------+------------+          +-----------+------------+
              |                                   |
              |  assert_credential_isolation(role) at startup
              |                                   |
              v                                   v
  +---------------------------------------------------------------+
  | PostgreSQL                                                    |
  |   now()  -> the only clock that judges a lease window         |
  +---------------------------------------------------------------+
                          ^
                          | claim / terminal mutations carry no timestamp
              +-----------+------------+
              | OutboxRepository       |  returns FenceReason, not a sentence
              | (Postgres)             |
              +------------------------+
                          ^
                          | stop, or cancel by reason class
              +-----------+------------+
              | MemoryOutboxWorker     |
              +------------------------+
```

**Allowed dependency direction.** The worker depends on the outbox repository, the
conversation service, the model adapter and the recorder — all existing, none
gaining a new dependency. `check_conversation_fence` and `check_outbox_lease` gain a
dependency on `FenceReason`, which lives with the memory write pipeline's error
vocabulary. The API gains nothing.

**Ownership.** The migration role owns every object; no object changes owner. The
isolation guard lives in `backend/app/` next to the settings it reads. `FenceReason`
lives in `backend/memory/write_pipeline/uow.py` beside `FencedWriteError`, which it
describes.

## Data Flow and Lifecycle

1. Compose assembles each process's environment from its allow-list. `.env` holds
   values; it no longer determines which keys a container receives.
2. Each process asserts at startup that the other role's database key is absent, and
   that its connected role is least-privilege.
3. The worker resolves a process-unique lease owner identity.
4. `claim_batch` leases rows with `lease_until` computed by the database.
5. Extraction runs outside any transaction.
6. The fence evaluates conversation state and the lease window, both against the
   database clock, inside the write transaction, and raises a typed `FenceReason`
   on failure.
7. The worker stops on a fence. It cancels only when the reason is a property of the
   conversation, and only at the site that first observed it.
8. `mark_succeeded` and `mark_failed` evaluate `holds_lease` against `now()`, so a
   worker that has lost its lease cannot alter the row.

## Approval Record

| Version | Decision owner | Date | Notes |
| --- | --- | --- | --- |
| 0.1 | Repository owner | 2026-09-12 | Drafted after an independent re-verification of the third review's findings 1, 2 and 3. |
| 0.1 | Repository owner | 2026-09-12 | **Approved** on the owner's instruction to implement. Version unchanged: the approved text is the text above. All three crux choices were taken as drafted — database-time lease authority, cancel-nothing after a fence, and an allow-list plus startup guard rather than either alone. |

**This document is approved.** Approval authorized ADRs 0032, 0033 and 0034 and the
implementation plan, and the owner then instructed implementation of that plan.

Approval does **not** authorize rewiring the worker counters, changing readiness, the
`RuntimeContainer` lifecycle, `event_type` filtering in the claim, the frontend
races, the `complete_turn` terminal-result check, documentation rebases, enabling
either Memory feature gate, or Git delivery. Each of those is a separate change with
its own spec.
