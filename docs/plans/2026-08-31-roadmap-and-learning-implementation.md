# Roadmap and Learning Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence.

**Goal:** Create the approved Package 4 master roadmap and engineering
curriculum so future work has milestone order, exit gates, and a practical
learning path.

**Architecture:** Package 4 is documentation-only. It creates a roadmap as the
canonical planning gateway and a curriculum as the canonical learning gateway,
then adds only approved routing and traceability updates after those files
exist.

**Tech Stack:** Markdown, Mermaid where helpful, shell, Ruby one-line link
checker, ripgrep, and Git read-only status inspection.

**Spec:** [Roadmap and Learning Design](../specs/2026-08-31-roadmap-and-learning-design.md),
approved version 0.1.

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-08-31 |
| Approved specification | [Roadmap and Learning Design](../specs/2026-08-31-roadmap-and-learning-design.md), version 0.1 |
| Execution owner | Coding agent after explicit plan approval |
| Decision owner | Repository owner |
| Scope | `docs/roadmap/master-roadmap.md`, `docs/learning/engineering-curriculum.md`, README routing, spec index, plan index, and this plan only |
| Verification | Deterministic Markdown checks, link checks, unsupported-claim scans, full document reads, final scope review, and owner change-set review |

## Global Constraints

1. Do not execute this plan until the repository owner explicitly approves this
   exact plan.
2. Create exactly these Package 4 content files:
   - `docs/roadmap/master-roadmap.md`
   - `docs/learning/engineering-curriculum.md`
3. Modify only these existing files:
   - `README.md`
   - `docs/specs/README.md`
   - `docs/specs/2026-08-31-roadmap-and-learning-design.md`
   - `docs/plans/README.md`
   - `docs/plans/2026-08-31-roadmap-and-learning-implementation.md`
4. Do not create Package 5 evaluation protocol files, Package 6 security or
   runbook files, Package 7 GitHub/open-source files, ADR files, changelog,
   license, or third-party notice files.
5. Do not change source code, tests, dependencies, CI, Docker, environment
   files, runtime configuration, local data, generated artifacts, or Git state.
6. Do not run application tests, Docker, dependency installation, model
   downloads, crawling, indexing, external model calls, or evaluation jobs for
   Package 4 verification.
7. Do not claim runtime memory, trip workspaces, planner behavior,
   authentication, production security, production privacy, passing CI, test
   health, RAG quality, memory quality, or shipped releases as implemented.
8. Link only to files that exist after this plan is implemented. Name future
   Package 5-7 files in prose without broken Markdown links.
9. Keep technical repository documentation in English.
10. Preserve unrelated untracked or dirty files from earlier accepted packages.
11. Repository-owner review of the exact change set is required before Git
    delivery.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `docs/roadmap/master-roadmap.md` | Canonical roadmap for documentation packages, runtime milestones, dependencies, statuses, and exit gates | Approved Package 4 spec, Package 0 rollout, Package 3 architecture |
| `docs/learning/engineering-curriculum.md` | Canonical repository-owner curriculum for senior AI engineering and senior software engineering practice through Travel Agent milestones | Approved Package 4 spec, master roadmap |
| `README.md` | Add concise navigation links to the roadmap and curriculum after those files exist | New Package 4 content files |
| `docs/specs/README.md` | Keep the Package 4 spec index status accurate | Approved Package 4 spec |
| `docs/specs/2026-08-31-roadmap-and-learning-design.md` | Record the approved implementation plan and later execution status | This plan |
| `docs/plans/README.md` | Add and later update the Package 4 implementation plan index row | This plan |
| `docs/plans/2026-08-31-roadmap-and-learning-implementation.md` | Track execution checkbox state, verification evidence, completion record, and remaining owner gates | Approved Package 4 spec and owner plan approval |

## Task 1: Create Master Roadmap

**Files:**

- Create: `docs/roadmap/master-roadmap.md`
- Read: `docs/specs/2026-08-30-documentation-system-design.md`
- Read: `docs/architecture/current-state.md`
- Read: `docs/architecture/target-state.md`
- Read: `docs/architecture/data-model.md`

**Interfaces:**

- Consumes: approved Package 4 roadmap requirements and Package 3 architecture
  baseline.
- Produces: canonical milestone ids and names that the curriculum can reference.

- [x] **Step 1: Read the governing context**

Read the Package 0 rollout section and Package 3 architecture documents before
writing roadmap content.

Expected: the roadmap starts from the current prototype and does not describe
target architecture as implemented.

- [x] **Step 2: Create `docs/roadmap/master-roadmap.md`**

Write a roadmap with this exact top-level structure:

```markdown
# Master Roadmap

## Scope
## Current Phase
## Roadmap Principles
## Milestone Status Vocabulary
## Milestone Map
## Dependency Rules
## Documentation Package Roadmap
## Runtime Product Roadmap
## Evaluation and Quality Gates
## Security, Operations, and Open-source Gates
## Milestone Review Questions
## Roadmap Change Rules
```

Required milestone ids:

1. `D0` Documentation System Bootstrap.
2. `D1` Agent Operating System.
3. `D2` Project Entry Points.
4. `D3` Architecture Baseline.
5. `D4` Roadmap and Learning.
6. `D5` Evaluation Protocols.
7. `D6` Operations and Security.
8. `D7` GitHub and Open Source.
9. `R0` Foundation Cleanup.
10. `R1` RAG Repair and Baseline.
11. `R2` Evaluation Harness.
12. `R3` Trip Workspace Foundation.
13. `R4` Conversation Persistence.
14. `R5` Shadow Memory Extraction.
15. `R6` Memory Retrieval.
16. `R7` Trip Planner State.
17. `R8` Observability and Operations.
18. `R9` Security and Privacy Hardening.
19. `R10` Open-source Release Readiness.

Each milestone row must include id, title, status, dependencies, deliverables,
exit gate, and evidence.

- [x] **Step 3: Verify roadmap headings and milestone ids**

Run:

```bash
rg -n '^## (Scope|Current Phase|Roadmap Principles|Milestone Status Vocabulary|Milestone Map|Dependency Rules|Documentation Package Roadmap|Runtime Product Roadmap|Evaluation and Quality Gates|Security, Operations, and Open-source Gates|Milestone Review Questions|Roadmap Change Rules)$' docs/roadmap/master-roadmap.md
rg -n '`D[0-7]`|`R([0-9]|10)`' docs/roadmap/master-roadmap.md
```

Expected: every required heading and milestone id appears.

- [x] **Step 4: Review checkpoint**

Read the full roadmap:

```bash
sed -n '1,420p' docs/roadmap/master-roadmap.md
```

Expected: planned work is not written as release history, future package files
are not broken links, and evaluation gates precede memory/planner quality
claims.

## Task 2: Create Engineering Curriculum

**Files:**

- Create: `docs/learning/engineering-curriculum.md`
- Read: `docs/roadmap/master-roadmap.md`
- Read: `docs/specs/README.md`
- Read: `docs/plans/README.md`
- Read: `docs/adr/README.md`
- Read: `CONTRIBUTING.md`

**Interfaces:**

- Consumes: roadmap milestone ids from Task 1.
- Produces: practical learning tracks, exercises, rubrics, and operating rhythm
  for the repository owner and future coding-agent teaching.

- [x] **Step 1: Read roadmap and workflow context**

Read the roadmap and workflow indexes before writing the curriculum.

Expected: curriculum exercises reference real repository artifacts and
approved workflow gates.

- [x] **Step 2: Create `docs/learning/engineering-curriculum.md`**

Write a curriculum with this exact top-level structure:

```markdown
# Engineering Curriculum

## Scope
## Learning Principles
## How To Use This Curriculum
## Track Map
## Roadmap Alignment
## Operating Rhythm
## Learning Tracks
## Senior Review Rubrics
## Coding-agent Collaboration Practice
## Evidence Journal
## Reflection Prompts
## Curriculum Change Rules
```

Required learning tracks:

1. Repository workflow.
2. Git and GitHub.
3. Codebase reading.
4. Architecture design.
5. Testing and verification.
6. RAG engineering.
7. Agent memory.
8. Evaluation.
9. Observability.
10. Security and privacy.
11. Product thinking.
12. Release practice.

For each track, include why it matters in Travel Agent, practice exercises,
evidence to keep, beginner signals, competent signals, and senior signals.

- [x] **Step 3: Verify curriculum headings and tracks**

Run:

```bash
rg -n '^## (Scope|Learning Principles|How To Use This Curriculum|Track Map|Roadmap Alignment|Operating Rhythm|Learning Tracks|Senior Review Rubrics|Coding-agent Collaboration Practice|Evidence Journal|Reflection Prompts|Curriculum Change Rules)$' docs/learning/engineering-curriculum.md
rg -n 'Repository workflow|Git and GitHub|Codebase reading|Architecture design|Testing and verification|RAG engineering|Agent memory|Evaluation|Observability|Security and privacy|Product thinking|Release practice' docs/learning/engineering-curriculum.md
```

Expected: every required heading and learning track appears.

- [x] **Step 4: Review checkpoint**

Read the full curriculum:

```bash
sed -n '1,520p' docs/learning/engineering-curriculum.md
```

Expected: the curriculum teaches through Travel Agent artifacts, does not
authorize bypassing specs/plans/verification, and maps learning to roadmap
milestones.

## Task 3: Update Routing and Traceability

**Files:**

- Modify: `README.md`
- Modify: `docs/specs/2026-08-31-roadmap-and-learning-design.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/plans/2026-08-31-roadmap-and-learning-implementation.md`

**Interfaces:**

- Consumes: completed roadmap and curriculum files.
- Produces: discoverable links and accurate implementation metadata.

- [x] **Step 1: Update README documentation links**

Add concise links to the Documentation section:

1. `docs/roadmap/master-roadmap.md` for milestone order and gates.
2. `docs/learning/engineering-curriculum.md` for project-based engineering
   learning.

Expected: README remains a concise gateway and does not duplicate roadmap or
curriculum content.

- [x] **Step 2: Update spec implementation-plan field**

Modify `docs/specs/2026-08-31-roadmap-and-learning-design.md` so
`Implementation plan` links to
`../plans/2026-08-31-roadmap-and-learning-implementation.md`, version 0.1, with
status `(Approved; In Progress)` during execution and `(Approved; Completed)`
after final verification passes.

- [x] **Step 3: Update plan index**

Modify `docs/plans/README.md` so the Plan Index contains:

```markdown
| 2026-08-31 | Roadmap and Learning Implementation Plan | [Roadmap and Learning Design](../specs/2026-08-31-roadmap-and-learning-design.md) v0.1 | In Progress | [Plan](./2026-08-31-roadmap-and-learning-implementation.md) |
```

After final verification passes, change the status to `Completed`.

- [x] **Step 4: Update this plan state**

Update this plan's `Status`, checkbox state, and Completion Record to match
actual execution state.

Expected: metadata reflects actual execution state and does not imply Git
delivery.

## Task 4: Final Package Verification

**Files:**

- Review: `docs/roadmap/master-roadmap.md`
- Review: `docs/learning/engineering-curriculum.md`
- Review: `README.md`
- Review: `docs/specs/2026-08-31-roadmap-and-learning-design.md`
- Review: `docs/plans/README.md`
- Review: `docs/plans/2026-08-31-roadmap-and-learning-implementation.md`

**Interfaces:**

- Consumes: Tasks 1 through 3.
- Produces: evidence for repository-owner change-set review.

- [x] **Step 1: Run link checks**

Run:

```bash
ruby -e 'missing=[]; ARGV.each do |f|; dir=File.dirname(f); File.read(f).scan(/\[[^\]]+\]\(([^)]+)\)/).flatten.each do |href|; path=href.split("#",2)[0]; next if path.empty? || path =~ /^[a-z][a-z0-9+.-]*:/ || path.start_with?("mailto:"); target=File.expand_path(path, dir); missing.push("#{f} -> #{href}") unless File.exist?(target); end; end; if missing.empty?; puts "all local markdown links resolve"; else; puts missing; exit 1; end' README.md docs/roadmap/master-roadmap.md docs/learning/engineering-curriculum.md docs/specs/2026-08-31-roadmap-and-learning-design.md docs/plans/2026-08-31-roadmap-and-learning-implementation.md docs/plans/README.md
```

Expected: `all local markdown links resolve`.

- [x] **Step 2: Run Markdown quality checks**

Run:

```bash
rg -n '[[:blank:]]+$' README.md docs/roadmap/master-roadmap.md docs/learning/engineering-curriculum.md docs/specs/2026-08-31-roadmap-and-learning-design.md docs/plans/2026-08-31-roadmap-and-learning-implementation.md docs/plans/README.md
rg -n 'T''ODO|T''BD|F''IXME|X''XX|P''LACEHOLDER|\x3c[^>]+\x3e' README.md docs/roadmap/master-roadmap.md docs/learning/engineering-curriculum.md docs/specs/2026-08-31-roadmap-and-learning-design.md docs/plans/2026-08-31-roadmap-and-learning-implementation.md docs/plans/README.md
awk 'BEGIN { bad=0 } /^```/ { fences[FILENAME]++ } END { for (f in fences) { if (fences[f] % 2) { print f ": odd fence count"; bad=1 } } if (!bad) print "markdown fence counts balanced"; exit bad }' README.md docs/roadmap/master-roadmap.md docs/learning/engineering-curriculum.md docs/specs/2026-08-31-roadmap-and-learning-design.md docs/plans/2026-08-31-roadmap-and-learning-implementation.md docs/plans/README.md
```

Expected: trailing-whitespace and drafting-marker searches return no matches;
fence check reports balanced counts.

- [x] **Step 3: Run unsupported-claim checks**

Run:

```bash
rg -n 'production-ready|production ready|secure by default|SLO|SLA|tested|passing CI|coverage|licensed under|MIT|Apache|memory is implemented|trip workspace is implemented|authenticated|tenant|shipped|released' README.md docs/roadmap/master-roadmap.md docs/learning/engineering-curriculum.md docs/specs/2026-08-31-roadmap-and-learning-design.md
```

Expected: no unsupported claims. Matches are acceptable only when explicitly
describing absence, unknown status, future direction, release-history
boundaries, or limitations.

- [x] **Step 4: Run final scope review**

Run:

```bash
git status --short --untracked-files=all
sed -n '1,520p' docs/roadmap/master-roadmap.md
sed -n '1,620p' docs/learning/engineering-curriculum.md
sed -n '1,150p' README.md
sed -n '1,360p' docs/specs/2026-08-31-roadmap-and-learning-design.md
sed -n '1,680p' docs/plans/2026-08-31-roadmap-and-learning-implementation.md
```

Expected: only approved Package 4 content, routing, and traceability files are
new or changed for this package. Source, tests, dependencies, CI, Docker,
runtime configuration, data, generated artifacts, and Git delivery remain
untouched.

- [x] **Step 5: Final self-review against acceptance criteria**

Review all 13 Package 4 acceptance criteria in the approved design and record
the result in this plan's Completion Record.

Expected: every accepted criterion is met with evidence or execution stops with
the exact blocker.

- [x] **Step 6: Mark plan completed after evidence passes**

If and only if required verification passes, update this plan status to
`Completed`, update the plan index to `Completed`, update the spec
implementation-plan field to `(Approved; Completed)`, and write the Completion
Record with date, verification summary, changed files, and remaining
repository-owner change-set review gate.

## Package Verification

Execution must produce fresh evidence for:

1. Complete change set including untracked files.
2. Existence and full read of `docs/roadmap/master-roadmap.md`.
3. Existence and full read of `docs/learning/engineering-curriculum.md`.
4. Relative link resolution for every live Package 4 link.
5. Markdown trailing whitespace, drafting markers, heading structure, and fence
   balance.
6. Unsupported maturity, production, security, license, CI, test, evaluation,
   memory, workspace, authentication, tenant-isolation, SLO, shipped-release,
   and implemented-runtime claims.
7. Exact plan checkbox state and metadata matching actual execution state.
8. No Package 5-7 file creation, source changes, dependency changes, CI
   changes, Docker changes, environment changes, local data changes, generated
   artifact changes, application tests, model downloads, crawling, indexing,
   external model calls, evaluation jobs, or Git delivery actions.
9. Repository-owner review of the exact Package 4 change set before Git
   delivery.

## Rollback

Before Git delivery, rollback removes only:

1. `docs/roadmap/master-roadmap.md`
2. `docs/learning/engineering-curriculum.md`
3. Package 4 README routing edits.
4. Package 4 traceability edits in
   `docs/specs/2026-08-31-roadmap-and-learning-design.md`.
5. Package 4 plan index edits in `docs/plans/README.md`.
6. `docs/plans/2026-08-31-roadmap-and-learning-implementation.md`.

Rollback must use `apply_patch` or another non-destructive file edit method and
must not touch source code, tests, dependencies, CI, data, runtime
configuration, Git history, accepted Package 0-3 files, or unrelated untracked
files.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-08-31 via the exact
conversation phrase `Approve Package 4 implementation plan`. Approval
authorizes implementation of Package 4 documentation only. It does not
authorize runtime changes, source changes, ADR creation, evaluation protocol
creation, security or runbook creation, GitHub template creation, license
changes, data migration, dependency changes, Git staging, commit, push, PR,
merge, or release.

## Completion Record

Completed on 2026-08-31.

Changed files:

1. Added `docs/roadmap/master-roadmap.md`.
2. Added `docs/learning/engineering-curriculum.md`.
3. Updated `README.md` with concise Package 4 documentation routing links.
4. Updated `docs/specs/2026-08-31-roadmap-and-learning-design.md` to record
   this implementation plan as approved and completed.
5. Updated `docs/plans/README.md` to mark the Package 4 plan completed.
6. Updated this plan's status, task checklist, approval record, and completion
   record.

Verification summary:

1. `docs/roadmap/master-roadmap.md` was created as the canonical roadmap with
   current phase, principles, status vocabulary, milestone map, dependency
   rules, documentation package roadmap, runtime product roadmap, evaluation
   gates, security and open-source gates, review questions, and change rules.
2. `docs/learning/engineering-curriculum.md` was created as the canonical
   repository-owner engineering curriculum with learning principles, operating
   rhythm, track map, roadmap alignment, twelve learning tracks, senior review
   rubrics, coding-agent collaboration practice, evidence journal, reflection
   prompts, and change rules.
3. Roadmap heading and milestone-id checks passed for `D0` through `D7` and
   `R0` through `R10`.
4. Curriculum heading and learning-track checks passed for repository workflow,
   Git and GitHub, codebase reading, architecture design, testing and
   verification, RAG engineering, agent memory, evaluation, observability,
   security and privacy, product thinking, and release practice.
5. Local Markdown link checks resolved all Package 4 links.
6. Markdown quality checks found no trailing whitespace, no drafting markers,
   and balanced fenced-code blocks.
7. Unsupported-claim scanning produced only acceptable matches that describe
   absence, future boundaries, scan terms, or graph-tool caveats rather than
   implemented maturity.
8. Full-document reads were performed for the roadmap, curriculum, README,
   governing spec, and this implementation plan during execution.
9. Final scope review showed only approved documentation, routing, and
   traceability files in scope for this package; no Package 5-7 files, source,
   tests, dependencies, CI, Docker, environment files, runtime configuration,
   local data, generated artifacts, application tests, model downloads,
   crawling, indexing, external model calls, evaluation jobs, or Git delivery
   actions were performed.

Acceptance criteria review:

1. The master roadmap exists and is the canonical roadmap.
2. The engineering curriculum exists and is the canonical repository-owner
   engineering curriculum.
3. The roadmap separates current state, planned work, future packages, runtime
   milestones, and release-history boundaries.
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
9. Package 4 created no Package 5, Package 6, Package 7, runtime source,
   dependency, CI, Docker, environment, data, migration, or Git delivery
   changes.
10. Local Markdown link checks passed.
11. Drafting-marker, trailing-whitespace, and fence-balance checks passed.
12. Unsupported-claim scans contained no unqualified implementation,
    production-readiness, security, privacy, CI, test, evaluation, memory,
    workspace, authentication, tenant-isolation, SLO, license, or release
    claims.
13. The Package 4 spec index row, implementation plan row, plan completion
    record, and repository-owner change-set review acceptance match actual
    execution.

Repository-owner change-set review was accepted on 2026-08-31 via the exact
conversation phrase `accept Package 4 change set`.

Remaining gate: Git delivery remains with the repository owner.
