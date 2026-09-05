# Planner State Evaluation `r7-state-v0.1`

Result: **PASS**

## Gates

| Gate | Applicable | Passed | Events |
| --- | --- | --- | --- |
| version_continuity | True | True | 0 |
| single_accepted | True | True | 0 |
| rejected_preservation | True | True | 0 |
| cross_workspace_isolation | True | True | 0 |
| operation_traceability | True | True | 0 |
| no_implicit_chat_writes | True | True | 0 |

## Examples

| Example | Slice | Failures |
| --- | --- | --- |
| v-chain | itinerary_versioning | - |
| v-drafts | itinerary_versioning | - |
| v-proposed | itinerary_versioning | - |
| v-archive | itinerary_versioning | - |
| d-accept-change | decision_lifecycle | - |
| d-reject | decision_lifecycle | - |
| d-direct-accepted | decision_lifecycle | - |
| d-replace | decision_lifecycle | - |
| j-one | rejected_option_preservation | - |
| j-two | rejected_option_preservation | - |
| x-itinerary | cross_workspace_isolation | - |
| x-decision | cross_workspace_isolation | - |
| x-accept | cross_workspace_isolation | - |
| t-mixed | operation_traceability | - |
| t-archive-chain | operation_traceability | - |
| c-quiet | chat_isolation | - |
