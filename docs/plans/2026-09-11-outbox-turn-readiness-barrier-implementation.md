# Outbox Turn-Readiness Barrier Implementation Plan

> **For agentic workers:** Execute task-by-task in order and preserve checkbox state.
> Each task ends with a review checkpoint. Do not advance past a failing checkpoint.

**Goal:** Make an outbox extraction event claimable only after the chat turn that
produced it is terminal, and narrow the worker's read to completed messages.

**Architecture:** Add a nullable `released_at` gate to `conversation_outbox`. Turn
allocation writes it `NULL`; `_transition_turn` — the single choke point for terminal
assistant transitions — releases it on success and cancels on failure in the same
transaction. Claim queries require the gate. The worker additionally discards
non-complete messages and reads a bounded range.

**Tech Stack:** Python 3.13, SQLAlchemy Core, Alembic, PostgreSQL 16, pytest.

**Spec:** [Outbox Turn-Readiness Barrier](../specs/2026-09-11-outbox-turn-readiness-barrier-design.md) v0.1

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-09-11 |
| Approved specification | `docs/specs/2026-09-11-outbox-turn-readiness-barrier-design.md` v0.1, Approved |
| Required ADR | ADR 0027, Accepted |
| Execution owner | Agent, under repository-owner instruction |
| Decision owner | Repository owner |
| Scope | Outbox readiness contract, two-phase turn transition, worker claim and read contracts |
| Verification | Migration round-trip; focused integration and unit suites; full backend suite; frontend suite |

## Global Constraints

1. Every persistent repository change requires a written specification and an approved implementation plan (`AGENTS.md`). The specification and this plan are approved; execute only the scope below. Level 3 also requires the ADR the design names — ADR 0027, which is Accepted.
2. The repository owner creates or selects branches and decides when to stage, commit in the primary working tree, push, open a PR, merge, and release. No Git delivery is authorized by this plan.
3. The working tree is dirty and large. Read a dirty file before touching it and work with the existing edits rather than reverting them.
4. **Do not enable either memory feature gate.** `MEMORY_WRITE_PIPELINE_ENABLED` and `MEMORY_SHADOW_EXTRACT_ENABLED` stay `False`. Do not add a worker service to `docker-compose.yml` and do not instantiate a worker in `RuntimeContainer`.
5. **Do not add a value to `OutboxStatus`.** The release fact is a separate column. The status vocabulary, ADR 0014's lifecycle and the tests that assert it are unchanged.
6. **Release and cancel both live in `_transition_turn`.** Do not release from a call site; a second writer would reintroduce drift.
7. **The backfill treats every pre-existing row as released**, whatever its status, because every existing row was written under a contract in which readiness was implied. Covering `leased` rows is not optional: the claim query's lease-expiry branch also requires the gate, so a `leased` row left blocked would be permanently unreclaimable rather than merely delayed. Do not cancel them and do not leave them blocked.
8. **The migration is applied before the code that reads the column.** The reverse order fails loudly on a missing column; that is acceptable and must be stated in the Completion Record.
9. Behaviour changes use a red-green-refactor cycle. Each task states the failing test first.
10. Never expose secrets, credentials, tokens, or sensitive personal data in code, logs, commands, evidence, or documentation.
11. `pytest backend/tests/unit backend/tests/boundaries` cannot be run as one command in this environment. Run directories separately. Always pass `--basetemp=.workbuddy-ai/tmp/pytest*`. Never run the backend and frontend suites concurrently.

## Required ADR — prerequisite

| ADR | Title | Status required | Status |
| --- | --- | --- | --- |
| 0027 | An outbox event is released only when its turn is terminal | Accepted | Accepted |

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/storage/migrations/versions/20260911_03_conversation_outbox_release_gate.py` | Add `released_at`, backfill, add the claim index; provide a faithful downgrade | — |
| `backend/storage/postgres.py` | Advance `ALEMBIC_HEAD` to the new revision | migration |
| `backend/conversations/postgres_repository.py` | Own the gate: the column, blocked allocation, release/cancel in `_transition_turn`, the cursor stamp | migration |
| `backend/memory/write_pipeline/outbox.py` | Require the gate in `claim_event` and `claim_batch` | column |
| `backend/memory/write_pipeline/worker.py` | Discard non-complete messages in `_load_messages` | read contract |
| `backend/tests/integration/test_outbox_turn_readiness.py` | Prove the gate end to end against PostgreSQL | all of the above |
| `backend/tests/unit/memory_write_pipeline/test_outbox.py` | Prove claim eligibility at the unit level | `outbox.py` |
| `backend/tests/integration/test_postgres_migrations.py` | Prove the migration round-trip and the backfill | migration |

## Task 1: Add the release gate column

**Files:** `backend/storage/migrations/versions/20260911_03_conversation_outbox_release_gate.py` (new), `backend/storage/postgres.py`, `backend/tests/integration/test_postgres_migrations.py`

**Interfaces:** produces `conversation_outbox.released_at timestamptz NULL` and `idx_conversation_outbox_ready`.

- [x] **Step 1: Write the failing tests**

In `test_postgres_migrations.py`, assert that after `upgrade head` the column exists with
type `timestamp with time zone`, is nullable, and that the index exists; and that a
pre-existing `status = 'pending'` row is backfilled to `released_at = created_at`. Assert
the downgrade removes the column and the index.

- [x] **Step 2: Run verification**

Expected: FAIL — the column does not exist.

- [x] **Step 3: Write the migration**

Revision `20260911_03`, down_revision `20260911_02`. Add the column nullable with no
default; run the backfill as a single `UPDATE conversation_outbox SET released_at =
created_at WHERE released_at IS NULL` — **no status predicate**, per Global Constraint 7;
create `idx_conversation_outbox_ready` on `(status, released_at)`. The downgrade drops the
index then the column. Advance `ALEMBIC_HEAD` in `backend/storage/postgres.py`.

- [x] **Step 4: Run verification**

Expected: PASS. Then confirm `alembic upgrade head` followed by `downgrade -1` followed by
`upgrade head` returns the database to head with no error.

- [x] **Step 5: Review checkpoint**

Confirm the backfill rule matches Global Constraint 7, the downgrade is faithful, and no
other migration file was modified.

## Task 2: Allocation writes a blocked event and stamps the cursor

**Files:** `backend/conversations/postgres_repository.py`, `backend/tests/integration/test_outbox_turn_readiness.py` (new)

**Interfaces:** consumes the column from Task 1; produces a blocked event carrying
`payload["after_sequence"]`.

- [x] **Step 1: Write the failing tests**

In the new module: after `append_turn` with an outbox intent, the row has
`released_at IS NULL`; and its `payload["after_sequence"]` equals the user message's
sequence minus one. Repeat the release assertion for `create_with_initial_turn`.

- [x] **Step 2: Run verification**

Expected: FAIL — `released_at` is `NULL` by accident but `after_sequence` is absent, so
the cursor assertion fails.

- [x] **Step 3: Implement**

Add `released_at` to the table definition. In `append_turn` and
`create_with_initial_turn`, insert `released_at=None` explicitly and set
`stored_payload["after_sequence"]` to the sequence immediately before the turn's user
message, overwriting any caller-supplied value, because the repository owns sequence
allocation. In the generic message-append path, whose message is inserted already
`complete`, insert `released_at=created_at` so today's behaviour is preserved.

- [x] **Step 4: Run verification**

Expected: PASS.

- [x] **Step 5: Review checkpoint**

Confirm the cursor stamp overwrites rather than defers, the generic append path is still
immediately claimable, and no message-status vocabulary changed.

## Task 3: Completion releases, failure cancels

**Files:** `backend/conversations/postgres_repository.py`, `backend/tests/integration/test_outbox_turn_readiness.py`

**Interfaces:** consumes Task 2; produces a released event on `complete_turn` and a
cancelled event on `fail_turn`, both atomic with the assistant transition.

- [x] **Step 1: Write the failing tests**

`complete_turn` sets `released_at` non-NULL in the same transaction as the assistant
becoming `complete`; a second `complete_turn` does not move the timestamp; `fail_turn`
leaves `status = 'cancelled'` and `released_at IS NULL`; and a failed turn's event is
never claimable.

- [x] **Step 2: Run verification**

Expected: FAIL — `released_at` stays `NULL` after completion.

- [x] **Step 3: Implement**

Add a `_release_turn_outbox` helper mirroring `_cancel_turn_outbox`, correlated through
the user message at `sequence - 1`, updating only where `released_at IS NULL` so the
release is idempotent. Call it from `_transition_turn` when the transitioned status is
`complete`, in the same transaction. Keep the existing cancellation call for `failed`.

- [x] **Step 4: Run verification**

Expected: PASS.

- [x] **Step 5: Review checkpoint**

Confirm release and cancel are in `_transition_turn` and nowhere else, the release is
idempotent, and the failure path is unchanged in intent.

## Task 4: Claim requires the gate

**Files:** `backend/memory/write_pipeline/outbox.py`, `backend/tests/unit/memory_write_pipeline/test_outbox.py`

**Interfaces:** consumes Tasks 1–3; produces a claim path that ignores blocked rows.

- [x] **Step 1: Write the failing tests**

A `pending` row with `released_at IS NULL` is not returned by `claim_batch` and is not
claimable by `claim_event`. A `pending` row with `released_at` set is returned. An expired
`leased` row is still reclaimable regardless of the gate. Existing claim, lease-expiry and
same-conversation serialization assertions continue to pass.

- [x] **Step 2: Run verification**

Expected: FAIL — the blocked row is claimed.

- [x] **Step 3: Implement**

Add `released_at IS NOT NULL` to the claimable condition in `claim_event` and in
`claim_batch`. Do not change the lease-expiry or serialization conditions.

- [x] **Step 4: Run verification**

Expected: PASS, including the pre-existing assertions.

- [x] **Step 5: Review checkpoint**

Confirm the gate applies to the `pending` branch only, the `leased` branch is untouched,
and no status value was added.

## Task 5: Narrow the worker's transcript read

**Files:** `backend/memory/write_pipeline/worker.py`, `backend/tests/unit/memory_write_pipeline/test_worker.py`

**Interfaces:** consumes the read contract; produces an extraction input containing only
completed messages.

- [x] **Step 1: Write the failing tests**

`_load_messages` excludes a `pending` assistant row and a `failed` assistant row, keeps a
`complete` row, and preserves the existing `after_sequence` filtering. A row that declares
no status is kept, matching the domain model's coercion.

- [x] **Step 2: Run verification**

Expected: FAIL — the pending row is returned with empty content.

- [x] **Step 3: Implement**

Resolve each message's status from the object attribute or mapping and skip anything that
resolves to a status other than `complete`. A message that declares no status counts as
`complete`, because `Message.__post_init__` already coerces an absent status to
`MessageStatus.COMPLETE` (`backend/conversations/models.py:274-275`); a stricter rule here
would contradict the model being consumed. Keep the existing sequence filter. Preserve the
current return shape so existing callers are unaffected.

- [x] **Step 4: Run verification**

Expected: PASS.

- [x] **Step 5: Review checkpoint**

Confirm the filter fails closed on a missing status, the sequence filter is intact, and
the returned shape is unchanged.

## Package Verification

Run on the exact final worktree state, in this order.

1. `PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… pytest backend/tests/integration/test_postgres_migrations.py -q --basetemp=.workbuddy-ai/tmp/g1` — expect pass, including the new round-trip assertions
2. `pytest backend/tests/integration/test_outbox_turn_readiness.py -q --basetemp=.workbuddy-ai/tmp/g2` — expect pass
3. `pytest backend/tests/unit -q --basetemp=.workbuddy-ai/tmp/g3` — expect pass
4. `pytest backend/tests/boundaries -q --basetemp=.workbuddy-ai/tmp/g4` — expect pass, unchanged count
5. `PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… pytest backend/tests/integration -q --basetemp=.workbuddy-ai/tmp/g5 -rs` — expect zero failures and zero skips
6. `cd frontend && npx vitest run` — expect pass
7. `grep -rn "MEMORY_WRITE_PIPELINE_ENABLED\|MEMORY_SHADOW_EXTRACT_ENABLED" backend/app/config.py` — expect both to still default `False`
8. `git status --short --untracked-files=all` — compare against the File Responsibility Map
9. Confirm the database returns to head `20260911_03` with the column present and no residue from the probe rows

Report actual output, exit status, and every check that could not run. Run the backend and
frontend suites sequentially, never concurrently.

## Rollback

Downgrade one revision to drop the column and the index, which restores the pre-change
behaviour including the race. Because the change is fail-closed, rolling back re-opens
the defect rather than breaking data; no data repair is required in either direction.

## Completion Record

| Field | Value |
| --- | --- |
| Specification approval | Approved 2026-09-11 on the repository owner's instruction to implement the reported outbox defects. |
| Plan approval | Approved 2026-09-11 on the same instruction. |
| Execution | **Complete.** All five tasks executed. |
| Verification | **Complete for this plan's scope, with one out-of-scope failure disclosed below.** |
| Delivery gate | Repository owner only. No Git delivery is authorized by this plan. |

### Per-task status

| Task | Implemented | Verified | Evidence |
| --- | --- | --- | --- |
| 1 — release gate column | Yes | Yes | 3 new migration tests green; column nullable, index present, downgrade faithful |
| 2 — blocked allocation and cursor | Yes | Yes | blocked row asserted; `after_sequence` stamped and overwritten |
| 3 — release on complete, cancel on fail | Yes | Yes | release asserted; idempotence asserted; cancel asserted |
| 4 — claim requires the gate | Yes | Yes | `claim_batch` and `claim_event` both gated, each with its own test |
| 5 — narrow the transcript read | Yes | Yes | 5 unit tests plus one integration test on real persisted rows |

### Verification results

| Check | Result |
| --- | --- |
| `test_postgres_migrations.py` | **33 passed** (was 30) |
| `test_outbox_turn_readiness.py` | **11 passed** (new) |
| `backend/tests/unit` | **805 passed, 1 failed** — see the disclosure below |
| `backend/tests/boundaries` | **16 passed**, unchanged |
| `backend/tests/integration` | **177 passed, 0 failed, 0 skipped** (was 163) |
| frontend | **28 passed** |
| Feature gates | Both still default `False`; worker still unmounted; no compose service |
| Database | At head `20260911_03`, column present, no probe residue |

### Mutation proofs — every new assertion is load-bearing

Each mutation reverted one piece of the fix, ran the test meant to catch it, and required
that test to fail. All five failed as expected, and all three production files were
restored byte-identically and verified.

| Mutation | Test | Result |
| --- | --- | --- |
| `claim_batch` gate removed | blocked-event test | **failed** |
| `claim_event` gate removed | single-claim test | **failed** |
| release call removed from `_transition_turn` | completion test | **failed** |
| cursor stamp removed | cursor test | **failed** |
| `_load_messages` filter removed | worker-read test | **failed** |

### The one failing check, and why it is not this plan's work

`backend/tests/unit/test_config.py::test_models_url_has_no_default` fails:

```
AssertionError: assert 'https://api.xkiro.com/v1' == ''
```

**Cause, established rather than assumed.** The test comes from the Configurable Model
Provider Endpoint plan and asserts that a *fresh interpreter* with the variable unset
yields the empty string. The repository owner has since populated `.env` with a live
provider configuration, and importing the settings module runs a dotenv load that writes
`.env` into `os.environ`. The test's isolation technique therefore cannot produce an unset
variable any more: `env -u GITHUB_MODELS_URL` still leaves the value present. The premise
of the test is defeated by the environment, not by a code defect in either change.

Nothing in this plan touches `config.py`, `.env`, or dotenv loading, so this failure is
independent of the readiness barrier. **It is recorded rather than fixed**, because
amending another plan's test is outside the approved scope of this one. The owner must
decide whether to fix that test's isolation (for example by running its subprocess in a
directory with no `.env`) or to keep `.env` and change the assertion.

Because a required verification check did not pass, this plan stays **`In Progress`**
rather than `Completed`, per the workflow rule that an unresolved failing check returns
the work to the owner. The implementation itself is complete.

### Facts established during execution

(a) **The revision identifier is `20260911_03`**, and `ALEMBIC_HEAD` now carries it.
(b) **The generic message-append path is not reachable from the chat route.** No caller of
`append_message` exists outside tests, so its insert-time release matters only for test
fidelity. It is still correct to set it, because the row it writes is already terminal.

### Two design refinements found while implementing, and applied

1. **The backfill covers every pre-existing row, not only `pending` ones.** A `leased` row
   left with `released_at IS NULL` would be permanently unreclaimable, because the claim
   query's lease-expiry branch also requires the gate. The specification and this plan were
   corrected before the migration was written, and a test pins the `leased` case.
2. **A message that declares no status is treated as `complete`.** `Message.__post_init__`
   already coerces an absent status to `MessageStatus.COMPLETE`
   (`backend/conversations/models.py:274-275`). A stricter rule in the worker would have
   made the same message complete to the repository and not-complete to the worker. The
   specification's edge case and this plan's Task 5 were corrected to match the model
   being consumed.

### A fifth defect, found by this plan's own tests and NOT fixed

`conversation_outbox` has row-level security enabled with an owner policy
(`owner_user_id = current_setting('app.tenant')`), but `claim_batch` and `claim_event` open
their own transaction **without setting `app.tenant`**. Under the least-privilege runtime
role the policy therefore compares against `NULL` and matches nothing, so **the worker
cannot claim any event as the runtime role** and would need a role that bypasses row-level
security — which conflicts with the least-privilege role the clean break established.

This is independent of ADR 0027, which is about *when* an event becomes claimable rather
than *who* may claim it. It is out of scope here and is **characterised by a test**
(`test_the_claim_path_is_not_tenant_scoped_today`) so it is visible in the suite rather
than buried in a report. That test must fail when the defect is fixed, which is the signal
that the fix landed.

### Limitations disclosed

(a) A turn abandoned while `pending` leaves its event blocked indefinitely; this is intended
fail-closed behaviour and no reconciliation is added. (b) The claim query's index usage is
asserted by construction, not by an executed plan analysis. (c) Neither feature gate is
enabled, so the pipeline stays dormant and the fix cannot be observed end to end in a
running system by this change alone. (d) `InMemoryOutboxRepository` does not model the
release gate; that divergence is documented on the class and characterised by a test, and
claim eligibility is proved against real PostgreSQL instead.
