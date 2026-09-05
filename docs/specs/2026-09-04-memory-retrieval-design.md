# Memory Retrieval Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.3 |
| Date | 2026-09-04 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Runtime milestone R6 - promotion of measured memory candidates into answer-eligible records, feature-gated memory retrieval for bound conversations, orchestration-owned context composition, traceable A/B evaluation, and privacy/scope/lifecycle guards |
| Parent design | [Architecture Baseline Design](./2026-08-31-architecture-baseline-design.md), version 0.1; [Roadmap and Learning Design](./2026-08-31-roadmap-and-learning-design.md), version 0.1 |
| Depends on | R5 delivered on `feature/agent-memory` at `89496eb`; [Shadow Memory Extraction Design](./2026-09-04-shadow-memory-extraction-design.md), version 0.1; [ADR 0006](../adr/0006-shadow-memory-candidate-store-and-policy-boundary.md); [ADR 0007](../adr/0007-feature-gated-memory-retrieval-and-context-boundary.md) (Accepted 2026-09-05); [Memory Evaluation Protocol](../evaluation/memory-evaluation.md); [Security Policy](../../SECURITY.md) |
| Architecture approval | Repository owner approved R6 spec version 0.1 in conversation on 2026-09-05, after a documentation review round that corrected the promotion allow-list against the delivered R5 vocabulary, replaced the `memory` schema version bump with a separate `memory_records` module, named the `RAGService` composition seam, and defined correction supersession. Version 0.2 amends only the correction-supersession age key: it resolves age through source-message provenance instead of pipeline wall-clock, and excludes siblings extracted from the same source message from the target set. The repository owner approved both amendments in conversation on 2026-09-06 after implementation review reproduced a same-message correction burying the preference stated in the same sentence. Version 0.3 amends the promotion accounting under the owner's 2026-09-06 review directive: duplicate detection covers records in any lifecycle status with a new `duplicate_superseded_record` reason, and the multi-target fan-out moves from `skip_reasons` to `multi_target_correction_count` so skip counts always sum to `skipped_count`; the evaluation harness attributes run records by promoted ids instead of timestamps. Repository owner accepted the R6 change set and version 0.3 amendment in conversation on 2026-09-05; Git delivery remains pending |
| Implementation plan | [Memory Retrieval Implementation Plan](../plans/2026-09-04-memory-retrieval-implementation.md), version 0.1 (Approved 2026-09-05) |
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
accepted memory gates. If provider-backed answer judging is unavailable, R6 may
validate retrieval and safety gates, but answer-quality and personalization
claims remain `INCONCLUSIVE`.

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
   Satisfied: R5 merged into `feature/agent-memory` at `89496eb`, and the
   delivered base verifies at `834 passed` with `compileall` exit `0`.
2. R5 produces a valid shadow evaluation report. If that report is `FAIL`,
   `INVALID`, or missing required metrics, R6 implementation stops unless the
   repository owner approves a revised spec. Satisfied: `r5-shadow-v0.1` is
   `PASS`.
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
9. The orchestrator asks `RAGService` for travel evidence and assembled travel
   context through a narrow injectable seam, prepends a controlled memory
   context section when memory is selected, and calls the existing generator
   through the same RAG-owned dependencies. The orchestrator must not construct
   vector-store or Chroma clients directly.
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
| `source_sequence` | R5 candidate `source_sequence` copied forward; part of the correction-supersession age key, which is `(source message created_at, source_sequence)` because `sequence` is monotonic only inside one conversation |
| `owner_user_id` | Local owner label copied from the workspace; not authentication |
| `scope` | `user`, `workspace`, or `conversation` |
| `scope_id` | Owner label for `user`, workspace id for `workspace`, conversation id for `conversation` |
| `memory_type` | `preference`, `constraint`, `profile_fact`, `episode`, `decision`, or `correction`. Promotion reaches only `preference`, `constraint`, and `correction`; the other three are reachable in R6 solely through seeded evaluation fixtures |
| `status` | `active`, `superseded`, `expired`, `archived`, `deletion_requested`, or `deleted` |
| `text` | Normalized memory text, at most 500 characters, never logged |
| `confidence` | Floating-point value in `[0.0, 1.0]` |
| `sensitivity_label` | `none` or `personal` for promoted R6 records; `personal` is forward-compatible only, because no `accepted` R5 candidate carries it |
| `supersedes_memory_id` | Optional older memory id suppressed by this record; derived only by the promotion-time rule in `Correction Supersession` |
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
| `skip_reasons` | Counts keyed by controlled reason; only non-promoted outcomes appear, so the counts always sum to `skipped_count` |
| `multi_target_correction_count` | Number of promoted corrections that suppressed more than one target; informational only, never a skip reason |
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

When `MEMORY_RETRIEVAL_ENABLED=false`, chat responses are schema-compatible with
R4/R5: `reply`, `model`, `citations`, and optional existing conversation
metadata. `backend/app/schemas/chat.py` must extend the existing
`_omit_absent_conversation` serializer pattern so an absent memory object is
omitted entirely, not serialized as `"memory": null`.

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
| `backend/memory/sqlite_repository.py` | `memory_records` schema module version 1 records, promotion runs, and retrieval events | Shared schema registry, memory repository |
| `backend/memory/promotion.py` | Candidate-to-record eligibility and skip reasons | Memory models/repository |
| `backend/memory/retrieval.py` | Scope/lifecycle filtering and deterministic ranking | Memory models/repository |
| `backend/memory/service.py` | Promotion and retrieval use cases | Memory repository plus R5-compatible candidate access |
| `backend/orchestration/memory_context.py` | Compose memory selections with RAG prompt context for a turn | Memory selection contracts and RAG `ContextBundle` |
| `backend/orchestration/conversation_orchestrator.py` | Calls memory retrieval only when enabled, then calls RAG/generator path | Conversation service, RAG service, optional memory service |
| `backend/rag/generation/rag_service.py` | Add an injectable travel-context seam so orchestration can compose memory without constructing retriever, assembler, generator, or vector-store clients | RAG retriever, context assembler, generator |
| `backend/rag/*` | Travel retrieval, travel context, citations, and RAG evaluation | Must not import `backend.memory` |
| `backend/memory/evaluation/*` | R6 memory retrieval evaluation runner and report writer | Memory service/repository, deterministic fakes |

## Promotion Rules

R6 promotes a candidate only when all conditions are true:

1. candidate status is `accepted`;
2. proposed scope is `user`, `workspace`, or `conversation`;
3. proposed type is not `none` and not `safety_note`;
4. confidence is at least `MEMORY_PROMOTION_MIN_CONFIDENCE`, default `0.75`;
5. sensitivity label is `none` or `personal`;
6. candidate provenance resolves to the same workspace and conversation;
7. policy reason is one of `supported_preference`,
   `supported_constraint`, `supported_profile_fact`,
   `supported_trip_decision`, or `explicit_correction`;
8. no record already exists for the same normalized text, scope, and
   source candidate, in any lifecycle status. The record table constrains
   `source_candidate_id` across all statuses, so a rerun after a
   supersession reports `duplicate_superseded_record` instead of attempting
   a reinsert. Supersession targets are still active records only.

Candidates with `secret`, `sensitive`, `unsafe`, `needs_user_action`,
`rejected`, `invalid`, `none` scope, or unresolved provenance are skipped with
controlled reasons.

### Promotion Reason Codes

R6 promotion uses a governed vocabulary, following the R5 pattern. A skip reason
is never free text and never contains candidate content.

| Code | Meaning |
| --- | --- |
| `promoted` | Candidate became an active memory record |
| `not_accepted` | Candidate status was `rejected`, `needs_user_action`, or `invalid` |
| `scope_not_promotable` | Proposed scope was `none` |
| `type_not_promotable` | Proposed type was `none` or `safety_note` |
| `below_min_confidence` | Confidence was under `MEMORY_PROMOTION_MIN_CONFIDENCE` |
| `sensitivity_not_promotable` | Sensitivity label was `sensitive`, `secret`, or `unsafe` |
| `provenance_unresolved` | Workspace, conversation, or message provenance did not resolve |
| `reason_not_promotable` | Policy reason was outside the promotion allow-list |
| `duplicate_active_record` | An active record already exists for the same normalized text, scope, and source candidate |
| `duplicate_superseded_record` | A non-active record already exists for the same normalized text, scope, and source candidate; the rerun skips instead of violating the table uniqueness constraint |
| `correction_supersedes_multiple` | Legacy, no longer emitted: a correction suppressed more than one active target. Stored rows may still carry it and must keep parsing; new runs report the fan-out on `multi_target_correction_count` instead, because a promoted candidate must never appear under a skip vocabulary |

### Producer Reachability of the Promotion Allow-list

The allow-list above is the governed vocabulary. The delivered R5 pipeline does
not currently produce all of it. Verified against `backend/memory/extraction.py`
and `backend/memory/policy.py` on 2026-09-04:

| Allowed reason | R5 producer | Evidence |
| --- | --- | --- |
| `supported_preference` | Yes; `preference` at `user` scope, confidence `0.80` | Preference markers in `extraction.py`, accepted by `policy.py` |
| `supported_constraint` | Yes; `constraint` at `workspace` scope, confidence `0.85` | Constraint markers in `extraction.py`, accepted by `policy.py` |
| `explicit_correction` | Yes; `correction` at `user` scope, confidence `0.85` | Correction markers in `extraction.py`, accepted by `policy.py` |
| `supported_profile_fact` | No producer | Every `profile_fact` draft carries `sensitivity_label = personal`, and `policy.py` maps `personal` to `needs_user_action` before the accept branch, so this reason is never attached to an `accepted` candidate |
| `supported_trip_decision` | No producer | The R5 extractor never proposes `memory_type = decision` |

Two consequences are explicit R6 scope decisions:

1. R6 keeps both no-producer reasons in the allow-list as forward-compatible
   entries. R6 must not add extraction rules to create them, because extraction
   behavior is R5-owned and changing it requires an approved change to the R5
   contract.
2. Because no `accepted` candidate carries `sensitivity_label = personal`, the
   `personal` branch of promotion rule 5 and the `personal` value of
   `MemoryRecord.sensitivity_label` are forward-compatible only. R6 must not
   claim promotion coverage for `personal` records.

Retrieval-side slices for `profile_fact` and `decision` memory are covered by
seeding `MemoryRecord` rows directly in R6 fixtures, which is the same
mechanism the lifecycle slices already use. Promotion coverage for those two
reasons is not claimed by R6.

### Correction Supersession

R5 candidates carry no link to the memory they correct. `supersedes_memory_id`
is therefore derived at promotion time from provenance, scope, and record age
only. Text similarity, embeddings, and model inference must not be used.

A candidate whose policy reason is `explicit_correction` selects its target set
as the existing memory records that satisfy all of:

1. `status` is `active`;
2. same `owner_user_id`;
3. same `scope` and `scope_id`;
4. `memory_type` is not `correction`;
5. the record's `source_message_id` differs from the correction candidate's;
6. the record is strictly older than the correction under the age key below.

Scope isolation comes from condition 3 alone. For `conversation` scope
`scope_id` is the conversation id, for `workspace` scope it is the workspace id,
and for `user` scope it is the owner label, so no target can cross a
conversation, workspace, or owner boundary that its own scope does not already
contain.

Targeting deliberately does not require the same `conversation_id`. A
user-global preference recorded in one trip must be correctable from another
trip, which is the reason `user` scope exists.

Because `Message.sequence` is monotonic per conversation and not comparable
across conversations, the age key is the tuple `(created_at, source_sequence)`
ascending, where each `created_at` is the source message's creation time
resolved through stored provenance — not pipeline wall-clock. Extraction and
promotion timestamps cannot order two candidates born in the same run, so
wall-clock comparison would leave same-run corrections with zero targets. A
record is older when its tuple is strictly less than the correction
candidate's. A record from a different source message that ties on both values
is also treated as older, matching the suppression bias stated below rather
than leaving an unresolved competitor active.

Condition 5 exists because message-time keys make ties routine rather than
rare. R5 evaluates every draft builder against each message, so one sentence
such as "actually I prefer mountains, please fix that" yields both a
correction and the preference it states, sharing the age key exactly. Those
two are one intent, not an older inference and its correction, so suppressing
the sibling would bury the memory the user just expressed. Same-message
siblings are therefore never targets, and the tie rule applies only across
different source messages.

Resolution is deterministic:

| Target count | Behavior |
| --- | --- |
| `0` | `supersedes_memory_id` is absent and the correction is promoted as a standalone active record |
| `1` | The correction records that `memory_id`, and the target's `status` becomes `superseded` |
| More than `1` | Every target's `status` becomes `superseded`, `supersedes_memory_id` records the oldest target by the age key, and the promotion result reports the count on `multi_target_correction_count` |

Suppressing every ambiguous target errs toward forgetting. That direction costs
retrieval recall and can suppress an unrelated record in the same scope, but it
can never leave an older inference outranking a newer explicit correction, which
is a hard gate. Precise correction targeting requires an explicit link field
produced during extraction, which is an R5 contract change outside R6 scope.

Supersession is resolved once, at promotion time, and stored as record status.
Retrieval does not re-derive it.

## Retrieval Rules

R6 retrieves memories only when all conditions are true:

1. server-side feature gate is enabled;
2. request is bound to an existing conversation;
3. conversation resolves to a workspace and owner label;
4. memory status is `active`;
5. `expires_at` is absent or in the future;
6. sensitivity label is `none` or `personal`;
7. scope matches the current owner, workspace, or conversation;
8. the record was not marked `superseded` by a later correction at promotion
   time; retrieval reads the stored status and does not re-derive supersession;
9. lexical score is above zero or the record is a direct active correction;
10. selected count does not exceed `MEMORY_MAX_SELECTED`, default `5`.

## Errors and Edge Cases

1. Missing R5 delivery evidence stops implementation before code changes.
2. Missing R5 evaluation report makes R6 implementation ineligible.
3. Existing `memory_records` schema newer than expected fails closed.
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
3. `memory_records` SQLite schema version 1 and temporary database isolation;
4. scope filtering for user, workspace, and conversation memories;
5. lifecycle filtering for inactive records;
6. correction precedence, including the zero-target, single-target, and
   multiple-target supersession cases;
7. feature-gate-off chat compatibility;
8. feature-gate-on bound chat memory selection;
9. RAG import-boundary checks;
10. R6 evaluation report result states;
11. omitted `memory` response key when the feature gate is off;
12. promotion skips the two allow-list reasons that have no R5 producer, proving
    the allow-list is forward-compatible rather than silently unreachable.

### Evaluation Gate Applicability

| Protocol gate | R6 applicability | R6 expectation |
| --- | --- | --- |
| Memory extraction precision | Indirect | Consumed from the R5 shadow report; R6 stops if R5 is `FAIL` or `INVALID` |
| Memory extraction recall | Indirect | Consumed from the R5 shadow report; not recomputed by R6 unless fixtures are reused for regression |
| Scope assignment accuracy | Applicable | Promotion and retrieval must preserve user, workspace, and conversation scope labels |
| Promotion precision | Applicable | Promoted records must come only from eligible accepted R5 candidates; target `>= 0.97`. Measured over the three reasons that have an R5 producer; `supported_profile_fact` and `supported_trip_decision` contribute no denominator |
| Memory Hit@5 | Applicable | Retrieval over seeded eligible records must meet the protocol threshold |
| Irrelevant-memory rate | Applicable | Selected memories must stay below the protocol maximum |
| Personalization win rate | Conditional | `INCONCLUSIVE` unless provider-backed or otherwise approved answer judging is configured |
| Constraint satisfaction delta | Conditional | `INCONCLUSIVE` without answer judging; no negative delta is allowed when judging is available |
| Cross-user leakage | Limited applicability | Measures isolation by the local `owner_user_id` label copied from the workspace, not authenticated identity |
| Cross-workspace leakage | Applicable | Zero tolerated failures |
| Deleted or tombstoned retrieval | Applicable through seeded lifecycle states | Zero tolerated retrieval of `deleted`, `deletion_requested`, `expired`, `archived`, or `superseded` records |
| Controlled secret-like promotion | Applicable | Zero tolerated promoted records from `secret`, `sensitive`, or `unsafe` candidates |
| Older inferred memory overriding explicit correction | Applicable | Zero tolerated failures. Enforced at promotion time by the `Correction Supersession` rule, which suppresses every ambiguous target rather than guessing one |

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

| Gate | State |
| --- | --- |
| R5 delivered on the selected integration base | Satisfied at `89496eb` on `feature/agent-memory` |
| R5 report reviewed and not `FAIL` or `INVALID` | Satisfied; `r5-shadow-v0.1` is `PASS` |
| ADR 0007 accepted | Satisfied 2026-09-05 |
| This spec approved | Satisfied 2026-09-05, version 0.1 |
| R6 implementation plan approved | Satisfied 2026-09-05, plan version 0.1 |

The storage change is additive. R6 registers a new `memory_records` schema
module at version 1 for answer-eligible records, promotion runs, and retrieval
events. The R5 `memory` schema module remains at version 1. Any unexpected
`memory_records` schema state fails closed.

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
5. RAG and RAG evaluation import-boundary checks prove no dependency on memory,
   and memory import-boundary checks prove `backend/memory` does not depend on
   `backend.rag` or `backend.orchestration`.
6. Memory retrieval never selects out-of-scope, deleted, expired, superseded,
   sensitive, secret-like, unsafe, or unresolved-provenance records.
7. R6 evaluation writes JSON and Markdown reports following the memory
   evaluation protocol.
8. Fresh backend tests and static checks pass.
9. Documentation states that memory retrieval remains feature-gated and not
   default-on.

## Approval Record

| Version | Approver role | Date | Authorization boundary |
| --- | --- | --- | --- |
| 0.1 | Repository owner | 2026-09-05 | Approved together with acceptance of ADR 0007 and approval of the matching implementation plan version 0.1. Approval followed a documentation review round that corrected the promotion allow-list against the delivered R5 `PolicyReason` vocabulary, recorded which allow-list reasons have no R5 producer, replaced the `memory` schema version bump with a separate `memory_records` module so ADR 0004 fail-closed behavior stays intact, named the `RAGService` composition seam, defined correction supersession, and added the reverse import-boundary check. This approval authorizes delegating backend-only R6 implementation to a worker following the approved plan. It does not authorize default-on memory retrieval, frontend work, authentication, deletion semantics, production deployment, Git delivery, or destructive cleanup |

Two limitations were accepted knowingly at approval time:

1. Personalization win rate and constraint satisfaction delta will report
   `INCONCLUSIVE` because no provider-backed answer judge is configured, so R6
   cannot by itself satisfy a personalization improvement claim.
2. The roadmap still lists `R9` as depending on `R6`, while two of the five hard
   memory gates depend on `R9` deliverables, namely authenticated identity and
   deletion semantics. Resolving that ordering is a separate roadmap change and
   is not part of R6.
