# ADR 0033: A Fenced Worker Stops Without Cancelling the Conversation's Other Events

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-12 |
| Decision owners | Repository owner |
| Scope | Which party holds the authority to cancel a conversation's outbox events, and what a worker does after a write is fenced |
| Governing spec | [Worker Authority: Credential, Lease Time, and Fence Semantics](../specs/2026-09-12-worker-authority-credential-lease-fence-design.md) v0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

A memory write is fenced inside its own transaction: the conversation must still be
active at the expected deletion epoch, and the outbox event must still be leased to
the caller. `check_conversation_fence` and `check_outbox_lease`
(`backend/conversations/postgres_repository.py:1116-1166`) detect six distinct
causes and report each as a sentence:

| Cause | Sentence |
| --- | --- |
| Conversation row absent | `The source conversation is gone.` |
| `retention_state != active` | `The source conversation is no longer active.` |
| Deletion epoch differs | `The source conversation deletion epoch moved.` |
| Outbox row absent | `The source outbox event is gone.` |
| Not leased, or held by another | `The source outbox lease was lost.` |
| Window closed | `The source outbox lease has expired.` |

`_check_fence` (`backend/memory/write_pipeline/postgres.py:514-524`) raises
`FencedWriteError(err)` — one exception type carrying whichever sentence applied. A
caller cannot branch on a sentence, so the worker does not try:

```python
except FencedWriteError as fence_error:
    ...
    self._outbox_repo.cancel_events(           # worker.py:498
        event.conversation_id,
        reason="fenced_by_source_move",
        now=utc_now(),
        lease_owner=self._worker_id,
    )
```

`cancel_events` scoped by `lease_owner` cancels that owner's leased rows **and every
`PENDING` row of the conversation** (`outbox.py:787-798`):

```python
conditions.append(
    or_(
        self._table.c.status == OutboxStatus.PENDING.value,   # unconditional
        and_(
            self._table.c.status == OutboxStatus.LEASED.value,
            self._table.c.lease_owner == lease_owner,
        ),
    )
)
```

The scope was narrowed once already, for a good reason: cancelling *every* leased row
would have destroyed the event the new worker had just claimed. But the `PENDING`
clause was left unconditional, and it is the same mistake in a different place.

The consequence: **a worker that lost its lease cancels every turn's queued
extraction in that conversation.** "Turn 1's lease expired" is a fact about one
worker's tenure. It is not a fact about the validity of turn 2 or turn 3, which are
`PENDING`, untouched, and will never be re-created once cancelled. Valid memory
formation is silently destroyed by an unrelated worker's slowness.

The two cause classes are not alike, and the code already treats them alike in one
place and differently in another. The revalidation path
(`worker.py:239, 256, 273`) cancels unscoped, which is correct there: a conversation
that is gone, deleted, or epoch-advanced has no valid remaining work. The fence path
cancels with the same effect for causes that are not about the conversation at all.

## Decision

**A worker's authority to cancel a conversation's events is determined by the reason
the write was fenced, and the reason for a lease loss is never a reason to cancel.**

Specifically:

1. The six sentences become a typed `FenceReason`: `CONVERSATION_GONE`,
   `CONVERSATION_NOT_ACTIVE`, `DELETION_EPOCH_MOVED`, `OUTBOX_EVENT_GONE`,
   `LEASE_LOST`, `LEASE_EXPIRED`. `check_conversation_fence` and
   `check_outbox_lease` return the enum; their sentences become the exception's
   message, derived from the enum, so logs stay readable and branching stops
   depending on prose. `FencedWriteError` carries the reason as a required
   attribute.
2. One rule, expressed as a predicate on `FenceReason`: **cancel a conversation's
   remaining events only when the cause is a property of the conversation, never
   when it is a property of this worker's tenure.**
3. Conversation-shaped reasons — `CONVERSATION_GONE`, `CONVERSATION_NOT_ACTIVE`,
   `DELETION_EPOCH_MOVED` — may cancel the conversation's pending and leased events.
4. Worker-shaped reasons — `LEASE_LOST`, `LEASE_EXPIRED` — cancel nothing. The event
   stays `LEASED` and becomes reclaimable when its window closes, which is the
   recovery path that already exists.
5. `OUTBOX_EVENT_GONE` cancels nothing: one event's absence says nothing about its
   siblings.
6. **The fence handler in `process_one` cancels nothing at all.** For the
   conversation-shaped reasons, the transaction that invalidated the conversation
   already cancelled its events in the same transaction, so the call matches zero
   rows; for the worker-shaped reasons it would be destructive. The worker's job
   after a fence is to stop.
7. The revalidation path keeps cancelling, because it is the site that *first
   observes* an invalid conversation and no prior transaction has cancelled it. It
   maps its detections onto the same enum and applies the same predicate, so there is
   one rule and two detection sites rather than two policies.
8. `FenceReason` exposes the predicate as a single member, so a future reason cannot
   be added without classifying it.

## Alternatives Considered

### Keep cancelling, but restrict the fence path to `PENDING` rows

**Approach.** Leave the fence handler's call in place and drop the `lease_owner`
scope's leased-row clause, so only `PENDING` rows are cancelled and a peer's lease is
never cleared.

**Benefits.** Preserves the intent the current code was reaching for — stop the
conversation's future work immediately rather than waiting for each lease to expire
— while removing the peer-cancellation hazard the existing scope already fixed.

**Costs.** It still treats one worker's lease loss as a statement about the
conversation. Turn 2 and turn 3 are cancelled because turn 1's worker was slow, which
*is* the defect rather than a mitigation of it. It also leaves two cancellation
policies in the codebase: the fence path's and the revalidation path's.

**Rejected because.** Scoping the blast radius is not the same as holding the right
authority. The reason a write was fenced determines whether cancelling is justified,
and a lease loss never justifies it.

### Branch inside the fence handler: cancel for conversation-shaped reasons, not for lease-shaped ones

**Approach.** Keep the fence-path cancellation, but gate it on the new typed reason,
cancelling only when the reason is a property of the conversation.

**Benefits.** Closest to the selected design and conservative: it leaves the call in
place for the cases where cancelling is legitimate, so if a deletion ever *did* leave
events behind, the worker repairs it.

**Costs.** For every conversation-shaped reason, the cancelling transaction is the
one that made the conversation invalid, and it cancels in the same transaction that
invalidates it. The branch therefore matches zero rows on every path that can reach
it. That is dead code whose presence asserts an authority the worker does not
exercise — and dead code in a security-relevant path is where the next reader
misreads the design.

**Rejected because.** The invariant it hedges against — "a deletion might not cancel
its own events" — is the invariant ADR 0023 and ADR 0027 establish. If that invariant
is false, the correct response is to fix the deletion path, not to add a second
canceller that will never fire. The plan verifies the invariant by observation before
the fence-path call is removed.

### Leave the behaviour as it is

**Approach.** Accept that a lease loss cancels the conversation's queued work.

**Benefits.** No change.

**Costs.** A slow worker permanently destroys valid memory formation for unrelated
turns, and the loss is silent: the events move to `CANCELLED`, which is a legitimate
terminal state indistinguishable from a deliberate cancellation. Nothing records that
the cause was an unrelated lease loss.

**Rejected because.** It converts a worker-latency problem into permanent, invisible
data loss. The events that die are precisely the ones the review's own framing says
must survive.

### Cancel by conversation on any fence, and let the deletion path be idempotent

**Approach.** Keep the unscoped call for every fence cause, relying on the deletion
path's cancellation being idempotent so the double-cancel is harmless.

**Benefits.** One code path, no branching, no new vocabulary.

**Costs.** It is harmless only for the deletion-shaped causes. For a lease loss it is
exactly the destructive behaviour being removed, and a lease loss is one of the six
causes this single path handles.

**Rejected because.** "Harmless because the other path already did it" is true for
three of six causes and false for the three that motivated this ADR.

## Consequences

**Positive.**

- A lease loss is contained to the worker that experienced it. Turn 2's and turn 3's
  extraction survives, which is the direct regression this ADR exists to prevent.
- Cancellation authority has one rule and one predicate, applied at both detection
  sites, so a future reason must be classified before it can be used.
- The fence's reasons become countable, which is the prerequisite for a `lease_lost`
  counter that actually counts.
- The worker's post-fence behaviour is "stop", which is the only action it has
  authority for.

**Negative.**

- `FencedWriteError` gains a required attribute, so every construction site must
  supply a reason. Test doubles and any other raiser must be updated.
- The two repositories' signatures change to return an enum rather than a
  `(bool, str)` pair, which touches the fence's call sites and their tests.
- If the invariant "the deleting transaction cancels the conversation's events" is
  ever broken, the worker will no longer mask it. That is intentional — a masked
  invariant is one nobody can verify — but it means the plan must confirm the
  invariant before removing the call.
- An event whose worker lost its lease now stays `LEASED` until its window closes
  rather than being cancelled immediately, so a stuck conversation recovers on lease
  expiry instead of on the fence. That is the existing recovery path, but it is
  slower than the current immediate cancellation for the case where the worker was
  right to stop.

**Neutral.**

- No schema change and no migration.
- The revalidation path's behaviour is unchanged in effect; only its vocabulary and
  its predicate are shared.
- The `CANCELLED` status and the `reason` string written to `last_error` are
  unchanged; the reason now originates from an enum rather than a literal.

## References

1. [ADR 0014: Transactional outbox and idempotent memory workers](./0014-transactional-outbox-and-idempotent-memory-workers.md)
2. [ADR 0023: Atomic two-phase chat turn](./0023-atomic-two-phase-chat-turn.md)
3. [ADR 0027: An outbox event is released only when its turn is terminal](./0027-outbox-event-released-only-when-turn-terminal.md)
4. [ADR 0032: An outbox lease is judged valid against database time, and held by a process identity](./0032-lease-validity-is-database-time.md)
5. [Worker Authority: Credential, Lease Time, and Fence Semantics](../specs/2026-09-12-worker-authority-credential-lease-fence-design.md) — governing specification
