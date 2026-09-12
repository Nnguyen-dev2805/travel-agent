# Message Status/Content Invariant: Enforcement and Repair

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-11 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Where the `messages` status/content invariant is enforced, and how the existing violation is repaired. Bounded by the `messages` schema, the conversation read path, and the rollback story of migration `20260911_01`. |
| Related issue | None filed. Authorization basis is the owner-requested review; evidence in `docs/plans/2026-09-11-atomic-chat-turn-and-memory-correctness-implementation.md` limit 2 and in the probe recorded under Current-state Evidence. |
| Superseded document | Not applicable |

## Summary

ADR 0023 established a server-owned turn status on `messages`: a `complete` row carries the reply, and a `pending` or `failed` row carries nothing. That invariant is enforced **only in Python**. The database accepts `status = 'complete'` with `content = ''`.

That combination is not merely untidy. `PostgresConversationRepository._row_to_message` re-validates every row it reads, so a `complete` row with empty content makes the repository raise `ConversationStorageError` — **the entire conversation becomes unreadable**, not just the offending row. A conversation that cannot be listed is a conversation the user has lost.

The gap is reachable through the rollback procedure ADR 0023 itself documents. Migration `20260911_01` adds the column with `DEFAULT 'complete'`, so `alembic downgrade -1` followed by `alembic upgrade head` re-labels every `pending` row as `complete`. Any turn that was in flight when the process died becomes a `complete` row with no content, and its conversation stops loading.

This specification decides where the invariant is enforced, and what happens to rows that already violate it. It does not change the status vocabulary, the read path's contract, or the frontend.

## Context

`messages` is created by the clean-break migrations and carries `status VARCHAR(16) NOT NULL DEFAULT 'complete'` with a check over `('pending', 'complete', 'failed')` and an index on `(conversation_id, status)` (migration `20260911_01_message_turn_status`). `docs/specs/2026-09-11-atomic-chat-turn-and-memory-correctness-design.md` states the contract:

> **Contract:** `status` is server-owned, never accepted from input. Existing rows default to `complete`. `content` remains non-empty for `COMPLETE`; a `PENDING` or `FAILED` row may carry an empty string, and `require_text` must therefore be applied only on the `complete` transition.

The first half of that contract — `status` is server-owned and governed — is enforced by the database. The second half — `content` is non-empty exactly when `status = 'complete'` — is enforced only by `backend/conversations/models.py`. The model is not a weak guard: it is what the repository, the service, and the API all funnel through. But it is a guard that runs *after* the write, on read, and its failure mode is a raised storage error rather than a rejected write.

That asymmetry is what this specification addresses.

**This is not a new requirement.** ADR 0023's acceptance criteria already include "a query asserts no `complete` row has empty content". The invariant has been an accepted obligation since ADR 0023 was accepted, and it is unmet because nothing but the model enforces it — and the model's guard runs on read, not on write. This specification does not add a rule; it puts the existing rule where it can hold, and repairs the rows that already broke it.

## Users

1. **Repository owner** — approves the enforcement location and the repair of existing rows.
2. **Authenticated end user** — depends on their transcript loading at all. An unreadable conversation is worse than a visible failed turn.
3. **Operator** — needs a migration that either succeeds or fails loudly, never one that silently leaves rows the application cannot read.
4. **Engineer implementing the memory pipeline** — reads conversations through the same repository and is blocked by the same failure.
5. **Future contributor** — needs to know whether a `messages` invariant belongs in the schema or the model, so the next one is not decided by accident.

## Problem Statement

**The database can hold a state the application cannot read.** `messages` has a primary key, a unique constraint on `(conversation_id, sequence)`, a foreign key to `conversations`, a check over the three status values, and no constraint relating `status` to `content`. A row with `status = 'complete'` and `content = ''` is therefore accepted by the database and rejected by the reader.

**The failure is total, not local.** `_row_to_message` raises for the offending row, and `list_messages` maps rows through it, so one bad row makes the whole conversation unloadable. Measured: after a `downgrade -1` / `upgrade head` round trip, five such rows existed and reading one of their conversations raised `ConversationStorageError`.

**The rollback path manufactures it.** `DEFAULT 'complete'` is the right default for adding the column to a pre-existing table — every pre-`20260911_01` row really was a complete message. But the same default is wrong on *re*-upgrade: a `pending` row is not a complete message, and re-adding the column silently asserts that it is. The plan's Rollback section explicitly contemplates downgrading to `20260910_04` and back, so this is a supported operation, not a misuse.

**Why now.** Plan B is implemented and verified, and its package verification check 7 (`complete` rows with empty content must be zero) fails. Until this is decided, that check cannot pass honestly, and the next person to run a migration round trip will produce unreadable conversations again.

## Goals

1. A `complete` row with empty content cannot be written to `messages`.
2. Rows that already violate the invariant are repaired into a state the application can read, or the migration fails loudly rather than leaving them.
3. The migration states plainly which of its effects are reversible and which are not.
4. The read path is not made tolerant of an invalid row. Coercing a bad row on read would hide the corruption instead of preventing it.
5. Package verification check 7 can pass on a database that has been through a migration round trip.

## Non-goals

1. Changing the status vocabulary, the `messages` columns other than through the new constraint, or the RLS policy.
2. Making the reader tolerant: no `complete`-with-empty-content row is to be silently reinterpreted during a read.
3. Any change to the frontend, which already renders `failed` and `pending` distinctly.
4. Enabling the memory write pipeline.
5. Preventing `pending` rows from surviving a crash. A visible `pending` row remains the intended behaviour; this specification only stops it from being *mislabelled* as complete.
6. Repairing `failed` rows that legitimately hold no content. Those satisfy the invariant.

## Assumptions

1. A `complete` message with empty content is never a legitimate reply. The message contract rejects it at every application entry point, so any such row is a defect, not a feature.
2. `failed` is the truthful status for a row that has no content and never produced a reply. This is what `fail_turn` already writes.
3. The runtime role `travel_app` may not run DDL; the migration runs as the bootstrap superuser, as every other migration does.
4. A database that already violates the invariant can be repaired in place, because the repair only moves rows from a state the application cannot read to one it can.
5. `ALTER TABLE ... ADD CONSTRAINT ... CHECK` takes an `ACCESS EXCLUSIVE` lock and validates existing rows by scanning the table. At the current scale (a disposable test database, and a product with no production deployment) that is acceptable; the plan requires the cost to be stated rather than assumed.

## User and System Flows

**Flow 1 — A normal turn.** Unchanged. `append_turn` writes a `complete` user row and a `pending` assistant row; `complete_turn` sets the content and the status together. Both satisfy the constraint.

**Flow 2 — A generation failure.** Unchanged. `fail_turn` writes `content = ''` with `status = 'failed'`, which the constraint permits.

**Flow 3 — A migration round trip over a database holding a `pending` row.** `downgrade -1` drops the column and its data. `upgrade head` re-adds it with `DEFAULT 'complete'`, so the row becomes `complete` with empty content. Under this specification the follow-up migration repairs it to `failed`, and the conversation loads again.

**Flow 4 — A writer attempts an invalid row.** The database rejects it with a check violation. The application already prevents this; the database now refuses to be the weaker of the two.

## Behavioral and Data Contracts

### Schema (`messages`)

- **Produces:** a check constraint `ck_messages_complete_has_content` with the predicate
  `status <> 'complete' OR length(content) > 0`.
- **Contract:** the predicate is deliberately written to permit `pending` and `failed` rows with empty content, and to permit any content on a non-`complete` row. It forbids exactly one combination: `complete` with empty content. It does not replace `ck_messages_status`, which continues to govern the vocabulary.

### Migration

- **Produces:** revision `20260911_02_message_complete_has_content`, `down_revision = "20260911_01"`, and `ALEMBIC_HEAD` updated to `20260911_02`.
- **Contract:** `upgrade` repairs the violating rows and then adds the constraint, in that order, in one transaction. `downgrade` drops the constraint. **The repair is not reversed by `downgrade`** — which rows were originally `failed` is not recoverable once they have been relabelled — and the migration docstring must say so.

### Read path

- **Contract:** unchanged. `_row_to_message` keeps raising on an invalid row. Tolerance on read is explicitly rejected as a solution because it converts a detectable inconsistency into an invisible one.

## Errors and Edge Cases

1. **A database contains `complete` rows with empty content.** Expected: `upgrade` relabels them `failed` and records the count in its log line, then adds the constraint. The conversations become readable.
2. **A database is already clean.** Expected: `upgrade` repairs zero rows and adds the constraint.
3. **A writer inserts `complete` with empty content after the migration.** Expected: the database rejects it; the caller sees an integrity error, which `_classify_integrity_error` maps to a repository error rather than a silent success.
4. **A writer inserts `failed` or `pending` with empty content.** Expected: accepted. The constraint must not over-reach.
5. **`downgrade` runs after a repair.** Expected: the constraint is dropped; the repaired rows stay `failed`. This is a one-way data effect and the plan requires it to be disclosed, not hidden.
6. **The constraint is added while another session writes.** Expected: the `ACCESS EXCLUSIVE` lock serialises it. The plan requires the lock to be acknowledged rather than assumed away.
7. **A `pending` row exists at migration time.** Expected: untouched. `pending` is a valid state and the constraint permits it.
8. **The constraint name collides with an existing one.** Expected: `upgrade` fails loudly. Names are constants in the revision module, as elsewhere in this chain.

## Security and Privacy

**Trust boundaries.** No new boundary. The constraint is a data-integrity guard inside the existing PostgreSQL trust boundary, and it is enforced for every role including the bootstrap superuser. No RLS policy changes; `messages` stays `FORCE`d.

**Authorization.** Unchanged. The migration runs as the bootstrap superuser through the existing Alembic path, which is how every other revision in this chain runs.

**Data classification.** The repair does not read, copy, or log message content. It moves a status value; the `content` column is only compared to the empty string. No content leaves the database, and the migration's log line carries a count and nothing else.

**Privacy.** Improved. A conversation that previously failed to load becomes loadable, which is the user's own data returned to them. No data is exposed to a new party.

## Observability and Operations

- `upgrade` emits one log line with the number of rows repaired. A non-zero count is a signal that a rollback previously ran over a `pending` row, and it is the operator's evidence that the repair was needed.
- Package verification check 7 (`SELECT count(*) FROM messages WHERE status = 'complete' AND content = ''`) becomes a meaningful steady-state assertion: it is now enforced by the database rather than merely asserted by a test.
- The plan requires the check to be run after a migration round trip, which is the operation that used to break it.

## Capacity, Latency, and Cost

- **Latency.** Adding a check constraint scans `messages` once and holds an `ACCESS EXCLUSIVE` lock for the duration. The table is small in every current environment. The plan requires the scan to be acknowledged and the measured row count reported.
- **Capacity.** One constraint; no new column, no new index. The repair is a single `UPDATE` over the violating subset, which the existing index on `(conversation_id, status)` cannot serve — but the subset is expected to be tiny and the statement is bounded by the table size.
- **Cost.** No model call, no new query on the request path. Every insert now evaluates one cheap predicate.
- **Measurement.** The plan requires the repaired-row count and the constraint's presence to be reported, and the migration's runtime to be observed rather than budgeted, since no numeric budget exists for this system.

## Compatibility and Staged Migration

**Coexistence.** A stricter database is compatible with an older application instance: an older writer cannot produce `complete` with empty content, because it never wrote `pending` rows at all. The new application is the one that produces `pending` rows, and it already refuses to complete a row with empty content. No application change is required for compatibility.

**Sequencing.** Single step. The migration is the change; no code depends on the constraint existing.

**Rollout gate.** Check 7 must return zero on a database that has been through `downgrade` and `upgrade`, and the migration must have run without a manual repair.

**Rollback boundary.** `downgrade` restores the schema exactly. It does **not** restore the pre-repair status values, and this is the one irreversible effect of the change. An operator rolling back must expect the repaired rows to remain `failed`.

## Failure and Recovery

| Failure | Behaviour | Recovery |
| --- | --- | --- |
| Existing rows violate the invariant | `upgrade` repairs them to `failed`, then adds the constraint | None needed; the conversations load |
| A writer submits `complete` with empty content | Database rejects the write | The application already prevents this; the error maps to a repository error |
| `upgrade` fails mid-way | The transaction rolls back; the constraint and the repair are both undone | Re-run after fixing the cause |
| `downgrade` after a repair | Constraint dropped; repaired rows stay `failed` | Accepted and disclosed; the original statuses are not recoverable |
| Lock contention during `ADD CONSTRAINT` | The migration waits or fails on timeout | Re-run in a quieter window; the operation is idempotent from a rolled-back state |

## Required ADRs

1. **ADR 0025 — The Message Status/Content Invariant Is Enforced in the Database.** Records the decision that the `complete`-implies-content invariant is a schema obligation rather than a model obligation, and that a violating row is repaired rather than reinterpreted on read. Extends ADR 0023's persistence contract with the enforcement location it left to the application.

**No second ADR is required.** The repair rule is a consequence of the existing status vocabulary, not a new decision: `failed` already means "this turn produced no reply", which is exactly what a `complete` row with empty content is.

## Alternatives Considered

### Repair, then constrain — the selected approach

**Approach.** One migration: `UPDATE messages SET status = 'failed' WHERE status = 'complete' AND content = ''`, then `ADD CONSTRAINT ck_messages_complete_has_content CHECK (status <> 'complete' OR length(content) > 0)`.

**Benefits.** The invariant becomes a database obligation, so no writer — including a future one, or a manual `psql` session — can violate it. The rows that are currently unreadable become readable, because `failed` is the truthful status for a row with no content. The constraint is trivially droppable. Check 7 becomes a real assertion.

**Costs.** The repair is not reversible: once a row is relabelled `failed`, the fact that it was `complete` is gone. `ADD CONSTRAINT` scans the table under an `ACCESS EXCLUSIVE` lock. A database that already violates the invariant is modified by a schema migration, which some operators prefer to handle manually.

**Selected because** it is the only alternative that both prevents recurrence and repairs the damage. The irreversibility is bounded and one-directional — the change only moves rows from a state the application cannot read into one it can — and it is disclosed in the migration, the plan, and the rollback boundary rather than left for an operator to discover.

### Add the constraint as `NOT VALID`

**Approach.** `ADD CONSTRAINT ... CHECK (...) NOT VALID`. New and updated rows are checked; existing rows are not, and no repair happens.

**Benefits.** Fully reversible: `downgrade` drops the constraint and nothing about the data changed. No table scan, so the lock is brief. No migration ever modifies user rows.

**Costs.** Every conversation that is unreadable today stays unreadable. The constraint prevents new damage while leaving the existing damage in place, which is the worst of both: the schema now claims an invariant the data does not satisfy, and check 7 still fails.

**Rejected because** it treats the symptom. The unreadable conversations are the actual harm; a constraint that leaves them broken while preventing new ones does not recover anything the user can see. It would also make check 7 permanently red, or force the check to be weakened to exclude legacy rows, which is how a verification step becomes decoration.

### Reinterpret an invalid row on read

**Approach.** No migration. Make `_row_to_message` treat a `complete` row with empty content as `failed`.

**Benefits.** Smallest possible change; no schema migration, no lock, nothing irreversible. Every existing conversation loads immediately.

**Costs.** The database keeps accepting a state the application defines as invalid, so the inconsistency is permanent and invisible: nothing counts the reinterpreted rows, nothing reports them, and a future reader of the code cannot tell whether the coercion is load-bearing or vestigial. It also silently rewrites the meaning of stored data during a read, which is exactly the class of silent degradation this repository has spent the day removing.

**Rejected because** it converts a detectable inconsistency into an invisible one, and because it leaves the invariant enforced nowhere the data can be checked. The whole point of the finding is that the model's guard runs too late; moving the guard's failure into a silent coercion runs it even later.

## Current-state Evidence

| Claim | Evidence path | Verified how |
| --- | --- | --- |
| `messages` has no constraint relating `status` to `content` | `backend/storage/migrations/versions/20260911_01_message_turn_status.py`; live `pg_constraint` for `messages` returns only `messages_pkey`, `messages_conversation_id_sequence_key`, `messages_conversation_id_fkey` | Direct read plus a live query on the disposable test database, 2026-09-11 |
| The column is added with `DEFAULT 'complete'` | `20260911_01_message_turn_status.py`, `server_default="complete"` | Direct source read |
| The model rejects a `complete` row with empty content | `backend/conversations/models.py`, `_normalize_message_fields` applies `require_text` only when the status is `COMPLETE` | Direct source read |
| The reader re-validates stored rows and raises | `backend/conversations/postgres_repository.py`, `_row_to_message` constructs `Message(...)` inside a `try` that maps `ConversationValidationError` to `ConversationStorageError` | Direct source read |
| Five such rows existed after a round trip, and their conversations raised | Probe on the disposable test database, 2026-09-11: `SELECT count(*) ... WHERE status='complete' AND content=''` returned 5; `repo.list_messages(...)` raised `ConversationStorageError` | Executed |
| The repair makes those conversations load again | Same probe: after `UPDATE ... SET status='failed'`, `repo.list_messages(...)` returned `[('user', 'complete'), ('assistant', 'failed')]` | Executed |
| The proposed predicate enforces exactly the intended combination | Same probe: `complete`+empty **rejected** (`CheckViolation`); `complete`+text, `failed`+empty and `pending`+empty all **accepted** | Executed |
| The rollback path is the reachable route | `docs/plans/2026-09-11-atomic-chat-turn-and-memory-correctness-implementation.md`, Rollback section, step 5 | Direct read |

**Not verified.** No production database was inspected; the violation is measured only on the disposable test database, where the rows came from a test fixture rather than a crashed process. The lock duration of `ADD CONSTRAINT` on a table of production size was not measured, because no production table exists. The claim that a crashed process leaves a `pending` row is reasoned from the two-phase write and from the specification's own failure table, not reproduced.

## Components and Dependency Direction

```
backend/storage/migrations/versions/20260911_02_message_complete_has_content.py
   │  repairs violating rows, then constrains them
   ▼
PostgreSQL 16 · messages (status, content, ck_messages_complete_has_content)
   ▲
   │  reads and writes unchanged
backend/conversations/postgres_repository.py
   │  still fails closed on an invalid row
   ▼
backend/conversations/service.py · backend/orchestration/conversation_orchestrator.py
```

**Allowed dependency direction.** Unchanged. Only the migration and the schema move; no module gains a dependency. The repository keeps its fail-closed read.

**Ownership.** The schema owns the invariant. The model keeps its own validation, because it is also the boundary for service-assembled input and for rehydrated rows; the two are complementary, and the schema is the one that cannot be bypassed.

## Data Flow and Lifecycle

**Turn lifecycle.** Unchanged: `pending` → `complete` on success, `pending` → `failed` on failure. The constraint narrows the transition into `complete` to those that carry content, which is already the only transition the repository performs.

**Violation lifecycle.** A row enters the violating state only through a column re-add (a rollback followed by a re-upgrade) or a manual write. After this change the second route is closed and the first is repaired on the next upgrade.

**Migration lifecycle.** `upgrade` is idempotent from a rolled-back state: the repair matches zero rows on a second run and the constraint already exists. `downgrade` drops the constraint and leaves the data as it stands.

## Approval Record

| Field | Value |
| --- | --- |
| Version | 0.1 |
| Status | Approved — 2026-09-11, repository owner |
| Approver role | Repository owner |
| Date | 2026-09-11 |
| Authorization boundary | Authorizes preparation and approval of the implementation plan at `docs/plans/2026-09-11-message-status-content-invariant-implementation.md` and acceptance of ADR 0025. Implementation is authorized only by the separate plan approval recorded below. |

**Approved 2026-09-11 by the repository owner, together with Plan C.** The approval authorizes implementation of Task 1 of that plan.

**What this approval does NOT authorize.** Enabling the memory write pipeline; any change to the status vocabulary or the RLS policy; making the read path tolerant of an invalid row; applying the migration to any environment other than the disposable test database; and any Git delivery.

**One effect of this approval is irreversible, and it is recorded here deliberately.** The migration repairs existing `complete` rows with empty content by relabelling them `failed`. `downgrade` drops the constraint but cannot restore the previous status values. Approving this specification therefore includes accepting a one-way data repair, bounded to rows the application cannot currently read.
