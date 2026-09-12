# ADR 0027: An Outbox Event Is Released Only When Its Turn Is Terminal

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-11 |
| Decision owners | Repository owner |
| Scope | `conversation_outbox` readiness, the two-phase chat turn, and the memory worker's claim and read contracts |
| Governing spec | [Outbox Turn-Readiness Barrier](../specs/2026-09-11-outbox-turn-readiness-barrier-design.md) v0.1 (Approved) |
| Superseded ADR | None |
| Supersedes | Extends [ADR 0023](./0023-atomic-two-phase-chat-turn.md); see the note below |

**Extends, does not supersede.** ADR 0023 remains correct: phase one still commits the
user message, the `pending` assistant row and the outbox event in one transaction, and
phase two still fills the assistant row under a `status = 'pending'` guard. This record
adds the fact ADR 0023 left open — **when the event becomes consumable** — and corrects
one of its consequences.

## Context

A transactional outbox must write the event in the same transaction as the message.
ADR 0023 did that, and it was right to. But "written atomically with the message" and
"ready to be consumed" are different facts, and the schema recorded only the first.

The consequence was measured against the real database on 2026-09-11:

1. The event is claimable from the instant of commit, while the assistant row is still
   `pending`. `claim_batch` returned it and marked it `leased`.
2. The failure-path cancellation cannot undo that. `_cancel_turn_outbox` matches
   `status = 'pending'` only, so once a worker has claimed the event the cancellation
   matches nothing. Measured: after `fail_turn`, the row was still `leased`.
3. `_load_messages` filters by `sequence` alone, so the extraction model received two
   assistant rows whose content was the empty placeholder.
4. No cursor is stamped, so a single new turn loaded the entire conversation.

ADR 0023 asserted the intent — *"A turn that produced no reply must not cause
extraction over an unanswered range"* — and implemented it only on the failure path,
where it also does not hold under contention. The intent was right; the mechanism could
not deliver it.

## Decision

**An outbox event carries an explicit readiness fact, and it is claimable only when
that fact says it is released.**

`conversation_outbox` gains a nullable `released_at` column:

1. **Allocation writes it `NULL`.** Phase one writes the event blocked. The row records
   that work is owed, not that it is ready.
2. **Completion releases it.** `_transition_turn`, the single choke point through which
   an assistant row becomes terminal, sets `released_at` in the same transaction that
   sets the assistant row to `complete`.
3. **Failure cancels it**, unchanged in intent and now correct in effect: because a
   blocked event can never have been leased, the cancellation always matches.
4. **Claim requires it.** `claim_event` and `claim_batch` treat a row with
   `released_at IS NULL` as ineligible, whatever its status.
5. **The read is narrowed.** The worker discards any message that is not `complete`, as
   a second independent layer behind the gate.
6. **The range is bounded.** Allocation stamps `payload["after_sequence"]` with the
   sequence immediately preceding the turn's user message.

The readiness fact is deliberately **not** a new `OutboxStatus` value. Where an event
sits in its retry lifecycle and whether its turn has finished are independent, and
merging them would make every future status transition carry a hidden second meaning.

## Alternatives Considered

### Alternative A — Add a `blocked` value to `OutboxStatus`

**Approach.** Phase one writes `status = 'blocked'`; completion transitions it to
`pending`; the claim query ignores `blocked`.

**Benefits.** The readiness is visible in the status column alone, and no column is
added.

**Costs.** It redefines a lifecycle ADR 0014 governs and that existing tests assert. A
blocked event that later needs a retry would have to express lifecycle and readiness
simultaneously in one field.

**Rejected because** the two facts are orthogonal, and the conflation would outlive
this change.

### Alternative B — Derive readiness by joining to `messages` at claim time

**Approach.** Require the assistant row correlated to the event to be terminal, with no
new column.

**Benefits.** No migration, and readiness cannot drift from the message state because it
is computed from it.

**Costs.** The correlation is positional (`sequence + 1`), so correctness would rest on
an adjacency invariant rather than a key. It adds a join to the claim hot path, and it
leaves the failure path still racing a claim.

**Rejected because** it does not fix the cancellation race, and it makes the queue's
correctness depend on positional adjacency.

### Alternative C — Release gate column

**Approach.** Add `released_at`; allocate blocked, release on completion, cancel on
failure, require the gate to claim.

**Benefits.** One nullable column, one predicate, one index. The release fact is
explicit and auditable. The status vocabulary and ADR 0014 are untouched. It makes the
cancellation race impossible rather than unlikely.

**Costs.** One more column, and a future writer must remember to set it.

**Selected**, with the mitigation that both release and cancel live in `_transition_turn`
rather than at call sites.

## Consequences

**Positive.**

- The worker can be mounted without extracting from an unfinished turn, which was the
  blocking defect for the memory milestone.
- The failure-path cancellation now holds under contention, because a blocked event
  cannot be leased before it is released.
- The extraction model no longer receives placeholder assistant turns.
- Extraction input is bounded to the turn's range instead of the whole conversation,
  which reduces cost and duplicate candidates.
- The audit trail can distinguish "work owed" from "work ready" after the fact.

**Negative.**

- A turn abandoned while `pending` leaves its event blocked indefinitely. That is the
  intended fail-closed behaviour, but it means the readiness of the queue now depends on
  the generation path completing turns. The disclosure is a blocked-age signal, and
  automatic reconciliation of a stuck turn remains out of scope.
- One more column and one more invariant for future writers to honour.

**Neutral.**

- No public API change. `POST /api/v1/chat` keeps its request and response contract.
- Neither memory feature gate changes. This record makes the contract correct; it does
  not enable the pipeline.
- ADR 0014's lease, retry and back-off semantics are unchanged.

## References

1. [ADR 0023](./0023-atomic-two-phase-chat-turn.md) — atomic two-phase chat turn; extended by this record.
2. [ADR 0014](./0014-transactional-outbox-and-idempotent-memory-workers.md) — transactional outbox and idempotent memory workers.
3. [ADR 0016](./0016-focused-memory-write-evaluation-and-rollout.md) — the gates that keep the pipeline off.
4. [Outbox Turn-Readiness Barrier](../specs/2026-09-11-outbox-turn-readiness-barrier-design.md) — governing specification.
5. Extended by: [ADR 0028](./0028-worker-role-and-outbox-claim-boundary.md) — the worker role and the outbox claim boundary. That record decides which role may claim a released event; this record's gate is unchanged and is a precondition of the claim.
