# ADR 0013: Model-assisted Extraction and Deterministic Resolution

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-07 |
| Decision owners | Repository owner |
| Scope | Candidate extraction, semantic relationship classification, write policy, and conflict mutation authority |
| Governing spec | [Basic Semantic Memory Write Pipeline Design](../specs/2026-09-07-basic-semantic-memory-write-pipeline-design.md), version 0.1 (Approved) |
| Superseded ADR | [ADR 0006](./0006-shadow-memory-candidate-store-and-policy-boundary.md) and correction/promotion rule 9 of [ADR 0007](./0007-feature-gated-memory-retrieval-and-context-boundary.md) for the V2 write path; legacy behavior remains compatibility evidence until migration |
| Superseded by | None |

## Context

Rules alone do not cover bilingual paraphrase and temporal language, while an
LLM that owns CRUD can make non-reproducible destructive mutations. The current
correction policy has no canonical key and may suppress unrelated same-scope
records.

## Decision

Use deterministic eligibility and secret filtering, then a strict structured
`MemoryExtractionModel` for candidate extraction. Use deterministic normalized
comparison first and a bounded model classifier only for unresolved semantic
relationships. The classifier returns one closed relation value and never a
database operation.

A deterministic resolver applies registry cardinality, authority, scope,
condition, effective time, and lifecycle rules to produce a typed
`MemoryChangeSet`. Uncertain or invalid relations become `PENDING_CONFLICT` and
cause no destructive mutation. Background extraction remains shadow-only in
the focused scope.

## Alternatives

### Rules only

Cheap and reproducible but produces rule explosion and weak bilingual semantic
coverage. Retained as deterministic guards, not the complete extractor.

### Model-owned ADD/UPDATE/DELETE

Flexible but gives untrusted, version-sensitive output destructive authority.
Rejected.

### Hybrid semantic classification and deterministic mutation

Adds adapters and evaluation surfaces but preserves language capability and
testable lifecycle authority. Selected.

## Consequences

### Positive

1. Model changes cannot silently redefine authorization or lifecycle rules.
2. Conflict behavior is testable from pure domain inputs.
3. Paraphrase and temporal language can be handled without using text as
   identity.

### Negative

1. Extraction and relation classification need separate datasets and versions.
2. One bounded repair may add cost.
3. Uncertain cases remain pending instead of maximizing recall.

## Migration

Introduce the V2 path behind independent explicit-write and background-shadow
gates. Preserve the legacy extractor as compatibility evidence until the new
path passes the focused protocol.

## Validation

Measure bilingual candidate precision/recall, key/value accuracy, relation
confusion, deterministic resolver truth tables, invalid-output behavior, model
outage degradation, and zero background promotion.

## References

1. Governing focused specification.
2. [ADR 0006](./0006-shadow-memory-candidate-store-and-policy-boundary.md).
3. [ADR 0007](./0007-feature-gated-memory-retrieval-and-context-boundary.md).
