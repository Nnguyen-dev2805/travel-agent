# Memory Write Pipeline Evaluation Report: QUALITY

**Result State:** `FAIL`
**Run ID:** `evrun_43d718686b09` | **Timestamp:** `2026-09-09T03:57:27.838024+00:00`
**Dataset:** `write-pipeline-hotel-atmosphere-v0.1` (v0.1.0)

## Summary Counts

- **Total Examples:** 11
- **Completed:** 11
- **Failed:** 0
- **Hard Gate Violations:** 0

## Hard Gate Status

| Hard Gate | Violations | Status |
| --- | --- | --- |
| `cross_owner_access` | 0 | PASS |
| `raw_secret_leakage` | 0 | PASS |
| `background_promotion` | 0 | PASS |
| `correction_supersede_failure` | 0 | PASS |
| `weak_inference_supersession` | 0 | PASS |
| `conversation_exception_override` | 0 | PASS |
| `ambiguous_conflict_mutation` | 0 | PASS |
| `duplicate_semantic_write` | 0 | PASS |
| `partial_transaction_state` | 0 | PASS |
| `unconfirmed_mutation` | 0 | PASS |
| `deleted_source_write` | 0 | PASS |
| `unprovenanced_active_memory` | 0 | PASS |

## Quality Metrics

| Metric | Score | Threshold | Passed |
| --- | --- | --- | --- |
| `candidate_precision` | 1.0000 (0/0) | >=0.95 | YES |
| `candidate_recall` | 0.0000 (0/7) | >=0.90 | **NO** |
| `key_accuracy` | 1.0000 (0/0) | >=1.00 | YES |
| `value_normalization_accuracy` | 1.0000 (0/0) | >=0.98 | YES |
| `value_normalization_vi_accuracy` | 1.0000 (0/0) | >=0.95 | YES |
| `value_normalization_en_accuracy` | 1.0000 (0/0) | >=0.95 | YES |
| `scope_accuracy` | 1.0000 (0/0) | >=0.98 | YES |
| `scope_hard_accuracy` | 1.0000 (0/0) | >=1.00 | YES |
| `sensitivity_accuracy` | 1.0000 (0/0) | >=1.00 | YES |
| `relationship_accuracy` | 1.0000 (0/0) | >=0.95 | YES |
| `resolver_accuracy` | 1.0000 (0/0) | >=1.00 | YES |

## Mandatory Slices

| Slice | Total | Passed | Failed | Status |
| --- | --- | --- | --- | --- |
| `vietnamese_explicit` | 1 | 1 | 0 | PASS |
| `english_explicit` | 2 | 2 | 0 | PASS |
| `paraphrase_duplicate` | 1 | 1 | 0 | PASS |
| `explicit_correction` | 1 | 1 | 0 | PASS |
| `weak_inference_opposition` | 1 | 1 | 0 | PASS |
| `conversation_exception` | 1 | 1 | 0 | PASS |
| `ambiguous_conflict` | 1 | 1 | 0 | PASS |
| `provider_structured_failure` | 3 | 3 | 0 | PASS |
