# Agent Memory Evaluation

Canonical staged evaluation record for the Agent Memory target architecture.
Tasks 11–16 extend this artifact rather than creating parallel reports
(`plan v0.7:482-488`).

**Governing spec:** [Agent Memory Target Architecture](../specs/2026-09-12-agent-memory-target-architecture-design.md) v0.3 (Approved 2026-09-13)
**Governing plan:** [Agent Memory Target Architecture Implementation](../plans/2026-09-12-agent-memory-target-architecture-implementation.md) v0.7 (Approved 2026-09-13)
**Evaluation code:** `backend/memory/write_pipeline/evaluation/stage1_metrics.py`
**Last run:** 2026-09-13, Stage 1 (Task 4)

---

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
false-positive rate, clarification correctness) and `plan v0.7:482-493`
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
(`approved_by`, `approved_on`), its fixture IDs must equal the evaluated examples
exactly **with no duplicates**, and its `grounding_required_fixture_ids` — not a
per-example flag — define the false-`NONE` denominator. The set must also meet
`MIN_APPROVED_GROUNDING_FIXTURES` (20).

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

`plan v0.7:489-493` makes the false-`NONE` gate mandatory:

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
| The approved set is bound to a manifest file, not a caller object | `backend/tests/unit/memory_write_pipeline/test_stage1_metrics.py::test_a_fabricated_manifest_fails_the_digest_check` |
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
- Formation, consolidation/lifecycle, read/use and runtime layers
  (`spec:876-879`) belong to Tasks 6–16 and are not evaluated here.
- The context-mode evaluation currently measures the *proposal* against the
  grounding requirement. It does not yet measure answer quality under each mode,
  because only `RAG_ONLY` is reachable.
