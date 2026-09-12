# Outbox Turn-Readiness Barrier: Release an Extraction Event Only After Its Turn Is Terminal

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-11 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | `conversation_outbox` readiness contract, the two-phase chat turn, and the memory worker's claim and transcript-read contracts |
| Related issue | Outbox race reported by the repository owner on 2026-09-11 |
| Superseded document | None |

## Summary

A memory-extraction outbox event is **claimable from the instant its turn is
committed**, while the assistant message for that same turn is still `pending`.
A worker that polls at the wrong moment extracts memory from an unfinished turn.
This was reproduced against the real database, not inferred.

Four distinct defects were measured. They share one cause: **the outbox row
records that work is owed, but records nothing about whether the work is ready.**

| # | Defect | Evidence |
| --- | --- | --- |
| D1 | The event is claimable before the turn is terminal | `claim_batch` returned the event while the assistant row was `pending` |
| D2 | The existing failure-path cancellation **loses the race** | after `fail_turn`, the row was still `leased` under the probe worker; `_cancel_turn_outbox` only matches `status = 'pending'` |
| D3 | The worker hands the model unfinished turns | `_load_messages` returned **2 assistant rows with empty content** |
| D4 | Every turn re-extracts the whole conversation | no cursor in the payload; one new turn loaded 4 rows, the entire conversation |

**Not a live incident.** `MEMORY_SHADOW_EXTRACT_ENABLED` defaults `False`, so the
orchestrator writes no outbox row at all; `MemoryOutboxWorker` is instantiated only
in tests; `docker-compose.yml` defines no worker service. The defects activate the
moment the worker is mounted, which is why they are a blocker rather than a note.

## Context

`docs/adr/0023-atomic-two-phase-chat-turn.md` established the two-phase turn: phase
one commits the user message, a `pending` assistant row and the outbox event
together; phase two fills the assistant row. That ADR states plainly:

> **Explicitly out of scope of this decision.** The recorder's shadow-only invariant
> is unchanged. The outbox lease, retry and back-off semantics are governed by ADR
> 0014 and are unchanged.

It also states the intent the code does not achieve:

> A turn that produced no reply must not cause extraction over an unanswered range.

The code satisfies that intent only on the **failure** path, and only when no worker
has already claimed the event. It has no mechanism for the success path, and none for
the window between commit and completion.

The claim query filters on outbox state alone
(`backend/memory/write_pipeline/outbox.py:453-479`, `:386-408`). It never consults
`messages`. There is no `blocked` or `pending_turn` state, and no release gate.

## Users

1. **The repository owner**, who must be able to mount the memory worker without the
   worker extracting from turns that have no reply.
2. **The memory worker**, which needs an unambiguous "this turn is finished" signal
   instead of inferring it from a sequence number.
3. **A later reader of the audit trail**, who must be able to tell why an event was
   claimable at a given time.

## Problem Statement

**The outbox row expresses obligation without expressing readiness.** Phase one must
write the event in the same transaction as the message — that is the whole point of a
transactional outbox, and it is correct. But "written atomically with the message"
is not the same as "ready to be consumed", and the schema cannot distinguish them.

**The existing mitigation cannot work, by construction.** `_cancel_turn_outbox` runs
on the failure path and matches `status = 'pending'`
(`backend/conversations/postgres_repository.py:855-863`). A worker that claimed the
event first has already moved it to `leased`, so the cancellation matches nothing. The
guard protects exactly the case that cannot happen and misses the one that can.

**The worker's read contract is wider than its intent.** `_load_messages`
(`backend/memory/write_pipeline/worker.py:536-582`) filters by `sequence` only. It
returns `pending` assistant rows, whose content is the empty placeholder, and hands
them to the extraction model as if they were real turns.

**Why now.** The memory milestone mounts the worker. Every defect here becomes live at
that moment, and all four are cheapest to fix before the worker exists rather than
after it has written to `memory_evidence`.

## Goals

1. An outbox event must not be claimable until the turn that produced it is terminal.
2. The success path must release the event in the same transaction that completes the
   assistant row.
3. The failure path must cancel the event in the same transaction that fails the
   assistant row, and must succeed even though the event may be old.
4. The worker must never present a non-terminal message to the extraction model.
5. The worker must read a bounded range, not the whole conversation, for each event.
6. Existing rows must migrate without losing work or inventing readiness.

## Non-goals

1. Mounting the worker, adding a worker service, or changing either feature gate. This
   specification makes the contract correct; it does not enable the pipeline.
2. Changing the memory activation policy, the registry, or the shadow-only invariant.
3. Adding a status value to `OutboxStatus`. The release gate is a separate fact from
   the event's lifecycle state, and conflating them would redefine a state machine
   that ADR 0014 governs and that existing tests assert.
4. Retrying, dead-lettering, or reconciling a turn whose assistant row stays `pending`
   forever. That is a separate recovery concern; this change makes such a turn
   *inert* rather than harmful.
5. Any public API change. `POST /api/v1/chat` keeps its contract.

## Assumptions

1. `_transition_turn` is the single choke point through which an assistant row becomes
   terminal. Falsified if another writer sets `messages.status` directly.
2. The outbox row for a turn is correlated to the assistant row by the user message at
   `sequence - 1`. This is the same correlation `_cancel_turn_outbox` already relies on.
3. A released event whose turn later becomes irrelevant is still protected by the
   existing conversation-retention and deletion-epoch revalidation in the worker.

## User and System Flows

### Flow 1 - Turn allocation (changed)

1. Phase one opens one transaction under the parent-row lock.
2. It inserts the user message as `complete`.
3. It inserts the assistant row as `pending`.
4. It inserts the outbox row with `released_at = NULL`, and stamps
   `payload["after_sequence"]` with the sequence immediately before the user message.
5. Commit. The event exists and is **not** claimable.

### Flow 2 - Turn completion (changed)

1. Phase two runs `_transition_turn` with `COMPLETE`.
2. In that transaction, the assistant row's `status` becomes `complete`.
3. In the same transaction, the turn's outbox row gets
   `released_at = now() WHERE released_at IS NULL`.
4. Commit. The event is now claimable, and only now.

### Flow 3 - Turn failure (changed in effect)

1. Phase two runs `_transition_turn` with `FAILED`.
2. In that transaction, the assistant row becomes `failed` and the outbox row becomes
   `cancelled`.
3. Because a blocked event can never have been leased, the cancellation now matches.
   The D2 race cannot occur.

### Flow 4 - Worker claim (changed)

1. The worker calls `claim_batch` or `claim_event`.
2. The query requires `released_at IS NOT NULL` in addition to the existing status,
   backoff and lease conditions.
3. A blocked event is invisible to the worker regardless of its status.

### Flow 5 - Worker transcript read (changed)

1. The worker resolves `after_sequence` from the payload.
2. It loads messages in that range.
3. It discards any message whose status is not `complete`.
4. Only the remaining messages reach the extraction model.

## Behavioral and Data Contracts

### `conversation_outbox.released_at`

- **Type.** `timestamptz`, nullable. `NULL` means blocked; a value means released.
- **Writers.** Set non-NULL only by the turn-completion path, and at insert time for a
  message that is already terminal.
- **Idempotence.** Releasing an already-released event must not move the timestamp.
- **Invariant.** A row with `status = 'pending'` and `released_at IS NULL` is blocked.
  A row with `status = 'cancelled'` is inert whatever `released_at` says.

### Claim eligibility

An event is claimable only when **all** hold:

- `status = 'pending'` (or `status = 'leased'` with an expired lease),
- `released_at IS NOT NULL`,
- `next_attempt_after IS NULL OR next_attempt_after <= now`,
- no live lease on the same conversation.

### Transcript read

`_load_messages` returns only messages whose status is `complete`. `pending` and
`failed` rows are excluded. This is a second, independent layer: the release gate is
the primary control, and this filter holds even if the gate is bypassed.

**A message that declares no status is treated as `complete`,** because that is what the
domain model already decides: `Message.__post_init__` coerces an absent status to
`MessageStatus.COMPLETE` (`backend/conversations/models.py:274-275`). The worker consumes
that model, so inventing a stricter rule for the same data would mean one message is
`complete` to the repository and not-complete to the worker. In production the case is
unreachable — a persisted `Message` always carries a coerced status — so the choice is
observable only through test doubles, and consistency with the model being consumed is
worth more there than an abstract preference for failing closed.

### Event payload

The payload of an event written by turn allocation carries `after_sequence`, equal to
one less than the user message's sequence. A worker that finds no `after_sequence`
retains today's behaviour of reading from the beginning, so the change is additive.

## Errors and Edge Cases

1. **A turn completes twice.** The second transition is a no-op, guarded by
   `status = 'pending'`. The release must also be a no-op; expected: `released_at`
   keeps its first value.
2. **A turn fails after being released.** Impossible: release and completion share one
   transaction, and the transition is guarded.
3. **A turn is abandoned while `pending`.** The event stays blocked forever. Expected:
   no extraction, and the row ages visibly. A blocked-age metric is the disclosure.
4. **An event is written for an already-terminal message** (the generic append path).
   Expected: released at insert, so today's behaviour is preserved.
5. **A pre-existing row from before this change.** Expected: released by the backfill,
   whatever its status, because it was written under a contract in which readiness was
   implied. A `leased` row left blocked would be permanently unreclaimable.
6. **The payload already carries `after_sequence`.** Expected: the stamped value wins,
   because the repository owns sequence allocation.
7. **A message row has no `status`.** Expected: treated as `complete`, matching the
   domain model's own coercion. Reachable only through a test double; a persisted
   `Message` always carries a status.
8. **Migration downgrade.** Expected: the column is dropped, and the pre-change
   behaviour returns.

## Security and Privacy

No new trust boundary and no new data class. The change reduces the amount of content
that reaches a model: an unfinished or failed turn no longer contributes transcript
text to extraction. Owner scoping, RLS, retention and deletion-epoch revalidation are
untouched, and the release gate does not weaken any of them.

## Observability and Operations

The change adds one operational signal worth emitting: the count and age of rows with
`status = 'pending'` and `released_at IS NULL`. A rising value means turns are being
allocated and never completed, which is a generation-path problem rather than a memory
problem, and today it would be invisible.

## Capacity, Latency, and Cost

The claim query gains one predicate on a column carried by a new index; the added cost
is one index lookup on a small table. The transcript filter reduces extraction input,
so the change is expected to reduce model cost rather than raise it. No new round trip.

## Compatibility and Staged Migration

The column is additive and nullable, so the change is backward compatible for readers.
The migration:

1. adds `released_at`, nullable, no default;
2. backfills `released_at = created_at` for **every** existing row, not only `pending`
   ones, because every existing row was written under a contract in which readiness was
   implied by the status alone;
3. adds an index supporting the claim path.

The backfill deliberately covers `leased` rows as well. A `leased` row left with
`released_at IS NULL` would be permanently unreclaimable, because the claim query's
lease-expiry branch also requires the gate. Such a row could never be recovered by lease
expiry, so it would be stuck rather than merely delayed. Backfilling every row keeps the
migration's effect limited to rows written after it.

Ordering: the migration must be applied before the code that requires the gate, or the
claim query would reference a column that does not exist. The reverse order is safe.

## Failure and Recovery

| Failure | Behaviour | Recovery |
| --- | --- | --- |
| Release never runs because the process died mid-turn | Event stays blocked | Re-run or reconcile the turn; no extraction occurs in the meantime |
| Assistant row stays `pending` forever | Event stays blocked and ages | Owner-visible via the blocked-age signal; no automatic repair in this change |
| Migration backfill misclassifies a row | A pre-existing event becomes claimable | Accepted: that was its state before the change |
| Claim query deployed before migration | Query fails loudly on a missing column | Apply the migration first, as stated above |

## Required ADRs

1. **ADR 0027 — "An outbox event is released only when its turn is terminal."** This
   amends ADR 0023, which fixed the outbox to phase one and cancelled it only on
   failure. The decision is durable: other components read the outbox contract, and a
   later worker, admin view or metric must honour the gate.

No second ADR is required. The change introduces no new component, no new trust
boundary, and no new store.

## Alternatives Considered

### Alternative A — Add a `blocked` value to `OutboxStatus`

**Approach.** Phase one writes `status = 'blocked'`; completion transitions it to
`pending`; the claim query ignores `blocked`.

**Benefits.** The state is visible in the status column alone, with no extra column.

**Costs.** It redefines a lifecycle that ADR 0014 governs and that existing tests
assert, and it conflates two independent facts: *where the event is in its retry
lifecycle* and *whether its turn is finished*. A blocked event that later needs a retry
would have to express both at once.

**Rejected because** the release fact is orthogonal to the lifecycle fact, and merging
them makes every future status transition carry a hidden second meaning.

### Alternative B — Derive readiness from the assistant message at claim time

**Approach.** Join the outbox row to `messages` and require the linked assistant row to
be terminal. No new column.

**Benefits.** No migration, and readiness cannot drift from the message state, because
it is computed from it.

**Costs.** The correlation is positional — the assistant row sits at the user message's
`sequence + 1` — so the join depends on an adjacency invariant rather than a key. It
puts a join on the claim hot path, and it leaves the failure path relying on
cancellation that still races a claim.

**Rejected because** it makes the queue's correctness depend on a positional
correlation, and it does not fix D2.

### Alternative C — Release gate column (selected)

**Approach.** Add `released_at`. Phase one writes `NULL`; completion sets it; failure
cancels. The claim query requires it.

**Benefits.** One nullable column, one predicate, one index. The release fact is
explicit and auditable. It does not touch the status vocabulary, so ADR 0014 and its
tests are undisturbed. It makes D2 impossible rather than merely unlikely, because a
blocked event can never be leased, so the cancellation always matches.

**Costs.** One more column, and one more thing a future writer must remember to set.
Mitigated by putting both release and cancel in `_transition_turn`, the single choke
point for terminal transitions.

**Selected.**

## Current-state Evidence

| Claim | Evidence path | Verified how |
| --- | --- | --- |
| Phase one writes the outbox row as claimable `pending` | `backend/conversations/postgres_repository.py:642-693`, `:257-287`, `:519-542` | direct read |
| The claim query never consults `messages` | `backend/memory/write_pipeline/outbox.py:453-479`, `:386-408` | direct read |
| A worker can claim while the assistant is `pending` | — | **executed**: `claim_batch` returned the event, status became `leased` |
| Cancellation cannot match a leased event | `backend/conversations/postgres_repository.py:855-863` | direct read, and **executed**: `cancellation succeeded: False` |
| `_load_messages` does not filter by status | `backend/memory/write_pipeline/worker.py:536-582` | direct read, and **executed**: 2 empty assistant rows returned |
| The orchestrator never sets `after_sequence` | `backend/orchestration/conversation_orchestrator.py` | direct read |
| The worker is not mounted | `backend/app/runtime_container.py:219-235`; `docker-compose.yml` | repository-wide search |
| The gates default off | `backend/app/config.py:84-86` | direct read |

**Not verified.** No worker has been run against a live queue, because none is
mounted; the reproduction drove `claim_batch` and `_load_messages` directly. The
backfill is designed but not yet executed against production-shaped data. The claim
query's index usage is asserted by construction, not by an executed plan analysis.

## Components and Dependency Direction

```text
HTTP chat route
-> ConversationOrchestrator
-> ConversationService / PostgresConversationRepository   (writes released_at)
-> conversation_outbox table

memory worker process
-> PostgresOutboxRepository.claim_*   (requires released_at)
-> ConversationService.get_messages_in_range   (complete rows only)
-> MemoryFormationEngine
```

**Allowed dependency direction.** The worker depends on the outbox and conversation
read contracts. The conversation repository must not depend on the worker, and the
outbox table must not learn about memory semantics.

**Ownership.** The conversation repository owns the release gate and the cursor stamp.
The outbox repository owns claim eligibility. The worker owns its transcript filter.

## Data Flow and Lifecycle

```text
allocate turn      -> outbox row: pending,  released_at = NULL   (blocked)
complete turn      -> assistant: complete; outbox: released_at = now
fail turn          -> assistant: failed;   outbox: cancelled
worker claim       -> only released rows are visible
worker read        -> only complete messages are extracted
```

## Approval Record

| Field | Value |
| --- | --- |
| Version | 0.1 |
| Status | Approved - authorized by the repository owner |
| Approver role | Repository owner |
| Date | 2026-09-11 |
| Approval basis | The owner instructed implementation of the reported outbox defects after the fix shape was presented. Recorded as: "Triển khai fix hết cho tôi" (2026-09-11). |
| Authorization boundary | Authorizes preparation of the implementation plan at `docs/plans/2026-09-11-outbox-turn-readiness-barrier-implementation.md` and its execution. Does not authorize enabling either memory feature gate, mounting a worker, adding a worker service, changing the memory activation policy, or any Git delivery. |

Approval of this specification authorizes the readiness barrier and the three
accompanying contract fixes. It does **not** authorize turning the memory pipeline on.
