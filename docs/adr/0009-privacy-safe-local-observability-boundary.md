# ADR 0009: Privacy-safe Local Observability Boundary

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-05 |
| Decision owners | Repository owner |
| Scope | R8 local observability, readiness, diagnostic reports, structured event shape, and privacy-safe operational evidence |
| Governing spec | [Observability and Operations Design](../specs/2026-09-05-observability-and-operations-design.md), version 0.2 |
| Superseded ADR | None |
| Superseded by | None |

## Context

Travel Agent now has local RAG, workspace, conversation, memory, and planner
paths. Those paths can fail for different reasons: a process can be alive while
the model credential is absent, Chroma data is missing, memory retrieval is
feature-gated off, SQLite schema ownership is incompatible, or planner writes
fail closed.

The current repository has a basic `/health` route and ad hoc logs. That is not
enough operational evidence for later milestones, but a full vendor tracing
stack would choose production infrastructure before the project has an approved
deployment architecture. R8 therefore needs a durable local boundary: useful
diagnostic signals without storing secrets, prompts, full user content, model
responses, or provider payloads.

The existing prompt-prefix log is a public-production blocker named in the
security policy and was previously left for later security hardening. R8 takes
over that one operational evidence item because it directly affects local log
safety. Broader R9 work such as authentication, authorization, deletion,
tenant isolation, and production privacy controls remains outside this decision.

## Decision

R8 will introduce a local `backend/observability/` module for privacy-safe
operational evidence. It will own:

1. structured event contracts;
2. redaction and safe-field validation;
3. request correlation context;
4. local readiness probes;
5. deterministic observability evaluation and reports.

The selected event channel is standard-library logging with structured JSON
messages. R8 will not introduce OpenTelemetry, Prometheus, Sentry, Datadog,
Grafana, a durable telemetry database, or a cloud log pipeline.

The allowed event payload is intentionally narrow:

```text
event_id, timestamp, event_name, component, severity, result, request_id,
workspace_id, conversation_id, message_id, memory_id, itinerary_version_id,
decision_id, operation_id, failure_class, duration_ms, and bounded counters.
```

R8 event payloads must not contain raw message content, prompts, retrieved
chunk text, memory text, itinerary text, decision statements, model responses,
provider request or response bodies, token values, environment values, raw file
paths, stack traces, or arbitrary exception strings.

Readiness is local and bounded. `/health` remains a simple liveness endpoint for
backward compatibility. A new readiness surface may report component states and
reason codes, but it must not perform state-changing setup, create databases,
create Chroma collections, call external model providers, or expose sensitive
configuration values.

## Alternatives

### Adopt OpenTelemetry Immediately

OpenTelemetry would align with common production observability practice and
could support traces, metrics, and exporters later. It is rejected for R8
because exporter choice, sampling, retention, and production telemetry access
are deployment and privacy architecture decisions that are not approved yet.

### Keep Ad Hoc Logs and Extend Runbooks Only

This preserves the smallest code change, but it leaves every module free to log
different fields and makes privacy-safety hard to review. It is rejected
because R8 needs deterministic evidence that operational logs and reports avoid
raw user content and secrets.

### Local Structured Events and Readiness Reports

This is selected. It gives developers and reviewers a useful local diagnostic
surface now, keeps event fields reviewable, and leaves vendor telemetry as a
future architecture decision.

## Consequences

### Positive

1. Operators can distinguish liveness from degraded RAG, model, memory, planner,
   and storage paths.
2. Reviewers get deterministic tests for log and report privacy safety.
3. Later production observability can map from stable local event contracts
   instead of retrofitting unstructured logs.
4. R8 can run without network access or a model provider.

### Negative

1. R8 does not provide production tracing, dashboards, alerts, or retention.
2. Local JSON logs are useful evidence, not a centralized telemetry system.
3. Readiness probes must be conservative where current dependencies only expose
   state-changing constructors.
4. Additional instrumentation increases the need for careful tests around user
   content leakage.

## Migration

R8 is additive. It adds local observability code, a readiness route or local
diagnostic command, tests, reports, and runbook updates. It does not change
existing user-facing response bodies, database schema versions, Chroma data,
memory behavior, planner behavior, RAG answer quality, or production deployment
topology.

R8 removes unsafe prompt-prefix logging, but it does not redesign HTTP 500
response bodies or close all public-production security blockers.

Rollback removes the `backend/observability/` module, the ops route wiring, the
R8 evaluation fixtures and reports, and the R8 documentation references.
Existing application state remains compatible because R8 defines no new durable
product data store.

## Validation

R8 implementation must prove:

1. `/health` response compatibility is preserved;
2. readiness reports component status and reason codes without state-changing
   setup;
3. structured events reject or redact unsafe fields;
4. chat, memory, planner, storage, and readiness logs exclude raw user content,
   prompts, model responses, provider payloads, secrets, and raw file paths;
5. the R8 operational evaluation reports `PASS`;
6. existing RAG, memory, and planner import-boundary checks remain clean.

## References

1. [Observability and Operations Design](../specs/2026-09-05-observability-and-operations-design.md)
2. [Observability and Operations Implementation Plan](../plans/2026-09-05-observability-and-operations-implementation.md)
3. [Operations and Security Design](../specs/2026-08-31-operations-and-security-design.md)
4. [Deployment Readiness Runbook](../runbooks/deployment.md)
5. [Incident Response Runbook](../runbooks/incident-response.md)
