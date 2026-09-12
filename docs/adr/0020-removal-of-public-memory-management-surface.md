# ADR 0020: Removal of Public Memory Management Surface

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-10 |
| Decision owners | Repository owner |
| Scope | User-facing Memory control API, Memory Manager UI, and command-service boundary |
| Governing spec | [Authenticated Chat-Only PostgreSQL Clean Break](../specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md), version 0.1 (Approved) |
| Superseded ADR | [ADR 0015](./0015-memory-sensitivity-and-confirmed-user-control.md) for the user-control surface; [ADR 0017](./0017-risk-based-memory-confirmation.md) for risk-based confirmation (risk rules remain historical input) |
| Superseded by | None |

## Context

The repository currently exposes a separate public Memory management API at
`/memory/controls` and a Memory Manager drawer in the frontend. This surface
supports list, remember, correct, forget, toggle, expand, and confirm Memory
operations through `MemoryCommandService`.

Evidence from the clean-break design:
- `backend/app/api/memory_controls.py` mounts routes that depend on command-specific parser branches, preview tokens, and confirmation flows.
- `backend/app/api/memory.py` mounts legacy extraction and promotion routes that depend on SQLite and Workspace.
- `frontend/src/components/memory/MemoryManager.jsx` and `MemoryConfirmation.jsx` expose Memory state management to users.
- `backend/memory/service.py` bundles background formation logic with user-initiated command handling in a single service.

The approved clean-break spec selects a narrower background-only Memory
interface as the next stable baseline. The user-control surface adds complexity
without being required for the Single-Step Context Agent milestone. Risk rules
from ADR 0017 remain as historical input for any future Chat command design.

## Decision

The public Memory management surface is removed:

- No Memory Manager drawer, MemoryConfirmation component, or Memory service in the frontend.
- No public list, remember, correct, forget, toggle, expand, or confirm Memory endpoints.
- No explicit Memory command parsing in this cleanup release.
- `backend/app/api/memory.py` (legacy extraction/promotion) and `backend/app/api/memory_controls.py` are deleted.
- Frontend Memory services, components, and tests whose only subject is the removed UI are deleted.

"Remove public Memory management" does not authorize orphaning private data.
Conversation and account retention operations must still invalidate or delete
dependent Memory evidence, pending outbox work, active versions, summaries,
episodes, and search projections when those records exist.

The background Memory worker must not depend on `MemoryCommandService` after
user-control removal. A narrow `BackgroundMemoryRecorder` interface records a
validated shadow candidate through the existing policy/resolver/UoW seams. It
exposes no user-initiated methods.

Preserved V2 modules:
- Registry and immutable models.
- Secret detection (`write_pipeline/secrets.py`).
- Policy and resolver.
- Memory UoW and PostgreSQL adapter.
- Outbox state and worker.
- Structured extraction model adapter.
- Focused non-legacy background evaluation (`write_pipeline/evaluation/`).

Command-only types, parser branches, preview state, confirmation tokens, direct
delete helpers, UI response events, HTTP schemas, routes, and their tests are
removed.

A future approved Chat command design may reintroduce explicit Memory controls
without restoring the Memory Manager.

## Alternatives

### Retain Memory Manager but gate with a feature flag

Keeps the surface dormant but keeps its source, imports, test coupling, and
maintenance burden. An accidental flag enables behavior that is not part of the
clean-break baseline. Rejected.

### Remove only the frontend Memory UI but keep the backend API

Reduces frontend deletion. Leaves unmounted or orphaned backend routes, command
parsers, and confirmation flows that mislead future agents about what is active.
Rejected.

### Delete command service but keep Memory endpoints wired to a stub

Stubs mask real failures and produce misleading test results. Rejected.

### Remove full public surface, preserve background V2 domain

Yields the smallest honest backend surface while retaining the approved
background Memory capability needed for extraction, policy, and future Read/Use.
Selected.

## Consequences

### Positive

1. Backend source contains no user-facing Memory command parsing or confirmation
   tokens; the attack surface is reduced.
2. Background Memory worker has a single narrow interface with no command
   coupling; its behavior is testable in isolation.
3. Frontend build contains no Memory drawer, modal, or service for the removed
   surface.
4. Privacy deletion obligations remain through conversation retention propagation.

### Negative

1. Users cannot explicitly list, add, correct, or delete Memory entries in this
   milestone. A future approved Chat command design is required to restore it.
2. ADR 0015 and ADR 0017 are superseded; their risk rules and confirmation model
   remain historical evidence only.
3. Any extraction outbox events accumulated before the removal must be drained or
   cancelled by operator action; they cannot be confirmed through the removed UI.

## Migration

Remove `/memory/controls` and `/workspaces/*/memory` routers from
`backend/app/main.py`. Delete `backend/app/api/memory.py`,
`backend/app/api/memory_controls.py`, and command-specific modules. Introduce
`BackgroundMemoryRecorder` interface using the existing policy/resolver/UoW
seams. Update the background worker to depend only on the narrow recorder
interface. Verify that V2 preserved modules import cleanly without
command-service imports.

## Validation

1. Static import scan: no mounted backend source imports legacy Memory route,
   command parser, or Memory Controls schema.
2. Removed URL paths (`/memory/controls/*`, `/workspaces/*/memory/*`) return
   `404`.
3. V2 preserved modules (`write_pipeline/`) pass their retained unit tests
   without command-service dependency.
4. `BackgroundMemoryRecorder` unit tests prove correct policy/resolver/UoW
   delegation without user-initiated methods.
5. Frontend build contains no `MemoryManager`, `MemoryConfirmation`, or Memory
   service imports.
6. Conversation delete propagation test confirms Memory evidence is invalidated
   when propagation is wired, or delete fails closed when not wired.

## References

1. [Authenticated Chat-Only PostgreSQL Clean Break](../specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md), v0.1.
2. [ADR 0015](./0015-memory-sensitivity-and-confirmed-user-control.md) — superseded.
3. [ADR 0017](./0017-risk-based-memory-confirmation.md) — superseded (risk rules remain historical input).
4. [ADR 0013](./0013-model-assisted-extraction-and-deterministic-resolution.md) — extraction model adapter retained.
5. [ADR 0014](./0014-transactional-outbox-and-idempotent-memory-workers.md) — outbox and worker retained.
6. [ADR 0016](./0016-focused-memory-write-evaluation-and-rollout.md) — evaluation harness retained.
