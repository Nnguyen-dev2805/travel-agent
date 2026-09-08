# Risk-based Memory Control Amendment Implementation Plan

> **For agentic workers:** Execute affected tasks only with their approved
> child plan and this approved amendment delta. It replaces confirmation behavior in the existing approved master and
> user-control plans without widening unrelated runtime scope.

**Goal:** Align approved implementation artifacts with risk-based confirmation,
application-owned save events, sensitive no-store, pending conflicts, and exact
Shadow semantics.

**Architecture:** Reuse the existing command handler, policy, resolver, Unit of
Work, UI, worker, and evaluation seams. Remove preview/token requirements from
low-risk actions; retain them for bulk delete and scope expansion.

**Tech Stack:** FastAPI, Pydantic, React/Vite, pytest, Vitest.

**Spec:** Risk-based Memory Control Amendment v0.1, Approved.

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-07 |
| Scope | Documentation and later implementation deltas for master Tasks 5, 8-9, 11-12 only |

## Task Table

| Task | Change | Verification |
| --- | --- | --- |
| 1 | Update domain/policy contracts for sensitive no-store and exact Shadow outcome | Policy/outcome unit tests |
| 2 | Update command backend for direct low-risk mutation, Undo, and bounded preview tokens | API/service tests |
| 3 | Update UI for application-owned save/update events and risk-based confirmation | Vitest/accessibility tests |
| 4 | Update focused evaluation scenarios and hard gates | Evaluation unit/CLI tests |

## Required Contract Changes

```text
remember low-risk -> direct commit -> MemorySavedEvent
delete-one/toggle -> direct commit -> UndoOperation
bulk-delete/scope-expansion -> preview -> token -> confirm -> commit
sensitive/restricted/prohibited -> no durable write and no save prompt
ambiguous relation -> PENDING_CONFLICT
valid below promotion authority -> SHADOW
```

## Verification

Run the amended policy, command API, user-control UI, background shadow, and
evaluation tests. Re-run all unchanged hard gates from the approved base
protocol. Inspect exact documentation and code diff for accidental confirm-all
or sensitive-prompt behavior.

## Rollback

Disable affected feature gates. Do not fall back to confirm-all silently; a
rollback that changes user-visible confirmation semantics requires owner review.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-09-08. It supersedes
the affected portions of the approved master, semantic-domain policy,
user-control, background, and evaluation plans. Unrelated child plans remain
valid. Runtime implementation still requires the applicable approved child
plan, isolated-worktree preflight, review, and verification.
