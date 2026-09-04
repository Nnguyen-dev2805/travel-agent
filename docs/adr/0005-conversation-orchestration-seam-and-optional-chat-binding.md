# ADR 0005: Conversation Orchestration Seam and Optional Chat Conversation Binding

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-04 |
| Decision owners | Repository owner |
| Scope | Coordination ownership for one chat turn, module dependency direction between product state and RAG execution, chat request and response compatibility, and write authority over assistant turns |
| Governing spec | [Conversation Persistence Design](../specs/2026-09-04-conversation-persistence-design.md), version 0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

Until R4 a chat turn has exactly one job. `backend/app/api/chat.py:18` validates
the request, resolves a process-global `RAGService`, and calls `generate_answer`.
The target architecture records this state plainly: the `Conversation
Orchestrator` row lists its current baseline as "Current chat route calls RAG
directly".

R4 gives a chat turn a second job. When a request is bound to a conversation, the
turn must persist the user message, generate an answer, and persist the assistant
message, while reporting truthfully whether each write succeeded. That is
coordination between two independent failure domains, and coordination needs an
owner.

Three candidate owners exist, and two of them break an established boundary. The
route handler is excluded by R3 Goals item 8, which requires that normalization,
validation, identity, time, and storage access live behind a module rather than in
a route. `RAGService` is excluded because it lives in `backend/rag/`, and giving
it knowledge of conversation storage is the same coupling that ADR 0002 rule 4
forbids between RAG and workspace modules.

The RAG module's own shape makes the third option cheap. Commit `85ee61c`
decomposed generation into `KnowledgeRetriever`, `ContextAssembler`
(`backend/rag/generation/context.py:23`), and `LLMGenerator`
(`backend/rag/generation/llm.py:54`), leaving `RAGService.generate_answer` at
`backend/rag/generation/rag_service.py:41` as a 35-line facade. A coordinator can
wrap that facade without reaching inside it.

There is a second, independent decision bundled here because it shares the same
boundary. Evaluation must stay independent of product state:
`backend/rag/evaluation/runtime.py` consumes the three RAG stages directly rather
than the facade, and ADR 0001 established a one-way seam in which evaluation
consumes runtime contracts and never the reverse. Whatever owns conversation
coordination must not become something the evaluation harness can reach.

Finally, the chat contract itself is at stake. R3 froze the request at `message`
only and the response at `reply`, `model`, and `citations`. R4 needs conversation
binding without breaking a client that knows nothing about conversations, and the
current browser client is one such client because frontend work is explicitly out
of R4 scope.

## Decision

Introduce a dedicated orchestration module that owns coordination for one chat
turn, and bind chat to a conversation through an optional, additive contract
change.

Coordination lives in `backend/orchestration/`. A `ConversationOrchestrator`
depends on the conversation service and on the RAG service facade. The chat route
delegates one turn to it and does nothing else beyond request validation and HTTP
mapping.

The decision has eight rules.

1. **Orchestration is a module, not a route concern.** The chat route validates
   its request and delegates. It contains no persistence call, no ordering logic,
   and no partial-failure policy.
2. **RAG stays unaware of product state.** `backend/rag`, including every
   generation, retrieval, and evaluation module, must not import
   `backend.conversations` or `backend.orchestration`. The dependency runs one
   way: orchestration depends on RAG.
3. **Evaluation stays independent.** The R2 evaluation harness and its tests must
   not import conversation or orchestration modules. Evaluation measures RAG
   quality and must not acquire a product-state dependency, consistent with the
   one-way seam in ADR 0001.
4. **Conversation state depends on workspace state, never the reverse.**
   `backend.conversations` may depend on the workspace repository interface to
   verify that a parent workspace exists. `backend.workspaces` must not depend on
   conversation modules.
5. **Chat binding is optional and additive.** `conversation_id` is an optional
   chat request field. A request without it behaves exactly as it does today, and
   its response contains exactly `reply`, `model`, and `citations` with no
   additional key. When the field is present the response gains one
   `conversation` object and nothing else changes.
6. **Persistence failure is reported, never hidden.** The user turn is persisted
   before any model call, so a storage failure costs no model request. If the
   assistant turn fails to persist, the reply is still returned and the response
   reports that the turn was not fully persisted. The system never implies that a
   message was stored when it was not.
7. **Assistant and tool turns are orchestrator-only.** The public message append
   route accepts only `user` and `system_event` roles. `assistant` and `tool`
   turns are writable only through the orchestrator, so a public caller cannot
   forge an assistant turn.
8. **No orchestration responsibility beyond R4 scope.** The orchestrator
   coordinates conversation persistence and generation only. Memory reads, memory
   writes, planner operations, and evaluation trace writes are named by the target
   architecture but are out of scope until their own approved designs exist.

This ADR does not prescribe class names beyond the module boundary, does not
choose a dependency-injection mechanism, and does not decide whether the
orchestrator later becomes the home for memory or planner coordination. Those
remain open.

## Alternatives

### Alternative A: Persist inside the chat route handler

The route could call the conversation service directly around its existing RAG
call.

This is the smallest diff and needs no new module. It puts coordination policy,
including write ordering and partial-failure reporting, inside an HTTP handler,
which R3 Goals item 8 excludes. It also concentrates the logic that later
milestones must extend for memory reads and trace writes in the place least
suited to hold it, guaranteeing a refactor under later delivery pressure.
Rejected.

### Alternative B: Persist inside `RAGService`

`RAGService` already sequences retrieval, context assembly, and generation, so it
could also persist the turn.

This reuses an existing coordinator, but `RAGService` lives in `backend/rag/`.
Giving it a conversation dependency is the coupling ADR 0002 rule 4 forbids for
workspaces, and it would place a storage dependency inside a module that
`backend/rag/evaluation/runtime.py` sits downstream of, threatening the
evaluation independence ADR 0001 established. Rejected.

### Alternative C: Put orchestration inside `backend/conversations/`

The conversation module could own the coordinated turn, since conversations are
what gets written.

This avoids a new module. It inverts the dependency the design needs: the
conversation storage module would have to import `backend.rag`, which makes the
product-state module depend on generation and drags RAG into the import graph of
every conversation test. Rejected as the wrong direction.

### Alternative D: A dedicated `backend/orchestration/` module

A new module depends on both the conversation module and the RAG facade, and the
chat route delegates to it.

This is the layer the target architecture already names and whose absence it
already records. `RAGService` is a thin facade after `85ee61c`, so wrapping it
costs little. The price is one more module and one more seam to review. Selected.

### Alternative E: Require `conversation_id` on every chat request

Chat could make the field mandatory, which is simpler to reason about than an
optional binding and removes a branch from the orchestrator.

This breaks the chat contract R3 froze, requires a superseding ADR, and breaks
the current browser client immediately even though frontend work is out of R4
scope. An optional field delivers the same provenance capability while keeping
existing callers byte-for-byte compatible. Rejected.

### Alternative F: Allow assistant turns through the public append route

The public route could accept any role, letting a test or tool write a full
transcript directly.

This is convenient for fixtures and would remove a validation rule. It also lets
any caller fabricate assistant content that later memory extraction would treat
as model output, which is a provenance integrity problem rather than a
convenience question. Tests can obtain assistant turns through the orchestrator
path, which is the path being tested anyway. Rejected.

## Consequences

### Positive

1. The chat route stays thin, consistent with the boundary R3 established.
2. RAG and the evaluation harness keep their independence from product state, so
   R1 and R2 evidence remains valid without qualification.
3. The coordination layer named by the target architecture becomes real, giving
   `R5` memory reads, `R6` retrieval gating, and `R7` planner operations a
   defined home instead of an implicit one.
4. Existing chat clients, including the current browser client, observe no change
   at all.
5. Partial persistence failure is visible to the caller, so no component has to
   assume a write succeeded.
6. Assistant turn authorship is structurally constrained, which protects the
   provenance that memory evaluation depends on.

### Negative

1. One more module and one more seam to understand, review, and test.
2. The chat response has two shapes rather than one, so response handling and
   tests must cover both the bound and unbound paths.
3. Coordination policy such as write ordering and partial-failure semantics now
   lives outside the route, which means reading a chat turn end to end requires
   following one more indirection.
4. The orchestrator is a natural magnet for future responsibility and could
   accumulate memory, planner, and trace logic without a deliberate boundary
   decision for each.
5. Restricting assistant writes to the orchestrator makes some test fixtures
   slightly less direct to construct.
6. The optional field creates a path that most callers will not exercise, so the
   unbound path needs explicit regression coverage to stay honest.

## Migration

R4 is the first milestone with any orchestration layer, so there is nothing to
migrate. `GET /health`, every R3 workspace route, RAG behavior, and the R2
evaluation harness remain unchanged.

Chat compatibility is preserved by construction rather than by convention: the
frozen fields keep their exact names, types, and values, and the new
`conversation` object is absent rather than null when the caller does not opt in.
A regression test asserting the exact response key set on the unbound path is the
evidence that this holds.

Rollback removes the orchestration module, the conversation module, their routes,
and the optional chat field, which restores the R3 chat contract exactly.
Evidence is the unbound chat compatibility test plus the boundary checks proving
no residual dependency remains.

Future work that gives the orchestrator memory, planner, or trace
responsibilities requires its own approved design, and a change that makes
`conversation_id` mandatory or alters the frozen chat fields requires a
superseding ADR.

## Validation

The R4 implementation plan must provide fresh evidence that:

1. the chat route delegates one turn to the orchestrator and contains no
   persistence call, ordering logic, or partial-failure policy;
2. `backend/rag` and the evaluation modules and their tests import no
   conversation or orchestration module;
3. `backend/workspaces` imports no conversation module, while the conversation
   service does verify workspace existence through the workspace repository
   interface;
4. a chat request without `conversation_id` returns exactly `reply`, `model`, and
   `citations`, with no `conversation` key present;
5. a chat request with a valid `conversation_id` persists the user turn before
   generation and the assistant turn after it, and reports success truthfully;
6. a chat request with an unknown `conversation_id` returns `404` before any model
   call, and a failed user-turn write returns `500` before any model call;
7. a failed assistant-turn write still returns the reply and reports that the turn
   was not fully persisted;
8. the public message append route rejects `assistant` and `tool` roles, and the
   orchestrator path does write them;
9. `GET /health`, every R3 workspace route, and the R2 evaluation harness remain
   contract-compatible.

## References

1. [Conversation Persistence Design](../specs/2026-09-04-conversation-persistence-design.md), version 0.1 (Approved).
2. [ADR 0004: Shared Local Application Store and Per-module Schema Registry](./0004-shared-local-application-store-and-per-module-schema-registry.md).
3. [ADR 0001: Separate Online RAG Execution from Config-driven Evaluation](./0001-separate-online-rag-execution-from-config-driven-evaluation.md).
4. [ADR 0002: Trip Workspace as Primary Product Container](./0002-trip-workspace-as-primary-product-container.md).
5. [Target-state Architecture](../architecture/target-state.md).
6. [Memory Evaluation](../evaluation/memory-evaluation.md).
7. [Security Policy](../../SECURITY.md).
