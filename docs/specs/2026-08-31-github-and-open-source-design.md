# GitHub and Open Source Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-08-31 |
| Change class | Level 2 - Feature Spec |
| Decision owner | Repository owner |
| Scope | Documentation Package 7 - GitHub intake/review templates, source license, third-party notices, and changelog |
| Parent design | [Documentation System Design](./2026-08-30-documentation-system-design.md), version 0.1 |
| Depends on | [Agent Operating System Design](./2026-08-30-agent-operating-system-design.md), version 0.1; [Project Entry Points Design](./2026-08-31-project-entry-points-design.md), version 0.1; [Operations and Security Design](./2026-08-31-operations-and-security-design.md), version 0.1 |
| Implementation plan | [GitHub and Open Source Implementation Plan](../plans/2026-08-31-github-and-open-source-implementation.md), version 0.1 (Completed; owner change set accepted) |
| Implementation state | Accepted in working tree; Git delivery not authorized |
| Related issue | None - Package 7 work was requested by the repository owner in this conversation |
| Superseded document | None |

## Summary

Package 7 establishes the repository's first reviewable open-source intake and
legal-document baseline. It will create eight canonical artifacts:

1. `.github/PULL_REQUEST_TEMPLATE.md`
2. `.github/ISSUE_TEMPLATE/feature.md`
3. `.github/ISSUE_TEMPLATE/bug.md`
4. `.github/ISSUE_TEMPLATE/technical-debt.md`
5. `.github/ISSUE_TEMPLATE/experiment.md`
6. `LICENSE`
7. `THIRD_PARTY_NOTICES.md`
8. `CHANGELOG.md`

The selected approach is a lightweight permissive open-source foundation. The
project source license will be Apache License 2.0 (`Apache-2.0`). GitHub
templates will collect evidence and route work into the existing spec, plan,
ADR, security, evaluation, and owner-review workflows. Third-party notices will
record verified attribution obligations without pretending to be a dependency
lockfile or complete software bill of materials. The changelog will record only
released outcomes and will not duplicate the roadmap.

Package 7 is documentation and repository-intake work only. It does not change
runtime behavior, dependencies, CI behavior, GitHub repository settings,
branch protection, release automation, deployment, data, Git state, or hosting
configuration.

Approval of version 0.1 authorizes preparation of the Package 7 implementation
plan only. It does not authorize creation of the eight Package 7 artifacts or
any Git, GitHub-platform, runtime, dependency, data, or release action.

## Current-state Evidence

Package 7 current-state claims are based on direct repository reads because its
primary evidence is documentation, configuration, manifests, and repository
metadata rather than structural code relationships.

| Evidence | Current fact relevant to Package 7 |
| --- | --- |
| [Documentation System Design](./2026-08-30-documentation-system-design.md) | Assigns Package 7 ownership of GitHub templates, `LICENSE`, `THIRD_PARTY_NOTICES.md`, and `CHANGELOG.md`; separates roadmap intent from released changelog history. |
| [README](../../README.md) | Describes the repository as open source but explicitly states that current documentation does not yet claim a source license or release process and delegates those artifacts to Package 7. |
| [Contributing Guide](../../CONTRIBUTING.md) | Already defines issue content, change classification, approval gates, review evidence, Git ownership, and the rule that GitHub intake does not itself authorize implementation. |
| [Security Policy](../../SECURITY.md) | Requires vulnerability details, credentials, private user data, and sensitive evidence to stay out of public issues and pull requests. |
| [Master Roadmap](../roadmap/master-roadmap.md) | `D7` is planned after accepted `D6`; later `R10` owns full open-source release readiness and release-checklist evidence. |
| `.github/workflows/ci.yml` | A CI workflow exists, but backend and frontend test commands can be converted into successful workflow steps with `|| echo`; Package 7 must not use CI existence as proof of test quality or release readiness. |
| `requirements.txt` and `backend/requirements.txt` | Python dependencies are declared as version ranges rather than a reproducible lockfile, so an exact transitive license inventory cannot be inferred from these files alone. |
| `frontend/package.json` and `frontend/package-lock.json` | Frontend direct dependencies and a resolved npm graph exist; license/notice obligations still require evidence review rather than assumption. |
| `.gitignore` and `data/` | Local processed travel data and Chroma state are ignored; a root source-code license must not silently claim rights over third-party datasets, models, or generated local data. |

At the start of Package 7 design, the only tracked `.github` artifact is the CI
workflow. The four issue templates, PR template, root license, third-party
notice file, and changelog do not yet exist.

## Context

Travel Agent is moving from a local RAG prototype toward a production-oriented
travel agent with trip workspaces, persistence, memory, planning, evaluation,
and stronger operations. The repository already has governance for
specification, implementation planning, architecture decisions, contribution,
security, and evidence, but a public contributor currently has no structured
GitHub intake path and a reviewer has no PR checklist that reflects those
contracts.

The repository also calls itself open source before a source license exists.
Without an explicit license, source availability alone does not provide clear
reuse rights. Future releases can also accumulate third-party code, models,
datasets, generated artifacts, and dependency notices that need provenance and
attribution review.

Package 7 closes this documentation gap while preserving a strict distinction
between source availability, contribution readiness, legal reviewability, and
production or release readiness.

## Users

1. **Repository owner:** needs clear licensing, intake, evidence, and review
   gates before accepting broader external contribution or release work.
2. **Contributor:** needs structured issue and PR prompts without having to know
   the repository's full governance model before reporting a problem or idea.
3. **Reviewer:** needs traceability from intake to approved spec, plan, ADRs,
   verification, risks, and rollback.
4. **Coding agent:** needs GitHub artifacts that route work to canonical docs
   rather than treating issue or PR text as authority.
5. **Future release maintainer:** needs a factual source license, attribution
   baseline, and release-history format that can be extended by `R10`.

## Problem Statement

The repository has contribution and security policy but lacks the GitHub
surfaces that consistently collect required evidence. Unstructured issues can
omit reproduction, scope, acceptance criteria, evaluation expectations, or
security impact. Unstructured PRs can omit approved artifacts, verification,
rollback, documentation changes, or deviations from scope.

The repository also lacks an explicit source license, third-party notice
inventory, and changelog. This creates ambiguity about reuse rights,
attribution, provenance, and what has actually shipped. Treating a public GitHub
repository as automatically licensed, treating dependency manifests as a legal
inventory, or putting planned roadmap work into a changelog would all create
misleading project signals.

## Goals

1. Establish four issue templates that capture the evidence needed to route
   features, bugs, technical debt, and experiments into repository governance.
2. Establish a PR template that makes approved artifacts, scope, verification,
   safety impact, documentation, rollback, and owner review visible.
3. Adopt Apache License 2.0 (`Apache-2.0`) as the repository's source license.
4. Define the boundary between project-authored source and third-party code,
   model, dataset, generated, and dependency licensing.
5. Establish `THIRD_PARTY_NOTICES.md` as the verified attribution and notice
   inventory for third-party material that the project includes or
   redistributes.
6. Establish `CHANGELOG.md` as release history only, with no fabricated release
   and no duplication of future roadmap work.
7. Preserve `SECURITY.md` as the only vulnerability-reporting policy and keep
   sensitive security evidence out of public templates.
8. Preserve the governance rule that issue and PR templates collect evidence
   but do not grant implementation, architecture, merge, or release approval.
9. Make Package 7 reviewable without claiming that later `R10` release
   readiness, CI reliability, runtime quality, or production security exists.

## Non-goals

1. Package 7 does not modify runtime source, tests, dependencies, Docker files,
   environment configuration, datasets, vector stores, model artifacts, or
   application behavior.
2. It does not fix, replace, or certify the current GitHub Actions workflow.
3. It does not create branch-protection rules, repository rulesets, labels,
   CODEOWNERS, bots, GitHub Apps, required checks, Discussions, or other hosting
   settings.
4. It does not stage, commit, push, open a PR, merge, tag, publish a release, or
   change Git history.
5. It does not create release automation, semantic-versioning automation,
   package publishing, container publishing, deployment automation, or a
   production release checklist; later `R10` owns full release readiness.
6. It does not claim that all direct or transitive dependencies have been
   legally audited when the current manifests cannot prove that fact.
7. It does not relicense third-party code, dependencies, models, datasets,
   generated content, or external travel content under Apache-2.0 when the
   repository does not own those rights.
8. It does not create a custom license or add legal clauses to Apache-2.0.
9. It does not replace `CONTRIBUTING.md`, `SECURITY.md`, specs, plans, ADRs,
   evaluation protocols, runbooks, or roadmap ownership with GitHub template
   text.
10. It does not promise contributor response times, security SLAs, release
    cadence, support guarantees, or production readiness.

## Assumptions

1. The repository owner intends Travel Agent to remain open source and accepts
   a permissive license unless this specification is rejected or revised.
2. Apache-2.0 is acceptable for project-authored source and documentation; its
   explicit patent grant is preferred over a shorter permissive license for an
   AI project that may receive external contributions.
3. Existing third-party packages retain their own license terms and are not
   relicensed by the root project license.
4. Dataset, model, web-content, and generated-artifact rights require separate
   provenance review when such material is committed or redistributed.
5. GitHub issue and PR text is public by default and therefore cannot be a safe
   channel for confidential vulnerability evidence or secrets.
6. The current CI workflow is evidence of configured automation only; it is not
   sufficient evidence that tests fail honestly or that the project is ready to
   release.
7. Package 7 can establish a truthful changelog before the first release by
   recording that no repository release has yet been published rather than
   inventing a version entry.
8. Exact release packaging and resolved transitive-license scanning depend on
   later release artifacts and therefore belong to `R10`, while Package 7 owns
   the source-tree attribution baseline.

## Selected Approach

Use a **governance-aware permissive foundation**:

1. Use plain Markdown GitHub templates with standard YAML front matter so the
   files are readable both on GitHub and locally.
2. Keep labels and assignees empty in template front matter until repository
   labels and ownership are separately verified and governed.
3. Ask contributors for problem evidence in the issue templates; let maintainers
   classify the change and create/approve persistent specs and plans when
   required.
4. Make the PR template evidence-oriented and require links to applicable
   governance artifacts without treating checked boxes as approval authority.
5. Use the unmodified Apache License 2.0 legal text as `LICENSE`.
6. Use `THIRD_PARTY_NOTICES.md` for verified notice and attribution obligations,
   while treating manifests, lockfiles, and future SBOM output as evidence
   sources rather than duplicates of the notice file.
7. Use a release-only changelog. When no release exists, state that fact; do not
   add an `Unreleased` roadmap surrogate.
8. Keep the current CI workflow outside Package 7 and require PR authors to
   report the exact verification that actually ran.

This approach adds the smallest set of artifacts already assigned to Package 7
while preserving existing governance and leaving release automation to later
work.

## Alternatives Considered

### MIT license plus lightweight templates

MIT is shorter and widely understood, with minimal license-text overhead. It
would be a reasonable permissive choice, but it does not contain the same
explicit patent grant and patent-termination terms as Apache-2.0. For a project
that may accept external AI/software contributions, Package 7 prefers the more
explicit patent contract despite the longer license text.

### Strong copyleft license

A GPL-family license would protect reciprocal source availability more strongly
when derivatives are distributed. That is a valid project strategy, but it
would impose a materially different redistribution contract and can complicate
integration into permissive or commercial systems. The current project intent
favors permissive reuse, so Package 7 does not select strong copyleft.

### Public source with no license

Leaving the repository without a license minimizes immediate work but does not
make reuse rights clear. Public visibility is not a substitute for explicit
permission. This conflicts with the repository's open-source intent and is
rejected.

### GitHub templates as the complete governance system

Embedding full spec, plan, ADR, security, and release policy in GitHub templates
would make every issue and PR self-contained but would duplicate canonical
documents and become stale. Package 7 instead uses templates as routing and
evidence surfaces.

## User and System Flows

### Feature, bug, debt, or experiment intake

1. A contributor selects the closest GitHub issue template.
2. The template asks for the minimum evidence appropriate to that intake type.
3. The contributor is warned to route confidential security details through
   `SECURITY.md` rather than the public issue.
4. A maintainer reviews the intake, classifies the work, and identifies required
   spec, architecture, plan, evaluation, and security gates.
5. Implementation starts only after the repository's required approvals exist.

### Pull request review

1. The contributor opens a PR only after the repository owner has authorized
   the applicable Git delivery step.
2. The PR links the issue/intake, approved spec, implementation plan, and ADRs
   when applicable.
3. The author records the exact verification and evaluation evidence that ran,
   including failures, skipped checks, and limitations.
4. The PR identifies security/privacy/data impact, migration/rollback impact,
   documentation changes, and deviations from approved scope.
5. Reviewers compare the PR to the approved artifacts and evidence; a checklist
   does not replace reviewer judgment or owner merge/release authority.

### License and third-party review

1. Project-authored source and documentation use the root Apache-2.0 license
   unless a file or subtree explicitly carries different terms approved by the
   repository owner.
2. Third-party material is identified from committed source/assets, dependency
   manifests and lockfiles, model/data provenance, and release packaging.
3. Required attribution or notice text is recorded only after its source and
   license obligation are verified.
4. Missing or incompatible provenance blocks distribution/release of the
   affected material until resolved; the root license does not override it.

### Changelog update

1. A release is actually approved and published by the repository owner.
2. User-visible outcomes in that released version are summarized under the
   released version and release date.
3. Planned roadmap items, experiments not promoted, and work still only in the
   working tree remain out of released changelog entries.

## GitHub Issue Template Contract

All four issue templates must use standard Markdown issue-template front matter
with `name`, `about`, `title`, `labels`, and `assignees`. Version 0.1 leaves
`labels` and `assignees` empty because Package 7 does not create or assume
repository labels or ownership settings.

Every issue template must:

1. Begin with a short pointer that confidential vulnerability evidence belongs
   in `SECURITY.md`, not the public issue.
2. Ask for evidence without requesting secrets, private user data, or full
   production traces.
3. Separate current behavior/problem evidence from proposed implementation.
4. Provide a place for scope and explicit non-goals.
5. Make acceptance or exit criteria observable.
6. Let maintainers record change classification and required governance
   artifacts after intake.
7. Avoid language that implies issue creation authorizes implementation.

### `.github/ISSUE_TEMPLATE/feature.md`

The feature template must capture:

1. User or engineering problem.
2. Impact and evidence.
3. Desired outcome.
4. Scope and non-goals.
5. Acceptance criteria.
6. Evaluation or quality expectations when applicable.
7. Security, privacy, data, and operational considerations.
8. Dependencies and related issues/specs.

### `.github/ISSUE_TEMPLATE/bug.md`

The bug template must capture:

1. Observed behavior.
2. Expected behavior.
3. Minimal reproduction steps.
4. Environment and relevant version/commit when known.
5. User/system impact and frequency.
6. Redacted evidence such as logs or screenshots when safe.
7. Regression-test expectation.
8. Known workaround and rollback/recovery considerations.

The bug template must make clear that suspected vulnerabilities are not normal
public bug reports.

### `.github/ISSUE_TEMPLATE/technical-debt.md`

The technical-debt template must capture:

1. Current evidence and affected boundary.
2. Cost, risk, or maintenance burden.
3. Desired boundary or measurable improvement.
4. Scope and non-goals.
5. Exit criteria.
6. Dependencies, compatibility, and migration concerns.
7. Verification and rollback expectations.

### `.github/ISSUE_TEMPLATE/experiment.md`

The experiment template must capture:

1. Hypothesis.
2. Baseline.
3. Independent variable or proposed intervention.
4. Fixed conditions and dataset/provenance.
5. Metrics, safety gates, and promotion threshold.
6. Expected failure interpretation.
7. Result location when completed.
8. Promotion decision: reject, continue experimenting, or propose separately
   governed product/runtime work.

An experiment result is evidence. It does not authorize production promotion or
silently change an evaluation protocol.

## Pull Request Template Contract

`.github/PULL_REQUEST_TEMPLATE.md` must make a PR reviewable without duplicating
the governing documents. It must include:

1. Summary and problem/outcome.
2. Related issue or approved intake exception.
3. Change classification.
4. Links to the exact approved spec and implementation plan when required.
5. Links to architecture approval and ADRs when Level 3 applies.
6. Scope confirmation and disclosed deviations.
7. Exact tests, builds, static checks, evaluation runs, or manual review that
   executed, with failures/skips/limitations disclosed.
8. Security, privacy, secret, user-data, and trust-boundary impact.
9. Migration, compatibility, operational, and rollback impact.
10. Canonical documentation updates.
11. Dependency, model, dataset, and license/provenance impact.
12. Confirmation that repository-owner change-set review occurred before the
    Git delivery action that created the PR, when required by governance.

The template must not contain a checkbox whose wording claims that checking it
approves a spec, architecture decision, implementation plan, merge, or release.
Those approvals remain separate owner actions.

## Source License Contract

Package 7 selects Apache License 2.0 using SPDX identifier `Apache-2.0`.

The implementation must:

1. Create root `LICENSE` from the unmodified canonical Apache License 2.0 text.
2. Treat the root license as the default license for project-authored source and
   documentation unless an approved file or subtree explicitly states different
   terms.
3. Preserve all third-party license and notice obligations; the root license
   never relicenses material the project does not own.
4. Avoid per-file license headers in Package 7 unless a later approved policy
   requires them.
5. Avoid adding custom restrictions, field-of-use clauses, attribution clauses,
   or warranty language outside the canonical license.
6. Treat trademark/name rights according to the license and applicable law; the
   source license does not create a separate project trademark policy.
7. Stop release/distribution work when ownership or licensing of included
   material is unresolved rather than assuming Apache-2.0 covers it.

The license selection is an engineering/open-source governance decision, not a
claim of individualized legal advice. A future owner/legal review may revise
the project license through a separately approved repository change if project
ownership or distribution requirements change.

## Third-party Notice Contract

`THIRD_PARTY_NOTICES.md` is the canonical human-reviewable inventory for
required notices and attribution associated with third-party code, models,
datasets, and other material included or redistributed by the project.

Each verified entry must identify, when applicable:

1. Component or asset name.
2. Category: code/dependency, model, dataset/content, or other bundled asset.
3. Upstream/source identity.
4. License identifier or license name.
5. Required notice or attribution.
6. How the project uses or distributes the material.
7. Evidence location used to verify the obligation.

The notice file must distinguish:

1. **Included or redistributed material:** requires verified provenance and all
   applicable notices before release.
2. **Declared dependencies:** package manifests or lockfiles identify software
   inputs but do not by themselves prove a complete legal inventory.
3. **External runtime services/content:** are not copied into the source license
   merely because the application can call or retrieve from them.

`THIRD_PARTY_NOTICES.md` is not a package lockfile, dependency resolver, SBOM,
or automated vulnerability database. Exact transitive-license scanning for a
specific release artifact remains part of later `R10` release readiness. If no
notice obligation can yet be verified for a category, the document must state
the bounded review status rather than invent a license or silently claim
completeness.

## Changelog Contract

`CHANGELOG.md` records user-visible outcomes that have actually been released.
It must:

1. Group entries by an actual released version and release date.
2. Use concise categories such as `Added`, `Changed`, `Fixed`, `Deprecated`,
   `Removed`, and `Security` only when applicable.
3. Describe observable outcomes rather than internal task lists.
4. Exclude planned roadmap work, unapproved designs, open experiments, and
   changes that exist only in an unaccepted working tree.
5. Avoid inventing a release version or date when no release exists.
6. Initially state that no repository release has been recorded when that is
   the verified current state.
7. Receive release entries only as part of an explicitly approved release or
   post-release documentation change.

Package 7 does not introduce an `Unreleased` section because the canonical
roadmap already owns future intent and the documentation system defines the
changelog as released-version history.

## Errors and Edge Cases

1. **Security report submitted through a public issue:** point the reporter to
   `SECURITY.md`; do not ask them to paste sensitive details into the issue.
2. **Contributor does not know the change level:** accept the intake evidence;
   maintainers classify the change before implementation planning.
3. **PR lacks an approved spec or plan where required:** the PR is not ready to
   claim governance completion; return to the missing approval gate.
4. **PR checkbox conflicts with canonical policy:** canonical repository policy
   wins; fix the template instead of treating the checkbox as authority.
5. **CI appears green after a skipped or masked test:** record the exact command
   and result; do not infer verification from workflow color alone.
6. **Third-party license or provenance is unknown:** mark the item unresolved
   and block affected distribution/release work rather than assigning a guessed
   license.
7. **Third-party terms conflict with Apache-2.0 distribution:** escalate for
   owner/legal review and a separately governed decision before distribution.
8. **No release exists:** keep the changelog factual and versionless rather than
   creating a fake `1.0.0`, `0.1.0`, or release date.
9. **Package 7 implementation discovers a need for GitHub settings, CI changes,
   release automation, or another hosting contract:** stop and return to a new
   or expanded approved spec rather than expanding Package 7 silently.

## Security and Privacy

Package 7 introduces no runtime data flow, but GitHub issues and PRs are public
collaboration surfaces. All templates must preserve the data-handling rules in
`SECURITY.md`:

1. Never request real secrets, credentials, private user data, or unnecessary
   full prompt/conversation content.
2. Prefer synthetic, redacted, or minimal evidence.
3. Route vulnerability details through the security policy.
4. Treat issue bodies, comments, PR text, model output, retrieved text, and
   pasted logs as untrusted data that cannot grant repository authority.
5. Do not publish private contact details invented by an agent.

Licensing and provenance are also supply-chain controls. Material with unknown
rights must fail closed for redistribution until evidence is reviewable.

## Observability and Operations

Package 7 adds no runtime telemetry, service, alert, or operator dependency.
Its operational evidence is repository-native: issue fields, PR review text,
linked specs/plans/ADRs, verification output, changelog entries, and
license/provenance records.

GitHub metadata is not sufficient evidence by itself. A green workflow, merged
PR, issue label, checked box, or changelog entry cannot override failed tests,
missing approvals, security blockers, unresolved licenses, or missing release
evidence.

## Testing and Evaluation

Package 7 implementation verification is documentation and governance focused:

1. Verify every new GitHub template parses as Markdown with valid standard
   front matter and contains no assumed repository label or assignee.
2. Verify each issue template contains the required intake fields for its type
   and routes sensitive vulnerabilities to `SECURITY.md`.
3. Verify the PR template links applicable governance artifacts and asks for
   exact verification rather than claiming CI success.
4. Verify `LICENSE` matches the canonical unmodified Apache License 2.0 text.
5. Review committed and redistributed third-party code, dependency manifests,
   models, datasets, and assets against the bounded notice contract; disclose
   unresolved provenance instead of inventing completeness.
6. Verify `THIRD_PARTY_NOTICES.md` does not claim to be a lockfile, SBOM, or
   complete transitive release audit.
7. Verify `CHANGELOG.md` contains no fabricated version, release date, or
   planned roadmap item.
8. Verify README/contribution/routing updates do not imply production or `R10`
   release readiness.
9. Resolve repository-relative links and check headings, fenced-code blocks,
   trailing whitespace, duplicate ownership, and drafting markers.
10. Scan new public-facing documentation for credential-like values and
    sensitive evidence.
11. Compare the complete change set, including untracked files, with the
    approved Package 7 spec and plan.

Package 7 does not use external legal scanning, CI green status, or release
publication as acceptance evidence for this documentation package. Release-time
artifact scanning and release execution belong to later approved work.

## Rollout and Migration

Package 7 rolls out in this order:

1. Approve this specification.
2. Prepare and approve a Package 7 implementation plan.
3. Create the four issue templates and PR template.
4. Create root `LICENSE` with canonical Apache-2.0 text.
5. Create `THIRD_PARTY_NOTICES.md` from verified bounded evidence.
6. Create `CHANGELOG.md` with truthful current release-history state.
7. Apply only the routing, roadmap, and traceability updates named in the
   approved implementation plan.
8. Run deterministic documentation, licensing, provenance, and scope checks.
9. Stop for repository-owner review of the exact Package 7 change set.

After Package 7 is accepted, documentation milestone `D7` is complete and
later `R10` has its required open-source documentation prerequisite. Package 7
does not by itself unblock public production, certify CI, or authorize a
release.

## Routing and Traceability Changes

The implementation plan may update only the minimum existing documents needed
to route readers to Package 7 artifacts:

1. `README.md`: link the source license, contribution/open-source documents,
   and changelog after they exist; replace the obsolete claim that no source
   license exists while preserving the distinction between source availability
   and release/production readiness.
2. `CONTRIBUTING.md`: point contributors to the GitHub intake templates and the
   license/provenance review expectations without duplicating template bodies.
3. `docs/roadmap/master-roadmap.md`: advance `D7` only according to actual
   implementation/review state and leave `R10` blocked until its own gates are
   satisfied.
4. `docs/specs/README.md` and, after plan creation, `docs/plans/README.md`: keep
   Package 7 lifecycle and discovery entries current.

No `AGENTS.md` or `SECURITY.md` routing change is required by this design: agent
GitHub work already routes through `CONTRIBUTING.md`, and vulnerability policy
already belongs to `SECURITY.md`. Any wider routing change is scope expansion
and returns to review.

## Rollback

Before Git delivery, Package 7 implementation rollback removes only:

1. The five GitHub templates created by the approved Package 7 plan.
2. Root `LICENSE` created by Package 7.
3. `THIRD_PARTY_NOTICES.md` created by Package 7.
4. `CHANGELOG.md` created by Package 7.
5. Package 7 routing and traceability edits named in the approved plan.
6. The Package 7 implementation plan if it was created for this package.

Rollback must not modify runtime source, tests, dependencies, Docker state,
local data, credentials, GitHub settings, CI configuration, Git history, tags,
releases, or accepted Packages 0-6 content outside explicitly named routing
fields.

After a public release or third-party redistribution occurs, license and notice
history may have legal significance and must not be treated as a simple file
deletion rollback. That later scenario requires release/legal review under the
governance applicable at that time.

## Acceptance Criteria

Package 7 implementation is acceptable only when:

1. The four issue templates and PR template exist at the canonical `.github`
   paths defined by the documentation system.
2. Templates collect evidence and route to governance without granting
   implementation, architecture, merge, or release authority.
3. Public templates route confidential vulnerability details to `SECURITY.md`
   and do not request secrets or private user data.
4. Feature, bug, technical-debt, and experiment templates each contain their
   required type-specific evidence and exit criteria.
5. The PR template records applicable spec, plan, ADR, verification,
   security/privacy/data, dependency/provenance, migration, rollback,
   documentation, and scope-deviation evidence.
6. Root `LICENSE` contains the canonical unmodified Apache License 2.0 text and
   the project consistently refers to the license as `Apache-2.0`.
7. Project-authored source licensing is clearly separated from third-party
   dependency, model, dataset, content, and asset rights.
8. `THIRD_PARTY_NOTICES.md` contains only verified attribution/notice facts,
   states its bounded scope, and does not claim to be a complete transitive
   release audit or SBOM.
9. Unknown or conflicting third-party provenance is represented as a
   distribution/release blocker rather than guessed away.
10. `CHANGELOG.md` records released history only and does not contain planned
    roadmap work or a fabricated first release.
11. Existing CI is not presented as proof that tests fail honestly or that the
    repository is release-ready.
12. `README.md` and `CONTRIBUTING.md` route to the new artifacts without
    duplicating their canonical content or claiming `R10`/production readiness.
13. Package 7 does not modify runtime code, tests, dependencies, CI,
    infrastructure, GitHub settings, data, model artifacts, Git state, tags, or
    releases.
14. All repository-relative links resolve and deterministic Markdown/licensing
    checks pass.
15. The repository owner approves Package 7 spec version 0.1 before an
    implementation plan is prepared.
16. The repository owner later accepts the exact Package 7 implementation
    change set before any Git delivery action.

## Verification

The Package 7 implementation plan must include:

1. Direct repository reads for current open-source artifacts, contribution
   policy, security policy, CI behavior, manifests, lockfiles, and data paths.
2. Front-matter checks for all five GitHub templates.
3. Content checks proving each issue type and PR review contract is present.
4. A canonical Apache-2.0 license-text comparison from an authoritative or
   trusted local source; hand-written paraphrase is not acceptable.
5. A bounded third-party provenance review covering committed/copied assets,
   Python dependency declarations, npm manifests/lockfile, and any model or
   dataset material intended for redistribution by Package 7 scope.
6. A changelog review proving that only actual released outcomes are recorded.
7. Secret/sensitive-evidence scans across the new public-facing documents.
8. Link resolution, trailing-whitespace, drafting-marker, heading, and
   fenced-code-block checks.
9. A final scope review using `git status --short --untracked-files=all` plus
   direct reads or read-only no-index diffs for untracked files.

## ADR Impact

No ADR is required to approve Package 7 version 0.1. The package selects an
open-source license and repository-document contracts but does not introduce a
runtime subsystem, storage boundary, protocol, deployment topology, trust
boundary, or another hard-to-reverse software architecture decision.

If implementation discovers that release automation, identity/permissions,
artifact signing, supply-chain attestation, hosting configuration, or another
hard-to-reverse platform boundary is required, work stops and returns to the
appropriate Level 2 or Level 3 design and approval process.

## Approval Record

Package 7 design was requested by the repository owner on 2026-08-31 in this
conversation. That request authorizes investigation and preparation of this
specification for review; it does not bypass the specification or
implementation-plan approval gates.

Version 0.1 was approved by the repository owner on 2026-08-31 via the exact
conversation phrase `Approve Package 7 spec version 0.1`. This approval
authorizes preparation of the Package 7 implementation plan only. It also
confirms the selected Apache-2.0 source license in this specification. It does
not authorize creation of Package 7 implementation artifacts, GitHub setting
changes, Git delivery, tagging, or release publication.
