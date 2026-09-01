# Implementation Plans

## Purpose and Prerequisite

An implementation plan translates one exact, approved specification into
ordered tasks with reviewable outputs and fresh verification evidence. Planning
does not reopen an approved design. If implementation requires a different
contract, boundary, or assumption, return to specification review first.

Every plan links its approved specification and version. Execution starts only
after the repository owner approves the exact plan.

## Lifecycle

```text
Draft -> In Review -> Approved -> In Progress -> Completed
                                      |
                                      -> Superseded
```

- `Draft`: authoring is incomplete.
- `In Review`: tasks and evidence are ready for an approval decision.
- `Approved`: the repository owner approved the recorded plan.
- `In Progress`: approved tasks are being executed.
- `Completed`: tasks passed verification; delivery or release may still remain.
- `Superseded`: a newer approved plan replaces it.

## Naming and Metadata

Use:

```text
docs/plans/YYYY-MM-DD-kebab-case-implementation.md
```

Every plan records:

| Field | Required value |
| --- | --- |
| Status | One lifecycle value |
| Date | ISO date |
| Approved specification | Exact path and approved version |
| Execution owner | Role performing approved tasks |
| Decision owner | Role approving the plan and resulting repository change set |
| Scope | Bounded implementation outcome |
| Verification | Exact commands and review methods |

## File Responsibility Map

Before tasks, map every created or modified file to one responsibility and its
dependencies. Files that change together should live together; unrelated work
does not enter the plan. The map is the boundary used during final scope review.

Use:

```markdown
| File | Responsibility | Depends on |
| --- | --- | --- |
| `[Exact path]` | [One responsibility] | [Inputs or earlier tasks] |
```

## Task Design Rules

1. Each task produces an independently reviewable result.
2. Name exact create, modify, read, and test paths.
3. Declare what the task consumes and what later tasks receive.
4. Declare exact interfaces between dependent code tasks.
5. Use test-first steps for behavior changes.
6. Use deterministic checks for documentation-only changes.
7. Include exact commands and expected outcomes.
8. Include documentation, migration, observability, and rollback when relevant.
9. Stop when evidence invalidates an approved assumption or expands scope.
10. End every task with an explicit review checkpoint.
11. Keep Git delivery actions under repository-owner control.

## Implementation Plan Template

Bracketed tokens below are intentional author inputs.

```markdown
# [Change Name] Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence.

**Goal:** [One observable outcome]

**Architecture:** [Approved approach and boundaries]

**Tech Stack:** [Relevant tools and frameworks]

**Spec:** [Approved spec path and version]

| Field | Value |
| --- | --- |
| Status | Draft |
| Date | [YYYY-MM-DD] |
| Approved specification | [Path and version] |
| Execution owner | [Role] |
| Decision owner | Repository owner |
| Scope | [Bounded implementation] |
| Verification | [Commands and review methods] |

## Global Constraints

1. [Exact project-wide constraint copied from the spec]

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `[Exact path]` | [One responsibility] | [Input] |

## Task 1: [Independently Reviewable Result]

**Files:**

- Create: `[Exact path]`
- Modify: `[Exact path and relevant location]`
- Test: `[Exact path]`

**Interfaces:**

- Consumes: [Exact input]
- Produces: [Exact output or signature]

- [ ] **Step 1: [One action]**

[Exact content or implementation instruction]

- [ ] **Step 2: Run verification**

Run: `[Exact command]`

Expected: [Observable result and exit condition]

- [ ] **Step 3: Review checkpoint**

Review: [Exact task output, evidence, and interfaces to inspect]

Expected: [Condition required before the next task begins]

## Package Verification

[Scope, tests, link checks, builds, scenarios, and evidence report]

## Rollback

[Safe recovery that preserves unrelated work and history]

## Completion Record

[Approval, execution, verification, and remaining delivery gate]
```

## Execution and Stop Conditions

Execute tasks in dependency order and update checkbox state as evidence. Stop
and return to the repository owner when:

1. The governing spec or plan is not approved.
2. A required dependency, interface, or assumption differs from the plan.
3. Scope expands or a new architecture decision appears.
4. Required verification fails or cannot run and the approved steps do not
   resolve it.
5. The change risks overwriting unrelated work.
6. Rollback is no longer safe.

The repository owner creates or selects branches and decides when to stage,
commit, push, open a PR, merge, and release.

## Self-review Checklist

- [ ] Every spec requirement maps to a task.
- [ ] Every file has one stated responsibility.
- [ ] Tasks declare exact paths, inputs, outputs, and order.
- [ ] Code names and interfaces remain consistent across tasks.
- [ ] Behavior changes use a red-green-refactor test cycle.
- [ ] Commands and expected outcomes are concrete.
- [ ] Security, migration, observability, documentation, and rollback are covered
      where applicable.
- [ ] No deferred requirement or hidden scope remains.
- [ ] Final verification compares the result with the approved spec.
- [ ] Git delivery actions remain with the repository owner.

## Plan Index

| Date | Title | Governing spec | Status | Path |
| --- | --- | --- | --- | --- |
| 2026-08-30 | Agent Operating System Implementation Plan | [Agent Operating System Design](../specs/2026-08-30-agent-operating-system-design.md) v0.1 | Completed | [Plan](./2026-08-30-agent-operating-system-implementation.md) |
| 2026-08-31 | Project Entry Points Implementation Plan | [Project Entry Points Design](../specs/2026-08-31-project-entry-points-design.md) v0.1 | Completed | [Plan](./2026-08-31-project-entry-points-implementation.md) |
| 2026-08-31 | Architecture Baseline Implementation Plan | [Architecture Baseline Design](../specs/2026-08-31-architecture-baseline-design.md) v0.1 | Completed | [Plan](./2026-08-31-architecture-baseline-implementation.md) |
| 2026-08-31 | Roadmap and Learning Implementation Plan | [Roadmap and Learning Design](../specs/2026-08-31-roadmap-and-learning-design.md) v0.1 | Completed | [Plan](./2026-08-31-roadmap-and-learning-implementation.md) |
| 2026-08-31 | Evaluation Protocols Implementation Plan | [Evaluation Protocols Design](../specs/2026-08-31-evaluation-protocols-design.md) v0.1 | Completed | [Plan](./2026-08-31-evaluation-protocols-implementation.md) |
| 2026-08-31 | Operations and Security Implementation Plan | [Operations and Security Design](../specs/2026-08-31-operations-and-security-design.md) v0.1 | Completed | [Plan](./2026-08-31-operations-and-security-implementation.md) |
| 2026-08-31 | GitHub and Open Source Implementation Plan | [GitHub and Open Source Design](../specs/2026-08-31-github-and-open-source-design.md) v0.1 | Completed | [Plan](./2026-08-31-github-and-open-source-implementation.md) |
| 2026-09-01 | Foundation Cleanup Implementation Plan | [Foundation Cleanup Design](../specs/2026-09-01-foundation-cleanup-design.md) v0.1 | Completed | [Plan](./2026-09-01-foundation-cleanup-implementation.md) |
