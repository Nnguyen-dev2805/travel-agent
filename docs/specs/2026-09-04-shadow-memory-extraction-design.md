# Shadow Memory Extraction Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-04 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Runtime milestone R5 - shadow memory candidate extraction from persisted conversations, memory candidate policy, local candidate persistence, inspection routes, and evaluation reports with no answer-time memory retrieval |
| Parent design | [Architecture Baseline Design](./2026-08-31-architecture-baseline-design.md), version 0.1; [Roadmap and Learning Design](./2026-08-31-roadmap-and-learning-design.md), version 0.1 |
| Depends on | R2 evaluation harness; R4 delivered at `e590ca6`; [Conversation Persistence Design](./2026-09-04-conversation-persistence-design.md), version 0.1; [ADR 0004](../adr/0004-shared-local-application-store-and-per-module-schema-registry.md); [ADR 0005](../adr/0005-conversation-orchestration-seam-and-optional-chat-binding.md); [Memory Evaluation Protocol](../evaluation/memory-evaluation.md); [Security Policy](../../SECURITY.md) |
| Architecture approval | Repository owner approved this spec version 0.1 and accepted [ADR 0006](../adr/0006-shadow-memory-candidate-store-and-policy-boundary.md) in conversation on 2026-09-04 |
| Implementation plan | [Shadow Memory Extraction Implementation Plan](../plans/2026-09-04-shadow-memory-extraction-implementation.md), version 0.1 (Approved) |
| Related issue | None - R5 specification drafting was authorized by the repository owner in conversation on 2026-09-04 |
| Superseded document | None |

## Summary

R5 introduces shadow memory extraction. The system will inspect persisted
conversation messages, propose memory candidates, classify their scope, type,
confidence, sensitivity, and policy result, persist candidate evidence locally,
and produce an evaluation report. It will not use those candidates in answers.

This milestone exists to make memory measurable before it becomes product
behavior. R5 should answer: "Can the system identify useful memories from
conversation history without inventing facts, crossing scope boundaries, or
promoting sensitive content?" It must not answer: "Does memory improve the user
experience?" That belongs to R6 after candidate quality is known.

R5 is backend-only. It adds no frontend UI, no authentication, no production
database, no vector memory retrieval, no deletion route, no prompt changes, no
chat-bound automatic extraction, and no personalization in generated answers.

## Current-state Evidence

Verified on `feature/agent-memory` at `e590ca6` on 2026-09-04.

| Claim | Evidence |
| --- | --- |
| R4 persisted conversations and messages | `backend/conversations/models.py`, `backend/conversations/service.py`, and `backend/conversations/sqlite_repository.py` define conversation and message contracts, service behavior, and SQLite persistence |
| A chat turn can optionally bind to a conversation | `backend/app/schemas/chat.py`, `backend/app/api/chat.py`, and `backend/orchestration/conversation_orchestrator.py` implement optional `conversation_id` binding |
| RAG remains a separate module | `backend/rag/generation/rag_service.py`, `backend/rag/generation/context.py`, and `backend/rag/evaluation/runtime.py` do not depend on conversation modules |
| The local app store supports module schemas | `backend/storage/schema_registry.py` manages the shared database sentinel and per-module schema version records |
| Current memory is not implemented | `ARCHITECTURE.md` and `docs/architecture/current-state.md` state that no implemented agent memory, memory read path, or memory write path exists |
| Memory candidates and records are conceptual | `docs/architecture/data-model.md` defines `MemoryCandidate` and `MemoryRecord` as target entities, while stating memory records remain conceptual after R4 |
| Memory evaluation gates already exist | `docs/evaluation/memory-evaluation.md` defines extraction, promotion, retrieval, answer-use, hard safety gates, mandatory slices, and result states |
| User content needs strict lifecycle handling | `SECURITY.md` classifies chat text and itinerary preferences as user content, forbids default full-content logging, and requires scope, retention, deletion, and verification evidence for durable user-data stores |

## Context

R1 and R2 made RAG evaluation repeatable. R3 created trip workspaces. R4 made
conversations and messages durable. Together those milestones give R5 the
minimum safe input for memory extraction: messages have stable identifiers,
conversation order, workspace scope, and storage tests.

The target architecture separates memory read from memory write. R5 implements
only the write-side shadow path. It extracts and evaluates candidates, but those
candidates remain invisible to RAG generation and invisible to answer-time
context assembly.

The hard part is not storing a row. The hard part is refusing to store the wrong
kind of row as useful memory. R5 must preserve provenance, reject unsafe or
unsupported candidates, distinguish user-global scope from trip/workspace scope,
and keep reports useful without leaking raw sensitive content.

## Users

1. The repository owner, who needs reviewable evidence before allowing memory to
   influence answers.
2. An implementation worker agent, which needs exact contracts and boundaries to
   build R5 without expanding into R6.
3. A local developer, who can run shadow extraction against synthetic or local
   conversation fixtures.
4. The future R6 memory retrieval milestone, which will consume only measured
   candidate evidence and a separately approved promotion design.
5. The evaluation harness owner, who needs memory reports that follow the
   accepted memory evaluation protocol.

## Problem Statement

The application now stores messages, but it still cannot identify durable facts
or preferences from those messages. Without R5, R6 would have to introduce
extraction, policy, persistence, retrieval, and answer influence in one step.
That would make failures hard to isolate and would make memory safety claims
weak.

Memory is riskier than ordinary conversation storage. A bad extractor can invent
a preference, preserve a transient detail forever, assign a trip-scoped fact to
the whole user, keep sensitive content, or let an older inference override a
newer correction. The memory evaluation protocol already says those failures
must be measured separately and that hard safety gates cannot be averaged away.

R5 therefore creates a shadow lane. The system observes conversations and writes
candidate evidence, but no candidate can affect an answer. That gives us a
frozen place to evaluate extraction quality, rejection behavior, scope quality,
and sensitivity handling before any user-facing personalization exists.

## Goals

1. Create a `backend/memory/` module that owns memory candidate contracts,
   extraction interfaces, policy decisions, repository interfaces, and a local
   SQLite adapter.
2. Define `MemoryCandidate`, `MemoryExtractionRun`, and policy/result
   vocabularies with server-generated identifiers and UTC timestamps.
3. Persist candidates in the existing local application database under a
   `memory` schema registered through the shared schema registry.
4. Require every non-empty candidate to reference an existing `message_id`,
   `conversation_id`, and `workspace_id`.
5. Provide deterministic rule-based extraction for R5 fixtures and tests, plus
   an extractor interface that can later be replaced by a model-backed
   extractor under a separate approved change.
6. Keep extraction and policy separate: extraction proposes; policy classifies,
   accepts for shadow evaluation, rejects, or marks candidates as needing user
   action.
7. Add backend inspection routes for triggering a manual shadow extraction run
   and listing runs/candidates for a workspace or conversation.
8. Produce a memory shadow evaluation report using the memory evaluation
   protocol result vocabulary: `PASS`, `FAIL`, `INCONCLUSIVE`, or `INVALID`.
9. Prove with tests and static checks that memory candidates never enter
   `ContextBundle`, prompt assembly, RAG retrieval, RAG evaluation, or generated
   answers.
10. Update canonical documentation so implemented R5 behavior and non-goals are
    discoverable.

## Non-goals

1. No answer-time memory retrieval, `MemoryRecord` retrieval, prompt injection,
   context assembly change, personalization, chat-bound automatic extraction, or
   memory-enabled answer quality claim.
2. No durable answer-eligible memory promotion. A candidate status of
   `accepted` means accepted into the shadow candidate set only.
3. No frontend UI and no browser persistence change.
4. No authentication, authorization, account model, tenant isolation, or public
   deployment claim.
5. No deletion API, tombstone API, redaction API, correction UI, or memory edit
   UI. R5 must model rejection and lifecycle labels, but does not implement a
   complete deletion lifecycle.
6. No vector database memory store, embedding index, Chroma write, semantic
   memory retrieval, or shared travel-knowledge collection.
7. No model-provider dependency for the default test suite. A later extractor
   may use a model only behind a separate approved design and test gate.
8. No changes to R1/R2 RAG benchmark data, RAG candidate comparison reports,
   travel knowledge chunks, embedding model, RAG prompts, or citation behavior.
9. No planner state, itinerary version, trip decision, or planner operation.
10. No staging, commit, push, PR, merge, release, branch deletion, or history
    rewrite by the implementation worker.

## Assumptions

1. R4 remains delivered at `e590ca6` or a later owner-approved integration base
   before R5 implementation starts.
2. The existing local SQLite app store remains sufficient for R5 shadow
   candidate evidence.
3. Conversation message records contain enough text, role, source,
   `trace_visibility`, sequence, and workspace scope for deterministic candidate
   extraction tests when messages are explicitly persisted with
   `trace_visibility = included`.
4. R5 can start with a deterministic rule-based extractor because the milestone
   is about contracts, policy, and evaluation harnessing, not model quality.
5. A candidate can be useful enough for shadow evaluation without being eligible
   for R6 answer-time retrieval.
6. If implementation needs a production privacy policy, authentication,
   deletion semantics, vector retrieval, model-backed extraction, or prompt
   changes, work stops and returns to design.

## User and System Flows

1. A workspace and conversation already exist through R3/R4 routes.
2. A user or test appends messages to the conversation with
   `trace_visibility = included`. Ordinary bound chat messages remain excluded
   by R4 default-deny behavior and are not R5 extraction input.
3. A local developer triggers shadow extraction for one conversation.
4. The memory service reads eligible messages through the conversation service
   or repository interface.
5. The extractor proposes zero or more raw candidate drafts with source message
   identifiers.
6. The policy evaluator validates provenance, scope, candidate type,
   sensitivity, confidence, and support.
7. The repository persists a `MemoryExtractionRun` and the resulting
   `MemoryCandidate` records.
8. The caller receives run metadata and counts only, not raw message content.
9. The developer lists candidate evidence for review.
10. The evaluation command reads fixture expectations and run records, computes
    extraction and policy metrics, writes a report, and marks the result
    `PASS`, `FAIL`, `INCONCLUSIVE`, or `INVALID`.

## Behavioral and Data Contracts

### MemorySourceMessage

`MemorySourceMessage` is the memory module's projection of a conversation
message. The memory service maps R4 `Message` records into this shape before
calling the extractor, so extraction code does not import conversation models.

| Field | Contract |
| --- | --- |
| `message_id` | Existing R4 message identifier |
| `conversation_id` | Existing conversation identifier |
| `workspace_id` | Existing workspace identifier inherited from the parent conversation |
| `sequence` | Stored R4 message sequence |
| `role` | R4 role value copied as text |
| `source` | R4 source value copied as text |
| `trace_visibility` | R4 trace visibility value copied as text |
| `content` | Source message content, normalized for extraction and never logged |
| `created_at` | Source message UTC timestamp |

### MemoryExtractionRun

`MemoryExtractionRun` records one shadow extraction execution.

| Field | Contract |
| --- | --- |
| `run_id` | Server-generated `mer_` identifier |
| `workspace_id` | Existing workspace identifier |
| `conversation_id` | Existing conversation identifier |
| `trigger` | `manual` or `evaluation` |
| `extractor_id` | Stable extractor implementation identifier |
| `policy_id` | Stable policy implementation identifier |
| `status` | `completed`, `completed_with_rejections`, `failed`, or `invalid` |
| `started_at` | UTC timestamp |
| `finished_at` | UTC timestamp or absent while running |
| `candidate_count` | Number of persisted candidates for the run |
| `accepted_count` | Number of candidates accepted for shadow evaluation |
| `rejected_count` | Number of rejected candidates |
| `needs_user_action_count` | Number of candidates requiring explicit user action before any future promotion |
| `invalid_count` | Number of candidates whose provenance, scope, or evidence was invalid |
| `failure_reason` | Controlled failure label, never raw message content |

### MemoryCandidate

`MemoryCandidate` is a proposed memory before any durable answer-eligible
promotion.

| Field | Contract |
| --- | --- |
| `candidate_id` | Server-generated `mc_` identifier |
| `run_id` | Parent extraction run |
| `workspace_id` | Existing workspace identifier |
| `conversation_id` | Existing conversation identifier |
| `source_message_id` | Existing message identifier |
| `source_sequence` | Stored message sequence copied for review and ordering |
| `proposed_scope` | `user`, `workspace`, `conversation`, or `none` |
| `proposed_type` | `preference`, `constraint`, `profile_fact`, `episode`, `decision`, `correction`, `safety_note`, or `none` |
| `status` | `accepted`, `rejected`, `needs_user_action`, or `invalid` |
| `confidence` | Floating-point value in `[0.0, 1.0]`; SQLite stores this as `REAL` |
| `sensitivity_label` | `none`, `personal`, `sensitive`, `secret`, or `unsafe` |
| `text` | Candidate content, normalized, at most 500 characters, and never logged |
| `evidence_summary` | Short redacted support summary for reports, at most 240 characters |
| `reason` | Controlled policy reason code |
| `created_at` | UTC timestamp |

### Policy Reason Codes

R5 uses a governed reason vocabulary:

| Code | Meaning |
| --- | --- |
| `supported_preference` | Explicit durable user preference |
| `supported_constraint` | Explicit durable trip or planning constraint |
| `supported_profile_fact` | Stable user profile fact |
| `supported_trip_decision` | Trip-scoped decision with clear workspace relevance |
| `explicit_correction` | User correction that supersedes an older inference |
| `no_memory_signal` | Message produced no durable memory candidate |
| `ambiguous` | Candidate lacks enough support or scope clarity |
| `transient` | Detail appears one-off or not worth durable memory |
| `wrong_scope` | Candidate cannot be safely assigned to the proposed scope |
| `low_confidence` | Confidence is below the R5 policy threshold |
| `sensitive` | Personal or sensitive content requires rejection or user action |
| `secret_like` | Controlled or real secret-like content must not be durably promoted |
| `unsupported` | Candidate text is not supported by the source message |
| `system_generated` | Source role or source type is not eligible for candidate extraction |
| `trace_excluded` | Source message is excluded from trace or memory use |

### Extraction Eligibility

R5 extracts only from messages that meet all of these conditions:

1. the parent conversation exists;
2. the parent workspace exists;
3. the message role is `user`;
4. `trace_visibility` is `included`;
5. the conversation retention state is `active`;
6. the message content is non-empty after normalization.

Assistant, tool, and `system_event` turns are not eligible as primary candidate
sources in R5. They may be referenced in evaluation fixtures as context only if
the spec is amended before implementation.

This rule intentionally means ordinary chat-bound turns are not eligible unless
a caller explicitly persisted the relevant user message with
`trace_visibility = included` through the message append route. R5 must not
change R4's default `excluded` value.

### Run Status Rules

| Run status | Required condition |
| --- | --- |
| `completed` | Extraction finished and every persisted candidate is `accepted` |
| `completed_with_rejections` | Extraction finished and at least one persisted candidate is `rejected`, `needs_user_action`, or `invalid` |
| `failed` | Extraction or persistence failed after a run was started; `failure_reason` is set |
| `invalid` | Required workspace, conversation, message, fixture, or policy evidence was malformed before extraction could be interpreted |

For a finished run, `candidate_count` must equal
`accepted_count + rejected_count + needs_user_action_count + invalid_count`.

### Route Contract

| Method and path | Request | Success response | Errors |
| --- | --- | --- | --- |
| `POST /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/memory/extractions` | Empty body or `{}` only; the public route always creates a `manual` run | `201` with one extraction run summary and counts | `404` for missing workspace or conversation; `409` for workspace/conversation mismatch; `422` for unknown request fields or any caller-supplied `trigger`; `500` for controlled storage failure |
| `GET /api/v1/workspaces/{workspace_id}/memory/extractions?conversation_id=<id>` | Query-only filter; `conversation_id` optional | `200` with `{"runs":[...]}` newest first | `404` for missing workspace; `409` for conversation outside workspace; `500` for controlled storage failure |
| `GET /api/v1/workspaces/{workspace_id}/memory/candidates?conversation_id=<id>&run_id=<id>` | Query-only filters; both optional | `200` with `{"candidates":[...]}`. With `run_id`, order by `source_sequence ASC, candidate_id ASC`. Without `run_id`, group by parent run newest first using `run.started_at DESC, run.run_id ASC`, then `source_sequence ASC, candidate_id ASC` inside each run | `404` for missing workspace or run; `409` for filter mismatch; `500` for controlled storage failure |

Responses may expose identifiers, timestamps, status values, counts,
controlled reason codes, sensitivity labels, confidence, and redacted summaries.
They must not include raw source message content.

### Schema

R5 registers module `memory` at version `1` through the shared schema registry.
SQLite DDL lives only in `backend/memory/sqlite_repository.py`.

```sql
CREATE TABLE IF NOT EXISTS memory_extraction_runs (
    run_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    trigger TEXT NOT NULL,
    extractor_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    candidate_count INTEGER NOT NULL,
    accepted_count INTEGER NOT NULL,
    rejected_count INTEGER NOT NULL,
    needs_user_action_count INTEGER NOT NULL,
    invalid_count INTEGER NOT NULL,
    failure_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_memory_runs_workspace_order
ON memory_extraction_runs(workspace_id, started_at DESC, run_id ASC);

CREATE INDEX IF NOT EXISTS idx_memory_runs_conversation_order
ON memory_extraction_runs(conversation_id, started_at DESC, run_id ASC);

CREATE TABLE IF NOT EXISTS memory_candidates (
    candidate_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    source_message_id TEXT NOT NULL,
    source_sequence INTEGER NOT NULL,
    proposed_scope TEXT NOT NULL,
    proposed_type TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
    sensitivity_label TEXT NOT NULL,
    text TEXT NOT NULL CHECK(length(text) <= 500),
    evidence_summary TEXT NOT NULL CHECK(length(evidence_summary) <= 240),
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, source_message_id, proposed_scope, proposed_type, text)
);

CREATE INDEX IF NOT EXISTS idx_memory_candidates_run_order
ON memory_candidates(run_id, source_sequence ASC, candidate_id ASC);

CREATE INDEX IF NOT EXISTS idx_memory_candidates_workspace_filter
ON memory_candidates(workspace_id, conversation_id, run_id);
```

The adapter may use SQLite foreign keys for `run_id`, but it must still validate
workspace, conversation, and message provenance in the service because R5 does
not own R3/R4 table contracts.

Candidate listing without `run_id` must join `memory_candidates` to
`memory_extraction_runs` for deterministic cross-run ordering. It must not rely
on `source_sequence` alone, because separate runs can contain candidates from
the same source message.

## Components and Dependency Direction

| Component | Responsibility | Allowed dependencies |
| --- | --- | --- |
| `backend/memory/models.py` | Candidate, run, and vocabulary contracts | Python standard library |
| `backend/memory/repository.py` | Repository protocol and controlled errors | Memory models |
| `backend/memory/sqlite_repository.py` | Local candidate and run persistence | Memory models, repository protocol, shared schema registry |
| `backend/memory/extraction.py` | Extractor protocol and deterministic rule-based extractor | Memory models |
| `backend/memory/policy.py` | Scope, sensitivity, confidence, and status decisions | Memory models |
| `backend/memory/service.py` | Use cases: run extraction, list runs, list candidates, report counts | Memory repository, conversation repository/service, workspace repository interface |
| `backend/app/schemas/memory.py` | Public JSON request/response shapes | Pydantic, memory models |
| `backend/app/api/memory.py` | HTTP mapping and dependency construction | App schemas, memory service and adapters |
| `backend/memory/evaluation/models.py` | Memory evaluation report contracts and result-state vocabulary | Memory evaluation protocol |
| `backend/memory/evaluation/runner.py` | Deterministic memory shadow evaluation runner | Memory service/repository interfaces, tracked fixtures |
| `backend/memory/evaluation/cli.py` | Memory-specific CLI entry point | Memory evaluation runner |
| `backend/rag/*` | Travel-knowledge retrieval and RAG evaluation | Must not import memory modules |

Dependency direction is one way: routes depend on services, services depend on
interfaces, adapters depend on the shared schema registry, and RAG depends on
none of them. R5 does not add any orchestration dependency.

## Data Flow and Lifecycle

R5 candidate lifecycle:

```text
message persisted -> extraction draft -> policy decision -> shadow candidate row -> evaluation report
```

Candidate statuses:

| Status | Meaning |
| --- | --- |
| `accepted` | Accepted into the R5 shadow candidate set for evaluation only |
| `rejected` | Not eligible for shadow acceptance under policy |
| `needs_user_action` | Potentially useful but requires explicit user confirmation before any future promotion |
| `invalid` | Required provenance, scope, or evidence was missing or inconsistent |

R5 does not create the `MemoryRecord` lifecycle. It may prepare enough evidence
for R6 to design that lifecycle, but it must not imply that any memory is
available for retrieval.

## Errors and Edge Cases

1. Missing workspace, conversation, or message provenance returns a controlled
   not-found or validation error without logging message content.
2. A conversation whose workspace does not match the requested workspace fails
   closed.
3. Unsupported source role, excluded trace visibility, empty content, ambiguous
   scope, low confidence, and sensitive content become explicit policy outcomes.
4. Duplicate extraction runs are allowed, but candidates must retain their run
   identity so evaluation can compare versions.
5. Repository schema version mismatch fails closed through the shared registry.
6. If extraction fails after the run row starts, the run status becomes `failed`
   with a controlled reason, and no partial candidate is reported as accepted
   unless it was persisted before the failure and counted explicitly.
7. If a message is excluded by `trace_visibility`, the policy outcome is
   `trace_excluded` and no accepted candidate is produced.

## Failure and Recovery

1. Missing provenance returns a controlled `404`, `409`, or validation error and
   writes no accepted candidates.
2. Extractor failure marks the run `failed` with a controlled `failure_reason`;
   any persisted candidates remain counted by status.
3. Policy uncertainty marks affected candidates `invalid`, `rejected`, or
   `needs_user_action`; uncertainty never becomes accepted memory.
4. Storage failure before run creation returns a controlled storage error and
   writes no candidate rows.
5. Storage failure after run creation marks the run `failed` when possible. If
   even that update fails, the caller receives a controlled storage error
   without raw content.
6. Report generation failure leaves runtime candidate rows unchanged and marks
   the evaluation result `INVALID`.
7. Boundary failure, including any memory value entering RAG retrieval, context
   assembly, prompts, or generated answers, fails the R5 change set and requires
   rollback or redesign.

## Security and Privacy

R5 processes user content and possible sensitive personal data. The approved
security posture is local development only.

1. Never log raw message content, candidate text, evidence summary, conversation
   title, or substrings of those values.
2. HTTP errors expose identifiers, counts, status, and controlled reason codes
   only.
3. Reports may include redacted excerpts only when needed to verify fixture
   identity.
4. Controlled secret-like fixtures must be artificial values created for tests.
5. Real credentials, tokens, travel documents, financial data, or unnecessary
   personal data must not be added to fixtures or committed.
6. Cross-user and cross-workspace leakage counts must remain zero in safety
   evaluation.
7. R5 does not implement deletion. It must not claim that candidate records can
   be fully removed from all derived copies.

## Observability and Operations

R5 may emit structured operational logs with:

1. route/action name;
2. `run_id`, `workspace_id`, `conversation_id`, and count fields;
3. extractor and policy identifiers;
4. controlled failure labels;
5. elapsed time.

R5 must not emit raw source content or candidate text. No metrics vendor,
tracing backend, alerting policy, or SLO is selected.

## Testing and Evaluation

R5 must add deterministic tests that require no network, model provider,
embedding model, Chroma data, Docker, or production database.

Required coverage:

1. model validation and enum vocabulary tests;
2. policy tests for supported preference, supported constraint, explicit
   correction, ambiguous text, transient text, wrong scope, low confidence,
   sensitive text, secret-like text, unsupported text, excluded trace visibility,
   and system-generated content;
3. repository tests for schema registration, create/list runs, create/list
   candidates, ordering, controlled failures, and schema mismatch;
4. service tests for provenance checks, extraction idempotence boundaries,
   run-count accuracy, and no raw content in controlled errors;
5. API tests for manual trigger/list routes and sanitized errors, including
   rejection of caller-supplied `trigger`;
6. evaluation tests proving result-state calculation and hard-gate behavior;
7. import-boundary checks proving RAG and RAG evaluation do not import memory.

### R5 Evaluation Applicability

| Protocol item | R5 applicability | Reason |
| --- | --- | --- |
| Extraction precision | Applicable | R5 extracts candidates and can compare to reviewed expected candidates |
| Extraction recall | Applicable | R5 can measure missed expected candidates |
| Scope assignment accuracy | Applicable | R5 assigns proposed scope |
| Promotion precision | Not applicable | R5 does not promote `MemoryRecord` rows |
| Memory Hit@5 | Not applicable | R5 has no memory retrieval path |
| Irrelevant-memory rate | Not applicable | R5 retrieves no memories |
| Personalization win rate | Not applicable | R5 does not affect answers |
| Constraint satisfaction delta | Not applicable | R5 does not affect answers |
| Cross-user leakage | Applicable only to candidate scope evidence | R5 must not create or report candidates outside the requested synthetic scope |
| Cross-workspace leakage | Applicable | Workspace-scoped candidates must not cross workspace filters |
| Deleted-memory retrieval | Not applicable | R5 has no deletion or retrieval path |
| Controlled secret-like durable promotion | Applicable as candidate rejection evidence | Secret-like candidates must be rejected or marked for user action, never accepted |
| Explicit correction precedence | Applicable as candidate classification evidence | R5 must label explicit correction candidates and not accept contradicted older inference as stronger evidence |
| Expiration/staleness | Not applicable | R5 defines no expiration producer |

The initial R5 report may be `INCONCLUSIVE` if the deterministic benchmark is
too small for promotion-quality claims. It must be `FAIL` if any applicable hard
safety gate records a confirmed event, and `INVALID` if required evidence is
missing or malformed.

## Rollout and Migration

R5 is additive behind backend routes and local commands. It creates memory
candidate tables only when the memory repository initializes against the shared
app database. Existing workspace, conversation, RAG, and evaluation behavior
must remain unchanged.

No runtime feature flag is needed for answer behavior because R5 has no answer
path. Chat-bound automatic extraction is out of scope; adding it later requires
an approved change that preserves R4's default-deny privacy boundary.

## Rollback

Rollback removes:

1. `backend/memory/`;
2. memory API schemas and routes;
3. memory evaluation command additions;
4. R5 documentation updates.

Because R5 does not alter RAG prompts, Chroma, `ContextBundle`, or generated
answers, rollback cannot change answer quality. Existing local memory candidate
rows become inert data in the development database.

## Capacity, Latency, and Cost

R5 default tests use deterministic local extraction and should add no network or
model cost. A single conversation extraction should be bounded by message count,
candidate count, and SQLite insert cost. The implementation plan must include
small fixture limits and report candidate counts so runaway extraction is
visible during review.

## Compatibility and Staged Migration

R5 must preserve:

1. `GET /health`;
2. every R3 workspace route;
3. every R4 conversation route;
4. unbound and bound `POST /api/v1/chat` response contracts;
5. RAG runtime behavior;
6. RAG evaluation output compatibility.

R6 may later consume R5 candidate evidence, but R5 does not pre-approve R6
storage, retrieval, prompt assembly, user confirmation, deletion, or promotion
contracts.

## Alternatives Considered

### Alternative A: Extract automatically from every bound chat turn

This would produce many candidates quickly and make R5 feel closer to real
product behavior. It conflicts with R4's default-deny `trace_visibility` choice:
ordinary chat messages are excluded unless explicitly opted in. Selected later
only if a separate privacy design approves the trigger.

### Alternative B: Keep R5 manual and evaluation-triggered only

Manual route triggers and evaluation fixtures make candidate extraction
explicit. This gives less runtime coverage, but it preserves R4 privacy
semantics and keeps R5 focused on measurable extraction and policy quality.
Selected.

### Alternative C: Put memory evaluation under `backend/rag/evaluation`

This reuses existing evaluation structure. It also makes RAG evaluation import
memory or forces a plan exception that contradicts ADR 0006. Rejected.

### Alternative D: Put memory evaluation under `backend/memory/evaluation`

Memory-specific evaluation lives beside the memory module while retaining the
same report vocabulary as the memory evaluation protocol. Existing RAG
evaluation commands stay unchanged and import-boundary checks remain simple.
Selected.

### Alternative E: Store fixtures under `data/evaluation`

This follows the physical location used by R1/R2 local run artifacts, but
`data/` is Git-ignored in this repository. R5 fixtures must be reviewable and
reproducible, so ignored fixture source files are rejected.

### Alternative F: Store fixtures under `docs/evaluation/fixtures`

Tracked fixture files live beside the protocol they exercise, are visible in
review, and can reproduce the report. Selected.

## Required ADRs

1. [ADR 0006: Shadow Memory Candidate Store and Policy Boundary](../adr/0006-shadow-memory-candidate-store-and-policy-boundary.md)

## Acceptance Criteria

1. ADR 0006 is accepted before implementation starts.
2. R5 spec and implementation plan are approved by the repository owner before
   source edits begin.
3. Memory contracts and repository interfaces are implemented in
   `backend/memory/`.
4. Memory candidate and extraction-run rows persist through the shared schema
   registry with module version `1`.
5. Candidate provenance requires existing workspace, conversation, and source
   message records.
6. Candidate policy separates extraction from status decisions and uses the
   governed vocabularies in this spec.
7. Manual or evaluation shadow extraction can be triggered and inspected through
   backend-only routes or commands.
8. R5 produces a memory shadow report with result state and hard-gate evidence.
9. No memory candidate is used in RAG retrieval, context assembly, prompts, or
   generated answers.
10. `backend/rag` and RAG evaluation import-boundary checks remain clean.
11. The full backend test suite passes using temporary databases.
12. Documentation clearly says R5 is shadow-only and makes no production memory
    or privacy claim.

## Approval Record

Spec version 0.1 was approved by the repository owner in conversation on
2026-09-04 together with acceptance of ADR 0006 and approval of the R5
implementation plan. Approval authorizes delegating backend-only shadow memory
extraction implementation. It does not authorize R6 memory retrieval, answer
personalization, frontend work, production deployment, Git delivery, or
destructive cleanup.
