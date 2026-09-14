# Agent Memory Target Architecture Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence. Use the repository development workflow, TDD for
> behavior changes, and a fresh review checkpoint after every task.

**Goal:** Deliver the approved chat-first Agent Memory architecture as staged,
evaluated vertical slices: typed turn understanding, explicit semantic Memory,
governed read/use, background inference, episodic/working Memory, optional
retrieval projections, and system-owned procedural publication.

**Architecture:** PostgreSQL remains canonical state. Deterministic application
policy owns authorization, lifecycle, persistence, and read eligibility; model
calls are bounded semantic interpreters only. Explicit Chat mutation and
background inference use separate transaction coordinators over shared lifecycle
and store primitives, while Memory Read/Use stays outside RAG and supplies only
structured context to generation.

**Tech Stack:** Python 3.11 baseline, FastAPI, SQLAlchemy Core, Alembic,
PostgreSQL 16, pytest, existing RAG/generation seams. pgvector/full-text are not
introduced unless Stage 6 evidence proves structured retrieval insufficient.

**Spec:** [Agent Memory Target Architecture](../specs/2026-09-12-agent-memory-target-architecture-design.md) v0.7 (Approved 2026-09-14)

| Field | Value |
| --- | --- |
| Status | Approved |
| Plan version | 0.14 — Task-9 authoritative unresolved-conflict state and read-projection clarification |
| Date | 2026-09-12 |
| Last amended | 2026-09-14 |
| Specification | [Agent Memory Target Architecture](../specs/2026-09-12-agent-memory-target-architecture-design.md) v0.7, Approved 2026-09-14 |
| Required ADRs | ADR 0036, 0037, 0038, 0039, 0040 — Accepted 2026-09-12 |
| Execution owner | Coding agent under repository-owner instruction |
| Decision owner | Repository owner |
| Approval | Repository owner approved plan v0.14 on 2026-09-14 as a Task-9 persistence/read-contract clarification; spec v0.7 and ADR-level architecture remain unchanged. |
| Scope | Stages 1–7 of the target architecture, with independent rollout gates and evidence-based stop conditions |
| Verification | Task-local CORE tests gate architectural progression. Deferred hardening remains mandatory before final production-readiness proof, including required PostgreSQL integration tests without required skips, exhaustive ADR validation where specified, evaluation gates, full backend suite, frontend regression suite, `compileall`, `git diff --check`, and exact change-set review. |

## Global Constraints

1. Authenticated, PostgreSQL-only standalone Chat is the baseline. Do not
   reintroduce Workspace, SQLite, the removed Memory Manager, or public Memory
   management endpoints.
2. PostgreSQL is canonical relational Memory state. Full-text/vector indexes are
   optional rebuildable projections and never lifecycle authority.
3. Model output alone never authorizes durable mutation, activation, sensitivity
   downgrade, SQL, or storage operation selection.
4. Explicit remember/correct/forget requires deterministic speech-act
   corroboration. Model-assisted parsing is limited to one bounded structured
   call, validates against the closed registry, and fails closed.
5. `MemoryLifecyclePolicy` is the single owner of lifecycle rules across write,
   formation, activation, and read. No path reimplements or weakens them.
6. Explicit and background commits share tenant/conversation fencing and lock
   order `conversation -> outbox (worker only) -> memory`; only the worker needs
   the outbox lease fence.
7. A successful explicit mutation atomically commits Memory effect, semantic
   idempotency result, `SourceHandlingRecord`, deterministic acknowledgement,
   and the guarded terminal turn transition.
8. A `SourceHandlingProposal` is non-authoritative. Missing persisted
   `SourceHandlingRecord` means `UNHANDLED`, never background permission; only a
   persisted `BACKGROUND_ELIGIBLE` record grants background formation.
9. Product forget is `REVOKE`/`REVOKED` plus suppression generation. It is not
   privacy erasure; stale generations cannot form, activate, or read.
10. `retention_mode`, optional `expires_at`, and typed `SourceValidity` are
    independent eligibility dimensions. Retention is persisted at write time;
    source validity is derived outside the pure lifecycle policy from canonical
    source/evidence state.
11. `ACTIVE` alone never means answer-eligible. Read still applies lifecycle,
    relevance, precedence, conflict exclusion, ranking, and bounded selection.
12. Memory context is structured data, never a citation or instruction channel.
    Raw source evidence does not enter generation context by default, and
    deleted/invalid-source evidence is filtered at the governed evidence read
    boundary even when a `USER_DURABLE` normalized value remains eligible.
13. `TurnDisposition` is internal to `TurnOutcome` in this rollout; do not add it
    to the public Chat response schema.
14. Inferred Memory remains shadow-only until a conclusive evaluation gate for
    that family/type is separately satisfied.
15. Shared/real-user runtime roles must be non-superuser and non-`BYPASSRLS`.
    Required PostgreSQL verification does not pass when skipped/uncollectable.
16. Operational logs/traces are content-safe by construction: IDs, typed or
    shape-validated reason/failure codes, timings, closed enums, and bounded
    counts are allowed; raw messages, Memory values, evidence, exception text,
    and secrets are not. Redaction remains defense in depth rather than the
    primary privacy boundary.
17. The current Task-9 execution head is `20260914_01`. If it differs when execution
    starts, stop and revise migration identifiers/dependencies before editing.
18. Rollback never clears revoke/suppression state, reactivates superseded or
    revoked versions, restores SQLite, or treats a projection as truth.
19. Git staging, commit in the primary tree, push, PR, merge, release, and
    destructive cleanup remain repository-owner decisions.
20. Each task uses RED -> minimal GREEN -> refactor only after GREEN, then an
    explicit review checkpoint.
21. `backend/memory/` remains the single Memory bounded-domain root. The clean-
    break sentinel must permanently reject the frozen legacy Memory command,
    service, repository, retrieval, promotion, extraction, evaluation, and
    public-route surfaces without treating every future `backend.memory.*`
    module as legacy.
22. Final-answer generation consumes a neutral generation contract. RAG keeps
    ownership of retrieval-domain `RetrievalResult`/`CitationEvidence`; Memory
    keeps ownership of governed Memory selection. Neither domain imports the
    other, and source-specific records are projected into generation input by
    orchestration rather than moved into the neutral contract.
23. Memory mutation flags remain default-off during staged implementation.
    Tasks 8–10 may enable explicit semantic writes only in controlled tests and
    evaluation; broad Memory-write enablement is forbidden until Task 11 proves
    the approved bounded `memory_outbox` lifecycle. This is the execution rule
    for specification acceptance criterion 20.
24. Stage 2 expands the first semantic slice into a closed, code-reviewed
    `semantic-registry-v2` with exactly eight P0 Travel Agent keys: hotel
    atmosphere, accommodation type, transport mode, travel pace, activity
    style, budget level, food style, and default departure city. Unknown keys,
    unknown enum members, unsupported city values, or raw free-form substitutes
    fail closed. Set-valued keys use deterministic sorted/deduplicated structured
    values under one current assertion version; delimiter-concatenated strings
    and one-ad-hoc-assertion-per-member are forbidden.
25. Set-valued semantic state is an immutable snapshot under the same assertion
    identity, not a mutable bag of rows. Positive compatible evidence may only
    grow the snapshot by deterministic union; a duplicate/subset reinforces the
    current version; an explicit correction/targeted member forget must first
    materialize the desired full snapshot and then use the governed temporal
    update path. A non-empty replacement supersedes the prior version; removing
    the last member revokes the assertion through the existing suppression-
    generation contract. `CONTRADICTION` alone never authorizes a set mutation.
26. Task 7 uses two execution tiers without changing ADR 0036: **CORE** is the
    minimum architecture gate required before progressing to Task 8; items marked
    **DEFERRED HARDENING** remain required before final production-readiness/Task
    16 proof. Deferral changes when evidence is collected, not the accepted
    transaction, fencing, idempotency, rollback, or lock-order contracts.

## Required ADRs

| ADR | Decision used by this plan |
| --- | --- |
| [ADR 0036](../adr/0036-chat-native-memory-actions-and-transaction-coordinators.md) | Chat-native explicit authority, dual commit owners, transaction-aware seams, fences, idempotency, lock order |
| [ADR 0037](../adr/0037-memory-retention-revocation-and-suppression.md) | Retention, temporal validity, `REVOKE/REVOKED`, suppression generation, re-remember, single lifecycle-policy owner |
| [ADR 0038](../adr/0038-positive-source-handling-and-inferred-activation-authority.md) | Positive family-specific source handling, evidence independence, shadow-first inferred activation |
| [ADR 0039](../adr/0039-memory-read-use-authority-and-retrieval-projections.md) | Read/Use authority, ContextPlanner/Arbiter, explicit inspect, RAG separation, projection boundary |
| [ADR 0040](../adr/0040-system-owned-procedural-memory-publication-boundary.md) | Procedural Memory as offline system-owned publication outside tenant scope/RLS |

## File Responsibility Map

| File | Responsibility | Tasks |
| --- | --- | --- |
| `backend/tests/boundaries/test_clean_break_boundaries.py` | Derived scan, frozen legacy-Memory denylist, closed route sentinel, mutation proof | 1 |
| `backend/observability/models.py` | Structured-event field shapes and bounded operational codes | 2 |
| `backend/observability/redaction.py` | Secret-key normalization and defense-in-depth value redaction | 2 |
| `backend/observability/events.py` | Single structured emission boundary; no raw-content escape hatch | 2 |
| `backend/app/api/chat.py` | Reclassify legacy domain literals away from `failure_class` | 2 |
| `backend/app/api/conversations.py` | Reclassify legacy domain literals away from `failure_class` | 2 |
| `backend/orchestration/turn_models.py` | Closed turn-understanding, disposition, routing, explicit-intent, and context-plan contracts | 3, 4 |
| `backend/orchestration/dialogue_state.py` | Ephemeral structural recent-turn dialogue state; no topic/referent/goal/intent/clarification inference | 3, 13 |
| `backend/orchestration/turn_understanding.py` | Deterministic-first understanding plus bounded structured parse | 4 |
| `backend/orchestration/action_router.py` | Deterministic branch selection and explicit-intent gate | 4 |
| `backend/orchestration/context_planner.py` | `none/rag_only/memory_only/both` source plan | 4, 10 |
| `backend/orchestration/context_arbiter.py` | Precedence/token-budget admission and source-to-generation projection | 10 |
| `backend/orchestration/conversation_orchestrator.py` | Bounded one-turn workflow, internal `TurnDisposition`, and Task-5 typed source-handling proposal production | 4, 5, 8, 10 |
| `backend/generation/contracts.py` | Source-neutral generation context/citation/result/sufficiency contracts | 10 |
| `backend/memory/source_handling.py` | Stdlib-only Memory-family/source-handling vocabulary, non-authoritative proposals, record contract, and fail-closed positive-background predicate | 5 |
| `backend/memory/lifecycle.py` | Single lifecycle-policy owner | 6 |
| `backend/memory/explicit_actions.py` | Chat-native remember/correct/forget/inspect proposals | 8, 10 |
| `backend/memory/commit_coordinators.py` | Explicit/background transaction ownership | 7 |
| `backend/memory/read_models.py` | Read, selection, abstention, inspect contracts | 9 |
| `backend/memory/read_engine.py` | Governed relevance/precedence/ranking/abstention | 9 |
| `backend/memory/postgres_store.py` | Tenant-scoped physical read adapter; no lifecycle/relevance policy | 9 |
| `backend/memory/context.py` | Prompt-safe structured Memory context | 10 |
| `backend/memory/formation.py` | Background formation into immutable evidence/candidates | 11 |
| `backend/memory/activation.py` | Family/type activation policy | 11–13 |
| `backend/memory/episodic.py` | Episodic vertical slice | 12 |
| `backend/memory/working.py` | Working Memory vertical slice | 13 |
| `backend/memory/projections.py` | Optional rebuildable projection boundary | 14 only if evidence justifies it |
| `backend/memory/procedural/` | System-owned procedural publication/read boundary | 15 |
| `backend/memory/write_pipeline/models.py` | Existing semantic domain extended with lifecycle vocabulary and typed deterministic single/set normalized-value contracts | 6 |
| `backend/memory/write_pipeline/registry.py` | `semantic-registry-v2`: eight governed P0 Travel Agent keys, values, synonyms, scopes, sensitivity floors, and cardinality | 6 |
| `backend/memory/write_pipeline/model_adapter.py` | Bounded bilingual extraction/normalization across registry-v2 keys; no hotel-only hard-code | 8 |
| `backend/tests/unit/memory_write_pipeline/test_registry.py` | Registry-v2 key/value/cardinality/normalization and fail-closed coverage | 6 |
| `backend/tests/unit/memory_write_pipeline/test_model_adapter.py` | Multi-key structured extraction and invalid-output rejection | 8 |
| `backend/memory/write_pipeline/resolver.py` | Deterministic single/set consolidation, immutable set snapshot transitions, and `REVOKE` | 6 |
| `backend/memory/write_pipeline/postgres.py` | Canonical Memory store primitives | 6, 7, 9, 11 |
| `backend/memory/write_pipeline/worker.py` | Positive handling + background commit | 11 |
| `backend/conversations/repository.py` | Owner-scoped repository contract for bounded recent-dialogue reads | 4 |
| `backend/conversations/service.py` | Application seam for bounded recent dialogue strictly before the current user message | 4 |
| `backend/conversations/postgres_repository.py` | Bounded recent-dialogue read plus caller-owned transaction primitives preserving guarded transitions | 4, 7 |
| `backend/app/runtime_container.py` | Runtime composition only; no new public Memory router | 8, 10, 15 |
| `backend/rag/contracts.py` | RAG-owned retrieval evidence/citation/ContextBundle; not generic Memory context | 10 |
| `backend/rag/generation/llm.py` | Transitional generator consumes neutral `GenerationContext`, not RAG evidence semantics | 10 |
| `backend/rag/generation/rag_service.py` | Travel-context builder plus narrow adapter into neutral generation contract; no Memory import | 10 |
| `backend/rag/evaluation/runtime.py` | RAG evaluation adapts to neutral generation result while retaining exact retrieval evidence | 10 |
| `backend/tests/unit/test_llm_generator.py` | Migrate generator contract tests from RAG `ContextBundle`/`GeneratedAnswer` to neutral generation contracts while preserving RAG-only prompt characterization | 10 |
| `backend/tests/unit/test_rag_contracts.py` | Keep retrieval/citation provenance tests in RAG; replace the removed `GeneratedAnswer` assertion with the neutral generation-result contract | 10 |
| `backend/tests/unit/test_rag_service.py` | Adapt RAG service fakes/results to the neutral generator seam without changing travel retrieval behavior | 10 |
| `backend/tests/unit/test_evaluation_runner.py` | Adapt evaluation fakes/type assertions from `GeneratedAnswer` to `GenerationResult` | 10 |
| `backend/tests/integration/test_rag_evaluation_flow.py` | Preserve end-to-end RAG evaluation evidence while migrating the generation result type | 10 |
| `backend/storage/migrations/versions/20260912_03_agent_memory_lifecycle.py` | Source handling + lifecycle/retention/revoke/suppression persistence | 6 |
| `backend/storage/migrations/versions/20260912_04_episodic_memory.py` | Episodic persistence only | 12 |
| `backend/storage/migrations/versions/20260912_05_working_memory.py` | Working Memory persistence only | 13 |
| `backend/storage/migrations/versions/20260912_06_procedural_publication.py` | Separate procedural publication state | 15 |
| `docs/evaluation/agent-memory-evaluation.md` | Stage metrics and promotion evidence | 4, 11–16 |

## Execution Stage Map

| Architecture stage | Tasks | Exit condition |
| --- | --- | --- |
| Stage-1 prerequisites | 1–2 | Boundary sentinel reflects the approved Memory domain and telemetry is content-safe before new traces |
| Stage 1 — understand/route/source handling | 3–5 | Typed turn understanding and positive source-handling authority pass their hard gates |
| Stage 2 — explicit semantic write/store | 6–8 | All eight registry-v2 keys, including deterministic set union/replacement/member-forget semantics, pass their Stage-2 gates and remember/correct/forget/re-remember work atomically through Chat |
| Stage 3 — governed read/use | 9–10 | Semantic read, neutral generation context, inspect, and explicit cross-conversation use pass |
| Stage 4 — background inference | 11 | Shadow formation/activation and bounded outbox behavior pass before inferred promotion |
| Stage 5 — additional tenant Memory families | 12–13 | Episodic then Working Memory each pass independent vertical-slice gates |
| Stage 6 — retrieval projection decision | 14 | Structured retrieval is proven sufficient or execution stops for an approved projection amendment |
| Stage 7 — procedural publication | 15 | System-owned publication authority and migration/readiness proof pass |
| Final proof | 16 | Cross-stage evaluation and every required runtime/test evidence source are conclusive |

## Acceptance-Criteria Traceability

This table is the execution/review map for the 25 acceptance criteria in the
approved governing specification v0.7. The criterion count is unchanged from
approved v0.6; v0.7 only tightens the contracts mapped below. A criterion is not considered implemented merely
because a task mentions the same concept; the mapped task must produce the
corresponding verification evidence and Task 16 must confirm the final
cross-stage behavior.

| Spec AC | Required outcome | Primary task evidence |
| --- | --- | --- |
| 1 | Authenticated PostgreSQL-only standalone Chat remains the baseline | 1, 6–10, 16 |
| 2 | Workspace/SQLite/separate Memory Manager are not reintroduced | 1, 8, 16 |
| 3 | Turn Understanding is typed and non-authoritative | 3–4 |
| 4 | Durable explicit mutation requires deterministic speech-act corroboration | 4, 8 |
| 5 | Explicit Memory effect + ack + source handling + idempotency commit atomically | 7–8 |
| 6 | Authority/scope/retention/sensitivity/lifecycle/response precedence stay distinct | 3, 5–6, 9–10 |
| 7 | Forget prevents stale resurrection during formation, activation, and read | 6, 8–11, 16 |
| 8 | Background extraction requires a persisted family-specific `BACKGROUND_ELIGIBLE` record; a proposal or missing record is insufficient | 5, 6, 11, 16 |
| 9 | Only lifecycle-eligible relevant active Memory reaches controlled context | 9–10, 16 |
| 10 | Explicit semantic E2E passes before inferred activation | 8, 10–11 |
| 11 | Every additional Memory family arrives as an evaluated vertical slice | 12–15 |
| 12 | Required PostgreSQL integration verification executes without required skips | 6–7, 9, 11–16 |
| 13 | Zero-tolerance gates pass; missing required evidence is `INCONCLUSIVE` | 4, 11, 16 |
| 14 | Migration/recovery/deletion behavior is documented before production enablement | 6, 11, 15–16 |
| 15 | Explicit commit preserves guarded terminal transition and canonical lock order | 7–8, 16 |
| 16 | Procedural Memory is system-owned publication state, not a tenant scope | 15–16 |
| 17 | Retention, temporal expiry, and typed source validity remain independent; `USER_DURABLE` value retention never re-exposes deleted-source evidence | 6, 9–10, 12–13, 16 |
| 18 | Shared runtime cannot bypass tenant isolation with a privileged DB role | 6–7, 9, 15–16 |
| 19 | `TurnDisposition` stays distinct from `MessageStatus`, obeys the matrix, and remains internal | 3–4, 16 |
| 20 | `memory_outbox` has a bounded lifecycle before broad Memory-write enablement | 11, 16 |
| 21 | Legacy retention backfill maps conversation scope to `CONVERSATION_BOUND` and user scope to `SOURCE_BOUND`, never silently to `USER_DURABLE` | 6, 16 |
| 22 | `MemoryLifecyclePolicy` exposes one pure stage-aware `evaluate` interface, closed deterministic reasons, explicit stage facts, and closed `SourceValidity` input semantics; `RetentionAssignmentPolicy` is the sole initial retention-assignment owner | 6, 16 |
| 23 | Persisted source handling uses the exact governed append-only `memory_source_handling` schema, tenant RLS, unique `(source_outbox_id, family)` authority, and no product-path update/delete | 6, 16 |
| 24 | Suppression generation starts at `1`; governed work carries a generation stamp; storage-owned `REVOKE` works for single/set and atomically advances generation; CAS `expected_version_id` stays distinct from semantic `reference_version_id` | 6, 16 |
| 25 | Semantic-registry-v2 normalization is data-driven from governed per-key values/synonyms while existing hotel constants remain compatibility aliases only, never special execution branches | 6, 16 |

---

## Task 1: Stage 1 Prerequisite — Refine the Clean-Break Memory Sentinel

**Files:** Modify `backend/tests/boundaries/test_clean_break_boundaries.py` only.

**Contract:** The filesystem-derived scan and eight-route approved HTTP surface
remain intact. The sentinel stops equating every `backend.memory.*` import with
legacy Memory and instead rejects the frozen legacy root modules/surfaces that
the 2026-09-10 clean break removed. New architecture modules under
`backend/memory/` are permitted without per-module allowlist maintenance. For
imports below `backend.memory`, legacy classification is **root-scoped**: inspect
the first segment after `backend.memory`, not every later segment. Thus
`backend.memory.evaluation.*` may remain forbidden while
`backend.memory.write_pipeline.evaluation.*` remains valid retained code.

- [x] Add RED mutation tests proving `backend.memory.lifecycle` is currently
  misclassified as legacy while planted legacy imports are still detected in
  both supported syntactic forms: `import backend.memory.service` and
  `from backend.memory import service`.
- [x] Replace the blanket `"memory" in mod_parts` rule with a closed legacy
  **root-module** denylist covering removed roots such as `service`,
  `sqlite_repository`, `repository`, `retrieval`, `promotion`, `policy`,
  `extraction`, `evaluation`, and the removed Memory-control/public-route
  surfaces. Match `backend.memory.<legacy_root>` and descendants by the first
  segment after `backend.memory`; handle `from backend.memory import <legacy_root>`
  explicitly. Do not use `"policy" in mod_parts`, `"evaluation" in mod_parts`,
  or a per-module allowlist of the new architecture.
- [x] Add regression assertions that retained
  `backend.memory.write_pipeline.policy` and
  `backend.memory.write_pipeline.evaluation.runner` are allowed while the
  corresponding removed root forms remain rejected.
- [x] Preserve the derived package scan and existing closed `APPROVED_ROUTES`;
  no route is added by this task.
- [x] Rename/update the sentinel docstring and test wording so the executable
  invariant says “legacy Memory command/service surfaces never return” rather
  than “all `backend.memory` outside `write_pipeline` is forbidden.”
- [x] Re-run the boundary suite. The new-architecture mutation is GREEN and the
  planted legacy import still makes the guard RED when mutation-tested.
- [x] Review checkpoint: this task changes only the meaning of the stale
  sentinel; it creates no product Memory behavior.

## Task 2: Stage 1 Prerequisite — Operational Telemetry Hardening

**Files:** Modify `backend/observability/models.py`,
`backend/observability/redaction.py`, `backend/observability/events.py`,
`backend/app/api/chat.py`, and `backend/app/api/conversations.py`; extend
`backend/tests/unit/test_observability_models.py`,
`test_observability_redaction.py`, and `test_observability_events.py`.

**Contracts:** `failure_class` means an exception-class identifier only and must
match `^[A-Za-z_][A-Za-z0-9_]{0,63}$`. **`OperationalEvent.reason_code`** is a
bounded machine code matching `^[a-z][a-z0-9_]{0,63}$`. This rule applies to the
structured operational-event boundary and `emit_event(...)` inputs; it does not
retroactively redefine persisted Memory audit/idempotency columns or
`MemoryChangeSet.reason` merely because they also use the name `reason_code`.
New Memory-domain reasons introduced by this plan remain typed at their own
domain boundary and may project their enum `.value` into operational telemetry.
Neither operational field may contain exception messages or user content.
Redaction is a second line of defense.

- [x] Write RED tests rejecting content-bearing `failure_class`/`reason_code`
  values, accepting representative exception class names and snake-case reason
  codes, and redacting normalized secret keys including `access_token`,
  `refresh_token`, `x-api-key`/`x_api_key`, and `session_id`.
- [x] Inventory the existing raw-log call sites that use
  `failure_class=validation`, `failure_class=not_found`, or
  `failure_class=conversation_not_found`; reclassify those domain outcomes as
  `reason_code=<closed_code>` while keeping real exception classes as
  `type(error).__name__`. Do not convert exception classes into one global enum.
- [x] Inventory every **operational** `emit_event(..., reason_code=<variable>)`
  producer and prove its value source is bounded by the new shape rule. Current
  variable producers include the API request completion path and readiness
  helpers; the RAG generation path already emits a closed literal. Treat
  `reason_code=` assignments in `backend/memory/write_pipeline/postgres.py` as
  persisted Memory audit/idempotency columns, not `OperationalEvent` inputs.
  They are outside this telemetry-shape change and must not be rewritten merely
  to satisfy the operational regex.
- [x] Add dedicated shape validators for `failure_class` and `reason_code` at
  the `OperationalEvent` boundary. Keep raw exception text and `str(error)` out
  of structured events.
- [x] Keep this task out of Memory persistence semantics: do not rewrite the
  existing shadow audit value `<decision_reason>|resolved_<operation>`, Memory
  event/idempotency schema, or `MemoryChangeSet.reason` unless a separate
  approved persistence change later requires it.
- [x] Normalize secret-like field names before classification, then retain the
  existing token/path patterns only as defense in depth. Do not add a growing
  regex catalogue as the primary privacy mechanism.
- [x] Re-run focused observability/API tests and confirm existing safe IDs,
  durations, counters, and governed reason codes still survive sanitization.
- [x] Review checkpoint: no new Memory tracing may be enabled until this task is
  GREEN; this is a prerequisite, not a final-stage cleanup.

## Task 3: Stage 1 Contracts and Ephemeral Dialogue State

**Files:** Create `backend/orchestration/turn_models.py`,
`backend/orchestration/dialogue_state.py`; create unit tests under
`backend/tests/unit/orchestration/`.

**Interfaces:**

```python
class TurnDisposition(str, Enum):
    ANSWERED = "answered"
    NEEDS_CLARIFICATION = "needs_clarification"
    INCOMPLETE = "incomplete"
    EXECUTION_FAILED = "execution_failed"

class DialogueStateResolver:
    def resolve(self, recent_turns: Sequence[Message]) -> DialogueState: ...
```

`DialogueStateResolver` is deliberately structural in Stage 1. It reconstructs
eligible delivered user/assistant turns from exactly one conversation, orders
them by stored `sequence`, and exposes the latest user/assistant turns. It must
not infer topic, referents, current goal, intent, or clarification semantics;
those belong to `TurnUnderstanding` in Task 4. Mixed-conversation input fails
closed instead of producing plausible cross-conversation state.

The approved combination contract copied from the specification is:

| Persisted `MessageStatus` | Finalized `TurnDisposition` |
| --- | --- |
| `PENDING` | none; disposition is not finalized yet |
| `FAILED` | any non-`ANSWERED` terminal disposition; never `ANSWERED` |
| `COMPLETE` | `ANSWERED`, `NEEDS_CLARIFICATION`, `INCOMPLETE`, or `EXECUTION_FAILED` |

- [x] Write RED tests for the matrix above and structural dialogue-state
  reconstruction: empty history, stored ordering, pending/failed filtering,
  latest delivered user/assistant turns, and mixed-conversation rejection;
  tests must not invent additional persistence semantics.
- [x] Run the focused tests and confirm import/contract failure.
- [x] Implement immutable closed contracts and deterministic recent-turn-only
  `DialogueStateResolver`; no semantic interpretation, model, DB write, or
  Working Memory dependency. Reject mixed-conversation input deterministically.
- [x] Re-run focused tests to GREEN.
- [x] Review: public `ChatResponse` has no `TurnDisposition`; resolver imports no
  Memory persistence/provider module.

## Task 4: Stage 1 Understanding, Explicit Intent Gate, Router, and Planner

**Files:** Modify `backend/orchestration/turn_models.py`; create
`backend/orchestration/turn_understanding.py`,
`backend/orchestration/action_router.py`, and
`backend/orchestration/context_planner.py`; modify
`backend/orchestration/conversation_orchestrator.py`, `backend/app/config.py`,
`backend/conversations/repository.py`, `backend/conversations/service.py`, and
`backend/conversations/postgres_repository.py`; create
`docs/evaluation/agent-memory-evaluation.md`; modify only the existing Memory
evaluation modules needed to compute the Stage-1 metrics; add focused unit and
repository/service tests.

**Interfaces:**

```python
class TurnUnderstanding:
    def understand(self, message: str, state: DialogueState) -> TurnUnderstandingResult: ...

class ExplicitIntentGate:
    def authorize(self, result: TurnUnderstandingResult) -> ExplicitIntentDecision: ...

class ContextPlanner:
    def plan(self, understanding: TurnUnderstandingResult) -> ContextPlan: ...

class ConversationService:
    def get_recent_messages_before(
        self,
        conversation_id: str,
        owner_user_id: str,
        before_sequence: int,
        limit: int = DEFAULT_HISTORY_LIMIT,
    ) -> tuple[Message, ...]: ...
```

`turn_models.py` is the single contract owner for Task-4 closed orchestration
types. Task 4 may add immutable `TurnUnderstandingResult`,
`ExplicitIntentDecision`, `ContextPlan`, and their closed enums there; behavior
stays in `turn_understanding.py`, `action_router.py`, and `context_planner.py`.
Do not create parallel model modules for the same contracts.

**Recent-dialogue reconstruction contract:** Task 4 does not read an unbounded
conversation and does not use `get_messages_in_range(..., limit=N)` as a
substitute for "latest N": the existing range API orders ascending before
applying `LIMIT`, so on a long conversation that would select the oldest rows in
the range. Add the dedicated owner-scoped `get_recent_messages_before()` seam.
Its storage implementation selects at most `DEFAULT_HISTORY_LIMIT = 50` rows
with `sequence < before_sequence`, chooses the newest matching rows, then returns
them in ascending transcript order. It must not assume sequence numbers are
dense. The current user message is passed separately to `TurnUnderstanding` and
must not appear inside `DialogueState`; for a just-persisted user message at
sequence `S`, orchestration reads history with `before_sequence=S`. A first turn
therefore resolves an empty `DialogueState`. No new Task-4 history-window tuning
setting is introduced.

Task 4 consumes only the current message plus bounded recent dialogue.
Conversation Summary and Working Memory are explicitly outside this task; Stage
1 must not depend on either future context mechanism.

`TurnUnderstanding` owns the semantic outputs already governed by the spec:
`interaction_mode`, topics, entities/referents, current assertions and
overrides, Memory namespaces needed, temporal context, clarification need, and
closed reason codes. `DialogueStateResolver` remains structural and does not
pre-compute any of them.

`ExplicitIntentGate` is an authorization boundary, not another extractor. It
deterministically corroborates explicit remember/correct/forget speech acts;
model classification or payload parsing alone cannot authorize durable state.
`explicit_inspect` may be recognized in Stage 1, but before Stage 3 it returns a
controlled internal `INCOMPLETE`/capability-unavailable result and never
fabricates Memory state.

**Stage-1 rollout contract:** the planner produces a **proposed** context plan
for shadow evaluation only. Normal-query execution keeps the current RAG-only
baseline in this stage even when the proposal is `NONE`; Stage 1 must not skip
retrieval or change answer grounding on the authority of the new planner. Add
`CONTEXT_PLANNER_ENFORCEMENT_ENABLED=False` as the explicit rollout gate.
Planner-authoritative source execution begins only in Task 10 after the
context-mode quality gate and neutral generation seam exist.

- [x] Write RED repository/service tests for `get_recent_messages_before()`:
  owner isolation, exclusive `before_sequence`, first-turn empty history,
  newest-50 selection from a history longer than 50 rows, ascending returned
  order, and a sparse-sequence fixture proving the implementation does not
  derive the window by arithmetic over sequence density.
- [x] Implement the dedicated bounded recent-history repository/service seam.
  The PostgreSQL query may select descending to apply the limit to the newest
  eligible rows, but the application contract always returns ascending
  transcript order to `DialogueStateResolver`.
- [x] RED fixtures cover normal query, obvious remember/correct/forget,
  ambiguous/quoted/negated commands, context-dependent turns such as
  `"tiếp tục đi"`, `"cái đầu tiên"`, and `"giữ cái đó nhưng đổi ngày"`, and inspect.
- [x] Prove `TurnUnderstanding` — not `DialogueStateResolver` — derives the
  active topic, referent(s), current goal, and pending-clarification semantics
  needed by those context-dependent turns from the current message plus
  structural `DialogueState`.
- [x] Implement deterministic-first understanding; optional semantic parser is
  at most one structured hard-timeout call, returns only the governed closed
  schema, and never grants durable authority. A parser timeout/schema failure
  degrades to deterministic ambiguity/clarification behavior; it does not
  silently authorize an action or widen the context plan.
- [x] Planner exposes all four enum values but Stage 1 can return only `NONE` or
  `RAG_ONLY`; inspect returns controlled `INCOMPLETE` before Stage 3. Record the
  proposed plan for evaluation, but while
  `CONTEXT_PLANNER_ENFORCEMENT_ENABLED=False` keep the effective normal-query
  source plan at the existing `RAG_ONLY` baseline.
- [x] RED orchestration regression proves a Stage-1 proposal of `NONE` still
  executes the existing RAG generation path and cannot silently produce an
  ungrounded answer.
- [x] Add internal `disposition` to `TurnOutcome` without changing Chat schema.
- [x] Create `docs/evaluation/agent-memory-evaluation.md` as the canonical staged
  evaluation record, then add intent precision/recall, durable-action
  false-positive rate, clarification correctness, context-mode evaluation, and
  **false-`NONE` rate**: grounding-required queries proposed as `NONE` divided by
  all approved grounding-required fixtures. The artifact records dataset/fixture
  identity, metric definition, result, and gate state so Tasks 11–16 can extend
  the same evidence rather than creating parallel reports.
- [x] Treat missing/insufficient approved grounding-required fixtures as
  `INCONCLUSIVE`, never `PASS`. The hard gate requires zero false-`NONE` on a
  conclusive approved set before planner enforcement may be enabled. While the
  gate is `INCONCLUSIVE` or failing,
  `CONTEXT_PLANNER_ENFORCEMENT_ENABLED=False` remains mandatory.
- [x] Review: zero durable-action false positives on the approved hard-gate set.
- [x] Review the Stage-1 execution invariant explicitly: Task 4 proves
  understanding/planning quality but does **not** change normal answer-source
  execution. A proposed `NONE` still executes the existing RAG-only generation
  path while enforcement is disabled.

## Task 5: Positive Family-Specific Source Handling

**Files:** Create `backend/memory/source_handling.py` and unit tests; modify
orchestration only as needed to produce typed proposals. Persistence and actual
outbox-identity binding land with Task 6/Stage 2; Task 5 must not widen the
Conversation repository/service API merely to obtain `source_outbox_id`.

```python
class MemoryFamily(str, Enum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    WORKING = "working"
    PROCEDURAL = "procedural"

class SourceHandlingProposalOutcome(str, Enum):
    BACKGROUND_ELIGIBLE = "background_eligible"
    BACKGROUND_BLOCKED = "background_blocked"

class SourceHandlingReason(str, Enum):
    EXPLICIT_ACTION = "explicit_action"
    BACKGROUND_POLICY_ELIGIBLE = "background_policy_eligible"
    AMBIGUOUS_INTENT = "ambiguous_intent"
    SENSITIVE_BLOCKED = "sensitive_blocked"

@dataclass(frozen=True)
class SourceHandlingProposal:
    source_message_id: str
    family: MemoryFamily
    outcome: SourceHandlingProposalOutcome
    reason_code: SourceHandlingReason

class SourceHandlingOutcome(str, Enum):
    BACKGROUND_ELIGIBLE = "background_eligible"
    EXPLICIT_APPLIED = "explicit_applied"
    EXPLICIT_REFUSED = "explicit_refused"
    EXPLICIT_NOOP = "explicit_noop"
    FORGET_APPLIED = "forget_applied"
    FORGET_REFUSED = "forget_refused"

@dataclass(frozen=True)
class SourceHandlingRecord:
    source_outbox_id: str
    source_message_id: str
    family: MemoryFamily
    outcome: SourceHandlingOutcome
    reason_code: SourceHandlingReason
    recorded_at: datetime
```

- [x] RED proposal truth table proves `BACKGROUND_POLICY_ELIGIBLE ->
  BACKGROUND_ELIGIBLE`, while `EXPLICIT_ACTION`, `AMBIGUOUS_INTENT`, and
  `SENSITIVE_BLOCKED` produce `BACKGROUND_BLOCKED`. Task 5 may propose
  background handling only for `MemoryFamily.SEMANTIC`; later families remain
  contract vocabulary only until their evaluated stages.
- [x] RED authority truth table proves `record is None` is `UNHANDLED`/deny and
  every explicit authoritative outcome fails the background gate. The gate
  returns allow only for a persisted-shape `SourceHandlingRecord` whose outcome
  is exactly `BACKGROUND_ELIGIBLE`.
- [x] Implement `MemoryFamily`, proposal/outcome/reason vocabularies and the pure
  fail-closed gate in `backend/memory/source_handling.py` using standard-library
  dependencies only. Do not import `backend.memory.write_pipeline` into
  orchestration or duplicate its persistence/lifecycle policy.
- [x] Produce a typed `SourceHandlingProposal` from orchestration using the
  already-persisted `source_message_id`. A proposal has no `source_outbox_id` and
  cannot grant formation authority. Do not query storage for the outbox row or
  change `append_turn` / `create_conversation_with_initial_turn` return shapes in
  Task 5 merely to obtain that identity.
- [x] Normal eligible semantic source may propose background eligibility;
  ambiguous, sensitive/prohibited, or explicit-action sources may only produce
  a blocked proposal. Task 5 does not move or duplicate secret-detection
  ownership; the typed sensitive-blocked result is a policy input/denial reason,
  and later formation still revalidates prohibited content before model use.
- [x] Keep source-handling reasons typed and closed. Observability may project
  `.value` into its bounded `reason_code`; persistence/domain logic never branches
  on arbitrary free text.
- [x] Review: proposal != permission; absence is never interpreted as permission;
  `UNHANDLED` is absence of a persisted record, not an enum value; and Task 5
  introduces no persistence, worker consumer, or config flag.

## Task 6: Stage 2 Lifecycle Domain and PostgreSQL Schema

**Files:** Modify `backend/memory/write_pipeline/models.py`,
`backend/memory/write_pipeline/registry.py`,
`backend/memory/write_pipeline/resolver.py`, and
`backend/memory/write_pipeline/postgres.py`; create `backend/memory/lifecycle.py`
and migration `20260912_03_agent_memory_lifecycle.py`; update `ALEMBIC_HEAD`;
extend `backend/tests/unit/memory_write_pipeline/test_registry.py`, domain/resolver
unit tests, migration tests, and PostgreSQL integration tests.

**Contracts:** add `RetentionMode.CONVERSATION_BOUND | SOURCE_BOUND |
USER_DURABLE`, `MemoryOperation.REVOKE`, `VersionStatus.REVOKED`, nullable
`expires_at`, generation identity, assertion `suppression_generation`, durable
source handling, binding of actual `(source_outbox_id, family)` identity at the
storage/transaction seam, and the first production-useful
`semantic-registry-v2`. Reuse Task-5 `MemoryFamily`/`SourceHandlingRecord`
contracts rather than defining parallel enums or record types.

**Lifecycle-policy interface:** `backend/memory/lifecycle.py` owns one pure,
stage-aware interface and no I/O:

```python
class LifecycleStage(str, Enum):
    WRITE = "write"
    FORMATION = "formation"
    ACTIVATION = "activation"
    READ = "read"

class MemoryLifecyclePolicy:
    def evaluate(
        self,
        *,
        stage: LifecycleStage,
        facts: LifecycleFacts,
    ) -> LifecycleDecision: ...
```

The closed reason vocabulary is:

```python
class LifecycleReason(str, Enum):
    MISSING_REQUIRED_FACT = "missing_required_fact"
    SCOPE_INELIGIBLE = "scope_ineligible"
    SENSITIVITY_INELIGIBLE = "sensitivity_ineligible"
    STALE_GENERATION = "stale_generation"
    EXPIRED = "expired"
    SOURCE_INVALID = "source_invalid"
    STATUS_INELIGIBLE = "status_ineligible"
    ELIGIBLE = "eligible"
```

When more than one predicate fails, `MemoryLifecyclePolicy.evaluate` returns the
first applicable reason in that exact order. `ELIGIBLE` is returned only after
all applicable checks pass. Free text may explain a decision in logs, but no
policy branch consumes free text.

`LifecycleFacts` carries only typed lifecycle inputs required by the selected
stage. The minimum fact matrix is normative:

| Lifecycle fact | WRITE | FORMATION | ACTIVATION | READ |
| --- | --- | --- | --- | --- |
| `retention_mode` | required | required | required | required |
| stamped suppression generation | required | required | required | required |
| current assertion suppression generation | required | required | required | required |
| scope | required | required | required | required |
| sensitivity | required | required | required | required |
| source/provenance validity | required for `CONVERSATION_BOUND` / `SOURCE_BOUND`, not required to authorize `USER_DURABLE` value retention | same | same | same |
| `expires_at` | optional | optional | optional | optional |
| evaluation time | required iff `expires_at` is present | same | same | same |
| lifecycle status | not applicable | not applicable | not applicable | required and must be `ACTIVE` |

Missing facts that the selected stage requires return
`MISSING_REQUIRED_FACT`. `READ` requires an eligible `ACTIVE` version; earlier
stages apply only their relevant lifecycle predicates. This module must not
query PostgreSQL, call a model/provider, or branch on API-vs-worker execution
mode.

`source/provenance validity` is represented by a closed enum, never a raw bool,
row, or free-text reason:

```python
class SourceValidity(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    NOT_REQUIRED = "not_required"
```

`LifecycleFacts.source_validity` is `SourceValidity | None`. The caller owning
the canonical source/evidence snapshot derives this fact before policy
evaluation; `MemoryLifecyclePolicy` never performs source/evidence I/O. For
`CONVERSATION_BOUND` and `SOURCE_BOUND`, `None` or `NOT_REQUIRED` returns
`MISSING_REQUIRED_FACT`, while `INVALID` returns `SOURCE_INVALID`. For
`USER_DURABLE` normalized-value eligibility, `NOT_REQUIRED` is the explicit
valid state; source deletion does not invalidate the normalized durable value.
This does not authorize access to deleted-source raw evidence: the governed
evidence/provenance read boundary filters invalid/deleted source material before
`MemoryReadEngine`, inspect, trace, citation, or `MemoryContextComposer` can
consume it. Task 9/10 implement that read boundary; Task 16 proves zero deleted-
source leakage.

**Retention-assignment interface:** the same module owns a separate pure
assignment policy. Assignment occurs before write; lifecycle evaluation never
re-derives retention:

```python
class RetentionAssignmentPolicy:
    def assign(
        self,
        *,
        scope: MemoryScope,
        authority: Authority,
    ) -> RetentionMode: ...
```

The initial mapping is closed: conversation scope -> `CONVERSATION_BOUND` for
every governed authority; user scope + `EXPLICIT_SAVE` -> `USER_DURABLE`; user
scope + `EXPLICIT_STATEMENT` or `REPEATED_INFERENCE` -> `SOURCE_BOUND`.
Unknown combinations fail closed. Execution mode is not an input.

**Generation and version-reference contract:** `MemoryCandidate`,
`MemoryVersionDraft`, and `MemoryVersion` carry one positive
`suppression_generation` stamp. `LifecycleFacts.stamped_generation` is projected
from that field and compared with the assertion's current
`suppression_generation`. New assertions start at generation `1`.

`MemoryOperation.REVOKE` is a semantic command, not a request to choose the next
generation. Do not add `next_generation` to `MemoryChangeSet`. Under the
assertion lock, the PostgreSQL write boundary must verify the current version,
mark the governed current version `REVOKED`, and increment
`memory_assertions.suppression_generation` atomically. Re-remember writes a new
version stamped with the new current generation; old-generation candidates,
drafts, or versions fail lifecycle evaluation with `STALE_GENERATION`.

Keep the two existing version identifiers separate:

- `expected_version_id` remains the CAS/concurrency precondition argument to
  `MemoryUnitOfWork.apply_memory_change`; mismatch rejects the write without a
  mutation.
- `MemoryChangeSet.reference_version_id` remains semantic linkage to a related
  version. It is not a concurrency token and must not be reused as one.

**Task-6 migration contract:**

- Add `memory_source_handling` as the durable authority table with this exact
  initial schema: `owner_user_id TEXT NOT NULL`, `source_outbox_id TEXT NOT NULL`,
  `source_message_id TEXT NOT NULL`, `family TEXT NOT NULL`, `outcome TEXT NOT
  NULL`, `reason_code TEXT NOT NULL`, and `recorded_at TIMESTAMPTZ NOT NULL`.
  `source_outbox_id`/`source_message_id` use the existing text identity
  convention of `conversation_outbox`/messages. Enforce uniqueness on
  `(source_outbox_id, family)`; do not add mutable bookkeeping columns merely
  for implementation convenience.
- Enable and force tenant RLS on `memory_source_handling`. `travel_app` and
  `travel_worker` receive only the `SELECT`/`INSERT` privileges required by
  their governed paths; no product path receives `UPDATE` or `DELETE` on this
  authority table.
- Duplicate insertion of an identical `(source_outbox_id, family)` record is an
  idempotent replay; the same authority key with different authoritative
  content fails closed. Do not implement mutable upsert semantics.
- Existing `conversation`-scope Memory backfills to
  `RetentionMode.CONVERSATION_BOUND`; existing `user`-scope Memory backfills to
  `RetentionMode.SOURCE_BOUND`. Legacy rows never become `USER_DURABLE` by
  migration. A source-bound row lacking provably valid provenance is ineligible
  until a new governed write establishes current evidence.
- Add `memory_assertions.suppression_generation` as `NOT NULL`, initial/default
  value `1`, with a positive-generation constraint (`>= 1`). Existing assertions
  backfill to generation `1`.
- `MemoryOperation.REVOKE` is a writing operation for both `SINGLE` and `SET`
  assertions. A successful revoke changes the governed current version to
  `REVOKED` and advances the assertion generation atomically; removing the last
  set member is one revoke trigger, not a set-only definition of revoke.
- Add the generation stamp required above to candidate/draft/version domain
  contracts and persist the version stamp. The migration/backfill must make
  existing version rows consistent with assertion generation `1`; no reader may
  manufacture a current-generation stamp when durable data says otherwise.

**Registry-definition contract:** every `SemanticKeyDefinition` owns its governed
per-value English/Vietnamese synonym data together with values, cardinality,
allowed scopes, and sensitivity floor. The representation must be immutable to
callers. `is_known_key`, lookup, and normalization are data-driven over the
registry entries; no hotel-specific execution branch remains.

Existing exported hotel constants required by current callers/evaluation — in
particular `HOTEL_ATMOSPHERE_KEY` and any directly-used companion constant —
remain compatibility aliases into the registry-v2 definition during Task 6.
They must not own separate values, normalization logic, or a special execution
branch. Removing those aliases is a later caller-migration cleanup, not a Task-6
requirement.

**Semantic Registry v2 — P0 product slice:**

| Canonical key | Kind | Cardinality | Governed normalized values |
| --- | --- | --- | --- |
| `travel.preference.hotel_atmosphere` | preference | single | `quiet`, `lively`, `central`, `secluded` |
| `travel.preference.accommodation_type` | preference | set | `hotel`, `resort`, `hostel`, `homestay`, `apartment`, `villa` |
| `travel.preference.transport_mode` | preference | set | `flight`, `train`, `bus`, `car`, `motorbike`, `public_transit`, `walking` |
| `travel.preference.travel_pace` | preference | single | `relaxed`, `balanced`, `packed` |
| `travel.preference.activity_style` | preference | set | `nature`, `culture`, `food`, `nightlife`, `shopping`, `adventure`, `relaxation`, `photography` |
| `travel.constraint.budget_level` | constraint | single | `budget`, `midrange`, `premium`, `luxury` |
| `travel.preference.food_style` | preference | set | `local`, `street_food`, `fine_dining`, `cafe`, `vegetarian_friendly`, `international` |
| `travel.profile.default_departure_city` | profile fact | single | `ho_chi_minh_city`, `hanoi`, `da_nang`, `can_tho`, `hai_phong`, `nha_trang`, `hue`, `phu_quoc` |

All eight entries allow user scope plus conversation-scope override and retain the
`ordinary_personal` minimum sensitivity floor unless the shared sensitivity
classifier raises it. The departure-city value is deliberately a governed
Travel Agent location slug in v2; unsupported cities trigger clarification or
no-store, never durable raw city text. Additional cities/keys are later reviewed
registry revisions, not model-invented values.

For `set` cardinality, extend the domain contract so one assertion version holds
a canonical sorted/deduplicated set of allowed members. Persistence must remain
structured (JSON payload plus deterministic normalized representation); do not
encode sets as `"a|b"`/CSV strings and do not change canonical assertion identity
merely to create one assertion row per selected member. Single-valued keys keep
the existing one-current-value invariant.

The domain representation is explicit rather than inferred from delimiters:
`NormalizedSemanticValue = str | tuple[str, ...]`. `single` keys carry one
governed `str`; `set` keys carry a non-empty, sorted, deduplicated tuple whose
members all belong to the registry entry. `MemoryCandidate`,
`MemoryVersionDraft`, and `MemoryVersion` use that contract consistently. In
PostgreSQL, `value_payload["normalized_value"]` is a JSON string for `single`
and a JSON array for `set`. The existing textual `normalized_value` column may
remain as a deterministic derived representation for lookup/audit, but a set is
serialized there as canonical compact JSON equivalent to
`json.dumps(list(value), separators=(",", ":"), ensure_ascii=False)` rather than
delimiter text, and reads rebuild the typed value from `value_payload` and
verify the derived representation. No reader may expose a raw JSON string as the
in-process set value.

**Set consolidation semantics:**

- First governed set signal -> `ADD` one canonical snapshot.
- Positive `SAME`/`COMPATIBLE` evidence is treated as member evidence, not a
  replacement command. Compute `union(active, candidate)` deterministically. If
  the union is unchanged, return `REINFORCE`; if it grows, return `SUPERSEDE`
  with a new full snapshot and supersede the prior active version. Never mutate
  an existing version payload in place.
- Deterministic relation pre-check classifies a candidate whose members are
  already contained by the active set as `SAME`; a positive candidate that adds
  governed members is `COMPATIBLE`. The bounded relation classifier is used only
  when those comparisons do not resolve the relation.
- Explicit correction or targeted member forget is not encoded as
  `CONTRADICTION`. The explicit-action layer reads the current active snapshot,
  materializes the desired full replacement snapshot, and submits the governed
  temporal-update path. A non-empty replacement -> `SUPERSEDE`; removing the
  final member -> `REVOKE` plus the normal suppression-generation advance.
- Background/model-only evidence may propose compatible additions or an
  unresolved relation, but may not independently request member removal or full
  replacement. Ambiguous negative intent stays non-mutating.
- A `CONTRADICTION` classification that overlaps members already present in the
  active set is an inconsistent relation result and fails closed with the
  governed relation/value-mismatch reason. Do not convert classifier
  inconsistency into an idempotent user action. Repeated positive evidence must
  reach `SAME`/`COMPATIBLE` and reinforce there.

- [x] RED registry tests enumerate all eight keys, every allowed normalized
  member, English/Vietnamese governed synonyms, single/set cardinality, scope,
  sensitivity floor, unknown-key rejection, unknown-member rejection, duplicate
  set-member collapse, and deterministic set ordering.
- [x] RED domain/resolver tests pin the set truth table: first-set `ADD`,
  duplicate/subset `REINFORCE`, compatible member addition -> immutable
  union-`SUPERSEDE`, explicit full replacement -> `SUPERSEDE`, targeted member
  removal -> replacement `SUPERSEDE`, removal of the final member -> `REVOKE`,
  and contradictory same/overlapping-member classifier output -> fail-closed
  relation/value mismatch. Re-read after add/replace/remove must preserve typed
  tuple shape and stable ordering.
- [x] RED persistence round-trip tests prove JSON-array storage for sets,
  canonical textual representation, typed reconstruction on read, and no
  delimiter encoding or in-place update of an existing version payload.
- [x] RED domain tests prove expiry/source validity independence, revoke +
  generation advance, stale generation rejection, re-remember as a new
  generation, the closed `LifecycleReason` vocabulary/precedence, every row of
  the stage-required-facts matrix, and fail-closed unknown retention-assignment
  inputs.
- [x] RED lifecycle tests pin `SourceValidity.VALID | INVALID | NOT_REQUIRED`,
  prove that bound retention rejects missing/`NOT_REQUIRED` validity, that
  `INVALID` yields `SOURCE_INVALID`, and that `USER_DURABLE` value eligibility
  accepts `NOT_REQUIRED` without granting raw-source access.
- [x] RED migration tests assert exact columns/constraints/indexes, source record
  uniqueness, append-only replay-vs-conflict behavior, RLS/ownership, least-
  privilege app/worker grants, conservative retention backfill, generation-1
  backfill/default/check constraint, and downgrade round-trip.
- [x] Implement `MemoryLifecyclePolicy` as the only lifecycle-rule owner; early
  stages apply stage-appropriate rules without pretending a candidate is ACTIVE.
  Implement `RetentionAssignmentPolicy` beside it as the only initial
  retention-assignment owner. Unit tests must cover every `LifecycleStage`,
  every closed reason and its deterministic precedence, the normative fact
  matrix, retention assignment for all current `MemoryScope`/`Authority`
  combinations, missing-required-fact fail-closed behavior,
  temporal/source/generation independence, and the rule that execution mode is
  not a policy input.
- [x] RED/write-store tests prove `REVOKE` generation advance is owned by the
  locked PostgreSQL write boundary rather than resolver/model output, that no
  `next_generation` field exists on `MemoryChangeSet`, and that
  `expected_version_id` CAS behavior remains distinct from
  `reference_version_id` semantic linkage.
- [x] Replace the registry's current hotel-only `is_known_key`, lookup, and
  normalization branches with data-driven `semantic-registry-v2` definitions.
  Existing `hotel_atmosphere` behavior is a regression baseline, not a special
  execution path.
- [x] Preserve currently-imported `HOTEL_ATMOSPHERE_*` compatibility constants
  as aliases into registry-v2 and add a regression test proving they resolve to
  the same governed definition/value data; no alias may retain separate
  normalization or execution logic.
- [x] Extend `Cardinality` with `SET`, change the normalized-value contracts
  consistently, and update stale single-only docstrings/comments in
  `models.py`, `registry.py`, and `resolver.py`; do not leave type annotations or
  comments implying every assertion is single-valued.
- [x] Keep resolver deterministic/side-effect-free and implement the set truth
  table above without adding `REMOVE_MEMBER` as a persistence operation. Model
  output cannot emit an authorized revoke, member removal, or set replacement by
  itself. Add `REVOKE` to persistence writing-operation handling for both
  cardinalities and verify generation advance is atomic with revocation.
- [x] Implement migration `20260912_03_agent_memory_lifecycle.py` exactly to the
  Task-6 migration contract above. Advance head to `20260912_03` only if the
  preflight head is still `20260912_02`; update all non-historical executable
  head assertions/documentation that represent current runtime state.
- [x] Required PostgreSQL tests run without skips.
- [x] Treat the eight-key registry as one closed Stage-2 contract for this plan:
  every key must pass its task-local registry/extraction/E2E evidence before
  Stage 2 exits. Do not silently drop a failing key during implementation;
  changing the approved eight-key P0 set requires a plan amendment. Task 11's
  inferred activation remains separately promoted per key/type.
- [x] Review: privacy deletion ledger remains distinct from product forget.

## Task 7: Stage 2 Transaction-Aware Stores and Dual Commit Coordinators

**Files:** Modify `backend/conversations/repository.py`,
`backend/conversations/postgres_repository.py`, `backend/memory/write_pipeline/uow.py`,
`backend/memory/write_pipeline/postgres.py`; create
`backend/memory/commit_coordinators.py`; add focused CORE tests now and defer the
exhaustive PostgreSQL concurrency/failure matrix to final hardening.

**Interfaces:**

```python
class MemoryWriteStore(Protocol):
    def apply_on(self, connection: Connection, *, change: MemoryChangeSet,
                 principal: AuthenticatedPrincipal,
                 evidence: tuple[MemoryEvidence, ...] = (),
                 decision: MemoryDecisionDraft | None = None,
                 idempotency_key: str | None = None,
                 expected_version_id: str | None = None,
                 fence: FenceContext | None = None,
                 source_validity: SourceValidity | None = None,
                 ) -> MemoryWriteResult: ...

@dataclass(frozen=True)
class ExplicitMemoryCommitRequest:
    principal: AuthenticatedPrincipal
    conversation_id: str
    assistant_message_id: str
    expected_deletion_epoch: int
    acknowledgement_text: str
    change: MemoryChangeSet
    evidence: tuple[MemoryEvidence, ...]
    decision: MemoryDecisionDraft | None
    idempotency_key: str
    expected_version_id: str | None
    source_validity: SourceValidity | None
    source_handling_record: SourceHandlingRecord

@dataclass(frozen=True)
class ExplicitMemoryCommitResult:
    memory: MemoryWriteResult
    transition: TransitionResult

@dataclass(frozen=True)
class BackgroundMemoryCommitRequest:
    principal: AuthenticatedPrincipal
    change: MemoryChangeSet
    evidence: tuple[MemoryEvidence, ...]
    decision: MemoryDecisionDraft | None
    idempotency_key: str
    expected_version_id: str | None
    source_validity: SourceValidity | None
    fence: FenceContext

class ExplicitMemoryTurnCommit:
    def commit(self, request: ExplicitMemoryCommitRequest) -> ExplicitMemoryCommitResult: ...

class BackgroundMemoryCommit:
    def commit(self, request: BackgroundMemoryCommitRequest) -> MemoryWriteResult: ...
```

The Task-7 request/result types above are frozen value contracts, not a license
to invent another transaction abstraction. `MemoryWriteStore.apply_on(...)`
mirrors the Task-6 `MemoryUnitOfWork.apply_memory_change(...)` write inputs and
executes exactly once on the supplied connection: it does not open, commit, or
roll back a transaction and does not run an internal whole-transaction retry.
The existing UoW facade may retain transaction ownership/bounded retry for its
standalone callers, but it delegates the actual storage mutation to the same
`apply_on(...)` primitive.

For explicit commit, the existing turn identity is `conversation_id` plus the
pending `assistant_message_id`; do not introduce a new `turn_id`. The explicit
request carries the deletion epoch observed by the API path so the coordinator
can validate it under the conversation lock before Memory mutation. It carries
the deterministic acknowledgement text and authoritative
`SourceHandlingRecord` because ADR 0036 requires those effects in the same
transaction. The explicit coordinator passes `fence=None` to the Memory store.

For background commit, `FenceContext` is required and already carries the
conversation/deletion epoch plus outbox id/lease owner needed for the worker
lock/fence checks and terminal source-event transition. It does not gain API
acknowledgement authority. A persisted background-eligibility source-handling
record is an authorization precondition from the governed source-handling path;
Task 7 does not manufacture a new authority record merely to complete a worker
transaction.

**CORE — required before Task 8:**

- [x] RED transaction-journal tests assert lock order `conversation -> memory`
  for explicit and `conversation -> outbox -> memory` for worker commits.
- [x] Extract caller-owned conversation primitives for tenant bind,
  conversation/deletion-epoch lock, and guarded terminal transition; preserve
  existing `TransitionResult.applied` behavior.
- [x] Extract `MemoryWriteStore.apply_on(connection, ...)`; existing UoW may stay
  as a facade but delegates to the same primitive.
- [x] Implement both coordinators. Explicit path never needs the outbox lease
  fence; worker path validates it before Memory mutation.
- [x] Add one focused stale-snapshot test proving an explicit set replacement or
  member-forget carries the base `expected_version_id` and is rejected if that
  version changed before the locked write. Task 7 must surface the stale result;
  Task 8 owns bounded re-read/re-resolution of the user intent. No stale snapshot
  may overwrite a concurrently changed set.
- [x] Add one representative late-failure rollback test proving the explicit
  coordinator owns one atomic transaction: a forced failure after prior Memory/
  idempotency/source-handling/ack work leaves no partial durable effect and no
  guarded terminal transition applied.
- [x] Run focused guard regressions for owner isolation, deletion epoch, stale
  worker lease, duplicate idempotency, and guarded terminal transition. Reuse
  existing tests where they already prove the invariant; do not create a broad
  permutation matrix merely for Task-7 progression.
- [x] Review: neither coordinator bypasses domain guards with ad-hoc semantic SQL.

**DEFERRED HARDENING — does not block Task 8, but remains mandatory before
Task 16/final production-readiness proof:**

- [ ] Complete ADR 0036's exhaustive forced-failure validation at each explicit
  commit step, not only the representative CORE rollback case.
- [ ] Run PostgreSQL concurrency/deadlock coverage for canonical lock ordering,
  including competing explicit/background writers and concurrent set updates;
  required final evidence must execute without required skips.
- [ ] Run the full PostgreSQL owner-isolation, deletion-epoch, lease-loss,
  duplicate-idempotency, and concurrent terminal-transition matrix under the
  isolated database test environment.
- [ ] Add stress/permutation coverage only where it materially increases confidence
  in transaction/fencing correctness; performance/load tuning and generalized
  retry optimization are final-hardening concerns, not Task-7 CORE scope.

## Task 8: Stage 2 Chat-Native Explicit Remember/Correct/Forget

**Files:** Create `backend/memory/explicit_actions.py`; modify
`backend/memory/write_pipeline/model_adapter.py`,
`backend/orchestration/conversation_orchestrator.py`,
`backend/app/runtime_container.py`, and `backend/app/config.py`; extend
`backend/tests/unit/memory_write_pipeline/test_model_adapter.py`; add
explicit-action unit tests and Chat/PostgreSQL E2E tests.

```python
class ExplicitMemoryActionHandler:
    def propose(self, understanding: TurnUnderstandingResult,
                state: DialogueState) -> ExplicitMemoryProposal: ...
```

- [x] RED fixtures cover remember, correction, forget, re-remember,
  registry-invalid payload, prohibited secret, ambiguous intent, retry, set
  member addition, set replacement, targeted set-member forget, and whole-key
  forget.
- [x] RED extraction fixtures cover all eight registry-v2 keys in English and
  Vietnamese, including multi-member set values, unsupported departure cities,
  unknown keys/values, and a mixed utterance that yields several independent
  governed candidates without collapsing them into `hotel_atmosphere`.
- [x] Implement deterministic gate -> one bounded structured parse when needed ->
  registry/sensitivity/policy -> deterministic resolver. Timeout/invalid output
  means no durable mutation.
- [x] For set-valued keys, keep speech-act authority deterministic: ordinary
  positive remember statements propose member additions; explicit correction
  materializes a full desired replacement from the governed current snapshot;
  targeted forget removes only the named governed members from that snapshot;
  whole-key forget emits the existing assertion-level revoke. If a correction or
  member-forget request cannot be resolved to a complete deterministic desired
  snapshot, do not mutate and return the governed clarification/non-mutation
  outcome rather than guessing from model relation output.
- [x] Bind every set replacement/removal proposal to the `expected_version_id`
  of the active snapshot used to materialize it. `ExplicitMemoryTurnCommit`
  verifies that expectation under the Memory lock; stale state triggers bounded
  re-read/re-resolution, never blind retry of the old replacement snapshot.
- [x] Generalize `model_adapter.py` from its current hotel-only prompt/parser to
  emit only keys present in registry v2 and normalize through the registry. The
  model may propose raw labels, but only deterministic registry normalization can
  create durable normalized values.
- [x] Wire the explicit proposal through `ExplicitMemoryTurnCommit`; acknowledgement
  is deterministic application copy, not a second free-form generation.
- [x] Add `MEMORY_EXPLICIT_ACTIONS_ENABLED=False` as an independent gate.
- [x] Keep the explicit-action gate default-off for broad rollout even after
  this task passes. Controlled E2E/evaluation may enable it, but production-like
  write volume remains blocked until Task 11's `memory_outbox` bound is GREEN.
- [x] Keep inspect unavailable in this task.
- [x] E2E tests prove atomic ack/effect, idempotency, no resurrection,
  cross-owner isolation, set add/correct/member-forget/whole-key-forget
  semantics, and no public Memory router/UI resurrection.
- [x] Review: Stage 2 is complete only after remember/correct/forget/re-remember
  work across all eight governed keys as one explicit semantic-family vertical
  slice; a failing governed key blocks the stage rather than being silently
  omitted.

## Task 9: Stage 3 Semantic Memory Read Engine

**Files:** Create `backend/memory/read_models.py`,
`backend/memory/read_engine.py`, and `backend/memory/postgres_store.py`; modify
`backend/memory/write_pipeline/postgres.py`,
`backend/memory/commit_coordinators.py`, `backend/storage/postgres.py`, and the
PostgreSQL migration/integration tests; create the next Alembic revision after
`20260914_01` for assertion conflict state; add read-engine unit and RLS
integration tests.

```python
class MemoryStore(Protocol):
    def list_storage_scoped(self, request: MemoryReadRequest) -> Sequence[StoredMemoryRow]: ...

class MemoryReadEngine:
    def select(self, request: MemoryReadRequest) -> MemorySelection: ...
```

**Task-9 closed contracts:**

1. `MemoryReadRequest.max_selected` defaults to `8`, validates inclusively in
   `1..8`, rejects booleans/non-integers, and cannot exceed the eight-key
   registry-v2 cap. After lifecycle,
   precedence, and conflict filtering, selection order is exactly
   `valid_from DESC -> canonical_key ASC -> version_id ASC`. Task 9 adds no
   ML/vector score.
2. `StoredMemoryRow` carries physical lifecycle facts only. The version row
   supplies `retention_mode`, `expires_at`, `status`, sensitivity, and the
   **stamped** suppression generation; the assertion row supplies
   `canonical_key`, scope, scope ID, the **current** suppression generation, and
   the authoritative unresolved-conflict flag. Database strings are converted
   back to the closed enums, and set-valued JSON arrays are reconstructed as
   immutable tuples before the row reaches `MemoryReadEngine`.
   `PostgresMemoryStore` may join/project source/conversation validity facts but
   never returns `is_readable` or another eligibility verdict.
   `MemoryReadEngine` alone builds `LifecycleFacts` and calls
   `MemoryLifecyclePolicy.evaluate(READ, ...)`.
3. `MemoryReadRequest.requested_keys` is a validated tuple of registry-v2
   canonical keys. Relevance is exact membership only; Task 9 does not parse
   user text, keyword-match, or derive keys from `TurnUnderstandingResult`.
   An empty requested-key tuple produces abstention. Task 10 owns application
   planning from turns to requested keys.
4. `MemorySelection` exposes only selected structured records
   (`version_id`, `canonical_key`, `normalized_value`, `scope`, `scope_id`,
   `authority`, `valid_from`) and one closed abstention reason. It exposes no
   raw evidence/source text or per-row rejection trace. Observability uses
   aggregate counters/logs outside this result contract.
5. A conversation-scoped record may override a user-scoped record only for the
   same canonical key and the request's current conversation. It never mutates
   or deletes the user-scoped record.

**Authoritative unresolved-conflict state:**

- Current conflict state is an assertion property, not an inference from
  historical `memory_events`, `memory_outbox`, or `memory_decisions`. Add
  `memory_assertions.has_unresolved_conflict BOOLEAN NOT NULL DEFAULT FALSE` in
  the Task-9 migration. Historical rows backfill to `FALSE`; no history scan is
  used to guess current state.
- Applying `MemoryOperation.PENDING_CONFLICT` sets the flag to `TRUE` for that
  assertion in the same transaction that persists the pending-conflict write
  evidence/event state. A failed transaction exposes neither side.
- Background/inferred paths never clear this flag. A successful
  `ExplicitMemoryTurnCommit` may clear it in the same transaction only when the
  same assertion receives an authoritative explicit resolution through
  `ADD`, `REINFORCE`, `SUPERSEDE`, or `REVOKE`. `NOOP` and
  `PENDING_CONFLICT` never clear it.
- `PostgresMemoryStore` projects the boolean unchanged as a physical fact.
  `MemoryReadEngine` owns the semantic consequence: if any storage-scoped row
  for a requested canonical key is marked unresolved, the engine suppresses
  the **whole key** before conversation/user precedence and ranking. If no key
  remains, it abstains.
- The conflict flag is deliberately the only new persistence state for this
  concern. Do not add a conflict table, conflict event-sourcing reducer, vector
  projection, or read-time reconstruction from history in Task 9.

- [x] RED truth table rejects deleted, revoked, expired, stale-generation,
  invalid-source, sensitivity-blocked, unresolved-conflict, and foreign-owner rows.
- [x] RED PostgreSQL tests prove `PENDING_CONFLICT` sets the assertion flag,
  explicit authoritative resolution clears it atomically, background work cannot
  clear it, and rollback leaves the prior flag unchanged.
- [x] RED store tests prove `canonical_key` and current generation come from the
  assertion row, stamped generation comes from the version row, enums are typed,
  and set values are reconstructed as tuples.
- [x] Implement exact structured semantic lookup first; no full-text/pgvector.
- [x] Keep `MemoryStore` limited to physical/tenant predicates;
  `MemoryLifecyclePolicy` owns semantic eligibility.
- [x] Implement relevance -> response precedence -> conflict exclusion -> ranking
  -> bounded selection/abstention in `MemoryReadEngine`.
- [x] `MemoryReadEngine` owns an injected `MemoryStore` and exposes the approved
  `select(request)` interface; callers do not pass preloaded rows or evaluation
  timestamps through the public API.
- [x] Fixtures prove unrelated query abstention and conversation override over
  user-scoped soft preference without mutation, whole-key conflict suppression,
  deterministic ordering, and a real eight-item cap.
- [x] PostgreSQL integration proves owner/RLS isolation with zero required skips.
- [x] Review: RAG imports no Memory module; Memory Read imports no RAG package.

## Task 10: Stage 3 Context Planning, Memory Use, and Explicit Inspect

**Files:** Modify `context_planner.py`; create `context_arbiter.py`,
`backend/memory/context.py`, `backend/generation/__init__.py`, and
`backend/generation/contracts.py`; modify `explicit_actions.py`, orchestrator,
runtime container, config, `backend/rag/contracts.py`,
`backend/rag/generation/llm.py`, `backend/rag/generation/rag_service.py`, and
`backend/rag/evaluation/runtime.py`; add planner/arbiter/composer,
generation-contract, RAG-contract/regression, and E2E tests.

**Contracts:** Stage 3 makes `MEMORY_ONLY` and `BOTH` reachable.
`MemoryContextComposer` emits only governed structured key/value/scope/influence
data. `ContextArbiter` owns precedence, token budget, and projection from
source-specific records into a source-neutral final-generation contract. Travel
citations remain travel citations. RAG retains `RetrievalResult`,
`CitationEvidence`, and its retrieval `ContextBundle`; those types are not moved
into the generation package. This task is also the first task allowed to make
the Stage-1 `ContextPlanner` proposal authoritative for normal-query source
execution; enabling that behavior requires the Task-4 context-mode gate,
including zero false-`NONE` on the approved grounding-required hard-gate set.

```python
class ContextSufficiency(str, Enum):
    NOT_REQUIRED = "not_required"
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"

@dataclass(frozen=True)
class GenerationCitation:
    title: str
    url: str

@dataclass(frozen=True)
class GenerationContext:
    prompt_context: str
    citations: tuple[GenerationCitation, ...]
    sufficiency: ContextSufficiency

@dataclass(frozen=True)
class GenerationResult:
    reply: str
    model: str
    citations: tuple[GenerationCitation, ...]
```

`GenerationContext` deliberately has no `travel_evidence`, `memory_context`, or
Memory/RAG domain types. `backend/generation/contracts.py` imports neither
`backend.rag`, `backend.memory`, nor `backend.orchestration`. This is an
implementation-level dependency correction under ADR 0039, not a new
architecture decision: no authority, policy owner, or public contract changes.
`ContextSufficiency.NOT_REQUIRED` is distinct from `INSUFFICIENT`: a turn such
as ordinary conversation may need no external source at all, whereas a turn
whose planned grounding source produced nothing must fail/abstain through the
controlled insufficient-context path. `GenerationResult` likewise remains
source-neutral; final-answer generation must not return a RAG-owned result type.

- [ ] RED fixtures cover `NONE`, `RAG_ONLY`, `MEMORY_ONLY`, `BOTH`, current-user
  override, Memory unavailable, RAG unavailable, and prompt-injection-like stored
  content.
- [ ] RED rollout tests prove planner enforcement remains disabled when
  `CONTEXT_PLANNER_ENFORCEMENT_ENABLED=False`; after the Task-4 quality gate is
  conclusive and passing, enabling it makes `NONE|RAG_ONLY|MEMORY_ONLY|BOTH`
  authoritative through `ContextArbiter` rather than through ad-hoc branches.
- [ ] RED contract tests prove `GenerationContext` is source-neutral, a valid
  Memory-only context is `ContextSufficiency.SUFFICIENT` with zero travel
  citations, an ordinary no-source turn can be `NOT_REQUIRED`, and a planned
  grounding source that returns nothing is `INSUFFICIENT` without falsifying
  RAG retrieval evidence.
- [ ] Implement prompt-safe Memory composition; never inject raw source/evidence.
- [ ] Keep `RAGService.build_travel_context()` returning the RAG-owned
  `ContextBundle`. Refactor the narrow generation seam so
  `generate_from_context()` consumes neutral `GenerationContext`; the existing
  `generate_answer()` path projects its own travel bundle into that contract for
  backward compatibility. Map `ContextBundle.insufficient_evidence=True` to
  `ContextSufficiency.INSUFFICIENT` rather than redefining that RAG flag. RAG
  gains no Memory import.
- [ ] Make `LLMGenerator` return neutral `GenerationResult` and update the RAG
  runtime/evaluation callers accordingly. Remove the now-redundant RAG-owned
  `GeneratedAnswer` contract after all call sites migrate. `RetrievalResult` and
  `CitationEvidence` stay RAG-owned so retrieval score/text/provenance do not
  leak upward into the generic generation layer.
- [ ] Migrate the existing direct consumers/tests explicitly:
  `test_llm_generator.py`, `test_rag_contracts.py`, `test_rag_service.py`,
  `test_evaluation_runner.py`, and `test_rag_evaluation_flow.py`.
  `test_rag_contracts.py` is rewritten to keep testing RAG evidence/citation
  provenance while the neutral `GenerationResult` contract gets its own test;
  do not merely delete coverage with `GeneratedAnswer`.
- [ ] `ContextArbiter` preserves RAG retrieval/citation provenance outside the
  neutral contract, projects only final display citations plus bounded prompt
  context into `GenerationContext`, and never copies raw `RetrievalResult.text`
  or raw Memory evidence as an instruction channel.
- [ ] Update the generator's system contract so it no longer assumes every
  admitted context item is “travel guide evidence.” It must treat labeled Memory
  as soft/user-state context, let the current request override remembered soft
  preferences, and emit travel citations only for travel evidence. Characterize
  the existing RAG-only behavior before the prompt refactor and keep that slice
  GREEN.
- [ ] Deliver `explicit_inspect` through the same governed read boundary; inspect
  exposes safe fields, never unrestricted evidence.
- [ ] Add `MEMORY_READ_ENABLED=False` and `MEMORY_USE_ENABLED=False`; use cannot
  be enabled before read, and rollback disables use before read.
- [ ] Run the complete explicit semantic vertical-slice evaluation: remember in
  conversation A/use in B, unrelated abstention, conversation override,
  correction, forget, and re-remember. The evaluation matrix must exercise every
  registry-v2 key at least once, prove set-valued preferences survive
  normalization/read/use without order instability, and prove current-turn input
  overrides remembered soft preferences/constraints for that response.
- [ ] Run RAG-only regression coverage including `test_llm_generator.py`,
  `test_rag_service.py`, `test_rag_generation_imports.py`, conversation
  orchestrator/chat bindings, and the RAG evaluation flow so the neutral seam
  does not degrade the existing baseline.
- [ ] Review: inferred activation remains impossible until this slice passes;
  RAG imports no Memory module, Memory imports no RAG module, and the neutral
  generation contract imports neither domain.

## Task 11: Stage 4 Background Semantic Formation, Activation, and Outbox Bound

**Files:** Create `backend/memory/formation.py` and `activation.py`; modify
`background_recorder.py`, `worker.py`, Memory evaluation modules, Postgres store,
config, `docs/evaluation/agent-memory-evaluation.md`, and deployment runbook;
add formation/activation/worker integration tests.

**Contracts:** Background formation requires positive family handling. Semantic
conversation-scope inference needs two independent agreeing user turns; user-scope
inference needs three independent evidence items across at least two conversations,
with no unresolved conflict. Redelivery/re-extraction of one source never
increases support.

- [ ] RED fixtures prove missing handling, duplicate delivery, same-source
  re-extraction, secret input, stale generation, deleted source, and unresolved
  contradiction cannot activate.
- [ ] Split formation, consolidation, activation: formation creates immutable
  evidence/candidate; existing resolver consolidates; activation is a separate
  deterministic policy; `BackgroundMemoryCommit` owns commit.
- [ ] Add `MEMORY_INFERRED_ACTIVATION_ENABLED=False`; shadow evaluation may run
  while active inferred versions remain impossible.
- [ ] Bound `memory_outbox` **before any broad Memory-write enablement**. Tasks
  8–10 may have exercised explicit writes in controlled evaluation, but their
  default-off mutation flag is not eligible for broad rollout until this step
  is GREEN. Because the outbox is rebuildable
  projection intent rather than canonical Memory and no consumer exists yet,
  add `MEMORY_PROJECTION_OUTBOX_RETENTION_DAYS=30` and
  `MEMORY_PROJECTION_OUTBOX_CLEANUP_BATCH_SIZE=500`. A worker maintenance pass
  deletes pending projection events older than the retention cutoff in bounded
  batches and records only closed prune reason/count telemetry. Canonical Memory
  is sufficient to rebuild a later projection; cleanup is never Memory deletion.
- [ ] Active inference requires a conclusive passing evaluation; missing/skipped
  evidence is `INCONCLUSIVE`. Promotion is per semantic key/type: evidence that
  `hotel_atmosphere` is safe does not authorize inferred activation of
  `budget_level`, `default_departure_city`, or any other registry-v2 key.
- [ ] Run worker/PostgreSQL retry/fence/idempotency tests without required skips.
- [ ] Review: zero background-without-positive-handling and zero post-forget
  resurrection failures.

## Task 12: Stage 5 Episodic Memory Vertical Slice

**Files:** Create `backend/memory/episodic.py`; extend registry, formation,
activation, read engine, evaluation; create
`backend/storage/migrations/versions/20260912_04_episodic_memory.py`; update
`ALEMBIC_HEAD`; add episode unit and PostgreSQL integration tests.

**Contract:** An episode requires grounded actor/event/time/provenance. One event
may activate only when those fields validate. Episode use remains lower
precedence than current request, verified hard constraints, and Working Memory.

- [ ] RED fixtures cover grounded event, missing actor/time/provenance,
  duplicate source, source deletion, retention, and unrelated-query abstention.
- [ ] Add the minimum typed episode representation and persistence required by
  those fixtures; do not add free-form speculative family tables.
- [ ] Wire episode formation -> activation -> lifecycle -> read/use with the same
  tenant/source/suppression policy owners used by semantic Memory.
- [ ] Run episode evaluation for extraction/grounding precision, source deletion,
  read abstention, precedence, and prompt safety.
- [ ] Run migration round-trip and required PostgreSQL isolation tests.
- [ ] Review: episode support independently passes its vertical-slice gate before
  Working Memory begins.

## Task 13: Stage 5 Working Memory Vertical Slice

**Files:** Create `backend/memory/working.py`; modify dialogue-state resolver,
formation, activation, read engine; create
`backend/storage/migrations/versions/20260912_05_working_memory.py`; update
`ALEMBIC_HEAD`; add Working Memory and resolver tests.

**Contract:** Working Memory is governed conversation open state/summary
replacement, not the ephemeral `DialogueState`. It becomes an additional input
to `DialogueStateResolver` only after passing lifecycle/read eligibility; that
does not move semantic interpretation out of `TurnUnderstanding`.

- [ ] RED fixtures cover deterministic replacement, stale-source rejection,
  conversation deletion, current-turn precedence, and non-duplication with
  ephemeral dialogue state.
- [ ] Implement typed Working Memory and source-consistent replacement; no raw
  transcript blob becomes a durable instruction.
- [ ] Admit only eligible Working Memory to `DialogueStateResolver`; recent turns
  remain the immediate structural dialogue source and `TurnUnderstanding`
  remains the semantic referent/topic/goal interpreter.
- [ ] Run cross-conversation/non-leakage, deletion, lifecycle, and read/use
  evaluation.
- [ ] Review: Working Memory cannot bypass conversation scope or become a second
  canonical transcript.

## Task 14: Stage 6 Structured-Retrieval Sufficiency Gate

**Files:** Extend `docs/evaluation/agent-memory-evaluation.md` and evaluation
runner/datasets. Create `backend/memory/projections.py` and a projection migration
only after the evidence branch below authorizes a plan amendment.

**Contract:** Projections can propose candidates only. Canonical tenant,
lifecycle, sensitivity, source-validity, conflict, and suppression checks still
run before use.

- [ ] Define and run the structured-retrieval benchmark across semantic,
  episodic, and Working Memory; measure retrieval precision/recall, correct
  abstention, latency, and token/cost behavior.
- [ ] If approved quality gates pass, record `NO_PROJECTION_REQUIRED` and add no
  full-text/pgvector dependency.
- [ ] If the benchmark fails specifically because candidate recall is
  insufficient, stop execution and submit a versioned plan amendment selecting
  PostgreSQL full-text or pgvector with measured justification, exact migration,
  grants, rebuild, revalidation, and rollback tests. The amendment must be
  approved before projection code is written.
- [ ] Review: no projection dependency is added merely because the architecture
  permits one.

## Task 15: Stage 7 System-Owned Procedural Publication

**Files:** Create `backend/memory/procedural/__init__.py`, `models.py`, `store.py`,
`publication.py`, `evaluation.py`; create migration
`20260912_06_procedural_publication.py` only if `20260912_05` is still the head;
update `backend/storage/postgres.py` `ALEMBIC_HEAD`, runtime/config only for read
consumption; add unit, migration, readiness, credential, and publication
integration tests.

```python
class ProceduralPublisher:
    def publish(self, candidate: ProcedureCandidate,
                evaluation: ProcedureEvaluation,
                approval: PublicationApproval) -> PublishedProcedure: ...

class ProceduralReader:
    def active(self, procedure_key: str) -> PublishedProcedure | None: ...
```

- [ ] RED authority tests prove tenant Chat and Memory-worker roles cannot mutate
  procedural publication state and a model candidate cannot self-publish.
- [ ] RED migration/readiness test proves applying
  `20260912_06_procedural_publication` without advancing `ALEMBIC_HEAD` is not a
  valid ready state; preflight must still observe `20260912_05` before this task
  writes the new migration.
- [ ] Implement separate system-owned versioned storage; do not reuse tenant
  `MemoryScope` or weaken tenant RLS.
- [ ] Publication requires deterministic validation, conclusive evaluation, and
  explicit repository-owner approval evidence.
- [ ] Runtime reads only a published active version and fails closed on invalid
  publication state.
- [ ] Advance `ALEMBIC_HEAD` to `20260912_06` in the same change as the migration
  and run migration round-trip plus readiness-revision verification.
- [ ] Implement rollback by version pointer/selection; never rewrite tenant
  Memory to roll back procedural state.
- [ ] Review: procedural behavior cannot override system/developer/security
  policy and ordinary Chat remains non-writable.

## Task 16: Cross-Stage Evaluation, Observability, Rollout, and Final Proof

**Files:** Finalize `docs/evaluation/agent-memory-evaluation.md`, deployment
runbook, closed-field observability definitions required by prior tasks, and E2E
Memory scenarios under `backend/tests/integration/`.

**Evidence layers:** understanding/action; formation; consolidation/lifecycle;
read/use; runtime. Missing required evidence is `INCONCLUSIVE`, never an
empty-dataset perfect score.

- [ ] Build the required E2E matrix proving cross-conversation remember/use,
  unrelated abstention, conversation override, correction, forget/no
  resurrection, re-remember as a new generation, source-deletion retention,
  shadow-before-promotion, worker retry idempotency, explicit commit rollback,
  and procedural non-writability from ordinary Chat. The semantic slice covers
  all eight registry-v2 keys, including at least one set-valued key with two
  simultaneous members and the governed departure-city profile fact.
- [ ] Prove zero-tolerance gates: no cross-owner mutation/selection, prohibited
  secret exposure to Memory model, classifier-only durable mutation,
  background-without-positive-handling, post-forget resurrection,
  unresolved-conflict use, non-atomic explicit commit, semantic duplication,
  deleted-source leakage, privileged shared-runtime role, or registry-invalid
  explicit durable Memory.
- [ ] Prove operational gates: required PostgreSQL scenarios actually execute;
  outbox growth is bounded; rollout flags disable in dependency order; logs have
  no raw Memory/evidence/secrets.
- [ ] Run every final verification command and record its exit status
  independently. A failure makes that evidence item fail or become
  `INCONCLUSIVE` as defined below, but must not suppress collection of unrelated
  checks that can still execute. Before the integration command, export
  `PG_TEST_DSN`, `PG_RUNTIME_TEST_DSN`, and `PG_WORKER_TEST_DSN` exactly as
  documented in `DEVELOPMENT.md`; do not replace them with inline placeholder
  credentials:

```bash
python -m compileall backend
.venv/bin/python -m pytest backend/tests/unit -q -p no:cacheprovider
.venv/bin/python -m pytest backend/tests/integration -m integration -q -p no:cacheprovider
.venv/bin/python -m pytest backend/tests -q -p no:cacheprovider
npm --prefix frontend run lint
git diff --check
npm --prefix frontend test -- --run
```

  The frontend regression suite is required evidence. If this host terminates
  Vitest with the already-observed exit `137`/memory pressure, rerun the same
  suite in repository CI or another approved higher-memory environment and
  attach that result to the verification record. `lint`, `build`, or an esbuild
  syntax check are supplementary evidence only; they never replace the test
  suite. If no suitable environment can execute the required suite, final
  verification is `INCONCLUSIVE`, not `PASS`. The already-collected backend,
  lint, and diff-check results remain valid evidence and are not discarded by
  the frontend infrastructure failure.

- [ ] Final review compares the exact Git-visible change set plus untracked files
  with all 25 spec acceptance criteria and ADR 0036–0040.

## Rollout Order

```text
0. Clean-break sentinel refinement + telemetry hardening prerequisites
1. Turn Understanding / ActionRouter / ContextPlanner shadow observation
2. Explicit Chat Memory implementation + controlled evaluation behind the
   default-off mutation gate
3. Memory Read
4. Memory prompt Use + planner-authoritative source execution after the
   context-mode/false-`NONE` gate passes
5. Bound `memory_outbox` + background capture; only after the outbox bound is
   GREEN may explicit Memory writes be enabled for broad rollout
6. Per-type inferred activation
7. Episodic / Working Memory
8. Optional projection only if evidence justifies it
9. Procedural publication
```

Rollback runs in reverse authority order: disable Use before Read; disable
inferred activation while preserving safe shadow evidence; stop new worker
claims while preserving reclaimable work; disable explicit actions without
restoring the removed Memory Manager/API. Revoke/suppression state is never
cleared as rollback.

## Plan Stop Conditions

Stop and return to architecture/plan review when:

1. the Alembic head or current store seams differ materially from this plan;
2. implementation requires changing an Accepted ADR;
3. `TurnDisposition` would need public API exposure;
4. a model would need durable authority beyond the approved bounded classifier;
5. a projection would be required without benchmark evidence;
6. tenant RLS/credential isolation would need weakening;
7. required PostgreSQL evidence cannot run; or
8. the neutral generation seam would require moving retrieval-domain
   `RetrievalResult`/`CitationEvidence` ownership out of RAG, importing Memory
   into RAG, or importing RAG into Memory;
9. the required frontend regression suite cannot run locally or in any approved
   external/CI environment, in which case verification remains `INCONCLUSIVE`;
   or
10. a task risks overwriting unrelated user work; or
11. set-valued registry support cannot preserve the approved canonical assertion
    identity/lifecycle model, typed normalized-value contract, immutable snapshot
    history, or the governed `ADD | REINFORCE | SUPERSEDE | REVOKE` transition
    semantics without a new architecture decision; in that case return to
    specification/ADR review rather than smuggling an identity/operation change
    into the registry implementation; or
12. any of the eight P0 registry keys cannot satisfy its Task 6/8 Stage-2 evidence.
    Do not silently remove or weaken that key; amend this plan explicitly before
    changing the closed registry contract.

## Self-Review Record

- [x] All 25 specification acceptance criteria have an explicit task/evidence
  mapping; Task 16 remains the final cross-stage proof rather than a substitute
  for the task-local gates.
- [x] Stage-1 prerequisites are Tasks 1–2; Stage 1 core is Tasks 3–5; Stage 2 is
  Tasks 6–8; Stage 3 is Tasks 9–10; Stage 4 is Task 11; Stage 5 is Tasks 12–13;
  Stage 6 is Task 14; Stage 7 is Task 15; cross-stage proof is Task 16.
- [x] The clean-break guard permits the approved new `backend/memory/`
  architecture without reintroducing any frozen legacy Memory/public surface;
  legacy matching is root-scoped and does not ban retained
  `write_pipeline.policy`/`write_pipeline.evaluation`.
- [x] Operational telemetry hardening precedes new Memory traces; domain reasons
  are typed and `failure_class` remains an exception-class identifier rather
  than an ever-growing enum. The operational `reason_code` validator does not
  silently redefine persisted Memory audit/idempotency reason fields.
- [x] Semantic Registry v2 is bounded to eight P0 Travel Agent keys; every key
  has governed values/cardinality and the plan adds multi-key extraction/read/use
  evidence instead of leaving `hotel_atmosphere` as the only production key.
- [x] Set-valued keys have an explicit typed representation and deterministic
  consolidation truth table: positive union is versioned, duplicates reinforce,
  explicit correction/member-forget materializes a full replacement, empty
  replacement revokes, and inconsistent contradiction output fails closed.
- [x] Stage 2 treats all eight P0 keys as one closed contract and blocks on a
  failing key; later inferred activation remains independently promoted per
  key/type rather than using one key's evidence to authorize another.
- [x] `MemoryLifecyclePolicy` has one owner reused across all lifecycle paths.
- [x] Lifecycle policy now has a closed reason vocabulary, deterministic reason
  precedence, and an explicit stage-required-facts matrix; retention assignment
  is owned by a separate pure `RetentionAssignmentPolicy` rather than inferred
  ad hoc by writers/readers.
- [x] Suppression generation has one write-side owner: governed work/version
  stamps are checked by lifecycle policy, while the locked PostgreSQL revoke
  path advances the assertion generation atomically. CAS `expected_version_id`
  remains distinct from semantic `reference_version_id`.
- [x] Explicit and background transaction owners remain distinct.
- [x] Public Chat schema does not expose `TurnDisposition`.
- [x] Stage-1 `ContextPlanner` is shadow-only: proposed `NONE` cannot skip the
  existing RAG baseline. Planner enforcement starts in Task 10 only after a
  conclusive context-mode gate with zero hard-gate false-`NONE` cases.
- [x] Stage-1 responsibility is single-owner: `DialogueStateResolver` performs
  deterministic structural context assembly and conversation isolation;
  `TurnUnderstanding` owns semantic topic/referent/goal/clarification
  interpretation.
- [x] `explicit_inspect` is unavailable before Stage 3.
- [x] Memory Read and RAG remain dependency-separated; source-specific RAG and
  Memory records are projected into a neutral generation contract instead of
  overloading `ContextBundle.insufficient_evidence`.
- [x] Projection work is evidence-gated rather than pre-authorized by fashion.
- [x] Procedural Memory stays outside tenant Memory scope/RLS.
- [x] Rollback, deletion, observability, evaluation, and required PostgreSQL
  verification are represented.
- [x] Explicit writes may be exercised in controlled evaluation before Task 11,
  but broad Memory-write rollout is blocked until the bounded `memory_outbox`
  lifecycle is GREEN.
- [x] Every planned migration advances and verifies `ALEMBIC_HEAD`, including
  procedural publication.
- [x] Final verification records independent check results; frontend regression
  evidence cannot be silently replaced by lint/build, and an unavailable
  required suite yields `INCONCLUSIVE` without hiding unrelated evidence.
- [x] Git delivery remains repository-owner authority.

## Completion Record

Plan version 0.9 was **Approved on 2026-09-14 by the repository owner** after a
traceability-only correction and is superseded by approved v0.10.

Plan version 0.10 was **Approved on 2026-09-14 by the repository owner** against
approved spec v0.6. It closes
the remaining Task-6 implementation choices that must not be invented by the
coding agent: closed lifecycle reasons and precedence, the normative stage-fact
matrix, the retention-assignment owner/mapping, storage-owned suppression-
generation advance, and the distinction between concurrency
`expected_version_id` and semantic `reference_version_id`. It also strengthens
AC 8 to require the persisted family-specific `BACKGROUND_ELIGIBLE` authority
record rather than a merely positive proposal. These clarifications do not
change ADR 0037 semantics or the eight-key registry scope.

Plan version 0.11 was **Approved on 2026-09-14 by the repository owner** against
approved spec v0.7. It freezes
the final four Task-6 clarification points before implementation: typed
`SourceValidity` and its producer boundary, deleted-source evidence suppression
ownership, the exact initial `memory_source_handling` column/type contract, and
registry-v2 compatibility aliases for existing hotel constants. It adds no new
Memory family, key, public API, persistence operation, or ADR-level decision.

Plan version 0.12 was **Approved on 2026-09-14 by the repository owner** against
approved spec v0.7 and accepted ADR 0036. It changes Task-7 execution sequencing,
not architecture: the transaction/store/coordinator invariants remain CORE,
while exhaustive failure injection, PostgreSQL concurrency/deadlock permutations,
and production-grade stress evidence move to deferred final hardening. Those
deferred checks remain mandatory before Task 16/final production-readiness proof.

Plan version 0.13 was **Approved on 2026-09-14 by the repository owner** against
approved spec v0.7 and accepted ADR 0036. It closes the Task-7 implementation
ambiguity without adding behavior: `MemoryWriteStore.apply_on(...)` now mirrors
the already-approved Task-6 write inputs, and the explicit/background coordinator
request/result value contracts are frozen around existing conversation, Memory,
source-handling, deletion-epoch, idempotency, CAS, and worker-fence authorities.
No new `turn_id`, execution mode, persistence operation, or transaction layer is
introduced.

Plan version 0.14 was **Approved on 2026-09-14 by the repository owner**. It changes only Task 9: current unresolved
conflict becomes an assertion-level PostgreSQL fact, `PENDING_CONFLICT` sets it,
only an authoritative explicit resolution may clear it, and the read adapter
projects that fact without reconstructing current state from history. It also
freezes the physical projection sources needed by the existing Task-9 read
contract. No new Memory family, retrieval mode, vector dependency, or ADR-level
authority is introduced.

Spec v0.7 plus this exact plan v0.14 are the current approved execution authority
for the remaining staged Agent Memory program. Plan v0.14 supersedes v0.13 as
current execution authority.
Task checkbox state is execution evidence only; it does not replace task review,
verification, or repository-owner change-set review.
