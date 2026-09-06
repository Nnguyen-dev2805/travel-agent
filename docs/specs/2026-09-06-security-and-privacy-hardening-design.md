# Security and Privacy Hardening Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.2 |
| Date | 2026-09-06 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Runtime milestone R9 - local authentication boundary, owner authorization, deletion/tombstone semantics, controlled error responses, request-size guard, and security/privacy evaluation |
| Parent design | [Operations and Security Design](./2026-08-31-operations-and-security-design.md), version 0.1; [Memory Retrieval Design](./2026-09-04-memory-retrieval-design.md), version 0.3; [Observability and Operations Design](./2026-09-05-observability-and-operations-design.md), version 0.2 |
| Depends on | `D6`; `R3`; `R4`; `R5`; `R6`; `R7`; `R8` accepted in the working tree; [ADR 0010](../adr/0010-local-identity-authorization-and-deletion-boundary.md) (Accepted) |
| Architecture approval | Approved by repository owner on 2026-09-06 |
| Implementation plan | [Security and Privacy Hardening Implementation Plan](../plans/2026-09-06-security-and-privacy-hardening-implementation.md), version 0.3 (Approved) |
| Related issue | None - R9 documentation drafting was authorized by the repository owner in conversation on 2026-09-06 |
| Superseded document | None |

## Summary

R9 adds a local security and privacy boundary around the backend product state.
It introduces authenticated local principals, authorization checks for owner and
workspace access, deletion/tombstone semantics for user data, controlled HTTP
500 responses, request-size limits, and a deterministic security/privacy
evaluation report.

R9 is not a production identity or deployment milestone. It creates evidence
that local backend routes no longer rely on caller-supplied owner labels as
authority and that deleted memory cannot influence answers.

## Current-state Evidence

Verified current implementation:

1. `SECURITY.md` says the backend has no implemented user authentication or
   authorization, permissive local CORS, raw HTTP 500 detail risk, and no
   production security claim.
2. `ARCHITECTURE.md` records that workspace, conversation, memory, planner, and
   ops routes are unauthenticated and that `owner_user_id` is a local scope
   label, not authorization.
3. `backend/workspaces/models.py` already has `RetentionState` values
   `active`, `archived`, `deletion_requested`, and `deleted`, but R3 implements
   no transition into deletion states. `backend/workspaces/sqlite_repository.py`
   already excludes `RetentionState.deleted` records from owner list results.
4. `backend/conversations/models.py` already has
   `ConversationRetentionState.deletion_requested` and `deleted`, but R4
   implements no transition into deletion states.
   `backend/conversations/sqlite_repository.py` already excludes deleted
   conversations from workspace list results.
5. `backend/memory/models.py` already has `MemoryRecordStatus.deleted` and
   `deletion_requested`; R6 retrieval filters lifecycle states, but no user
   deletion path creates those states. `backend/memory/retrieval.py` requests
   only `MemoryRecordStatus.active` and double-checks eligibility before
   selection.
6. `backend/planner/models.py` has `archived` and `superseded` lifecycle values
   for planner records, but no workspace-level deletion policy.
7. `backend/app/errors.py` redacts validation error payloads, but raw
   exception-derived HTTP 500 behavior remains a security blocker in user-facing
   paths.
8. R8 added request ids, privacy-safe events, readiness diagnostics, and an ops
   report, giving R9 a safe evidence channel for security verification.

## Context

R3-R8 deliberately built product capability before full security hardening.
That sequence was useful, but R9 is the point where the prototype must stop
treating caller-supplied labels as enough evidence for privacy-sensitive flows.

The memory protocol has two unresolved zero-tolerance gates: authenticated
cross-user leakage and deleted-memory retrieval. Both require R9 deliverables.
Without R9, R10 cannot claim open-source release confidence for a backend that
stores user-entered trip content.

The R9 change set must therefore do more than create a standalone security
report. After authentication and deletion exist, it must refresh memory evidence
for the R6 report line that is currently label-based, produce authenticated
cross-user and deleted-memory gate evidence, and update the roadmap's
`Open Ordering Problem: R6 and R9` section.

## Users

1. **Repository owner:** needs reviewable proof that privacy-sensitive routes
   have a local security boundary before release work.
2. **Developer:** needs deterministic local auth and deletion behavior that can
   be tested without external providers.
3. **Coding agent:** needs exact rules for which route inputs are authority and
   which are compatibility data.
4. **Reviewer:** needs hard-gate evidence for cross-owner access, deletion, and
   raw error leakage.
5. **Future operator:** needs clear public-production blockers that remain after
   local hardening.

## Problem Statement

The current backend can persist workspaces, conversations, memory, and planner
state, but product routes still rely on caller-provided identifiers and owner
labels. A caller who knows or guesses ids can attempt cross-owner reads and
writes. Deletion vocabulary exists, but no product flow requests or confirms
deletion. Some error paths can still expose arbitrary exception text.

R9 must create a narrow security layer that is testable now and honest about
what it does not solve.

## Goals

1. Add local authenticated principal contracts and settings.
2. Require product routes to resolve authorization from the server-side
   principal when auth is enabled.
3. Preserve unauthenticated local compatibility only behind an explicit
   development mode.
4. Ensure callers cannot use body, query, or path owner labels to impersonate
   another owner when auth is enabled.
5. Add workspace-owned deletion request and confirmation flows.
6. Tombstone or hide deleted workspace, conversation, memory, and planner state
   from normal product reads and writes.
7. Ensure deleted or deletion-requested memory is never promoted, selected, or
   included in answer context.
8. Replace raw exception-derived HTTP 500 responses with controlled,
   content-free error details and request id correlation.
9. Add a deterministic request body size limit for API requests.
10. Tighten local CORS behavior when auth is enabled.
11. Produce an R9 security/privacy evaluation report with zero-tolerance gates.
12. Re-run or extend memory evaluation evidence so the former R6/R9 ordering
    gap is closed by authenticated identity and confirmed deletion.
13. Update `SECURITY.md`, `ARCHITECTURE.md`, runbooks, roadmap, and indexes with
    truthful current-state evidence.

## Non-goals

1. No OAuth, OIDC, hosted identity provider, SSO, browser session, refresh token,
   password login, email verification, or account recovery flow.
2. No frontend UI, login page, memory management screen, or deletion UI.
3. No production deployment, TLS termination, WAF, rate limiting, audit-log
   retention service, SIEM, external telemetry vendor, or cloud secret manager.
4. No hard deletion from SQLite, backup erasure, replica erasure, or legal
   compliance claim.
5. No default-on personalization decision.
6. No change to RAG document retrieval ranking, prompt policy, or benchmark
   dataset.
7. No booking integration or external travel account access.
8. No claim that the backend is public-production ready after R9.

## Assumptions

Implementation must stop if any assumption differs:

1. The implementation base includes R8 source and docs, including request ids,
   safe operational events, readiness, and the R8 ops report.
2. Local bearer-token authentication is acceptable for R9 evidence, while
   production identity remains a later architecture decision.
3. Existing lifecycle vocabularies are sufficient for soft deletion, except for
   additive repository/service methods needed to apply transitions.
4. Deleted records may remain in the local SQLite database as tombstones for
   audit and evaluation.
5. Health remains a compatibility liveness endpoint.
6. R9 can change protected API error behavior for security, especially auth
   failures, cross-owner access, oversized requests, and HTTP 500 details.
7. Existing clients may need new headers only when auth is enabled.
8. Security evaluation can use synthetic users, tokens, workspaces, messages,
   memory, and planner records.
9. R9 security evaluation and refreshed memory hard-gate evidence run with
   `AUTH_REQUIRED=true`; if authentication cannot be enabled, the relevant
   report state is `INVALID`, not `PASS`.
10. Ops readiness remains protected when `AUTH_REQUIRED=true`; if token
    configuration is broken, operators use `/health` plus privacy-safe logs for
    diagnosis until the registry is repaired.

## User and System Flows

### Authenticated Product Request

Caller sends `Authorization: Bearer <token>` -> auth dependency compares the
token with the local token registry -> server resolves `AuthenticatedPrincipal`
with `owner_user_id` -> route/service authorizes the requested workspace owner
-> product operation proceeds or returns a controlled `401`, `403`, or `404`.

### Local Compatibility Request

When auth is disabled by explicit local setting, existing local request shapes
continue to work. The code path must label the principal as compatibility mode
and must not be used as evidence for authenticated cross-user isolation.

### Workspace Deletion

Authenticated owner requests deletion for a workspace -> workspace moves to
`deletion_requested` -> conversations move to `deletion_requested`; active
memory records become `deletion_requested`; planner state becomes hidden from
normal reads -> authenticated owner confirms deletion -> workspace,
conversations, and memory records move to `deleted`; planner state remains
unavailable through product routes -> memory retrieval returns no deleted or
deletion-requested records.

The ordering is intentional. R9 does not require one transaction spanning four
independent repository adapters, because current adapters open their own SQLite
connections. Instead, workspace `deletion_requested` is the fail-closed barrier:
once set, normal product reads and writes for that workspace are denied while
idempotent child transitions are retried or reconciled.

### Bound Chat Authorization

For bound chat, the route cannot authorize from request body owner data because
`ChatRequest` has only `message` and optional `conversation_id`. The required
chain is:

```text
conversation_id -> conversation.workspace_id -> workspace.owner_user_id -> principal.owner_user_id
```

That chain must be the single source of owner truth. The orchestrator may still
resolve workspace owner for memory retrieval, but it must receive a conversation
that has already passed the same owner authorization rule when auth is enabled.

### Controlled Failure

Unhandled product exception -> global handler emits safe event with
`failure_class` and request id -> response body contains a generic detail and
the request id -> raw exception text, stack trace, SQL, paths, prompts, and user
content stay out of the response.

## Alternatives Considered

### A. OAuth/OIDC Provider in R9

This gives the most realistic production auth model, but it pulls in provider
selection, frontend login, callback routes, token storage, deployments, and
secret management. It is too broad for R9 and is rejected.

### B. Local Header Owner Only

This would replace `owner_user_id` fields with a header such as
`X-Owner-User-ID`, but the caller would still choose the identity. It is
rejected because it does not prove cross-user isolation.

### C. Local Bearer-token Principal with Soft Deletion

This is selected. It gives server-resolved identity, owner authorization, and
deletion evidence without external dependencies or production identity claims.

## Components and Dependency Direction

R9 introduces this boundary:

```text
FastAPI routes and middleware
↓
security dependencies and privacy services
↓
workspace, conversation, memory, and planner services
↓
repository interfaces and SQLite adapters
```

Allowed dependencies:

1. `backend/security/models.py` and token utilities may depend only on standard
   library and Pydantic.
2. `backend/security/dependencies.py` may depend on FastAPI, settings, and
   security models.
3. Product route modules may depend on security dependencies and authorization
   helpers.
4. Privacy/deletion orchestration may depend on workspace, conversation, memory,
   and planner service/repository interfaces.
5. Security evaluation may construct synthetic data and use local repositories.
6. Observability event/context modules remain lower-level and must not import
   security, product routes, or privacy services.

Forbidden dependencies:

1. RAG must not import security, memory, workspace, planner, or deletion code.
2. Low-level security token validation must not import product services.
3. Repositories must not inspect HTTP headers or FastAPI request objects.
4. Deletion and authorization must not use Chroma as a source of product truth.
5. Security evaluation must not use real credentials, real user data, network
   calls, or external identity providers.

## Behavioral and Data Contracts

### Auth Settings

R9 adds settings with these meanings:

| Setting | Contract |
| --- | --- |
| `AUTH_REQUIRED` | Boolean. `false` preserves local compatibility; `true` protects product and ops routes except `/health` |
| `LOCAL_AUTH_TOKENS_JSON` | JSON object mapping `owner_user_id` to local bearer token values; required when `AUTH_REQUIRED=true` |
| `MAX_REQUEST_BODY_BYTES` | Positive integer request body limit for API requests |
| `ALLOWED_CORS_ORIGINS` | Comma-separated local origins; wildcard is rejected when `AUTH_REQUIRED=true` |

`LOCAL_AUTH_TOKENS_JSON` is secret-bearing configuration. It must be excluded
from settings representations, readiness responses, logs, reports, and error
messages. `.env.example` may document the variable name and JSON shape with
safe placeholders only.

### AuthenticatedPrincipal

| Field | Contract |
| --- | --- |
| `owner_user_id` | Server-resolved owner id from token registry |
| `auth_mode` | `authenticated` or `compatibility` |
| `credential_label` | Safe label such as `local_token`, never the token value |

### Authorization

1. Authenticated route access is granted only when the requested workspace owner
   matches the principal owner.
2. Cross-owner workspace, conversation, memory, and planner ids return
   controlled `404` when the request addresses an existing resource id.
3. Creating a new workspace with body `owner_user_id` different from the
   authenticated principal returns `403`, because no existing resource id is
   being concealed.
4. Listing workspaces ignores cross-owner query labels in auth mode and returns
   only the principal's owner scope, or rejects mismatched owner query labels
   with `403`.
5. Existing not-found behavior must not reveal whether an id exists under
   another owner.
6. Route handlers may pass `principal.owner_user_id` to services, but services
   and repositories remain responsible for deterministic owner/workspace checks.

| Request shape | Auth-mode result |
| --- | --- |
| Missing or invalid bearer token on protected route | `401` |
| Create workspace with mismatched body owner | `403` |
| List workspace owner scope different from principal | `403` or principal-only filter, but never another owner's data |
| Read/mutate/delete existing cross-owner workspace id | `404` |
| Read/mutate existing cross-owner conversation, memory, planner, or bound chat id | `404` |
| Delete already deleted own workspace | Idempotent success or controlled conflict, never raw storage error |

### Deletion

| Entity | Deletion-request behavior | Confirmed deletion behavior |
| --- | --- | --- |
| Workspace | `retention_state=deletion_requested` | `retention_state=deleted`; hidden from list/get/create-dependent flows |
| Conversation | `retention_state=deletion_requested` | `retention_state=deleted`; messages no longer returned through normal APIs |
| Memory records | `status=deletion_requested` | `status=deleted`; never selected for answers |
| Planner itineraries | hidden from normal reads once workspace deletion starts | hidden from normal reads; no new writes accepted |
| Planner decisions | hidden from normal reads once workspace deletion starts | hidden from normal reads; no new writes accepted |
| Operation logs | retained as content-minimized evidence where already present | excluded from normal product APIs unless a later audit spec approves access |

### Error Responses

Unhandled HTTP 500 responses use:

```json
{
  "detail": "Internal server error.",
  "request_id": "rq_<32 lowercase hex characters>"
}
```

Raw exception text, stack traces, local paths, SQL, prompts, messages, memory
text, itinerary text, decisions, tokens, and provider payloads must not appear
in the response.

## Security and Privacy

R9 handles security-sensitive user data. Requirements:

1. Token values must never be logged, persisted, returned, or committed.
2. Auth failures use controlled reason codes only.
3. Authorization checks must happen before returning product content.
4. Deletion requests and confirmations must require the authenticated owner.
5. Evaluation fixtures must use synthetic tokens and synthetic user content.
6. Reports may include ids, counts, and gate names, but no raw content or token
   values.
7. R9 does not authorize public production deployment.

## Observability and Operations

R9 uses R8 events for safe evidence. Event names should describe security
outcomes without exposing content, for example:

1. `security.auth.rejected`
2. `security.authorization.denied`
3. `privacy.deletion.requested`
4. `privacy.deletion.confirmed`
5. `api.request.rejected`

Events carry request id, owner id when safe, workspace id when authorized or
already caller-supplied in path, controlled reason codes, and counts. They must
not carry token values or raw content.

## Testing and Evaluation

R9 implementation must add focused tests for:

1. auth disabled compatibility;
2. auth enabled missing token, invalid token, valid token;
3. token values absent from logs and responses;
4. workspace create/list/get owner authorization;
5. conversation, memory, planner cross-owner denial;
6. deletion request and confirmation lifecycle transitions;
7. memory retrieval ignores `deletion_requested` and `deleted` records;
8. deleted workspace cannot receive new conversations, memory extraction,
   memory promotion, itinerary versions, or planner decisions;
9. HTTP 500 response body is generic and correlated with request id;
10. oversized request body rejection;
11. CORS wildcard rejected when auth is enabled;
12. R9 security/privacy evaluation report.

The R9 fixture lives under:

```text
docs/evaluation/fixtures/security/r9-security-privacy-v0.1/
```

The R9 reports live under:

```text
docs/reports/security/r9-security-privacy-v0.1.json
docs/reports/security/r9-security-privacy-v0.1.md
```

Required zero-tolerance gates:

| Gate | Required result |
| --- | --- |
| unauthenticated protected access | `0` successful protected operations |
| invalid-token protected access | `0` successful protected operations |
| cross-owner data access | `0` successful reads or writes |
| deleted-memory retrieval | `0` selected deleted or deletion-requested records |
| raw 500 detail leakage | `0` leaked exception strings |
| token leakage | `0` token values in logs, responses, or reports |

The R9 report must be generated with `AUTH_REQUIRED=true` and a synthetic token
registry. If the auth gate is off, token registry setup is invalid, or a gate
cannot observe the protected behavior it claims to measure, the result is
`INVALID`.

R9 must also refresh memory evidence for the R6/R9 ordering gap. The refreshed
evidence may be a new `r6-retrieval-v0.2` report or an R9-owned memory gate
appendix that the roadmap links explicitly. It must prove authenticated
cross-user memory leakage count `0` and deleted/deletion-requested memory
selection count `0`.

## Failure and Recovery

R9 must fail closed:

1. `AUTH_REQUIRED=true` with no valid token registry makes protected routes
   unavailable with controlled `500` or startup/config evidence; it must not
   silently fall back to compatibility mode.
2. A malformed token registry reports a controlled configuration failure without
   token values.
3. Cross-owner ids return not-found or forbidden without disclosing ownership.
4. Deletion confirmation that partially fails must leave the workspace in
   `deletion_requested`, keep normal product access denied, and return a
   controlled retryable failure. It must not claim confirmed deletion until
   workspace-scoped child transitions have completed.
5. Evaluation report generation that sees malformed fixture data returns
   `INVALID`.

## Capacity, Latency, and Cost

R9 adds no network calls, external auth providers, or vendor cost. Token lookup
is in-memory after settings load. Authorization checks should use existing
workspace ownership and repository filters. Deletion transitions must be bounded
by one workspace and should avoid full database scans outside that workspace.

## Compatibility and Staged Migration

R9 is staged:

1. Add auth/security contracts and tests.
2. Add route dependencies in compatibility mode.
3. Enable auth in focused tests and evaluation.
4. Add deletion request/confirmation behavior.
5. Harden HTTP 500 and request-size behavior.
6. Update docs after implementation.

Existing local clients remain compatible when `AUTH_REQUIRED=false`. When
`AUTH_REQUIRED=true`, clients must send a valid bearer token and cannot choose
another owner by request body or query string.

Deployment runbook gates for authentication and CORS may gain local evidence
after R9, but they remain public-production blocked because local bearer tokens
and local CORS allowlists are not production identity, TLS, hosting, or
deployment architecture.

## Required ADRs

1. [ADR 0010](../adr/0010-local-identity-authorization-and-deletion-boundary.md)
   records the local identity, authorization, and deletion boundary.

## Rollout and Migration

1. Accept ADR 0010.
2. Approve this spec.
3. Approve the R9 implementation plan.
4. Implement in an isolated worktree from the repository-owner selected base.
5. Run R9 tests, security evaluation, refreshed memory gate evidence, compile,
   boundary checks, and docs verification.
6. Mark R9 `Accepted in working tree` only after owner review acceptance.
7. Mark R9 `Delivered` only after Git delivery occurs.

## Rollback

Rollback disables the auth gate, removes R9 security/deletion modules, removes
R9 route dependencies/endpoints, removes R9 fixtures/reports, and restores R9
documentation references. Tombstoned records remain compatible because existing
lifecycles already include non-active states and normal list/retrieval paths
exclude deleted records.

## Acceptance Criteria

R9 can be accepted when ADR 0010 is accepted, this spec and its implementation
plan are approved, implementation creates the planned auth, authorization,
deletion, error-hardening, request-size, evaluation, and documentation changes,
all R9 tests pass, the R9 report is `PASS`, refreshed memory gate evidence
closes the authenticated cross-user and deleted-memory gaps, no token/raw-content
leakage is observed, the roadmap ordering problem is updated, and
public-production readiness remains explicitly unclaimed.

## Approval Record

| Version | Decision owner | Date | Notes |
| --- | --- | --- | --- |
| 0.1 | Repository owner | 2026-09-06 | Drafted for R9 review. External review found verification commands that could self-match or fail on missing report directories, missing refreshed memory evidence for the R6/R9 ordering gap, ambiguous auth-on evaluation requirements, unsafe deletion atomicity wording, unclear readiness-auth failure handling, underspecified bound-chat authorization, and conflicting 403/404 wording |
| 0.2 | Repository owner | 2026-09-06 | Approved after review fixes. Addresses R9 review feedback by requiring auth-enabled evaluation, adding refreshed memory gate evidence, choosing fail-closed ordered deletion over cross-adapter transaction claims, protecting readiness with documented fallback, specifying bound-chat owner resolution, clarifying 403/404 behavior, documenting secret settings handling, and keeping deployment gates public-production blocked. Approval authorizes accepting ADR 0010 and approving implementation plan version 0.3, and authorizes implementation in an isolated worktree. It does not authorize Git delivery, public production deployment, OAuth/OIDC, frontend work, hard deletion, external providers, or release |
