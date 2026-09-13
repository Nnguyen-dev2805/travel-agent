# ADR 0039: Memory Read/Use Authority and Rebuildable Retrieval Projections

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-12 |
| Decision owners | Repository owner |
| Scope | Memory read eligibility, query/context planning, answer-time precedence, prompt composition, explicit inspect, RAG separation, and secondary retrieval projections |
| Governing spec | `docs/specs/2026-09-12-agent-memory-target-architecture-design.md` v0.2 (Approved 2026-09-12) |
| Superseded ADR | [ADR 0007](./0007-feature-gated-memory-retrieval-and-context-boundary.md) |
| Superseded by | Not applicable |

## Context

ADR 0007 established an early feature-gated retrieval seam for workspace-era
Memory. The product is now authenticated, Chat-first, PostgreSQL-backed, and no
longer uses workspace binding as the Memory read boundary. The target also needs
to distinguish four separate responsibilities that the legacy seam did not fully
separate: physical storage filtering, lifecycle eligibility, relevance/ranking,
and final context admission/use.

The read path must answer two different questions without conflating them:

1. should this turn use Memory, RAG, both, or neither?
2. if Memory is requested, which Memory is actually eligible and relevant?

Vector similarity cannot answer lifecycle, tenant, sensitivity, conflict, or
current-request precedence safely.

## Decision

Read/use is split into explicit authority layers.

`MemoryStore` owns physical/storage predicates and tenant isolation. It returns
storage-scoped rows and must not own semantic lifecycle eligibility, relevance,
precedence, ranking, or prompt composition.

`MemoryLifecyclePolicy`, governed by ADR 0037, is the single owner of semantic
lifecycle eligibility across write, formation, activation, and read. This ADR
consumes that policy on the read path; it does not redefine it. In particular,
a row is not readable merely because its stored status is `ACTIVE`.

`MemoryReadEngine` owns the semantic read sequence:

```text
eligible candidates
-> request relevance
-> scope/response precedence
-> conflict exclusion
-> ranking/bounded selection
-> select or abstain
```

`ContextPlanner` owns the source plan for one bounded turn using the closed
vocabulary:

```text
none
rag_only
memory_only
both
```

Stage 1 exposes that vocabulary but only `none|rag_only` are reachable. Stage 3
makes `memory_only|both` reachable after governed Memory Read exists. Memory and
RAG may execute in parallel inside the single read-only context phase.

`ContextArbiter` deterministically admits context under policy, precedence, and
token budget. `MemoryContextComposer` emits structured Memory context, not raw
source text. Memory is never represented as a travel citation and never becomes
an instruction channel.

Response-time precedence is:

```text
system/developer policy
> current user request
> verified hard constraints
> current conversation working state / temporary override
> user-scoped soft preferences/profile
> episodes/summaries
```

The current user request may suppress a soft durable preference for one response
without silently mutating it.

Chat-native `explicit_inspect` uses the same governed lifecycle/read boundary as
normal Memory selection. It is not a direct database dump. Before Stage 3 it
returns a controlled capability-unavailable `INCOMPLETE` outcome.

PostgreSQL full-text and pgvector are optional secondary projections introduced
only when evaluated structured retrieval is insufficient. They are rebuildable,
non-canonical, tenant-bounded candidate sources. Projection results are
revalidated against canonical PostgreSQL lifecycle/sensitivity/scope state
before use. A projection can improve recall/ranking; it cannot grant eligibility.

This ADR replaces ADR 0007's legacy workspace-era retrieval and
context seam. ADR 0007's already-superseded V2 write correction rule remains
historical; its general principle that RAG does not own personal Memory is
preserved here.

## Alternatives

### Put Memory retrieval inside RAG

This gives one retrieval component, but makes travel corpus retrieval depend on
personal state and mixes Memory evaluation with RAG evaluation. Rejected.

### Let `MemoryStore` return only final answer-ready Memory

This shortens the call chain, but couples SQL/storage adapters to lifecycle,
relevance, precedence, and ranking policy. Those policies change at different
rates and require different tests. Rejected.

### Make pgvector the canonical Memory read surface

This provides semantic similarity early, but similarity does not encode tenant,
revocation, source validity, sensitivity, or conflict authority. Rejected.

### Inject raw Memory/evidence text into the prompt

This preserves maximum detail, but increases prompt-injection and privacy risk
and lets provenance text masquerade as instruction. Rejected.

### Layered governed read/use with optional projections

This adds interfaces, but keeps each correctness question under one explicit
owner and allows exact retrieval to remain the baseline. Selected.

## Consequences

### Positive

1. Tenant/storage filtering, lifecycle eligibility, semantic selection, and
   prompt composition can be tested independently.
2. Current-turn intent and higher policy remain authoritative over soft Memory.
3. RAG remains travel-knowledge retrieval rather than personal-state authority.
4. Explicit inspect cannot bypass lifecycle/sensitivity policy.
5. Vector/full-text indexes can be added or rebuilt without becoming canonical
   Memory state.

### Negative

1. The read path has several deliberate components instead of one repository
   query.
2. Abstention and precedence need explicit evaluation datasets, not only
   retrieval recall metrics.
3. Structured Memory context may omit nuance that raw evidence contains; missing
   fields must be addressed through typed schemas rather than raw-text fallback.
4. Projection consumers must revalidate canonical state, adding a small latency
   and implementation cost.

## Migration

Deliver the exact structured semantic read path first. Do not enable
`memory_only|both` until Stage 3 lifecycle/read/use tests pass. Keep pgvector and
full-text out of the critical path until structured retrieval has measured
insufficiency.

ADR 0007 is marked `Superseded` and links back to this record. Rollback disables
Memory source modes and returns the ContextPlanner to
`none|rag_only`; canonical Memory rows remain intact. Never fall back to a vector
index as truth.

## Validation

1. Deleted, revoked, expired, stale-generation, invalid-source, sensitive-blocked,
   and unresolved-conflict rows are never selected.
2. `ACTIVE` alone is insufficient to pass eligibility.
3. Current-request temporary overrides beat user-scoped soft preferences without
   mutating them.
4. `explicit_inspect` returns only governed eligible/safe fields and cannot dump
   raw evidence text.
5. Planner fixtures cover `none`, `rag_only`, `memory_only`, and `both`, plus
   correct abstention when Memory is unnecessary.
6. RAG and Memory remain dependency-separated and can be evaluated independently.
7. Projection loss/rebuild does not change canonical lifecycle state.
8. Projection candidates that became revoked/deleted after indexing are rejected
   by canonical revalidation before use.
9. Prompt tests prove Memory is structured data, not an instruction or citation.

## References

1. [Agent Memory Target Architecture](../specs/2026-09-12-agent-memory-target-architecture-design.md) v0.2.
2. [ADR 0007](./0007-feature-gated-memory-retrieval-and-context-boundary.md).
3. [ADR 0012](./0012-versioned-semantic-memory-in-postgresql.md).
4. [ADR 0013](./0013-model-assisted-extraction-and-deterministic-resolution.md).
5. [ADR 0020](./0020-removal-of-public-memory-management-surface.md).
6. [ADR 0037](./0037-memory-retention-revocation-and-suppression.md) for the canonical lifecycle-eligibility owner and predicate.
