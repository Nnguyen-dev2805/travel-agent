# Operations and Security Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-08-31 |
| Change class | Level 2 - Feature Spec |
| Decision owner | Repository owner |
| Scope | Documentation Package 6 - repository security policy and operational runbooks |
| Parent design | [Documentation System Design](./2026-08-30-documentation-system-design.md), version 0.1 |
| Depends on | [Architecture Baseline Design](./2026-08-31-architecture-baseline-design.md), version 0.1; [Roadmap and Learning Design](./2026-08-31-roadmap-and-learning-design.md), version 0.1; [Evaluation Protocols Design](./2026-08-31-evaluation-protocols-design.md), version 0.1 |
| Implementation plan | [Operations and Security Implementation Plan](../plans/2026-08-31-operations-and-security-implementation.md), version 0.1 (Completed; owner change set accepted) |
| Implementation state | Accepted in working tree; Git delivery not authorized |
| Related issue | None - Package 6 work was requested by the repository owner in this conversation |
| Superseded document | None |

## Summary

Package 6 establishes the repository-wide security baseline and the first
operational runbooks for Travel Agent. It will create four canonical artifacts:

1. `SECURITY.md`
2. `docs/runbooks/local-development.md`
3. `docs/runbooks/deployment.md`
4. `docs/runbooks/incident-response.md`

The selected approach is conservative: document the prototype exactly as it
exists, define safe operating boundaries, and make production deployment fail
closed until later runtime work establishes authentication, authorization,
tenant isolation, restrictive CORS, secret management, privacy-safe telemetry,
approved persistence, and an approved deployment topology.

Package 6 is documentation-only. It does not fix the current code, choose a
cloud provider, introduce authentication, alter CORS, change logging, rotate
credentials, mutate Chroma data, deploy a service, or make the project
production-ready.

Approval of version 0.1 authorizes preparation of a Package 6 implementation
plan only. It does not authorize creation of the four Package 6 artifacts or
any runtime, infrastructure, dependency, data, Git, or hosting-platform change.

## Current-state Evidence

Codebase Memory was checked at Verify tier for the current repository. The
graph project is
`Users-tnhatnguyendev2805-Documents-Projects-travel-agent`; the checked index
reported 962 nodes and 2109 edges. Coverage checks for the governing
documentation paths returned no recorded issue with matching metadata. This is
a best-effort coverage signal, not proof of semantic completeness. Material
source, configuration, and documentation were also read directly.

| Evidence | Current fact relevant to Package 6 |
| --- | --- |
| [`backend/app/config.py`](../../backend/app/config.py) | Loads repository-root `.env` when present. `GITHUB_TOKEN` is the current model credential name; `LLM_MODEL` defaults to `gpt-4o-mini`. |
| [`backend/app/main.py`](../../backend/app/main.py) | FastAPI has no authentication middleware in the bounded app setup. CORS allows localhost origins and `*`, with credentials, all methods, and all headers enabled. |
| [`backend/app/api/chat.py`](../../backend/app/api/chat.py) | The chat route accepts a single message, logs the first 50 characters of user input, and can return exception details in HTTP 500 responses. |
| [`docker-compose.yml`](../../docker-compose.yml) | The current stack is local-development oriented: ports 8000 and 5173 are published, `.env` is injected into the backend, source/data paths are bind-mounted, and the frontend uses `http://localhost:8000`. |
| [`backend/Dockerfile`](../../backend/Dockerfile) | Starts Uvicorn on `0.0.0.0:8000`; it does not establish a production reverse proxy, TLS, authentication, secret manager, or deployment topology. |
| [`frontend/Dockerfile`](../../frontend/Dockerfile) | Starts the Vite development server on `0.0.0.0:5173`; this is not a production web-serving contract. |
| [Current Architecture](../architecture/current-state.md) | Records no user identity, authentication, conversation persistence, workspace persistence, user memory store, or approved production security/deployment topology. It also records permissive local CORS and prompt-prefix logging as current risks. |
| [Development Guide](../../DEVELOPMENT.md) | `.env.example` is currently empty. `GITHUB_TOKEN` is sensitive and real credential values must not be committed, logged, pasted into issues, or placed in documentation. |
| [Evaluation Protocols](./2026-08-31-evaluation-protocols-design.md) | Requires synthetic or redacted evaluation data, zero tolerance for cross-scope memory leakage and deleted-memory retrieval, and delegates final secret handling, privacy, retention, authorization, and incident response to Package 6. |
| [Contributing Guide](../../CONTRIBUTING.md) | Contains interim vulnerability-reporting guidance: avoid public exploit details and prefer the hosting platform's private reporting channel. Package 6 must replace that interim ownership with a canonical security policy. |
| [Master Roadmap](../roadmap/master-roadmap.md) | `D6` is planned after accepted `D5`; `R8` operations and `R9` security/privacy hardening remain blocked behind later runtime gates. |

The Git remote points to the public GitHub repository
`Nnguyen-dev2805/travel-agent`. Repository inspection does not establish whether
GitHub Private Vulnerability Reporting is enabled. Package 6 therefore cannot
claim that a particular private GitHub reporting control is available unless
that availability is separately verified.

## Context

Travel Agent is an early RAG prototype moving toward a multi-user travel agent
with trip workspaces, conversation persistence, layered memory, planner state,
and evaluation traces. Those future features increase the sensitivity of the
system because they introduce durable user data, cross-workspace isolation,
memory deletion requirements, and more operational state.

The current prototype already has security-relevant surfaces: an external model
credential, browser-to-API traffic, external model calls, persistent Chroma
travel-knowledge data, local bind mounts, logs, retrieved external content, and
public repository collaboration. The project needs explicit operating rules
before later runtime milestones expand these surfaces.

Package 6 turns those rules into canonical repository contracts without
pretending that documentation itself fixes runtime risk.

## Users

1. **Repository owner:** needs a clear security boundary and a reviewable answer
   to whether the system is safe to expose, deploy, or recover.
2. **Developer:** needs safe procedures for broken local environments, secrets,
   logs, data, and recovery actions.
3. **Coding agent:** needs deterministic stop conditions for security-sensitive
   work and deployment claims.
4. **Reviewer or contributor:** needs a canonical private-vulnerability
   reporting policy and rules for handling sensitive evidence.
5. **Future operator:** needs deployment readiness checks, incident triage,
   containment, recovery, and evidence requirements.

## Problem Statement

The repository currently documents local setup and architecture, but it does
not own a canonical security policy or operational recovery procedures. Current
runtime behavior includes permissive CORS, no authentication, prompt-prefix
logging, a local `.env` credential, development-oriented containers, and no
approved production deployment topology.

Without Package 6, later work can accidentally treat local development behavior
as a production contract, expose an unauthenticated API, place user content in
logs or evaluation artifacts, mishandle credentials, or improvise destructive
recovery steps during an incident. A public repository also needs a clear
vulnerability-reporting path that does not invite exploit details into public
issues.

## Goals

1. Establish `SECURITY.md` as the canonical repository security, privacy,
   trust, secret-handling, and vulnerability-reporting policy.
2. Define explicit data-handling classes and default rules for public data,
   operational metadata, user content, sensitive user data, and secrets.
3. Define local-only security boundaries for the current prototype and block
   production-readiness claims that the code cannot support.
4. Define a deployment-readiness runbook that fails closed when mandatory
   security and operational gates are absent.
5. Define a local recovery runbook for diagnosed development failures without
   duplicating ordinary setup from `DEVELOPMENT.md`.
6. Define an incident-response runbook with severity, triage, containment,
   evidence, recovery, and post-incident review.
7. Define privacy-safe logging and evidence rules that prevent secrets or
   unnecessary user content from becoming operational artifacts.
8. Define retention and deletion requirements as contracts that future stores
   must satisfy before they hold user, workspace, conversation, memory, planner,
   or trace data in a production environment.
9. Preserve Package 5 hard safety gates and connect operational response to
   cross-scope leakage, deleted-memory retrieval, and sensitive-memory failures.
10. Provide routing updates so humans and coding agents load the correct
    security or runbook document when its trigger applies.

## Non-goals

1. Package 6 does not implement authentication, authorization, user identity,
   tenant isolation, encryption, rate limiting, CSRF protection, WAF rules, or
   network policy.
2. It does not change current CORS behavior, chat logging, exception responses,
   `.env.example`, source code, tests, dependencies, Docker images, or Compose.
3. It does not choose a cloud provider, container platform, reverse proxy,
   database, secret manager, log platform, tracing vendor, alerting vendor, or
   backup technology.
4. It does not deploy, publish, expose, stop, restart, or mutate a live service.
5. It does not introduce user, workspace, conversation, memory, planner, or
   evaluation-trace persistence.
6. It does not define the detailed runtime authentication or authorization
   architecture; that is later Level 3 work with any required ADRs.
7. It does not create GitHub issue templates, PR templates, `LICENSE`,
   `THIRD_PARTY_NOTICES.md`, or `CHANGELOG.md`; Package 7 owns those artifacts.
8. It does not claim private vulnerability reporting is enabled on GitHub when
   repository evidence has not verified that setting.
9. It does not create production SLOs or capacity budgets that have no measured
   runtime evidence.
10. It does not perform Git staging, commit, push, PR, merge, release, or
    hosting-platform configuration changes.

## Assumptions

1. The current Docker Compose configuration is a development stack, not a
   production deployment contract.
2. A public production deployment is unsafe while the bounded backend has no
   authentication and permits wildcard CORS.
3. Future user memory and trip data require stronger isolation, retention,
   deletion, and audit contracts than the current public travel-knowledge
   vectors.
4. Security documentation must distinguish current implemented safeguards from
   required future controls.
5. Operational runbooks should prefer diagnosis and reversible containment
   before destructive cleanup.
6. Public issues are not an acceptable place for exploit details, credentials,
   private user data, or sensitive incident evidence.
7. A deployment runbook is useful before production infrastructure exists when
   it functions as a readiness gate and explicitly blocks unsupported
   deployment.
8. Numeric retention periods should be defined only for stores and operational
   platforms whose ownership and behavior are actually approved. Until then,
   the safe default is no durable retention of user content by new operational
   artifacts.

If an assumption is rejected, Package 6 returns to specification review before
an implementation plan is prepared.

## Selected Approach

Use one root policy and three narrow runbooks:

1. `SECURITY.md` owns policy: reporting, trust, secrets, data classes, privacy,
   authorization boundaries, logging, retention/deletion requirements, and
   production security gates.
2. `docs/runbooks/local-development.md` owns recovery procedures for a broken
   local stack after the normal setup path in `DEVELOPMENT.md` fails.
3. `docs/runbooks/deployment.md` owns deployment readiness, promotion,
   verification, rollback, and explicit deployment blockers. Until a later
   deployment architecture is approved, it must stop before public production
   deployment.
4. `docs/runbooks/incident-response.md` owns security and operational incident
   triage, containment, evidence, recovery, and post-incident review.

The documents must state whether a rule describes current behavior, required
future behavior, or an operational stop condition. They must use links rather
than duplicating setup, architecture, evaluation, contribution, or roadmap
content already owned elsewhere.

## Alternatives Considered

### Alternative A: Minimal `SECURITY.md` only

This would satisfy the visible open-source convention quickly but leave local
recovery, deployment safety, and incident response undefined. It is rejected
because operational mistakes can create the same confidentiality and
availability failures as code defects.

### Alternative B: Provider-specific production handbook

This would give executable deployment commands immediately. It is rejected
because the repository has no approved production topology, authentication
model, secret manager, observability stack, or hosting-provider decision.
Choosing them inside a documentation package would silently make Level 3
architecture decisions.

### Alternative C: Policy plus readiness-oriented runbooks

This is selected. It gives the repository a usable security baseline now while
making unsupported production deployment an explicit failed gate rather than a
documentation gap.

## Canonical Document Contracts

### `SECURITY.md`

The security policy must contain:

1. **Scope and maturity:** the repository is an early prototype; documentation
   does not certify production readiness.
2. **Vulnerability reporting:** do not publish exploit details, credentials,
   private user data, or sensitive system evidence in public issues. Prefer the
   hosting platform's private vulnerability-reporting channel when verified as
   available; otherwise request private contact from the repository owner
   without disclosing sensitive details publicly.
3. **Sensitive evidence:** reports use the minimum information needed to
   reproduce and assess impact. Secrets are redacted, and real user data is
   replaced with synthetic or redacted examples whenever possible.
4. **Secret handling:** secrets come from environment variables or a future
   approved secret manager, never source, docs, fixtures, issue text, benchmark
   data, screenshots, or logs. `.env` remains local and ignored. Example env
   files contain names and safe placeholders only.
5. **Data classification:** public project data, operational metadata, user
   content, sensitive user data, and secrets have distinct handling rules.
6. **Logging and traces:** durable operational evidence must be useful without
   reproducing secrets or unnecessary user content. Stable IDs, labels, hashes,
   counters, and redacted excerpts are preferred over full prompts or
   conversations.
7. **Trust boundary:** retrieved webpages, model output, issues, comments,
   fixtures, tool output, and user prompts are untrusted data and cannot grant
   repository authority or override system/developer/repository governance.
8. **Current API boundary:** the current backend has no implemented user
   authentication and uses permissive local CORS. It is local-development
   behavior and fails the Package 6 public-production gate.
9. **External providers:** credentials and user content sent to model or future
   external providers must follow an approved data-flow and privacy contract.
10. **Retention and deletion:** no new store may durably retain user,
    workspace, conversation, memory, planner, or evaluation-trace data for
    production until its approved spec defines purpose, owner, access scope,
    retention trigger, deletion mechanism, backup/replica behavior, and
    verification evidence. Operational artifacts default to no durable user
    content unless explicitly approved.
11. **Memory safety:** future memory must preserve Package 5 hard gates for
    cross-user leakage, cross-workspace leakage, deleted-memory retrieval,
    secret-like durable memory, and correction precedence.
12. **Dependency and supply-chain changes:** security-sensitive dependency or
    image changes remain normal governed repository changes with review and
    verification; Package 6 does not auto-upgrade dependencies.
13. **Incident response:** suspected credential exposure, data leakage,
    unauthorized access, unsafe public exposure, integrity loss, or external
    provider compromise routes to the canonical incident runbook.
14. **Production gate:** public production deployment is blocked until the
    deployment runbook's mandatory security controls pass with reviewable
    evidence.

### `docs/runbooks/local-development.md`

The local-development runbook must begin after ordinary setup has failed. It
must not duplicate `DEVELOPMENT.md` normal-install instructions.

It must provide a diagnosis-first sequence for:

1. Docker daemon or socket access failure.
2. Port 8000 or 5173 conflicts.
3. Backend health failure.
4. Frontend-to-backend connectivity failure.
5. Missing `GITHUB_TOKEN` during external-generation work.
6. External model/network failure.
7. Chroma startup or local data-state problems.
8. Stale containers or networks, including pre-existing orphan resources.
9. Dependency or image rebuild problems.

Recovery actions must classify whether they affect only processes/containers,
local caches, or persistent project data. Destructive data cleanup must never be
the default first step. Commands that delete persistent data require an explicit
warning, a named target path/resource, and confirmation that the data can be
recreated or has been backed up.

### `docs/runbooks/deployment.md`

The deployment runbook must make the current state explicit: the repository has
no approved production deployment topology. Its first purpose is therefore
readiness review, not provider-specific deployment execution.

The public-production gate must fail if any applicable item lacks evidence:

1. Approved deployment architecture and required ADRs.
2. Authentication and authorization for user-scoped functionality.
3. Tenant/workspace isolation for persisted or retrieved user data.
4. Restrictive environment-specific CORS; wildcard CORS is not acceptable for
   a credentialed public API.
5. TLS termination and trusted public origin configuration.
6. Production secret storage and rotation procedure.
7. Privacy-safe logging, tracing, and error responses.
8. Approved data stores with retention, deletion, backup, restore, and access
   ownership.
9. Health and readiness checks that distinguish process health from dependency
   degradation where required.
10. Resource, timeout, retry, rate-limit, and cost controls appropriate to the
    runtime milestone.
11. Versioned deployable artifacts and reproducible dependency installation.
12. Tested rollback procedure and state-compatibility boundary.
13. Incident ownership and a reachable operator path.
14. Package 5 quality and safety gates for any RAG or memory behavior claimed by
    the release.

The runbook may document local or future staging promotion concepts, but it
must not invent cloud commands, DNS names, credentials, production URLs, SLOs,
or vendor settings.

### `docs/runbooks/incident-response.md`

The incident runbook must cover both security and operational failures using a
common lifecycle:

1. Detect and record the symptom without copying sensitive data unnecessarily.
2. Classify severity and affected scope.
3. Contain the exposure or unsafe behavior using the least destructive
   reversible action available.
4. Preserve reviewable evidence with secrets and private user data redacted.
5. Eradicate the cause through separately governed fixes where code,
   configuration, architecture, or data changes are required.
6. Recover service or development state only after the relevant security and
   integrity checks pass.
7. Review root cause, affected data, detection gap, response quality, and
   follow-up work.

The runbook must include specific first-response guidance for:

1. Credential or token exposure.
2. User/private data exposed in logs, issues, traces, screenshots, or reports.
3. Suspected unauthorized access or cross-user/cross-workspace data leakage.
4. Deleted or tombstoned memory becoming retrievable.
5. Unsafe public exposure of the current unauthenticated or wildcard-CORS API.
6. Data corruption, accidental deletion, or vector-store integrity loss.
7. External model/provider outage or suspected provider compromise.
8. Malicious retrieved content or prompt-injection behavior that crosses a trust
   boundary.
9. Dependency or container-image compromise.

The incident document must distinguish an operational workaround from a
permanent repository change. Permanent fixes remain subject to normal spec,
architecture, plan, verification, and owner-review gates.

## Data Classification and Handling Contract

Package 6 uses these documentation-level classes:

| Class | Examples | Default handling |
| --- | --- | --- |
| Public project data | Source, public docs, public travel knowledge, synthetic fixtures | May be committed and reviewed normally when licensing and provenance allow |
| Operational metadata | Request IDs, timings, counts, component states, redacted failure labels | May be retained only for an approved operational purpose; avoid user content by default |
| User content | Chat text, itinerary preferences, future workspace/conversation content | Do not commit; minimize logging; send or persist only through approved data flows |
| Sensitive user data | Precise travel identity data, contact details, travel documents, financial or other high-impact personal data if future features introduce them | Requires explicit approved purpose, access scope, retention, deletion, and stronger review before storage or external transmission |
| Secrets | API tokens, credentials, signing keys, private connection material | Environment or approved secret manager only; never source, docs, logs, issues, fixtures, or benchmark artifacts |

The classification is a policy vocabulary, not a claim that every listed future
data type exists today.

## Retention and Deletion Contract

Package 6 must avoid invented numeric retention periods for stores that do not
exist. Instead, it establishes a mandatory contract:

1. Current chat user content has no approved durable application store. New
   documentation must not imply that the current prototype saves conversations.
2. New operational logs or traces must not durably retain full user content by
   default.
3. Any later durable user-data store must define a retention trigger and
   deletion behavior in its approved feature or architecture design before
   production use.
4. Deletion semantics must state whether deletion is immediate, tombstoned,
   asynchronously purged, or propagated to backups/replicas, and how completion
   is verified.
5. Memory deletion must be testable against Package 5's deleted-memory retrieval
   hard gate.
6. Security and incident evidence must retain only what is necessary for the
   approved investigation purpose, with sensitive fields minimized or redacted.

This contract is the Package 6 retention baseline. Numeric periods can be added
only when a concrete storage or operational platform has an approved owner and
measurable lifecycle.

## Vulnerability Reporting Contract

The implementation must provide a usable policy without claiming an unverified
hosting feature:

1. If GitHub Private Vulnerability Reporting is verified as enabled at
   implementation/review time, `SECURITY.md` may name it as the preferred
   channel.
2. If it is not verified, `SECURITY.md` must instruct reporters to avoid public
   details and request private contact from the repository owner using only a
   minimal non-sensitive public message when no other private channel is known.
3. The policy must request impact, affected version or commit, reproduction
   conditions, and suggested mitigation when safe to share privately.
4. The policy must not promise a response-time SLA that the repository owner has
   not explicitly adopted.

## Errors and Edge Cases

1. **Security policy references a private channel that is not enabled:** treat
   as documentation verification failure and use the verified fallback wording.
2. **A runbook command can delete persistent state:** label the exact state,
   require a recoverability check, and keep the destructive action out of the
   default recovery path.
3. **A current code risk conflicts with desired policy:** document the risk as a
   production blocker and create later governed remediation work; do not edit
   runtime code inside Package 6.
4. **Deployment topology is still unknown:** stop at readiness review. Do not
   select a provider or invent deployment commands.
5. **Authentication or storage design becomes necessary to make a claim:** stop
   and create the required Level 3 design/ADR rather than embedding the decision
   in a runbook.
6. **An incident requires immediate containment but permanent repository changes
   are unapproved:** use reversible operational containment first and route the
   permanent fix through normal governance.
7. **Evidence contains credentials or private data:** redact before placing it
   in repository artifacts, issues, reports, or review notes.
8. **Current prompt-prefix logging remains:** treat it as a known privacy risk
   and production blocker, not as accepted logging policy.
9. **Package 5 hard safety gate fails:** do not average, waive, or hide the
   failure inside operational metrics; route it to incident/review handling as
   defined by the evaluation protocol.

## Security and Privacy

Package 6 is the canonical documentation owner for repository-wide security and
privacy guidance, but it cannot create runtime controls by documentation alone.

The core policy is:

1. Minimize sensitive data collection and retention.
2. Keep secrets out of repository and operational artifacts.
3. Treat external/retrieved content and user/model text as untrusted data.
4. Isolate future user/workspace data by explicit approved scope.
5. Make deletion verifiable where durable user data exists.
6. Fail closed on public deployment when authentication, authorization,
   isolation, CORS, secrets, logging, persistence, or recovery contracts are
   missing.
7. Prefer synthetic or redacted evidence for tests, evaluation, incidents, and
   documentation.
8. Preserve Package 5 hard safety gates as non-compensating release blockers.

## Observability and Operations

Package 6 defines operational expectations, not a telemetry vendor:

1. Operators need stable component state, request/run identity, timing, failure
   reason, and gate outcome without requiring full prompt or conversation logs.
2. Logs and traces must not expose credential values.
3. User-content logging is opt-in through an approved privacy purpose, never the
   default debugging shortcut.
4. Health evidence must distinguish a running process from a fully trustworthy
   RAG, memory, planner, or external-provider path.
5. Incidents must record enough timeline and scope evidence for review without
   turning the incident record into a sensitive-data archive.
6. Later `R8` runtime work owns concrete telemetry, dashboards, alerts, and
   operational review cadence.

## Testing and Evaluation

Package 6 implementation verification is documentation-focused:

1. Verify every current-state claim against source, configuration, or existing
   approved documentation.
2. Verify `SECURITY.md` contains no real credential, token, private contact
   information invented by the agent, or unverified vulnerability-reporting
   capability.
3. Verify each runbook separates normal setup from recovery and current behavior
   from future production requirements.
4. Verify destructive commands are either absent or explicitly guarded by a
   named-state and recoverability check.
5. Verify the deployment runbook fails closed for the current unauthenticated,
   wildcard-CORS prototype.
6. Verify incident guidance covers secrets, private-data exposure,
   cross-scope leakage, unsafe public exposure, integrity loss, provider
   failure, prompt injection, and dependency compromise.
7. Verify Package 5 hard gates remain unchanged and linked rather than
   redefined.
8. Resolve all repository-relative links.
9. Check headings, fenced-code blocks, trailing whitespace, duplicate ownership,
   and drafting markers.
10. Compare the complete change set, including untracked files, with the
    approved Package 6 scope.

Package 6 does not run production penetration testing or external vulnerability
scanning as documentation acceptance evidence. Later runtime/security
milestones may add those controls under their own approved scope.

## Rollout and Migration

Package 6 documentation rolls out in this order:

1. Approve this specification.
2. Prepare and approve a Package 6 implementation plan.
3. Create `SECURITY.md`.
4. Create `docs/runbooks/local-development.md`.
5. Create `docs/runbooks/deployment.md`.
6. Create `docs/runbooks/incident-response.md`.
7. Apply only the routing, roadmap, and traceability updates named in the
   approved implementation plan.
8. Run deterministic documentation checks and evidence review.
9. Stop for repository-owner review of the exact Package 6 change set.

After Package 6 is accepted, it unblocks documentation dependency `D7` and
provides policy prerequisites for later runtime milestones. It does not itself
authorize `R8`, `R9`, deployment, authentication, memory, or storage work.

## Routing and Traceability Changes

The implementation plan may update only the minimum existing documents needed
to route readers to the new canonical artifacts:

1. `AGENTS.md`: add task triggers for security-sensitive work and operational
   runbooks once those targets exist.
2. `README.md`: link the security policy/runbooks and remove the obsolete claim
   that no security policy or deployment runbook exists, while preserving the
   statement that production readiness is not established.
3. `DEVELOPMENT.md`: point diagnosed local-stack recovery to the local runbook
   without moving normal setup ownership.
4. `CONTRIBUTING.md`: replace interim vulnerability-reporting ownership with a
   pointer to `SECURITY.md`.
5. `ARCHITECTURE.md`: point production security/deployment questions to the
   policy and readiness runbook without claiming implemented controls.
6. `docs/roadmap/master-roadmap.md`: advance `D6` only according to actual
   implementation/review state; do not silently repair unrelated milestone
   status inconsistencies.
7. `docs/specs/README.md` and, after plan creation, `docs/plans/README.md`: keep
   Package 6 lifecycle and discovery entries current.

Any wider routing or runtime change is scope expansion and returns to review.

## Rollback

Before Git delivery, Package 6 documentation rollback removes only:

1. `SECURITY.md` created by the approved Package 6 plan.
2. `docs/runbooks/local-development.md`.
3. `docs/runbooks/deployment.md`.
4. `docs/runbooks/incident-response.md`.
5. Package 6 traceability/routing edits named in the approved plan.
6. The Package 6 implementation plan if it was created for this package.

Rollback must not alter current source code, dependencies, Docker state,
credentials, `.env`, Chroma data, existing Packages 0-5 content outside named
Package 6 routing fields, hosting-platform settings, or Git history.

## Acceptance Criteria

Package 6 implementation is acceptable only when:

1. `SECURITY.md` exists and is the canonical vulnerability-reporting,
   repository security, privacy, trust, secret-handling, and data-handling
   policy.
2. The three canonical runbooks exist and preserve their distinct ownership:
   local recovery, deployment readiness/operations, and incident response.
3. The security policy accurately states the current absence of authentication
   and production deployment guarantees.
4. Wildcard CORS and current prompt-prefix logging are identified as production
   blockers or risks, not accepted production controls.
5. Secrets are prohibited from source, docs, issues, fixtures, benchmarks,
   screenshots, and logs; approved environment/secret-storage mechanisms are
   the only allowed sources.
6. Public project data, operational metadata, user content, sensitive user data,
   and secrets have explicit handling rules.
7. Future durable user-data stores are blocked from production until retention,
   deletion, backup/replica behavior, scope, and verification are approved.
8. The vulnerability policy never publishes exploit details and never claims an
   unverified private-reporting channel.
9. Local recovery uses diagnosis-first, reversible procedures and does not make
   destructive data cleanup a default step.
10. The deployment runbook fails the current public-production gate until
    authentication/authorization, isolation, restrictive CORS, secrets,
    privacy-safe logging, approved persistence, deployment architecture, and
    rollback evidence exist.
11. The incident runbook covers credential exposure, private-data leakage,
    cross-scope leakage, deleted-memory retrieval, unsafe public exposure, data
    integrity loss, provider compromise/outage, prompt injection, and supply
    chain compromise.
12. Package 5 hard safety gates remain linked and non-compensating.
13. Existing canonical documents are linked rather than duplicated.
14. Current behavior is clearly separated from required future behavior.
15. No runtime source, test, dependency, Docker, credential, persistent data,
    hosting-platform, or Git delivery change is included in Package 6.
16. All repository-relative links resolve and deterministic Markdown checks
    pass.
17. The repository owner approves Package 6 spec version 0.1 before an
    implementation plan is prepared.
18. The repository owner later accepts the exact Package 6 implementation
    change set before any Git delivery action.

## Verification

The Package 6 implementation plan must include:

1. Codebase Memory Verify-tier coverage checks for every relied-on source and
   documentation path.
2. Direct source/config reads for current authentication, CORS, logging,
   credential, Docker, Compose, and persistence claims.
3. A secret-safety scan over the new documentation for credential-like values
   and accidental `.env` content.
4. A policy ownership review proving `SECURITY.md`, `DEVELOPMENT.md`,
   architecture docs, evaluation docs, contribution docs, and each runbook do
   not duplicate canonical responsibilities.
5. A runbook command review that classifies side effects and flags destructive
   actions.
6. A deployment-gate review proving the current prototype cannot pass public
   production readiness by documentation alone.
7. An incident scenario review covering every required first-response case.
8. Link resolution, trailing-whitespace, drafting-marker, heading, and
   fenced-code-block checks.
9. A final scope review using `git status --short --untracked-files=all` plus
   direct reads or read-only no-index diffs for untracked files.

## ADR Impact

No ADR is required to approve this documentation package because version 0.1
does not select authentication architecture, deployment topology, storage,
observability vendor, secret manager, or another hard-to-reverse runtime
boundary.

If implementation discovers that one of those decisions is required to make a
Package 6 claim, work stops and returns as Level 3 architecture scope with the
required architecture approval and ADRs.

## Approval Record

Package 6 work was requested by the repository owner on 2026-08-31 in this
conversation. Under repository governance, that request authorizes
investigation and preparation of this specification for review; it does not
bypass the specification or implementation-plan approval gates.

Version 0.1 was approved by the repository owner on 2026-08-31 via the exact
conversation phrase `Approve Package 6 spec version 0.1`. This approval
authorizes preparation of the Package 6 implementation plan only. It does not
authorize creation of `SECURITY.md`, operational runbooks, runtime or
infrastructure changes, dependency or data changes, deployment, or Git delivery.
