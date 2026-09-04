# Documentation System Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-08-30 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Repository-wide documentation and approval system |
| Derived specs | [Agent Operating System Design](./2026-08-30-agent-operating-system-design.md), version 0.1; [Project Entry Points Design](./2026-08-31-project-entry-points-design.md), version 0.1 (Approved); [Architecture Baseline Design](./2026-08-31-architecture-baseline-design.md), version 0.1 (Approved) |

## Summary

This document defines the documentation system for Travel Agent. It establishes
which documents exist, what each document owns, how documents reference one
another, and which approval gates apply before repository changes begin.

The system uses concise root documents as entry points and places detailed,
task-specific material under `docs/`. `AGENTS.md` acts as the operational router
for coding agents. Specifications define why and what will change;
implementation plans define how an approved specification will be delivered;
ADRs preserve durable architecture decisions.

This design is the only deliverable in Documentation Package 0. It does not
authorize creation of the remaining documentation packages or implementation
changes.

## Context

Travel Agent is moving from an early RAG prototype toward a production-oriented
travel assistant with trip workspaces, evaluated retrieval, and layered agent
memory. The repository currently lacks a stable documentation hierarchy and a
formal method for approving changes. Without explicit ownership boundaries,
documentation can become duplicated, stale, or too broad for a human or coding
agent to use reliably.

The repository owner also requires an educational workflow: architectural
reasoning, trade-offs, verification evidence, and operational practices must be
visible rather than hidden inside implementation work.

## Goals

1. Give humans and coding agents one predictable entry point for every kind of
   repository work.
2. Keep each fact, rule, decision, and procedure in one canonical location.
3. Require explicit specification, design, and plan approvals before changes are
   implemented.
4. Make every change traceable from problem statement through verification and
   review.
5. Separate current facts from proposed target state.
6. Keep documentation maintainable as the product, architecture, and team grow.
7. Make engineering decisions and their evidence useful as learning material.

## Non-goals

1. This design does not define the final application architecture, RAG design,
   memory design, or data model.
2. This design does not create empty placeholder files for future packages.
3. This design does not replace executable configuration, source code, tests, or
   generated command help as sources of truth.
4. This design does not authorize code, dependency, infrastructure, Git, or
   GitHub configuration changes.
5. This design does not require enterprise documentation tooling or an external
   documentation service.

## Design Principles

### Single source of truth

Each subject has one canonical document. Other documents link to that source and
provide only enough context to explain why the link is relevant. When two files
appear to own the same information, ownership must be resolved before either is
approved.

Executable repository configuration remains authoritative for values that can
be discovered cheaply, including dependency versions, script definitions, and
tool configuration. Documentation records intent, workflow, non-obvious
constraints, and verified usage rather than copying configuration line by line.

### Progressive disclosure

Frequently needed rules stay in short root documents. Detailed architecture,
evaluation, operations, and learning material lives under `docs/` and is loaded
only when the task requires it. `AGENTS.md` contains trigger-based pointers to
the relevant canonical documents.

### Evidence before claims

Current-state documentation must cite repository paths, commands, tests, or
other reviewable evidence. Target-state documentation must label proposed
behavior explicitly. An unimplemented design must never be described as current
behavior.

### Checkable completion

Specifications, plans, ADRs, runbooks, and evaluation documents must define
observable completion or decision criteria. Terms such as "production-ready",
"robust", or "well-tested" are insufficient without measurable conditions.

### Approval is a hard gate

Preparation and investigation may precede approval. Repository implementation
may not. If new evidence invalidates an approved assumption, work returns to the
appropriate approval gate before continuing.

### Documentation is part of the change

A change is incomplete when its behavior, interface, operation, security model,
or architectural decision has changed but its canonical documentation has not.
Documentation updates belong in the same review unit as the behavior they
describe unless an approved migration plan explicitly sequences them.

## Information Architecture

### Root documents

Root documents are short, stable entry points.

| Document | Canonical responsibility |
| --- | --- |
| `AGENTS.md` | Agent workflow, required reading triggers, approval gates, verification rules, and Git safety |
| `CLAUDE.md` | Claude-specific adapter that points to `AGENTS.md`; only Claude-specific differences belong here |
| `README.md` | Product identity, current maturity, quick start, repository map, and documentation entry points |
| `DEVELOPMENT.md` | Supported local toolchain, setup, commands, environment, and development troubleshooting |
| `CONTRIBUTING.md` | Issue, branch, commit, review, approval, and contribution workflow |
| `ARCHITECTURE.md` | High-level system map, architectural invariants, and pointers to detailed architecture documents |
| `SECURITY.md` | Vulnerability reporting and repository-wide security, privacy, trust, and secret-handling policy |
| `CHANGELOG.md` | User-visible changes grouped by released version |
| `LICENSE` | License terms for repository source code |
| `THIRD_PARTY_NOTICES.md` | Required notices and attribution for third-party code, models, and datasets |

Root documents must not reproduce detailed material owned by `docs/`.

### Detailed documents

| Path | Canonical responsibility |
| --- | --- |
| `docs/roadmap/` | Product and engineering milestones, dependencies, and milestone exit gates |
| `docs/specs/` | Approved or in-review change specifications and architecture designs |
| `docs/plans/` | Approved or in-review implementation plans derived from specifications |
| `docs/adr/` | Durable architecture decisions, alternatives, and consequences |
| `docs/architecture/` | Verified current state, approved target state, and cross-domain data model |
| `docs/evaluation/` | Evaluation datasets, metrics, protocols, quality gates, and result interpretation |
| `docs/runbooks/` | Step-by-step operational procedures for known conditions |
| `docs/learning/` | Engineering curriculum, milestone lessons, and review exercises |

Each of `docs/specs/`, `docs/plans/`, and `docs/adr/` has a `README.md` index.
The index owns the artifact template, status definitions, discovery table, and
links within that document category. It does not repeat the content of indexed
documents. An index is created with the first package that needs its workflow;
it is not created as an empty placeholder.

### GitHub documents

| Path | Canonical responsibility |
| --- | --- |
| `.github/PULL_REQUEST_TEMPLATE.md` | Evidence and review checklist for proposed repository changes |
| `.github/ISSUE_TEMPLATE/feature.md` | Feature problem, scope, acceptance, and evaluation intake |
| `.github/ISSUE_TEMPLATE/bug.md` | Reproduction, impact, expected behavior, and regression-test intake |
| `.github/ISSUE_TEMPLATE/technical-debt.md` | Evidence, risk, desired boundary, and exit criteria for technical debt |
| `.github/ISSUE_TEMPLATE/experiment.md` | Hypothesis, baseline, variables, dataset, metrics, and promotion decision |

GitHub templates collect work intake and review evidence. They do not replace
repository specifications when the change classification requires a persistent
design artifact.

## Document Boundaries

### Development guide and local runbook

`DEVELOPMENT.md` owns installation, supported versions, normal commands, and
common development troubleshooting. `docs/runbooks/local-development.md` owns
operational recovery procedures for a broken local stack. A normal setup command
belongs only in `DEVELOPMENT.md`; a diagnosed recovery sequence belongs only in
the runbook.

### Architecture gateway and detailed architecture

`ARCHITECTURE.md` is the stable map. `docs/architecture/current-state.md`
contains evidence-backed behavior that exists. `docs/architecture/target-state.md`
contains approved future boundaries and migration direction.
`docs/architecture/data-model.md` owns cross-domain entities, relationships,
lifecycles, and isolation constraints.

### Specifications, plans, and ADRs

A specification defines the problem, desired behavior, scope, constraints,
alternatives, risks, and acceptance criteria. An implementation plan translates
one approved specification into ordered, independently verifiable tasks. An ADR
records a durable decision after its alternatives have been evaluated; it does
not serve as a feature specification or task plan.

### Roadmap and changelog

The roadmap describes intended future outcomes and milestone gates. The
changelog records outcomes that have already shipped in a version. Planned work
must never appear as a released changelog entry.

## Change Classification

Every persistent repository change requires a written specification and an
approved implementation plan. The artifact size scales with risk, but the
approval gate does not disappear.

### Level 1 - Change Spec

Use for a narrow documentation correction, isolated bug fix, configuration
adjustment, or dependency maintenance change that does not alter architecture or
cross-module contracts.

Required content:

1. Problem and evidence.
2. Scope and non-goals.
3. Expected behavior.
4. Acceptance criteria.
5. Verification commands or review method.
6. Risk and rollback.
7. Implementation steps.

The approved GitHub issue may contain both the specification and implementation
plan for Level 1 work. A repository spec file is optional unless the decision
must remain discoverable after the issue is closed.

### Level 2 - Feature Spec

Use for new behavior or a material change to an API, schema, user flow,
evaluation protocol, security rule, or module contract.

Required content:

1. Context, problem, and users affected.
2. Goals, non-goals, and assumptions.
3. User and system flows.
4. Behavioral and data contracts.
5. Error and edge-case behavior.
6. Security, privacy, observability, and operational impact.
7. Testing and evaluation strategy.
8. Rollout, migration, and rollback.
9. Measurable acceptance criteria.

Level 2 work requires separate files under `docs/specs/` and `docs/plans/`.

### Level 3 - Architecture Design

Use for new subsystems or changes to module boundaries, storage, protocols,
deployment topology, trust boundaries, or other hard-to-reverse decisions.

Level 3 includes every Level 2 section plus:

1. Current-state evidence.
2. At least two viable alternatives and their trade-offs.
3. Component responsibilities and dependency direction.
4. Data flow and lifecycle design.
5. Failure modes and recovery behavior.
6. Capacity, latency, and cost considerations where relevant.
7. Compatibility and staged migration strategy.
8. Decision records required after approval.

Level 3 work requires a design under `docs/specs/`, an implementation plan under
`docs/plans/`, and an ADR for each accepted durable architecture decision.

When classification is uncertain, use the higher level. Discovery of wider
impact during implementation upgrades the classification and returns the work
to design review.

## Required Metadata

Every specification and implementation plan begins with a metadata table.

Required specification fields:

1. Status.
2. Version.
3. Date.
4. Change class.
5. Decision owner.
6. Scope.
7. Related issue when one exists.
8. Superseded document when applicable.

Required implementation plan fields:

1. Status.
2. Date.
3. Approved specification path and version.
4. Execution owner.
5. Scope.
6. Verification commands.

An ADR records status, date, decision owners, context, decision, alternatives,
consequences, and superseded ADRs where applicable.

## Naming Rules

1. Specifications use `docs/specs/YYYY-MM-DD-kebab-case-design.md`.
2. Implementation plans use
   `docs/plans/YYYY-MM-DD-kebab-case-implementation.md`.
3. ADRs use `docs/adr/NNNN-kebab-case.md`, where the number is monotonically
   increasing and never reused.
4. Long-lived architecture, evaluation, runbook, and learning files use stable
   kebab-case names without dates.
5. Technical documentation, code identifiers, API names, commits, and GitHub
   artifacts use English.
6. Conversation and teaching explanations may use Vietnamese.
7. Renaming an approved document requires updating every repository reference in
   the same change.

## Document Status Lifecycle

### Specifications

1. `Draft`: authoring is in progress and no approval is implied.
2. `In Review`: content is complete enough for the decision owner to evaluate.
3. `Approved`: the decision owner has explicitly approved the recorded version.
4. `Superseded`: a newer approved document replaces the design; the replacement
   is linked in metadata.

Rejected proposals do not become authoritative repository documentation. Their
discussion remains in the associated issue or review history.

### Implementation plans

1. `Draft`.
2. `In Review`.
3. `Approved`.
4. `In Progress`.
5. `Completed`.
6. `Superseded`.

Plan status records delivery state, not product release state. A completed plan
may still await PR review or release.

### ADRs

ADRs use `Proposed`, `Accepted`, `Superseded`, or `Deprecated`. Accepted ADRs are
immutable except for factual corrections and status or reference updates. A new
decision supersedes the old ADR rather than rewriting its historical reasoning.

## Approval Workflow

Every change follows this sequence:

1. **Intake:** record the problem, evidence, desired outcome, and initial scope.
2. **Classification:** assign Level 1, Level 2, or Level 3.
3. **Specification:** complete the required design content for that level.
4. **Spec approval:** the repository owner approves the exact specification
   version.
5. **Architecture approval:** for Level 3, approve durable architecture decisions
   and identify the ADRs that will preserve them.
6. **Implementation planning:** produce ordered tasks from the approved spec.
7. **Plan approval:** the repository owner approves the exact plan version.
8. **Implementation:** make only changes covered by the approved artifacts.
9. **Verification:** run the specified checks and preserve reviewable evidence.
10. **Change-set review:** the repository owner reviews the exact repository
    change set, including untracked file contents.
11. **Git operations:** the repository owner creates or selects the branch and
    decides when to commit, push, open a PR, merge, and release.
12. **Closure:** update document status and linked artifacts after the result is
    accepted.

Package 0 is the documentation-system bootstrap. The repository owner approved
its scope and writing plan in the design conversation before this file was
created. It therefore has no separate repository plan file. This is a one-time
bootstrap exception to artifact location, not to human approval. Starting with
Package 1, every change follows the artifact requirements defined in this
document.

Coding agents may investigate, draft, implement after approval, and report
verification evidence. They do not create or switch branches, commit, push,
merge, change GitHub settings, or bypass an approval gate unless the repository
owner explicitly requests that exact action.

## Change Control

Implementation must stop and return to review when any of these occurs:

1. A stated assumption is false.
2. Scope expands beyond the approved acceptance criteria.
3. A public contract, schema, trust boundary, or module boundary changes
   unexpectedly.
4. A planned dependency or migration is no longer viable.
5. Verification reveals a risk not covered by the approved design.
6. The rollback strategy is no longer safe.

Minor wording corrections that do not alter meaning may be reviewed as Level 1
changes. Any correction that changes requirements, behavior, boundaries, or
acceptance criteria requires a new document version and explicit reapproval.

## Traceability

The intended trace is:

`issue or intake -> specification -> ADRs -> implementation plan -> repository change set -> verification evidence -> PR -> release`

Each artifact links backward to the decision it derives from and forward to the
next artifact when that artifact exists. A reviewer must be able to determine:

1. Why the change exists.
2. What was approved.
3. Which decisions constrain the implementation.
4. How correctness was evaluated.
5. What actually changed.
6. How to recover if the change fails.

Bootstrap documentation may begin without a GitHub issue. Starting with Package
1, repository changes should use a linked issue unless the repository owner
explicitly approves a documented exception.

## Agent Context Loading

`AGENTS.md` will be the canonical always-loaded router. It must remain concise
and use explicit task triggers:

1. Architecture or cross-module work loads `ARCHITECTURE.md`, relevant detailed
   architecture, the approved spec, and applicable ADRs.
2. Implementation work loads the approved spec and implementation plan.
3. RAG work loads the RAG evaluation protocol.
4. Memory work loads the memory evaluation protocol and applicable data/security
   rules.
5. Environment or test setup work loads `DEVELOPMENT.md`.
6. Operational work loads the relevant runbook.
7. Contribution and GitHub work loads `CONTRIBUTING.md`.
8. Security-sensitive work loads `SECURITY.md`.

Agent adapters such as `CLAUDE.md` point to `AGENTS.md` and contain only
tool-specific differences. Duplicating general instructions across adapters is
not permitted because it creates conflicting sources of truth.

## Maintenance Rules

1. The author of a behavioral change identifies affected canonical documents in
   the specification and implementation plan.
2. Reviewers reject links to missing, superseded, or contradictory sources.
3. Generated outputs, evaluation reports, and model indexes are stored according
   to their artifact policy; they are not manually copied into narrative docs.
4. Every release review checks whether `README.md`, `CHANGELOG.md`, runbooks,
   migrations, and security guidance changed.
5. Every milestone review checks roadmap status, evaluation gates, architecture
   drift, and accumulated technical debt.
6. Superseded documents remain available for history and clearly point to their
   replacements.
7. Empty documents and speculative directory scaffolding are not created. A file
   is added when its first approved content is ready.
8. Documentation links use repository-relative paths inside repository files.

## Quality Standard

A document is ready for review only when all applicable checks pass:

1. Its purpose and canonical ownership are explicit.
2. Scope and non-goals are both present.
3. Current-state claims are supported by evidence.
4. Proposed behavior is distinguishable from implemented behavior.
5. Requirements and completion criteria are measurable or directly reviewable.
6. Error cases, risks, security, migration, and rollback are addressed at the
   depth appropriate to the change class.
7. Terms and identifiers are consistent across related documents.
8. Every referenced file exists or is clearly identified as a future artifact in
   an approved rollout sequence.
9. There are no unresolved drafting markers or deferred requirements.
10. The document does not duplicate a canonical source.
11. Links and commands are syntactically valid.
12. The decision owner can determine exactly what approval authorizes.

## Documentation Package Rollout

The remaining documentation is divided into independently reviewable packages:

1. **Package 1 - Agent Operating System:** `AGENTS.md`, `CLAUDE.md`,
   `CONTRIBUTING.md`, and the `docs/specs/`, `docs/plans/`, and `docs/adr/`
   workflow indexes.
2. **Package 2 - Project Entry Points:** `README.md`, `DEVELOPMENT.md`, and
   `ARCHITECTURE.md`.
3. **Package 3 - Architecture Baseline:** current state, target state, and data
   model.
4. **Package 4 - Roadmap and Learning:** master roadmap and engineering
   curriculum.
5. **Package 5 - Evaluation:** RAG and memory evaluation protocols.
6. **Package 6 - Operations and Security:** `SECURITY.md` and operational
   runbooks.
7. **Package 7 - GitHub and Open Source:** templates, license, notices, and
   release documentation.

Each package receives its own approved specification and implementation plan.
Approval of this design authorizes only the documentation system and the
preparation of Package 1's specification; it does not approve Package 1 content
or implementation.

## Alternatives Considered

### One comprehensive handbook

A single handbook would be easy to locate but would mix agent instructions,
architecture, setup, operations, and learning material. It would impose high
context cost, make ownership unclear, and encourage unrelated edits to the same
file. This option is rejected.

### Independent documents without a canonical router

Small independent documents reduce file size, but humans and agents would need
to guess which files apply. Important approval and security rules could be
missed. This option is rejected.

### External wiki as the primary source

An external wiki provides navigation and collaboration features but separates
decisions from the code and makes versioned review harder. It also introduces an
unnecessary service dependency for the current team size. This option is
rejected for the current stage.

### Repository hierarchy with progressive disclosure

Short root entry points plus focused documents under `docs/` preserve
discoverability, versioning, review history, and selective context loading. The
additional files create some navigation cost, which is controlled by
`AGENTS.md`, root gateways, and directory indexes. This is the selected design.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Documentation becomes bureaucratic | Scale artifact depth by change level while retaining the approval gate |
| Root files become duplicated handbooks | Enforce canonical ownership and use links for details |
| Agents ignore relevant detailed docs | Use trigger-based pointers in concise `AGENTS.md` |
| Approved docs drift from code | Treat documentation updates as part of the same change and review architecture drift at milestones |
| Many small files become hard to navigate | Maintain focused gateway and index documents only when real content exists |
| Plans silently diverge from approved specs | Link exact spec versions and return to approval when assumptions change |
| Historical decisions are rewritten | Preserve accepted ADRs and supersede them with new records |

## Acceptance Criteria

Documentation Package 0 is complete when:

1. This design exists at
   `docs/specs/2026-08-30-documentation-system-design.md`.
2. The repository owner has reviewed the exact repository change set, including
   untracked file contents, and explicitly approved version 0.1.
3. The approved document defines canonical ownership for every planned document
   category.
4. Change levels, artifact requirements, status lifecycles, approval gates, and
   stop conditions are unambiguous.
5. Specifications, plans, ADRs, and GitHub intake artifacts have distinct
   responsibilities.
6. Agent and repository-owner permissions are explicit.
7. The document contains no unresolved placeholders or broken internal links.
8. No Package 1-7 file has been created as part of Package 0.
9. After approval, status is changed from `In Review` to `Approved` in a
   separately reviewed change.

## Approval Record

Version 0.1 was explicitly approved by the repository owner on 2026-08-30. This
approval establishes the documentation system and authorizes preparation of the
Package 1 specification. It does not approve Package 1 content or implementation.
