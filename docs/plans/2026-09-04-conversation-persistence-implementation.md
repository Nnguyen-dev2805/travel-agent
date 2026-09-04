# Conversation Persistence Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and preserve checkbox
> state as review evidence.

**Goal:** Conversations and messages persist durably under an existing trip
workspace, a chat turn can optionally bind to a conversation and report its
persistence outcome truthfully, and the workspace store becomes a shared
application store with per-module schema versions, with no change to the
unbound chat contract, the health route, any R3 workspace route, RAG behavior, or
the R2 evaluation harness.

**Architecture:** Backend-only. A shared schema registry owns per-module version
bookkeeping in one local SQLite database at `APP_DB_PATH`. A new
`backend/conversations/` module owns conversation and message contracts, a
repository interface, a SQLite adapter, and a service that verifies workspace
existence. A new `backend/orchestration/` module owns coordination between
conversation persistence and RAG generation for one chat turn. Dependencies run
one way: orchestration depends on conversations and RAG; conversations depend on
the workspace repository interface; RAG, evaluation, and workspaces depend on
none of the new modules.

**Tech Stack:** Python 3.11 baseline, FastAPI, Pydantic, standard-library
`sqlite3`, pytest, the existing settings pattern, the existing backend test
layout, Markdown documentation.

**Spec:** [Conversation Persistence Design](../specs/2026-09-04-conversation-persistence-design.md), version 0.1 (Approved)

| Field | Value |
| --- | --- |
| Status | Approved |
| Plan version | 0.1 |
| Date | 2026-09-04 |
| Approved specification | [Conversation Persistence Design](../specs/2026-09-04-conversation-persistence-design.md), version 0.1 (Approved 2026-09-04) |
| Governing ADRs | [ADR 0004](../adr/0004-shared-local-application-store-and-per-module-schema-registry.md) (Accepted), [ADR 0005](../adr/0005-conversation-orchestration-seam-and-optional-chat-binding.md) (Accepted) |
| Plan approval | Repository owner approved implementation plan version 0.1 in conversation on 2026-09-04, conditional on synchronizing the `R3` and `R4` roadmap status and adding the symlink guard; both conditions were satisfied before this status changed |
| Execution base | `feature/agent-memory` at `2f632e2`, baseline `447 passed` |
| Execution owner | Coordinating agent |
| Decision owner | Repository owner |
| Scope | Runtime milestone R4 - shared schema registry, conversation module, orchestration seam, optional chat binding, five conversation routes, tests, and documentation |
| Verification | `./.venv/bin/python -m pytest backend/tests`, `./.venv/bin/python -m compileall backend`, boundary and containment `grep` checks, storage rollback evidence, `git diff --check`, `git status --short --untracked-files=all` |

## Global Constraints

1. No source implementation before the repository owner approves this plan.
2. Execute R4 source work only on a workspace state containing the merged R3
   change set at `2f632e2` or a later explicitly approved integration base.
   Confirm the baseline test count before editing; if it differs from `447
   passed`, stop and report rather than adjusting the plan silently.
3. Preserve `GET /health` behavior exactly.
4. Preserve the unbound `POST /api/v1/chat` contract exactly. A request carrying
   only `message` must return a response whose key set is exactly `reply`,
   `model`, `citations`, with no `conversation` key present.
5. `conversation_id` on the chat request is optional and additive. Never make it
   required, and never change the name, type, or value of `reply`, `model`, or
   `citations`.
6. Preserve every R3 workspace route path, request shape, response shape,
   ordering, and status code. The `TripWorkspace` contract and the
   `WorkspaceRepository` interface do not change; only the workspace adapter's
   version bookkeeping changes.
7. No authentication, authorization, sessions, collaboration, memory,
   conversation summarization, planner state, itinerary versions, deletion
   semantics, production database infrastructure, ORM, or migration framework.
8. `owner_user_id` remains a local development scope label owned by the workspace
   record. Conversations carry no owner field. Never describe any part of R4 as
   tenant isolation, authentication, authorization, or a verified user.
9. No frontend work. `frontend/` is not modified. R4 delivers the capability to
   persist a turn without persisting real browser traffic, and documentation must
   say so plainly.
10. Route handlers and orchestration code carry no SQL, no table DDL, no database
    path creation, and no direct SQLite connection management.
11. `backend/rag`, including every generation, retrieval, and evaluation module
    and their tests, must not import `backend.conversations`,
    `backend.orchestration`, or the conversation API modules.
    `backend/workspaces` must not import `backend.conversations`.
12. No conversation or message record is written to Chroma or any vector
    database. No R1/R2 evaluation artifact is modified.
13. Tests use temporary database paths and in-memory fakes. No test may read or
    write the default developer database, require a model provider, an embedding
    model, Chroma data, Docker, or network access.
14. Never log message `content`, conversation `title`, or any substring of
    either. Logs and HTTP error details carry identifiers, sequence numbers,
    roles, counts, route or action names, and failure classes only. Do not
    extend the existing chat message-prefix log, and do not remove it either:
    removing it is out of R4 scope and is recorded as a known gap.
15. Do not create, delete, or clean persistent local database files outside
    explicit test temporary directories. The R3 database at the old default path
    is left untouched; deleting it requires the repository owner to name the
    exact path and approve.
16. Symlinks follow the symlink guard in
    [Execution environment](#execution-environment): only `data/processed` may be
    linked, never `git add` a symlink or force-add any path under `data/`, verify
    `git status --short --untracked-files=all` right after creating it and again
    before handoff, and never replace a symlink with a real directory.
17. Preserve unrelated user work. No stage, commit, push, PR, merge, tag,
    publish, branch delete, or history rewrite without an explicit repository
    owner request for that exact Git action.

## Verification Toolchain

The repository pins no linter and no type checker in `requirements.txt`, and CI
runs only `compileall` and `pytest`. Verification in this plan is therefore
pytest, `compileall`, static `grep` checks, and Git checks. Do not introduce a
new checker as part of R4; that is separate tooling work.

| Concern | Command | Environment note |
| --- | --- | --- |
| Test runner | `./.venv/bin/python -m pytest` | The repository interpreter is Python 3.14.5 with pytest 9.1.1. Host `python3` reports `No module named pytest`, so always invoke the virtual environment interpreter |
| Static check | `./.venv/bin/python -m compileall` | Same interpreter |
| Static search | `grep -rn -E` and `grep -n -E` | `command -v rg` returns nothing on this machine; `/usr/bin/grep` is present |

If a required check cannot run under the command given, stop and report rather
than substituting weaker evidence.

### Execution environment

The repository owner selects the branch or linked worktree for R4 source work.
Both are viable, and the plan's commands are identical in either case except for
how the interpreter is reached.

If a linked worktree is used, two Git-ignored paths are absent there and must be
resolved without editing source or tests:

| Absent in a linked worktree | Why it matters | Resolution |
| --- | --- | --- |
| `.venv` | `./.venv/bin/python` does not resolve from the worktree | Invoke the primary tree interpreter by absolute path; `backend/` is still collected from the worktree |
| `data/processed/` | `backend/tests/unit/test_chunker.py` reads `data/processed/vietnam_travel_raw.jsonl` and fails without it | Symlink only `data/processed`. Do not link `data/chromadb` or `data/evaluation`, so no test can write into R1/R2 baseline artifacts |

#### Symlink guard

During R3 a `docs` symlink was replaced by a real directory and sixteen local
Markdown files were lost, including the approved version of that plan. Six of
those files were never recovered. Any symlink created for R4 therefore carries
explicit rules rather than being treated as a harmless convenience.

1. **Only `data/processed` may be symlinked.** Do not symlink `docs`,
   `.venv`, `backend`, `frontend`, `data` itself, `data/chromadb`, or
   `data/evaluation`. A symlink at `data` would shadow the ignored directory and
   expose the R1/R2 baseline artifacts to test writes.
2. **Never `git add` a symlink, and never use `git add -f` on any path under
   `data/`.** `.gitignore` line 29 ignores `data`, so `git status` will not offer
   the symlink and no accidental commit is possible unless the ignore rule is
   deliberately overridden. Overriding it is forbidden in R4.
3. **Verify invisibility immediately after creating the symlink.** Run
   `git status --short --untracked-files=all` in the worktree and confirm the
   symlink does not appear. If it appears, stop: the ignore rule is not covering
   it, and creating it was unsafe.
4. **Verify again before handoff.** Run
   `git status --short --untracked-files=all` and confirm the change set contains
   only R4 source, test, and documentation paths, with no symlink and no database
   file. Read untracked file contents directly, because `git diff` does not show
   them.
5. **Never replace a symlink with a real directory, and never delete the target
   through the link.** If a symlink is in the way, report it instead of resolving
   it, because that exact operation is what caused the R3 loss.
6. **Removing the symlink after R4 is a repository-owner decision.** Do not
   delete it as cleanup; `data/processed` in the primary tree is real data
   reached through it.

The `docs/` tree is no longer Git-ignored: commit `359a2ab` tracked it and the
current `.gitignore` has no `docs/` entry. R4 documentation edits are therefore
ordinary tracked deliverables and must never be reached through a symlink.

Record the baseline test count in the chosen environment before any R4 edit. The
expected baseline is `447 passed` at `2f632e2`.

## Sentinel Value Decision

The approved specification requires a sentinel in `PRAGMA user_version` and
leaves the concrete value to this plan. This plan fixes it at:

```python
SENTINEL_USER_VERSION = 1000
```

Rationale. It must differ from `0`, which means an uninitialized SQLite file, and
from `1`, which is the value a pre-R4 workspace build expects. A value far from
any plausible sequential schema number makes accidental collision with a future
per-file version scheme unlikely, and makes the value self-evidently a marker
rather than a count when a developer inspects the database by hand.

Registry initialization reads `PRAGMA user_version` and behaves as follows:

| Observed value | Meaning | Behavior |
| --- | --- | --- |
| `0` | Fresh database file | Create `schema_versions`, set the pragma to `1000` |
| `1000` | Database managed by an R4 or later build | Proceed and read `schema_versions` |
| Anything else | Legacy or unknown ownership, including a value of `1` written by a pre-R4 workspace build | Fail closed with a controlled storage error; never migrate automatically |

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/storage/__init__.py` | Export the shared schema registry entry points | Registry module |
| `backend/storage/schema_registry.py` | Open the shared database, own the sentinel pragma, create and read `schema_versions`, register or verify one module version, and fail closed on unknown ownership or unsupported version | Approved spec, ADR 0004, `sqlite3`, `pathlib` |
| `backend/conversations/__init__.py` | Export stable conversation contracts and service and repository entry points | Conversation modules |
| `backend/conversations/models.py` | `Conversation`, `Message`, `MessageDraft`, role, source, trace-visibility and retention vocabularies, validation helpers, identity generation, UTC time | Approved spec, ADR 0005 |
| `backend/conversations/repository.py` | Conversation storage interface and repository error types | `backend/conversations/models.py`, ADR 0004 |
| `backend/conversations/sqlite_repository.py` | Conversation schema version 1 tables, sequence allocation inside one immediate transaction, parent `updated_at` bump, cursor reads, fail-closed row mapping | Conversation contracts, repository interface, shared schema registry, `sqlite3` |
| `backend/conversations/service.py` | Create, get, list, append, and history use cases; normalization; workspace existence verification; identity and timestamps | Conversation contracts, conversation repository interface, workspace repository interface |
| `backend/orchestration/__init__.py` | Export the conversation orchestrator | Orchestration module |
| `backend/orchestration/conversation_orchestrator.py` | Coordinate one chat turn: verify the conversation, persist the user turn before generation, call RAG, persist the assistant turn, report the outcome | Conversation service, RAG service facade, ADR 0005 |
| `backend/app/schemas/conversations.py` | Public request and response JSON shapes for conversation and message routes | Pydantic, conversation contracts |
| `backend/app/api/conversations.py` | Five routes, dependency construction, the public role restriction, controlled HTTP errors, content-free logging | API schemas, conversation service, SQLite adapter |
| `backend/app/schemas/chat.py` | Add optional `conversation_id` to the request and the optional `conversation` object to the response | Existing chat schemas, approved contract |
| `backend/app/api/chat.py` | Delegate one turn to the orchestrator and map its outcome to HTTP | Chat schemas, conversation orchestrator |
| `backend/app/main.py` | Mount the conversation router under `settings.API_V1_STR` beside chat and workspaces | Existing route registration pattern |
| `backend/app/config.py` | Add `APP_DB_PATH` with a local default and accept `WORKSPACE_DB_PATH` as a deprecated alias | ADR 0004, existing settings pattern |
| `backend/workspaces/sqlite_repository.py` | Move version bookkeeping from `PRAGMA user_version` to the shared registry | Shared schema registry, ADR 0004 |
| `backend/app/api/workspaces.py` | Resolve the renamed setting at the existing single construction site | `backend/app/config.py` |
| `backend/tests/unit/test_schema_registry.py` | Registry initialization, sentinel behavior, module version isolation, fail-closed cases, and storage rollback evidence | Shared schema registry |
| `backend/tests/unit/test_sqlite_workspace_repository.py` | Existing R3 coverage, with the three version-behavior tests rewritten to assert registry semantics and the sentinel | Workspace adapter, shared registry |
| `backend/tests/unit/test_conversation_models.py` | Contract and validation coverage | Conversation models |
| `backend/tests/unit/test_conversation_service.py` | Service normalization, workspace existence enforcement, identity retry, no-write-on-invalid coverage | Conversation service and fakes |
| `backend/tests/unit/test_sqlite_conversation_repository.py` | Schema, persistence, sequence allocation, ordering, cursor reads, transactional bump, fail-closed mapping | Conversation SQLite adapter |
| `backend/tests/unit/test_conversation_orchestrator.py` | Turn ordering, partial-failure reporting, and role authority with fakes | Orchestrator |
| `backend/tests/integration/test_conversation_api.py` | Five routes, error cases, role restriction, cursor and limit bounds | FastAPI app, dependency override |
| `backend/tests/integration/test_chat_conversation_binding.py` | Bound chat turn behavior with a fake RAG service and a temporary database | FastAPI app, orchestrator override |
| `backend/tests/integration/test_api.py` | Existing health and chat assertions, extended to assert the exact unbound chat response key set | Existing API tests |
| `DEVELOPMENT.md` | Conversation routes, optional chat field, `APP_DB_PATH` and its deprecated alias, no-auth and non-production limits, deferred frontend | Implemented route and config behavior |
| `ARCHITECTURE.md` | Gateway notes for the conversation and orchestration runtime components and the shared store | Accepted ADRs and implemented modules |
| `docs/architecture/current-state.md` | Current-state backend map after R4 | Implemented modules and routes |
| `docs/architecture/data-model.md` | Mark `Conversation` and `Message` implemented fields, keep `summary` and other records conceptual | Conversation contracts |
| `docs/roadmap/master-roadmap.md` | R4 status and evidence update only | Completed verification evidence |
| `docs/plans/README.md` | Plan index entry and status lifecycle updates | This plan |
| `docs/plans/2026-09-04-conversation-persistence-implementation.md` | Approved execution contract and completion record | Approved spec, ADR 0004, ADR 0005 |

## Task 1: Confirm Base State and Mark Execution Start

**Files:**

- Read: the approved spec, ADR 0004, ADR 0005, this plan, `docs/roadmap/master-roadmap.md`
- Modify after approval only: this plan, `docs/plans/README.md`, `docs/roadmap/master-roadmap.md`

**Interfaces:**

- Consumes: approved R4 spec version 0.1, accepted ADR 0004 and ADR 0005,
  repository owner plan approval, merged R3 base at `2f632e2`
- Produces: plan status transition to `In Progress` and a confirmed execution
  base with a recorded baseline test count

- [ ] **Step 1: Verify approval gates**

Confirm that the spec header states `Approved` at version 0.1, that both ADRs
state `Accepted`, and that this plan has been approved by the repository owner.
Confirm the R3 change set is present by checking that `backend/workspaces/`
exists as tracked source.

If any gate is missing, stop before editing and report which one.

- [ ] **Step 2: Record the baseline**

Run: `./.venv/bin/python -m pytest backend/tests -q`

Expected: `447 passed`. Record the exact number and duration. If the number
differs, stop and report rather than editing the plan to match.

- [ ] **Step 3: Mark execution start**

Move this plan and its `docs/plans/README.md` index row from `Approved` to
`In Progress`. Update only the `R4` row in `docs/roadmap/master-roadmap.md`,
changing its status from `Blocked by gate` to `In progress` and naming the spec
and both ADRs. Do not touch any other roadmap row.

- [ ] **Step 4: Run verification**

Run: `git status --short --untracked-files=all`

Expected: no unrelated changes overlap the R4 affected paths. If overlapping work
exists, inspect it and stop before editing.

If a linked worktree was created for R4 and `data/processed` was symlinked,
confirm here that the symlink does not appear in this output. If it appears, stop
and report: the ignore rule is not covering it and the symlink is unsafe to keep.

- [ ] **Step 5: Review checkpoint**

Review: plan status, plan index status, roadmap `R4` row, recorded baseline, Git
status, and symlink invisibility when a worktree is used.

Expected: approval gates are satisfied, the baseline is recorded, and no
unrelated work is at risk.

## Task 2: Add the Shared Schema Registry and Move Workspace Versioning Onto It

**Files:**

- Create: `backend/storage/__init__.py`, `backend/storage/schema_registry.py`, `backend/tests/unit/test_schema_registry.py`
- Modify: `backend/workspaces/sqlite_repository.py`, `backend/tests/unit/test_sqlite_workspace_repository.py`, `backend/app/config.py`, `backend/app/api/workspaces.py`
- Test: `backend/tests/unit/test_schema_registry.py`, `backend/tests/unit/test_sqlite_workspace_repository.py`

**Interfaces:**

- Consumes: approved spec, ADR 0004, the sentinel value fixed by this plan
- Produces:
  - `SENTINEL_USER_VERSION = 1000`
  - `SchemaRegistryError` raised for unknown ownership or unsupported version,
    carrying no filesystem path, SQL text, or user content
  - `open_application_database(db_path: Path) -> sqlite3.Connection` which
    creates the parent directory, opens the database, enforces the sentinel rule,
    and ensures `schema_versions` exists
  - `register_module_schema(connection, module: str, version: int, create: Callable[[sqlite3.Connection], None]) -> None`
    which creates a module's tables and records its version on first use,
    accepts a matching recorded version, and fails closed on a mismatch
  - `read_module_version(connection, module: str) -> int | None`
  - Settings field `APP_DB_PATH` defaulting to
    `data/app/travel_agent.sqlite3`, with `WORKSPACE_DB_PATH` honored as a
    deprecated alias when `APP_DB_PATH` is unset

- [ ] **Step 1: Write registry tests first**

In `backend/tests/unit/test_schema_registry.py`, using `tmp_path` databases only,
assert that:

1. opening a nonexistent path creates the parent directory, creates
   `schema_versions`, and sets `PRAGMA user_version` to `1000`;
2. reopening a database created by the registry succeeds and leaves the sentinel
   unchanged;
3. opening a database whose `PRAGMA user_version` is `1`, with no
   `schema_versions` table, fails closed with `SchemaRegistryError` and does not
   create any table or change the pragma;
4. opening a database whose pragma holds an arbitrary other nonzero value fails
   closed the same way;
5. registering a module on a fresh database runs its create callback exactly once
   and records the version;
6. registering the same module again with the same version does not re-run the
   create callback and does not change the recorded version;
7. registering a module whose recorded version is higher than the requested
   version fails closed with `SchemaRegistryError`;
8. two modules register independent versions, and reading one module's version
   never returns the other's;
9. `read_module_version` returns `None` for an unregistered module;
10. a registry error message contains no database path and no SQL text.

Storage rollback evidence lives here as well:

11. a database initialized by the registry is rejected by the pre-R4 workspace
    version rule. Assert this by reading `PRAGMA user_version` from an
    R4-initialized database and confirming it is neither `0` nor
    `SCHEMA_VERSION`, which are the only two values the pre-R4 branch at
    `backend/workspaces/sqlite_repository.py:170` accepts without raising. Name
    the test so its purpose as rollback evidence is explicit.

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_schema_registry.py`

Expected: tests fail because `backend.storage.schema_registry` does not exist.

- [ ] **Step 2: Implement the registry**

Implement `backend/storage/schema_registry.py` with the smallest code that passes.
Use parameterized SQL and context-managed connections. Keep the module free of
FastAPI, Pydantic, RAG, Chroma, model-provider, evaluation, workspace, and
conversation imports: it depends on the standard library only.

`schema_versions` is created as:

```sql
CREATE TABLE IF NOT EXISTS schema_versions (
    module  TEXT PRIMARY KEY,
    version INTEGER NOT NULL
)
```

- [ ] **Step 3: Rewrite the three workspace version tests**

In `backend/tests/unit/test_sqlite_workspace_repository.py`, rewrite
`test_initialization_records_schema_version`,
`test_incompatible_schema_version_fails_closed`, and
`test_incompatible_schema_version_is_not_silently_migrated` so they assert
registry semantics rather than `PRAGMA user_version` semantics: the workspace
module records `('workspaces', 1)` in `schema_versions`, the sentinel is present,
a recorded workspace version higher than supported fails closed, and no
automatic migration occurs. Preserve each test's intent; do not weaken an
assertion to make it pass.

Leave every other test in the file unchanged.

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_workspace_repository.py`

Expected: the three rewritten tests fail because the adapter still uses the
pragma; the remaining tests still pass.

- [ ] **Step 4: Move the workspace adapter onto the registry**

Change `_initialize_schema` in `backend/workspaces/sqlite_repository.py` to open
the database through the registry and register `('workspaces', 1)` with a create
callback holding the existing `CREATE TABLE` and `CREATE INDEX` statements. Keep
`WorkspaceStorageError` as the error type the adapter raises outward, translating
`SchemaRegistryError` into it so the workspace repository's public error contract
does not change. Do not change the workspace table definition, the queries, the
ordering, or the `TripWorkspace` mapping.

- [ ] **Step 5: Add the setting and the deprecated alias**

In `backend/app/config.py`, add `APP_DB_PATH` defaulting to
`ROOT_DIR / "data" / "app" / "travel_agent.sqlite3"`. When the `APP_DB_PATH`
environment variable is unset and `WORKSPACE_DB_PATH` is set, use the alias value
and log exactly one deprecation warning naming the variable without its value.
Update the single construction site in `backend/app/api/workspaces.py` to resolve
`settings.APP_DB_PATH`. Do not change RAG or model-provider settings.

- [ ] **Step 6: Run verification**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_schema_registry.py backend/tests/unit/test_sqlite_workspace_repository.py backend/tests/integration/test_workspace_api.py`

Run: `./.venv/bin/python -m compileall backend/storage backend/workspaces backend/app/config.py backend/app/api/workspaces.py`

Expected: all pass, including the untouched R3 workspace coverage and the R3
route integration tests.

- [ ] **Step 7: Review checkpoint**

Review: registry interface, sentinel handling, the three rewritten tests, the
workspace adapter diff, the error translation boundary, and the alias behavior.

Expected: the workspace public contract is unchanged, R3 coverage is intact in
intent, and storage rollback evidence exists as a named test.

## Task 3: Add Conversation Contracts Test-first

**Files:**

- Create: `backend/conversations/__init__.py`, `backend/conversations/models.py`, `backend/conversations/repository.py`, `backend/tests/unit/test_conversation_models.py`
- Test: `backend/tests/unit/test_conversation_models.py`

**Interfaces:**

- Consumes: approved spec contract tables, ADR 0005
- Produces:
  - `CONVERSATION_ID_PREFIX = "cv_"`, `MESSAGE_ID_PREFIX = "ms_"`,
    `TITLE_MAX_LENGTH = 120`
  - `MessageRole` enum with `USER = "user"`, `ASSISTANT = "assistant"`,
    `TOOL = "tool"`, `SYSTEM_EVENT = "system_event"`
  - `PUBLIC_WRITABLE_ROLES` containing `MessageRole.USER` and
    `MessageRole.SYSTEM_EVENT` only
  - `MessageSource` enum with `UI = "ui"`, `TOOL = "tool"`, `MODEL = "model"`,
    `SYSTEM = "system"`, `IMPORT = "import"`
  - `TraceVisibility` enum with `EXCLUDED = "excluded"`, `INCLUDED = "included"`
  - `ConversationRetentionState` enum with `ACTIVE = "active"`,
    `SUMMARIZED = "summarized"`, `ARCHIVED = "archived"`,
    `DELETION_REQUESTED = "deletion_requested"`, `DELETED = "deleted"`
  - `DEFAULT_MESSAGE_SOURCE = MessageSource.UI`,
    `DEFAULT_TRACE_VISIBILITY = TraceVisibility.EXCLUDED`,
    `DEFAULT_RETENTION_STATE = ConversationRetentionState.ACTIVE`
  - `ConversationCreate(workspace_id: str, title: str | None)`
  - `Conversation(conversation_id, workspace_id, title, created_at, updated_at, retention_state)`
  - `MessageDraft(conversation_id, role, content, source, trace_visibility, created_at)`
  - `Message(message_id, conversation_id, sequence, role, content, source, trace_visibility, created_at)`
  - `MessageHistoryQuery(conversation_id: str, after_message_id: str | None, limit: int)`
  - `generate_conversation_id()`, `generate_message_id()`, `utc_now()`,
    `require_text()`
  - `ConversationValidationError(ValueError)`
  - `ConversationRepository` protocol with `create`, `get`, `list_by_workspace`,
    `append_message`, `list_messages`
  - `ConversationRepositoryError`, `ConversationAlreadyExistsError`,
    `MessageSequenceConflictError`, `ConversationStorageError`

- [ ] **Step 1: Write contract tests first**

In `backend/tests/unit/test_conversation_models.py`, assert that:

1. `conversation_id` and `message_id` are generated by the module, are strings
   prefixed `cv_` and `ms_`, and differ across calls;
2. `ConversationCreate` has no `conversation_id` field and `MessageDraft` has no
   `message_id` or `sequence` field, so identity and ordering cannot arrive from
   caller input;
3. `workspace_id` is stripped and required non-empty;
4. `title` is optional, stripped when present, at most 120 characters, and a
   blank title normalizes to absent rather than raising;
5. a title of exactly 120 characters is accepted and 121 raises
   `ConversationValidationError`;
6. `content` is required and raises when blank or whitespace-only;
7. `content` has no maximum length: a very long string is accepted, matching the
   deliberate departure recorded in the spec;
8. `role`, `source`, and `trace_visibility` accept their governed enum members and
   their governed string values, and raise on any other string;
9. `PUBLIC_WRITABLE_ROLES` contains exactly `user` and `system_event`;
10. defaults resolve to `source` `ui`, `trace_visibility` `excluded`, and
    conversation `retention_state` `active`;
11. `ConversationRetentionState` exposes all five governed states;
12. `created_at` and `updated_at` must be timezone-aware and are normalized to
    UTC, and a naive datetime raises;
13. `Message.sequence` must be an integer of at least `1`, and `0` or a negative
    value raises;
14. `MessageHistoryQuery` rejects a limit below `1` and above `200`, and defaults
    to `50` when the limit is absent;
15. every public name above is importable from `backend.conversations`.

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_conversation_models.py`

Expected: tests fail with `ModuleNotFoundError: No module named
'backend.conversations'`.

- [ ] **Step 2: Implement the contracts**

Implement `models.py` and `repository.py` with the smallest code that passes.
Follow the R3 module style: frozen dataclasses, `__post_init__` normalization, and
one shared normalization helper where two value objects validate the same field,
because `Conversation` and `Message` are also rehydrated from storage where a row
could violate the contract.

The modules must import the standard library only. Do not import FastAPI,
Pydantic, `sqlite3`, RAG, Chroma, model-provider, evaluation, or workspace
modules here.

- [ ] **Step 3: Run verification**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_conversation_models.py`

Run: `./.venv/bin/python -m compileall backend/conversations`

Expected: all contract tests pass and compilation succeeds.

- [ ] **Step 4: Review checkpoint**

Review: enum member values against the spec tables, default resolution, identity
prefixes, the `content` no-limit decision, the sequence floor, the history limit
bounds, and the module import list.

Expected: the contract layer is storage-agnostic, route-agnostic, and free of any
RAG or workspace dependency.

## Task 4: Add the Conversation Service and SQLite Repository Test-first

**Files:**

- Create: `backend/conversations/service.py`, `backend/conversations/sqlite_repository.py`, `backend/tests/unit/test_conversation_service.py`, `backend/tests/unit/test_sqlite_conversation_repository.py`
- Test: both new test files

**Interfaces:**

- Consumes: conversation contracts, conversation repository interface,
  `WorkspaceRepository` interface, shared schema registry
- Produces:
  - `ConversationService.create_conversation(input: ConversationCreate) -> Conversation`
  - `ConversationService.get_conversation(conversation_id: str) -> Conversation | None`
  - `ConversationService.list_conversations(workspace_id: str) -> tuple[Conversation, ...]`
  - `ConversationService.append_message(draft_input) -> Message`
  - `ConversationService.list_messages(query: MessageHistoryQuery) -> tuple[Message, ...]`
  - `SQLiteConversationRepository(db_path: Path)` registering
    `('conversations', 1)` through the shared registry
  - `WorkspaceNotFoundError` and `ConversationNotFoundError` raised by the service
    so the route layer can map them to `404` without inspecting storage details

- [ ] **Step 1: Write service tests first**

In `backend/tests/unit/test_conversation_service.py`, using a fake conversation
repository and a fake workspace repository, assert that:

1. creating a conversation under a missing workspace raises
   `WorkspaceNotFoundError` and performs no repository write;
2. creating a conversation under an existing workspace returns the record the
   repository created, with a `cv_` identity, `retention_state` `active`, and
   `created_at` equal to `updated_at`;
3. an invalid title performs no repository write;
4. listing conversations for a missing workspace raises `WorkspaceNotFoundError`
   before any list call;
5. listing returns repository order without re-sorting in the service;
6. `get_conversation` returns `None` for a missing conversation and does not
   raise;
7. appending to a missing conversation raises `ConversationNotFoundError` and
   performs no write;
8. appending with blank content performs no write;
9. appending sets `created_at` from the service and leaves `sequence` to the
   repository;
10. a duplicate generated `conversation_id` is retried exactly once with a fresh
    identity, and a second collision raises `ConversationStorageError` with no
    partial write;
11. the same retry rule holds for a duplicate generated `message_id`;
12. `list_messages` for a missing conversation raises `ConversationNotFoundError`;
13. `list_messages` passes the resolved cursor and limit through to the repository
    unchanged;
14. the service module imports no FastAPI, Pydantic, `sqlite3`, RAG, Chroma,
    model-provider, or evaluation module, asserted against the real import graph
    rather than by searching the source text.

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_conversation_service.py`

Expected: failure before implementation.

- [ ] **Step 2: Write SQLite repository tests first**

In `backend/tests/unit/test_sqlite_conversation_repository.py`, using `tmp_path`
databases only, assert that:

1. initialization registers `('conversations', 1)` and creates both tables and
   both indexes;
2. a workspace repository and a conversation repository can share one database
   file, and each reads only its own registry row;
3. `create` persists normalized fields and returns the stored record;
4. `get` returns the exact stored conversation, and `None` when absent;
5. `list_by_workspace` excludes other workspaces;
6. `list_by_workspace` orders by `updated_at` descending, then `created_at`
   descending, then `conversation_id` ascending;
7. `list_by_workspace` excludes `retention_state` `deleted` rows, verified by
   inserting one directly through the adapter's own write path;
8. `append_message` assigns `sequence` `1` for the first message in a
   conversation and increments for each subsequent message;
9. sequences increment independently per conversation, so two conversations both
   start at `1`;
10. `append_message` advances the parent conversation's `updated_at` in the same
    transaction;
11. a failed message insert leaves the parent conversation's `updated_at`
    unchanged, proving the write is transactional;
12. inserting a duplicate `(conversation_id, sequence)` pair raises
    `MessageSequenceConflictError` rather than silently overwriting a turn;
13. `list_messages` returns messages ordered by `sequence` ascending;
14. `list_messages` with a cursor returns only messages after that sequence;
15. `list_messages` respects the limit and reports whether more rows remain;
16. a cursor referring to a message in a different conversation is rejected;
17. a stored row whose `role`, `source`, `trace_visibility`, or `retention_state`
    is outside the governed vocabulary fails closed through a repository error
    rather than being coerced;
18. a stored timestamp that is not valid ISO or lacks timezone information fails
    closed;
19. records persist across repository instances pointed at the same file;
20. no test reads or writes the default developer database path.

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_conversation_repository.py`

Expected: failure before implementation.

- [ ] **Step 3: Implement the adapter and the service**

Implement `sqlite_repository.py` using the shared registry for schema ownership,
parameterized SQL, context-managed connections, and UTC ISO timestamp storage.
Create the tables and indexes exactly as the approved spec defines them.

Allocate `sequence` inside one `BEGIN IMMEDIATE` transaction that reads
`MAX(sequence)` for the conversation, inserts the message, and updates the parent
conversation's `updated_at`. Keep all three statements in that single
transaction. Translate `sqlite3.IntegrityError` on the unique constraint into
`MessageSequenceConflictError` and any other `sqlite3.Error` into
`ConversationStorageError`, with messages that carry no database path, no SQL
text, and no user content.

Implement `service.py` depending on the conversation contracts, the conversation
repository interface, and the workspace repository interface only. Resolve a
cursor `after_message_id` to its `sequence` before delegating, so the repository
receives `after_sequence` and never has to interpret an identifier.

- [ ] **Step 4: Run verification**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_conversation_service.py backend/tests/unit/test_sqlite_conversation_repository.py`

Run: `./.venv/bin/python -m compileall backend/conversations`

Expected: all pass.

- [ ] **Step 5: Review checkpoint**

Review: that SQL appears only inside the adapter, that sequence allocation and the
parent bump share one transaction, that the transactional-rollback test genuinely
exercises a failed insert, that timestamps are UTC, that error messages leak
nothing, and that the service enforces workspace and conversation existence.

Expected: the service and repository are reviewable independently of FastAPI, and
two modules coexist in one database file without version contention.

## Task 5: Add Conversation API Routes Test-first

**Files:**

- Create: `backend/app/schemas/conversations.py`, `backend/app/api/conversations.py`, `backend/tests/integration/test_conversation_api.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_conversation_api.py`

**Interfaces:**

- Consumes: conversation service, conversation contracts, approved route contract
- Produces:
  - `POST /api/v1/workspaces/{workspace_id}/conversations` returning `201`
  - `GET /api/v1/workspaces/{workspace_id}/conversations` returning
    `{"conversations": [...]}`, never a bare array
  - `GET /api/v1/conversations/{conversation_id}` returning the record or `404`
  - `POST /api/v1/conversations/{conversation_id}/messages` returning `201`
  - `GET /api/v1/conversations/{conversation_id}/messages` returning
    `{"messages": [...], "next_cursor": ...}`
  - `get_conversation_service()` as the single dependency construction site that
    resolves `settings.APP_DB_PATH`, overridable in tests

- [ ] **Step 1: Write route tests first**

In `backend/tests/integration/test_conversation_api.py`, using a dependency
override backed by a `tmp_path` database, assert that:

1. creating a conversation returns `201`, a `cv_` identity, normalized fields,
   `retention_state` `active`, and timestamps;
2. creating under a missing workspace returns `404`;
3. a title over 120 characters returns `422` and creates no record;
4. getting an existing conversation returns it, and a missing one returns `404`;
5. listing returns the `{"conversations": [...]}` object shape, excludes other
   workspaces, and applies the governed ordering;
6. listing for a workspace with no conversations returns an empty array;
7. listing under a missing workspace returns `404`;
8. appending a `user` message returns `201` with `sequence` `1`, then `2`;
9. appending a `system_event` message succeeds;
10. appending `role` `assistant` returns `422`, and the response body contains
    neither the submitted content nor the word `assistant` echoed from user input;
11. appending `role` `tool` returns `422`;
12. appending an unknown `role`, `source`, or `trace_visibility` returns `422`;
13. appending blank content returns `422` and creates no record;
14. appending to a missing conversation returns `404`;
15. reading history returns messages in `sequence` ascending order;
16. reading history with `after_message_id` returns only later messages and a
    `next_cursor` that is `null` when the page is the last one;
17. reading history with `limit` `0` or `201` returns `422`;
18. reading history with a cursor from another conversation returns `422`;
19. reading history for a conversation with no messages returns an empty array and
    a `null` cursor;
20. every `422` and `404` body is free of submitted message content and
    conversation titles.

Run: `./.venv/bin/python -m pytest backend/tests/integration/test_conversation_api.py`

Expected: failure to import `backend.app.api.conversations`.

- [ ] **Step 2: Implement schemas and routes**

Implement `backend/app/schemas/conversations.py` with request and response models
and `from_domain` mappers, following the R3 schema style. The list responses are
objects, not bare arrays.

Implement `backend/app/api/conversations.py` with the five routes. Enforce the
public role restriction in the schema or the route, before the service call, and
return `422` naming the restriction without echoing user input. Map
`WorkspaceNotFoundError` and `ConversationNotFoundError` to `404`,
`ConversationValidationError` to `422`, and `ConversationRepositoryError` to a
controlled `500`. Log route, action, identifiers, sequence, role, counts, and
failure classes only.

Mount the router in `backend/app/main.py` with `prefix=settings.API_V1_STR`,
matching the existing chat and workspace registration pattern. Keep the diff to
the import line and the `include_router` line.

- [ ] **Step 3: Run verification**

Run: `./.venv/bin/python -m pytest backend/tests/integration/test_conversation_api.py backend/tests/integration/test_workspace_api.py backend/tests/integration/test_api.py`

Run: `./.venv/bin/python -m compileall backend/app backend/conversations`

Expected: all pass, including the untouched R3 workspace and existing API tests.

- [ ] **Step 4: Review checkpoint**

Review: route paths against the approved contract, status codes, response field
names, the nested versus flat decision, the single dependency construction site,
the role restriction placement, and the absence of RAG, Chroma, or model-provider
construction in these routes.

Expected: the public API matches the spec exactly, and no error body leaks user
content.

## Task 6: Add the Orchestrator and Optional Chat Binding Test-first

**Files:**

- Create: `backend/orchestration/__init__.py`, `backend/orchestration/conversation_orchestrator.py`, `backend/tests/unit/test_conversation_orchestrator.py`, `backend/tests/integration/test_chat_conversation_binding.py`
- Modify: `backend/app/schemas/chat.py`, `backend/app/api/chat.py`, `backend/tests/integration/test_api.py`
- Test: `backend/tests/unit/test_conversation_orchestrator.py`, `backend/tests/integration/test_chat_conversation_binding.py`, `backend/tests/integration/test_api.py`

**Interfaces:**

- Consumes: conversation service, the `RAGService` facade, ADR 0005
- Produces:
  - `TurnOutcome(reply, model, citations, conversation)` where `conversation` is
    `None` for an unbound turn
  - `TurnPersistence(conversation_id, user_message_id, assistant_message_id, persisted)`
  - `ConversationOrchestrator.handle_turn(message: str, conversation_id: str | None) -> TurnOutcome`
  - `ChatRequest` gains `conversation_id: Optional[str] = None`
  - `ChatResponse` gains `conversation: Optional[ConversationTurnPayload] = None`
    excluded from serialization when unset, so an unbound response has no
    `conversation` key at all

- [ ] **Step 1: Write orchestrator tests first**

In `backend/tests/unit/test_conversation_orchestrator.py`, using a fake
conversation service and a fake RAG service that records call order, assert that:

1. an unbound turn calls the RAG service and performs no conversation service
   call at all, and returns `conversation` as `None`;
2. a bound turn with an unknown `conversation_id` raises
   `ConversationNotFoundError` and never calls the RAG service;
3. a bound turn persists the user message before calling the RAG service,
   asserted through recorded call order rather than through mock call counts;
4. the persisted user message carries `role` `user` and `source` `ui`;
5. a user-message write failure propagates a storage error and the RAG service is
   never called;
6. after generation the assistant message is persisted with `role` `assistant` and
   `source` `model`;
7. a successful bound turn returns `persisted` `True` with both message
   identifiers populated;
8. an assistant-message write failure returns the generated reply with
   `persisted` `False` and `assistant_message_id` `None`, and does not raise;
9. a generation failure propagates and leaves the already-persisted user message
   untouched in the fake service;
10. the orchestrator never writes `role` `tool`;
11. the orchestrator module imports no FastAPI, `sqlite3`, Chroma, or evaluation
    module, asserted against the real import graph.

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_conversation_orchestrator.py`

Expected: failure because `backend.orchestration` does not exist.

- [ ] **Step 2: Write chat binding integration tests first**

In `backend/tests/integration/test_chat_conversation_binding.py`, using a
dependency override that supplies a fake RAG service and a `tmp_path` database,
assert that:

1. a chat request with a valid `conversation_id` returns `200` with `reply`,
   `model`, `citations`, and a `conversation` object whose `persisted` is `true`;
2. after that request, reading message history returns exactly two messages, the
   first `role` `user` with `sequence` `1` and the second `role` `assistant` with
   `sequence` `2`;
3. the persisted user content equals the submitted message, verified through the
   history route rather than through a log;
4. a chat request with an unknown `conversation_id` returns `404` and the fake RAG
   service records no call;
5. a chat request whose user-message write fails returns `500` and the fake RAG
   service records no call;
6. a chat request whose assistant-message write fails returns `200` with the reply
   and `persisted` `false`, and history then contains only the user message;
7. two sequential bound chat requests produce sequences `1` through `4` in order;
8. an empty `message` with a valid `conversation_id` still returns `400` and
   persists nothing.

In `backend/tests/integration/test_api.py`, extend the existing chat coverage to
assert that an unbound chat response key set is exactly
`{"reply", "model", "citations"}`, with no `conversation` key present. Do not
modify the existing health assertions.

Run: `./.venv/bin/python -m pytest backend/tests/integration/test_chat_conversation_binding.py backend/tests/integration/test_api.py`

Expected: the new binding tests fail; the extended unbound assertion fails until
the response model excludes the unset field.

- [ ] **Step 3: Implement the orchestrator and the chat binding**

Implement `backend/orchestration/conversation_orchestrator.py` depending on the
conversation service and the `RAGService` facade only. Keep the turn ordering and
the partial-failure policy here, not in the route.

Extend `backend/app/schemas/chat.py` with the optional request field and the
optional response object. The response must omit the `conversation` key entirely
when it is unset rather than serializing `null`, so an existing client sees no
change.

Change `backend/app/api/chat.py` to delegate one turn to the orchestrator and map
its outcome to HTTP: `ConversationNotFoundError` to `404`, an empty message to the
existing `400`, a user-turn storage failure to `500`, and existing generation
failures to their current behavior. Keep the existing message-prefix log exactly
as it is; do not extend it and do not remove it.

- [ ] **Step 4: Run verification**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_conversation_orchestrator.py backend/tests/integration/test_chat_conversation_binding.py backend/tests/integration/test_api.py`

Run: `./.venv/bin/python -m compileall backend/orchestration backend/app`

Expected: all pass, and the unbound chat key-set assertion passes.

- [ ] **Step 5: Review checkpoint**

Review: the recorded call order proving the user turn precedes generation, the
partial-failure return shape, the absence of a `conversation` key on the unbound
path, the chat route's thinness, and the orchestrator's import list.

Expected: coordination lives in the orchestrator, the frozen chat fields are
untouched, and no persistence gap can be silent.

## Task 7: Add Documentation Updates

**Files:**

- Modify: `DEVELOPMENT.md`, `ARCHITECTURE.md`, `docs/architecture/current-state.md`, `docs/architecture/data-model.md`, `docs/roadmap/master-roadmap.md`, this plan, `docs/plans/README.md`

**Interfaces:**

- Consumes: implemented route, config, module, and contract behavior
- Produces: canonical documentation that matches implemented behavior and keeps
  maturity language honest

- [ ] **Step 1: Update the development guide**

In `DEVELOPMENT.md`, document `APP_DB_PATH` with its default path and the
`WORKSPACE_DB_PATH` deprecated alias in the environment table, the five
conversation routes with example local requests carrying no secrets, the optional
`conversation_id` chat field with both response shapes, the explicit
no-authentication limitation, the statement that local SQLite is not production
storage readiness, and the statement that the frontend is unchanged so browser
traffic is not persisted in R4.

- [ ] **Step 2: Update the architecture gateway and current state**

In `ARCHITECTURE.md`, add the conversation routes, the conversation module, the
orchestration module, and the shared local application store to the current
component table; add a local conversation flow section showing
route to orchestrator to service to repository to store; add the caller-to-
conversation-routes trust boundary noting the routes are unauthenticated; and add
the known gaps for deferred frontend, deferred summarization, and absent deletion
semantics.

In `docs/architecture/current-state.md`, update the backend component map, record
the implemented conversation and message contracts with their vocabularies and
ordering rules, record the shared store and the per-module registry, and update
the gap list. Do not repair the pre-existing stale claims in this file about CI
masking or `.env.example`; those belong to earlier milestones and are out of R4
scope.

- [ ] **Step 3: Update the data model**

In `docs/architecture/data-model.md`, mark the `Conversation` and `Message`
implemented field subsets with their R4 rules, following the existing
`Implemented TripWorkspace Fields (R3)` pattern. State explicitly that `summary`
has no column and no producer in R4, that messages carry no independent retention
state and follow their parent conversation, and that every other entity and
relationship remains conceptual.

- [ ] **Step 4: Update roadmap and plan state**

Update the `R4` roadmap row with implementation evidence only after verification
passes. Do not mark `R5` or any later milestone started. Move this plan and its
plan index row to `Completed` only after package verification and repository-owner
change-set review evidence exist.

- [ ] **Step 5: Run the documentation check**

Run:

```bash
grep -n -E "tenant isolation|authenticated user|authorization control|production ready|production database" DEVELOPMENT.md ARCHITECTURE.md docs/architecture/current-state.md docs/architecture/data-model.md docs/roadmap/master-roadmap.md docs/plans/2026-09-04-conversation-persistence-implementation.md
```

Expected: every match is reviewed and either removed or clearly framed as future
work or an explicit non-goal.

- [ ] **Step 6: Review checkpoint**

Review: that documentation matches implemented behavior, that the deferred
frontend is stated plainly rather than implied, and that nothing overclaims
production, security, memory, planner, or summarization behavior.

Expected: a reader of the canonical docs can find every R4 route and limitation
without reading the spec.

## Task 8: Run Package Verification and Scope Review

**Files:**

- Read: every changed tracked and untracked R4 file
- Modify after verification: this plan's completion record, `docs/plans/README.md`
  status, `docs/roadmap/master-roadmap.md` `R4` evidence

**Interfaces:**

- Consumes: the complete R4 change set
- Produces: fresh verification evidence and a repository-owner review packet

- [ ] **Step 1: Run the full backend suite**

Run: `./.venv/bin/python -m pytest backend/tests`

Expected: the recorded `447` baseline plus every new R4 test, with no previously
passing test turning red. If any test requires an unavailable external model or
Chroma state, stop and report the exact failing command and reason rather than
substituting weaker evidence.

- [ ] **Step 2: Compile**

Run: `./.venv/bin/python -m compileall backend`

Expected: exit `0`.

- [ ] **Step 3: Run import-boundary checks**

Run:

```bash
grep -rn -E "backend\.conversations|backend\.orchestration|app\.api\.conversations|app\.schemas\.conversations" backend/rag
```

```bash
grep -n -E "backend\.conversations|backend\.orchestration|app\.api\.conversations|app\.schemas\.conversations" backend/tests/unit/test_evaluation_*.py backend/tests/integration/test_rag_evaluation_flow.py
```

```bash
grep -rn -E "backend\.conversations|backend\.orchestration" backend/workspaces
```

Expected: no matches from any of the three commands. `grep` exit status `1` with
empty output is the passing result.

Also confirm the R3 boundary still holds:

```bash
grep -rn -E "backend\.workspaces|app\.api\.workspaces|app\.schemas\.workspaces" backend/rag
```

Expected: exit `1`, no matches.

- [ ] **Step 4: Run containment checks**

Run:

```bash
grep -rn -E "sqlite3|CREATE TABLE|PRAGMA user_version" backend/app backend/workspaces backend/conversations backend/orchestration backend/storage
```

Expected: `sqlite3` and `CREATE TABLE` appear only in
`backend/storage/schema_registry.py`,
`backend/workspaces/sqlite_repository.py`, and
`backend/conversations/sqlite_repository.py`. `PRAGMA user_version` appears only
in `backend/storage/schema_registry.py`. Any other match is a boundary violation
and must be fixed, not explained.

Run:

```bash
grep -rn -E "APP_DB_PATH|WORKSPACE_DB_PATH" backend/app backend/workspaces backend/conversations backend/orchestration backend/storage
```

Expected: `APP_DB_PATH` appears in `backend/app/config.py`, which defines it, and
at the two dependency construction sites in `backend/app/api/workspaces.py` and
`backend/app/api/conversations.py`. `WORKSPACE_DB_PATH` appears only in
`backend/app/config.py` as the deprecated alias.

- [ ] **Step 5: Run API contract checks**

Run: `./.venv/bin/python -m pytest backend/tests/integration/test_conversation_api.py backend/tests/integration/test_chat_conversation_binding.py backend/tests/integration/test_workspace_api.py backend/tests/integration/test_api.py`

Expected: all pass, proving the new routes work and the health, chat, and R3
workspace contracts are preserved.

- [ ] **Step 6: Confirm storage rollback evidence**

Run: `./.venv/bin/python -m pytest backend/tests/unit/test_schema_registry.py`

Expected: the named rollback-evidence test passes, demonstrating that a database
initialized by R4 presents a `PRAGMA user_version` value that the pre-R4
workspace version rule rejects.

- [ ] **Step 7: Run diff and status checks**

Run: `git diff --check`

Expected: no whitespace errors.

Run: `git status --short --untracked-files=all`

Expected: every changed and untracked file is reviewed and belongs to the approved
scope. No database file appears, and no symlink appears. Inspect untracked file
contents directly, because `git diff` alone does not show them.

- [ ] **Step 8: Confirm no default database was created**

Run: `ls data/app 2>&1`

Expected: the directory does not exist, proving no test touched the default
developer database path.

- [ ] **Step 9: Scope review**

Confirm that R4 implements only the shared registry, the conversation module, the
orchestration seam, the optional chat binding, the five routes, tests, and
documentation. Confirm that no authentication, authorization, memory,
summarization, planner state, itinerary versioning, deletion semantics, ORM,
migration framework, production database, or frontend work was added. Confirm that
health, chat, workspace, RAG, and evaluation compatibility evidence is fresh.

- [ ] **Step 10: Repository owner review handoff**

Record the exact verification commands and outcomes in the completion record.
Summarize changed files, evidence, limitations, and the remaining Git delivery
gate. Do not stage, commit, push, or open a pull request unless explicitly asked.

## Package Verification

Run freshly from the implementation environment after Task 7:

```bash
./.venv/bin/python -m pytest backend/tests/unit/test_schema_registry.py
./.venv/bin/python -m pytest backend/tests/unit/test_conversation_models.py
./.venv/bin/python -m pytest backend/tests/unit/test_conversation_service.py
./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_conversation_repository.py
./.venv/bin/python -m pytest backend/tests/unit/test_conversation_orchestrator.py
./.venv/bin/python -m pytest backend/tests/unit/test_sqlite_workspace_repository.py
./.venv/bin/python -m pytest backend/tests/integration/test_conversation_api.py backend/tests/integration/test_chat_conversation_binding.py
./.venv/bin/python -m pytest backend/tests/integration/test_workspace_api.py backend/tests/integration/test_api.py
./.venv/bin/python -m pytest backend/tests
./.venv/bin/python -m compileall backend
grep -rn -E "backend\.conversations|backend\.orchestration|app\.api\.conversations|app\.schemas\.conversations" backend/rag
grep -n -E "backend\.conversations|backend\.orchestration|app\.api\.conversations|app\.schemas\.conversations" backend/tests/unit/test_evaluation_*.py backend/tests/integration/test_rag_evaluation_flow.py
grep -rn -E "backend\.conversations|backend\.orchestration" backend/workspaces
grep -rn -E "backend\.workspaces|app\.api\.workspaces|app\.schemas\.workspaces" backend/rag
grep -rn -E "sqlite3|CREATE TABLE|PRAGMA user_version" backend/app backend/workspaces backend/conversations backend/orchestration backend/storage
grep -rn -E "APP_DB_PATH|WORKSPACE_DB_PATH" backend/app backend/workspaces backend/conversations backend/orchestration backend/storage
git diff --check
git status --short --untracked-files=all
ls data/app 2>&1
```

Expected package result:

1. Every workspace, conversation, orchestration, and route test passes.
2. The full suite reports the recorded `447` baseline plus the new R4 tests, with
   nothing previously passing turning red, or any unavailable external dependency
   named with its exact failure output.
3. Compilation succeeds with exit `0`.
4. All four import-boundary greps return no matches, with `grep` exit `1`.
5. `sqlite3` and `CREATE TABLE` are confined to the schema registry and the two
   repository adapters; `PRAGMA user_version` is confined to the schema registry;
   `APP_DB_PATH` is confined to settings and the two construction sites; and
   `WORKSPACE_DB_PATH` appears only as the alias in settings.
6. The unbound chat response key set is exactly `reply`, `model`, `citations`.
7. The named storage rollback evidence test passes.
8. No whitespace errors, and every tracked and untracked implementation file is
   reviewed against the approved scope.
9. `data/app` does not exist after the suite runs.

## Rollback

Before repository-owner acceptance, the entire change set can be withdrawn:
remove `backend/storage/`, `backend/conversations/`, `backend/orchestration/`, the
conversation routes and schemas, the chat schema and route changes, the
`APP_DB_PATH` setting, the new tests, and the documentation edits; restore
`backend/workspaces/sqlite_repository.py` to its `PRAGMA user_version`
bookkeeping and the three version tests to their original assertions.

Rollback evidence has three layers, as the approved spec defines:

1. **Code rollback.** The unbound chat compatibility test and the boundary and
   containment greps prove the R3 contract is restored with no residual
   dependency.
2. **Schema rollback.** A database initialized by R4 carries
   `PRAGMA user_version = 1000`, which the pre-R4 workspace check at
   `backend/workspaces/sqlite_repository.py:170` rejects because it differs from
   its expected `1`. An older build therefore refuses the file instead of writing
   into it. The named registry test is the evidence.
3. **Data rollback.** A database file created during R4 testing lives only in a
   pytest temporary directory. The default developer database is never created by
   tests, and any real database file is developer state that must not be deleted
   without the repository owner naming the exact path.

Rollback must not delete unrelated local data, Chroma state, R1/R2 evaluation
artifacts, or the R3 workspace database at the old default path.

## Completion Record

Not yet executed. This plan is `Approved` at version 0.1 and no task has run.

No source file has been created or modified for R4. The artifacts written so far
are the approved specification, ADR 0004, ADR 0005, this plan, their index
entries, and the roadmap status synchronization described below.

### Pre-execution amendments

The repository owner approved this plan conditional on two corrections, both
applied before the status changed to `Approved`.

**Roadmap status synchronization.** The roadmap contradicted the approved spec and
the actual Git state. The spec depends on "R3 accepted change set merged at
`2f632e2`" and `HEAD` is that merge commit, but the `R3` row still read
`In progress` with "awaiting repository-owner change-set review before Git
delivery", and the `R4` row still read `Blocked by gate`. A worker reading both
documents would have been unable to decide whether R3 was accepted or still under
review.

Verified before editing: `git log` shows `2f632e2 Merge branch 'r3-trip-workspace'
into feature/agent-memory`, and `git ls-files` confirms `backend/workspaces/` and
the workspace routes are tracked source on the branch.

Applied changes, all within the roadmap's own change rule 1 for status updates:

1. Added a `Delivered` status to the Milestone Status Vocabulary, meaning
   implemented, verified, accepted, and merged into the active development branch.
   The existing `Accepted in working tree` value could not express a merged state,
   which is why R3 had no correct value available.
2. Moved `R3` to `Delivered` and replaced its pending-review evidence with the
   acceptance and merge record, preserving the historical `427 passed` on base
   `6076d9e` alongside the post-merge `447 passed`, per change rule 5.
3. Moved `R4` to `In progress`, added ADR 0004 and ADR 0005 to its dependencies,
   expanded its deliverables to match the approved spec, and recorded that the
   spec, both ADRs, and this plan are approved while no source exists yet.
4. Rewrote the `Current Phase` section, which still described trip workspaces as
   living in an unmerged worktree and named `D4` as the active documentation
   package while the map showed `D5` through `D7` accepted.
5. Corrected the `D4` recommended action, which still read "Complete this
   package".

`R5` and `R7` remain `Blocked by gate` on `R4`, which is still correct because R4
has no implementation.

**Symlink guard.** The plan instructs symlinking `data/processed` into a linked
worktree. During R3 a `docs` symlink was replaced by a real directory and sixteen
local Markdown files were lost, six permanently. A six-rule guard was added to
[Execution environment](#execution-environment), referenced from Global Constraint
16, and enforced at two verification points: Task 1 Step 4 confirms the symlink is
invisible to `git status` immediately after creation, and Task 8 Step 7 confirms no
symlink appears in the final change set.

Verified before writing the guard: `.gitignore` line 29 ignores `data`, and
`git check-ignore -v` confirms both `data` and `data/processed` are covered, so the
existing R3 worktree symlink is already invisible to `git status`. The guard
therefore forbids overriding that protection rather than adding a new one. Also
verified that `docs/` is no longer ignored, so R4 documentation edits are tracked
deliverables that must never be reached through a symlink.

### Remaining gates

1. Implementation of Tasks 1 through 8, review, and fresh verification.
2. Repository-owner change-set review.
3. Git delivery, which remains a repository-owner action. Nothing has been staged,
   committed, pushed, or opened as a pull request.
