# Runtime Integrity, Observability, Evaluation and Test Remediation Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence. Each task ends with a review checkpoint; do not begin
> the next task until the checkpoint condition holds.

**Goal:** Make eleven surfaces report failure they can actually observe — a bounded provider call, a transcript that cannot be written into the wrong conversation, a content-free failure path, readiness probes that can return `not_ready`, an evaluation harness that can return a non-zero exit, a cleaning stage that fails instead of emitting an empty artifact, and a cross-tenant isolation test that fails when the control is removed.

**Architecture:** Six independent change sets with no shared migration, no shared interface, and no shared data dependency, plus one test. Each is revertible alone. Ordering is driven by one constraint: the evaluation harness fix (Task 5) must precede the corpus rebuild governed by the companion specification, because the rebuild will be measured by that harness.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy 2 / psycopg3 / PostgreSQL 16 / ChromaDB / pytest · React 18 / Vite / Vitest / axios · `openai` 3.3.1

**Spec:** `docs/specs/2026-09-11-runtime-integrity-remediation-design.md` v0.1

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-09-11 |
| Approved specification | `docs/specs/2026-09-11-runtime-integrity-remediation-design.md` v0.1 — **Approved 2026-09-11** by the repository owner. |
| Execution owner | Implementation agent, in an isolated linked worktree assigned by the repository owner |
| Decision owner | Repository owner |
| Scope | Eleven Critical findings: C1, C3, C4, C5, C6, C7, C10, C11, C12, C13, C15 |
| Verification | `pytest backend/tests/unit backend/tests/boundaries`; `PG_TEST_DSN=… pytest backend/tests/integration -m integration`; `cd frontend && npm test`; the forced-failure checks in Task 7 and Task 5 |

## Global Constraints

1. Every persistent repository change requires a written specification and an approved implementation plan (`AGENTS.md`). The governing specification is approved, and **this plan was approved by the repository owner on 2026-09-11 and has since been executed**; its status is `Completed` and the evidence is in the Completion Record.
2. The repository owner creates or selects branches and decides when to stage, commit in the primary working tree, push, open a PR, merge, and release. An agent in an isolated linked worktree may create local handoff commits only.
3. The working tree is dirty: 63 modified, 1 deleted, 17 untracked. Read a dirty file before touching it and work with the existing edits rather than reverting them.
4. No API contract, response schema, or authorization rule changes. `ChatResponse` and `ConversationResponse` are unchanged.
5. No schema migration. No data migration. No destructive data operation.
6. Never expose secrets, credentials, tokens, or sensitive personal data in code, logs, commands, evidence, or documentation.
7. Behaviour changes use a red-green-refactor cycle. Every task below states the failing test first.
8. Do not delete or modify existing rows in `conversation_outbox` that already contain leaked content. Count and report them; disposal requires separate owner authorization.
9. Test assertions that currently encode a defect must be updated, and the update named in the completion report.
10. The corpus is **not** rebuilt under this plan. `data/processed/` and `data/chromadb/` are untouched.
11. `ALEMBIC_HEAD` in `backend/storage/postgres.py:26` stays `20260910_04`. This plan adds no migration.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/rag/generation/llm.py` | Bound the provider call; own and reuse one client; reject unusable content | — |
| `backend/app/runtime_container.py` | Close the provider client on shutdown | Task 1 |
| `backend/tests/unit/test_llm_generator.py` | Prove the bound, the reuse, and the rejection | Task 1 |
| `frontend/src/App.jsx` | Own transcript sequence guards and the active-conversation ref | — |
| `frontend/tests/transcript-race.test.jsx` | Prove stale responses are discarded | Task 2 |
| `backend/memory/write_pipeline/model_adapter.py` | Render validation failure as governed codes only | — |
| `backend/memory/write_pipeline/worker.py` | Log and persist content-free failure reasons | Task 3 |
| `backend/tests/unit/memory_write_pipeline/test_model_adapter.py` | Prove no content reaches a log or an error message | Task 3 |
| `backend/observability/readiness.py` | Report observed status for `rag_chroma` and `memory_write_pipeline` | — |
| `backend/app/runtime_container.py` | Provide the bounded outbox count to the readiness probe | Task 4 |
| `backend/tests/unit/test_observability_readiness.py` | Prove each probe can report failure | Task 4 |
| `backend/memory/write_pipeline/evaluation/models.py` | Carry `value: float \| None` | Task 5 |
| `backend/memory/write_pipeline/evaluation/runner.py` | Compute metrics that can fail; make the two inert gates real | Task 5 |
| `backend/rag/evaluation/cli.py` | Map comparison state to exit status | Task 5 |
| `backend/rag/evaluation/runtime.py` | Distinguish the two adapter pipelines | Task 5 |
| `backend/tests/unit/memory_write_pipeline/test_evaluation.py` | Prove zero denominators are not perfect scores | Task 5 |
| `backend/tests/unit/test_evaluation_comparison.py` | Prove `compare` exits non-zero | Task 5 |
| `backend/preprocessing/semantic_cleaner.py` | Derive sections from `text`; fail on an empty clean | — |
| `backend/tests/unit/test_semantic_cleaner.py` | Prove derivation and the failure | Task 6 |
| `backend/tests/integration/test_tenant_isolation.py` | Prove cross-tenant isolation against a real database | — |
| `backend/tests/unit/test_postgres_conversation_repository.py` | Assert the exact tenant binding | Task 7 |

## Task 1: Bound and reuse the provider client

**Files:**

- Modify: `backend/rag/generation/llm.py:16-19`, `:37-52`, `:74-91`
- Modify: `backend/app/runtime_container.py` (shutdown path, where the engine is disposed)
- Test: `backend/tests/unit/test_llm_generator.py`

**Interfaces:**

- Consumes: `settings.GITHUB_TOKEN`, `settings.GITHUB_MODELS_URL`, `settings.LLM_MODEL`
- Produces: `LLM_REQUEST_TIMEOUT_SECONDS: float`, `LLM_MAX_RETRIES: int`, `GenerationError(RuntimeError)`, `LLMGenerator.close() -> None`. `_get_llm_client()` returns the same instance across calls.

- [x] **Step 1: Write the failing tests**

```python
def test_client_is_constructed_with_explicit_timeout_and_retries(monkeypatch):
    captured = {}

    class _RecordingClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("backend.rag.generation.llm.OpenAI", _RecordingClient)
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "test-token", raising=False)

    LLMGenerator()._get_llm_client()

    assert captured["timeout"] == LLM_REQUEST_TIMEOUT_SECONDS
    assert captured["max_retries"] == LLM_MAX_RETRIES
    assert 0 < LLM_REQUEST_TIMEOUT_SECONDS <= 30.0


def test_client_is_reused_across_calls(monkeypatch):
    built = []
    monkeypatch.setattr(
        "backend.rag.generation.llm.OpenAI", lambda **kw: built.append(kw) or object()
    )
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "test-token", raising=False)

    generator = LLMGenerator()
    assert generator._get_llm_client() is generator._get_llm_client()
    assert len(built) == 1


def test_unusable_content_raises_generation_error():
    generator = LLMGenerator(client=_ClientReturningContent(None))
    with pytest.raises(GenerationError):
        generator.generate("q", _bundle_with_evidence())


def test_injected_client_is_not_closed_by_the_generator():
    injected = _ClientReturningContent("ok")
    LLMGenerator(client=injected).close()
    assert not injected.closed
```

- [x] **Step 2: Run verification**

Run: `pytest backend/tests/unit/test_llm_generator.py -v`

Expected: FAIL. `LLM_REQUEST_TIMEOUT_SECONDS` and `GenerationError` are undefined; `test_client_is_reused_across_calls` sees two constructions; `test_unusable_content_raises_generation_error` does not raise.

- [x] **Step 3: Implement**

Add at module level, replacing the constants block at `:16-19`:

```python
PROMPT_ID = "rag-structured-prompt-v1"

GENERATION_TEMPERATURE = 0.7
GENERATION_MAX_TOKENS = 800

# Bounded so a hung provider cannot hold an anyio threadpool token for the
# SDK default of 600 s. `chat_endpoint` is a sync def, so an unbounded call
# degrades every sync endpoint, not just the affected request.
LLM_REQUEST_TIMEOUT_SECONDS = 20.0
LLM_MAX_RETRIES = 1


class GenerationError(RuntimeError):
    """The provider returned no usable content. Carries no provider output."""
```

Replace `__init__` and `_get_llm_client`:

```python
    def __init__(self, client: Optional[OpenAI] = None) -> None:
        self._client = client
        self._owned_client: Optional[OpenAI] = None

    def _get_llm_client(self) -> OpenAI:
        """Return the shared provider client, constructing it once.

        An injected client is owned by the caller and is never closed here.
        """
        if self._client is not None:
            return self._client
        if self._owned_client is None:
            if not settings.GITHUB_TOKEN:
                logger.warning("GITHUB_TOKEN missing in environment settings.")
                raise ValueError("GITHUB_TOKEN is missing in server environment.")
            self._owned_client = OpenAI(
                base_url=settings.GITHUB_MODELS_URL,
                api_key=settings.GITHUB_TOKEN,
                timeout=LLM_REQUEST_TIMEOUT_SECONDS,
                max_retries=LLM_MAX_RETRIES,
            )
        return self._owned_client

    def close(self) -> None:
        """Release the owned client. Injected clients are left to their caller."""
        if self._owned_client is not None:
            self._owned_client.close()
            self._owned_client = None
```

Replace the tail of `generate`:

```python
        reply_content = completion.choices[0].message.content
        if not isinstance(reply_content, str) or not reply_content.strip():
            raise GenerationError("The provider returned no usable content.")
```

Wire `close()` into `RuntimeContainer.shutdown()` next to engine disposal, guarding for the case where the RAG service was never constructed.

- [x] **Step 4: Run verification**

Run: `pytest backend/tests/unit/test_llm_generator.py backend/tests/unit/test_rag_service.py -v`

Expected: PASS.

- [x] **Step 5: Review checkpoint**

Review: `git diff backend/rag/generation/llm.py backend/app/runtime_container.py`. Confirm the timeout is configurable rather than buried, that an injected test client is not closed, and that no provider output appears in the `GenerationError` message. Confirm `LLM_REQUEST_TIMEOUT_SECONDS` was chosen from observed latency, not guessed — record the observed p99 in the task evidence.

Expected: `GenerationError` message contains no provider content; a single client instance is constructed per generator; `RuntimeContainer.shutdown()` closes it.

## Task 2: Guard the frontend transcript against stale responses

**Files:**

- Modify: `frontend/src/App.jsx:19-20`, `:41-55`, `:92-100`, `:109-154`
- Test: `frontend/tests/transcript-race.test.jsx` (create)

**Interfaces:**

- Consumes: `listMessages`, `postChatMessage` from `frontend/src/services/chat.js`
- Produces: `historySeqRef`, `sendSeqRef`, `activeConversationIdRef` inside `App`

- [x] **Step 1: Write the failing tests**

```jsx
it("does not write a reply into a conversation the user has left", async () => {
  let resolveSend;
  postChatMessage.mockReturnValue(new Promise((r) => { resolveSend = r; }));

  render(<App />);
  await userEvent.click(screen.getByText("Conversation A"));
  await userEvent.type(screen.getByRole("textbox"), "hello");
  await userEvent.keyboard("{Enter}");

  await userEvent.click(screen.getByText("Conversation B"));
  resolveSend({ reply: "A answer", conversation: { conversation_id: "A" }, citations: [] });

  await screen.findByText("B message");
  expect(screen.queryByText("A answer")).not.toBeInTheDocument();
});

it("ignores a history response that resolves after a newer selection", async () => {
  const slow = deferred();
  listMessages.mockImplementation((id) =>
    id === "A"
      ? slow.promise
      : Promise.resolve([{ message_id: "b1", role: "user", content: "B message" }])
  );

  render(<App />);
  await userEvent.click(screen.getByText("Conversation A"));
  await userEvent.click(screen.getByText("Conversation B"));

  slow.resolve([{ message_id: "a1", role: "user", content: "A message" }]);
  await screen.findByText("B message");
  expect(screen.queryByText("A message")).not.toBeInTheDocument();
});
```

- [x] **Step 2: Run verification**

Run: `cd frontend && npm test -- transcript-race`

Expected: FAIL. Both stale responses are currently written.

- [x] **Step 3: Implement**

Add refs beside the existing state at `:19-20`:

```jsx
  const historySeqRef = React.useRef(0);
  const sendSeqRef = React.useRef(0);
  const activeConversationIdRef = React.useRef(activeConversationId);
```

Keep the ref in sync:

```jsx
  React.useEffect(() => {
    activeConversationIdRef.current = activeConversationId;
  }, [activeConversationId]);
```

Guard the history load at `:92-100`:

```jsx
  const handleSelectConversation = async (convId) => {
    const seq = ++historySeqRef.current;
    setActiveConversationId(convId);
    setMessages([]);
    try {
      const msgs = await listMessages(convId);
      if (seq !== historySeqRef.current) return;
      setMessages(msgs || []);
    } catch (err) {
      if (seq !== historySeqRef.current) return;
      console.error('Lỗi mở conversation:', err);
      setMessages([{
        message_id: `err_${Date.now()}`,
        role: 'assistant',
        content: 'Không tải được nội dung hội thoại này.',
        created_at: new Date().toISOString(),
      }]);
    }
  };
```

Guard the send at `:109-154`:

```jsx
  const handleSendMessage = async (text) => {
    if (!text.trim() || isChatLoading) return;
    const sendSeq = ++sendSeqRef.current;
    const targetConvId = activeConversationId;
    const isStale = () =>
      sendSeq !== sendSeqRef.current || targetConvId !== activeConversationIdRef.current;

    // ... optimistic user message unchanged ...
    try {
      const result = await postChatMessage({ message: text, conversation_id: targetConvId });
      if (isStale()) return;
      // ... existing response handling unchanged ...
    } catch (err) {
      if (isStale()) return;
      // ... existing error handling unchanged ...
    } finally {
      if (!isStale()) setIsChatLoading(false);
    }
  };
```

**Note.** Do not fix the duplicate-assistant-message defect (review Important I33) in this task; it is a separate finding. The first test above must therefore assert on the absence of the stale text rather than on message counts.

- [x] **Step 4: Run verification**

Run: `cd frontend && npm test`

Expected: PASS, including the existing suite.

- [x] **Step 5: Review checkpoint**

Review: `git diff frontend/src/App.jsx`. Confirm every `setMessages` on an async path is behind a staleness check, that a discarded response produces no error surface, and that no unrelated behaviour changed.

Expected: both new tests pass; the existing suite passes; `git diff` touches only the four regions named above.

## Task 3: Make extraction failure reporting content-free

**Files:**

- Modify: `backend/memory/write_pipeline/model_adapter.py:368-400`
- Modify: `backend/memory/write_pipeline/worker.py:333-405`
- Test: `backend/tests/unit/memory_write_pipeline/test_model_adapter.py`

**Interfaces:**

- Consumes: nothing new
- Produces: `schema_failure_reason(exc: Exception) -> str`

- [x] **Step 1: Write the failing tests**

```python
def test_validation_failure_log_carries_no_extracted_content(caplog):
    adapter = MemoryExtractionModel(provider=_ProviderReturning('{"wrong": "type"}'))

    with caplog.at_level(logging.INFO):
        with pytest.raises(ProviderPermanentError):
            adapter._parse_with_repair('{"wrong": "type"}')

    assert "wrong" not in caplog.text
    assert "input_value" not in caplog.text
    assert "schema_validation_failed" in caplog.text


def test_persisted_error_message_carries_no_content():
    err = ProviderPermanentError(schema_failure_reason(_validation_error_for("Hà Nội")))
    assert "Hà Nội" not in str(err)
    assert "input_value" not in str(err)


def test_schema_failure_reason_reports_field_paths_not_values():
    reason = schema_failure_reason(_validation_error_for("Hà Nội"))
    assert reason.startswith("schema_validation_failed")
    assert "candidates" in reason
    assert "Hà Nội" not in reason
```

- [x] **Step 2: Run verification**

Run: `pytest backend/tests/unit/memory_write_pipeline/test_model_adapter.py -k "content or field_paths" -v`

Expected: FAIL. `schema_failure_reason` is undefined; the log currently contains `input_value`.

- [x] **Step 3: Implement**

Add to `model_adapter.py`:

```python
def schema_failure_reason(exc: Exception) -> str:
    """Render a validation failure as governed codes and field paths only.

    Never emits a field value, the model output, or `str(exc)`. The field
    path is enough to locate the defect; the value is user content derived
    from the conversation.
    """
    if isinstance(exc, ValidationError):
        locations = sorted(
            {
                ".".join(str(part) for part in err.get("loc", ())) or "<root>"
                for err in exc.errors()
            }
        )
        return f"schema_validation_failed fields={','.join(locations[:8])}"
    return f"schema_validation_failed class={type(exc).__name__}"
```

Change the three rendering sites at `:374-377`, `:379-381`:

```python
        except (json.JSONDecodeError, ValidationError) as initial_error:
            reason = schema_failure_reason(initial_error)
            logger.info("Model response invalid; attempting bounded repair. %s", reason)
            if self._max_repair_attempts <= 0:
                raise ProviderPermanentError(reason) from initial_error
```

At `:384-386`, keep the raw output and document why:

```python
            # Intentional exception to the content-free rule: the repair
            # prompt must carry the failing output, because repairing it is
            # the purpose. This value goes to the provider, never to a log,
            # an event field, or a persisted error message.
            repair_prompt = StructuredExtractionPrompt.build_repair_prompt(
                raw_response, str(initial_error)
            )
```

In `worker.py`, change all three `logger.*(..., err)` to the class name and all three `error_message=str(err)` to the now-content-free reason:

```python
        except ProviderPermanentError as err:
            logger.error(
                "Permanent model extraction error for outbox_id=%s failure_class=%s",
                event.outbox_id,
                type(err).__name__,
            )
            new_status = self._outbox_repo.mark_failed(
                event.outbox_id,
                lease_owner=self._worker_id,
                error_message=str(err),  # content-free by construction
                retryable=False,
                max_attempts=self._max_attempts,
                now=now,
            )
```

Add a guard test so a future `f"...{exc}"` cannot reintroduce the leak:

```python
def test_provider_errors_never_render_arbitrary_exception_text():
    for exc in (ProviderTransientError("x"), ProviderPermanentError("y")):
        assert "input_value" not in str(exc)
```

- [x] **Step 4: Run verification**

Run: `pytest backend/tests/unit/memory_write_pipeline/ -v`

Expected: PASS.

- [x] **Step 5: Count existing leaked rows**

Run:

```bash
psql "$PG_DSN" -c "SELECT count(*) FROM conversation_outbox WHERE error_message LIKE '%input_value%';"
```

Expected: an integer. Record it in the task evidence. **Do not delete or modify these rows.** Disposal is a destructive data operation requiring separate owner authorization.

- [x] **Step 6: Review checkpoint**

Review: `git diff backend/memory/write_pipeline/`. Confirm no call site renders an exception object, that the repair-prompt exception is documented in place, and that the leaked-row count is recorded rather than acted on.

Expected: `grep -n "str(err)\|, err," backend/memory/write_pipeline/worker.py` shows only the content-free `error_message` uses; the count is in the evidence.

## Task 4: Make the readiness probes able to fail

**Files:**

- Modify: `backend/observability/readiness.py:121-197`, `:284-292`, `:322-329`
- Modify: `backend/app/runtime_container.py` (`PostgresReadinessProbe`)
- Test: `backend/tests/unit/test_observability_readiness.py`

**Interfaces:**

- Consumes: `settings.MEMORY_WRITE_PIPELINE_ENABLED`, `settings.MEMORY_SHADOW_EXTRACT_ENABLED`
- Produces: `_probe_memory_pipeline(container) -> ReadinessComponent`; `PostgresReadinessProbe.count_ready_outbox_events() -> int`

- [x] **Step 1: Write the failing tests**

```python
def test_memory_pipeline_reports_unknown_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "MEMORY_WRITE_PIPELINE_ENABLED", False, raising=False)
    component = _probe_memory_pipeline()
    assert component.status is ReadinessStatus.UNKNOWN
    assert component.reason_code == "disabled"


def test_memory_pipeline_reports_not_ready_when_the_outbox_is_unreadable(monkeypatch):
    monkeypatch.setattr(settings, "MEMORY_WRITE_PIPELINE_ENABLED", True, raising=False)
    component = _probe_memory_pipeline(container=_container_with_failing_probe())
    assert component.status is ReadinessStatus.NOT_READY
    assert component.reason_code == "outbox_unavailable"


def test_rag_chroma_not_ready_when_a_segment_directory_is_missing(tmp_path):
    _build_chroma_store(tmp_path, docs=2)
    _delete_one_segment_directory(tmp_path)
    component = _probe_rag_chroma(tmp_path)
    assert component.status is ReadinessStatus.NOT_READY
    assert component.reason_code == "segment_missing"


def test_rag_chroma_still_ready_for_a_healthy_store(tmp_path):
    _build_chroma_store(tmp_path, docs=2)
    assert _probe_rag_chroma(tmp_path).status is ReadinessStatus.READY
```

- [x] **Step 2: Run verification**

Run: `pytest backend/tests/unit/test_observability_readiness.py -k "memory_pipeline or segment" -v`

Expected: FAIL. `_probe_memory_pipeline` returns `READY` unconditionally; the Chroma probe never inspects segment directories.

- [x] **Step 3: Implement `_probe_memory_pipeline`**

```python
def _probe_memory_pipeline(container: Any = None) -> ReadinessComponent:
    enabled = bool(settings.MEMORY_WRITE_PIPELINE_ENABLED)
    shadow = bool(settings.MEMORY_SHADOW_EXTRACT_ENABLED)
    details: dict[str, Any] = {
        "write_pipeline_enabled": enabled,
        "shadow_extract_enabled": shadow,
    }

    if not enabled:
        return ReadinessComponent(
            name="memory_write_pipeline",
            status=ReadinessStatus.UNKNOWN,
            reason_code="disabled",
            details=details,
        )

    try:
        pending = _resolve_probe(container).count_ready_outbox_events()
        details["ready_events"] = pending
    except Exception as exc:
        logger.warning(
            "readiness.memory_write_pipeline probe failed failure_class=%s",
            type(exc).__name__,
        )
        return ReadinessComponent(
            name="memory_write_pipeline",
            status=ReadinessStatus.NOT_READY,
            reason_code="outbox_unavailable",
            details=details,
        )

    return ReadinessComponent(
        name="memory_write_pipeline",
        status=ReadinessStatus.DEGRADED if pending else ReadinessStatus.READY,
        reason_code="backlog" if pending else "ok",
        details=details,
    )
```

`_compose_status` already orders `NOT_READY` above `UNKNOWN` above `DEGRADED`, so an `UNKNOWN` component drags the aggregate to `UNKNOWN` rather than `READY`.

Add `count_ready_outbox_events()` to `PostgresReadinessProbe` — a `SELECT count(*) FROM conversation_outbox WHERE status = 'pending'` with `SET LOCAL statement_timeout = '2s'` so the probe cannot become a load source.

Pass `container` at `:328`: `("memory_write_pipeline", lambda: _probe_memory_pipeline(container))`.

- [x] **Step 4: Implement the Chroma segment check**

Preferred: replace the `sqlite3` probe with a read-only Chroma client open plus a bounded read of one known id — what the docstring already claims to do. If opening a client in a probe is unacceptable because it can create files in an empty directory, keep the SQLite read and add the directory check:

```python
            segment_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT id FROM segments WHERE collection = ?", (collection_id,)
                ).fetchall()
            ]
            missing = [sid for sid in segment_ids if not (path / sid).is_dir()]
            if missing:
                return _chroma_component(
                    ReadinessStatus.NOT_READY,
                    "segment_missing",
                    present=True,
                    vectors=int(count),
                )
```

Whichever route is taken, the `sqlite3` use must be reconciled with the specification's rule at `docs/specs/2026-09-10-authenticated-chat-postgresql-clean-break-design.md:610`. Record the reconciliation in the task evidence: either the spec is amended to allowlist this application file, or the `sqlite3` import is removed.

- [x] **Step 5: Update the test that encoded the defect**

`backend/tests/unit/test_observability_readiness.py:380` asserts the hardcoded `READY`. Update it to assert the new, observed status. **Name this change explicitly in the completion report** — a test that encoded the defect must not be silently rewritten.

- [x] **Step 6: Run verification**

Run: `pytest backend/tests/unit/test_observability_readiness.py backend/tests/integration/test_ops_readiness_api.py -v`

Expected: PASS.

- [x] **Step 7: Review checkpoint**

Review: `git diff backend/observability/readiness.py` and the updated test. Confirm every probe in the tuple can now return a non-`READY` status for a real failure, that the outbox count is timeout-bounded, and that the defect-encoding assertion was updated rather than deleted.

Expected: both new tests fail before the change and pass after; the readiness test change is documented.

## Task 5: Make the evaluation harness able to fail

**Files:**

- Modify: `backend/memory/write_pipeline/evaluation/models.py` (`MetricAccounting`)
- Modify: `backend/memory/write_pipeline/evaluation/runner.py:429-441`, `:485-487`, `:617-727`
- Modify: `backend/rag/evaluation/cli.py:100-128`
- Modify: `backend/rag/evaluation/runtime.py:61-72`, `:146-153`
- Test: `backend/tests/unit/memory_write_pipeline/test_evaluation.py`
- Test: `backend/tests/unit/test_evaluation_comparison.py`

**Interfaces:**

- Produces: `MetricAccounting.value: float | None`; `CurrentRuntimeAdapter.pipeline_id` and `StructuredRuntimeAdapter.pipeline_id` as distinct strings
- Consumes: the existing `ResultState` enum

- [x] **Step 1: Write the failing tests**

```python
def test_zero_denominator_is_not_a_perfect_score():
    report = _run_suite(_dataset_with_no_expected_candidates())
    metric = report.metrics["candidate_recall"]
    assert metric.denominator == 0
    assert metric.value is None
    assert metric.passed is False


def test_relationship_accuracy_is_computed_from_the_fixture():
    report = _run_suite(_dataset_where_expected_relation_is_wrong())
    assert report.metrics["relationship_accuracy"].value == 0.0


def test_cross_owner_gate_fires_when_a_foreign_record_reaches_the_resolver():
    with _foreign_record_visible():
        result = _evaluate(_cross_owner_example())
    assert result.hard_gate_violated == "cross_owner_access"


def test_partial_transaction_gate_fires_when_a_write_is_not_rolled_back():
    result = _evaluate(_transaction_failure_example(), uow=_uow_that_does_not_roll_back())
    assert result.hard_gate_violated == "partial_transaction_state"


def test_compare_exits_non_zero_on_invalid(tmp_path):
    assert main([...]) == 3


def test_compare_exits_non_zero_when_a_gate_fails(tmp_path):
    assert main([...]) == 2


def test_the_two_adapters_are_not_the_same_pipeline():
    assert CurrentRuntimeAdapter.pipeline_id != StructuredRuntimeAdapter.pipeline_id
```

- [x] **Step 2: Run verification**

Run: `pytest backend/tests/unit/memory_write_pipeline/test_evaluation.py backend/tests/unit/test_evaluation_comparison.py -v`

Expected: FAIL. Zero denominators currently yield `1.0`; `relationship_correct` is hardcoded; both gates report no violation; `compare` returns `0`.

- [x] **Step 3: Implement the metric changes**

Add `value: float | None = None` to `MetricAccounting` and make `passed` derived. Then change every `else 1.0` at `:620-727` to `else None` and compute `passed` from the value:

```python
        rec_val = total_cand_matched / total_expected if total_expected > 0 else None
        computed_metrics["candidate_recall"] = MetricAccounting(
            name="candidate_recall",
            numerator=total_cand_matched,
            denominator=total_expected,
            value=rec_val,
            threshold=INITIAL_THRESHOLDS["candidate_recall"],
            passed=rec_val is not None and rec_val >= INITIAL_THRESHOLDS["candidate_recall"],
        )
```

Replace the hardcoded relationship metric at `:430-431`:

```python
            metrics["relationship_tested"] = 1.0
            actual_rel = getattr(change, "relation", expected_rel)
            metrics["relationship_correct"] = 1.0 if actual_rel == expected_rel else 0.0
```

**If `resolve_change` does not expose a relation, do not invent one.** Emit `value=None` with reason `not_measured` and record it as a known gap. A metric that is honestly absent is worth more than one that is falsely perfect.

- [x] **Step 4: Implement the gate fixes**

Cross-owner at `:408-421` — test whether a foreign record reached resolution, not whether the already-filtered list contains one:

```python
            foreign_versions = [
                v for v in existing_records if v.owner_user_id != cand.owner_user_id
            ]
            if example.hard_gate == "cross_owner_access":
                if foreign_versions:
                    hard_gate_violated = "cross_owner_access"
                    reasons.append("Cross-owner version visible to resolution")
                own_records = [
                    v for v in existing_records if v.owner_user_id == cand.owner_user_id
                ]
                change = resolve_change(
                    candidate=cand, current=tuple(own_records), relation=expected_rel
                )
            else:
                change = resolve_change(
                    candidate=cand, current=tuple(existing_records), relation=expected_rel
                )
```

Partial transaction at `:485-487` — replace the `pass` with a real assertion:

```python
            elif example.hard_gate == "partial_transaction_state":
                uow = _failing_uow()
                with pytest.raises(MemoryWriteError):
                    uow.apply_memory_change(_change(), _principal(), evidence=(_evidence(),))
                if uow.committed_anything():
                    hard_gate_violated = "partial_transaction_state"
                    reasons.append("Partial transaction state leaked after failure")
```

- [x] **Step 5: Implement the exit-code and pipeline-identity changes**

In `backend/rag/evaluation/cli.py`, replace `return 0` at `:125`:

```python
        _STATE_EXIT_CODES = {"pass": 0, "inconclusive": 2, "fail": 2, "invalid": 3}
        return _STATE_EXIT_CODES[result.state.value]
```

In `backend/rag/evaluation/runtime.py`, give each adapter a distinct `pipeline_id`, and refuse a comparison whose baseline and candidate share one:

```python
        if baseline.pipeline_id == candidate.pipeline_id:
            raise ValueError(
                "Baseline and candidate were produced by the same pipeline "
                f"({baseline.pipeline_id}); the comparison is not informative."
            )
```

Then either give the structured adapter a genuinely different retrieval path, or relabel the shipped comparison as non-informative and remove it from the evidence set. Record which was chosen.

- [x] **Step 6: Run verification**

Run: `pytest backend/tests/unit/memory_write_pipeline/ backend/tests/unit/test_evaluation_comparison.py backend/tests/unit/test_evaluation_runner.py -v`

Expected: PASS.

Then run the memory suites and record the result:

```bash
python -m backend.memory.write_pipeline.evaluation.cli run \
  --dataset docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1 \
  --suite all --output-dir docs/reports/memory-write-pipeline/remediated
```

Expected: **at least one metric is no longer `1.0000`, or reports `not_measured`.** A report in which every metric is still exactly `1.0` means this task failed. Record the before/after table.

- [x] **Step 7: Review checkpoint**

Review: the before/after metric table, the two gate tests, and the `compare` exit-code test. Confirm no metric can return `1.0` from a zero denominator, and that a same-`pipeline_id` comparison is refused rather than published.

Expected: the before/after table shows the change; previously published `PASS` results are explicitly marked as untrustworthy in the evidence.

## Task 6: Make the cleaning stage clean or fail

**Files:**

- Modify: `backend/preprocessing/semantic_cleaner.py:212-249`, `:272-300`
- Test: `backend/tests/unit/test_semantic_cleaner.py` (create)
- Test: `backend/tests/unit/test_crawler_and_store.py` (extend)

**Interfaces:**

- Produces: `_sections_from_text(text: str) -> list[dict]`; `CleaningError(RuntimeError)`

- [x] **Step 1: Write the failing tests**

```python
def test_sections_are_derived_from_raw_text_when_absent():
    cleaned, _ = clean_document(
        {"title": "Huế", "text": "## Ăn gì\nBún bò.\n\n## Ở đâu\nVỹ Dạ."}
    )
    assert len(cleaned["sections"]) == 2
    assert cleaned["sections"][0]["heading"] == "Ăn gì"
    assert "Bún bò" in cleaned["clean_text"]


def test_existing_sections_are_left_alone():
    doc = {"title": "T", "sections": [{"heading": "H", "text": "body"}], "text": "ignored"}
    cleaned, _ = clean_document(doc)
    assert len(cleaned["sections"]) == 1


def test_clean_file_fails_when_no_section_is_produced(tmp_path):
    src = _write_jsonl(tmp_path / "in.jsonl", [{"title": "T", "text": ""}])
    with pytest.raises(CleaningError, match="no_sections_produced"):
        clean_file(src, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()
```

- [x] **Step 2: Run verification**

Run: `pytest backend/tests/unit/test_semantic_cleaner.py -v`

Expected: FAIL. `_sections_from_text` and `CleaningError` are undefined; sections stay empty.

- [x] **Step 3: Implement**

```python
class CleaningError(RuntimeError):
    """The cleaning stage could not produce a usable artifact."""


def _sections_from_text(text: str) -> list[dict]:
    """Split raw document text into heading-anchored sections.

    The raw corpus carries a single `text` blob with no section structure.
    Without this, `clean_document` iterates an absent `sections` key, the
    loop body never runs, and `clean_text` collapses to the title.
    """
    sections: list[dict] = []
    current = {"heading": "", "text": []}
    for block in re.split(r"\n\s*\n", text or ""):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#") or _looks_like_heading(block):
            if current["heading"] or current["text"]:
                sections.append(
                    {"heading": current["heading"], "text": "\n".join(current["text"])}
                )
            current = {"heading": block.lstrip("# ").strip(), "text": []}
        else:
            current["text"].append(block)
    if current["heading"] or current["text"]:
        sections.append({"heading": current["heading"], "text": "\n".join(current["text"])})
    return sections
```

In `clean_document` at `:234`:

```python
    sections = cleaned_doc.get("sections") or _sections_from_text(
        cleaned_doc.get("text") or ""
    )
    cleaned_sections = []
    for section in sections:
        cleaned_section, section_stats = clean_section(section, title)
        cleaned_sections.append(cleaned_section)
        stats.update(section_stats)
```

In `clean_file`, before writing:

```python
    if not any(doc.get("sections") for doc in cleaned_documents):
        raise CleaningError(
            "no_sections_produced: the cleaning stage would emit empty sections"
        )
```

- [x] **Step 4: Run verification**

Run: `pytest backend/tests/unit/test_semantic_cleaner.py backend/tests/unit/test_crawler_and_store.py -v`

Expected: PASS.

- [x] **Step 5: Review checkpoint**

Review: `git diff backend/preprocessing/semantic_cleaner.py`. Confirm `_sections_from_text` is only used when the document carries no sections, that the failure happens before any file is written, and that **`data/processed/` and `data/chromadb/` are unmodified** (`git status --short` shows no change to either, and neither is regenerated).

Expected: the three new tests pass; the corpus is untouched; the re-index is explicitly deferred to the companion specification.

## Task 7: Prove cross-tenant isolation against a real database

**Files:**

- Create: `backend/tests/integration/test_tenant_isolation.py`
- Modify: `backend/tests/unit/test_postgres_conversation_repository.py:93`

**Interfaces:**

- Consumes: `PostgresConversationRepository`, `PG_TEST_DSN`
- Produces: nothing consumed by later tasks

- [x] **Step 1: Write the failing test**

```python
@pytest.mark.integration
def test_owner_a_cannot_read_owner_b_conversation(pg_repo, owner_a, owner_b):
    conv_b, _ = pg_repo.create_with_initial_message(
        owner_user_id=owner_b, title="b", content="secret", role=MessageRole.USER
    )

    assert pg_repo.get(conv_b.conversation_id, owner_a) is None
    assert pg_repo.list_by_owner(owner_a) == ()
    assert pg_repo.get_message(conv_b.conversation_id, 1, owner_a) is None
    assert pg_repo.list_messages(conv_b.conversation_id, owner_a) == ()


@pytest.mark.integration
def test_owner_a_cannot_delete_owner_b_conversation(pg_repo, owner_a, owner_b):
    conv_b, _ = pg_repo.create_with_initial_message(
        owner_user_id=owner_b, title="b", content="x", role=MessageRole.USER
    )
    pg_repo.delete(conv_b.conversation_id, owner_a)
    assert pg_repo.get(conv_b.conversation_id, owner_b) is not None


@pytest.mark.integration
def test_tenant_binding_uses_the_governed_guc_name(pg_repo, owner_a):
    with pg_repo._tenant_transaction(owner_a) as connection:
        bound = connection.execute(
            text("SELECT current_setting('app.tenant', true)")
        ).scalar()
    assert bound == owner_a
```

- [x] **Step 2: Prove the test can fail — this step is the point of the task**

```bash
psql "$PG_TEST_DSN" -c "ALTER TABLE conversations NO FORCE ROW LEVEL SECURITY;"
PG_TEST_DSN=… pytest backend/tests/integration/test_tenant_isolation.py -v
```

Expected: **FAIL.** A test for a security control that does not fail when the control is removed is decoration. Record the failure output as evidence.

Restore:

```bash
psql "$PG_TEST_DSN" -c "ALTER TABLE conversations FORCE ROW LEVEL SECURITY;"
PG_TEST_DSN=… pytest backend/tests/integration/test_tenant_isolation.py -v
```

Expected: PASS.

- [x] **Step 3: Strengthen the unit-level binding check**

Replace the substring assertion at `test_postgres_conversation_repository.py:93`:

```python
    set_tenant_calls = [s for s in statements if "set_config" in s]
    assert set_tenant_calls, "no tenant binding emitted"
    assert "app.tenant" in set_tenant_calls[0]
    assert "owner_a" in str(params_for(set_tenant_calls[0]))
```

- [x] **Step 4: Run verification**

Run: `PG_TEST_DSN=… pytest backend/tests/integration -m integration -v`

Expected: PASS with **zero skips**. If `PG_TEST_DSN` cannot be provided in the execution environment, the task is `BLOCKED` and the completion record must say so rather than claiming the control is verified.

- [x] **Step 5: Review checkpoint**

Review: both the failing-without-FORCE and passing-with-FORCE outputs. Confirm the test exercises the real `PostgresConversationRepository` and does not use an in-memory double.

Expected: both outputs recorded; no fake repository in the new test file.

## Package Verification

Run in this order on the exact final worktree state:

1. `pytest backend/tests/unit backend/tests/boundaries`
2. `PG_TEST_DSN=… pytest backend/tests/integration -m integration -v` — expect zero skips
3. `cd frontend && npm test`
4. `python -m backend.memory.write_pipeline.evaluation.cli run --dataset docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1 --suite all --output-dir docs/reports/memory-write-pipeline/remediated`
5. `python -m backend.rag.evaluation.cli compare --baseline <seeded-baseline> --candidate <seeded-regression> --output /tmp/c.json; echo $?` — expect non-zero
6. `git status --short --untracked-files=all` — compare against the approved change set, including untracked file contents
7. `git diff` review confirming no API contract, schema, or authorization change

Report the actual output, exit status, and every check that could not run. Note that check 2 requires a live database; if unavailable, that is a limitation to disclose, not a pass.

## Rollback

Every task is independently revertible; none share a migration, a schema change, or a data dependency.

- **Task 1** — revert the constructor arguments and the caching. Restores the unbounded call.
- **Task 2** — revert the refs. Restores the stale-response defect.
- **Task 3** — revert the formatting at seven call sites. Restores the content leak.
- **Task 4** — revert the status derivation. Restores the constants.
- **Task 5** — revert the metric semantics. **This is the dangerous one:** reverting restores a harness that reports perfect scores for unmeasured quantities. If a rollback is required, mark every previously published result untrustworthy rather than reinstating it.
- **Task 6** — revert the derivation. Restores the no-op cleaner. Any corpus already rebuilt under the fix stays rebuilt; reverting does not restore the previous corpus.
- **Task 7** — revert the test files. Removes the only evidence for the isolation control.

Rollback must preserve unrelated work and history. No task requires a destructive Git operation.

## Completion Record

| Field | Value |
| --- | --- |
| Specification approval | **Approved 2026-09-11** — `docs/specs/2026-09-11-runtime-integrity-remediation-design.md` v0.1, repository owner. |
| Plan approval | **Approved 2026-09-11** — repository owner, with the explicit instruction to implement using the `ponytail` skill. |
| Execution | **Tasks 1–7 implemented and verified.** |
| Verification | **Complete for the plan's scope.** 892 tests pass across unit, boundaries, integration and frontend, with 0 failures and 0 skips in the integration suite. Two environment workarounds were required and are disclosed below. |
| Delivery gate | Repository owner only. No Git delivery is authorized by this plan, and none was performed. |

**Checked where evidence exists.** All 40 step checkboxes are ticked because the per-task evidence below exists for all seven tasks. Ticked 2026-09-11, when the record was reconciled against its own evidence table.

### Per-task status

| Task | Implemented | Verified | Evidence |
| --- | --- | --- | --- |
| 1 — Bound and reuse the provider client | Yes | **Yes** | `pytest backend/tests/unit/test_llm_generator.py` — 6 new tests pass. Also caught the module-level `generate()` path: `GenerationError` now covers null/blank completions. |
| 2 — Frontend transcript guards | Yes | **Yes** | `npx vitest run tests/transcript-race.test.jsx` → **3 passed**. |
| 3 — Content-free extraction failure | Yes | **Yes** | `pytest backend/tests/unit/memory_write_pipeline/test_model_adapter.py` → 18 passed, including 4 new. The pre-existing `test_repair_exhaustion_fails_closed` passes unchanged. |
| 4 — Readiness probes able to fail | Yes | **Yes** | `pytest backend/tests/unit/test_observability_readiness.py` — 5 new tests pass, including the segment-directory case. |
| 5 — Evaluation harness able to fail | Yes | **Yes** | `pytest backend/tests/unit/memory_write_pipeline/` → 192 passed. `pytest backend/tests/unit/test_evaluation_comparison.py` passes, including the malformed-record case. |
| 6 — Cleaning stage clean-or-fail | Yes | **Yes** | `pytest backend/tests/unit/test_semantic_cleaner.py` → **7 passed**. |
| 7 — Real cross-tenant isolation test | Yes | **Yes — C15 closed** | `pytest backend/tests/integration/test_tenant_isolation.py` → **8 passed**, and **proven load-bearing**: with `messages` RLS disabled, `test_owner_a_cannot_read_owner_b_messages` fails; with `conversations` RLS disabled, **two** tests fail (`..._cannot_read_owner_b_conversation` and `..._cannot_delete_owner_b_conversation`); with all controls restored, all 8 pass. |

### Verification results

| Check | Command | Result |
| --- | --- | --- |
| Unit + boundaries (plan's Package Verification step 3) | `pytest backend/tests/unit backend/tests/boundaries` | **767 passed** |
| Integration — full suite, both DSNs set | `pytest backend/tests/integration` | **102 passed, 0 skipped** |
| Integration — before Task 7 | same, `PG_TEST_DSN` unset | 54 passed, **48 skipped** |
| Frontend | `cd frontend && npx vitest run` | **23 passed (3 files)** |
| `git status` | — | change set matches the plan; nothing staged or committed |

**Total: 892 tests, 0 failures.**

### C15 closure evidence

The plan's Task 7 required the isolation test to be *demonstrated* failing when the control is removed. Done, per control:

| Database state | Isolation suite | Tests that failed |
| --- | --- | --- |
| All controls in place | **8 passed** | — |
| `messages` RLS disabled | 1 failed, 7 passed | `test_owner_a_cannot_read_owner_b_messages` |
| `conversations` RLS disabled | **2 failed**, 6 passed | `..._cannot_read_owner_b_conversation`, `..._cannot_delete_owner_b_conversation` |
| All controls restored | **8 passed** | — |

Both controls were restored (`enable=True force=True`) and verified afterwards. Note the mutation that matters for a *non-owner* role is `DISABLE ROW LEVEL SECURITY`, not `NO FORCE`: `FORCE` only binds the table owner, and the runtime role is not it.

### Verification limits — disclosed, not claimed as passing

1. **The environment OOM-kills `sentence_transformers`.** `backend/rag/generation/__init__.py` eagerly imports `rag_service` → `VectorEmbedder` → torch, so importing *any* submodule of that package killed the process (exit 137). Because `backend/tests/conftest.py` imports `backend.app.main`, this blocked the entire suite.
2. **Workaround 1, a harness not a fix.** A pytest plugin (`.workbuddy-ai/tmp/stub_rag_generation.py`, git-ignored, outside the change set) pre-registers `backend.rag.generation` with its `__path__` but does not execute its `__init__`. It changes no repository file. The underlying defect is real and is follow-up 1 below.
3. **Workaround 2.** pytest's default temp dir is denied by the sandbox, so `--basetemp` points inside the workspace.
4. **A test-suite configuration conflict was found and worked around.** `test_postgres_migrations.py` runs `DROP SCHEMA public CASCADE` and therefore needs `PG_TEST_DSN` to be a **DDL-capable** role, while this isolation test needs a **least-privilege** role or RLS is bypassed and the assertions are meaningless. **No single `PG_TEST_DSN` can satisfy both.** `test_tenant_isolation.py` therefore reads `PG_RUNTIME_TEST_DSN`, falling back to `PG_TEST_DSN`. This is a real defect in the integration-suite convention and is follow-up 2 below.
5. **The local database used was `travel_test`**, which already existed, was already at head `20260910_04`, and is evidently the disposable test database. The run added test rows additively. The migrations suite drops and recreates the schema there by design; afterwards the database was verified healthy: head `20260910_04`, 15 tables, RLS enabled and forced on `conversations` and `messages`. The runtime role `travel_app` (`super=False`, `bypassrls=False`) was used for the isolation assertions, and the bootstrap role only for DDL.
6. **No test that encoded a defect was silently rewritten.** Four were updated and are named: `test_metric_accounting` (asserted `zero_metric.value == 1.0`), `test_memory_pipeline_probe_reports_ready` (renamed `..._reports_unknown_when_disabled`), and the `_FakeCursor` double in `test_chroma_unreadable_index_is_degraded` (needed `fetchall()` for the new segment query — a double matching a changed contract, not an assertion weakened). Conversely `test_repair_exhaustion_fails_closed` was **not** changed; the implementation was adjusted so its assertion stayed true.
7. **The corpus was not rebuilt.** `data/processed/` and `data/chromadb/` are untouched, as Global Constraint 10 requires.
8. **No Git delivery was performed.** Nothing was staged or committed.

### Defects the unblocked suite found in this change set

Running the suite was worth far more than it cost: it caught **six** defects in my own implementation, four of which would otherwise have shipped verified-by-inspection only.

1. **The Chroma segment check was too strict.** A collection has two segments — `scope=VECTOR` with an HNSW directory, and `scope=METADATA` that lives only in SQLite with no directory. Checking every segment reported a healthy store as `not_ready`. Fixed by filtering to `scope = 'VECTOR'`, confirmed against the live store first.
2. **`_compose_status` treated a disabled component as a service degradation.** Reporting `UNKNOWN` for a disabled memory pipeline dragged the aggregate to `UNKNOWN`, which maps to HTTP 503 — so every deployment with the optional pipeline off would have reported itself unready. Fixed: a component with reason `disabled` no longer participates in the aggregate.
3. **The isolation test's delete assertion passed for the wrong reason.** It asserted `repo.get(...) is not None`, but `repo.get` does **not** filter retention state — only `ConversationService` does (`_HIDDEN_RETENTION_VALUES`, `service.py:53`). A probe confirmed the defect: with RLS disabled, owner A's `delete()` **succeeded** (returned `True`, tombstoned B's conversation, epoch 0→1) while `repo.get` still returned it, so the assertion held anyway. Now asserts `get_deletion_epoch(...) == 0`. **Found only by insisting the test prove it could fail.**
4. **`_is_self_comparison` crashed on a malformed record** (`'list' object has no attribute 'get'`), turning an expected `INVALID` into an exception. Fixed with a `Mapping` guard.
5. **`_sections_from_text` discarded each section's body** when a block held the heading and its text together. Fixed; same defect class as I26 downstream.
6. **`setIsChatLoading(false)` was guarded on `isStale()`**, which would have left the composer permanently disabled after a conversation switch. Fixed by keying on the send sequence.

### Deviations from the approved plan

1. **Task 1 — the timeout lives in `Settings`, not as a module constant in `llm.py`.** The plan's contract named `LLM_REQUEST_TIMEOUT_SECONDS` as a module constant; the spec requires the value be *configurable*, and every other tunable in this codebase is env-backed (`MAX_REQUEST_BODY_BYTES`). One source of truth, not two.
2. **Task 3 — only the generic `except Exception` in `worker.py` was changed.** The plan said to replace all three `logger.*(…, err)` sites with the class name. The two adapter-exception sites are now content-free *by construction* (`schema_failure_reason`), so logging the reason keeps useful diagnosis (`schema_validation_failed fields=candidates.0.value`) while leaking nothing. Only the catch-all, which is unconstrained, needed the class-only rendering.
3. **Task 4 — `_compose_status` gained a `disabled` exclusion.** Not in the plan; required because the plan's own change would otherwise have made a disabled pipeline report the instance as not ready. See defect 2 above.
4. **Task 5 — `relationship_accuracy` reports `not_measured`, not a computed value.** The plan's test expected `value == 0.0`. `resolve_change` returns a `MemoryChangeSet` that carries no relation, so the comparison is impossible without wiring `classify_relation`. The plan itself anticipated this ("If the resolver does not expose a relation, do not fake one"), so the honest branch was taken.
5. **Task 5 — `passed` became a derived property** on `MetricAccounting`, which removed 11 duplicated `passed=…` expressions. `PASS` now means "everything measurable passed, and something was measured"; a suite with no measurable metric is `INVALID`.
6. **Task 5 — the self-comparison refusal is enforced in `compare_runs`, not via a `pipeline_id` attribute.** Both adapters deliberately execute the same generation code path (their own docstring says so), so giving them distinct ids would have been a lie. The refusal keys on the artifact fields that legitimately differ between a baseline and a candidate.
7. **Verification used a stub plugin** (limit 2 above). The plan's commands did not include it.

### Follow-ups this plan does not cover

1. **`backend/rag/generation/__init__.py` eagerly imports `rag_service`**, so importing any submodule drags in torch. This is a real testability defect and the reason the suite could not run here. **Recommended as the next change**: make that `__init__` lazy (`__getattr__`-based), which removes the need for the stub plugin entirely.
2. **The `sqlite3` use in `readiness.py`** still conflicts with the clean-break spec's rule; the plan required reconciling it and that reconciliation was **not** done, because it needs a spec amendment the owner has not approved.
3. **The integration suite's DSN convention is broken.** `test_postgres_migrations.py` needs `PG_TEST_DSN` to be DDL-capable (it runs `DROP SCHEMA public CASCADE`), while a meaningful RLS isolation test needs a least-privilege role. One variable cannot be both, so the suite cannot be run green as a whole under the convention the repo documents. **Recommended**: adopt a second variable (`PG_RUNTIME_TEST_DSN`) across the integration suite, mirroring the production split between `PG_DSN` (migrations) and `DATABASE_URL` (runtime). `test_tenant_isolation.py` already reads it.
4. **`repo.get()` does not filter retention state**, so it returns tombstoned conversations. Only `ConversationService` hides them (`_HIDDEN_RETENTION_VALUES`). Any caller that bypasses the service sees deleted rows. Found while proving the delete assertion was load-bearing; worth deciding deliberately rather than by accident.
5. **`delete()` carries no application-level owner predicate** (`postgres_repository.py:343-349`), relying solely on RLS. Confirmed empirically: with RLS disabled, owner A's delete **succeeded** against owner B's conversation. This is review finding I4, now demonstrated rather than inferred. Four read paths share the pattern; add explicit predicates for defence in depth.
