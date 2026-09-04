# Operations and Security Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence. Use the approved specification as the authority for
> Package 6 behavior and stop when a required assumption, boundary, or approval
> changes.

**Goal:** Create the canonical repository security policy and three operational
runbooks that accurately describe the current prototype, define safe operating
boundaries, and fail closed on unsupported public production deployment.

**Architecture:** Package 6 is documentation-only. One root `SECURITY.md` owns
repository-wide security, privacy, trust, secret-handling, data-handling, and
vulnerability-reporting policy; three focused runbooks own local recovery,
deployment readiness, and incident response. Existing canonical documents are
linked and minimally routed rather than duplicated, and no runtime or provider
architecture is selected.

**Tech Stack:** Markdown, Codebase Memory MCP at Verify tier, direct source and
configuration reads, shell, ripgrep, Ruby one-line repository-link checking,
and Git read-only status inspection.

**Spec:** [Operations and Security Design](../specs/2026-08-31-operations-and-security-design.md),
approved version 0.1.

| Field | Value |
| --- | --- |
| Status | Completed |
| Plan version | 0.1 |
| Date | 2026-08-31 |
| Approved specification | [Operations and Security Design](../specs/2026-08-31-operations-and-security-design.md), version 0.1 |
| Execution owner | Coding agent after explicit plan approval |
| Decision owner | Repository owner |
| Scope | `SECURITY.md`, three `docs/runbooks/` documents, approved routing and Package 6 traceability updates, and this plan only |
| Verification | Codebase Memory Verify-tier evidence, direct source/config reads, secret-safety scan, policy-ownership review, runbook side-effect review, deployment fail-closed review, incident-scenario review, deterministic Markdown/link checks, final scope review, and owner change-set review |

## Global Constraints

1. Do not execute this plan until the repository owner explicitly approves this
   exact plan.
2. Package 6 is documentation-only. Do not modify runtime source, tests,
   dependencies, Dockerfiles, Compose, environment files, persistent data,
   hosting-platform settings, or Git history.
3. Create exactly these Package 6 canonical content files:
   - `SECURITY.md`
   - `docs/runbooks/local-development.md`
   - `docs/runbooks/deployment.md`
   - `docs/runbooks/incident-response.md`
4. Modify only these existing files during approved Package 6 execution:
   - `AGENTS.md`
   - `README.md`
   - `DEVELOPMENT.md`
   - `CONTRIBUTING.md`
   - `ARCHITECTURE.md`
   - `docs/roadmap/master-roadmap.md`
   - `docs/specs/README.md`
   - `docs/specs/2026-08-31-operations-and-security-design.md`
   - `docs/plans/README.md`
   - `docs/plans/2026-08-31-operations-and-security-implementation.md`
5. Do not implement or select authentication, authorization, tenant isolation,
   encryption, rate limiting, CSRF protection, WAF rules, network policy,
   production deployment topology, cloud provider, reverse proxy, database,
   secret manager, observability vendor, backup technology, or another Level 3
   architecture boundary.
6. Do not change current CORS behavior, prompt-prefix logging, exception
   responses, `.env.example`, or credential configuration inside Package 6.
   Document those current risks and route remediation to later governed work.
7. Do not claim the current prototype is production-ready. Public production
   deployment must remain blocked while mandatory security and operational
   controls lack reviewable evidence.
8. Do not claim GitHub Private Vulnerability Reporting is enabled unless that
   capability is positively verified during implementation or review. Without
   verification, use the approved minimal public fallback that requests private
   contact without publishing sensitive details.
9. Never place real credentials, tokens, private contact details invented by the
   agent, private user data, or sensitive incident evidence in repository
   documentation, examples, screenshots, fixtures, or review notes.
10. Use public, synthetic, or redacted examples by default. Operational evidence
    should prefer stable IDs, labels, hashes, counters, and redacted excerpts
    over full prompts or conversations.
11. Do not invent numeric retention periods, production SLOs, production URLs,
    DNS names, vendor settings, or capacity budgets without an approved concrete
    owner and measurable runtime evidence.
12. Local recovery and incident containment must prefer diagnosis and reversible
    actions before destructive cleanup. Any documented persistent-data deletion
    must name the exact state, warn clearly, require a recoverability check, and
    remain outside the default recovery path.
13. Preserve Package 5 memory hard gates as non-compensating. Cross-user
    leakage, cross-workspace leakage, deleted-memory retrieval, secret-like
    durable memory, and correction-precedence failures cannot be averaged away.
14. Keep technical repository documentation in English.
15. Preserve unrelated dirty or untracked work from Packages 0-5.
16. Repository-owner review of the exact Package 6 implementation change set is
    required before any Git staging, commit, push, PR, merge, release, or owner-
    accepted roadmap status.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `SECURITY.md` | Canonical repository security, privacy, trust, secret-handling, data-handling, retention/deletion, vulnerability-reporting, and production-gate policy | Approved Package 6 spec and Task 1 evidence |
| `docs/runbooks/local-development.md` | Diagnosis-first recovery after normal local setup in `DEVELOPMENT.md` has failed | `DEVELOPMENT.md`, current Docker/Compose/backend evidence, `SECURITY.md` policy |
| `docs/runbooks/deployment.md` | Deployment-readiness, promotion, verification, rollback, and fail-closed public-production gate without choosing a provider | `SECURITY.md`, architecture docs, Package 5 evaluation gates |
| `docs/runbooks/incident-response.md` | Security and operational incident lifecycle, first response, containment, evidence, recovery, and follow-up routing | `SECURITY.md`, Package 5 safety gates, current architecture risks |
| `AGENTS.md` | Route security-sensitive and operational tasks to the new canonical policy/runbooks after they exist | Four Package 6 artifacts |
| `README.md` | Link Package 6 artifacts and remove obsolete absence claims without asserting production readiness | Four Package 6 artifacts |
| `DEVELOPMENT.md` | Route diagnosed local-stack recovery to the local-development runbook while retaining normal setup ownership | Local-development runbook |
| `CONTRIBUTING.md` | Replace interim vulnerability-reporting ownership with a pointer to `SECURITY.md` | Security policy |
| `ARCHITECTURE.md` | Route production security and deployment-readiness questions to Package 6 policy/runbook without claiming controls are implemented | Security policy and deployment runbook |
| `docs/roadmap/master-roadmap.md` | Reflect actual `D6` implementation/review state only | Package 6 implementation evidence |
| `docs/specs/README.md` | Keep Package 6 discovery and lifecycle metadata consistent with the approved spec | Approved Package 6 spec |
| `docs/specs/2026-08-31-operations-and-security-design.md` | Track plan linkage and implementation/review state without changing spec approval | This plan |
| `docs/plans/README.md` | Index this plan and keep its lifecycle state accurate | This plan |
| `docs/plans/2026-08-31-operations-and-security-implementation.md` | Track approved tasks, verification evidence, completion state, and remaining owner gate | Approved Package 6 spec and owner plan approval |

## Task 1: Re-establish Current Security and Operations Evidence

**Files:**

- Read: `backend/app/config.py`
- Read: `backend/app/main.py`
- Read: `backend/app/api/chat.py`
- Read: `backend/Dockerfile`
- Read: `frontend/Dockerfile`
- Read: `docker-compose.yml`
- Read: `.env.example`
- Read: `DEVELOPMENT.md`
- Read: `CONTRIBUTING.md`
- Read: `docs/architecture/current-state.md`
- Read: `docs/architecture/target-state.md`
- Read: `docs/evaluation/rag-evaluation.md`
- Read: `docs/evaluation/memory-evaluation.md`
- Read: `docs/roadmap/master-roadmap.md`
- Read: `docs/specs/2026-08-31-operations-and-security-design.md`

**Interfaces:**

- Consumes: approved Package 6 spec plus current source, configuration,
  architecture, evaluation, and roadmap state.
- Produces: verified current-state facts and limitations used by Tasks 2-6.

- [x] **Step 1: Refresh Codebase Memory evidence at Verify tier**

Confirm the active graph project and current generation. Locate the FastAPI app,
configuration object, and chat route structurally; inspect material symbols and
trace relevant inbound/outbound relationships where useful. Run
`check_index_coverage` once with every relied-on code and documentation path.

Expected: current authentication, CORS, credential, logging, request, and
documented-persistence claims have graph evidence with coverage state recorded.
Any partial, skipped, excluded, stale, pending, unknown, or missed range is read
directly before relying on it.

- [x] **Step 2: Read security-relevant source and configuration directly**

Run:

```bash
sed -n '1,260p' backend/app/config.py
sed -n '1,300p' backend/app/main.py
sed -n '1,320p' backend/app/api/chat.py
sed -n '1,260p' backend/Dockerfile
sed -n '1,260p' frontend/Dockerfile
sed -n '1,360p' docker-compose.yml
sed -n '1,220p' .env.example
```

Expected: current credential naming, local environment loading, authentication
absence in the bounded app setup, CORS policy, prompt-prefix logging, exception
behavior, published ports, bind mounts, development servers, and current
environment-example state are confirmed without reading or printing a real
`.env` file.

- [x] **Step 3: Reconcile documentation-level persistence and safety claims**

Run:

```bash
rg -n 'authentication|authorization|CORS|conversation persistence|workspace persistence|memory|Chroma|logging|GITHUB_TOKEN|production|deployment|retention|deletion' DEVELOPMENT.md CONTRIBUTING.md docs/architecture/current-state.md docs/architecture/target-state.md docs/evaluation/rag-evaluation.md docs/evaluation/memory-evaluation.md docs/roadmap/master-roadmap.md
```

Expected: Package 6 wording distinguishes current travel-knowledge persistence
from absent user/workspace/conversation/memory persistence and preserves Package
5 hard safety gates.

- [x] **Step 4: Establish vulnerability-reporting wording**

Use positive repository/platform evidence only if GitHub Private Vulnerability
Reporting availability can be verified without changing settings. If no such
evidence is available, use the approved fallback: do not publish exploit or
sensitive details; request a private contact path from the repository owner with
only a minimal non-sensitive public message.

Expected: `SECURITY.md` will not name an unverified private reporting feature,
invent a private address, or promise a response-time SLA.

- [x] **Step 5: Review checkpoint**

Compare all Task 1 findings with the spec's Current-state Evidence, Assumptions,
Errors and Edge Cases, and Verification sections.

Expected: no material assumption has changed. If current code or repository
state requires a new architecture decision or contradicts the approved spec,
stop and return to specification review before creating Package 6 artifacts.

## Task 2: Create Canonical Security Policy

**Files:**

- Create: `SECURITY.md`
- Read: Task 1 evidence
- Read: `docs/evaluation/memory-evaluation.md`
- Read: `docs/specs/2026-08-31-operations-and-security-design.md`

**Interfaces:**

- Consumes: verified current-state evidence and approved Package 6 policy
  contracts.
- Produces: canonical security/privacy policy consumed by all three runbooks and
  routing updates.

- [x] **Step 1: Create `SECURITY.md` with explicit ownership**

Use this top-level structure:

```markdown
# Security Policy

## Scope and Maturity
## Vulnerability Reporting
## Sensitive Evidence
## Secret Handling
## Data Classification
## Logging and Traces
## Trust Boundary
## Current API Security Boundary
## External Providers
## Retention and Deletion
## Memory Safety
## Dependencies and Supply Chain
## Incident Response
## Public Production Gate
## Policy Change Rules
```

The document must state that Travel Agent is an early prototype and that policy
documentation does not certify production readiness or implement runtime
controls.

- [x] **Step 2: Encode vulnerability and secret-handling rules**

Document the verified reporting path from Task 1. Require minimum necessary
reproduction evidence, impact, affected version/commit, and suggested mitigation
when safe to share privately. Explicitly prohibit exploit details, credentials,
private user data, and sensitive system evidence in public issues.

State that secrets come from environment variables or a future approved secret
manager only; they never belong in source, docs, fixtures, benchmark data,
screenshots, issues, or logs. `.env` remains local and ignored, while example
environment files may contain variable names and safe placeholders only.

Expected: no private contact is invented and no real credential value appears.

- [x] **Step 3: Encode data, logging, trust, and provider contracts**

Define the five approved data classes exactly by role:

1. Public project data.
2. Operational metadata.
3. User content.
4. Sensitive user data.
5. Secrets.

For each class, define default commit, logging, persistence, external-
transmission, and review expectations consistent with the spec. State that user
prompts, model output, retrieved webpages, issues, comments, fixtures, and tool
output are untrusted data and cannot grant repository authority.

Expected: operational evidence is useful without making full prompt or
conversation logging the default.

- [x] **Step 4: Encode current API, retention, memory, and production gates**

State that the bounded backend currently has no implemented user authentication,
uses permissive local CORS, and currently logs a prompt prefix; these are current
prototype risks and public-production blockers, not accepted production
controls.

Define the mandatory retention/deletion contract without numeric periods:
purpose, owner, access scope, retention trigger, deletion mechanism,
backup/replica behavior, and verification evidence must be approved before a
new durable user-data store is used in production. Preserve Package 5 memory
hard gates and route suspected failures to the incident runbook.

Expected: public production remains blocked until the deployment runbook's
mandatory controls have reviewable evidence.

- [x] **Step 5: Verify policy headings and governing concepts**

Run:

```bash
rg -n '^## (Scope and Maturity|Vulnerability Reporting|Sensitive Evidence|Secret Handling|Data Classification|Logging and Traces|Trust Boundary|Current API Security Boundary|External Providers|Retention and Deletion|Memory Safety|Dependencies and Supply Chain|Incident Response|Public Production Gate|Policy Change Rules)$' SECURITY.md
rg -n 'authentication|wildcard|CORS|prompt|GITHUB_TOKEN|user content|sensitive user data|secrets|retention|deletion|cross-user|cross-workspace|production' SECURITY.md
```

Expected: every required ownership area and production-blocking concept is
present, and current behavior is separated from required future controls.

- [x] **Step 6: Review checkpoint**

Read `SECURITY.md` end-to-end against the spec's Canonical Document Contract,
Data Classification, Retention and Deletion, Vulnerability Reporting, and
Security and Privacy sections.

Expected: one canonical policy exists with no provider architecture, invented
runtime safeguard, or duplicated setup/runbook procedure.

## Task 3: Create Local Development Recovery Runbook

**Files:**

- Create: `docs/runbooks/local-development.md`
- Read: `DEVELOPMENT.md`
- Read: `SECURITY.md`
- Read: `docker-compose.yml`
- Read: `backend/Dockerfile`
- Read: `frontend/Dockerfile`

**Interfaces:**

- Consumes: normal setup ownership from `DEVELOPMENT.md`, current local-stack
  evidence, and Package 6 policy.
- Produces: diagnosis-first broken-stack recovery procedures without replacing
  normal setup instructions.

- [x] **Step 1: Create the local recovery runbook**

Use this top-level structure:

```markdown
# Local Development Recovery Runbook

## Scope
## Safety Rules
## Triage Sequence
## Docker Daemon or Socket Failure
## Port Conflicts
## Backend Health Failure
## Frontend-to-Backend Connectivity Failure
## Missing Model Credential
## External Model or Network Failure
## Chroma or Local Data-state Problems
## Stale Containers and Networks
## Dependency or Image Rebuild Problems
## Persistent-data Recovery Boundary
## Evidence to Record
## Escalation and Stop Conditions
```

Start explicitly after the normal setup path in `DEVELOPMENT.md` has failed and
link back to that guide rather than restating installation/setup steps.

- [x] **Step 2: Build a diagnosis-first recovery sequence**

For every required failure class, document:

1. Observable symptom.
2. Non-destructive diagnostic command or check.
3. Likely scope of impact.
4. Reversible recovery action.
5. Verification after recovery.
6. Stop/escalation condition.

Classify every action as process/container only, local cache/rebuild state, or
persistent project data.

Expected: Docker daemon/socket, ports 8000/5173, backend health, frontend API
connectivity, missing `GITHUB_TOKEN`, external model/network failure, Chroma
state, stale/orphan resources, and rebuild failures are all covered.

- [x] **Step 3: Guard persistent-data actions**

Keep destructive persistent-data deletion out of the default path. If any such
command is documented as a last-resort example, place immediately beside it:

1. The exact target path or resource.
2. A destructive-action warning.
3. A recoverability or backup check.
4. An explicit statement that unrelated volumes/data must not be removed.

Expected: the runbook cannot be read as permission for broad cleanup or
destructive Git operations.

- [x] **Step 4: Verify required recovery coverage**

Run:

```bash
rg -n 'Docker|socket|8000|5173|health|frontend|GITHUB_TOKEN|network|Chroma|orphan|rebuild|persistent|destructive|backup|recover' docs/runbooks/local-development.md
```

Expected: every required failure family and persistent-data guard is present.

- [x] **Step 5: Review checkpoint**

Compare the runbook with `DEVELOPMENT.md` and the Package 6 spec.

Expected: normal installation remains owned by `DEVELOPMENT.md`; recovery begins
only after diagnosis, side effects are explicit, and destructive data cleanup is
not a default remedy.

## Task 4: Create Deployment Readiness Runbook

**Files:**

- Create: `docs/runbooks/deployment.md`
- Read: `SECURITY.md`
- Read: `ARCHITECTURE.md`
- Read: `docs/architecture/current-state.md`
- Read: `docs/architecture/target-state.md`
- Read: `docs/evaluation/rag-evaluation.md`
- Read: `docs/evaluation/memory-evaluation.md`

**Interfaces:**

- Consumes: canonical security policy, architecture boundaries, and Package 5
  release-quality/safety gates.
- Produces: provider-neutral deployment-readiness, promotion, verification, and
  rollback contract that explicitly blocks the current prototype from public
  production.

- [x] **Step 1: Create the deployment runbook**

Use this top-level structure:

```markdown
# Deployment Readiness Runbook

## Scope and Current State
## Evidence Required for Promotion
## Public Production Gate
## Pre-deployment Review
## Promotion Sequence
## Post-deployment Verification
## Degraded Dependency Handling
## Rollback Readiness
## State Compatibility
## Incident Handoff
## Unsupported Actions and Stop Conditions
```

State first that no production deployment topology is approved and that this
document is currently a readiness gate, not a provider-specific deployment
procedure.

- [x] **Step 2: Encode all mandatory public-production gates**

Create a review table covering all 14 approved gate families:

1. Approved deployment architecture and ADRs.
2. Authentication and authorization.
3. Tenant/workspace isolation.
4. Restrictive environment-specific CORS.
5. TLS and trusted public origins.
6. Production secret storage and rotation.
7. Privacy-safe logs, traces, and errors.
8. Approved stores with retention/deletion/backup/restore/access ownership.
9. Health and readiness evidence.
10. Resource, timeout, retry, rate-limit, and cost controls.
11. Versioned deployable artifacts and reproducible dependencies.
12. Tested rollback and state-compatibility boundary.
13. Incident ownership and reachable operator path.
14. Package 5 RAG/memory quality and hard safety gates for claimed behavior.

Each row must define the required evidence and current outcome. Unknown or
missing evidence fails closed; it must never be treated as a pass.

Expected: the current unauthenticated, wildcard-CORS prototype cannot pass the
public-production gate by documentation alone.

- [x] **Step 3: Define provider-neutral promotion and rollback contracts**

Document pre-deployment review, promotion evidence, post-deployment verification,
dependency degradation, rollback readiness, state compatibility, and incident
handoff without inventing cloud commands, production URLs, DNS names,
credentials, vendor settings, or SLOs.

Expected: the runbook is useful before infrastructure selection while making
every provider-specific execution step an explicit later governed concern.

- [x] **Step 4: Verify fail-closed wording and gate completeness**

Run:

```bash
rg -n 'authentication|authorization|isolation|CORS|TLS|secret|logging|retention|deletion|backup|readiness|timeout|retry|rate|cost|versioned|rollback|incident|RAG|memory|FAIL|BLOCKED|production' docs/runbooks/deployment.md
```

Expected: all 14 gate families are visible and missing evidence cannot produce a
production-ready outcome.

- [x] **Step 5: Review checkpoint**

Read the complete deployment runbook together with `SECURITY.md` and current
architecture docs.

Expected: no deployment topology or runtime control is invented, and current
prototype limitations are clearly distinguished from future mandatory controls.

## Task 5: Create Incident Response Runbook

**Files:**

- Create: `docs/runbooks/incident-response.md`
- Read: `SECURITY.md`
- Read: `docs/runbooks/deployment.md`
- Read: `docs/evaluation/memory-evaluation.md`
- Read: `docs/specs/2026-08-31-operations-and-security-design.md`

**Interfaces:**

- Consumes: Package 6 security policy, deployment stop conditions, Package 5
  memory hard gates, and approved incident scenarios.
- Produces: common security/operations incident lifecycle with bounded first
  responses and routing for permanent fixes.

- [x] **Step 1: Create the incident response runbook**

Use this top-level structure:

```markdown
# Incident Response Runbook

## Scope
## Incident Principles
## Severity and Scope Classification
## Detect and Record
## Contain
## Preserve Evidence
## Eradicate
## Recover
## Post-incident Review
## Scenario Playbooks
## Permanent-fix Governance
## Escalation and Stop Conditions
```

Define a simple severity model by impact and scope without promising response-
time SLAs that the repository owner has not adopted.

- [x] **Step 2: Encode the common incident lifecycle**

For detect, classify, contain, preserve evidence, eradicate, recover, and review,
state the goal, minimum evidence, privacy/redaction rule, reversible action
preference, and condition required to advance.

Expected: incident records remain reviewable without becoming repositories of
secrets or unnecessary private user content.

- [x] **Step 3: Add all required first-response scenarios**

Create bounded scenario playbooks for:

1. Credential/token exposure.
2. Private/user data in logs, issues, traces, screenshots, or reports.
3. Unauthorized access or cross-user/cross-workspace leakage.
4. Deleted/tombstoned memory becoming retrievable.
5. Unsafe public exposure of the current unauthenticated or wildcard-CORS API.
6. Data corruption, accidental deletion, or vector-store integrity loss.
7. External model/provider outage or suspected provider compromise.
8. Malicious retrieved content or prompt injection crossing a trust boundary.
9. Dependency or container-image compromise.

Each scenario must distinguish immediate reversible containment from permanent
repository remediation.

Expected: Package 5 hard-gate incidents remain visible as hard failures and are
not softened by aggregate operational metrics.

- [x] **Step 4: Verify scenario completeness**

Run:

```bash
rg -n 'credential|token|logs|issues|traces|cross-user|cross-workspace|deleted|tombstoned|unauthenticated|CORS|corruption|vector|provider|prompt injection|dependency|container|contain|redact|recover|post-incident' docs/runbooks/incident-response.md
```

Expected: all required first-response cases and lifecycle phases are present.

- [x] **Step 5: Review checkpoint**

Read the runbook against the spec's Incident Response, Errors and Edge Cases,
Security and Privacy, and Observability and Operations sections.

Expected: immediate containment is operational and reversible where possible;
permanent code/configuration/architecture/data changes route back through normal
spec, architecture, plan, verification, and owner-review gates.

## Task 6: Add Minimal Routing and Package Traceability

**Files:**

- Modify: `AGENTS.md` under `Context Routing`
- Modify: `README.md` documentation navigation and current-limitations wording
- Modify: `DEVELOPMENT.md` local troubleshooting/recovery routing
- Modify: `CONTRIBUTING.md` `Security Reports`
- Modify: `ARCHITECTURE.md` production security/deployment routing
- Modify: `docs/roadmap/master-roadmap.md` `D6` rows only
- Modify: `docs/specs/README.md` Package 6 discovery row only if lifecycle text needs synchronization
- Modify: `docs/specs/2026-08-31-operations-and-security-design.md` implementation-plan and execution traceability fields
- Modify: `docs/plans/README.md` Package 6 plan row
- Modify: `docs/plans/2026-08-31-operations-and-security-implementation.md` lifecycle/checklist evidence

**Interfaces:**

- Consumes: Tasks 2-5 canonical documents and successful task-level review.
- Produces: discoverable Package 6 ownership without duplicating canonical
  content or prematurely accepting `D6`.

- [x] **Step 1: Route agent context**

Add only the minimum `AGENTS.md` Context Routing triggers needed after the new
targets exist:

1. Repository security, privacy, secrets, trust boundary, vulnerability
   reporting, and production security gate -> `SECURITY.md`.
2. Diagnosed local-stack recovery -> `docs/runbooks/local-development.md`.
3. Deployment readiness/promotion/rollback -> `docs/runbooks/deployment.md`.
4. Security or operational incident response ->
   `docs/runbooks/incident-response.md`.

Expected: existing architecture, setup, evaluation, spec, plan, ADR, and
contribution routing remains intact.

- [x] **Step 2: Update human entry points without duplicating policy**

Update `README.md` to link the policy and runbooks and remove only the obsolete
claim that no security policy or deployment runbook exists. Preserve the claim
that production readiness is not established.

Update `DEVELOPMENT.md` with a concise pointer from diagnosed broken-stack
recovery to the local runbook. Do not move normal installation/setup ownership.

Update `CONTRIBUTING.md` so `Security Reports` points to `SECURITY.md` as the
canonical policy instead of retaining interim ownership.

Update `ARCHITECTURE.md` so production security/privacy and deployment-readiness
questions route to `SECURITY.md` and the deployment runbook without claiming the
controls are implemented.

Expected: each document remains a gateway to canonical ownership rather than a
second copy of Package 6 policy.

- [x] **Step 3: Update Package 6 lifecycle and discovery metadata**

During approved execution, change only the `D6` milestone state from `Planned`
to `In progress` and update its recommended next action to reflect Package 6
implementation/review. Do not alter the known unrelated `D4` state or any
runtime milestone.

Keep `docs/specs/README.md`, the Package 6 spec `Implementation plan` field,
`docs/plans/README.md`, and this plan synchronized with actual lifecycle state.
After successful verification, this plan may become `Completed` while the `D6`
roadmap remains `In progress` until the repository owner accepts the exact
change set.

Expected: spec status stays `Approved`; plan execution status never implies Git
delivery or owner acceptance.

- [x] **Step 4: Review checkpoint**

Read every routing and lifecycle edit together.

Expected: all new links resolve, ownership is unambiguous, production readiness
is not overstated, `D7` remains dependent on `D6`, and unrelated roadmap states
are unchanged.

## Task 7: Package Verification and Repository-owner Review Gate

**Files:**

- Read: every file in the File Responsibility Map
- Read: every source/configuration file used by Task 1 evidence

**Interfaces:**

- Consumes: Tasks 1-6 outputs.
- Produces: deterministic Package 6 evidence for repository-owner review of the
  exact implementation change set.

- [x] **Step 1: Run secret-safety scan**

Run:

```bash
rg -n 'gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|GITHUB_TOKEN=[^[:space:]]+' SECURITY.md docs/runbooks AGENTS.md README.md DEVELOPMENT.md CONTRIBUTING.md ARCHITECTURE.md docs/roadmap/master-roadmap.md docs/specs/README.md docs/specs/2026-08-31-operations-and-security-design.md docs/plans/README.md docs/plans/2026-08-31-operations-and-security-implementation.md
```

Expected: no credential-like values, private keys, or assigned non-placeholder
`GITHUB_TOKEN` values are present. Credential names such as `GITHUB_TOKEN`
without a secret value are allowed.

- [x] **Step 2: Run drafting-marker, whitespace, and fenced-block checks**

Run:

```bash
rg -n 'TO''DO|TB''D|PLACE''HOLDER|\[Exact'' path\]|\[One'' action\]|\[YYYY''-MM-DD\]' SECURITY.md docs/runbooks docs/plans/2026-08-31-operations-and-security-implementation.md
rg -n '[[:blank:]]+$' SECURITY.md docs/runbooks/local-development.md docs/runbooks/deployment.md docs/runbooks/incident-response.md AGENTS.md README.md DEVELOPMENT.md CONTRIBUTING.md ARCHITECTURE.md docs/roadmap/master-roadmap.md docs/specs/README.md docs/specs/2026-08-31-operations-and-security-design.md docs/plans/README.md docs/plans/2026-08-31-operations-and-security-implementation.md
ruby -e 'bad=[]; ARGV.each { |f| n=File.read(f).scan(/^```/).length; bad << "#{f}: #{n}" if n.odd? }; if bad.empty?; puts "all fenced code blocks balanced"; else; puts bad; exit 1; end' SECURITY.md docs/runbooks/local-development.md docs/runbooks/deployment.md docs/runbooks/incident-response.md docs/plans/2026-08-31-operations-and-security-implementation.md
```

Expected: no unresolved drafting markers or trailing whitespace in Package 6
scope, and every checked Markdown file has balanced fenced code blocks.

- [x] **Step 3: Resolve repository-relative Markdown links**

Run:

```bash
ruby -e 'missing=[]; ARGV.each do |f|; dir=File.dirname(f); File.read(f).scan(/\[[^\]]+\]\(([^)]+)\)/).flatten.each do |href|; path=href.split("#",2)[0]; next if path.empty? || path =~ /^[a-z][a-z0-9+.-]*:/ || path.start_with?("mailto:"); target=File.expand_path(path, dir); missing.push("#{f} -> #{href}") unless File.exist?(target); end; end; if missing.empty?; puts "all local markdown links resolve"; else; puts missing; exit 1; end' SECURITY.md docs/runbooks/local-development.md docs/runbooks/deployment.md docs/runbooks/incident-response.md AGENTS.md README.md DEVELOPMENT.md CONTRIBUTING.md ARCHITECTURE.md docs/roadmap/master-roadmap.md docs/specs/README.md docs/specs/2026-08-31-operations-and-security-design.md docs/plans/README.md docs/plans/2026-08-31-operations-and-security-implementation.md
```

Expected: `all local markdown links resolve`.

- [x] **Step 4: Perform policy-ownership review**

Read `SECURITY.md`, `DEVELOPMENT.md`, `CONTRIBUTING.md`, `ARCHITECTURE.md`, both
Package 5 evaluation protocols, and all three runbooks together. For each topic,
name one canonical owner:

1. Normal local setup -> `DEVELOPMENT.md`.
2. Security/privacy/secrets/reporting/data handling -> `SECURITY.md`.
3. Broken local-stack recovery -> local-development runbook.
4. Architecture/current-target system truth -> architecture docs.
5. RAG/memory evaluation gates -> Package 5 evaluation protocols.
6. Deployment readiness/promotion/rollback -> deployment runbook.
7. Incident lifecycle/first response -> incident-response runbook.
8. Contribution workflow -> `CONTRIBUTING.md`.

Expected: routing documents summarize only enough to point to the canonical
owner; contradictory or duplicated policy is removed from Package 6 scope.

- [x] **Step 5: Review runbook command side effects**

Inspect every shell command shown in the three runbooks and classify it as:

1. Read-only diagnostic.
2. Process/container lifecycle.
3. Local cache/rebuild state.
4. Persistent project data.
5. External or hosting-platform effect.

Expected: persistent-data commands, if any, are explicitly guarded and outside
default recovery; no command mutates hosting-platform settings or performs Git
delivery; no provider-specific production deployment command exists.

- [x] **Step 6: Prove deployment fails closed for the current prototype**

Review each of the 14 public-production gate rows against Task 1 current-state
evidence.

Expected: missing authentication/authorization, permissive CORS, absent approved
production topology, and other missing evidence keep the public-production gate
in a failed/blocked state. Documentation alone cannot change that result.

- [x] **Step 7: Review every required incident scenario**

Walk the nine scenario playbooks and record whether each includes detection,
scope, reversible containment, redacted evidence, recovery criteria, and
permanent-fix routing.

Expected: credential exposure, private-data leakage, cross-scope leakage,
deleted-memory retrieval, unsafe public exposure, integrity loss, provider
failure/compromise, prompt injection, and supply-chain compromise all have
complete first-response guidance.

- [x] **Step 8: Re-check Codebase Memory coverage and direct-source claims**

Re-run the Verify-tier coverage check for every source and documentation path
relied on by current-state statements. Re-read any reported missed range and the
material source lines for authentication, CORS, logging, credentials, Docker,
Compose, and persistence claims.

Expected: every material current-state statement in Package 6 remains grounded
in current repository evidence; limitations are disclosed.

- [x] **Step 9: Review the complete working-tree scope**

Run:

```bash
git status --short --untracked-files=all
```

Then directly read every Package 6 file that is untracked and use read-only
diffs for tracked Package 6 files. Do not rely on `git diff` alone because
earlier documentation packages may still be untracked.

Expected: Package 6 changes are bounded to the File Responsibility Map, all
unrelated Package 0-5 work is preserved, and no runtime, dependency, Docker,
environment, credential, persistent-data, hosting-platform, or Git-delivery
change is included.

- [x] **Step 10: Stop for repository-owner change-set review**

Report changed files, Codebase Memory coverage evidence, direct-source evidence,
secret-safety results, policy-ownership review, runbook side-effect review,
deployment-gate result, incident-scenario coverage, deterministic Markdown/link
checks, scope review, and every limitation.

Expected: no Git staging, commit, push, PR, merge, release, or `D6` owner-
accepted status occurs before the repository owner explicitly accepts the exact
Package 6 implementation change set.

## Package Verification

Package 6 is ready for repository-owner review only when all of the following
are true:

1. `SECURITY.md` and all three runbooks exist with distinct canonical ownership.
2. Current authentication, CORS, logging, credential, Docker, Compose, and
   persistence statements were refreshed with Codebase Memory Verify-tier
   evidence plus direct source/configuration reads.
3. The security policy contains no real secret, invented private contact, or
   unverified vulnerability-reporting capability.
4. Data-class handling, logging minimization, trust boundaries, retention and
   deletion contracts, and Package 5 memory hard gates match the approved spec.
5. Local recovery starts after normal setup, uses diagnosis-first reversible
   actions, and does not make persistent-data deletion the default.
6. The deployment runbook includes all 14 mandatory gate families and the
   current prototype demonstrably fails closed for public production.
7. The incident runbook covers all nine required first-response scenarios and
   distinguishes immediate containment from governed permanent fixes.
8. Existing canonical setup, architecture, evaluation, contribution, roadmap,
   and governance documents are linked rather than duplicated.
9. All repository-relative links resolve; drafting-marker, whitespace, fenced-
   block, and secret-safety checks pass.
10. The complete Package 6 change set is within the approved documentation-only
    scope and preserves unrelated working-tree changes.
11. No provider architecture, authentication architecture, production SLO,
    numeric retention policy, live deployment, platform setting, runtime
    security control, or penetration-test claim is introduced.
12. Repository-owner change-set review remains open until explicit acceptance.

## Rollback

Before Git delivery, rollback removes only `SECURITY.md`, the three Package 6
runbooks, and Package 6 routing/traceability edits named in the File
Responsibility Map. Preserve all unrelated Package 0-5 work and user changes.
Do not alter runtime source, tests, dependencies, Docker/Compose state, `.env`,
credentials, Chroma data, hosting-platform settings, or Git history.

## Completion Record

Plan version 0.1 was prepared after approval of
[Operations and Security Design](../specs/2026-08-31-operations-and-security-design.md)
version 0.1. The repository owner approved this exact implementation plan on
2026-08-31 via the conversation phrase `Approve Package 6 implementation plan`.
The approved tasks were executed and the Package 6 documentation passed the
plan's verification checks on 2026-08-31. The repository owner accepted the
exact Package 6 change set on 2026-08-31 via the conversation phrase
`accept Package 6 change set`. Package 6 is therefore accepted in the working
tree. This acceptance does not authorize Git delivery.

Fresh verification recorded for this completion includes Codebase Memory
Verify-tier coverage with direct source/configuration checks, all 15 required
security-policy headings, all 14 deployment gates in a blocked/fail-closed
state, all nine incident scenarios with complete first-response fields, no
credential-like values in Package 6 content, no drafting markers or trailing
whitespace, balanced fenced code blocks, and resolving repository-relative
Markdown links. Runbook command review found no persistent-data deletion,
hosting-platform mutation, provider-specific production deployment, or Git
delivery command.

Repository-owner review of the exact Package 6 change set is **Accepted**.
`D6` is `Accepted in working tree`. No staging, commit, push, PR, merge, or
release is authorized by this acceptance.
