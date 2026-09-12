# ADR 0019: PostgreSQL-Only Application Relational Persistence and SQLite Retirement

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-10 |
| Decision owners | Repository owner |
| Scope | Application relational storage authority, SQLite adapter removal, and Alembic migration contract |
| Governing spec | [Authenticated Chat-Only PostgreSQL Clean Break](../specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md), version 0.1 (Approved) |
| Superseded ADR | [ADR 0003](./0003-local-sqlite-workspace-storage-boundary-for-r3.md) for SQLite as primary store; [ADR 0004](./0004-shared-local-application-store-and-per-module-schema-registry.md) for shared SQLite schema registry |
| Superseded by | None |

## Context

The repository currently operates two relational persistence generations in
parallel: an application-owned SQLite store with a shared schema registry
(`backend/storage/schema_registry.py`) for Workspace, Conversation, legacy
Memory, and Planner; and a PostgreSQL adapter
(`backend/conversations/postgres_repository.py`) with Alembic migrations for
standalone conversations, messages, and outbox.

Evidence gathered before the clean-break design:
- `backend/conversations/sqlite_repository.py`, `backend/memory/sqlite_repository.py`, and `backend/planner/sqlite_repository.py` all import `sqlite3` and depend on `APP_DB_PATH`.
- `backend/observability/readiness.py` probes application SQLite schema version, not PostgreSQL Alembic revision.
- Tests in `backend/tests/integration/` silently skip PostgreSQL assertions when no DSN is set, allowing SQLite behavior to masquerade as PostgreSQL coverage.
- `backend/storage/schema_registry.py` manages versioned DDL for multiple modules, coupling schema management to application source code.

Continuing with split persistence creates cross-store atomicity risk, misleading
readiness signals, duplicate ownership models, and ongoing test-skip acceptance.

## Decision

PostgreSQL is the only application relational source of truth after the clean
break. "Remove SQLite" means:

- Deleting `APP_DB_PATH`, `WORKSPACE_DB_PATH`, and default SQLite path helpers from configuration.
- Deleting `backend/storage/schema_registry.py` and the shared DDL management pattern.
- Deleting all `sqlite_repository.py` adapters (`conversations`, `memory`, `planner`).
- Deleting application SQLite volumes, generated database files, and documentation that instructs users to initialize or inspect application SQLite.

It does not mean replacing Chroma. Chroma is an RAG/vector-store dependency
that may use SQLite internally; its persistence is not under this application's
ownership. Chroma replacement requires a separate retrieval-storage decision.

Alembic migration history is append-only. The clean-break revision:
1. Ensures `conversations.owner_user_id` is NOT NULL.
2. Removes `conversations.workspace_id` and its indexes and constraints.
3. Removes the PostgreSQL `workspaces` compatibility table after dependency checks.
4. Preserves `messages` and `conversation_outbox` foreign keys and V2 Memory tables.
5. Adds owner, retention, and index constraints required by standalone list and history.
6. Upgrades and downgrades safely in an isolated database.

Existing revisions are not rewritten. Final-schema verification, not
intermediate presence, defines success.

Observability readiness probes PostgreSQL connectivity and Alembic revision,
not SQLite schema version.

Required PostgreSQL integration tests run with zero required skips; silently
skipping database assertions is not accepted after this change.

Before deleting any local database file, an inventory of table names and row
counts is recorded. If any non-synthetic or user-valued data exists, deletion
stops for an explicit disposal decision.

## Alternatives

### Dual-write SQLite and PostgreSQL during migration

Supports gradual cutover without a forced stop. Introduces cross-store
atomicity, reconciliation, conflict authority, and rollback direction problems
without evidence of production traffic requiring them. Rejected.

### Keep SQLite as read-only fallback for legacy data

Prevents immediate data loss if synthetic assumption is wrong. Retains the
dual-authority problem, maintains SQLite import chains, and defers the cleanup
cost. Rejected.

### PostgreSQL-only with clean-cut source deletion

Inventory legacy data, build PostgreSQL replacement, cut over once, then delete.
Loses old URL compatibility but produces one storage authority. Rollback before
cutover is branch abandonment; after cutover is backup restore. Selected.

## Consequences

### Positive

1. One authoritative relational store simplifies ownership, readiness, and testing.
2. Schema changes use the established Alembic workflow; no parallel DDL registry.
3. Readiness correctly reflects whether conversation and Memory tables are
   migration-current.
4. PostgreSQL RLS and application owner checks apply uniformly.

### Negative

1. Local development requires PostgreSQL; the convenience of a zero-setup SQLite
   store is lost.
2. Tests that previously skipped PostgreSQL assertions must be updated or removed.
3. Data disposal of any non-synthetic SQLite content requires explicit operator
   action before file deletion.

## Migration

Before deletion: run read-only SQLite inventory. Record table names and row
counts. If non-synthetic data exists, halt and obtain disposal decision. Apply
clean-break Alembic revision. Verify upgrade, downgrade, and re-upgrade on an
isolated database. Delete SQLite files, adapters, schema registry, and
configuration only after PostgreSQL runtime is verified green.

## Validation

1. `python -m compileall backend` exits clean: no `sqlite3`, `APP_DB_PATH`,
   `schema_registry` import in mounted backend source.
2. Alembic upgrade, downgrade, and re-upgrade pass on an isolated schema.
3. Final schema contains no `workspace_id` column or `workspaces` table.
4. `observability/readiness.py` probes PostgreSQL revision, not SQLite.
5. All required PostgreSQL integration tests run with zero skips.
6. No SQLite file path or `APP_DB_PATH` reference remains in `.env.example`,
   `docker-compose*.yml`, `DEVELOPMENT.md`, or `ARCHITECTURE.md`.

## References

1. [Authenticated Chat-Only PostgreSQL Clean Break](../specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md), v0.1.
2. [ADR 0003](./0003-local-sqlite-workspace-storage-boundary-for-r3.md) — superseded.
3. [ADR 0004](./0004-shared-local-application-store-and-per-module-schema-registry.md) — superseded.
4. [ADR 0011](./0011-authenticated-standalone-conversations.md) — PostgreSQL conversation adapter retained.
5. [ADR 0012](./0012-versioned-semantic-memory-in-postgresql.md) — V2 Memory tables retained.
