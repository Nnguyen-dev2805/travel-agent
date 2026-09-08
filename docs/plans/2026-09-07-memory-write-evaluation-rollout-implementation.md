# Memory Write Evaluation and Rollout Implementation Plan

> **For agentic workers:** Execute only after this exact child plan is approved
> and all preceding child outputs have passed review.

**Goal:** Implement the focused dataset/harness, prove every quality and hard
gate, resolve legacy data safely, and produce the exact final review packet.

**Architecture:** A deterministic evaluation package owns fixture validation,
scoring, result states, reports, and comparison. Rollout gates remain separate
for explicit writes and background shadow capture. Historical R5/R6 evidence is
preserved rather than rewritten.

**Tech Stack:** Python CLI, JSON/JSONL, pytest, PostgreSQL integration, existing
backend/frontend verification toolchain.

**Spec:** Approved focused spec v0.1; ADR 0016 and evaluation protocol v0.1
Approved.

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-07 |
| Scope | Master Tasks 12-13 only |
| Verification | Focused protocol, migrations, full repository checks, exact diff review |

## Execution Hold

The affected confirmation, sensitivity, conflict-prompt, and Shadow scenarios
remain on hold until the risk-based control amendment and its evaluation
amendment are approved. Unrelated harness structure may be reviewed but must not
freeze obsolete S01, S09, S16, or S17 expectations.

## Task Table

| Task | Output | Verification |
| --- | --- | --- |
| 1 | S01-S22 fixtures, deterministic harness, reports, and CLI | Evaluation unit and CLI tests |
| 2 | Legacy decision, feature gates, docs, and final verification packet | Full plan verification |

## Task 1: Evaluation Harness and Dataset

**Files:** Create `backend/memory/write_pipeline/evaluation/`, its tests, and
`docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1/`.

**Interfaces:** CLI commands `validate-dataset`, `preflight`, `run`, and
`compare`; result states `PASS`, `FAIL`, `INCONCLUSIVE`, `INVALID`.

- [ ] Write RED tests for S01-S22, mandatory slices, metric accounting, hard
  gates, missing-slice invalidation, report redaction, and run metadata.
- [ ] Implement strict loaders, scorers, reports, and synthetic bilingual
  fixtures without real sensitive data.
- [ ] Require unit tests GREEN, then run dataset validation, safety, quality,
  and operational suites.
- [ ] Review every hard-gate example and largest quality failure.

## Task 2: Rollout, Legacy Data, and Package Verification

**Files:** Modify feature configuration, `.env.example`, `DEVELOPMENT.md`,
current-state architecture, umbrella evaluation docs, and create only generated
evidence reports from fresh runs.

- [ ] Inventory SQLite read-only without printing message/candidate content;
  record schema/count/provenance and choose the already-governed disposable or
  quarantine path.
- [ ] Add independent explicit-write and background-shadow gates and exact
  rollback documentation.
- [ ] Run all focused unit/integration tests, migration round trips, protocol
  suites, full backend compile/tests, frontend lint/tests/build, and Docker
  Compose configuration.
- [ ] Inspect `git status --short --untracked-files=all`, `git diff --check`,
  tracked diff, and direct contents of untracked artifacts.
- [ ] Produce the repository-owner review packet with requirement mapping,
  RED/GREEN evidence, reports, migration result, limitations, rollback, and no
  Git-delivery claim.

## Child Verification

All approved protocol commands and full repository commands must exit zero.
Unavailable required evidence makes the result invalid or inconclusive, never
passed.

## Rollback

Disable both gates, stop workers, preserve diagnostic outbox evidence, use only
reviewed Alembic downgrade paths, rebuild derived indexes, and never resurrect
deleted content.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-09-07 for sequential
implementation by a different implementation agent. The current planning agent
is review-only and may assess fixtures, reports, verification output, and the
exact change set, but it is not authorized to implement or perform Git delivery.
