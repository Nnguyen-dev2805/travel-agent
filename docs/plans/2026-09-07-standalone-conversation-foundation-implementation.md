# Standalone Conversation Foundation Implementation Plan

> **For agentic workers:** Execute only after this exact child plan is approved.
> Use test-driven development and stop at every review checkpoint.

**Goal:** Preserve current memory behavior while making authenticated standalone
conversations owned directly by users and creatable on the first chat turn.

**Architecture:** Freeze the current R5/R6 flow with characterization tests,
then add `owner_user_id` and optional `workspace_id` at the storage-neutral
conversation seam. PostgreSQL persistence belongs to the later persistence
child plan.

**Tech Stack:** Python, dataclasses, FastAPI domain contracts, pytest.

**Spec:** `docs/specs/2026-09-07-basic-semantic-memory-write-pipeline-design.md`
v0.1 Approved; ADR 0011 Accepted.

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-07 |
| Approved specification | Basic Semantic Memory Write Pipeline Design v0.1 |
| Scope | Master Tasks 1-2 only |
| Verification | Characterization plus conversation domain/service tests |

## Task Table

| Task | Output | Files | Verification |
| --- | --- | --- | --- |
| 1 | Current R5/R6 flow frozen as executable evidence | New characterization test; read existing memory/orchestrator modules | Focused legacy test suite passes unchanged |
| 2 | Direct-owner, optional-workspace conversation domain | Conversation models, repository interface, service, unit tests | Standalone and compatibility tests pass |

## Task 1: Characterize Current Memory and Chat Behavior

**Files:** Create `backend/tests/characterization/test_current_memory_write_flow.py`.

**Interfaces:** Consumes current R5/R6 behavior; produces compatibility tests
only.

- [ ] Write tests for accepted preference extraction, trace-excluded rejection,
  manual promotion, broad correction behavior, separate promotion writes,
  gate-off chat, and bound-turn persistence.
- [ ] Run `pytest -q backend/tests/characterization/test_current_memory_write_flow.py`.
  Expected: PASS without production changes.
- [ ] Run the current extraction, policy, promotion, and chat-memory integration
  test files. Expected: PASS.
- [ ] Review the test names as a source-to-candidate-to-record-to-context map.

## Task 2: Add Standalone Conversation Domain Ownership

**Files:** Modify `backend/conversations/models.py`,
`backend/conversations/repository.py`, and `backend/conversations/service.py`;
create `backend/tests/unit/test_standalone_conversation.py`; update
`backend/tests/unit/test_conversation_service.py`.

**Interfaces:**

```python
ConversationCreate(owner_user_id: str, workspace_id: str | None, title: str | None)
Conversation(conversation_id: str, owner_user_id: str,
             workspace_id: str | None, title: str | None, ...)
```

- [ ] Write failing tests for required owner, optional workspace, valid
  workspace compatibility, mismatch rejection, and owned list/get.
- [ ] Run `pytest -q backend/tests/unit/test_standalone_conversation.py`.
  Expected: FAIL on the absent contract.
- [ ] Implement only storage-neutral domain/interface/service behavior; create
  no hidden workspace and do not modify HTTP or adapters.
- [ ] Run standalone and existing conversation service tests. Expected: PASS.
- [ ] Review owner/scope invariants and confirm the later PostgreSQL child plan
  receives an exact contract.

## Child Verification

Run characterization, conversation model/service, and import-boundary tests.
Inspect `git status --short --untracked-files=all` and `git diff --check`.

## Rollback

Remove new storage-neutral ownership contracts and tests only if no later child
has consumed them. Preserve characterization tests as historical evidence.

## Approval Record

Version 0.1 was approved by the repository owner on 2026-09-07 for sequential
implementation by a different implementation agent. The current planning agent
is review-only: it may inspect code, compare the change set with this plan, and
assess verification evidence, but it is not authorized to implement runtime
changes or perform Git delivery.
