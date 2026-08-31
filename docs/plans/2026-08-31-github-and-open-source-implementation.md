# GitHub and Open Source Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence. Use the approved specification as the authority for
> Package 7 behavior and stop when a required assumption, boundary, or approval
> changes.

**Goal:** Create the repository's first governance-aware GitHub intake/review
templates and truthful open-source legal/history baseline without claiming
release or production readiness.

**Architecture:** Package 7 is documentation and repository-intake work only.
GitHub templates collect evidence and route contributors into existing
governance; `LICENSE`, `THIRD_PARTY_NOTICES.md`, and `CHANGELOG.md` have distinct
canonical responsibilities; existing routing documents receive only the
minimal approved links and lifecycle updates.

**Tech Stack:** Markdown, YAML front matter, Apache License 2.0 canonical text,
Codebase Memory MCP at Verify tier, direct repository reads, shell, ripgrep,
Node.js for deterministic `package-lock.json` inspection, Ruby one-line
repository-link checking, and Git read-only inspection.

**Spec:** [GitHub and Open Source Design](../specs/2026-08-31-github-and-open-source-design.md),
approved version 0.1.

| Field | Value |
| --- | --- |
| Status | Completed |
| Plan version | 0.1 |
| Date | 2026-08-31 |
| Approved specification | [GitHub and Open Source Design](../specs/2026-08-31-github-and-open-source-design.md), version 0.1 |
| Execution owner | Coding agent after explicit plan approval |
| Decision owner | Repository owner |
| Scope | Five GitHub templates, root `LICENSE`, `THIRD_PARTY_NOTICES.md`, `CHANGELOG.md`, approved routing/traceability updates, and this plan only |
| Verification | Verify-tier coverage evidence, template front-matter/content checks, canonical Apache-2.0 comparison, bounded third-party provenance review, release-history review, sensitive-data scan, deterministic Markdown/link checks, exact change-set review, and owner change-set review |

## Global Constraints

1. Do not execute this plan until the repository owner explicitly approves this
   exact plan.
2. Package 7 is documentation and repository-intake work only. Do not modify
   runtime source, tests, dependencies, Docker files, environment files, CI,
   application behavior, persistent data, model artifacts, GitHub settings,
   branch protection, Git history, tags, or releases.
3. Create exactly these Package 7 canonical artifacts:
   - `.github/PULL_REQUEST_TEMPLATE.md`
   - `.github/ISSUE_TEMPLATE/feature.md`
   - `.github/ISSUE_TEMPLATE/bug.md`
   - `.github/ISSUE_TEMPLATE/technical-debt.md`
   - `.github/ISSUE_TEMPLATE/experiment.md`
   - `LICENSE`
   - `THIRD_PARTY_NOTICES.md`
   - `CHANGELOG.md`
4. Modify only these existing files during approved Package 7 execution:
   - `README.md`
   - `CONTRIBUTING.md`
   - `docs/roadmap/master-roadmap.md`
   - `docs/specs/README.md`
   - `docs/specs/2026-08-31-github-and-open-source-design.md`
   - `docs/plans/README.md`
   - `docs/plans/2026-08-31-github-and-open-source-implementation.md`
5. GitHub issue and PR templates are intake and review surfaces only. They never
   authorize implementation, architecture, merge, release, or another owner
   decision.
6. Public templates must route confidential vulnerability evidence to
   `SECURITY.md` and must not request credentials, private user data, sensitive
   production traces, or unnecessary full prompts/conversations.
7. All four issue templates use standard Markdown front matter containing
   `name`, `about`, `title`, `labels`, and `assignees`; `labels` and `assignees`
   remain empty in Package 7.
8. Root `LICENSE` must be the unmodified canonical Apache License 2.0 text and
   the repository must refer to the selected source license by SPDX identifier
   `Apache-2.0`.
9. The root source license applies by default to project-authored source and
   documentation only. It does not relicense third-party dependencies, copied
   code, models, datasets, generated artifacts, or external content.
10. `THIRD_PARTY_NOTICES.md` records only verified attribution/notice facts and
    bounded review status. It must not claim to be a dependency lockfile, SBOM,
    automated vulnerability database, or complete transitive release audit.
11. Unknown or conflicting third-party provenance fails closed for affected
    redistribution/release work. Never guess a license or notice obligation.
12. `CHANGELOG.md` records actual released history only. Do not create an
    `Unreleased` roadmap surrogate or invent a version/date when no release is
    verified.
13. Do not use the existence or visual status of `.github/workflows/ci.yml` as
    evidence that tests fail honestly or that the repository is release-ready.
14. Full release readiness remains owned by roadmap milestone `R10`; Package 7
    must not claim production readiness, release certification, or release
    automation.
15. Keep technical repository documentation in English.
16. Preserve unrelated dirty or untracked work from Packages 0-6.
17. The repository owner creates/selects branches and decides when to stage,
    commit, push, open a PR, merge, tag, publish a release, or otherwise perform
    Git delivery.
18. Repository-owner review of the exact Package 7 implementation change set is
    required before any Git delivery action or owner-accepted `D7` completion.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `.github/ISSUE_TEMPLATE/feature.md` | Collect feature problem, outcome, scope, acceptance, evaluation, and safety evidence | Approved spec and Task 1 evidence |
| `.github/ISSUE_TEMPLATE/bug.md` | Collect safe reproducible bug evidence, regression expectations, and recovery context | Approved spec, `SECURITY.md`, Task 1 evidence |
| `.github/ISSUE_TEMPLATE/technical-debt.md` | Collect debt boundary, cost/risk, desired improvement, exit, migration, verification, and rollback evidence | Approved spec and Task 1 evidence |
| `.github/ISSUE_TEMPLATE/experiment.md` | Collect hypothesis, baseline, controlled intervention, metrics, safety gates, result location, and promotion decision | Approved spec and evaluation docs |
| `.github/PULL_REQUEST_TEMPLATE.md` | Collect review traceability, exact verification, impact, rollback, provenance, documentation, and deviation evidence | Existing governance docs and four issue templates |
| `LICENSE` | Canonical unmodified Apache License 2.0 text for project-authored source/documentation | Approved license decision and authoritative Apache text |
| `THIRD_PARTY_NOTICES.md` | Human-reviewable bounded inventory of verified third-party attribution/notice obligations and unresolved provenance blockers | Task 1 provenance evidence and root license boundary |
| `CHANGELOG.md` | Released user-visible history only, or truthful no-release state when no release is verified | Task 1 release evidence |
| `README.md` | Route readers to license, contribution/open-source documents, and changelog without claiming release readiness | Created Package 7 artifacts |
| `CONTRIBUTING.md` | Route contributors to GitHub intake surfaces and license/provenance expectations without duplicating template bodies | GitHub templates, license/notices, existing governance |
| `docs/roadmap/master-roadmap.md` | Reflect actual `D7` implementation/review state while leaving `R10` separately gated | Package 7 evidence and owner review state |
| `docs/specs/README.md` | Keep Package 7 specification discovery/lifecycle entry accurate | Approved Package 7 spec |
| `docs/specs/2026-08-31-github-and-open-source-design.md` | Track implementation-plan linkage and implementation/review state without changing design approval | This plan and later implementation evidence |
| `docs/plans/README.md` | Index this plan and keep its lifecycle status accurate | This plan |
| `docs/plans/2026-08-31-github-and-open-source-implementation.md` | Track approved tasks, verification evidence, completion state, and remaining owner gate | Approved Package 7 spec and owner plan approval |

## Task 1: Re-establish Open-source and Provenance Evidence

**Files:**

- Read: `README.md`
- Read: `CONTRIBUTING.md`
- Read: `SECURITY.md`
- Read: `.github/workflows/ci.yml`
- Read: `requirements.txt`
- Read: `backend/requirements.txt`
- Read: `frontend/package.json`
- Read: `frontend/package-lock.json`
- Read: `.gitignore`
- Read: `docs/roadmap/master-roadmap.md`
- Read: `docs/specs/2026-08-31-github-and-open-source-design.md`

**Interfaces:**

- Consumes: approved Package 7 spec plus current repository, dependency,
  release, security, and roadmap state.
- Produces: verified current-state facts, bounded provenance inventory, and
  limitations consumed by Tasks 2-7.

- [x] **Step 1: Refresh Codebase Memory evidence at Verify tier**

Confirm the active graph project/generation and run `check_index_coverage` for
every relied-on repository path. Read every reported partial, skipped, stale,
pending, unknown, or not-tracked range directly before relying on it.

Expected: current Package 7 evidence paths have explicit coverage state. A clean
coverage signal is treated as best-effort rather than proof of semantic
completeness.

- [x] **Step 2: Re-read contribution, security, CI, dependency, and roadmap evidence**

Run:

```bash
sed -n '1,240p' README.md
sed -n '1,260p' CONTRIBUTING.md
sed -n '1,260p' SECURITY.md
sed -n '1,260p' .github/workflows/ci.yml
sed -n '1,260p' requirements.txt
sed -n '1,260p' backend/requirements.txt
sed -n '1,260p' frontend/package.json
sed -n '1,240p' .gitignore
rg -n 'D7|R10|Package 7|license|release|GitHub|open.source' docs/roadmap/master-roadmap.md README.md CONTRIBUTING.md
```

Expected: implementation preserves current governance and security routing,
does not treat CI status as test/release proof, and does not infer a complete
Python license graph from range-based requirements.

- [x] **Step 3: Build a bounded repository-material inventory**

Run:

```bash
rg --files -g '!frontend/node_modules/**' -g '!data/processed/**' -g '!data/chromadb/**'
rg --files -g '!frontend/node_modules/**' -g '!data/processed/**' -g '!data/chromadb/**' | rg '\.(png|jpg|jpeg|webp|svg|gif|csv|tsv|jsonl|parquet|onnx|pt|pth|bin|gguf|model)$'
rg -n --hidden -g '!.git/**' -g '!frontend/node_modules/**' -g '!data/processed/**' -g '!data/chromadb/**' 'SPDX-License-Identifier|Copyright|Licensed under|Apache License|MIT License|Permission is hereby granted' .
```

Expected: committed/copied assets and embedded third-party license/notice clues
are enumerated without traversing generated dependencies or ignored persistent
data. Any candidate third-party material is verified from its actual source
before becoming a notice entry.

- [x] **Step 4: Inspect frontend resolved license metadata deterministically**

Run:

```bash
node -e 'const p=require("./frontend/package-lock.json"); const rows=Object.entries(p.packages||{}).filter(([k,v])=>k&&v&&v.license).map(([k,v])=>[k,v.license]); const counts={}; for (const [,license] of rows) counts[license]=(counts[license]||0)+1; console.log(JSON.stringify({resolvedPackages:rows.length,licenseCounts:counts},null,2));'
node -e 'const p=require("./frontend/package-lock.json"); const rows=Object.entries(p.packages||{}).filter(([k,v])=>k&&v&&v.license&&!["MIT","ISC","Apache-2.0","BSD-2-Clause","BSD-3-Clause"].includes(v.license)).map(([k,v])=>({package:k,license:v.license})); console.log(JSON.stringify(rows,null,2));'
```

Expected: the lockfile is used as provenance evidence, not as a legal
conclusion. Non-routine identifiers receive manual source verification if they
could create notice/attribution obligations for material redistributed by the
project.

- [x] **Step 5: Establish current release evidence**

Run:

```bash
git tag --list
git log --decorate --oneline -n 30
rg -n --hidden -g '!.git/**' -g '!frontend/node_modules/**' 'release|released|version [0-9]+\.[0-9]+\.[0-9]+|v[0-9]+\.[0-9]+\.[0-9]+' README.md CHANGELOG.md docs .github 2>/dev/null
```

If a configured remote and authenticated read-only GitHub CLI are already
available, additionally run `gh release list --limit 20` without changing
repository state. If remote release state cannot be verified, describe only
what local repository evidence proves and do not invent a release.

Expected: Task 6 has enough evidence either to record actual released versions
or to state the bounded fact that no repository release is recorded in the
verified evidence.

- [x] **Step 6: Review checkpoint**

Compare Task 1 evidence with the spec's Current-state Evidence, Assumptions,
Source License Contract, Third-party Notice Contract, Changelog Contract, and
Verification sections.

Expected: no material assumption has changed. A need for CI changes, GitHub
settings, release automation, a different license, or another unapproved
platform boundary stops Package 7 and returns to specification review.

## Task 2: Create Four GitHub Issue Templates

**Files:**

- Create: `.github/ISSUE_TEMPLATE/feature.md`
- Create: `.github/ISSUE_TEMPLATE/bug.md`
- Create: `.github/ISSUE_TEMPLATE/technical-debt.md`
- Create: `.github/ISSUE_TEMPLATE/experiment.md`
- Read: `CONTRIBUTING.md`
- Read: `SECURITY.md`
- Read: `docs/evaluation/rag-evaluation.md`
- Read: `docs/evaluation/memory-evaluation.md`

**Interfaces:**

- Consumes: approved issue-template contracts, current contribution/security
  policy, and evaluation ownership.
- Produces: four public intake surfaces consumed by maintainers and referenced
  by Task 7 routing updates.

- [x] **Step 1: Create standard front matter for all four templates**

Use these exact front-matter values:

```yaml
---
name: Feature request
about: Propose a user or engineering capability with evidence and observable outcomes
title: ""
labels: ""
assignees: ""
---
```

```yaml
---
name: Bug report
about: Report a reproducible defect with safe, redacted evidence
title: ""
labels: ""
assignees: ""
---
```

```yaml
---
name: Technical debt
about: Describe a bounded maintenance risk and measurable improvement
title: ""
labels: ""
assignees: ""
---
```

```yaml
---
name: Experiment
about: Propose a controlled experiment with baseline, metrics, and promotion gates
title: ""
labels: ""
assignees: ""
---
```

Expected: no unverified label or assignee is assumed.

- [x] **Step 2: Add the shared public-intake safety and governance boundary**

Begin every issue body with a concise warning that suspected vulnerabilities or
confidential security evidence belong through the path defined in
`SECURITY.md`, not the public issue. Request synthetic, minimal, or redacted
evidence and state that issue creation does not authorize implementation.

Every template must also provide headings for scope/non-goals, observable
acceptance or exit criteria, related dependencies/artifacts, and maintainer
classification/governance routing.

Expected: no public template asks for secrets, private user data, or full
production traces.

- [x] **Step 3: Add feature-specific evidence fields**

Use body headings that cover: problem, impact/evidence, desired outcome, scope,
non-goals, acceptance criteria, evaluation/quality expectations, security/
privacy/data/operations, and dependencies/related issues or specs.

Expected: the feature template captures the spec contract without prescribing
an implementation before classification and approval.

- [x] **Step 4: Add bug-specific evidence fields**

Use body headings that cover: observed behavior, expected behavior, minimal
reproduction, environment/version/commit when known, impact/frequency, safe
redacted evidence, regression-test expectation, workaround, and rollback/
recovery considerations.

Expected: suspected vulnerabilities are explicitly excluded from normal public
bug reporting.

- [x] **Step 5: Add technical-debt-specific evidence fields**

Use body headings that cover: current evidence/affected boundary, cost/risk,
desired measurable improvement, scope, non-goals, exit criteria, dependencies,
compatibility/migration, verification, and rollback expectations.

Expected: debt intake remains measurable and bounded rather than becoming an
unapproved refactor mandate.

- [x] **Step 6: Add experiment-specific evidence fields**

Use body headings that cover: hypothesis, baseline, intervention/independent
variable, fixed conditions and dataset/provenance, metrics, safety gates,
promotion threshold, failure interpretation, result location, and promotion
decision (`reject`, `continue experimenting`, or `propose separately governed
product/runtime work`).

Expected: experiment results remain evidence and do not authorize production
promotion or evaluation-protocol changes.

- [x] **Step 7: Verify front matter and required issue content**

Run:

```bash
for f in .github/ISSUE_TEMPLATE/feature.md .github/ISSUE_TEMPLATE/bug.md .github/ISSUE_TEMPLATE/technical-debt.md .github/ISSUE_TEMPLATE/experiment.md; do ruby -e 's=File.read(ARGV[0]); abort("missing front matter") unless s.start_with?("---\n") && s.split("---\n",3).length==3; fm=s.split("---\n",3)[1]; %w[name about title labels assignees].each{|k| abort("missing #{k}: #{ARGV[0]}") unless fm.match?(/^#{Regexp.escape(k)}:/)}; abort("labels must be empty") unless fm.match?(/^labels: ""$/); abort("assignees must be empty") unless fm.match?(/^assignees: ""$/)' "$f" || exit 1; done
rg -n 'SECURITY\.md|scope|non-goal|accept|exit|classification|spec|plan|approval' .github/ISSUE_TEMPLATE/*.md
rg -n 'secret|credential|private user data|redact|confidential|vulnerabil' .github/ISSUE_TEMPLATE/*.md
```

Expected: all four templates parse the required front-matter shape, leave labels
and assignees empty, include their type-specific contract, and preserve public
data-safety/governance boundaries.

- [x] **Step 8: Review checkpoint**

Read all four templates against the spec's shared issue-template contract and
the four type-specific contracts.

Expected: a maintainer can reject one template independently without invalidating
the others, and none of them duplicates canonical policy bodies.

## Task 3: Create Pull Request Review Template

**Files:**

- Create: `.github/PULL_REQUEST_TEMPLATE.md`
- Read: `CONTRIBUTING.md`
- Read: `SECURITY.md`
- Read: `docs/specs/README.md`
- Read: `docs/plans/README.md`
- Read: `docs/adr/README.md`

**Interfaces:**

- Consumes: approved PR-template contract and existing governance ownership.
- Produces: one public PR evidence surface used during repository-owner and
  reviewer change-set review.

- [x] **Step 1: Create the PR template with canonical review sections**

Use this top-level structure:

```markdown
# Summary
## Related Intake
## Change Classification
## Approved Governance Artifacts
## Scope and Deviations
## Verification Evidence
## Security, Privacy, Data, and Trust Boundaries
## Migration, Compatibility, Operations, and Rollback
## Documentation
## Dependencies, Models, Datasets, and Provenance
## Repository-owner Change-set Review
```

Within `Approved Governance Artifacts`, provide fields for exact approved spec,
implementation plan, architecture approval, and ADR links when applicable.
Within `Verification Evidence`, require exact commands/runs, outcomes,
failures, skips, and limitations rather than a generic CI-green checkbox.

Expected: all twelve PR contract areas from the approved spec are represented.

- [x] **Step 2: Encode approval and sensitive-data boundaries**

State explicitly that checked boxes and PR text do not approve a spec,
architecture decision, implementation plan, merge, or release. Route
confidential vulnerability evidence to `SECURITY.md` and request only redacted
or synthetic public evidence.

Expected: the template supports review without granting repository authority.

- [x] **Step 3: Verify PR contract content**

Run:

```bash
rg -n '^# Summary$|^## (Related Intake|Change Classification|Approved Governance Artifacts|Scope and Deviations|Verification Evidence|Security, Privacy, Data, and Trust Boundaries|Migration, Compatibility, Operations, and Rollback|Documentation|Dependencies, Models, Datasets, and Provenance|Repository-owner Change-set Review)$' .github/PULL_REQUEST_TEMPLATE.md
rg -n 'spec|plan|ADR|architecture|failure|skip|limitation|SECURITY\.md|rollback|provenance|license|change-set review' .github/PULL_REQUEST_TEMPLATE.md
```

Expected: exact governance, verification, impact, rollback, documentation, and
provenance evidence is requested without making CI or a checkbox authoritative.

- [x] **Step 4: Review checkpoint**

Read the PR template end-to-end against `CONTRIBUTING.md`, `SECURITY.md`, and the
approved PR Template Contract.

Expected: canonical documents remain authoritative and the PR body acts only as
a traceability/review surface.

## Task 4: Create Canonical Apache-2.0 Source License

**Files:**

- Create: `LICENSE`
- Read: approved Package 7 spec

**Interfaces:**

- Consumes: approved Apache-2.0 license decision and authoritative canonical
  license text.
- Produces: root source license consumed by README/contribution routing and the
  third-party boundary in Task 5.

- [x] **Step 1: Obtain canonical Apache License 2.0 text from the authoritative source**

Use the Apache Software Foundation canonical text at
`https://www.apache.org/licenses/LICENSE-2.0.txt`. During execution, retrieve it
read-only into a temporary file with:

```bash
curl -fsSL https://www.apache.org/licenses/LICENSE-2.0.txt -o /tmp/travel-agent-apache-license-2.0.txt
```

If network access is unavailable, use a trusted local canonical copy only after
recording its provenance. Do not reconstruct or paraphrase the legal text from
memory.

Expected: the source text is authoritative or has explicit trusted local
provenance.

- [x] **Step 2: Create root `LICENSE` without modification**

Create `LICENSE` byte-for-byte from the verified canonical text. Do not append
project-specific restrictions, attribution clauses, warranty text, copyright
headers, or field-of-use terms.

Expected: Package 7 changes the repository source-license state only through
the canonical Apache License 2.0 text approved by the owner.

- [x] **Step 3: Verify exact license identity**

Run:

```bash
cmp -s LICENSE /tmp/travel-agent-apache-license-2.0.txt
printf '%s\n' "$?"
rg -n '^Apache License$|^Version 2\.0, January 2004$|http://www\.apache\.org/licenses/' LICENSE
```

Expected: `cmp` exit status is `0`; no project-specific legal text has been
inserted into `LICENSE`.

- [x] **Step 4: Review checkpoint**

Review the root-license boundary against the Source License Contract.

Expected: project-authored source/documentation defaults to `Apache-2.0`, while
third-party rights remain separate and are handled by Task 5.

## Task 5: Create Bounded Third-party Notice Inventory

**Files:**

- Create: `THIRD_PARTY_NOTICES.md`
- Read: Task 1 provenance evidence
- Read: `requirements.txt`
- Read: `backend/requirements.txt`
- Read: `frontend/package.json`
- Read: `frontend/package-lock.json`
- Read: repository-material candidates identified by Task 1

**Interfaces:**

- Consumes: verified source/asset provenance evidence and the root-license
  boundary from Task 4.
- Produces: a human-reviewable notice/attribution baseline with unresolved
  provenance represented explicitly as a redistribution/release blocker.

- [x] **Step 1: Create the notice document with bounded ownership**

Use this top-level structure:

```markdown
# Third-party Notices

## Purpose and Scope
## Project License Boundary
## Included or Redistributed Material
## Declared Dependencies
## Models, Datasets, and Content
## External Runtime Services and Content
## Unresolved Provenance
## Release-time Review Boundary
## Updating This Inventory
```

State explicitly that this file is not a lockfile, dependency resolver, SBOM,
automated vulnerability database, or complete transitive release audit.

- [x] **Step 2: Record only verified included/redistributed entries**

For every material item that Task 1 proves is included or redistributed and has
a relevant notice/attribution obligation, record: component/asset name,
category, upstream/source identity, verified license identifier/name, required
notice/attribution, project use/distribution, and evidence location.

If Task 1 verifies no such entry in the bounded source-tree scope, state that
bounded result instead of inventing entries.

Expected: every factual notice can be traced to evidence and no dependency
manifest alone is treated as proof of a legal obligation.

- [x] **Step 3: Record dependency and provenance limitations**

Explain that Python manifests declare version ranges and do not resolve an exact
transitive graph. Explain that `frontend/package-lock.json` is resolved package
metadata but still requires release-specific obligation review. Separate
external runtime services/content from material actually copied into a release.

Expected: unknown/conflicting provenance is named as a blocker for affected
distribution, never guessed away.

- [x] **Step 4: Verify notice boundaries and evidence fields**

Run:

```bash
rg -n '^## (Purpose and Scope|Project License Boundary|Included or Redistributed Material|Declared Dependencies|Models, Datasets, and Content|External Runtime Services and Content|Unresolved Provenance|Release-time Review Boundary|Updating This Inventory)$' THIRD_PARTY_NOTICES.md
rg -n 'Apache-2\.0|lockfile|SBOM|transitive|provenance|redistribut|release|evidence|unresolved' THIRD_PARTY_NOTICES.md
```

Expected: source licensing and third-party licensing are visibly separated,
bounded review status is honest, and release-time transitive scanning remains
owned by `R10`.

- [x] **Step 5: Review checkpoint**

Compare the final notice inventory with every Task 1 candidate and the
Third-party Notice Contract.

Expected: no candidate material with relevant redistribution implications is
silently omitted, and no unverified license/notice claim is added.

## Task 6: Create Truthful Release-only Changelog

**Files:**

- Create: `CHANGELOG.md`
- Read: Task 1 release evidence
- Read: `docs/roadmap/master-roadmap.md`

**Interfaces:**

- Consumes: verified local/remote release evidence and the roadmap/changelog
  ownership boundary.
- Produces: release-history document with no planned work represented as shipped.

- [x] **Step 1: Create the changelog according to verified release state**

Use:

```markdown
# Changelog

This file records user-visible outcomes from repository releases only. Planned
work belongs in `docs/roadmap/master-roadmap.md`.

No repository release has been recorded in the verified project evidence.
```

Use that exact no-release statement only if Task 1 still supports it. If Task 1
positively verifies an actual release, stop and revise this task within the
approved changelog contract before writing a versioned entry; do not fabricate
history from commits or roadmap milestones.

Expected: the initial file is versionless when no release is verified and has
no `Unreleased` section.

- [x] **Step 2: Verify no fabricated release or roadmap content exists**

Run:

```bash
rg -n '^## \[?v?[0-9]+\.[0-9]+\.[0-9]+' CHANGELOG.md && exit 1 || true
rg -n '^## Unreleased$|D7|R10|Planned|In Progress|Blocked by gate' CHANGELOG.md && exit 1 || true
rg -n 'release|roadmap' CHANGELOG.md
```

Expected: no version/date or future roadmap status appears unless Task 1 proved
an actual release requiring a separately factual entry.

- [x] **Step 3: Review checkpoint**

Compare `CHANGELOG.md` with the Changelog Contract and Task 1 release evidence.

Expected: changelog history and roadmap intent remain distinct canonical
responsibilities.

## Task 7: Apply Minimal Routing and Traceability Updates

**Files:**

- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `docs/roadmap/master-roadmap.md`
- Modify: `docs/specs/README.md`
- Modify: `docs/specs/2026-08-31-github-and-open-source-design.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/plans/2026-08-31-github-and-open-source-implementation.md`

**Interfaces:**

- Consumes: all Package 7 artifacts and verified implementation state from
  Tasks 1-6.
- Produces: discoverable Package 7 documentation with lifecycle metadata that
  reflects actual evidence and does not overstate `D7` or `R10` status.

- [x] **Step 1: Update `README.md` open-source routing**

Replace the obsolete statement that the repository has no source license with
a concise `Apache-2.0` link to `LICENSE`. Link `CONTRIBUTING.md`,
`THIRD_PARTY_NOTICES.md`, and `CHANGELOG.md` where readers look for project
governance/open-source information.

Preserve explicit wording that source licensing and documentation readiness do
not certify production or full release readiness.

- [x] **Step 2: Update `CONTRIBUTING.md` intake and provenance routing**

Point contributors to the four `.github/ISSUE_TEMPLATE/` intake types and the
PR template without duplicating their bodies. Add concise license/provenance
expectations that route source licensing to `LICENSE`, verified third-party
notices to `THIRD_PARTY_NOTICES.md`, and confidential vulnerability evidence to
`SECURITY.md`.

Expected: contribution policy remains canonical for approvals and Git ownership.

- [x] **Step 3: Update roadmap and lifecycle metadata truthfully**

After Tasks 1-6 pass, update `D7` only to the implementation state actually
supported by evidence. Do not mark `R10` complete or imply release readiness.

Update the Package 7 spec implementation-plan field to point to this exact plan.
During execution, set implementation state/status only when the corresponding
evidence exists. Keep the Package 7 spec approval itself at `Approved` version
0.1.

Update `docs/specs/README.md` and `docs/plans/README.md` lifecycle/discovery
entries to match the resulting spec/plan state.

- [x] **Step 4: Verify routing language and absence of overclaims**

Run:

```bash
rg -n 'Apache-2\.0|LICENSE|THIRD_PARTY_NOTICES\.md|CHANGELOG\.md|CONTRIBUTING\.md' README.md
rg -n 'ISSUE_TEMPLATE|PULL_REQUEST_TEMPLATE|LICENSE|THIRD_PARTY_NOTICES\.md|SECURITY\.md|approval|repository owner' CONTRIBUTING.md
rg -n 'D7|R10|GitHub and Open Source|github-and-open-source' docs/roadmap/master-roadmap.md docs/specs/README.md docs/specs/2026-08-31-github-and-open-source-design.md docs/plans/README.md docs/plans/2026-08-31-github-and-open-source-implementation.md
rg -n 'production.ready|release.ready|CI.*proof|green.*proof' README.md CONTRIBUTING.md docs/roadmap/master-roadmap.md docs/specs/2026-08-31-github-and-open-source-design.md
```

Expected: new artifacts are discoverable, Package 7 state is accurate, and no
route claims `R10`, CI reliability, public production readiness, or release
certification.

- [x] **Step 5: Review checkpoint**

Read every routing edit beside the canonical artifact it references.

Expected: links replace duplication, ownership remains stable, and no wider
`AGENTS.md` or `SECURITY.md` edit is introduced.

## Task 8: Verify Exact Package 7 Change Set

**Files:**

- Test: all Package 7 created and modified files named in this plan
- Read: approved Package 7 spec and this approved implementation plan

**Interfaces:**

- Consumes: Tasks 1-7 outputs.
- Produces: deterministic acceptance evidence and the exact repository-owner
  change set for the final review gate.

- [x] **Step 1: Verify required artifact existence and forbidden-scope absence**

Run:

```bash
for f in .github/PULL_REQUEST_TEMPLATE.md .github/ISSUE_TEMPLATE/feature.md .github/ISSUE_TEMPLATE/bug.md .github/ISSUE_TEMPLATE/technical-debt.md .github/ISSUE_TEMPLATE/experiment.md LICENSE THIRD_PARTY_NOTICES.md CHANGELOG.md; do test -f "$f" || exit 1; done
git status --short --untracked-files=all
git diff -- .github/workflows/ci.yml requirements.txt backend/requirements.txt frontend/package.json frontend/package-lock.json docker-compose.yml backend frontend/src
```

Expected: all eight canonical Package 7 artifacts exist and Package 7 has not
modified CI, dependencies, runtime source, Docker configuration, or other
forbidden surfaces.

- [x] **Step 2: Re-run template, license, notice, and changelog checks**

Run every deterministic command from Tasks 2-6 freshly in the final repository
state.

Expected: all commands succeed with the exact expected conditions; failures or
skips are reported rather than masked.

- [x] **Step 3: Scan new public-facing documentation for sensitive evidence**

Run:

```bash
rg -n --hidden -g '!.git/**' -g '!frontend/node_modules/**' '(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)' .github README.md CONTRIBUTING.md THIRD_PARTY_NOTICES.md CHANGELOG.md docs/specs/2026-08-31-github-and-open-source-design.md docs/plans/2026-08-31-github-and-open-source-implementation.md
```

Expected: no credential-like value or private key appears. Any match is reviewed
before continuing; real sensitive material is removed from public artifacts and
handled according to `SECURITY.md`.

- [x] **Step 4: Run deterministic Markdown and repository-relative link checks**

Run:

```bash
rg -n '[[:blank:]]+$' .github README.md CONTRIBUTING.md THIRD_PARTY_NOTICES.md CHANGELOG.md docs/roadmap/master-roadmap.md docs/specs/README.md docs/specs/2026-08-31-github-and-open-source-design.md docs/plans/README.md docs/plans/2026-08-31-github-and-open-source-implementation.md
rg -n '\b(T[O]DO|T[B]D|F[I]XME|X[X]X)\b|\[[i]nsert|\[[r]eplace|\[[a]dd ' .github README.md CONTRIBUTING.md THIRD_PARTY_NOTICES.md CHANGELOG.md docs/roadmap/master-roadmap.md docs/specs/README.md docs/specs/2026-08-31-github-and-open-source-design.md docs/plans/README.md docs/plans/2026-08-31-github-and-open-source-implementation.md
ruby -e 'files=ARGV; bad=[]; files.each{|f| s=File.read(f); s.scan(/\[[^\]]+\]\((?!https?:|mailto:|#)([^)]+)\)/).flatten.each{|raw| p=raw.split("#",2)[0]; next if p.empty?; target=File.expand_path(p,File.dirname(f)); bad << "#{f}: #{raw}" unless File.exist?(target)}}; abort(bad.join("\n")) unless bad.empty?' README.md CONTRIBUTING.md THIRD_PARTY_NOTICES.md CHANGELOG.md docs/roadmap/master-roadmap.md docs/specs/README.md docs/specs/2026-08-31-github-and-open-source-design.md docs/plans/README.md docs/plans/2026-08-31-github-and-open-source-implementation.md .github/PULL_REQUEST_TEMPLATE.md .github/ISSUE_TEMPLATE/feature.md .github/ISSUE_TEMPLATE/bug.md .github/ISSUE_TEMPLATE/technical-debt.md .github/ISSUE_TEMPLATE/experiment.md
ruby -e 'ARGV.each{|f| s=File.read(f); abort("unbalanced fences: #{f}") unless s.scan(/^```/).length.even?}' README.md CONTRIBUTING.md THIRD_PARTY_NOTICES.md CHANGELOG.md docs/roadmap/master-roadmap.md docs/specs/README.md docs/specs/2026-08-31-github-and-open-source-design.md docs/plans/README.md docs/plans/2026-08-31-github-and-open-source-implementation.md .github/PULL_REQUEST_TEMPLATE.md .github/ISSUE_TEMPLATE/feature.md .github/ISSUE_TEMPLATE/bug.md .github/ISSUE_TEMPLATE/technical-debt.md .github/ISSUE_TEMPLATE/experiment.md
```

Expected: trailing-whitespace and drafting-marker searches return no matches,
all repository-relative links resolve, and fenced-code blocks are balanced.

- [x] **Step 5: Compare the exact change set with approved scope**

Run:

```bash
git status --short --untracked-files=all
git diff -- README.md CONTRIBUTING.md docs/roadmap/master-roadmap.md docs/specs/README.md docs/specs/2026-08-31-github-and-open-source-design.md docs/plans/README.md docs/plans/2026-08-31-github-and-open-source-implementation.md
```

Because Package 0-7 documentation may still be untracked, directly read every
untracked Package 7 file and use a read-only no-index diff against `/dev/null`
when a line-level review is useful. Do not infer untracked content from
`git diff` alone.

Expected: every Package 7 change maps to the approved spec and this plan, and no
unrelated user work was altered.

- [x] **Step 6: Final owner-review checkpoint**

Report changed files, exact verification outcomes, provenance limitations,
release-evidence limitations, and any checks that could not run. Stop before
Git staging, commit, push, PR, merge, tag, or release.

Expected: the only remaining gate is explicit repository-owner acceptance of
the exact Package 7 implementation change set.

## Package Verification

Package 7 is complete only after all task-level checks pass freshly and the
final report demonstrates:

1. Five public GitHub templates satisfy front-matter, evidence, security, and
   governance contracts.
2. `LICENSE` matches authoritative canonical Apache License 2.0 text exactly.
3. Third-party notices contain only verified facts and bounded limitations.
4. Changelog content reflects only verified release history.
5. README/contribution/roadmap/spec/plan routing is accurate without `R10`, CI,
   production, or release-readiness overclaims.
6. No runtime, test, dependency, CI, infrastructure, GitHub-setting, data,
   model, Git-delivery, tag, or release scope entered Package 7.
7. Repository-relative links, Markdown hygiene, drafting-marker checks, and
   sensitive-evidence scans pass.
8. `git status --short --untracked-files=all` plus direct reads/no-index diffs
   expose the complete Package 7 change set for owner review.

## Rollback

Before Git delivery, rollback removes only the five GitHub templates, `LICENSE`,
`THIRD_PARTY_NOTICES.md`, `CHANGELOG.md`, and the exact routing/traceability
edits introduced by approved Package 7 execution. Preserve unrelated work and
accepted Packages 0-6 documentation.

Do not use destructive Git history operations to roll back this package. If any
public release or third-party redistribution has occurred, license/notice
history may have legal significance and deletion is no longer a routine Package
7 rollback; stop for separately governed owner/legal/release review.

## Completion Record

Plan version 0.1 was prepared on 2026-08-31 from approved Package 7 spec version
0.1 and approved by the repository owner on 2026-08-31 via the exact phrase
`Approve Package 7 implementation plan`. The approved tasks were executed and
the Package 7 documentation passed the plan's verification checks on
2026-08-31. The repository owner accepted the exact Package 7 change set on
2026-08-31 via the conversation phrase `accept Package 7 change set`.

Fresh verification recorded for this completion includes Codebase Memory
Verify-tier coverage with direct reads for partial or not-tracked paths, valid
front matter for all four issue templates, PR-template governance and evidence
coverage, byte-for-byte Apache License 2.0 comparison against the authoritative
downloaded text, bounded third-party provenance review, no fabricated changelog
release, no credential-like values in Package 7 public content, no drafting
markers or trailing whitespace, balanced fenced code blocks, resolving
repository-relative Markdown links, and exact change-set inspection.

Repository-owner review of the exact Package 7 change set is **Accepted**.
`D7` is `Accepted in working tree`. No staging, commit, push, PR, merge, tag, or
release is authorized by this acceptance.
