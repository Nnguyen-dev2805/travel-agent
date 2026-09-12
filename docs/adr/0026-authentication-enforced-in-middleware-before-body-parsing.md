# ADR 0026: Authentication Is Enforced in Middleware, Before the Request Body Is Parsed

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-11 |
| Decision owners | Repository owner |
| Scope | Where bearer authentication is enforced in the request pipeline, and whether the public surface is an allowlist or a per-route omission. Bounded by the middleware stack in `backend/app/main.py` and the security policy in `backend/security/dependencies.py`. |
| Governing spec | `docs/specs/2026-09-11-authentication-enforcement-ordering-design.md` v0.1 (Status: Approved 2026-09-11) |
| Superseded ADR | Not applicable |
| Superseded by | Not applicable |

## Context

ADR 0018 made authentication unconditional: the compatibility mode and the unauthenticated deployment path were removed, so every request must carry a valid bearer token. The decision said what must happen. It did not say where in the pipeline it happens, and that omission turned out to be load-bearing.

Authentication is enforced by a FastAPI dependency, `require_principal`, declared on each guarded route. `backend/app/api/chat.py` documents the guarantee that was assumed to follow from declaring it first:

> `require_principal` is declared first so an unauthenticated request is rejected with `401` before any storage, RAG, or memory dependency is constructed.

Declaring a parameter first orders the parameters **within** `solve_dependencies`. It cannot order anything that happens before `solve_dependencies`, and FastAPI reads and JSON-parses the request body in `get_request_handler` before calling it. So a body that is not valid JSON raises `RequestValidationError` and produces `422` without `require_principal` executing at all.

Measured on 2026-09-11 against the real application, with no credentials:

| Request | Status |
| --- | --- |
| `POST /api/v1/chat`, malformed JSON, no `Authorization` header | `422` |
| `POST /api/v1/chat`, malformed JSON, **invalid** token | `422` |
| `POST /api/v1/chat`, valid JSON, no header | `401` |
| `POST /api/v1/chat`, valid JSON, wrong shape, no header | `401` |
| `POST /api/v1/conversations`, malformed JSON, no header | `422` |

Only JSON **parse** errors are affected; schema errors are raised inside `solve_dependencies`, after the dependencies, and already produce `401`.

Two things follow. First, the invariant ADR 0018 established is false on every body-bearing route, and a request carrying a **rejected** token is answered identically to one carrying none — the authentication decision is skipped, not deferred. Second, the per-route model is default-allow: a route that omits `Depends(require_principal)` is public, and nothing detects the omission. ADR 0018 asked for authentication that is unconditional, and a per-route guard can only express "unconditional where someone remembered".

Three options were considered: move enforcement into middleware with an explicit allowlist, declare the dependency once on the routers, or accept the behaviour and document it.

## Decision

Authentication is enforced in the request pipeline, ahead of routing and therefore ahead of body parsing, by `enforce_authentication` in `backend/security/dependencies.py`, called from the existing correlation middleware in `backend/app/main.py` **before** `enforce_request_body_limit`.

The public surface is a module-level allowlist — `GET /health` plus the FastAPI documentation paths — and nothing else. A path is public only if it is listed; there is no pattern that makes one public implicitly, and the allowlist is a constant rather than a setting, so widening it requires a code change.

`enforce_authentication` inspects the `Authorization` header and the URL path only. It never reads the body. On success it stashes the principal on `request.state.principal` and returns `None`; on failure it returns a `401` with the same content-free detail strings the dependency already produced.

`require_principal` becomes an accessor of the stashed principal and **fails closed** with `500` when it is absent. It does not fall back to resolving credentials: that would restore a second source of truth and let a mis-wired stack authenticate silently.

`CORSMiddleware` is registered **last**, so it is outermost. Starlette inserts each middleware at position 0 and therefore builds the stack with the most recently registered layer outermost. With the previous order the correlation middleware sat outside CORS, so any early response it produced carried no CORS headers. The reordering is part of this decision rather than a consequence to be discovered later: an early `401` that a browser cannot read is not a usable `401`.

Every exit path of the correlation middleware emits exactly one `api.request.completed` event. Previously the two early returns — an oversized body and an unconfigured body limit — returned before the emission point and appeared nowhere in the event stream. Adding a third silent early return while the change's stated purpose is to make unauthenticated traffic visible would have extended that defect.

## Alternatives Considered

### Declare the dependency once on the routers

**Approach.** `APIRouter(dependencies=[Depends(require_principal)])`, or the equivalent on `FastAPI(...)`, so the guard is declared in one place.

**Benefits.** Removes the per-route repetition, so a route added to an existing router is guarded. Small diff. No middleware change and no ordering change, so nothing about CORS or the event stream moves.

**Costs.** It does not change the measured behaviour. Router-level dependencies are solved inside `solve_dependencies`, the same phase as route-level ones, so the body is still parsed first and a malformed body still yields `422` with no authentication. It also still leaves `GET /health` and the documentation paths to be handled by exclusion rather than inclusion, and the ordering constraint it implies is the same one that produced the defect.

**Rejected because** it looks like a fix and is not one. It would produce a change set that appears to address the finding and passes a review that reads decorators, while leaving every measured row of the case table unchanged. This rejection is recorded at length deliberately: it is the change a reader would most reasonably expect to work.

### Authenticate inside a custom route class

**Approach.** Subclass `APIRoute`, override `get_route_handler` to authenticate before the parent handler reads the body, and apply it through `route_class`.

**Benefits.** Enforcement sits exactly at the boundary that needs it, with the body read demonstrably after it. No middleware ordering change, and the response is produced inside normal routing, so CORS applies as it does today.

**Costs.** Couples the security boundary to a framework extension point that is not part of the public contract and has changed between releases. It must be applied to every router, so a router constructed without the class is unguarded and the default-allow problem returns in a subtler form. It is more code than a middleware for the same guarantee.

**Rejected because** it trades a small, well-understood ordering change for a dependency on framework internals, and it does not achieve default-deny across the whole application.

### Accept the behaviour and document the deviation

**Approach.** Change nothing. Record that authentication is evaluated after body parsing, and that a malformed body yields `422`.

**Benefits.** Zero risk, no code change, no ordering change, no test updates.

**Costs.** The invariant ADR 0018 established stays false. The `422`-versus-`401` distinction remains an unauthenticated oracle for probing which routes exist and what shape their bodies take. Unauthenticated traffic stays invisible to any `401`-based signal. A rejected token stays indistinguishable from an absent one on this path.

**Rejected because** it accepts a reproduced defect as documentation, and the claim it contradicts is a requirement of an accepted decision rather than an incidental comment.

### Enforce in middleware with an explicit allowlist

**Approach.** As decided above.

**Benefits.** The invariant becomes true on every path, including bodies the parser rejects. Enforcement is default-deny, so a newly added route is guarded without anyone remembering. The public surface becomes a written, reviewable list. The authentication decision cannot be skipped by input shape. The `401` stays readable by a browser. No client contract changes.

**Costs.** The middleware ordering changes, which alters CORS behaviour and event emission on two existing early-return paths. `require_principal` can no longer be called standalone, which breaks one existing boundary assertion that must be moved rather than deleted. Understanding the authentication path now requires reading two files instead of one.

**Selected because** it is the only alternative that fixes the measured behaviour, and because it additionally converts a default-allow model into a default-deny one. The ordering change is required for the fix to be usable by the actual client, and it repairs a defect on the `413` and configuration-`500` paths at the same time.

## Consequences

**Positive.**

- An unauthenticated request is rejected with `401` on every path, before its body is read, whether or not that body parses.
- A rejected token is rejected by the authentication decision rather than bypassing it.
- The public surface is a constant list in one file; a new route is guarded by default.
- An unauthenticated rejection is visible in the event stream, and so are the oversized-body and configuration-failure paths that were previously silent.
- A browser client can read the `401`, so an expired session is distinguishable from a network failure.
- The `401` detail strings, the status codes, and the response shapes are unchanged, so no client contract moves.

**Negative.**

- The middleware stack order becomes significant and non-obvious. `CORSMiddleware` must stay last, and moving it back would silently restore the CORS defect; a boundary test now asserts the position.
- An oversized body (`413`) and a configuration failure (`500`) change observable behaviour: both gain CORS headers and a completion event.
- `401` volume will rise for malformed-body traffic that previously produced `422`, so a `401`-based alert begins to fire on traffic that was previously invisible. This must be announced before rollout.
- `require_principal` is no longer usable without the middleware. A mis-wired stack fails closed with `500` rather than resolving credentials, which is deliberate but does mean the dependency cannot be reasoned about in isolation.
- The authentication path spans two files, and a reader looking only at the route decorators will not see where enforcement happens.
- One existing boundary assertion must move from `require_principal` to `enforce_authentication`, because the control it tested changed location.

**Neutral.**

- The token format, the registry, the hashing, and the `500` for a misconfigured registry are unchanged.
- The unauthenticated documentation surface is unchanged. It is now an explicit exemption rather than an accident of the framework's defaults; closing it remains a separate decision.
- No data is written, so the change has no irreversible effect and no rollback hazard.

## References

1. Governing spec: `docs/specs/2026-09-11-authentication-enforcement-ordering-design.md` v0.1
2. Implementation plan: `docs/plans/2026-09-11-authentication-enforcement-ordering-implementation.md`
3. Extends: [ADR 0018](./0018-authenticated-chat-only-product-container.md) — Authenticated Chat-Only Product Container
4. Related: [ADR 0021](./0021-standalone-conversation-ownership-and-auto-create.md) — Standalone Conversation Ownership, Route Contract, and Auto-Create Behavior
5. Related: [ADR 0019](./0019-postgresql-only-application-persistence-sqlite-retirement.md) — PostgreSQL-Only Application Relational Persistence and SQLite Retirement
