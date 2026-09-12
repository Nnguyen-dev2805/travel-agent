# ADR 0023: Atomic Two-Phase Chat Turn

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-11 |
| Decision owners | Repository owner |
| Scope | Conversation turn persistence: the transaction boundary that defines a chat turn, the `messages` turn status, and the transcript visibility of an incomplete turn. Bounded by the conversation repository contract and the `messages` schema. |
| Governing spec | `docs/specs/2026-09-11-atomic-chat-turn-and-memory-correctness-design.md` v0.1 (Status: Approved 2026-09-11) |
| Superseded ADR | Not applicable |
| Superseded by | Not applicable |

## Context

ADR 0021 established standalone conversation ownership, the route contract, and auto-create behaviour, but it did not decide what constitutes a *turn* at the persistence boundary. The implementation therefore assembled a turn in the orchestrator, and it commits in four transactions: an ownership read, the user-message write with its outbox event, a generation call outside any transaction, a second ownership read, and the assistant-message write (`backend/orchestration/conversation_orchestrator.py:100-166`, verified by direct source read on 2026-09-11).

This was tolerable while a workspace container held the conversation, because the workspace imposed an outer consistency boundary. ADR 0018 removed that container. The turn is now the only boundary there is, and it does not exist.

Two Critical defects follow.

**Loss of turn adjacency.** `append_message` takes `SELECT … FOR UPDATE` on the parent conversation before reading `max(sequence)` (`backend/conversations/postgres_repository.py:425-435`), so sequences stay unique and contiguous. But the assistant write takes that lock a second time, later. Two concurrent turns on one conversation therefore commit as `user_A, user_B, assistant_A, assistant_B`. Every user message is no longer immediately followed by its own reply. Range-based memory extraction then attributes B's reply to A's turn.

**Orphaned and duplicated turns.** Generation runs after the user turn is committed. If it fails, the user message and a live outbox event persist with no reply. On a first turn the response carries no `conversation_id` even though the conversation was created, so a client retry creates a second conversation and a duplicate user message, and the phantom conversation persists in `listConversations` indefinitely. The assistant-append failure path is worse still: it returns HTTP `200` with `persisted=false` (`:176-195`), and the frontend ignores that flag, so the user is shown a saved turn that vanishes on reload.

A durable decision is required because every remedy changes either the repository contract, the `messages` schema, or the visible transcript — and because ADR 0021's ownership contract is silent on precisely this point, so a future contributor has no record to argue from.

## Decision

**A chat turn is one unit of work, persisted in two phases.**

1. **Phase one — allocate the turn.** In a single transaction, under a single `SELECT … FOR UPDATE` on the parent conversation row, the repository inserts the user message with status `complete`, inserts the assistant row with status `pending` at the next sequence, inserts the outbox event when enabled, and bumps `updated_at`. Both sequences are allocated together, so adjacency holds regardless of which generation finishes first.

2. **Phase two — fill the turn.** After generation, a single-row update sets the assistant row's content and status to `complete`. The update is guarded by `status = 'pending'`, so a duplicate call is a no-op rather than a corruption. On generation failure, a single-row update sets status to `failed` and cancels the turn's outbox event in the same transaction.

**`messages` carries a server-owned turn status** — `pending`, `complete`, or `failed` — defaulting to `complete` for existing rows. The status is never accepted from input.

**An incomplete turn is visible, not hidden.** A crash leaves a `pending` row that an operator can count. The alternative — an invisible inconsistency — is the defect being fixed. The API exposes the status so a client renders a failed turn distinctly rather than as an empty reply.

**The orchestrator owns turn sequencing and failure classification.** The repository owns transaction boundaries. Neither owns the other's concern.

**Explicitly out of scope of this decision.** The recorder's shadow-only invariant is unchanged. The outbox lease, retry and back-off semantics are governed by ADR 0014 and are unchanged. No automatic reconciliation of a `pending` row is decided here.

## Alternatives

### Compensation — keep the current order and delete the user message on failure

**Benefits.** No schema change. Smallest diff. Does not require the frontend to render a new state.

**Costs.** Turn adjacency is still not preserved, because the assistant write still acquires the parent lock separately, so the concurrency defect remains. If the compensating transaction itself fails, the orphan returns, making the failure mode probabilistic rather than eliminated. The compensation is a destructive write against the user's own message, which is harder to reason about than a status transition.

**Not selected.** It fixes the smaller defect while leaving the larger one in place, and it consumes the architecture approval for touching the same code without resolving it.

### Generate first, persist afterwards

**Benefits.** Genuinely one transaction for the write phase. No schema change. No `pending` state to render or reconcile.

**Costs.** The user's message is lost entirely if generation fails, so the turn vanishes rather than being recorded as failed. Retry semantics degrade: a retry after a failure is indistinguishable from a first attempt, so duplicate generation is unavoidable. A slow provider holds no persisted record of the request, which makes a provider failure harder to diagnose and makes the user's input unrecoverable.

**Not selected.** Silently losing the user's message is a worse outcome than recording a failed turn, and it removes the only record that could diagnose a provider failure. It also inverts an ordering that the event stream and the readiness probe both currently assume.

## Consequences

### Positive

1. Turn adjacency holds under concurrent turns on one conversation, because both sequences are allocated under one lock.
2. A generation failure is recorded as a failed turn rather than an orphan, a silent loss, or a degraded success.
3. The outbox event is cancelled in the same transaction as the failure, so memory extraction no longer runs over an unanswered range.
4. A process crash leaves a countable `pending` row instead of an inconsistency that no query can find.
5. The repository gains the ability to express a turn, so the orchestrator stops assembling one.

### Negative

1. A schema migration on `messages`, with a real `downgrade` obligation and an `ALEMBIC_HEAD` update in the same change.
2. A non-terminal `pending` state exists in the transcript. It must be rendered distinctly, and it must be observable, or it becomes a new silent failure mode.
3. A second write after generation whose failure is a new observable condition, not previously distinguishable.
4. The backend and frontend must be deployed together: a new instance writes `pending` rows that an older instance would render as an empty assistant reply. This is a rollout constraint, not a compatibility guarantee.
5. Rollback is ordered. The column cannot be dropped before the orchestrator is reverted, because the old code cannot interpret a `pending` row.
6. Holding the parent lock across two inserts slightly increases the per-conversation lock duration. Cross-conversation throughput is unaffected because the lock is per conversation.

## Migration

**Sequence.** Migration `20260911_01` adds the column with a `complete` default, a check constraint, and an index on `(conversation_id, status)`. `ALEMBIC_HEAD` in `backend/storage/postgres.py:26` is updated in the same change. The repository and service gain the three methods. The orchestrator switches to the two-phase path and the four-transaction path is **removed in the same change**, not retained as a fallback — a fallback would let the defect persist unnoticed. The frontend renders `pending` and `failed`.

**RLS.** `messages` is `FORCE`d. The new column inherits the table's policy; no policy change is required.

**Rollout gate.** The `pending`-row count must be observed at zero in steady state before the change is considered stable. A non-zero steady-state count is an operational signal, not an expected condition.

**Rollback boundary.** Revert the frontend, then the orchestrator, then the repository methods, then the migration. A `pending` row present at rollback time must be reported, because after the rollback no code understands it.

## Validation

1. A test asserts both rows exist and are correctly typed at the moment generation runs.
2. A test asserts that a generation failure leaves a `complete` user row followed by a `failed` assistant row, and that the turn's outbox event is cancelled.
3. A test asserts that a first-turn generation failure returns a conversation id.
4. A concurrency test runs two turns on one conversation and asserts the committed order is `user, assistant, user, assistant` with contiguous sequences.
5. A migration round-trip test asserts the `downgrade` removes the index, the constraint and the column.
6. A steady-state query asserts `SELECT count(*) FROM messages WHERE status = 'pending'` is zero.
7. A query asserts no `complete` row has empty content.

## References

1. Governing spec: `docs/specs/2026-09-11-atomic-chat-turn-and-memory-correctness-design.md` v0.1
2. Implementation plan: `docs/plans/2026-09-11-atomic-chat-turn-and-memory-correctness-implementation.md`
3. Review evidence: `.workbuddy-ai/reports/code-review-2026-09-11.md` (git-ignored local artifact), findings C2 and C14
4. Related ADRs: 0014 (transactional outbox and idempotent memory workers), 0018 (authenticated chat-only product container), 0021 (standalone conversation ownership, route contract, and auto-create behaviour)
5. Extended by: [ADR 0025](./0025-message-status-content-invariant-in-database.md) — the status/content invariant stated here as a model rule is enforced in the database, and the rows that violate it are repaired. Acceptance criterion 7 above was unmet until that change.
6. Extended by: [ADR 0027](./0027-outbox-event-released-only-when-turn-terminal.md) — this record fixes the outbox event to phase one and cancels it only on failure, but never states **when the event becomes consumable**. ADR 0027 adds that fact: an event is claimable only once its turn is terminal. It also corrects the consequence recorded above — the failure-path cancellation could not match an event a worker had already claimed.
