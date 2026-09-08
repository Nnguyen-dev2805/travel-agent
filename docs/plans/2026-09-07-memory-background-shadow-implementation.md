# Memory Background Shadow Implementation Plan

> **For agentic workers:** Execute only after this exact child plan is approved
> and domain/PostgreSQL outputs have passed review.

**Goal:** Capture normal-chat source events atomically and process bilingual
semantic candidates asynchronously as shadow evidence without blocking chat or
creating active versions.

**Architecture:** A PostgreSQL outbox delivers typed handlers at least once.
Workers lease briefly, call the configured structured model outside database
transactions, then revalidate source/deletion/idempotency and persist immutable
shadow evidence through the Unit of Work.

**Tech Stack:** PostgreSQL outbox, Python worker runtime, configured model
adapter, pytest.

**Spec:** Approved focused spec v0.1; ADRs 0013 and 0014 Accepted.

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-07 |
| Scope | Master Tasks 10-11 only |
| Verification | Outbox/lease/retry/model/shadow integration tests |

## Task Table

| Task | Output | Verification |
| --- | --- | --- |
| 1 | Atomic message/outbox capture and typed worker runtime | Runtime integration tests |
| 2 | Structured bilingual model extraction with bounded repair | Adapter and shadow-flow tests |

## Task 1: Outbox and Worker Runtime

**Files:** Create `backend/memory/write_pipeline/outbox.py`, `worker.py`, and
`backend/tests/integration/test_memory_write_runtime.py`; modify the PostgreSQL
conversation repository and conversation orchestrator.

- [ ] Write RED tests for message/outbox atomicity, chat non-blocking, debounce,
  cursor, lease/expiry, parallel owners, same-key serialization, retry classes,
  dead-letter, priority, starvation protection, and deletion cancellation.
- [ ] Implement states `PENDING`, `LEASED`, `SUCCEEDED`, `DEAD_LETTER`, and
  `CANCELLED`; claim briefly and process outside the lease transaction.
- [ ] Revalidate source lifecycle, deletion epoch, versions, and idempotency
  before result commit.
- [ ] Require runtime tests GREEN and review that no model call holds a DB lock.

## Task 2: Structured Model Adapter and Shadow Flow

**Files:** Create `backend/memory/write_pipeline/model_adapter.py` and unit
tests; modify the write-pipeline service and runtime tests.

- [ ] Write RED fake-provider tests for Vietnamese/English normalization,
  strict candidate/relation schemas, one repair, invalid-after-repair,
  timeout/429/5xx, unknown key, pre-model secret rejection, and uncertainty.
- [ ] Implement `MemoryExtractionModel` with model/prompt/schema/version,
  timeout, token, provider-request, retry, and cost evidence.
- [ ] Enforce outcomes limited to `SHADOW`, `HELD_SENSITIVE`,
  `PENDING_CONFLICT`, `REJECTED`, or `INVALID`; create zero active versions.
- [ ] Require adapter and runtime tests GREEN; review prompt/data authority and
  zero fallback auto-promotion.

## Child Verification

Run model-adapter and runtime tests, log/DB content scans, chat timing checks,
and zero-background-promotion assertions.

## Rollback

Disable capture and worker gates independently. Preserve pending/cancelled
outbox evidence; stop processing without deleting canonical messages.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-09-07 for sequential
implementation by a different implementation agent. The current planning agent
is review-only and is not authorized to implement runtime changes, invoke paid
model work for implementation, or perform Git delivery.
