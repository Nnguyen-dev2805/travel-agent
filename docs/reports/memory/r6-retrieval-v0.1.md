# R6 Memory Retrieval Evaluation Report

- Report: `r6-retrieval-v0.1-20260905T025818Z`
- Dataset: `r6-retrieval-v0.1` v0.1 (benchmark)
- Extractor: `rule-based-v1`; Policy: `policy-v1`
- Eligible examples: 20; invalid: 0; skipped: 0
- Disabled run: `r6-retrieval-v0.1-20260905T025818Z-disabled`; enabled traces: 13
- Result: **PASS**

## Metrics

| Metric | Value | Matched / Total | Threshold |
| --- | --- | --- | --- |
| promotion_precision | 1.0000 | 4 / 4 | >= 0.97 |
| scope_accuracy | 1.0000 | 10 / 10 | >= 0.98 |
| hit_at_5 | 1.0000 | 6 / 6 | >= 0.9 |
| irrelevant_rate | 0.0000 | 0 / 6 | <= 0.1 |
| personalization_win_rate | n/a | 0 / 0 | n/a without judge |
| constraint_delta | n/a | 0 / 0 | n/a without judge |

## Hard Gates

| Gate | Events | Applicable | Passed |
| --- | --- | --- | --- |
| cross_workspace_leakage | 0 | yes | yes |
| cross_user_leakage | 0 | yes | yes |
| secret_durable_promotion | 0 | yes | yes |
| deleted_memory_retrieval | 0 | yes | yes |
| correction_precedence | 0 | yes | yes |

## Mandatory Slices

| Slice | Examples | Matched / Actual | Precision |
| --- | --- | --- | --- |
| ambiguous | 1 | 0 / 0 | n/a |
| correction | 3 | 3 / 3 | 1.0000 |
| cross-scope | 3 | 0 / 0 | n/a |
| deletion | 1 | 0 / 0 | n/a |
| explicit-preference | 1 | 1 / 1 | 1.0000 |
| inferred-preference | 1 | 1 / 1 | 1.0000 |
| relevant-help | 2 | 1 / 1 | 1.0000 |
| secret-like | 2 | 0 / 0 | n/a |
| staleness | 1 | 0 / 0 | n/a |
| transient | 2 | 1 / 1 | 1.0000 |
| user-global | 1 | 1 / 1 | 1.0000 |
| workspace-decision | 2 | 2 / 2 | 1.0000 |

## Per-example Evidence

| Example | Slice | Matched / Expected / Actual | Failures |
| --- | --- | --- | --- |
| `r6p-pref-001` | explicit-preference | 1 / 1 / 1 | — |
| `r6p-constraint-001` | workspace-decision | 1 / 1 / 1 | — |
| `r6p-correction-001` | correction | 1 / 1 / 1 | — |
| `r6p-ambiguous-001` | ambiguous | 0 / 0 / 0 | — |
| `r6p-secret-001` | secret-like | 0 / 0 / 0 | — |
| `r6p-transient-001` | transient | 0 / 0 / 0 | — |
| `r6p-supersede-001` | correction | 1 / 1 / 1 | — |
| `r6r-hit-user-001` | user-global | 1 / 1 / 1 | — |
| `r6r-hit-workspace-001` | workspace-decision | 1 / 1 / 1 | — |
| `r6r-inferred-001` | inferred-preference | 1 / 1 / 1 | — |
| `r6r-episode-001` | transient | 1 / 1 / 1 | — |
| `r6r-correction-001` | correction | 1 / 1 / 1 | — |
| `r6r-deleted-001` | deletion | 0 / 0 / 0 | — |
| `r6r-stale-001` | staleness | 0 / 0 / 0 | — |
| `r6r-cross-ws-001` | cross-scope | 0 / 0 / 0 | — |
| `r6r-cross-conv-001` | cross-scope | 0 / 0 / 0 | — |
| `r6r-cross-user-001` | cross-scope | 0 / 0 / 0 | — |
| `r6r-secret-store-001` | secret-like | 0 / 0 / 0 | — |
| `r6r-no-memory-001` | relevant-help | 0 / 0 / 0 | — |
| `r6r-multi-001` | relevant-help | 1 / 1 / 1 | — |

## Notes

- R6 retrieval report: promotion, scope, retrieval, and lifecycle gates are measured end to end; answer-quality fields stay INCONCLUSIVE without a provider-backed judge, per the limitation accepted at R6 approval time.
- Cross-user isolation is measured by the local owner label, not authenticated identity, per the open R6/R9 ordering problem.
