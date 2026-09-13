# Memory User Controls Implementation Plan

> **Historical plan — do not execute as current authority.** ADR 0020 and the
> authenticated Chat/PostgreSQL clean break removed the dedicated public Memory
> Manager/control API. Explicit Memory behavior in the approved target returns
> through Chat and is governed by ADR 0036 plus the Agent Memory implementation
> plan v0.5.

**Historical goal:** Let authenticated users inspect and perform confirmed remember,
correct, delete, enable, and disable operations through UI and natural language
without duplicating policy or persistence logic.

**Historical architecture:** One `MemoryCommandHandler` produces previews and confirmation
tokens, then revalidates and commits through the accepted policy/resolver/UoW.
The dedicated Memory Manager and conversational commands consume the same HTTP
contracts.

**Tech Stack:** FastAPI, Pydantic, React/Vite, Vitest, pytest.

**Historical spec:** Focused spec v0.1 as amended at the time by the Risk-based
Memory Control Amendment. That public-control authority is now superseded; use
the 2026-09-12 Agent Memory authority chain for current implementation.

| Field | Value |
| --- | --- |
| Status | Superseded |
| Version | 0.1 |
| Date | 2026-09-07 |
| Scope | Master Tasks 8-9 only |
| Verification | Backend command/API and frontend interaction/accessibility tests |
| Superseded by | [ADR 0020](../adr/0020-removal-of-public-memory-management-surface.md) for public controls; [Agent Memory Target Architecture Implementation Plan](./2026-09-12-agent-memory-target-architecture-implementation.md) v0.5 for Chat-native explicit Memory |

## Historical Amendment Authority

The
[Risk-based Memory Control Amendment](../specs/2026-09-07-risk-based-memory-control-amendment.md)
v0.1 and [ADR 0017](../adr/0017-risk-based-memory-confirmation.md) governed this
historical child at the time. Both are now superseded for the public-control
surface; their risk semantics are historical input only and do not authorize
restoring the removed UI/API.

## Task Table

| Task | Output | Verification |
| --- | --- | --- |
| 1 | Confirmed command backend and HTTP contract | Service/API integration tests |
| 2 | Dedicated Memory Manager and confirmation UI | Vitest, accessibility review, build |

## Task 1: Command Handler and API

**Files:** Create `backend/memory/write_pipeline/service.py`,
`backend/app/schemas/memory_controls.py`, `backend/app/api/memory_controls.py`,
unit/integration tests; modify `backend/app/main.py`.

**Interfaces:** `propose_command(...) -> MemoryCommandPreview` and
`confirm_command(command_id, confirmation_token, principal) -> MemoryWriteResult`.

- [ ] Write RED tests for remember, correct, delete, enable, disable, refusal,
  expiry, stale preview, cross-owner IDs, exact operation/scope display, and no
  success acknowledgement before commit.
- [ ] Implement stored preview/confirmation with owner, expected version,
  sensitivity, expiry, and deletion-epoch revalidation.
- [ ] Require backend tests GREEN.
- [ ] Review every mutation path through the same handler/policy/resolver/UoW.

## Task 2: Memory Manager UI

**Files:** Create `frontend/src/services/memory.js`,
`frontend/src/components/memory/MemoryManager.jsx`,
`frontend/src/components/memory/MemoryConfirmation.jsx`, and
`frontend/tests/memory-manager.test.jsx`; modify `frontend/src/App.jsx`.

- [ ] Write RED tests for loading, empty, error, inspect, preview, confirmation,
  refusal, stale state, keyboard/focus behavior, and refresh.
- [ ] Implement minimal accessible UI using existing auth/client/styles; show
  exact key, display value, scope, source summary, and operation.
- [ ] Require Vitest GREEN and production build success.
- [ ] Review interruption cost, confirmation clarity, responsive behavior, and
  parity with conversational commands.

## Child Verification

Run focused backend control tests, all frontend tests, lint, and build. Inspect
response/log redaction and cross-owner behavior.

## Rollback

Disable user-control routes and UI entry while preserving canonical memory
state. Pending unconfirmed previews may expire; no durable mutation is undone
implicitly.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-09-07 for sequential
implementation by a different implementation agent. The current planning agent
is review-only and is not authorized to implement runtime or UI changes or
perform Git delivery.
