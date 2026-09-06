# R6 Memory Retrieval Evaluation Report

- Report: `r6-retrieval-v0.2-20260906T055726Z`
- Dataset: `r6-retrieval-v0.2` v0.2 (development)
- Extractor: `rule-based-v1`; Policy: `policy-v1`
- Eligible examples: 9; invalid: 0; skipped: 0
- Disabled run: `r6-retrieval-v0.2-20260906T055726Z-disabled`; enabled traces: 7
- Result: **PASS**

## Metrics

| Metric | Value | Matched / Total | Threshold |
| --- | --- | --- | --- |
| promotion_precision | 1.0000 | 2 / 2 | >= 0.97 |
| scope_accuracy | 1.0000 | 2 / 2 | >= 0.98 |
| hit_at_5 | 1.0000 | 3 / 3 | >= 0.9 |
| irrelevant_rate | 0.0000 | 0 / 3 | <= 0.1 |
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

| Slice | Examples | Matched / Actual | Precision | Hit rate |
| --- | --- | --- | --- | --- |
| cross-scope | 1 | 0 / 0 | n/a | n/a |
| cross-user | 1 | 1 / 1 | 1.0000 | 1.0000 |
| deletion | 3 | 2 / 2 | 1.0000 | n/a |
| explicit-preference | 1 | 1 / 1 | 1.0000 | n/a |
| user-global | 1 | 1 / 1 | 1.0000 | 1.0000 |
| workspace-decision | 2 | 2 / 2 | 1.0000 | 1.0000 |

## Environment

- dirty_working_tree: True
- retrieval.correction_bypass: True
- retrieval.max_selected_default: 5
- retrieval.min_confidence_default: 0.75
- retrieval.tokenizer: unicode-word-lowercase

## Per-example Evidence

| Example | Slice | Matched / Expected / Actual | Failures |
| --- | --- | --- | --- |
| `r6p-pref-001` | explicit-preference | 1 / 1 / 1 | — |
| `r6p-constraint-001` | workspace-decision | 1 / 1 / 1 | — |
| `r6r-hit-user-001` | user-global | 1 / 1 / 1 | — |
| `r6r-hit-workspace-001` | workspace-decision | 1 / 1 / 1 | — |
| `r6r-deleted-001` | deletion | 0 / 0 / 0 | — |
| `r6r-cross-user-001` | cross-scope | 0 / 0 / 0 | — |
| `r6x-own-001` | cross-user | 1 / 1 / 1 | — |
| `r6d-lifecycle-001` | deletion | 1 / 1 / 1 | — |
| `r6d-lifecycle-002` | deletion | 1 / 1 / 1 | — |

## Notes

- R6 retrieval report: promotion, scope, retrieval, and lifecycle gates are measured end to end; answer-quality fields stay INCONCLUSIVE without a provider-backed judge, per the limitation accepted at R6 approval time.
- The disabled branch executes the gate-off path over the identical query set, which selects nothing by definition; the paired comparison is enabled selections versus that empty baseline. No answer is generated on either branch without a provider.
- R9 refreshed evidence: cross-user isolation is measured between token-registry identities with authentication enabled, and deleted-memory retrieval is measured after confirmed deletion through the ordered privacy flow. The R6 v0.1 label-based limitation no longer applies to this suite; quality metrics cover carried cases only, not a full re-run.
