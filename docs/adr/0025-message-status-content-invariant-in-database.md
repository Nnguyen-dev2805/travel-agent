# ADR 0025: The Message Status/Content Invariant Is Enforced in the Database

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-11 |
| Decision owners | Repository owner |
| Scope | Where the `messages` invariant "a `complete` row carries content" is enforced, and what happens to rows that already violate it. Bounded by the `messages` schema and the conversation read path. |
| Governing spec | `docs/specs/2026-09-11-message-status-content-invariant-design.md` v0.1 (Status: Approved 2026-09-11) |
| Superseded ADR | Not applicable |
| Superseded by | Not applicable |

## Context

ADR 0023 made a chat turn one unit of work with a two-phase write: a user message and a placeholder assistant row commit together, and the assistant row is filled in afterwards. It introduced `messages.status` with three values and stated the persistence contract that accompanies them:

> `content` remains non-empty for `COMPLETE`; a `PENDING` or `FAILED` row may carry an empty string, and `require_text` must therefore be applied only on the `complete` transition.

That contract is enforced in `backend/conversations/models.py` and nowhere else. The database accepts `status = 'complete'` with `content = ''`.

The reader re-validates every stored row. `PostgresConversationRepository._row_to_message` constructs a `Message` inside a `try` that maps `ConversationValidationError` to `ConversationStorageError`, and `list_messages` maps every row through it. So a single invalid row does not merely look wrong — it makes the entire conversation fail to load. Measured on 2026-09-11: five such rows existed on the disposable test database, and `list_messages` raised `ConversationStorageError` for their conversations.

The route into that state is a supported operation, not a misuse. Migration `20260911_01` adds the column with `DEFAULT 'complete'`, which is correct when adding a column to a table of pre-existing messages and wrong when re-adding it: `alembic downgrade -1` followed by `alembic upgrade head` relabels every `pending` row as `complete`. The implementation plan for ADR 0023 documents exactly that rollback. Any turn in flight when a process died — a state the same specification describes as intended and visible — becomes a `complete` row with no content, and its conversation stops loading.

That obligation was not new. ADR 0023's own acceptance criteria already include "a query asserts no `complete` row has empty content". The invariant was therefore an accepted requirement from the moment ADR 0023 was accepted, and it went unmet because nothing but the model enforced it — and the model's guard runs on read, not on write. This ADR does not introduce a requirement; it puts the existing requirement somewhere it can hold.

Three options were considered: leave the invariant in the model and make the reader tolerant, add the constraint without repairing existing rows, or repair and then constrain.

## Decision

The invariant `status <> 'complete' OR length(content) > 0` is enforced by a check constraint on `messages`, named `ck_messages_complete_has_content`, added by revision `20260911_02`.

The migration repairs violating rows first: `UPDATE messages SET status = 'failed' WHERE status = 'complete' AND content = ''`, then adds the constraint, in one transaction.

The read path does not change. `_row_to_message` continues to raise on a row that violates the contract.

The repair is deliberately one-way. `downgrade` drops the constraint and does not restore the previous status values, because which rows were originally `failed` is not recoverable once they have been relabelled. The migration must say so, and the plan requires the count of repaired rows to be reported on rollback.

## Alternatives Considered

### Leave the invariant in the model and reinterpret an invalid row on read

**Approach.** No migration. `_row_to_message` treats a `complete` row with empty content as `failed`.

**Benefits.** No schema change, no lock, nothing irreversible, and every existing conversation loads immediately.

**Costs.** The database keeps accepting a state the application defines as invalid, so the inconsistency becomes permanent and invisible: nothing counts the reinterpreted rows, nothing reports them, and a later reader cannot tell whether the coercion is load-bearing. It also rewrites the meaning of stored data during a read.

**Rejected because** it converts a detectable inconsistency into an invisible one and leaves the invariant enforced nowhere the data can be checked. The finding is that the model's guard runs too late; a silent coercion runs it later still.

### Constrain without repairing, as `NOT VALID`

**Approach.** `ADD CONSTRAINT ... CHECK (...) NOT VALID`. New and updated rows are checked; existing rows are not.

**Benefits.** Fully reversible. Brief lock. No migration ever modifies user rows.

**Costs.** Every unreadable conversation stays unreadable. The schema then claims an invariant the data does not satisfy, and the steady-state assertion that no `complete` row is empty stays red — or has to be weakened to exclude legacy rows.

**Rejected because** it treats the symptom. The unreadable conversations are the harm; preventing new damage while leaving the existing damage in place recovers nothing the user can see, and a verification step that has to exclude the rows it was written to catch is decoration.

### Repair, then constrain

**Approach.** Repair violating rows to `failed`, then add the constraint and validate it.

**Benefits.** The invariant becomes a database obligation that no writer — including a future one, or a manual session — can bypass. The rows that are currently unreadable become readable, because `failed` is the truthful status for a row that produced no reply. The constraint is trivially droppable, and the steady-state assertion becomes meaningful.

**Costs.** The repair is not reversible. `ADD CONSTRAINT` scans `messages` under an `ACCESS EXCLUSIVE` lock. A schema migration modifies user rows.

**Selected because** it is the only alternative that both prevents recurrence and recovers the damage, and because its irreversibility is bounded and one-directional: it moves rows from a state the application cannot read into one it can. That effect is disclosed in the migration, the plan, and the rollback boundary rather than left for an operator to discover.

## Consequences

**Positive.**

- A `complete` row with empty content cannot be written, by any writer, under any role.
- Conversations that are currently unreadable load again, and the frontend renders the repaired rows as failed turns, which is what they are.
- The invariant is enforced at the layer that cannot be bypassed, while the model keeps its own validation for service-assembled input.
- Package verification check 7 becomes a real assertion rather than a test that fails after every migration round trip.

**Negative.**

- The repair cannot be undone. After a rollback, repaired rows stay `failed`, and no record exists of which were `complete`.
- `ADD CONSTRAINT` holds an `ACCESS EXCLUSIVE` lock while it scans the table. Acceptable at the current scale; it would need an online approach on a large table.
- A schema migration now modifies user data, which some operators prefer to handle by hand.
- Two layers enforce one invariant, and they can drift if one is changed without the other. The constraint is the stronger of the two, so drift degrades to a stricter database rather than a looser one.

**Neutral.**

- No application code changes. The repository already writes only valid rows and already fails closed on invalid ones.
- No RLS change; `messages` stays `FORCE`d and the constraint applies to every role.

## References

1. Governing spec: `docs/specs/2026-09-11-message-status-content-invariant-design.md` v0.1
2. Implementation plan: `docs/plans/2026-09-11-message-status-content-invariant-implementation.md`
3. Extends: [ADR 0023](./0023-atomic-two-phase-chat-turn.md) — Atomic Two-Phase Chat Turn
4. Evidence: `docs/plans/2026-09-11-atomic-chat-turn-and-memory-correctness-implementation.md`, limit 2
5. Related: [ADR 0019](./0019-postgresql-only-application-persistence-sqlite-retirement.md) — PostgreSQL-Only Application Relational Persistence and SQLite Retirement
