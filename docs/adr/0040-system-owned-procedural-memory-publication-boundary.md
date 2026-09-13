# ADR 0040: System-owned Procedural Memory Publication Boundary

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-12 |
| Decision owners | Repository owner |
| Scope | Procedural Memory ownership, offline evaluation/publication, runtime consumption, tenant isolation boundary, and rollback |
| Governing spec | `docs/specs/2026-09-12-agent-memory-target-architecture-design.md` v0.2 (Approved 2026-09-12) |
| Superseded ADR | Not applicable |
| Superseded by | Not applicable |

## Context

The target architecture names procedural Memory as a fourth AI-Memory family,
but its ownership is fundamentally different from semantic, episodic, and
working user Memory. Procedures encode reusable system behavior/configuration,
not facts inferred from one tenant's Chat history.

Treating procedural Memory as another tenant `MemoryScope` would either duplicate
the same system procedure across users or tempt the implementation to weaken
tenant RLS so shared rows can be read by everyone. Allowing ordinary Chat or a
model to publish a new procedure would also turn user/model content into system
behavior authority.

## Decision

Procedural Memory is a system-owned, versioned publication/configuration family.
It is not a tenant Memory scope and does not share tenant user-Memory RLS tables.

Procedural versions are produced through an offline governed pipeline:

```text
candidate procedure
-> deterministic validation
-> evaluation suite
-> owner-approved publication
-> versioned active publication
```

Ordinary Chat cannot create, edit, delete, or activate procedural Memory.
Tenant-derived Memory workers cannot publish it. Model output may propose a
candidate in an explicitly governed offline workflow, but it cannot self-publish
or change the active version.

Runtime consumption reads only an explicitly published version. Publication and
rollback use version identity/pointer state so a prior approved version can be
restored without rewriting tenant Memory.

Procedural Memory cannot override system/developer policy, authentication,
authorization, lifecycle, sensitivity, or safety rules. It supplies bounded
system behavior/configuration only within those higher-authority constraints.

Storage and credentials for procedural publication remain separate from tenant
Memory write authority. Tenant RLS is neither disabled nor broadened to make
system-owned procedures visible.

## Alternatives

### Store procedures as user-scoped Memory rows

This reuses the tenant schema, but duplicates shared state and confuses user data
with system configuration. Rejected.

### Store one shared procedure row in tenant tables and bypass RLS

This is operationally convenient, but weakens the isolation boundary for all
tenant Memory in order to solve an unrelated ownership problem. Rejected.

### Let the agent learn and publish procedures online from successful turns

This is adaptive, but allows prompt/model behavior to mutate future system
behavior without an evaluation or approval boundary. Rejected for this target.

### System-owned offline evaluated publication

This is slower to adapt, but keeps behavior authority reviewable, versioned, and
separate from user Memory. Selected.

## Consequences

### Positive

1. Tenant Memory isolation remains simple and strong.
2. System behavior changes have an explicit evaluation and publication history.
3. One published procedure can serve all tenants without duplicating user-state
   rows.
4. Rollback is a version-selection operation rather than a tenant-data rewrite.
5. User/model content cannot silently promote itself into system behavior.

### Negative

1. Procedural Memory needs its own publication tooling/storage boundary.
2. Online self-improvement is intentionally deferred.
3. Evaluation datasets and publication metadata become operational requirements.
4. The word "Memory" now spans two ownership domains, so documentation and types
   must make tenant-owned versus system-owned authority obvious.

## Migration

Do not create procedural rows in existing tenant Memory tables. Stage 7 defines
the dedicated publication representation only after semantic, episodic, and
working user-Memory boundaries are proven.

Initial rollout publishes no procedure automatically. A first active version
requires explicit repository-owner approval and passing evaluation evidence.
Rollback selects the prior accepted published version or disables procedural
consumption; it does not alter tenant Memory or tenant RLS.

## Validation

1. Tenant Chat and Memory-worker credentials cannot insert/update procedural
   publication state.
2. A model-generated candidate cannot become active without deterministic
   validation, evaluation, and explicit publication approval.
3. Runtime reads only the active published version and fails closed on unknown
   or invalid publication state.
4. Procedural consumption cannot override higher-authority policy or security
   decisions.
5. Tenant RLS tests remain unchanged and enabled; no `BYPASSRLS` grant is added
   to serve procedural reads.
6. Version rollback restores the prior approved procedure without touching
   tenant Memory rows.
7. Required evaluation evidence missing or `INCONCLUSIVE` blocks publication.

## References

1. [Agent Memory Target Architecture](../specs/2026-09-12-agent-memory-target-architecture-design.md) v0.2.
2. [ADR 0012](./0012-versioned-semantic-memory-in-postgresql.md) for the separate tenant semantic Memory boundary.
3. [ADR 0034](./0034-per-process-credential-isolation.md) for role-specific database authority.
