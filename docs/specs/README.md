# Specifications

## Purpose

Specifications define why a repository change is needed, what behavior or
decision is approved, and how acceptance will be judged. The approved
[Documentation System Design](./2026-08-30-documentation-system-design.md) is
the governing policy. This file operationalizes that policy with selection
rules, authoring templates, review checks, and an index.

Implementation begins only after the exact specification and its implementation
plan are approved by the repository owner.

## Choose a Change Level

| Level | Use when | Persistent artifact |
| --- | --- | --- |
| Level 1 - Change Spec | Narrow documentation correction, isolated bug, configuration adjustment, or dependency maintenance with no architecture or cross-module contract change | An approved issue may contain the spec and plan; use a repository spec when durable discovery is needed |
| Level 2 - Feature Spec | New behavior or a material API, schema, user-flow, evaluation, security, or module-contract change | Separate files under `docs/specs/` and `docs/plans/` |
| Level 3 - Architecture Design | New subsystem or a storage, protocol, trust-boundary, module-boundary, deployment, or other hard-to-reverse change | Architecture design, implementation plan, architecture approval, and accepted ADRs |

When classification is uncertain, select the higher level. Wider impact found
during implementation stops the work and returns it to design review.

## Lifecycle

```text
Draft -> In Review -> Approved -> Superseded
```

- `Draft`: authoring is incomplete; no approval is implied.
- `In Review`: the document is complete enough for a decision.
- `Approved`: the repository owner approved the recorded version.
- `Superseded`: a newer approved document replaces it and is linked in metadata.

Rejected proposals stay in issue or review history rather than becoming
authoritative repository documentation.

## Naming and Metadata

Use:

```text
docs/specs/YYYY-MM-DD-kebab-case-design.md
```

Every specification begins with:

| Field | Required value |
| --- | --- |
| Status | One lifecycle value |
| Version | Document version reviewed for approval |
| Date | ISO date |
| Change class | Level 1, Level 2, or Level 3 |
| Decision owner | Role that grants approval |
| Scope | Bounded system or change area |
| Related issue | Issue path, or an explicit approved exception |
| Superseded document | Required when this document replaces another |

Use English for technical artifacts. Mark current-state facts with evidence and
label proposed behavior so it cannot be mistaken for implemented behavior.

## Level 1 Change Spec Template

Bracketed tokens below are intentional author inputs.

```markdown
# [Change Title]

| Field | Value |
| --- | --- |
| Status | Draft |
| Version | [Version] |
| Date | [YYYY-MM-DD] |
| Change class | Level 1 - Change Spec |
| Decision owner | Repository owner |
| Scope | [Bounded scope] |
| Related issue | [Issue path or approved exception] |
| Superseded document | [Path when applicable] |

## Problem and Evidence

[Observed problem and reviewable evidence]

## Scope

[Included behavior and files]

## Non-goals

[Explicit exclusions]

## Expected Behavior

[Observable result]

## Acceptance Criteria

1. [Checkable criterion]

## Verification

1. `[Exact command or review method]`
2. Expected: [Observable outcome]

## Risks

[Known risk and mitigation]

## Rollback

[Safe recovery procedure]

## Specification Approval Record

[Version, approver role, date, and authorization to prepare the implementation
steps]

## Implementation Steps

1. [Ordered, independently reviewable step]

## Implementation Plan Approval Record

[Version, approver role, date, and authorization to implement]
```

In a combined Level 1 artifact, `Implementation Steps` is the implementation
plan. Its approval occurs only after specification approval and is recorded
separately before implementation begins.

## Level 2 Feature Spec Template

```markdown
# [Feature Title]

| Field | Value |
| --- | --- |
| Status | Draft |
| Version | [Version] |
| Date | [YYYY-MM-DD] |
| Change class | Level 2 - Feature Spec |
| Decision owner | Repository owner |
| Scope | [Bounded feature scope] |
| Related issue | [Issue path or approved exception] |
| Superseded document | [Path when applicable] |

## Summary

[Decision-oriented overview]

## Context

[Relevant current state and evidence]

## Users

1. [Affected user or system actor]

## Problem Statement

[Problem, impact, and why it matters now]

## Goals

1. [Observable goal]

## Non-goals

1. [Explicit exclusion]

## Assumptions

1. [Assumption that would stop work if invalidated]

## User and System Flows

1. [Ordered interaction or data flow]

## Behavioral and Data Contracts

[Inputs, outputs, state transitions, ownership, and compatibility]

## Errors and Edge Cases

1. [Condition, expected response, and recovery]

## Security and Privacy

[Trust boundaries, authorization, data classification, and retention]

## Observability and Operations

[Logs, metrics, traces, alerts, and operational ownership]

## Testing and Evaluation

[Component tests, integration tests, quality metrics, and gates]

## Rollout and Migration

[Sequence, compatibility, data migration, and promotion gates]

## Rollback

[Safe recovery and irreversible effects]

## Acceptance Criteria

1. [Measurable or directly reviewable criterion]

## Approval Record

[Version, approver role, date, and authorization boundary]
```

## Level 3 Architecture Additions

Start with the Level 2 template, change the class to
`Level 3 - Architecture Design`, and add:

```markdown
## Current-state Evidence

[Verified components, flows, constraints, and evidence paths]

## Alternatives Considered

### [Viable Alternative A]

[Approach, benefits, costs, and rejection or selection reason]

### [Viable Alternative B]

[Approach, benefits, costs, and rejection or selection reason]

## Components and Dependency Direction

[Responsibilities, interfaces, ownership, and allowed dependencies]

## Data Flow and Lifecycle

[Creation, mutation, access, retention, and deletion]

## Failure and Recovery

[Failure modes, degradation, retry, recovery, and operator action]

## Capacity, Latency, and Cost

[Applicable budgets and measurement approach]

## Compatibility and Staged Migration

[Coexistence, sequencing, rollout gates, and rollback boundaries]

## Required ADRs

1. [Durable decision to record after approval]
```

Level 3 requires explicit architecture approval. At least two viable approaches
must be compared; a cosmetic variant is not a distinct alternative.

## Review Checklist

- [ ] Purpose and canonical ownership are explicit.
- [ ] Scope and non-goals are bounded.
- [ ] Current-state claims have reviewable evidence.
- [ ] Proposed behavior is distinguishable from implemented behavior.
- [ ] Requirements and acceptance criteria are checkable.
- [ ] Errors, risks, security, privacy, and operations are addressed.
- [ ] Migration and rollback are explicit where applicable.
- [ ] Terms, types, and identifiers are internally consistent.
- [ ] References resolve and superseded documents are identified.
- [ ] No unresolved drafting markers or deferred requirements remain.
- [ ] The decision owner can state exactly what approval authorizes.

## Specification Index

| Date | Title | Level | Version | Status | Path |
| --- | --- | --- | --- | --- | --- |
| 2026-08-30 | Documentation System Design | Level 3 | 0.1 | Approved | [Design](./2026-08-30-documentation-system-design.md) |
| 2026-08-30 | Agent Operating System Design | Level 2 | 0.1 | Approved | [Design](./2026-08-30-agent-operating-system-design.md) |
| 2026-08-31 | Project Entry Points Design | Level 2 | 0.1 | Approved | [Design](./2026-08-31-project-entry-points-design.md) |
| 2026-08-31 | Architecture Baseline Design | Level 3 | 0.1 | Approved | [Design](./2026-08-31-architecture-baseline-design.md) |
| 2026-08-31 | Roadmap and Learning Design | Level 2 | 0.1 | Approved | [Design](./2026-08-31-roadmap-and-learning-design.md) |
| 2026-08-31 | Evaluation Protocols Design | Level 2 | 0.1 | Approved | [Design](./2026-08-31-evaluation-protocols-design.md) |
| 2026-08-31 | Operations and Security Design | Level 2 | 0.1 | Approved | [Design](./2026-08-31-operations-and-security-design.md) |
| 2026-08-31 | GitHub and Open Source Design | Level 2 | 0.1 | Approved | [Design](./2026-08-31-github-and-open-source-design.md) |
| 2026-09-01 | Foundation Cleanup Design | Level 2 | 0.1 | Approved | [Design](./2026-09-01-foundation-cleanup-design.md) |
| 2026-09-01 | RAG Repair and Evaluation Harness Design | Level 3 | 0.1 | Approved | [Design](./2026-09-01-rag-repair-and-evaluation-harness-design.md) |
| 2026-09-03 | Trip Workspace Foundation Design | Level 3 | 0.1 | Approved | [Design](./2026-09-03-trip-workspace-foundation-design.md) |
| 2026-09-04 | Conversation Persistence Design | Level 3 | 0.1 | Approved | [Design](./2026-09-04-conversation-persistence-design.md) |
| 2026-09-04 | Shadow Memory Extraction Design | Level 3 | 0.1 | Approved | [Design](./2026-09-04-shadow-memory-extraction-design.md) |
| 2026-09-04 | Memory Retrieval Design | Level 3 | 0.3 | Approved | [Design](./2026-09-04-memory-retrieval-design.md) |
| 2026-09-05 | Trip Planner State Design | Level 3 | 0.2 | Approved | [Design](./2026-09-05-trip-planner-state-design.md) |
