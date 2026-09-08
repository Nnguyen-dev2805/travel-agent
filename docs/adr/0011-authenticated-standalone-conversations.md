# ADR 0011: Authenticated Standalone Conversations

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-07 |
| Decision owners | Repository owner |
| Scope | Conversation ownership, first-turn creation, and optional workspace association |
| Governing spec | [Basic Semantic Memory Write Pipeline Design](../specs/2026-09-07-basic-semantic-memory-write-pipeline-design.md), version 0.1 (Approved) |
| Superseded ADR | [ADR 0002](./0002-trip-workspace-as-primary-product-container.md) and [ADR 0005](./0005-conversation-orchestration-seam-and-optional-chat-binding.md) for mandatory-workspace and unbound-chat behavior; retained orchestration and persistence-order rules carry forward |
| Superseded by | None |

## Context

The current conversation model requires a workspace and inherits its owner.
Unbound chat generates an answer without persistence. The approved focused
design requires an authenticated user to start a persistent chat immediately,
while preserving optional future project/workspace association.

## Decision

`Conversation` owns `owner_user_id` directly and accepts nullable
`workspace_id`. Authenticated `POST /chat` without `conversation_id` creates a
standalone conversation, persists the user and assistant turns, and returns the
new conversation identity. Guest durable conversation and memory are excluded.

An existing workspace-bound conversation remains valid after owner backfill.
No hidden default workspace is created. Workspace scope remains reserved and
inactive for the first semantic-memory slice.

## Alternatives

### Hidden workspace per user

Reduces migration work but creates a false product concept, keeps memory coupled
to workspaces, and makes later project semantics ambiguous. Rejected.

### Keep unbound chat non-persistent

Preserves current behavior but prevents cross-conversation continuity and the
approved ChatGPT-like entry experience. Rejected.

### Direct owner plus optional workspace

Requires migration and broader ownership tests but expresses both standalone
and project conversations honestly. Selected.

## Consequences

### Positive

1. Users can begin a persistent chat without setup ceremony.
2. Owner isolation no longer depends on workspace existence.
3. Future projects can associate conversations without defining a fake parent.

### Negative

1. Existing rows require owner backfill through their workspace.
2. Repository, authorization, deletion, API, and tests must support nullable
   workspace association.
3. ADR 0002 and ADR 0005 need explicit partial-supersession updates if accepted.

## Migration

Add owner identity, backfill only from resolved workspaces, verify mismatches,
then make owner non-null. Preserve workspace IDs where present. No missing or
foreign workspace may produce an invented owner.

## Validation

Prove standalone first-turn persistence, owner-scoped list/get/chat, existing
workspace compatibility, cross-owner denial, and controlled migration failure.

## References

1. Governing focused specification.
2. [ADR 0002](./0002-trip-workspace-as-primary-product-container.md).
3. [ADR 0005](./0005-conversation-orchestration-seam-and-optional-chat-binding.md).
