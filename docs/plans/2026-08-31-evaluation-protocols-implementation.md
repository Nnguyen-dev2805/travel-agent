# Evaluation Protocols Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence.

**Goal:** Create canonical RAG and memory evaluation protocols that define
reproducible datasets, metrics, result states, quality gates, safety gates, and
review evidence before later runtime evaluation work begins.

**Architecture:** Package 5 is documentation-only. It uses one shared
evaluation contract with separate RAG and memory protocols. The documents
describe current evaluator behavior where it exists, distinguish target
behavior from implemented behavior, and define the contract that later `R2`
runtime work must implement.

**Tech Stack:** Markdown, Codebase Memory MCP at Verify tier, direct source
reads, shell, Ruby one-line repository-link checking, ripgrep, and Git read-only
status inspection.

**Spec:** [Evaluation Protocols Design](../specs/2026-08-31-evaluation-protocols-design.md),
approved version 0.1.

| Field | Value |
| --- | --- |
| Status | Completed |
| Plan version | 0.1 |
| Date | 2026-08-31 |
| Approved specification | [Evaluation Protocols Design](../specs/2026-08-31-evaluation-protocols-design.md), version 0.1 |
| Execution owner | Coding agent after explicit plan approval |
| Decision owner | Repository owner |
| Scope | `docs/evaluation/rag-evaluation.md`, `docs/evaluation/memory-evaluation.md`, README routing, D5 roadmap status, spec-plan traceability, plan index, and this plan only |
| Verification | Codebase Memory Verify-tier evidence, direct source reads, metric-contract review, judge-contract review, memory hard-gate review, deterministic Markdown/link checks, final scope review, and owner change-set review |

## Global Constraints

1. Do not execute this plan until the repository owner explicitly approves this
   exact plan.
2. Create exactly these Package 5 content files:
   - `docs/evaluation/rag-evaluation.md`
   - `docs/evaluation/memory-evaluation.md`
3. Modify only these existing files during plan execution:
   - `README.md`
   - `docs/roadmap/master-roadmap.md`
   - `docs/specs/2026-08-31-evaluation-protocols-design.md`
   - `docs/plans/README.md`
   - `docs/plans/2026-08-31-evaluation-protocols-implementation.md`
4. Do not change evaluator source, tests, benchmark data, checkpoints,
   generated reports, RAG retrieval behavior, memory runtime, dependencies, CI,
   Docker, environment files, persistent data, or Git history.
5. Do not run application tests, crawling, indexing, model downloads, external
   model calls, LLM-judge calls, or evaluation jobs as Package 5 acceptance
   evidence.
6. Treat the current evaluator as evidence of implemented behavior, not as the
   protocol. Clearly label required behavior that the current code does not yet
   implement.
7. Do not claim the current RAG benchmark is reproducible while referenced
   evaluation datasets or report artifacts are absent.
8. Never document malformed judge output, infrastructure failure, or missing
   data as a favorable score or implicit candidate win.
9. Keep memory hard gates non-compensating. Aggregate quality scores cannot
   offset a leakage, deletion, secret-like promotion, or correction-precedence
   failure.
10. Use synthetic, public, or redacted fixtures as the default evaluation-data
    policy; do not introduce real credentials or unnecessary sensitive data.
11. Keep technical repository documentation in English.
12. Preserve unrelated untracked or dirty files from earlier packages.
13. Repository-owner review of the exact implementation change set is required
    before any Git delivery action.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `docs/evaluation/rag-evaluation.md` | Canonical protocol for RAG retrieval, answer quality, judge use, datasets, result states, failure taxonomy, and promotion gates | Approved Package 5 spec, current evaluator evidence |
| `docs/evaluation/memory-evaluation.md` | Canonical protocol for memory extraction, promotion, retrieval, use, conflict, correction, deletion, scope, privacy, and hard gates | Approved Package 5 spec, target memory architecture |
| `README.md` | Add concise navigation to the two evaluation protocols after they exist | Both protocol files |
| `docs/roadmap/master-roadmap.md` | Mark `D5` as in progress during approved execution without claiming owner acceptance | Approved plan and created protocol files |
| `docs/specs/2026-08-31-evaluation-protocols-design.md` | Record the Package 5 implementation-plan link and execution status | This plan |
| `docs/plans/README.md` | Index this plan and keep its lifecycle state accurate | This plan |
| `docs/plans/2026-08-31-evaluation-protocols-implementation.md` | Track approved tasks, checkbox evidence, verification, completion record, and remaining owner gate | Approved Package 5 spec and owner plan approval |

## Task 1: Establish Current Evaluation Evidence

**Files:**

- Read: `backend/rag/evaluation/evaluator.py`
- Read: `backend/rag/evaluation/llm_judge_evaluator.py`
- Read: `backend/tests/unit/test_evaluator.py`
- Read: `docs/architecture/target-state.md`
- Read: `docs/architecture/data-model.md`
- Read: `docs/roadmap/master-roadmap.md`
- Read: `docs/specs/2026-08-31-evaluation-protocols-design.md`

**Interfaces:**

- Consumes: approved spec plus current evaluator, architecture, and roadmap
  evidence.
- Produces: verified current-state facts and limitations used by Tasks 2 and 3.

- [x] **Step 1: Refresh Codebase Memory evidence at Verify tier**

Confirm the active graph project and generation. Use structural graph search to
locate the retrieval evaluator and LLM-judge evaluator, inspect material
symbols, and trace relevant relationships where useful. Call index coverage
checking once for every relied-on code path.

Expected: current evaluator symbols and coverage state are recorded before any
protocol claims are written. Any missed, stale, partial, or unknown range is
read directly before relying on it.

- [x] **Step 2: Read material source directly**

Run:

```bash
sed -n '1,360p' backend/rag/evaluation/evaluator.py
sed -n '1,420p' backend/rag/evaluation/llm_judge_evaluator.py
sed -n '1,320p' backend/tests/unit/test_evaluator.py
```

Expected: metric formulas, K handling, strategy assumptions, judge schema,
temperature, parse behavior, and test coverage used by the protocol are
confirmed from source.

- [x] **Step 3: Check referenced evaluation artifacts directly**

Run:

```bash
for path in data/evaluation docs/reports; do
  if [ -d "$path" ]; then
    find "$path" -maxdepth 3 -type f -print
  else
    printf 'ABSENT %s\n' "$path"
  fi
done
find backend -type f \( -name '*evaluation*' -o -name '*checkpoint*' -o -name '*report*' \) -print
```

Expected: absent artifacts remain documented as absent; newly discovered
artifacts are reviewed before any reproducibility statement changes.

- [x] **Step 4: Review checkpoint**

Review the evidence against the spec's Current-state Evidence and Verification
sections.

Expected: no material spec assumption has changed. If an assumption differs,
stop and return to specification review before writing protocols.

## Task 2: Create Canonical RAG Evaluation Protocol

**Files:**

- Create: `docs/evaluation/rag-evaluation.md`
- Read: evidence from Task 1
- Read: `docs/specs/2026-08-31-evaluation-protocols-design.md`

**Interfaces:**

- Consumes: verified current evaluator evidence and the shared Package 5
  evaluation contract.
- Produces: canonical RAG protocol and shared vocabulary that Task 3 must reuse.

- [x] **Step 1: Create `docs/evaluation/rag-evaluation.md`**

Use this top-level structure:

```markdown
# RAG Evaluation Protocol

## Scope
## Current-state Limitations
## Evaluation Principles
## Dataset Contract
## Run and Report Contract
## Result States
## Retrieval Evaluation
## Answer-quality Evaluation
## LLM-as-a-Judge Contract
## Mandatory Slices
## Quality Gates
## Failure Taxonomy
## Invalid and Inconclusive Evidence
## Regression Dataset Lifecycle
## Security and Privacy
## R2 Harness Contract
## Review Checklist
## Protocol Change Rules
```

The protocol must define:

1. Development, regression, benchmark, and safety dataset roles.
2. Required dataset/run identity and provenance metadata.
3. `PASS`, `FAIL`, `INCONCLUSIVE`, and `INVALID` semantics.
4. Retrieval and answer-quality evaluation as separate layers.
5. Hit@K, MRR@K, nDCG@K, Precision@K, source URL hit, relevant chunk
   count, and unique document count semantics.
6. Primary retrieval comparison at `K=5` with diagnostic K values separated.
7. Groundedness, answer relevance, correctness, completeness, practical
   usefulness, and clarity.
8. Frozen-baseline, no-regression, improvement, slice, and hard-review rules
   exactly matching the approved spec.
9. Strict LLM-judge schema validation, calibration, pairwise position handling,
   and zero synthetic fallback scoring.
10. Missing current datasets/reports and unsafe legacy judge fallback as
    explicit current limitations.
11. Shared failure labels and per-example evidence requirements.
12. The later `R2` harness contract without choosing storage or vendor details.

- [x] **Step 2: Verify RAG metric contracts**

Create a review table inside the document or review notes covering every gated
metric with: name, definition/formula, direction, unit/range, comparison basis,
primary slice, threshold, and invalid-data behavior.

Expected: no promotion metric depends on an undefined denominator, implicit K,
unversioned judge prompt, or favorable error fallback.

- [x] **Step 3: Verify headings and required terms**

Run:

```bash
rg -n '^## (Scope|Current-state Limitations|Evaluation Principles|Dataset Contract|Run and Report Contract|Result States|Retrieval Evaluation|Answer-quality Evaluation|LLM-as-a-Judge Contract|Mandatory Slices|Quality Gates|Failure Taxonomy|Invalid and Inconclusive Evidence|Regression Dataset Lifecycle|Security and Privacy|R2 Harness Contract|Review Checklist|Protocol Change Rules)$' docs/evaluation/rag-evaluation.md
rg -n 'Hit@5|MRR@5|nDCG@5|groundedness|PASS|FAIL|INCONCLUSIVE|INVALID|judge_invalid|synthetic fallback|benchmark|regression|safety' docs/evaluation/rag-evaluation.md
```

Expected: every required section and governing concept is present.

- [x] **Step 4: Review checkpoint**

Read the full RAG protocol and compare every implemented-behavior claim with
Task 1 source evidence.

Expected: retrieval and answer quality remain separate, current limitations are
explicit, and target behavior is not presented as already implemented.

## Task 3: Create Canonical Memory Evaluation Protocol

**Files:**

- Create: `docs/evaluation/memory-evaluation.md`
- Read: `docs/evaluation/rag-evaluation.md`
- Read: `docs/architecture/target-state.md`
- Read: `docs/architecture/data-model.md`
- Read: `docs/specs/2026-08-31-evaluation-protocols-design.md`

**Interfaces:**

- Consumes: shared vocabulary from Task 2 plus approved future memory
  architecture concepts.
- Produces: canonical memory quality and safety protocol.

- [x] **Step 1: Create `docs/evaluation/memory-evaluation.md`**

Use this top-level structure:

```markdown
# Memory Evaluation Protocol

## Scope
## Preconditions and Current-state Limitations
## Evaluation Principles
## Dataset Contract
## Run and Report Contract
## Result States
## Memory Lifecycle Evaluation
## Hard Safety Gates
## Quality Gates
## Mandatory Slices
## Conflict, Correction, Deletion, and Scope Scenarios
## Failure Taxonomy
## Invalid and Inconclusive Evidence
## Security and Synthetic Fixtures
## Regression Dataset Lifecycle
## R2 Harness Contract
## Review Checklist
## Protocol Change Rules
```

Within `Memory Lifecycle Evaluation`, define separate evaluation for:

1. Candidate extraction.
2. Promotion policy.
3. Retrieval.
4. Use in the answer.
5. Conflict, correction, deletion, expiration, scope, and safety.

The protocol must preserve the approved hard gates:

1. Cross-user memory leakage count = `0`.
2. Cross-workspace leakage for trip-scoped memory = `0`.
3. Deleted-memory retrieval count after confirmed deletion = `0`.
4. Controlled secret-like durable promotion count = `0`.
5. Older inferred memory overriding an explicit correction = `0`.

It must also preserve the initial quality thresholds from the spec, including
candidate extraction precision/recall, scope accuracy, promotion precision,
Memory Hit@5, irrelevant-memory rate, personalization win rate, and constraint
satisfaction no-regression.

- [x] **Step 2: Verify shared-contract consistency**

Compare RAG and memory protocol definitions for dataset roles, run metadata,
result states, failure-record requirements, regression lifecycle, and invalid
evidence semantics.

Expected: shared concepts have one meaning across both documents while
domain-specific metrics remain separate.

- [x] **Step 3: Verify memory hard gates and quality thresholds**

Run:

```bash
rg -n 'cross-user|cross-workspace|deleted-memory|secret-like|explicit correction|0\.95|0\.90|0\.98|0\.97|Hit@5|0\.10|0\.60' docs/evaluation/memory-evaluation.md
rg -n 'PASS|FAIL|INCONCLUSIVE|INVALID|development|regression|benchmark|safety' docs/evaluation/memory-evaluation.md
```

Expected: every zero-tolerance gate and initial quality threshold is visible,
and no aggregate score can compensate for a hard-gate failure.

- [x] **Step 4: Review checkpoint**

Read the complete memory protocol against target architecture and the approved
Package 5 spec.

Expected: future memory behavior is clearly labeled as protocol target, no
runtime memory implementation is implied, and privacy tests use controlled
synthetic identities and secret-like fixtures.

## Task 4: Add Routing, Roadmap, and Traceability

**Files:**

- Modify: `README.md`
- Modify: `docs/roadmap/master-roadmap.md`
- Modify: `docs/specs/2026-08-31-evaluation-protocols-design.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/plans/2026-08-31-evaluation-protocols-implementation.md`

**Interfaces:**

- Consumes: completed protocol documents from Tasks 2 and 3.
- Produces: discoverable canonical links and accurate Package 5 lifecycle
  metadata.

- [x] **Step 1: Add README evaluation links**

Add concise links under `## Documentation` to:

1. `docs/evaluation/rag-evaluation.md` for RAG quality measurement.
2. `docs/evaluation/memory-evaluation.md` for memory quality and safety
   measurement.

Expected: README remains a gateway and does not duplicate protocol content.

- [x] **Step 2: Update D5 roadmap status**

Change only the `D5` milestone status from `Planned` to `In progress` and update
its recommended next action to reflect protocol implementation/review. Do not
mark `D5` as `Accepted in working tree` until the repository owner accepts the
exact Package 5 change set.

Expected: downstream runtime milestones remain blocked by their existing gates.

- [x] **Step 3: Update spec-plan traceability**

Update the Package 5 spec `Implementation plan` field to link this plan as
version 0.1 with its current lifecycle status. After execution verification,
record that implementation is complete but owner change-set acceptance remains.

Expected: spec approval remains unchanged and no new architecture approval is
invented for this Level 2 package.

- [x] **Step 4: Update plan index and lifecycle**

Keep the Package 5 row in `docs/plans/README.md` synchronized with this plan.
During approved execution use `In Progress`; after all verification passes use
`Completed` while explicitly retaining the repository-owner change-set review
gate.

Expected: plan lifecycle describes work performed, not Git delivery or owner
acceptance.

- [x] **Step 5: Review checkpoint**

Review all routing and status edits.

Expected: every added link resolves, `D5` is not prematurely accepted, and no
Package 6/7 or runtime milestone status changes are introduced.

## Task 5: Package Verification and Owner Review Gate

**Files:**

- Read: every file in the File Responsibility Map
- Read: `backend/rag/evaluation/evaluator.py`
- Read: `backend/rag/evaluation/llm_judge_evaluator.py`
- Read: `backend/tests/unit/test_evaluator.py`

**Interfaces:**

- Consumes: Tasks 1-4 outputs.
- Produces: deterministic evidence for the repository-owner Package 5
  change-set review.

- [x] **Step 1: Run drafting-marker and Markdown checks**

Run:

```bash
rg -n 'TO''DO|TB''D|PLACE''HOLDER|\[Exact'' path\]|\[One'' action\]|\[YYYY''-MM-DD\]' docs/evaluation docs/plans/2026-08-31-evaluation-protocols-implementation.md
rg -n '[[:blank:]]+$' docs/evaluation/rag-evaluation.md docs/evaluation/memory-evaluation.md docs/plans/2026-08-31-evaluation-protocols-implementation.md README.md docs/roadmap/master-roadmap.md docs/specs/2026-08-31-evaluation-protocols-design.md docs/plans/README.md
```

Expected: no unresolved drafting markers or trailing whitespace in Package 5
content. Intentional template text outside Package 5 scope is ignored.

- [x] **Step 2: Resolve repository-relative Markdown links**

Run:

```bash
ruby -e 'missing=[]; ARGV.each do |f|; dir=File.dirname(f); File.read(f).scan(/\[[^\]]+\]\(([^)]+)\)/).flatten.each do |href|; path=href.split("#",2)[0]; next if path.empty? || path =~ /^[a-z][a-z0-9+.-]*:/ || path.start_with?("mailto:"); target=File.expand_path(path, dir); missing.push("#{f} -> #{href}") unless File.exist?(target); end; end; if missing.empty?; puts "all local markdown links resolve"; else; puts missing; exit 1; end' README.md docs/roadmap/master-roadmap.md docs/evaluation/rag-evaluation.md docs/evaluation/memory-evaluation.md docs/specs/2026-08-31-evaluation-protocols-design.md docs/plans/2026-08-31-evaluation-protocols-implementation.md docs/plans/README.md
```

Expected: `all local markdown links resolve`.

- [x] **Step 3: Perform metric-definition review**

Review every RAG and memory promotion metric for:

1. Name.
2. Formula or operational definition.
3. Direction of improvement.
4. Unit or score range.
5. Comparison basis.
6. Primary K or slice where applicable.
7. Threshold or hard invariant.
8. Invalid-data behavior.

Expected: every gate is reproducible from the protocol and no undefined score
can decide promotion.

- [x] **Step 4: Perform judge-contract review**

Compare the RAG judge contract with the current LLM-judge source and scan both
protocols for fallback/error wording.

Expected: current favorable parse fallback is named only as a limitation; the
target protocol has no path that converts malformed or unavailable judge
evidence into favorable scores.

- [x] **Step 5: Perform memory hard-gate review**

Read every safety-gate and result-state section together.

Expected: one cross-user leakage, trip-scope leakage, deleted-memory retrieval,
controlled secret-like promotion, or explicit-correction precedence failure is
visible as a non-compensating promotion failure.

- [x] **Step 6: Verify no forbidden Package 5 artifacts were created**

Run:

```bash
git status --short --untracked-files=all
for path in data/evaluation docs/reports; do
  if [ -d "$path" ]; then
    find "$path" -maxdepth 3 -type f -print
  else
    printf 'ABSENT %s\n' "$path"
  fi
done
```

Expected: Package 5 adds no benchmark data, generated reports, checkpoints,
runtime code, dependency files, CI files, Docker files, environment files, or
persistent runtime data.

- [x] **Step 7: Review the complete Package 5 change set**

Use `git status --short --untracked-files=all`, direct full-file reads for
untracked Package 5 files, and read-only diffs where available. Do not rely on
`git diff` alone because current documentation files may be untracked.

Expected: changes are bounded to the File Responsibility Map and preserve
unrelated work.

- [x] **Step 8: Stop for repository-owner change-set review**

Report changed files, Codebase Memory coverage evidence, direct-source evidence,
metric/judge/hard-gate review outcomes, deterministic documentation checks, and
all limitations.

Expected: no Git staging, commit, push, PR, merge, release, or D5 owner-accepted
status is performed before the repository owner explicitly accepts the exact
Package 5 change set.

## Package Verification

Package 5 is ready for owner review only when all of the following are true:

1. Both canonical protocol files exist.
2. Current evaluator claims were reverified with Codebase Memory at Verify tier
   plus direct source reads and index-coverage handling.
3. RAG retrieval and answer-quality evaluation remain separate.
4. Both documents use the same dataset roles, run/report contract, result-state
   vocabulary, regression lifecycle, and invalid-evidence semantics.
5. Every gated metric has a complete operational definition and threshold.
6. Judge failure cannot produce favorable evidence.
7. Memory hard gates remain zero-tolerance and non-compensating.
8. Current missing evaluation artifacts are disclosed rather than silently
   substituted.
9. All links and deterministic Markdown checks pass.
10. The exact change set is within the approved documentation-only scope.
11. No runtime quality claim is made and no evaluation job is required for
    Package 5 acceptance.
12. Repository-owner change-set review remains open.

## Rollback

Before Git delivery, rollback removes the two Package 5 protocol files and
reverts only Package 5 routing, D5 status, spec-plan traceability, plan-index,
and plan-lifecycle edits. Preserve all unrelated Package 0-4 work and user
changes. Do not alter evaluator source, tests, benchmark data, Chroma state,
dependencies, Docker state, environment files, or Git history.

## Completion Record

Plan version 0.1 was prepared after approval of
[Evaluation Protocols Design](../specs/2026-08-31-evaluation-protocols-design.md)
version 0.1. The repository owner approved this exact implementation plan on
2026-08-31 via the conversation phrase `Approve Package 5 implementation plan`.
Implementation and verification are **Completed** under that approval. The
repository owner accepted the exact Package 5 change set on 2026-08-31 via the
conversation phrase `accept Package 5 change set`. Package 5 is therefore
accepted in the working tree. This acceptance does not authorize runtime
changes, evaluation runs, data generation, Git staging, commit, push, PR,
merge, or release.
