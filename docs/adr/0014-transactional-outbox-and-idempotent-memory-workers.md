# ADR 0014: Transactional Outbox and Idempotent Memory Workers

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-07 |
| Decision owners | Repository owner |
| Scope | Background write triggering, delivery, leasing, retry, cancellation, concurrency, and derived indexing |
| Governing spec | [Basic Semantic Memory Write Pipeline Design](../specs/2026-09-07-basic-semantic-memory-write-pipeline-design.md), version 0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

Normal chat must not wait for model-backed extraction, but message persistence
and work scheduling cannot diverge. External model calls prevent a single
exactly-once transaction across the full pipeline.

## Decision

Commit source messages and outbox intent atomically in PostgreSQL. Deliver work
at least once through typed handlers on one database-backed worker runtime.
Claim work in a short transaction using `lease_owner` and `lease_until`, call
models outside the transaction, and revalidate owner, source lifecycle,
deletion epoch, idempotency, and versions before commit.

Use states `PENDING`, `LEASED`, `SUCCEEDED`, `DEAD_LETTER`, and `CANCELLED`.
Retry by job/failure class with bounded exponential backoff and jitter. Serialize
only by natural mutation identity. Derived indexes update asynchronously and
must be revalidated against canonical PostgreSQL state.

## Alternatives

### Synchronous extraction in chat

Simpler delivery but adds model latency and provider availability to chat.
Rejected.

### Kafka or Redis/RabbitMQ immediately

Provides dedicated queue features but adds a second operational authority and
cross-system delivery problem before measured need. Deferred.

### PostgreSQL transactional outbox

Requires lease, cleanup, and queue metrics but matches the target scale and
keeps source state plus work intent atomic. Selected.

## Consequences

### Positive

1. Chat remains independent from background model latency.
2. Lost work and duplicate delivery have explicit recovery semantics.
3. Search projections remain rebuildable.

### Negative

1. Workers may repeat expensive work before idempotent commit.
2. PostgreSQL carries queue load and operational cleanup.
3. Lease, retry, dead-letter, fairness, and deletion cancellation need tests and
   runbooks.

## Migration

Enable capture and workers behind separate gates. Do not dual-write to an
external broker. Preserve outbox evidence when workers are stopped or rolled
back.

## Validation

Prove message/outbox atomicity, redelivery idempotency, lease expiry,
same-identity serialization, cross-owner parallelism, retry classification,
dead-letter, cancellation, deletion-epoch rejection, and chat non-blocking.

## References

1. Governing focused specification.
2. [Debezium outbox pattern](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html).
3. Extended by: [ADR 0027](./0027-outbox-event-released-only-when-turn-terminal.md) — an outbox event is released only when its turn is terminal. This record's lease, retry and back-off semantics are unchanged.
4. Extended by: [ADR 0028](./0028-worker-role-and-outbox-claim-boundary.md) — the worker role and the outbox claim boundary. This record established the outbox and its worker; that record decides which role claims and what it may see.
5. Extended by: [ADR 0031](./0031-the-idempotency-key-is-reserved-before-the-effect.md) — the idempotency key is reserved before the semantic effect it guards. This record required an idempotent worker; that record makes the key enforce its effect instead of racing.
