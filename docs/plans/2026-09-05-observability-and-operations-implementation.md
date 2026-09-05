# Observability and Operations Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence.

**Goal:** Build local privacy-safe observability for R8 so developers can
diagnose degraded RAG, model, storage, memory, and planner paths without leaking
secrets or raw user content.

**Architecture:** `backend/observability/` owns request context, structured event
contracts, redaction, readiness probes, and operational evaluation. Existing
routes and services may emit safe events through the low-level event API, while
readiness composition stays behind the ops route and CLI. `/health` remains a
compatibility liveness endpoint.

**Tech Stack:** Python 3.11+ baseline, FastAPI middleware/routes, Pydantic,
standard-library `logging`, `contextvars`, `uuid`, `json`, `sqlite3`, `pathlib`,
pytest, existing Markdown/JSON report style.

**Spec:** [Observability and Operations Design](../specs/2026-09-05-observability-and-operations-design.md), version 0.2 (In Review)

| Field | Value |
| --- | --- |
| Status | Approved |
| Plan version | 0.3 |
| Date | 2026-09-05 |
| Approved specification | [Observability and Operations Design](../specs/2026-09-05-observability-and-operations-design.md), version 0.2, approved by repository owner on 2026-09-05 |
| Governing ADRs | [ADR 0009](../adr/0009-privacy-safe-local-observability-boundary.md) (Accepted) |
| Plan approval | Approved by repository owner on 2026-09-05 |
| Execution owner | Implementation worker agent in an isolated worktree |
| Decision owner | Repository owner |
| Scope | Runtime milestone R8 - observability contracts, request correlation, safe event logging, readiness diagnostics, ops API/CLI, deterministic operational evaluation, tests, reports, and docs |
| Verification | `./.venv/bin/python -m pytest backend/tests`, `./.venv/bin/python -m compileall backend`, `./.venv/bin/python -m backend.observability.evaluation.cli run-readiness --suite r8-operational-readiness-v0.1`, observability privacy and import-boundary `grep` checks, `git diff --check`, `git status --short --untracked-files=all` |

## Approval Gate

Do not implement this plan until all are true:

1. ADR 0009 is accepted.
2. R8 spec version 0.2 is approved.
3. This implementation plan version 0.3 is approved.
4. The selected implementation base includes R7 delivered work through `57e70fe`,
   or a later repository-owner selected base.

## Global Constraints

1. R8 is backend-only.
2. Preserve the existing `/health` response body.
3. Add no frontend UI, authentication, authorization, production deployment,
   OpenTelemetry, Prometheus, Sentry, Datadog, cloud logging, dashboard, alert
   route, durable telemetry database, or external provider health call.
4. No raw message content, prompts, retrieved chunk text, memory text,
   itinerary text, decision statements, assistant answers, model/provider
   payloads, token values, environment values, raw filesystem paths, stack
   traces, or arbitrary exception strings in logs, readiness responses, or R8
   reports.
5. Readiness probes must be read-only and must not create databases, create
   Chroma directories or collections, run migrations, index data, call embedding
   models, call model providers, or mutate evaluation artifacts.
6. Existing chat, workspace, conversation, memory, and planner response bodies
   remain unchanged. A response header `X-Request-ID` and a new ops route are
   allowed. R8 must not redesign raw exception-derived HTTP 500 details.
7. Low-level observability event modules must not import RAG, memory, planner,
   workspace, conversation, orchestration, or route modules.
8. Product-domain modules may import only `backend.observability.context` and
   `backend.observability.events`; they must not import readiness, evaluation,
   or ops route modules.
9. R8 takes over the narrow prompt-prefix logging fix from the later R9
   security-hardening bucket. Authentication, authorization, deletion, tenant
   isolation, and production privacy hardening remain out of scope.
10. Tests must use temporary paths and synthetic data.
11. R8 evaluation fixtures and reports must live under tracked `docs/` paths,
    not gitignored `data/`.
12. Git staging, commit, push, PR, merge, release, and destructive cleanup remain
    repository-owner actions unless explicitly requested.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/observability/__init__.py` | Stable package exports | R8 observability modules |
| `backend/observability/models.py` | Event, readiness, component, result, and severity contracts | Standard library/Pydantic |
| `backend/observability/redaction.py` | Safe-field validation and redaction helpers | Observability models |
| `backend/observability/context.py` | Request id context variable and id generation | Standard library |
| `backend/observability/events.py` | Structured JSON logging API | Context, redaction, models |
| `backend/observability/readiness.py` | Read-only local readiness probes and snapshot composition | Settings, schema metadata, report files |
| `backend/observability/evaluation/__init__.py` | Evaluation exports | Evaluation runner |
| `backend/observability/evaluation/models.py` | R8 report model and result-state contracts | D5 result-state vocabulary |
| `backend/observability/evaluation/runner.py` | Deterministic operational evaluation | Observability models, redaction, readiness |
| `backend/observability/evaluation/cli.py` | `run-readiness` CLI command | Evaluation runner |
| `backend/app/api/ops.py` | Safe ops readiness route | Readiness service only |
| `backend/app/main.py` | Request-id middleware and ops router mount | Context/events/ops route |
| `backend/app/api/chat.py` | Replace prompt-prefix and unsafe exception logging with safe events | Observability events |
| `backend/orchestration/conversation_orchestrator.py` | Emit safe chat persistence and memory-selection outcome events | Observability events |
| `backend/rag/generation/rag_service.py` | Emit safe retrieval/model outcome events | Observability events |
| `backend/memory/service.py` | Emit safe extraction/promotion service events | Observability events |
| `backend/planner/service.py` | Emit safe planner operation outcome events | Observability events |
| `backend/storage/schema_registry.py` | Emit safe schema compatibility failure events | Observability events |
| `backend/tests/unit/test_observability_models.py` | Contract tests | Observability models |
| `backend/tests/unit/test_observability_redaction.py` | Redaction and unsafe-field tests | Redaction helpers |
| `backend/tests/unit/test_observability_events.py` | Structured logger tests | Event API |
| `backend/tests/unit/test_observability_readiness.py` | Read-only readiness tests | Readiness service |
| `backend/tests/unit/test_observability_evaluation_runner.py` | R8 evaluation tests | Evaluation runner |
| `backend/tests/integration/test_ops_readiness_api.py` | Readiness route and health compatibility tests | FastAPI app |
| `backend/tests/integration/test_observability_log_safety.py` | Captured log privacy tests across chat/memory/planner paths | FastAPI app and services |
| `docs/evaluation/fixtures/ops/r8-operational-readiness-v0.1/manifest.json` | Fixture manifest | R8 evaluation design |
| `docs/evaluation/fixtures/ops/r8-operational-readiness-v0.1/examples.jsonl` | Synthetic operational scenarios | R8 evaluation design |
| `docs/reports/ops/r8-operational-readiness-v0.1.json` | Machine-readable R8 report | R8 evaluation run |
| `docs/reports/ops/r8-operational-readiness-v0.1.md` | Human-readable R8 report | R8 evaluation run |
| `ARCHITECTURE.md` | Current architecture gateway after implementation | Implemented R8 behavior |
| `SECURITY.md` | Current security blocker truth after prompt-prefix logging is removed | Implemented R8 behavior |
| `DEVELOPMENT.md` | Local ops commands and readiness meaning | Implemented R8 behavior |
| `docs/architecture/current-state.md` | Implemented observability description | Implemented R8 behavior |
| `docs/runbooks/local-development.md` | Local degraded-state recovery routing | Implemented R8 behavior |
| `docs/runbooks/deployment.md` | Deployment readiness evidence update | Implemented R8 behavior |
| `docs/runbooks/incident-response.md` | Incident evidence and operational signal update | Implemented R8 behavior |
| `docs/roadmap/master-roadmap.md` | R8 status and evidence | Owner review and verification |
| `docs/plans/README.md` | Plan index status | This plan |
| `docs/specs/README.md` | Spec index status | R8 spec |

## Task 1: Preflight and Governance Gate

**Files:**

- Read: `AGENTS.md`
- Read: `docs/specs/2026-09-05-observability-and-operations-design.md`
- Read: `docs/adr/0009-privacy-safe-local-observability-boundary.md`
- Read: `docs/plans/2026-09-05-observability-and-operations-implementation.md`
- Modify: `docs/plans/2026-09-05-observability-and-operations-implementation.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/roadmap/master-roadmap.md`

**Interfaces:**

- Consumes: owner approvals for ADR 0009, R8 spec v0.2, and this plan v0.3.
- Produces: implementation worktree with documented base commit and R8 plan
  state moved to `In Progress`.

- [ ] **Step 1: Confirm implementation base**

Run:

```text
git status --short --branch --untracked-files=all
git log --oneline -8
```

Expected: implementation worktree is clean and base includes R7 delivered work
through `57e70fe`, or the repository-owner selected later base.

- [ ] **Step 2: Confirm approval gates**

Expected headers:

```text
ADR 0009: Accepted
R8 spec v0.2: Approved
R8 plan v0.3: Approved
```

Stop if any value is missing.

- [ ] **Step 3: Move R8 docs into implementation state**

Update this plan status to `In Progress`, update `docs/plans/README.md`, and
update roadmap `R8` from `Blocked by gate` to `In progress`.

- [ ] **Step 4: Run baseline tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests
```

Expected: pass, or disclose known non-R8 external/environment failures before
changing source.

- [ ] **Step 5: Review checkpoint**

Review: approval gates, base commit, clean status, and R8 status edits.

Expected: no source change has started before the gate is satisfied.

## Task 2: Observability Contracts and Redaction

**Files:**

- Create: `backend/observability/__init__.py`
- Create: `backend/observability/models.py`
- Create: `backend/observability/redaction.py`
- Test: `backend/tests/unit/test_observability_models.py`
- Test: `backend/tests/unit/test_observability_redaction.py`

**Interfaces:**

- Consumes: event/readiness contracts from the spec.
- Produces: `OperationalEvent`, `ReadinessSnapshot`, `ReadinessComponent`,
  safe payload validation primitives, and redaction helpers.

- [ ] **Step 1: Write failing model tests**

Cover:

```text
request ids use rq_<32 hex>
event ids use ev_<32 hex>
event severity is info|warning|error
event result is success|failure|degraded|skipped
readiness status is ready|degraded|not_ready|unknown
duration_ms cannot be negative
counters accept only bounded scalar values
```

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_observability_models.py -q
```

Expected: fail because the module does not exist.

- [ ] **Step 2: Write failing redaction tests**

Cover:

```text
GITHUB_TOKEN-like values redact to [REDACTED]
/Users/example/project/data/app.sqlite3 redacts as [PATH]
request.message, prompt, reply, content, candidate_text, itinerary_text,
decision_statement, provider_response, stack_trace, and raw_exception are
rejected keys
safe ids, reason_code, failure_class, duration_ms, and counters survive
```

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_observability_redaction.py -q
```

Expected: fail because redaction does not exist.

- [ ] **Step 3: Implement minimal contracts**

Implement dataclasses or Pydantic models with explicit enums and validation.
Use `uuid.uuid4().hex` for ids and timezone-aware UTC timestamps.

- [ ] **Step 4: Implement redaction and unsafe-key rejection**

Create one public helper:

```python
def sanitize_event_fields(fields: Mapping[str, object]) -> dict[str, object]:
    ...
```

It rejects forbidden keys and redacts token-like and path-like scalar values
before returning a serializable dictionary.

- [ ] **Step 5: Run focused contract tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_observability_models.py backend/tests/unit/test_observability_redaction.py -q
```

Expected: pass.

- [ ] **Step 6: Review checkpoint**

Review: contract and redaction files import no product domains or route modules.

Expected command:

```text
grep -RnE --include='*.py' "^[[:space:]]*(from|import)[[:space:]]+backend\.(rag|memory|planner|workspaces|conversations|orchestration|app\.api)" backend/observability/__init__.py backend/observability/models.py backend/observability/redaction.py
```

Expected: exit `1` with no output.

## Task 3: Request Context and Structured Event Logging

**Files:**

- Create: `backend/observability/context.py`
- Create: `backend/observability/events.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/test_observability_events.py`
- Test: `backend/tests/integration/test_ops_readiness_api.py`

**Interfaces:**

- Consumes: models and redaction helpers from Task 2.
- Produces: `current_request_id()`, `set_request_id()`, request-id middleware,
  `emit_event(event_name, component, result, **fields)`.

- [ ] **Step 1: Write failing event logger tests**

Cover:

```text
emit_event writes one JSON log record with event_id, timestamp, event_name,
component, severity, result, and request_id
emit_event rejects unsafe keys before logging
emit_event records failure_class without raw exception text
```

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_observability_events.py -q
```

Expected: fail.

- [ ] **Step 2: Write failing middleware tests**

Cover:

```text
GET /health response JSON remains {"status": "ok", "service": settings.PROJECT_NAME}
GET /health includes X-Request-ID header
two requests receive different request ids
captured request-completed log has no request body or query string
```

Run:

```text
./.venv/bin/python -m pytest backend/tests/integration/test_ops_readiness_api.py::test_health_body_unchanged_with_request_id_header -q
```

Expected: fail because middleware is absent.

- [ ] **Step 3: Implement context and event logger**

Use `contextvars.ContextVar` for request id storage and standard-library
`logging.getLogger("travel_agent_observability")` for JSON event logs.

- [ ] **Step 4: Add FastAPI middleware**

Generate a server-owned request id for every request, set it in context, add
`X-Request-ID` to the response, and emit an `api.request.completed` event with
method, route path template when available, status code, duration, and result.
Expose `X-Request-ID` through CORS so local browser clients can read it. Do not
log request bodies or query strings.

- [ ] **Step 5: Run focused tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_observability_events.py backend/tests/integration/test_ops_readiness_api.py::test_health_body_unchanged_with_request_id_header -q
```

Expected: pass.

- [ ] **Step 6: Review checkpoint**

Review: `/health` body compatibility and request id header behavior.

Expected: no existing response body changes outside the new header, and CORS
exposes `X-Request-ID`.

## Task 4: Privacy-safe Instrumentation of Runtime Paths

**Files:**

- Modify: `backend/app/api/chat.py`
- Modify: `backend/orchestration/conversation_orchestrator.py`
- Modify: `backend/rag/generation/rag_service.py`
- Modify: `backend/memory/service.py`
- Modify: `backend/planner/service.py`
- Modify: `backend/storage/schema_registry.py`
- Test: `backend/tests/integration/test_observability_log_safety.py`

**Interfaces:**

- Consumes: `emit_event` from Task 3.
- Produces: content-free events for chat, RAG, model-provider, memory, planner,
  and schema compatibility outcomes.

- [ ] **Step 1: Write failing log-safety tests**

Use synthetic strings such as:

```text
NEVER_LOG_USER_MESSAGE
NEVER_LOG_PROMPT
NEVER_LOG_MEMORY_TEXT
NEVER_LOG_ITINERARY_TEXT
NEVER_LOG_DECISION_STATEMENT
ghp_NEVER_LOG_TOKEN_VALUE
```

Cover captured logs for a chat validation path, a bound chat path with memory
retrieval disabled, memory extraction, planner itinerary creation, planner
decision recording, and schema incompatibility. Assert those strings are absent
and safe ids/reason codes are present.

Run:

```text
./.venv/bin/python -m pytest backend/tests/integration/test_observability_log_safety.py -q
```

Expected: fail while prompt-prefix logging still exists.

- [ ] **Step 2: Remove prompt-prefix logging**

Replace `logger.info(f"Received chat request: '{user_message[:50]}...'")` with a
content-free `chat.request.accepted` event.

- [ ] **Step 3: Replace unsafe exception logging on chat path**

Use controlled `failure_class` and `reason_code` fields. Do not place arbitrary
exception strings in log event payloads for chat path failures. Do not change
HTTP response bodies in this step; raw exception-derived HTTP 500 detail
hardening remains outside R8.

- [ ] **Step 4: Add success/degraded events**

Emit:

```text
chat.turn.completed
rag.retrieval.completed
model.call.completed
model.call.failed
memory.retrieval.completed
memory.extraction.completed
planner.operation.applied
storage.schema.failed
```

Use ids, counts, status, selected counts, result ids, duration, and reason codes
only.

- [ ] **Step 5: Run focused privacy tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests/integration/test_observability_log_safety.py -q
```

Expected: pass.

- [ ] **Step 6: Review checkpoint**

Review: instrumentation does not change business return values, persistence,
evaluation scoring, or route response bodies.

Expected: `git diff` shows only logging/event additions and removal of unsafe
prompt-prefix logging.

## Task 5: Readiness Service and Ops API

**Files:**

- Create: `backend/observability/readiness.py`
- Create: `backend/app/api/ops.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/test_observability_readiness.py`
- Test: `backend/tests/integration/test_ops_readiness_api.py`

**Interfaces:**

- Consumes: observability models from Task 2.
- Produces: `build_readiness_snapshot() -> ReadinessSnapshot` and
  `GET /api/v1/ops/readiness`.

- [ ] **Step 1: Write failing readiness unit tests**

Cover:

```text
missing GITHUB_TOKEN -> model_provider not_ready credential_missing
missing Chroma path -> rag_chroma unknown or not_ready without creating path
missing APP_DB_PATH -> app_db unknown or not_ready without creating file
incompatible schema registry row -> app_db not_ready schema_incompatible
memory flag false -> memory degraded memory_retrieval_disabled
existing report result_state PASS is surfaced as safe metadata
absolute paths are not included in snapshot dict
```

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_observability_readiness.py -q
```

Expected: fail.

- [ ] **Step 2: Write failing ops API tests**

Cover:

```text
GET /api/v1/ops/readiness returns status and components
response contains X-Request-ID
response contains no absolute path, token, prompt, or user-content field
route does not create APP_DB_PATH when it is absent
```

Run:

```text
./.venv/bin/python -m pytest backend/tests/integration/test_ops_readiness_api.py -q
```

Expected: fail until route is mounted.

- [ ] **Step 3: Implement read-only probes**

Implement local metadata probes. Do not instantiate constructors that create
state. Use direct read-only SQLite connection only when the DB file already
exists. Use relative report paths only when reporting existing docs evidence.

- [ ] **Step 4: Implement ops route**

Mount under `settings.API_V1_STR`:

```text
GET /api/v1/ops/readiness
```

The route calls the readiness service and returns the serialized snapshot. It
contains no SQL, Chroma calls, filesystem traversal, or redaction policy.

- [ ] **Step 5: Run focused readiness tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_observability_readiness.py backend/tests/integration/test_ops_readiness_api.py -q
```

Expected: pass.

- [ ] **Step 6: Review checkpoint**

Review: readiness probes are read-only and `/health` compatibility remains
intact.

Expected: no test creates the default developer app DB or Chroma path.

## Task 6: Operational Evaluation Harness

**Files:**

- Create: `backend/observability/evaluation/__init__.py`
- Create: `backend/observability/evaluation/models.py`
- Create: `backend/observability/evaluation/runner.py`
- Create: `backend/observability/evaluation/cli.py`
- Create: `docs/evaluation/fixtures/ops/r8-operational-readiness-v0.1/manifest.json`
- Create: `docs/evaluation/fixtures/ops/r8-operational-readiness-v0.1/examples.jsonl`
- Create: `docs/reports/ops/r8-operational-readiness-v0.1.json`
- Create: `docs/reports/ops/r8-operational-readiness-v0.1.md`
- Test: `backend/tests/unit/test_observability_evaluation_runner.py`

**Interfaces:**

- Consumes: readiness and event/redaction APIs.
- Produces: `run_readiness_evaluation(manifest_path, output_dir)` and CLI
  command `run-readiness`.

- [ ] **Step 1: Write failing evaluation tests**

Cover:

```text
valid fixture produces PASS
fixture with unsafe log field produces FAIL
malformed fixture produces INVALID
empty fixture produces INCONCLUSIVE
report JSON and Markdown are written with dataset id r8-operational-readiness-v0.1
report excludes raw test secrets and content sentinels
```

Run:

```text
./.venv/bin/python -m pytest backend/tests/unit/test_observability_evaluation_runner.py -q
```

Expected: fail.

- [ ] **Step 2: Create fixture suite**

Create at least 12 synthetic examples across these slices:

```text
request_correlation
log_privacy
readiness_degradation
storage_schema
evaluation_report_evidence
runbook_routing
```

Every example has `example_id`, `slice`, `scenario`, expected component states
or blocked unsafe fields, and no real user content.

Fixtures and generated reports must stay under the tracked `docs/evaluation/`
and `docs/reports/` paths listed in the File Responsibility Map, not under
gitignored `data/`.

- [ ] **Step 3: Implement runner and report renderer**

Use D5 result states: `PASS`, `FAIL`, `INCONCLUSIVE`, and `INVALID`. Include
per-slice counts, gate outcomes, and failure reason codes. This is a
milestone-scoped R8 harness and must not create a new D5 protocol document.

- [ ] **Step 4: Implement CLI**

Command:

```text
./.venv/bin/python -m backend.observability.evaluation.cli run-readiness --suite r8-operational-readiness-v0.1
```

Expected stdout includes:

```text
result_state=PASS
eligible_examples=<count>
output_dir=docs/reports/ops
```

- [ ] **Step 5: Run evaluation**

Run:

```text
./.venv/bin/python -m backend.observability.evaluation.cli run-readiness --suite r8-operational-readiness-v0.1
```

Expected: exit `0`; report result is `PASS`; `docs/reports/ops/` now exists with
both report artifacts, which the Task 8 sentinel check depends on.

- [ ] **Step 6: Review checkpoint**

Review: report claims match fixture outputs and do not contain unsafe sentinel
strings.

Expected: Markdown and JSON report are internally consistent.

## Task 7: Documentation and Runbooks

**Files:**

- Modify: `ARCHITECTURE.md`
- Modify: `SECURITY.md`
- Modify: `DEVELOPMENT.md`
- Modify: `docs/architecture/current-state.md`
- Modify: `docs/runbooks/local-development.md`
- Modify: `docs/runbooks/deployment.md`
- Modify: `docs/runbooks/incident-response.md`
- Modify: `docs/roadmap/master-roadmap.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/specs/README.md`

**Interfaces:**

- Consumes: implemented R8 behavior and report evidence.
- Produces: canonical docs describing local observability truth.

- [ ] **Step 1: Update architecture docs**

Add implemented observability component, request-id middleware, readiness route,
event privacy boundary, trust-boundary row for the unauthenticated ops route,
the R8 evaluation report, and the explicit rule that observability context and
events are the only R8 cross-cutting imports allowed into product modules.
Preserve local-only and not-production-ready language.

- [ ] **Step 2: Update development guide**

Add local commands:

```text
curl --fail --silent --show-error http://localhost:8000/health
curl --fail --silent --show-error http://localhost:8000/api/v1/ops/readiness
./.venv/bin/python -m backend.observability.evaluation.cli run-readiness --suite r8-operational-readiness-v0.1
```

Explain that `/health` is liveness and ops readiness is diagnostic readiness.

- [ ] **Step 3: Update security policy**

Update `SECURITY.md` so it no longer claims the current chat route logs a user
message prefix after R8 removes that behavior. Keep raw exception-derived HTTP
500 details listed as a public-production blocker.

- [ ] **Step 4: Update local development runbook**

Route degraded model, Chroma, SQLite schema, memory, planner, and missing report
states to the R8 readiness command before destructive recovery.

- [ ] **Step 5: Update deployment and incident runbooks**

State that R8 local observability evidence improves diagnosis but does not pass
production telemetry, alerting, or retention gates.

- [ ] **Step 6: Update roadmap and indexes**

Keep R8 `In progress` until owner review accepts the implementation change set.
Do not mark `Accepted in working tree` or `Delivered` early.

- [ ] **Step 7: Run documentation checks**

Run:

```text
grep -R -n "OpenTelemetry\\|Prometheus\\|Sentry\\|Datadog" backend ARCHITECTURE.md SECURITY.md DEVELOPMENT.md docs/architecture docs/runbooks
grep -R -n "production-ready\\|public-production ready" docs/specs/2026-09-05-observability-and-operations-design.md docs/plans/2026-09-05-observability-and-operations-implementation.md ARCHITECTURE.md SECURITY.md DEVELOPMENT.md docs/architecture/current-state.md docs/runbooks
git diff --check
```

Expected: the first command exits `1` with no output, because vendor names should
remain only in R8 spec/plan/ADR review context. One reviewed exception is allowed:
a vendor name may appear in a Known Gaps or non-goal sentence that explicitly
denies adoption, such as naming that no exporter exists. Record any such hit as a
reviewed exception with its file and line instead of deleting the honest gap
statement. The second command may return existing and new hits; manually review
every hit and confirm production-readiness language is framed as blocked or not
claimed. Diff check is clean.

- [ ] **Step 8: Review checkpoint**

Review: docs match implemented behavior and do not overstate production
readiness.

Expected: R8 remains local development observability only.

## Task 8: Package Verification and Handoff

**Files:**

- Read: all files in the File Responsibility Map
- Modify: `docs/plans/2026-09-05-observability-and-operations-implementation.md`
- Modify: `docs/roadmap/master-roadmap.md`

**Interfaces:**

- Consumes: Tasks 1-7 outputs.
- Produces: R8 review packet and completed plan evidence.

- [ ] **Step 1: Run full backend tests**

Run:

```text
./.venv/bin/python -m pytest backend/tests
```

Expected: pass, or disclose exact known non-R8 blockage and run all focused R8
tests successfully.

- [ ] **Step 2: Run compile check**

Run:

```text
./.venv/bin/python -m compileall backend
```

Expected: exit `0`.

- [ ] **Step 3: Run R8 evaluation**

Run:

```text
./.venv/bin/python -m backend.observability.evaluation.cli run-readiness --suite r8-operational-readiness-v0.1
```

Expected: `result_state=PASS`.

- [ ] **Step 4: Run import-boundary checks**

Run:

```text
grep -RnE --include='*.py' "^[[:space:]]*(from|import)[[:space:]]+backend\.(rag|memory|planner|workspaces|conversations|orchestration|app\.api)" backend/observability/models.py backend/observability/redaction.py backend/observability/context.py backend/observability/events.py
grep -RnE --include='*.py' "^[[:space:]]*(from|import)[[:space:]]+backend\.(observability\.(readiness|evaluation)|app\.api\.ops)" backend/rag backend/memory backend/planner backend/workspaces backend/conversations backend/orchestration
```

Expected: each exits `1` with no output.

- [ ] **Step 5: Run privacy sentinel checks**

Run:

```text
grep -R -n "NEVER_LOG_USER_MESSAGE\\|NEVER_LOG_PROMPT\\|NEVER_LOG_MEMORY_TEXT\\|NEVER_LOG_ITINERARY_TEXT\\|NEVER_LOG_DECISION_STATEMENT\\|NEVER_LOG_TOKEN_VALUE" docs/reports/ops
```

Expected: no output, and exit `1` because `docs/reports/ops/` exists from Task 6
with no sentinel match. Exit `2` means `grep` could not read the directory, which
is a Task 6 failure to investigate rather than a passing privacy check.

- [ ] **Step 6: Run final diff checks**

Run:

```text
git diff --check
git status --short --untracked-files=all
```

Expected: diff check clean; status contains only intentional R8 files.

- [ ] **Step 7: Complete plan evidence**

Update this plan's Completion Record with final task status, verification
commands/results, reviewer findings, accepted limitations, and handoff commit
if one exists.

- [ ] **Step 8: Review checkpoint**

Review: final change set against the approved R8 spec and plan.

Expected: ready for repository-owner review; no Git delivery performed unless
the repository owner explicitly requested it.

## Package Verification

Run:

```text
./.venv/bin/python -m pytest backend/tests
./.venv/bin/python -m compileall backend
./.venv/bin/python -m backend.observability.evaluation.cli run-readiness --suite r8-operational-readiness-v0.1
grep -RnE --include='*.py' "^[[:space:]]*(from|import)[[:space:]]+backend\.(rag|memory|planner|workspaces|conversations|orchestration|app\.api)" backend/observability/models.py backend/observability/redaction.py backend/observability/context.py backend/observability/events.py
grep -RnE --include='*.py' "^[[:space:]]*(from|import)[[:space:]]+backend\.(observability\.(readiness|evaluation)|app\.api\.ops)" backend/rag backend/memory backend/planner backend/workspaces backend/conversations backend/orchestration
grep -R -n "NEVER_LOG_USER_MESSAGE\\|NEVER_LOG_PROMPT\\|NEVER_LOG_MEMORY_TEXT\\|NEVER_LOG_ITINERARY_TEXT\\|NEVER_LOG_DECISION_STATEMENT\\|NEVER_LOG_TOKEN_VALUE" docs/reports/ops
git diff --check
git status --short --untracked-files=all
```

Expected evidence:

1. backend tests pass or a known non-R8 external blockage is disclosed with all
   focused R8 tests passing;
2. compileall exits `0`;
3. R8 evaluation reports `PASS`;
4. import-boundary checks exit `1` with no output;
5. privacy sentinel check exits `1` with no output; exit `2` means
   `docs/reports/ops/` is missing, which is a Task 6 failure, not a pass;
6. diff check is clean;
7. final status contains only intentional R8 files.

## Rollback

Rollback removes R8 middleware, ops routes, observability modules, evaluation
fixtures/reports, and documentation references. Existing local app database,
Chroma data, RAG reports, memory reports, and planner reports remain compatible
because R8 adds no product data schema and no durable telemetry store.

## Completion Record

| Field | Value |
| --- | --- |
| Approval | ADR 0009 accepted, R8 spec v0.2 approved, and plan v0.3 approved by repository owner on 2026-09-05 |
| Execution | Not started |
| Verification | Not run |
| Owner review | Pending |
| Git delivery | Not authorized |

## Approval Record

| Version | Decision owner | Date | Notes |
| --- | --- | --- | --- |
| 0.1 | Repository owner | 2026-09-05 | Drafted for R8 review. External review found false-positive verification commands, stale R7 delivery wording, missing R8/R9 scope transfer notes, missing `SECURITY.md` updates, and a middleware latency guardrail without evidence |
| 0.2 | Repository owner | 2026-09-05 | Addressed the first R8 review round. Superseded by version 0.3 after review found the sentinel check expected exit `1` where an absent report directory returns exit `2`, and the vendor-name check had no recorded exception for an honest gap statement |
| 0.3 | Repository owner | Pending | Makes the sentinel check state its Task 6 dependency and distinguish exit `1` from exit `2`, and records the reviewed vendor-name exception for Known Gaps and non-goal statements that deny adoption. Approval authorizes implementation in an isolated worktree only, not Git delivery, production deployment, external telemetry vendors, authentication, frontend work, public exposure, or raw HTTP 500 response-body hardening |
