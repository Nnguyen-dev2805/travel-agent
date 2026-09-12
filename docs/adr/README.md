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
| 0015 | Memory Sensitivity and Confirmed User Control | Superseded | 2026-09-07 | [ADR 0015](./0015-memory-sensitivity-and-confirmed-user-control.md) |
| 0016 | Focused Memory Write Evaluation and Rollout | Accepted | 2026-09-07 | [ADR 0016](./0016-focused-memory-write-evaluation-and-rollout.md) |
| 0017 | Risk-based Memory Confirmation | Accepted | 2026-09-07 | [ADR 0017](./0017-risk-based-memory-confirmation.md) |
| 0018 | Authenticated Chat-Only Product Container | Accepted | 2026-09-10 | [ADR 0018](./0018-authenticated-chat-only-product-container.md) |
| 0019 | PostgreSQL-Only Application Relational Persistence and SQLite Retirement | Accepted | 2026-09-10 | [ADR 0019](./0019-postgresql-only-application-persistence-sqlite-retirement.md) |
| 0020 | Removal of Public Memory Management Surface | Accepted | 2026-09-10 | [ADR 0020](./0020-removal-of-public-memory-management-surface.md) |
| 0021 | Standalone Conversation Ownership, Route Contract, and Auto-Create Behavior | Accepted | 2026-09-10 | [ADR 0021](./0021-standalone-conversation-ownership-and-auto-create.md) |
| 0022 | Clean-Break Migration, Data Disposal, and Rollback Authority | Accepted | 2026-09-10 | [ADR 0022](./0022-clean-break-migration-data-disposal-rollback.md) |
| 0023 | Atomic Two-Phase Chat Turn | Accepted | 2026-09-11 | [ADR 0023](./0023-atomic-two-phase-chat-turn.md) |
| 0024 | Evaluation Results Distinguish Unmeasurable from Perfect | Accepted | 2026-09-11 | [ADR 0024](./0024-evaluation-results-distinguish-unmeasurable-from-perfect.md) |
| 0025 | The Message Status/Content Invariant Is Enforced in the Database | Accepted | 2026-09-11 | [ADR 0025](./0025-message-status-content-invariant-in-database.md) |
| 0026 | Authentication Is Enforced in Middleware, Before the Request Body Is Parsed | Accepted | 2026-09-11 | [ADR 0026](./0026-authentication-enforced-in-middleware-before-body-parsing.md) |
| 0027 | An Outbox Event Is Released Only When Its Turn Is Terminal | Accepted | 2026-09-11 | [ADR 0027](./0027-outbox-event-released-only-when-turn-terminal.md) |
| 0028 | The Background Worker Claims Through a Role-Scoped Policy, and Binds a Tenant After the Claim | Accepted | 2026-09-11 | [ADR 0028](./0028-worker-role-and-outbox-claim-boundary.md) |
| 0029 | The Background Memory Worker Runs as Its Own Service Under Its Own Role | Accepted | 2026-09-12 | [ADR 0029](./0029-the-memory-worker-runs-as-its-own-service.md) |
| 0030 | A Conversation's Outbox Events Are Claimed Under a Per-Conversation Advisory Lock | Accepted | 2026-09-12 | [ADR 0030](./0030-a-conversation-is-claimed-under-an-advisory-lock.md) |
| 0031 | The Idempotency Key Is Reserved Before the Semantic Effect It Guards | Accepted | 2026-09-12 | [ADR 0031](./0031-the-idempotency-key-is-reserved-before-the-effect.md) |
| 0032 | An Outbox Lease Is Judged Valid Against Database Time, and Held by a Process Identity | Accepted | 2026-09-12 | [ADR 0032](./0032-lease-validity-is-database-time.md) |
| 0033 | A Fenced Worker Stops Without Cancelling the Conversation's Other Events | Accepted | 2026-09-12 | [ADR 0033](./0033-a-fenced-worker-stops-without-cancelling.md) |
| 0034 | Each Process Receives Only the Credential Its Role Requires | Accepted | 2026-09-12 | [ADR 0034](./0034-per-process-credential-isolation.md) |
| 0035 | Application Composition Happens at Startup, and a Request Without It Fails Closed | Accepted | 2026-09-12 | [ADR 0035](./0035-application-composition-happens-at-startup.md) |
