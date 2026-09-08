# Basic Semantic Memory Write Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` only after the exact
> specification and this plan are approved. Execute one task at a time and stop
> at every review checkpoint.

**Goal:** Deliver one production-shaped semantic-memory write vertical slice
for `travel.preference.hotel_atmosphere`, with authenticated standalone
conversations, explicit confirmed writes, background shadow extraction,
deterministic conflict resolution, atomic/idempotent PostgreSQL persistence,
user controls, and governed evaluation.

**Architecture:** Pure domain contracts and resolver behavior are completed
before adapters. PostgreSQL is the canonical lifecycle authority, with one
unit-of-work transaction for evidence, decision, assertion/version, trace, and
outbox state. Normal chat captures durable background work but cannot
auto-promote; user-initiated mutations share one confirmed command handler.

**Tech Stack:** Python, FastAPI, Pydantic, SQLAlchemy Core, Alembic, psycopg,
PostgreSQL, pytest, React/Vite, Vitest.

**Spec:** `docs/specs/2026-09-07-basic-semantic-memory-write-pipeline-design.md`
v0.1 (`Approved` on 2026-09-07; plan execution remains blocked).

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-09-07 |
| Approved specification | `docs/specs/2026-09-07-basic-semantic-memory-write-pipeline-design.md` v0.1, approved 2026-09-07 |
| Execution owner | Repository-approved implementation agent in an isolated worktree |
| Decision owner | Repository owner |
| Scope | First semantic key and the exact trigger, safety, conflict, persistence, control, and evaluation behavior in the governing spec |
| Verification | Focused unit/integration/evaluation commands plus full backend, frontend, migration, diff, and documentation review |

## Execution Block

This plan is a review artifact only. Do not execute Task 1 until:

1. the exact child plan containing the target task is approved;
2. an isolated implementation worktree is created under repository workflow;
3. the primary worktree and target paths are checked for overlapping changes.

The
[Risk-based Memory Control Amendment](../specs/2026-09-07-risk-based-memory-control-amendment.md)
v0.1, ADR 0017, and the exact amendment implementation plan are approved.
Tasks 5, 8-9, and 11 execute under that amendment delta rather than historical
confirm-all behavior. Task 12 remains on hold until the evaluation amendment
is separately approved.

## Global Constraints

1. Implement only `travel.preference.hotel_atmosphere` with normalized values
   `quiet`, `lively`, `central`, and `secluded`.
2. User and conversation scopes execute; workspace scope remains compatible but
   is not a new behavior surface.
3. Background extraction is shadow-only and creates zero active versions.
4. Risk-based confirmation governs user mutations: explicit low-risk remember,
   delete-one, and toggle operations commit directly with application-owned
   saved/Undo state; bulk delete and conversation-to-user scope expansion use
   preview plus one-time confirmation; sensitive data is no-store/no-prompt.
5. Model output never owns authorization, sensitivity downgrades, lifecycle
   mutation, SQL, or transaction boundaries.
6. Secrets and prohibited payment/authentication values never reach durable
   candidate, model request, index, log, or report state outside controlled
   redaction evidence.
7. Every canonical mutation is atomic, idempotent, owner-scoped, and traceable.
8. PostgreSQL is used for active development/integration/production behavior;
   SQLite remains legacy-only during migration.
9. Preserve unrelated user changes and current R5/R6 compatibility until an
   approved task explicitly replaces a named contract.
10. No inferred auto-promotion, summary, episode, pgvector, graph, Kafka, or
    multi-region work enters this plan.

## Task Matrix

This is the master sequencing matrix. Before execution, split it into child
plans at these review boundaries: Task 2; Tasks 3-5; Tasks 6-7; Tasks 8-9;
Tasks 10-11; and Tasks 12-13. Approval of this master draft does not authorize
all child scopes at once.

| Task | Independently reviewable outcome | Depends on | Primary verification |
| --- | --- | --- | --- |
| 1 | Characterized current flow and protected compatibility tests | None | Existing R5/R6 focused suite |
| 2 | Standalone owned conversation domain contract | 1 | Conversation domain/service tests |
| 3 | First semantic key registry and immutable write domain model | 1 | Pure registry/model tests |
| 4 | Deterministic relationship and conflict resolver | 3 | Resolver truth-table tests |
| 5 | Eligibility, secret, sensitivity, and write policy | 3-4 | Policy/safety unit tests |
| 6 | PostgreSQL/Alembic foundation and schema | 2-5 | Migration upgrade/downgrade and schema tests |
| 7 | Atomic Memory Unit of Work, RLS, and idempotency | 6 | PostgreSQL failure/concurrency tests |
| 8 | Explicit confirmed memory command backend | 7 | API/service confirmation tests |
| 9 | Memory Manager and conversational control UI | 8 | Vitest and backend contract tests |
| 10 | Message/outbox capture and worker runtime | 2, 6-7 | Chat/outbox/lease/retry/cancel tests |
| 11 | Structured model extraction and background shadow flow | 5, 10 | Bilingual/schema/provider tests |
| 12 | Focused evaluation harness, fixtures, and reports | 3-11 | Protocol CLI and hard-gate tests |
| 13 | Migration decision, feature gates, documentation, and package verification | 1-12 | Full verification packet |

## File Responsibility Map

| File | Responsibility | Depends on |
| --- | --- | --- |
| `backend/memory/write_pipeline/registry.py` | Versioned canonical key, value, scope, cardinality, sensitivity, and authority definitions | Focused spec |
| `backend/memory/write_pipeline/models.py` | Immutable evidence, candidate, decision, assertion, version, relation, operation, and change-set contracts | Registry |
| `backend/memory/write_pipeline/resolver.py` | Pure deterministic change-set resolution | Registry and models |
| `backend/memory/write_pipeline/policy.py` | Eligibility, sensitivity escalation, authority, and candidate disposition | Registry, models, secret detector |
| `backend/memory/write_pipeline/secrets.py` | Deterministic prohibited-secret/payment detection and redaction | Security contract |
| `backend/memory/write_pipeline/uow.py` | Transaction-scoped persistence interface | Domain change set |
| `backend/memory/write_pipeline/postgres.py` | SQLAlchemy Core PostgreSQL unit-of-work adapter | PostgreSQL schema |
| `backend/memory/write_pipeline/outbox.py` | Outbox contracts, lease transitions, idempotency, and typed handler dispatch | PostgreSQL adapter |
| `backend/memory/write_pipeline/model_adapter.py` | Strict bilingual candidate/relationship extraction interface and provider adapter | Registry and models |
| `backend/memory/write_pipeline/service.py` | Explicit command and background shadow orchestration through policy/resolver/UoW | All write modules |
| `backend/memory/write_pipeline/evaluation/` | Focused dataset loader, scorer, report, and CLI | Protocol and runtime interfaces |
| `backend/conversations/models.py` | Direct conversation owner and optional workspace domain contract | Standalone conversation decision |
| `backend/conversations/repository.py` | Owner-scoped optional-workspace repository interface | Conversation model |
| `backend/conversations/service.py` | Owned standalone conversation creation and scope checks | Conversation repository |
| `backend/conversations/postgres_repository.py` | PostgreSQL conversation/message adapter and message/outbox atomic append | PostgreSQL foundation |
| `backend/app/api/chat.py` | Auto-create owned conversation and preserve controlled chat failures | Conversation and orchestrator interfaces |
| `backend/app/api/memory_controls.py` | Proposed/confirmed memory command and Memory Manager HTTP contracts | Memory command service |
| `backend/app/schemas/memory_controls.py` | Strict request/response schemas without raw trace leakage | Command contracts |
| `backend/app/config.py` | PostgreSQL, explicit write, and background shadow feature configuration | Deployment contract |
| `backend/storage/postgres.py` | Engine/pool creation and transaction context without product policy | SQLAlchemy/psycopg |
| `backend/storage/migrations/` | Alembic environment and ordered conversation/memory schema revisions | SQLAlchemy metadata |
| `frontend/src/services/memory.js` | Memory Manager and confirmation client calls | HTTP contracts |
| `frontend/src/components/memory/MemoryManager.jsx` | Inspect and initiate confirmed memory actions | Memory client |
| `frontend/src/components/memory/MemoryConfirmation.jsx` | Display exact operation/scope and capture confirmation/refusal | Confirmation contract |
| `docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1/` | Synthetic bilingual quality and safety fixtures | Focused evaluation protocol |

## Task 1: Characterize and Freeze the Existing Flow

**Files:**

- Create: `backend/tests/characterization/test_current_memory_write_flow.py`
- Read: `backend/memory/extraction.py`
- Read: `backend/memory/policy.py`
- Read: `backend/memory/promotion.py`
- Read: `backend/memory/service.py`
- Read: `backend/memory/sqlite_repository.py`
- Read: `backend/orchestration/conversation_orchestrator.py`

**Interfaces:**

- Consumes: current R5/R6 public and service contracts.
- Produces: compatibility tests that identify behavior preserved until a later
  task explicitly migrates it.

- [ ] **Step 1: Write characterization tests**

Cover current accepted preference extraction, trace-excluded rejection, manual
promotion, broad correction behavior, separate promotion repository calls,
gate-off chat compatibility, and bound-turn persistence.

- [ ] **Step 2: Run the tests against current source**

Run:

```bash
pytest -q backend/tests/characterization/test_current_memory_write_flow.py
```

Expected: PASS without implementation changes. If a test cannot describe actual
behavior, correct the characterization rather than changing production code.

- [ ] **Step 3: Run affected existing tests**

```bash
pytest -q \
  backend/tests/unit/test_memory_extraction.py \
  backend/tests/unit/test_memory_policy.py \
  backend/tests/unit/test_memory_promotion.py \
  backend/tests/integration/test_chat_memory_retrieval.py
```

Expected: PASS.

- [ ] **Step 4: Review checkpoint**

Review the test names as a code-reading map. The implementer must explain the
current source-to-candidate-to-record-to-context flow and identify which tests
will remain compatibility checks versus migration checks.

## Task 2: Add the Standalone Owned Conversation Domain Contract

**Files:**

- Modify: `backend/conversations/models.py`
- Modify: `backend/conversations/repository.py`
- Modify: `backend/conversations/service.py`
- Create: `backend/tests/unit/test_standalone_conversation.py`
- Modify: `backend/tests/unit/test_conversation_service.py`

**Interfaces:**

- Produces:

```python
@dataclass(frozen=True)
class ConversationCreate:
    owner_user_id: str
    workspace_id: str | None = None
    title: str | None = None

@dataclass(frozen=True)
class Conversation:
    conversation_id: str
    owner_user_id: str
    workspace_id: str | None
    title: str | None
    created_at: datetime
    updated_at: datetime
    retention_state: ConversationRetentionState
```

- [ ] **Step 1: Write failing domain tests**

Test required owner, optional workspace, compatibility with a valid workspace,
owner mismatch rejection, and owned standalone list/get behavior.

- [ ] **Step 2: Verify RED**

```bash
pytest -q backend/tests/unit/test_standalone_conversation.py
```

Expected: FAIL because direct owner and optional workspace are absent.

- [ ] **Step 3: Implement minimal domain and interface changes**

Do not change HTTP or persistence adapters yet. Keep ownership validation in
the service and storage-neutral contracts.

- [ ] **Step 4: Verify GREEN and compatibility**

```bash
pytest -q \
  backend/tests/unit/test_standalone_conversation.py \
  backend/tests/unit/test_conversation_service.py
```

Expected: PASS.

- [ ] **Step 5: Review checkpoint**

Confirm no hidden/default workspace was introduced and existing workspace-bound
conversation semantics remain expressible.

## Task 3: Implement the First Registry Entry and Immutable Domain Model

**Files:**

- Create: `backend/memory/write_pipeline/__init__.py`
- Create: `backend/memory/write_pipeline/registry.py`
- Create: `backend/memory/write_pipeline/models.py`
- Create: `backend/tests/unit/memory_write_pipeline/test_registry.py`
- Create: `backend/tests/unit/memory_write_pipeline/test_models.py`

**Interfaces:**

- Produces:

```python
SEMANTIC_REGISTRY_VERSION = "semantic-registry-v1"
HOTEL_ATMOSPHERE_KEY = "travel.preference.hotel_atmosphere"

class HotelAtmosphere(str, Enum):
    QUIET = "quiet"
    LIVELY = "lively"
    CENTRAL = "central"
    SECLUDED = "secluded"

def get_key_definition(key: str) -> SemanticKeyDefinition: ...
def normalize_value(key: str, value: object) -> object: ...
def assertion_identity(candidate: MemoryCandidate) -> AssertionIdentity: ...
```

- [ ] **Step 1: Write failing registry/model tests**

Test the exact key, values, single cardinality, user/conversation scopes,
ordinary-personal minimum, deterministic condition fingerprint, prefixed IDs,
UTC times, immutability, and unknown-key/value rejection.

- [ ] **Step 2: Verify RED**

```bash
pytest -q backend/tests/unit/memory_write_pipeline/test_registry.py backend/tests/unit/memory_write_pipeline/test_models.py
```

- [ ] **Step 3: Implement the minimal pure-domain package**

Use no FastAPI, Pydantic, SQLAlchemy, model provider, repository, or legacy
memory import inside these files.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Review checkpoint**

Trace one English and one Vietnamese display string to the same normalized
value without using the display string as assertion identity.

## Task 4: Implement the Pure Deterministic Conflict Resolver

**Files:**

- Create: `backend/memory/write_pipeline/resolver.py`
- Create: `backend/tests/unit/memory_write_pipeline/test_resolver.py`

**Interfaces:**

- Consumes: immutable candidate, current assertion versions, typed relation,
  authority, scope, and expected version.
- Produces:

```python
def resolve_change(
    candidate: MemoryCandidate,
    current: tuple[MemoryVersion, ...],
    relation: MemoryRelation,
) -> MemoryChangeSet: ...
```

- [ ] **Step 1: Write the resolver truth table as failing parameterized tests**

Include `ADD`, `REINFORCE`, explicit `SUPERSEDE`, weaker-opposition hold,
`ADD_EXCEPTION`, `PENDING_CONFLICT`, `REJECT`, and `NOOP`.

- [ ] **Step 2: Verify RED**

```bash
pytest -q backend/tests/unit/memory_write_pipeline/test_resolver.py
```

- [ ] **Step 3: Implement minimal deterministic resolution**

The resolver returns data only. It must not import a repository, SQLAlchemy,
FastAPI, or model adapter.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: PASS with every operation asserted exactly.

- [ ] **Step 5: Review checkpoint**

Explain why a conversation exception leaves the user default unchanged and why
an uncertain relation cannot mutate lifecycle state.

## Task 5: Add Eligibility, Secret, Sensitivity, and Write Policy

**Files:**

- Create: `backend/memory/write_pipeline/secrets.py`
- Create: `backend/memory/write_pipeline/policy.py`
- Create: `backend/tests/unit/memory_write_pipeline/test_secrets.py`
- Create: `backend/tests/unit/memory_write_pipeline/test_policy.py`

**Interfaces:**

- Produces:

```python
def detect_prohibited_content(text: str) -> SecretDetection: ...
def evaluate_eligibility(event: MemorySourceEvent) -> EligibilityDecision: ...
def classify_sensitivity(candidate: MemoryCandidate) -> SensitivityBand: ...
def decide_candidate(candidate: MemoryCandidate, context: PolicyContext) -> MemoryDecision: ...
```

- [ ] **Step 1: Write failing safety/policy tests**

Cover authenticated user evidence, assistant/tool/external rejection, inactive
or deleted source, unknown key, ordinary preference, restricted hold,
prohibited secret, and background `SHADOW` disposition.

- [ ] **Step 2: Verify RED**

```bash
pytest -q backend/tests/unit/memory_write_pipeline/test_secrets.py backend/tests/unit/memory_write_pipeline/test_policy.py
```

- [ ] **Step 3: Implement deterministic layers**

Reuse secret patterns only through an explicitly owned shared detector or move
them under this module with compatibility tests. A contextual model result may
escalate but never downgrade the deterministic/registry floor.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: PASS with no raw prohibited value in assertion
messages or captured logs.

- [ ] **Step 5: Review checkpoint**

Confirm extraction answers what the text may mean, while policy alone answers
whether it may become durable memory.

## Task 6: Establish PostgreSQL, SQLAlchemy Core, and Alembic

**Files:**

- Modify: `requirements.txt`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `backend/app/config.py`
- Create: `alembic.ini`
- Create: `backend/storage/postgres.py`
- Create: `backend/storage/migrations/env.py`
- Create: `backend/storage/migrations/script.py.mako`
- Create: `backend/storage/migrations/versions/20260907_01_owned_conversations.py`
- Create: `backend/storage/migrations/versions/20260907_02_memory_write_pipeline.py`
- Create: `backend/tests/integration/test_postgres_migrations.py`

**Interfaces:**

- Produces a configured SQLAlchemy engine/pool and ordered reversible schema for
  conversations, events, candidates, decisions, evidence, assertions, versions,
  outbox, summaries, episodes, and deletion ledger.

- [ ] **Step 1: Write migration verification tests**

Assert upgrade from empty database, expected tables/constraints/RLS policies,
downgrade to the previous revision, and clean re-upgrade.

- [ ] **Step 2: Verify RED in isolated PostgreSQL**

```bash
pytest -q backend/tests/integration/test_postgres_migrations.py
```

Expected: FAIL because configuration and migrations do not exist.

- [ ] **Step 3: Add pinned dependencies and local PostgreSQL service**

Add SQLAlchemy, Alembic, psycopg, and pooling through the repository dependency
source of truth. Add safe placeholder environment names only; no credentials.

- [ ] **Step 4: Implement metadata and migrations**

Use typed columns for identity/lifecycle/time and registry-validated JSONB for
value/condition payloads. Preserve prefixed text IDs. Enable fail-closed RLS
policies without relying on them as the sole application authorization.

- [ ] **Step 5: Verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 6: Review checkpoint**

Review upgrade/downgrade SQL, unique-current-version enforcement, owner
constraints, JSONB bounds, indexes, and connection tenant-context reset.

## Task 7: Implement MemoryUnitOfWork, Atomicity, RLS, and Idempotency

**Files:**

- Create: `backend/memory/write_pipeline/uow.py`
- Create: `backend/memory/write_pipeline/postgres.py`
- Create: `backend/tests/integration/test_memory_write_postgres.py`

**Interfaces:**

- Produces:

```python
class MemoryUnitOfWork(Protocol):
    def apply_memory_change(
        self,
        change: MemoryChangeSet,
        principal: AuthenticatedPrincipal,
    ) -> MemoryWriteResult: ...
```

- [ ] **Step 1: Write failing integration tests**

Test add, reinforce, supersede, exception, pending conflict, owner isolation,
missing tenant context, duplicate idempotency key, stale expected version,
concurrent same-assertion writers, and failure injection after each write stage.

- [ ] **Step 2: Verify RED**

```bash
pytest -q backend/tests/integration/test_memory_write_postgres.py
```

- [ ] **Step 3: Implement one transaction-scoped adapter**

Use `READ COMMITTED`, insert-or-resolve assertion identity, `SELECT FOR UPDATE`,
fresh re-resolution, immutable row inserts, outbox insert, and bounded retry.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: PASS and zero partial-state assertions.

- [ ] **Step 5: Review checkpoint**

Inspect transaction ownership, rollback evidence, SQL parameterization, RLS
tenant setup/reset, and absence of model/network calls inside the transaction.

## Task 8: Implement Explicit Confirmed Memory Commands

**Files:**

- Create: `backend/memory/write_pipeline/service.py`
- Create: `backend/app/schemas/memory_controls.py`
- Create: `backend/app/api/memory_controls.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/unit/memory_write_pipeline/test_command_service.py`
- Create: `backend/tests/integration/test_memory_control_api.py`

**Interfaces:**

- Produces:

```python
def propose_command(command: MemoryUserCommand, principal: AuthenticatedPrincipal) -> MemoryCommandPreview: ...
def confirm_command(command_id: str, confirmation_token: str, principal: AuthenticatedPrincipal) -> MemoryWriteResult: ...
```

- [ ] **Step 1: Write failing command and API tests**

Test remember, correct, delete, enable, disable, refusal, expired confirmation,
stale preview/version, cross-owner command ID, exact scope display, and success
acknowledgement only after commit.

- [ ] **Step 2: Verify RED**

```bash
pytest -q backend/tests/unit/memory_write_pipeline/test_command_service.py backend/tests/integration/test_memory_control_api.py
```

- [ ] **Step 3: Implement preview/confirmation contracts**

Store no durable mutation before confirmation. Revalidate owner, assertion
version, sensitivity, and deletion epoch during confirmation.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Review checkpoint**

Confirm every user mutation crosses the same handler/policy/resolver/UoW path
and no HTTP response exposes unrestricted evidence content.

## Task 9: Implement the Memory Manager and Confirmation UI

**Files:**

- Create: `frontend/src/services/memory.js`
- Create: `frontend/src/components/memory/MemoryManager.jsx`
- Create: `frontend/src/components/memory/MemoryConfirmation.jsx`
- Modify: `frontend/src/App.jsx`
- Create: `frontend/tests/memory-manager.test.jsx`

**Interfaces:**

- Consumes the Task 8 list/search/preview/confirm/refuse contracts.
- Produces inspect, remember, correct, delete, enable, and disable flows with
  explicit confirmation and controlled failure states.

- [ ] **Step 1: Write failing Vitest interaction tests**

Cover loading, empty, error, confirmation, refusal, stale confirmation,
cross-device refresh, keyboard navigation, focus return, and no optimistic
success before backend commit.

- [ ] **Step 2: Verify RED**

```bash
cd frontend && npm test -- --run tests/memory-manager.test.jsx
```

- [ ] **Step 3: Implement minimal accessible UI**

Reuse existing authenticated API client and product styles. Show exact key,
display value, scope, source summary, and operation. Do not expose model
confidence as a truth probability.

- [ ] **Step 4: Verify GREEN and build**

```bash
cd frontend && npm test -- --run tests/memory-manager.test.jsx && npm run build
```

Expected: tests and production build pass.

- [ ] **Step 5: Review checkpoint**

Review interruption cost, confirmation clarity, accessibility, responsive
behavior, and consistency with natural-language commands.

## Task 10: Add Atomic Message/Outbox Capture and the Worker Runtime

**Files:**

- Create: `backend/memory/write_pipeline/outbox.py`
- Create: `backend/memory/write_pipeline/worker.py`
- Modify: `backend/conversations/postgres_repository.py`
- Modify: `backend/orchestration/conversation_orchestrator.py`
- Create: `backend/tests/integration/test_memory_write_runtime.py`

**Interfaces:**

- Produces typed outbox handlers and states `PENDING`, `LEASED`, `SUCCEEDED`,
  `DEAD_LETTER`, and `CANCELLED`.

- [ ] **Step 1: Write failing runtime tests**

Test message/outbox atomicity, non-blocking chat, conversation debounce,
new-message cursor, lease claim/expiry, parallel different-owner work,
same-identity serialization, retry classification, dead-letter, priority, and
deletion-epoch cancellation.

- [ ] **Step 2: Verify RED**

```bash
pytest -q backend/tests/integration/test_memory_write_runtime.py
```

- [ ] **Step 3: Implement the smallest database-backed runtime**

Claim in a short transaction; run handlers outside the lease transaction;
revalidate source/deletion/idempotency before canonical commit. Keep typed
handlers in one process; do not add Redis, RabbitMQ, or Kafka.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Review checkpoint**

Confirm no model call occurs while a database transaction/row lock is held and
normal chat never waits for background extraction.

## Task 11: Add Structured Model Extraction and Shadow Processing

**Files:**

- Create: `backend/memory/write_pipeline/model_adapter.py`
- Modify: `backend/memory/write_pipeline/service.py`
- Create: `backend/tests/unit/memory_write_pipeline/test_model_adapter.py`
- Modify: `backend/tests/integration/test_memory_write_runtime.py`

**Interfaces:**

- Produces strict bilingual candidate and relation outputs with provider,
  model, prompt, output-schema, extractor, and policy version evidence.

- [ ] **Step 1: Write failing adapter tests with a fake provider**

Cover Vietnamese/English normalization, exact schema, one repair attempt,
invalid-after-repair, timeout/429/5xx classification, unknown key, secret input
pre-filter, and relation uncertainty.

- [ ] **Step 2: Verify RED**

```bash
pytest -q backend/tests/unit/memory_write_pipeline/test_model_adapter.py
```

- [ ] **Step 3: Implement the provider-independent interface and configured adapter**

Never pass prohibited content. Bound input/output tokens and timeout. Background
results always create `SHADOW`, `HELD_SENSITIVE`, `PENDING_CONFLICT`,
`REJECTED`, or `INVALID`; they create zero active versions.

- [ ] **Step 4: Verify GREEN and runtime integration**

```bash
pytest -q backend/tests/unit/memory_write_pipeline/test_model_adapter.py backend/tests/integration/test_memory_write_runtime.py
```

- [ ] **Step 5: Review checkpoint**

Review prompt/data authority separation, version capture, repair bounds, cost
counters, and proof that background extraction cannot call the promotion path.

## Task 12: Build the Focused Evaluation Harness and Dataset

**Files:**

- Create: `backend/memory/write_pipeline/evaluation/__init__.py`
- Create: `backend/memory/write_pipeline/evaluation/models.py`
- Create: `backend/memory/write_pipeline/evaluation/dataset.py`
- Create: `backend/memory/write_pipeline/evaluation/runner.py`
- Create: `backend/memory/write_pipeline/evaluation/cli.py`
- Create: `docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1/manifest.json`
- Create: `docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1/examples.jsonl`
- Create: `backend/tests/unit/memory_write_pipeline/test_evaluation.py`

**Interfaces:**

- Produces CLI commands `validate-dataset`, `preflight`, `run`, and `compare`
  with `PASS`, `FAIL`, `INCONCLUSIVE`, and `INVALID` reports.

- [ ] **Step 1: Write failing dataset/result-state tests**

Encode S01-S22, mandatory slices, numerator/denominator accounting, hard-gate
priority, missing-slice invalidation, report redaction, and reproducible run
metadata.

- [ ] **Step 2: Verify RED**

```bash
pytest -q backend/tests/unit/memory_write_pipeline/test_evaluation.py
```

- [ ] **Step 3: Implement the deterministic harness and synthetic fixtures**

Reuse shared result discipline where it does not alter the focused protocol.
Do not copy raw user content into reports.

- [ ] **Step 4: Verify GREEN and run the suite**

```bash
python -m backend.memory.write_pipeline.evaluation.cli validate-dataset --dataset docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1
python -m backend.memory.write_pipeline.evaluation.cli run --dataset docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1 --suite safety --output-dir docs/reports/memory-write-pipeline/candidate
python -m backend.memory.write_pipeline.evaluation.cli run --dataset docs/evaluation/fixtures/memory/write-pipeline-hotel-atmosphere-v0.1 --suite quality --output-dir docs/reports/memory-write-pipeline/candidate
```

Expected: commands exit zero only when the protocol's evidence is valid and all
applicable gates pass.

- [ ] **Step 5: Review checkpoint**

Review the largest failures, every hard-gate example, environment metadata,
and proof that the dataset has no real sensitive data.

## Task 13: Gate Rollout, Resolve Legacy Data, and Verify the Package

**Files:**

- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Modify: `DEVELOPMENT.md`
- Modify: `docs/architecture/current-state.md`
- Modify: `docs/evaluation/memory-evaluation.md`
- Create or update: the approved migration evidence report under `docs/reports/`

**Interfaces:**

- Produces independent server gates for explicit writes and background shadow
  capture, an evidence-backed SQLite disposal/quarantine decision, operator
  setup, rollback, and the final review packet.

- [ ] **Step 1: Inventory existing R5/R6 SQLite data read-only**

Record table counts, schema versions, whether data is synthetic/dev/real, and
whether provenance can resolve. Do not print candidate/message text.

- [ ] **Step 2: Apply the approved legacy decision**

If no real data exists, keep SQLite state disposable and document removal under
the approved rollback. If retention is required, import only as quarantined
legacy evidence and prove zero active V2 versions.

- [ ] **Step 3: Run focused verification**

```bash
pytest -q backend/tests/unit/memory_write_pipeline
pytest -q backend/tests/integration/test_postgres_migrations.py backend/tests/integration/test_memory_write_postgres.py backend/tests/integration/test_memory_control_api.py backend/tests/integration/test_memory_write_runtime.py
```

Expected: PASS.

- [ ] **Step 4: Run full repository verification**

```bash
python -m compileall backend
pytest -q backend/tests
cd frontend && npm run lint && npm test -- --run && npm run build
docker compose config
```

Expected: every command exits zero; skipped or unavailable checks are reported
and prevent a completion claim when required by the approved plan.

- [ ] **Step 5: Run migration and evaluation verification**

Execute Alembic upgrade/downgrade/re-upgrade against isolated PostgreSQL and all
focused protocol suites. Expected: schema round-trip succeeds and reports are
valid with zero hard-gate events.

- [ ] **Step 6: Inspect exact change set**

```bash
git status --short --untracked-files=all
git diff --check
```

Directly inspect untracked content and compare every changed path with the
approved spec and File Responsibility Map.

- [ ] **Step 7: Review checkpoint**

Return to repository-owner review with requirement mapping, RED/GREEN evidence,
evaluation reports, migration outcome, rollback, known limitations, and an
explicit statement that inferred auto-promotion, summary, episode, pgvector,
and production-readiness claims remain outside scope.

## Package Verification Table

| Requirement | Evidence |
| --- | --- |
| One canonical key | Registry/model tests and dataset key accuracy |
| Explicit confirmed write | Command service/API/UI tests |
| Background shadow only | Runtime tests and zero-promotion hard gate |
| Conflict correctness | Pure resolver truth table and focused scenarios S04-S08 |
| Secret/sensitivity policy | Unit safety tests and scenarios S09-S10 |
| Atomicity/idempotency | PostgreSQL failure injection, redelivery, and concurrency tests |
| Owner isolation | Application and RLS integration tests |
| Non-blocking chat | Timing/integration evidence |
| Traceability | Canonical decision/evidence assertions and report metadata |
| Migration safety | SQLite inventory and zero-auto-active evidence |
| Learning outcome | Review walkthrough from message to candidate, relation, change set, transaction, and report |

## Rollback

1. Disable explicit-write and background-shadow gates independently.
2. Stop workers and preserve pending/cancelled outbox evidence for diagnosis.
3. Downgrade PostgreSQL only through the reviewed Alembic revision and only
   when no approved privacy deletion would be reversed.
4. Preserve current R5/R6 behavior until the approved migration marks it inert.
5. Remove/rebuild derived indexes without altering canonical lifecycle state.
6. Never restore deleted user content from legacy SQLite, reports, fixtures,
   caches, or outbox payloads.

## Self-review Record

- Spec coverage: every focused goal and acceptance criterion maps to Tasks 1-13.
- Scope: summary, episode, inferred auto-promotion, pgvector, graph, Kafka, and
  full production load certification are explicitly excluded.
- Type consistency: registry, candidate, decision, assertion, version,
  relation, operation, change set, unit of work, command, and result names are
  consistent across tasks.
- Placeholder scan: no unresolved implementation placeholder authorizes an
  executor to invent behavior; numerical tuning that depends on SLO evidence
  remains outside execution approval.

## Plan Approval Record

Version 0.1 was approved by the repository owner on 2026-09-07 as the master
sequencing and decomposition authority. It authorizes preparation and review of
six bounded child plans. It does not authorize runtime implementation,
dependency installation, migration, deployment, or execution of any child
scope before that exact child plan receives separate approval.
