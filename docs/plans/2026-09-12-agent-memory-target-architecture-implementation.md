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

**Spec:** [Agent Memory Target Architecture](../specs/2026-09-12-agent-memory-target-architecture-design.md) v0.2 (Approved 2026-09-12)

| Field | Value |
| --- | --- |
| Status | Approved |
| Plan version | 0.5 — closes Semantic Registry v2 set-value consolidation semantics and Stage-2 traceability gaps in plan v0.4 |
| Date | 2026-09-12 |
| Last amended | 2026-09-13 |
| Approved specification | [Agent Memory Target Architecture](../specs/2026-09-12-agent-memory-target-architecture-design.md) v0.2, Approved 2026-09-12 |
| Required ADRs | ADR 0036, 0037, 0038, 0039, 0040 — Accepted 2026-09-12 |
| Execution owner | Coding agent under repository-owner instruction |
| Decision owner | Repository owner |
| Approval | Repository owner approved exact plan v0.5 on 2026-09-13 |
| Scope | Stages 1–7 of the approved target architecture, with independent rollout gates and evidence-based stop conditions |
| Verification | Focused unit tests per task, required PostgreSQL integration tests without required skips, evaluation gates, full backend suite, frontend regression suite, `compileall`, `git diff --check`, and exact change-set review |

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
8. Missing `SourceHandlingRecord` means `UNHANDLED`, never background permission.
9. Product forget is `REVOKE`/`REVOKED` plus suppression generation. It is not
   privacy erasure; stale generations cannot form, activate, or read.
10. `retention_mode`, optional `expires_at`, and source validity are independent
    eligibility dimensions. Retention is persisted at write time.
11. `ACTIVE` alone never means answer-eligible. Read still applies lifecycle,
    relevance, precedence, conflict exclusion, ranking, and bounded selection.
12. Memory context is structured data, never a citation or instruction channel.
    Raw source evidence does not enter generation context by default.
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
17. The current Alembic head is `20260912_02`. If it differs when execution
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
| `backend/orchestration/turn_models.py` | Closed turn-understanding, disposition, routing, context-plan contracts | 3 |
| `backend/orchestration/dialogue_state.py` | Ephemeral recent-turn state and referents | 3, 13 |
| `backend/orchestration/turn_understanding.py` | Deterministic-first understanding plus bounded structured parse | 4 |
| `backend/orchestration/action_router.py` | Deterministic branch selection and explicit-intent gate | 4 |
| `backend/orchestration/context_planner.py` | `none/rag_only/memory_only/both` source plan | 4, 10 |
| `backend/orchestration/context_arbiter.py` | Precedence/token-budget admission and source-to-generation projection | 10 |
| `backend/orchestration/conversation_orchestrator.py` | Bounded one-turn workflow and internal `TurnDisposition` | 4, 8, 10 |
| `backend/generation/contracts.py` | Source-neutral generation context/citation/result/sufficiency contracts | 10 |
| `backend/memory/source_handling.py` | Family source outcomes, typed reasons, positive background authority | 5 |
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
| `backend/conversations/postgres_repository.py` | Caller-owned transaction primitives preserving guarded transitions | 7 |
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

This table is the execution/review map for the 20 acceptance criteria in the
approved specification. A criterion is not considered implemented merely
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
| 8 | Background extraction requires positive source handling | 5, 11, 16 |
| 9 | Only lifecycle-eligible relevant active Memory reaches controlled context | 9–10, 16 |
| 10 | Explicit semantic E2E passes before inferred activation | 8, 10–11 |
| 11 | Every additional Memory family arrives as an evaluated vertical slice | 12–15 |
| 12 | Required PostgreSQL integration verification executes without required skips | 6–7, 9, 11–16 |
| 13 | Zero-tolerance gates pass; missing required evidence is `INCONCLUSIVE` | 4, 11, 16 |
| 14 | Migration/recovery/deletion behavior is documented before production enablement | 6, 11, 15–16 |
| 15 | Explicit commit preserves guarded terminal transition and canonical lock order | 7–8, 16 |
| 16 | Procedural Memory is system-owned publication state, not a tenant scope | 15–16 |
| 17 | Retention, temporal expiry, and source validity remain independent dimensions | 6, 9, 12–13 |
| 18 | Shared runtime cannot bypass tenant isolation with a privileged DB role | 6–7, 9, 15–16 |
| 19 | `TurnDisposition` stays distinct from `MessageStatus`, obeys the matrix, and remains internal | 3–4, 16 |
| 20 | `memory_outbox` has a bounded lifecycle before broad Memory-write enablement | 11, 16 |

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

The approved combination contract copied from the specification is:

| Persisted `MessageStatus` | Finalized `TurnDisposition` |
| --- | --- |
| `PENDING` | none; disposition is not finalized yet |
| `FAILED` | any non-`ANSWERED` terminal disposition; never `ANSWERED` |
| `COMPLETE` | `ANSWERED`, `NEEDS_CLARIFICATION`, `INCOMPLETE`, or `EXECUTION_FAILED` |

- [ ] Write RED tests for the matrix above and context-dependent turns such as
  `"tiếp tục đi"`; tests must not invent additional persistence semantics.
- [ ] Run the focused tests and confirm import/contract failure.
- [ ] Implement immutable closed contracts and deterministic recent-turn-only
  `DialogueStateResolver`; no model, DB write, or Working Memory dependency.
- [ ] Re-run focused tests to GREEN.
- [ ] Review: public `ChatResponse` has no `TurnDisposition`; resolver imports no
  Memory persistence/provider module.

## Task 4: Stage 1 Understanding, Explicit Intent Gate, Router, and Planner

**Files:** Create `turn_understanding.py`, `action_router.py`,
`context_planner.py`; modify `conversation_orchestrator.py`, `app/config.py`, and
Memory evaluation docs/modules; add focused unit tests.

**Interfaces:**

```python
class TurnUnderstanding:
    def understand(self, message: str, state: DialogueState) -> TurnUnderstandingResult: ...

class ExplicitIntentGate:
    def authorize(self, result: TurnUnderstandingResult) -> ExplicitIntentDecision: ...

class ContextPlanner:
    def plan(self, understanding: TurnUnderstandingResult) -> ContextPlan: ...
```

**Stage-1 rollout contract:** the planner produces a **proposed** context plan
for shadow evaluation only. Normal-query execution keeps the current RAG-only
baseline in this stage even when the proposal is `NONE`; Stage 1 must not skip
retrieval or change answer grounding on the authority of the new planner. Add
`CONTEXT_PLANNER_ENFORCEMENT_ENABLED=False` as the explicit rollout gate.
Planner-authoritative source execution begins only in Task 10 after the
context-mode quality gate and neutral generation seam exist.

- [ ] RED fixtures cover normal query, obvious remember/correct/forget,
  ambiguous/quoted/negated commands, `"tiếp tục đi"`, and inspect.
- [ ] Implement deterministic-first understanding; optional semantic parser is
  one structured hard-timeout call and never grants durable authority.
- [ ] Planner exposes all four enum values but Stage 1 can return only `NONE` or
  `RAG_ONLY`; inspect returns controlled `INCOMPLETE` before Stage 3. Record the
  proposed plan for evaluation, but while
  `CONTEXT_PLANNER_ENFORCEMENT_ENABLED=False` keep the effective normal-query
  source plan at the existing `RAG_ONLY` baseline.
- [ ] RED orchestration regression proves a Stage-1 proposal of `NONE` still
  executes the existing RAG generation path and cannot silently produce an
  ungrounded answer.
- [ ] Add internal `disposition` to `TurnOutcome` without changing Chat schema.
- [ ] Add intent precision/recall, durable-action false-positive rate,
  clarification correctness, context-mode evaluation, and **false-`NONE` rate**:
  grounding-required queries proposed as `NONE` divided by all approved
  grounding-required fixtures. The hard-gate dataset requires zero false-`NONE`
  before planner enforcement may be enabled; missing fixtures are
  `INCONCLUSIVE`.
- [ ] Review: zero durable-action false positives on the approved hard-gate set.

## Task 5: Positive Family-Specific Source Handling

**Files:** Create `backend/memory/source_handling.py` and unit tests; produce
typed proposals from orchestration. Persistence lands with Task 6 migration.

```python
class SourceHandlingReason(str, Enum):
    EXPLICIT_ACTION = "explicit_action"
    BACKGROUND_POLICY_ELIGIBLE = "background_policy_eligible"
    AMBIGUOUS_INTENT = "ambiguous_intent"
    SENSITIVE_BLOCKED = "sensitive_blocked"

@dataclass(frozen=True)
class SourceHandlingRecord:
    source_outbox_id: str
    source_message_id: str
    family: MemoryFamily
    outcome: SourceHandlingOutcome
    reason_code: SourceHandlingReason
    recorded_at: datetime
```

- [ ] RED truth table proves every explicit outcome fails the background gate.
- [ ] Implement unique authority identity `(source_outbox_id, family)` and
  `UNHANDLED` semantics; only `BACKGROUND_ELIGIBLE` grants future formation.
- [ ] Normal eligible semantic source may propose background eligibility;
  ambiguous, secret, or explicit-action sources may not.
- [ ] Keep source-handling reasons typed and closed. Observability may project
  `.value` into its bounded `reason_code`; persistence/domain logic never branches
  on arbitrary free text.
- [ ] Review: absence is never interpreted as permission.

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
source handling, and the first production-useful `semantic-registry-v2`.

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

- [ ] RED registry tests enumerate all eight keys, every allowed normalized
  member, English/Vietnamese governed synonyms, single/set cardinality, scope,
  sensitivity floor, unknown-key rejection, unknown-member rejection, duplicate
  set-member collapse, and deterministic set ordering.
- [ ] RED domain/resolver tests pin the set truth table: first-set `ADD`,
  duplicate/subset `REINFORCE`, compatible member addition -> immutable
  union-`SUPERSEDE`, explicit full replacement -> `SUPERSEDE`, targeted member
  removal -> replacement `SUPERSEDE`, removal of the final member -> `REVOKE`,
  and contradictory same/overlapping-member classifier output -> fail-closed
  relation/value mismatch. Re-read after add/replace/remove must preserve typed
  tuple shape and stable ordering.
- [ ] RED persistence round-trip tests prove JSON-array storage for sets,
  canonical textual representation, typed reconstruction on read, and no
  delimiter encoding or in-place update of an existing version payload.
- [ ] RED domain tests prove expiry/source validity independence, revoke +
  generation advance, stale generation rejection, and re-remember as a new
  generation.
- [ ] RED migration tests assert exact columns/constraints/indexes, source record
  uniqueness, RLS/ownership, and downgrade round-trip.
- [ ] Implement `MemoryLifecyclePolicy` as the only lifecycle-rule owner; early
  stages apply stage-appropriate rules without pretending a candidate is ACTIVE.
- [ ] Replace the registry's current hotel-only `is_known_key`, lookup, and
  normalization branches with data-driven `semantic-registry-v2` definitions.
  Existing `hotel_atmosphere` behavior is a regression baseline, not a special
  execution path.
- [ ] Extend `Cardinality` with `SET`, change the normalized-value contracts
  consistently, and update stale single-only docstrings/comments in
  `models.py`, `registry.py`, and `resolver.py`; do not leave type annotations or
  comments implying every assertion is single-valued.
- [ ] Keep resolver deterministic/side-effect-free and implement the set truth
  table above without adding `REMOVE_MEMBER` as a persistence operation. Model
  output cannot emit an authorized revoke, member removal, or set replacement by
  itself.
- [ ] Implement the migration and conservative explicit backfill; advance head to
  `20260912_03` only if the preflight head is still `20260912_02`.
- [ ] Required PostgreSQL tests run without skips.
- [ ] Treat the eight-key registry as one closed Stage-2 contract for this plan:
  every key must pass its task-local registry/extraction/E2E evidence before
  Stage 2 exits. Do not silently drop a failing key during implementation;
  changing the approved eight-key P0 set requires a plan amendment. Task 11's
  inferred activation remains separately promoted per key/type.
- [ ] Review: privacy deletion ledger remains distinct from product forget.

## Task 7: Stage 2 Transaction-Aware Stores and Dual Commit Coordinators

**Files:** Modify `backend/conversations/repository.py`,
`backend/conversations/postgres_repository.py`, `backend/memory/write_pipeline/uow.py`,
`backend/memory/write_pipeline/postgres.py`; create
`backend/memory/commit_coordinators.py`; add unit and PostgreSQL concurrency tests.

**Interfaces:**

```python
class MemoryWriteStore(Protocol):
    def apply_on(self, connection: Connection, *, change: MemoryChangeSet,
                 principal: AuthenticatedPrincipal, evidence: MemoryEvidence,
                 decision: MemoryDecision, idempotency_key: str,
                 fence: FenceContext | None) -> MemoryWriteResult: ...

class ExplicitMemoryTurnCommit:
    def commit(self, request: ExplicitMemoryCommitRequest) -> ExplicitMemoryCommitResult: ...

class BackgroundMemoryCommit:
    def commit(self, request: BackgroundMemoryCommitRequest) -> MemoryWriteResult: ...
```

- [ ] RED transaction-journal tests assert lock order `conversation -> memory`
  for explicit and `conversation -> outbox -> memory` for worker commits.
- [ ] RED concurrent set-update tests prove read-modify-write safety: an explicit
  correction/member-forget proposal carries the active base version it read;
  if another writer changes that assertion before commit, the locked
  `expected_version_id` check rejects the stale replacement and the application
  re-reads/re-resolves within the bounded retry policy. No stale snapshot may
  overwrite a concurrently added member.
- [ ] RED failure-injection tests fail after Memory effect, idempotency reservation,
  source handling, and acknowledgement and assert the whole explicit transaction
  rolls back.
- [ ] Extract caller-owned conversation primitives for tenant bind,
  conversation/deletion-epoch lock, and guarded terminal transition; preserve
  existing `TransitionResult.applied` behavior.
- [ ] Extract `MemoryWriteStore.apply_on(connection, ...)`; existing UoW may stay
  as a facade but delegates to the same primitive.
- [ ] Implement both coordinators. Explicit path never needs the outbox lease
  fence; worker path validates it before Memory mutation.
- [ ] Run owner-isolation, deletion-epoch, lease-loss, idempotency, and concurrent
  terminal-transition integration tests.
- [ ] Review: neither coordinator bypasses domain guards with ad-hoc semantic SQL.

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

- [ ] RED fixtures cover remember, correction, forget, re-remember,
  registry-invalid payload, prohibited secret, ambiguous intent, retry, set
  member addition, set replacement, targeted set-member forget, and whole-key
  forget.
- [ ] RED extraction fixtures cover all eight registry-v2 keys in English and
  Vietnamese, including multi-member set values, unsupported departure cities,
  unknown keys/values, and a mixed utterance that yields several independent
  governed candidates without collapsing them into `hotel_atmosphere`.
- [ ] Implement deterministic gate -> one bounded structured parse when needed ->
  registry/sensitivity/policy -> deterministic resolver. Timeout/invalid output
  means no durable mutation.
- [ ] For set-valued keys, keep speech-act authority deterministic: ordinary
  positive remember statements propose member additions; explicit correction
  materializes a full desired replacement from the governed current snapshot;
  targeted forget removes only the named governed members from that snapshot;
  whole-key forget emits the existing assertion-level revoke. If a correction or
  member-forget request cannot be resolved to a complete deterministic desired
  snapshot, do not mutate and return the governed clarification/non-mutation
  outcome rather than guessing from model relation output.
- [ ] Bind every set replacement/removal proposal to the `expected_version_id`
  of the active snapshot used to materialize it. `ExplicitMemoryTurnCommit`
  verifies that expectation under the Memory lock; stale state triggers bounded
  re-read/re-resolution, never blind retry of the old replacement snapshot.
- [ ] Generalize `model_adapter.py` from its current hotel-only prompt/parser to
  emit only keys present in registry v2 and normalize through the registry. The
  model may propose raw labels, but only deterministic registry normalization can
  create durable normalized values.
- [ ] Wire the explicit proposal through `ExplicitMemoryTurnCommit`; acknowledgement
  is deterministic application copy, not a second free-form generation.
- [ ] Add `MEMORY_EXPLICIT_ACTIONS_ENABLED=False` as an independent gate.
- [ ] Keep the explicit-action gate default-off for broad rollout even after
  this task passes. Controlled E2E/evaluation may enable it, but production-like
  write volume remains blocked until Task 11's `memory_outbox` bound is GREEN.
- [ ] Keep inspect unavailable in this task.
- [ ] E2E tests prove atomic ack/effect, idempotency, no resurrection,
  cross-owner isolation, set add/correct/member-forget/whole-key-forget
  semantics, and no public Memory router/UI resurrection.
- [ ] Review: Stage 2 is complete only after remember/correct/forget/re-remember
  work across all eight governed keys as one explicit semantic-family vertical
  slice; a failing governed key blocks the stage rather than being silently
  omitted.

## Task 9: Stage 3 Semantic Memory Read Engine

**Files:** Create `backend/memory/read_models.py`,
`backend/memory/read_engine.py`, and `backend/memory/postgres_store.py`; add
read-engine unit and RLS integration tests.

```python
class MemoryStore(Protocol):
    def list_storage_scoped(self, request: MemoryReadRequest) -> Sequence[StoredMemoryRow]: ...

class MemoryReadEngine:
    def select(self, request: MemoryReadRequest) -> MemorySelection: ...
```

- [ ] RED truth table rejects deleted, revoked, expired, stale-generation,
  invalid-source, sensitivity-blocked, unresolved-conflict, and foreign-owner rows.
- [ ] Implement exact structured semantic lookup first; no full-text/pgvector.
- [ ] Keep `MemoryStore` limited to physical/tenant predicates;
  `MemoryLifecyclePolicy` owns semantic eligibility.
- [ ] Implement relevance -> response precedence -> conflict exclusion -> ranking
  -> bounded selection/abstention in `MemoryReadEngine`.
- [ ] Fixtures prove unrelated query abstention and conversation override over
  user-scoped soft preference without mutation.
- [ ] Review: RAG imports no Memory module; Memory Read imports no RAG package.

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
to `DialogueStateResolver` only after passing lifecycle/read eligibility.

- [ ] RED fixtures cover deterministic replacement, stale-source rejection,
  conversation deletion, current-turn precedence, and non-duplication with
  ephemeral dialogue state.
- [ ] Implement typed Working Memory and source-consistent replacement; no raw
  transcript blob becomes a durable instruction.
- [ ] Admit only eligible Working Memory to `DialogueStateResolver`; recent turns
  remain the immediate referent source.
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
  with all 20 spec acceptance criteria and ADR 0036–0040.

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

- [x] All 20 specification acceptance criteria have an explicit task/evidence
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
- [x] Explicit and background transaction owners remain distinct.
- [x] Public Chat schema does not expose `TurnDisposition`.
- [x] Stage-1 `ContextPlanner` is shadow-only: proposed `NONE` cannot skip the
  existing RAG baseline. Planner enforcement starts in Task 10 only after a
  conclusive context-mode gate with zero hard-gate false-`NONE` cases.
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

Plan version 0.5 is `Approved`. It retains the v0.4 P0
`semantic-registry-v2` product slice and closes its set-valued semantics:
typed single/set values, immutable union/replacement snapshots, deterministic
member-forget behavior, fail-closed contradictory relation output, and an
explicit all-eight-key Stage-2 gate. This remains inside the approved Semantic
Memory family and the spec's evaluated-vertical-slice rule; no ADR authority
boundary changes. Architecture v0.2 and ADR 0036–0040 are approved. The
repository owner approved this exact plan version on 2026-09-13, so staged
implementation is authorized under this plan and repository workflow. Task
checkbox state is execution evidence only; it does not replace task review,
verification, or repository-owner change-set review.
