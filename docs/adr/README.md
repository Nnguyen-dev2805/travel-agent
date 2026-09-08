# Architecture Decision Records

## Purpose

An Architecture Decision Record preserves one approved, durable architecture
decision, the viable alternatives considered, and the consequences accepted.
ADRs provide historical reasoning after implementation details and team context
change.

An ADR is not a feature specification or implementation plan:

1. A specification defines why and what a change must achieve.
2. An implementation plan defines how approved work will be delivered.
3. An ADR records one durable architecture decision and its consequences.

## When an ADR Is Required

Create an ADR after architecture approval when a decision materially affects:

1. Storage technology or data ownership.
2. Inter-service or external protocols.
3. Authentication, authorization, privacy, or trust boundaries.
4. Module boundaries or dependency direction.
5. Deployment topology or runtime ownership.
6. A major framework or dependency that is expensive to replace.
7. A compatibility, migration, or operational commitment that is hard to
   reverse.

Do not create an ADR for routine implementation details, reversible local
choices, or an unapproved proposal. Those belong in the governing spec or plan.

## Lifecycle

```text
Proposed -> Accepted -> Superseded
                     -> Deprecated
```

- `Proposed`: ready for architecture review; not authoritative.
- `Accepted`: explicitly approved and authoritative for its scope.
- `Superseded`: replaced by a newer accepted ADR linked in both records.
- `Deprecated`: no longer recommended and not replaced by one decision.

## Numbering and Naming

Use:

```text
docs/adr/NNNN-kebab-case.md
```

Numbers increase monotonically from `0001`. Never reuse a number after a
proposal is rejected, removed, deprecated, or superseded. The filename title is
stable after acceptance; changed decisions receive new ADRs.

Required metadata:

| Field | Required value |
| --- | --- |
| Status | Proposed, Accepted, Superseded, or Deprecated |
| Date | ISO decision date |
| Decision owners | Roles that approved the decision |
| Scope | Architecture boundary governed by the record |
| Governing spec | Approved architecture design path and version |
| Superseded ADR | Previous ADR path when applicable |
| Superseded by | Replacement ADR path when applicable |

## ADR Template

Bracketed tokens below are intentional author inputs.

```markdown
# ADR [NNNN]: [Decision Title]

| Field | Value |
| --- | --- |
| Status | Proposed |
| Date | [YYYY-MM-DD] |
| Decision owners | [Roles] |
| Scope | [Architecture boundary] |
| Governing spec | [Approved design path and version] |
| Superseded ADR | [Path when applicable] |
| Superseded by | [Path when applicable] |

## Context

[Forces, constraints, evidence, and why a durable decision is required]

## Decision

[Chosen architecture and explicit boundaries]

## Alternatives

### [Viable Alternative A]

[Benefits, costs, and reason not selected]

### [Viable Alternative B]

[Benefits, costs, and reason not selected]

## Consequences

### Positive

1. [Accepted benefit]

### Negative

1. [Accepted cost or constraint]

## Migration

[Compatibility, sequencing, rollout, and rollback boundaries]

## Validation

[Evidence and metrics that will test the decision]

## References

1. [Governing spec, plan, evidence, or related ADR]
```

## Immutability and Supersession

After acceptance, preserve the Context, Decision, Alternatives, and Consequences
as historical evidence. Factual corrections and status or reference updates are
allowed through normal review. A materially changed decision requires a new ADR
that marks the previous record `Superseded`.

When superseding, update both records so navigation works in both directions.
Never rewrite history to make an old decision appear to have anticipated later
evidence.

## Decision Index

| Number | Title | Status | Date | Path |
| --- | --- | --- | --- | --- |
| 0001 | Separate Online RAG Execution from Config-driven Evaluation | Accepted | 2026-09-01 | [ADR 0001](./0001-separate-online-rag-execution-from-config-driven-evaluation.md) |
| 0002 | Trip Workspace as Primary Product Container | Superseded | 2026-09-03 | [ADR 0002](./0002-trip-workspace-as-primary-product-container.md) |
| 0003 | Local SQLite Workspace Storage Boundary for R3 | Superseded | 2026-09-03 | [ADR 0003](./0003-local-sqlite-workspace-storage-boundary-for-r3.md) |
| 0004 | Shared Local Application Store and Per-module Schema Registry | Superseded | 2026-09-04 | [ADR 0004](./0004-shared-local-application-store-and-per-module-schema-registry.md) |
| 0005 | Conversation Orchestration Seam and Optional Chat Conversation Binding | Superseded | 2026-09-04 | [ADR 0005](./0005-conversation-orchestration-seam-and-optional-chat-binding.md) |
| 0006 | Shadow Memory Candidate Store and Policy Boundary | Superseded | 2026-09-04 | [ADR 0006](./0006-shadow-memory-candidate-store-and-policy-boundary.md) |
| 0007 | Feature-gated Memory Retrieval and Context Boundary | Accepted | 2026-09-05 | [ADR 0007](./0007-feature-gated-memory-retrieval-and-context-boundary.md) |
| 0008 | Workspace-owned Planner State and Operation Log | Accepted | 2026-09-05 | [ADR 0008](./0008-workspace-owned-planner-state-and-operation-log.md) |
| 0009 | Privacy-safe Local Observability Boundary | Accepted | 2026-09-05 | [ADR 0009](./0009-privacy-safe-local-observability-boundary.md) |
| 0010 | Local Identity, Authorization, and Deletion Boundary | Accepted | 2026-09-06 | [ADR 0010](./0010-local-identity-authorization-and-deletion-boundary.md) |
| 0011 | Authenticated Standalone Conversations | Accepted | 2026-09-07 | [ADR 0011](./0011-authenticated-standalone-conversations.md) |
| 0012 | Versioned Semantic Memory in PostgreSQL | Accepted | 2026-09-07 | [ADR 0012](./0012-versioned-semantic-memory-in-postgresql.md) |
| 0013 | Model-assisted Extraction and Deterministic Resolution | Accepted | 2026-09-07 | [ADR 0013](./0013-model-assisted-extraction-and-deterministic-resolution.md) |
| 0014 | Transactional Outbox and Idempotent Memory Workers | Accepted | 2026-09-07 | [ADR 0014](./0014-transactional-outbox-and-idempotent-memory-workers.md) |
| 0015 | Memory Sensitivity and Confirmed User Control | Accepted | 2026-09-07 | [ADR 0015](./0015-memory-sensitivity-and-confirmed-user-control.md) |
| 0016 | Focused Memory Write Evaluation and Rollout | Accepted | 2026-09-07 | [ADR 0016](./0016-focused-memory-write-evaluation-and-rollout.md) |
| 0017 | Risk-based Memory Confirmation | Proposed | 2026-09-07 | [ADR 0017](./0017-risk-based-memory-confirmation.md) |
