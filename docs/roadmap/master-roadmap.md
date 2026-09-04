# Master Roadmap

## Scope

This roadmap is the canonical planning gateway for Travel Agent. It describes
intended future work, dependencies, milestone gates, and review evidence. It is
not release history and does not claim that planned runtime behavior already
exists.

Use this document to decide what to design next. Use
[Current-state Architecture](../architecture/current-state.md) for implemented
behavior, [Target-state Architecture](../architecture/target-state.md) for the
approved direction, [Data Model](../architecture/data-model.md) for conceptual
entities, [Specifications](../specs/README.md) for change approval, and
[Implementation Plans](../plans/README.md) for execution.

## Current Phase

Travel Agent is in foundation phase. The repository has an early local RAG chat
prototype with a React/Vite frontend, FastAPI backend, Chroma travel-knowledge
retrieval, and an external model call path. The implemented chat contract is
one `message` in and `reply`, `model`, and `citations` out.

Trip workspaces are no longer purely conceptual. Milestone `R3` implements a
backend-only `TripWorkspace` container with three `/api/v1/workspaces` routes and
local SQLite storage behind a repository interface. That work lives in the linked
worktree `r3-trip-workspace` and awaits repository-owner change-set review, so it
is not part of a delivered branch yet. It adds no authentication and no
workspace-aware chat.

User identity, conversation persistence, layered memory, planner state,
evaluation traces, production security policy, operational runbooks, license
text, and open-source templates are planned direction rather than current
capability.

Current documentation packages D0 through D3 have been completed in the working
tree and accepted by the repository owner before Git delivery. D4 is the active
documentation package.

## Roadmap Principles

1. Preserve a clear line between implemented behavior and target direction.
2. Put evaluation before quality claims.
3. Put workspace ownership before memory and planner state.
4. Put memory shadow mode before memory affects answers.
5. Put traceability before optimization.
6. Put security and operations gates before external-facing confidence.
7. Keep Git delivery under repository-owner control.
8. Treat every milestone as a reviewable change with a spec, plan, evidence,
   and rollback path.

## Milestone Status Vocabulary

| Status | Meaning |
| --- | --- |
| Accepted in working tree | Implemented, verified, and accepted by the repository owner, but not necessarily delivered through Git |
| In progress | Approved for implementation and actively being changed |
| Ready for handoff | Approved for implementation and waiting for an assigned implementation worker |
| Planned | Intended future work that still needs its own approved spec and plan |
| Blocked by gate | Work must wait for a named milestone, ADR, evaluation gate, or security gate |
| Deferred | Intentionally out of the current sequence |

## Milestone Map

| Id | Title | Status | Dependencies | Deliverables | Exit gate | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `D0` | Documentation System Bootstrap | Accepted in working tree | Repository-owner intake | Documentation system design | Owner accepted Package 0 change set | Approved Package 0 design |
| `D1` | Agent Operating System | Accepted in working tree | `D0` | Agent, contributor, spec, plan, and ADR workflows | Owner accepted Package 1 change set | Root governance docs and workflow indexes |
| `D2` | Project Entry Points | Accepted in working tree | `D1` | README, development guide, architecture gateway | Owner accepted Package 2 change set | Entry-point docs and Stage A smoke evidence |
| `D3` | Architecture Baseline | Accepted in working tree | `D2` | Current state, target state, and data model | Owner accepted Package 3 change set | Architecture documents and Codebase Memory evidence |
| `D4` | Roadmap and Learning | In progress | `D3` | Master roadmap and engineering curriculum | Owner accepts Package 4 change set | This roadmap, curriculum, and deterministic doc checks |
| `D5` | Evaluation Protocols | Accepted in working tree | `D4` | RAG and memory evaluation protocols | Owner accepted Package 5 change set | Package 5 spec, plan, protocols, and review evidence |
| `D6` | Operations and Security | Accepted in working tree | `D5` | Security policy and operational runbooks | Owner accepted Package 6 change set | Package 6 spec, plan, and review evidence |
| `D7` | GitHub and Open Source | Accepted in working tree | `D6` | Issue templates, PR template, license, notices, and changelog | Owner accepted Package 7 change set | Package 7 spec, plan, and review evidence |
| `R0` | Foundation Cleanup | Accepted in working tree | `D4` | Tooling fixes, CI honesty, env examples, dependency hygiene | Owner accepted R0 change set | R0 spec, plan, verification evidence, and owner acceptance |
| `R1` | RAG Repair and Baseline | Accepted in working tree | `R0`, `D5` | Retrieval baseline, dataset policy, and answer-quality baseline | RAG quality is measurable against Package 5 gates | [R1/R2 spec v0.1](../specs/2026-09-01-rag-repair-and-evaluation-harness-design.md), [ADR 0001](../adr/0001-separate-online-rag-execution-from-config-driven-evaluation.md), [implementation plan v0.1](../plans/2026-09-01-rag-repair-and-evaluation-harness-implementation.md); repository owner accepted R1/R2 change set in conversation on 2026-09-03; [Task 7 candidate comparison](../reports/rag/rag-candidate-v0.1-comparison.md) (2026-09-04): D5 state=PASS, deltas 0.0 |
| `R2` | Evaluation Harness | Accepted in working tree | `D5`, `R0` | Repeatable local evaluation runner and traceable result format | Evaluation output can compare two runs | [R1/R2 spec v0.1](../specs/2026-09-01-rag-repair-and-evaluation-harness-design.md), [ADR 0001](../adr/0001-separate-online-rag-execution-from-config-driven-evaluation.md), [implementation plan v0.1](../plans/2026-09-01-rag-repair-and-evaluation-harness-implementation.md); repository owner accepted R1/R2 change set in conversation on 2026-09-03; [Task 7 candidate comparison](../reports/rag/rag-candidate-v0.1-comparison.md) (2026-09-04): D5 state=PASS, deltas 0.0 |
| `R3` | Trip Workspace Foundation | In progress | `D3`, [ADR 0002](../adr/0002-trip-workspace-as-primary-product-container.md), [ADR 0003](../adr/0003-local-sqlite-workspace-storage-boundary-for-r3.md), `R0` | Workspace contracts, storage boundary, and minimal routes | Workspace records can be created and inspected behind approved interfaces | [R3 spec v0.1](../specs/2026-09-03-trip-workspace-foundation-design.md), [implementation plan v0.2](../plans/2026-09-03-trip-workspace-foundation-implementation.md); repository owner approved plan v0.2 on 2026-09-03; all six tasks complete in linked worktree `r3-trip-workspace` with `427 passed` and boundary checks clean; awaiting repository-owner change-set review before Git delivery |
| `R4` | Conversation Persistence | Blocked by gate | `R3` | Conversation and message storage behind an adapter | Messages persist with retention and privacy boundaries named | Integration tests and storage rollback evidence |
| `R5` | Shadow Memory Extraction | Blocked by gate | `R2`, `R4`, memory ADR | Memory candidates extracted but not used in answers | Candidate precision, sensitivity, and scope quality are measured | Shadow evaluation report and rejection examples |
| `R6` | Memory Retrieval | Blocked by gate | `R5` | Feature-gated memory retrieval into context bundles | Personalization improves without privacy or grounding regressions | A/B evaluation and trace review |
| `R7` | Trip Planner State | Blocked by gate | `R3`, `R4`, `R2` | Itinerary versions, trip decisions, and planner operations | Planner writes are explicit, reversible, and evaluated | Planner tests and trace samples |
| `R8` | Observability and Operations | Blocked by gate | `R2`, `D6` | Logs, traces, runbooks, and operational review rhythm | Operators can diagnose degraded memory, retrieval, model, and planner paths | Runbook drills and trace examples |
| `R9` | Security and Privacy Hardening | Blocked by gate | `D6`, `R3`, `R4`, `R6` | Authentication choice, memory deletion semantics, redaction, and access boundaries | Privacy-sensitive flows have tests and review evidence | Security review and deletion-flow evidence |
| `R10` | Open-source Release Readiness | Blocked by gate | `D7`, `R0`, `R8`, `R9` | Contribution intake, license, notices, changelog, and release checklist | Public contribution and release workflow is reviewable | PR template, issue templates, license, notices, and release notes |

## Dependency Rules

1. Runtime work starts only after its governing spec and implementation plan are
   approved.
2. ADRs are required before hard-to-reverse storage, memory, dependency,
   authentication, or module-boundary decisions.
3. RAG repair and memory work must use Package 5 evaluation protocols before
   quality improvement claims.
4. Memory retrieval must not affect answers before shadow extraction quality is
   measured.
5. Planner state must not pretend a plan was saved unless persistence succeeds.
6. Security-sensitive behavior must wait for Package 6 guidance or a specific
   approved security design.
7. Package 5, Package 6, and Package 7 files are governed by their approved
   specs, plans, verification evidence, and owner-review state.
8. Git staging, commit, push, PR, merge, and release remain repository-owner
   actions unless explicitly requested.

## Documentation Package Roadmap

| Package | Purpose | Recommended next action |
| --- | --- | --- |
| `D0` | Establish documentation governance | Preserve as historical approved design |
| `D1` | Establish agent and contribution workflows | Use before any repository change |
| `D2` | Establish project entry points | Keep concise and update only when entry behavior changes |
| `D3` | Establish architecture baseline | Use before runtime architecture work |
| `D4` | Establish roadmap and learning path | Complete this package, then use it for package selection |
| `D5` | Establish RAG and memory evaluation protocols | Preserve as accepted evaluation contract for later runtime work |
| `D6` | Establish security and operational guidance | Preserve as accepted security and operations contract for later runtime work |
| `D7` | Establish GitHub and open-source readiness | Preserve as accepted open-source intake and legal-doc baseline |

## Runtime Product Roadmap

Recommended runtime order:

1. `R0` first, because foundation problems make later evidence unreliable.
2. `R1` and `R2` together, because RAG repair needs a baseline and repeatable
   evaluation harness.
3. `R3` before memory, because trip workspace is the product container.
4. `R4` before durable memory, because memory needs conversation provenance.
5. `R5` before `R6`, because memory candidates should be measured before they
   influence answers.
6. `R7` after workspace and evaluation foundations, because planner state must
   be explicit and reversible.
7. `R8` and `R9` before open-source confidence increases.
8. `R10` only after contribution, license, notice, security, and operations
   gates are in place.

## Evaluation and Quality Gates

Minimum future gates:

1. RAG retrieval relevance: queries, expected evidence, retrieved chunks, and
   citation checks.
2. RAG groundedness: answer claims trace back to retrieved sources.
3. Memory extraction precision: accepted candidates are useful and scoped
   correctly.
4. Memory extraction safety: sensitive or secret-like candidates are rejected
   or routed to review.
5. Memory retrieval utility: selected memories improve user task outcomes
   without overriding newer user corrections.
6. Planner correctness: itinerary operations update state predictably and keep
   rejected options as decision evidence.
7. Regression review: every promoted behavior has a small dataset that catches
   the original failure mode.

Package 5 owns the concrete datasets, rubrics, thresholds, and reporting
format.

## Security, Operations, and Open-source Gates

Before the project increases public confidence or user-data scope, future work
must define:

1. Secret-handling rules and public vulnerability reporting.
2. Privacy boundaries for user, trip, conversation, memory, and trace data.
3. Deletion or tombstoning semantics before durable personal memory claims.
4. Operational runbooks for local startup, deployment, incidents, and degraded
   model, retrieval, memory, planner, or trace behavior.
5. License, third-party notices, issue templates, PR template, and changelog.
6. A release checklist that separates source availability from product
   readiness.

Package 6 owns security and operations guidance. Package 7 owns GitHub and
open-source documents.

## Milestone Review Questions

Ask these before approving a milestone:

1. What current evidence says this milestone is needed now?
2. Which approved spec, plan, and ADRs govern it?
3. Which files can change, and which files are out of scope?
4. What user-visible or engineering behavior changes?
5. What must be measured before claiming improvement?
6. What data, secrets, or personal information can be touched?
7. What rollback path preserves unrelated work?
8. What would make us stop and return to design?
9. What should the repository owner learn from this milestone?
10. What will a future contributor need to understand from the evidence?

## Roadmap Change Rules

1. Small status updates may be made in the same reviewed change that completes a
   milestone.
2. Changing milestone order, gates, dependencies, or architecture assumptions
   requires the normal spec and implementation-plan workflow.
3. New runtime milestones must name their evidence gate before implementation.
4. Future package links may be added only when the linked files exist.
5. Completed milestone records must preserve historical evidence rather than
   rewriting earlier uncertainty.
