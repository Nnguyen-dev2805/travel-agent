# ADR 0002: Trip Workspace as Primary Product Container

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-03 |
| Decision owners | Repository owner |
| Scope | Product identity and data ownership boundary for trip-scoped runtime records |
| Governing spec | [Trip Workspace Foundation Design](../specs/2026-09-03-trip-workspace-foundation-design.md), version 0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

Travel Agent is moving from a stateless RAG chat prototype toward a
workspace-first travel assistant. The current runtime chat contract accepts one
message and returns one answer. It has no stable trip identifier, no user
identity, no conversation persistence, no memory records, no planner state, and
no itinerary version ownership.

The target architecture and data model already identify `TripWorkspace` as the
product container that later milestones can attach to. R3 needs to turn that
concept into the first runtime boundary before adding conversations, memory,
planner operations, or itinerary versions.

This decision is durable because the chosen identity boundary will shape later
schemas, route contracts, retention controls, traceability, and review evidence.
If later records are scoped to a different primary object, migration and
privacy reasoning become harder.

## Decision

Adopt `TripWorkspace` as the primary product container for trip-scoped runtime
data.

R3 establishes a workspace record with a server-generated `workspace_id`, a
caller-supplied local `owner_user_id` scope label, title, destination scope,
optional date window, planning status, retention state, and timestamps. Later
runtime records for a trip should attach to `workspace_id` unless a future
approved design introduces a more specific child identity.

The decision has five rules.

1. **Workspace identity is the trip scope.** Conversations, memory candidates,
   selected memories, itinerary versions, trip decisions, and evaluation traces
   should be designed as workspace-scoped records when those milestones arrive.
2. **Workspace ownership is a product boundary, not authentication.** In R3,
   `owner_user_id` is only a local development scope label supplied by the
   caller. It is not tenant isolation, authorization, or a verified principal.
3. **Chat remains compatible in R3.** R3 adds workspace routes beside the
   existing chat route. It does not add `workspace_id` to the chat request or
   response contract.
4. **Workspace modules must stay independent from RAG execution.** R3 does not
   make retrieval, generation, Chroma collections, embeddings, or evaluation
   artifacts depend on workspace modules.
5. **Workspace records are intentionally minimal.** R3 stores only the fields
   needed to create and inspect a trip container. Memory, planning, deletion,
   collaboration, and production retention behavior require later approved
   designs.

This ADR does not prescribe exact filenames, Python class names, or route
implementation details. The R3 implementation plan may map the boundary onto
the existing FastAPI project with the smallest practical source change that
preserves these rules.

## Alternatives

### Alternative A: Keep Chat Messages as the Primary Product Container

The system could keep each chat request as the only product scope and attach
future memory or itinerary data directly to message identifiers.

This is smaller for the current prototype, but it fails the product model. A
planned trip usually spans many messages, decisions, dates, and artifacts.
Message-scoped records would make it difficult to retrieve trip state, compare
itinerary versions, reason about retention, or present a user-facing trip
workspace. It is rejected.

### Alternative B: Make User Profile the Primary Container

The system could attach memory, conversations, and planner state directly to a
user profile and derive trips later.

This may fit global preferences, but it makes trip-specific facts too broad too
early. Visa notes, budget constraints, companion details, and itinerary choices
often apply to one trip but not every future trip. Because the current system
also has no authenticated user identity, using user profile as the primary
runtime container would overstate both product maturity and security. It is
rejected.

### Alternative C: Introduce Workspace Only When Conversation Persistence Ships

The project could delay workspace identity until the R4 conversation milestone
and keep R3 focused on RAG or route cleanup.

This avoids one early module, but it pushes a core architecture decision into a
larger persistence change. R4, memory, planner, and evaluation trace work would
then need to design storage scope under delivery pressure. It is rejected.

## Consequences

### Positive

1. Later conversation, memory, planner, itinerary, and trace records have a
   stable trip-level parent identity.
2. R3 can move the product toward workspace-first behavior without changing the
   existing chat contract.
3. Privacy and retention discussions can distinguish trip-scoped data from
   global user data.
4. Future UI and API design can expose trips as durable user-facing objects.
5. Evaluation and debugging can eventually associate evidence with the trip
   context that produced it.

### Negative

1. The system gains a new runtime identity before authentication exists.
2. `owner_user_id` can be misunderstood as authorization unless routes,
   documentation, and tests keep the no-auth limitation explicit.
3. Later milestones must consistently attach trip-specific records to
   `workspace_id`, which adds migration discipline.
4. R3 introduces storage and route behavior that must be preserved or migrated
   when the project adopts production identity and database infrastructure.

## Migration

R3 creates the first workspace records, so there is no migration from existing
workspace data. Existing `/health` and `/api/v1/chat` behavior remains
compatible.

Future milestones should migrate forward by adding child records that reference
`workspace_id` rather than changing the workspace identity itself. If a future
design replaces the primary product container, it must introduce a superseding
ADR and a migration plan for workspace-scoped records.

Rollback before owner acceptance removes the R3 workspace module, workspace
routes, tests, and documentation through normal reviewed Git history. It must
not delete local workspace database files unless the repository owner explicitly
names the path and approves deletion.

## Validation

The R3 implementation plan must provide fresh evidence that:

1. workspace create/get/list routes expose and preserve a stable
   `workspace_id`;
2. workspace records include the governed minimal fields from the approved R3
   specification;
3. the existing chat request and response contracts remain compatible;
4. RAG and evaluation modules do not import workspace modules in R3;
5. route documentation and tests state that `owner_user_id` is a local scope
   label, not authentication or authorization;
6. future-facing architecture documentation names `TripWorkspace` as the
   parent scope for later conversation, memory, itinerary, decision, and trace
   records.

## References

1. [Trip Workspace Foundation Design](../specs/2026-09-03-trip-workspace-foundation-design.md), version 0.1 (Approved).
2. [Target Architecture](../architecture/target-state.md).
3. [Target Data Model](../architecture/data-model.md).
4. [Master Roadmap](../roadmap/master-roadmap.md).
5. [Security Policy](../../SECURITY.md).
