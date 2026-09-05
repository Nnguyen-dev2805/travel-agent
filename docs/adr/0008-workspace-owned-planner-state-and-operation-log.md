# ADR 0008: Workspace-owned Planner State and Operation Log

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-05 |
| Decision owners | Repository owner |
| Scope | R7 planner state storage, module ownership, write provenance, and operation log boundary |
| Governing spec | [Trip Planner State Design](../specs/2026-09-05-trip-planner-state-design.md), version 0.2 |
| Superseded ADR | None |
| Superseded by | None |

## Context

Travel Agent now has trip workspaces, persisted conversations, shadow memory
extraction, and feature-gated memory retrieval. The next runtime milestone needs
planner state: itinerary versions, trip decisions, and an operation trail that
proves what changed.

Planner state is user-content-derived data. It must not be confused with memory:
memory records describe durable user preferences or facts, while planner state
describes choices and itinerary snapshots for one trip workspace. The system
also must not pretend a trip plan was saved unless persistence succeeds.

The durable decision is required because R7 affects storage ownership, module
boundaries, write provenance, rollback semantics, and future planner evaluation.

## Decision

R7 will introduce a `backend/planner/` module that owns planner contracts,
service use cases, repository protocol, SQLite adapter, and planner evaluation.

Planner state is scoped to `TripWorkspace` and stored in the shared local
application SQLite database under a new schema module:

```text
('planner_state', 1)
```

The module owns three record families:

1. `ItineraryVersion`: immutable itinerary snapshots with a contiguous
   `version_number` sequence for successful creates per workspace.
2. `TripDecision`: explicit accepted, rejected, changed, superseded, or pending
   planning decisions.
3. `PlannerOperation`: append-only write records that describe what operation
   created or changed itinerary and decision state.

R7 planner writes are explicit. They happen only through planner service methods
or planner API routes, never as an implicit side effect of chat generation,
memory retrieval, RAG retrieval, or evaluation reads.

Dependency direction:

```text
FastAPI planner routes
↓
PlannerService
↓
PlannerRepository protocol
↓
SQLitePlannerRepository
```

`backend/planner` may validate workspace and optional conversation provenance
through the existing workspace and conversation repository interfaces. It must
not import RAG, memory, or orchestration modules. RAG, memory, and orchestration
must not import planner in R7.

## Alternatives

### Store Planner State as Memory Records

This reuses the R6 memory record table and could make retrieval easier later.
It is rejected because trip decisions and itinerary snapshots have different
lifecycle, provenance, and rollback semantics from remembered user preferences.
Conflating them would make deletion, evaluation, and planner correctness harder
to reason about.

### Store Only the Latest Itinerary

This is simpler and minimizes tables. It is rejected because the roadmap requires
planner writes to be explicit and reversible. Keeping only the latest itinerary
would erase rejected options and make regressions difficult to diagnose.

### Add a Generic Event-sourcing Layer

An event-sourced store could replay all planner state from operations. It is
rejected for R7 because it is too much architecture for the local prototype.
R7 stores current queryable records plus an append-only operation log, which is
enough to support review, rollback by version selection, and evaluation.

## Consequences

### Positive

1. Planner state remains separate from memory and travel knowledge retrieval.
2. Every state-changing planner action has a durable operation record.
3. Itinerary versions can be listed, inspected, accepted, archived, and compared
   by version number without mutating older snapshots.
4. Rejected planning options remain first-class decision evidence.
5. R7 can be evaluated without a model provider or frontend.

### Negative

1. R7 adds another local SQLite schema module that must be verified against the
   shared schema registry.
2. Planner state is still local-development storage, not production readiness.
3. R7 does not automatically generate itineraries from chat; an explicit planner
   API caller must write planner state.
4. There is no authentication or user-facing deletion workflow in R7.

## Migration

R7 is additive. It creates the `planner_state` schema module at version `1` and
does not change existing workspace, conversation, memory, RAG, or schema
registry module versions.

Rollback removes planner routes, planner service wiring, planner evaluation
commands, and the `backend/planner/` module. Existing local planner rows may
remain in the SQLite file as inert development data; R7 defines no production
migration.

## Validation

R7 implementation must prove:

1. Schema initialization is idempotent and fail-closed on incompatible
   `planner_state` schema versions.
2. Planner repository methods use temporary database paths in tests.
3. Successful itinerary version numbers are contiguous per workspace.
4. Accepting one itinerary supersedes any previously accepted itinerary for the
   same workspace.
5. Rejected decisions remain stored and listable.
6. Planner operations are written for every state-changing service method.
7. Chat, RAG, memory, and orchestration paths do not import planner and do not
   create planner rows.
8. Planner evaluation reports PASS/FAIL/INCONCLUSIVE/INVALID with traceable
   fixture evidence.

## References

1. [Trip Planner State Design](../specs/2026-09-05-trip-planner-state-design.md)
2. [Master Roadmap](../roadmap/master-roadmap.md)
3. [Data Model](../architecture/data-model.md)
4. [ADR 0004](./0004-shared-local-application-store-and-per-module-schema-registry.md)
5. [ADR 0005](./0005-conversation-orchestration-seam-and-optional-chat-binding.md)
