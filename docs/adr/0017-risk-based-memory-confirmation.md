# ADR 0017: Risk-based Memory Confirmation

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-07 |
| Accepted | 2026-09-08 |
| Decision owners | Repository owner |
| Scope | User-memory confirmation, application save feedback, sensitive no-store, conflict prompting, and Shadow meaning |
| Governing spec | [Risk-based Memory Control Amendment](../specs/2026-09-07-risk-based-memory-control-amendment.md), version 0.1 (Approved) |
| Superseded ADR | [ADR 0015](./0015-memory-sensitivity-and-confirmed-user-control.md) |
| Superseded by | None |

## Context

ADR 0015 required confirmation for every user-initiated memory action. Review
found that a second prompt for clear low-risk remember, edit, delete-one, and
toggle actions adds friction and habituation without proportional safety.

## Decision

Use risk-based confirmation. Explicit low-risk remember commits directly after
hard validation and the application renders `Memory Saved` after commit,
separate from the model response. Small reversible operations use Undo. Bulk
delete and conversation-to-user scope expansion use preview plus one-time
confirmation. Sensitive content is no-store/no-prompt in the focused scope.
Ambiguous conflicts stay pending and are clarified only when relevant. Shadow
means valid but lacks promotion authority.

The layered bands remain `ordinary_personal`, `contextually_sensitive`,
`restricted`, and `prohibited_secret`. Deterministic secret detection and the
registry sensitivity floor run before contextual classification; model output
may raise but never lower sensitivity. In this focused slice only ordinary
personal memory may become durable.

## Alternatives

### Confirm every action

Maximizes explicit ceremony but creates friction and confirmation fatigue.
Rejected after approval review.

### Never confirm

Fast but unsafe for broad deletion and widened scope. Rejected.

### Risk-based confirmation

Concentrates confirmation on high-blast-radius actions and uses application
state/Undo elsewhere. Selected.

## Consequences

### Positive

1. Clear low-risk personalization does not interrupt travel work.
2. UI truth comes from commit state, not model language.
3. High-impact mutations retain stale/replay protection.

### Negative

1. Classification and validation errors can commit low-risk actions directly.
2. Undo requires compensating lifecycle operations.
3. Sensitive personalization is unavailable across chats in this scope.

## Migration

Do not execute the superseded confirm-all behavior. Amend and separately
approve the focused evaluation, master plan, semantic-domain policy task, and
user-control child plan before implementing affected runtime behavior.

## Validation

Prove application-event separation, no false saved state, no sensitive durable
write/prompt, confirmation for bulk/scope actions, deterministic conflicts, and
strict Shadow/non-Shadow outcome semantics.

## References

1. Governing amendment.
2. [ADR 0015](./0015-memory-sensitivity-and-confirmed-user-control.md).
