# ADR 0036: Chat-native Memory Actions and Dual Transaction Coordinators

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-12 |
| Decision owners | Repository owner |
| Scope | Explicit Chat-native Memory mutation authority, API/worker transaction ownership, shared store seams, fencing, idempotency, and canonical lock ordering |
| Governing spec | `docs/specs/2026-09-12-agent-memory-target-architecture-design.md` v0.2 (Approved 2026-09-12) |
| Superseded ADR | Not applicable |
| Superseded by | Not applicable |

## Context

The product has intentionally removed the separate public Memory-management
surface. Explicit remember, correct, and forget actions therefore have to travel
through the normal authenticated Chat turn without turning ordinary statements
into mutation authority.

The repository also has two different execution owners. The API owns the
synchronous Chat turn, while the Memory worker owns background extraction work.
Both may eventually produce the same canonical semantic Memory effect, but their
fences and terminal states are different. The API must preserve the existing
guarded `PENDING -> terminal` turn transition. The worker must additionally
prove that its outbox lease is still valid.

A durable boundary is required because independently committing conversation,
Memory, acknowledgement, and source-handling state can expose a Memory effect
that the user never sees acknowledged, or can acknowledge an effect that later
rolls back.

## Decision

Explicit Memory mutation remains Chat-native and is authorized in two steps:

1. `TurnUnderstanding` may interpret the semantic intent and payload.
2. `ExplicitIntentGate` must deterministically corroborate the explicit
   remember/correct/forget speech act before any durable mutation is allowed.

A bounded structured model call may help normalize an already-authorized
payload, but model output alone never authorizes a durable write.

Two transaction coordinators are intentionally separate:

```text
ExplicitMemoryTurnCommit
    API-owned transaction

BackgroundMemoryCommit
    worker-owned transaction
```

`ExplicitMemoryTurnCommit` commits one explicit action atomically on one caller-
owned PostgreSQL transaction/connection:

1. canonical Memory evidence/decision/lifecycle effect;
2. the stable semantic idempotency result;
3. the family-specific `SourceHandlingRecord`;
4. the deterministic assistant acknowledgement row; and
5. the guarded terminal turn/outbox transition.

If any step fails, none of those effects becomes visible.

`BackgroundMemoryCommit` owns a different transaction. It commits the fenced
background Memory effect, stable idempotency result, and source-event terminal
transition only after the worker proves its lease and source fences are still
valid.

The two coordinators share pure consolidation/lifecycle logic and a
transaction-aware `MemoryWriteStore`. They do not call each other and are not
collapsed into one mode-switched coordinator.

Conversation and Memory adapters expose caller-owned transaction seams rather
than opening nested independent commits. The coordinator must call those domain
seams; it must not reproduce their concurrency or idempotency rules with ad hoc
SQL. In particular, the Conversation side preserves the existing conditional
turn transition and `TransitionResult.applied` behavior.

Both coordinators use the same shared primitives and lock order:

```text
bind tenant
-> validate/lock conversation + deletion_epoch
-> worker only: validate/lock outbox lease
-> validate/lock Memory rows
```

Canonical row-lock order is therefore:

```text
conversation
-> outbox (worker only)
-> memory rows
```

The API path never claims worker authority. The worker path never gains
authority to complete or acknowledge an API turn.

## Alternatives

### One generic transaction coordinator with an execution-mode flag

This reduces the number of classes, but it combines API acknowledgement rules
with lease/retry/fence rules and makes it easy for one mode to accidentally
inherit the other's authority. Rejected. Sharing the smaller primitives and
pure domain logic gives reuse without merging trust boundaries.

### Let repositories keep their own independent transactions

This preserves current adapter encapsulation, but cannot atomically couple a
Memory effect with acknowledgement and guarded turn completion. Compensation
would still leave failure windows. Rejected.

### Let the model decide whether a turn is an explicit Memory command

This is flexible for language variation, but a parser/classifier false positive
would become mutation authority. Rejected. Model interpretation may support the
decision, not grant it.

### Restore a dedicated Memory API/UI for explicit actions

This makes mutation intent easy to identify, but reverses ADR 0020 and fragments
the Chat-first product behavior. Rejected.

## Consequences

### Positive

1. Explicit Memory mutation and its user-visible acknowledgement share one
   atomic outcome.
2. API and worker authority remain separate while reusing the same canonical
   Memory domain and storage primitives.
3. One lock order makes deadlock analysis and concurrency testing bounded.
4. Existing turn concurrency/idempotency guards remain the authority instead of
   being bypassed by coordinator-specific SQL.
5. Model mistakes cannot directly authorize durable Memory mutation.

### Negative

1. Conversation and Memory repositories need transaction-aware seams that can
   operate on a caller-owned connection.
2. The application layer gains two explicit transaction coordinators.
3. Tests must cover rollback across modules, lock ordering, stale fences, and
   duplicate idempotency keys rather than only isolated repository behavior.
4. Acknowledgement text for explicit actions must be deterministic enough to be
   recreated safely under idempotent retry.

## Migration

Introduce the shared transaction primitives and caller-owned store seams before
mounting Chat-native explicit mutation. Keep background processing on its current
worker path until `BackgroundMemoryCommit` has the same fence and idempotency
coverage.

Do not enable a fallback that independently commits Memory and acknowledgement.
Rollback disables the new explicit action routing and leaves the existing normal
Chat path intact. Existing worker leases/outbox work remain governed by their
accepted worker ADRs.

## Validation

1. A remember/correct/forget test proves one transaction contains Memory effect,
   idempotency, source handling, acknowledgement, and guarded terminal turn state.
2. Forced failure at each commit step leaves no partial explicit Memory effect.
3. Duplicate explicit retries return the same semantic result without a second
   mutation.
4. A stale conversation deletion epoch blocks both explicit and background
   commit.
5. A stale worker lease blocks background commit but does not cancel unrelated
   events.
6. Concurrency tests prove the canonical lock order and no cross-order deadlock.
7. Tests prove model output without `ExplicitIntentGate` authority cannot mutate
   Memory.
8. Import/dependency checks prove RAG and provider clients do not own either
   transaction boundary.

## References

1. [Agent Memory Target Architecture](../specs/2026-09-12-agent-memory-target-architecture-design.md) v0.2.
2. [ADR 0014](./0014-transactional-outbox-and-idempotent-memory-workers.md).
3. [ADR 0017](./0017-risk-based-memory-confirmation.md) as superseded historical input for explicit-action risk and confirmation semantics preserved through ADR 0020.
4. [ADR 0020](./0020-removal-of-public-memory-management-surface.md).
5. [ADR 0023](./0023-atomic-two-phase-chat-turn.md).
6. [ADR 0027](./0027-outbox-event-released-only-when-turn-terminal.md).
7. [ADR 0031](./0031-the-idempotency-key-is-reserved-before-the-effect.md).
8. [ADR 0032](./0032-lease-validity-is-database-time.md).
9. [ADR 0033](./0033-a-fenced-worker-stops-without-cancelling.md).
