# ADR 0010: Local Identity, Authorization, and Deletion Boundary

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-06 |
| Decision owners | Repository owner |
| Scope | R9 local authentication, authorization, data deletion, error hardening, and privacy verification boundary |
| Governing spec | [Security and Privacy Hardening Design](../specs/2026-09-06-security-and-privacy-hardening-design.md), version 0.2 |
| Superseded ADR | None |
| Superseded by | None |

## Context

Travel Agent now stores local workspace, conversation, memory, and planner data.
Earlier milestones intentionally used caller-supplied `owner_user_id` as a local
scope label, not an authenticated identity. That kept R3-R8 small, but it leaves
two memory hard gates unprovable: cross-user memory leakage and deleted-memory
retrieval after confirmed deletion.

The project also still has public-production blockers named in `SECURITY.md` and
`ARCHITECTURE.md`: unauthenticated product routes, permissive local CORS, no
request body size limit, no deletion semantics, and raw exception-derived HTTP
500 details.

R9 needs a durable security boundary that is strong enough for local tests and
review evidence without pretending the prototype has a production identity
provider, session system, TLS termination, or deployment topology.

## Decision

R9 will introduce a local security and privacy boundary with four parts:

1. a server-side authenticated principal resolved from a local bearer-token
   registry when authentication is enabled;
2. authorization helpers that require the principal owner to match the owning
   workspace before reading or writing workspace, conversation, memory, or
   planner state;
3. soft deletion and tombstone semantics that make deleted workspace data
   inaccessible through product APIs and ineligible for memory retrieval;
4. content-free HTTP 500 handling, request-size limits, and security evaluation
   evidence.

The selected authentication mechanism is deliberately local. Tokens are read
from environment configuration, compared with `hmac.compare_digest`, never
logged, never persisted, and never returned. The authenticated principal owns a
single `owner_user_id`; caller-supplied owner labels become compatibility input
only and cannot grant access when authentication is enabled.

R9 does not select OAuth, OIDC, hosted identity, cookies, browser sessions,
multi-tenant production storage, TLS, WAF, rate limiting, cloud secret
management, or deployment topology.

R9 security evaluation must run with authentication enabled. If the local auth
gate cannot be enabled with a valid synthetic token registry, the security
evaluation is `INVALID`; it must not report `PASS` from compatibility mode.

Deletion is ordered for safety rather than coordinated through one cross-module
SQLite transaction. The workspace enters `deletion_requested` first, which makes
normal reads and writes fail closed. Conversation, memory, and planner
transitions are idempotent and retryable; confirmation can complete only after
the workspace-scoped child transitions are verified.

## Alternatives

### Adopt OAuth or OIDC Now

This would be closer to a public product architecture, but it requires provider
selection, redirect/session behavior, frontend changes, secret rotation, and
deployment assumptions that are not approved. It is rejected for R9.

### Keep Caller-supplied Owner Labels

This preserves compatibility, but it cannot prove cross-user isolation because
any caller can choose any owner label. It is rejected as the R9 security
boundary, although unauthenticated compatibility mode may remain for local
development.

### Local Bearer-token Principal Boundary

This is selected. It gives deterministic local authorization and evaluation
evidence now, keeps secrets out of storage and logs, and leaves production
identity as a later architecture decision.

## Consequences

### Positive

1. Cross-user isolation can be tested against authenticated principals.
2. Product routes can stop trusting caller-supplied owner labels as authority.
3. Deleted memory and workspace data can be made ineligible through a governed
   lifecycle instead of an ad hoc filter.
4. Raw exception strings no longer need to appear in HTTP 500 responses.
5. R10 can evaluate release readiness against concrete local security evidence.

### Negative

1. Local bearer-token auth is not a production identity provider.
2. Existing local clients may need headers when authentication is enabled.
3. Tombstoning leaves records in SQLite for audit and evaluation, so hard-delete
   semantics remain a later decision.
4. Route wiring becomes more explicit because every product read/write must pass
   through an owner authorization check.

## Migration

R9 is staged. It first adds security contracts, then applies them to product
routes behind an explicit authentication setting, then adds deletion transitions
and evaluation evidence. Existing local development can keep compatibility mode
unless the repository owner enables the local auth gate. R9 must also refresh
memory evaluation evidence for the two previously unobservable R6/R9 gates and
close the roadmap's open ordering problem only after that evidence exists.

Rollback disables the auth gate, removes the new route dependencies and deletion
endpoints, and removes R9 evaluation/report artifacts. Product data remains
readable by older code because R9 uses existing lifecycle vocabulary or additive
columns only where the approved plan requires them.

## Validation

R9 implementation must prove:

1. unauthenticated protected requests are rejected when auth is enabled;
2. invalid bearer tokens are rejected without logging token values;
3. an authenticated owner cannot read, mutate, or delete another owner's
   workspace, conversation, memory, or planner state;
4. deleted or tombstoned memory is never selected for answers;
5. deleted workspace state is hidden from normal product reads and writes;
6. HTTP 500 responses contain a controlled generic detail and request id, not
   arbitrary exception text;
7. request body size limits reject oversized payloads deterministically;
8. the R9 security/privacy evaluation report returns `PASS`;
9. refreshed memory evidence proves authenticated cross-user isolation and
   deleted-memory retrieval gates.

## References

1. [Security and Privacy Hardening Design](../specs/2026-09-06-security-and-privacy-hardening-design.md)
2. [Security and Privacy Hardening Implementation Plan](../plans/2026-09-06-security-and-privacy-hardening-implementation.md)
3. [Security Policy](../../SECURITY.md)
4. [Memory Evaluation Protocol](../evaluation/memory-evaluation.md)
5. [Master Roadmap](../roadmap/master-roadmap.md)
