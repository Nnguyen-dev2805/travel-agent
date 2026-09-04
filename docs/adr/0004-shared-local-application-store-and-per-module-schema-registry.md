# ADR 0004: Shared Local Application Store and Per-module Schema Registry

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-04 |
| Decision owners | Repository owner |
| Scope | Local relational storage ownership, schema version bookkeeping, and cross-module storage boundary for prototype product records |
| Governing spec | [Conversation Persistence Design](../specs/2026-09-04-conversation-persistence-design.md), version 0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

R3 introduced the first relational store in this repository: one SQLite file
holding the `trip_workspaces` table behind a repository interface, with its
schema version recorded in `PRAGMA user_version` and a fail-closed check that
refuses to migrate an unexpected version automatically.

R4 adds a second module that needs relational storage. That exposes a structural
limit rather than a preference: SQLite provides exactly one `user_version` slot
per database file, and `backend/workspaces/sqlite_repository.py:36` already
claims it with `SCHEMA_VERSION = 1`. A second module sharing the file would
either overwrite the workspace version or have to encode two versions into one
integer, and either outcome makes the fail-closed check at
`backend/workspaces/sqlite_repository.py:170` unreliable. That check is the
safety property R3 was careful to establish, so weakening it is not acceptable.

The decision cannot be deferred to R4 alone. `R5` shadow memory extraction, `R6`
memory retrieval, and `R7` trip planner state each need durable records before
`R9` and `R10`. Whatever R4 chooses becomes the pattern those milestones inherit,
and reversing it later means migrating several stores at once.

Two further facts shape the choice. SQLite foreign-key enforcement is not enabled
in the current adapter, which contains no `PRAGMA foreign_keys`, so a shared file
does not automatically buy referential integrity. And the target architecture
still lists "Which storage technology owns users, workspaces, conversations,
messages, itinerary versions, and memory records?" as an open question, so no
prior decision constrains the answer.

## Decision

Use one shared local SQLite database for all relational product records in the
prototype, with schema versions tracked per module in a `schema_versions` table
rather than in `PRAGMA user_version`.

The database lives at `APP_DB_PATH`, defaulting to
`data/app/travel_agent.sqlite3`. `WORKSPACE_DB_PATH` is retained as a deprecated
alias so an existing local environment keeps working: when the alias is set and
`APP_DB_PATH` is not, the alias value is used and one deprecation warning is
logged without its value.

The decision has seven rules.

1. **One local file, many modules.** Every relational product record in the
   prototype lives in the database at `APP_DB_PATH`. Modules do not create
   private database files.
2. **Version bookkeeping is per module.** A `schema_versions` table maps a module
   name to an integer version. The workspace module registers `('workspaces', 1)`
   and the conversation module registers `('conversations', 1)`. Modules never
   read or write each other's version row.
3. **The pragma carries a sentinel, not a version.** R4 writes a sentinel value
   into `PRAGMA user_version` alongside the registry. The sentinel exists so a
   pre-R4 build reads a value different from its expected `1` and takes the
   existing fail-closed path rather than treating the file as uninitialized. The
   concrete sentinel value is an implementation detail owned by the approved
   plan.
4. **Initialization stays bounded and fails closed.** A module may create its own
   tables and register its version on first use. An unsupported registry version,
   or a legacy pragma value with no registry present, raises a controlled storage
   error and never migrates automatically. This preserves the R3 guarantee rather
   than replacing it.
5. **Storage details stay behind interfaces.** Route handlers, services, and
   orchestration code must not embed table DDL, SQL statements, path creation, or
   connection management. `sqlite3` and table DDL appear only in the per-module
   repository adapters and in the shared schema registry module. `APP_DB_PATH`
   appears only in settings and at each module's single dependency construction
   site.
6. **Product state stays out of the vector store.** Workspace, conversation, and
   message records are structured operational data and are never written to
   Chroma or any vector database.
7. **Production claims remain forbidden.** Documentation and completion reports
   must state that this is a local development store and must name production
   database technology, migrations, backup, restore, concurrency, retention, and
   deletion semantics as future work.

This ADR does not choose an ORM, a cloud database, a tenant model, a backup
strategy, a migration framework, or foreign-key enforcement. Those require later
approved designs.

### Relationship to ADR 0003

[ADR 0003](./0003-local-sqlite-workspace-storage-boundary-for-r3.md) remains
`Accepted` and is not superseded. Its core decision, that SQLite is a local
development adapter behind a repository interface and not a production database
commitment, is unchanged and still governs.

This ADR narrows exactly two mechanics of ADR 0003 that were scoped to R3: the
database file is now shared rather than workspace-specific, and schema version
lives in a registry table rather than in `PRAGMA user_version`. ADR 0003 rules 1,
2, 3, 5, and 6 continue to apply verbatim; rule 4, bounded schema
initialization, is preserved in substance and extended to a per-module registry.

Marking ADR 0003 `Superseded` was considered and rejected: most of its content
remains authoritative, and supersession would discard rules that are still the
reason the prototype's storage boundary is honest.

## Alternatives

### Alternative A: Keep `PRAGMA user_version` in one shared file

Both modules could share the file and the existing pragma.

This requires no new table and no change to how a version is read. It fails on
the structural limit described in Context: one slot cannot honestly represent two
independently evolving schemas, and any encoding scheme makes the fail-closed
check ambiguous. A safety check that cannot distinguish "workspace schema is
newer" from "conversation schema is newer" is not a safety check. Rejected.

### Alternative B: One SQLite file per module

Each module could own a private database file with its own pragma, leaving the R3
adapter completely untouched.

This is the cheapest option at the moment of decision, and its zero-touch
property is genuinely valuable because R3 has just merged. It also loses little
within R4 itself: foreign keys are not enforced today, R4 implements no workspace
deletion so orphan rows cannot occur, and a service-level existence check
produces a clearer `404` than an integrity violation would.

It was rejected on trajectory rather than on R4 mechanics. `R5`, `R6`, and `R7`
each need storage, so this pattern produces four or five local databases, each
with an independent version slot to keep consistent and none able to participate
in a single transaction with the others. R4 already needs one cross-table
transaction, because appending a message advances its parent conversation's
`updated_at`, and that is simpler and safer in one file. Choosing per-module
files would also mean revisiting this decision under the delivery pressure of a
later milestone.

### Alternative C: Adopt a production database and migration framework now

R4 could introduce Postgres, an ORM, and a migration tool.

ADR 0003 rejected this for R3 because the project lacked authentication,
deployment readiness, retention policy, backup and restore policy, and
production operations ownership. Every one of those conditions is still unmet at
`2f632e2`. Adopting production storage here would create more architecture
surface than the project can honestly validate, and it would bind a storage
migration to a provenance milestone whose purpose is unrelated. Rejected.

### Alternative D: Enable foreign-key enforcement as part of this decision

The shared file could enable `PRAGMA foreign_keys = ON` per connection and
declare real foreign keys between tables.

This sounds like a natural benefit of sharing one file, and it was the original
reason to prefer sharing. On inspection the benefit is small now: enforcement
would have to be turned on for every connection, which changes the behavior of
the R3 adapter that just merged, and the integrity it protects cannot yet be
violated because no deletion path exists. A service-level existence check also
yields a better API error than an opaque constraint violation. Deferred rather
than rejected: enabling enforcement becomes worthwhile when a deletion milestone
arrives, and it can be adopted then without changing this ADR's boundary.

## Consequences

### Positive

1. A second module can persist records without contending for one version slot.
2. `R5`, `R6`, and `R7` inherit a storage pattern that already accommodates them,
   so no later milestone has to redesign storage before starting its own work.
3. Cross-table transactions remain available inside one local database, which R4
   needs for the message append and conversation timestamp update.
4. The R3 fail-closed guarantee is preserved rather than traded away, and the
   sentinel extends it to protect an R4 database from an older build.
5. Storage technology remains replaceable at a small number of adapter
   boundaries.
6. One database file is simpler for a developer to inspect, back up by hand, or
   delete deliberately than several files with interdependent contents.

### Negative

1. The R3 adapter must change its version bookkeeping, and three existing tests
   that assert version behavior must be rewritten in intent. This touches code
   that has just been merged and verified.
2. `WORKSPACE_DB_PATH` becomes a misleading name, so a rename plus a deprecated
   alias is required, along with documentation updates wherever the old name
   appears.
3. A database created during R3 development is left at the old default path as
   orphaned developer state. It is not adopted and must not be deleted without
   the repository owner naming the exact path.
4. One shared file becomes a single point of local corruption for all product
   records rather than isolating failure per module.
5. A registry table is one more schema object to reason about, and a module that
   forgets to register its version would appear uninitialized.
6. Sharing one file without foreign-key enforcement means referential integrity
   is a service-layer responsibility that a future module could forget.

## Migration

R4 introduces the shared store, so there is no shared-store data to migrate. The
new default path is a new file, which means the common developer case requires no
migration at all.

A database created by R3 at the old default path is not adopted. If an operator
deliberately points `APP_DB_PATH`, or the deprecated alias, at a database whose
`PRAGMA user_version` is neither `0` nor the R4 sentinel and which has no
`schema_versions` table, initialization fails closed with a controlled storage
error. Automatic inference of a legacy schema is explicitly not implemented,
because a silent migration is the failure mode ADR 0003 rule 4 exists to
prevent.

Rollback has two layers beyond ordinary code removal. Schema rollback is
guaranteed by the sentinel: a pre-R4 workspace adapter reading an R4 database
finds a version different from its expected `1` and refuses to migrate through
the existing check, so it cannot write into a file it does not understand. Data
rollback is a deliberate operator action: the local database file is developer
state, R4 creates no backup, replica, or export, and removing a database file is
never a default recovery step.

Future migration to production storage requires a new approved design and plan
covering database technology, migrations, backup, restore, retention,
concurrency, authorization, operational ownership, and data migration from local
prototype state when applicable.

## Validation

The R4 implementation plan must provide fresh evidence that:

1. the `schema_versions` table records module versions independently, and the
   workspace and conversation modules coexist in one database file without
   version contention;
2. R4 writes the sentinel `PRAGMA user_version` value, and a pre-R4 workspace
   version check rejects an R4 database with a controlled storage error;
3. an unsupported registry version, and a legacy pragma value with no registry,
   both fail closed without automatic migration;
4. the existing R3 workspace test suite passes against the registry-based store,
   with the three version-behavior tests rewritten to assert registry semantics
   and the sentinel;
5. `sqlite3` and table DDL appear only in the per-module repository adapters and
   the shared schema registry, and `APP_DB_PATH` appears only in settings and at
   each module's single dependency construction site;
6. `WORKSPACE_DB_PATH` continues to work as a deprecated alias, and using it logs
   one warning without its value;
7. a failed message insert leaves its parent conversation's `updated_at`
   unchanged, demonstrating that the cross-table write is transactional;
8. no workspace, conversation, or message record is written to Chroma;
9. documentation states that the shared SQLite store is a local development
   adapter and names production database, migration, backup, restore,
   concurrency, retention, and deletion semantics as future work.

## References

1. [Conversation Persistence Design](../specs/2026-09-04-conversation-persistence-design.md), version 0.1 (Approved).
2. [ADR 0003: Local SQLite Workspace Storage Boundary for R3](./0003-local-sqlite-workspace-storage-boundary-for-r3.md).
3. [ADR 0005: Conversation Orchestration Seam and Optional Chat Conversation Binding](./0005-conversation-orchestration-seam-and-optional-chat-binding.md).
4. [Trip Workspace Foundation Design](../specs/2026-09-03-trip-workspace-foundation-design.md), version 0.1 (Approved).
5. [Target-state Architecture](../architecture/target-state.md).
6. [Data Model](../architecture/data-model.md).
7. [Security Policy](../../SECURITY.md).
8. [Development Guide](../../DEVELOPMENT.md).
