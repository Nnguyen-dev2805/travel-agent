# Roadmap and Learning Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-08-31 |
| Change class | Level 2 - Feature Spec |
| Decision owner | Repository owner |
| Scope | Documentation Package 4 - master roadmap and engineering curriculum |
| Parent design | [Documentation System Design](./2026-08-30-documentation-system-design.md), version 0.1 |
| Depends on | [Architecture Baseline Design](./2026-08-31-architecture-baseline-design.md), version 0.1 |
| Implementation plan | [Roadmap and Learning Implementation Plan](../plans/2026-08-31-roadmap-and-learning-implementation.md), version 0.1 (Approved; Completed) |
| Related issue | None - approval of version 0.1 records the repository-owner exception for this conversation intake |
| Superseded document | None |

## Summary

Package 4 creates two long-lived planning documents:
`docs/roadmap/master-roadmap.md` and
`docs/learning/engineering-curriculum.md`.

The master roadmap turns the approved documentation and architecture baseline
into an ordered product and engineering path. It must show how Travel Agent can
move from the current RAG prototype toward evaluated trip workspaces, layered
memory, planning, operations, and open-source readiness without implying that
future milestones already exist.

The engineering curriculum turns the same roadmap into a practical learning
path for the repository owner. It must teach senior AI engineering and senior
software engineering judgment through this repository's actual milestones,
approval gates, verification habits, and implementation sequence.

Approval of this specification authorizes preparation of a Package 4
implementation plan only. It does not authorize creating the roadmap or
curriculum files, implementing runtime behavior, changing architecture,
creating ADRs, changing GitHub configuration, or performing Git delivery.

## Context

Documentation Packages 0 through 3 established the repository governance,
entry points, and architecture baseline:

1. Package 0 defined the documentation system and identified Package 4 as
   roadmap and learning documentation.
2. Package 1 created agent, contribution, spec, plan, and ADR workflows.
3. Package 2 created concise project entry points and local development
   guidance.
4. Package 3 recorded the implemented architecture baseline, target
   workspace-first architecture, and conceptual target data model.

The repository still lacks a single milestone map that answers what should be
built next and why. It also lacks a learning path that helps the repository
owner practice the engineering skills needed to run the project with coding
agents, GitHub, specs, plans, evaluations, and production-minded architecture.

## Users

1. **Repository owner:** wants a clear build order and a practical curriculum
   for becoming stronger at AI engineering, coding, GitHub workflow, and
   architecture review.
2. **Coding agent:** needs a canonical roadmap to avoid proposing work out of
   sequence or bypassing approval and evaluation gates.
3. **Contributor:** needs milestone context before selecting an issue or
   proposing a change.
4. **Reviewer:** needs exit criteria and dependencies to decide whether a
   milestone is genuinely complete.
5. **Future evaluator:** needs to understand when RAG, memory, planner, and
   product behavior become measurable gates.

## Problem Statement

Travel Agent has a target direction, but the work is still easy to sequence
poorly. Implementing memory before evaluation, planner state before workspace
ownership, or production claims before security and operations would create
fragile software and misleading documentation.

The repository owner is also learning how to work like a senior AI engineer and
senior coder. Without a curriculum connected to the real roadmap, learning can
become scattered: reading architecture theory in one place, coding in another,
and using agents without a repeatable review discipline.

Package 4 must turn the project into a teaching system and execution system at
the same time: every milestone should say what to build, what to prove, what to
avoid, and what engineering capability the owner should practice.

## Goals

1. Create a master roadmap that orders product, architecture, evaluation,
   operations, and open-source work into reviewable milestones.
2. Connect every milestone to prerequisites, deliverables, exit gates, and
   expected evidence.
3. Preserve the current RAG prototype and future target architecture as
   separate concepts.
4. Make Package 5 evaluation, Package 6 security and operations, and Package 7
   open-source work visible without creating their files early.
5. Create an engineering curriculum tied to this repository rather than a
   generic course outline.
6. Teach senior judgment around specs, ADRs, test strategy, RAG quality,
   memory quality, privacy, observability, code review, GitHub workflow, and
   release discipline.
7. Give coding agents enough context to choose the next package or milestone
   without inventing hidden priorities.
8. Keep Package 4 documentation-only and reviewable.

## Non-goals

1. Package 4 does not implement runtime memory, trip workspaces, planner tools,
   authentication, storage, observability, security controls, or evaluation
   code.
2. It does not create Package 5 evaluation protocol files, Package 6 security
   or runbook files, or Package 7 GitHub and open-source files.
3. It does not create ADR files or accept durable architecture decisions.
4. It does not change source code, tests, dependencies, CI, Docker,
   environment files, local data, or generated artifacts.
5. It does not claim any milestone is complete unless previous repository
   evidence already proves it.
6. It does not define release notes or shipped-version history; that belongs to
   `CHANGELOG.md` in Package 7.
7. It does not replace approved specs, plans, ADRs, architecture documents, or
   future evaluation protocols.
8. It does not authorize Git staging, commit, push, PR creation, merge, or
   release.

## Assumptions

1. Package 4 will be implemented after this specification and a separate
   implementation plan are approved.
2. The roadmap should start from the current repository state: documentation
   packages are in progress, and runtime memory/workspace/planner features are
   not implemented.
3. The engineering curriculum should target the repository owner as the primary
   learner and assume they want practical project-based learning.
4. The roadmap should favor evaluation and safety gates before high-confidence
   product claims.
5. The curriculum should teach enough GitHub and project workflow to work
   professionally with coding agents and human review.
6. Package 4 documentation should remain stable even as future milestone specs
   add details.

If an assumption is invalidated during implementation, execution stops and
returns to specification review.

## User and System Flows

### Roadmap Planning Flow

1. A repository owner or coding agent opens `docs/roadmap/master-roadmap.md`.
2. The document states the current project phase and the next recommended
   milestone.
3. The reader checks milestone dependencies before proposing work.
4. The reader checks the milestone exit gate before claiming completion.
5. The reader follows links to specs, plans, architecture documents, ADR
   workflow, evaluation protocols, runbooks, or GitHub templates when those
   files exist.
6. If a referenced package is future work, the roadmap labels it as future
   rather than linking to a missing file.

### Learning Flow

1. The repository owner opens `docs/learning/engineering-curriculum.md`.
2. The curriculum presents learning tracks aligned with project milestones.
3. Each track explains the skill, why it matters in this repository, exercises
   to perform, and evidence that the skill has been practiced.
4. The owner uses milestone work, review questions, and retrospectives to learn
   by doing.
5. Coding agents can use the curriculum to explain trade-offs and teach while
   implementing future approved plans.

### Future Package Selection Flow

1. A reader asks what package or milestone should happen next.
2. The roadmap identifies the next unfinished package, its purpose, and the
   gate required before implementation.
3. The reader drafts the required spec instead of jumping directly to runtime
   changes.
4. The implementation plan for that future package records the exact files and
   verification commands.

## Behavioral and Data Contracts

Package 4 produces documentation contracts, not runtime contracts.

`docs/roadmap/master-roadmap.md` must contain:

1. A statement that the roadmap is planned work, not release history.
2. A current phase summary that distinguishes implemented prototype behavior
   from target architecture.
3. A milestone table with at least: milestone id, title, purpose, dependencies,
   deliverables, exit gate, and status.
4. A recommended order for Package 5, Package 6, Package 7, and later runtime
   implementation.
5. Runtime milestones for at least: foundation cleanup, RAG repair,
   evaluation, trip workspace, memory shadow mode, memory retrieval, planner,
   observability, security, and open-source readiness.
6. Explicit dependency rules that prevent memory or planner claims before
   evaluation and trace gates exist.
7. Review questions for milestone planning.
8. A rule that future milestone updates require the normal spec and plan
   workflow when they change priorities, gates, or architecture assumptions.

`docs/learning/engineering-curriculum.md` must contain:

1. A statement that the curriculum is for repository-owner learning through the
   Travel Agent project.
2. Learning tracks for at least: repository workflow, Git and GitHub, codebase
   reading, architecture design, testing, RAG, agent memory, evaluation,
   observability, security/privacy, product thinking, and release practice.
3. A mapping from learning tracks to roadmap milestones.
4. Exercises that use repository artifacts such as specs, plans, ADRs,
   architecture docs, tests, eval reports, review notes, and pull requests.
5. Quality rubrics that describe beginner, competent, and senior signals.
6. A weekly or milestone-based operating rhythm.
7. Reflection prompts for improving how the owner works with coding agents.
8. Explicit boundaries that the curriculum is educational guidance, not
   authorization to bypass approved specs, plans, or verification gates.

Root documents may link to Package 4 files only if the approved implementation
plan includes those routing edits. Package 4 must not create links to Package
5-7 files before those files exist.

## Errors and Edge Cases

1. If `docs/roadmap/` or `docs/learning/` does not exist, the implementation
   may create only the directory needed for the approved file.
2. If a future package file does not exist, Package 4 must name it as future
   work in prose and must not create a broken Markdown link.
3. If current repository status includes unrelated untracked files from earlier
   accepted packages, Package 4 final verification must disclose that status
   instead of deleting or modifying those files.
4. If roadmap sequencing conflicts with an approved architecture document, the
   implementation stops and returns to spec review.
5. If the curriculum starts prescribing unapproved runtime changes, it must be
   rewritten as learning guidance or moved to a future approved spec.
6. If a milestone cannot be evaluated yet, the roadmap must say which future
   package or gate will define its evaluation method.

## Security and Privacy

Package 4 must preserve security and privacy boundaries:

1. Do not include real credentials, tokens, private account data, or sensitive
   user details.
2. Do not claim authentication, authorization, deletion semantics, tenant
   isolation, incident response, or production privacy guarantees are
   implemented.
3. Treat memory, traces, and user profile examples as conceptual examples, not
   real user data.
4. Keep Package 6 as the owner of security policy and operational runbooks.
5. Teach privacy and sensitive-memory judgment in the curriculum without
   defining final legal or security policy.

## Observability and Operations

Package 4 adds no runtime observability or operations behavior. It may define
future milestone gates requiring:

1. Trace capture for RAG, memory, planner, and user-correction flows.
2. Evaluation result interpretation before feature promotion.
3. Operational runbooks before production-style claims.
4. Review of technical debt, architecture drift, and quality regressions at
   milestone boundaries.

Operational procedures themselves remain Package 6 scope.

## Testing and Evaluation

Package 4 verification is deterministic documentation review:

1. Confirm the spec and plan indexes contain accurate Package 4 entries.
2. Confirm `docs/roadmap/master-roadmap.md` and
   `docs/learning/engineering-curriculum.md` exist only after implementation
   plan approval.
3. Check all local Markdown links resolve.
4. Search for unsupported implementation, production, security, license, CI,
   test, evaluation, memory, workspace, authentication, tenant-isolation, and
   SLO claims.
5. Search for drafting markers, placeholders, and trailing whitespace.
6. Check Markdown fenced-code block balance.
7. Read the full roadmap and curriculum before completion.
8. Compare the change set with the approved scope, including untracked files.

Package 4 does not run application tests, Docker, dependency installation,
model downloads, crawling, indexing, external model calls, or evaluation jobs.

## Rollout and Migration

Package 4 rolls out as one documentation review unit:

1. Approve this specification.
2. Prepare and approve a Package 4 implementation plan.
3. Create `docs/roadmap/master-roadmap.md`.
4. Create `docs/learning/engineering-curriculum.md`.
5. Apply approved routing or traceability updates only if the plan includes
   them.
6. Run deterministic documentation verification.
7. Record completion and repository-owner change-set review.

No data migration, runtime rollout, feature flag, or production deployment is
in scope.

## Rollback

Before Git delivery, rollback removes only:

1. `docs/roadmap/master-roadmap.md`.
2. `docs/learning/engineering-curriculum.md`.
3. Package 4 traceability edits in `docs/specs/README.md`.
4. Package 4 plan traceability edits in `docs/plans/README.md` if created by
   the implementation plan.
5. The Package 4 implementation plan if it was created.

Rollback must not touch accepted Package 0-3 files except Package 4
traceability fields explicitly added by the approved plan.

## Acceptance Criteria

Package 4 implementation is acceptable only when:

1. `docs/roadmap/master-roadmap.md` exists and is the canonical roadmap.
2. `docs/learning/engineering-curriculum.md` exists and is the canonical
   repository-owner engineering curriculum.
3. The roadmap separates current state, planned work, future packages, runtime
   milestones, and shipped outcomes.
4. The roadmap defines milestone dependencies, deliverables, statuses, and exit
   gates.
5. The roadmap makes evaluation gates prerequisites for memory, planner, and
   quality-improvement claims.
6. The curriculum maps senior AI engineering and senior software engineering
   skills to Travel Agent milestones.
7. The curriculum includes practical exercises, evidence requirements, and
   review rubrics.
8. The curriculum teaches coding-agent collaboration without bypassing specs,
   plans, verification, or repository-owner approval.
9. Package 4 creates no Package 5, Package 6, Package 7, runtime source,
   dependency, CI, Docker, environment, data, migration, or Git delivery
   changes.
10. All local Markdown links resolve.
11. Drafting-marker, trailing-whitespace, and fence-balance checks pass.
12. Unsupported-claim scans contain no unqualified implementation,
    production-readiness, security, privacy, CI, test, evaluation, memory,
    workspace, authentication, tenant-isolation, SLO, license, or release
    claims.
13. The Package 4 spec index row, implementation plan row, plan completion
    record, and repository-owner change-set review status match actual
    execution.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-08-31 via the exact
conversation phrase `Approve Package 4 spec version 0.1`. Approval authorizes
preparation of a Package 4 implementation plan only. It does not authorize
creating the roadmap or curriculum files, runtime changes, source changes,
dependency changes, CI changes, data operations, Git staging, commit, push, PR,
merge, or release.
