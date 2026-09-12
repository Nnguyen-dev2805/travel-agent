# ADR 0035: Application Composition Happens at Startup, and a Request Without It Fails Closed

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-12 |
| Decision owners | Repository owner |
| Scope | When the application's object graph is composed, and what a request observes when it was not |
| Governing spec | [Worker Authority: Credential, Lease Time, and Fence Semantics](../specs/2026-09-12-worker-authority-credential-lease-fence-design.md) v0.1 (Approved) — this record ratifies the composition-lifecycle change that spec listed as out of its approval scope |
| Superseded ADR | None |
| Superseded by | None |

## Context

ADR 0018 made `RuntimeContainer` the single composition root for the API
process: the FastAPI lifespan constructs it, stores it on `app.state.container`,
and disposes it on shutdown. What ADR 0018 did not decide is what happens when a
request arrives and no container is there.

`get_runtime_container` (`backend/app/runtime_container.py`) used to answer that
question itself: when `app.state.container` was absent it constructed a
production container on demand — engine, DSN resolution, least-privilege role
check included — and served the request from it. Three consequences followed:

1. **A second composition root existed.** The lifespan was the composition root
   on paper, but any request served without it silently built its own runtime.
   A bare ASGI mount, a probe, a test — each became its own composition
   authority, with its own engine and its own pool, none of them disposed by the
   shutdown path that did not create them.
2. **Unit tests opened real database connections.** The lazy path resolved
   `DATABASE_URL` from `.env`, so a test that reached a route dependency without
   the lifespan — `TestClient` does not run lifespans by default — connected to
   the developer's live PostgreSQL, as whichever role `.env` named. The suite's
   result depended on whether a database happened to be reachable, and on which
   privileges its role carried.
3. **A broken deployment looked like a working one.** A process that never ran
   its lifespan — a misconfigured entry point, a stripped-down ASGI mount —
   served traffic indistinguishably from a composed one. The defect was
   invisible precisely at the moment it mattered: in production, where nobody
   watches for "did the lifespan run?".

The fail-closed shape was already implemented in the working tree and is
referenced by three sites (`backend/app/runtime_container.py`,
`backend/tests/integration/test_auth_api.py`,
`backend/tests/integration/test_ops_readiness_api.py`) as "ADR 0035" — a record
that did not exist. This ADR is that record, written after the fact to give the
implemented behavior the architecture authority it was already being cited
under, per the repository owner's instruction to implement the verified review
findings without a separate spec round.

## Decision

**Application composition happens once, at startup, in the FastAPI lifespan. A
request that finds no composed container fails closed with
`ContainerUnavailableError` rather than composing one on demand.**

Specifically:

1. `get_runtime_container` reads `app.state.container` and raises
   `ContainerUnavailableError` when it is absent. It never constructs a
   container, an engine, or any other production resource.
2. `ContainerUnavailableError` is a `RuntimeError`: a process serving requests
   without its lifespan is a broken deployment, not a request to serve. The
   API's existing 500 path renders it as a content-free server error with a
   correlated request id.
3. Tests that need a container compose their own — an explicit, in-test
   substitution for the lifespan — as `test_auth_api.py` and
   `test_ops_readiness_api.py` already do. A test that forgets fails loudly
   with the same error a broken deployment produces, instead of quietly
   connecting to a live database.
4. The same rule holds for the background Memory worker (ADR 0029): its
   `main()` is the only place its object graph is composed, and its failure to
   start is a non-zero exit rather than a partially-constructed runtime.

## Alternatives Considered

### Keep the lazy composition as a convenience

**Approach.** Leave `get_runtime_container` able to build a container when the
lifespan did not run.

**Costs.** Every consequence in Context remains: a second composition root,
tests that depend on a reachable database, and a deployment defect that serves
traffic. The convenience served no production path — a correctly deployed
process always runs its lifespan — and its only observable effect was in tests,
where the "convenience" was a live-database dependency the suite never asked
for.

### Fail closed with a dedicated retry or warmup

**Approach.** Treat a missing container as a cold start: compose one, but
synchronously within the request, and log a warning.

**Costs.** This is the lazy path with a log line. The request still pays engine
construction, the role check still runs per-process rather than once, and the
signal "this deployment never composed itself" is still buried. A deployment
defect should stop traffic, not add latency to its first request.

## Consequences

- A bare ASGI mount or a miswired entry point now produces loud, immediate
  `500`s naming `ContainerUnavailableError`, instead of silently serving.
- `TestClient`-based tests that reach container-backed dependencies must either
  use `with TestClient(app)` to run the lifespan or compose their own container
  substitute. The two integration modules cited above show the pattern.
- The composition root claim in ADR 0018 is now enforced by the runtime rather
  than by convention: there is exactly one place composition can happen.
- Engine construction, DSN resolution, and the least-privilege role check each
  run exactly once per process, at startup, where their failures name the
  environment rather than a request.

## Verification

- `backend/tests/unit/test_runtime_container.py` covers the fail-closed path:
  a request without a container raises, and one with a container returns it.
- `backend/tests/integration/test_auth_api.py` and
  `backend/tests/integration/test_ops_readiness_api.py` compose their own
  container substitutes, demonstrating the test-side contract this decision
  creates.
- The three "ADR 0035" references in the tree now point at an existing record;
  this document is that record.
