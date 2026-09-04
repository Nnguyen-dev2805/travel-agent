# Architecture Baseline Design

| Field | Value |
| --- | --- |
| Status | Approved |
| Version | 0.1 |
| Date | 2026-08-31 |
| Change class | Level 3 - Architecture Design |
| Decision owner | Repository owner |
| Scope | Documentation Package 3 - architecture baseline, target architecture, and data model |
| Parent design | [Documentation System Design](./2026-08-30-documentation-system-design.md), version 0.1 |
| Depends on | [Project Entry Points Design](./2026-08-31-project-entry-points-design.md), version 0.1 |
| Implementation plan | [Architecture Baseline Implementation Plan](../plans/2026-08-31-architecture-baseline-implementation.md), version 0.1 (Approved; Completed) |
| Related issue | None - approval of version 0.1 records the repository-owner exception for this conversation intake |
| Superseded document | None |

## Summary

Package 3 establishes the architecture baseline for Travel Agent without
changing runtime behavior. It creates three detailed architecture documents:
`docs/architecture/current-state.md`, `docs/architecture/target-state.md`, and
`docs/architecture/data-model.md`.

The selected direction is a workspace-first travel assistant architecture.
A trip workspace becomes the primary product container for one planned trip.
Layered memory is designed around explicit module seams: short-lived working
context, trip-scoped state, user-scoped long-term preferences, episodic
conversation memories, retrieved travel knowledge, and evaluation traces. This
design is future target architecture, not implemented behavior.

Approval of this design authorizes preparation of a Package 3 implementation
plan for architecture documentation only. It does not authorize source code
changes, schema migrations, database setup, memory implementation, trip
workspace implementation, RAG repair, external service configuration, or Git
delivery.

## Current-state Evidence

Codebase Memory was checked at Verify tier for the current source paths named
below. The graph project was
`Users-tnhatnguyendev2805-Documents-Projects-travel-agent`, indexed at
generation `2026-08-31T00:13:25Z` with 664 nodes and 1811 edges. Coverage for
the cited paths returned `no_recorded_issue` and `metadata_match`. This is a
best-effort index signal, not proof of semantic completeness. Exact source and
configuration were also read directly.

| Evidence | Current fact relevant to Package 3 |
| --- | --- |
| [Architecture Gateway](../../ARCHITECTURE.md) | Package 2 already records the high-level implemented component map, online request flow, offline data flow, trust boundaries, invariants, and known gaps. |
| [`backend/app/main.py`](../../backend/app/main.py) | FastAPI mounts `/health` and the chat router under `/api/v1`; startup attempts to pre-warm RAG and converts failures to warnings. |
| [`backend/app/api/chat.py`](../../backend/app/api/chat.py) | `chat_endpoint` strips one `message`, logs a prefix, calls process-global RAG, and returns reply, model, and citations. |
| [`backend/app/schemas/chat.py`](../../backend/app/schemas/chat.py) | The public request contains only `message`; there is no user, trip, workspace, conversation, or memory identifier. |
| [`frontend/src/services/api.js`](../../frontend/src/services/api.js) | The browser posts `{ message }` to `${VITE_API_URL}/api/v1/chat`, defaulting to `http://localhost:8000`. |
| [`backend/rag/generation/rag_service.py`](../../backend/rag/generation/rag_service.py) | `RAGService.generate_answer` embeds the message, retrieves up to `top_k` Chroma results, builds a prompt, calls the configured external model, and formats citations. |
| [`backend/rag/embedding/embedder.py`](../../backend/rag/embedding/embedder.py) | `VectorEmbedder` lazily loads `BAAI/bge-m3` and has a deterministic fallback when sentence-transformers is unavailable. |
| [`backend/rag/retrieval/vector_store.py`](../../backend/rag/retrieval/vector_store.py) | `ChromaVectorStore` creates or opens persistent local Chroma collections and exposes add/search/count operations. |
| [`backend/rag/indexing.py`](../../backend/rag/indexing.py) | Offline indexing loads travel data, chunks documents, embeds text, and upserts baseline and parent-child collections. |
| [`backend/app/config.py`](../../backend/app/config.py) | Backend settings define `API_V1_STR`, `GITHUB_TOKEN`, `LLM_MODEL`, and an OpenAI-compatible model endpoint URL. |
| [`docker-compose.yml`](../../docker-compose.yml) | Local Compose defines backend and frontend services only, with mounted `backend/`, `frontend/`, `data/`, and Hugging Face cache paths. |
| [Development Guide](../../DEVELOPMENT.md) | Stage A Docker startup and `/health` pass in an escalated local shell; frontend lint and tests still fail for recorded tooling reasons. |

Trace evidence: `chat_endpoint` calls `get_rag_service`,
`RAGService.generate_answer`, `ChatResponse`, and string conversion.
`generate_answer` calls `VectorEmbedder.embed_query`,
`ChromaVectorStore.search_similar`, and `_get_llm_client`. The current bounded
online path has no implemented memory read, memory write, identity lookup,
trip workspace lookup, evaluation trace write, or planner module.

## Context

Travel Agent is currently an early RAG prototype. It can start locally and
serve `/health`; the real chat path depends on an external model credential,
network access, embedding model availability, and useful Chroma data. The code
already contains enough shape to identify an online chat module and offline RAG
indexing module, but not enough product or data structure to support durable
trip planning.

The repository owner wants the eventual system to become an AI travel agent
with trip planning, project-like trip workspaces, long-term and short-term
memory, and measurable quality improvement. Package 3 turns that direction into
reviewable architecture documentation before implementation begins.

## Users

1. **Traveler:** wants continuity across planning sessions, remembered
   preferences, and an editable trip plan.
2. **Repository owner:** wants a senior-engineering path from prototype to
   evaluated product, with explicit approval gates.
3. **Coding agent:** needs module seams, dependency direction, and data
   contracts before modifying code.
4. **Evaluator:** needs traceable artifacts that explain why an answer used or
   ignored a memory or retrieval result.
5. **Contributor:** needs to distinguish current behavior, target architecture,
   and implementation-ready decisions.

## Problem Statement

The current prototype has no durable product container for a trip and no
implemented memory system. The chat contract is stateless from the product
perspective: one message enters, retrieved Chroma context is added, and one
reply returns. That is not enough to support multi-session planning,
preference-aware recommendations, itinerary evolution, or measurable learning
from user corrections.

Without Package 3, future implementation work would likely mix identity, trip
state, memory extraction, retrieval, prompting, and evaluation inside the
existing RAG service. That would create shallow modules, unclear ownership, hard
testing, and low confidence in quality improvements.

## Goals

1. Preserve a precise current-state baseline for the implemented RAG prototype.
2. Define the target architecture for trip workspaces and layered memory.
3. Define the target data model needed to support user, trip, conversation,
   message, memory, retrieval, planner, and evaluation records.
4. Identify module seams and dependency direction before code changes.
5. Separate product memory from travel knowledge retrieval.
6. Define how memory read/write quality will be evaluated later.
7. Identify durable decisions that must become ADRs after approval.
8. Keep Package 3 documentation implementation bounded and reviewable.

## Non-goals

1. Package 3 does not implement memory, trip workspaces, authentication, user
   accounts, storage adapters, database migrations, or planner tools.
2. It does not repair RAG quality, frontend lint, frontend tests, CI masking, or
   local setup gaps.
3. It does not create evaluation protocols owned by Package 5, but it may name
   architecture-level evaluation surfaces and metrics.
4. It does not choose a final production vendor for database, vector store,
   observability, authentication, or model provider.
5. It does not create ADR files directly; ADRs are created after architecture
   approval and plan approval.
6. It does not change root `ARCHITECTURE.md` except through a later approved
   Package 3 implementation plan if routing updates are needed.
7. It does not stage, commit, push, open a PR, merge, or release.

## Assumptions

1. Trip workspace is the primary product container for planning one trip.
2. A user can own multiple trip workspaces.
3. A trip workspace can contain multiple conversations, itinerary versions,
   decisions, constraints, and memories.
4. Memory must be scoped by user and trip before it is used for personalization.
5. Memory writes require a policy that classifies what is safe and valuable to
   remember.
6. Retrieved travel knowledge is untrusted content and must remain separate
   from instruction hierarchy and durable user memory.
7. Evaluation traces must be designed early enough that future improvements can
   be measured.
8. Current source remains the executable baseline until a separately approved
   implementation changes it.

If any assumption is rejected, the Package 3 design returns to review before an
implementation plan is prepared.

## Selected Approach

Use a workspace-first layered-memory architecture:

1. **Trip workspace as product container:** all planning state, conversations,
   itinerary drafts, decisions, constraints, and trip-scoped memories attach to
   one workspace.
2. **Layered memory:** working context, conversation summary, trip state,
   user long-term profile, episodic memories, and retrieval knowledge are
   separate layers with explicit read/write rules.
3. **Small interfaces at module seams:** chat orchestration calls memory,
   retrieval, planning, and evaluation modules through explicit interfaces
   rather than embedding their implementation inside one RAG service.
4. **Evidence-bearing context assembly:** every memory or retrieval item used in
   an answer carries scope, provenance, confidence, recency, and source type.
5. **Evaluation-first rollout:** future implementation must prove memory
   extraction precision, memory retrieval relevance, personalization utility,
   groundedness, privacy behavior, and trip-plan quality before claiming
   improvement.

This approach is selected because it gives the repository owner the ChatGPT-like
project organization they want while keeping memory testable and auditable.

## Alternatives Considered

### Alternative A: Keep a stateless RAG chat and improve retrieval first

This minimizes product and data-model changes. It is a reasonable short-term
RAG repair path, but it does not solve multi-session planning, remembered
preferences, trip decisions, or personalized continuity. It is rejected as the
Package 3 target architecture, while still allowed as a bounded RAG quality
workstream later.

### Alternative B: Add memory directly inside the existing RAG service

This appears fast because `RAGService.generate_answer` already assembles
context and calls the model. It would make memory, retrieval, prompting, and
model calls share one shallow interface and would make testing difficult. It is
rejected because memory policy and evaluation need their own module seams.

### Alternative C: Workspace-first layered memory

This adds more upfront design work but creates durable product structure,
clearer data ownership, and better evaluation surfaces. It is selected for
Package 3.

## Components and Dependency Direction

The target architecture uses these modules and interfaces:

| Module | Interface responsibility | Depends on | Must not depend on |
| --- | --- | --- | --- |
| Client Experience | Sends user intent, workspace selection, and conversation events | Backend application interface | Storage implementation, memory internals, model-provider internals |
| Backend Application | Authenticates request context later, validates contracts, and calls orchestration | Orchestration interface | Vector-store implementation details |
| Conversation Orchestrator | Coordinates memory read, knowledge retrieval, planning, generation, and evaluation trace | Memory, retrieval, planner, generation, evaluation interfaces | Concrete storage vendors hidden behind adapters |
| Workspace Module | Owns trip workspace lifecycle, itinerary state, constraints, decisions, and membership | Workspace repository interface | Generation prompt implementation |
| Memory Module | Owns memory extraction, consolidation, retrieval, confidence, retention, and deletion policy | Memory repository and embedding interface | UI components or route internals |
| Knowledge Retrieval Module | Owns travel-document retrieval and citation metadata | Vector-store adapter and embedding interface | User profile storage |
| Planner Module | Owns itinerary drafts, plan operations, alternatives, and decision state | Workspace and policy interfaces | Raw model-provider client |
| Generation Module | Owns prompt assembly and model-provider calls | Context bundle and model-provider adapter | Persistent storage writes |
| Evaluation and Trace Module | Owns trace capture, offline datasets, metric inputs, and quality gates | Event and trace repository interface | Product UI state |
| Storage Adapters | Persist relational, vector, blob, and trace data behind interfaces | External storage systems | Business orchestration policy |

Dependency direction flows inward from routes and UI toward orchestration, then
through small interfaces to specialized modules. Storage and model providers are
adapters at seams, not direct dependencies of product logic.

## Target Memory Layers

| Layer | Scope | Examples | Lifetime | Evaluation focus |
| --- | --- | --- | --- | --- |
| Working context | One model turn or bounded context window | Current user message, active itinerary slice, selected memory bundle | Minutes | Correct inclusion and token discipline |
| Conversation summary | One conversation | Open questions, recent decisions, unresolved constraints | Days to trip lifetime | Summary faithfulness and update accuracy |
| Trip state | One trip workspace | Destination shortlist, dates, budget, traveler count, itinerary versions, booked items | Trip lifetime plus retention policy | Plan consistency and conflict detection |
| User profile memory | One user across trips | Stable preferences, accessibility needs, dietary patterns, pace, hotel style | Until edited or deleted | Precision, usefulness, and privacy safety |
| Episodic memory | One user or trip event | "User rejected Da Nang for this winter trip because of rain concern" | Policy-defined | Retrieval relevance and decay behavior |
| Travel knowledge | Global or tenant-independent corpus | Destination facts, activities, travel guide chunks, citations | Dataset lifecycle | Retrieval relevance and groundedness |
| Evaluation trace | Request, run, or experiment | Inputs, retrieved items, memory items, answer, judge scores, failures | Evaluation retention policy | Reproducibility and learning signal quality |

## User and System Flows

### Current flow to preserve as baseline

1. Browser sends one message to the backend.
2. Backend validates the message and calls the process-global RAG service.
3. RAG embeds the query, searches Chroma, builds context, calls the model, and
   returns reply, model, and citations.
4. No user, trip, memory, or evaluation state is written by the bounded chat
   route.

### Target trip workspace flow

1. User creates or opens a trip workspace.
2. User chats inside the workspace.
3. Orchestrator loads workspace state, relevant memories, and relevant travel
   knowledge.
4. Planner proposes or updates itinerary state.
5. Generation produces a reply with visible citations and memory usage metadata
   suitable for tracing.
6. Memory policy classifies candidate memories from the interaction.
7. Safe and useful memory candidates are stored with provenance, scope,
   confidence, and retention metadata.
8. Evaluation trace records what was retrieved, used, rejected, and produced.

## Behavioral and Data Contracts

Package 3 implementation will document target contracts, not implement them.
The target model must include these concepts:

| Entity | Owns | Key relationships |
| --- | --- | --- |
| User | Stable identity and user-scoped preference memory | Many trip workspaces, conversations, memories |
| TripWorkspace | One planned trip and its durable planning state | One user or membership set, many conversations, itinerary versions, trip memories |
| Conversation | Ordered planning dialogue within a workspace | Many messages and summaries |
| Message | User, assistant, tool, or system-visible event content | Belongs to one conversation; may produce memory candidates and traces |
| ItineraryVersion | A structured snapshot of a proposed plan | Belongs to one workspace; can supersede earlier versions |
| TripDecision | Accepted, rejected, or pending planning decision | Belongs to one workspace and may reference messages or itinerary versions |
| MemoryRecord | Durable remembered fact, preference, constraint, or episode | Scoped to user, trip, conversation, or system; references provenance |
| MemoryCandidate | Proposed memory before policy acceptance | Derived from messages, planner events, or user edits |
| KnowledgeDocument | Source travel content | Split into chunks and retrieved with citations |
| RetrievalChunk | Searchable knowledge unit | Belongs to one document or parent chunk |
| ContextBundle | Per-turn selected memories, trip state, and retrieval items | Input to generation and evaluation |
| EvaluationTrace | Reproducible quality evidence for one run | References request, context bundle, response, scores, and failures |

Memory records must store at least scope, type, normalized content, provenance,
confidence, created time, updated time, retention state, and deletion state.
Exact physical storage is intentionally deferred to an ADR.

## Errors and Edge Cases

1. **No workspace selected:** target routes must either create an explicit
   default workspace or reject the request with a recoverable product error.
2. **Memory conflict:** newer explicit user edits outrank inferred memories;
   conflicting records must be visible to evaluation and review.
3. **Low-confidence memory candidate:** candidate is not promoted to durable
   memory unless policy allows it.
4. **Sensitive data detected:** candidate is rejected, redacted, or requires
   explicit user action according to the approved policy.
5. **Empty or stale Chroma data:** assistant can answer with limitations and
   evaluation marks the retrieval failure.
6. **Model-provider failure:** orchestrator returns a controlled error and
   records the failure in trace data when trace storage exists.
7. **Deletion request:** memory and trip records must support deletion or
   tombstoning semantics before production claims are made.

## Security and Privacy

The target architecture treats memory as sensitive user data. It must support:

1. Scope isolation between users and trip workspaces.
2. Explicit provenance for inferred memories.
3. User inspection, correction, and deletion of durable memories.
4. A policy for sensitive personal data, secrets, and credentials.
5. Separation between untrusted retrieved travel content and instruction
   hierarchy.
6. Avoiding raw secret values in logs, traces, docs, or fixtures.
7. Clear retention states for messages, memory, trip plans, and traces.

Package 3 does not establish a final security policy. Package 6 owns security
policy and runbooks, and later implementation must not claim production privacy
or tenant isolation without approved controls and verification.

## Observability and Operations

The target architecture must make these events observable enough for later
evaluation and debugging:

1. Workspace opened or created.
2. Message received.
3. Memory retrieval requested and completed.
4. Memory candidates proposed, accepted, rejected, edited, or deleted.
5. Travel knowledge retrieval requested and completed.
6. Context bundle assembled.
7. Model generation requested and completed.
8. Planner state changed.
9. Evaluation trace written.
10. Error, timeout, retry, or fallback path used.

Trace content must avoid leaking secrets and should support sampling or
redaction before any production deployment.

## Testing and Evaluation

Package 3 defines the architecture surfaces for evaluation. Package 5 will own
the detailed evaluation protocol and benchmark files.

Future implementation should be judged across these dimensions:

1. **Memory extraction precision:** accepted memories are true, useful, and
   scoped correctly.
2. **Memory extraction recall:** important stable preferences, trip constraints,
   and decisions are not missed.
3. **Memory retrieval relevance:** the right memories appear for the right trip
   or user query.
4. **Context assembly discipline:** selected memory and RAG items are useful,
   deduplicated, source-labeled, and token-bounded.
5. **Answer groundedness:** factual claims are supported by retrieved knowledge
   or clearly framed as reasoning or preference-based advice.
6. **Personalization utility:** answers improve when correct memories are
   available and degrade gracefully when they are absent.
7. **Trip-plan consistency:** itinerary updates preserve accepted constraints
   and surface conflicts.
8. **Privacy behavior:** sensitive candidates, deletion, redaction, and scope
   isolation pass targeted tests.

## Rollout and Migration

Package 3 documentation rollout is:

1. Approve this Level 3 design.
2. Prepare and approve a Package 3 implementation plan.
3. Create `docs/architecture/current-state.md`,
   `docs/architecture/target-state.md`, and
   `docs/architecture/data-model.md`.
4. Update only approved routing and traceability links.
5. Run deterministic Markdown, link, and evidence checks.
6. Stop for repository-owner change-set review.

Runtime rollout is intentionally not approved here. Later implementation should
use staged compatibility:

1. Preserve the existing `message`-only chat route until a new contract is
   approved.
2. Add workspace and memory routes behind explicit contracts.
3. Add storage adapters behind module interfaces.
4. Run shadow memory extraction before using memories in answers.
5. Promote memory retrieval into context assembly only after evaluation passes.
6. Promote planner state updates only after conflict and rollback behavior is
   tested.

## Rollback

Before Git delivery, Package 3 documentation rollback removes only the Package
3 spec, plan, architecture files, and approved routing/index edits created for
this package. It must not touch source code, tests, data, dependencies, Docker
state, Git history, or accepted Package 0-2 files.

After Git delivery, rollback requires a separately reviewed documentation
change. Runtime rollback is not applicable to Package 3 because no runtime
behavior is changed.

## Data Flow and Lifecycle

Target data lifecycle:

1. User message enters a conversation inside a trip workspace.
2. Conversation orchestrator requests relevant workspace state, user memories,
   trip memories, episodic memories, and travel knowledge.
3. Context bundle is assembled with provenance and scope.
4. Generation creates a response.
5. Planner may propose itinerary or decision changes.
6. Memory policy derives memory candidates from user messages, assistant
   confirmations, planner events, and explicit edits.
7. Accepted memories are written with scope, confidence, retention, and
   provenance.
8. Evaluation trace records request, selected context, response, decisions, and
   quality signals.
9. User edits or deletion requests update memory and trip records according to
   retention policy.

## Failure and Recovery

The target architecture must support graceful degradation:

1. If long-term memory is unavailable, continue with trip state, current
   conversation, and retrieval knowledge.
2. If travel knowledge retrieval is unavailable, answer with explicit
   limitations or ask for permission to proceed without citations.
3. If planner state write fails, do not pretend an itinerary was saved.
4. If evaluation trace write fails, user-facing chat may proceed, but the
   operation must be visible to operators later.
5. If memory conflict is detected, prefer explicit user correction and retain
   enough trace to evaluate the conflict.

## Capacity, Latency, and Cost

No production budgets are established by Package 3. The architecture documents
must define what future budgets need to measure:

1. Memory retrieval latency per turn.
2. Knowledge retrieval latency per turn.
3. Context assembly token budget.
4. Model call token and cost budget.
5. Memory extraction cost per message or conversation batch.
6. Evaluation trace storage growth.
7. Workspace and itinerary storage growth.

Later implementation plans must set concrete budgets before claiming production
readiness.

## Compatibility and Staged Migration

The existing `POST /api/v1/chat` request contract contains only `message`.
Package 3 must document that this remains the current contract. Any future
workspace-aware or memory-aware contract must be introduced through a separate
approved spec and may coexist with the current route during migration.

Target compatibility constraints:

1. Existing Stage A health startup remains valid.
2. Existing RAG route remains the baseline until a new route or request schema
   is approved.
3. New memory and workspace records must be traceable to messages or explicit
   user edits.
4. Knowledge retrieval and user memory storage must stay logically separate.
5. Evaluation traces must be able to compare baseline RAG behavior against
   memory-aware behavior.

## Required ADRs

After architecture approval and before runtime implementation, prepare ADRs for:

1. Trip workspace as the primary product container.
2. Layered memory model and memory promotion policy.
3. Storage ownership for relational data, vector data, and trace data.
4. Context assembly and dependency direction between memory, RAG, planner, and
   generation modules.
5. Evaluation trace schema and quality gate ownership.

Additional ADRs may be required later for authentication, authorization,
deployment topology, model-provider adapters, and production observability.

## Acceptance Criteria

Package 3 implementation is acceptable only when:

1. `docs/architecture/current-state.md`,
   `docs/architecture/target-state.md`, and
   `docs/architecture/data-model.md` exist after an approved implementation
   plan.
2. Current-state documentation cites reviewable source and configuration
   evidence and does not overstate implemented behavior.
3. Target-state documentation presents trip workspaces and layered memory as
   proposed architecture, not current behavior.
4. Data-model documentation covers user, trip workspace, conversation, message,
   itinerary, memory, retrieval, and evaluation trace concepts.
5. Memory layers have explicit scope, lifetime, provenance, privacy, and
   evaluation considerations.
6. Module seams and dependency direction are clear enough for a future
   implementation plan.
7. Required ADRs are listed and no runtime implementation is implied before
   those approvals.
8. All repository-relative links resolve.
9. Markdown checks pass with no unresolved drafting markers.
10. The change set stays within Package 3 documentation scope.
11. The repository owner grants architecture approval before an implementation
    plan is prepared.
12. The repository owner accepts the exact Package 3 change set before any Git
    delivery action.

## Verification

The Package 3 implementation plan must include:

1. Codebase Memory Verify-tier checks for every source path cited by
   current-state architecture.
2. Direct source reads for every material claim about implemented behavior.
3. Link resolution for every repository-relative link.
4. Markdown trailing whitespace, drafting marker, heading, and fence checks.
5. Unsupported-claim scans for production readiness, security, privacy,
   authentication, memory implementation, trip workspace implementation, test
   support, CI support, and SLO support.
6. A final scope review using `git status --short --untracked-files=all` and
   direct reads of untracked files.

## Approval Record

Version 0.1 received architecture approval from the repository owner on
2026-08-31 via the conversation phrase `architecture approval`. Approval
authorizes preparation of the Package 3 implementation plan only. It does not
authorize implementation, ADR creation, runtime changes, source changes,
dependency changes, data migration, or Git delivery.
