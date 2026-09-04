# R5 Shadow Memory Evaluation Report

- Report: `r5-shadow-v0.1-20260904T105938Z`
- Dataset: `r5-shadow-v0.1` v0.1 (benchmark)
- Extractor: `rule-based-v1`; Policy: `policy-v1`
- Eligible examples: 13; invalid: 0; skipped: 0
- Result: **PASS**

## Metrics

| Metric | Value | Matched / Total | Threshold |
| --- | --- | --- | --- |
| extraction_precision | 1.0000 | 13 / 13 | >= 0.95 |
| extraction_recall | 1.0000 | 13 / 13 | >= 0.9 |
| scope_accuracy | 1.0000 | 13 / 13 | >= 0.98 |

## Hard Gates

| Gate | Events | Applicable | Passed |
| --- | --- | --- | --- |
| cross_workspace_leakage | 0 | yes | yes |
| secret_durable_promotion | 0 | yes | yes |
| correction_precedence | 0 | no | yes |
| deleted_memory_retrieval | 0 | no | yes |
| cross_user_leakage | 0 | no | yes |

## Mandatory Slices

| Slice | Examples | Matched / Actual | Precision |
| --- | --- | --- | --- |
| ambiguous | 1 | 1 / 1 | 1.0000 |
| assistant-turn | 1 | 1 / 1 | 1.0000 |
| correction | 1 | 1 / 1 | 1.0000 |
| explicit-preference | 1 | 1 / 1 | 1.0000 |
| profile-fact | 1 | 1 / 1 | 1.0000 |
| secret-like | 1 | 1 / 1 | 1.0000 |
| sensitive-personal | 1 | 1 / 1 | 1.0000 |
| trace-excluded | 2 | 2 / 2 | 1.0000 |
| transient | 2 | 2 / 2 | 1.0000 |
| trip-constraint | 1 | 1 / 1 | 1.0000 |
| wrong-scope | 1 | 1 / 1 | 1.0000 |

## Per-example Evidence

| Example | Slice | Matched / Expected / Actual | Failures |
| --- | --- | --- | --- |
| `r5-pref-001` | explicit-preference | 1 / 1 / 1 | — |
| `r5-constraint-001` | trip-constraint | 1 / 1 / 1 | — |
| `r5-profile-001` | profile-fact | 1 / 1 / 1 | — |
| `r5-correction-001` | correction | 1 / 1 / 1 | — |
| `r5-transient-001` | transient | 1 / 1 / 1 | — |
| `r5-transient-002` | transient | 1 / 1 / 1 | — |
| `r5-ambiguous-001` | ambiguous | 1 / 1 / 1 | — |
| `r5-scope-001` | wrong-scope | 1 / 1 / 1 | — |
| `r5-excluded-001` | trace-excluded | 1 / 1 / 1 | — |
| `r5-chat-001` | assistant-turn | 1 / 1 / 1 | — |
| `r5-secret-001` | secret-like | 1 / 1 / 1 | — |
| `r5-sensitive-001` | sensitive-personal | 1 / 1 / 1 | — |
| `r5-chat-002` | trace-excluded | 1 / 1 / 1 | — |

## Notes

- R5 shadow report: candidates are measured but never used in answers. Promotion precision, retrieval, and personalization metrics are not applicable and carry no values here.
- Cross-user and deleted-memory gates are not applicable: R5 has no user identity, no deletion path, and no memory retrieval.
- Correction precedence is not applicable as a hard-gate event: R5 keeps no competing memory store, so no older inference can override a correction at retrieval time. Correction classification is measured in the correction slice instead.
- The secret gate scans accepted candidate content with the secret-like patterns rather than trusting the sensitivity label.
