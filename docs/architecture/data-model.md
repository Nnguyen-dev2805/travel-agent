# Data Model

## Purpose

This document owns the conceptual target model for Agent Memory: entities,
relationships, ownership, lifecycle dimensions, and read/write semantics. It is
not the physical PostgreSQL schema, an ORM contract, or evidence that every
entity is implemented.

Use [Current-state Architecture](current-state.md) for the implemented schema and
runtime. Use [Target-state Architecture](target-state.md) for component and data
flows.

## Current Implementation vs Target Model

The current code implements only a subset of this document.

Current write-side Memory has:

- `semantic-registry-v1`;
- one key: `travel.preference.hotel_atmosphere`;
- single-value cardinality only;
- user and conversation scopes;
- `ACTIVE` and `SUPERSEDED` version states;
- write operations `ADD`, `REINFORCE`, `SUPERSEDE`, `ADD_EXCEPTION`,
  `PENDING_CONFLICT`, `REJECT`, and `NOOP`.

Retention modes, revoke/suppression generations, multi-key/set-valued semantics,
SourceHandlingRecord, Memory Read/Use, Episodic/Working behavior, and Procedural
publication below are target concepts unless source code shows otherwise.

## Ownership Model

The product boundary is authenticated standalone Chat. There is no target
`workspace_id` parent for Conversation or tenant Memory.

| Concept | Meaning |
| --- | --- |
| Authenticated principal | Request-time identity that supplies `owner_user_id`; authorization does not trust an owner id from user payload data |
| Conversation | Standalone dialogue directly owned by one authenticated user |
| Message | Ordered persisted user/assistant record within a conversation |
| Conversation outbox event | Transactional source event released only after its producing turn is terminal |
| Tenant Memory | User-derived Semantic, Episodic, or Working Memory isolated by owner and scope |
| Procedural publication | System-owned versioned behavior outside tenant Memory ownership/RLS |

## Target Entity Overview

| Entity | Purpose | State |
| --- | --- | --- |
| Conversation | Owner-scoped dialogue and deletion boundary | Canonical PostgreSQL |
| Message | Ordered turn content/status/provenance | Canonical PostgreSQL |
| ConversationOutboxEvent | Async source handoff with release/lease/retry state | Canonical PostgreSQL |
| DialogueState | Current-turn referents/topic/goal | Ephemeral |
| TurnSemantics | Typed non-authoritative interpretation of the current turn | Ephemeral |
| ContextPlan | Whether the response needs Memory, RAG, both, or neither | Ephemeral |
| MemoryAssertion | Stable identity for one remembered semantic proposition | Canonical PostgreSQL |
| MemoryVersion | Immutable normalized state/lifecycle version under an assertion | Canonical PostgreSQL |
| MemoryEvidence | Provenance supporting or contradicting a Memory decision | Canonical PostgreSQL |
| MemoryCandidate | Proposed normalized item before governed resolution | Canonical PostgreSQL |
| MemoryDecision | Auditable decision/effect or abstention | Canonical PostgreSQL |
| SourceHandlingRecord | Family-specific positive authority for processing one source/outbox event | Canonical PostgreSQL |
| MemoryWriteIdempotency | Stable result for retry-safe semantic writes | Canonical PostgreSQL |
| MemoryReadSelection | Eligible/relevant selected Memory for one response | Ephemeral |
| PublishedProcedure | Versioned system-owned procedural state | Separate canonical publication state |

## Core Relationships

```mermaid
erDiagram
    CONVERSATION ||--o{ MESSAGE : contains
    CONVERSATION ||--o{ CONVERSATION_OUTBOX_EVENT : emits
    MESSAGE ||--o{ MEMORY_EVIDENCE : sources
    CONVERSATION_OUTBOX_EVENT ||--o{ SOURCE_HANDLING_RECORD : authorizes_per_family
    MEMORY_ASSERTION ||--o{ MEMORY_VERSION : versions
    MEMORY_ASSERTION ||--o{ MEMORY_EVIDENCE : supported_by
    MEMORY_CANDIDATE }o--o{ MEMORY_EVIDENCE : grounded_in
    MEMORY_DECISION }o--|| MEMORY_CANDIDATE : decides
    MEMORY_VERSION }o--o{ MEMORY_EVIDENCE : justified_by
    PUBLISHED_PROCEDURE ||--o| PUBLISHED_PROCEDURE : supersedes
```

The diagram is conceptual. Migrations and repository contracts own physical
foreign keys and table layouts.

## Semantic Assertion Identity

A semantic assertion groups versions of one proposition under a stable identity.
The value itself is versioned state and is not part of that identity.

Conceptually:

```text
owner
+ scope
+ semantic key
+ subject
+ condition
```

This lets a correction create a new version of the same proposition rather than
a disconnected assertion.

The target assertion also carries the suppression-generation boundary required
for deterministic forget/no-resurrection behavior.

## Memory Version

A target `MemoryVersion` is immutable historical state. Representative fields
include:

- assertion and version identity;
- normalized value;
- authority;
- scope;
- retention mode;
- sensitivity;
- lifecycle status;
- suppression generation;
- optional `expires_at`;
- creation/supersession/revocation provenance;
- schema/policy version metadata needed for audit or replay.

Correction creates a new version and supersedes the old one; it does not rewrite
history in place.

## Semantic Registry Evolution

### Current Registry

The implemented `semantic-registry-v1` contains one single-valued key:

| Key | Cardinality |
| --- | --- |
| `travel.preference.hotel_atmosphere` | single |

Implemented normalized values are `quiet`, `lively`, `central`, and `secluded`.

### Target Registry

The target semantic slice extends the governed registry to these travel-facing
keys:

| Key | Cardinality |
| --- | --- |
| `travel.preference.hotel_atmosphere` | single |
| `travel.preference.accommodation_type` | set |
| `travel.preference.transport_mode` | set |
| `travel.preference.travel_pace` | single |
| `travel.preference.activity_style` | set |
| `travel.constraint.budget_level` | single |
| `travel.preference.food_style` | set |
| `travel.profile.default_departure_city` | single |

The target in-process representation is:

```text
single-valued key -> governed string member
set-valued key    -> non-empty sorted/deduplicated tuple of governed members
```

Set state is one immutable assertion-version snapshot, not a delimiter-joined
string and not one assertion per member. Compatible additions produce a new
full set snapshot only when the normalized set changes.

## Evidence, Candidate, and Decision

### MemoryEvidence

Evidence is immutable provenance. It identifies the source conversation,
message/outbox event, observation time, and the generation relevant to lifecycle
decisions.

Repeated processing of the same source does not become independent evidence.
When a source is deleted or invalidated, source-dependent eligibility must be
recomputed without exposing deleted raw text through read, prompt, inspect,
trace, summary, projection, or citation.

### MemoryCandidate

A candidate is a proposed normalized Memory item, not durable truth. Before it
can produce a state change it must pass the applicable registry, scope,
sensitivity, source-validity, generation, and lifecycle rules.

### MemoryDecision

A decision records the governed relation/effect or abstention. The target
relation vocabulary includes:

```text
new | duplicate | reinforcement | correction | contradiction |
temporary_exception | stale | unrelated | uncertain
```

Target effects include:

```text
ADD | REINFORCE | SUPERSEDE | ADD_EXCEPTION |
PENDING_CONFLICT | REJECT | NOOP | REVOKE
```

A bounded model may help classify an unresolved semantic relation. Deterministic
application policy owns the resulting effect.

## SourceHandlingRecord

Background processing requires positive, family-specific source authority.
Conceptually the record is keyed by:

```text
(source_outbox_id, memory_family)
```

Target outcomes include:

```text
BACKGROUND_ELIGIBLE
EXPLICIT_APPLIED
EXPLICIT_REFUSED
EXPLICIT_NOOP
FORGET_APPLIED
FORGET_REFUSED
```

Absence of a record means `UNHANDLED`, never implicit background permission.

## Independent Memory Dimensions

These dimensions must remain separate because they answer different questions.

### Authority

```text
EXPLICIT_SAVE
EXPLICIT_STATEMENT
REPEATED_INFERENCE
```

Authority answers how strongly the system may trust the observation, not how
long it should live.

### Scope

```text
conversation
user
```

Scope answers where the Memory may apply. Procedural state is not a tenant
scope.

### Retention

```text
CONVERSATION_BOUND
SOURCE_BOUND
USER_DURABLE
```

Retention is persisted when target Memory is written. Expiry and source validity
remain separate eligibility inputs.

### Lifecycle

Target lifecycle includes at least:

```text
SHADOW / PENDING
ACTIVE
SUPERSEDED
REVOKED
REJECTED
EXPIRED
```

`ACTIVE` is necessary but not sufficient for answer-time use.

### Sensitivity

A deterministic registry/policy sets a minimum sensitivity classification. A
model may raise that classification but never lower the floor. Higher-risk
classes remain non-storable until an explicit policy permits them.

## Forget, Suppression, and Re-remember

Target product forget is a lifecycle operation, not physical history rewriting:

```text
generation 1 active
-> explicit forget
-> generation 1 revoked
-> suppression_generation advances to 2
-> delayed generation 1 work cannot form, activate, or read
-> later explicit re-remember may create current generation 2 state
```

Privacy erasure/source deletion is a separate concern. It may invalidate or
remove source content while preserving only the minimum lifecycle facts needed
to prevent resurrection.

## Conflict and Response Precedence

Equal-authority unresolved contradiction becomes non-answer-eligible pending
conflict rather than last-write-wins.

Target response precedence is:

```text
system/developer policy
> current user request
> verified hard constraints
> current conversation working state / temporary override
> user-scoped soft preference/profile
> episodic context
```

A conversation-specific or current-turn override may suppress a softer user
preference for one response without mutating the durable user-scoped value.

## Read/Use Projection

Target selection filters canonical state before prompt composition:

```text
owner + scope
-> lifecycle / retention / source-validity / suppression eligibility
-> relevance
-> conflict and response-precedence exclusion
-> bounded ranking/selection
```

The result is a structured `MemoryReadSelection`, not a raw database dump and
not a citation. Optional full-text/vector projections may accelerate discovery
later, but every candidate selected from such a projection must be revalidated
against canonical state.

## Memory Families

| Family | Ownership | Typical scope | Core purpose |
| --- | --- | --- | --- |
| Semantic | Tenant/user-derived | user or conversation | Stable facts, preferences, constraints |
| Episodic | Tenant/user-derived | conversation; governed user generalization | Grounded past experiences/events |
| Working | Tenant/user-derived | conversation | Short-lived continuity/current working state |
| Procedural | System-owned | separate non-tenant boundary | Versioned system behavior |

Each tenant family must have explicit formation, retention, read/use, deletion,
failure, and evaluation behavior. Sharing infrastructure must not turn them into
one ungoverned payload type.

## Procedural Publication

Procedural Memory is system-owned publication state. Ordinary Chat users and
tenant Memory workers cannot publish it.

A target procedure version becomes selectable only after deterministic
validation, evaluation, and explicit publication. Rollback changes the active
published version; it does not rewrite tenant Memory.
