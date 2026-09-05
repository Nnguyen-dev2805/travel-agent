# ADR 0007: Feature-gated Memory Retrieval and Context Boundary

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-05 |
| Decision owners | Repository owner |
| Scope | R6 memory promotion, memory retrieval, answer-time context composition, feature gating, evaluation traceability, and dependency direction between memory, orchestration, and RAG |
| Governing spec | [Memory Retrieval Design](../specs/2026-09-04-memory-retrieval-design.md), version 0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

R5 is the shadow memory extraction milestone. It creates memory candidates and
evaluation evidence, but ADR 0006 explicitly forbids candidates from influencing
answers. R6 is the first milestone where measured memory may be selected at
answer time, so the boundary between memory storage, retrieval, orchestration,
and RAG must be explicit before implementation starts.

The current R4 answer path is:

```text
chat route -> ConversationOrchestrator -> RAGService -> ContextAssembler -> LLMGenerator
```

RAG currently owns travel-knowledge retrieval, travel evidence formatting, and
citations. Memory is user/product state, not travel corpus knowledge. If memory
retrieval is added directly inside RAG, RAG evaluation would begin depending on
personal state and ADR 0001's separation between online RAG behavior and
config-driven evaluation would weaken.

The memory evaluation protocol also requires that answer-time memory selection
be auditable: selected memory IDs, selection reasons, scope checks, deletion
state, and A/B comparison must be visible without turning memory into ordinary
citations.

## Decision

R6 introduces answer-eligible `MemoryRecord` rows and feature-gated memory
retrieval under `backend/memory/`. The answer-eligible record store registers as
a new local schema module named `memory_records` at version 1, rather than
changing R5's `memory` module version. Memory retrieval is called only by
`ConversationOrchestrator`, and only when the R6 feature gate is enabled for a
bound conversation. `backend/rag` remains unaware of `backend.memory`.

The decision has ten rules.

1. **Promoted records are separate from candidates.** R5 `MemoryCandidate`
   records remain shadow evidence. R6 creates `MemoryRecord` records only from
   eligible, accepted candidates after policy validation. R6 does not change R5
   extraction or policy behavior to widen what becomes promotable; the governing
   spec records which allow-list reasons currently have no R5 producer and
   remain forward-compatible entries.
2. **Feature gate defaults off.** `MEMORY_RETRIEVAL_ENABLED` defaults to false.
   When disabled, bound and unbound chat behavior remains R4 behavior.
3. **Bound conversations only.** R6 memory retrieval requires a
   `conversation_id` that resolves to a workspace. Unbound chat cannot retrieve
   memory.
4. **Orchestration composes answer context.** `ConversationOrchestrator` owns the
   answer-time composition of travel RAG context plus selected memory context.
   RAG does not call memory services. R6 may add a narrow, injectable
   `RAGService` seam that returns travel retrieval context before generation so
   orchestration can compose memory without constructing vector-store clients.
5. **Travel citations stay travel citations.** Memory records are not source
   citations. Selected memory IDs and selection reasons are exposed through
   memory trace fields and evaluation artifacts, not citation objects.
6. **Scope and lifecycle fail closed.** A memory must match user, workspace, or
   conversation scope and must be active. Deleted, tombstoned, archived,
   expired, superseded, or deletion-requested records are ineligible.
7. **Sensitive material is not promoted.** R6 does not promote candidates with
   `sensitive`, `secret`, or `unsafe` labels. Secret-like controlled fixtures
   must produce zero promoted records and zero retrievals.
8. **No vector memory store in R6.** R6 uses deterministic lexical retrieval and
   policy ranking. Chroma remains travel knowledge only.
9. **Corrections outrank older inferences.** Explicit corrections and newer
   direct statements suppress older inferred records within the same scope.
   Suppression is resolved once at promotion time from scope identity and record
   age only, never from text similarity or model inference, and is stored as
   record status so retrieval reads it instead of re-deriving it. When the
   target is ambiguous, every candidate target is suppressed, because losing
   retrieval recall is recoverable and letting an older inference outrank a
   newer correction is a hard-gate failure.
10. **Evaluation controls rollout.** R6 may be delivered with the feature gate
    off. Turning it on by default requires memory evaluation evidence that
    satisfies the approved gates.

## Alternatives

### Alternative A: Add memory retrieval inside `backend/rag`

This would be direct because the generator already consumes RAG context.
However, it would make travel retrieval depend on product memory and would make
RAG evaluation consume user state. Rejected.

### Alternative B: Use Chroma for memory records

Semantic search is attractive for memory. R6 does not yet have deletion,
tombstone, tenant, or production privacy semantics, so vector memory would add a
harder-to-audit storage surface before the lifecycle is mature. Rejected.

### Alternative C: Expose a public per-request memory toggle

A request field such as `memory_enabled` would help manual testing, but it lets
callers change privacy-sensitive answer behavior independently of server-side
configuration. R6 uses configuration and evaluation overrides instead. Rejected
for the public API in R6.

### Alternative D: Orchestration-owned, feature-gated memory retrieval

The memory module owns promotion and retrieval policy. The orchestrator owns
combining selected memory with RAG context for a specific conversation turn.
RAG remains focused on travel knowledge. Selected.

## Consequences

### Positive

1. RAG and RAG evaluation remain independent from memory state.
2. Memory selection has one auditable policy owner before it affects answers.
3. The feature can be implemented, tested, and evaluated while disabled by
   default.
4. A/B reports can compare memory-disabled and memory-enabled runs without
   changing the public default behavior.
5. Future deletion and privacy work can target a dedicated memory lifecycle
   surface.

### Negative

1. R6 adds a second memory artifact type, so the candidate-versus-record
   distinction must remain clear in code and documentation.
2. Lexical retrieval is simpler and more auditable than semantic retrieval, but
   it may miss useful memories outside the fixture language.
3. The orchestrator becomes responsible for one more coordination step.
4. R6 cannot justify default-on personalization unless the evaluation report
   passes the approved memory gates.
5. Promotion coverage is narrower than the allow-list vocabulary. The delivered
   R5 extractor produces only preference, constraint, and correction candidates
   that reach `accepted`, so `profile_fact` and `decision` memory exist in R6
   only through seeded evaluation fixtures. Widening coverage means changing R5
   extraction under its own approved change.
6. Correction targeting is coarse. Without a link field from R5, an ambiguous
   correction suppresses every older active target in the same scope, which can
   suppress an unrelated record. A later milestone can narrow this only by
   adding explicit correction targets during extraction.

## Migration

R6 is additive to the local application database. It registers answer-eligible
memory record and retrieval trace tables as a separate `memory_records` schema
module at version 1. R5's `memory` schema module remains at version 1,
preserving ADR 0004's fail-closed version guarantee and avoiding a general
migration framework.

If R5 has not been delivered, R6 implementation stops. If an existing
`memory_records` module schema has an unexpected version, R6 fails closed and
returns a controlled infrastructure error.

Rollback disables `MEMORY_RETRIEVAL_ENABLED`, removes orchestration memory
composition, removes R6 routes or commands, and leaves promoted records as inert
local data. Because the feature gate defaults off, rollback must restore R4/R5
answer behavior without touching travel RAG collections.

## Validation

R6 validation must prove:

1. feature-gate-off chat responses preserve R4 behavior;
2. `backend/rag` and RAG evaluation do not import `backend.memory`, and
   `backend/memory` does not import `backend.rag` or `backend.orchestration`;
3. only active, in-scope, non-sensitive records can be selected;
4. deleted, tombstoned, archived, expired, superseded, and
   deletion-requested records are never selected;
5. selected memory IDs and reasons appear in traceable evaluation artifacts;
6. memory-enabled and memory-disabled evaluation runs can be compared;
7. hard memory safety gates have zero tolerated failures;
8. the full backend test suite passes with temporary databases.

## References

1. [Memory Retrieval Design](../specs/2026-09-04-memory-retrieval-design.md)
2. [Memory Evaluation Protocol](../evaluation/memory-evaluation.md)
3. [Shadow Memory Extraction Design](../specs/2026-09-04-shadow-memory-extraction-design.md)
4. [ADR 0006](./0006-shadow-memory-candidate-store-and-policy-boundary.md)
5. [ADR 0001](./0001-separate-online-rag-execution-from-config-driven-evaluation.md)
6. [ADR 0005](./0005-conversation-orchestration-seam-and-optional-chat-binding.md)
