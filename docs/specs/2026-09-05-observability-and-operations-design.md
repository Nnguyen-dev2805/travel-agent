# Observability and Operations Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.2 |
| Date | 2026-09-05 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Runtime milestone R8 - local privacy-safe observability contracts, request correlation, readiness diagnostics, operational evaluation, and runbook integration |
| Parent design | [Architecture Baseline Design](./2026-08-31-architecture-baseline-design.md), version 0.1; [Operations and Security Design](./2026-08-31-operations-and-security-design.md), version 0.1; [Evaluation Protocols Design](./2026-08-31-evaluation-protocols-design.md), version 0.1 |
| Depends on | `D6` accepted operations and security guidance; `R2` accepted evaluation harness vocabulary; `R6` delivered memory retrieval; `R7` delivered planner state on the active development branch at `57e70fe`; [ADR 0009](../adr/0009-privacy-safe-local-observability-boundary.md) (Accepted) |
| Architecture approval | Approved by repository owner on 2026-09-05 |
| Implementation plan | [Observability and Operations Implementation Plan](../plans/2026-09-05-observability-and-operations-implementation.md), version 0.3 (Approved) |
| Related issue | None - R8 documentation drafting was authorized by the repository owner in conversation on 2026-09-05 |
| Superseded document | None |

## Summary

R8 adds local observability and operations evidence without turning the prototype
into a production service. It introduces structured privacy-safe operational
events, request correlation, readiness diagnostics, and an R8 evaluation report
that can show whether a developer can diagnose degraded RAG, model, storage,
memory, and planner paths without leaking secrets or user content.

## Current-state Evidence

Verified current implementation:

1. `backend/app/main.py` configures global logging with
   `logging.basicConfig(...)`, mounts health, chat, workspace, conversation,
   memory, and planner routers, and attempts RAG pre-warm during app lifespan.
2. `backend/app/api/health.py` exposes `GET /health` returning only `status`
   and `service`.
3. `backend/app/api/chat.py` still logs the first 50 characters of the stripped
   user message before calling the conversation orchestrator.
4. Chat exception handling now has controlled conversation-storage errors, but
   RAG `ValueError` and generic exception branches still log exception strings
   and return details derived from those strings.
5. `backend/app/config.py` owns local settings, including `APP_DB_PATH`,
   `GITHUB_TOKEN`, `LLM_MODEL`, and R6 memory retrieval flags.
6. R5 and R6 memory evaluation commands write local Markdown and JSON reports
   under `docs/reports/memory/`.
7. R7 planner evaluation writes local Markdown and JSON reports under
   `docs/reports/planner/`.
8. Package 6 runbooks define readiness, incident response, and privacy-safe
   evidence expectations, but they do not implement runtime diagnostics.
9. `SECURITY.md` names prompt-prefix logging and raw HTTP 500 exception details
   as current public-production blockers.

Verified gaps:

1. No `backend/observability/` package exists.
2. There is no request correlation id in responses or logs.
3. There is no readiness endpoint or CLI that distinguishes liveness from
   degraded model, Chroma, SQLite, memory, planner, or evaluation evidence.
4. There is no structured event contract that blocks raw prompts, messages,
   model responses, memory text, itinerary text, decision statements, tokens,
   or raw filesystem paths from logs and reports.
5. There is no R8 operational evaluation fixture or report.

## Context

The project now has enough local product state that a simple process health
check is too weak. A developer needs to know whether the API process is alive,
whether the configured model credential is present, whether local Chroma data is
available, whether the shared SQLite store is compatible, whether memory
retrieval is enabled or degraded, and whether planner state can be inspected.

At the same time, Package 6 explicitly warns that operational evidence must not
become a second data leak. The right R8 shape is therefore local and bounded:
add structured diagnostics and privacy-safe logs now, defer production tracing,
alerting, retention, and telemetry vendor choices to later deployment work.

R8 deliberately absorbs one narrow R9-adjacent item: removing prompt-prefix
logging from the chat path. That item is operational evidence hygiene. R9 still
owns authentication, authorization, tenant isolation, deletion semantics,
broader redaction policy, and production privacy hardening.

## Users

1. **Repository owner:** needs a clear answer to "what is degraded and why?"
   before approving later runtime or release work.
2. **Developer:** needs local commands and routes that separate liveness,
   readiness, data availability, model configuration, and feature-gate state.
3. **Coding agent:** needs exact event and readiness contracts that prevent raw
   content from appearing in evidence.
4. **Reviewer:** needs tests proving logs and reports are useful but
   privacy-safe.
5. **Future operator:** needs stable event names and reason codes that can later
   be mapped to production tracing and alerting.

## Problem Statement

The current backend can fail in many ways that `/health` cannot identify. A
successful `/health` response does not prove model-provider readiness, RAG data
availability, memory retrieval quality, planner state integrity, SQLite schema
compatibility, or safe error behavior. Current ad hoc logs also make it too
easy to leak user messages or exception details while trying to debug a failure.

R8 must create a local operational evidence layer that is structured enough to
debug and test, but narrow enough not to decide production observability
architecture prematurely.

## Goals

R8 must:

1. Preserve the existing `/health` response body for compatibility.
2. Add server-generated request correlation for backend requests.
3. Add structured privacy-safe operational events with fixed event names,
   components, severity, result, ids, reason codes, durations, and counters.
4. Remove chat prompt-prefix logging and replace it with content-free request
   and outcome events.
5. Add readiness diagnostics that distinguish app liveness, model credential
   presence, RAG data availability, SQLite store compatibility, memory feature
   state, planner state availability, and latest local evaluation report state.
6. Ensure readiness probes are read-only and never create databases, create
   Chroma collections, migrate schema, call external providers, or mutate
   evaluation artifacts.
7. Add an ops route or command that returns/writes only safe diagnostic fields.
8. Add deterministic R8 operational evaluation with a Markdown and JSON report.
9. Update runbooks and development docs with the new local diagnostics.
10. Keep production observability, alerting, dashboards, and telemetry retention
    explicitly out of scope.

## Non-goals

R8 does not add authentication, authorization, user identity, production
deployment, TLS, restrictive production CORS, rate limiting, cloud logging,
OpenTelemetry, Prometheus, Sentry, Datadog, dashboards, alert routing, durable
telemetry storage, retention periods, backup/restore, model-provider health
calls, frontend UI, booking integrations, or changes to RAG, memory, or planner
business behavior.

R8 does not change response bodies for existing chat, workspace, conversation,
memory, or planner APIs. Adding a response header for request correlation and a
new ops route is allowed. R8 does not fix raw exception-derived HTTP 500 detail
bodies; that remains a public-production blocker for later security hardening.

## Assumptions

Implementation must stop if any assumption differs:

1. The implementation base includes R7 source and docs through `57e70fe`, or a
   later repository-owner selected base.
2. `GET /health` remains the compatibility liveness endpoint and keeps its
   current response body fields.
3. R8 can add new backend modules and routes without selecting a production
   observability vendor.
4. Readiness checks can report `unknown` or `not_configured` when a dependency
   cannot be inspected safely without creating state.
5. Local diagnostics do not need a model-provider network call; credential
   presence and configured model metadata are sufficient for R8.
6. R8 evaluation can use synthetic fixtures and log-capture tests without real
   credentials, real user data, external model calls, or Chroma downloads.
7. Existing local reports under `docs/reports/rag/`, `docs/reports/memory/`, and
   `docs/reports/planner/` are operational evidence inputs, not production
   telemetry.
8. R8 evaluation uses D5 result states but is a milestone-scoped operational
   evaluation harness. It does not create a new canonical D5 operations
   protocol file.
9. R8 fixture and report artifacts belong under tracked `docs/evaluation/` and
   `docs/reports/` paths, not under gitignored `data/`.

## User and System Flows

### Request Correlation

API request -> middleware creates `rq_<uuid.uuid4().hex>` -> request id is held
in a context variable -> route/service events include the request id when
available -> response includes `X-Request-ID` -> logs never include request
body, query string, prompt, answer, or raw exception text.

Browser callers may read the request id because R8 exposes `X-Request-ID`
through CORS. The header is for local correlation only and is not an
authentication or authorization token.

### Readiness Inspection

Local caller -> `GET /api/v1/ops/readiness` or CLI command -> readiness service
runs read-only probes -> response/report returns component statuses, reason
codes, selected safe ids, counts, flags, and missing-evidence markers -> caller
uses runbook guidance to decide whether to continue, degrade, or stop.

### Operational Evaluation

Evaluation command -> replays synthetic cases for redaction, event validation,
readiness status composition, missing data, incompatible store markers, and
report rendering -> writes `docs/reports/ops/r8-operational-readiness-v0.1.*`
-> report state is `PASS`, `FAIL`, `INCONCLUSIVE`, or `INVALID`.

## Alternatives Considered

### A. Adopt OpenTelemetry in R8

This would provide industry-standard traces and exporters. It is rejected for
R8 because exporter choice, sampling, retention, access control, and production
log storage are not approved. R8 should create stable local contracts that a
future OpenTelemetry adapter can map to later.

### B. Extend Existing Ad Hoc Logs Only

This is smaller, but it keeps privacy safety dependent on every call site. It is
rejected because the project already has prompt-prefix logging and exception
string exposure. R8 needs central validation and tests.

### C. Structured Local Events, Readiness, and Evaluation

This is selected. It gives useful diagnostics now, keeps privacy boundaries
reviewable, and avoids premature production infrastructure decisions.

## Components and Dependency Direction

R8 introduces this boundary:

```text
FastAPI middleware and ops routes
↓
Observability request context, event logger, readiness service
↓
Read-only probes over settings, filesystem metadata, reports, schema registry,
and optional domain repository health helpers
```

Allowed dependencies:

1. `backend/observability/models.py`, `redaction.py`, `context.py`, and
   `events.py` may use only standard library and Pydantic if already available.
   They must not import RAG, memory, planner, workspace, conversation,
   orchestration, or app route modules.
2. Domain and route modules may import `backend.observability.context` and
   `backend.observability.events` to emit safe events. They must not import
   readiness or evaluation modules.
3. `backend/observability/readiness.py` may inspect settings, reports, schema
   registry metadata, and safe filesystem facts. If it imports domain adapters,
   it must not call constructors that create databases, directories,
   collections, or schema.
4. `backend/observability/evaluation/*` may construct synthetic inputs and call
   observability code. It must not call external providers.
5. `backend/app/api/ops.py` may call the readiness service only. It must not
   contain probe logic, SQL, Chroma calls, filesystem traversal, or redaction
   policy.

Forbidden dependencies:

1. RAG, memory, planner, workspace, conversation, and orchestration modules must
   not import `backend.observability.readiness`, `backend.observability.evaluation`,
   or `backend.app.api.ops`.
2. Observability events must not depend on any product-domain model to avoid
   circular ownership.
3. Readiness must not instantiate `ChromaVectorStore` when doing so would create
   a directory or collection as a side effect.
4. Observability context and event emission are the only R8 cross-cutting
   imports allowed into RAG, memory, planner, workspace, conversation,
   orchestration, storage, and route modules.

## Data Flow and Lifecycle

Operational events are emitted to process logs only. R8 does not add a telemetry
database or schema registry module. Every event is built from approved safe
fields, assigned an `ev_<uuid.uuid4().hex>` identifier, and validated before it
is logged.

Readiness snapshots are computed on demand. They can be returned by the ops
route or written by the evaluation command, but they are not product records and
do not mutate application state.

R8 reports are local documentation artifacts under `docs/reports/ops/`. They may
contain component names, status, reason codes, counts, booleans, run ids, and
safe report paths relative to the repository. They must not contain raw user
content, secrets, prompts, answers, provider payloads, raw filesystem paths, or
stack traces.

## Behavioral and Data Contracts

### Request ID

Request ids are server-generated strings using the prefix `rq_` plus
`uuid.uuid4().hex`. R8 does not trust or persist caller-supplied request ids.
The response header is:

```text
X-Request-ID: rq_<32 lowercase hex characters>
```

The FastAPI CORS middleware must expose this header to local browser clients:

```python
expose_headers=["X-Request-ID"]
```

### Event

The event contract contains:

| Field | Type | Rule |
| --- | --- | --- |
| `event_id` | string | `ev_` plus `uuid.uuid4().hex` |
| `timestamp` | UTC datetime | Server-generated |
| `event_name` | enum/string | Controlled names such as `api.request.completed`, `chat.turn.completed`, `rag.retrieval.completed`, `model.call.failed`, `memory.retrieval.completed`, `planner.operation.applied`, `storage.schema.failed`, `ops.readiness.completed` |
| `component` | enum/string | `api`, `chat`, `rag`, `model_provider`, `storage`, `workspace`, `conversation`, `memory`, `planner`, `ops` |
| `severity` | enum | `info`, `warning`, `error` |
| `result` | enum | `success`, `failure`, `degraded`, `skipped` |
| `request_id` | optional string | Current request id only |
| ids | optional strings | Workspace, conversation, message, memory, itinerary, decision, or operation ids |
| `failure_class` | optional string | Controlled class name, not exception text |
| `reason_code` | optional string | Controlled reason code |
| `duration_ms` | optional number | Non-negative |
| `counters` | mapping | Bounded scalar values only |

Unsafe keys are rejected before logging. Unsafe values are redacted if they
match token-like patterns, path-like values, or configured secret names.

### Readiness Snapshot

The readiness snapshot contains:

```json
{
  "status": "ready",
  "checked_at": "2026-09-05T00:00:00Z",
  "components": [
    {
      "name": "app",
      "status": "ready",
      "reason_code": "ok",
      "details": {"version": "1.0.0"}
    }
  ]
}
```

Status values are `ready`, `degraded`, `not_ready`, and `unknown`. Details are
safe scalar values only. A missing optional capability should report `degraded`
or `unknown`, not pretend success.

Minimum components:

1. `app`: settings loaded and version available.
2. `model_provider`: credential presence and model name only, no network call.
3. `rag_chroma`: local Chroma path/collection availability without creating
   state.
4. `app_db`: SQLite file presence and schema registry compatibility when safely
   inspectable.
5. `memory`: feature flag state and latest memory report state when present.
6. `planner`: planner module/report state when R7 exists in the selected base.
7. `evaluation_reports`: latest known RAG, memory, and planner report states.

## Errors and Edge Cases

1. Missing `.env` or absent `GITHUB_TOKEN` reports `model_provider` as
   `not_ready` with `credential_missing`, not as a process failure.
2. Missing Chroma data reports `rag_chroma` as `not_ready` or `unknown`, but the
   probe must not create the directory or collection.
3. Missing SQLite app database reports `app_db` as `unknown` or `not_ready`,
   depending on the requested readiness profile. It must not create the file.
4. Incompatible schema registry metadata reports `storage.schema.failed` and
   `app_db` `not_ready` without running migrations.
5. Missing RAG/memory/planner reports are evidence gaps, not failures of the
   application process.
6. Event validation failures are test failures and must not be silently logged
   as raw dictionaries.

## Security and Privacy

R8 operational evidence is sensitive metadata. It may contain stable ids and
counts, but never raw content. Requirements:

1. No secrets, token values, environment values, `.env` content, provider
   payloads, raw prompts, full messages, assistant answers, retrieved chunk
   text, memory text, itinerary text, decision statements, raw stack traces, or
   raw filesystem paths in logs, readiness responses, or R8 reports.
2. Event redaction must happen before serialization.
3. Request bodies and query strings must not be logged.
4. Exception logging must use controlled `failure_class` values and reason codes
   instead of arbitrary exception strings for user-facing paths.
5. Readiness routes remain unauthenticated local development routes and must not
   be represented as production-safe.

## Observability and Operations

R8 itself is the observability milestone. It defines:

1. a stable local event vocabulary;
2. request correlation in logs and response headers;
3. readiness status and component reason codes;
4. a local CLI/report path for operational review;
5. runbook updates that route degraded model, RAG, storage, memory, and planner
   states to the right recovery or incident process.

Operational status is intentionally local. R8 does not create alert thresholds,
SLOs, paging policy, retention durations, or production dashboards.

## Testing and Evaluation

R8 implementation must add focused tests for:

1. event id and request id generation;
2. unsafe key rejection;
3. token-like, path-like, and content-like redaction;
4. no raw chat message in captured logs;
5. no raw memory or planner content in captured logs;
6. `/health` response compatibility;
7. readiness response schema and safe details;
8. read-only readiness probes that do not create app DB or Chroma state;
9. R8 evaluation report result-state and report rendering.

The evaluation is milestone-scoped and local. It borrows D5 result-state names
for consistency but does not create a new D5 protocol document.

The R8 evaluation fixture lives under:

```text
docs/evaluation/fixtures/ops/r8-operational-readiness-v0.1/
```

The R8 reports live under:

```text
docs/reports/ops/r8-operational-readiness-v0.1.json
docs/reports/ops/r8-operational-readiness-v0.1.md
```

## Failure and Recovery

R8 must fail safe:

1. If an event contains unsafe fields, the event builder rejects it before
   serialization.
2. If readiness cannot inspect a dependency without side effects, it reports
   `unknown` with a reason code.
3. If an ops report cannot parse required inputs, it reports `INVALID`.
4. If full backend tests are blocked by a known non-R8 environment issue, the
   R8 worker must disclose it and run focused R8 tests plus compile and boundary
   checks.

Permanent production remediation remains governed by Package 6 and future
runtime specs.

## Capacity, Latency, and Cost

R8 adds no network calls and no vendor cost. Event building should be constant
time with bounded payload size. Readiness probes must be cheap local metadata
checks and should not perform full Chroma scans, embedding generation, model
calls, or data migrations.

## Compatibility and Staged Migration

R8 is additive. Existing route response bodies remain compatible. `/health`
keeps the current response body. New correlation appears as an HTTP response
header and structured logs. New readiness and evaluation outputs are opt-in.

R8 updates `SECURITY.md`, `ARCHITECTURE.md`, `DEVELOPMENT.md`, current-state
architecture, runbooks, roadmap, and indexes after implementation. It does not
change database schema versions or product data.

## Required ADRs

1. [ADR 0009](../adr/0009-privacy-safe-local-observability-boundary.md) records
   the local structured-event and readiness boundary.

## Rollout and Migration

1. Accept ADR 0009.
2. Approve this spec.
3. Approve the R8 implementation plan.
4. Implement in an isolated worktree from the repository-owner selected base.
5. Run R8 tests, operational evaluation, compile, boundary checks, and docs
   verification.
6. Mark R8 `Accepted in working tree` only after owner review acceptance.
7. Mark R8 `Delivered` only after Git delivery occurs.

## Rollback

Rollback removes observability modules, ops routes, middleware wiring, R8
fixtures/reports, and R8 documentation references. Since R8 adds no durable
product data store, local application databases remain compatible.

## Acceptance Criteria

R8 can be accepted when ADR 0009 is accepted, this spec and its implementation
plan are approved, implementation creates the planned observability contracts,
request correlation, readiness diagnostics, evaluation reports, and docs, R8
tests pass, `/health` compatibility is preserved, logs/reports are privacy-safe,
and no existing RAG, memory, planner, or product-data behavior changes outside
the approved instrumentation surface.

## Approval Record

| Version | Decision owner | Date | Notes |
| --- | --- | --- | --- |
| 0.1 | Repository owner | 2026-09-05 | Drafted for R8 review. External review found false-positive verification commands, stale R7 delivery wording, missing R8/R9 scope transfer notes, missing `SECURITY.md` updates, and a middleware latency guardrail without evidence |
| 0.2 | Repository owner | 2026-09-05 | Addressed the R8 review feedback by tightening verification commands, marking R7 delivered locally, recording the narrow R9-adjacent prompt-log fix, keeping HTTP 500 body hardening out of scope, clarifying milestone-scoped ops evaluation, exposing `X-Request-ID`, and adding security/trust-boundary documentation requirements. Approval authorizes accepting ADR 0009 and approving the implementation plan. It does not authorize Git delivery, production deployment, external telemetry vendors, authentication, default public exposure, or frontend work |
