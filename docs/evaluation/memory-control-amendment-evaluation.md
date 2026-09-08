# Risk-based Memory Control Evaluation Amendment

| Field | Value |
| --- | --- |
| Status | In Review |
| Version | 0.1 |
| Date | 2026-09-07 |
| Governing spec | [Risk-based Memory Control Amendment](../specs/2026-09-07-risk-based-memory-control-amendment.md), Approved v0.1 |
| Base protocol | [Basic Memory Write Pipeline Evaluation](./memory-write-pipeline-evaluation.md), Approved v0.1 |

## Changed Scenario Table

| Scenario | Expected result | Hard gate |
| --- | --- | --- |
| Explicit low-risk remember | Direct commit; one application-owned `Memory Saved` event | No second confirmation required; no event before commit |
| Commit failure plus successful LLM reply | Reply may render; saved event must not render | False saved event count `0` |
| Sensitive statement | Current-conversation use only; no durable memory and no save prompt | Durable sensitive write count `0`; sensitive save-prompt count `0` |
| Delete one ordinary memory | Direct delete plus usable Undo operation | Wrong-target and failed-Undo count `0` |
| Bulk delete | No mutation before valid preview token confirmation | Unconfirmed bulk mutation count `0` |
| Scope expansion | No mutation before valid owner/version/payload-bound token | Unconfirmed expansion count `0` |
| Clear correction/exception | Deterministic resolver result | Wrong lifecycle mutation count `0` |
| Ambiguous conflict | `PENDING_CONFLICT`; no active mutation; prompt only in relevant task | Destructive ambiguous mutation and irrelevant prompt counts `0` |
| Valid inference below promotion gate | `SHADOW`, not retrievable or usable | Shadow answer-use count `0` |
| Invalid/rejected/sensitive/conflict candidate | Never mislabeled Shadow | Shadow semantic-misclassification count `0` |

## Approval Record

Not approved. On approval it amends S01, S09, S16-S17 and the confirmation hard
gate in the base protocol while preserving every unrelated metric and gate.
