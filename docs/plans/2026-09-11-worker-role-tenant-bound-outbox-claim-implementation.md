# Worker Role and Tenant-Bound Outbox Claim — Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence. Each task ends with a review checkpoint; do not begin
> the next task until the checkpoint condition holds.

**Goal:** Give the background Memory worker a least-privilege role that can claim
a cross-owner outbox queue under row-level security, bind a tenant for everything
it reads afterwards, and let the runtime role observe the queue without gaining
row access.

**Architecture:** A new `travel_worker` role (`NOSUPERUSER NOBYPASSRLS`, owning
nothing) receives enumerated grants and two permissive policies on
`conversation_outbox` alone. `conversations`, `messages`, and the Memory tables
keep their existing policies and stay reachable only under a bound tenant, which
the worker binds from the claimed row's `owner_user_id`. The runtime role's queue
visibility is a single parameterless `SECURITY DEFINER` function returning
`bigint`.

**Tech Stack:** Python 3.13, SQLAlchemy Core, Alembic, PostgreSQL 16, pytest.

**Spec:** [Worker Role and Tenant-Bound Outbox Claim](../specs/2026-09-11-worker-role-tenant-bound-outbox-claim-design.md) v0.1

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-09-11 |
| Approved specification | [Worker Role and Tenant-Bound Outbox Claim](../specs/2026-09-11-worker-role-tenant-bound-outbox-claim-design.md) v0.1, approved 2026-09-11 |
| Required ADR | ADR 0028 — Accepted 2026-09-11 |
| Execution owner | Agent, under repository-owner instruction |
| Decision owner | Repository owner |
| Scope | Worker role, claim policies, enumerated grants, bounded readiness count, worker DSN contract, and the tests that prove the claim boundary |
| Verification | Migration round-trip; focused integration and unit suites; full backend suite; frontend suite |

## Global Constraints

1. Every persistent repository change requires a written specification and an
   approved implementation plan (`AGENTS.md`). **Do not execute this plan until
   the specification is approved and ADR 0028 is accepted.** Level 3 requires
   both.
2. The repository owner creates or selects branches and decides when to stage,
   commit in the primary working tree, push, open a PR, merge, and release. No
   Git delivery is authorized by this plan.
3. The working tree is dirty and large. Read a dirty file before touching it and
   work with the existing edits rather than reverting them.
4. **Do not enable either memory feature gate.** `MEMORY_WRITE_PIPELINE_ENABLED`
   and `MEMORY_SHADOW_EXTRACT_ENABLED` stay `False`. Do not add a worker service
   to `docker-compose.yml` and do not instantiate a worker in `RuntimeContainer`.
5. **Never grant `BYPASSRLS` or `SUPERUSER` to any runtime or worker role.**
   ADR 0028 rejects it explicitly.
6. **Grants are enumerated per table.** No `GRANT ... ON ALL TABLES`, and no
   `ALTER DEFAULT PRIVILEGES` entry for `travel_worker`. A future table must be
   exposed deliberately, not silently.
7. **No new policy on `conversations`, `messages`, or any Memory table.** Those
   stay behind a bound tenant.
8. **Do not change the outbox status vocabulary or the ADR 0027 gate.** The
   release fact stays a separate column, and `released_at IS NOT NULL` remains a
   precondition of every claim branch.
9. **Do not grant `travel_worker` any privilege on `alembic_version`.** It does
   not check the migration head.
10. The migration is applied before the code that reads the new objects. The
    reverse order fails loudly on a missing object; that is acceptable and must
    be stated in the Completion Record.
11. Behaviour changes use a red-green-refactor cycle. Each task states the
    failing test first.
12. Never expose secrets, credentials, tokens, or sensitive personal data in
    code, logs, commands, evidence, or documentation.
13. `pytest backend/tests/unit backend/tests/boundaries` cannot be run as one
    command in this environment. Run directories separately. Always pass
    `--basetemp=.workbuddy-ai/tmp/pytest*`. Never run the backend and frontend
    suites concurrently. Integration requires `PG_TEST_DSN` and
    `PG_RUNTIME_TEST_DSN`.

## Required ADR — prerequisite

| ADR | Title | Status required |
| --- | --- | --- |
| [ADR 0028](../adr/0028-worker-role-and-outbox-claim-boundary.md) | The Background Worker Claims Through a Role-Scoped Policy, and Binds a Tenant After the Claim | **Accepted** before Task 1 |

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/storage/migrations/versions/20260911_04_worker_role_and_claim_policy.py` | Create `travel_worker`, the two claim policies, the enumerated grants, and the bounded counting function | Task 1 |
| `backend/storage/postgres.py` | Advance `ALEMBIC_HEAD` to the new revision | Task 1 |
| `docker/postgres/init-app-role.sh` | Grant `LOGIN` and the credential for `travel_worker` on first bootstrap | Task 1 |
| `backend/app/config.py` | `PG_WORKER_USER`, `PG_WORKER_PASSWORD`, `worker_dsn()`, and the fail-closed role guard | Task 2 |
| `backend/app/runtime_container.py` | `count_ready_outbox_events()` reads the bounded function instead of the table | Task 3 |
| `backend/tests/integration/test_outbox_turn_readiness.py` | Replace the defect characterisation with real-role behaviour tests | Task 4 |
| `backend/tests/integration/test_postgres_migrations.py` | Role flags, policy existence, grant narrowness, downgrade | Task 5 |
| `backend/tests/unit/test_config.py` | Worker DSN resolution and the role guard | Task 2 |

---

## Task 1: Worker Role, Claim Policies, Enumerated Grants, and the Counting Function

**Files:**
- Create: `backend/storage/migrations/versions/20260911_04_worker_role_and_claim_policy.py`
- Modify: `backend/storage/postgres.py` (`ALEMBIC_HEAD`)
- Modify: `docker/postgres/init-app-role.sh`
- Test: `backend/tests/integration/test_postgres_migrations.py`

**Interfaces:**
- Consumes: revision `20260911_03`
- Produces: role `travel_worker`; policies `worker_outbox_claim` and
  `worker_outbox_lease` on `conversation_outbox`; function
  `ready_outbox_event_count() RETURNS bigint`

- [x] **Step 1: Write the failing migration tests**

Add tests asserting, after `upgrade head`:

```text
- role travel_worker exists with rolsuper = false and rolbypassrls = false
- pg_policies has worker_outbox_claim and worker_outbox_lease on conversation_outbox
- information_schema.role_table_grants for travel_worker lists exactly
  SELECT, UPDATE on conversation_outbox and SELECT on conversations, messages
- travel_worker has no privilege on alembic_version
- ready_outbox_event_count() exists, returns bigint, has no parameters,
  and is SECURITY DEFINER
- downgrade removes both policies and the function and leaves the role
```

- [x] **Step 2: Run verification — expect FAIL**

```bash
PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… \
  .venv/bin/python -m pytest backend/tests/integration/test_postgres_migrations.py \
  -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-m1
```

Expected: the new tests fail because the revision does not exist.

- [x] **Step 3: Implement the migration**

`upgrade()`:

```text
1. CREATE ROLE travel_worker NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
   NOREPLICATION NOLOGIN, guarded by IF NOT EXISTS.
2. ALTER ROLE travel_worker NOSUPERUSER NOBYPASSRLS, so a pre-existing role
   keeps no bypass whatever created it.
3. GRANT USAGE ON SCHEMA public TO travel_worker.
4. GRANT SELECT, UPDATE ON conversation_outbox TO travel_worker.
5. GRANT SELECT ON conversations, messages TO travel_worker.
6. CREATE POLICY worker_outbox_claim ON conversation_outbox
     FOR SELECT TO travel_worker USING (true);
   CREATE POLICY worker_outbox_lease ON conversation_outbox
     FOR UPDATE TO travel_worker USING (true) WITH CHECK (true);
7. CREATE FUNCTION ready_outbox_event_count() RETURNS bigint
     LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
       SELECT count(*) FROM conversation_outbox
       WHERE status = 'pending' AND released_at IS NOT NULL
     $$;
   REVOKE ALL ON FUNCTION ready_outbox_event_count() FROM PUBLIC;
   GRANT EXECUTE ON FUNCTION ready_outbox_event_count() TO travel_app;
```

Guard every object against an existing definition, matching the idempotence
discipline of `20260910_04`. Do **not** add an `ALTER DEFAULT PRIVILEGES` entry.

`downgrade()`: drop both policies, drop the function, revoke the enumerated
grants and `USAGE ON SCHEMA public`, and leave the role lifecycle to operations.

- [x] **Step 4: Advance `ALEMBIC_HEAD`**

Set `ALEMBIC_HEAD = "20260911_04"` in `backend/storage/postgres.py`.

- [x] **Step 5: Extend the bootstrap script**

In `docker/postgres/init-app-role.sh`, add `travel_worker` with `LOGIN
NOSUPERUSER NOBYPASSRLS` and a `WORKER_DB_PASSWORD` credential, mirroring the
`travel_app` block. Keep the same "password assignment outside the DO body" rule.

- [x] **Step 6: Run verification — expect PASS**

Re-run the command from Step 2.

- [x] **Step 7: Review checkpoint**

Review: the revision is idempotent, the grants are enumerated, no default
privilege was added, and `ALEMBIC_HEAD` matches the revision.

---

## Task 2: Worker DSN Contract

**Files:**
- Modify: `backend/app/config.py`
- Test: `backend/tests/unit/test_config.py`

**Interfaces:**
- Consumes: the `travel_worker` role name from Task 1
- Produces: `Settings.worker_dsn() -> str`

- [x] **Step 1: Write the failing tests**

```text
- worker_dsn() resolves WORKER_DATABASE_URL when set
- worker_dsn() falls back to PG_WORKER_USER / PG_WORKER_PASSWORD / PG_HOST /
  PG_PORT / PG_DB, with PG_WORKER_USER defaulting to "travel_worker"
- worker_dsn() refuses a role that is superuser or BYPASSRLS unless
  ALLOW_PRIVILEGED_DB_ROLE is true
- the existing database_dsn() behaviour is unchanged
```

Write the guard test so it does not depend on `.env`: resolve the setting from an
explicit mapping, or run the check in a directory without a `.env` file.

- [x] **Step 2: Run verification — expect FAIL**

```bash
.venv/bin/python -m pytest backend/tests/unit/test_config.py \
  -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-m2
```

- [x] **Step 3: Implement**

Add `PG_WORKER_USER`, `PG_WORKER_PASSWORD`, and `WORKER_DATABASE_URL` to
`Settings`, and a `worker_dsn()` that reuses the same resolution order as
`database_dsn()`. Extend the existing fail-closed guard so both DSNs share it.

- [x] **Step 4: Run verification — expect PASS**

Re-run the command from Step 2.

- [x] **Step 5: Review checkpoint**

Review: the worker DSN cannot silently resolve to a privileged role, and the
runtime DSN contract is untouched.

---

## Task 3: Readiness Count Through the Bounded Function

**Files:**
- Modify: `backend/app/runtime_container.py`
- Test: `backend/tests/unit/test_observability_readiness.py`,
  `backend/tests/integration/test_postgres_migrations.py`

**Interfaces:**
- Consumes: `ready_outbox_event_count()` from Task 1
- Produces: `PostgresReadinessProbe.count_ready_outbox_events()` backed by the
  function

- [x] **Step 1: Write the failing tests**

```text
- the probe calls ready_outbox_event_count() rather than selecting the table
- a blocked event (released_at IS NULL) is not counted
- a ready event is counted
- a missing function makes the probe raise, so readiness reports not_ready
  rather than a constant zero
```

- [x] **Step 2: Run verification — expect FAIL**

```bash
.venv/bin/python -m pytest backend/tests/unit/test_observability_readiness.py \
  -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-m3
```

- [x] **Step 3: Implement**

Replace the inline `SELECT count(*)` with a call to
`ready_outbox_event_count()`, keeping the `statement_timeout` bound and the
"raise rather than return a constant" behaviour the docstring already promises.

- [x] **Step 4: Run verification — expect PASS**

Re-run the command from Step 2, then run the integration test that asserts the
count against real rows.

- [x] **Step 5: Review checkpoint**

Review: the probe cannot report a zero it cannot justify, and the count excludes
unreleased events.

---

## Task 4: Replace the Defect Characterisation With Real-Role Behaviour Tests

**Files:**
- Modify: `backend/tests/integration/test_outbox_turn_readiness.py`

**Interfaces:**
- Consumes: the worker role, the policies, and `Settings.worker_dsn()` from
  Tasks 1 and 2
- Produces: behaviour tests that prove the claim boundary

- [x] **Step 1: Write the failing tests**

```text
- travel_worker claims a ready event through claim_batch
- travel_worker claims a ready event through claim_event
- travel_app still claims nothing (fail-closed, asserted not tolerated)
- travel_worker cannot read another owner's transcript without binding a tenant
- travel_worker reads the claimed owner's transcript once the tenant is bound
- the ADR 0027 gate still blocks an unreleased event for travel_worker
```

- [x] **Step 2: Run verification — expect FAIL**

```bash
PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… \
  .venv/bin/python -m pytest backend/tests/integration/test_outbox_turn_readiness.py \
  -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-m4
```

Expected: the new worker tests fail until Tasks 1-3 land; the existing gate tests
keep passing.

- [x] **Step 3: Delete the characterisation test**

Remove `test_the_claim_path_is_not_tenant_scoped_today` and its module docstring
paragraph describing the claim path as not tenant-scoped. The defect it asserted
is now fixed, so keeping it would assert the wrong behaviour.

- [x] **Step 4: Implement the tests**

Add a worker engine fixture built from `Settings.worker_dsn()`. Claim with the
worker engine, then bind the tenant through the existing `tenant_transaction` and
read the transcript. Assert that the unbound read returns zero rows.

- [x] **Step 5: Run verification — expect PASS**

Re-run the command from Step 2.

- [x] **Step 6: Review checkpoint**

Review: no test asserts a defect; every claim-boundary assertion fails when the
corresponding policy or grant is removed.

---

## Task 5: Migration Contract Tests

**Files:**
- Modify: `backend/tests/integration/test_postgres_migrations.py`

**Interfaces:**
- Consumes: the revision from Task 1
- Produces: contract tests for the role, the policies, and the grant set

- [x] **Step 1: Write the failing tests**

```text
- upgrade/downgrade/re-upgrade round-trips without error
- travel_worker has no privilege on alembic_version
- travel_worker has no INSERT or DELETE on conversation_outbox
- travel_worker has no privilege on any memory_* table
- the tenant_isolation policy on conversation_outbox is unchanged
- no ALTER DEFAULT PRIVILEGES entry exists for travel_worker
```

- [x] **Step 2: Run verification — expect FAIL**

```bash
PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… \
  .venv/bin/python -m pytest backend/tests/integration/test_postgres_migrations.py \
  -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-m5
```

- [x] **Step 3: Implement**

Add the assertions against `pg_roles`, `pg_policies`,
`information_schema.role_table_grants`, and `pg_default_acl`.

- [x] **Step 4: Run verification — expect PASS**

Re-run the command from Step 2.

- [x] **Step 5: Review checkpoint**

Review: the grant set is exactly the enumerated minimum, and the round-trip is
faithful.

---

## Package Verification

Run on the exact final worktree state, in this order:

1. `python -m compileall backend`
2. `.venv/bin/python -m pytest backend/tests/unit -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-p1`
3. `.venv/bin/python -m pytest backend/tests/boundaries -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-p2`
4. `PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… .venv/bin/python -m pytest backend/tests/integration -q -p no:cacheprovider --basetemp=.workbuddy-ai/tmp/pytest-p3 -rs`
5. Alembic round-trip: `upgrade head`, `downgrade -1`, `upgrade head`
6. `cd frontend && npm run lint && npm test`
7. `docker compose config --quiet`
8. `git status --short --untracked-files=all` and `git diff --check`

A required skip, a conflict marker, or a failing check blocks the completion
claim. The integration suite must run with zero required skips.

## Rollback

| Stage | Action |
| --- | --- |
| Before the migration is applied | Abandon the worktree; no persistent change |
| After the migration, before any worker is mounted | `alembic downgrade -1`; the policies and function are dropped and the role is left to operations |
| After a worker is mounted (a later milestone) | Stop the worker before downgrading; leases are untouched by the downgrade, so a re-upgrade restores claimability |
| A role grant turns out to be too wide | Revoke the specific grant; no data repair is required |

No table is altered and no row is written by this change, so rollback never
requires a data restore.

## Completion Record

| Field | Value |
| --- | --- |
| Specification approval | Approved 2026-09-11 on the repository owner's instruction to implement. |
| Plan approval | Approved 2026-09-11 on the same instruction. |
| Execution | **Complete.** All five tasks executed. |
| Verification | **Complete for this plan's scope, with one out-of-scope failure disclosed below.** |
| Delivery gate | Repository owner only. No Git delivery is authorized by this plan. |

### Per-task status

| Task | Implemented | Verified | Evidence |
| --- | --- | --- | --- |
| 1 — worker role, claim policies, enumerated grants, counting function | Yes | Yes | Revision `20260911_04`; 8 migration contract tests green |
| 2 — worker DSN contract | Yes | Yes | 5 unit tests green; `assert_least_privilege_role` extracted and shared |
| 3 — readiness count through the bounded function | Yes | Yes | Probe reads `ready_outbox_event_count()`; end-to-end probe shows 0 → 1 across the release |
| 4 — replace the defect characterisation with behaviour tests | Yes | Yes | 5 behaviour tests green; the characterisation test is deleted |
| 5 — migration contract tests | Yes | Yes | Role flags, policy scoping, exact grant set, no default ACL, function ACL, downgrade, round-trip |

### Facts established during execution

1. The revision identifier Alembic produces is `20260911_04`.
2. `travel_worker` did not exist before this change in the test database, so the
   guarded `CREATE ROLE` branch ran. The `ALTER ROLE` branch is still exercised
   because it runs unconditionally after the guard.
3. The bootstrap credential variable is `WORKER_DB_PASSWORD`. It was added to
   `docker-compose.yml` and documented in `.env.example`, because the script now
   requires it and a fresh volume would otherwise fail to bootstrap.

### Verification results

| Check | Result |
| --- | --- |
| `python -m compileall -q backend` | exit 0 |
| `pytest backend/tests/unit` | **814 passed, 1 failed** — the failure is pre-existing and out of scope (see below) |
| `pytest backend/tests/boundaries` | 16 passed |
| `pytest backend/tests/integration -rs` | **189 passed, 0 skipped** |
| Alembic round-trip (`upgrade head` → `downgrade -1` → `upgrade head`) | `20260911_04` → `20260911_03` → `20260911_04` |
| `docker compose config --quiet` | clean |
| Frontend suite | 28 passed |
| Mutation proof (5 mutations) | all five failed as expected; every new assertion is load-bearing |
| End-to-end defect closure | `count_ready_outbox_events()` as `travel_app`: **0 before the turn completed, 1 after** (was a false 0 in both states); `claim_batch` as `travel_worker`: **1** (was 0); `claim_batch` as `travel_app`: **0** |

### Deviations from the plan, recorded rather than silently applied

1. **`worker_dsn()` cannot itself refuse a privileged role.** The plan's Task 2
   Step 1 asked for that, but a pure DSN resolver has no connection and therefore
   cannot read `pg_roles`. The rule is enforced by `assert_least_privilege_role`,
   extracted from `RuntimeContainer` into `backend/storage/postgres.py` and now
   shared, so the worker gets the identical guard the API runtime has. The
   container delegates to it; a unit test asserts the container no longer carries
   its own copy of the query.

2. **A test-isolation defect in this plan's own Task 5 tests was found by the
   mutation proof and fixed.** The five migration contract tests were written with
   `pg_engine` alone, which does not reset the schema. They therefore measured
   whatever the previous test had left, and the "grant set widens to INSERT"
   mutation **passed** — a hole. Every ADR 0028 migration test now takes
   `fresh_db`. This is the second time the mutation proof has caught a
   non-load-bearing assertion in this repository; it is the reason the proof is
   run rather than assumed.

### Disclosed failure, out of scope

`backend/tests/unit/test_config.py::test_models_url_has_no_default` fails with
`'https://api.xkiro.com/v1' == ''`. This is pre-existing and unrelated to this
plan: `config.py:8-10` loads the repository `.env` unconditionally, and `.env`
line 1 sets `GITHUB_MODELS_URL`, so the test's "unset variable" premise cannot
hold. Fixing it needs a product change (a dotenv path or disable flag), which is a
separate Level 2 decision. **It is not fixed here and must not be relabelled as
passing.**

### Limitations

1. No worker is mounted, so the composed worker-plus-tenant flow is not exercised
   end to end; the claim and the transcript read are proven separately with real
   roles, and the tenant binding is proved through the same `tenant_transaction`
   the worker will call.
2. The Memory-table grant set the future worker milestone needs is deliberately
   not enumerated here, so that milestone needs its own migration.
3. Neither feature gate is enabled, so the pipeline remains dormant and this change
   cannot be observed end to end in a running system.
4. The claim query's index usage under the new policy is asserted by construction,
   not by an executed plan analysis.
