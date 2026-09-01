# Engineering Curriculum

## Scope

This curriculum is the canonical repository-owner learning guide for Travel
Agent. It teaches senior AI engineering and senior software engineering
practice through this repository's milestones, artifacts, reviews, and
verification habits.

This is educational guidance. It does not authorize bypassing approved
specifications, implementation plans, ADRs, verification, repository-owner
change-set review, or Git delivery control.

Use [Master Roadmap](../roadmap/master-roadmap.md) for milestone order,
[Specifications](../specs/README.md) for design approval,
[Implementation Plans](../plans/README.md) for execution planning, and
[Architecture Decision Records](../adr/README.md) for durable decisions.

## Learning Principles

1. Learn by changing the real project in small approved units.
2. Treat evidence as a habit, not a final ceremony.
3. Separate current state, target design, and implementation.
4. Prefer clear interfaces over clever code.
5. Make quality measurable before trying to optimize it.
6. Review trade-offs before tools and libraries become commitments.
7. Keep privacy, secrets, and user trust visible in every memory decision.
8. Use coding agents as collaborators whose work still needs human review.

## How To Use This Curriculum

Use this curriculum in milestone cycles:

1. Pick the next milestone from the roadmap.
2. Read its governing docs and exit gate.
3. Study the tracks that map to that milestone.
4. Draft the spec or plan with an agent.
5. Implement only after approval.
6. Run the required verification.
7. Write a short evidence journal entry.
8. Review what improved in your engineering judgment.

The goal is not to finish every lesson before coding. The goal is to attach the
right lesson to the work that needs it.

## Track Map

| Track | Main skill | Primary milestones |
| --- | --- | --- |
| Repository workflow | Scope, approvals, evidence, rollback | `D0`, `D1`, `D4`, all runtime milestones |
| Git and GitHub | Branches, commits, PRs, review hygiene | `D7`, `R0`, `R10` |
| Infrastructure and Operations | Docker, CI, env contracts, dependencies, command evidence, local recovery | `R0`, `R8`, `R10` |
| Codebase reading | Finding behavior before editing it | `D2`, `D3`, `R0`, `R1` |
| Architecture design | Boundaries, dependencies, ADRs | `D3`, `R3`, `R5`, `R6`, `R7` |
| Testing and verification | Cheap checks, regression datasets, gates | `R0`, `R1`, `R2`, `R7` |
| RAG engineering | Retrieval, chunking, grounding, citations | `D5`, `R1`, `R2` |
| Agent memory | Extraction, promotion, retrieval, deletion | `D5`, `R5`, `R6`, `R9` |
| Evaluation | Metrics, judges, datasets, failure labels | `D5`, `R1`, `R2`, `R5`, `R6`, `R7` |
| Observability | Logs, traces, dashboards, runbooks | `D6`, `R8` |
| Security and privacy | Secrets, data boundaries, sensitive memory | `D6`, `R9`, `R10` |
| Product thinking | User value, trip workflow, decision design | `R3`, `R4`, `R7` |
| Release practice | Packaging, notes, contribution readiness | `D7`, `R10` |

## Roadmap Alignment

| Phase | Milestones | Learning focus |
| --- | --- | --- |
| Documentation foundation | `D0` to `D4` | Governance, current-state reading, target-state thinking, review evidence |
| Evaluation foundation | `D5`, `R1`, `R2` | RAG metrics, memory metrics, trace design, regression discipline |
| Product foundation | `R3`, `R4`, `R7` | Trip workspaces, conversation state, planner operations, user corrections |
| Memory foundation | `R5`, `R6` | Candidate extraction, promotion policy, retrieval utility, privacy behavior |
| Operations foundation | `D6`, `R8`, `R9` | Runbooks, degraded behavior, secrets, deletion, incident response |
| Open-source foundation | `D7`, `R10` | License, notices, issue intake, PR review, release readiness |

## Operating Rhythm

Use this weekly or milestone rhythm:

1. Monday: choose one milestone or one approved task.
2. Tuesday: read current evidence and write the smallest useful spec or plan.
3. Wednesday: implement or review one bounded change.
4. Thursday: run verification and inspect failures without rushing fixes.
5. Friday: write an evidence journal entry and identify one lesson for the next
   cycle.

For heavier milestones, stretch the same rhythm across two or more weeks. Keep
the loop visible: problem, design, plan, implementation, verification, review,
and learning.

## Learning Tracks

### Repository workflow

Why it matters in Travel Agent: memory and planner systems have many tempting
shortcuts. Workflow keeps each change small, approved, measurable, and
reversible.

Practice exercises:

1. Classify three proposed changes as Level 1, Level 2, or Level 3.
2. For one milestone, list scope, non-goals, stop conditions, and rollback.
3. Review a plan and find one ambiguity before implementation starts.

Evidence to keep: approved spec, approved plan, verification output, final
change-set review note, and a short lesson learned.

Beginner signal: can follow the checklist when prompted.

Competent signal: can explain why a change needs a spec, ADR, or smaller scope.

Senior signal: detects hidden scope early and returns to design before wasteful
implementation begins.

### Git and GitHub

Why it matters in Travel Agent: open-source work needs reviewable history and
clean collaboration, especially when agents generate large changes quickly.

Practice exercises:

1. Create a branch name and Conventional Commit message for a planned milestone.
2. Review `git status --short --untracked-files=all` before and after a docs
   change.
3. Draft a PR summary with changed files, verification, risks, and rollback.

Evidence to keep: branch name, commit message draft, PR draft, status snapshot,
and review checklist.

Beginner signal: can avoid destructive Git commands and read status output.

Competent signal: can group changes into atomic commits and explain each one.

Senior signal: preserves unrelated work, keeps history reviewable, and refuses
to hide failing evidence.

### Infrastructure and Operations

Why it matters in Travel Agent: AI agents can write code quickly, but the
project only becomes dependable when setup, CI, containers, dependencies,
environment contracts, and recovery steps are honest and repeatable.

Practice exercises:

1. Inspect the CI workflow and mark every command that can hide a failure.
2. Draw the Stage A local stack: browser, frontend, backend, health route, data
   mount, and environment file.
3. Compare `requirements.txt`, `backend/requirements.txt`, backend Docker
   installs, and CI installs, then state the approved dependency owner.
4. Run the baseline verification commands and classify each result as pass,
   expected current failure, environment failure, regression, or opt-in
   prerequisite.
5. Update one runbook entry after a real failed local command.
6. Write a short evidence journal entry for the R0 change set.

Evidence to keep: approved R0 spec and plan, command output summaries, CI
workflow diff, safe `.env.example`, dependency ownership note, Stage A and
Stage B command taxonomy, and one evidence journal entry.

Beginner signal: can run setup commands and identify whether a failure is from
the repo, local environment, or missing prerequisite.

Competent signal: can read CI, Docker, dependency, and env contracts and
explain what each check proves.

Senior signal: designs checks that fail honestly, keeps deployment and release
claims separate from local development, and records enough evidence for the
next engineer to reproduce the result.

### Evidence Journal Entry

| Field | Entry |
| --- | --- |
| Date | 2026-09-01 |
| Milestone | R0 Foundation Cleanup |
| Environment | Local shell, Docker, CI, or sandbox |
| Command or review | Exact command or review method |
| Result | Passed, failed, skipped, or blocked |
| Failure class | Current-state defect, regression, environment limitation, or expected opt-in prerequisite |
| Evidence summary | Short factual result |
| Next action | Repair, document, defer, or return to design |

### Codebase reading

Why it matters in Travel Agent: the current RAG path already has behavior and
risks. Senior work starts by reading the system instead of guessing.

Practice exercises:

1. Trace the chat flow from frontend request to backend response.
2. Compare a documentation claim with exact source or configuration evidence.
3. Identify one module that owns too many responsibilities and propose a
   smaller boundary.

Evidence to keep: source paths, commands, snippets, coverage caveats when using
graph tools, and notes on uncertainty.

Beginner signal: can find relevant files with guidance.

Competent signal: can explain the implemented flow with caveats.

Senior signal: can separate executable evidence from assumptions and design a
safe next step.

### Architecture design

Why it matters in Travel Agent: trip workspace, memory, retrieval, planner, and
generation must not collapse into one large service.

Practice exercises:

1. Draw the dependency direction for one future milestone.
2. Write an ADR outline for storage ownership or memory promotion policy.
3. Identify which interface hides a provider, store, or model choice.

Evidence to keep: diagrams, alternatives, ADR drafts, rejected options, and
compatibility notes.

Beginner signal: can name components.

Competent signal: can explain responsibilities and dependencies.

Senior signal: can choose boundaries that preserve testability, rollback, and
future provider changes.

### Testing and verification

Why it matters in Travel Agent: agent behavior can appear good in one chat and
fail systematically across a dataset.

Practice exercises:

1. Convert a bug or bad answer into a regression case.
2. Define which command proves one acceptance criterion.
3. Separate health readiness, chat readiness, and quality evidence.

Evidence to keep: commands, exit status, fixture data, failing examples,
passing examples, and skipped checks.

Beginner signal: can run a provided command and paste the result.

Competent signal: can choose the right check for a claim.

Senior signal: designs gates that catch regressions before behavior is
promoted.

### RAG engineering

Why it matters in Travel Agent: travel answers need useful retrieval,
grounded responses, and source-aware citations before personalization is added.

Practice exercises:

1. Compare baseline chunks and parent-child chunks on the same questions.
2. Label retrieval misses, citation problems, and unsupported answer claims.
3. Define a small golden set for Vietnam travel questions.

Evidence to keep: queries, retrieved chunks, answer claims, citation metadata,
failure labels, and metric summaries.

Beginner signal: can explain embedding, retrieval, context, and generation.

Competent signal: can diagnose retrieval versus generation failures.

Senior signal: improves retrieval with fixed baselines and avoids optimizing
only for one attractive demo.

### Agent memory

Why it matters in Travel Agent: memory can make the assistant personal, but it
can also preserve wrong, sensitive, stale, or over-scoped facts.

Practice exercises:

1. Classify memory candidates by scope: user, trip, conversation, global
   knowledge, or evaluation run.
2. Decide which candidates should be accepted, rejected, or sent to user
   review.
3. Compare memory retrieval with and without newer user correction.

Evidence to keep: memory candidates, policy decisions, confidence, provenance,
retention state, rejection reasons, and trace samples.

Beginner signal: can distinguish memory from travel knowledge.

Competent signal: can design read and write paths separately.

Senior signal: promotes only useful, scoped, provenance-backed memory and keeps
deletion behavior visible.

### Evaluation

Why it matters in Travel Agent: the project goal is not just to build memory,
but to prove when memory improves travel assistance.

Practice exercises:

1. Write a metric rubric for groundedness, relevance, personalization, or
   privacy behavior.
2. Create a failure taxonomy for RAG, memory, and planner mistakes.
3. Compare two runs and explain whether the newer one is better.

Evidence to keep: dataset version, run id, model name, selected context,
scores, failure labels, and promotion decision.

Beginner signal: can read an evaluation report.

Competent signal: can interpret failures and propose focused fixes.

Senior signal: defines metrics that guide product decisions without hiding
qualitative judgment.

### Observability

Why it matters in Travel Agent: once memory and planner state exist, failures
need to be visible after the chat turn ends.

Practice exercises:

1. Define what a trace should record for one chat request.
2. Design log fields that help debugging without exposing secrets.
3. Write a degraded-mode runbook outline for model, retrieval, or memory
   failures.

Evidence to keep: trace schema notes, sample redacted logs, failure scenarios,
and operator questions.

Beginner signal: can distinguish logs, metrics, and traces.

Competent signal: can connect a symptom to the right diagnostic evidence.

Senior signal: designs observability that supports debugging, evaluation, and
privacy at the same time.

### Security and privacy

Why it matters in Travel Agent: travel planning can involve personal
preferences, budgets, dates, constraints, and sensitive context.

Practice exercises:

1. Identify which fields in the data model can contain personal information.
2. Decide what must be redacted from logs and traces.
3. Review a memory candidate that should not become durable memory.

Evidence to keep: data classification notes, redaction examples, deletion
semantics, and security review notes.

Beginner signal: can keep real secrets out of docs and logs.

Competent signal: can classify data and name trust boundaries.

Senior signal: designs privacy controls before expanding user-data scope.

### Product thinking

Why it matters in Travel Agent: the agent should help users plan trips, not
just demonstrate technical memory.

Practice exercises:

1. Write a trip workspace user story with success and failure outcomes.
2. Compare global user memory, trip-scoped memory, and rejected decisions for a
   planning scenario.
3. Define what the user should be able to inspect, edit, or delete.

Evidence to keep: user story, workflow sketch, accepted decisions, rejected
decisions, and product risk notes.

Beginner signal: can describe the feature from the user's perspective.

Competent signal: can turn user needs into explicit state and contracts.

Senior signal: cuts attractive features that do not improve the planning job or
cannot be evaluated.

### Release practice

Why it matters in Travel Agent: an open-source repository needs clear license,
notices, contribution flow, and honest maturity language before wider sharing.

Practice exercises:

1. Draft release notes that separate changes from future direction.
2. Review third-party dependency and dataset attribution needs.
3. Prepare a PR checklist for a milestone.

Evidence to keep: release note draft, attribution notes, PR checklist, and
remaining risk list.

Beginner signal: can describe what changed.

Competent signal: can prepare review material that another contributor can
follow.

Senior signal: communicates maturity honestly and does not let packaging imply
product readiness.

## Senior Review Rubrics

Use these rubrics during milestone review:

| Area | Beginner | Competent | Senior |
| --- | --- | --- | --- |
| Scope | Accepts broad tasks | Narrows tasks with help | Defines small reversible review units |
| Evidence | Runs requested checks | Maps checks to claims | Designs evidence before implementation |
| Architecture | Names components | Explains boundaries | Protects dependency direction and rollback |
| RAG | Knows retrieval steps | Diagnoses failure type | Uses baselines and datasets before tuning |
| Memory | Stores facts | Separates scopes | Controls promotion, provenance, privacy, and decay |
| Agent use | Accepts generated output | Reviews agent work | Directs agents with specs, gates, and critique |
| Communication | Reports activity | Reports results | Reports evidence, risk, and decision options |

## Coding-agent Collaboration Practice

Practice these habits with every agent-assisted milestone:

1. Give the agent the approved spec and plan before implementation.
2. Ask the agent to state scope, non-goals, and stop conditions.
3. Require fresh verification before completion claims.
4. Review untracked files, not just diffs.
5. Ask for alternatives when the agent proposes a hard-to-reverse choice.
6. Treat agent confidence as a prompt for evidence, not as evidence.
7. Keep final approval and Git delivery as repository-owner decisions.

## Evidence Journal

After each milestone, record:

| Field | Prompt |
| --- | --- |
| Date | When did the review happen? |
| Milestone | Which roadmap id was touched? |
| Claim | What changed or was learned? |
| Evidence | Which commands, files, or reviews support the claim? |
| Limitation | What was not proved? |
| Skill practiced | Which curriculum track improved? |
| Next question | What should be clarified before the next milestone? |

The journal can live in an issue, PR description, or future learning note. Do
not store secrets or sensitive personal data in it.

## Reflection Prompts

Use these prompts during weekly or milestone review:

1. What did I assume before reading the code or docs?
2. Which claim needed stronger evidence?
3. Where did scope try to expand?
4. What did the agent do well, and what needed correction?
5. Which decision should have become an ADR?
6. What failure would my current tests or evaluation miss?
7. What should be easier for a future contributor?
8. What skill moved from beginner toward competent this week?

## Curriculum Change Rules

1. Small wording clarifications can be included in the same reviewed change that
   improves a related document.
2. Adding, removing, or reordering tracks requires the normal spec and
   implementation-plan workflow.
3. Curriculum exercises must remain tied to Travel Agent artifacts.
4. Future links may be added only when the linked files exist.
5. The curriculum must stay educational and must not become an alternate
   authority for implementation approval.
