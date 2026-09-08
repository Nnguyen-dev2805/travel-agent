# ADR 0012: Versioned Semantic Memory in PostgreSQL

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-07 |
| Decision owners | Repository owner |
| Scope | Semantic memory identity, lifecycle ownership, canonical persistence, migrations, and tenant defense |
| Governing spec | [Basic Semantic Memory Write Pipeline Design](../specs/2026-09-07-basic-semantic-memory-write-pipeline-design.md), version 0.1 (Approved) |
| Superseded ADR | [ADR 0003](./0003-local-sqlite-workspace-storage-boundary-for-r3.md) and [ADR 0004](./0004-shared-local-application-store-and-per-module-schema-registry.md) for active relational storage; SQLite remains migration-era legacy evidence |
| Superseded by | None |

## Context

The local SQLite record model lacks canonical semantic keys, immutable decision
history, typed assertion identity, and an atomic multi-row promotion boundary.
The approved target must support approximately 1,000 authenticated users and
must not let derived search become lifecycle authority.

## Decision

PostgreSQL owns normalized `memory_events`, `memory_candidates`,
`memory_decisions`, `memory_evidence`, `memory_assertions`, `memory_versions`,
`memory_outbox`, summary, episode, and deletion-ledger state. Semantic memory is
modeled as immutable evidence supporting a stable assertion with immutable
versions.

Typed columns own identity, lifecycle, authority, sensitivity, and time;
registry-validated JSONB owns variable value and condition payloads. Owner
identity is present on every owner-scoped row. Application authorization and
PostgreSQL RLS both enforce scope. SQLAlchemy Core and Alembic own active schema
access and migration history. SQLite becomes legacy-only.

## Alternatives

### One JSONB memory table

Flexible but weakens lifecycle, uniqueness, provenance, deletion, and
operational constraints. Rejected.

### Full temporal graph source of truth

Powerful for multi-hop relationships but adds another operational and
transaction authority before local evaluation proves need. Deferred.

### Normalized PostgreSQL plus rebuildable projections

Adds relational complexity but provides one transactional lifecycle authority,
RLS, constraints, migrations, and sufficient scale. Selected.

## Consequences

### Positive

1. Evidence, decisions, semantic identity, and value history are independently
   auditable.
2. Database constraints protect one-current-version and owner invariants.
3. Full-text/vector projections can be rebuilt without changing lifecycle.

### Negative

1. Local development requires PostgreSQL.
2. More tables and joins must be understood and operated.
3. Legacy data needs inventory and cannot become active automatically.

## Migration

Use PostgreSQL in development, integration, and production. Inspect SQLite: if
no data matters, treat it as disposable; otherwise import it only as quarantined
legacy evidence. Never auto-activate legacy rows.

## Validation

Run migration round trips, constraint and RLS tests, owner-mismatch tests,
concurrent assertion writes, failure injection, and search revalidation tests.

## References

1. Governing focused specification.
2. [ADR 0004](./0004-shared-local-application-store-and-per-module-schema-registry.md).
3. [ADR 0006](./0006-shadow-memory-candidate-store-and-policy-boundary.md).
4. [ADR 0007](./0007-feature-gated-memory-retrieval-and-context-boundary.md).
