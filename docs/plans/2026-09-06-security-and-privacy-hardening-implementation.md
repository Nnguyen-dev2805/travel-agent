# Security and Privacy Hardening Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence.

**Goal:** Build the R9 local security/privacy boundary so authenticated local
principals, owner authorization, deletion semantics, controlled failures, and
security evaluation are reviewable before open-source release work.

**Architecture:** `backend/security/` owns local identity and authorization
contracts. Product routes resolve a principal through FastAPI dependencies and
authorize workspace ownership before exposing state. Deletion is coordinated
through service/repository interfaces and verified by a local security
evaluation report.

**Tech Stack:** Python 3.11+, FastAPI dependencies/middleware, Pydantic,
standard-library `json`, `hmac`, `secrets`, `sqlite3`, `pathlib`, pytest,
existing R8 observability events, existing docs report pattern.

**Spec:** [Security and Privacy Hardening Design](../specs/2026-09-06-security-and-privacy-hardening-design.md), version 0.2 (Approved)

| Field | Value |
| --- | --- |
| Status | In Progress |
| Plan version | 0.3 |
| Date | 2026-09-06 |
| Approved specification | [Security and Privacy Hardening Design](../specs/2026-09-06-security-and-privacy-hardening-design.md), version 0.2, approved by repository owner on 2026-09-06 |
| Governing ADRs | [ADR 0010](../adr/0010-local-identity-authorization-and-deletion-boundary.md) (Accepted) |
| Plan approval | Approved by repository owner on 2026-09-06 |
| Execution owner | Implementation worker agent in an isolated worktree |
| Decision owner | Repository owner |
| Scope | Runtime milestone R9 - local auth, authorization, deletion/tombstones, safe HTTP 500, request-size limit, CORS auth guard, security evaluation, refreshed memory hard-gate evidence, tests, reports, and docs |
| Verification | `./.venv/bin/python -m pytest backend/tests`, `./.venv/bin/python -m compileall backend`, `AUTH_REQUIRED=true LOCAL_AUTH_TOKENS_JSON='{"owner_a":"secret-alpha-token","owner_b":"secret-beta-token"}' ./.venv/bin/python -m backend.security.evaluation.cli run-security --suite r9-security-privacy-v0.1`, refreshed memory gate evidence, privacy/security grep checks, import-boundary checks, `git diff --check`, `git status --short --untracked-files=all` |

## Approval Gate

Do not implement this plan until all are true:

1. ADR 0010 is accepted.
2. R9 spec version 0.2 is approved.
3. This implementation plan version 0.3 is approved.
4. The selected implementation base includes accepted R8 work, or a later
   repository-owner selected base.

## Global Constraints

1. R9 is backend-only.
2. Add no OAuth, OIDC, hosted identity provider, frontend UI, production
   deployment, TLS termination, WAF, external auth provider, cloud secret
   manager, external telemetry vendor, hard deletion, or release claim.
3. Token values, environment values, prompts, messages, retrieved chunk text,
   memory text, itinerary text, decision statements, provider payloads, SQL,
   raw filesystem paths, stack traces, and arbitrary exception strings must not
   appear in logs, responses, readiness, or R9 reports.
4. `AUTH_REQUIRED=false` preserves local compatibility; `AUTH_REQUIRED=true`
   must fail closed and require a valid local bearer token for protected routes.
5. Caller-supplied owner labels are not authority when auth is enabled.
6. Cross-owner ids must not reveal existence across owners.
7. Deleted or deletion-requested memory must never be selected for answers.
8. Deletion transitions must use fail-closed ordering: mark the workspace
   `deletion_requested` first, deny normal access immediately, then perform
   idempotent child transitions. Confirmation must not claim completion until
   workspace-scoped child transitions are verified.
9. Tests must use temporary paths, synthetic users, and synthetic tokens.
10. R9 fixtures and reports must live under tracked `docs/` paths. Delivered
    reports from earlier milestones are historical evidence and must not be
    overwritten; a refreshed suite gets its own `dataset_id`.
11. R9 security evaluation and refreshed memory hard-gate evidence must run with
    `AUTH_REQUIRED=true`; if the auth gate or synthetic token registry is not
    valid, the report state is `INVALID`, not `PASS`.
12. The synthetic token strings in this plan appear in the privacy sentinel
    pattern on purpose. Sentinel checks therefore scope to report directories
    only; widening them to `docs/` would match this plan and its own commands.
13. Git staging, commit, push, PR, merge, release, and destructive cleanup remain
    repository-owner actions unless explicitly requested.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/security/__init__.py` | Stable security package exports | R9 security modules |
| `backend/security/models.py` | `AuthenticatedPrincipal`, auth mode, and security error contracts | Standard library/Pydantic |
| `backend/security/local_tokens.py` | Parse local token registry and compare bearer tokens safely | Settings, security models |
| `backend/security/dependencies.py` | FastAPI principal resolution and protected-route helpers | FastAPI, local token registry |
| `backend/security/authorization.py` | Owner/workspace authorization helpers | Workspace service/repository interfaces |
| `backend/privacy/__init__.py` | Stable privacy package exports | R9 deletion modules |
| `backend/privacy/deletion.py` | Workspace deletion request/confirmation orchestration | Workspace, conversation, memory, planner repositories |
| `backend/app/config.py` | R9 auth, CORS, and request-size settings | Environment variables |
| `.env.example` | Safe placeholder documentation for R9 environment variables | R9 settings |
| `backend/app/main.py` | Request-size middleware, safe 500 handler, and auth-aware CORS guard | R8 observability, security settings |
| `backend/app/api/workspaces.py` | Apply principal authorization and deletion endpoints | Security dependencies, deletion service |
| `backend/app/api/conversations.py` | Require workspace ownership before conversation reads/writes | Security authorization |
| `backend/app/api/memory.py` | Require workspace ownership and hide deleted scopes | Security authorization |
| `backend/app/api/planner.py` | Require workspace ownership and hide deleted scopes | Security authorization |
| `backend/app/api/chat.py` | Require auth when enabled and authorize bound conversation access | Security dependencies |
| `backend/app/api/ops.py` | Protect readiness when auth is enabled except liveness remains `/health` | Security dependencies |
| `backend/workspaces/repository.py` | Add lifecycle transition methods | Workspace models |
| `backend/workspaces/sqlite_repository.py` | Persist workspace deletion transitions | Schema registry |
| `backend/workspaces/service.py` | Expose deletion-aware workspace operations | Workspace repository |
| `backend/conversations/repository.py` | Add workspace-scoped retention transition/list hiding methods | Conversation models |
| `backend/conversations/sqlite_repository.py` | Persist conversation deletion transitions | Schema registry |
| `backend/conversations/service.py` | Reject operations under deleted workspaces | Workspace/conversation repositories |
| `backend/memory/repository.py` | Add workspace-scoped memory deletion transition methods | Memory models |
| `backend/memory/sqlite_repository.py` | Persist memory deletion transitions and keep retrieval filters strict | Schema registry |
| `backend/memory/retrieval.py` | Prove deleted/deletion-requested records are never selected | Memory repository |
| `backend/planner/repository.py` | Add workspace deletion visibility helpers if required | Planner models |
| `backend/planner/sqlite_repository.py` | Hide planner state for deleted workspaces | Planner repository |
| `backend/security/evaluation/__init__.py` | Evaluation package exports | R9 evaluation |
| `backend/security/evaluation/models.py` | R9 result-state and gate contracts | D5 vocabulary |
| `backend/security/evaluation/runner.py` | Deterministic security/privacy evaluation | Security, privacy, repositories |
| `backend/security/evaluation/cli.py` | `run-security` CLI command | Evaluation runner |
| `backend/tests/unit/test_security_models.py` | Security model tests | Security contracts |
| `backend/tests/unit/test_local_token_auth.py` | Token parsing/comparison tests | Local token registry |
| `backend/tests/unit/test_authorization.py` | Owner/workspace authorization tests | Authorization helpers |
| `backend/tests/unit/test_privacy_deletion.py` | Deletion orchestration tests | Privacy service |
| `backend/tests/unit/test_security_evaluation_runner.py` | R9 report tests | Evaluation runner |
| `backend/tests/integration/test_auth_api.py` | Protected route auth behavior | FastAPI app |
| `backend/tests/integration/test_cross_owner_isolation.py` | Workspace/conversation/memory/planner cross-owner gates | FastAPI app |
| `backend/tests/integration/test_deletion_api.py` | Deletion route and tombstone behavior | FastAPI app |
| `backend/tests/integration/test_security_error_handling.py` | Safe 500 and request-size behavior | FastAPI app |
| `docs/evaluation/fixtures/security/r9-security-privacy-v0.1/manifest.json` | Security fixture manifest | R9 evaluation design |
| `docs/evaluation/fixtures/security/r9-security-privacy-v0.1/examples.jsonl` | Synthetic security scenarios | R9 evaluation design |
| `docs/reports/security/r9-security-privacy-v0.1.json` | Machine-readable R9 report | R9 evaluation run |
| `docs/reports/security/r9-security-privacy-v0.1.md` | Human-readable R9 report | R9 evaluation run |
| `docs/evaluation/fixtures/memory/r6-retrieval-v0.2/manifest.json` | Refreshed memory fixture manifest carrying `dataset_id` `r6-retrieval-v0.2` so reports never overwrite the R6 baseline | R6 fixture, R9 auth and deletion behavior |
| `docs/evaluation/fixtures/memory/r6-retrieval-v0.2/examples.jsonl` | Synthetic authenticated cross-owner and deletion cases | R6 fixture, R9 auth and deletion behavior |
| `docs/reports/memory/r6-retrieval-v0.2.json` | Refreshed memory hard-gate evidence with authenticated identity and deletion | R9 evaluation run |
| `docs/reports/memory/r6-retrieval-v0.2.md` | Human-readable refreshed memory hard-gate evidence | R9 evaluation run |
| `SECURITY.md` | Updated security policy current state after R9 | Implemented behavior |
| `ARCHITECTURE.md` | Updated trust boundaries and remaining blockers | Implemented behavior |
| `DEVELOPMENT.md` | Local auth/deletion/test commands | Implemented behavior |
| `docs/architecture/current-state.md` | Implemented R9 architecture state | Implemented behavior |
| `docs/architecture/data-model.md` | Deletion lifecycle semantics | Implemented behavior |
| `docs/runbooks/deployment.md` | Public-production gate truth after R9 | Implemented behavior |
| `docs/runbooks/incident-response.md` | Auth/deletion incident evidence | Implemented behavior |
| `docs/roadmap/master-roadmap.md` | R9 status and evidence | Owner review and verification |
| `docs/plans/README.md` | Plan index status | This plan |
| `docs/specs/README.md` | Spec index status | R9 spec |
| `docs/adr/README.md` | ADR index status | ADR 0010 |

## Task 1: Preflight and Governance Gate

**Files:**

- Read: `AGENTS.md`
- Read: `SECURITY.md`
- Read: `ARCHITECTURE.md`
- Read: `docs/specs/2026-09-06-security-and-privacy-hardening-design.md`
- Read: `docs/adr/0010-local-identity-authorization-and-deletion-boundary.md`
- Read: `docs/plans/2026-09-06-security-and-privacy-hardening-implementation.md`
- Modify: `docs/plans/2026-09-06-security-and-privacy-hardening-implementation.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/roadmap/master-roadmap.md`

**Interfaces:**

- Consumes: owner approvals for ADR 0010, R9 spec v0.2, and this plan v0.3.
- Produces: implementation worktree with documented base commit and R9 plan
  state moved to `In Progress`.

- [x] **Step 1: Confirm implementation base**

Run:

```text
git status --short --branch --untracked-files=all
git log --oneline -8
```

Expected: implementation worktree is clean and includes accepted R8 work, or the
repository-owner selected later base.

- [x] **Step 2: Confirm approval gates**

Expected headers:

```text
ADR 0010: Accepted
R9 spec v0.2: Approved
R9 plan v0.3: Approved
```

Stop if any value is missing.

- [x] **Step 3: Move R9 docs into implementation state**

Update this plan status to `In Progress`, update `docs/plans/README.md`, and
update roadmap `R9` from `Blocked by gate` to `In progress`.

- [x] **Step 4: Run baseline tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests
```

Expected: pass, or disclose exact known non-R9 external/environment failures
before changing source.

- [x] **Step 5: Review checkpoint**

Review: approval gates, base commit, clean status, and R9 status edits.

Expected: no source change has started before gates are satisfied.

## Task 2: Security Contracts and Local Token Registry

**Files:**

- Create: `backend/security/__init__.py`
- Create: `backend/security/models.py`
- Create: `backend/security/local_tokens.py`
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Test: `backend/tests/unit/test_security_models.py`
- Test: `backend/tests/unit/test_local_token_auth.py`

**Interfaces:**

- Consumes: R9 auth settings from the spec.
- Produces: `AuthenticatedPrincipal`, `AuthMode`, `SecurityConfigurationError`,
  `AuthenticationError`, `parse_local_token_registry(raw: str)`,
  `resolve_local_principal(token: str, registry: Mapping[str, str])`.

- [x] **Step 1: Write failing security model tests**

Cover valid principal construction, blank owner rejection, credential label
validation, and enum values `authenticated` and `compatibility`.

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_security_models.py -q
```

Expected: fail because `backend.security` does not exist.

- [x] **Step 2: Write failing local token tests**

Cover:

```text
valid JSON registry maps owner ids to tokens
blank owner id is rejected
blank token is rejected
malformed JSON is rejected without echoing raw input
valid token resolves the correct owner
invalid token raises AuthenticationError
duplicate token values are rejected
```

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_local_token_auth.py -q
```

Expected: fail because token registry code does not exist.

- [x] **Step 3: Implement minimal contracts**

Implement immutable models and parsing helpers. Use `hmac.compare_digest` for
token comparison. Error messages must not include token values or raw JSON.

- [x] **Step 4: Add settings**

Add:

```python
AUTH_REQUIRED: bool = _env_flag("AUTH_REQUIRED", False)
LOCAL_AUTH_TOKENS_JSON: str = os.getenv("LOCAL_AUTH_TOKENS_JSON", "{}")
MAX_REQUEST_BODY_BYTES: int = int(os.getenv("MAX_REQUEST_BODY_BYTES", "1048576"))
ALLOWED_CORS_ORIGINS: str = os.getenv(
    "ALLOWED_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
```

Validate that `MAX_REQUEST_BODY_BYTES > 0` in security/config code or tests.
Ensure settings representation, readiness output, logs, and errors never include
`LOCAL_AUTH_TOKENS_JSON` or token values. Append the four R9 variables to the
existing `.env.example` with safe placeholder values only; do not rewrite the
file, because it already documents `GITHUB_TOKEN`, `LLM_MODEL`, `VITE_API_URL`,
and the R6 memory flags.

- [x] **Step 5: Run focused tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_security_models.py backend/tests/unit/test_local_token_auth.py -q
```

Expected: pass.

- [x] **Step 6: Review checkpoint**

Review: token values are never logged, returned, or included in exception
messages; settings representation does not expose `LOCAL_AUTH_TOKENS_JSON`;
low-level security modules import no product services.

Expected: security contracts are standalone and deterministic.

## Task 3: FastAPI Auth Dependencies, CORS Guard, and Request-size Limit

**Files:**

- Create: `backend/security/dependencies.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_auth_api.py`
- Test: `backend/tests/integration/test_security_error_handling.py`

**Interfaces:**

- Consumes: Task 2 security contracts and settings.
- Produces: `get_optional_principal`, `require_principal`, request-size
  middleware, auth-aware CORS validation, and a protected-readiness policy.

- [x] **Step 1: Write failing auth API tests**

Cover:

```text
AUTH_REQUIRED=false allows existing local /health and product behavior
AUTH_REQUIRED=true rejects missing Authorization on protected route with 401
AUTH_REQUIRED=true rejects invalid bearer token with 401
AUTH_REQUIRED=true accepts valid bearer token
/health remains available without auth
```

Run:

```text
./.venv/bin/python -m pytest backend/tests/integration/test_auth_api.py -q
```

Expected: fail because auth dependencies are not wired.

- [x] **Step 2: Write failing request-size/CORS tests**

Cover oversized request returns `413` with controlled detail; wildcard CORS is
rejected or narrowed when `AUTH_REQUIRED=true`; malformed auth configuration
does not silently enter compatibility mode.

Run:

```text
./.venv/bin/python -m pytest backend/tests/integration/test_security_error_handling.py -q
```

Expected: fail for missing request-size behavior.

- [x] **Step 3: Implement dependencies and middleware**

Implement bearer parsing, compatibility principal fallback when auth is disabled,
request-size middleware using `Content-Length` and safe body rejection, and CORS
origin parsing that fails closed for wildcard origins when auth is enabled.
Protect `/api/v1/ops/readiness` when `AUTH_REQUIRED=true`; keep `/health`
unauthenticated. If the token registry is malformed, readiness is unavailable
through the route and operators must use `/health` plus privacy-safe logs.

- [x] **Step 4: Run focused tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests/integration/test_auth_api.py backend/tests/integration/test_security_error_handling.py -q
```

Expected: pass.

- [x] **Step 5: Review checkpoint**

Review: `/health` remains compatible, protected routes can require auth, token
values are absent from logs/responses, and request-size rejection is content-free.

Expected: auth shell exists without product authorization claims yet.

## Task 4: Owner Authorization Across Product Routes

**Files:**

- Create: `backend/security/authorization.py`
- Modify: `backend/app/api/workspaces.py`
- Modify: `backend/app/api/conversations.py`
- Modify: `backend/app/api/memory.py`
- Modify: `backend/app/api/planner.py`
- Modify: `backend/app/api/chat.py`
- Modify: `backend/app/api/ops.py`
- Test: `backend/tests/unit/test_authorization.py`
- Test: `backend/tests/integration/test_cross_owner_isolation.py`

**Interfaces:**

- Consumes: Tasks 2-3 principal dependencies and existing services.
- Produces: route-level owner/workspace authorization for workspaces,
  conversations, memory, planner, bound chat, and ops readiness.

- [ ] **Step 1: Write failing authorization unit tests**

Cover same-owner allow, mismatched-owner forbidden, unknown workspace not-found,
and compatibility mode preserving current local behavior.

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_authorization.py -q
```

Expected: fail because authorization helpers do not exist.

- [ ] **Step 2: Write failing integration isolation tests**

Create two synthetic authenticated owners. Prove owner A cannot list, get,
append, extract, promote, retrieve, create planner records, update planner
records, or bind chat turns to owner B workspace/conversation ids.

Run:

```text
./.venv/bin/python -m pytest backend/tests/integration/test_cross_owner_isolation.py -q
```

Expected: fail because routes still trust caller-supplied ids.

- [ ] **Step 3: Implement workspace authorization**

Wire principal dependencies into workspace routes. In auth mode, create accepts
only body owner equal to `principal.owner_user_id`; mismatched create returns
`403`; list either filters to the principal owner or rejects a mismatched owner
query with `403`; reading, mutating, or deleting an existing cross-owner
workspace id returns `404`.

- [ ] **Step 4: Implement dependent route authorization**

Before conversation, memory, and planner operations return content or mutate
state, resolve workspace ownership and require the authenticated principal to
match. Cross-owner ids return controlled `404` where revealing existence would
leak another owner.

For bound chat, authorize with one owner-resolution chain:

```text
conversation_id -> conversation.workspace_id -> workspace.owner_user_id -> principal.owner_user_id
```

Do not authorize bound chat from caller-supplied owner fields; `ChatRequest` has
none. The orchestrator's memory owner resolver must agree with this same
workspace owner.

- [ ] **Step 5: Protect ops readiness when auth is enabled**

Keep `/health` unauthenticated. Require auth for `/api/v1/ops/readiness` when
`AUTH_REQUIRED=true`.

- [ ] **Step 6: Run focused tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_authorization.py backend/tests/integration/test_cross_owner_isolation.py -q
```

Expected: pass.

- [ ] **Step 7: Review checkpoint**

Review: no route treats caller-supplied `owner_user_id` as authority when auth
is enabled; cross-owner tests cover every product module.

Expected: authenticated cross-user leakage gate is now testable.

## Task 5: Deletion and Tombstone Semantics

**Files:**

- Create: `backend/privacy/__init__.py`
- Create: `backend/privacy/deletion.py`
- Modify: `backend/workspaces/repository.py`
- Modify: `backend/workspaces/sqlite_repository.py`
- Modify: `backend/workspaces/service.py`
- Modify: `backend/conversations/repository.py`
- Modify: `backend/conversations/sqlite_repository.py`
- Modify: `backend/conversations/service.py`
- Modify: `backend/memory/repository.py`
- Modify: `backend/memory/sqlite_repository.py`
- Modify: `backend/memory/retrieval.py`
- Modify: `backend/planner/repository.py`
- Modify: `backend/planner/sqlite_repository.py`
- Modify: `backend/app/api/workspaces.py`
- Test: `backend/tests/unit/test_privacy_deletion.py`
- Test: `backend/tests/integration/test_deletion_api.py`

**Interfaces:**

- Consumes: authenticated owner authorization from Task 4.
- Produces: workspace deletion request and confirmation flow; deleted data
  hidden from normal APIs; deleted memory ineligible for retrieval.

- [ ] **Step 1: Write failing deletion unit tests**

Cover deletion request, confirmed deletion, rollback on repository failure using
fail-closed ordering, idempotent retry after partial child transition failure,
and deleted-memory retrieval exclusion.

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_privacy_deletion.py -q
```

Expected: fail because privacy deletion service does not exist.

- [ ] **Step 2: Write failing deletion API tests**

Cover:

```text
owner can request workspace deletion
other owner cannot request deletion
owner can confirm deletion
deleted workspace is absent from list/get
deleted workspace rejects new conversations
deleted workspace rejects memory extraction and promotion
deleted workspace rejects planner writes
deleted memory is not selected for bound chat
```

Run:

```text
./.venv/bin/python -m pytest backend/tests/integration/test_deletion_api.py -q
```

Expected: fail because deletion routes and repository transitions do not exist.

- [ ] **Step 3: Add repository lifecycle transitions**

Add workspace-scoped transition methods that move active records to
`deletion_requested` and then `deleted`. Keep transitions idempotent for already
matching states and controlled for unknown ids. Reuse existing list/retrieval
filters that already exclude deleted workspace, conversation, and inactive
memory records instead of rewriting them.

- [ ] **Step 4: Implement privacy deletion service**

Coordinate workspace, conversation, memory, and planner visibility changes with
safe ordering rather than one cross-adapter transaction. First move the
workspace to `deletion_requested`; this immediately blocks normal product access.
Then perform idempotent child transitions. If a child adapter fails, leave the
workspace in `deletion_requested`, return a controlled retryable failure, and do
not claim confirmed deletion.

- [ ] **Step 5: Add deletion API endpoints**

Add authenticated owner-only endpoints under the workspace route, for example:

```text
POST /api/v1/workspaces/{workspace_id}/deletion-requests
POST /api/v1/workspaces/{workspace_id}/deletion-confirmations
```

Responses contain ids, lifecycle states, and counts only.

- [ ] **Step 6: Enforce deleted-workspace guards**

Reject new conversations, memory runs/promotions, planner writes, and bound chat
against deleted or deletion-requested workspaces with controlled errors.

- [ ] **Step 7: Run focused tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_privacy_deletion.py backend/tests/integration/test_deletion_api.py -q
```

Expected: pass.

- [ ] **Step 8: Review checkpoint**

Review: deletion creates no hard-delete claim, no raw user content in responses,
and memory retrieval cannot select deleted or deletion-requested records.

Expected: deletion hard gate is now testable.

## Task 6: Authenticated Memory Gate Refresh

**Files:**

- Modify: `backend/memory/evaluation/runner.py`
- Modify: `backend/memory/evaluation/cli.py`
- Create: `docs/evaluation/fixtures/memory/r6-retrieval-v0.2/manifest.json`
- Create: `docs/evaluation/fixtures/memory/r6-retrieval-v0.2/examples.jsonl`
- Create: `docs/reports/memory/r6-retrieval-v0.2.json`
- Create: `docs/reports/memory/r6-retrieval-v0.2.md`
- Modify: `docs/roadmap/master-roadmap.md`
- Test: `backend/tests/unit/test_memory_retrieval_evaluation_runner.py`

**Interfaces:**

- Consumes: Tasks 2-5 auth, authorization, and deletion behavior.
- Produces: refreshed memory evidence for authenticated cross-user isolation and
  deleted-memory retrieval gates.

- [ ] **Step 1: Write failing memory evidence tests**

Cover:

```text
auth-enabled cross-owner memory access records zero successful leaks
deleted-memory retrieval records zero selected deleted/deletion_requested records
AUTH_REQUIRED=false makes authenticated hard-gate evidence INVALID
missing or malformed synthetic token registry makes the evidence INVALID
```

Run:

```text
AUTH_REQUIRED=true LOCAL_AUTH_TOKENS_JSON='{"owner_a":"secret-alpha-token","owner_b":"secret-beta-token"}' ./.venv/bin/python -m pytest backend/tests/unit/test_memory_retrieval_evaluation_runner.py -q
```

Expected: fail because refreshed R9 memory evidence does not exist.

- [ ] **Step 2: Create the refreshed fixture suite**

`backend/memory/evaluation/runner.py` derives report file names from the manifest
`dataset_id` through `_report_stem`, not from `--suite`. Reusing the
`r6-retrieval-v0.1` manifest would therefore overwrite the delivered R6 baseline
reports, destroying the historical label-based evidence this task must preserve.

Create `docs/evaluation/fixtures/memory/r6-retrieval-v0.2/` with
`"dataset_id": "r6-retrieval-v0.2"` and `"dataset_version": "0.2"`. Carry over the
R6 cases needed for the two formerly unobservable hard gates and add
authenticated cross-owner and confirmed-deletion cases. Leave the
`r6-retrieval-v0.1` fixture and its reports untouched.

- [ ] **Step 3: Extend memory evaluation output**

Add a R9-owned path that writes `r6-retrieval-v0.2` evidence or an equivalent
explicit memory gate appendix. The output must name the prior
`r6-retrieval-v0.1` label-based limitation and replace it with authenticated
evidence for only the two formerly unobservable gates.

- [ ] **Step 4: Run refreshed memory evidence**

Run:

```text
AUTH_REQUIRED=true LOCAL_AUTH_TOKENS_JSON='{"owner_a":"secret-alpha-token","owner_b":"secret-beta-token"}' ./.venv/bin/python -m backend.memory.evaluation.cli run-retrieval --suite r6-retrieval-v0.2 --output-dir docs/reports/memory
```

Expected: produces refreshed evidence showing authenticated cross-user leakage
`0` and deleted/deletion-requested memory retrieval `0`, written to
`docs/reports/memory/r6-retrieval-v0.2.{json,md}`. Confirm
`docs/reports/memory/r6-retrieval-v0.1.{json,md}` are unchanged; if either was
rewritten, stop and restore them before continuing. If the implementation uses a
different command or report id, record the exact command in the Completion
Record.

- [ ] **Step 5: Update roadmap ordering problem**

Update `docs/roadmap/master-roadmap.md` so `Open Ordering Problem: R6 and R9`
is no longer an unresolved blocker after the refreshed evidence exists. Preserve
the historical note that `r6-retrieval-v0.1` was label-based.

- [ ] **Step 6: Review checkpoint**

Review: R9 does not claim all R6 quality gates were re-run unless they were.
Only the two formerly unobservable hard gates are upgraded by this task, and the
delivered `r6-retrieval-v0.1` reports remain byte-for-byte intact as historical
evidence.

Expected: R9 now closes the reason the R6/R9 ordering problem existed.

## Task 7: Controlled HTTP 500 Responses and Security Events

**Files:**

- Modify: `backend/app/main.py`
- Modify: `backend/app/api/chat.py`
- Modify: `backend/app/api/workspaces.py`
- Modify: `backend/app/api/conversations.py`
- Modify: `backend/app/api/memory.py`
- Modify: `backend/app/api/planner.py`
- Test: `backend/tests/integration/test_security_error_handling.py`

**Interfaces:**

- Consumes: R8 request id/event context and R9 auth/deletion errors.
- Produces: content-free HTTP 500 response body with request id and safe
  security/privacy events.

- [ ] **Step 1: Extend failing error tests**

Cover route-level unhandled exception, storage exception, and auth configuration
exception. Assert response body excludes raw exception text and includes
`request_id`.

Run:

```text
./.venv/bin/python -m pytest backend/tests/integration/test_security_error_handling.py -q
```

Expected: fail for any raw exception-derived detail still exposed.

- [ ] **Step 2: Implement global safe 500 handler**

Use R8 request id context. Return only:

```json
{"detail": "Internal server error.", "request_id": "rq_<32 lowercase hex characters>"}
```

Emit safe event fields with controlled `failure_class` and `reason_code`.

- [ ] **Step 3: Normalize route 500 details**

Keep existing controlled service-unavailable details where already safe, but
remove arbitrary exception strings from user-facing 500 responses.

- [ ] **Step 4: Run focused tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests/integration/test_security_error_handling.py -q
```

Expected: pass.

- [ ] **Step 5: Review checkpoint**

Review: no raw exception text, path, SQL, prompt, message, token, or stack trace
can reach a 500 response or security event.

Expected: raw HTTP 500 blocker is closed for R9 scope.

## Task 8: Security Evaluation Harness and Reports

**Files:**

- Create: `backend/security/evaluation/__init__.py`
- Create: `backend/security/evaluation/models.py`
- Create: `backend/security/evaluation/runner.py`
- Create: `backend/security/evaluation/cli.py`
- Create: `docs/evaluation/fixtures/security/r9-security-privacy-v0.1/manifest.json`
- Create: `docs/evaluation/fixtures/security/r9-security-privacy-v0.1/examples.jsonl`
- Create: `docs/reports/security/r9-security-privacy-v0.1.json`
- Create: `docs/reports/security/r9-security-privacy-v0.1.md`
- Test: `backend/tests/unit/test_security_evaluation_runner.py`

**Interfaces:**

- Consumes: Tasks 2-7 security behavior.
- Produces: `run_security_evaluation(manifest_path, output_dir)` and CLI
  command `run-security`.

- [ ] **Step 1: Write failing evaluation tests**

Cover valid fixture parsing, invalid fixture result `INVALID`, zero-tolerance
gate aggregation, JSON report rendering, Markdown report rendering, and privacy
sentinel absence from reports.

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_security_evaluation_runner.py -q
```

Expected: fail because security evaluation package does not exist.

- [ ] **Step 2: Create fixture**

Create synthetic examples covering:

```text
missing_token_denied
invalid_token_denied
cross_owner_workspace_denied
cross_owner_conversation_denied
cross_owner_memory_denied
cross_owner_planner_denied
deleted_memory_not_selected
deleted_workspace_rejects_writes
raw_500_detail_redacted
oversized_request_denied
token_value_not_reported
auth_disabled_report_invalid
```

- [ ] **Step 3: Implement runner and CLI**

Use result states `PASS`, `FAIL`, `INCONCLUSIVE`, and `INVALID`. Reports carry
ids, counts, gates, and reason codes only.

- [ ] **Step 4: Run focused tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_security_evaluation_runner.py -q
AUTH_REQUIRED=true LOCAL_AUTH_TOKENS_JSON='{"owner_a":"secret-alpha-token","owner_b":"secret-beta-token"}' ./.venv/bin/python -m backend.security.evaluation.cli run-security --suite r9-security-privacy-v0.1
```

Expected: tests pass and CLI prints `result_state=PASS`.

- [ ] **Step 5: Review checkpoint**

Review: R9 report contains no token values, prompts, messages, memory text,
itinerary text, decision statements, raw exception text, or raw paths.

Expected: R9 evaluation evidence is safe to commit.

## Task 9: Documentation, Verification, and Handoff

**Files:**

- Modify: `SECURITY.md`
- Modify: `ARCHITECTURE.md`
- Modify: `DEVELOPMENT.md`
- Modify: `docs/architecture/current-state.md`
- Modify: `docs/architecture/data-model.md`
- Modify: `docs/runbooks/deployment.md`
- Modify: `docs/runbooks/incident-response.md`
- Modify: `docs/roadmap/master-roadmap.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/specs/README.md`
- Modify: `docs/adr/README.md`
- Modify: `docs/plans/2026-09-06-security-and-privacy-hardening-implementation.md`
- Modify: `.env.example`

**Interfaces:**

- Consumes: Tasks 1-8 outputs.
- Produces: R9 review packet and completed plan evidence.

- [ ] **Step 1: Update security policy**

Record implemented local auth boundary, owner authorization, soft deletion,
generic 500 behavior, request-size limit, secret-setting handling, and remaining
non-production blockers.

- [ ] **Step 2: Update architecture docs**

Update trust-boundary rows for product routes, ops route, local identity, and
deletion lifecycle. Preserve the claim that public production remains blocked
until deployment and provider decisions exist.

- [ ] **Step 3: Update development docs and runbooks**

Document local auth environment variables in `.env.example` with placeholders
only, example synthetic token setup, security evaluation command, deletion
recovery notes, and incident evidence rules.

For the deployment runbook, update authentication and CORS gates with R9 local
evidence while keeping public-production status blocked: local bearer tokens and
local CORS allowlists are not production identity, TLS, hosting, or deployment
architecture.

- [ ] **Step 4: Update roadmap and indexes**

Update R9 status/evidence, the ADR/spec/plan indexes, and the roadmap
`Open Ordering Problem: R6 and R9` section after refreshed memory evidence
exists. Do not mark R9 `Delivered` unless repository-owner Git delivery has
occurred.

- [ ] **Step 5: Run full backend tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests
```

Expected: pass, or disclose exact known non-R9 external/environment failure and
run all focused R9 tests successfully.

- [ ] **Step 6: Run compile and R9 evaluation**

Run:

```text
./.venv/bin/python -m compileall backend
AUTH_REQUIRED=true LOCAL_AUTH_TOKENS_JSON='{"owner_a":"secret-alpha-token","owner_b":"secret-beta-token"}' ./.venv/bin/python -m backend.security.evaluation.cli run-security --suite r9-security-privacy-v0.1
```

Expected: compile exits `0`; evaluation reports `result_state=PASS`.

- [ ] **Step 7: Run refreshed memory evidence**

Run:

```text
AUTH_REQUIRED=true LOCAL_AUTH_TOKENS_JSON='{"owner_a":"secret-alpha-token","owner_b":"secret-beta-token"}' ./.venv/bin/python -m backend.memory.evaluation.cli run-retrieval --suite r6-retrieval-v0.2 --output-dir docs/reports/memory
```

Expected: refreshed evidence proves authenticated cross-user memory leakage `0`
and deleted/deletion-requested memory retrieval `0`, or reports `INVALID` if the
auth-enabled gate cannot be observed. `docs/reports/memory/r6-retrieval-v0.1.*`
must remain unchanged.

- [ ] **Step 8: Run privacy/security grep checks**

Run:

```text
grep -R -n "secret-alpha-token\|secret-beta-token\|NEVER_LOG_USER_MESSAGE\|NEVER_LOG_MEMORY_TEXT\|NEVER_LOG_ITINERARY_TEXT\|NEVER_LOG_DECISION_STATEMENT\|Traceback" docs/reports/security docs/reports/memory/r6-retrieval-v0.2.md docs/reports/memory/r6-retrieval-v0.2.json
grep -R -n "production-ready\|public-production ready" docs/specs/2026-09-06-security-and-privacy-hardening-design.md docs/plans/2026-09-06-security-and-privacy-hardening-implementation.md SECURITY.md ARCHITECTURE.md docs/architecture/current-state.md docs/runbooks
```

Expected: first command exits `1` with no output after Task 8 and the refreshed
memory report create the target report paths. If a target report path is
missing, the command may exit `2`; treat that as missing evidence, not a privacy
PASS. Second command may return hits and must be manually reviewed to ensure R9
does not claim public-production readiness.

- [ ] **Step 9: Run import-boundary checks**

Run:

```text
grep -RnE --include='*.py' "^[[:space:]]*(from|import)[[:space:]]+backend\.(rag|memory|planner|workspaces|conversations|orchestration|app\.api)" backend/security/models.py backend/security/local_tokens.py
grep -RnE --include='*.py' "^[[:space:]]*(from|import)[[:space:]]+backend\.(security\.dependencies|security\.authorization|privacy\.deletion|app\.api)" backend/rag
grep -RnE --include='*.py' "^[[:space:]]*(from|import)[[:space:]]+backend\.security\.evaluation" backend/app backend/rag backend/memory backend/planner backend/workspaces backend/conversations backend/orchestration
```

Expected: each exits `1` with no output.
Run these only after Task 2 has created `backend/security/models.py` and
`backend/security/local_tokens.py`; a missing target file is a verification
failure, not a passing boundary check.

- [ ] **Step 10: Run final diff checks**

Run:

```text
git diff --check
git status --short --untracked-files=all
```

Expected: diff check clean; status contains only intentional R9 files.

- [ ] **Step 11: Complete plan evidence**

Update this plan's Completion Record with final task status, verification
commands/results, reviewer findings, accepted limitations, and handoff commit
if one exists.

- [ ] **Step 12: Review checkpoint**

Review: final change set against the approved R9 spec, ADR 0010, and this plan.

Expected: ready for repository-owner review; no Git delivery performed unless
the repository owner explicitly requested it.

## Package Verification

Run:

```text
./.venv/bin/python -m pytest backend/tests
./.venv/bin/python -m compileall backend
AUTH_REQUIRED=true LOCAL_AUTH_TOKENS_JSON='{"owner_a":"secret-alpha-token","owner_b":"secret-beta-token"}' ./.venv/bin/python -m backend.security.evaluation.cli run-security --suite r9-security-privacy-v0.1
AUTH_REQUIRED=true LOCAL_AUTH_TOKENS_JSON='{"owner_a":"secret-alpha-token","owner_b":"secret-beta-token"}' ./.venv/bin/python -m backend.memory.evaluation.cli run-retrieval --suite r6-retrieval-v0.2 --output-dir docs/reports/memory
grep -R -n "secret-alpha-token\|secret-beta-token\|NEVER_LOG_USER_MESSAGE\|NEVER_LOG_MEMORY_TEXT\|NEVER_LOG_ITINERARY_TEXT\|NEVER_LOG_DECISION_STATEMENT\|Traceback" docs/reports/security docs/reports/memory/r6-retrieval-v0.2.md docs/reports/memory/r6-retrieval-v0.2.json
grep -RnE --include='*.py' "^[[:space:]]*(from|import)[[:space:]]+backend\.(rag|memory|planner|workspaces|conversations|orchestration|app\.api)" backend/security/models.py backend/security/local_tokens.py
grep -RnE --include='*.py' "^[[:space:]]*(from|import)[[:space:]]+backend\.(security\.dependencies|security\.authorization|privacy\.deletion|app\.api)" backend/rag
grep -RnE --include='*.py' "^[[:space:]]*(from|import)[[:space:]]+backend\.security\.evaluation" backend/app backend/rag backend/memory backend/planner backend/workspaces backend/conversations backend/orchestration
git diff --check
git status --short --untracked-files=all
```

Expected evidence:

1. backend tests pass or a known non-R9 external blockage is disclosed with all
   focused R9 tests passing;
2. compileall exits `0`;
3. R9 evaluation reports `PASS`;
4. refreshed memory evidence closes authenticated cross-user and deleted-memory
   gates, or reports `INVALID` rather than fake success, and
   `docs/reports/memory/r6-retrieval-v0.1.*` remain unchanged;
5. privacy sentinel check exits `1` with no output after report paths exist;
6. import-boundary checks exit `1` with no output after target files exist;
7. diff check is clean;
8. status contains only intentional R9 files;
9. docs do not claim public-production readiness.

## Rollback

Before Git delivery, abandon the isolated implementation worktree. After owner
accepted work is merged, revert the R9 merge commit or revert the R9 commit set.
Rollback must not hard-delete user data. If deletion transitions were exercised
in a local database, restore from a user-owned backup or keep tombstoned rows as
local evidence; do not rewrite production-like deletion history.

## Completion Record

| Field | Value |
| --- | --- |
| Approval | ADR 0010 accepted, R9 spec v0.2 approved, and plan v0.3 approved by repository owner on 2026-09-06 |
| Execution base | Pending selection at Task 1 Step 1 |
| Implementation worktree | Pending creation by the repository owner |
| Final verification | Not run |
| Owner review | Pending |
| Git delivery | Not authorized by this plan |

## Approval Record

| Version | Decision owner | Date | Notes |
| --- | --- | --- | --- |
| 0.1 | Repository owner | 2026-09-06 | Drafted for R9 review. External review found self-matching sentinel checks, missing refreshed memory evidence for the R6/R9 ordering gap, ambiguous auth-enabled evaluation semantics, unsafe cross-adapter transaction wording, unclear readiness-auth failure handling, underspecified bound-chat authorization, and conflicting 403/404 wording |
| 0.2 | Repository owner | 2026-09-06 | Addressed the first R9 review round. Superseded by version 0.3 after review found the memory refresh command reused the `r6-retrieval-v0.1` manifest, whose `dataset_id` drives report file names and would have overwritten the delivered R6 baseline evidence, and `.env.example` was listed as a new file |
| 0.3 | Repository owner | 2026-09-06 | Approved after review fixes. Adds a dedicated `r6-retrieval-v0.2` fixture so refreshed memory evidence never overwrites the delivered R6 reports, corrects every refresh command to that suite, records the historical-evidence and sentinel-scope constraints, and changes `.env.example` to an append-only modification. Approval authorizes implementation in an isolated worktree only, not Git delivery, public production deployment, OAuth/OIDC, frontend work, hard deletion, external providers, or release |
