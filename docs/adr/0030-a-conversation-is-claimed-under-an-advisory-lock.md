# ADR 0030: A Conversation's Outbox Events Are Claimed Under a Per-Conversation Advisory Lock

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-12 |
| Decision owners | Repository owner |
| Scope | How two workers are prevented from claiming two events of one conversation at the same instant |
| Governing spec | [Memory Worker Runtime](../specs/2026-09-12-memory-worker-runtime-design.md) v0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

`PostgresOutboxRepository.claim_batch` (`backend/memory/write_pipeline/outbox.py:459-544`)
expresses same-conversation serialisation two ways: an `active_lease_exists`
subquery that looks for a live lease on the same conversation, and a `seen_convs`
set that dedupes conversations *within one batch*. It then takes
`FOR UPDATE SKIP LOCKED` on the rows it selected.

Neither is atomic across workers. The subquery is evaluated at SELECT time, and
`SKIP LOCKED` locks only the rows this transaction selected — so two workers
selecting *different* rows of one conversation lock different rows and never block
each other. Each sees no active lease, because the other's lease is uncommitted.

Proved with two concurrent transactions on the worker role:

```
worker A holds cout_8a6b... (uncommitted)
worker B claimed while A holds its lock: 1 -> ['cout_e773...']
final leased rows: cout_8a6b... held by worker_A
                   cout_e773... held by worker_B
```

Two extractions over one transcript can then produce contradictory candidates for
the same assertion, and the consolidation that follows resolves a conflict that
does not exist. It is latent today because no worker is mounted.

A constraint shapes the fix: at claim time the worker does **not** know the owner,
so it has no tenant bound, and `conversations` is `FORCE`-enabled. The worker
therefore cannot see a conversation row in order to lock it.

## Decision

**`claim_batch` takes a per-conversation advisory lock before selecting a
conversation's events, and skips any conversation whose lock it cannot take.**

Specifically:

1. For each candidate conversation, in a deterministic order,
   `pg_try_advisory_xact_lock(hashtextextended(conversation_id, 0))`.
2. A conversation whose lock is not acquired is skipped for this poll. Its events
   remain `pending` and are claimable next poll.
3. The lock is transaction-scoped, so it is released when the claim transaction
   ends. It guards *claiming*, not *processing*.
4. The lock is keyed by a hash of `conversation_id`. A hash collision between two
   conversations costs a skipped claim in one poll, never incorrectness.
5. No table privilege is required, so `travel_worker`'s enumerated grant set is
   unchanged.

## Alternatives Considered

### Lock the parent `conversations` row

**Approach.** `SELECT ... FOR UPDATE SKIP LOCKED` on `conversations` before claiming
its events.

**Benefits.** A real row lock rather than an advisory lock; the intent is visible in
the data model, and the lock is tied to the row it protects.

**Costs.** `conversations` is `FORCE`-enabled and the worker binds no tenant at
claim time, so the row is invisible to it. Making it visible requires a worker
policy on `conversations` — widening the worker's cross-owner visibility beyond the
queue that ADR 0028 deliberately confined it to. It would also require `UPDATE`
privilege on `conversations` for `FOR UPDATE`, or a policy that permits locking
under a SELECT grant.

**Rejected because.** It widens the cross-owner grant to solve a concurrency
problem, when a mechanism that needs no table privilege does the job.

### One event per conversation per poll

**Approach.** Keep the `seen_convs` dedupe and claim at most one event per
conversation per batch.

**Benefits.** No new mechanism; already implemented.

**Costs.** It does not address the defect. Two workers claiming simultaneously
still take two different rows, because the dedupe is per batch and per worker.

**Rejected because.** It is the current behaviour, and the current behaviour is the
defect.

### Serialise at the conversation level in application code

**Approach.** A process-local lock, or a single-worker deployment.

**Benefits.** No database mechanism.

**Costs.** Correctness becomes a function of how many workers happen to run and
where. A second worker started during an incident silently breaks the invariant,
and the failure is a data conflict rather than an error.

**Rejected because.** The invariant must not depend on the deployment's shape.

## Consequences

**Positive.**

- Two workers cannot claim two events of one conversation at the same instant,
  regardless of how many are running.
- No schema change, no grant change, no new table privilege.
- The worker's cross-owner visibility stays confined to the outbox queue.
- The mechanism is transaction-scoped, so a crashed claim cannot leave a lock held.

**Negative.**

- Advisory locks are a new mechanism in this repository and are not visible in the
  schema, so a reader of `conversation_outbox` cannot see the serialisation.
- Hash collisions between conversation ids cause a skipped claim in one poll. The
  effect is latency, not incorrectness, but it is a real (rare) behaviour.
- A lock is held for the duration of the claim transaction only. Two workers can
  still process one conversation's *successive* events concurrently once the first
  is leased — which is correct, and is a deliberate limit of what this record
  guarantees.
- `hashtextextended` is a PostgreSQL-specific function, so the claim path is tied
  to PostgreSQL. It already was.

**Neutral.**

- The outbox status vocabulary (ADR 0014) and the release gate (ADR 0027) are
  unchanged.
- Claim latency is unaffected in the uncontended case.

## References

1. [ADR 0014: Transactional outbox and idempotent memory workers](./0014-transactional-outbox-and-idempotent-memory-workers.md)
2. [ADR 0028: The background worker claims through a role-scoped policy, and binds a tenant after the claim](./0028-worker-role-and-outbox-claim-boundary.md)
3. [Memory Worker Runtime](../specs/2026-09-12-memory-worker-runtime-design.md) — governing specification
4. PostgreSQL documentation, "Advisory Locks" — transaction-scoped advisory locks
