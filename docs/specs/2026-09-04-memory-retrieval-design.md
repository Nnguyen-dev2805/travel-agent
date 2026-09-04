# Memory Retrieval Design

| Field | Value |
| --- | --- |
| Status | In Review |
| Version | 0.1 |
| Date | 2026-09-04 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Runtime milestone R6 - promotion of measured memory candidates into answer-eligible records, feature-gated memory retrieval for bound conversations, orchestration-owned context composition, traceable A/B evaluation, and privacy/scope/lifecycle guards |
| Parent design | [Architecture Baseline Design](./2026-08-31-architecture-baseline-design.md), version 0.1; [Roadmap and Learning Design](./2026-08-31-roadmap-and-learning-design.md), version 0.1 |
| Depends on | R5 delivered and accepted; [Shadow Memory Extraction Design](./2026-09-04-shadow-memory-extraction-design.md), version 0.1; [ADR 0006](../adr/0006-shadow-memory-candidate-store-and-policy-boundary.md); [ADR 0007](../adr/0007-feature-gated-memory-retrieval-and-context-boundary.md) proposed; [Memory Evaluation Protocol](../evaluation/memory-evaluation.md); [Security Policy](../../SECURITY.md) |
| Architecture approval | Pending repository-owner review and ADR 0007 acceptance |
| Implementation plan | [Memory Retrieval Implementation Plan](../plans/2026-09-04-memory-retrieval-implementation.md), version 0.1 (In Review) |
| Related issue | None - R6 specification drafting was authorized by the repository owner in conversation on 2026-09-04 |
| Superseded document | None |

## Summary

R6 adds feature-gated answer-time memory retrieval. It promotes eligible R5
shadow candidates into durable `MemoryRecord` rows, selects in-scope active
records for a bound chat turn, composes those records with travel RAG context in
the orchestration layer, and evaluates memory-enabled behavior against a
memory-disabled baseline.

R6 does not make memory default-on. The feature gate remains off unless a local
developer or evaluation runner explicitly enables it. Default-on personalization
requires a later owner decision after the R6 evaluation report satisfies the
accepted memory gates.

R6 is backend-only. It adds no frontend UI, no authentication, no vector memory
store, no Chroma writes, no deletion API, no memory edit UI, no planner state,
and no public deployment claim.

## Current-state Evidence

Verified from the R4/R5 governance and current codebase context on
`feature/agent-memory` on 2026-09-04.

| Claim | Evidence |
| --- | --- |
| R4 answer orchestration is separate from routes | `backend/orchestration/conversation_orchestrator.py` coordinates optional conversation persistence and RAG generation |
| RAG context assembly is travel-evidence focused | `backend/rag/generation/context.py` builds `ContextBundle` from `RetrievalResult` and `CitationEvidence` |
| RAG generation consumes prompt text, not memory records | `backend/rag/generation/llm.py` receives a `ContextBundle` and formats the prompt from `prompt_context` |
| RAG evaluation constructs RAG stages directly | `backend/rag/evaluation/runtime.py` builds retriever, assembler, and generator without product memory |
| R5 governance is shadow-only | ADR 0006 and the R5 spec forbid memory candidates from entering `ContextBundle`, prompts, generated answers, or RAG evaluation |
| The roadmap blocks R6 on R5 | `docs/roadmap/master-roadmap.md` lists R6 as blocked by R5 and requires memory candidates to be measured before they influence answers |
| Memory gates already exist | `docs/evaluation/memory-evaluation.md` defines retrieval utility, personalization, deletion, scope, and hard safety gates |
| User content remains security-sensitive | `SECURITY.md` requires scope, retention, deletion, and verification evidence for durable user-data stores |

## Context

R5 creates memory candidates but does not answer the product question: "Can the
assistant safely use remembered facts to improve a reply?" R6 answers that
question under a feature gate.

The central risk is scope. A memory about one trip must not influence another
trip. A conversation-specific correction must not become a user-global profile.
A deleted or superseded record must not be selected. A secret-like candidate
must not become durable answer context. These failures are not quality tradeoffs;
they are hard gates.

R6 therefore separates three operations:

1. promotion from measured candidates into answer-eligible records;
2. retrieval and ranking of active in-scope records for a bound turn;
3. orchestration-time composition of selected memory with travel RAG context.

## Users

1. The repository owner, who needs evidence before memory can affect answers.
2. An implementation worker agent, which needs exact R6 boundaries and stop
   conditions.
3. A local developer, who can run memory-disabled and memory-enabled evaluation
   pairs.
4. A future privacy/security milestone, which will add deletion and access
   semantics on top of the R6 lifecycle surface.
5. A future planner milestone, which must not confuse planner state with memory.

## Problem Statement

The assistant currently answers only from the user message plus travel RAG
evidence. That prevents personalization and makes repeated trip preferences
invisible. At the same time, using memory too early would risk privacy and
grounding regressions.

R6 must make memory retrieval measurable and reversible. It should allow a
developer to answer:

1. Which records were eligible?
2. Which records were selected?
3. Why were they selected or rejected?
4. Did the answer improve compared with the memory-disabled baseline?
5. Did any hard safety, scope, deletion, or correction gate fail?

## Goals

1. Add `MemoryRecord` contracts for answer-eligible durable memory.
2. Promote only eligible R5 accepted candidates into active memory records.
3. Keep candidate storage and answer-eligible records separate.
4. Add deterministic memory retrieval with scope, lifecycle, sensitivity,
   confidence, and correction gates.
5. Add server-side feature gating with `MEMORY_RETRIEVAL_ENABLED=false` by
   default.
6. Preserve exact R4/R5 chat behavior when the feature gate is disabled.
7. Compose selected memory with RAG prompt context in orchestration, while
   keeping `backend/rag` free of `backend.memory` imports.
8. Expose selected memory IDs, reasons, and gate state through controlled
   response metadata or evaluation traces without turning memory into citations.
9. Produce an R6 memory retrieval evaluation report with memory-disabled versus
   memory-enabled comparison.
10. Update canonical documentation after implementation so current state and
    roadmap evidence remain truthful.

## Non-goals

1. No frontend UI, browser memory view, or memory management screen.
2. No authentication, account model, tenant isolation, or public deployment
   security claim.
3. No default-on memory retrieval.
4. No vector memory database, embeddings, Chroma memory collection, or semantic
   memory retrieval.
5. No deletion API, tombstone API, redaction API, correction UI, or memory edit
   UI. R6 must respect lifecycle states if present, but does not expose user
   deletion controls.
6. No planner state, itinerary versioning, trip operation log, or planner
   decision store.
7. No change to R1/R2 travel benchmark data or travel retrieval ranking.
8. No raw message, memory text, or evidence summary logging.
9. No public request field that lets a caller override memory behavior.
10. No staging, commit, push, PR, merge, release, branch deletion, or history
    rewrite by an implementation worker.

## Assumptions

1. R5 is implemented, verified, accepted by the repository owner, and delivered
   to the selected R6 integration base before R6 source implementation starts.
2. R5 produces a valid shadow evaluation report. If that report is `FAIL`,
   `INVALID`, or missing required metrics, R6 implementation stops unless the
   repository owner approves a revised spec.
3. The R5 candidate schema remains compatible with this spec's promotion rules.
4. The local SQLite application store remains the R6 storage target.
5. Deterministic lexical retrieval is acceptable for R6 because the milestone
   emphasizes safety, traceability, and feature-gated evaluation before semantic
   optimization.
6. R6 can be delivered with memory retrieval disabled by default if provider
   prerequisites prevent full answer-quality claims.

## User and System Flows

1. R5 has produced accepted shadow candidates for a workspace conversation.
2. A local developer runs R6 promotion for a workspace or conversation.
3. The memory service validates each candidate against status, confidence,
   scope, sensitivity, provenance, and policy reason.
4. Eligible candidates become active `MemoryRecord` rows. Ineligible candidates
   produce controlled skip reasons.
5. A bound chat request arrives with `conversation_id`.
6. The orchestrator checks server-side memory retrieval settings.
7. If disabled, the turn follows the R4 path exactly.
8. If enabled, the orchestrator resolves workspace and owner scope from the
   conversation, asks the memory retrieval service for eligible records, and
   records selected memory IDs and reasons.
9. The orchestrator retrieves travel evidence through RAG, assembles travel
   context, prepends a controlled memory context section when memory is
   selected, and calls the existing generator.
10. The response preserves travel citations and may include controlled memory
    trace metadata only when the gate is enabled.
11. The evaluation runner executes paired memory-disabled and memory-enabled
    cases and writes JSON plus Markdown reports.

## Behavioral and Data Contracts

### MemoryRecord

`MemoryRecord` is the first answer-eligible memory entity. It is created only by
promotion policy, not directly by the extractor.

| Field | Contract |
| --- | --- |
| `memory_id` | Server-generated `mem_` identifier |
| `source_candidate_id` | Existing R5 candidate identifier |
| `workspace_id` | Existing workspace identifier for provenance |
| `conversation_id` | Existing conversation identifier for provenance |
| `source_message_id` | Existing message identifier for provenance |
| `owner_user_id` | Local owner label copied from the workspace; not authentication |
| `scope` | `user`, `workspace`, or `conversation` |
| `scope_id` | Owner label for `user`, workspace id for `workspace`, conversation id for `conversation` |
| `memory_type` | `preference`, `constraint`, `profile_fact`, `episode`, `decision`, or `correction` |
| `status` | `active`, `superseded`, `expired`, `archived`, `deletion_requested`, or `deleted` |
| `text` | Normalized memory text, at most 500 characters, never logged |
| `confidence` | Floating-point value in `[0.0, 1.0]` |
| `sensitivity_label` | `none` or `personal` for promoted R6 records |
| `supersedes_memory_id` | Optional older memory id suppressed by this record |
| `created_at` | UTC timestamp |
| `updated_at` | UTC timestamp |
| `expires_at` | Optional UTC timestamp after which the record is ineligible |

### MemoryPromotionResult

Promotion returns counts and skip reasons, not raw source text.

| Field | Contract |
| --- | --- |
| `promotion_run_id` | Server-generated `mpr_` identifier |
| `workspace_id` | Workspace being promoted |
| `conversation_id` | Optional conversation filter |
| `source_candidate_count` | Number of candidates examined |
| `promoted_count` | Number of created active memory records |
| `skipped_count` | Number of candidates skipped |
| `skip_reasons` | Counts keyed by controlled reason |
| `started_at` | UTC timestamp |
| `finished_at` | UTC timestamp |

### MemorySelection

`MemorySelection` is the per-turn retrieval output.

| Field | Contract |
| --- | --- |
| `memory_id` | Selected memory id |
| `scope` | Selected scope |
| `memory_type` | Selected type |
| `reason` | Controlled selection reason |
| `score` | Deterministic ranking score |
| `text` | Text used for prompt composition; not logged outside controlled traces |

### Chat Response Compatibility

When `MEMORY_RETRIEVAL_ENABLED=false`, chat responses are byte-for-byte
compatible at the schema level with R4/R5: `reply`, `model`, `citations`, and
optional existing conversation metadata.

When enabled, R6 may add an optional `memory` object:

| Field | Contract |
| --- | --- |
| `enabled` | `true` |
| `status` | `selected`, `none_selected`, or `skipped` |
| `selected_memory_ids` | Ordered memory ids selected for the turn |
| `selection_reasons` | Controlled reasons aligned to selected ids |

The `memory` object must not include raw source message content.

## Components and Dependency Direction

| Component | Responsibility | Allowed dependencies |
| --- | --- | --- |
| `backend/memory/models.py` | Memory record, promotion, retrieval, and trace contracts | Standard library only |
| `backend/memory/repository.py` | Repository protocols and controlled errors | Memory models |
| `backend/memory/sqlite_repository.py` | Memory schema version 2 records, promotion runs, and retrieval events | Shared schema registry, memory repository |
| `backend/memory/promotion.py` | Candidate-to-record eligibility and skip reasons | Memory models/repository |
| `backend/memory/retrieval.py` | Scope/lifecycle filtering and deterministic ranking | Memory models/repository |
| `backend/memory/service.py` | Promotion and retrieval use cases | Memory repository plus R5-compatible candidate access |
| `backend/orchestration/memory_context.py` | Compose memory selections with RAG prompt context for a turn | Memory selection contracts and RAG `ContextBundle` |
| `backend/orchestration/conversation_orchestrator.py` | Calls memory retrieval only when enabled, then calls RAG/generator path | Conversation service, RAG service, optional memory service |
| `backend/rag/*` | Travel retrieval, travel context, citations, and RAG evaluation | Must not import `backend.memory` |
| `backend/memory/evaluation/*` | R6 memory retrieval evaluation runner and report writer | Memory service/repository, deterministic fakes |

## Promotion Rules

R6 promotes a candidate only when all conditions are true:

1. candidate status is `accepted`;
2. proposed scope is `user`, `workspace`, or `conversation`;
3. proposed type is not `none` and not `safety_note`;
4. confidence is at least `MEMORY_PROMOTION_MIN_CONFIDENCE`, default `0.80`;
5. sensitivity label is `none` or `personal`;
6. candidate provenance resolves to the same workspace and conversation;
7. policy reason is one of `supported_preference`,
   `supported_constraint`, `supported_profile_fact`, `supported_episode`,
   `supported_decision`, or `explicit_correction`;
8. no active duplicate record already exists for the same normalized text,
   scope, and source candidate.

Candidates with `secret`, `sensitive`, `unsafe`, `needs_user_action`,
`rejected`, `invalid`, `none` scope, or unresolved provenance are skipped with
controlled reasons.

## Retrieval Rules

R6 retrieves memories only when all conditions are true:

1. server-side feature gate is enabled;
2. request is bound to an existing conversation;
3. conversation resolves to a workspace and owner label;
4. memory status is `active`;
5. `expires_at` is absent or in the future;
6. sensitivity label is `none` or `personal`;
7. scope matches the current owner, workspace, or conversation;
8. record is not superseded by a newer selected correction;
9. lexical score is above zero or the record is a direct active correction;
10. selected count does not exceed `MEMORY_MAX_SELECTED`, default `5`.

## Errors and Edge Cases

1. Missing R5 delivery evidence stops implementation before code changes.
2. Missing R5 evaluation report makes R6 implementation ineligible.
3. Existing memory schema newer than expected fails closed.
4. Feature gate disabled returns R4/R5 behavior.
5. Unbound chat skips memory retrieval.
6. Conversation not found uses the existing conversation error path and does not
   retrieve memory.
7. No eligible records produces `none_selected` in enabled traces.
8. Deleted, deletion-requested, expired, archived, or superseded records are not
   selected.
9. Secret-like or unsafe records must not exist through promotion; if found in
   storage, retrieval rejects them.
10. Older inferred memory must not override newer explicit correction.

## Security and Privacy

R6 remains local development behavior. It does not add authentication,
authorization, tenant isolation, or production readiness.

Memory records are durable user-content-derived data. R6 therefore requires:

1. default-off feature gate;
2. no raw memory or message content in logs;
3. temporary databases in tests;
4. controlled reason codes in errors and traces;
5. zero retrieval of deleted, tombstoned, or secret-like records in evaluation;
6. no memory writes to Chroma or travel-knowledge collections;
7. no public request toggle for memory retrieval.

## Observability and Operations

R6 adds controlled local traces for:

1. promotion counts and skip reasons;
2. retrieval eligibility counts;
3. selected memory IDs;
4. selection reasons;
5. feature gate state;
6. evaluation pair IDs.

Logs must use counts and identifiers only. Raw message text, memory text,
candidate text, evidence summaries, and prompt fragments are not logged.

## Testing and Evaluation

R6 must add unit and integration tests for:

1. memory record model validation;
2. promotion eligibility and skip reasons;
3. SQLite schema version 2 and temporary database isolation;
4. scope filtering for user, workspace, and conversation memories;
5. lifecycle filtering for inactive records;
6. correction precedence;
7. feature-gate-off chat compatibility;
8. feature-gate-on bound chat memory selection;
9. RAG import-boundary checks;
10. R6 evaluation report result states.

The R6 evaluation report must include:

1. memory-disabled and memory-enabled run identities;
2. selected memory IDs and reasons per example;
3. memory Hit@5;
4. irrelevant-memory rate;
5. personalization win rate when answer evaluation is available;
6. constraint satisfaction delta;
7. hard-gate counts;
8. result state: `PASS`, `FAIL`, `INCONCLUSIVE`, or `INVALID`.

If no provider-backed answer judge is configured, R6 may still validate
promotion, retrieval, scope, lifecycle, and trace gates, but answer-quality
claims must be marked `INCONCLUSIVE`.

## Rollout and Migration

R6 implementation starts only after:

1. R5 is delivered on the selected integration base;
2. R5 report is reviewed and not `FAIL` or `INVALID`;
3. ADR 0007 is accepted;
4. this spec is approved;
5. the R6 implementation plan is approved.

The storage change is additive. The memory module may move from schema version 1
to schema version 2 through one reviewed R6 upgrade step. Any unexpected schema
state fails closed.

The runtime feature gate remains off by default after delivery.

## Rollback

Rollback disables `MEMORY_RETRIEVAL_ENABLED`, removes orchestration memory
composition, removes R6 memory routes or commands, and leaves memory records as
inert local data. Travel RAG collections and R5 candidate evidence remain
unchanged.

## Acceptance Criteria

1. R6 implementation does not begin before R5 delivery and owner approval gates.
2. `MemoryRecord`, promotion, retrieval, and trace contracts match this spec.
3. Feature-gate-off chat behavior preserves R4/R5 responses.
4. Feature-gate-on bound chat can select in-scope active memories and expose
   selected IDs/reasons through controlled metadata or traces.
5. RAG and RAG evaluation import-boundary checks prove no dependency on memory.
6. Memory retrieval never selects out-of-scope, deleted, expired, superseded,
   sensitive, secret-like, unsafe, or unresolved-provenance records.
7. R6 evaluation writes JSON and Markdown reports following the memory
   evaluation protocol.
8. Fresh backend tests and static checks pass.
9. Documentation states that memory retrieval remains feature-gated and not
   default-on.

## Approval Record

Version 0.1 is in review. It is not approved for implementation until the
repository owner explicitly accepts ADR 0007, approves this spec version, and
approves the matching implementation plan.
