# Atomic Chat Turn and Memory Write Pipeline Correctness

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-11 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Four Critical defects that share one root cause — a chat turn is not a unit of work, and the memory write pipeline resolves against an empty history it never reads. Governs the conversation repository contract, the `messages` schema, and the `MemoryUnitOfWork` protocol. |
| Related issue | None filed. Authorization basis is the owner-requested review; evidence in `.workbuddy-ai/reports/code-review-2026-09-11.md` (git-ignored local artifact, not a repository document). |
| Superseded document | Not applicable |

## Summary

A chat turn currently commits in **four** transactions. The user message and its outbox event commit first, generation runs with no transaction at all, the ownership check is re-run, and the assistant message commits separately. Nothing holds the turn together.

This produces two Critical defects. **C14:** two concurrent turns on one conversation commit in the order `user_A, user_B, assistant_A, assistant_B`, destroying the turn-adjacency invariant that `backend/conversations/models.py` and the orchestrator docstrings treat as a stored fact. **C2:** a generation failure after the user commit returns `500` with no `conversation_id`, so the client retry creates a second conversation and a duplicate user message, and the phantom conversation persists in `listConversations` indefinitely.

Separately, the memory write pipeline has two Critical defects that are latent only because the recorder forces `operation=NOOP`. **C8:** `BackgroundMemoryRecorder` reads existing active versions through a `hasattr` probe that never matches, so the resolver always sees an empty history and no contradiction, reinforcement, supersession or scope-exception is ever detected. **C9:** the confidence gate reads a field the candidate type does not have, so it always sees `1.0` and the threshold is never applied to the only producer of candidates.

The remedy is to make a turn a real unit of work — one transaction that allocates both messages and the outbox event, with the assistant row filled in afterwards — and to give the resolver a real history to resolve against, with the silent fallbacks removed rather than repaired.

## Context

`feature/agent-memory` at `cec0933` is the third architecture iteration of this repository, following ADRs 0018–0022 which retired Workspace containers, Trip Planner, the public memory management surface, and SQLite. It is the first iteration in which a conversation is standalone and owned directly by `owner_user_id`, which is what makes the turn-atomicity defect newly reachable: previously a workspace held the turn together.

The memory write pipeline was built under ADRs 0012–0017 and is fully implemented but dormant. It is dormant for four independent reasons, recorded in the review: no caller instantiates the worker; the orchestrator emits an `OutboxIntent` only when `MEMORY_SHADOW_EXTRACT_ENABLED` is true and it defaults false; the recorder forces `NOOP` so no version is ever created; and the relation classifier is never invoked so the resolver always receives `UNRELATED`.

**This specification does not enable the pipeline.** It fixes the two defects that would make enabling it actively harmful. Enabling remains a separate, separately-approved decision.

## Users

1. **Repository owner** — approves this architecture design, the required ADRs, and the implementation plan.
2. **Authenticated end user** — relies on their transcript being correct and on their message not being silently duplicated or orphaned.
3. **Engineer implementing the memory pipeline** — depends on the resolver receiving real history and on the confidence gate actually gating, or the pipeline writes wrong memory.
4. **Operator** — depends on a half-written turn being visible rather than indistinguishable from a complete one.
5. **Future contributor** — depends on the repository contract expressing what a turn is, rather than the orchestrator assembling it.

## Problem Statement

**Problem 1 — the turn is not a unit of work.** A bound turn executes: ownership read (transaction 1), user message write (transaction 2), generation (no transaction), ownership read (transaction 3), assistant message write (transaction 4). Evidence: `backend/orchestration/conversation_orchestrator.py:100-166`. The consequences are:

- Turn adjacency is not preserved under concurrency. The sequence allocator holds a `SELECT … FOR UPDATE` on the parent conversation (`backend/conversations/postgres_repository.py:425-435`), so sequences stay unique and contiguous — but the *pairing* is not protected, because the assistant write takes the lock again later and appends after whatever user messages have arrived in between.
- A generation failure leaves a committed user message with no reply and a live outbox event, so memory extraction runs on an unanswered turn.
- A first-turn generation failure returns `500` without a `conversation_id`, so the client cannot reconcile and creates a duplicate conversation on retry.
- The outbox event fires on turns with no assistant reply.

**Problem 2 — the resolver resolves against nothing.** `background_recorder.py:239-248` probes `hasattr(uow, "get_active_versions")` then `hasattr(uow, "list_active_versions")`. Verified against `backend/memory/write_pipeline/uow.py:80-105`: the `MemoryUnitOfWork` protocol declares only `apply_memory_change`, and `PostgresMemoryUnitOfWork` implements neither method. Both branches are false, `existing_versions` stays `()`, and `resolve_change` always takes the `first_add` path. Every downstream capability of ADR 0013 — contradiction detection, supersession, reinforcement, scope exceptions, `PENDING_CONFLICT` — is unreachable.

The failure is silent by construction. A `hasattr` probe that returns false is indistinguishable from a legitimate empty history, so no test and no runtime ever reported it.

**Problem 3 — the confidence gate is dead.** `background_recorder.py:191` reads `getattr(candidate, "confidence", 1.0)`. Verified: `ShadowCandidate` **does** declare `confidence: float = 1.0` (`background_recorder.py:106`), but `MemoryCandidate` does not, and `_to_memory_candidate` (`:166-180`) does not carry it. The adapter emits `MemoryCandidate`, so the gate always sees `1.0` and `MIN_CONFIDENCE_THRESHOLD` (`:50`) is never applied to the only producer of candidates. A model extraction the model itself scored `0.0` persists as evidence, and as real memory once promoted.

**Why now.** The companion specification will rebuild the retrieval corpus and re-baseline the evaluation harness. Before any of that work is measured, the memory pipeline's correctness must be established, because the pipeline is the subsystem the branch is named after and the one most likely to be enabled next. Enabling it in its current state would write wrong memory silently, which is the least recoverable failure mode in the system.

## Goals

1. A chat turn's user message, assistant row, and outbox event are written in a single transaction, under a single parent-row lock, with both sequences allocated together.
2. The assistant row is filled in after generation. A turn that fails generation is recorded as failed, not left as an orphan and not silently absent.
3. Turn adjacency — every user message is immediately followed by its own assistant row — holds under concurrent turns on the same conversation.
4. A generation failure on a first turn returns enough information for the client to continue the same conversation rather than create a second one.
5. The resolver receives the real set of active versions for the candidate's owner and canonical key.
6. A candidate below the confidence threshold is rejected before any persistence occurs.
7. Neither behaviour depends on a silent fallback: a missing capability raises rather than returning empty.

## Non-goals

1. Enabling the memory write pipeline. `MEMORY_WRITE_PIPELINE_ENABLED` and `MEMORY_SHADOW_EXTRACT_ENABLED` defaults do not change.
2. Removing the shadow-only invariant. The recorder continues to force `NOOP`; this specification fixes the *inputs* to resolution, not the write operation.
3. Wiring `classify_relation` so that `MemoryRelation` reaches the resolver. The review records it as a separate finding; this specification notes that until it is wired, the resolver's relation-dependent branches remain unreachable even after the fix, and the resolver must therefore be correct for `UNRELATED` and must not be assumed to exercise its contradiction branches in production.
4. The outbox lease, retry, backoff and dead-letter defects (Important I13–I16, I18, I20). Recorded in the review; not authorized here.
5. Streaming responses, idempotency keys for chat, and pagination for `GET /conversations`.
6. Any change to the RLS policy expressions or the runtime role model.

## Assumptions

1. PostgreSQL is the only store, per ADR 0019. A single transaction spanning two message inserts and one outbox insert is available.
2. The `(conversation_id, sequence)` unique constraint is the existing guard; this change must not weaken it.
3. A `pending` assistant row is acceptable in the transcript if it is visible and distinguishable. The alternative — an invisible orphan — is the defect being fixed.
4. The frontend can render `pending` and `failed` distinctly. If it cannot within this change, the API must still expose the status so the UI can be updated separately; a pending row must never render as an empty successful reply.
5. `PostgresMemoryUnitOfWork` can read active versions inside a tenant-bound transaction using the existing `read_current_versions` logic in `backend/memory/write_pipeline/postgres.py:204`.
6. Making the confidence gate real may reject a large fraction of existing candidates. This is intended; the plan requires the confidence distribution to be measured before the threshold is relied upon.

## User and System Flows

**Flow 1 — A successful turn.**
`POST /api/v1/chat` → principal resolved → orchestrator opens one transaction: allocate the turn, insert the user message (`complete`), insert the assistant row (`pending`) with the next sequence, insert the outbox event if enabled, bump `updated_at`. Transaction commits. Generation runs outside any transaction. A second, single-row transaction updates the assistant row to `complete` with the generated content. Response returns the reply, citations, and the conversation id.

**Flow 2 — Generation fails on a bound turn.**
The first transaction has committed a user message and a `pending` assistant row. Generation raises. A second transaction marks the assistant row `failed` and cancels the outbox event written with the turn. The route returns `500` with a correlated request id. The transcript shows a user message and a failed assistant turn. A retry appends a new turn.

**Flow 3 — Generation fails on the first turn.**
Same as Flow 2, except the conversation was created in the first transaction. The response must carry the conversation id so the client continues that conversation rather than creating another. The transcript shows one conversation containing one failed turn.

**Flow 4 — Two concurrent turns on one conversation.**
Both requests contend on the parent-row lock. The first to acquire it allocates sequences `n` and `n+1` and commits; the second allocates `n+2` and `n+3`. Generation runs concurrently for both. Each completion updates only its own row by `message_id`. The committed transcript is `user, assistant, user, assistant` — adjacency preserved regardless of which generation finishes first.

**Flow 5 — A delete lands during generation.**
The first transaction committed; the conversation is then deleted, which tombstones it, bumps `deletion_epoch`, cancels pending and leased outbox rows, and invalidates evidence. The completion write must fail closed: it must not resurrect content into a deleted conversation. The route returns `404`.

**Flow 6 — A memory candidate is resolved.**
The worker extracts a candidate. The recorder reads the candidate's confidence; below threshold it returns `low_confidence` without touching the unit of work. At or above threshold it calls `uow.get_active_versions(owner, canonical_key)` inside a tenant-bound transaction, passes the real tuple to the resolver, and applies the resulting change under the existing fence.

## Behavioral and Data Contracts

### Conversation repository (`backend/conversations/`)

- **Produces:**
  - `ConversationRepository.append_turn(conversation_id, owner_user_id, user_content, assistant_placeholder, outbox_event=None) -> tuple[Message, Message]` — returns `(user_message, pending_assistant_message)`. Both rows and the outbox event commit in one transaction under one parent-row lock.
  - `ConversationRepository.complete_turn(conversation_id, message_id, owner_user_id, content) -> Message` — sets content and `status = 'complete'` on one row, only if the row is still `pending` and the conversation is still active.
  - `ConversationRepository.fail_turn(conversation_id, message_id, owner_user_id) -> Message` — sets `status = 'failed'`, only if still `pending` and still active. Idempotent.
  - `ConversationService.append_turn`, `.complete_turn`, `.fail_turn` mirroring the above.
- **Contract:** `append_turn` must be the only path that allocates a user/assistant pair. `complete_turn` and `fail_turn` are single-row updates guarded by `status = 'pending'`, so a duplicate call is a no-op rather than a corruption. Neither may write into a tombstoned conversation or one whose `deletion_epoch` has moved.

### Message model (`backend/conversations/models.py`)

- **Produces:** `MessageStatus` enum with members `PENDING`, `COMPLETE`, `FAILED`; `Message.status: MessageStatus`.
- **Contract:** `status` is server-owned, never accepted from input. Existing rows default to `complete`. `content` remains non-empty for `COMPLETE`; a `PENDING` or `FAILED` row may carry an empty string, and `require_text` must therefore be applied only on the `complete` transition.

### Memory unit of work (`backend/memory/write_pipeline/`)

- **Produces:** `MemoryUnitOfWork.get_active_versions(owner_user_id: str, canonical_key: str) -> tuple[MemoryVersion, ...]` added to the protocol in `uow.py` and implemented on `PostgresMemoryUnitOfWork` in `postgres.py`, tenant-bound.
- **Produces:** `MemoryCandidate.confidence: float` in `models.py`, populated by `model_adapter.extract` from `ExtractionCandidateSchema.confidence` and carried by `_to_memory_candidate`.
- **Contract:** a cross-owner read returns an empty tuple, never another owner's versions. The recorder no longer probes with `hasattr`; a unit of work without the capability is a type error, not a silent empty history. The confidence read is a direct attribute access, not `getattr` with a default.

### Schema

- **Produces:** `messages.status` `VARCHAR(16) NOT NULL DEFAULT 'complete'` with a check constraint over `('pending', 'complete', 'failed')` and an index on `(conversation_id, status)`.
- **Contract:** the migration must be reversible with a real `downgrade` that drops the index, the constraint and the column. Existing rows are backfilled to `complete` by the column default. `ALEMBIC_HEAD` in `backend/storage/postgres.py:26` must be updated in the same change.

## Errors and Edge Cases

1. **Generation raises any exception.** Expected: the pending row becomes `failed`, the turn's outbox event is cancelled in the same transaction, the exception propagates, the route returns `500`. Recovery: the client retries; a new turn is appended.
2. **`complete_turn` is called twice for one row.** Expected: the second call is a no-op because the row is no longer `pending`. No duplicate content, no error.
3. **`fail_turn` races `complete_turn`.** Expected: whichever commits first wins; the other is a no-op. Neither may produce a row with content and `status = 'failed'`, or empty content and `status = 'complete'`.
4. **The conversation is deleted between the turn transaction and the completion.** Expected: the completion update matches no row and raises the existing `ConversationGoneError`, mapped to `404`. The deleted conversation is not resurrected.
5. **Two turns start simultaneously on a new conversation.** Expected: one creates the conversation and appends the first turn; the other appends a turn to it. The existing identity-collision retry handles a duplicate conversation id.
6. **A `pending` row survives a process crash.** Expected: it remains `pending` and is visible as such. There is no automatic recovery in this specification; the plan records this as a known operational limitation and requires the status to be exposed in the API so an operator can identify it.
7. **The unit of work cannot read active versions.** Expected: the read fails and the error propagates. It must not be swallowed into an empty tuple.
8. **The model returns no confidence.** Expected: the adapter uses its documented default and records that it did so; the gate then applies to that default. The default must be explicit rather than an accident of a missing field.
9. **An existing candidate has no confidence because it predates the field.** Expected: the migration and the model default it to `1.0`, and the completion record states how many rows were affected.

## Security and Privacy

**Trust boundaries.** No new boundary. The turn transaction continues to run inside `tenant_transaction` with `app.tenant` bound to `owner_user_id`. The new `get_active_versions` read must do the same, or it will silently return nothing under RLS — which is precisely the failure mode being fixed, so the plan requires a tenant-scoped test for it.

**Authorization.** `append_turn`, `complete_turn` and `fail_turn` all take `owner_user_id` and must bind the tenant. A cross-owner call must fail closed. The existing RLS policies are unchanged; this change adds application-level owner predicates where the new methods write.

**Data classification.** A `pending` or `failed` assistant row contains no generated content and therefore no model output. A `failed` row must not carry a partial reply or a provider error string — the failure is recorded as a status, and the reason stays in the event stream, content-free.

**Privacy.** The turn's outbox event is now cancelled in the same transaction as the failure, so a turn with no reply no longer causes extraction over an unanswered range. That is a privacy improvement: less user content is extracted for turns the user never completed.

## Observability and Operations

- `pending` and `failed` turns must be countable. The plan requires an operator-visible count, either through the readiness snapshot or a bounded query documented in the runbook.
- A failed turn must emit an event distinguishable from a degraded-but-persisted turn. The existing `EventResult.DEGRADED` member is currently unused (review finding I10); this change does not fix that, but a `failed` turn must not emit `CHAT_TURN_COMPLETED` with `SUCCESS`.
- The completion write is a second transaction. Its failure is now a distinct, observable condition rather than an indistinguishable degraded response.
- The confidence gate becoming real will change the volume of persisted candidates. The plan requires the distribution to be measured and reported before the threshold is trusted.

## Capacity, Latency, and Cost

- **Latency.** The turn transaction now performs two message inserts and one outbox insert under one lock instead of one insert, and adds a single-row update after generation. The added round trips are bounded and constant. The parent-row lock is held slightly longer; the lock is per-conversation, so cross-conversation throughput is unaffected.
- **Capacity.** The `(conversation_id, status)` index adds one index to `messages`. Pending rows are expected to be transient; a leak would be visible as a growing count, which the observability requirement makes detectable.
- **Cost.** Unchanged. No additional model call is introduced. `get_active_versions` adds one indexed read per memory write.
- **Measurement.** The plan requires the turn p50/p99 latency and the parent-lock wait to be observed before and after, and reported. No numeric budget is asserted here because none exists in the current system; the plan's review checkpoint establishes one from the observed baseline.

## Compatibility and Staged Migration

**Coexistence.** The `status` column is added with a default, so an older application instance that does not know about it continues to insert and read rows correctly. The reverse is not true: a new instance writes `pending` rows that an older instance would render as an empty assistant message. The plan therefore requires the backend and frontend to be deployed together, and states this as a rollout constraint rather than a compatibility guarantee.

**Sequencing.**

1. Migration `20260911_01` adds `messages.status` and the index; `ALEMBIC_HEAD` is updated.
2. Repository and service gain `append_turn`, `complete_turn`, `fail_turn`.
3. The orchestrator switches to the new path; the old four-transaction path is removed in the same change, not left as a fallback.
4. The frontend renders `pending` and `failed`.
5. The memory fixes land independently of 1–4; they share no migration and no file.

**Rollout gate.** The `pending`-row count must be observed at zero steady state before the change is considered stable.

**Rollback boundary.** Reverting the schema requires the column to be droppable, which requires no reader to depend on it. Because step 3 removes the old path in the same change, a rollback of step 3 must precede a rollback of step 1.

## Failure and Recovery

| Failure | Behaviour | Recovery |
| --- | --- | --- |
| Generation raises | Turn marked `failed`, outbox event cancelled, `500` returned | Client retries; new turn appended |
| Completion write fails | Turn stays `pending`; a second attempt is possible | Operator or a bounded retry marks it `failed`; no automatic recovery in this change |
| Process crash after turn commit | Turn stays `pending` | Visible in the count; manual or future automated reconciliation |
| Conversation deleted mid-turn | Completion matches no row, `404` returned | None needed; the delete is authoritative |
| Concurrent turns | Parent-row lock serialises allocation; adjacency holds | None needed |
| `get_active_versions` fails | Error propagates; the memory write fails | The outbox retry policy applies (Important findings I14/I15 govern its quality) |
| A unit of work lacks the capability | Type error at the call site | None needed; this is the intended fail-fast |

## Required ADRs

1. **ADR 0023 — Atomic Two-Phase Chat Turn.** Records the decision that a chat turn is one unit of work with a two-phase write, that `messages` carries a server-owned turn status, and that a half-written turn is visible rather than hidden. Supersedes nothing; extends ADR 0021's ownership and auto-create contract with the persistence semantics it left open.
2. **ADR 0024 — Evaluation Results Distinguish Unmeasurable from Perfect.** Records the decision that a metric with no denominator reports `not_measured` rather than a perfect score, and that a comparison harness returns a non-zero exit status on failure. Required by the companion specification; recorded here because both ADRs are presented for architecture approval together.

**No ADR is required for C8 or C9.** ADR 0013 already decides that resolution is deterministic against existing active versions. C8 is the code failing to implement that decision, not a new decision. C9 is a threshold that ADR 0016 already assumes is applied. Recording an ADR for either would misrepresent a defect fix as an architecture choice.

## Alternatives Considered

### Compensation — keep the current order, delete the user message on failure

**Approach.** Leave the four-transaction order. On a generation failure, open a compensating transaction that tombstones the user message and cancels the outbox event.

**Benefits.** No schema change. No new repository methods beyond a delete. Smallest diff. Does not require the frontend to render a new status.

**Costs.** Adjacency is still not preserved under concurrency, because the assistant write still takes the parent lock separately — so C14 is not fixed, only C2 is. If the compensating transaction itself fails, the orphan returns, so the failure mode is probabilistic rather than eliminated. The compensating delete is a destructive write on the user's own message, which is harder to reason about than a status transition.

**Rejected because** it does not fix C14, and this specification's stated purpose is that a turn becomes a unit of work. A partial fix here would leave the harder defect in place while consuming the approval for touching the same code.

### Generate first, persist afterwards

**Approach.** Call RAG before writing anything, then persist the user message, the assistant message and the outbox event in one transaction.

**Benefits.** Genuinely one transaction for the write phase. No schema change. No `pending` state to render.

**Costs.** The user's message is lost if generation fails — the turn vanishes entirely rather than being recorded as failed. This changes retry semantics: a client retry after a failure is indistinguishable from a first attempt, so duplicate generation is unavoidable. It also inverts the current ordering, which means a slow provider holds no persisted record of what the user asked, making the failure harder to diagnose.

**Rejected because** losing the user's message is a worse outcome than recording a failed turn, and the loss is silent from the user's perspective. It also removes the only record that could be used to diagnose a provider failure.

### Two-phase turn — one transaction for the turn, one update for the content

**Approach.** In one transaction under one parent-row lock, allocate both sequences and insert the user message as `complete` and the assistant row as `pending`, plus the outbox event. After generation, a single-row update sets the content and `complete`, guarded by `status = 'pending'`.

**Benefits.** Adjacency holds under concurrency because both sequences are allocated together under one lock. A generation failure is recorded as `failed` rather than lost or orphaned. The failure mode of a crash is a visible `pending` row, not an invisible inconsistency. The outbox event can be cancelled in the same transaction as the failure, which also closes the "extraction over an unanswered turn" defect. Retry semantics are preserved: a failed turn is visibly a turn.

**Costs.** A schema migration on `messages`. A `pending` state that the frontend must render. A second write after generation, whose failure is a new observable condition. A window in which a `pending` row exists with no content.

**Selected.** It is the only alternative that preserves the invariant the repository already documents, and it converts an invisible failure into a visible one.

## Current-state Evidence

| Claim | Evidence path | Verified how |
| --- | --- | --- |
| A bound turn commits in four transactions | `backend/orchestration/conversation_orchestrator.py:111-166` | Direct source read on 2026-09-11 |
| Generation runs with no transaction between the two writes | `backend/orchestration/conversation_orchestrator.py:157` | Direct source read |
| Sequence allocation holds a parent-row lock | `backend/conversations/postgres_repository.py:425-435` | Direct source read. `SELECT … FOR UPDATE` on the conversation before reading `max(sequence)` |
| A first-turn failure returns no `conversation_id` | `backend/orchestration/conversation_orchestrator.py:100-109`, `backend/app/api/chat.py:149-166` | Direct source read. The conversation id is known locally but the failure path raises before it is returned |
| The assistant-append failure path returns `200` with `persisted=false` | `backend/orchestration/conversation_orchestrator.py:176-195` | Direct source read |
| The outbox event is attached to the user message before generation | `backend/orchestration/conversation_orchestrator.py:130-155` | Direct source read |
| `MemoryUnitOfWork` declares only `apply_memory_change` | `backend/memory/write_pipeline/uow.py:80-105` | Direct source read of the full protocol |
| The recorder probes with `hasattr` and falls through to an empty tuple | `backend/memory/write_pipeline/background_recorder.py:236-248` | Direct source read |
| `ShadowCandidate` declares `confidence`; `MemoryCandidate` does not | `backend/memory/write_pipeline/background_recorder.py:106` vs `:166-180` | Direct source read. `_to_memory_candidate` constructs `MemoryCandidate` without the field |
| The confidence gate uses a defaulting `getattr` | `backend/memory/write_pipeline/background_recorder.py:191` | Direct source read |
| The recorder forces `operation=NOOP` | `backend/memory/write_pipeline/background_recorder.py:268-286` | Direct source read |
| `ALEMBIC_HEAD` is `20260910_04` | `backend/storage/postgres.py:26` | Direct source read |

**Not verified.** No migration was executed and no live database was exercised. The concurrency behaviour of the proposed design is reasoned from the existing lock semantics, not reproduced. The `pending`-row steady-state count is asserted as a target, not measured.

## Components and Dependency Direction

```
frontend/src/App.jsx
   │  renders status; discards stale responses
   ▼
backend/app/api/chat.py                    (unchanged contract)
   ▼
backend/orchestration/conversation_orchestrator.py
   │  opens the turn, then completes or fails it
   ▼
backend/conversations/service.py           (append_turn / complete_turn / fail_turn)
   ▼
backend/conversations/postgres_repository.py   (one transaction per method)
   │
   ▼
PostgreSQL 16 · messages(status) · conversation_outbox

backend/memory/write_pipeline/worker.py
   ▼
backend/memory/write_pipeline/background_recorder.py
   │  reads confidence, reads active versions
   ▼
backend/memory/write_pipeline/uow.py        (protocol gains get_active_versions)
   ▼
backend/memory/write_pipeline/postgres.py   (tenant-bound implementation)
```

**Allowed dependency direction.** The orchestrator depends on the conversation service; the service depends on the repository port; only the Postgres adapter touches SQLAlchemy. The recorder depends on the unit-of-work protocol; only the Postgres implementation touches storage. Neither direction changes.

**Ownership.** The conversation repository owns turn persistence. The unit of work owns memory persistence. The orchestrator owns sequencing and failure classification. No component gains a responsibility it did not already have; the repository gains the ability to express a turn, which it previously could not.

## Data Flow and Lifecycle

**Turn lifecycle.** `pending` → `complete` on success, `pending` → `failed` on generation failure. `pending` is the only non-terminal state and is expected to be transient. A `pending` row older than a documented threshold is an operational signal, not a valid steady state.

**Sequence lifecycle.** Sequences are allocated for both rows in one transaction and never reallocated. A `failed` assistant row keeps its sequence, so the transcript remains contiguous and adjacency is preserved even for failed turns. This is deliberate: reusing a sequence would make the transcript non-monotonic and would let a later turn be mistaken for an earlier one.

**Conversation deletion.** Deleting a conversation tombstones it, bumps `deletion_epoch`, cancels pending and leased outbox rows, and invalidates dependent memory evidence, all in one transaction (`backend/conversations/postgres_repository.py:342-381`). `complete_turn` and `fail_turn` must respect that fence: an update must not resurrect content into a tombstoned conversation or one whose epoch moved.

**Memory version lifecycle.** Unchanged. The recorder still forces `NOOP`, so no version is created. What changes is that the resolver now receives the real active-version set, so its decision is meaningful and its reason code is accurate.

## Approval Record

| Field | Value |
| --- | --- |
| Version | 0.1 |
| Status | Approved — 2026-09-11, repository owner |
| Approver role | Repository owner |
| Date | 2026-09-11 |
| Authorization boundary | Authorizes the implementation plan at `docs/plans/2026-09-11-atomic-chat-turn-and-memory-correctness-implementation.md` and acceptance of ADR 0023 and ADR 0024. Implementation is authorized only by the separate plan approval recorded in that plan's Completion Record. |

**Approved 2026-09-11 by the repository owner, together with its implementation plan.** ADR 0023 and ADR 0024 are `Accepted` as of the same date.

**What this approval does NOT authorize.** Enabling the memory write pipeline (`MEMORY_WRITE_PIPELINE_ENABLED` and `MEMORY_SHADOW_EXTRACT_ENABLED` defaults do not change); removing the recorder's shadow-only `NOOP` invariant; applying the `messages.status` migration to any environment other than a disposable test database; wiring `classify_relation` so that `MemoryRelation` reaches the resolver; the outbox lease, retry, back-off and dead-letter defects; and any Git delivery.

**Two owner-authorized scope additions are recorded in the plan, not here.** The plan's "Owner-authorized scope additions" section records the lazy `backend/rag/generation/__init__.py` refactor and the `PG_RUNTIME_TEST_DSN` standardisation. Both were instructed directly by the repository owner; neither is specified in this document. They are recorded there so the change set is not silently wider than its governing documents, and so that a reviewer can see exactly which parts of it rest on a direct owner instruction rather than on this approval.
