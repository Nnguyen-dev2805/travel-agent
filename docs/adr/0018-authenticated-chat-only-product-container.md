# ADR 0018: Authenticated Chat-Only Product Container

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-10 |
| Decision owners | Repository owner |
| Scope | Mounted product surface, authentication enforcement, and removal of Workspace and Planner runtime behavior |
| Governing spec | [Authenticated Chat-Only PostgreSQL Clean Break](../specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md), version 0.1 (Approved) |
| Superseded ADR | [ADR 0002](./0002-trip-workspace-as-primary-product-container.md) for workspace-as-product-container; [ADR 0008](./0008-workspace-owned-planner-state-and-operation-log.md) for Planner surface; [ADR 0010](./0010-local-identity-authorization-and-deletion-boundary.md) for AUTH_REQUIRED compatibility mode |
| Superseded by | None |

## Context

The repository currently mounts eight routers: health, ops, chat, conversations,
workspaces, planner, memory, and memory_controls. These routers represent two
incompatible product models — Workspace-first with SQLite and standalone
conversation with PostgreSQL — at the same time. The `AUTH_REQUIRED=false`
compatibility flag allows unauthenticated access to owner-scoped routes.

Fresh evidence shows that the bound chat integration fails because
`ConversationCreate.owner_user_id` requires an authenticated principal that the
Workspace-first path did not supply. Continuing agent and Memory work on this
mixed base would multiply compatibility branches without a coherent mounted
behavior.

The approved clean-break spec selects a single product container — an
authenticated standalone Chat — before the Single-Step Context Agent is
implemented.

## Decision

The mounted HTTP surface is reduced to exactly:

| Route | Authentication |
| --- | --- |
| `GET /health` | Public — liveness only, no dependency detail |
| `GET /api/v1/ops/readiness` | Required |
| `POST /api/v1/chat` | Required |
| `POST /api/v1/conversations` | Required |
| `GET /api/v1/conversations` | Required |
| `GET /api/v1/conversations/{conversation_id}` | Required |
| `GET /api/v1/conversations/{conversation_id}/messages` | Required |
| `DELETE /api/v1/conversations/{conversation_id}` | Required |

`AUTH_REQUIRED` and the unauthenticated compatibility principal are removed.
`require_principal` always requires a valid `Authorization: Bearer <token>`.
`get_optional_principal` and `AuthMode.COMPATIBILITY` are removed.

Owner identity comes exclusively from the authenticated principal. Request bodies
and query strings cannot select another owner.

Workspace, Planner, legacy Memory, and Memory Manager routes are unmounted and
their source is deleted. Removed routes return unmounted `404`; no compatibility
proxy or redirect is added.

CORS wildcard is prohibited; only explicitly configured origins are accepted.

## Alternatives

### Keep all routers mounted, gate legacy routes with feature flags

Reduces deletion work and eases rollback. Retains hundreds of legacy imports,
conflicting ownership models, and misleading architecture. Agents working on
top of it continue to produce compatibility branches. Rejected.

### Unmount legacy routes but retain their source in the repository

Routes stop responding but the source remains. Import chains and test coupling
persist. The next feature can silently re-activate a removed behavior. Rejected.

### Delete Workspace and Planner but retain legacy Memory surface

Partial cleanup leaves the split persistence authority and the user-facing
Memory command surface. Memory and Auth coupling remain ambiguous. Rejected.

### Authenticated Chat-only surface with full source deletion

Breaks removed URL compatibility deliberately, produces the smallest honest
runtime, and establishes one storage authority before adaptive context work
begins. Selected.

## Consequences

### Positive

1. Every protected route requires a real credential; no anonymous owner-scope
   access is possible at the application layer.
2. Route ownership, auth, and test boundaries are unambiguous.
3. Agent and Memory development starts from a known-clean surface.
4. Frontend auth gating is unconditional and testable.

### Negative

1. Workspace, Planner, and legacy Memory URL compatibility is intentionally
   broken. External consumers of those URLs are blocked until a future approved
   design restores needed behavior.
2. Source deletion is a one-way operation; rollback requires restoring from Git
   history plus a separately approved design.
3. Existing development tokens remain valid; token expiry is deferred to a
   separate identity-provider decision.

## Migration

Stop old runtime. Apply PostgreSQL migrations. Start authenticated Chat runtime.
Run verification. Delete legacy source and data. Do not dual-write or proxy
removed URLs. Removed Workspace, Planner, legacy Memory, and Memory Manager
behavior may be restored only by a separately approved design, not an emergency
hidden flag.

## Validation

1. Static import scan: no mounted backend source imports Workspace, Planner,
   legacy Memory, or Memory Controls after completion.
2. Every protected route rejects missing, malformed, and invalid credentials.
3. No compatibility principal is created at any code path.
4. Removed URL paths return `404`; no redirect or proxy intercepts them.
5. Wildcard CORS fails configuration validation.
6. Frontend build contains no route, button, drawer, modal, or service for
   removed capabilities.

## References

1. [Authenticated Chat-Only PostgreSQL Clean Break](../specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md), v0.1.
2. [ADR 0002](./0002-trip-workspace-as-primary-product-container.md) — superseded.
3. [ADR 0008](./0008-workspace-owned-planner-state-and-operation-log.md) — superseded.
4. [ADR 0010](./0010-local-identity-authorization-and-deletion-boundary.md) — AUTH_REQUIRED removal.
5. [ADR 0011](./0011-authenticated-standalone-conversations.md) — standalone conversation ownership retained.
6. [ADR 0026](./0026-authentication-enforced-in-middleware-before-body-parsing.md) — extends this decision with the enforcement location and the default-deny model. This ADR stated that authentication is unconditional; it did not state where in the request pipeline it is enforced, and that omission allowed a body-parsing error to answer `422` before the authentication decision ran.
