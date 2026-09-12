# ADR 0031: The Idempotency Key Is Reserved Before the Semantic Effect It Guards

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-12 |
| Decision owners | Repository owner |
| Scope | The order in which the idempotency row and the semantic rows are written, and what happens on a key conflict |
| Governing spec | [Memory Worker Runtime](../specs/2026-09-12-memory-worker-runtime-design.md) v0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

`PostgresMemoryUnitOfWork.apply_memory_change` writes the semantic rows first —
assertion, version, evidence, decision, event, outbox (`postgres.py:441-457`) — and
records the idempotency key last, in `_record_idempotency` (`:741-779`):

```python
try:
    with connection.begin_nested():
        connection.execute(idempotency_table.insert().values(...))
except sa_exc.IntegrityError:
    # A concurrent redelivery recorded first; its result stands.
    existing = connection.execute(select(...)).mappings().fetchone()
    if existing is None or existing["owner_user_id"] != owner:
        raise
```

The savepoint stops a duplicate key from poisoning the transaction. It does not
stop the transaction from committing everything it wrote *before* that point. The
memory tables carry only surrogate primary keys — `evidence_id`, `decision_id`,
`event_id`, `outbox_id` — so nothing else refuses a duplicate either.

Proved with two concurrent transactions sharing one key:

```
txn B outcome          : IntegrityError swallowed (exactly as _record_idempotency does)
idempotency rows for K : 1     <- the guard worked
evidence rows committed: 2  ['ev_A', 'ev_B']
```

The key already identifies the effect: `_semantic_idempotency_key`
(`background_recorder.py:57`) derives it from `source_outbox_id`, assertion
identity, normalized value and resolved operation — deliberately never from the
per-extraction candidate id. What is missing is not the identity but the
enforcement.

Latent today because no worker is mounted. It becomes live the moment one is.

## Decision

**The idempotency row is inserted before the semantic rows, in the same
transaction, and a conflict on the key aborts the transaction rather than being
swallowed.**

Specifically:

1. Reserve: insert the idempotency row with its result columns `NULL`, before any
   semantic row is written.
2. Effect: write assertion, version, evidence, decision, event and outbox.
3. Fill: update the reserved row with the result.
4. A conflict on the key is **not** caught. The losing transaction aborts and
   commits nothing.
5. A caller that loses the race re-reads the key to distinguish the two cases:
   - the row is complete → the effect is already applied; report the recorded
     result and write nothing;
   - the row is still incomplete → the competing transaction has not committed;
     retry.
6. A transaction that aborts after reserving releases the reservation with it, so
   a crash cannot strand a key.

## Alternatives Considered

### Add a unique effect key to four tables

**Approach.** Add `effect_key` plus a unique index to `memory_evidence`,
`memory_decisions`, `memory_events` and `memory_outbox`.

**Benefits.** The invariant becomes structural. The database refuses a duplicate
even if a future caller forgets the ordering rule, and the guarantee survives a
second producer.

**Costs.** A schema change on four tables; a key that every writer must compute and
carry; and it duplicates an identity the idempotency key already is.

**Rejected for now, not dismissed.** The transactional reservation achieves the
same guarantee with no schema change, because there is one producer. This becomes
the right answer if a second producer ever appears, and that trigger is recorded
here so the choice can be revisited rather than rediscovered.

### Keep swallowing the conflict and dedupe on read

**Approach.** Leave the code as it is; filter duplicates when reading.

**Benefits.** No change.

**Costs.** A committed duplicate is indistinguishable from a genuine second
observation. Two evidence rows for one assertion look exactly like corroboration,
which is the signal the activation policy counts.

**Rejected because.** It converts a correctness defect into a data-quality defect
that the activation thresholds would then amplify.

### Reserve outside the transaction

**Approach.** Write the idempotency row in its own transaction before starting the
effect transaction.

**Benefits.** The reservation is visible to competing workers sooner.

**Costs.** A crash between the two leaves a reservation with no effect and no way
to distinguish it from an in-flight one; the key becomes permanently blocked or
needs an expiry heuristic.

**Rejected because.** It replaces a transaction-boundary guarantee with a timeout
guess.

## Consequences

**Positive.**

- One key produces at most one semantic effect, enforced by the transaction that
  writes it rather than by a later reader.
- No schema change; the key that already identifies the effect is the key that
  enforces it.
- The loser aborts, so partial effects cannot commit.
- Evidence counts stay honest, which the activation thresholds depend on.

**Negative.**

- The transaction now aborts on a duplicate key instead of continuing, so a caller
  must handle it: distinguish "already applied" from "failed", and retry the
  in-flight case. That is new caller behaviour and must be tested.
- The idempotency row exists briefly with `NULL` results, so a reader of that table
  must tolerate an incomplete row. Nothing reads it except this path today.
- `_record_idempotency`'s savepoint, and the comment explaining it, are removed —
  the mechanism they protected is gone.

**Neutral.**

- The idempotency table's shape is unchanged.
- The key derivation is unchanged.
- Redelivery of a completed effect stays a no-op, now enforced by the reservation
  rather than by a lookup that raced.

## References

1. [ADR 0014: Transactional outbox and idempotent memory workers](./0014-transactional-outbox-and-idempotent-memory-workers.md)
2. [ADR 0028: The background worker claims through a role-scoped policy, and binds a tenant after the claim](./0028-worker-role-and-outbox-claim-boundary.md)
3. [Memory Worker Runtime](../specs/2026-09-12-memory-worker-runtime-design.md) — governing specification
4. [Basic Semantic Memory Write Pipeline Design](../specs/2026-09-07-basic-semantic-memory-write-pipeline-design.md)
