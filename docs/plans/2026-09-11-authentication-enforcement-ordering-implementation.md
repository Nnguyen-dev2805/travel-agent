# Authentication Enforcement Ordering Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence. Each task ends with a review checkpoint; do not begin
> the next task until the checkpoint condition holds.

**Goal:** Enforce authentication ahead of request-body parsing, so an unauthenticated request is rejected with `401` on every path regardless of whether its body parses, and make the public surface an explicit allowlist rather than a per-route omission.

**Architecture:** Authentication moves from a FastAPI dependency into the existing correlation middleware, ahead of `enforce_request_body_limit`. `enforce_authentication` consults a module-level allowlist, resolves the principal once, stashes it on `request.state`, and returns a content-free `401` itself on failure. `require_principal` becomes a fail-closed accessor. `CORSMiddleware` is registered last so the early response traverses it, and every exit path of the middleware emits exactly one completion event.

**Tech Stack:** Python 3 / FastAPI / Starlette 1.6 / pytest / Vitest

**Spec:** `docs/specs/2026-09-11-authentication-enforcement-ordering-design.md` v0.1

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-09-11 |
| Approved specification | `docs/specs/2026-09-11-authentication-enforcement-ordering-design.md` v0.1 — **Approved 2026-09-11** by the repository owner, together with this plan. ADR 0026 is `Accepted` as of the same date. |
| Execution owner | Implementation agent |
| Decision owner | Repository owner |
| Scope | The enforcement point for bearer authentication, the public-path allowlist, the middleware ordering, and the event emitted for an early rejection |
| Verification | The reproduced case table end to end; a mounted-route inventory test; `pytest backend/tests/unit backend/tests/boundaries`; `pytest backend/tests/integration`; `cd frontend && npx vitest run` |

## Global Constraints

1. Every persistent repository change requires a written specification and an approved implementation plan (`AGENTS.md`). The specification and this plan were approved by the repository owner on 2026-09-11, and Level 3 architecture approval is recorded in the specification's Approval Record with ADR 0026 `Accepted`.
2. The repository owner creates or selects branches and decides when to stage, commit in the primary working tree, push, open a PR, merge, and release. No Git delivery is authorized by this plan.
3. The working tree is dirty and large. Read a dirty file before touching it and work with the existing edits rather than reverting them.
4. The `401` contract must not change: the same status code, the same `detail` strings (`"Authentication required."`, `"Invalid bearer token."`, `"Authentication is unavailable."`), and the same `X-Request-ID` header. No client contract may change.
5. The middleware reads the `Authorization` header and the URL path only. It must never read the request body.
6. `require_principal` must fail **closed**. It must not fall back to resolving credentials when the stashed principal is absent: that would restore two sources of truth and reintroduce the silent-fallback pattern removed elsewhere in this codebase.
7. Authentication must be evaluated before `enforce_request_body_limit`, so an unauthenticated request is rejected without its body being read.
8. `CORSMiddleware` must be registered **last** in `main.py`. Without this the early `401` carries no `access-control-allow-origin` and a browser client cannot read it. This is verified, not assumed.
9. The public allowlist contains `GET /health` and the FastAPI documentation paths, and nothing else. It is a constant, not a setting.
10. No change to the token format, the registry, the hashing, or the status code for a misconfigured registry. No rate limiting, no authentication-failure accounting, and no change to the unauthenticated documentation surface beyond listing it.
11. Behaviour changes use a red-green-refactor cycle. Every task states the failing test first.
12. Never expose secrets, credentials, tokens, or sensitive personal data in code, logs, commands, evidence, or documentation. Test tokens are obvious placeholders, as in the existing suites.
13. **Three observable behaviour changes must be recorded in the Completion Record**: an oversized body and a configuration failure gain CORS headers; those same two paths gain a completion event; and `401` volume will rise for traffic that previously produced `422`.

## Required ADR — prerequisite

| ADR | Title | Status required |
| --- | --- | --- |
| 0026 | Authentication Is Enforced in Middleware, Before the Request Body Is Parsed | Accepted |

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/security/dependencies.py` | Own the public allowlist, `enforce_authentication`, and the fail-closed `require_principal` accessor | ADR 0026 accepted |
| `backend/app/main.py` | Call authentication before the body limit, unify the middleware exits so every one emits an event, register `CORSMiddleware` last | Task 1 |
| `backend/app/api/chat.py` | Correct the docstring that claims an ordering guarantee the framework does not provide | Task 2 |
| `backend/tests/unit/test_auth_enforcement.py` | Prove the allowlist predicate and the fail-closed accessor | Task 1 |
| `backend/tests/integration/test_auth_enforcement_ordering.py` | Prove the reproduced case table, the mounted-route inventory, and preflight | Task 2 |
| `backend/tests/boundaries/test_clean_break_boundaries.py` | Move the no-compatibility-mode assertion to the control's new location; assert the middleware is registered and CORS is outermost | Task 3 |
| `ARCHITECTURE.md`, `docs/architecture/current-state.md`, `SECURITY.md` | Correct any statement about where authentication is enforced or how the middleware is ordered | Task 3 |

**Approved specs and ADRs are historical records and must not be rewritten.** The clean-break specification's statement of the invariant stays as written; this specification and ADR 0026 record the enforcement point it left implicit.

## Task 1: The enforcement point

**Files:**

- Modify: `backend/security/dependencies.py`
- Test: `backend/tests/unit/test_auth_enforcement.py` (create)

**Interfaces:**

- Produces: `is_public_path(path: str) -> bool`; `enforce_authentication(request: Request) -> Optional[JSONResponse]`
- Changes: `require_principal(request: Request) -> AuthenticatedPrincipal` becomes an accessor of `request.state.principal`
- Consumes: `_resolve_authenticated`, `_bearer_token`, and the existing detail constants, all unchanged

- [x] **Step 1: Write the failing tests**

```python
def test_health_is_public():
    assert is_public_path("/health") is True


def test_documentation_paths_are_public():
    for path in ("/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"):
        assert is_public_path(path) is True, path


def test_a_guarded_route_is_not_public():
    for path in ("/api/v1/chat", "/api/v1/conversations", "/api/v1/ops/readiness"):
        assert is_public_path(path) is False, path


def test_a_path_merely_starting_with_a_public_prefix_is_not_public():
    # `/docsomething` must not inherit `/docs`.
    assert is_public_path("/docsomething") is False
    assert is_public_path("/healthz") is False


def test_enforce_authentication_passes_a_public_path_without_resolving():
    request = _request("/health", headers={})
    assert enforce_authentication(request) is None


def test_enforce_authentication_rejects_a_missing_header():
    response = enforce_authentication(_request("/api/v1/chat", headers={}))
    assert response.status_code == 401
    assert json.loads(response.body) == {"detail": "Authentication required."}


def test_enforce_authentication_rejects_an_invalid_token():
    request = _request("/api/v1/chat", headers={"authorization": "Bearer nope"})
    response = enforce_authentication(request)
    assert response.status_code == 401
    assert json.loads(response.body) == {"detail": "Invalid bearer token."}


def test_enforce_authentication_never_reads_the_body():
    """The body must stay unread, or the rejection costs what the fix saves."""
    request = _request("/api/v1/chat", headers={}, body=b'{"message": "hi"')
    assert enforce_authentication(request) is not None
    assert request._body is None, "the middleware must not consume the body"


def test_enforce_authentication_stashes_the_principal():
    request = _request("/api/v1/chat", headers={"authorization": f"Bearer {TOKEN}"})
    assert enforce_authentication(request) is None
    assert request.state.principal.owner_user_id == "alice"


def test_require_principal_fails_closed_without_the_middleware():
    with pytest.raises(HTTPException) as excinfo:
        require_principal(_request("/api/v1/chat", headers={}))
    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == "Authentication is unavailable."


def test_require_principal_reads_the_stashed_principal():
    request = _request("/api/v1/chat", headers={"authorization": f"Bearer {TOKEN}"})
    enforce_authentication(request)
    assert require_principal(request).owner_user_id == "alice"


def test_enforce_authentication_returns_500_when_the_registry_is_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_AUTH_TOKENS_JSON", SecretStr(""))
    response = enforce_authentication(
        _request("/api/v1/chat", headers={"authorization": f"Bearer {TOKEN}"})
    )
    assert response.status_code == 500
    assert json.loads(response.body) == {"detail": "Authentication is unavailable."}
```

- [x] **Step 2: Run verification**

Run: `pytest backend/tests/unit/test_auth_enforcement.py -q`

Expected: FAIL on import — `is_public_path` and `enforce_authentication` do not exist.

- [x] **Step 3: Implement**

```python
# The complete public surface. A path is reachable without credentials only if it
# is listed here; there is no pattern that makes one public implicitly.
#
# `GET /health` must stay open: a liveness probe that requires a token cannot
# report an authentication outage. The documentation paths are public today and
# are listed so the exemption is deliberate and reviewable rather than an
# accident of the framework's defaults. Closing them is a separate decision.
_PUBLIC_PATHS = frozenset({"/health"})
_PUBLIC_PATH_PREFIXES = ("/docs", "/redoc", "/openapi.json")


def is_public_path(path: str) -> bool:
    """Return whether `path` is reachable without credentials."""
    if path in _PUBLIC_PATHS:
        return True
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in _PUBLIC_PATH_PREFIXES
    )


def enforce_authentication(request: Request) -> Optional[JSONResponse]:
    """Authenticate ahead of routing, or return the rejection to send.

    Returns `None` to continue. Never reads the body: it inspects the
    `Authorization` header and the URL path only, which is what makes the
    rejection cheaper than the request it refuses.
    """
    if is_public_path(request.url.path):
        return None
    try:
        principal = _resolve_authenticated(_bearer_token(request))
    except HTTPException as error:
        return JSONResponse(
            status_code=error.status_code, content={"detail": error.detail}
        )
    request.state.principal = principal
    return None


def require_principal(request: Request) -> AuthenticatedPrincipal:
    """Return the principal resolved by `enforce_authentication`.

    Fails closed when it is absent: that means the middleware did not run, which
    is a wiring defect. Resolving credentials here instead would restore a second
    source of truth and let a mis-wired stack silently authenticate.
    """
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=500, detail=_CONFIG_FAILED_DETAIL)
    return principal
```

- [x] **Step 4: Run verification**

Run: `pytest backend/tests/unit/test_auth_enforcement.py -q`

Expected: PASS.

- [x] **Step 5: Review checkpoint**

Review: the allowlist predicate and its tests, and the accessor. Confirm no body read, that the detail strings are the existing constants and not new literals, that the accessor contains no fallback path, and that the allowlist is a constant rather than a setting.

Expected: the unit module passes and the fail-closed case returns `500` rather than resolving credentials.

## Task 2: The pipeline

**Files:**

- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_auth_enforcement_ordering.py` (create)

**Interfaces:**

- Consumes: `enforce_authentication` from Task 1
- Produces: a stack ordered CORS → correlation → authentication → router, and one completion event per request on every exit path

- [x] **Step 1: Write the failing tests**

The case table is the finding. Each row must be asserted explicitly, because the defect was that two rows returned the same status for different reasons.

```python
CASES = [
    # (label, path, body, headers, expected_status)
    ("malformed body, no header", CHAT, MALFORMED, {}, 401),
    ("malformed body, invalid token", CHAT, MALFORMED, BAD, 401),
    ("malformed body, valid token", CHAT, MALFORMED, GOOD, 422),
    ("valid body, no header", CHAT, VALID, {}, 401),
    ("wrong-shape body, no header", CHAT, WRONG_SHAPE, {}, 401),
    ("malformed body, no header (conversations)", CONVERSATIONS, MALFORMED, {}, 401),
    ("oversized body, no header", CHAT, OVERSIZED, {}, 401),
    ("oversized body, valid token", CHAT, OVERSIZED, GOOD, 413),
]


@pytest.mark.parametrize("label,path,body,headers,expected", CASES)
def test_status_case_table(label, path, body, headers, expected):
    assert _post(path, body, headers).status_code == expected, label


def test_an_unauthenticated_rejection_carries_cors_headers():
    response = _post(CHAT, VALID, {}, origin=True)
    assert response.status_code == 401
    assert response.headers.get("access-control-allow-origin") == ORIGIN


def test_an_unauthenticated_rejection_carries_a_request_id():
    response = _post(CHAT, VALID, {})
    assert response.headers["X-Request-ID"].startswith("rq_")


def test_a_preflight_request_is_not_answered_401():
    response = client.options(CHAT, headers={
        "Origin": ORIGIN,
        "Access-Control-Request-Method": "POST",
    })
    assert response.status_code != 401


def test_every_guarded_route_rejects_an_unauthenticated_request():
    """Default-deny, over the mounted table rather than a written list.

    A route added later is covered without anyone remembering to guard it.
    """
    mounted = _mounted_api_paths(app)
    assert mounted, "the route inventory must not be empty"
    for path in mounted:
        if is_public_path(path):
            continue
        assert _request_without_credentials(app, path).status_code == 401, path


def test_every_public_path_is_reachable_without_credentials():
    """The allowlist must match reality, or a rename silently closes /health."""
    for path in ("/health", "/openapi.json"):
        assert _get_without_credentials(app, path).status_code != 401, path


def test_the_documentation_paths_are_still_reachable():
    for path in ("/docs", "/redoc"):
        assert _get_without_credentials(app, path).status_code == 200, path
```

- [x] **Step 2: Run verification**

Run: `pytest backend/tests/integration/test_auth_enforcement_ordering.py -q`

Expected: FAIL on the first two rows of the case table (`422` where `401` is required) and on the CORS row.

- [x] **Step 3: Wire the middleware and unify its exits**

Call authentication before the body limit, and route every exit through one tail so each emits an event. Today the two early returns emit nothing, which is why an unauthenticated rejection would otherwise be invisible.

```python
@app.middleware("http")
async def request_correlation_middleware(request: Request, call_next):
    request_id = generate_request_id()
    token = set_request_id(request_id)
    request.scope["r9.request_id"] = request_id
    start = time.perf_counter()
    try:
        # Authentication first: an unauthenticated request must be refused
        # without its body being read, so this precedes the size check.
        response = enforce_authentication(request)
        if response is None:
            try:
                response = await enforce_request_body_limit(request)
            except SecurityConfigurationError as error:
                logger.error(
                    "security.request rejected failure_class=%s",
                    type(error).__name__,
                )
                response = JSONResponse(
                    status_code=500,
                    content={"detail": "Request rejected.", "request_id": request_id},
                )
        if response is None:
            response = await call_next(request)
    except Exception as error:
        try:
            emit_event(
                EventName.API_REQUEST_COMPLETED,
                EventComponent.API,
                EventResult.FAILURE,
                counters={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                },
                failure_class=type(error).__name__,
                reason_code="unhandled_exception",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        finally:
            reset_request_id(token)
        raise

    # One tail for every exit, including the early rejections. Previously the
    # 413 and configuration-500 returned before this point and emitted nothing.
    status_code = response.status_code
    if status_code < 400:
        result, severity, reason = EventResult.SUCCESS, EventSeverity.INFO, "ok"
    elif status_code < 500:
        result, severity, reason = (
            EventResult.FAILURE, EventSeverity.WARNING, "http_client_error",
        )
    else:
        result, severity, reason = (
            EventResult.FAILURE, EventSeverity.ERROR, "http_server_error",
        )
    response.headers["X-Request-ID"] = request_id
    try:
        emit_event(
            EventName.API_REQUEST_COMPLETED,
            EventComponent.API,
            result,
            severity=severity,
            counters={
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
            },
            reason_code=reason,
            duration_ms=(time.perf_counter() - start) * 1000,
        )
    except Exception as error:
        logger.warning(
            "observability.emit failed failure_class=%s", type(error).__name__
        )
    finally:
        reset_request_id(token)
    return response
```

- [x] **Step 4: Register `CORSMiddleware` last**

Move the existing `app.add_middleware(CORSMiddleware, ...)` call to **after** the
correlation middleware definition, leaving every argument unchanged. Starlette
inserts each middleware at position 0, so the last one registered is outermost;
with the current order the correlation middleware is outside CORS and its early
responses carry no CORS headers. Add a comment recording why the position
matters, because moving it back would silently restore the defect.

- [x] **Step 5: Run verification**

Run: `pytest backend/tests/integration/test_auth_enforcement_ordering.py -q`

Expected: PASS, all rows of the case table.

- [x] **Step 6: Run the existing suites that touch authentication**

Run: `pytest backend/tests/integration backend/tests/unit -q`

Expected: PASS. Any module that breaks must be named and its reason recorded — do not adjust a test to fit the implementation without saying so. `test_local_token_auth.py` exercises the resolver directly and is expected to be unaffected; `test_auth_api.py`, `test_security_error_handling.py`, `test_chat_conversation_binding.py::test_invalid_bearer_token_chat_returns_401` and `test_conversation_api.py::test_invalid_bearer_token_returns_401` all go through the client and must still see `401` with the same detail.

- [x] **Step 7: Review checkpoint**

Review: the middleware function, the `CORSMiddleware` position, and the case-table results. Confirm the body limit is still enforced for an authenticated oversized request (`413`), that the correlation id is still bound and reset on every path, that no `401` body carries a path or a token, and that the allowlist was not widened to make a test pass.

Expected: the case table passes; `413` and `500` now emit an event; no response body changed except in the two rows the finding is about.

## Task 3: Move the assertion, correct the record

**Files:**

- Modify: `backend/tests/boundaries/test_clean_break_boundaries.py`
- Modify: `backend/app/api/chat.py`
- Modify: `ARCHITECTURE.md`, `docs/architecture/current-state.md`, `SECURITY.md` (only where a statement is now false)

- [x] **Step 1: Move the no-compatibility-mode assertion**

`backend/tests/boundaries/test_clean_break_boundaries.py:360-368` calls
`require_principal(request)` directly and asserts `401`. After Task 1 that call
returns `500`, because the control it was testing now lives in
`enforce_authentication`. The assertion is **moved, not deleted**: assert that
`enforce_authentication` returns a `401` for a request with no credentials, and
keep the existing AST check over `require_principal`'s body.

Add two boundary assertions that did not exist before:

- the application registers the authentication middleware, so a future edit
  cannot drop it;
- `CORSMiddleware` is registered last, because the early `401` is unreadable by a
  browser otherwise and nothing else would catch the reordering.

- [x] **Step 2: Correct the false docstring**

`backend/app/api/chat.py` claims `require_principal` is declared first "so an
unauthenticated request is rejected with `401` before any storage, RAG, or memory
dependency is constructed". The second half is now true for a different reason
and the stated mechanism was never true. Replace it with what actually holds:
enforcement is in the middleware, ahead of routing, and the dependency reads the
principal the middleware resolved.

- [x] **Step 3: Sweep the current-state documents**

Grep `ARCHITECTURE.md`, `docs/architecture/current-state.md` and `SECURITY.md`
for statements about where authentication is enforced, the middleware order, or
the public surface. Correct any that are now false and record which changed.
**Do not rewrite `docs/specs/` or `docs/adr/`** — those are historical records of
what was decided at the time.

- [x] **Step 4: Run verification**

Run: `pytest backend/tests/boundaries -q` then `pytest backend/tests/unit backend/tests/boundaries -q`

Expected: PASS. Report the exact count.

- [x] **Step 5: Review checkpoint**

Review: the boundary test diff, the docstring, and the document sweep. Confirm the moved assertion is strictly stronger than the one it replaced rather than weaker, that the new ordering assertion actually fails if CORS is moved back, and that no approved specification or ADR was edited.

Expected: the boundary suite passes; the moved assertion still fails if `enforce_authentication` is made permissive.

## Package Verification

Run in this order on the exact final worktree state:

1. `pytest backend/tests/unit backend/tests/boundaries` — expect pass, zero errors
2. `PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… pytest backend/tests/integration` — expect zero skips
3. `cd frontend && npx vitest run` — expect pass
4. The reproduced case table, printed as a table, before and after: `malformed body + no header`, `malformed body + invalid token`, `valid body + no header`, `wrong-shape body + no header`, `malformed body + no header (conversations)`
5. A preflight `OPTIONS` request to `/api/v1/chat` with an `Origin` header — expect not `401`
6. The mounted-route inventory test — expect every non-allowlisted path to reject an unauthenticated request
7. `grep -n "add_middleware" backend/app/main.py` — expect `CORSMiddleware` to appear **after** the correlation middleware definition
8. A load-bearing check: move `CORSMiddleware` back above the middleware definition and confirm the CORS assertion fails, then restore. Report the result.
9. `git status --short --untracked-files=all` — compare against the approved change set, including untracked file contents

Report actual output, exit status, and every check that could not run. Checks 4,
5 and 6 require the application to import, which it now does without the model
stack; if that changes, it is a limitation to disclose, not a pass.

## Rollback

1. Revert `backend/app/main.py` to restore the previous middleware order and the
   previous early-return behaviour.
2. Revert `backend/security/dependencies.py` to restore the resolving
   `require_principal`.
3. Revert the boundary test, the docstring, and the document sweep.

Nothing in this change writes data, so there is no irreversible effect and no
data repair. No step requires a destructive Git operation.

## Completion Record

| Field | Value |
| --- | --- |
| Specification approval | **Approved 2026-09-11** — `docs/specs/2026-09-11-authentication-enforcement-ordering-design.md` v0.1, repository owner. |
| ADR 0026 acceptance | **Accepted 2026-09-11** — `docs/adr/0026-authentication-enforced-in-middleware-before-body-parsing.md`. |
| Plan approval | **Approved 2026-09-11** — repository owner, with the explicit instruction to implement immediately. |
| Execution | **Complete — Tasks 1, 2 and 3 implemented.** |
| Verification | **Run on the final worktree state.** All nine package checks pass, with the limitations below disclosed rather than smoothed over. |
| Delivery gate | Repository owner only. No Git delivery is authorized by this plan. |

**Checked where evidence exists.** The 17 step checkboxes are ticked only because the evidence below exists.

### Per-task status

| Task | Implemented | Verified | Evidence |
| --- | --- | --- | --- |
| 1 — The enforcement point | Yes | **Yes** | `backend/tests/unit/test_auth_enforcement.py` → **15 passed**. Includes the allowlist predicate, the anchored-prefix cases, both rejection details, the unconfigured and duplicate-token registries, the no-body-read assertion, and the fail-closed accessor. |
| 2 — The pipeline | Yes | **Yes** | `backend/tests/integration/test_auth_enforcement_ordering.py` → **24 passed**. The case table, CORS headers, the request id, preflight, the mounted-route inventory, the unknown-path case, the body-limit interaction, and the event emission. |
| 3 — Move the assertion, correct the record | Yes | **Yes** | `backend/tests/boundaries` → **8 passed** (was 6). The moved assertion plus two new boundary checks. |

### The case table — the finding, before and after

| Request | Before | After |
| --- | --- | --- |
| malformed body, no header | **422** | **401** |
| malformed body, invalid token | **422** | **401** |
| malformed body, valid token | 422 | 422 |
| valid body, no header | 401 | 401 |
| wrong-shape body, no header | 401 | 401 |
| malformed body, no header (`/conversations`) | **422** | **401** |

Exactly three rows changed, and each is a row where the authentication decision was previously skipped. The `422` for an authenticated malformed body is unchanged, which is the control.

### Package verification — actual results

| # | Check | Result |
| --- | --- | --- |
| 1 | `pytest backend/tests/unit backend/tests/boundaries` | **Could not run as one command** — see limit 1. Run separately: unit **792 passed**, boundaries **8 passed**, 0 failures. |
| 2 | `pytest backend/tests/integration` | **160 passed, 0 failed, 0 skipped** (was 136; +24) |
| 3 | `cd frontend && npx vitest run` | **28 passed (3 files)** |
| 4 | The case table | 3 rows changed `422` → `401`; the rest unchanged |
| 5 | Preflight `OPTIONS` | **200** with `access-control-allow-origin`, not `401` |
| 6 | Mounted-route inventory | every non-allowlisted API route returns `401` without credentials; every allowlisted path is reachable |
| 7 | `grep -n "add_middleware" backend/app/main.py` | `@app.middleware("http")` at line 112, `app.add_middleware` at line 233 — CORS registered last |
| 8 | Load-bearing check | moving `CORSMiddleware` back above the middleware makes **3 tests fail**; restored → 3 passed |
| 9 | `git status --short --untracked-files=all` | nothing staged or committed; no Git delivery |

The change set matches the File Responsibility Map exactly: five modified application/test/doc files, three modified index files, and five new files (two test modules, the spec, the plan, the ADR).

### Load-bearing proofs recorded

1. **The middleware ordering.** Moving the `CORSMiddleware` registration back above the correlation middleware fails three tests: the boundary ordering check, the CORS-header assertion on the early `401`, and the preflight assertion. Restored → green. Without this proof the reordering would be an unverified claim about framework internals.
2. **The fail-closed accessor.** `test_authentication_has_no_compatibility_mode` asserts that `require_principal` raises `500` when no principal was stashed, alongside the `401` from `enforce_authentication`. If the accessor could resolve credentials itself, deleting the middleware would go unnoticed — that is what makes the enforcement point load-bearing rather than decorative.
3. **The unauthenticated request never reads its body.** Asserted directly, and implied by the ordering check that `enforce_authentication` is called before `enforce_request_body_limit`.

### Tests changed, named rather than quietly adjusted

`test_require_principal_has_no_compatibility_mode` in `backend/tests/boundaries/test_clean_break_boundaries.py` was **renamed and rewritten** as `test_authentication_has_no_compatibility_mode`. Its runtime assertion moved from `require_principal` (which now returns `500`) to `enforce_authentication` (which returns the `401`), and its AST check now covers both functions. **The assertion was moved, not weakened**: the `401` is still asserted at the control's location, and a new assertion that the accessor fails closed was added. No other existing assertion was altered.

### Deviations from the approved plan

1. **`docs/architecture/current-state.md` needed no correction.** The File Responsibility Map listed it "only where a statement is now false". The sweep found **no current-state document containing a statement this change makes false** — the reverse is true: `SECURITY.md`'s claim that "unauthenticated requests immediately return a content-free `401`" and `ARCHITECTURE.md`'s claim that "all product routes strictly enforce Bearer authentication" were false before this change and are now true. The file is therefore unmodified.
2. **Two documents gained a positive statement** beyond correcting false ones: `SECURITY.md` control 1 and `ARCHITECTURE.md`'s security-boundary row and sequence line now name the enforcement layer. The plan's step said "correct any statement"; the enforcement location is a newly decided architectural fact with no existing statement, so the smallest useful thing was to record it where a reader looks first.
3. **A behaviour change the specification did not name, discovered during implementation.** An unauthenticated request to a path that matches **no** route now returns `401` rather than `404`, because default-deny is evaluated before routing. This further closes the route-enumeration oracle — an unauthenticated caller can no longer distinguish a real path from a fictional one — but it is a response change the approved specification did not list. A test pins it so it is deliberate.
4. **The route inventory enumerates through `app.openapi()`.** `app.routes` cannot be walked directly in this FastAPI version: an included router appears as `_IncludedRouter` with `path=None`. The OpenAPI schema is how the existing boundary suite already reads the mounted surface, so the inventory reuses it rather than reaching into a private attribute.
5. **Task 3's checkpoint condition on the boundary test was met by a rename plus an addition**, not by a same-name edit, because the function's name described a control that moved.

### Limits — disclosed, not claimed as passing

1. **`pytest backend/tests/unit backend/tests/boundaries` cannot complete as a single command in this environment.** The combined run reports **695 passed and 105 setup ERRORs**, every traceback inside the host's own safe-delete shim (`SAFE_DELETE_BULK_CONFIRM_REQUIRED {"count":50,"threshold":50}`), which refuses pytest's `tmp_path` churn. The same tests pass when the two directories are run separately (**792** and **8**). This is an environment artefact and is not a regression; it is disclosed because the plan named the combined command.
2. **No reverse proxy was tested.** Behaviour behind a proxy that terminates, rewrites, or strips the `Authorization` header was not exercised. The failure mode is a blanket `401`, which is fail-closed, but it is reasoned rather than reproduced.
3. **The alert-volume consequence is reasoned, not observed.** No alerting system is configured, so the claim that a `401`-based signal will begin firing on malformed-body traffic was not measured against one. The `401` emission itself is verified by test.
4. **The two newly-emitting paths have an unmeasured downstream effect.** An oversized body and a configuration failure now write a completion event where they previously wrote none. That is verified by test; whether it disturbs any log-volume budget or retention assumption is not, because no such budget exists in this repository.
5. **The token comparison cost is asserted, not benchmarked.** `require_principal` no longer re-resolves, so an authenticated request performs the same number of comparisons as before and an unauthenticated one performs fewer, because the body is no longer read. No timing was measured; the reasoning is structural.
6. **The public allowlist was not widened to make a test pass.** It contains `GET /health` and the documentation paths, and `test_the_route_inventory_is_not_vacuous` guards against an inventory that would pass trivially.
7. **No Git delivery was performed.** Nothing was staged or committed.
