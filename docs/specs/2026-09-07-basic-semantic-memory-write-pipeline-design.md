# Basic Semantic Memory Write Pipeline Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-07 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | First deployable semantic-memory write vertical slice for authenticated standalone conversations |
| Related issue | Repository-owner approved exception: interactive architecture design session on 2026-09-07 |
| Superseded document | None; this focused proposal derives from the living Memory Write Pipeline Architecture Design |

## Summary

This specification defines the smallest deployable Write Memory capability that
proves the target architecture without implementing every production feature.
It supports one semantic preference key, explicit confirmed writes, background
shadow extraction from normal chat, deterministic safety and conflict policy,
atomic/idempotent persistence, and focused evaluation.

The implementation proceeds as learning-oriented vertical slices. Pure domain
behavior is completed and reviewed before PostgreSQL, worker, model, API, or UI
integration. A target decision documented in the broader architecture does not
silently enter this scope.

## Governing Architecture

1. [Memory Write Pipeline Architecture Design](./2026-09-07-memory-write-pipeline-architecture-design.md), Draft v0.1.
2. [Conversation Persistence Design](./2026-09-04-conversation-persistence-design.md), Approved v0.1.
3. [Shadow Memory Extraction Design](./2026-09-04-shadow-memory-extraction-design.md), Approved v0.1.
4. [Memory Retrieval Design](./2026-09-04-memory-retrieval-design.md), Approved v0.3.
5. [ADR 0005](../adr/0005-conversation-orchestration-seam-and-optional-chat-binding.md).
6. [ADR 0006](../adr/0006-shadow-memory-candidate-store-and-policy-boundary.md).
7. [ADR 0007](../adr/0007-feature-gated-memory-retrieval-and-context-boundary.md).

This document is not approved merely because the broader architecture contains
confirmed direction. Implementation remains blocked until this exact version
and its exact implementation plan receive repository-owner approval.

## Approved Amendment

[Risk-based Memory Control Amendment](./2026-09-07-risk-based-memory-control-amendment.md)
v0.1 is approved and replaces this version's confirm-all behavior with application-
owned low-risk save feedback, sensitive no-store/no-prompt behavior, bounded
confirmation for bulk delete and scope expansion, and clarified conflict/Shadow
semantics. It has normative precedence over requirements 4, the Explicit
trigger row, the explicit flow, Security and Privacy rule 7, Acceptance
Criterion 4, and every other confirm-all statement in this historical base.
ADR 0017 is Accepted and ADR 0015 is Superseded. Affected runtime tasks remain
on hold only until their amended implementation plan is separately approved.

## Current-state Evidence

| Evidence | Current behavior | Relevance to this change |
| --- | --- | --- |
| `backend/memory/extraction.py` | `MemoryExtractor` produces candidate drafts; `RuleBasedMemoryExtractor` detects controlled signals and secrets | Preserve the extractor seam; do not let extraction own persistence |
| `backend/memory/policy.py` | `MemoryPolicy` applies deterministic candidate disposition | Preserve deterministic safety authority, but replace trace-consent coupling in the new path |
| `backend/memory/promotion.py` | `MemoryPromotionPolicy` decides candidate promotion and broad correction supersession | Replace scope-wide correction with canonical-key conflict resolution |
| `backend/memory/service.py` | Manual extraction and promotion compose multiple repository calls | Introduce immutable decisions and one atomic unit-of-work mutation |
| `backend/memory/repository.py` | Storage interface separates product logic from SQLite | Preserve an interface seam while adding a PostgreSQL target adapter |
| `backend/orchestration/conversation_orchestrator.py` | Unbound chat generates without persistence; bound chat persists messages | A prerequisite slice must create owned standalone conversations on first chat |
| R5/R6 evaluation runners and fixtures | Measure extraction, promotion, retrieval, scope, correction, secret, and deletion behavior | Reuse result discipline but add canonical-key and write-integrity scenarios |

## Goals

1. An authenticated user can start a persistent standalone conversation without
   creating a workspace.
2. The first supported semantic key is
   `travel.preference.hotel_atmosphere`.
3. Its initial normalized values are `quiet`, `lively`, `central`, and
   `secluded`; it is single-valued, ordinary personal, and valid in user or
   conversation scope.
4. A user-initiated remember or correction command requires confirmation and
   commits synchronously before success is acknowledged.
5. A normal user message is persisted with a durable outbox event and may be
   processed asynchronously without blocking chat.
6. Background processing creates shadow candidates only; it cannot
   auto-promote inferred memory in this scope.
7. Extraction, policy, semantic relationship classification, conflict
   resolution, and persistence have separate ownership.
8. Duplicate delivery is idempotent and a semantic change commits evidence,
   decision, assertion/version mutation, trace, and outbox atomically.
9. Secret and prohibited content creates no candidate, memory, embedding, raw
   trace, or model input where pre-model detection is possible.
10. The implementation and tests teach the flow from evidence to assertion,
    version, change set, and durable result.

## Non-goals

1. Conversation Summary Memory.
2. Episodic Memory.
3. Inferred-preference auto-promotion.
4. Durable restricted health, accessibility, identity, location, or payment
   memory.
5. Multiple semantic keys beyond the first registry entry.
6. Memory retrieval optimization, pgvector, graph memory, or a separate vector
   database.
7. Full worker prioritization, perfect retry tuning, multi-region operation, or
   a 1,000-user production-readiness claim.
8. Workspace behavior beyond preserving an optional compatibility association.

## Implementation Decision Table

| Concern | Selected decision | Implementation approach | Why selected | Accepted trade-off | Proof |
| --- | --- | --- | --- | --- | --- |
| First key | One registry key: `travel.preference.hotel_atmosphere` | Versioned code-reviewed registry entry projected into storage | Makes identity, values, scope, cardinality, sensitivity, authority, and tests concrete | Other useful preferences remain unsupported | Registry contract and unknown-key rejection tests |
| Canonical value | Typed normalized value plus display text | Enum-like normalized payload and separate localized presentation | Conflict uses meaning rather than phrasing | Normalizer and renderer need versions | Paraphrase produces `REINFORCE` |
| Assertion identity | Owner + scope + key + subject + condition fingerprint | Deterministic normalized identity with database uniqueness | Prevents text/embedding-based identity drift | Requires normalization discipline | Duplicate and concurrent-create tests |
| Cardinality | Single-valued | Registry metadata and one-current-version database constraint | Hotel atmosphere represents one default per condition/scope | Multiple preferences require structured conditions or future set support | Unique-current-version test |
| Candidate model | Immutable candidate and immutable decisions | Extract once; append `MemoryDecision` outcomes | Preserves extractor proposal and decision history | Latest decision must be resolved | Decision-history tests |
| Explicit trigger | User command, then confirmation, then synchronous commit | `MemoryCommandHandler` creates proposed command and confirmation token; confirmed command uses the same resolver/UoW | Success can be acknowledged only after commit | Adds one confirmation interaction to every user action | API/UI confirmation tests |
| Normal-chat trigger | Persist message and outbox atomically; process new user-message range after debounce | PostgreSQL outbox and typed semantic extraction handler | Does not add model latency to chat and cannot lose work silently | Candidate freshness is delayed | Chat/outbox and worker tests |
| Background authority | Shadow only | Store candidate, evidence, and decision `SHADOW`; create no active version | Permits evaluation before autonomous durable writes | No automatic personalization from new inferred evidence yet | Zero background promotion test |
| Eligibility | Authenticated active user conversation and unprocessed user evidence only | Deterministic prefilter before any model call | Reduces cost and authority laundering | Some useful external/tool context is excluded | Source/owner/lifecycle tests |
| Sensitivity | Layered classification; prohibited secret fails before extraction | Deterministic secret detector, registry floor, contextual escalation, deterministic final band | Model semantics cannot weaken hard safety policy | Contextual classifier adds a later model surface | Secret and escalation hard gates |
| Extractor | Deterministic guards plus structured model adapter | `MemoryExtractionModel` returns strict candidates only; one bounded repair attempt | Understands bilingual paraphrase without persistence authority | Provider latency, cost, and invalid output | Schema and provider-failure tests |
| Relationship | Deterministic comparison first; bounded model classification only when needed | Allowed enum: same, compatible, contradiction, temporal update, scope exception, unrelated, uncertain | Avoids unnecessary model calls while handling semantic language | Relationship classifier needs its own dataset | Confusion-matrix evaluation |
| Conflict mutation | Deterministic typed resolver | Produce `ADD`, `REINFORCE`, `SUPERSEDE`, `ADD_EXCEPTION`, `PENDING_CONFLICT`, `REJECT`, or `NOOP` | Authority, scope, time, and cardinality stay reproducible | Policy code is more explicit than model-owned CRUD | Resolver truth-table tests |
| Uncertainty | Hold as `PENDING_CONFLICT` | No destructive mutation; ask only when later relevant | Contains model or evidence uncertainty | Unresolved state needs aging and metrics | Low-confidence relation test |
| Persistence | PostgreSQL normalized tables | SQLAlchemy Core, Alembic, direct owner columns, app authorization plus RLS | Supports atomic lifecycle and target scale with one authority | Heavier local setup than SQLite | PostgreSQL integration and RLS tests |
| Atomicity | One `MemoryUnitOfWork.apply_memory_change` transaction | Lock assertion under `READ COMMITTED`, re-resolve, write evidence/decision/version/trace/outbox, commit all or none | Eliminates current partial promotion window | Retry and transaction code are required | Injected-failure rollback tests |
| Delivery | At-least-once, idempotent worker | Durable idempotency key and prior-result lookup | Exactly-once cannot span database and model provider | Duplicate work may occur before commit | Redelivery tests |
| Indexing | Derived and asynchronous | Structured/GIN projection after canonical commit; lifecycle revalidation before use | Search cannot become lifecycle authority | Temporary index lag | Index lag/revalidation test |
| Trace | Canonical decision evidence in transaction; external telemetry fail-open | IDs, versions, reason codes, latency/cost counters; no unrestricted content | Every durable mutation has a durable reason | Canonical trace availability affects write availability | Missing-trace rollback test |
| User controls | Dedicated manager plus natural-language commands through one handler | Inspect, remember, correct, delete, enable, and disable share authorization/policy/UoW | Avoids divergent UI/chat mutation semantics | UI and command tests increase | Cross-surface contract tests |
| Migration | Inspect R5/R6 data; discard prototype-only state or quarantine retained state | Never auto-activate legacy rows | Old rows lack new semantic and authority contracts | Migration choice waits for inventory | Inventory and no-auto-activation evidence |

## Core Data Contracts

```text
SemanticKeyDefinition
  key
  registry_version
  value_schema
  cardinality
  allowed_scopes
  minimum_sensitivity
  authority_policy_id
  conflict_policy_id

MemoryEvidence
  evidence_id
  owner_user_id
  conversation_id
  source_event_id
  source_message_id
  canonical_key
  normalized_value
  polarity
  authority
  sensitivity
  event_time
  extractor_version

MemoryCandidate
  candidate_id
  evidence_ids
  proposed_scope
  canonical_key
  normalized_value
  display_text
  authority
  sensitivity

MemoryDecision
  decision_id
  candidate_id
  outcome
  reason_code
  actor_type
  model_or_policy_version
  resulting_assertion_id
  resulting_version_id

MemoryAssertion
  assertion_id
  owner_user_id
  scope_type
  scope_id
  canonical_key
  subject_key
  condition_fingerprint

MemoryVersion
  version_id
  assertion_id
  normalized_value
  display_text
  authority
  sensitivity
  status
  valid_from
  valid_until
  supersedes_version_id

MemoryChangeSet
  operation
  assertion_identity
  evidence_ids
  expected_current_version
  proposed_version
  decision
  idempotency_key
```

Exact Python types and PostgreSQL DDL belong to the implementation plan and may
not change these behavioral meanings without returning to spec review.

## User and System Flows

### Explicit confirmed write

```text
authenticated user memory command
-> extract proposed typed mutation
-> validate key, scope, sensitivity, and source
-> resolve existing assertion and preview operation
-> present exact operation for confirmation
-> confirmed command revalidates current state
-> atomic commit
-> acknowledge success only after commit
```

### Normal-chat background shadow write

```text
persist user message + extraction outbox event atomically
-> finish normal chat without waiting for extraction
-> debounce by conversation
-> claim event range idempotently
-> deterministic secret/eligibility filter
-> structured candidate extraction
-> validate and classify sensitivity
-> compare related assertions and classify relationship
-> record immutable evidence, candidate, and SHADOW decision
-> create no active semantic version
```

### Conflict resolution

| Existing state | New candidate | Result |
| --- | --- | --- |
| No assertion | Valid explicit preference | `ADD` |
| Same normalized value | Explicit or shadow evidence | `REINFORCE` |
| Explicit current value | Weaker contradictory inference | Keep current; `PENDING_CONFLICT` or shadow opposition |
| Explicit current value | Explicit confirmed correction | `SUPERSEDE` |
| User default | Conversation-specific incompatible value | `ADD_EXCEPTION` |
| Equal authority, unclear time/condition | Contradictory value | `PENDING_CONFLICT` |
| Prohibited secret | Any state | `REJECT`; no candidate/model/index |

## Errors and Recovery

| Failure | Behavior |
| --- | --- |
| User refuses or confirmation expires | No mutation; controlled cancelled result |
| Unknown key/value | `INVALID` or `REJECTED`; no canonical write |
| Extractor/model unavailable | Chat succeeds; background job retries; explicit operation reports pending/failure rather than false success |
| Invalid structured output after one repair | Immutable `INVALID` decision; no mutation |
| Relationship uncertainty | `PENDING_CONFLICT`; no destructive mutation |
| Concurrent assertion update | Roll back, reload, resolve again, bounded retry |
| Worker redelivery | Return prior idempotent result or complete the missing safe step |
| Source deleted before commit | Cancel by deletion epoch; no derived write |
| Canonical trace unavailable | Roll back memory mutation |
| External metrics unavailable | Mutation may commit; emit best-effort local failure evidence |

## Security and Privacy

1. Authenticate every route and command; guest memory is out of scope.
2. Enforce owner checks in application code and PostgreSQL RLS.
3. Keep memory-write consent separate from evaluation visibility.
4. Reject secrets, credentials, private keys, raw payment data, CVV, and PIN
   before candidate or embedding creation.
5. The first key is ordinary personal; restricted durable memory is excluded.
6. Treat model output and external content as untrusted.
7. Every user action requires confirmation in this scope.
8. Conversation deletion cancels pending derivation and invalidates dependent
   shadow evidence according to the governing architecture.

## Testing and Evaluation

The focused protocol is [Basic Memory Write Pipeline Evaluation](../evaluation/memory-write-pipeline-evaluation.md). It owns fixtures, metrics,
hard gates, result states, commands, and evidence requirements for this scope.

## Rollout and Migration

1. Complete and review pure domain tests with no database or model dependency.
2. Add PostgreSQL persistence and prove atomicity/idempotency with the model
   adapter stubbed.
3. Add explicit confirmed write behind a server-side feature gate.
4. Add normal-chat outbox capture and background shadow extraction behind a
   separate feature gate.
5. Run the focused evaluation; keep background promotion impossible.
6. Inspect legacy SQLite data and apply the separately approved disposal or
   quarantine decision.
7. Do not enable inferred auto-promotion inside this specification.

## Rollback

1. Disable background capture and explicit semantic writes independently.
2. Preserve current R5/R6 APIs and data as inert legacy behavior until their
   supersession is explicitly approved.
3. Stop workers without deleting outbox evidence; cancelled events remain
   reviewable.
4. Treat PostgreSQL search projections as rebuildable and disposable.
5. Do not roll back a completed privacy deletion by reactivating source or
   derived rows.

## Acceptance Criteria

1. All twelve core evaluation scenarios defined in the focused protocol pass.
2. The first key supports add, reinforce, explicit supersession, scoped
   exception, pending conflict, reject, and no-op behavior.
3. Background chat extraction produces shadow decisions and zero active
   versions.
4. Every user action requires and verifies confirmation before mutation.
5. Duplicate delivery produces one semantic result.
6. Injected failures leave no partial evidence/assertion/version/trace/outbox
   state.
7. Cross-owner, secret promotion, deleted-source write, stale-worker
   resurrection, and background auto-promotion counts are all zero.
8. Chat does not wait for normal background extraction.
9. Every durable mutation records source evidence and versioned decision
   metadata.
10. A code walkthrough can trace one fixture from source message to decision,
    change set, transaction, and report without reading unrelated modules.

## Required ADRs

Before implementation, review and accept:

1. [ADR 0011: Authenticated Standalone Conversations](../adr/0011-authenticated-standalone-conversations.md).
2. [ADR 0012: Versioned Semantic Memory in PostgreSQL](../adr/0012-versioned-semantic-memory-in-postgresql.md).
3. [ADR 0013: Model-assisted Extraction and Deterministic Resolution](../adr/0013-model-assisted-extraction-and-deterministic-resolution.md).
4. [ADR 0014: Transactional Outbox and Idempotent Memory Workers](../adr/0014-transactional-outbox-and-idempotent-memory-workers.md).
5. [ADR 0015: Memory Sensitivity and Confirmed User Control](../adr/0015-memory-sensitivity-and-confirmed-user-control.md).
6. [ADR 0016: Focused Memory Write Evaluation and Rollout](../adr/0016-focused-memory-write-evaluation-and-rollout.md).
7. [ADR 0017: Risk-based Memory Confirmation](../adr/0017-risk-based-memory-confirmation.md), which supersedes ADR 0015.

## Documentation Deliverable Matrix

| Artifact | Purpose | When required | Current action |
| --- | --- | --- | --- |
| `docs/specs/2026-09-07-memory-write-pipeline-architecture-design.md` | Living north-star decisions, trade-offs, dependency map, glossary, and deferred frontier | Throughout design | Exists as Draft; update after every material decision |
| This focused specification | Exact basic Write Pipeline scope and acceptance contract | Before plan approval | Exists as Draft; owner review required |
| `docs/plans/2026-09-07-basic-semantic-memory-write-pipeline-implementation.md` | Master task/dependency and verification map | After focused spec approval; before execution planning | Exists as Draft; execution blocked |
| `docs/evaluation/memory-write-pipeline-evaluation.md` | Exact fixtures, metrics, hard gates, commands, and report evidence | Before implementation approval | Exists as Draft; owner review required |
| Required ADR set | Durable standalone-conversation, storage, model-policy, outbox, sensitivity, and evaluation decisions | After architecture approval and before affected runtime tasks | Do not create before architecture approval |
| `docs/specs/YYYY-MM-DD-memory-manager-design.md` | Detailed inspect/confirm/correct/delete/enable/disable UX and accessibility contract | Before Memory Manager backend/UI child plan | Proposed; not created until focused domain and user-flow decisions are ready |
| `docs/security/memory-threat-model.md` | Trust boundaries, assets, actors, poisoning, cross-owner, deletion resurrection, model/provider, and operator threats | Before model-assisted/background or restricted-memory execution | Proposed; may remain a focused spec section if review finds a separate file unnecessary |
| `docs/architecture/memory-data-dictionary.md` | Human-readable canonical keys, value schemas, cardinality, scopes, sensitivity floor, authority, conflict, and examples | Created with the first approved registry implementation | Proposed; generated facts must remain secondary to code-reviewed registry source |
| Dataset card under the focused fixture directory | Provenance, synthetic-data policy, labels, slices, reviewer, limitations, and version history | Created with evaluation fixtures | Proposed with Task 12 |
| `docs/runbooks/memory-workers.md` | Start/stop, queue inspection, retry, dead-letter, replay, provider outage, and index rebuild | Before background workers are operated outside development | Proposed for the worker child plan |
| `docs/runbooks/memory-deletion.md` | Tombstone, propagation, verification, stuck cleanup, and non-resurrection recovery | Before user deletion reaches real data | Proposed for the control/deletion child plan |
| PostgreSQL migration and recovery runbook update | Upgrade, rollback, backup, restore, pool/RLS checks, and legacy SQLite treatment | Before PostgreSQL cutover | Extend the canonical local/deployment runbooks rather than create duplicate ownership |
| Generated evaluation and verification reports | Evidence from the exact code/dataset/configuration revision | After implementation and fresh runs | Never author favorable placeholder reports |

The master implementation plan should be split before execution into child
plans for: standalone conversation foundation; pure semantic domain;
PostgreSQL/UoW; user controls; background extraction; and evaluation/rollout.
Each child plan must link the same approved focused specification while limiting
its File Responsibility Map and verification commands to one reviewable change
set.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-09-07. This approval
authorizes preparation and review of the required ADRs, focused evaluation
protocol, master sequencing plan, and child implementation plans. It does not
authorize runtime implementation, dependency installation, data migration,
deployment, Git delivery, or execution of any plan before the exact plan and
required ADRs are separately approved.
