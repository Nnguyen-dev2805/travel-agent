# ADR 0038: Positive Source Handling and Inferred Activation Authority

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-12 |
| Decision owners | Repository owner |
| Scope | Family-specific source handling, background formation permission, inferred activation authority, evidence independence, and shadow-first rollout |
| Governing spec | `docs/specs/2026-09-12-agent-memory-target-architecture-design.md` v0.2 (Approved 2026-09-12) |
| Superseded ADR | Not applicable |
| Superseded by | Not applicable |

## Context

The background Memory worker processes Chat-derived outbox events asynchronously.
A normal Chat message can contain useful evidence, an explicit Memory command, a
refusal, a correction, a secret, or no Memory-relevant content at all. Treating
"no explicit block was recorded" as permission to infer Memory would make
missing state an authorization mechanism.

Inferred activation also has a different trust model from explicit Memory. A
model can extract a plausible candidate from one utterance, but model confidence
is not evidence that the candidate is true, stable, or appropriate to persist as
active user state.

## Decision

Every source/outbox event is handled per Memory family through a durable typed
record:

```text
SourceHandlingRecord(
  source_outbox_id,
  source_message_id,
  family,
  outcome,
  reason_code,
  recorded_at,
)
```

The uniqueness boundary is:

```text
(source_outbox_id, family)
```

Representative outcomes are:

```text
BACKGROUND_ELIGIBLE
EXPLICIT_APPLIED
EXPLICIT_REFUSED
EXPLICIT_NOOP
FORGET_APPLIED
FORGET_REFUSED
```

Absence of a record means `UNHANDLED`. It never means permission.

Background formation for a family may run only when that family has the positive
`BACKGROUND_ELIGIBLE` outcome. An explicit action outcome for the same source
and family therefore prevents the worker from independently reinterpreting that
source as background permission.

After positive source handling, a structured model may form immutable evidence
and candidate objects. It may classify bounded unresolved semantics, but it does
not decide activation or durable lifecycle effects.

Activation remains family/type-specific deterministic policy over validated
evidence. The initial authority rules include:

1. conversation-scoped inferred semantic preference/profile: at least two
   independent agreeing user turns and no unresolved conflict;
2. user-scoped inferred semantic preference/profile: at least three independent
   evidence items across at least two conversations and no unresolved conflict;
3. inferred constraints: shadow until policy-specific evidence and impact gates
   are approved;
4. relationship Memory: grounded entity resolution plus repeated evidence when
   ambiguous;
5. episodic Memory: one grounded event may suffice only when actor, event, time,
   and provenance validate;
6. Working Memory: governed deterministic conversation transition or validated
   source-consistent replacement;
7. Procedural Memory: never activated from tenant Chat evidence.

Retries or re-extraction of one source do not create independent support.
Evidence independence is based on provenance identity, not row count.

New inferred activation ships shadow-first. Background formation may produce
evaluation evidence before it is allowed to create answer-eligible active
versions. Enabling active inferred Memory requires a separately approved,
conclusive evaluation gate for that family/type.

## Alternatives

### Treat every released outbox event as background permission

This is simple and maximizes recall, but it lets missing routing state and
explicit-command sources silently become inference authority. Rejected.

### Let the extraction model decide whether a candidate should activate

This reduces deterministic policy code, but turns model confidence into product
authority and makes repeated extraction of the same source look like stronger
evidence. Rejected.

### Use one global evidence threshold for every Memory family

This is easy to explain, but semantic preferences, episodes, relationships,
constraints, and working state have different error costs and evidence shapes.
Rejected.

### Positive family handling plus type-specific activation gates

This is more explicit and requires more evaluation fixtures, but keeps
authorization, evidence support, and model interpretation as separate concerns.
Selected.

## Consequences

### Positive

1. Missing routing/audit state fails closed instead of granting background
   permission.
2. Explicit and background handling of one source/family cannot silently double
   count the same evidence.
3. Evidence thresholds reflect the failure cost of each Memory type.
4. Shadow-first rollout makes inferred quality measurable before it influences
   answers.
5. Model confidence is prevented from becoming a truth or authorization signal.

### Negative

1. Every family needs source-handling outcomes, reason codes, fixtures, and
   evaluation coverage.
2. High-precision activation intentionally sacrifices recall for user-scoped
   inferred Memory.
3. Multi-conversation evidence accounting becomes part of Memory correctness.
4. Promotion from shadow to active requires explicit evaluation governance per
   family/type instead of one global switch.

## Migration

Introduce family-specific `SourceHandlingRecord` production before expanding
background formation. Existing outbox rows without a positive record remain
`UNHANDLED`; they are not grandfathered into background eligibility.

Keep inferred output shadow-only until the implementation plan defines and the
owner approves the evaluation gate. A rollback may stop new claims or disable
formation, but must preserve source-handling and evaluation evidence needed to
explain prior decisions.

## Validation

1. A source with no family record cannot enter background formation.
2. `EXPLICIT_APPLIED`, `EXPLICIT_REFUSED`, `EXPLICIT_NOOP`, `FORGET_APPLIED`,
   and `FORGET_REFUSED` do not satisfy `BACKGROUND_ELIGIBLE`.
3. Duplicate delivery/re-extraction of one source contributes one independent
   evidence identity.
4. User-scoped semantic inference cannot activate from three rows that all
   derive from one conversation/source lineage.
5. Equal-authority unresolved contradiction remains non-active and excluded from
   use.
6. Shadow mode records measurable decisions without creating answer-eligible
   versions.
7. Active inferred Memory remains disabled when the required evaluation result
   is missing, skipped, uncollectable, or `INCONCLUSIVE`.
8. Secret/sensitivity hard-policy failures are rejected rather than converted
   into shadow candidates.

## References

1. [Agent Memory Target Architecture](../specs/2026-09-12-agent-memory-target-architecture-design.md) v0.2.
2. [ADR 0013](./0013-model-assisted-extraction-and-deterministic-resolution.md).
3. [ADR 0014](./0014-transactional-outbox-and-idempotent-memory-workers.md).
4. [ADR 0016](./0016-focused-memory-write-evaluation-and-rollout.md).
5. [ADR 0027](./0027-outbox-event-released-only-when-turn-terminal.md).
6. [ADR 0029](./0029-the-memory-worker-runs-as-its-own-service.md).
