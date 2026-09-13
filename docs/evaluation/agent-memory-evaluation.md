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
| Intent precision | durable actions correctly recognized ÷ durable actions proposed | — | `INCONCLUSIVE` |
| Intent recall | durable actions correctly recognized ÷ durable actions expected | — | `INCONCLUSIVE` |
| Durable-action false-positive rate | durable actions proposed where none was expected ÷ durable actions proposed | — | `INCONCLUSIVE` |
| Clarification correctness | turns whose `needs_clarification` flag matched expectation ÷ all evaluated turns | — | `INCONCLUSIVE` |
| Context-mode accuracy | turns whose proposed context mode matched the grounding requirement ÷ all evaluated turns | — | `INCONCLUSIVE` |
| **False-`NONE` rate** | grounding-required queries proposed as `NONE` ÷ all approved grounding-required fixtures | — | **`INCONCLUSIVE`** |

**Recorded run (2026-09-13):**

```text
compute_stage1_metrics([])
  state                     = inconclusive
  reason                    = no evaluated fixtures were supplied
  evaluated                 = 0
  intent_precision          = None
  intent_recall             = None
  durable_action_false_positive_rate = None
  clarification_correctness = None
  context_mode_accuracy     = None
  false_none_rate           = None
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

### Known gap: the flag is recorded but not yet wired

`CONTEXT_PLANNER_ENFORCEMENT_ENABLED` is declared and defaults to `False`, but
**no production code reads it yet.** `ConversationOrchestrator` may not import
`backend.app` (an existing dependency-boundary test forbids it), so the planner
arrives by constructor injection and defaults to the shadow one. The composition
root — `backend/app/runtime_container.py` — does not pass a planner, and that
file is outside Task 4's declared file list.

The gap is in the safe direction: enforcement cannot turn on by accident, and
`False` is what the gate requires here anyway. Closing it is a one-line change at
the composition root, which should be approved rather than folded into this task.
Until then the flag is an explicit, documented rollout switch rather than an
active one.

## 4. Stage-1 execution invariant (not a metric)

Separately from the metrics, Stage 1 must not change normal answer-source
execution. This is verified by test, not by a rate:

| Invariant | Evidence |
| --- | --- |
| A planner proposal of `NONE` still executes the existing RAG generation path | `backend/tests/unit/test_conversation_orchestrator.py::test_a_stage_one_none_proposal_still_executes_the_rag_generation_path` |
| The effective mode stays the `RAG_ONLY` baseline while enforcement is off | `backend/tests/unit/orchestration/test_context_planner.py::test_enforcement_off_keeps_the_baseline_for_every_reading` |
| `TurnUnderstanding` owns semantic interpretation, not `DialogueStateResolver` | `backend/tests/unit/orchestration/test_turn_understanding.py::test_the_same_cue_resolves_once_prior_context_exists` and `::test_the_resolver_contributes_no_semantics_of_its_own` |
| Model output alone cannot authorize a durable action | `backend/tests/unit/orchestration/test_action_router.py::test_only_the_deterministic_reason_authorizes` |

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
