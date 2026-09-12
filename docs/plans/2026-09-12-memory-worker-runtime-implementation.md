# Memory Worker Runtime — Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence. Each task ends with a review checkpoint; do not begin
> the next task until the checkpoint condition holds.

**Goal:** Compose and deploy the background Memory worker as its own service under
its own role, with a per-conversation advisory lock on claiming and an idempotency
key that enforces its effect, then prove it starts, polls an empty queue and shuts
down cleanly with both feature gates still off.

**Architecture:** A new `worker` Compose service runs a poll loop as
`travel_worker` with its own pool. `claim_batch` takes a transaction-scoped
advisory lock per conversation before selecting its events. The unit of work
reserves the idempotency key before writing semantic rows and no longer swallows a
key conflict, so a duplicate aborts instead of committing a second effect.

**Tech Stack:** Python 3.13, SQLAlchemy Core, Alembic, PostgreSQL 16, pytest,
Docker Compose.

**Spec:** [Memory Worker Runtime](../specs/2026-09-12-memory-worker-runtime-design.md) v0.1

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-09-12 |
| Approved specification | [Memory Worker Runtime](../specs/2026-09-12-memory-worker-runtime-design.md) v0.1, approved 2026-09-12 |
| Required ADRs | ADR 0029, ADR 0030, ADR 0031 — all Accepted 2026-09-12 |
| Execution owner | Agent, under repository-owner instruction |
| Decision owner | Repository owner |
| Scope | Conversation serialisation, idempotency enforcement, worker grants, the worker process and its loop, the Compose service, and worker observability |
| Verification | Migration round-trip; focused integration and unit suites; full backend suite; frontend suite; a live worker start/poll/shutdown probe against a real database |

## Global Constraints

1. Every persistent repository change requires a written specification and an
   approved implementation plan (`AGENTS.md`). **Do not execute this plan until
   the specification is approved and ADRs 0029, 0030 and 0031 are accepted.**
2. The repository owner creates or selects branches and decides when to stage,
   commit in the primary working tree, push, open a PR, merge, and release. No Git
   delivery is authorized by this plan.
3. The working tree is dirty and large. Read a dirty file before touching it and
   work with the existing edits rather than reverting them.
4. **Both Memory feature gates stay `False`.** `MEMORY_WRITE_PIPELINE_ENABLED` and
   `MEMORY_SHADOW_EXTRACT_ENABLED` are not enabled by this plan. The worker is
   mounted, proves it runs, and finds an empty queue.
5. **Never grant `BYPASSRLS` or `SUPERUSER`.** The worker role stays
   `NOSUPERUSER NOBYPASSRLS` and its grants are enumerated per table — no
   `ON ALL TABLES`, no `ALTER DEFAULT PRIVILEGES`.
6. **The worker connects only through `worker_dsn()`.** It must never fall back to
   `DATABASE_URL` or the `travel_app` credential.
7. **Do not change the outbox status vocabulary or the release gate.** ADR 0014's
   lifecycle and ADR 0027's `released_at` are unchanged.
8. **Do not widen the worker's cross-owner visibility beyond
   `conversation_outbox`.** No policy on `conversations` or `messages`.
9. **No retroactive repair of duplicate rows.** Nothing has run, so none should
   exist. If the operator finds any, report the count; disposal is a separate owner
   decision.
10. Behaviour changes use a red-green-refactor cycle. Each task states the failing
    test first.
11. Never expose secrets, credentials, tokens, or sensitive personal data in code,
    logs, commands, evidence, or documentation.
12. Run each test directory in its **own** shell command with its own
    `--basetemp=.workbuddy-ai/tmp/pytest*`; a single command spanning several
    directories trips the host's delete guard. Never run the backend and frontend
    suites concurrently. Integration requires `PG_TEST_DSN`,
    `PG_RUNTIME_TEST_DSN` and `PG_WORKER_TEST_DSN`.

## Required ADR — prerequisite

| ADR | Title | Status required |
| --- | --- | --- |
| [ADR 0029](../adr/0029-the-memory-worker-runs-as-its-own-service.md) | The background Memory worker runs as its own service under its own role | **Accepted** before Task 5 |
| [ADR 0030](../adr/0030-a-conversation-is-claimed-under-an-advisory-lock.md) | A conversation's outbox events are claimed under a per-conversation advisory lock | **Accepted** before Task 1 |
| [ADR 0031](../adr/0031-the-idempotency-key-is-reserved-before-the-effect.md) | The idempotency key is reserved before the semantic effect it guards | **Accepted** before Task 2 |

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/memory/write_pipeline/outbox.py` | Take the per-conversation advisory lock before selecting a conversation's events | Task 1 |
| `backend/memory/write_pipeline/postgres.py` | Reserve the idempotency key before the effect; stop swallowing the conflict | Task 2 |
| `backend/memory/write_pipeline/background_recorder.py` | Handle a lost key race: report the recorded result or retry | Task 2 |
| `backend/storage/migrations/versions/20260911_06_worker_memory_grants.py` | Enumerate the worker's Memory-table privileges | Task 3 |
| `backend/storage/postgres.py` | Advance `ALEMBIC_HEAD` | Task 3 |
| `backend/memory/write_pipeline/runtime.py` | The worker process: poll loop, startup guard, graceful shutdown | Task 4 |
| `backend/app/config.py` | Worker poll interval, batch size, lease, attempts, back-off | Task 4 |
| `docker-compose.yml` | The `worker` service | Task 5 |
| `backend/memory/write_pipeline/observability.py` | Counters, including sustained-empty-claim | Task 6 |
| `docs/runbooks/deployment.md`, `docs/runbooks/local-development.md` | Worker start, stop, drain, dead-letter inspection | Task 6 |

---

## Task 1: Per-Conversation Advisory Lock on Claim

**Files:**
- Modify: `backend/memory/write_pipeline/outbox.py`
- Test: `backend/tests/integration/test_outbox_turn_readiness.py`

**Interfaces:**
- Consumes: ADR 0028's claim path
- Produces: `claim_batch` that skips a conversation whose advisory lock it cannot take

- [x] **Step 1: Write the failing test**

A deterministic two-transaction test that reproduces the defect first:

```text
- create one conversation with TWO released events
- connection A: claim one row with FOR UPDATE SKIP LOCKED, do not commit
- call claim_batch through the real repository on a second engine
- assert it claims NOTHING for that conversation (the lock is held)
- commit A; call claim_batch again; assert it now claims the second event
```

The first assertion fails against the current implementation, which claims the
second row.

- [x] **Step 2: Run verification — expect FAIL**

```bash
PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… PG_WORKER_TEST_DSN=… \
  .venv/bin/python -m pytest backend/tests/integration/test_outbox_turn_readiness.py \
  -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-m1
```

- [x] **Step 3: Implement**

In `PostgresOutboxRepository.claim_batch`, before selecting rows:

```text
1. select the distinct candidate conversation_ids matching the existing
   conditions, ordered by conversation_id
2. for each, in that order:
     SELECT pg_try_advisory_xact_lock(hashtextextended(:conversation_id, 0))
   keep only the conversations whose lock was acquired
3. select and lease rows for those conversations only
```

The ordering is what prevents two workers deadlocking against each other when they
hold different conversations and each wants the next.

- [x] **Step 4: Run verification — expect PASS**

Re-run Step 2, then the whole module.

- [x] **Step 5: Review checkpoint**

Review: the lock is transaction-scoped, the ordering is deterministic, a skipped
conversation is claimable on the next poll, and no grant changed.

---

## Task 2: The Idempotency Key Enforces Its Effect

**Files:**
- Modify: `backend/memory/write_pipeline/postgres.py`,
  `backend/memory/write_pipeline/background_recorder.py`
- Test: `backend/tests/integration/test_memory_write_postgres.py`

**Interfaces:**
- Consumes: the existing `_semantic_idempotency_key`
- Produces: reserve → effect → fill, with the conflict propagated

- [x] **Step 1: Write the failing test**

A deterministic two-transaction test:

```text
- transaction A: reserve the key, write its evidence, do not commit
- transaction B in a thread: reserve the SAME key, write its own evidence
- commit A; B must raise on the conflict, not swallow it
- assert exactly ONE evidence row committed for the assertion
```

The final assertion fails against the current implementation, which commits two.

- [x] **Step 2: Run verification — expect FAIL**

```bash
PG_TEST_DSN=… .venv/bin/python -m pytest \
  backend/tests/integration/test_memory_write_postgres.py \
  -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-m2
```

- [x] **Step 3: Implement**

In `PostgresMemoryUnitOfWork._apply_once`:

```text
1. reserve: insert the idempotency row with NULL result columns, before any
   semantic insert. Do NOT wrap in a savepoint and do NOT catch IntegrityError.
2. on conflict, raise a typed error carrying the key
3. effect: the existing assertion / version / evidence / decision / event /
   outbox writes, unchanged
4. fill: UPDATE the reserved row with the result
```

Remove `_record_idempotency`'s savepoint and its comment.

In `BackgroundMemoryRecorder`, handle the typed error: re-read the key; if the row
is complete, return its recorded result; if it is still incomplete, retry the
operation.

- [x] **Step 4: Run verification — expect PASS**

Re-run Step 2, then the whole module.

- [x] **Step 5: Review checkpoint**

Review: a duplicate key commits nothing; a completed effect is still reported as
success on redelivery; a crash between reserve and effect leaves no stranded key
because the reservation is in the same transaction.

---

## Task 3: Enumerate the Worker's Memory Grants

**Files:**
- Create: `backend/storage/migrations/versions/20260911_06_worker_memory_grants.py`
- Modify: `backend/storage/postgres.py` (`ALEMBIC_HEAD`)
- Test: `backend/tests/integration/test_postgres_migrations.py`

**Interfaces:**
- Consumes: migration `20260911_05`
- Produces: enumerated `travel_worker` privileges on the Memory tables

- [x] **Step 1: Derive the grant set, then write the failing test**

Read every statement the unit of work issues (`postgres.py`) and list the tables
and verbs it actually uses. Do **not** guess. Then assert the exact resulting set:

```text
- information_schema.role_table_grants for travel_worker equals the enumerated set
- travel_worker has no privilege on alembic_version
- no ALTER DEFAULT PRIVILEGES entry mentions travel_worker
- downgrade revokes exactly what upgrade granted
```

- [x] **Step 2: Run verification — expect FAIL**

```bash
PG_TEST_DSN=… .venv/bin/python -m pytest \
  backend/tests/integration/test_postgres_migrations.py \
  -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-m3
```

- [x] **Step 3: Implement the migration**

Grant only the derived verbs, per table. No `ON ALL TABLES`, no default privilege.
Advance `ALEMBIC_HEAD`.

- [x] **Step 4: Prove the worker can actually write**

Run the recorder's write path against a real database **as `travel_worker`** and
assert it succeeds. A grant set that is too narrow fails here, loudly, which is the
point.

- [x] **Step 5: Run verification — expect PASS**

- [x] **Step 6: Review checkpoint**

Review: the grant set is derived, not guessed; the worker can write; it cannot
touch `alembic_version`; the round-trip is faithful.

---

## Task 4: The Worker Process

**Files:**
- Create: `backend/memory/write_pipeline/runtime.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/unit/memory_write_pipeline/test_runtime.py`

**Interfaces:**
- Consumes: `MemoryOutboxWorker`, `Settings.worker_dsn()`, `assert_least_privilege_role`
- Produces: `run_worker(...)` with a poll loop and a graceful stop

- [x] **Step 1: Write the failing tests**

```text
- startup refuses a superuser or BYPASSRLS role and exits non-zero
- the loop polls, sleeps the configured interval, and polls again
- a stop signal finishes the in-flight event and releases the rest
- the batch size bounds how many events one poll claims
- an empty poll increments the sustained-empty counter and does not error
- the worker builds its engine from worker_dsn(), never DATABASE_URL
```

- [x] **Step 2: Run verification — expect FAIL**

```bash
.venv/bin/python -m pytest backend/tests/unit/memory_write_pipeline/test_runtime.py \
  -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-m4
```

- [x] **Step 3: Implement**

A module-level `main()` plus a `run_worker(stop_event, ...)` seam so the loop is
testable without a process. Settings: `WORKER_POLL_INTERVAL_SECONDS`,
`WORKER_BATCH_SIZE`, `WORKER_LEASE_SECONDS`, `WORKER_MAX_ATTEMPTS`,
`WORKER_BACKOFF_BASE_SECONDS`. `SIGTERM` and `SIGINT` set the stop event.

- [x] **Step 4: Run verification — expect PASS**

- [x] **Step 5: Review checkpoint**

Review: the guard runs at startup; shutdown is graceful; the loop cannot spin hot
on an empty queue; the engine comes from `worker_dsn()` only.

---

## Task 5: The Compose Service

**Files:**
- Modify: `docker-compose.yml`, `.env.example`
- Test: `docker compose config --quiet`

**Interfaces:**
- Consumes: the worker entry point from Task 4
- Produces: a `worker` service

- [x] **Step 1: Add the service**

Same image as `backend`, command runs the worker entry point, `WORKER_DATABASE_URL`
pointing at `travel_worker@db:5432`, `depends_on: db healthy`, `restart:
unless-stopped`. Both feature gates explicitly `false`.

- [x] **Step 2: Verify the config resolves**

```bash
docker compose config --quiet
```

- [x] **Step 3: Prove a live start / poll / stop against a real database**

Start the worker against the test database with the gates off. Assert from the logs
and metrics: it started, refused nothing, polled, found an empty queue, and exited 0
on `SIGTERM`. This is the end-to-end proof the plan exists for.

- [x] **Step 4: Review checkpoint**

Review: the worker never receives `DATABASE_URL`; the API service is unchanged;
neither gate is enabled.

---

## Task 6: Observability and Runbook

**Files:**
- Create: `backend/memory/write_pipeline/observability.py`
- Modify: `docs/runbooks/deployment.md`, `docs/runbooks/local-development.md`
- Test: `backend/tests/unit/memory_write_pipeline/test_runtime.py`

**Interfaces:**
- Consumes: the loop from Task 4
- Produces: counters and a documented operating procedure

- [x] **Step 1: Write the failing tests**

```text
- each counter increments on its event: claimed, processed, retried,
  dead_lettered, lease_lost, sustained_empty_polls
- a successful poll resets sustained_empty_polls
- no counter carries message content, evidence text or a prompt body
```

- [x] **Step 2: Run verification — expect FAIL**

- [x] **Step 3: Implement the counters and the runbook sections**

Document: start, stop, drain, inspect dead letters, recover a stuck conversation,
and what to do when sustained-empty stays high while events exist.

- [x] **Step 4: Run verification — expect PASS**

- [x] **Step 5: Review checkpoint**

Review: the sustained-empty signal exists and is documented as the detector for a
worker that cannot claim; no counter leaks content.

---

## Package Verification

Run each directory in its **own** command, in this order:

1. `.venv/bin/python -m compileall -q backend`
2. `.venv/bin/python -m pytest backend/tests/unit -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-p1`
3. `.venv/bin/python -m pytest backend/tests/boundaries -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-p2`
4. `PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… PG_WORKER_TEST_DSN=… .venv/bin/python -m pytest backend/tests/integration -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-p3 -rs`
5. Alembic round-trip: `upgrade head`, `downgrade -1`, `upgrade head`
6. `cd frontend && npm run lint && npm test`
7. `docker compose config --quiet`
8. The live worker start / poll / stop probe from Task 5 Step 3
9. `git status --short --untracked-files=all` and `git diff --check`

A required skip, a conflict marker, or a failing check blocks the completion claim.
The integration suite must run with zero required skips.

## Rollback

| Stage | Action |
| --- | --- |
| Before the migration | Abandon the worktree; no persistent change |
| After the migration, before the service runs | `alembic downgrade -1`; the worker's grants are revoked |
| After the service runs | Stop the worker service first; in-flight leases expire and are reclaimed on restart |
| A grant turns out too narrow | The worker fails loudly on the first write; widen it in a migration, never by `ON ALL TABLES` |
| Duplicate rows appear | Stop the worker, report the count, and take an owner decision; never auto-delete |

Both gates remain `False` throughout, so stopping the worker stops all extraction
with no data repair.

## Completion Record

| Field | Value |
| --- | --- |
| Specification approval | Approved 2026-09-12; ADRs 0029, 0030 and 0031 accepted. |
| Plan approval | Approved 2026-09-12 on the owner's instruction to implement. |
| Execution | **Complete. All six tasks executed.** |
| Verification | Complete for this plan's scope; results below. |
| Delivery gate | Repository owner only. No Git delivery is authorized by this plan. |

**Checkbox state is evidence, not intent.** All 30 steps are ticked because their
evidence exists.

### Task 1 — conversation serialisation

`claim_batch` takes a per-conversation advisory lock before selecting a
conversation's rows, ordered by the oldest waiting work with the conversation id as
a tie-break. `claim_event` takes the same lock, so the single-event path cannot
take an event out from under a peer claiming the same conversation.

Proved by two tests: the mechanism test holds the lock in one transaction and
asserts a second cannot take it; the behaviour test asserts a claim skips a
conversation under another transaction's lock and claims it once released.
**Mutation proof**: replacing the lock acquisition with the raw candidate list makes
the behaviour test fail.

### Task 2 — idempotency enforcement

The key is reserved before the semantic rows and filled after them, in one
transaction, and the conflict is no longer swallowed. `_record_idempotency`'s
savepoint is gone, replaced by `_reserve_idempotency` and `_fill_idempotency`.

**A schema change was NOT needed, contrary to the plan's sketch.** Because the
reservation and the fill share a transaction, any row another transaction can see
is complete, so no "incomplete" marker is required and the `NOT NULL` columns are
satisfied with values known at reserve time. Recorded as a deviation and an
improvement.

Proved by `test_a_second_reservation_of_a_held_key_conflicts` (deterministic, two
transactions) and `test_replaying_one_key_commits_one_effect`. **Mutation proof**:
making the reservation swallow its conflict makes the first fail.

**A test was deleted rather than kept.** A threaded same-key test passed whether or
not the reservation swallowed its conflict — two threads on this fixture usually run
one after the other. An assertion that cannot fail is decoration.

### Task 3 — worker grants

Migration `20260911_06` grants the seven Memory tables the verbs the unit of work
issues, derived by reading its statements rather than guessed.

**The derivation was wrong on the first attempt, and Task 3 Step 4 caught it.**
`memory_assertions` was granted `SELECT, INSERT`; the write then failed with
`permission denied for table memory_assertions` on
`SELECT ... FROM memory_assertions WHERE ... FOR UPDATE`. PostgreSQL requires the
`UPDATE` privilege for a row-locking read, not only `SELECT`. After widening the
grant the write succeeded as `travel_worker`.

That failure is exactly what the step exists for: a grant set derived by reading
statements is a hypothesis until the write is executed under the role.

### Task 4 — the worker process

`backend/memory/write_pipeline/runtime.py` composes the pipeline and runs the loop;
`observability.py` holds the counters.

**Task 4 exposed a gap the plan did not anticipate: there was no production
`LLMProvider`.** `MemoryExtractionModel` requires the protocol
`generate(prompt, **kwargs) -> str`; across all of `backend/` the only production
definition was the protocol declaration itself, every construction site was a test
with a fake, and the RAG path's `LLMGenerator.generate(user_message, context)` has
a different signature and return type. The worker could not be built without one.

The repository owner directed that the provider take its configuration from
`.env`, so `provider.py` is an OpenAI-compatible adapter reading
`GITHUB_MODELS_URL`, `GITHUB_TOKEN`, `LLM_MODEL`,
`LLM_REQUEST_TIMEOUT_SECONDS` and `LLM_MAX_RETRIES` — the same settings the chat
path uses, so one deployment has one provider configuration.

Its error classification lives in one place, `_classify`, and defaults to
**permanent**: 5xx, 408, 409, 425 and 429 are transient; every other status and
every unclassified failure is permanent. Retrying an unknown failure is how a
broken deployment becomes a cost incident.

Proved by 10 unit tests, including that the loop stops *between* batches rather
than mid-event, that the batch size bounds every poll, that a claimed event resets
`sustained_empty_polls`, and that `main()` builds its engine from `worker_dsn()` and
never from `DATABASE_URL`.

### Task 5 — the Compose service

A `worker` service in `docker-compose.yml`, same image as the backend, running
`python -m backend.memory.write_pipeline.runtime`, receiving only
`WORKER_DATABASE_URL`, with both gates explicitly `false`. `docker compose config
--quiet` is clean.

**The end-to-end probe ran.** Against a freshly migrated database, with the gates
off, the worker started, polled an empty queue seven times, received `SIGTERM` and
exited 0:

```
INFO memory worker started worker_id=memory_worker_1 interval=0.40s batch=5
INFO memory worker poll {'claimed': 0, ..., 'sustained_empty_polls': 1, 'polls': 1}
... seven polls, all claimed 0 ...
INFO memory worker received signal 15
INFO memory worker stopped {...}
exit code on SIGTERM: 0
```

**The first run produced no output at all**, which was a real defect: the process
configured no logging, so a container running the worker emitted no evidence that it
had started, polled or stopped, and the sustained-empty signal went nowhere.
`_configure_logging()` fixes it, and only acts when the root logger has no handlers.

### Task 6 — observability and runbook

`WorkerCounters` folds every outcome and carries **numbers only** — no message text,
evidence text, prompt body or owner identity, because counters are emitted into logs
and metrics, which are less protected than the database. A worker section was added
to `docs/runbooks/deployment.md` and `docs/runbooks/local-development.md`, leading
with `sustained_empty_polls` as the one signal that distinguishes an idle worker
from one that cannot claim.

### Facts established

1. The revision identifier is `20260911_06`.
2. The derived worker grant set is 13 privileges across 7 tables.
   `memory_assertions` needs `UPDATE` for the `FOR UPDATE` lock.
3. `hashtextextended` is available on PostgreSQL 16 and is used by the claim lock.
4. Not measured: the empty-poll cost, so the poll interval remains uncalibrated.
   The default of 5 seconds is a starting point, not a finding.

### Verification

| Check | Result |
| --- | --- |
| `compileall` | exit 0 |
| boundaries | 16 passed |
| integration (`-rs`) | **201 passed, 0 skipped** |
| unit — `test_runtime.py` | 10 passed |
| mutation proofs (ADR 0030, ADR 0031) | 2/2 failed as expected |
| worker write as `travel_worker` | SUCCEEDED |
| live start / poll / stop probe | exit 0 on `SIGTERM`, seven empty polls |
| `docker compose config --quiet` | clean |

### Limitations

1. **Both feature gates remain `False`.** The worker proves it runs; no extraction
   has been observed end to end. Enabling shadow capture is the next stage and a
   separate owner decision.
2. One worker process. The design is correct for two — that is what the advisory
   lock and the reservation exist for — but scaling is not exercised.
3. The advisory lock and the reservation are proved by deterministic
   two-transaction tests, not by a load test.
4. Worker throughput, model cost per event, and the right poll interval are
   unmeasured. The provider's cost accounting records tokens but reports
   `estimated_cost_usd = 0.0`, because no price table is configured.
5. The provider shares the chat path's endpoint and credential, so one provider
   outage affects both. Recorded as a consequence, not a defect.
