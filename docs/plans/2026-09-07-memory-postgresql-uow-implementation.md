# Memory PostgreSQL and Unit of Work Implementation Plan

> **For agentic workers:** Execute only after this exact child plan is approved
> and the standalone/domain child outputs have passed review.

**Goal:** Persist owned conversations and semantic evidence/assertion/version
changes atomically and idempotently in PostgreSQL.

**Architecture:** SQLAlchemy Core and Alembic own schema/migrations. One
`MemoryUnitOfWork` locks an assertion, re-resolves current state, and commits
evidence, decision, version, trace, and outbox together under application
authorization plus RLS.

**Tech Stack:** PostgreSQL, SQLAlchemy Core, Alembic, psycopg, pytest.

**Spec:** Approved focused spec v0.1; ADR 0012 Accepted.

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-07 |
| Scope | Master Tasks 6-7 only |
| Verification | Migration, constraint, RLS, rollback, idempotency, concurrency |

## Task Table

| Task | Output | Verification |
| --- | --- | --- |
| 1 | PostgreSQL configuration, metadata, and reversible migrations | Migration round-trip tests |
| 2 | Atomic owner-scoped Unit of Work | Failure/concurrency integration tests |

## Task 1: PostgreSQL and Migrations

**Files:** Modify `requirements.txt`, `docker-compose.yml`, `.env.example`, and
`backend/app/config.py`; create `alembic.ini`, `backend/storage/postgres.py`,
`backend/storage/migrations/`, `backend/conversations/postgres_repository.py`,
and `backend/tests/integration/test_postgres_migrations.py`.

- [ ] Write RED migration tests for empty upgrade, owned-conversation backfill,
  all normalized tables, constraints, RLS, downgrade, and re-upgrade.
- [ ] Add pinned dependencies and safe local PostgreSQL configuration without
  secret values.
- [ ] Implement typed columns, registry-validated JSONB, owner constraints,
  prefixed text IDs, indexes, and reversible Alembic revisions.
- [ ] Require migration tests GREEN.
- [ ] Review SQL, downgrade safety, tenant-context reset, and legacy boundaries.

## Task 2: MemoryUnitOfWork

**Files:** Create `backend/memory/write_pipeline/uow.py`,
`backend/memory/write_pipeline/postgres.py`, and
`backend/tests/integration/test_memory_write_postgres.py`.

**Interface:**

```python
apply_memory_change(change: MemoryChangeSet,
                    principal: AuthenticatedPrincipal) -> MemoryWriteResult
```

- [ ] Write RED tests for every operation, missing tenant context, cross-owner,
  duplicate idempotency key, stale version, concurrent writers, and injected
  failure after every write stage.
- [ ] Implement `READ COMMITTED`, insert-or-resolve assertion, `FOR UPDATE`,
  fresh re-resolution, atomic immutable writes, outbox insert, and bounded retry.
- [ ] Require GREEN and zero partial state.
- [ ] Review that no external model/network call occurs inside the transaction.

## Child Verification

Run migration round trips and PostgreSQL integration tests in isolated state;
inspect schema diff, dependency lock/source, `git diff --check`, and full status.

## Rollback

Disable the new adapter, stop consumers, and use only reviewed Alembic downgrade
paths that cannot resurrect deleted data. Preserve legacy state as inert.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-09-07 for sequential
implementation by a different implementation agent. The current planning agent
is review-only and is not authorized to implement runtime changes, install
dependencies, run migrations against user data, or perform Git delivery.
