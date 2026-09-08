# Risk-based Memory Control Amendment

| Field | Value |
| --- | --- |
| Status | In Review |
| Version | 0.1 |
| Date | 2026-09-07 |
| Change class | Level 3 - Architecture Amendment |
| Decision owner | Repository owner |
| Scope | Confirmation, application-owned save feedback, sensitive no-store policy, ambiguous conflicts, and Shadow semantics |
| Related issue | Repository-owner approved exception: interactive memory design session on 2026-09-07 |
| Superseded document | Amends the approved [Basic Semantic Memory Write Pipeline Design](./2026-09-07-basic-semantic-memory-write-pipeline-design.md) v0.1 after approval |

## Summary

Replace confirm-all behavior with risk-based confirmation. Explicit low-risk
remember commands commit after deterministic validation and produce an
application-owned `Memory Saved` event separate from the model response.
Contextually sensitive, restricted, and prohibited content is not durable
memory and does not trigger a permission prompt. Bulk deletion and scope
expansion retain preview plus one-time confirmation. Ambiguous conflicts remain
pending until relevant. `SHADOW` means valid but unpromoted, not rejected.

## Decision Table

| Case | Selected behavior | Reason | Trade-off |
| --- | --- | --- | --- |
| Explicit low-risk `remember` | Validate, atomically commit, then UI renders `Memory Saved` | The user command is already explicit intent | A classification bug has no second prompt; hard validation must fail closed |
| LLM response | Generated separately from mutation result | Only application state can prove commit | UI handles two response channels |
| Contextually sensitive/restricted | Use only in current conversation when needed; create no durable memory and ask no save question | Focused scope lacks protected durable handling | No cross-chat sensitive personalization |
| Prohibited secret/payment/authentication | Reject and redact before model/candidate/index | No memory business purpose | May discard surrounding text when safe separation is impossible |
| Delete one ordinary memory | Direct mutation plus application Undo | Small and reversible | Undo needs a real compensating version |
| Enable/disable memory | Direct setting mutation plus Undo | Toggle is explicit and reversible | State propagation must be consistent across clients |
| Bulk delete | Preview exact count/scope, issue bound token, commit after confirmation | Broad destructive impact | Extra interaction and token lifecycle |
| Conversation-to-user scope expansion | Preview old/new scope and confirm | Widens future impact across chats | Extra interaction |
| Clear conflict | Deterministic `REINFORCE`, `SUPERSEDE`, or `ADD_EXCEPTION` | Key/scope/time semantics are explicit | Requires reliable normalization |
| Ambiguous conflict | `PENDING_CONFLICT`; current utterance governs current answer; ask only when relevant | Avoids destructive guessing and interruption | Profile may remain unresolved |
| Valid inferred candidate below promotion authority | `SHADOW`; store evidence for evaluation only | Separates learning from answer authority | Storage/retention and later re-evaluation required |
| Hard-policy failure | `INVALID`, `REJECTED`, `HELD_SENSITIVE`, or `PENDING_CONFLICT`, never `SHADOW` | Shadow must mean valid-but-unpromoted | More precise outcome vocabulary |

## Runtime Contracts

```text
explicit low-risk request
-> deterministic eligibility/key/value/scope/sensitivity checks
-> conflict resolver
-> atomic commit
-> mutation_result=saved
-> UI system event: Memory Saved

assistant generation
-> separate response payload/state
-> cannot claim persistence from model text
```

```text
normal user message
-> background candidate
-> hard policy
-> valid but not promotion-authorized: SHADOW
-> no retrieval, prompt use, save event, or answer effect
```

```text
ambiguous same-key contradiction
-> PENDING_CONFLICT
-> no durable active-value mutation
-> current message governs current response
-> when later relevant, ask whether temporary exception or global update
-> unresolved pending record expires/retracts under a later retention decision
```

## Confirmation-token Contract

Tokens exist only for bulk deletion and scope expansion. They bind owner,
command, operation/payload hash, old/new scope, expected version, expiry, and a
one-time nonce. Confirmation revalidates current state; stale previews are
rejected and regenerated. No transaction or row lock remains open while waiting
for the user.

## Security and Privacy

1. Application events render only after canonical commit.
2. Model text cannot synthesize `Memory Saved` state.
3. Sensitive no-store is deterministic policy; user wording cannot override it
   in this focused scope.
4. Shadow candidates never become prompt context or citations.
5. Bulk/scope confirmation tokens are owner-bound, one-time, expiring, and
   version-bound.

## Acceptance Criteria

1. Explicit low-risk save commits without a second prompt and renders one
   application event only after success.
2. Failed commit renders no saved event regardless of model response.
3. Sensitive/prohibited examples create zero durable memory and zero save
   prompts.
4. Bulk delete and scope expansion mutate only after valid confirmation.
5. Clear conflict outcomes remain deterministic.
6. Ambiguous conflict creates no active mutation and prompts only when relevant.
7. Shadow candidates are valid, non-active, non-retrievable, non-prompt inputs.
8. Hard-policy failures never receive `SHADOW` status.

## Approval Record

Not approved. Approval will authorize ADR 0017 acceptance and superseding
updates to the evaluation and implementation artifacts; it will not by itself
authorize runtime code changes beyond separately approved amended plans.

