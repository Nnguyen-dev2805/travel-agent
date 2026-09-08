# ADR 0016: Focused Memory Write Evaluation and Rollout

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-07 |
| Decision owners | Repository owner |
| Scope | First-key write evaluation, hard gates, result states, and rollout authority |
| Governing spec | [Basic Semantic Memory Write Pipeline Design](../specs/2026-09-07-basic-semantic-memory-write-pipeline-design.md), version 0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

Existing R5/R6 reports measure useful mechanics but do not cover the new
canonical key, immutable decisions, confirmed commands, PostgreSQL atomicity,
idempotent background delivery, or deletion-epoch safety. A single average
score could hide persistent privacy and correctness failures.

## Decision

Adopt the focused protocol in
`docs/evaluation/memory-write-pipeline-evaluation.md`. Evaluate domain, model
extraction, policy, persistence, trigger/runtime, security/privacy, and
operations separately. Use `PASS`, `FAIL`, `INCONCLUSIVE`, and `INVALID` result
states. Hard gates are non-compensating.

Normal-chat background output remains shadow-only. The first valid development
run establishes measurement behavior, not inferred auto-promotion authority.
Any later auto-promotion requires a separate approved specification, frozen
benchmark/safety evidence, and comparison against shadow behavior.

## Alternatives

### Reuse only the existing R5/R6 report

Cheaper but cannot prove new identity, confirmation, transaction, worker, or
deletion semantics. Rejected.

### One blended memory-quality score

Easy to rank but permits quality gains to compensate for isolation or secret
failures. Rejected.

### Layered protocol with zero-tolerance hard gates

Requires more fixtures and reports but identifies failure ownership and keeps
safety non-compensating. Selected.

## Consequences

### Positive

1. Every spec requirement maps to a scenario, metric, hard gate, or review.
2. Background auto-promotion cannot arrive through implementation drift.
3. Failures can be localized to extraction, policy, resolution, persistence, or
   runtime.

### Negative

1. The first slice requires a dedicated dataset and harness.
2. Provider-backed evaluation adds cost and reproducibility obligations.
3. Small samples may produce `INCONCLUSIVE`, delaying rollout.

## Migration

Keep current R5/R6 reports as compatibility evidence. Add the focused protocol
and dataset under new identities; never rewrite historical reports to appear as
V2 evidence.

## Validation

Run all focused scenarios, mandatory slices, hard gates, migration tests,
failure injection, full backend/frontend verification, and exact change-set
review before repository-owner promotion.

## References

1. Governing focused specification.
2. [Focused evaluation protocol](../evaluation/memory-write-pipeline-evaluation.md).
3. [Memory Evaluation Protocol](../evaluation/memory-evaluation.md).
