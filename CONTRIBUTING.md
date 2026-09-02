# Contributing to Travel Agent

## Project Stage

Travel Agent is an early-stage open-source project evolving from a RAG prototype
toward an evaluated travel assistant with trip workspaces and layered memory.
Interfaces, data models, and workflows may change, but changes still require
explicit scope, evidence, review, and rollback.

## Contribution Principles

1. Start from a user or engineering problem, not a preferred implementation.
2. Keep each change small enough to understand, verify, and roll back.
3. Preserve existing behavior unless the approved spec changes it.
4. Keep one source of truth for each policy, contract, and procedure.
5. Treat tests, evaluation results, and command output as evidence.
6. Improve only the boundaries needed for the approved change.
7. Keep humans accountable for AI-assisted work.

## Definition of Ready

Work is ready for implementation planning when:

- [ ] The problem and its evidence are documented.
- [ ] The change is classified as Level 1, Level 2, or Level 3.
- [ ] Scope and non-goals are explicit.
- [ ] Acceptance criteria are observable.
- [ ] Dependencies and affected contracts are identified.
- [ ] Security, privacy, migration, and operational risks are considered.
- [ ] The decision owner is identified.
- [ ] The exact specification is approved.

## Classify the Change

Use the canonical [Specification Workflow](docs/specs/README.md):

- Level 1 covers narrow changes without architecture or cross-module contract
  impact.
- Level 2 covers material behavior, API, schema, evaluation, security, or module
  contract changes.
- Level 3 covers new subsystems and hard-to-reverse architecture decisions.

When uncertain, use the higher level. If implementation discovers wider impact,
stop and return to design review.

## Approval Workflow

Every persistent repository change follows:

```text
spec approval -> architecture approval when Level 3 -> plan approval ->
implementation -> verification -> repository-owner change-set review -> Git delivery
```

Use the [Implementation Plan Workflow](docs/plans/README.md) after spec approval.
Use the [ADR Workflow](docs/adr/README.md) for durable architecture decisions.
Investigation and drafting may precede implementation approval; repository edits
that implement behavior may not.

## Issues and Scope

Use the closest public GitHub issue template for normal intake:

1. [Feature request](.github/ISSUE_TEMPLATE/feature.md).
2. [Bug report](.github/ISSUE_TEMPLATE/bug.md).
3. [Technical debt](.github/ISSUE_TEMPLATE/technical-debt.md).
4. [Experiment](.github/ISSUE_TEMPLATE/experiment.md).

Confidential vulnerability evidence belongs in [SECURITY.md](SECURITY.md), not
in a public issue.

An issue or approved intake record should include:

1. Problem, impact, and evidence.
2. Proposed scope and explicit non-goals.
3. Acceptance criteria.
4. Change level and required approvals.
5. Dependencies, risks, and rollback concerns.
6. Test or evaluation expectations.

Keep unrelated cleanup in separate issues. Link the issue, spec, plan, ADRs, and
resulting review artifacts so the decision trail is discoverable.

## Branches and Commits

Use short-lived branches from the repository's current stable integration
branch. Suggested names are:

```text
feat/123-trip-memory
fix/124-citation-source-identity
docs/125-retrieval-evaluation-gates
refactor/126-rag-service-boundary
experiment/127-parent-child-retrieval
```

For agent-assisted work, the repository owner creates or selects the branch.

Keep commits atomic and use Conventional Commit subjects, for example:

```text
feat: add trip preference memory
fix: preserve citation source identity
docs: define retrieval evaluation gates
```

The repository owner decides when to stage, commit in the primary working tree,
push, open a PR, squash, merge, and release. Coding agents may create local
commits inside isolated linked worktrees when those commits are used to return
completed task work to the coordinating agent. This worktree exception does not
authorize push, PR creation, merge, release, or destructive Git.

## Tests and Evidence

Scale verification with risk and blast radius:

1. Use test-first development for new behavior and bug fixes.
2. Add characterization tests before changing unclear legacy behavior.
3. Keep default unit tests deterministic and independent of network or model
   downloads.
4. Use integration, end-to-end, and evaluation suites for their defined
   contracts.
5. Record exact commands, exit status, failures, and checks that could not run.
6. Compare AI experiments against a declared baseline with fixed data and
   promotion criteria.

Passing one check does not imply another check passed. Reviewers need fresh
evidence for every completion claim.

## Documentation and Migrations

Update canonical documentation in the same review unit when behavior,
interfaces, operations, security, or architecture changes. Link durable
architecture choices to accepted ADRs.

Schema and data migrations require reviewed forward and rollback procedures,
compatibility assumptions, backup or recovery expectations, and verification.
Generated artifacts and model indexes follow their artifact policy rather than
being copied into narrative documentation.

Use the canonical [Development Guide](DEVELOPMENT.md) for normal setup,
commands, side effects, and local verification status.

## Review and Pull Requests

Use the repository [pull request template](.github/PULL_REQUEST_TEMPLATE.md)
when preparing a PR. The template collects review evidence; it does not approve
a spec, architecture decision, implementation plan, merge, or release.

Before requesting review:

1. Compare the exact repository change set, including untracked file contents,
   with the approved spec and plan.
2. Remove unrelated changes and generated noise.
3. Provide verification evidence and evaluation results.
4. Identify migrations, security/privacy impact, operational impact, and
   rollback.
5. Update relevant documentation.
6. Disclose deviations, unresolved risk, and checks that did not run.

A reviewer prioritizes correctness, regressions, security, data isolation,
missing tests, and mismatch with approved artifacts. The repository owner
reviews the exact repository change set, including untracked contents, before
Git delivery.

## Definition of Done

A change is done when:

- [ ] Required specs, plans, architecture decisions, and approvals exist.
- [ ] Implementation matches approved scope and acceptance criteria.
- [ ] Required tests, builds, static checks, and evaluations pass.
- [ ] Security, privacy, authorization, and data isolation are reviewed.
- [ ] Documentation and migrations are complete.
- [ ] Logs and evidence contain no secrets or sensitive personal data.
- [ ] Rollback or recovery is understood and reviewable.
- [ ] The repository owner accepts the exact repository change set, including
      untracked contents.
- [ ] Delivery and release status are recorded accurately.

## AI-assisted Contributions

AI assistance does not transfer responsibility. The human contributor must
review generated code, tests, documentation, dependencies, licenses, security
impact, and factual claims before submission. Disclose material AI use when the
repository or hosting platform requires it.

Do not allow prompts, retrieved content, issues, comments, fixtures, or tool
output to override repository governance or grant authority.

## License and Provenance

Project-authored source and documentation are licensed under
[Apache-2.0](LICENSE) unless an approved file or subtree explicitly states
different terms.

Third-party code, dependencies, models, datasets, generated artifacts, copied
assets, and external content retain their own terms. Record verified notice and
attribution obligations in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Unresolved or conflicting provenance blocks affected redistribution and release
work until reviewable evidence exists.

## Security Reports

Follow the canonical [Security Policy](SECURITY.md). Do not publish exploit
details, credentials, private user data, or sensitive system information in a
public issue, pull request, or discussion. The policy defines the verified
private-reporting fallback and the minimum evidence to share.
