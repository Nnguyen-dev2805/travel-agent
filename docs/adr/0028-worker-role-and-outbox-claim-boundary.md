# ADR 0028: The Background Worker Claims Through a Role-Scoped Policy, and Binds a Tenant After the Claim

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-11 |
| Decision owners | Repository owner |
| Scope | The identity of the background Memory worker, how it reads a cross-owner queue under row-level security, and how it is confined to one owner afterwards |
| Governing spec | [Worker Role and Tenant-Bound Outbox Claim](../specs/2026-09-11-worker-role-tenant-bound-outbox-claim-design.md) v0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

`conversation_outbox` carries `ENABLE ROW LEVEL SECURITY` with the policy
`owner_user_id = current_setting('app.tenant', true)`. It is not `FORCE`-enabled:
`20260910_02_tenant_rls.py:32` forces RLS only on `conversations` and `messages`.
PostgreSQL therefore applies the policy to every role except the table owner, and
the table is owned by the migration role `travel_agent`.

The runtime role `travel_app` is `NOSUPERUSER NOBYPASSRLS` and is not the owner,
so the policy binds it. `PostgresOutboxRepository.claim_batch` and `claim_event`
open `self._engine.begin()` without binding `app.tenant`, and a grep across
`backend/memory/write_pipeline/outbox.py` for `app.tenant`, `set_config`, and
`current_setting` returns nothing.

Measured on the live database: `claim_batch` returns one event as `travel_agent`
and zero as `travel_app`; `count_ready_outbox_events()` returns one and zero
respectively. Because `.env`'s `DATABASE_URL` names `travel_app`,
`Settings().database_dsn()` already hands the runtime an engine that sees no
outbox rows.

The difficulty is structural rather than accidental. A worker must discover work
before it knows whose work it is, but the tenant policy is per-owner by
construction. `backend/conversations/postgres_repository.py:68-79` already binds
a tenant through `tenant_transaction(engine, owner_user_id)`, and that is the
right pattern — but it cannot be used to *find* the row, only to read it once the
owner is known.

ADR 0014 established the transactional outbox and its idempotent worker. ADR 0027
added the turn-readiness gate. Neither decided which role claims, or what that
role may see.

## Decision

**The background worker runs as a dedicated role `travel_worker`, created
`NOSUPERUSER NOBYPASSRLS`, owning nothing. It claims through two permissive
policies scoped to that role on `conversation_outbox` alone, and it binds a
tenant for every read and write that follows a claim.**

Specifically:

1. `travel_worker` receives enumerated grants only: `SELECT, UPDATE` on
   `conversation_outbox`, and `SELECT` on `conversations` and `messages`. It
   receives nothing on `alembic_version`. No `ON ALL TABLES`, and no
   `ALTER DEFAULT PRIVILEGES` entry, so a future table is not silently exposed.

2. Two policies are added to `conversation_outbox`, both `TO travel_worker`:
   `worker_outbox_claim` for `SELECT` and `worker_outbox_lease` for `UPDATE`,
   each `USING (true)`. They are permissive and therefore OR-ed with the existing
   `tenant_isolation` policy. For `travel_worker` the union admits every row; for
   every other role the union is exactly `tenant_isolation`, unchanged.

3. No policy is added to `conversations`, `messages`, or any Memory table. Those
   remain reachable only under a bound tenant. `conversations` and `messages` are
   `FORCE`-enabled, so a worker that reads them without binding sees zero rows.

4. After a claim, the worker binds the claimed row's `owner_user_id` through the
   existing `tenant_transaction`. The binding is derived from the claimed row,
   never from a caller-supplied value. `require_tenant_context` fails closed, so
   an unbound path raises rather than reading broadly.

5. The runtime role's ability to observe the queue is a single parameterless
   `SECURITY DEFINER` function, `ready_outbox_event_count()`, returning `bigint`
   and granted `EXECUTE` to `travel_app`. It counts events that are `pending` and
   `released_at IS NOT NULL`, because an unreleased event is not claimable. It
   cannot return a row, a payload, or an owner.

6. The rule for future grants is recorded here: the milestone that mounts the
   worker derives its Memory-table grant set from the unit of work's actual
   statements and enumerates them. Blanket DML is not used.

## Alternatives Considered

### A `SECURITY DEFINER` claim function

**Approach.** Move the claim into a function owned by the migration role and
grant `travel_worker` only `EXECUTE`, so the worker holds no privilege on the
table itself.

**Benefits.** The narrowest interface; RLS stays fully enforced on the table for
every role.

**Costs.** The claim predicate — the ADR 0027 gate, the lease branches, the
debounce cutoff, the skip-locked ordering, and the per-conversation dedupe —
moves into a SQL function body. That logic is currently Python with focused
tests, and it would be reimplemented and re-tested at the SQL boundary.

**Rejected because.** The marginal security gain is small — a worker bug can
rewrite lease columns either way — while the correctness cost lands on the most
subtle code in the pipeline. Content isolation is achieved by the forced policies
on the content tables regardless.

### `travel_worker` with `BYPASSRLS`

**Approach.** Grant the worker role `BYPASSRLS` and leave the claim code
untouched.

**Benefits.** Trivial to implement.

**Costs.** A global, unconstrained privilege. A compromised worker reads every
tenant's messages and Memory, and `FORCE` RLS becomes decorative for that role —
the exact defect `20260910_04` removed.

**Rejected because.** It trades a bounded, auditable grant for an unbounded one.

### Owner-scoped iteration

**Approach.** Enumerate owners with claimable work, then claim per owner under a
bound tenant.

**Benefits.** Every claim is tenant-bound; no new role privilege on the queue.

**Costs.** The owner enumeration is itself a cross-owner read, so the privileged
seam remains. It adds a round-trip per owner and a fairness question.

**Rejected because.** It relocates the cross-owner read rather than bounding it.

## Consequences

**Positive.**

- The worker has an identity that can legitimately see a cross-owner queue, and
  no identity that can see cross-owner content.
- The cross-owner exposure is confined to one table whose payload carries no
  message content.
- All existing claim logic and its tests stay in Python, unchanged.
- `travel_app`'s effective access to the outbox is unchanged; it gains only
  `EXECUTE` on a scalar function.
- The readiness probe stops reporting a confident zero it cannot justify.

**Negative.**

- `travel_worker` holds direct `SELECT, UPDATE` on `conversation_outbox`, so a
  worker bug could rewrite lease or status columns. The queue is control-plane
  data, but a corrupted lease can delay or duplicate work.
- Two policies now exist on one table, so the effective policy set is a union
  that a reader must reason about rather than a single predicate.
- The counting function is a second `SECURITY DEFINER` object to review and keep
  minimal.
- A second role adds an operational credential and a DSN to provision.

**Neutral.**

- No table is altered and no backfill is required, so the migration is additive
  and the downgrade is clean.
- The outbox status vocabulary and the ADR 0027 gate are unchanged.
- The worker remains unmounted; this decision makes the claim path correct
  without composing the runtime.

## References

1. [ADR 0014: Transactional outbox and idempotent memory workers](./0014-transactional-outbox-and-idempotent-memory-workers.md)
2. [ADR 0027: An outbox event is released only when its turn is terminal](./0027-outbox-event-released-only-when-turn-terminal.md)
3. [Worker Role and Tenant-Bound Outbox Claim](../specs/2026-09-11-worker-role-tenant-bound-outbox-claim-design.md)
4. [Authenticated Chat-Only PostgreSQL Clean Break](../specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md)
5. [Outbox Turn-Readiness Barrier](../specs/2026-09-11-outbox-turn-readiness-barrier-design.md)
6. `outputs/review-verification-2026-09-11.md` — the empirical verification of the claim failure
7. PostgreSQL documentation, "Row Security Policies" — the owner-exemption rule for `ENABLE` versus `FORCE` ROW LEVEL SECURITY
8. Extended by: [ADR 0029](./0029-the-memory-worker-runs-as-its-own-service.md) — the background Memory worker runs as its own service under its own role. This record created the role and the claim interface; that record composes the process that uses them.
9. Extended by: [ADR 0030](./0030-a-conversation-is-claimed-under-an-advisory-lock.md) — a conversation's outbox events are claimed under a per-conversation advisory lock. This record bounded *which rows* the worker may see; that record serialises claims within a conversation, without widening the grant.
