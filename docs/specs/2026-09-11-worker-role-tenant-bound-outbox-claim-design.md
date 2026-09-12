# Worker Role and Tenant-Bound Outbox Claim

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-11 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | The background worker's identity, its claim interface over `conversation_outbox`, the tenant binding that follows a claim, and the readiness count that observes the queue |
| Related issue | External review blocker B1, verified 2026-09-11 in `outputs/review-verification-2026-09-11.md` |
| Superseded document | None. This design amends the claim contract introduced by ADR 0014 and gated by ADR 0027; it does not supersede either |

## Summary

The background Memory worker cannot claim a single outbox event when it runs
under the role the architecture designates for it. The claim path is not
tenant-scoped, while the table it reads is protected by a tenant policy.

`conversation_outbox` is owned by `travel_agent` and carries
`ENABLE ROW LEVEL SECURITY` with policy
`owner_user_id = current_setting('app.tenant', true)`. It is **not**
`FORCE`-enabled: `20260910_02_tenant_rls.py:32` forces RLS only on
`("conversations", "messages")`. PostgreSQL therefore applies the policy to
every role **except the owner**. The designated runtime role `travel_app` is not
the owner, so the policy binds it. `PostgresOutboxRepository.claim_batch` and
`claim_event` open `self._engine.begin()` without binding `app.tenant` —
a grep for `app.tenant`, `set_config`, and `current_setting` across
`backend/memory/write_pipeline/outbox.py` returns zero matches.

Measured on the live database:

| Probe | Result |
| --- | --- |
| `claim_batch` as `travel_agent` (superuser) | claimed **1** |
| `claim_batch` as `travel_app` (least privilege) | claimed **0** |
| Rows in `conversation_outbox` visible to `travel_app` | **0** (`app.tenant` is `NULL`) |
| `count_ready_outbox_events()` as `travel_app` | **0** — a false zero |
| `count_ready_outbox_events()` as `travel_agent` | **1** |

The condition is live, not latent. `.env`'s `DATABASE_URL` names `travel_app`,
so `Settings().database_dsn()` already hands the runtime an engine that sees no
outbox rows at all. Both Memory feature gates default `False`, so no event is
written yet; the moment they are enabled and a worker is mounted, the pipeline
silently does nothing while reporting healthy.

This design gives the worker its own least-privilege role, a narrowly scoped
policy that lets it see the queue, and a mandatory tenant binding for everything
it reads afterwards.

## Context

The architecture already separates the two roles. `20260910_04_runtime_role_grants.py`
introduces `travel_app` as `NOSUPERUSER NOBYPASSRLS`, owning nothing, and its
docstring states the intent plainly:

> `travel_app`: the only role the backend runtime may use.

That separation is correct and this design keeps it. The gap is that the worker
was never given a role of its own, so it has no identity that can legitimately
see a cross-owner queue.

The tenant-binding primitive already exists and is already used correctly on the
other path. `backend/conversations/postgres_repository.py:68-79` defines:

```python
@contextmanager
def tenant_transaction(engine, owner_user_id):
    with transaction(engine) as connection:
        set_tenant(connection, owner_user_id)
        require_tenant_context(connection)
        yield connection
```

Every conversation read and write goes through it. `set_tenant`
(`backend/storage/postgres.py:71`) uses `set_config(..., true)`, so the binding
is transaction-local and resets automatically. The outbox repository has no
equivalent, and cannot have one in the same shape: **the worker does not know
the owner until after it has read the row.**

That is the whole difficulty. The queue is cross-owner by nature; the tenant
policy is per-owner by design. Something has to give, and the question is how
narrowly it gives.

The readiness probe has the same shape of problem from the other side.
`PostgresReadinessProbe.count_ready_outbox_events()`
(`backend/app/runtime_container.py:56-73`) reads the outbox with the runtime
engine. Its docstring promises it "Raises when the outbox cannot be read, so the
readiness probe can report `not_ready` instead of a constant" — but under
`travel_app` the query succeeds and returns `0`. The probe reports a confident,
wrong answer rather than failing.

## Users

1. **The background Memory worker process.** It needs to claim ready events
   across all owners, then process each one strictly inside that owner's scope.
2. **The synchronous Chat runtime.** It writes outbox events and must not gain
   any ability to read another owner's queue.
3. **The operator.** They need the readiness probe to report the queue honestly,
   and need the worker's privileges to be auditable and narrow.
4. **The repository owner.** They approve the role boundary and the policy that
   implements it.

## Problem Statement

**The claim interface has no identity that can see the queue.** A worker needs
to find work before it knows whose work it is. Every existing role either cannot
see the queue (`travel_app`, correctly) or sees everything without limit
(`travel_agent`, a superuser with `BYPASSRLS`). There is no role in between.

**A blocked or empty claim is indistinguishable from a healthy quiet system.**
`claim_batch` returns `()` in both cases, and `count_ready_outbox_events()`
returns `0`. Nothing raises, nothing logs an error, and the readiness probe
reports `ready`. The failure mode is silent.

**The readiness probe reports a false zero.** It cannot distinguish "the queue
is empty" from "this role cannot see the queue", so it always reports the
former.

**Why now.** The outbox readiness gate (ADR 0027) is implemented and verified,
so the claim path is the last contract standing between the current state and a
mountable worker. Every Memory milestone behind it — background formation,
consolidation, activation — depends on a worker that can actually pick up work.
Building anything on top of a claim path that returns zero would produce a
system that passes its tests and does nothing in production.

## Goals

1. Give the worker a dedicated database role that is `NOSUPERUSER` and
   `NOBYPASSRLS`, so `FORCE` RLS is never decorative for it.
2. Let that role claim ready events across owners through a **bounded** policy on
   `conversation_outbox` only, with no visibility into message or Memory content
   until a tenant is bound.
3. Require a tenant binding for every read and write that follows a claim, so the
   worker processes each event inside exactly one owner's scope.
4. Make `count_ready_outbox_events()` report the true ready count when called by
   the runtime role, or fail closed — never a confident zero.
5. Keep the existing tenant policy intact for every other role, including
   `travel_app` and `public`.
6. Make the claim path demonstrable in the integration suite with the real roles,
   replacing the test that currently asserts the defect.
7. Keep grants enumerated per table. No `ON ALL TABLES`, no blanket
   `ALTER DEFAULT PRIVILEGES` for the new role.

## Non-goals

1. **Enabling either Memory feature gate.** `MEMORY_WRITE_PIPELINE_ENABLED` and
   `MEMORY_SHADOW_EXTRACT_ENABLED` stay `False`.
2. **Mounting a worker.** No worker service in `docker-compose.yml`, no worker
   instantiated in `RuntimeContainer`. This design makes the claim path correct;
   composing the runtime is a later milestone.
3. **Granting the worker DML on the Memory tables.** The worker is not mounted,
   so those grants would be unused privileges. They are deferred to the
   milestone that mounts it, and this design records the rule that milestone must
   follow.
4. **`BYPASSRLS` for any role.** Explicitly rejected; see Alternatives.
5. **Changing the outbox status vocabulary.** ADR 0014's lifecycle and ADR 0027's
   `released_at` gate are unchanged.
6. **Narrowing `travel_app`'s existing grants** (external review issue 4). The
   same migration area, but a distinct decision about the runtime role's blast
   radius. Recorded as a follow-up, not folded in here.
7. **Request-fingerprint binding for idempotency** (external review issue 9).
   Related to Memory correctness, unrelated to the claim boundary.
8. **Multi-worker coordination beyond `FOR UPDATE SKIP LOCKED`.** No leader
   election, no advisory locks, no distributed scheduling.

## Assumptions

1. **The migration role owns the schema and stays out of runtime DSNs.**
   Falsifiable: `20260910_04_runtime_role_grants.py` creates `travel_app` as
   `NOLOGIN` and the bootstrap script grants `LOGIN` separately; if a runtime DSN
   ever named the migration role, the role separation this design relies on would
   already be broken.
2. **The worker is a single trusted process, not a multi-tenant surface.**
   Falsifiable: if the worker ever executes owner-supplied SQL or hosts
   per-tenant plugins, a table-level policy is no longer a sufficient boundary.
3. **`conversation_outbox.payload` carries no message content.** Falsifiable:
   `PostgresConversationRepository` writes `{"deletion_epoch": N,
   "conversation_id": "..."}`; if a future event type added transcript text to
   the payload, cross-owner queue visibility would become a content exposure.
4. **`travel_app` remains the only runtime role for the API process.**
   Falsifiable: the readiness count design assumes the API role cannot read the
   outbox rows and must go through a bounded function.

## User and System Flows

### Flow 1 — Worker claims and processes one event

1. The worker opens a transaction on the **worker engine** (role
   `travel_worker`).
2. It calls `claim_batch`. The `worker_outbox_claim` policy admits
   `conversation_outbox` rows regardless of owner; the ADR 0027 gate
   (`released_at IS NOT NULL`) and the lease conditions still apply.
3. The claim selects with `FOR UPDATE SKIP LOCKED` and updates the winning rows
   to `leased`. The returned event carries `owner_user_id`.
4. For each claimed event the worker opens a **separate tenant-bound
   transaction** using the existing `tenant_transaction(engine, owner_user_id)`
   and reads the transcript through `ConversationService.get_messages_in_range`.
   RLS on `conversations` and `messages` (both `FORCE`) now admits exactly that
   owner's rows.
5. The worker completes or fails the event, updating `conversation_outbox`
   through the worker engine.

### Flow 2 — Chat runtime writes an event

Unchanged. `PostgresConversationRepository` writes the user message, the pending
assistant row, and the blocked outbox event in one tenant-bound transaction as
`travel_app`. `complete_turn` releases the gate. The worker's policy does not
change this path.

### Flow 3 — Readiness reports queue depth

1. The API process calls `count_ready_outbox_events()` with the runtime engine.
2. The probe invokes the bounded `ready_outbox_event_count()` function, which is
   `SECURITY DEFINER` and returns only a `bigint`.
3. The probe compares the count to its threshold and reports `ready` or
   `not_ready`. If the function is missing or errors, the probe reports
   `not_ready` — never a zero it cannot justify.

### Flow 4 — The runtime role tries to claim

1. Any code path that calls `claim_batch` with the `travel_app` engine.
2. `travel_app` has no policy admitting it to `conversation_outbox`, so the claim
   returns `()`.
3. This remains correct behaviour: the API role must not drain the queue.

## Behavioral and Data Contracts

### Worker role

**Produces** a database role `travel_worker`.

- `LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE`,
  `NOREPLICATION`. The migration creates it `NOLOGIN`; the bootstrap script
  grants `LOGIN` with a real credential, matching the existing `travel_app`
  pattern.
- The role owns no object.
- Its privileges are enumerated in the migration, table by table. It receives
  `SELECT, UPDATE` on `conversation_outbox` and `SELECT` on `conversations` and
  `messages`. It receives no privilege on `alembic_version`.
- It receives no `ALTER DEFAULT PRIVILEGES` entry, so a future table is not
  silently exposed to it.

### Claim policy

**Produces** two permissive policies on `conversation_outbox`, both scoped to
`travel_worker`.

- `worker_outbox_claim` — `FOR SELECT TO travel_worker USING (true)`.
- `worker_outbox_lease` — `FOR UPDATE TO travel_worker USING (true) WITH CHECK (true)`.

- Both are permissive and are therefore OR-ed with the existing
  `tenant_isolation` policy. For `travel_worker` the union admits every row; for
  every other role the union is exactly `tenant_isolation`, unchanged.
- No policy is added to `conversations`, `messages`, or any Memory table. The
  worker reaches those only through a bound tenant.

### Tenant binding after a claim

**Produces** a mandatory binding for every operation that follows a claim.

- The worker reads the transcript through the existing
  `tenant_transaction(engine, owner_user_id)`. No new binding mechanism is
  introduced.
- `require_tenant_context` already fails closed when no tenant is bound, so a
  worker path that forgets to bind raises `TenantContextError` rather than
  reading across owners.
- A worker that reads `conversations` or `messages` without binding sees zero
  rows, because both tables are `FORCE`-enabled and the worker is not their
  owner.

### Readiness count

**Produces** a bounded counting interface for the runtime role.

- `ready_outbox_event_count()` — `SECURITY DEFINER`, owned by the migration role,
  `LANGUAGE sql`, **no parameters**, returns `bigint`, and executes
  `SELECT count(*) FROM conversation_outbox WHERE status = 'pending' AND released_at IS NOT NULL`.
- `EXECUTE` is granted to `travel_app`. `EXECUTE` is revoked from `PUBLIC`.
- It returns a number only. It cannot return a row, a payload, or an owner, so it
  grants no read access to queue content.
- It counts **ready** events, not merely `pending` ones. Under ADR 0027 a
  `pending` event with `released_at IS NULL` is not claimable, so counting it
  would overstate the queue. This is a deliberate semantic correction of the
  existing method, which counts `status = 'pending'` alone.

### Configuration

**Produces** a worker DSN contract, used by the integration suite now and by the
worker milestone later.

- `PG_WORKER_USER` (default `travel_worker`) and `PG_WORKER_PASSWORD`.
- `Settings.worker_dsn()`, resolved the same way `database_dsn()` is: an explicit
  `WORKER_DATABASE_URL` wins, otherwise the DSN is assembled from `PG_*` parts.
- The existing fail-closed guard applies: `worker_dsn()` must refuse a role that
  is superuser or `BYPASSRLS` unless `ALLOW_PRIVILEGED_DB_ROLE` is explicitly
  set, exactly as the runtime DSN does.

## Errors and Edge Cases

1. **The worker engine connects as a role without the claim policy.** Expected:
   `claim_batch` returns `()`. The worker must treat a sustained empty claim as
   worth observing, not as proof of an empty queue.
2. **`ready_outbox_event_count()` is absent** (migration not applied). Expected:
   the probe raises and reports `not_ready`, not `0`.
3. **The worker reads the transcript without binding a tenant.** Expected:
   `require_tenant_context` raises `TenantContextError`.
4. **The worker binds a tenant different from the claimed event's owner.**
   Expected: the read returns zero rows, because RLS admits only the bound
   owner's rows. The worker must bind the owner it claimed, never a caller-supplied
   value.
5. **An event is claimed and the lease expires before completion.** Expected:
   unchanged from ADR 0014 — the row becomes reclaimable once
   `lease_until < now` and the ADR 0027 gate is satisfied.
6. **A blocked event (`released_at IS NULL`) exists in the queue.** Expected: the
   worker cannot claim it, and `ready_outbox_event_count()` does not count it.
7. **`travel_app` attempts a claim.** Expected: `()`. This is correct and is
   asserted, not merely tolerated.
8. **The migration is applied before the code that reads the worker DSN.**
   Expected: `worker_dsn()` still resolves; nothing reads it until the worker is
   mounted, so the ordering is safe in either direction.
9. **The migration is downgraded while a worker holds a lease.** Expected: the
   policy and grants disappear; the lease columns are untouched, so a re-upgrade
   restores claimability without data repair.
10. **A future table is added.** Expected: `travel_worker` receives nothing,
    because no default privilege was granted. The grant must be added
    deliberately.

## Security and Privacy

### Trust boundaries

1. `travel_worker` is `NOSUPERUSER NOBYPASSRLS`. It cannot bypass a policy,
   forced or not.
2. The cross-owner grant is confined to `conversation_outbox`, whose payload
   carries `conversation_id` and `deletion_epoch` and no message content.
3. Message and Memory content stay behind `FORCE` RLS and a bound tenant. The
   worker has no policy admitting it to those tables.
4. The counting function is parameterless and returns a scalar. It is the
   smallest interface that lets the API role observe the queue.

### Authorization

1. The worker's tenant binding is derived from the claimed row's
   `owner_user_id`, never from a request payload.
2. `require_tenant_context` fails closed, so an unbound path raises rather than
   reading broadly.
3. `travel_app` gains no new privilege on `conversation_outbox`; its only new
   capability is `EXECUTE` on the counting function.

### Data classification

1. Outbox metadata: internal, not personal content.
2. Message and Memory content: personal, tenant-scoped, unchanged.
3. No new store, no new copy, no new export.

### Privacy

1. No policy change widens what any role can read about a user's content.
2. The counting function discloses a queue depth, not a per-owner breakdown, so it
   cannot be used to enumerate owners.

## Observability and Operations

1. The worker must emit the claimed count, the processed count, the retry count,
   and a **sustained-empty-claim** signal, so the silent-zero failure cannot
   recur unnoticed.
2. `count_ready_outbox_events()` remains the readiness input. Its semantic change
   (ready, not merely pending) must be reflected in the probe's threshold
   documentation.
3. The migration must be observable in the usual way: one revision, listed in the
   readiness revision check, with `ALEMBIC_HEAD` advanced.
4. Role creation is idempotent, so re-running the revision is safe.

## Capacity, Latency, and Cost

1. The policy adds no measurable cost. `worker_outbox_claim` is
   `USING (true)`, so the planner uses the existing
   `idx_conversation_outbox_ready` index path from ADR 0027 rather than a
   policy-driven scan.
2. The counting function is a single indexed `count(*)`. It runs behind the
   probe's existing `statement_timeout`.
3. One extra transaction per claimed event is introduced by the mandatory tenant
   binding. At the initial target of 1,000 registered users this is not a
   throughput concern; it is the correctness price of the boundary.
4. No new connection pool is required by this design, because no worker is
   mounted. The worker milestone must size its pool separately from the API pool.

## Compatibility and Staged Migration

### Stage 1 — this design

Create `travel_worker`, the two claim policies, the counting function, and the
worker DSN contract. Do not mount a worker. Prove the claim path with the real
roles in the integration suite.

### Stage 2 — the worker milestone (not this design)

Mount the worker runtime, grant the enumerated Memory-table DML, enable shadow
capture, and observe. That milestone must follow the rule this design records:
enumerated grants per table, no `ON ALL TABLES`, no default privileges.

### Compatibility

1. The new policies are additive and permissive. Every existing role's effective
   policy set is unchanged.
2. `travel_app`'s privileges are unchanged except for the added `EXECUTE`.
3. No table is altered, so no backfill is required.
4. `ALEMBIC_HEAD` advances to the new revision.

## Failure and Recovery

| Failure | Behaviour | Recovery |
| --- | --- | --- |
| Worker role missing | Claim raises on connect | Re-run the revision; role creation is idempotent |
| Claim policy missing | `claim_batch` returns `()`, silently | Readiness stays green; the worker's sustained-empty-claim signal is the detector |
| Counting function missing | Probe raises, reports `not_ready` | Re-run the revision |
| Worker binds no tenant | `TenantContextError` | Fail the event; do not retry without fixing the binding |
| Worker binds the wrong tenant | Zero rows read | Fail the event; bind the claimed owner |
| Lease lost mid-processing | ADR 0014 behaviour: the write must not commit | Reclaim after lease expiry |
| Downgrade while leases are held | Policy and grants removed | Re-upgrade; lease state is untouched |
| Runtime role tries to claim | `()` — correct | None; this is the designed boundary |

## Required ADRs

1. **ADR 0028 — the worker role and the outbox claim boundary.** Required. It
   decides where the cross-owner read lives, which is architecture: a
   role-scoped policy on one table, with content behind `FORCE` RLS and a bound
   tenant. It also records the rule for future Memory-table grants.

   No second ADR is required. The counting function is a bounded implementation
   detail of the same boundary, and the worker DSN contract reuses an existing
   resolution pattern rather than deciding a new one.

## Alternatives Considered

### Alternative A: `SECURITY DEFINER` claim function

**Approach.** Move the claim into a PostgreSQL function owned by the migration
role, marked `SECURITY DEFINER`, granted `EXECUTE` to `travel_worker`. The worker
holds no privilege on `conversation_outbox` at all.

**Benefits.** The narrowest possible interface: a compromised worker can call the
claim function and nothing else. RLS stays fully enforced on the table for every
role.

**Costs.** The claim predicate — the ADR 0027 gate, the lease branches, the
debounce cutoff, the skip-locked ordering, and the per-conversation dedupe — moves
into a SQL function body. That logic is currently Python with focused tests; it
would need to be reimplemented and re-tested at the SQL boundary, duplicating the
most subtle code in the pipeline.

**Rejected because.** The security gain over the selected approach is narrow — a
worker SQL-injection can rewrite outbox lease columns either way — while the
correctness cost is concentrated in exactly the code that took the most care to
get right. The bounded policy achieves the same content isolation because
`conversations`, `messages`, and the Memory tables remain `FORCE`-scoped and
tenant-bound.

### Alternative B: `travel_worker` with `BYPASSRLS`

**Approach.** Create the worker role with `BYPASSRLS`.

**Benefits.** Trivial. No policy, no function, no grant enumeration; the existing
claim code works unchanged.

**Costs.** A global, unconstrained privilege. A compromised or buggy worker reads
every tenant's messages and Memory. It also makes `FORCE` RLS decorative for that
role, which is the exact defect `20260910_04` was written to remove.

**Rejected because.** The external review explicitly warns against it, and it
trades a bounded, auditable grant for an unbounded one.

### Alternative C: Role-scoped policy on the outbox (selected)

**Approach.** Add two permissive policies scoped to `travel_worker`, grant it
`SELECT, UPDATE` on `conversation_outbox` and `SELECT` on `conversations` and
`messages`, and keep the existing claim code. Bind the tenant after the claim
through the existing `tenant_transaction`.

**Benefits.** The smallest change that closes the gap. All claim logic stays in
Python with its existing tests. Content isolation is unchanged because every
content-bearing table stays behind `FORCE` RLS and a bound tenant. The grant is
enumerated, auditable, and confined to the queue. `travel_app` and `public` see
exactly what they saw before.

**Costs.** The worker holds direct table access on the queue, so a worker bug
could rewrite lease columns. The queue is a control-plane table, not content, so
the exposure is bounded.

**Selected because.** It isolates the cross-owner read to the one table that is
cross-owner by nature, leaves the tested claim code untouched, and keeps content
behind the existing forced policies.

### Alternative D: Owner-scoped iteration

**Approach.** Enumerate owners with claimable work, then claim per owner with a
bound tenant.

**Benefits.** No new role privilege; every claim is tenant-bound.

**Costs.** It does not remove the need for a privileged seam — someone must
enumerate owners, and that enumeration is itself a cross-owner read. It adds a
round-trip per owner and a fairness question about how owners are ordered.

**Rejected because.** It relocates the cross-owner read rather than bounding it,
and adds scheduling complexity for no isolation gain.

## Current-state Evidence

| Claim | Evidence path | Verified how |
| --- | --- | --- |
| `conversation_outbox` is `ENABLE` but not `FORCE` | `backend/storage/migrations/versions/20260910_02_tenant_rls.py:32`; live `pg_class` | Read source; queried `relrowsecurity`/`relforcerowsecurity` |
| The claim path binds no tenant | `backend/memory/write_pipeline/outbox.py:459-544`, `:400-457` | Read source; grep for `app.tenant`/`set_config`/`current_setting` = 0 hits |
| `travel_app` cannot claim; `travel_agent` can | live database | Ran `claim_batch` under both roles: 1 vs 0 |
| `count_ready_outbox_events()` returns a false zero | `backend/app/runtime_container.py:56-73` | Read source; called it under both roles: 0 vs 1 |
| The runtime engine uses `travel_app` | `.env` `DATABASE_URL`; `backend/app/config.py:99-121` | Resolved `Settings().database_dsn()`; `current_user` = `travel_app` |
| The tenant-binding primitive exists and is used on the conversation path | `backend/conversations/postgres_repository.py:68-79`; `backend/storage/postgres.py:71-90` | Read source; grepped every `tenant_transaction` call site |
| `conversations` and `messages` are `FORCE`-enabled | live `pg_class` | Queried `relforcerowsecurity` = true |
| The Memory tables are `ENABLE`-only with a `tenant_isolation` policy | `backend/storage/migrations/versions/20260907_02_memory_write_pipeline.py:41-46`; live `pg_class`/`pg_policies` | Read source; queried the catalog |
| `travel_app` holds blanket DML including on `alembic_version` | `backend/storage/migrations/versions/20260910_04_runtime_role_grants.py:60-71` | Read source; queried `information_schema.role_table_grants` |
| The suite currently asserts the defect | `backend/tests/integration/test_outbox_turn_readiness.py:391-436` | Read source; test name `test_the_claim_path_is_not_tenant_scoped_today` |

**Not verified.** No worker process exists, so the composed worker-plus-tenant
flow has never executed end to end; this design proves the claim and the
transcript read separately, with real roles, and does not claim more. The
behaviour of a mounted worker under concurrent claims across multiple processes
is not measured. The Memory-table grant set that the future worker milestone
needs is not enumerated here, because the worker's write path is not mounted and
the grants would be speculative; the milestone must derive that set from the UoW's
actual statements. The readiness probe's threshold value is unchanged and is not
re-derived by this design.

## Components and Dependency Direction

```text
                      +--------------------------+
  API process ------> | PostgresReadinessProbe   |
  (travel_app)        |  count_ready_outbox_...  |
                      +------------+-------------+
                                   | EXECUTE (no parameters, scalar)
                                   v
                      +--------------------------+
                      | ready_outbox_event_count |  SECURITY DEFINER
                      |  owned by migration role |
                      +--------------------------+

  worker process ---> +--------------------------+
  (travel_worker)     | PostgresOutboxRepository |
                      |  claim_batch / claim_event|
                      +------------+-------------+
                                   | SELECT/UPDATE on conversation_outbox
                                   |   via worker_outbox_claim / _lease
                                   v
                      +--------------------------+
                      | conversation_outbox      |  ENABLE RLS
                      |  tenant_isolation        |  (public, unchanged)
                      |  worker_outbox_claim     |  (travel_worker)
                      |  worker_outbox_lease     |  (travel_worker)
                      +--------------------------+

  worker process ---> +--------------------------+
  after the claim     | tenant_transaction()     |
                      |  set_tenant(owner)       |
                      +------------+-------------+
                                   v
                      +--------------------------+
                      | conversations / messages |  FORCE RLS
                      | memory_*                 |  ENABLE RLS
                      +--------------------------+
```

**Allowed dependency direction.** The worker depends on the outbox repository and
the conversation service, exactly as the existing code does. Neither gains a new
dependency. The readiness probe depends on a scalar function rather than a table.

**Ownership.** The migration role owns every object. `travel_worker` and
`travel_app` own nothing. `travel_worker`'s privileges are enumerated in the
migration; `travel_app`'s are unchanged apart from the added `EXECUTE`.

## Data Flow and Lifecycle

1. Chat commits a user message, a pending assistant row, and a **blocked** outbox
   event in one tenant-bound transaction (ADR 0027).
2. `complete_turn` releases the gate atomically; the event becomes ready.
3. The worker claims ready events with `FOR UPDATE SKIP LOCKED` through the
   worker role. The claim is cross-owner by policy.
4. Each claimed event carries `owner_user_id`. The worker opens a tenant-bound
   transaction and reads that owner's transcript.
5. The worker processes the event and completes it, or fails it and lets the
   lease expire.
6. The readiness probe reports the ready count through the bounded function.

## Approval Record

| Version | Decision owner | Date | Notes |
| --- | --- | --- | --- |
| 0.1 | Repository owner | 2026-09-11 | Drafted after verifying external review blocker B1 on the live database. The owner selected the role-scoped policy over a `SECURITY DEFINER` claim function and over `BYPASSRLS`, and scoped the design to the claim path alone. |
| 0.1 | Repository owner | 2026-09-11 | **Approved** on the owner's instruction to implement. Version unchanged: the approved text is the text above. |

**This document is approved.** Approval authorized preparation of ADR 0028 and the
implementation plan, and the owner then instructed implementation of that plan.

Approval does **not** authorize enabling either Memory feature gate, mounting a
worker, granting the worker DML on the Memory tables, narrowing `travel_app`'s
existing grants, adding idempotency request fingerprints, dependency changes, or
Git delivery.
