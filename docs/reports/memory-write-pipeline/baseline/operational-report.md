# Memory Write Pipeline Evaluation Report: OPERATIONAL

**Result State:** `FAIL`
**Run ID:** `evrun_23d3d83ff0ce` | **Timestamp:** `2026-09-09T03:57:27.838487+00:00`
**Dataset:** `write-pipeline-hotel-atmosphere-v0.1` (v0.1.0)

## Summary Counts

- **Total Examples:** 9
- **Completed:** 9
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
| `candidate_recall` | 0.0000 (0/6) | >=0.90 | **NO** |
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
| `redelivery_idempotency` | 1 | 1 | 0 | PASS |
| `transaction_failure` | 2 | 2 | 0 | PASS |
| `deleted_source_stale_worker` | 1 | 1 | 0 | PASS |
| `background_shadow_rollout` | 2 | 2 | 0 | PASS |
| `provider_structured_failure` | 3 | 3 | 0 | PASS |
