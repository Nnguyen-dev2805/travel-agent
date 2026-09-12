# ADR 0022: Clean-Break Migration, Data Disposal, and Rollback Authority

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-10 |
| Decision owners | Repository owner |
| Scope | Migration strategy, legacy data disposal contract, and rollback boundaries |
| Governing spec | [Authenticated Chat-Only PostgreSQL Clean Break](../specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md), version 0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

The clean-break spec requires a one-time cutover from Workspace-first SQLite to
authenticated standalone PostgreSQL Chat. This ADR records the migration
strategy, the data disposal contract for legacy SQLite files, and the rollback
boundaries that apply at each stage.

The repository has three local SQLite database files in active use during
development: the shared application store (`APP_DB_PATH`) holding Workspace,
legacy Conversation, legacy Memory, and Planner tables; and potentially others
created by schema registry initialization. Before any file deletion, an
inventory read must determine whether any non-synthetic or user-valued data
exists.

The Alembic migration history for PostgreSQL is the authoritative change log
and must remain append-only. Rewriting revisions that may have been applied
in development or CI is prohibited.

## Decision

The migration strategy is **clean cutover**, not dual-write:

```text
1. old runtime off
2. PostgreSQL migrations (append-only clean-break revision)
3. authenticated Chat runtime on
4. verification
5. legacy source/data removal
```

**SQLite Data Disposal Contract**:
Before deleting any local database file, record table names and row counts
without reading or printing content. If any table contains non-synthetic or
user-valued rows, stop and obtain an explicit disposal/export decision from the
repository owner. Empty or synthetic development state may be removed under
this approved clean break without a separate export step.

The SQLite inventory is conducted with a read-only connection (`mode=ro`).
The inventory module (`sqlite_inventory.py`) produced for Child Plan 6 provides
this capability and is itself deleted after its final report is recorded.

**Alembic Clean-Break Revisions**:
The clean-break changes to PostgreSQL schema follow an append-only revision sequence:
1. `20260910_01_clean_break_remove_workspace.py`: Drops `workspace_id` and the `workspaces` table, enforcing `owner_user_id NOT NULL` across standalone conversations.
2. `20260910_02_tenant_rls.py`: Establishes tenant row-level security (RLS) policies and deletion epoch support.
3. `20260910_03_memory_evidence_invalidation.py`: Adds memory evidence invalidation tracking.
4. `20260910_04_runtime_role_grants.py`: Enforces least-privilege runtime role grants, defining the authoritative head `EXPECTED_ALEMBIC_HEAD = "20260910_04"`.

Each revision includes both upgrade and downgrade paths and is verified with empty upgrade → downgrade → re-upgrade cycles on an isolated database.

**No dual-write, no SQLite fallback**:
After PostgreSQL migration, the application reads and writes only PostgreSQL.
SQLite is not used as a fallback for any production or development path.

**No compatibility proxy for removed URLs**:
Removed Workspace, Planner, legacy Memory, and Memory Controls URLs return
unmounted `404`. No redirect, proxy, or shim is added.

**Rollback authority**:

| Stage | Rollback action |
| --- | --- |
| Before data cutover | Branch/worktree abandonment; no PostgreSQL or SQLite mutation has occurred |
| After PostgreSQL migration, before traffic | Downgrade Alembic revision only in an isolated environment after confirming no dependent rows were added |
| After traffic starts | Application release rollback against the forward-compatible PostgreSQL schema; does not restore SQLite writes |
| Before deleting SQLite files | Create an owner-approved export or recoverable quarantine artifact if non-synthetic data is found |
| After destructive database failure | Restore PostgreSQL from a tested backup |

Removed Workspace, Planner, legacy Memory, and Memory Manager behavior may be
restored only by a separately approved design, not an emergency hidden flag or
ad hoc revert.

## Alternatives

### Dual-write SQLite and PostgreSQL during migration

Supports gradual cutover and reduces data risk. Introduces cross-store atomicity,
reconciliation, conflict authority, and rollback direction problems. No evidence
of production traffic requires them. Rejected.

### Keep SQLite files as offline archive without deletion

Retains the data risk; files may be loaded accidentally by future tooling or
developers. Does not resolve the split-authority problem. Rejected.

### Delete SQLite files without inventory

Loses any non-synthetic data without recovery. Prohibited by both the spec
and this ADR's data disposal contract. Rejected.

### Clean cutover with pre-deletion inventory and rollback boundaries per stage

Produces the smallest honest runtime at each stage, with clearly defined
rollback authorities and no hidden fallbacks. Selected.

## Consequences

### Positive

1. Each stage has a defined rollback action; rollback authority is never ambiguous.
2. No user-valued SQLite data is deleted without an explicit owner decision.
3. The Alembic history remains auditable and append-only.
4. No legacy URL compatibility shim can accidentally become permanent.

### Negative

1. Local development PostgreSQL is required at every stage after migration; the
   zero-setup SQLite path is permanently retired.
2. Any non-synthetic SQLite data discovered during inventory halts migration
   until the owner makes a disposal/export decision.
3. A Alembic downgrade after traffic has started requires careful row-count
   verification to ensure no dependent data was added.

## Migration

Execute stages in the order listed under Decision. Do not reorder or parallelize
disposal and migration steps. Record the inventory report before any file
deletion. Preserve the inventory report as a governance artifact even after the
SQLite files are removed.

## Validation

1. Inventory report exists in `docs/reports/` and is committed before any SQLite
   file deletion.
2. Alembic upgrade, downgrade, and re-upgrade succeed on an isolated database.
3. No SQLite `.db` file remains in the repository after the approved disposal.
4. No `APP_DB_PATH`, `WORKSPACE_DB_PATH`, or schema registry reference appears
   in mounted backend source, `.env.example`, or Docker Compose configuration.
5. Rollback instructions are documented in the deployment runbook and tested
   against an isolated PostgreSQL schema.

## References

1. [Authenticated Chat-Only PostgreSQL Clean Break](../specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md), v0.1.
2. [ADR 0019](./0019-postgresql-only-application-persistence-sqlite-retirement.md) — storage authority.
3. [ADR 0016](./0016-focused-memory-write-evaluation-and-rollout.md) — SQLite inventory module origin.
4. [Deployment Readiness Runbook](../runbooks/deployment.md).
