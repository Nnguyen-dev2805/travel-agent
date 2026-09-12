# Memory Worker Runtime

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-12 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Composing, deploying and operating the background Memory worker, plus the two concurrency contracts its correctness depends on |
| Related issue | External review findings 5, 8 and 9 (2026-09-12), verified in the second review |
| Superseded document | None. This design composes what ADR 0014, ADR 0027 and ADR 0028 already built |

## Summary

The Memory write pipeline is complete and unmounted. `MemoryOutboxWorker` has
`run_batch`, `poll_once` and `process_one`; `PostgresOutboxRepository` claims,
leases, retries and dead-letters; the recorder, resolver, policy and unit of work
all exist and are covered by tests. Nothing constructs any of it outside tests,
and `docker-compose.yml` has no worker service. Chat writes an outbox event and
nothing ever reads it.

Measured today:

| Fact | Evidence |
| --- | --- |
| Both gates default `False` | `backend/app/config.py` |
| No worker service | `docker-compose.yml` has `db`, `backend`, `frontend` only |
| `MemoryOutboxWorker` instantiated only in tests | grep across `backend/app`, `backend/orchestration` |
| The worker role can claim | ADR 0028, verified: `travel_worker` claims 1 where `travel_app` claims 0 |
| The worker role has no Memory-table grants | migration `20260911_05` enumerates only `conversation_outbox`, `conversations`, `messages` |
| The worker has never run | no process, no loop, no observability |

Mounting it exposes two correctness defects that are latent today because nothing
runs. Both are proved, not suspected:

1. **Two workers claim two events of one conversation simultaneously.** Proved with
   two concurrent transactions: `active_lease_exists` is a read-time predicate and
   `FOR UPDATE SKIP LOCKED` locks only the rows it selected.
2. **One idempotency key can produce two semantic effects.** Proved with two
   concurrent transactions: one idempotency row committed, **two evidence rows**
   committed. The savepoint in `_record_idempotency` protects the transaction, not
   the data.

A worker that claims correctly but writes duplicates is worse than no worker,
because the duplicate is durable and indistinguishable from a real second
observation.

## Context

ADR 0014 established the transactional outbox and its idempotent worker. ADR 0027
added the turn-readiness gate, so an event is claimable only once its turn is
terminal. ADR 0028 gave the worker its own least-privilege role and a bounded
policy on the queue, and proved it can claim. Each of those is verified and
shipped. None of them composes a process.

The unified architecture specification
(`2026-09-10-unified-multi-conversation-agent-memory-architecture.md`) stages the
work as: Stage 1 chat and PostgreSQL, Stage 2 turn understanding and explicit
semantic memory, **Stage 3 background semantic formation** — deploy the worker
runtime, stable idempotency, consolidation, and type-specific activation, shadow
first. This design is Stage 3's first half.

The two defects this design must fix are properties *of* the worker, which is why
they were deferred: their correct shape depends on how the worker is composed and
how much concurrency it is allowed. That is now decided.

## Users

1. **The operator.** They deploy the worker, watch it drain a queue, stop it
   without losing work, and read its metrics.
2. **The authenticated user.** They never see the worker; they benefit from memory
   formed from their conversations, and they depend on it never being formed twice
   or attributed to the wrong turn.
3. **The synchronous Chat runtime.** It writes outbox events and must remain
   unaffected by the worker's health.
4. **The repository owner.** They approve the composition boundary and the two
   concurrency contracts.

## Problem Statement

**Nothing consumes the queue.** Chat writes an event per turn; the event sits
`pending` and released forever. The pipeline cannot be observed end to end, so
every claim about it is a claim about code that has never run together.

**Two workers can process one conversation at once.** `claim_batch` dedupes
conversations *within a batch* and checks for an active lease at read time. Two
workers selecting different rows of one conversation lock different rows and never
block each other. Two concurrent extractions over one transcript can produce
contradictory candidates for the same assertion, and the consolidation that
follows sees a conflict that does not exist.

**One idempotency key can produce two effects.** `_record_idempotency` runs after
the semantic rows are written and swallows `IntegrityError` inside a savepoint, so
the loser of a duplicate-key race commits its evidence, decision, version and
event rows anyway. The key already identifies the effect; nothing enforces it.

**Why now.** Everything downstream — consolidation, activation, read and use —
assumes a worker that has drained a real queue under real concurrency. Building
those on a worker that has never run, or that duplicates under load, would move
the defect somewhere harder to see. This is the last step before the memory
pipeline is demonstrable.

## Goals

1. Run the worker as its own process, under the `travel_worker` role ADR 0028
   created, with its own connection pool and no shared state with the API.
2. Make a conversation's outbox events claimable by at most one worker at a time,
   atomically, without widening the worker's table grants.
3. Make the idempotency key enforce its effect: a second transaction with the same
   key must not commit a second semantic effect.
4. Grant the worker exactly the Memory-table privileges its write path uses,
   enumerated per table.
5. Start, stop and lease correctly: graceful shutdown releases leases, an
   interrupted batch leaves events reclaimable, and a stuck worker does not hold a
   conversation forever.
6. Make the worker observable: claimed, processed, retried, dead-lettered, lease
   lost, and a sustained-empty-claim signal.
7. Deploy with both gates `False` and prove the worker starts, polls an empty
   queue, and shuts down cleanly before any extraction is enabled.

## Non-goals

1. **Enabling active inference.** `MEMORY_WRITE_PIPELINE_ENABLED` and
   `MEMORY_SHADOW_EXTRACT_ENABLED` stay `False` in this design. Rollout is a
   separate owner decision after shadow observation.
2. **Consolidation, activation, or read/use.** Stage 3's second half and Stage 4.
3. **Procedural memory.** Stage 6.
4. **Multi-worker scaling.** One worker process. The design must be *correct* for
   two, because correctness cannot be a function of how many you happen to run,
   but scaling is not a goal.
5. **A distributed queue.** The transactional outbox remains the queue; ADR 0014's
   saturation argument is unchanged.
6. **Retroactive repair of duplicate rows.** No duplicates exist, because nothing
   has run. If the worker is ever run before this change, the operator reports the
   count rather than deleting.
7. **Changing the outbox status vocabulary** (ADR 0014) or the release gate
   (ADR 0027).

## Assumptions

1. **The worker is a single trusted process.** Falsifiable: if it ever executes
   owner-supplied SQL or hosts per-tenant plugins, an advisory lock and a
   table-level policy stop being sufficient boundaries.
2. **`conversation_id` is stable for the life of an event.** Falsifiable: the
   outbox row's `conversation_id` is written at allocation and never updated.
3. **An advisory lock is available to `travel_worker`.** Falsifiable:
   `pg_try_advisory_xact_lock` requires no table privilege; if a future role
   provisioning revokes it, claiming breaks loudly rather than silently.
4. **The idempotency key is a faithful effect identity.** Falsifiable:
   `_semantic_idempotency_key` derives it from `source_outbox_id`, assertion
   identity, normalized value and operation — never from the per-extraction
   candidate id. If a future producer changes that derivation, this design's
   guarantee changes with it.

## User and System Flows

### Flow 1 — the worker polls and drains

1. The worker process starts, resolves `worker_dsn()`, and refuses to start on a
   superuser or `BYPASSRLS` role (`assert_least_privilege_role`).
2. It polls `claim_batch` on an interval. The claim takes a per-conversation
   advisory lock before selecting, so a conversation already being processed is
   skipped rather than double-claimed.
3. Each claimed event is processed inside its own tenant-bound transaction.
4. The event is marked succeeded, retried with back-off, or dead-lettered.

### Flow 2 — graceful shutdown

1. The worker receives `SIGTERM`.
2. It stops claiming new events.
3. It finishes or releases the events it holds, so they become reclaimable on
   lease expiry rather than waiting out the lease.
4. It disposes its engine and exits 0.

### Flow 3 — a conversation is deleted mid-processing

Unchanged from ADR 0023/0027: the delete transaction tombstones the conversation,
bumps the deletion epoch, cancels pending and leased outbox events, and invalidates
memory evidence. The worker's fence detects the move on its next write and stops.

### Flow 4 — the operator observes

Metrics: claimed, processed, retried, dead-lettered, lease lost, and a
**sustained-empty-claim** counter. The last one exists because an empty claim is
otherwise indistinguishable from a healthy quiet system — the failure ADR 0028
fixed at the database level and which must not reappear at the process level.

## Behavioral and Data Contracts

### Worker process

**Produces** an entry point that owns the loop.

- Constructs `PostgresOutboxRepository`, `ConversationService`,
  `MemoryExtractionModel` and `BackgroundMemoryRecorder` from `worker_dsn()`.
- Runs `claim_batch` → `process_one` per event, on a configurable interval.
- Polls with a bounded batch size, so one large backlog cannot starve shutdown.
- Exits non-zero if it cannot start; exits 0 on a clean shutdown.

### Conversation serialisation

**Produces** a per-conversation claim lock.

- `claim_batch` takes `pg_try_advisory_xact_lock(hashtextextended(conversation_id, 0))`
  for each candidate conversation **before** selecting its rows, in a deterministic
  order, and skips any conversation whose lock is not acquired.
- The lock is transaction-scoped, so it releases when the claim transaction ends.
  It guards *claiming*, not processing: a worker that claims a conversation and
  then takes a minute to process it does not hold the lock for that minute, and a
  second worker can claim the conversation's *next* event once the first is
  leased. What the lock prevents is two workers claiming two events of one
  conversation **in the same instant**, which is the defect.
- No table privilege is required, so the worker's grant set is unchanged.

### Idempotency

**Produces** an effect-enforcing key.

- The idempotency row is inserted **before** the semantic rows, in the same
  transaction, with the result columns left `NULL`.
- A conflict on the key is **not** swallowed: the transaction aborts. A second
  transaction with the same key therefore commits nothing.
- After the semantic rows are written, the reserved row is updated with the
  result.
- A caller that loses the race must distinguish "already applied" from "failed".
  It re-reads the key: if the row is now complete, the recorded result stands and
  the caller reports success without writing; if it is still incomplete, the
  competing transaction has not committed and the caller retries.

### Worker grants

**Produces** enumerated Memory-table privileges for `travel_worker`.

- A migration grants the verbs the write path uses, per table, following ADR
  0028's rule: no `ON ALL TABLES`, no default privilege.
- The set is derived from the unit of work's actual statements, not guessed.

### Configuration

**Produces** worker settings, separate from the API's.

- Poll interval, batch size, lease duration, max attempts, and back-off base.
- `worker_dsn()` already exists (ADR 0028). The worker pool is sized separately
  from the API pool.

## Errors and Edge Cases

1. **The queue is empty.** Expected: the poll returns 0, the sustained-empty
   counter advances, the worker sleeps for the interval. Not an error.
2. **The worker role is a superuser or `BYPASSRLS`.** Expected: `startup` raises
   and the process exits non-zero.
3. **Two workers claim the same conversation.** Expected: one takes the advisory
   lock, the other skips that conversation and claims a different one.
4. **Two transactions use one idempotency key.** Expected: exactly one commits a
   semantic effect; the other aborts and reports the recorded result.
5. **A lease expires while the worker is still processing.** Expected: the fence
   rejects the write (`check_outbox_lease` now compares `lease_until`), the worker
   does not cancel a peer's event (`cancel_events` is scoped to its own lease), and
   the event is reclaimed after expiry.
6. **`SIGTERM` arrives mid-batch.** Expected: the current event completes or is
   released; no event is left `leased` with a full lease remaining.
7. **The model provider is transiently down.** Expected: bounded back-off,
   `pending` with `next_attempt_after`, chat unaffected.
8. **The model provider is permanently broken.** Expected: dead-letter after max
   attempts; the event is inspectable, not silently dropped.
9. **A conversation is deleted mid-processing.** Expected: the fence stops the
   write; the delete already cancelled the conversation's events.
10. **The migration is applied before the worker starts.** Expected: the worker
    fails loudly on a missing grant rather than silently claiming nothing.
11. **An event's turn never completes.** Expected: ADR 0027's gate keeps it
    blocked forever, and `ready_outbox_event_count()` does not count it. Intended
    fail-closed behaviour; no reconciliation is added.

## Security and Privacy

1. The worker connects as `travel_worker`, `NOSUPERUSER`/`NOBYPASSRLS`, owning
   nothing, with enumerated grants.
2. The worker's cross-owner visibility is the outbox queue alone. Every read of
   conversation or Memory content is tenant-bound from the claimed row's
   `owner_user_id`.
3. The advisory lock is keyed by a hash of `conversation_id` and carries no
   content. Two different conversations may collide on the hash; the consequence is
   a skipped claim this poll, not incorrectness.
4. The worker never accepts owner input and never executes owner-supplied SQL.
5. Model provider credentials stay in the worker's environment, not in the API's.
6. Logs and metrics exclude message content, evidence text and prompt bodies.

## Observability and Operations

1. Counters: claimed, processed, succeeded, retried, dead-lettered, lease lost,
   sustained-empty polls.
2. A dead-letter that persists is an operator alert; a retry storm is a cost alert.
3. Readiness and liveness are separate from the API's: the worker has no HTTP
   surface in this design, so its liveness is the process itself plus a heartbeat
   metric.
4. Runbook additions: start, stop, drain, inspect dead-letters, and recover a
   stuck conversation.
5. `docs/runbooks/` gains a worker section; the deployment runbook's stop
   conditions cover a worker that cannot start.

## Capacity, Latency, and Cost

1. Polling interval and batch size are configuration; the initial values are
   conservative and calibrated by observation, not guessed.
2. Model cost is per extracted event and is bounded by the batch size times the
   interval.
3. The advisory lock adds one catalog-free lock acquisition per candidate
   conversation per poll.
4. The worker pool is sized independently of the API pool so a backlog cannot
   exhaust the API's connections.
5. No synchronous latency budget: the worker is off the chat path entirely.

## Compatibility and Staged Migration

### Stage A — this design, gates off

Mount the worker with both gates `False`. Prove: it starts, refuses a privileged
role, polls an empty queue, emits the sustained-empty signal, and shuts down
cleanly on `SIGTERM`. No extraction runs.

### Stage B — shadow capture

Enable `MEMORY_SHADOW_EXTRACT_ENABLED`. Extraction runs, candidates are recorded,
no active version is created. Observe quality and cost.

### Stage C — active inference

Enable `MEMORY_WRITE_PIPELINE_ENABLED` only after Stage B's gates pass. Separate
owner decision.

### Compatibility

1. The advisory lock changes no schema and no grant.
2. The idempotency reordering changes transaction shape but not the table.
3. The worker is a new service; the API and frontend are untouched.
4. `ALEMBIC_HEAD` advances for the grant migration.

## Failure and Recovery

| Failure | Behaviour | Recovery |
| --- | --- | --- |
| Worker cannot reach the database | Exits non-zero at startup | Fix connectivity; restart |
| Worker role lacks a grant | Fails loudly on the first write | Re-run the migration |
| Advisory lock never acquired | That conversation is skipped every poll | Alert on sustained-empty-claim; check for a stuck holder |
| Worker killed mid-batch | Leases expire; events are reclaimed | Restart; no repair needed |
| Duplicate idempotency key | The loser aborts and reports the recorded result | None; this is the fix |
| Dead-letter backlog | Events are inspectable | Operator reviews and re-queues deliberately |
| Provider outage | Back-off, then dead-letter | Restore the provider; re-queue dead letters |
| Duplicates found from an earlier run | Counted and reported | Owner decides disposal; never auto-delete |

## Required ADRs

1. **ADR 0029** — the worker runs as its own service under its own role. Required:
   it decides where a process and a credential live.
2. **ADR 0030** — a conversation's events are claimed under a per-conversation
   advisory lock. Required: it commits to advisory locks as a mechanism.
3. **ADR 0031** — the idempotency key is reserved before the effect it guards.
   Required: it changes when a transaction may abort.

Three ADRs, not one, because they are three separable commitments: a deployment
boundary, a locking mechanism, and a transaction ordering rule. A future change to
one must not be read as reopening the others.

## Alternatives Considered

### Alternative A: an in-process worker inside the API

**Approach.** Start the poll loop as a background task in the API's lifespan.

**Benefits.** No new service, no new deployment artefact, one process to operate.

**Costs.** The API process would need the worker's credential as a second engine,
so one process holds two identities and the least-privilege split ADR 0028
established collapses. A memory backlog would compete with request handling for
the same pool and the same event loop.

**Rejected because.** It trades the role boundary for operational convenience, and
the boundary is the thing that makes the worker safe.

### Alternative B: an external scheduler invoking a one-shot poll

**Approach.** A cron or Job runs `poll_once` on a schedule.

**Benefits.** No long-running process; the platform owns restart and scheduling.

**Costs.** Claim latency is bounded by the schedule, and each run must start, claim
and exit within the schedule window. Graceful drain between runs has no natural
home: a killed run leaves leases that must expire rather than be released.

**Rejected because.** The outbox is a queue with a poll interval, not a batch job,
and the lease lifecycle needs a process that can shut down deliberately.

### Alternative C: lock the parent `conversations` row

**Approach.** `SELECT ... FOR UPDATE SKIP LOCKED` on `conversations` before
claiming its events.

**Benefits.** Uses a real row lock rather than an advisory lock; the intent is
visible in the data model.

**Costs.** `conversations` is `FORCE`-enabled and the worker has no tenant bound at
claim time, so it cannot see the row. Making it visible needs a worker policy on
`conversations`, widening the cross-owner grant beyond the queue.

**Rejected because.** It widens the worker's cross-owner visibility to fix a
concurrency problem, when a lock that needs no table privilege does the job.

### Alternative D: a unique effect key on four tables

**Approach.** Add `effect_key` plus a unique index to `memory_evidence`,
`memory_decisions`, `memory_events` and `memory_outbox`.

**Benefits.** The invariant becomes structural: the database refuses a duplicate
even if a future caller forgets the ordering rule.

**Costs.** A schema change on four tables, and a key that must be computed and
carried by every writer. The idempotency key already is that identity; this
duplicates it.

**Rejected because.** Reserving the existing key before the effect achieves the
same guarantee inside the transaction that already exists. The structural version
remains available if a second producer ever appears — recorded as a follow-up, not
dismissed.

## Current-state Evidence

| Claim | Evidence path | Verified how |
| --- | --- | --- |
| The worker exists and is complete | `backend/memory/write_pipeline/worker.py` — `run_batch`, `poll_once`, `process_one` | Read source |
| Nothing constructs it outside tests | grep `MemoryOutboxWorker(` across `backend/app`, `backend/orchestration` | Read source |
| No worker service | `docker-compose.yml` | Read source |
| Both gates default `False` | `backend/app/config.py` | Read source |
| The worker role can claim | migration `20260911_04`; ADR 0028 verification | Ran `claim_batch` under both roles: 1 vs 0 |
| The worker role has no Memory grants | migration `20260911_05` | Queried `information_schema.role_table_grants` |
| Two workers claim one conversation | `outbox.py:459-544` | Two concurrent transactions; both rows leased by different workers |
| One key, two effects | `postgres.py:741-779`, `:441-457` | Two concurrent transactions; 1 idempotency row, 2 evidence rows |
| The fence now checks the lease window | `postgres_repository.py:1109-1145` | Read source; unit test on an expired lease |

**Not verified.** No worker process exists, so nothing in this design has run. The
advisory-lock approach is unproven against this schema; it is standard PostgreSQL
but this repository has never used one. The Memory-table grant set is derived by
reading the unit of work's statements, not by running them under the worker role —
the plan must confirm it empirically. Worker throughput, model cost per event, and
the right poll interval are unmeasured; the design deliberately treats them as
configuration to be calibrated rather than numbers to be asserted.

## Components and Dependency Direction

```text
  +---------------------+        +----------------------+
  | worker process      |        | API process          |
  | role travel_worker  |        | role travel_app      |
  | own pool            |        | own pool             |
  +----------+----------+        +----------+-----------+
             |                              |
             | claim_batch (advisory lock)  | writes blocked events
             v                              v
  +-------------------------------------------------------+
  | conversation_outbox   ENABLE RLS                      |
  |   tenant_isolation (public) + worker policies         |
  +-------------------------------------------------------+
             |  after claim: tenant_transaction(owner)
             v
  +-------------------------------------------------------+
  | conversations / messages   FORCE RLS                  |
  | memory_*                   ENABLE RLS                 |
  +-------------------------------------------------------+
             ^
             | reserve key -> effect -> fill result
  +----------+----------+
  | PostgresMemoryUnitOfWork |
  +---------------------+
```

**Allowed dependency direction.** The worker depends on the outbox repository, the
conversation service, the model adapter and the recorder — all of which already
exist and gain no new dependency. The API gains nothing.

**Ownership.** The migration role owns every object. `travel_worker` owns nothing
and holds enumerated grants. The advisory lock is held by the claiming transaction
and released with it.

## Data Flow and Lifecycle

1. Chat commits a user message, a pending assistant row, and a blocked outbox
   event atomically, tenant-bound, as `travel_app`.
2. `complete_turn` releases the gate.
3. The worker polls. `claim_batch` takes the conversation's advisory lock, then
   selects and leases its ready events.
4. The worker binds the claimed owner's tenant and reads the transcript inside the
   event's range.
5. Extraction produces candidates; the recorder derives the effect key, **reserves
   it**, then writes evidence, decision, version and event, then fills the result.
6. The event is marked succeeded. The advisory lock was released when the claim
   transaction ended.
7. Metrics report the batch.

## Approval Record

| Version | Decision owner | Date | Notes |
| --- | --- | --- | --- |
| 0.1 | Repository owner | 2026-09-12 | Drafted after the owner chose all three crux decisions: a dedicated Compose service, a per-conversation advisory lock, and reserving the idempotency key before the effect. |

| 0.1 | Repository owner | 2026-09-12 | **Approved** on the owner's instruction to implement. Version unchanged: the approved text is the text above. |

**This document is approved.** Approval authorized ADRs 0029, 0030 and 0031 and the
implementation plan, and the owner then instructed implementation of that plan.

Approval does **not** authorize enabling either Memory feature gate, active
inference, consolidation, activation, read/use in Chat, procedural memory,
multi-worker scaling, or Git delivery.
