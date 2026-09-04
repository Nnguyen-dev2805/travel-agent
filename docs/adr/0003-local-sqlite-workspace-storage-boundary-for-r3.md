# ADR 0003: Local SQLite Workspace Storage Boundary for R3

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-03 |
| Decision owners | Repository owner |
| Scope | R3 local workspace persistence technology, module boundary, and production limitation |
| Governing spec | [Trip Workspace Foundation Design](../specs/2026-09-03-trip-workspace-foundation-design.md), version 0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None. [ADR 0004](./0004-shared-local-application-store-and-per-module-schema-registry.md) narrows two R3-scoped mechanics of this record without superseding it: the database file is now shared across modules rather than workspace-specific, and schema version is tracked in a `schema_versions` registry table rather than in `PRAGMA user_version`. Rules 1, 2, 3, 5, and 6 below continue to apply verbatim, and rule 4 is preserved in substance and extended to a per-module registry |

## Context

R3 needs enough persistence to create, retrieve, and list trip workspace
records behind approved backend interfaces. The repository currently has no
workspace store, no production database, no migrations framework, no
authenticated user identity, and no workspace-aware chat or planner runtime.

The project is still a local prototype with public production blocked by the
security policy. R3 therefore needs a storage choice that is inspectable,
deterministic in tests, easy to run locally, and small enough not to imply that
production storage, tenancy, backup, restore, retention, or migration policy has
been solved.

This decision is durable because route handlers, future services, tests, and
documentation need a clear dependency direction: product code should depend on a
workspace repository interface, not directly on SQLite details.

## Decision

Use a local SQLite-backed workspace repository for R3, hidden behind a small
workspace repository interface.

R3 will store workspace records in a SQLite database at `WORKSPACE_DB_PATH`,
defaulting to `data/workspaces/travel_agent_workspaces.sqlite3`. The repository
adapter owns schema initialization for version 1, persistence operations, and
SQLite-specific error handling. API routes and workspace service logic depend
on the repository interface and workspace contracts rather than constructing
SQL directly.

The decision has six rules.

1. **SQLite is a local R3 adapter.** It is accepted for local development and
   tests only. It is not a production database commitment.
2. **Storage details sit behind an interface.** Route handlers and service
   logic must not embed table DDL, SQL statements, path creation, or SQLite
   connection management.
3. **Workspace persistence is separate from RAG persistence.** R3 does not
   store workspace records in Chroma and does not make workspace routes depend
   on embedding, retrieval, generation, or evaluation modules.
4. **Schema initialization is bounded.** R3 may create the version 1 workspace
   table if missing, but it does not introduce a general migration framework.
5. **Tests use isolated stores.** Unit and integration tests must use temporary
   database paths and must not depend on developer-local database state.
6. **Production claims are forbidden.** Documentation and completion reports
   must state the local storage boundary and name production database,
   migration, backup, restore, concurrency, retention, and deletion semantics as
   future work.

This ADR does not choose an ORM, cloud database, tenant model, backup strategy,
or final migration framework. Those require later approved designs.

## Alternatives

### Alternative A: Store Workspaces in JSON Files

The project could write workspace records to local JSON files.

This is easy to inspect, but it makes uniqueness, filtering, timestamp ordering,
partial writes, and future schema evolution more fragile. It also encourages
ad hoc file parsing in route or service code. SQLite gives the local prototype
structured queries and transactional behavior while remaining lightweight. This
alternative is rejected.

### Alternative B: Store Workspaces in Chroma

The project could store workspace records in the existing vector database
alongside travel knowledge.

This reuses an existing dependency, but it mixes product state with retrieval
indexes. Workspace records are structured operational data, not semantic
retrieval chunks. Putting them in Chroma would blur ownership, retention,
backup, filtering, and future authorization boundaries. It is rejected.

### Alternative C: Adopt a Production Database and Migration Framework Now

The project could introduce Postgres or another production database plus an ORM
and migrations during R3.

That may be the right future direction, but it expands R3 beyond the approved
milestone. The current system lacks authentication, deployment readiness,
retention policy, backup and restore policy, and production operations
commitments. Choosing production storage now would create more architecture
surface than the project can honestly validate in R3. It is rejected.

### Alternative D: Keep Only an In-memory Repository

The project could provide an in-memory implementation and defer durable local
storage.

This would simplify testing but miss the R3 exit gate that workspace records
can be created and inspected behind approved interfaces across normal backend
repository operations. It would also provide weaker evidence for route and
storage boundaries. It is rejected.

## Consequences

### Positive

1. R3 can persist workspace records locally without requiring external services.
2. Tests can use temporary SQLite files with deterministic setup and teardown.
3. The repository interface keeps route handlers independent of storage
   technology.
4. Structured queries support deterministic owner-scope listing and
   newest-first ordering.
5. Future storage replacement can target one adapter boundary rather than every
   route handler.

### Negative

1. SQLite does not settle production database, multi-user concurrency,
   tenancy, backup, restore, or migration policy.
2. The implementation must maintain clear documentation so local storage is not
   mistaken for public-production readiness.
3. Schema version 1 creates a compatibility obligation even for a prototype.
4. A later production database migration will need explicit mapping from the R3
   workspace schema and identifiers.
5. Local database files become developer state that must be handled carefully
   during cleanup and rollback.

## Migration

R3 introduces the first workspace store, so there is no existing workspace data
to migrate. The SQLite adapter should initialize schema version 1 safely when
the configured database is first used.

Future migration to production storage requires a new approved design and plan
covering database technology, migrations, backups, restore, retention,
authorization, operational ownership, and data migration from local prototype
state when applicable.

Rollback before owner acceptance removes the adapter, workspace module, routes,
tests, and documentation through normal reviewed Git history. Local SQLite
files created during testing or development are local state and must not be
deleted without an explicit owner decision naming the exact path.

## Validation

The R3 implementation plan must provide fresh evidence that:

1. workspace route handlers depend on workspace service/repository interfaces
   rather than embedding SQLite statements directly;
2. SQLite schema version 1 initializes at `WORKSPACE_DB_PATH` and supports
   create/get/list behavior;
3. invalid create and list inputs fail before storage writes;
4. tests use temporary database paths and do not require external services;
5. `/health` and `/api/v1/chat` remain compatible;
6. RAG and evaluation modules do not import workspace modules in R3;
7. documentation states that SQLite is a local R3 adapter, not production
   storage readiness.

## References

1. [Trip Workspace Foundation Design](../specs/2026-09-03-trip-workspace-foundation-design.md), version 0.1 (Approved).
2. [Target Architecture](../architecture/target-state.md).
3. [Target Data Model](../architecture/data-model.md).
4. [Development Guide](../../DEVELOPMENT.md).
5. [Security Policy](../../SECURITY.md).
