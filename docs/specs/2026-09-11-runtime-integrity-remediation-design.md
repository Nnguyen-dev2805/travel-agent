# Runtime Integrity, Observability, Evaluation and Test Remediation

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-11 |
| Change class | Level 2 - Feature Spec |
| Decision owner | Repository owner |
| Scope | Eleven Critical defects on live paths, the observability surface, both offline evaluation harnesses, the offline cleaning stage, and the tenant-isolation test surface. Excludes the atomic chat turn and memory write pipeline correctness, governed separately by `2026-09-11-atomic-chat-turn-and-memory-correctness-design.md`. |
| Related issue | None filed. Authorization basis is the owner-requested review; evidence in `.workbuddy-ai/reports/code-review-2026-09-11.md` (git-ignored local artifact, not a repository document). |
| Superseded document | Not applicable |

## Summary

An owner-requested full-codebase review of `feature/agent-memory` at `cec0933` found 109 defects, 15 of them Critical. This specification governs eleven of those fifteen. They share a single property: **the system reports health, correctness or success that it cannot observe.** A readiness probe returns `READY` for a component it never inspects. An evaluation metric returns a perfect score when it has measured nothing. A cleaner reports `PIPELINE COMPLETE` after emitting an empty artifact. A security control is asserted by a test that implements the control itself.

The remediation is not "add features". It is to make each of these surfaces able to report failure, and to prove that ability by making them fail on demand.

## Context

Current state is recorded with evidence from the review at `.workbuddy-ai/reports/code-review-2026-09-11.md` and confirmed by direct source reads on 2026-09-11. The working tree is dirty (63 modified, 1 deleted, 17 untracked); findings reflect on-disk state, not `HEAD` alone.

| Ref | Defect | Evidence | Verified how |
| --- | --- | --- | --- |
| C1 | The model call has no explicit timeout or retry bound, and a client is constructed per request and never closed | `backend/rag/generation/llm.py:49-52`, `:74` | Source read. `openai` 3.3.1 defaults are 600 s with 2 retries. `chat_endpoint` is a sync `def` (`backend/app/api/chat.py:38`), so each turn holds an anyio threadpool token |
| C3 | An assistant reply is appended to whichever conversation is currently open | `frontend/src/App.jsx:141` | Source read. `handleSendMessage` captures `activeConversationId` but appends unconditionally |
| C4 | An out-of-order history response overwrites the transcript | `frontend/src/App.jsx:92-96` | Source read. No request-generation guard around `listMessages` |
| C5 | Model-extracted user content reaches logs and a database column unredacted | `backend/memory/write_pipeline/model_adapter.py:374-377`, `:379-381`; `backend/memory/write_pipeline/worker.py:334-337`, `:346`, `:363-366`, `:371`, `:387-390`, `:395` | Source read. The pydantic `ValidationError` renders `input_value=<model output>`; the extraction prompt is built from user messages. Reproduced on pydantic 2.13.4 |
| C6 | `rag_chroma` readiness returns `READY` without opening the vector store | `backend/observability/readiness.py:121-197` | Source read. The probe counts `embeddings` joined to `segments` in `chroma.sqlite3`; those rows are independent of the HNSW segment directories |
| C7 | `memory_write_pipeline` readiness returns `READY` unconditionally | `backend/observability/readiness.py:284-292` | Source read. Status is a literal |
| C10 | Memory evaluation metrics cannot fail | `backend/memory/write_pipeline/evaluation/runner.py:431`, `:620-727` | Source read. `relationship_correct` is hardcoded `1.0`; every metric uses `x/y if y > 0 else 1.0`. Reproduced in-process: all eleven metrics report exactly `1.0000` |
| C11 | The memory extractor mirrors its own fixtures and two hard gates are inert | `backend/memory/write_pipeline/evaluation/runner.py:113-226`, `:412`, `:419`, `:485-487` | Source read. `own_records` is filtered to the candidate's owner then tested for a foreign owner; `partial_transaction_state` has a bare `pass` |
| C12 | The RAG evaluation compares a pipeline to itself, and `compare` cannot fail CI | `backend/rag/evaluation/runtime.py:61-72`, `:146-153`; `backend/rag/evaluation/cli.py:125` | Source read. `cmd_compare` returns `0` unconditionally. Both adapters execute the same retriever |
| C13 | The cleaning stage is a no-op across the whole corpus | `backend/preprocessing/semantic_cleaner.py:234`, `:212-224` | Source read. `clean_document` iterates `document.get("sections")`, which the raw JSONL does not contain, so `rebuild_document_text(title, [])` returns the title alone. All 281 cleaned documents have `sections == []` and `clean_text == title` |
| C15 | Tenant isolation has no behavioural test | `backend/tests/integration/test_chat_conversation_binding.py:100`; `backend/tests/unit/test_postgres_conversation_repository.py:93` | Source read. Cross-owner assertions run against `InMemoryConversationRepository`, which implements owner scoping itself; tenant binding is "verified" by the substring `"set_config" in statements[0]` |

**Documentation debt this specification does not address.** The ADR index marks ADR 0017 `Accepted` while ADR 0020 claims to supersede it, and ADR 0008/0010/0011 remain `Accepted` despite ADRs 0018/0021 claiming supersession (`docs/adr/README.md:148-157`). This is a governance bookkeeping defect, not one of the eleven Critical findings, and is deliberately out of scope here.

## Users

1. **Repository owner** — approves this specification and the plan; decides when the resulting change set is delivered.
2. **Operator / on-call** — relies on `GET /api/v1/ops/readiness` to decide whether the service can serve traffic. Today it cannot trust the answer for two of six components.
3. **Authenticated end user** — relies on the chat transcript matching what the server stored, and on their conversations not being confused with one another.
4. **Engineer / reviewer** — relies on the evaluation harness to detect a regression, and on the test suite to prove a security control holds.
5. **Data subject** — whose conversation content must not appear in logs or in a persisted error column.

## Problem Statement

Five distinct failure classes, one shared shape.

1. **Availability.** A hung model provider stalls the entire server, not just the request, because the call is unbounded and synchronous on a shared threadpool (C1).
2. **Correctness of the client view.** The frontend writes responses into whatever conversation is open rather than the one that was asked (C3, C4).
3. **Privacy.** Conversation content derived from user messages is written to application logs and to `conversation_outbox.error_message`, in a background context with no request identifier (C5).
4. **False observability.** Two of six readiness components cannot report failure. One never inspects the resource it names; the other returns a constant (C6, C7). The evaluation harness is worse: it cannot report failure at all, so its published `PASS` results carry no information (C10, C11, C12).
5. **False confidence in tests.** The tenant-isolation control — the single most security-critical invariant in a multi-tenant system — has no test that would fail if the control were removed (C15). The offline cleaning stage reports success while emitting an empty artifact (C13).

**Why now.** The evaluation harness is about to be relied upon to measure a corpus rebuild governed by the companion specification. Measuring that rebuild with an instrument that always reports `PASS` would produce numbers that look like a regression and cannot be interpreted either way. The harness must be trustworthy before the corpus changes.

## Goals

1. A hung or slow model provider degrades one request, not the server, and the provider client is reused rather than reconstructed per request.
2. A response is only ever written to the conversation it was requested for; a superseded response is discarded.
3. No conversation content reaches a log line, an event field, an HTTP error body, or a persisted error column.
4. Each readiness component reports a status it has actually observed, and can be made to report `not_ready` by breaking the dependency it names.
5. Each evaluation metric distinguishes "measured and failed" from "not measurable", and `compare` returns a non-zero exit status on a failed or invalid comparison.
6. The cleaning stage either produces non-empty sections or fails loudly.
7. A cross-tenant isolation test exists that fails when `FORCE ROW LEVEL SECURITY` is removed.

## Non-goals

1. The atomic chat turn and the memory write pipeline correctness defects (C2, C8, C9, C14). Governed by the companion specification.
2. The 34 Important findings, including the four additional `sqlite3`-adjacent, auth-ordering and committed-credential issues. Recorded in the review report; not authorized here.
3. Restoring the `data-model.md` and `ARCHITECTURE.md` drift. Separate documentation change.
4. ADR supersession bookkeeping (§Context).
5. Any change to the retrieval algorithm, ranking, or answer quality.
6. Any change to the authentication scheme, the RLS policy expressions, or the role model.

## Assumptions

1. `openai` remains the provider SDK and its timeout and retry parameters remain the mechanism for bounding a call. If the SDK is replaced, Goal 1 must be re-specified.
2. The pydantic validation failure path is the only place model output reaches a log. The review identified three call sites in `worker.py` and four in `model_adapter.py`; if a further sink exists, Goal 3 is not met.
3. `chroma.sqlite3` catalogue rows and the HNSW segment directories can diverge, and the segment directory is what the application's query path needs. The review verified the schema; it did not corrupt a live index.
4. A cross-tenant isolation test can run against a real PostgreSQL instance in CI with `PG_TEST_DSN` set. If CI cannot provide one, C15 cannot be closed and this specification must be revised.
5. The repository owner approves the resulting re-baseline of the RAG evaluation numbers, understanding that the post-fix values will differ from the current published values.

## User and System Flows

**Flow 1 — A provider that never responds (Goal 1).**
Client sends `POST /api/v1/chat`. The route resolves the principal, the orchestrator persists the user turn, and generation begins. With the fix, the provider call raises a timeout error after the configured bound, the failure propagates as a single `500` for that request, the threadpool token is released, and concurrent requests continue to be served. The readiness probe continues to report the model provider as configured.

**Flow 2 — The user switches conversation mid-flight (Goal 2).**
The user sends a message in conversation A. Before the response arrives they select conversation B. With the fix, the response for A is discarded because its sequence token no longer matches, and B's transcript is untouched. Symmetrically, if A's history load resolves after B's, it is discarded.

**Flow 3 — A malformed model response (Goal 3).**
The extraction adapter receives output that fails schema validation. With the fix, the log line and the persisted `error_message` carry the failure class and the offending field paths only. The repair prompt still carries the raw output, because repairing it is its purpose; that value goes to the provider and is never logged.

**Flow 4 — A deleted vector segment (Goal 4).**
An operator deletes one HNSW segment directory while the catalogue rows remain. With the fix, `GET /api/v1/ops/readiness` reports the `rag_chroma` component as `not_ready` with reason `segment_missing`, and the aggregate becomes `not_ready`.

**Flow 5 — A seeded regression (Goal 5).**
A candidate evaluation run violates a comparison gate. With the fix, `compare` writes the report and exits non-zero, so a CI job fails.

**Flow 6 — A corpus with no derivable structure (Goal 6).**
The ETL stage reads a raw record with no section structure and no usable text. With the fix, the run fails with `no_sections_produced` rather than writing a cleaned artifact whose `clean_text` equals its title.

**Flow 7 — The security control is removed (Goal 7).**
An engineer drops `FORCE ROW LEVEL SECURITY` on `conversations`. With the fix, `backend/tests/integration/test_tenant_isolation.py` fails.

## Behavioral and Data Contracts

### Provider client (`backend/rag/generation/llm.py`)

- **Consumes:** `settings.GITHUB_TOKEN`, `settings.GITHUB_MODELS_URL`, `settings.LLM_MODEL`.
- **Produces:** `LLMGenerator._get_llm_client() -> OpenAI` returns the same instance across calls for the lifetime of the generator. `LLMGenerator.close() -> None` releases it. Module constants `LLM_REQUEST_TIMEOUT_SECONDS: float` and `LLM_MAX_RETRIES: int`.
- **New failure type:** `GenerationError(RuntimeError)`, raised when the provider returns no usable content. Its message carries no provider output.
- **Contract:** `LLM_REQUEST_TIMEOUT_SECONDS` must be less than the anyio threadpool's useful lifetime under the expected concurrency, and is configurable rather than literal.

### Frontend transcript (`frontend/src/App.jsx`)

- **Produces:** `historySeqRef` and `sendSeqRef` monotonic counters, and `activeConversationIdRef` mirroring `activeConversationId`.
- **Contract:** a resolved `listMessages` response is applied only if its captured sequence equals the current `historySeqRef`. A resolved `postChatMessage` response is applied only if its captured sequence equals the current `sendSeqRef` **and** its target conversation equals `activeConversationIdRef.current`. A discarded response produces no state write and no error surface.

### Redaction (`backend/memory/write_pipeline/model_adapter.py`)

- **Produces:** `schema_failure_reason(exc: Exception) -> str`, returning a governed reason code plus at most eight offending field paths.
- **Contract:** the return value must never contain a field value, the model output, or `str(exc)` for a non-`ValidationError`. Every log line and every `error_message` write on the extraction failure path uses this function.
- **Exception:** `StructuredExtractionPrompt.build_repair_prompt(raw_response, ...)` continues to receive the raw output. This is required for repair and is documented as an intentional exception.

### Readiness (`backend/observability/readiness.py`)

- **Produces:** `_probe_memory_pipeline(container) -> ReadinessComponent` returning `UNKNOWN` with reason `disabled` when `MEMORY_WRITE_PIPELINE_ENABLED` is false, `NOT_READY` with reason `outbox_unavailable` when the outbox cannot be read, `DEGRADED` with reason `backlog` when ready events are pending, and `READY` with reason `ok` otherwise. `PostgresReadinessProbe.count_ready_outbox_events() -> int`.
- **Contract:** every probe must be able to return a non-`READY` status for a real failure of the dependency it names, and that ability must be demonstrated by a test. `_compose_status` already orders `NOT_READY` above `UNKNOWN` above `DEGRADED`; a component that cannot observe its dependency returns `UNKNOWN`, not `READY`.

### Evaluation (`backend/memory/write_pipeline/evaluation/`, `backend/rag/evaluation/`)

- **Produces:** `MetricAccounting.value: float | None`. `passed` is true only when `value is not None and value >= threshold`.
- **Contract:** a zero denominator yields `value = None`, never `1.0`. A metric that cannot be computed reports `not_measured` rather than a number. `cmd_compare` maps result state to exit status: `pass` → 0, `inconclusive` → 2, `fail` → 2, `invalid` → 3, and any unexpected exception → 1. A comparison whose baseline and candidate share a `pipeline_id` is refused.

### Cleaning (`backend/preprocessing/semantic_cleaner.py`)

- **Produces:** `_sections_from_text(text: str) -> list[dict]`; `CleaningError` raised when a run produces no section for any document.
- **Contract:** `clean_document` derives sections from `text` when the document carries none. `clean_file` raises rather than writing an artifact in which every document has an empty `sections` list.

### Tenant isolation test (`backend/tests/integration/test_tenant_isolation.py`)

- **Contract:** the test asserts that owner A cannot read, list, or delete owner B's conversation through `PostgresConversationRepository`, and that `current_setting('app.tenant', true)` inside a tenant transaction equals the bound owner. It must be demonstrated to fail when `FORCE ROW LEVEL SECURITY` is dropped on `conversations`.

## Errors and Edge Cases

1. **Provider timeout.** Expected response: a single `500` for the affected request with a correlated request id. Recovery: none required; the next request proceeds normally. The threadpool token must be released.
2. **Provider returns empty or null content.** Expected response: `GenerationError`, mapped to `500`, no assistant message persisted. Recovery: the client retries.
3. **Missing `GITHUB_TOKEN`.** Expected: the existing `ValueError` path, unchanged. The client is not constructed.
4. **Two sends in flight, then a conversation switch.** Expected: both responses are discarded if neither matches the active conversation. The optimistic user messages remain until the next history load.
5. **A history load fails after a newer selection.** Expected: the failure is ignored, not surfaced, and the newer conversation's transcript is untouched.
6. **`_probe_memory_pipeline` cannot read the outbox.** Expected: `NOT_READY`, reason `outbox_unavailable`, aggregate `not_ready`, HTTP 503.
7. **A Chroma segment directory is absent but the catalogue has rows.** Expected: `NOT_READY`, reason `segment_missing`.
8. **A comparison input path resolves to an unintended run.** Expected: `load_run_artifact` behaviour is unchanged in this specification; the pipeline-identity refusal is the guard added here.
9. **The cleaning run encounters a document with no text and no sections.** Expected: `CleaningError("no_sections_produced: …")`, non-zero exit, no output artifact written.
10. **`PG_TEST_DSN` is unset.** Expected: the isolation test skips. This is a known gap; the plan requires the CI job to set it and the completion record to state whether it ran.

## Security and Privacy

**Trust boundaries affected.** The readiness endpoint remains behind `require_principal`. This specification does not widen it. The privacy fix narrows what leaves the process: the log stream and the `conversation_outbox.error_message` column both stop carrying user-derived content.

**Data classification.** Conversation content is user personal data. Model-extracted candidates are derived from it and inherit its classification. Both must be absent from logs and from persisted error strings.

**Retention.** No retention change. Existing rows in `conversation_outbox` that already contain leaked content are **not** deleted by this change. The plan requires them to be counted and reported; disposal is a destructive data operation requiring its own owner authorization.

**Secrets.** No credential is added, moved, or logged. The provider client continues to read `GITHUB_TOKEN` from settings.

**Authorization.** No authorization rule changes. The isolation test strengthens evidence for the existing rule rather than altering it.

## Observability and Operations

- Readiness gains the ability to report `not_ready` for `rag_chroma` and `memory_write_pipeline`. Operators gain a signal that previously did not exist; alerting that currently never fires may begin to fire. This is intended and should be announced before rollout.
- The `_probe_memory_pipeline` change requires a bounded `statement_timeout` on the outbox count query so a probe cannot become a load source.
- The extraction failure path emits a governed reason code instead of an exception rendering. Existing log-based debugging that relied on reading the validation text will need to use the field path and the schema version instead.
- `CHAT_TURN_COMPLETED` and `OPS_READINESS_COMPLETED` result semantics are **not** changed here; the mislabelling of a degraded turn as `SUCCESS` and of a `not_ready` snapshot as `SUCCESS` are Important findings in the review, deferred.

## Testing and Evaluation

**Component tests**

1. `backend/tests/unit/test_llm_generator.py` — the client is constructed with the configured timeout and retry bound; the client is reused; null content raises `GenerationError`.
2. `frontend/tests/transcript-race.test.jsx` — a reply for conversation A is not written after switching to B; a history response that resolves after a newer selection is discarded.
3. `backend/tests/unit/memory_write_pipeline/test_model_adapter.py` — the validation-failure log contains no field value and no `input_value`; a constructed `ProviderPermanentError` carries no content.
4. `backend/tests/unit/test_observability_readiness.py` — `memory_write_pipeline` reports `UNKNOWN` when disabled and `NOT_READY` when the outbox is unreadable; `rag_chroma` reports `NOT_READY` when a segment directory is missing.
5. `backend/tests/unit/memory_write_pipeline/test_evaluation.py` — a zero denominator yields `value is None` and `passed is False`; `relationship_accuracy` is computed from the fixture.
6. `backend/tests/unit/test_evaluation_comparison.py` — `compare` exits non-zero for `invalid` and `fail`; a same-`pipeline_id` comparison is refused.
7. `backend/tests/unit/test_semantic_cleaner.py` — sections are derived from `text`; a run with no derivable sections raises `CleaningError`.

**Integration tests**

8. `backend/tests/integration/test_tenant_isolation.py` — owner A cannot read, list, or delete owner B's conversation; the bound tenant GUC equals the owner. **Must be demonstrated to fail with `FORCE ROW LEVEL SECURITY` removed.**

**Evaluation gates**

9. The memory evaluation suites must produce at least one non-`1.0` metric, or report `not_measured`, after the fix. A suite in which every metric is `1.0` is a failure of this specification.
10. `compare` on a deliberately seeded regression must exit non-zero.

**Re-baseline.** The RAG evaluation numbers will change once the cleaning stage produces real sections. This specification does **not** authorize the corpus rebuild; that is governed by the companion specification. The harness fix must land first.

## Rollout and Migration

**Sequence.**

1. Land the provider bound and the frontend guards. Both are self-contained and reversible.
2. Land the privacy fix. Count and report existing leaked rows without deleting them.
3. Land the readiness fixes, updating the one existing test that asserts the hardcoded `READY`.
4. Land the evaluation fixes. Expect previously published `PASS` results to become `FAIL` or `not_measured`; announce this before the change, because it will look like a regression and is not one.
5. Land the cleaning fix. The corpus and index are **not** rebuilt under this specification.
6. Land the isolation test and demonstrate it failing with the policy removed.

**Compatibility.** No API contract changes. `ChatResponse` and `ConversationResponse` are unchanged. The readiness response shape is unchanged; only status values and reason codes change, and both are already enumerated in the schema.

**Migration.** No schema migration. No data migration. No destructive operation.

## Rollback

Every item is independently revertible by reverting its change set; none share a migration or a data dependency.

- The provider bound is a constructor-argument change.
- The frontend guards are additive refs; reverting restores the previous behaviour, including the defect.
- The privacy fix is a formatting change at seven call sites.
- The readiness fixes change status values; reverting restores the previous constants.
- The evaluation fixes change metric semantics. **Reverting restores a harness that reports perfect scores for unmeasured quantities.** If a rollback is required, the previous published numbers must be marked untrustworthy rather than reinstated.
- The cleaning fix changes an offline artifact. Reverting restores the no-op behaviour; any corpus already rebuilt under the fix stays rebuilt, and reverting does not restore the old corpus.

## Acceptance Criteria

1. A provider call is bounded by an explicit, configurable timeout and a bounded retry count, and the client instance is reused across requests. Verified by test and by reading the constructor call.
2. A `postChatMessage` response for conversation A produces no state write when conversation B is active. Verified by `frontend/tests/transcript-race.test.jsx`.
3. No `ValidationError` rendering reaches a log line or an `error_message` value on the extraction failure path. Verified by test and by `SELECT count(*) FROM conversation_outbox WHERE error_message LIKE '%input_value%'` returning 0 for rows written after the change.
4. `_probe_memory_pipeline` returns a non-`READY` status when the outbox cannot be read, and `_probe_rag_chroma` returns a non-`READY` status when a segment directory is missing. Both verified by tests that fail before the change.
5. `MetricAccounting.value` is `None` for a zero denominator and `passed` is `False`. Verified by test.
6. `compare` exits non-zero for an `invalid` and for a `fail` result. Verified by test.
7. `clean_file` raises `CleaningError` when no document yields a section. Verified by test.
8. `backend/tests/integration/test_tenant_isolation.py` passes, **and** fails when `FORCE ROW LEVEL SECURITY` is dropped on `conversations`. Both states recorded as evidence.
9. No API contract, schema, or authorization rule changes. Verified by `backend/tests/boundaries/test_clean_break_boundaries.py` and by `git diff` review.
10. Every existing test that encoded a defect (notably the readiness test asserting a hardcoded `READY`) is updated, and the update is named in the completion report.

## Approval Record

| Field | Value |
| --- | --- |
| Version | 0.1 |
| Status | Approved |
| Approver role | Repository owner |
| Date | 2026-09-11 |
| Authorization boundary | Authorizes preparation of the implementation plan at `docs/plans/2026-09-11-runtime-integrity-remediation-implementation.md` and nothing beyond it. Implementation begins only after that plan is separately approved. |

**What this approval does not authorize.** Approval of this specification does not authorize implementation, does not authorize the corpus rebuild or re-index governed by `2026-09-11-atomic-chat-turn-and-memory-correctness-design.md`, does not authorize deletion or modification of the `conversation_outbox` rows that already contain leaked content, does not authorize any schema migration, and does not authorize any Git delivery.

**Recorded consequence of this approval.** The evaluation changes in Goal 5 will cause previously published `PASS` results to become `FAIL` or `not_measured`. Those results must be marked untrustworthy rather than reinstated, and the change must be announced before rollout. The specification's §Rollout and §Rollback both state this; it is restated here so the approval is recorded against it.
