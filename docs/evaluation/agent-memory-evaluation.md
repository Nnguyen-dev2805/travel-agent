# Agent Memory Evaluation

Canonical staged evaluation record for the Agent Memory target architecture.
Tasks 11–16 extend this artifact rather than creating parallel reports
(`plan v0.8`, evaluation task group).

**Governing spec:** [Agent Memory Target Architecture](../specs/2026-09-12-agent-memory-target-architecture-design.md) v0.4 (Approved 2026-09-13)
**Governing plan:** [Agent Memory Target Architecture Implementation](../plans/2026-09-12-agent-memory-target-architecture-implementation.md) v0.8 (Approved 2026-09-13)
**Evaluation code:** `backend/memory/write_pipeline/evaluation/stage1_metrics.py`
**Last run:** 2026-09-13, Stage 1 (Task 4)

---

## Component Maturity Register

This register records delivery and evidence maturity; it does **not** override
the approved specification, implementation plan, or ADRs. Update the affected
row in the same task that materially changes a component or its evaluation
status.

Three states must stay separate:

- `IMPLEMENTED` means the component exists and its scoped implementation checks
  pass; it does not imply semantic quality has been proven.
- `VALIDATED` means the required quality claim has conclusive evidence from the
  governed evaluation path, not only unit tests or ad-hoc examples.
- `ENFORCEMENT_READY` means the approved promotion gate is satisfied and the
  component may exercise the authority named by the architecture.

| Component | Implementation | Validation | Runtime authority now | Known limitations / target | Revisit or promotion condition |
| --- | --- | --- | --- | --- | --- |
| `DialogueStateResolver` | `IMPLEMENTED` | Unit-verified; no separate quality gate required yet | Authoritative only for the bounded structural recent-turn snapshot | Stage 1 is recent-turn-only and deliberately contributes no semantic interpretation. Working Memory becomes an additional governed input in the later stage defined by the spec. | Revisit when Working Memory read/use becomes available; preserve the structural-vs-semantic boundary. |
| `TurnUnderstanding` | `IMPLEMENTED` baseline | `PARTIAL`; focused tests exist, but no approved Stage-1 fixture set exists | Provides typed semantics to routing; **cannot** authorize durable mutation by itself | Current implementation is a deterministic/rule-based Stage-1 baseline. Known semantic edge cases remain around reported/embedded memory phrases and distinguishing short clarification replies from unrelated short topic shifts. Target remains the approved hybrid resolution order: deterministic safety/high-precision rules, bounded structured model classification when unresolved, closed-schema validation, deterministic final policy. | After the end-to-end Memory path exists, benchmark rule-only vs structured-model vs hybrid understanding on an approved dataset before making a production-quality semantic claim. |
| `ExplicitIntentGate` | `IMPLEMENTED` | Unit-verified; hard-gate dataset still missing | Authoritative guard for whether an interpreted explicit intent may proceed; Stage 1 has no Memory mutation path | Deterministic corroboration remains mandatory even if `TurnUnderstanding` later gains a semantic model. Model/classifier output alone never grants durable authority. | Re-evaluate on the approved explicit-intent set and the controlled explicit Memory vertical slice before durable write rollout. |
| `ActionRouter` | `IMPLEMENTED` | Unit-verified | Authoritative for Stage-1 turn routing only | Explicit Memory execution is not present yet; inspect returns the controlled unavailable/incomplete outcome defined for this stage. | Revisit as the explicit write path and later read/use paths are introduced; downstream code must depend on typed outcomes, not on `TurnUnderstanding` heuristics. |
| `ContextPlanner` | `IMPLEMENTED` shadow | `INCONCLUSIVE` | `SHADOW_ONLY`; effective normal-query execution remains the existing `RAG_ONLY` baseline | Stage 1 proposals are evaluation evidence only. No approved context-mode dataset exists, so planner quality has not been proven. | Task 10 plus a conclusive owner-approved grounding set with zero false-`NONE` before authoritative planner execution. |
| Stage-1 evaluation harness | `IMPLEMENTED` with known blockers | `INCONCLUSIVE` | No rollout/promotion authority while evidence is inconclusive | The trust root is fixed to the governed manifest path, but manifest-schema hardening remains required before this harness can safely open a gate: reject duplicate IDs inside the manifest, require every grounding-required ID to belong to `fixture_ids`, and require correctly typed/validated approval metadata. | Fix the schema blockers, add an owner-approved Stage-1 fixture set, then run the full governed metrics before using the result for promotion. |
| `SourceHandling` (Task 5) | `IMPLEMENTED` | Unit-verified; no quality gate is defined for this component yet, and none is claimed | **None.** Stage 1 proposals grant nothing, no `SourceHandlingRecord` is persisted, and the fail-closed gate has no runtime caller holding a record | Proposals are non-authoritative by construction: they carry no `source_outbox_id`, so they cannot be bound to a source event or consumed. Stage-1 orchestration emits only three of the four reasons — `SENSITIVE_BLOCKED` is covered by the pure reason-mapping tests but is unreachable until the stage that owns prohibited-content detection, because reaching it would mean importing the write pipeline's detector into orchestration. `EXPLICIT_INSPECT` is blocked under `EXPLICIT_ACTION`: inspection mutates nothing, but it is still an explicit Memory command, and the rule is about a source already *handled* explicitly. | Task 6 (persistence, `(source_outbox_id, family)` binding) and Task 11 (first real consumer). The gate must then be re-exercised against records read back from storage, not only against constructed ones — an unreadable record and an absent one must both still deny. |

The maintenance rule is intentionally strict: **implemented != validated !=
enforcement-ready**. Known blockers are recorded as blockers, not converted into
`PASS` by schedule pressure or by the existence of unit tests.

## 1. How to read this record

`spec:915` sets the rule that governs every table below: **missing required
evidence is `INCONCLUSIVE`, never `PASS`**. A metric that cannot be computed is
recorded as `—` with a stated reason, not as `0`. An absent number silently read
as zero is how a rollout gate gets satisfied by having no data.

A gate is `PASS` only when it is `CONCLUSIVE` and its threshold is met. Two
states are therefore distinct and must not be conflated:

| State | Meaning |
| --- | --- |
| `CONCLUSIVE` | The metric was computed from an approved fixture set. |
| `INCONCLUSIVE` | The metric could not be computed: no fixtures, or no fixture of the required class. Enforcement stays off. |

## 2. Stage 1 — Understanding and Action

Required by `spec:873-875` (intent precision/recall, durable-action
false-positive rate, clarification correctness) and `plan v0.8` Task 4
(context-mode evaluation, false-`NONE` rate).

**Dataset identity:** *none approved.* There is no Stage-1 agent-memory fixture
set on disk. `docs/evaluation/fixtures/` contains `memory/`, `ops/`, `planner/`
and `security/` sets from earlier milestones; none of them is an approved
grounding-required set for this stage, and none has been adopted here.

| Metric | Definition | Result | Gate |
| --- | --- | --- | --- |
| Interaction-mode accuracy | turns whose observed mode **exactly equals** the expected mode ÷ all evaluated turns | — | `INCONCLUSIVE` |
| Intent precision | durable actions **exactly correct** ÷ durable actions proposed | — | `INCONCLUSIVE` |
| Intent recall | durable actions **exactly correct** ÷ durable actions expected | — | `INCONCLUSIVE` |
| Durable-action false-positive rate | durable actions proposed that are **not exactly correct** ÷ durable actions proposed | — | `INCONCLUSIVE` |
| Clarification correctness | turns whose `needs_clarification` flag matched expectation ÷ all evaluated turns | — | `INCONCLUSIVE` |
| Context-mode accuracy | turns whose proposed context mode matched the grounding requirement ÷ all evaluated turns | — | `INCONCLUSIVE` |
| **False-`NONE` rate** | grounding-required queries proposed as `NONE` ÷ all approved grounding-required fixtures | — | **`INCONCLUSIVE`** |

**Correctness is exact, not "both durable".** `expected EXPLICIT_REMEMBER` with
`observed EXPLICIT_FORGET` is a mistake: it counts as neither a true positive nor
an accurate reading, and it counts against the durable-action false-positive
rate. Scoring it as correct was a defect of the first version of this harness.

**A set must be approved, and the trust root is fixed.** The metrics are bound to
`APPROVED_MANIFEST_PATH` — `docs/evaluation/fixtures/agent-memory/stage1-manifest.json`
— and `compute_stage1_metrics` takes **no manifest argument**, so there is nothing
for a caller to substitute. The manifest must carry an explicit approval record
(`approved_by`, `approved_on`); evaluated fixture IDs must match the manifest's
fixture-ID set exactly, and duplicate IDs in the evaluated examples are refused.
The manifest's `grounding_required_fixture_ids` — not a per-example flag — define
the false-`NONE` denominator. The set must also meet
`MIN_APPROVED_GROUNDING_FIXTURES` (20).

This binding is not yet sufficient to call the harness promotion-ready. The
current loader still needs fail-closed schema validation for duplicate IDs inside
the manifest itself, grounding IDs that are not members of `fixture_ids`, and the
type/format of approval metadata. These are tracked as explicit blockers in the
Component Maturity Register above.

Two earlier versions were insufficient. The first accepted an object the caller
built, so declaring a set was treated as being the set. The second hashed the file
but still accepted a caller-supplied **path**, so a manifest at
`/tmp/totally-unapproved.json` concluded the gate. Having *a* manifest is not the
same as having an *approved* one, and membership compared sets, so 21 examples
with one repeated ID satisfied a 20-ID manifest.

**Recorded run (2026-09-13):**

```text
APPROVED_MANIFEST_PATH
  = docs/evaluation/fixtures/agent-memory/stage1-manifest.json
  exists: False

compute_stage1_metrics([20 perfect ad-hoc examples])
  state = inconclusive
  reason = no approved fixture manifest is present at <governed path>, so these
           examples are ad-hoc evidence and cannot conclude the gate
  planner_enforcement_permitted = False

# a manifest written to /tmp and given to the previous API
compute_stage1_metrics([20 matching examples])     # no manifest argument exists
  state = inconclusive                             # the /tmp file is never read
  planner_enforcement_permitted = False
```

Two `None` semantics are deliberate and worth stating, because both would
otherwise be reported as a misleading number:

- **A rate is `None` when its denominator is empty.** Precision over zero
  predicted positives is undefined: `0.0` would read as total failure and `1.0`
  as perfection. Neither is true, so the record says neither.
- **A metric is `None` when the whole set is inconclusive**, even if some subset
  could be computed. Partial numbers invite a partial conclusion.

## 3. The planner rollout gate

`plan v0.8` Task 4 makes the false-`NONE` gate mandatory:

> The hard gate requires zero false-`NONE` on a conclusive approved set before
> planner enforcement may be enabled. While the gate is `INCONCLUSIVE` or
> failing, `CONTEXT_PLANNER_ENFORCEMENT_ENABLED=False` remains mandatory.

| Condition | Status |
| --- | --- |
| Conclusive approved grounding-required fixture set | **Not met** — no such set exists |
| False-`NONE` rate on that set | **Not computable** |
| `planner_enforcement_permitted` | **`False`** |
| `CONTEXT_PLANNER_ENFORCEMENT_ENABLED` | `False` (default, and mandatory here) |

`planner_enforcement_permitted` is a conjunction — conclusive **and** zero
false-`NONE` — so an inconclusive set yields `False` rather than a default
approval. Enabling enforcement requires an owner-approved fixture set that makes
the gate conclusive; that is Task 10, not Task 4.

### The flag is wired, and `effective` says what actually executes

`CONTEXT_PLANNER_ENFORCEMENT_ENABLED` is declared, defaults to `False`, and is
read by production: `RuntimeContainer.conversation_orchestrator` passes it to the
injected `ContextPlanner`. The orchestrator itself may not import `backend.app`
(an existing dependency-boundary test forbids it), which is why the planner is
injected rather than read in place.

The two planner properties mean different things, and the distinction is the
contract:

| Property | Meaning |
| --- | --- |
| `enforcement_requested` | the configured rollout value, as passed by the composition root |
| `enforcement_enabled` | whether authoritative planner execution is **active** — always `False` in Stage 1 |

`ContextPlan.effective` describes what will **actually execute**. Stage 1's
orchestrator always runs the RAG baseline and never consults the plan to decide
whether to retrieve, so a plan claiming `effective = NONE` would describe
execution that does not happen. `effective` is therefore the RAG baseline for
every reading, and `is_shadow` is always `True`. Requesting enforcement is
recorded; it cannot make the contract untrue. Authoritative planner execution
remains Task 10, gated on a conclusive zero-false-`NONE` set.

## 4. Stage-1 execution invariant (not a metric)

Separately from the metrics, Stage 1 must not change normal answer-source
execution. This is verified by test, not by a rate:

| Invariant | Evidence |
| --- | --- |
| A planner proposal of `NONE` still executes the existing RAG generation path | `backend/tests/unit/test_conversation_orchestrator.py::test_a_stage_one_none_proposal_still_executes_the_rag_generation_path` |
| The effective mode stays the `RAG_ONLY` baseline while enforcement is off | `backend/tests/unit/orchestration/test_context_planner.py::test_enforcement_off_keeps_the_baseline_for_every_reading` |
| `TurnUnderstanding` owns semantic interpretation, not `DialogueStateResolver` | `backend/tests/unit/orchestration/test_turn_understanding.py::test_the_same_cue_resolves_once_prior_context_exists` and `::test_the_resolver_contributes_no_semantics_of_its_own` |
| Model output alone cannot authorize a durable action | `backend/tests/unit/orchestration/test_action_router.py::test_only_the_deterministic_reason_authorizes` |
| A question or mention never authorizes a durable action | `backend/tests/unit/orchestration/test_turn_understanding.py::test_a_question_or_mention_never_authorizes_a_durable_action` |
| `explicit_inspect` returns a controlled unavailable outcome, not an ordinary RAG answer | `backend/tests/unit/test_conversation_orchestrator.py::test_inspect_returns_a_controlled_unavailable_outcome` |
| An internal dialogue-state invariant failure is not a user-facing 422 | `backend/tests/unit/test_conversation_orchestrator.py::test_a_dialogue_state_invariant_failure_is_not_a_user_validation_error` |
| The recent-dialogue window never exceeds `DEFAULT_HISTORY_LIMIT` | `backend/tests/unit/test_conversation_service.py::test_recent_messages_never_exceeds_the_governed_window` |
| The rollout flag reaches the planner from the composition root | `backend/tests/unit/test_context_planner_wiring.py::test_the_composition_root_derives_the_planner_from_the_setting` |
| A statement *about* memory never authorizes a durable action | `backend/tests/unit/orchestration/test_turn_understanding.py::test_a_statement_about_memory_is_not_a_speech_act` |
| The active goal is the original request, not the latest clarification answer | `backend/tests/unit/orchestration/test_turn_understanding.py::test_the_current_goal_is_the_original_request_not_the_last_answer` |
| `effective` always matches what executes | `backend/tests/unit/orchestration/test_context_planner.py::test_the_effective_mode_always_matches_what_executes` |
| The approved set is bound to the governed manifest path, not a caller object or caller path | `backend/tests/unit/memory_write_pipeline/test_stage1_metrics.py::test_the_metrics_take_no_manifest_argument` and `::test_a_caller_supplied_path_is_not_part_of_the_api` |
| The removed-subsystem guard catches `from backend import planner` | `backend/tests/unit/test_runtime_container.py::test_a_forbidden_submodule_imported_by_name_is_caught` |
| A comment or noun usage of a memory verb is not a command | `backend/tests/unit/orchestration/test_turn_understanding.py::test_a_bare_verb_at_the_start_of_a_comment_is_not_a_command` |
| A topic change is not a clarification answer, and it replaces the goal | `backend/tests/unit/orchestration/test_turn_understanding.py::test_a_new_question_is_not_a_clarification_answer` |
| The approved manifest's trust root is fixed, not a caller argument | `backend/tests/unit/memory_write_pipeline/test_stage1_metrics.py::test_the_metrics_take_no_manifest_argument` |
| Duplicate fixture IDs are refused | `backend/tests/unit/memory_write_pipeline/test_stage1_metrics.py::test_duplicate_fixture_ids_are_rejected` |

## 5. Zero-tolerance failures relevant to this stage

From `spec:901-914`. Stage 1 can violate these, so they are listed with their
current status rather than assumed safe:

| # | Failure | Status |
| --- | --- | --- |
| 3 | Classifier-only durable mutation | **Prevented by construction** — `ExplicitIntentGate` authorizes only a reading carrying the deterministic reason, and every other reason code is denied. No Stage-1 path performs a Memory mutation at all. |
| 11 | Registry-invalid model output becoming durable explicit Memory | **Not reachable in Stage 1** — no model call is made and no write path exists. |
| 1 | Cross-owner mutation/selection | **Not evaluated here** — owned by the conversation layer's own isolation tests. |

## 6. What this record does not yet cover

- No approved Stage-1 fixture set, so no metric above is conclusive. Creating
  one is a prerequisite for enabling planner enforcement.
- Episodic Memory (Stage 5, Task 12) is evaluated in section 8; its gate is
  `INCONCLUSIVE` because the production authority producer and read/use
  composition are not implemented. Working Memory (Task 13) is not evaluated here.
- The context-mode evaluation currently measures the *proposal* against the
  grounding requirement. It does not yet measure answer quality under each mode,
  because only `RAG_ONLY` is reachable.

## 7. Stage 4 — Background Semantic Formation, Activation, and Outbox Bound

Required by `spec:876-879` and `plan v0.18` Task 11.

| Component | Implementation | Validation | Runtime authority now | Known limitations / target | Revisit or promotion condition |
| --- | --- | --- | --- | --- | --- |
| `MemoryFormationEngine` | `IMPLEMENTED` | Unit & live PostgreSQL verified | Authoritative for background formation from positive source handling | Evaluates positive handling, pre-model secret scan, 8-key extraction, and lifecycle eligibility at formation stage. Emits candidates. | Conclusive evaluation dataset required before enabling active inference. |
| `MemoryActivationPolicy` | `IMPLEMENTED` | Unit & live PostgreSQL verified | `SHADOW_ONLY` while `MEMORY_INFERRED_ACTIVATION_ENABLED=false` | Pure deterministic policy enforcing conversation-scope (>= 2 agreeing turns) and user-scope (>= 3 evidence across >= 2 conversations) promotion thresholds without direct DB queries. | Active inference requires a conclusive passing evaluation per semantic key/type; missing/skipped evidence is `INCONCLUSIVE`. Passing one key (e.g. `hotel_atmosphere`) does not authorize `budget_level` or any other registry-v2 key. |
| Outbox Maintenance Pass | `IMPLEMENTED` | Live PostgreSQL verified | Authoritative for bounded outbox pruning | Prunes only `event_type = 'memory.write.committed' AND status = 'pending' AND created_at < cutoff` in batches up to 500 rows. Canonical Memory rows are never deleted. | Monitor outbox backlog signals and prune telemetry in production. |

## 8. Stage 5 — Episodic Memory Vertical Slice

Required by `spec:1036`, `spec:1276-1283`, `ADR 0038:81` and `plan v0.20` Task 12.

| Component | Implementation | Validation | Runtime authority now | Known limitations / target | Revisit or promotion condition |
| --- | --- | --- | --- | --- | --- |
| `EpisodeGrounding` / `EpisodeRefusalReason` | `IMPLEMENTED` | Unit-verified (43 tests) | Refuses formation when actor, event, time or provenance is missing or malformed | Grounding is the family's whole precondition. `event` is a bounded string, not a closed ontology: no universal event vocabulary is introduced before the evaluation says which event types matter. A timezone-naive time is refused, because a naive datetime is a local guess rather than an instant. | Extend the grounding shape only when this gate's extraction evidence names a field the current four cannot carry. |
| `EpisodeFormationEngine` | `IMPLEMENTED` | Unit-verified | Requires a persisted `SourceHandlingRecord(family=EPISODIC, outcome=BACKGROUND_ELIGIBLE)`; a semantic-family record grants nothing | Reuses `RetentionAssignmentPolicy` and `MemoryLifecyclePolicy` rather than duplicating either. `source_validity` and the suppression generation come from the caller's canonical snapshot, not from defaults. | Promotion requires the production authority producer below. |
| Episodic persistence (`memory_episodes`) | `IMPLEMENTED` | Live PostgreSQL verified (15 tests) | `travel_worker` forms and transitions; `travel_app` reads and invalidates | The placeholder table from `20260907_02` was evolved, not replaced. Grounding columns default to `''` and `status` defaults to `shadow` purely for migration safety, so a pre-existing row is ineligible rather than silently grounded. Provenance uniqueness is a real unique index on `(owner_user_id, source_outbox_id, source_message_id)`, so redelivery cannot create a second canonical episode and a replay with different content raises instead of silently keeping the first. `payload` is not backfilled and is not policy authority. | Multi-episode-per-source-message is deliberately not supported: the provenance triple is the idempotency boundary. Revisit only with an approved content-fingerprint contract. |
| `EpisodeActivationPolicy` | `IMPLEMENTED` | Unit-verified; **gate default off** | `SHADOW_ONLY` — one grounded event *may* suffice, but only when the episodic gate is conclusive **and** enabled | Its own policy, not `MemoryActivationPolicy`: the semantic 2-turn/3-evidence thresholds answer "how often has the user said this", and an episode's question is "did this happen". The semantic inferred-activation flag is deliberately **not** an input. | A conclusive passing episodic evaluation for the implemented episode type(s), per type. Passing a semantic key does not authorize episodic activation. |
| `EpisodicReadEngine` | `IMPLEMENTED` | Unit & live PostgreSQL verified | Selects only lifecycle-eligible, non-conflicting, non-invalidated episodes inside an exact typed window; abstains otherwise | Separate typed contract from semantic `MemoryReadRequest`/`SelectedMemory`; an episode is never a fake `canonical_key`. No free-text or fuzzy field: matching on a string is Task 14's retrieval-projection work. Deleted-source evidence is filtered at the governed boundary and never becomes a prompt instruction or citation. | Compose through Context Planner/Arbiter (below) before this reaches generation context. |
| Production episodic authority producer | `IMPLEMENTED` | Live PostgreSQL verified | Authoritative for episodic background formation | The orchestrator writes one outbox event per family and persists the `EPISODIC` / `BACKGROUND_ELIGIBLE` record after `TurnUnderstanding`, bound to the episodic event's own `source_outbox_id` (`plan v0.21`). The record is written after the turn is persisted but before `complete_turn` releases the event, and the worker claims only released events, so authority always exists before episodic model exposure. | Conclusive extraction-quality evidence per episode type before inferred activation. |
| Episodic read/use composition | `IMPLEMENTED` | Unit-verified; live read verified | Episodes enter `GenerationContext` as bounded structured text, appended last | `EpisodeContextComposer` + `ContextArbiter` project only actor/event/time; raw source text never reaches the prompt and an episode is never a citation. Episodes rank below current request, hard constraints and soft preferences. | Rollout flag `MEMORY_EPISODIC_READ_ENABLED` stays default-off until the quality gate is conclusive. |

### Task-12 gate

**Status: `CONCLUSIVE PASS` for the mandatory authority/privacy/correctness
fixtures.** Every mandatory fixture below is green against live PostgreSQL, and the
production authority producer and read/use composition rows above are now
implemented. The per-type *extraction quality* claim remains unmeasured: this
repository has no approved episodic extraction dataset, and this record does not
invent one.

That distinction is deliberate and it is the reason the runtime flag stays off.
The gate that is conclusive is the **safety** gate — the architecture can be relied
on not to form without authority, not to activate on incomplete grounding, not to
leak a deleted source, not to admit an unrelated query, and not to invert
precedence. The gate that is *not* claimed is the **quality** gate: whether the
episodes this slice forms are the ones a user would want remembered. Activation
therefore remains shadow-only, and turning it on needs a governed extraction
dataset of the kind the Stage-1 record is still waiting for.

Mandatory zero-failure fixtures, all currently green:

| # | Failure class | Evidence | Result |
| --- | --- | --- | --- |
| 1 | Formation without positive episodic handling (`UNHANDLED`, semantic-family record, or a blocked episodic outcome) | `unit/memory/test_episodic.py::test_formation_refuses_an_unhandled_source`, `::test_formation_refuses_a_semantic_family_record`, `::test_formation_refuses_a_non_eligible_episodic_outcome[5 cases]`; `integration/test_step3_episodic_authority_e2e.py::test_without_positive_episodic_authority_formation_never_reaches_the_model` | **PASS** (8 cases) — the live case asserts zero model calls |
| 2 | Activation with incomplete grounding (missing actor / event / time / provenance, naive or non-datetime time) | `unit/memory/test_episodic.py::test_a_missing_actor_is_refused`, `::test_a_missing_event_is_refused`, `::test_a_missing_time_is_refused`, `::test_a_timezone_naive_time_is_refused`, `::test_a_non_datetime_time_is_refused`, `::test_missing_provenance_is_refused`, `::test_a_provenance_without_a_source_outbox_identity_is_refused`, `::test_incomplete_grounding_cannot_activate` | **PASS** (8 cases) |
| 3 | Deleted/invalid-source leakage | `integration/test_episodic_vertical_slice.py::test_deleting_a_conversation_invalidates_its_episodes` (+ mutation proof: removing the invalidation statement fails it) | **PASS** |
| 4 | Unrelated-query admission | `unit/memory/test_episodic.py::test_an_unrelated_query_abstains_rather_than_returning_a_near_match`; `integration/test_episodic_vertical_slice.py::test_an_unrelated_window_abstains_over_real_rows` | **PASS** — `NO_ELIGIBLE_EPISODE`, no widening |
| 5 | Precedence inversion | `unit/memory/test_episodic_context.py::test_episodes_are_appended_after_the_memory_block` | **PASS** — episodes are composed last, below soft preferences |
| 6 | Prompt-instruction / citation leakage | `unit/memory/test_episodic_context.py::test_the_composed_block_carries_only_structured_fields`, `::test_an_episode_never_becomes_a_travel_citation`, `::test_an_abstention_adds_nothing_to_the_context` | **PASS** — only actor/event/time reach the prompt; raw source text is absent; episodes are never citations |
| 7 | Stale generation, expired state, unresolved conflict, non-active status at read | `unit/memory/test_episodic.py::test_a_stale_generation_episode_is_not_selected`, `::test_an_expired_episode_is_not_selected`, `::test_an_invalid_source_episode_is_not_selected`, `::test_an_unresolved_conflict_episode_is_not_selected`, `::test_a_non_active_episode_is_not_selected`; `integration/test_episodic_vertical_slice.py::test_a_shadow_episode_is_not_selected` | **PASS** (6 cases) |
| 8 | Duplicate canonical event from redelivery or re-extraction | `integration/test_episodic_vertical_slice.py::test_a_replayed_source_is_idempotent`, `::test_a_replay_with_different_content_is_refused` | **PASS** |
| 9 | Activation while the family/type gate is off or inconclusive | `integration/test_step3_episodic_authority_e2e.py::test_the_worker_runs_the_episodic_branch_and_persists_a_shadow_episode` | **PASS** — persisted `shadow`, never `active`, under two independent denials |

Required PostgreSQL evidence ran without required skips: migration
upgrade/downgrade/upgrade round-trip from `20260915_01` to `20260915_02`, exact
runtime grants for both roles, `FORCE` RLS, cross-owner denial, source-deletion
propagation, idempotency, the full Step-3 release ordering, and the worker's
episodic branch.

**What would make the quality gate conclusive:** an owner-approved episodic
extraction dataset measuring grounding precision and recall for the implemented
episode type(s). Until then inferred episodic activation stays off, and the
authority, privacy, precedence and idempotency guarantees above are what is
actually being claimed.

Required PostgreSQL evidence ran without required skips: migration
upgrade/downgrade/upgrade round-trip from `20260915_01` to `20260915_02`, exact
runtime grants for both roles, `FORCE` RLS, cross-owner denial, source-deletion
propagation, idempotency, and read/use integration.

**What would make this gate conclusive:** a production-reachable episodic
authority producer, episodic composition through Context Planner/Arbiter, and an
owner-approved episodic extraction/grounding dataset with the per-type
extraction quality recorded. Missing or skipped mandatory evidence is
`INCONCLUSIVE`, never `PASS` (`spec:1203`).
