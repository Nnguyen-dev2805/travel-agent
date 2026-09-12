# ADR 0029: The Background Memory Worker Runs as Its Own Service Under Its Own Role

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-12 |
| Decision owners | Repository owner |
| Scope | Where the background Memory worker process runs and which credential it holds |
| Governing spec | [Memory Worker Runtime](../specs/2026-09-12-memory-worker-runtime-design.md) v0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

ADR 0014 built the transactional outbox and its worker. ADR 0027 made an event
claimable only once its turn is terminal. ADR 0028 gave the worker a dedicated
role, `travel_worker`, and a bounded policy on `conversation_outbox`, and proved it
can claim where the API role cannot.

None of them composes a process. `MemoryOutboxWorker` has `run_batch`, `poll_once`
and `process_one`, and is instantiated only in tests. `docker-compose.yml` defines
`db`, `backend` and `frontend`. Chat writes an outbox event per turn and nothing
reads it.

The question this record settles is not *whether* to run the worker but *where* it
runs and *as whom*. That matters because ADR 0028 deliberately split the
identities: `travel_app` cannot see the queue, `travel_worker` can, and both are
`NOSUPERUSER NOBYPASSRLS`. Any composition that puts both identities in one process
gives that process the union of their privileges.

## Decision

**The background Memory worker runs as its own process, as its own service, holding
only the `travel_worker` credential.**

Specifically:

1. `docker-compose.yml` gains a `worker` service built from the same image as the
   backend, running the worker entry point rather than the API.
2. The worker connects through `Settings.worker_dsn()` — the `travel_worker` role —
   and never through `DATABASE_URL` or `travel_app`.
3. The worker owns its own connection pool, sized independently of the API's, so a
   memory backlog cannot exhaust the API's connections.
4. The worker runs `assert_least_privilege_role` at startup, exactly as the API
   does, and exits non-zero rather than starting on a superuser or `BYPASSRLS`
   role.
5. The API process gains no worker code path, no worker credential, and no
   background task.

## Alternatives Considered

### An in-process worker inside the API

**Approach.** Start the poll loop as a background task in the API's lifespan.

**Benefits.** No new service, no new deployment artefact, one process to operate.

**Costs.** The API process would need a second engine on the worker credential, so
one process holds two identities and the least-privilege split collapses into a
union. A backlog would compete with request handling for the same pool and the same
event loop, and the API's readiness would become a function of the worker's health.

**Rejected because.** It trades the role boundary for operational convenience, and
the boundary is what makes the worker safe.

### An external scheduler invoking a one-shot poll

**Approach.** A cron entry or platform Job runs a single `poll_once` per schedule.

**Benefits.** No long-running process; the platform owns restart and scheduling.

**Costs.** Claim latency is bounded by the schedule. Each run must start, claim and
exit inside its window. Graceful drain has no natural home: a killed run leaves
leases that must expire rather than being released deliberately, so a conversation
can be unclaimable for the lease duration after every run.

**Rejected because.** The outbox is a queue with a poll interval, not a batch job,
and the lease lifecycle needs a process that can shut down on purpose.

### One process holding both credentials

**Approach.** Run the worker in the API process but connect with a second engine on
`travel_worker`.

**Benefits.** Keeps the database privileges separate while sharing a process.

**Costs.** The separation is then only as strong as the code that chooses which
engine to use. A bug that passes the wrong engine hands the API the queue, or hands
the worker the API's narrower view, with no process boundary to catch it.

**Rejected because.** A credential boundary that lives inside one process is a
convention, not a boundary.

## Consequences

**Positive.**

- The process boundary matches the credential boundary: neither process can use the
  other's identity even by mistake.
- Worker failure is isolated. A crash, a leak, or a runaway extraction does not
  touch request handling.
- The worker's pool, poll interval and batch size are tunable without touching the
  API.
- Startup fails closed on a privileged role in both processes, by the same shared
  guard.

**Negative.**

- One more service to build, deploy, monitor and document, and one more credential
  to provision.
- Two processes reading the same database means two pools; the total connection
  budget must be reasoned about rather than assumed.
- Local development needs the worker service running, or memory simply does not
  form — which is easy to forget and produces a silent empty pipeline.

**Neutral.**

- The API and frontend are untouched.
- No schema change.
- ADR 0028's role, policies and grants are unchanged; this record consumes them.

## References

1. [ADR 0014: Transactional outbox and idempotent memory workers](./0014-transactional-outbox-and-idempotent-memory-workers.md)
2. [ADR 0027: An outbox event is released only when its turn is terminal](./0027-outbox-event-released-only-when-turn-terminal.md)
3. [ADR 0028: The background worker claims through a role-scoped policy, and binds a tenant after the claim](./0028-worker-role-and-outbox-claim-boundary.md)
4. [Memory Worker Runtime](../specs/2026-09-12-memory-worker-runtime-design.md) — governing specification
5. [Worker Role and Tenant-Bound Outbox Claim](../specs/2026-09-11-worker-role-tenant-bound-outbox-claim-design.md)
