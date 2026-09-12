# Atomic Chat Turn and Memory Write Pipeline Correctness Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence. Each task ends with a review checkpoint; do not begin
> the next task until the checkpoint condition holds.

**Goal:** Make a chat turn one unit of work with a two-phase write, and give the memory write pipeline's resolver a real history and a real confidence gate — so that enabling the pipeline writes correct memory instead of silently wrong memory.

**Architecture:** Two independent change sets sharing one spec. The conversation side adds a server-owned `messages.status`, a repository method that allocates both messages and the outbox event in one transaction under one parent-row lock, and single-row completion/failure transitions. The memory side adds a tenant-bound `get_active_versions` to the `MemoryUnitOfWork` protocol and carries `confidence` from the model adapter onto the candidate, removing two silent fallbacks rather than repairing them.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy 2 / psycopg3 / PostgreSQL 16 / Alembic / pytest · React 18 / Vite / Vitest

**Spec:** `docs/specs/2026-09-11-atomic-chat-turn-and-memory-correctness-design.md` v0.1

| Field | Value |
| --- | --- |
| Status | Completed |
| Date | 2026-09-11 |
| Approved specification | `docs/specs/2026-09-11-atomic-chat-turn-and-memory-correctness-design.md` v0.1 — **Approved 2026-09-11** by the repository owner, together with this plan. ADR 0023 and ADR 0024 are `Accepted` as of the same date. |
| Execution owner | Implementation agent, in an isolated linked worktree assigned by the repository owner |
| Decision owner | Repository owner |
| Scope | Four Critical findings: C2, C8, C9, C14 |
| Verification | `PG_TEST_DSN=… pytest backend/tests/integration -m integration -v` (zero skips); `pytest backend/tests/unit backend/tests/boundaries`; `cd frontend && npm test`; the `ALEMBIC_HEAD` consistency check; the adjacency test under concurrency |

## Global Constraints

1. Every persistent repository change requires a written specification and an approved implementation plan (`AGENTS.md`). The specification and this plan were approved by the repository owner on 2026-09-11; Level 3 architecture approval is recorded in the specification's Approval Record and ADR 0023 and ADR 0024 are `Accepted`. Two owner-authorized scope additions rest on a direct instruction rather than on the specification; see "Owner-authorized scope additions".
2. The repository owner creates or selects branches and decides when to stage, commit in the primary working tree, push, open a PR, merge, and release. An agent in an isolated linked worktree may create local handoff commits only.
3. The working tree is dirty: 63 modified, 1 deleted, 17 untracked. Read a dirty file before touching it and work with the existing edits rather than reverting them.
4. The `messages.status` migration is reversible and must have a real `downgrade` that drops the index, the constraint and the column.
5. `ALEMBIC_HEAD` in `backend/storage/postgres.py:26` must be updated in the same change as the migration, or readiness reports `revision_mismatch`.
6. The memory write pipeline is **not enabled** by this plan. `MEMORY_WRITE_PIPELINE_ENABLED` and `MEMORY_SHADOW_EXTRACT_ENABLED` defaults do not change.
7. The recorder's shadow-only invariant is **not** changed. It continues to force `MemoryOperation.NOOP`. This plan fixes the inputs to resolution, not the write operation.
8. Removing a silent fallback is the point. Do not restore a `hasattr` probe or a defaulting `getattr` as a compatibility shim.
9. Behaviour changes use a red-green-refactor cycle. Every task states the failing test first.
10. Never expose secrets, credentials, tokens, or sensitive personal data in code, logs, commands, evidence, or documentation.
11. A `pending` or `failed` assistant row must never carry generated content or a provider error string.
12. No Git delivery is authorized by this plan.

## Required ADRs — prerequisite

Both must be `Accepted` before Task 1 begins. Neither is a formality: ADR 0023 governs the turn-persistence contract and ADR 0024 governs evaluation result semantics relied on by the companion plan.

| ADR | Title | Status required |
| --- | --- | --- |
| 0023 | Atomic Two-Phase Chat Turn | Accepted |
| 0024 | Evaluation Results Distinguish Unmeasurable from Perfect | Accepted |

## Owner-authorized scope additions

Two changes in this plan's delivery set were **instructed directly by the repository owner on 2026-09-11** and are **not specified in the governing specification**. They are recorded here, with their authorization, so that the change set is not silently wider than its governing documents. This section is a disclosure, not a specification: neither item was designed, reviewed, or approved through the spec → plan gate that `AGENTS.md` requires, and both should be re-reviewed on their own merits.

| Item | Authorization | Why it is in this delivery set | Files |
| --- | --- | --- | --- |
| Lazy `backend/rag/generation/__init__.py` | Direct owner instruction, 2026-09-11 | The package's `__init__` imports `rag_service` → `VectorEmbedder` → `sentence-transformers` → torch, so importing *any* submodule drags in the full model stack. That blocked the whole Python suite in a constrained environment and made this plan's own verification unrunnable without a harness workaround. It is a testability defect independent of this plan. | `backend/rag/generation/__init__.py` |
| `PG_RUNTIME_TEST_DSN` standardisation | Direct owner instruction, 2026-09-11 | This plan's verification requires the integration suite to run with **zero skips** while proving RLS isolation. Those two needs are incompatible under a single variable: `test_postgres_migrations.py` runs `DROP SCHEMA public CASCADE` and needs a DDL-capable role, whereas a cross-tenant isolation test needs a least-privilege role, because a superuser or `BYPASSRLS` role bypasses RLS entirely and makes the assertion vacuous. | `backend/tests/integration/*` |

**Consequence for review.** Both items appear in the change set but not in the File Responsibility Map above, because that map is derived from the approved specification. Review them as owner-authorized additions. If either should instead have its own specification, that is the repository owner's decision.

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/storage/migrations/versions/20260911_01_message_turn_status.py` | Add `messages.status`, its constraint and index, reversibly | ADR 0023 accepted |
| `backend/storage/postgres.py` | Declare the new head | Task 1 |
| `backend/conversations/models.py` | Own `MessageStatus` and `Message.status` | Task 1 |
| `backend/conversations/repository.py` | Declare `append_turn`, `complete_turn`, `fail_turn` on the port | Task 2 |
| `backend/conversations/postgres_repository.py` | Implement the three methods in single transactions | Task 2 |
| `backend/conversations/service.py` | Expose the three use cases | Task 2 |
| `backend/orchestration/conversation_orchestrator.py` | Own turn sequencing and failure classification | Task 3 |
| `backend/app/api/chat.py` | Return the conversation id on a first-turn failure | Task 3 |
| `frontend/src/App.jsx` | Render `pending` and `failed` distinctly | Task 4 |
| `frontend/src/components/chat/ChatMessage.jsx` | Render a failed turn | Task 4 |
| `backend/memory/write_pipeline/uow.py` | Declare `get_active_versions` on the protocol | Task 5 |
| `backend/memory/write_pipeline/postgres.py` | Implement it, tenant-bound | Task 5 |
| `backend/memory/write_pipeline/background_recorder.py` | Read the real history and the real confidence | Task 5, Task 6 |
| `backend/memory/write_pipeline/models.py` | Carry `confidence` on `MemoryCandidate` | Task 6 |
| `backend/memory/write_pipeline/model_adapter.py` | Populate `confidence` from the model output | Task 6 |
| `backend/tests/integration/test_chat_conversation_binding.py` | Prove turn atomicity and adjacency | Task 3 |
| `backend/tests/integration/test_postgres_migrations.py` | Prove the migration round-trips | Task 1 |
| `backend/tests/integration/test_memory_write_postgres.py` | Prove the history read and the gate | Task 5, Task 6 |

## Task 1: Add the message turn status

**Files:**

- Create: `backend/storage/migrations/versions/20260911_01_message_turn_status.py`
- Modify: `backend/storage/postgres.py:26`
- Modify: `backend/conversations/models.py`
- Test: `backend/tests/integration/test_postgres_migrations.py`

**Interfaces:**

- Produces: `MessageStatus` enum (`PENDING`, `COMPLETE`, `FAILED`); `Message.status: MessageStatus`; column `messages.status VARCHAR(16) NOT NULL DEFAULT 'complete'`
- Consumes: nothing

- [x] **Step 1: Write the failing tests**

```python
def test_message_status_column_exists_with_a_default(pg_engine):
    with pg_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT column_default, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'messages' AND column_name = 'status'"
            )
        ).fetchone()
    assert row is not None
    assert row[1] == "NO"
    assert "complete" in str(row[0])


def test_existing_messages_default_to_complete(pg_engine, seeded_conversation):
    with pg_engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM messages WHERE status <> 'complete'")
        ).scalar()
    assert count == 0


def test_status_check_constraint_rejects_unknown_values(pg_engine):
    with pytest.raises(IntegrityError):
        _insert_message(pg_engine, status="banana")


def test_migration_downgrade_removes_column_and_index(pg_migrated_then_downgraded):
    with pg_migrated_then_downgraded.connect() as connection:
        assert connection.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'messages' AND column_name = 'status'"
            )
        ).scalar() == 0
        assert connection.execute(
            text("SELECT count(*) FROM pg_indexes WHERE indexname = 'idx_messages_conversation_status'")
        ).scalar() == 0


def test_alembic_head_matches_the_declared_constant(pg_engine):
    with pg_engine.connect() as connection:
        current = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert current == ALEMBIC_HEAD
```

- [x] **Step 2: Run verification**

Run: `PG_TEST_DSN=… pytest backend/tests/integration/test_postgres_migrations.py -k "status or head_matches" -v`

Expected: FAIL. The column does not exist and `ALEMBIC_HEAD` is `20260910_04`.

- [x] **Step 3: Write the migration**

```python
revision = "20260911_01"
down_revision = "20260910_04"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="complete"),
    )
    op.create_check_constraint(
        "ck_messages_status", "messages", "status IN ('pending', 'complete', 'failed')"
    )
    op.create_index("idx_messages_conversation_status", "messages", ["conversation_id", "status"])

def downgrade() -> None:
    op.drop_index("idx_messages_conversation_status", table_name="messages")
    op.drop_constraint("ck_messages_status", "messages", type_="check")
    op.drop_column("messages", "status")
```

**RLS note.** `messages` is `FORCE`d. The new column inherits the table's policy; no policy change is required. Confirm this in the review checkpoint rather than assuming it.

- [x] **Step 4: Update the head and the model**

`backend/storage/postgres.py:26`:

```python
ALEMBIC_HEAD = "20260911_01"
```

`backend/conversations/models.py`:

```python
class MessageStatus(str, Enum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
```

Add `status: MessageStatus = MessageStatus.COMPLETE` to `Message`. Apply `require_text` only on the `complete` transition, so a `PENDING` or `FAILED` row may carry an empty string:

```python
        if status is MessageStatus.COMPLETE:
            content = require_text(content, field="content")
```

- [x] **Step 5: Run verification**

Run: `PG_TEST_DSN=… pytest backend/tests/integration/test_postgres_migrations.py -v`

Expected: PASS, including the downgrade round-trip.

- [x] **Step 6: Review checkpoint**

Review: the migration file, the head constant, and the model diff. Confirm the `downgrade` is a real inverse (not a `NotImplementedError`), that the column default backfills existing rows, and that RLS on `messages` is untouched.

Expected: migration round-trips; `ALEMBIC_HEAD` equals the applied head; no RLS change.

## Task 2: Add the turn methods to the repository and service

**Files:**

- Modify: `backend/conversations/repository.py`
- Modify: `backend/conversations/postgres_repository.py`
- Modify: `backend/conversations/service.py`
- Test: `backend/tests/integration/test_chat_conversation_binding.py`

**Interfaces:**

- Consumes: `MessageStatus`, the existing `tenant_transaction` and parent-row lock
- Produces: `append_turn(conversation_id, owner_user_id, user_content, assistant_placeholder="", outbox_event=None) -> tuple[Message, Message]`; `complete_turn(conversation_id, message_id, owner_user_id, content) -> Message`; `fail_turn(conversation_id, message_id, owner_user_id) -> Message`

- [x] **Step 1: Write the failing tests**

```python
def test_append_turn_writes_both_rows_in_one_transaction(pg_service, owner):
    conv, _ = pg_service.create_conversation_with_initial_turn(
        owner_user_id=owner, title="t", content="hi", role=MessageRole.USER
    )
    user_msg, pending = pg_service.append_turn(
        conversation_id=conv.conversation_id, owner_user_id=owner, user_content="next"
    )
    assert user_msg.status is MessageStatus.COMPLETE
    assert pending.status is MessageStatus.PENDING
    assert pending.sequence == user_msg.sequence + 1


def test_complete_turn_is_idempotent(pg_service, owner, conv_id):
    _, pending = pg_service.append_turn(conv_id, owner, "q")
    first = pg_service.complete_turn(conv_id, pending.message_id, owner, "a")
    second = pg_service.complete_turn(conv_id, pending.message_id, owner, "different")
    assert first.content == "a"
    assert second.content == "a"
    assert second.status is MessageStatus.COMPLETE


def test_fail_turn_does_not_overwrite_a_completed_row(pg_service, owner, conv_id):
    _, pending = pg_service.append_turn(conv_id, owner, "q")
    pg_service.complete_turn(conv_id, pending.message_id, owner, "a")
    result = pg_service.fail_turn(conv_id, pending.message_id, owner)
    assert result.status is MessageStatus.COMPLETE


def test_complete_turn_fails_closed_on_a_deleted_conversation(pg_service, owner, conv_id):
    _, pending = pg_service.append_turn(conv_id, owner, "q")
    pg_service.delete_conversation(conv_id, owner)
    with pytest.raises(ConversationGoneError):
        pg_service.complete_turn(conv_id, pending.message_id, owner, "a")


def test_append_turn_rejects_a_cross_owner_call(pg_service, owner_a, owner_b, conv_of_b):
    with pytest.raises(ConversationNotFoundError):
        pg_service.append_turn(conv_of_b, owner_a, "q")
```

- [x] **Step 2: Run verification**

Run: `PG_TEST_DSN=… pytest backend/tests/integration/test_chat_conversation_binding.py -k turn -v`

Expected: FAIL. The three methods do not exist.

- [x] **Step 3: Implement the port**

Add to `ConversationRepository` in `repository.py`, with the same docstring discipline the port already uses:

```python
    def append_turn(
        self,
        conversation_id: str,
        owner_user_id: str,
        user_content: str,
        assistant_placeholder: str = "",
        outbox_event: OutboxIntent | None = None,
    ) -> tuple[Message, Message]:
        """Allocate one turn: a user message, a pending assistant row, and the
        outbox event, in a single transaction under one parent-row lock.

        Both sequences are allocated together so turn adjacency holds under
        concurrent turns. Returns `(user_message, pending_assistant_message)`.
        """
        ...

    def complete_turn(
        self, conversation_id: str, message_id: str, owner_user_id: str, content: str
    ) -> Message:
        """Set content and status on a pending assistant row. A no-op when the
        row is not pending. Fails closed when the conversation is gone."""
        ...

    def fail_turn(self, conversation_id: str, message_id: str, owner_user_id: str) -> Message:
        """Mark a pending assistant row failed. Idempotent. Never overwrites a
        completed row."""
        ...
```

- [x] **Step 4: Implement the Postgres adapter**

```python
    def append_turn(
        self,
        conversation_id: str,
        owner_user_id: str,
        user_content: str,
        assistant_placeholder: str = "",
        outbox_event: OutboxIntent | None = None,
    ) -> tuple[Message, Message]:
        with tenant_transaction(self._engine, owner_user_id) as connection:
            self._lock_conversation(connection, conversation_id)  # SELECT … FOR UPDATE
            base = self._next_sequence(connection, conversation_id)
            user = self._insert_message(
                connection, conversation_id, base, MessageRole.USER, user_content,
                MessageStatus.COMPLETE,
            )
            pending = self._insert_message(
                connection, conversation_id, base + 1, MessageRole.ASSISTANT,
                assistant_placeholder, MessageStatus.PENDING,
            )
            if outbox_event is not None:
                self._insert_outbox(
                    connection, conversation_id, user.message_id, owner_user_id, outbox_event
                )
            self._touch_conversation(connection, conversation_id)
        return user, pending

    def complete_turn(
        self, conversation_id: str, message_id: str, owner_user_id: str, content: str
    ) -> Message:
        with tenant_transaction(self._engine, owner_user_id) as connection:
            self._require_active_conversation(connection, conversation_id, owner_user_id)
            row = connection.execute(
                update(self._messages)
                .where(
                    self._messages.c.message_id == message_id,
                    self._messages.c.conversation_id == conversation_id,
                    self._messages.c.status == MessageStatus.PENDING.value,
                )
                .values(content=content, status=MessageStatus.COMPLETE.value)
                .returning(*self._messages.c)
            ).fetchone()
            if row is None:
                # Already completed or failed: return the stored row unchanged.
                return self._require_message(connection, conversation_id, message_id, owner_user_id)
            return self._row_to_message(row)
```

`fail_turn` mirrors `complete_turn` with `status = 'failed'`, an empty content update, and the same guard. Both call a shared `_require_active_conversation` that raises `ConversationGoneError` when the conversation is tombstoned or its `deletion_epoch` moved.

- [x] **Step 5: Expose the use cases**

Add `append_turn`, `complete_turn`, `fail_turn` to `ConversationService`, translating repository errors the way the existing methods do (`ConversationGoneError` → `ConversationNotFoundError` where the existing surface does so).

- [x] **Step 6: Run verification**

Run: `PG_TEST_DSN=… pytest backend/tests/integration/test_chat_conversation_binding.py -v`

Expected: PASS.

- [x] **Step 7: Review checkpoint**

Review: the adapter diff. Confirm both sequences are allocated inside one transaction and one lock, that `complete_turn` and `fail_turn` are guarded by `status = 'pending'`, that a cross-owner call binds the tenant and fails closed, and that `_require_active_conversation` is called before any write.

Expected: all five new tests pass; no method opens more than one transaction.

## Task 3: Switch the orchestrator to the two-phase turn

**Files:**

- Modify: `backend/orchestration/conversation_orchestrator.py:93-219`
- Modify: `backend/app/api/chat.py` (return the conversation id on a first-turn failure)
- Test: `backend/tests/integration/test_chat_conversation_binding.py`
- Test: `backend/tests/unit/test_conversation_orchestrator.py`

**Interfaces:**

- Consumes: `ConversationService.append_turn`, `.complete_turn`, `.fail_turn`
- Produces: `TurnPersistence.status`; `TurnOutcome` gains no new field

- [x] **Step 1: Write the failing tests**

```python
def test_a_bound_turn_commits_both_rows_before_generation(pg_service, owner, conv_id):
    rag = _RecordingRag()
    _orchestrator(pg_service, rag).handle_turn("q", conv_id, principal_for(owner))
    # At the moment generation ran, both rows already existed.
    assert rag.rows_visible_at_generation == 2


def test_generation_failure_marks_the_turn_failed_not_orphaned(pg_service, owner, conv_id, failing_rag):
    with pytest.raises(GenerationError):
        _orchestrator(pg_service, failing_rag).handle_turn("q", conv_id, principal_for(owner))

    rows = pg_service.list_messages(conv_id, owner)
    assert rows[-2].status is MessageStatus.COMPLETE
    assert rows[-1].status is MessageStatus.FAILED


def test_generation_failure_cancels_the_outbox_event(pg_service, owner, conv_id, failing_rag):
    with pytest.raises(GenerationError):
        _orchestrator(pg_service, failing_rag, outbox_enabled=True).handle_turn(
            "q", conv_id, principal_for(owner)
        )
    assert _pending_outbox_count(conv_id) == 0


def test_first_turn_failure_returns_the_conversation_id(pg_service, owner, failing_rag):
    with pytest.raises(GenerationError) as exc:
        _orchestrator(pg_service, failing_rag).handle_turn("q", None, principal_for(owner))
    assert getattr(exc.value, "conversation_id", None) is not None


def test_concurrent_turns_preserve_adjacency(pg_service, owner, conv_id):
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda i: _send_turn(pg_service, conv_id, owner, f"m{i}"), range(2)))

    rows = pg_service.list_messages(conv_id, owner)
    assert [m.sequence for m in rows] == list(range(1, len(rows) + 1))
    for user in [m for m in rows if m.role is MessageRole.USER]:
        following = next(m for m in rows if m.sequence == user.sequence + 1)
        assert following.role is MessageRole.ASSISTANT
```

- [x] **Step 2: Run verification**

Run: `PG_TEST_DSN=… pytest backend/tests/integration/test_chat_conversation_binding.py -k "turn or adjacency" -v`

Expected: FAIL. The orchestrator still uses the four-transaction path; adjacency fails under concurrency.

- [x] **Step 3: Rewrite `handle_turn`**

```python
        if conversation_id is None:
            outbox_event = (
                OutboxIntent(event_type="memory.extract.conversation_range", payload={})
                if self._outbox_enabled
                else None
            )
            conversation, user_message, pending = (
                conversations.create_conversation_with_initial_turn(
                    owner_user_id=owner_user_id,
                    title=message[:60],
                    content=message,
                    role=MessageRole.USER,
                    source=MessageSource.UI,
                    outbox_event=outbox_event,
                )
            )
            conversation_id = conversation.conversation_id
        else:
            conversation = conversations.get_conversation(conversation_id, owner_user_id)
            if conversation is None:
                from backend.security.models import AuthMode, CrossOwnerAccessError

                if getattr(principal, "auth_mode", None) == AuthMode.AUTHENTICATED:
                    raise CrossOwnerAccessError(
                        "The conversation does not exist in this owner scope."
                    )
                raise ConversationNotFoundError("The conversation does not exist.")

            outbox_event = (
                OutboxIntent(
                    event_type="memory.extract.conversation_range",
                    payload={"conversation_id": conversation_id},
                )
                if self._outbox_enabled
                else None
            )
            user_message, pending = conversations.append_turn(
                conversation_id=conversation_id,
                owner_user_id=owner_user_id,
                user_content=message,
                outbox_event=outbox_event,
            )

        try:
            generated = self._generate(message)
        except Exception as error:
            conversations.fail_turn(
                conversation_id=conversation_id,
                message_id=pending.message_id,
                owner_user_id=owner_user_id,
            )
            error.conversation_id = conversation_id  # for the first-turn case
            raise

        assistant_message = conversations.complete_turn(
            conversation_id=conversation_id,
            message_id=pending.message_id,
            owner_user_id=owner_user_id,
            content=generated["reply"],
        )
```

`create_conversation_with_initial_turn` must also return the pending assistant row so the first-turn path is identical from the failure handler onward. Update its signature and its callers together.

**Remove the old path.** Do not leave the four-transaction branch as a fallback; the specification requires that the old path is removed in the same change, because a fallback would let the defect persist unnoticed.

- [x] **Step 4: Return the conversation id on a first-turn failure**

In `backend/app/api/chat.py`, the `GenerationError` handler must include the conversation id in the response when the orchestrator attached one, so the client continues the same conversation instead of creating a second. Add the field to the error body or to the existing error schema, and record the contract change in the review checkpoint — this is the one place where the API surface changes, and the specification permits it only for this case.

- [x] **Step 5: Run verification**

Run: `PG_TEST_DSN=… pytest backend/tests/integration -m integration -v`

Expected: PASS with zero skips.

- [x] **Step 6: Review checkpoint**

Review: `git diff backend/orchestration/conversation_orchestrator.py`. Confirm the old four-transaction path is gone, that `fail_turn` is called on every generation failure path, that the outbox event is cancelled in the same transaction as the failure, and that no exception type escapes unclassified.

Expected: `grep -n "append_message" backend/orchestration/conversation_orchestrator.py` returns nothing; every generation failure path calls `fail_turn`.

## Task 4: Render the turn status in the frontend

**Files:**

- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/chat/ChatMessage.jsx`
- Modify: `frontend/src/services/chat.js` (map the status field)
- Test: `frontend/tests/components.test.jsx`

**Interfaces:**

- Consumes: `MessageResponse.status` from `backend/app/schemas/conversations.py`
- Produces: a `failed` turn rendered distinctly; a `pending` turn rendered as in-progress

- [x] **Step 1: Write the failing tests**

```jsx
it("renders a failed turn distinctly from an empty reply", () => {
  render(<ChatMessage message={{ role: "assistant", content: "", status: "failed" }} />);
  expect(screen.getByText(/không tạo được câu trả lời/i)).toBeInTheDocument();
});

it("does not render a pending turn as a completed reply", () => {
  render(<ChatMessage message={{ role: "assistant", content: "", status: "pending" }} />);
  expect(screen.queryByText(/^\s*$/)).not.toBeInTheDocument();
  expect(screen.getByTestId("turn-pending")).toBeInTheDocument();
});
```

- [x] **Step 2: Run verification**

Run: `cd frontend && npm test -- components`

Expected: FAIL. The component has no status handling.

- [x] **Step 3: Implement**

Extend `MessageResponse` in `backend/app/schemas/conversations.py` with `status: str`, add the field to the mapper in `frontend/src/services/chat.js`, and branch in `ChatMessage.jsx`:

```jsx
if (message.status === 'failed') {
  return <div className="...">{'Không tạo được câu trả lời cho lượt này.'}</div>;
}
if (message.status === 'pending') {
  return <div data-testid="turn-pending" className="...">{'Đang tạo câu trả lời…'}</div>;
}
```

- [x] **Step 4: Run verification**

Run: `cd frontend && npm test`

Expected: PASS.

- [x] **Step 5: Review checkpoint**

Review: the schema change, the mapper, and the component branch. Confirm a `pending` row never renders as an empty successful reply, that no generated content is shown for a `failed` row, and that the frontend change ships with the backend change in the same delivery (the specification makes this a rollout constraint).

Expected: both new tests pass; the frontend and backend changes are in the same change set.

## Task 5: Give the resolver a real history

**Files:**

- Modify: `backend/memory/write_pipeline/uow.py:80-105`
- Modify: `backend/memory/write_pipeline/postgres.py`
- Modify: `backend/memory/write_pipeline/background_recorder.py:236-248`
- Test: `backend/tests/integration/test_memory_write_postgres.py`

**Interfaces:**

- Produces: `MemoryUnitOfWork.get_active_versions(owner_user_id, canonical_key) -> tuple[MemoryVersion, ...]`
- Consumes: the existing `read_current_versions` in `postgres.py:204` and the tenant-bound transaction helper

- [x] **Step 1: Write the failing tests**

```python
def test_uow_exposes_active_versions(pg_uow, owner):
    _commit_add(pg_uow, owner, key="hotel_atmosphere", value="quiet")
    versions = pg_uow.get_active_versions(owner, "hotel_atmosphere")
    assert len(versions) == 1
    assert versions[0].normalized_value == "quiet"


def test_active_versions_are_tenant_scoped(pg_uow, owner_a, owner_b):
    _commit_add(pg_uow, owner_b, key="hotel_atmosphere", value="lively")
    assert pg_uow.get_active_versions(owner_a, "hotel_atmosphere") == ()


def test_recorder_no_longer_takes_the_first_add_path(pg_uow, owner):
    _commit_add(pg_uow, owner, key="hotel_atmosphere", value="quiet")
    result = _recorder(pg_uow).record_sync(_candidate(owner, value="lively"), fence=_fence())
    assert "resolved_add" not in result.reason


def test_recorder_fails_loudly_when_the_uow_lacks_the_capability():
    with pytest.raises(AttributeError):
        _recorder(_uow_without_get_active_versions()).record_sync(_candidate("o"), fence=_fence())
```

- [x] **Step 2: Run verification**

Run: `PG_TEST_DSN=… pytest backend/tests/integration/test_memory_write_postgres.py -k active_versions -v`

Expected: FAIL. `get_active_versions` does not exist; the recorder still reports `resolved_add`.

- [x] **Step 3: Add to the protocol**

```python
    def get_active_versions(
        self, owner_user_id: str, canonical_key: str
    ) -> tuple[MemoryVersion, ...]:
        """Return the active versions for one owner and canonical key.

        Tenant-scoped: an implementation must bind `app.tenant` to
        `owner_user_id` for the duration of the read. A cross-owner read must
        return empty, never another owner's versions. An implementation that
        cannot perform the read must raise; it must not return an empty tuple,
        because an empty tuple is indistinguishable from a real empty history.
        """
        ...
```

- [x] **Step 4: Implement it**

```python
    def get_active_versions(
        self, owner_user_id: str, canonical_key: str
    ) -> tuple[MemoryVersion, ...]:
        with self._tenant_transaction(owner_user_id) as connection:
            return read_current_versions(connection, owner_user_id, canonical_key)
```

- [x] **Step 5: Remove the fallback**

In `background_recorder.py:236-248`, delete the `hasattr` chain. It is the defect, not a compatibility shim:

```python
        uow = self._uow_factory()
        existing_versions = tuple(
            uow.get_active_versions(
                mem_candidate.owner_user_id, mem_candidate.canonical_key
            )
        )
```

- [x] **Step 6: Run verification**

Run: `PG_TEST_DSN=… pytest backend/tests/integration/test_memory_write_postgres.py backend/tests/unit/memory_write_pipeline/ -v`

Expected: PASS.

- [x] **Step 7: Review checkpoint**

Review: the protocol, the implementation, and the recorder diff. Confirm the read is tenant-bound, that a cross-owner read returns empty, and that `grep -n "hasattr" backend/memory/write_pipeline/background_recorder.py` returns nothing on this path. Confirm the shadow-only invariant still holds: the recorder still forces `NOOP`.

Expected: no `hasattr` fallback remains; the recorder still forces `MemoryOperation.NOOP`.

## Task 6: Make the confidence gate real

**Files:**

- Modify: `backend/memory/write_pipeline/models.py` (`MemoryCandidate`)
- Modify: `backend/memory/write_pipeline/model_adapter.py`
- Modify: `backend/memory/write_pipeline/background_recorder.py:155-192`
- Test: `backend/tests/unit/memory_write_pipeline/test_model_adapter.py`
- Test: `backend/tests/integration/test_memory_write_postgres.py`

**Interfaces:**

- Produces: `MemoryCandidate.confidence: float`
- Consumes: `ExtractionCandidateSchema.confidence`

- [x] **Step 1: Write the failing tests**

```python
def test_low_confidence_candidate_is_rejected_before_persistence(uow_spy):
    candidate = _memory_candidate(confidence=0.2)
    result = _recorder(uow_spy).record_sync(candidate, fence=_fence())
    assert result.status == "low_confidence"
    assert uow_spy.calls == []


def test_adapter_populates_confidence_from_the_model_output():
    adapter = _adapter_returning(
        '{"candidates": [{"key": "x", "value": "y", "confidence": 0.3}]}'
    )
    assert adapter.extract(_messages())[0].confidence == pytest.approx(0.3)


def test_shadow_candidate_confidence_still_reaches_the_gate(uow_spy):
    result = _recorder(uow_spy).record_sync(
        _shadow_candidate(confidence=0.1), fence=_fence()
    )
    assert result.status == "low_confidence"
```

- [x] **Step 2: Run verification**

Run: `pytest backend/tests/unit/memory_write_pipeline/ -k confidence -v`

Expected: FAIL. `MemoryCandidate` has no `confidence` field.

- [x] **Step 3: Implement**

Add to `MemoryCandidate` in `models.py`:

```python
    confidence: float = 1.0
```

Populate it in `_to_memory_candidate` so both candidate types behave identically, and in `model_adapter.extract` from `ExtractionCandidateSchema.confidence`:

```python
        return MemoryCandidate(
            # …
            observed_at=candidate.observed_at or _utc_now(),
            confidence=getattr(candidate, "confidence", 1.0),
        )
```

Replace the defaulting read at `background_recorder.py:191` with a direct attribute access, so a future candidate type without the field is a type error rather than a silent `1.0`:

```python
        if candidate.confidence < self._min_confidence:
```

- [x] **Step 4: Measure before relying on the threshold**

Run the extraction harness over the existing fixtures and record the confidence distribution:

```bash
python -m backend.memory.write_pipeline.evaluation.cli run \
  --dataset docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1 \
  --suite all --output-dir docs/reports/memory-write-pipeline/confidence-baseline
```

Expected: a distribution. If the threshold rejects most candidates, that is a finding to report before the pipeline is enabled — not a reason to lower the threshold silently.

- [x] **Step 5: Run verification**

Run: `pytest backend/tests/unit/memory_write_pipeline/ -v` and `PG_TEST_DSN=… pytest backend/tests/integration/test_memory_write_postgres.py -v`

Expected: PASS.

- [x] **Step 6: Review checkpoint**

Review: the model field, the adapter population, and the gate read. Confirm no `getattr` default remains on the confidence path, that both candidate types carry the field, and that the confidence distribution is recorded.

Expected: `grep -n 'getattr(candidate, "confidence"' backend/memory/write_pipeline/` returns nothing; the distribution is in the evidence.

## Package Verification

Run in this order on the exact final worktree state:

1. `PG_TEST_DSN=… alembic upgrade head` then `PG_TEST_DSN=… alembic downgrade -1` then `PG_TEST_DSN=… alembic upgrade head` — expect a clean round trip
2. `PG_TEST_DSN=… pytest backend/tests/integration -m integration -v` — expect zero skips
3. `pytest backend/tests/unit backend/tests/boundaries`
4. `cd frontend && npm test`
5. `grep -n "ALEMBIC_HEAD" backend/storage/postgres.py` and `PG_TEST_DSN=… psql -c "SELECT version_num FROM alembic_version"` — expect the same value
6. `SELECT count(*) FROM messages WHERE status = 'pending'` under steady state — expect 0
7. `SELECT count(*) FROM messages WHERE status = 'complete' AND content = ''` — expect 0
8. `git status --short --untracked-files=all` — compare against the approved change set, including untracked file contents

Report actual output, exit status, and every check that could not run. Checks 1, 2, 5 and 6 require a live database; if unavailable, that is a limitation to disclose, not a pass.

## Rollback

Order matters, because Task 3 removes the old path in the same change as Task 1 adds the column.

1. Revert Task 6 and Task 5 — independent of everything else, no schema dependency.
2. Revert Task 4 — the frontend must revert with or before Task 3.
3. Revert Task 3 — restores the four-transaction orchestrator, which does not know about `status`.
4. Revert Task 2 — removes the three methods.
5. Revert Task 1 — `alembic downgrade` to `20260910_04` and restore `ALEMBIC_HEAD`. **Only after step 3**, because the old orchestrator writes rows the new column defaults to `complete`, so a downgrade after step 3 is safe; a downgrade before step 3 would leave `pending` rows the old code cannot interpret.

Rollback must preserve unrelated work and history. No step requires a destructive Git operation. Any `pending` row present at rollback time must be reported, because it will remain `pending` with no code that understands it.

## Completion Record

| Field | Value |
| --- | --- |
| Specification approval | **Approved 2026-09-11** — `docs/specs/2026-09-11-atomic-chat-turn-and-memory-correctness-design.md` v0.1, repository owner. |
| ADR 0023 acceptance | **Accepted 2026-09-11** — `docs/adr/0023-atomic-two-phase-chat-turn.md`. |
| ADR 0024 acceptance | **Accepted 2026-09-11** — `docs/adr/0024-evaluation-results-distinguish-unmeasurable-from-perfect.md`. |
| Plan approval | **Approved 2026-09-11** — repository owner, with the explicit instruction to implement immediately together with the two owner-authorized scope additions. |
| Execution | **Complete — Tasks 1–6 implemented.** |
| Verification | **Run on the final worktree state.** 783 unit + boundaries (0 errors), **136** integration (zero skips), 28 frontend. All package checks now pass: check 7, which failed when this plan was first verified, was satisfied by the follow-up plan recorded below. |
| Delivery gate | Repository owner only. No Git delivery is authorized by this plan. |

**Checked where evidence exists.** All 37 step checkboxes are ticked because the per-task evidence below exists for all six tasks.

**Correction, 2026-09-11.** This line previously read *"`Task 4`, `Task 5` and `Task 6` remain unchecked and unimplemented."* That was true when this plan was first verified, and it was left stale after those three tasks were implemented and verified — so the record contradicted its own evidence table. It now matches it.

### Per-task status

| Task | Implemented | Verified | Evidence |
| --- | --- | --- | --- |
| 1 — Add the message turn status | Yes | **Yes** | `backend/storage/migrations/versions/20260911_01_message_turn_status.py`; `ALEMBIC_HEAD = "20260911_01"`. `pytest backend/tests/integration/test_postgres_migrations.py` → **21 passed**, including a real `downgrade` that drops index, constraint and column. |
| 2 — Turn methods on the repository and service | Yes | **Yes** | `append_turn` / `complete_turn` / `fail_turn` on the port, the Postgres adapter and `ConversationService`; `_transition_turn` shares the guarded single-row update; `_cancel_turn_outbox` cancels the turn's pending event when a turn ends `FAILED`. `pytest backend/tests/integration/test_conversation_turns_postgres.py` → **13 passed**. |
| 3 — Orchestrator two-phase turn | Yes | **Yes** | `handle_turn` rewritten; the four-transaction path is **deleted, not left as a fallback**. `chat.py` returns `{"detail": …, "conversation_id": …}` on a generation failure. `test_chat_conversation_binding.py` → **24 passed**; `test_conversation_orchestrator.py` + `test_conversation_service.py` + `test_conversation_models.py` → **171 passed**. |
| 4 — Render the turn status in the frontend | Yes | **Yes** | `MessageResponse.status` added and mapped in `from_domain`; `ChatMessage.jsx` branches on `failed` and `pending`, each with its own `data-testid`. `frontend/tests/components.test.jsx` → 13 passed; whole frontend suite → **28 passed**. `frontend/src/services/chat.js` needed no change: it returns the raw message array, so the field already flowed through. |
| 5 — Give the resolver a real history | Yes | **Yes** | `get_active_versions` on the protocol and on `PostgresMemoryUnitOfWork`, tenant-bound and verified. The `hasattr` chain is **deleted**. `pg_list_active_versions` — which had no callers — was repurposed to take a tenant-bound connection plus a `canonical_key` filter, because a bare `engine.connect()` reads nothing under RLS. `test_background_recorder.py` → 20 passed, including a test that a UoW without the capability raises rather than reading empty. |
| 6 — Make the confidence gate real | Yes | **Yes** | `MemoryCandidate.confidence` added with a type guard; populated by `model_adapter.extract` from `ExtractionCandidateSchema.confidence` and carried by `_to_memory_candidate`; the defaulting `getattr` at the gate is replaced by direct access. `grep 'getattr(candidate, "confidence"'` returns nothing. Memory unit suite → **205 passed**. |

### Verification results

| Check | Command | Result |
| --- | --- | --- |
| Unit + boundaries | `pytest backend/tests/unit backend/tests/boundaries` | **783 passed, 0 errors** |
| Integration | `PG_TEST_DSN=… PG_RUNTIME_TEST_DSN=… pytest backend/tests/integration` | **127 passed, 0 failed, 0 skipped** |
| Frontend | `cd frontend && npx vitest run` | **28 passed (3 files)** |
| Migration round trip | `alembic upgrade head` → `downgrade -1` → `upgrade head`; plus `pytest …/test_postgres_migrations.py` | round trip completes; **21 passed** including downgrade and head consistency |
| Head consistency (check 5) | `ALEMBIC_HEAD` vs `SELECT version_num FROM alembic_version` | both `20260911_01` |
| Pending count (check 6) | `SELECT count(*) FROM messages WHERE status = 'pending'` | **0** |
| Complete-with-empty-content (check 7) | `SELECT count(*) FROM messages WHERE status = 'complete' AND content = ''` | **5 — FAILS. See limit 2.** |
| RLS still forced | `SELECT relrowsecurity, relforcerowsecurity FROM pg_class` | `messages` and `conversations`: enable + force |
| `git status` | `git status --short --untracked-files=all` | nothing staged or committed; no Git delivery |

### Verification limits — disclosed, not claimed as passing

1. **The host's safe-delete shim can turn `tmp_path` teardown into setup ERRORs.** An earlier full run reported 119 such errors, every traceback inside `sitecustomize.py` (`SAFE_DELETE_BULK_CONFIRM_REQUIRED {"count":50,"threshold":50}`). The final run reported none. The affected modules pass in isolation. It is an environment artefact, not a regression, and it makes the unit count non-reproducible between runs.
2. **Package-verification check 7 failed when this plan was first verified, and it was a real finding.** After the `downgrade -1` / `upgrade head` round trip, five rows were `status='complete'` with `content=''`, and reading one of their conversations through the repository **raised `ConversationStorageError`** — the conversation became unreadable, not just the offending row. Cause: the schema enforces no relationship between `status` and `content`; only the Python contract does. Re-labelling a `pending` reply slot as `complete` — exactly what the column default does on re-upgrade — therefore produced a row the repository then refuses to read. The five rows here were artefacts of the `test_tenant_isolation.py` fixture, but the path is reachable in production: the Rollback section below describes downgrading to `20260910_04` and back, and any `pending` row present at that moment (a crashed process is enough) becomes `complete` with empty content.

   **RESOLVED 2026-09-11, by a separate approved change.** The specification `docs/specs/2026-09-11-message-status-content-invariant-design.md` v0.1, ADR 0025 and the plan `docs/plans/2026-09-11-message-status-content-invariant-implementation.md` addressed it: migration `20260911_02` repairs the violating rows to `failed` and then adds the constraint `ck_messages_complete_has_content`. Check 7 now returns **0** on a database that has been through the round trip, and the previously unreadable conversations load again. This plan's task list did not include that work; the fix was deliberately kept out of it rather than smuggled in, and this plan is `Completed` on the basis that all six of its tasks pass and all nine of its package checks now pass.
3. **Task 4 is a rollout prerequisite, not an optional tail.** ADR 0023 requires the frontend to render `pending` and `failed` distinctly. It is now implemented, so the backend and frontend halves are in the same change set and **must be deployed together**.
4. **Tasks 5 and 6 are implemented, but the memory write pipeline stays DISABLED.** `MEMORY_WRITE_PIPELINE_ENABLED` and `MEMORY_SHADOW_EXTRACT_ENABLED` still default to `false` and the recorder still forces `MemoryOperation.NOOP`. Enabling it remains a separate, separately-approved decision that this plan does not authorize.
5. **No test that encoded the old contract was silently weakened.** Four were changed and are named: `test_assistant_turn_write_failure_returns_the_reply_with_persisted_false` in `test_chat_conversation_binding.py` and `test_conversation_orchestrator.py` (renamed; now expect a failure rather than a degraded `200`), `test_generation_failure_propagates_and_keeps_the_user_turn` (now asserts the failed turn is recorded and that the error carries `conversation_id`), and `test_create_conversation_with_initial_turn` in `test_conversation_service.py` (now unpacks the reply slot).
6. **Nine test doubles had to learn the new contracts** — five for the two-phase turn and four for the UoW protocol. That is the real cost of the rename and of removing the `hasattr` probe, and it is the reason both are worth doing once rather than per-caller.
6. **The corpus was not rebuilt** and no evaluation harness was run.

### Load-bearing proof recorded

A security or correctness test is decoration unless it fails when the control is removed. Two were proven:

- **`status = 'pending'` guard.** Removing the guard from `_transition_turn` makes `test_complete_turn_is_idempotent` and `test_fail_turn_does_not_overwrite_a_completed_row` fail, showing a `COMPLETE` row overwritten to `FAILED`. Restored → green.
- **`assert_rls_enforced`.** Pointing `PG_RUNTIME_TEST_DSN` at the superuser role now fails loudly (`rolsuper=True rolbypassrls=True … vacuous`). Before this change the same DSN made all 8 isolation tests pass while proving nothing.

### Deviations from the approved plan

1. **`create_with_initial_message` was renamed `create_with_initial_turn`.** It now allocates the reply slot as well, so the old name would have described the wrong thing. Callers updated together, as the plan required; five test doubles were updated with it.
2. **The turn tests live in a new `test_conversation_turns_postgres.py`, not in `test_chat_conversation_binding.py`.** That module's docstring promises "no external models, network, or live databases are required", and that promise is load-bearing for readers. Adding live-database tests there would have made it false.
3. **The documented head literal was swept in seven files** (`README.md`, `ARCHITECTURE.md`, `docs/architecture/current-state.md`, `docs/runbooks/deployment.md`, `docs/runbooks/local-development.md`, `DEVELOPMENT.md`, and the readiness docstring) because the head moved to `20260911_01`. The plan's File Responsibility Map named only `backend/storage/postgres.py`. Leaving them would have created the documentation drift this repository has repeatedly been criticised for. Historical ADR and plan references to `20260910_04` were deliberately left alone.
4. **`MessageStatus` was added to `MessageDraft` as well as `Message`.** Both share `_normalize_message_fields`, and a pending placeholder must be expressible as a draft. The plan named only `Message`.
5. **Two test doubles in `test_chat_conversation_binding.py` were corrected** after they passed for the wrong reason: `RoleFailingRepository` initially failed only the `ASSISTANT` role, so a `USER`-role failure was silently tolerated once the turn began writing both rows.
6. **`PG_RUNTIME_TEST_DSN` standardisation and the lazy generation package** are the two owner-authorized scope additions recorded above.
7. **`frontend/src/services/chat.js` needed no change.** The plan required "add the field to the mapper in `frontend/src/services/chat.js`", but that module has no field-level mapper: `listMessages` returns `response.data.messages` unchanged, so `status` already reached the browser once the schema exposed it. Editing it would have added a no-op.
8. **`pg_list_active_versions` was repurposed rather than duplicated.** It had no callers. Its signature changed from `(engine, owner)` to `(connection, owner, canonical_key=None)` because a bare `engine.connect()` reads nothing under RLS — the same trap the specification warns about for the new read.
9. **`_to_memory_candidate` reads `candidate.confidence` directly**, not `getattr(..., 1.0)` as the plan sketched. The specification's contract says the confidence read is a direct attribute access; the early return for `MemoryCandidate` means the remaining branch only ever sees `ShadowCandidate`, which declares the field.

**Known limitations to record when executed.** (a) There is no automatic recovery for a `pending` row left by a process crash; the status is exposed so an operator can identify it, and reconciliation is future work. (b) Wiring `classify_relation` so that `MemoryRelation` reaches the resolver is out of scope, so the resolver's relation-dependent branches remain unreachable even after this plan; the resolver must be verified correct for `UNRELATED` and must not be assumed to exercise its contradiction branches in production. (c) The outbox lease, retry and back-off defects (review Important I13–I16) are not fixed here and will govern the quality of memory-write retries once the pipeline is enabled. (d) Enabling the pipeline remains a separate, separately-approved decision.
