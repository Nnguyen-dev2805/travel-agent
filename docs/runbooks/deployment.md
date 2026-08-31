# Deployment Readiness Runbook

## Scope and Current State

Travel Agent has no approved production deployment topology. The current
Dockerfiles and Docker Compose configuration are local-development contracts,
including a Vite development server, bind mounts, published ports, no implemented
user authentication, and permissive CORS that includes `*`.

This document is therefore a provider-neutral readiness and promotion gate. It
does not contain a cloud deployment procedure and does not authorize public
exposure. Current implementation truth lives in
[Current-state Architecture](../architecture/current-state.md); security policy
lives in [Security Policy](../../SECURITY.md).

## Evidence Required for Promotion

Promotion evidence must be current, reviewable, tied to the exact release
candidate, and produced by the owner of the relevant control. A document that
states a desired control is not evidence that the runtime implements it.

Evidence should include, as applicable:

- approved spec/ADR identifiers;
- versioned artifact or commit identity;
- test/evaluation run identifiers and results;
- configuration review without secret values;
- health/readiness and rollback evidence;
- incident/operator ownership;
- data-store lifecycle and recovery evidence.

Missing, unknown, stale, contradictory, or non-reviewable evidence is a failed
gate.

## Public Production Gate

Public production is **BLOCKED** unless every applicable row below passes.
There is no partial score and no average across rows.

| Gate family | Required evidence | Current outcome |
| --- | --- | --- |
| 1. Approved deployment architecture and ADRs | Approved production topology, trust boundaries, runtime ownership, and all required ADRs | **BLOCKED** - no production topology is approved |
| 2. Authentication and authorization | Implemented and tested identity, authentication, authorization, and failure behavior for user-scoped capabilities | **BLOCKED** - bounded backend has no implemented user authentication/authorization |
| 3. Tenant/workspace isolation | Tests and design evidence that persisted/retrieved user data cannot cross user/workspace scope | **BLOCKED** - user/workspace runtime is not implemented |
| 4. Restrictive environment-specific CORS | Reviewed allowlist for trusted production origins; no wildcard credentialed public API | **BLOCKED** - current CORS includes `*` |
| 5. TLS and trusted public origins | Approved TLS termination, trusted origins, and public endpoint boundary | **BLOCKED** - no production ingress/TLS topology is approved |
| 6. Production secret storage and rotation | Approved secret storage, access, injection, rotation, and incident procedure | **BLOCKED** - current local `.env`/`GITHUB_TOKEN` handling is not a production secret-management contract |
| 7. Privacy-safe logs, traces, and errors | Evidence that secrets/unnecessary user content are excluded and client errors do not expose unsafe internal details | **BLOCKED** - current chat logs a prompt prefix and can return raw exception detail |
| 8. Approved stores and lifecycle | Approved store ownership, access scope, retention, deletion, backup, restore, replica/derived-copy behavior, and verification | **BLOCKED** - no approved production user-data store or lifecycle exists |
| 9. Health and readiness | Checks that distinguish process health from required dependency/RAG/model readiness, with reviewed failure behavior | **BLOCKED** - `/health` exists, but production readiness semantics are not approved |
| 10. Runtime resource controls | Reviewed timeout, retry, rate-limit, resource, concurrency, and cost controls appropriate to the release | **BLOCKED** - no production runtime-control budget is approved |
| 11. Versioned reproducible artifacts | Versioned deployable artifact and reproducible dependency installation/build evidence | **BLOCKED** - current development images are not an approved release artifact contract |
| 12. Rollback and state compatibility | Tested rollback path plus explicit data/schema/state compatibility boundary | **BLOCKED** - no production rollback/state contract exists |
| 13. Incident ownership | Reachable operator path, incident owner, evidence path, containment and recovery handoff | **BLOCKED** - this runbook defines readiness expectations, not a deployed operator organization |
| 14. Package 5 RAG/memory quality and safety | Passing governed RAG gates and, for memory claims, all applicable memory quality gates plus zero hard-safety failures | **BLOCKED** - no release candidate has supplied complete Package 5 production-promotion evidence |

Because multiple mandatory rows are blocked, the current prototype must not be
represented as public-production ready.

## Pre-deployment Review

Before any environment promotion is authorized:

1. identify the exact release candidate and intended environment;
2. confirm the approved deployment architecture and required ADRs;
3. walk all 14 gate rows and attach current evidence;
4. confirm secret values are absent from review artifacts;
5. confirm data stores and migrations have reviewed retention/deletion/backup/
   restore ownership;
6. confirm Package 5 evaluation evidence matches the behavior being claimed;
7. confirm rollback and incident ownership are available before exposure.

If any applicable item is missing or uncertain, stop. The outcome is
**BLOCKED**, not "pass with follow-up".

## Promotion Sequence

Once a later approved deployment architecture exists and all mandatory gates
pass, promotion should follow this provider-neutral sequence:

1. freeze the reviewed release candidate identity;
2. verify reproducible build/artifact evidence;
3. verify environment configuration and secret references without printing
   secret values;
4. apply only the approved environment-specific deployment procedure;
5. keep exposure bounded until post-deployment checks pass;
6. run health, readiness, security-boundary, data, and quality smoke checks;
7. compare results with predeclared success/rollback criteria;
8. either accept the promotion or execute the tested rollback path.

Provider commands, URLs, DNS records, credentials, and vendor settings are
intentionally absent until their architecture is approved.

## Post-deployment Verification

Post-deployment verification must cover the release's actual behavior, not only
process liveness:

- process health and dependency readiness;
- authentication/authorization denial and success paths;
- workspace/user isolation where applicable;
- trusted origin/CORS and TLS boundary;
- secret non-disclosure in logs/errors;
- required data-store read/write/delete behavior;
- degraded-provider behavior and retry/timeout controls;
- RAG evaluation smoke/regression evidence;
- memory hard gates whenever memory is active;
- rollback trigger observability.

A failed hard safety gate, leakage event, or unsafe public exposure routes
immediately to [Incident Response](./incident-response.md).

## Degraded Dependency Handling

Health and readiness must distinguish a running process from degraded model,
retrieval, memory, planner, storage, or external-provider behavior. A dependency
failure must not silently convert unsupported behavior into a successful answer
or production-ready state.

The release design must define which capabilities fail closed, which may degrade
with an explicit limitation, and what evidence triggers rollback or incident
handling. Package 6 does not invent those per-feature runtime decisions.

## Rollback Readiness

Rollback is a precondition for promotion, not an improvised incident step. A
later production design must identify:

- the previous known-good artifact/version;
- the exact rollback trigger;
- the operator/decision owner;
- the rollback procedure;
- expected impact and downtime boundary where applicable;
- post-rollback health, security, data-integrity, and quality verification.

No public promotion should proceed when rollback is untested or its state impact
is unknown.

## State Compatibility

Rollback must account for durable state. Before a release can modify schemas,
indexes, workspace/conversation/memory data, planner state, or evaluation traces,
its approved design must state whether old and new application versions can read
the same state and how incompatible changes are reversed or migrated.

Unknown state compatibility fails closed. Do not use destructive data cleanup as
a substitute for a tested rollback boundary.

## Incident Handoff

Promotion or operation stops and hands off to
[Incident Response](./incident-response.md) when evidence shows credential
exposure, private-data leakage, unauthorized access, cross-scope leakage,
deleted-memory retrieval, unsafe public exposure, integrity loss, provider
compromise, prompt-injection boundary crossing, or supply-chain compromise.

Record the release identity, affected component, gate/result state, redacted
evidence, and containment action without copying secrets or unnecessary user
content.

## Unsupported Actions and Stop Conditions

This runbook does not authorize:

- choosing a cloud, reverse proxy, secret manager, database, observability
  vendor, backup technology, or authentication model;
- inventing a production URL, DNS record, credential, SLO, retention period, or
  capacity budget;
- exposing the current unauthenticated/wildcard-CORS API publicly;
- treating documentation as evidence that a runtime control exists;
- overriding Package 5 hard safety gates with aggregate metrics;
- applying provider/hosting changes without the approved architecture and
  execution authority;
- staging, committing, pushing, opening/merging a PR, or releasing without the
  repository owner's explicit Git-delivery instruction.

When the necessary architecture or evidence does not exist, the correct result
is **BLOCKED** and the next step is governed design work.
