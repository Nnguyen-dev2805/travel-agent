# ADR 0032: An Outbox Lease Is Judged Valid Against Database Time, and Held by a Process Identity

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-12 |
| Decision owners | Repository owner |
| Scope | What a lease's validity is a function of: the clock that judges its window, and the identity that holds it |
| Governing spec | [Worker Authority: Credential, Lease Time, and Fence Semantics](../specs/2026-09-12-worker-authority-credential-lease-fence-design.md) v0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

A lease exists so that two workers cannot process one outbox event at once. Its
validity is therefore a coordination fact between processes, and it is currently
decided by the process being judged.

`process_one` captures the time once, at entry, and reuses it for every terminal
mutation:

```python
def process_one(self, event: OutboxEvent) -> WorkerResult:
    now = utc_now()                      # worker.py:152
```

That value then crosses an unbounded interval. Extraction runs outside any
transaction (`:341`), and when it fails, the failure is recorded with the timestamp
from before it started:

```python
new_status = self._outbox_repo.mark_failed(
    event.outbox_id, ..., now=now,       # worker.py:363, :387, :413
)
```

`mark_succeeded` has the same shape over a shorter window: `current_now` is captured
at `:430`, before the candidate-persistence loop, and consumed at `:527` after it.

The repository trusts whatever it is handed (`outbox.py:732-736`):

```python
holds_lease = (
    current is OutboxStatus.LEASED
    and holder == lease_owner
    and (lease_until is None or lease_until >= now)
)
```

So a lease that expired at 10:00:30 is still reported as held at 10:00:40, because
`now` says 10:00:00. The fence has the same dependency: `_check_fence`
(`postgres.py:492-496`) accepts a `now`, and its only caller
(`postgres.py:359`) omits it, so `check_outbox_lease` falls back to
`datetime.now(timezone.utc)` (`postgres_repository.py:1143-1144`) — an application
clock again.

The second half of the same problem is the holder check. `holder == lease_owner`
compares strings, and `WORKER_ID` defaults to a constant
(`backend/app/config.py:91`):

```python
WORKER_ID: str = os.getenv("WORKER_ID", "memory_worker_1")
```

Two replicas started from the same configuration are therefore indistinguishable.
Every operation that keys on the holder — `mark_failed`, `mark_succeeded`, and
`cancel_events(lease_owner=…)` — treats them as one worker. The defect this ADR
addresses is reachable the first time the worker is scaled horizontally, which is
the ordinary deployment.

## Decision

**The database clock is the sole authority for whether an outbox lease is valid, and
a lease is held by an identity that identifies a process.**

Specifically:

1. `lease_until` is written by the statement that leases the row, as
   `now() + make_interval(secs => :lease_seconds)`. No application timestamp
   participates in writing it.
2. Lease validity is evaluated as `lease_until > now()` **inside the same statement
   that reads the row** — in `claim_batch`, `claim_event`, `mark_succeeded`,
   `mark_failed`, and `check_outbox_lease`.
3. `next_attempt_after` is derived from `now()` on the same basis.
4. `now()` is PostgreSQL's transaction timestamp, not `clock_timestamp()`. One claim
   and one fence therefore each observe exactly one instant, which is what makes a
   fence meaningful: a write transaction cannot see its own lease expire partway
   through.
5. The `now` parameter is **removed** from `PostgresOutboxRepository.claim_batch`,
   `claim_event`, `mark_succeeded`, `mark_failed`, and from `check_outbox_lease`. A
   caller can no longer supply a time authority it does not own, and the removal is
   what makes that structural rather than a convention a future caller might not
   follow.
6. `InMemoryOutboxRepository` keeps an injectable clock, because its purpose is fast
   unit tests. It carries an explicit note that it does not model the authority —
   the same treatment it already gives the release gate it also does not model.
7. The lease owner identity must distinguish processes. `WORKER_ID` is no longer
   defaulted to a constant; unset, it derives from the process as
   `f"{socket.gethostname()}-{os.getpid()}"`. A configured value is honoured, so an
   operator may choose a stable identity and takes responsibility for its
   uniqueness.

## Alternatives Considered

### Re-capture `utc_now()` immediately before each terminal mutation

**Approach.** Keep the application clock, but stop reusing the value captured at
`process_one` entry. Capture a fresh timestamp at each `mark_failed` and
`mark_succeeded` call site.

**Benefits.** A few lines. The injectable clock survives, so lease-expiry tests stay
fast unit tests. No SQL change and no interface change, which means no other caller
is affected.

**Costs.** It narrows the window without removing the class of defect.
`lease_until` is still written from one process's clock and compared against
another's, so two replicas on hosts whose clocks disagree will disagree about the
same lease. The window it closes is the long one; the short one — a persistence loop
outlasting the remaining lease — remains, and so does cross-host skew.

**Rejected because.** A lease is a coordination primitive between processes, and a
coordination primitive whose authority is a local clock is not a coordination
primitive. This alternative fixes the measurement the review took, not the mechanism
that produced it.

### Use `clock_timestamp()` instead of `now()`

**Approach.** Derive and compare the lease window with `clock_timestamp()`, which
advances within a transaction, rather than the transaction timestamp.

**Benefits.** Each statement sees the true wall-clock time, which is closer to what
"expired" means in ordinary language.

**Costs.** A long-running write transaction would see its own lease expire between
two of its own statements, so a fence could pass its check and then fail the same
check a statement later inside one atomic unit of work. It also makes the outcome
depend on how many statements ran, which is not a property anyone can reason about
from the outside.

**Rejected because.** The design needs one instant per transaction precisely so that
a fence's answer is stable for the transaction that asked. Wall-clock precision is
the wrong goal here.

### Keep the application clock and reconcile by tolerance

**Approach.** Keep application timestamps, and accept a lease as valid within some
skew tolerance.

**Benefits.** No SQL change; tolerant of clock drift between hosts.

**Costs.** A tolerance is a guess that must be tuned, and it widens the window in
which two workers both believe they hold one lease — reintroducing exactly the
concurrent-processing defect ADR 0030 fixed. It also puts a magic constant between a
lease and its meaning.

**Rejected because.** It trades a correctness property for a tuning parameter.

### Make the identity a configured, required setting

**Approach.** Remove the default entirely and refuse to start without an explicit
`WORKER_ID`.

**Benefits.** The identity is always deliberate; no replica can collide by accident.

**Costs.** Every existing deployment and the Compose service must be updated before
the worker can start at all, and an operator who forgets gets a startup failure
rather than a working worker. It also makes the identity something a human must keep
unique, when the process already knows a unique answer.

**Rejected because.** The derived default is correct without human attention, and a
configured override remains available for operators who want identity to survive a
restart.

## Consequences

**Positive.**

- A lease can no longer be extended by the party holding it. A worker that spent too
  long extracting fails its fence, which is the intended outcome.
- Two replicas on skewed hosts agree about the same lease, because neither host's
  clock is consulted.
- `mark_failed`, `mark_succeeded` and `cancel_events(lease_owner=…)` act only on the
  caller's own leases, so one replica cannot clear or cancel another's row.
- Removing the parameter makes the guarantee structural: there is no argument through
  which a caller could reintroduce a local clock.

**Negative.**

- Lease-expiry tests that used an injected clock against the Postgres repository must
  move to the database (integration) or to the in-memory repository. That is a real
  testing cost, and it is the honest one: a fake clock was never testing the
  authority the code actually uses.
- `InMemoryOutboxRepository` and `PostgresOutboxRepository` diverge further. They
  already differ on the release gate, and the divergence is now documented rather
  than incidental.
- A worker's identity changes across a restart, so its previous leases are not
  adopted. Intended, but it means a fast restart cannot resume its own in-flight
  work; it waits out the lease.
- A configured `WORKER_ID` changes meaning from a label to a required-unique
  identity. Operators who set one must ensure it is unique.

**Neutral.**

- No schema change and no migration. `lease_until` and `next_attempt_after` keep
  their types and semantics; only who computes them changes.
- The lease duration stays configuration.
- Claim ordering, batch size and the per-conversation advisory lock (ADR 0030) are
  unaffected.

## References

1. [ADR 0014: Transactional outbox and idempotent memory workers](./0014-transactional-outbox-and-idempotent-memory-workers.md)
2. [ADR 0028: The background worker claims through a role-scoped policy, and binds a tenant after the claim](./0028-worker-role-and-outbox-claim-boundary.md)
3. [ADR 0030: A conversation's outbox events are claimed under a per-conversation advisory lock](./0030-a-conversation-is-claimed-under-an-advisory-lock.md)
4. [Worker Authority: Credential, Lease Time, and Fence Semantics](../specs/2026-09-12-worker-authority-credential-lease-fence-design.md) — governing specification
5. [Memory Worker Runtime](../specs/2026-09-12-memory-worker-runtime-design.md) — the design that deferred these lease defects
