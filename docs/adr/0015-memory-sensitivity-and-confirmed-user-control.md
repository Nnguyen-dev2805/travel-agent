# ADR 0015: Memory Sensitivity and Confirmed User Control

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-07 |
| Decision owners | Repository owner |
| Scope | Sensitivity classification, prohibited content, confirmation, Memory Manager, and deletion behavior |
| Governing spec | [Basic Semantic Memory Write Pipeline Design](../specs/2026-09-07-basic-semantic-memory-write-pipeline-design.md), version 0.1 (Approved) |
| Superseded ADR | None; this record extends [ADR 0010](./0010-local-identity-authorization-and-deletion-boundary.md) and supersedes V2 sensitivity assumptions only through ADR 0013's replacement of ADR 0006 |
| Superseded by | None |

## Context

Owner-linked memory is personal data. Sensitivity is contextual: a food
preference may reveal religion or health, while future travel dates and exact
locations create physical-security risk. Secrets and payment authentication
data have no personalization purpose. The repository owner requires
confirmation for every user-initiated memory mutation.

## Decision

Use `ordinary_personal`, `contextually_sensitive`, `restricted`, and
`prohibited_secret` bands. Classify through deterministic secret detection, a
canonical-key minimum, contextual structured classification, and deterministic
escalation. A model may raise but never lower the hard minimum.

The focused slice supports durable ordinary memory only. Prohibited content is
rejected before candidate/model/index persistence. Restricted durable memory is
blocked until protected handling and user controls are delivered. A dedicated
Memory Manager and natural-language commands share one handler. Every
user-initiated remember, correct, delete, enable, or disable action requires
confirmation before mutation.

## Alternatives

### Review every generated candidate

Maximizes awareness but interrupts normal travel work. Rejected for background
shadow observations.

### Model-only sensitivity and silent user actions

Reduces deterministic policy and UI steps but can under-classify or mutate by
mistake. Rejected.

### Layered sensitivity and confirmed user commands

Adds confirmation friction and classification work but separates passive
observation from explicit durable mutation. Selected by the repository owner.

## Consequences

### Positive

1. Secrets and restricted categories cannot be enabled by model confidence.
2. UI and conversational controls share one policy path.
3. User-initiated mutations are explicit and auditable.

### Negative

1. Confirming every action can create fatigue.
2. Restricted personalization is unavailable in the first slice.
3. Contextual sensitivity needs its own evaluation and protected storage design.

## Migration

Rename or reinterpret legacy `none` as no heightened sensitivity rather than
non-personal data. Do not auto-promote legacy sensitive records. Deliver
ordinary controls before any restricted-memory phase.

## Validation

Prove secret leakage count zero, no restricted active version, no unconfirmed
mutation, cross-surface command consistency, owner isolation, deletion
propagation, and accessible confirmation behavior.

## References

1. Governing focused specification.
2. [ADR 0010](./0010-local-identity-authorization-and-deletion-boundary.md).
3. [NIST SP 800-122](https://doi.org/10.6028/NIST.SP.800-122).
4. [PCI DSS](https://www.pcisecuritystandards.org/standards/pci-dss/).
