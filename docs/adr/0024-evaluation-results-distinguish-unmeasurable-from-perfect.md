# ADR 0024: Evaluation Results Distinguish Unmeasurable from Perfect

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-11 |
| Decision owners | Repository owner |
| Scope | Result semantics for both offline evaluation harnesses and the exit contract of their comparison command. Bounded by `backend/rag/evaluation/` and `backend/memory/write_pipeline/evaluation/`. |
| Governing spec | `docs/specs/2026-09-11-runtime-integrity-remediation-design.md` v0.1 (Status: Approved 2026-09-11) |
| Superseded ADR | Not applicable |
| Superseded by | Not applicable |

## Context

ADR 0001 separated online RAG execution from config-driven evaluation, and ADR 0016 established focused memory-write evaluation with hard gates and rollout thresholds. Both assume the harness can report a failure. It cannot.

Three verified defects, read directly on 2026-09-11:

**A metric with no denominator scores a perfect 1.0.** Every metric in `backend/memory/write_pipeline/evaluation/runner.py:620-727` uses the form `x / y if y > 0 else 1.0`. When nothing was measured — no expected candidates, no sensitivity cases, no scope cases — the metric reports `1.0000` and `passed=True`. Running the safety, quality and combined suites in-process yields all eleven metrics at exactly `1.0000`, including `sensitivity_accuracy` and `scope_hard_accuracy`, both computed from a zero denominator. The published result is `PASS` and carries no information.

**A metric is hardcoded.** `relationship_correct` is set to `1.0` with the comment "Relationship classification matches expected_rel", but no comparison is performed (`:431`). The metric cannot fail.

**Two hard gates cannot fire.** `partial_transaction_state` has a bare `pass` body (`:485-487`). `cross_owner_access` filters `own_records` to the candidate's own owner and then tests whether that filtered list contains a foreign owner (`:412`, `:419`), so the predicate is structurally false. Both always report zero violations.

**A comparison gate cannot fail a build.** `cmd_compare` returns `0` unconditionally after writing its report (`backend/rag/evaluation/cli.py:125`); only an exception yields a non-zero status. Reproduced by feeding it an `INVALID` candidate: the report records `state=INVALID` and `main()` still returns `0`. A regression therefore never fails CI.

**And the comparison has nothing to compare.** `CurrentRuntimeAdapter` and `StructuredRuntimeAdapter` both execute the same `KnowledgeRetriever` and `LLMGenerator` (`backend/rag/evaluation/runtime.py:61-72`, `:146-153`). The two shipped runs have byte-identical aggregate metrics (hit@5 = 0.24) and a `comparison.json` reporting `PASS` with every paired delta at `0.0`. The A/B gate compares a code path to itself.

A durable decision is required because these are not four independent bugs. They are one design position: *the harness treats the absence of a measurement as a measurement of success*. Correcting that changes the meaning of every published number, and any consumer of those numbers — a CI gate, a rollout threshold, a future spec — depends on the semantics. Changing semantics without recording the decision would make historical results uninterpretable.

## Decision

**The absence of a measurement is not a measurement.**

1. **A metric with no denominator reports `not_measured`.** `MetricAccounting.value` becomes `float | None`. A zero denominator yields `value = None`, and `passed` is true only when `value is not None and value >= threshold`. A metric that cannot be computed must never report a passing number.

2. **A metric that is not implemented must say so.** A metric whose comparison is not performed reports `value = None` with a `not_measured` reason code, rather than a hardcoded value. An honestly absent metric is worth more than a falsely perfect one.

3. **A hard gate must be able to fire.** A gate is only a gate if a test demonstrates it firing. A gate whose body is a no-op, or whose predicate is structurally unsatisfiable, is removed or implemented — never left reporting zero violations.

4. **A comparison command returns a non-zero exit status on a failed or invalid result.** `pass` → 0, `inconclusive` → 2, `fail` → 2, `invalid` → 3, unexpected exception → 1. A regression must fail a build.

5. **A comparison between a pipeline and itself is refused.** Each adapter declares a `pipeline_id`, and a comparison whose baseline and candidate share one raises rather than publishing a null result as evidence.

**Explicitly out of scope of this decision.** Which metrics should exist, what their thresholds should be, and whether the structured adapter should implement a genuinely different retrieval path. Those are evaluation design questions for the harness owners, not consequences of this decision.

## Alternatives

### Report a perfect score for an unmeasured metric

**Benefits.** No change to the result schema. Existing published results remain interpretable under their original semantics. No consumer of the harness needs updating.

**Costs.** The harness cannot detect a regression in any metric whose denominator is zero, which today is most of them. `PASS` carries no information, so every rollout threshold in ADR 0016 is unenforced. A reader cannot distinguish a genuinely clean run from a harness that measured nothing.

**Not selected.** This is the current behaviour and the reason the decision is required. Retaining it means the evaluation protocol is documentation rather than a control.

### Treat an unmeasured metric as a failure

**Benefits.** Unambiguous. Nothing can be published as a pass without a measurement, so the harness fails closed.

**Costs.** A dataset that legitimately contains no case for a given slice — a small fixture, a suite that does not exercise sensitivity — would report `FAIL` despite nothing being wrong. The result would be indistinguishable from a real regression, so operators would learn to ignore the harness.

**Not selected.** Conflating "not measured" with "measured and failed" replaces a false pass with a false failure, and false failures train operators to ignore the signal.

### Raise an exception on a zero denominator

**Benefits.** Impossible to ignore. A malformed dataset stops the run immediately.

**Costs.** A partially applicable suite becomes unrunnable. The memory harness runs three suites over one fixture set; some metrics legitimately do not apply to some suites. The harness would have to be restructured before any result could be produced.

**Not selected.** It makes the harness brittle in exchange for a guarantee that `not_measured` already provides, without blocking the run.

## Consequences

### Positive

1. A published `PASS` means something: every metric that reported a number met its threshold, and every metric that did not is named.
2. A regression fails CI, so the comparison gate becomes a control rather than a report.
3. The two structurally inert gates become real or are removed, so the safety suite's "zero violations" claim becomes evidence.
4. A self-comparison is refused, so the harness cannot publish a null result as an A/B finding.

### Negative

1. **Previously published results become untrustworthy.** Every `PASS` produced before this change must be marked as such rather than reinterpreted. This is a communication obligation, not a technical one, and it is the most likely source of confusion.
2. **CI will start failing on runs that previously passed.** That is the intent, but it must be announced, and a known-good baseline must be established before the gate is relied upon.
3. Every consumer of `MetricAccounting` must handle `None`. A caller that assumes a float will break, which is the point but is also work.
4. A suite that legitimately measures nothing will now be visibly hollow. That is a finding, not a defect, but it will require fixture work before the memory harness can report a meaningful pass.
5. The refusal of a same-`pipeline_id` comparison invalidates the currently shipped `comparison.json`, which will need either a real treatment or an explicit non-informative label.

## Migration

**Sequence.** Land the metric semantics, the gate implementations, and the exit-code mapping together — a partial change would leave the harness reporting a mixture of old and new semantics. Then announce the invalidation of previously published results. Then re-baseline, which is governed by the companion specification and must not happen before this change, because the re-baseline would otherwise be measured by the defective harness.

**Compatibility.** No API contract changes; these are offline tools. The result artifact schema gains a nullable `value` field and new reason codes, so a consumer that requires a number must be updated.

**Rollback boundary.** Reverting restores a harness that reports perfect scores for unmeasured quantities. If a rollback is required, the previously published results must be marked untrustworthy rather than reinstated — reverting the code does not make the old numbers meaningful.

## Validation

1. A test asserts a zero denominator yields `value is None` and `passed is False`.
2. A test asserts `relationship_accuracy` is computed from the fixture rather than hardcoded.
3. A test asserts the cross-owner gate fires when a foreign record reaches the resolver.
4. A test asserts the partial-transaction gate fires when a write is not rolled back.
5. A test asserts `compare` exits non-zero for an `invalid` result and for a `fail` result.
6. A test asserts the two adapters declare distinct `pipeline_id` values.
7. A run of the memory suites produces at least one non-`1.0` metric, or reports `not_measured`. A report in which every metric is still exactly `1.0` means this decision was not implemented.
8. The before/after metric table is recorded as evidence.

## References

1. Governing spec: `docs/specs/2026-09-11-runtime-integrity-remediation-design.md` v0.1
2. Implementation plan: `docs/plans/2026-09-11-runtime-integrity-remediation-implementation.md`, Task 5
3. Review evidence: `.workbuddy-ai/reports/code-review-2026-09-11.md` (git-ignored local artifact), findings C10, C11, C12
4. Related ADRs: 0001 (separate online RAG execution from config-driven evaluation), 0016 (focused memory write evaluation and rollout)
5. Evaluation protocols: `docs/evaluation/rag-evaluation.md`, `docs/evaluation/memory-write-pipeline-evaluation.md`
