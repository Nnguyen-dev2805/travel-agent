# Worker Authority: Credential, Lease Time, and Fence Semantics Implementation Plan

> **For agentic workers:** Execute this plan task by task. Preserve checkbox state as
> you go: tick `- [x] **Step N**` → `- [x] **Step N**` in the same edit that records
> the evidence. Do not batch ticks. Do not tick a step whose evidence does not exist.

**Goal:** Close the three "borrowed authority" defects in the Memory worker's claim
path — the worker holding the API's credential, a lease judged by a caller-supplied
timestamp, and a lost lease cancelling another turn's work — without a schema change.

**Architecture:** Three separable commitments, recorded as ADR 0032, ADR 0033 and
ADR 0034. The database clock becomes the sole authority for lease validity and a
lease is held by a process identity; a fenced write carries a typed reason and the
worker stops without cancelling anything; each process receives only the credential
its role requires, enforced by an allow-list plus a startup assertion.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.x + psycopg 3, PostgreSQL 16,
Alembic (no migration in this change), pytest, Docker Compose v2, React 18 + Vite
(frontend untouched).

**Spec:** [Worker Authority: Credential, Lease Time, and Fence Semantics](../specs/2026-09-12-worker-authority-credential-lease-fence-design.md)

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-09-12 |
| Approved specification | [Worker Authority: Credential, Lease Time, and Fence Semantics](../specs/2026-09-12-worker-authority-credential-lease-fence-design.md) v0.1 (Approved) |
| Execution owner | Agent, on the repository owner's instruction |
| Decision owner | Repository owner |
| Scope | `backend/app/config.py`, `backend/app/main.py`, `backend/memory/write_pipeline/{outbox,postgres,uow,worker,runtime}.py`, `backend/conversations/postgres_repository.py`, `docker-compose.yml`, and the tests that pin them |
| Verification | `PYTHONPATH=. .venv/bin/pytest backend/tests/unit backend/tests/boundaries`; `PYTHONPATH=. .venv/bin/pytest backend/tests/integration -m integration` against the live PostgreSQL on `localhost:5433`; `docker compose config`; `python -m compileall`; `cd frontend && npm test`; the two mutation proofs in Task 3 and Task 7 |

## Global Constraints

1. **Governance gate.** The specification is Approved and the owner instructed
   implementation. This plan authorizes implementation of the seven tasks below and
   nothing else. The work stops and returns to the owner if scope expands, an
   assumption fails, or a required verification cannot run.
2. **No schema change.** No Alembic revision is created and `ALEMBIC_HEAD` stays
   `20260911_06`. A change that needs a migration is out of scope.
3. **Dirty tree.** The working tree carries unrelated modifications from earlier
   approved work. Read a file before editing it, work with the relevant edits, and do
   not revert or reformat anything outside this plan's File Responsibility Map.
4. **Git delivery is not authorized.** Do not stage, commit, push, branch, or open a
   PR. The owner decides when that happens.
5. **Secrets.** Never print, log, or commit a credential value. The isolation guard
   names environment *keys* only. Do not echo `.env` contents; `cut -d= -f1 .env`
   lists keys and is the only permitted read.
6. **Do not weaken an existing guard to make a test pass.** If a test fails because a
   guard fired, the test's premise is wrong, not the guard.
7. **Test-first.** Each task writes its failing test, runs it to confirm it fails for
   the intended reason, then implements, then re-runs. A test that passes before the
   implementation is not load-bearing and must be strengthened or removed.
8. **`PYTHONPATH=.` is mandatory** for every pytest invocation in this repository.

## Required ADR — prerequisite

| ADR | Title | Status required |
| --- | --- | --- |
| [0032](../adr/0032-lease-validity-is-database-time.md) | An Outbox Lease Is Judged Valid Against Database Time, and Held by a Process Identity | **Accepted** |
| [0033](../adr/0033-a-fenced-worker-stops-without-cancelling.md) | A Fenced Worker Stops Without Cancelling the Conversation's Other Events | **Accepted** |
| [0034](../adr/0034-per-process-credential-isolation.md) | Each Process Receives Only the Credential Its Role Requires | **Accepted** |

All three are Accepted, recorded in the specification's Approval Record.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/app/config.py` | Add `CredentialIsolationError` and `assert_credential_isolation(role, environ=None)`; derive `WORKER_ID` from the process when unset | — |
| `backend/app/main.py` | Call `assert_credential_isolation("api")` at the start of the lifespan, before the container starts | Task 1 |
| `backend/memory/write_pipeline/runtime.py` | Call `assert_credential_isolation("worker")` in `main()` before `build_worker` | Task 1 |
| `docker-compose.yml` | Replace `env_file` on both services with per-service `environment:` allow-lists | Task 1 (guard must exist first) |
| `backend/memory/write_pipeline/outbox.py` | `PostgresOutboxRepository` derives and compares every lease timestamp from `now()`; drop the `now` parameter from `claim_event`, `claim_batch`, `mark_succeeded`, `mark_failed` | — |
| `backend/conversations/postgres_repository.py` | `check_conversation_fence` and `check_outbox_lease` return `FenceReason`; the lease window is compared against `now()` | Task 6 |
| `backend/memory/write_pipeline/postgres.py` | `_check_fence` raises `FencedWriteError(reason)`; drop its `now` parameter | Tasks 4, 6 |
| `backend/memory/write_pipeline/uow.py` | Add `FenceReason`; `FencedWriteError` carries a required `reason` | — |
| `backend/memory/write_pipeline/worker.py` | Drop `now` from repository calls; the fence handler stops without cancelling; the revalidation path applies the reason rule | Tasks 3, 6, 7 |
| `backend/tests/unit/memory_write_pipeline/*` | Unit coverage for the guard, the fence vocabulary, and the cancellation rule | — |
| `backend/tests/integration/*` | Drop the removed `now` argument; pin the two mutation proofs | — |

## Task 1: Credential isolation guard

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/tests/unit/test_credential_isolation.py`

**Interfaces:**
- Produces: `CredentialIsolationError(RuntimeError)`; `assert_credential_isolation(role: str, environ: Mapping[str, str] | None = None) -> None` raising when the other role's database key is present, and `ValueError` for an unknown role.

- [x] **Step 1: Write the failing tests.** Cover: the worker role rejects `DATABASE_URL`; the API role rejects `WORKER_DATABASE_URL`; each role accepts an environment with only its own key; an unrelated key is accepted; an unknown role raises `ValueError`; the error message names the offending key and contains no value from the environment.

- [x] **Step 2: Run verification.** `PYTHONPATH=. .venv/bin/pytest backend/tests/unit/test_credential_isolation.py -q` → expected **FAIL** (`ImportError: cannot import name 'assert_credential_isolation'`).

- [x] **Step 3: Implement.** Add the exception, a private `_ROLE_DATABASE_KEYS` map of `role -> (own_key, forbidden_key)`, and the guard. It must not read `Settings`, so it is callable before settings resolve and testable with a plain mapping.

- [x] **Step 4: Run verification.** Same command → expected **PASS**.

- [x] **Step 5: Review checkpoint.** Confirm no other module imports the guard yet, so this task cannot change runtime behaviour on its own.

## Task 2: Per-service credential allow-lists

**Files:**
- Modify: `docker-compose.yml`, `backend/app/main.py`, `backend/memory/write_pipeline/runtime.py`
- Modify: `backend/tests/unit/test_credential_isolation.py` (entry-point wiring)

**Interfaces:**
- Consumes: `assert_credential_isolation` (Task 1).
- Produces: a `worker` service whose environment is an explicit allow-list with no `env_file`, and a `backend` service likewise; both processes assert isolation at startup.

- [x] **Step 1: Write the failing tests.** Assert that `backend/app/main.py`'s lifespan and `runtime.main` each call the guard, and assert the guard runs *before* the container is constructed — the failure must precede any connection attempt. Use the existing import-introspection pattern in `backend/tests/unit/test_runtime_container.py` if it fits, otherwise a source-level assertion with an explicit rationale.

- [x] **Step 2: Run verification.** `PYTHONPATH=. .venv/bin/pytest backend/tests/unit/test_credential_isolation.py -q` → expected **FAIL**.

- [x] **Step 3: Implement the wiring.** `assert_credential_isolation("api")` as the first statement of the lifespan; `assert_credential_isolation("worker")` as the first statement of `main()`. Neither goes into `RuntimeContainer.__init__`, `build_worker`, or the request dependency.

- [x] **Step 4: Implement the Compose allow-lists.** Remove `env_file` from both services. Give each an explicit `environment:` list:
  - `backend`: `DATABASE_URL` (already present, keep its comment), `GITHUB_MODELS_URL`, `GITHUB_TOKEN`, `LLM_MODEL`, `LOCAL_AUTH_TOKENS_JSON`, `MEMORY_WRITE_PIPELINE_ENABLED`, `MEMORY_SHADOW_EXTRACT_ENABLED`.
  - `worker`: `WORKER_DATABASE_URL` (already present, keep its comment), `GITHUB_MODELS_URL`, `GITHUB_TOKEN`, `LLM_MODEL`, `MEMORY_WRITE_PIPELINE_ENABLED`, `MEMORY_SHADOW_EXTRACT_ENABLED`.
  - `LOCAL_AUTH_TOKENS_JSON` must use the `${LOCAL_AUTH_TOKENS_JSON:-{}}` form. Verified empirically: that form yields `{}` when unset, whereas `${LOCAL_AUTH_TOKENS_JSON}` yields an empty string, which `Settings` would pass to `SecretStr` as `""` and which fails JSON parsing — a change from today's absent-value default of `"{}"`.
  - `GITHUB_TOKEN` may use `${GITHUB_TOKEN:-}`: `Settings.GITHUB_TOKEN` defaults to `""`, so absent and empty are already identical.
  - Do **not** add `WORKER_ID` to either list. An empty value would defeat the Task 5 derivation.

- [x] **Step 5: Run verification.** `docker compose config` → expected **exit 0**, and the rendered `worker` environment must contain `WORKER_DATABASE_URL` and **not** `DATABASE_URL`; the rendered `backend` environment must contain `DATABASE_URL` and **not** `WORKER_DATABASE_URL`. Record both lists in the Completion Record as the boundary evidence.

- [x] **Step 6: Review checkpoint.** Confirm `.env` was not modified and no credential value appears in any file this task touched.

## Task 3: Database-time lease window in the outbox repository

**Files:**
- Modify: `backend/memory/write_pipeline/outbox.py`
- Modify: `backend/tests/integration/test_outbox_turn_readiness.py`, `backend/tests/integration/test_memory_write_runtime.py`

**Interfaces:**
- Produces: `PostgresOutboxRepository.claim_event(outbox_id, lease_owner, lease_duration_seconds)`, `claim_batch(lease_owner, lease_duration_seconds, limit=10, debounce_seconds=0.0)`, `mark_succeeded(outbox_id, lease_owner)`, `mark_failed(outbox_id, lease_owner, error_message, retryable, max_attempts=3, backoff_seconds=10.0)` — the `now` parameter is gone from all four.
- `InMemoryOutboxRepository` keeps its `now` parameter and its injectable clock.

- [x] **Step 1: Write the failing tests.** In `backend/tests/integration/`, add tests that a lease written by `claim_batch` is judged by database time: (a) claim with a lease duration of `0`, then confirm the event is immediately reclaimable; (b) claim with `30`, then confirm `mark_succeeded` from the same owner succeeds and from a different owner fails; (c) an expired lease is produced by an explicit `UPDATE conversation_outbox SET lease_until = now() - interval '5 minutes'`, then confirm `mark_failed` refuses it and `claim_batch` reclaims it. Assert the *reason* for each outcome, not only the boolean.

- [x] **Step 2: Run verification.** `PYTHONPATH=. .venv/bin/pytest backend/tests/integration -m integration -q -k "lease"` → expected **FAIL** (`TypeError: claim_batch() got an unexpected keyword argument 'now'` or the assertion).

- [x] **Step 3: Implement.** Replace every application timestamp with the database clock: `lease_until` written as `now() + make_interval(secs => :lease_seconds)` via a `text()` expression with bound parameters (SQLAlchemy's `func.make_interval(secs=…)` renders `=` notation, which PostgreSQL rejects; verify the rendered SQL rather than assuming); comparisons against `func.now()`; `next_attempt_after` and `updated_at` likewise. In `mark_failed`, compute lease validity in the statement — select the holder's lease as still-valid alongside the row — instead of comparing a fetched value in Python. Remove `now` from the four signatures and from `OutboxRepository`'s protocol entries for them.

- [x] **Step 4: Update the callers and tests.** Drop the `now=` argument in `worker.py` and in the two integration modules. Where a test previously used a fabricated timestamp to mean "expired", use the explicit `UPDATE` idiom that `test_outbox_turn_readiness.py:353-364` already uses.

- [x] **Step 5: Run verification.** `PYTHONPATH=. .venv/bin/pytest backend/tests/unit/memory_write_pipeline backend/tests/integration -m integration -q` → expected **PASS**, zero skips.

- [x] **Step 6: Mutation proof.** Confirm the fix is load-bearing: temporarily restore a Python-side comparison against a stale captured timestamp and confirm the new expiry test fails. Revert the mutation and re-run to **PASS**. Record both outputs.

- [x] **Step 7: Review checkpoint.** Confirm `InMemoryOutboxRepository` still models lease expiry with its own clock and that no unit test regressed.

## Task 4: Database-time lease window in the fence

**Files:**
- Modify: `backend/conversations/postgres_repository.py`, `backend/memory/write_pipeline/postgres.py`
- Modify: `backend/tests/integration/*` (fence coverage)

**Interfaces:**
- Consumes: Task 3's convention.
- Produces: `check_outbox_lease(connection, outbox_id, lease_owner)` — no `now`; `_check_fence(connection, fence, owner)` — no `now`.

- [x] **Step 1: Write the failing test.** A fence evaluated inside a write transaction against an expired lease must be refused, and the lease must be expired by database time — not by a parameter the caller chose. Assert that passing a "helpful" future timestamp is no longer possible, because the parameter is gone.

- [x] **Step 2: Run verification.** `PYTHONPATH=. .venv/bin/pytest backend/tests/integration -m integration -q -k "fence"` → expected **FAIL**.

- [x] **Step 3: Implement.** Compare the window with `now()` in the statement that reads the row. Remove `now` from `check_outbox_lease` and from `_check_fence`, and from `_check_fence`'s call site at `postgres.py:359`.

- [x] **Step 4: Run verification.** Same command → expected **PASS**.

- [x] **Step 5: Review checkpoint.** Confirm the fence still holds the row `FOR UPDATE`, so the check and the write remain in one transaction.

## Task 5: Process-unique worker identity

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/tests/unit/test_worker_identity.py`

**Interfaces:**
- Produces: `Settings.WORKER_ID` derived from `f"{socket.gethostname()}-{os.getpid()}"` when the environment value is unset **or blank**.

- [x] **Step 1: Write the failing tests.** Assert the derived value is not the old constant `"memory_worker_1"`, that it contains the hostname and the pid, that an explicit `WORKER_ID` is honoured verbatim, and that a blank `WORKER_ID` falls back to the derived value rather than yielding `""`.

- [x] **Step 2: Run verification.** `PYTHONPATH=. .venv/bin/pytest backend/tests/unit/test_worker_identity.py -q` → expected **FAIL**.

- [x] **Step 3: Implement.** `WORKER_ID: str = (os.getenv("WORKER_ID") or "").strip() or f"{socket.gethostname()}-{os.getpid()}"`, with a comment stating why a constant is wrong: `holder == lease_owner` is the only thing distinguishing two replicas, and `cancel_events(lease_owner=…)` is scoped by it.

- [x] **Step 4: Run verification.** Same command → expected **PASS**, then the full unit suite.

- [x] **Step 5: Review checkpoint.** Confirm no production code depends on the literal `"memory_worker_1"`, and confirm no test asserts it.

## Task 6: Fence reason vocabulary

**Files:**
- Modify: `backend/memory/write_pipeline/uow.py`, `backend/conversations/postgres_repository.py`, `backend/memory/write_pipeline/postgres.py`
- Modify: `backend/tests/unit/memory_write_pipeline/test_worker.py:825`

**Interfaces:**
- Produces: `FenceReason` with members `CONVERSATION_GONE`, `CONVERSATION_NOT_ACTIVE`, `DELETION_EPOCH_MOVED`, `OUTBOX_EVENT_GONE`, `LEASE_LOST`, `LEASE_EXPIRED`, and a `cancels_conversation_work` property; `FencedWriteError(reason: FenceReason, message: str | None = None)` with a required `reason` attribute; `check_conversation_fence` and `check_outbox_lease` return `(bool, FenceReason | None)`.

- [x] **Step 1: Write the failing tests.** Assert each of the six causes maps to its own member, that `LEASE_LOST` and `LEASE_EXPIRED` report `cancels_conversation_work is False`, that the three conversation-shaped reasons and `OUTBOX_EVENT_GONE` do not, and that `FencedWriteError` exposes `.reason` and still renders a human-readable message.

- [x] **Step 2: Run verification.** `PYTHONPATH=. .venv/bin/pytest backend/tests/unit/memory_write_pipeline -q` → expected **FAIL**.

- [x] **Step 3: Implement.** Add the enum and the partition; change both check functions to return the enum; have `_check_fence` raise `FencedWriteError(reason)`. Keep the existing sentences as the messages, derived from the enum so logging stays readable.

- [x] **Step 4: Update the existing raiser.** `backend/tests/unit/memory_write_pipeline/test_worker.py:825` raises `FencedWriteError("The source conversation is no longer active.")`; it must now raise with `FenceReason.CONVERSATION_NOT_ACTIVE`.

- [x] **Step 5: Run verification.** Same command → expected **PASS**.

- [x] **Step 6: Review checkpoint.** Confirm no call site branches on a message string any more, and that `reason` is required rather than optional.

## Task 7: The fence handler stops; the revalidation path applies the rule

**Files:**
- Modify: `backend/memory/write_pipeline/worker.py`
- Modify: `backend/tests/unit/memory_write_pipeline/test_worker.py`

**Interfaces:**
- Consumes: `FenceReason` and its predicate (Task 6).
- Produces: a fence handler that cancels nothing; a private cancellation helper the revalidation path uses, so the "cancel only for conversation-shaped reasons" rule is expressed once.

- [x] **Step 1: Write the failing tests.** The load-bearing one is parametrized over **all six** `FenceReason` members: after a fence, the worker must have issued **zero** `cancel_events` calls and left every `PENDING` event of the conversation `PENDING`. Add the direct regression: a conversation with a `PENDING` turn-2 event and a `LEASED` turn-1 event whose lease is lost must end with turn 2 still `PENDING`. Also assert the revalidation path still cancels for each conversation-shaped reason.

- [x] **Step 2: Run verification.** `PYTHONPATH=. .venv/bin/pytest backend/tests/unit/memory_write_pipeline/test_worker.py -q` → expected **FAIL**, showing the peer's lease and the `PENDING` events being cancelled.

- [x] **Step 3: Implement.** Delete the `cancel_events` call from the `FencedWriteError` handler at `worker.py:497-510` and replace it with a log line carrying `fence_error.reason`. Route the three revalidation-site cancels (`:239`, `:256`, `:273`) through one helper that returns early unless `reason.cancels_conversation_work`, and writes `reason.value` as `last_error`.

- [x] **Step 4: Run verification.** Same command → expected **PASS**, plus the full unit suite.

- [x] **Step 5: Mutation proof.** Re-add a single unconditional `cancel_events` call in the fence handler and confirm the parametrized test fails. Revert and re-run to **PASS**. Record both outputs. This is the evidence that the regression test is load-bearing rather than decorative.

- [x] **Step 6: Review checkpoint.** Confirm the revalidation path's behaviour is unchanged in effect, and that no cancellation remains in any fence path.

## Package Verification

Run on the exact final worktree state, in this order:

1. `PYTHONPATH=. .venv/bin/pytest backend/tests/unit backend/tests/boundaries -q` — expected: all pass, zero failures.
2. `PYTHONPATH=. .venv/bin/pytest backend/tests/integration -m integration -q` against the live PostgreSQL on `localhost:5433` — expected: all pass, **zero skips**.
3. `python -m compileall backend` — expected: exit 0.
4. `docker compose config` — expected: exit 0, with the rendered `worker` environment containing no `DATABASE_URL` and the rendered `backend` environment containing no `WORKER_DATABASE_URL`.
5. `cd frontend && npm test` — expected: all pass. The frontend is untouched; this confirms the change did not reach it.
6. `git diff --check` — expected: no whitespace errors.
7. `git status --short --untracked-files=all` — compare the change set against the File Responsibility Map. `git diff` alone does not show untracked files.
8. The two mutation proofs from Task 3 Step 6 and Task 7 Step 5.

## Rollback

1. **Task 2 (Compose).** Restore `env_file` on both services. The guard in Task 1 is a no-op on a correct environment, so it can stay; leaving it while restoring `env_file` reintroduces the `DATABASE_URL` leak and the worker will refuse to start, which is the intended fail-closed behaviour. Restore both together or neither.
2. **Task 3 and Task 4 (lease time).** Restore the `now` parameters and the Python-side comparisons. No data changes, so a revert is complete; any lease written by the new code carries an ordinary timestamp either way.
3. **Task 5 (identity).** Restore the constant default. Leases held under a derived identity become orphaned and expire normally.
4. **Task 6 and Task 7 (fence).** Restore the previous handler only if the parametrized regression test is removed in the same change — reverting the handler while keeping the test leaves a red suite, which is the correct signal.
5. No migration, so there is nothing to downgrade.

## Completion Record

| Field | Value |
| --- | --- |
| Status | Completed |
| Completed | 2026-09-12 |
| Executed by | Agent, on the repository owner's instruction |
| Reviewed by | Repository owner (pending) |
| Change set | 31 files: 20 under `backend/` (8 source, 12 test), `docker-compose.yml`, and 10 governance/runbook documents. Enumerated by modification time, because the working tree also carries earlier sessions' uncommitted work and `git diff` cannot separate the two. |
| Verification | Unit **891 passed**; boundaries **16 passed**; integration **215 passed, 0 skipped, 0 errors**; `compileall` exit 0; `docker compose config` exit 0 with the boundary asserted; `git diff --check` clean; **six** mutation proofs, all load-bearing. The frontend suite **could not run** — see below. |

### Per-task evidence

| Task | Evidence |
| --- | --- |
| 1 — Credential isolation guard | `backend/tests/unit/test_credential_isolation.py`: 17 passed. The guard names the offending key and never a value. The wrong-key case is caught by tokenising the message rather than substring-matching it, because `WORKER_DATABASE_URL` contains `DATABASE_URL`. |
| 2 — Per-service allow-lists | `docker compose config` exit 0, no warnings. Rendered worker environment: `WORKER_DATABASE_URL`, `GITHUB_*`, `LLM_MODEL`, both gates — **no `DATABASE_URL`, no `LOCAL_AUTH_TOKENS_JSON`**. Rendered API environment: `DATABASE_URL`, `GITHUB_*`, `LLM_MODEL`, `LOCAL_AUTH_TOKENS_JSON`, both gates — **no `WORKER_DATABASE_URL`**. The guard is wired into the lifespan and `runtime.main`, and both entry-point tests observe that no connection is attempted first. |
| 3 — Database-time lease window | `backend/tests/integration/test_outbox_lease_authority.py`: 14 passed. `func.now()` appears 15 times in `PostgresOutboxRepository`; no Python-computed lease window remains. The interval expression is proved against the database rather than assumed: `test_the_lease_window_is_the_requested_duration` reads the window back as ~30s from `now()`. |
| 4 — Fence lease window | 4 fence tests in the same file. `check_outbox_lease` and `_check_fence` no longer accept `now`, asserted by signature. |
| 5 — Process-unique worker identity | `backend/tests/unit/test_worker_identity.py`: 10 passed, each settings case spawning a fresh interpreter, because `Settings` captures `os.getenv` at import. Final review found the constant in a **second** place — `MemoryOutboxWorker.__init__` still defaulted `worker_id="memory_worker_1"`, a live default a caller could take by accident, reintroducing the collision this ADR removes. All three construction sites already passed it explicitly, so the parameter is now **required**. One test asserts it has no default; another walks the AST of every non-test `backend/*.py` for the literal as live code, because a grep cannot distinguish a string literal from a docstring or a comment — and a comment describing the old default is exactly what should remain. |
| 6 — Fence reason vocabulary | `backend/tests/unit/memory_write_pipeline/test_fence_reason.py`: 13 passed, including that the partition of the six reasons is total. |
| 7 — Fence stops; revalidation applies the rule | 7 fence tests in `test_worker.py`, parametrized over all six `FenceReason` members, asserting zero `cancel_events` calls and that a later turn's `PENDING` event survives. |

### Mutation proofs

A control that passes with and without the change is decoration. Each mutation was
applied, run, reverted, and re-run green.

| Control removed | Result |
| --- | --- |
| `env_file` re-added to the worker and `DATABASE_URL` listed on it | 2 failed → load-bearing |
| Lease window widened in `mark_succeeded` and skipped in `mark_failed` | 2 failed → load-bearing |
| Window check dropped from `check_outbox_lease` | 1 failed → load-bearing |
| `WORKER_ID` restored to the constant `"memory_worker_1"` | 6 failed → load-bearing |
| Unconditional `cancel_events` re-added to the fence handler | 7 failed → load-bearing |
| `worker_id` default restored to the constant on `MemoryOutboxWorker.__init__` | 2 failed → load-bearing |

`docker-compose.yml` and `backend/memory/write_pipeline/outbox.py` were verified
byte-identical after restore (`docker-compose.yml` sha256 prefix `bac8eec371b131de`),
and every mutated file was checked for residue afterwards: no widened window, no
skipped check, no stray `sqlalchemy as sa` import, and the old constant present only
inside comments.

### What could not be verified

1. **The frontend suite did not run.** `npx vitest run` and `npm test` each exited
   `137` (SIGKILL) across five attempts, including
   `--pool=forks --poolOptions.forks.singleFork=true`. This is host memory pressure,
   not the change: no frontend file is in the change set, and nothing this plan
   modified reaches the frontend. It is the plan's one unexecuted check.
2. **The clock authority is proved structurally, not behaviourally.**
   `test_the_fence_judges_the_lease_window_against_database_time` **passed before the
   fix as well**, because on one host the application clock and the database clock
   agree and no behavioural test can separate them. What proves the authority is
   `test_the_fence_does_not_accept_a_caller_supplied_time` — the parameter is gone —
   together with the mutation proof that the window check is load-bearing. A skewed
   host would be needed to show the divergence end to end; none is available here.
   This is recorded rather than glossed, because the behavioural test looks like
   proof and is not.
3. **A transient full-suite failure was disproven, not ignored.** One integration run
   reported `209 passed, 6 errors` in `test_ops_readiness_api.py`,
   `test_rag_evaluation_flow.py` and `test_vector_store.py`. The two RAG/Chroma files
   exit `137` in isolation and import **none** of the modules this change touched; the
   readiness file passes in isolation (5 passed). A re-run on a fresh `--basetemp`
   gave **215 passed, 0 errors**.

### Deviations from the approved plan

1. **`InMemoryOutboxRepository`'s `now` became optional rather than removed.** The
   plan removed `now` from the `OutboxRepository` protocol; the double implements
   that protocol and its parameter was *required*, so the worker's new call shape
   raised `TypeError` in 15 tests. The clock stays injectable — it is what makes lease
   and back-off tests deterministic — and is now optional. The class docstring gained
   a second disclosed divergence: it judges the window from a local clock, which the
   real repository never does.
2. **The worker keeps one local clock read**, at the lease-*renewal* decision, plus a
   pre-persistence early-out. Neither can extend a lease: the window is only ever
   written from `now()`, and the fence re-checks it inside the write transaction. Both
   sites are annotated as such rather than left to be rediscovered.
3. **`cancel_events` keeps its `now` parameter.** The specification scoped it out, and
   its only use is an audit `updated_at`, not a lease decision.
4. **`_require_fence_reason` was added**, which the plan did not name. A `check_*`
   returning `False` without a reason would otherwise have defaulted to a plausible
   one and silently misclassified the fence — the direction that destroys valid memory
   formation. It raises instead.
5. **A `FenceReason` import now crosses from `conversations/` into the memory
   pipeline.** The specification's Components and Dependency Direction section allows
   this direction; the import was verified cycle-free by importing every dependent
   module.
6. **Runbook notes were added** to `docs/runbooks/deployment.md` and
   `docs/runbooks/local-development.md`, honouring the specification's Observability
   and Operations commitment, which the plan's File Responsibility Map did not list.

**Review gate.** The repository owner reviews this change set. Nothing is staged,
committed, pushed, or released, and neither Memory feature gate was enabled.
