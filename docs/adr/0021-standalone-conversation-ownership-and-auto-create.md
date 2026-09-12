# ADR 0021: Standalone Conversation Ownership, Route Contract, and Auto-Create Behavior

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-10 |
| Decision owners | Repository owner |
| Scope | Conversation domain model, route contract, auto-create-on-first-chat, and direct message append removal |
| Governing spec | [Authenticated Chat-Only PostgreSQL Clean Break](../specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md), version 0.1 (Approved) |
| Superseded ADR | [ADR 0011](./0011-authenticated-standalone-conversations.md) for optional workspace association and first-turn creation — this ADR makes workspace association permanent zero and removes direct message append |
| Superseded by | None |

## Context

ADR 0011 established standalone conversations with optional `workspace_id` and
first-turn creation. After the clean-break spec, there is no Workspace concept
remaining in the mounted product. Keeping `workspace_id` as a nullable field
retains an inactive foreign key, unused code paths, and misleading domain
semantics.

Additionally, `backend/app/api/conversations.py` currently exposes a direct
message append route that allows callers to post user or assistant messages
without going through the Chat orchestration path. This bypasses message/outbox
atomicity, role validation, and generation ordering.

The clean-break spec removes `workspace_id` from the Conversation domain and
makes direct public message append impossible.

## Decision

The `Conversation` domain model after the clean break:

```
Conversation
  conversation_id    (immutable)
  owner_user_id      (NOT NULL, set exclusively from authenticated principal)
  title              (optional, set on create or first turn)
  retention_state    (active | tombstoned)
  created_at
  updated_at
```

`workspace_id` is removed from the domain model, service, PostgreSQL adapter,
Alembic schema, and all API schemas. No nullable foreign key to a workspace is
retained.

The `RuntimeContainer` module owns process-scoped PostgreSQL pool creation and
constructs `PostgresConversationRepository`, `ConversationService`, and
`ConversationOrchestrator`. FastAPI routes depend on provider interfaces from
this module and do not construct adapters independently.

Auto-create behavior: `POST /api/v1/chat` without a `conversation_id` creates a
standalone conversation owned by the authenticated principal, persists the user
message and optional extraction outbox intent in one transaction, calls RAG
generation, and returns the new `conversation_id` with persistence metadata. The
caller is not required to create a conversation before the first chat message.

Explicit create: `POST /api/v1/conversations` remains available for clients
that need a conversation ID before the first message.

Direct public message append is removed. User messages enter exclusively through
`POST /api/v1/chat`. Assistant and tool messages are application-owned. This
prevents callers from forging transcript roles or bypassing message/outbox
atomicity.

The `ConversationService` requires an authenticated owner for create, get, list,
append, history, and delete. It never resolves ownership through a Workspace.

Cross-owner create, read, list, history, and delete are denied without
enumeration: foreign or missing conversations return `404`, not `403`.

## Alternatives

### Retain nullable workspace_id for forward compatibility

Avoids migration cost and preserves the possibility of future workspace
re-association. Maintains dead code paths, misleading domain semantics, and an
unused foreign key in a table the application no longer manages. Rejected.

### Allow direct message append through the conversations API

Reduces frontend complexity for clients that build their own chat loops.
Bypasses message ordering, outbox atomicity, and role validation enforced by the
orchestration path. Creates a second entry point that can produce inconsistent
transcript state. Rejected.

### Keep workspace_id but make it write-once on conversation create

Preserves the association slot without the overhead of keeping the workspaces
table. Still requires code paths and test coverage for the association semantics
that are explicitly not part of this milestone. Rejected.

### No workspace_id, Chat-only message entry, RuntimeContainer isolation

Produces the smallest domain model and the only message entry point through the
controlled orchestration path. Selected.

## Consequences

### Positive

1. The conversation domain model maps to exactly what is stored and shown; no
   inactive fields or dead foreign keys.
2. Message ordering, outbox atomicity, and role validation are enforced at the
   only message entry point.
3. Owner identity cannot be set by the caller; BOLA is structurally prevented.
4. `RuntimeContainer` isolates adapter construction; routes are testable with
   interface fakes.

### Negative

1. Clients that previously used direct message append must migrate to the Chat
   path; this is a breaking API change.
2. The nullable `workspace_id` migration requires an Alembic revision and
   verification that no active foreign key constraints exist.
3. Auto-create behavior means `POST /chat` has a side effect; clients that send
   duplicate first messages may create multiple conversations if they do not
   persist the returned `conversation_id`.

## Migration

Add Alembic clean-break revision: drop `workspace_id` column and its
constraints from `conversations`. Verify that the `workspaces` table (if
retained as a compatibility artifact) has no dependent foreign key before
dropping. Remove `workspace_id` from `ConversationCreate`, `Conversation`, and
all API schemas. Remove direct message append route from `conversations.py`.
Add `RuntimeContainer` module as the sole adapter construction site.

## Validation

1. `Conversation` model and all serialization schemas contain no `workspace_id`.
2. Final PostgreSQL schema contains no `conversations.workspace_id` column.
3. Auto-create first-turn: `POST /chat` without `conversation_id` creates a
   conversation and returns `conversation_id` in response.
4. Explicit create: `POST /conversations` creates a conversation owned by the
   principal.
5. Cross-owner read/list/history/delete returns content-free `404`.
6. Direct message append route (`POST /conversations/{id}/messages`) returns
   `404` (unmounted).
7. `RuntimeContainer` unit test verifies adapter construction order and
   interface contracts.

## References

1. [Authenticated Chat-Only PostgreSQL Clean Break](../specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md), v0.1.
2. [ADR 0011](./0011-authenticated-standalone-conversations.md) — superseded for workspace association.
3. [ADR 0014](./0014-transactional-outbox-and-idempotent-memory-workers.md) — outbox atomicity preserved.
