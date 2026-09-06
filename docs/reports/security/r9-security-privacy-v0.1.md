# Security and Privacy Evaluation `r9-security-privacy-v0.1`

Result: **PASS**

## Gates

| Gate | Applicable | Passed | Events |
| --- | --- | --- | --- |
| unauthenticated_access | True | True | 0 |
| invalid_token_access | True | True | 0 |
| cross_owner_access | True | True | 0 |
| deleted_memory_retrieval | True | True | 0 |
| raw_500_leakage | True | True | 0 |
| token_leakage | True | True | 0 |
| oversized_request_accepted | True | True | 0 |

## Examples

| Example | Slice | Failures |
| --- | --- | --- |
| r9a-missing-token | authentication | - |
| r9a-invalid-token | authentication | - |
| r9x-workspace | cross_owner | - |
| r9x-conversation | cross_owner | - |
| r9x-memory | cross_owner | - |
| r9x-planner | cross_owner | - |
| r9d-memory-selected | deletion | - |
| r9d-writes-rejected | deletion | - |
| r9e-500-redacted | error_hardening | - |
| r9e-oversized | error_hardening | - |
| r9p-tokens | privacy | - |
| r9p-auth-off | privacy | - |
