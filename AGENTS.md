# Repository Agent Instructions

## Mission

Keep Travel Agent understandable, evidence-backed, and small. Prefer simple
changes over process ceremony while preserving security and correctness.

## Source of Truth

Use, in order:

1. the repository owner's current request;
2. this file;
3. `docs/architecture/current-state.md`, `target-state.md`, and `data-model.md`;
4. source code, migrations, tests, configuration, and fresh tool output.

Historical specs, plans, and ADR collections are not active governance. Living
architecture decisions belong in the canonical architecture documents.

## Workflow

Scale process to the change:

- Small change: inspect -> implement -> verify -> owner review.
- Medium feature: state problem/scope/checks -> owner approval -> implement -> verify.
- Architecture change: update the relevant canonical architecture document ->
  owner approval -> implement -> verify.

Do not create a new document when an existing canonical document can own the
decision.

## Canonical Documentation

- `docs/architecture/current-state.md`: implemented runtime.
- `docs/architecture/target-state.md`: intended architecture.
- `docs/architecture/data-model.md`: conceptual data model.
- `docs/roadmap/master-roadmap.md`: remaining work.
- `DEVELOPMENT.md`: local setup and commands.
- `SECURITY.md`: security and privacy.
- `CONTRIBUTING.md`: contribution and Git workflow.

## Engineering Rules

1. Read the affected flow before editing it.
2. Prefer deletion/simplification over speculative abstractions.
3. Keep an abstraction only when it protects a real invariant or removes real
   duplication.
4. Never simplify away tenant isolation, validation, deletion semantics,
   idempotency, stale-worker fencing, or other correctness/security invariants.
5. Keep Memory and RAG authority separate unless architecture explicitly changes.
6. Preserve unrelated user changes.
7. Never expose credentials, secrets, or sensitive user content.

## Git and Verification

Do not stage, commit, push, merge, rewrite history, or release unless the owner
explicitly requests that Git action. Verify changed behavior freshly, inspect
`git status --short --untracked-files=all` and the final diff, and report what
was and was not verified. Local tests alone do not prove production readiness.
