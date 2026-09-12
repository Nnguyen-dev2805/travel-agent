# Authentication Enforcement Ordering: Enforce Before the Body Is Parsed

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-11 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Where authentication is enforced in the request pipeline, and what happens to a request whose body cannot be parsed. Bounded by the middleware stack in `backend/app/main.py`, the security policy in `backend/security/dependencies.py`, and the public-path surface. |
| Related issue | None filed. Authorization basis is the repository owner's selection of workstream W1 from the owner-requested triage of the 2026-09-11 code review. Evidence is reproduced under Current-state Evidence. |
| Superseded document | Not applicable |

## Summary

Authentication is enforced by a FastAPI dependency, `require_principal`. FastAPI parses the request body in `get_request_handler` **before** it calls `solve_dependencies`, and dependencies are solved inside `solve_dependencies`. A body that is not valid JSON therefore raises `RequestValidationError` and produces a `422` **before `require_principal` ever executes**.

Measured on the real application, with no credentials at all:

| Request | Status today | Status expected |
| --- | --- | --- |
| `POST /api/v1/chat`, malformed JSON, no `Authorization` header | **422** | 401 |
| `POST /api/v1/chat`, malformed JSON, **invalid** token | **422** | 401 |
| `POST /api/v1/chat`, valid JSON, no header | 401 | 401 |
| `POST /api/v1/chat`, valid JSON, wrong shape, no header | 401 | 401 |
| `POST /api/v1/conversations`, malformed JSON, no header | **422** | 401 |

Only JSON **parse** errors are affected. Schema errors are raised inside `solve_dependencies`, after the dependencies, so they already produce 401.

The consequence is not data exposure — the handler never runs. It is that the invariant the product claims, and that `backend/app/api/chat.py` documents in its own docstring, is false on every body-bearing route: an unauthenticated request is processed far enough to parse and validate its body, and a request carrying a **rejected** token is answered identically to one carrying none.

This specification moves enforcement into the request pipeline, ahead of routing and therefore ahead of body parsing, and makes the public surface an explicit allowlist rather than an accident of what each route remembered to declare.

## Context

The product exposes eight routes. Seven declare `Depends(require_principal)`; one, `GET /health`, does not:

| Route | Guarded today |
| --- | --- |
| `GET /health` | no — deliberate liveness probe |
| `GET /api/v1/ops/readiness` | yes |
| `POST /api/v1/chat` | yes |
| `POST /api/v1/conversations` | yes |
| `GET /api/v1/conversations` | yes |
| `GET /api/v1/conversations/{conversation_id}` | yes |
| `GET /api/v1/conversations/{conversation_id}/messages` | yes |
| `DELETE /api/v1/conversations/{conversation_id}` | yes |

Four further paths are served without credentials by FastAPI defaults: `/docs`, `/redoc`, `/openapi.json`, and `/docs/oauth2-redirect`.

`backend/app/api/chat.py` documents the guarantee that does not hold:

> `require_principal` is declared first so an unauthenticated request is rejected with `401` before any storage, RAG, or memory dependency is constructed.

Declaring a parameter first controls the order **within** `solve_dependencies`. It cannot control anything that happens before `solve_dependencies`, and the body read happens before it.

**The deeper problem is the enforcement model, not the ordering.** Guarding each route individually makes the system default-allow: a new route that forgets `Depends(require_principal)` is public, and nothing detects it. The clean-break specification removed the compatibility mode precisely so that authentication would be unconditional; a per-route model cannot express "unconditional", only "unconditional where someone remembered".

## Users

1. **Repository owner** — approves the enforcement location and the change to the middleware ordering.
2. **Authenticated end user** — depends on the client being able to distinguish an expired session from a network failure. A `401` the browser cannot read is not a `401` the user can act on.
3. **Security reviewer** — needs the "mandatory bearer auth" claim to be true and testable, and needs the public surface to be a written list.
4. **Operator** — needs unauthenticated traffic to be visible. Today it is invisible to any `401`-based signal, because malformed requests never reach the authentication path.
5. **Future contributor** — needs a new route to be guarded by default, so security is not a per-route memory exercise.

## Problem Statement

**Authentication is enforced after the point at which unauthenticated work has already been done.** The body is read, buffered, and JSON-parsed before the first dependency runs. `enforce_request_body_limit` in `main.py` already demonstrates the correct layer: it runs in the correlation middleware, before routing, and returns an early `413`. Authentication simply was never moved to that layer.

**A rejected token is treated the same as an absent one on this path.** Both produce `422` when the body is malformed, so the authentication decision is skipped entirely — not merely deferred.

**The failure is invisible to the operations signal that should catch it.** The completion event carries `status_code: 422` and `reason_code: http_client_error`. A flood of unauthenticated malformed requests therefore looks like ordinary client error traffic and never appears as an authentication failure.

**The enforcement model is default-allow.** Each of the seven guarded routes repeats `Depends(require_principal)`. Nothing enforces the pattern, so the next route added decides by omission whether it is public.

**Why now.** The owner-requested review reproduced this as the only remaining finding with a demonstrated exploitation path. The fix is small; the ordering it depends on is not obvious, which is why it is decided here rather than patched in place.

## Goals

1. An unauthenticated request to any guarded route is rejected with `401` **before its body is read**, whether or not the body is parseable.
2. A request carrying an invalid token is rejected with `401` on the same path, so the authentication decision is never skipped.
3. The public surface is an explicit, named allowlist in code, not the absence of a dependency on a route.
4. A newly mounted route is guarded by default.
5. The `401` response carries the same status, the same content-free `detail` strings, and the same `X-Request-ID` header as today, so no client contract changes.
6. The `401` is reachable by a browser client: it carries CORS headers, so the frontend can distinguish an expired session from a network failure.

## Non-goals

1. Changing the token format, the registry, the hashing, or the `401`/`500` detail strings.
2. Changing the status code for a misconfigured registry. An unset or invalid `LOCAL_AUTH_TOKENS_JSON` continues to produce `500`, as today. That is a separate finding and is not decided here.
3. Closing the unauthenticated `/docs`, `/redoc`, `/openapi.json` surface. This specification preserves it and makes it an explicit, documented exemption; closing it is a separate decision with its own user-visible cost.
4. Changing which routes exist, their paths, or their response schemas.
5. Rate limiting, auditing, or authentication failure accounting. Goal 4 in **Users** notes that unauthenticated traffic is currently invisible; making it visible is a follow-up, not part of this change.
6. Any change to the memory write pipeline or to the conversation turn contract.

## Assumptions

1. `GET /health` must remain reachable without credentials, because a liveness probe that requires a token cannot report an authentication outage.
2. The four FastAPI documentation paths are intended to be public in development. They are public today; this specification preserves that rather than changing it.
3. The middleware stack is the correct enforcement layer, because Starlette builds it outside the router, so a middleware runs before routing and therefore before any body read.
4. The existing `enforce_request_body_limit` call inside `request_correlation_middleware` establishes that an early return from that middleware is an accepted pattern in this codebase.
5. An early `401` returned from a middleware must pass through `CORSMiddleware` to carry CORS headers, and `CORSMiddleware` must therefore be the outermost layer. This is verified, not assumed — see Current-state Evidence.

## User and System Flows

**Flow 1 — An authenticated request.** The CORS layer wraps the response. The correlation middleware binds a request id and emits the completion event. The authentication middleware resolves the principal, stashes it, and calls through. The route's `require_principal` reads the stash. Unchanged from the caller's perspective.

**Flow 2 — An unauthenticated request with a valid body.** The authentication middleware rejects it with `401` before routing. The route is never selected, the body is never parsed, no container dependency is constructed. The response carries CORS headers, `X-Request-ID`, and one completion event with `status_code: 401`.

**Flow 3 — An unauthenticated request with a malformed body.** Identical to Flow 2. This is the behaviour the finding is about: the outcome no longer depends on whether the body happens to parse.

**Flow 4 — A request to a public path.** `GET /health`, and the documentation paths, pass through the authentication middleware untouched and behave exactly as today.

**Flow 5 — A request to a newly added route.** Guarded without any change to the new route, because the middleware is default-deny. A contributor who wants a public route must add it to the allowlist, which is a reviewable edit in one file.

## Behavioral and Data Contracts

### Public surface (`backend/security/dependencies.py`)

- **Produces:** a module-level allowlist of paths exempt from authentication, and the predicate that consults it.
- **Contract:** the allowlist is an exact-path set plus a small prefix set for the documentation routes. It contains `GET /health` and the FastAPI documentation paths, and nothing else. A path is public only if it is listed; there is no pattern that makes a path public implicitly.
- **Contract:** the allowlist is a constant, not a setting. A deployment cannot widen the public surface without a code change.

### Authentication middleware entry point (`backend/security/dependencies.py`)

- **Produces:** `enforce_authentication(request)`, returning a `JSONResponse` to short-circuit with, or `None` to continue.
- **Contract:** for a public path it returns `None` and resolves nothing. For any other path it resolves the principal and either stashes it and returns `None`, or returns a `401` response. It returns the same `detail` strings the dependency produces today (`"Authentication required."` for an absent or malformed header, `"Invalid bearer token."` for a rejected token) and the same `500` with `"Authentication is unavailable."` when the registry is unconfigured.
- **Contract:** it never reads the request body. It inspects the `Authorization` header and the URL path only.

### Principal handoff

- **Produces:** the resolved principal on `request.state.principal`.
- **Contract:** the middleware writes it; `require_principal` reads it. `require_principal` no longer resolves credentials itself.
- **Contract:** `require_principal` fails closed when the principal is absent. An absent principal means the middleware did not run, which is a wiring defect, and it must produce a `500` rather than resolve credentials again. Re-resolving is explicitly rejected: it would restore two sources of truth and reintroduce the silent-fallback pattern removed elsewhere in this codebase.

### Middleware ordering (`backend/app/main.py`)

- **Produces:** a stack ordered, outermost first, as CORS → correlation → authentication → router.
- **Contract:** `CORSMiddleware` is registered **last**, because Starlette builds the stack with the most recently registered middleware outermost. It is currently registered first, which makes the correlation middleware outermost and means every early return from it bypasses CORS.
- **Contract:** authentication is evaluated before `enforce_request_body_limit`, so an unauthenticated request is rejected without reading its body.
- **Produces:** every exit path of the correlation middleware emits exactly one `api.request.completed` event. Today the two early returns — an oversized body and an unconfigured body limit — return **without emitting anything**, so neither appears in the event stream at all. Adding a third early return in that shape would extend the defect while the change's stated purpose is to make unauthenticated traffic visible, so the exits are unified instead.
- **Consequence to record:** the existing early returns for an oversized body (`413`) and for an unconfigured body limit (`500`) gain CORS headers **and a completion event** as a result. That is a behaviour change to two existing paths, and it is an improvement on both counts: each is currently unreadable by a browser client and invisible in the event stream, for the same structural reason.

### Route declarations

- **Contract:** routes keep `Depends(require_principal)`. It becomes the principal accessor rather than the enforcement point, and keeping it declared on each route preserves the readable statement of which routes need an identity.

## Errors and Edge Cases

1. **Malformed JSON body, no credentials.** Expected: `401` before the body is read. This is the finding.
2. **Malformed JSON body, invalid token.** Expected: `401`, not `422`. The authentication decision is not skipped.
3. **Malformed JSON body, valid token.** Expected: `422` from the validation handler, as today. The request is authenticated, so the schema rejection is the correct answer.
4. **Valid body, no credentials.** Expected: `401` with `"Authentication required."`, as today.
5. **Oversized body, no credentials.** Expected: `401`, not `413`. Authentication is evaluated first, so an unauthenticated caller cannot learn the body limit by probing it.
6. **Oversized body, valid credentials.** Expected: `413`, as today, now with CORS headers.
7. **Registry unconfigured or invalid.** Expected: `500` with `"Authentication is unavailable."`, as today, now raised from the middleware and now carrying CORS headers.
8. **The middleware is not registered, or runs after the route.** Expected: `require_principal` fails closed with `500`. This is a loud failure by construction and must not be softened into a fallback.
9. **A public path is renamed.** Expected: the allowlist stops matching, the path becomes guarded, and `GET /health` returns `401`. The plan requires a test asserting each allowlisted path is reachable without credentials, so a rename fails the suite rather than the deployment.
10. **A new route is added without a dependency.** Expected: guarded. The plan requires a test that walks the mounted route table and asserts every non-allowlisted path rejects an unauthenticated request.
11. **A path is requested with a trailing slash or different casing.** Expected: not treated as public. Matching is exact on the path, which is case-sensitive, so only the listed spelling is exempt.
12. **A preflight `OPTIONS` request.** Expected: handled by `CORSMiddleware`, which is now outermost, before authentication. The plan requires a test that a preflight request is not answered `401`.

## Security and Privacy

**Trust boundaries.** Unchanged in number; the authentication boundary moves earlier in the pipeline, ahead of body parsing and routing. No new trust boundary is introduced.

**Authorization.** Strengthened. The model changes from default-allow to default-deny, so a route added without a guard is protected rather than exposed. The authentication decision is no longer skippable by choosing a body the parser rejects.

**Attack surface.** Reduced. An unauthenticated caller can no longer cause the application to read, buffer, and validate a request body, nor to construct a container dependency. The `422`-versus-`401` distinction is no longer available as an unauthenticated oracle for probing route existence and body shape.

**Data classification.** No change. The middleware reads the `Authorization` header and the URL path, neither of which is user content. It never reads the body, so no message content enters the authentication path. The `detail` strings are content-free constants and are unchanged.

**Privacy.** No change. No user content is read, logged, or moved. No stored data is touched by this change.

**Observability.** Improved. An unauthenticated request now produces a completion event with `status_code: 401` and `reason_code: http_client_error`, on a path that previously produced `422` or, for a valid body, `401`. The consequence is stated plainly: a signal that alerts on `401` volume will begin to fire for malformed-body traffic that previously produced `422`. This is intended — that traffic is unauthenticated — but it is a change in alert behaviour and must be announced before rollout.

## Observability and Operations

- The `401` response carries `X-Request-ID` and one `api.request.completed` event, because the correlation middleware wraps the authentication check and every one of its exits now emits.
- One event per rejected request, with `method`, `path`, and `status_code: 401` in counters. No body, no query string, and no token, consistent with the existing content-free event contract.
- A configuration failure produces the same `500` and the same log line as today (`security.auth configuration failure failure_class=...`), and now also a completion event.
- An oversized body produces the same `413` and now also a completion event. Both of these are new entries in the event stream for traffic that was previously silent, and the plan requires that to be recorded rather than discovered.
- The plan requires the alert-volume consequence to be stated in the Completion Record, so the operator is not surprised by a new signal source.

## Capacity, Latency, and Cost

- **Latency.** Adds one header lookup and, for a non-public path, one token comparison per request, performed earlier than it is performed today. The token comparison is not duplicated, because the dependency no longer re-resolves. Net cost on an authenticated request is approximately zero; on an unauthenticated request it is a saving, because the body is no longer read or parsed.
- **Capacity.** No new storage, no new query, no new connection. The allowlist is two in-memory collections.
- **Cost.** No model call. No effect on the RAG or memory paths.
- **Measurement.** The plan requires the unauthenticated malformed-body case to be measured before and after, since that is the case whose cost changes from a full body read to a header check.

## Compatibility and Staged Migration

**Coexistence.** The change is internal to one process; there is no wire-format or schema change. A client cannot distinguish the new server from the old except by the status code of a malformed, unauthenticated request, which is the behaviour being corrected.

**Sequencing.** Single step, single deployable. The middleware ordering change and the enforcement change must land together: enforcement without the reordering would produce a `401` the browser cannot read, and the reordering without enforcement would change only the `413` and configuration-`500` paths.

**Rollout gate.** Every allowlisted path is reachable without credentials, every non-allowlisted path returns `401` without credentials, and a preflight `OPTIONS` request is not answered `401`.

**Rollback boundary.** Reverting the commit restores the previous ordering and the previous enforcement point exactly. Nothing in this change writes data, so there is no irreversible effect and no data repair.

## Failure and Recovery

| Failure | Behaviour | Recovery |
| --- | --- | --- |
| Registry unconfigured | `500` with a content-free detail, from the middleware | Fix the configuration; the path is unchanged from today |
| Middleware not registered | Every guarded route returns `500` from `require_principal` | Fail-closed by construction; the suite must catch it before deployment |
| Allowlist and routes disagree | A path is guarded that should be public, or the reverse | The plan requires a test per allowlisted path and a test over the mounted route table |
| A proxy strips the `Authorization` header | Every request is `401` | Configuration fault at the proxy, visible immediately and not silently degraded |
| Preflight blocked | Browser clients fail before sending the real request | `CORSMiddleware` is outermost and handles preflight before authentication; asserted by a test |

## Required ADRs

1. **ADR 0026 — Authentication Is Enforced in Middleware, Before the Request Body Is Parsed.** Records the decision that authentication is a pipeline concern rather than a per-route concern, that the enforcement point is ahead of body parsing, and that the public surface is an explicit allowlist. Extends ADR 0018's unconditional-authentication decision with the enforcement location and the default-deny model that ADR 0018 did not state.

**No second ADR is required.** The `CORSMiddleware` ordering change is a consequence of the enforcement point, not an independent decision: an early response must traverse the outer layers, and the current registration order prevents it. It is recorded as a contract and a consequence in this specification.

## Alternatives Considered

### Enforce in middleware, with an explicit public allowlist — the selected approach

**Approach.** A middleware-level `enforce_authentication` runs before routing. It consults an allowlist, resolves the principal for every other path, stashes it on `request.state`, and returns a `401` itself on failure. `require_principal` becomes a fail-closed accessor. `CORSMiddleware` is registered last so the early response traverses it.

**Benefits.** The invariant becomes true on every path, including bodies the parser rejects. Enforcement is default-deny, so a new route is guarded without anyone remembering. The public surface becomes a written list in one file. The authentication decision can no longer be skipped by input shape. The `401` remains readable by a browser. No client contract changes.

**Costs.** The middleware ordering changes, which alters CORS behaviour on two existing early-return paths. `require_principal` can no longer be called standalone without a request that carries the stashed principal, which breaks one existing boundary assertion that must be moved rather than deleted. A reader must now look in two files to understand the authentication path.

**Selected because** it is the only alternative that fixes the reported behaviour, and it additionally converts a default-allow model into a default-deny one. The ordering change is required for the fix to be usable by the actual client, and it repairs a defect on the `413` and configuration-`500` paths at the same time.

### Declare the dependency on the routers instead of each route

**Approach.** `APIRouter(dependencies=[Depends(require_principal)])`, or `app = FastAPI(dependencies=[...])`, so the guard is declared once.

**Benefits.** Removes the per-route repetition, so a new route on an existing router is guarded. Small diff, no middleware change, no ordering change.

**Costs.** It does not fix the finding. Router-level dependencies are solved inside `solve_dependencies`, which is the same phase the route-level dependency is solved in, so the body is still parsed first and a malformed body still produces `422` without authentication. It also still leaves `GET /health` and the documentation paths to be handled by exclusion rather than inclusion.

**Rejected because** it looks like a fix and is not one. It would produce a change set that appears to address the finding, passes a review that reads the decorators, and leaves the reproduced behaviour exactly as measured. Recording this rejection matters more than usual, because it is the change a reader would expect to work.

### Authenticate inside a custom route class

**Approach.** Subclass `APIRoute` and override `get_route_handler` to authenticate before the parent handler reads the body, applied via `route_class`.

**Benefits.** Enforcement sits exactly at the boundary that needs it, with the body read demonstrably after it. No middleware ordering change; the response is produced inside the normal routing path, so CORS applies as it does today.

**Costs.** Couples the security boundary to a FastAPI internal extension point, whose signature and behaviour are not part of the public contract and have changed between releases. It must be applied to every router, and a router created without the class is unguarded, so the default-allow problem returns in a subtler form. It is also more code than a middleware for the same guarantee.

**Rejected because** it trades a small, well-understood middleware-ordering change for a dependency on framework internals, and it does not achieve default-deny across the whole application.

### Accept the `422` and document the deviation

**Approach.** Change nothing. Record that authentication is evaluated after body parsing, and that a malformed body yields `422`.

**Benefits.** Zero risk, zero code change, no ordering change, no test updates.

**Costs.** The product's stated invariant remains false. The `422`-versus-`401` distinction remains an unauthenticated oracle. Unauthenticated traffic continues to be invisible to authentication signals. A rejected token continues to be indistinguishable from an absent one on this path.

**Rejected because** it accepts a reproduced security defect as documentation, and the claim it contradicts is a requirement of the approved clean-break specification rather than an incidental comment.

## Current-state Evidence

| Claim | Evidence path | Verified how |
| --- | --- | --- |
| The body is parsed before dependencies are solved | `backend/app/api/chat.py:54-58` declares `request: ChatRequest` before `Depends(require_principal)`; FastAPI's `get_request_handler` reads and JSON-parses the body before calling `solve_dependencies` | Reproduced on the real application, 2026-09-11 |
| Malformed body, no credentials, returns `422` | `POST /api/v1/chat` with `{"message": "hi"` and no header returned `422` with `{"detail":[{"type":"json_invalid","loc":["body",16],...}]}` | Executed |
| Malformed body, invalid token, returns `422` | Same request with `Authorization: Bearer not-a-real-token-at-all-000000000000` returned `422` | Executed |
| A valid body still produces `401` | Same route with `{"message": "hi"}` and no header returned `401 {"detail":"Authentication required."}` | Executed |
| Schema errors are unaffected | Same route with `{"unexpected": 1}` and no header returned `401`, not `422` | Executed |
| Every body-bearing route is affected | `POST /api/v1/conversations` with a malformed body and no header returned `422` | Executed |
| Only `/health` and the documentation paths are public | Probe over the mounted app without credentials: `/health` 200, `/openapi.json` 200, `/docs` 200, `/redoc` 200, `/api/v1/ops/readiness` 401, `/api/v1/conversations` 401 | Executed |
| Seven of eight routes declare the guard | `backend/app/api/{chat,conversations,ops}.py` | Direct source read |
| A middleware can hand a value to a route | Isolated probe, Starlette 1.6.0: a `@app.middleware("http")` writing `request.state.principal` was read by the route, as was a `ContextVar` | Executed |
| An early middleware response carries CORS headers only when `CORSMiddleware` is outermost | Isolated probe, same version: with CORS registered first the early `401` had no `access-control-allow-origin`; with CORS registered last it carried `http://localhost:5173` | Executed |
| The current registration order makes the correlation middleware outermost | `backend/app/main.py:110` registers `CORSMiddleware`, `:120` registers the correlation middleware; Starlette inserts each at position 0, so the last registered is outermost | Direct source read plus the probe above |
| An existing boundary test calls the guard directly | `backend/tests/boundaries/test_clean_break_boundaries.py:360-368` calls `require_principal(request)` and asserts `401` | Direct source read |

**Not verified.** The alert-volume consequence is reasoned from the completion event's `status_code` field and has not been observed against a live alerting system, because none is configured. Behaviour behind a real reverse proxy that terminates or rewrites the `Authorization` header was not tested. The `422`-versus-`401` oracle was demonstrated against the application's own routes; it was not used to enumerate anything.

## Components and Dependency Direction

```
backend/app/main.py
   │  CORSMiddleware (outermost)  ->  correlation middleware  ->  authentication
   ▼
backend/security/dependencies.py
   │  enforce_authentication(request)  ->  allowlist, resolve, stash, or 401
   │  require_principal(request)      ->  reads request.state.principal, fails closed
   ▼
backend/app/api/{chat,conversations,ops}.py
   │  Depends(require_principal) unchanged as a declaration
   ▼
backend/orchestration/ · backend/conversations/
```

**Allowed dependency direction.** Unchanged. `backend/security` already owns request policy shared by the middleware and the tests, and `main.py` already imports it. No new module is introduced and no layer is inverted.

**Ownership.** The security package owns the enforcement decision and the allowlist. `main.py` owns the ordering of the stack. Routes keep declaring that they need an identity, which is a statement about the route rather than about enforcement.

## Data Flow and Lifecycle

**Request lifecycle.** Correlation id bound → path checked against the allowlist → principal resolved or `401` returned → body limit enforced → routed → handler reads the stashed principal. An unauthenticated request terminates at the third step, before the body is read.

**Configuration lifecycle.** The allowlist is a module constant, so the public surface changes only through a code change and a review. The token registry remains a setting and its failure mode is unchanged.

**Failure lifecycle.** A missing or invalid registry fails closed with `500`. A missing principal in the dependency fails closed with `500`. Neither degrades into allowing the request.

## Approval Record

| Field | Value |
| --- | --- |
| Version | 0.1 |
| Status | Approved — 2026-09-11, repository owner |
| Approver role | Repository owner |
| Date | 2026-09-11 |
| Authorization boundary | Authorizes preparation and approval of the implementation plan at `docs/plans/2026-09-11-authentication-enforcement-ordering-implementation.md` and acceptance of ADR 0026. Implementation is authorized only by the separate plan approval recorded below. |

**Approved 2026-09-11 by the repository owner, together with Plan D and ADR 0026.** The approval authorizes execution of the three tasks of that plan.

**What this approval does NOT authorize.** Closing the unauthenticated documentation surface (`/docs`, `/redoc`, `/openapi.json`); changing the status code for a misconfigured registry; rate limiting or authentication-failure accounting; any change to the token format, the registry, or the hashing; any change to the routes or their response schemas; enabling the memory write pipeline; and any Git delivery.

**Three consequences of this approval must be understood as part of it, and all three change observable behaviour.** First, an oversized body (`413`) and a configuration failure (`500`) will begin carrying CORS headers. Second, those same two paths will begin emitting a completion event, where today they emit nothing. Third, a `401` volume alert will begin to fire for malformed-body traffic that previously produced `422`. All three are intended, and all three are recorded here so they are not discovered during rollout.
