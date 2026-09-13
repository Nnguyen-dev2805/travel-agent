# ADR 0037: Memory Retention, Revocation, Suppression, and Re-remember

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-12 |
| Decision owners | Repository owner |
| Scope | Tenant Memory retention semantics, temporal validity, product forget, suppression generations, source/conversation invalidation, and explicit re-remember |
| Governing spec | `docs/specs/2026-09-12-agent-memory-target-architecture-design.md` v0.2 (Approved 2026-09-12) |
| Superseded ADR | Not applicable |
| Superseded by | Not applicable |

## Context

Memory lifetime cannot be represented by one `active` flag or one expiration
timestamp. A Memory may be durable across conversations, bound to one source, or
bound to one conversation. Separately, a fact may be temporally valid only until
a date. Product-level "forget this" is also different from privacy deletion: the
system needs enough lifecycle state to prevent delayed background work from
resurrecting what the user explicitly revoked.

Without an explicit contract, a late worker can activate an old candidate after
forget, conversation deletion can require rewriting an unbounded number of rows,
and re-remember becomes indistinguishable from accidental resurrection.

## Decision

Every tenant Memory version persists one retention mode at write time:

```text
CONVERSATION_BOUND
SOURCE_BOUND
USER_DURABLE
```

Retention is immutable for that version. A later policy change creates a new
governed version/effect rather than silently reinterpreting old rows.

`expires_at` represents temporal validity only. It is not used to encode source
deletion, conversation deletion, product forget, or revocation.

Canonical read eligibility evaluates source validity separately:

```text
lifecycle_status == ACTIVE
AND temporal_valid(expires_at)
AND source_valid(retention_mode, provenance)
AND suppression_generation_is_current
AND sensitivity/scope/type lifecycle policy passes
```

`MemoryLifecyclePolicy` owns the shared lifecycle rules and stage-specific
eligibility decisions across **write, formation, activation, and read**. The
full predicate above is the read-eligibility form; earlier stages apply the
relevant lifecycle rules before an active version exists. In particular,
write/formation/activation must enforce source validity, current suppression
generation, retention/temporal constraints where applicable, and
sensitivity/scope/type lifecycle policy without pretending a not-yet-active
candidate already satisfies `lifecycle_status == ACTIVE`.

None of those four paths may independently reimplement or weaken the shared
rules. Execution mode is not a lifecycle-policy input: the explicit API path
and background worker path consume the same policy owner and contracts.

Read-time relevance, response precedence, unresolved-conflict exclusion,
ranking, and final selection are deliberately outside `MemoryLifecyclePolicy`;
they remain the responsibility of `MemoryReadEngine` as governed by ADR 0039.

Conversation deletion always invalidates evidence sourced from that
conversation. The retention mode then determines the semantic result:

1. `CONVERSATION_BOUND` becomes ineligible with the conversation.
2. `SOURCE_BOUND` re-evaluates remaining valid independent evidence and becomes
   ineligible if its activation requirement is no longer satisfied.
3. `USER_DURABLE` may keep the normalized value, but deleted-source text/evidence
   becomes inaccessible through read, inspect, trace, prompt, or citation.

Product-level forget uses explicit lifecycle vocabulary:

```text
MemoryOperation.REVOKE
VersionStatus.REVOKED
assertion.suppression_generation
```

On a successful forget, the governed active version is revoked and the
assertion's `suppression_generation` advances. Evidence/candidates/work stamped
with an older generation may not form, activate, or read after that point.

An explicit later re-remember is allowed, but it is a new authorized write in the
current generation. It does not reactivate the revoked version and it does not
erase the audit history.

`memory_deletion_ledger` remains a privacy/retention deletion artifact. It is not
repurposed to model product forget.

## Alternatives

### Delete Memory rows when the user says forget

This makes the current value disappear, but destroys the lifecycle fact needed
to fence delayed work. It also conflates product behavior with privacy erasure.
Rejected.

### Use only `expires_at`

One timestamp is simple, but cannot distinguish temporal expiry from source
invalidation or user revocation, and would require mass expiry updates on
conversation deletion. Rejected.

### Last-write-wins by timestamp

A new write could outrank an old one without an explicit generation. This fails
when delayed background work commits after forget and makes re-remember versus
resurrection ambiguous. Rejected.

### Persist retention plus suppression generation

This adds lifecycle state, but makes invalidation and no-resurrection rules
deterministic at formation, activation, and read. Selected.

## Consequences

### Positive

1. Forget has a first-class semantic meaning without pretending to be privacy
   erasure.
2. Late background work cannot resurrect an explicitly forgotten Memory.
3. Conversation deletion remains bounded by provenance/source invalidation
   rather than O(number-of-Memory-rows) expiry rewrites.
4. Temporal expiry, provenance validity, and retention remain independently
   understandable and testable.
5. Explicit re-remember is possible without rewriting history.

### Negative

1. Every formation/write/activation/read path must carry and validate generation
   and retention data.
2. Source-bound Memory requires evidence accounting when a source disappears.
3. Inspect/debug tooling must explain why an `ACTIVE` row is nevertheless
   ineligible.
4. Existing records need an explicit migration/default policy before the new
   contract can become runtime authority.

## Migration

Add the retention, temporal-validity, revocation, and suppression-generation
fields before any new read path depends on them. Backfill existing rows with an
explicit migration rule approved by the implementation plan; do not infer a
durable user scope from missing legacy metadata at runtime.

Introduce generation checks at write/formation first, then activation and read.
Rollback may disable the new feature paths, but must not clear revocation or
suppression state and must not reactivate revoked/superseded versions.

## Validation

1. Forget revokes the active version and advances suppression generation in one
   transaction.
2. A generation-N candidate delivered after generation N+1 exists cannot form,
   activate, or read.
3. Explicit re-remember creates a current-generation version without reactivating
   the revoked version.
4. Temporal expiry does not mutate retention mode or suppression generation.
5. Conversation deletion makes conversation-bound Memory ineligible without
   rewriting every version's `expires_at`.
6. Source-bound Memory re-evaluates support using only remaining independent
   valid evidence.
7. User-durable normalized state may survive source deletion while raw deleted
   source text/evidence is unavailable to read/inspect/trace/prompt surfaces.
8. Privacy deletion remains separate from `REVOKE` semantics.

## References

1. [Agent Memory Target Architecture](../specs/2026-09-12-agent-memory-target-architecture-design.md) v0.2.
2. [ADR 0012](./0012-versioned-semantic-memory-in-postgresql.md).
3. [ADR 0013](./0013-model-assisted-extraction-and-deterministic-resolution.md).
4. [ADR 0014](./0014-transactional-outbox-and-idempotent-memory-workers.md).
5. [ADR 0020](./0020-removal-of-public-memory-management-surface.md).
6. [ADR 0039](./0039-memory-read-use-authority-and-retrieval-projections.md) for read-time relevance, precedence, ranking, and selection layered after lifecycle eligibility.
