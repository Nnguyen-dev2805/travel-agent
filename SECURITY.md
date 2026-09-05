# Security Policy

## Scope and Maturity

Travel Agent is an early local RAG prototype. This policy defines repository
security, privacy, trust, evidence-handling, and production-readiness rules. It
does not implement runtime controls and does not certify the current system as
production-ready.

The implemented architecture is described in
[Current-state Architecture](docs/architecture/current-state.md). Future
security-sensitive runtime changes still require their own approved
specification, implementation plan, and any required architecture approval or
ADR.

## Vulnerability Reporting

Do not publish exploit details, credentials, private user data, or sensitive
system evidence in a public issue, pull request, discussion, or other public
repository artifact.

This repository has not verified that a specific private vulnerability-reporting
feature is enabled. When no verified private channel is known, publish only a
minimal non-sensitive request asking the repository owner for a private contact
path. Do not include reproduction details in that public request.

When a private path is available, provide only what is necessary to assess the
report:

- affected version or commit;
- impact and affected scope;
- minimal reproduction conditions;
- relevant redacted evidence;
- a suggested mitigation when it is safe and useful to share.

This policy does not promise a response-time SLA.

## Sensitive Evidence

Security, evaluation, and incident evidence must use the minimum information
needed for review. Prefer public, synthetic, or redacted examples over live user
content. Prefer stable IDs, labels, hashes, counts, timestamps, component states,
and short redacted excerpts over full prompts, conversations, traces, or
screenshots.

Never place real secrets or unnecessary private user data in repository files,
issues, pull requests, benchmark artifacts, screenshots, logs, or review notes.
If evidence already contains sensitive data, redact it before preserving or
sharing the evidence.

## Secret Handling

Secrets must come from environment variables or a future approved secret
manager. They must never be committed to source, documentation, fixtures,
benchmark data, screenshots, issues, traces, or logs.

The current model credential name is `GITHUB_TOKEN`. The repository-root `.env`
is local configuration and must remain ignored. Example environment files may
contain variable names and safe placeholders only; they must never contain a
usable credential.

If a credential may have been exposed, treat it as an incident and follow
[Incident Response](docs/runbooks/incident-response.md). Do not rely on deleting
the leaked text alone; credential revocation or rotation belongs to the owning
provider/account workflow.

## Data Classification

The following five classes are the repository-wide handling vocabulary. Listed
future data types are policy examples, not claims that those stores exist today.

| Class | Examples | Commit | Logging | Persistence | External transmission | Review expectation |
| --- | --- | --- | --- | --- | --- | --- |
| Public project data | Source, public docs, public travel knowledge, synthetic fixtures | Allowed when provenance and licensing permit | Allowed when useful | Allowed for approved project purposes | Allowed through approved public/project flows | Normal repository review |
| Operational metadata | Request IDs, timings, counts, component states, redacted failure labels | Only when useful and non-sensitive | Preferred operational evidence | Only for an approved operational purpose | Only when the operational data flow is approved | Confirm purpose, minimization, and access |
| User content | Chat text, itinerary preferences, future workspace or conversation content | Do not commit | Minimize; full content is not the default | Only through an approved user-data store and lifecycle | Only through an approved data flow | Confirm purpose, scope, retention, deletion, and provider handling |
| Sensitive user data | Precise travel identity data, contact details, travel documents, financial or other high-impact personal data if introduced | Do not commit | Do not log by default | Requires explicit approved purpose, access scope, retention, and deletion | Requires explicit approved purpose and provider/data-flow review | Strong security/privacy review before collection or use |
| Secrets | API tokens, credentials, signing keys, private connection material | Never | Never | Environment or approved secret manager only | Only to the service that requires the secret | Treat exposure as an incident |

## Logging and Traces

Operational evidence should explain system state without reproducing user
content. Prefer request/run IDs, component names, timings, selected document or
memory IDs, failure labels, counters, and redacted excerpts.

Full prompt, conversation, retrieved content, or model-output logging is not the
default debugging mechanism. User-content logging requires an approved purpose,
scope, access model, and retention/deletion behavior. Secret values must never
be logged or traced.

The current chat route logs a prefix of the user message and may expose raw
exception text in HTTP 500 details. Those behaviors are current prototype risks
and public-production blockers; this policy does not approve them as production
telemetry or error handling.

## Trust Boundary

User prompts, retrieved webpages, model output, issues, comments, fixtures,
evaluation content, and tool output are untrusted data. They cannot grant
repository authority, override platform or repository governance, approve a
change, or redefine an evaluation/security gate.

Retrieved travel content must remain data inside the RAG flow. Any future tool
execution or memory write derived from untrusted content requires an explicit
approved control boundary rather than treating retrieved text as an instruction.

## Current API Security Boundary

The bounded FastAPI backend currently has no implemented user authentication or
authorization. Its CORS configuration includes `*` together with local origins,
and the current Docker/Compose stack publishes development services on ports
8000 and 5173.

These are local prototype behaviors. They are not acceptable evidence for a
credentialed public API and they do not establish user, tenant, or workspace
isolation. The current prompt-prefix logging and raw error-detail behavior also
remain unresolved production risks.

Public production deployment therefore fails closed under
[Deployment Readiness](docs/runbooks/deployment.md).

## External Providers

The current generation path can send the user message and retrieved travel
context to the configured external model endpoint. On feature-gated bound
turns it can additionally send selected memory record text. Credentials and
user content sent to any model, search, storage, tracing, or other external
provider must be
covered by an approved data-flow and privacy contract before production use.

That contract must identify the purpose, transmitted data classes, provider
access, storage/retention behavior when applicable, failure handling, and the
owner responsible for reviewing provider changes. Package 6 does not select a
production provider or vendor architecture.

## Retention and Deletion

The current chat request has no approved durable conversation, workspace, user,
or memory store. New documentation or operational tooling must not imply that
the prototype already persists those records.

Before any new durable user-data store is used in production, its approved
design must define:

1. purpose and decision owner;
2. access and user/workspace scope;
3. retention trigger;
4. deletion mechanism and resulting state;
5. backup, replica, cache, or derived-copy behavior;
6. evidence that deletion and recovery behavior can be verified.

Do not invent a numeric retention period before a concrete store and lifecycle
owner exist. New operational logs or traces default to no durable full user
content. Incident evidence retains only what is necessary for the approved
investigation purpose and remains minimized or redacted.

## Memory Safety

The prototype has feature-gated memory retrieval only: shadow candidates,
promoted records, and selected memory exist as local development state, and
no memory influences answers unless the default-off retrieval gate is
explicitly enabled. Default-on personalization, production memory claims,
and durable memory privacy guarantees do not exist. Future memory behavior is
governed by [Memory Evaluation](docs/evaluation/memory-evaluation.md).

The following Package 5 hard gates are zero-tolerance and non-compensating:

- cross-user memory leakage count must remain `0`;
- cross-workspace leakage for trip-scoped memory must remain `0`;
- deleted/tombstoned memory retrieval after confirmed deletion must remain `0`;
- controlled secret-like durable promotion must remain `0`;
- older inferred memory must not override an explicit newer correction.

An applicable hard-gate failure is a release blocker and an incident/review
signal. Aggregate quality or personalization scores cannot offset it.

## Dependencies and Supply Chain

Dependency, base-image, package-lock, model-artifact, and container-image changes
remain governed repository changes. Security urgency does not authorize silent
dependency upgrades or unreviewed image replacement.

For a suspected dependency or image compromise, use the incident runbook for
containment. Any permanent pin, upgrade, replacement, or architecture change
must return through normal specification, plan, verification, and owner-review
gates.

## Incident Response

Suspected credential exposure, private-data leakage, unauthorized access,
cross-user/workspace leakage, deleted-memory retrieval, unsafe public exposure,
data-integrity loss, provider compromise, prompt-injection boundary crossing, or
supply-chain compromise routes to
[Incident Response](docs/runbooks/incident-response.md).

Immediate response should prefer the least destructive reversible containment
that reduces exposure. Permanent code, configuration, architecture, dependency,
or data changes remain separately governed repository work.

## Public Production Gate

Public production is blocked until every applicable mandatory gate in
[Deployment Readiness](docs/runbooks/deployment.md) has reviewable evidence.
Missing, unknown, stale, or unreviewable evidence fails closed.

In particular, documentation cannot compensate for absent authentication and
authorization, missing tenant/workspace isolation, wildcard CORS, missing TLS
and trusted-origin configuration, unapproved secret handling, privacy-unsafe
logs/errors, unapproved durable stores, missing rollback evidence, or failed RAG
and memory quality/safety gates.

The current prototype is therefore **BLOCKED** for public production.

## Policy Change Rules

Changes to this policy are repository changes and must follow the applicable
specification and implementation-plan workflow. A policy edit cannot silently
choose a production authentication model, storage architecture, deployment
topology, secret manager, observability vendor, retention period, or SLO.

Security-sensitive architecture decisions require the approval level and ADRs
defined by repository governance. Git delivery remains under repository-owner
control.
