# ADR 0006: Shadow Memory Candidate Store and Policy Boundary

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-09-04 |
| Decision owners | Repository owner |
| Scope | R5 memory candidate ownership, shadow extraction boundary, promotion policy boundary, storage adapter direction, privacy and evaluation evidence for memory candidates |
| Governing spec | [Shadow Memory Extraction Design](../specs/2026-09-04-shadow-memory-extraction-design.md), version 0.1 (Approved) |
| Superseded ADR | None |
| Superseded by | None |

## Context

R4 delivered durable conversations and messages under trip workspaces. That gives
R5 a stable source for memory provenance: every candidate can point to a
conversation message and inherit workspace scope from that conversation.

The roadmap deliberately puts R5 before R6. Memory candidates must be measured
before any remembered fact is used in answers, because the memory evaluation
protocol treats missing provenance, broken scope, deletion uncertainty, or
sensitive promotion as invalid or failing evidence.

R5 introduces the first memory-specific subsystem. That subsystem touches user
content, possible preferences, possible trip constraints, and artificial
secret-like fixtures. It therefore needs a durable decision about where memory
candidate extraction lives, where promotion policy is enforced, and what R5 is
not allowed to do.

## Decision

Create a dedicated `backend/memory/` module for R5 shadow memory extraction.
The module owns memory candidate contracts, extraction interfaces, promotion
policy, repository interfaces, and local SQLite persistence for candidate and
shadow-run evidence.

R5 stores `MemoryCandidate` and `MemoryExtractionRun` records in the existing
local application database through the shared schema registry introduced by
ADR 0004. R5 does not create durable `MemoryRecord` records that are eligible
for retrieval, does not inject memory into answer generation, and does not
modify RAG retrieval behavior.

R4 intentionally defaults message `trace_visibility` to `excluded`. R5 preserves
that default-deny privacy decision. Shadow extraction therefore runs only on
messages that were explicitly persisted with `trace_visibility = included` or on
reviewed synthetic fixtures created for memory evaluation.

The decision has ten rules.

1. **Memory has its own module.** `backend/memory/` owns extraction, policy,
   candidate state, memory evaluation serialization, and memory repository
   interfaces. Conversation, workspace, RAG, and route modules do not own memory
   policy.
2. **R5 is shadow-only.** R5 may extract, classify, persist, inspect, and report
   candidates. It must not retrieve memory into `ContextBundle`, change prompts,
   alter generated answers, or write durable answer-eligible `MemoryRecord`
   rows.
3. **Conversation provenance is mandatory.** Every candidate must reference an
   existing `message_id`, `conversation_id`, and `workspace_id`. Missing or
   mismatched provenance fails closed.
4. **Scope is explicit.** A candidate must carry a proposed scope from the
   governed vocabulary: `user`, `workspace`, `conversation`, or `none`.
   `none` means the extractor saw no durable memory to propose.
5. **Policy and extraction are separate.** Extraction proposes candidate facts.
   Policy decides candidate status and rejection reason. The extractor is not
   allowed to directly mark a candidate accepted.
6. **Accepted in R5 does not mean answer-eligible.** `accepted` means "accepted
   as a shadow candidate for evaluation", not "promoted into durable memory for
   retrieval." R6 must define promotion into answer-eligible memory separately.
7. **Sensitive data fails closed.** Secret-like, unsafe, or unsupported content
   must be rejected or marked for manual action. R5 reports redacted evidence
   and never logs raw content from message text, candidate text, or rationale.
8. **RAG remains independent.** `backend/rag`, including the R2 evaluation
   harness, must not import `backend.memory`. Memory evaluation code lives under
   `backend/memory/evaluation/`, so RAG evaluation does not consume memory
   state.
9. **R5 does not hook into chat orchestration.** Bound chat turns remain exactly
   R4 behavior. Automatic or chat-bound memory extraction requires a later
   approved design because it changes when user content becomes memory input.
10. **No production privacy claim.** R5 is a local development feature with
    unauthenticated scope labels inherited from R3/R4. It does not establish
    authentication, authorization, tenant isolation, legal compliance, or
    complete deletion semantics.

## Alternatives

### Alternative A: Put memory extraction inside `backend/conversations/`

The conversation module has the source messages and could extract candidates
when messages are appended.

This is convenient but gives the message store memory policy ownership. It also
forces future memory retrieval, conflict handling, and evaluation into a module
whose R4 contract is only conversation persistence. Rejected.

### Alternative B: Put memory extraction inside `backend/rag/`

RAG already prepares context and generation evidence, so it could also extract
remembered facts.

This breaks the established separation between travel knowledge retrieval and
user memory. It would also make RAG evaluation depend on product state, weakening
ADR 0001. Rejected.

### Alternative C: Store memory candidates only in evaluation JSON files

R5 could avoid database work and write candidate runs directly to
`data/evaluation`.

This is simple for benchmarking, but it gives runtime extraction no reviewable
repository boundary and cannot prove candidate identity, source message
uniqueness, or local inspection routes. It also diverges from R3/R4's local
adapter pattern. Rejected.

### Alternative D: Dedicated memory module with a shadow candidate store

`backend/memory/` owns memory contracts, policy, and candidate persistence.
Evaluation reports read from candidate runs, but the runtime answer path stays
unchanged.

This adds a new module and a new schema version, but it keeps each boundary
honest and lets R5 be evaluated before R6 uses memory in answers. Selected.

## Consequences

### Positive

1. Memory policy has one explicit owner before memory can influence answers.
2. R5 produces durable, inspectable candidate evidence for evaluation and review.
3. Conversation provenance from R4 becomes testable input rather than prose.
4. RAG and RAG evaluation remain independent from product memory state.
5. R6 can build retrieval on top of measured candidates instead of inventing
   extraction and retrieval at the same time.

### Negative

1. R5 adds a local memory schema even though no answer uses memory yet.
2. `accepted` candidate language can be confused with durable memory promotion,
   so the spec and plan must define the distinction repeatedly.
3. Shadow extraction adds runtime and evaluation surfaces that must redact
   content carefully.
4. A later R6 design may supersede parts of the candidate schema once real
   `MemoryRecord` retrieval is approved.
5. R5 will not extract from ordinary chat-bound messages unless those messages
   are explicitly persisted with `trace_visibility = included`; this limits early
   coverage but preserves R4's default-deny privacy boundary.

## Migration

R5 is additive. A database without memory tables initializes the `memory` module
schema through the shared schema registry. Existing workspace and conversation
records remain unchanged.

Rollback removes the memory routes, memory module imports, and memory schema
registration. Existing memory candidate rows become inert local development data
because no R4 or RAG path depends on them. R5 does not write to Chroma or to any
answer path, so rollback cannot change generated answers.

## Validation

R5 validation must prove:

1. memory candidates cannot be created without existing conversation provenance;
2. unsupported, ambiguous, transient, wrong-scope, and secret-like candidates are
   rejected or marked for manual action;
3. no memory candidate reaches RAG context assembly or generated answers;
4. memory reports contain redacted evidence and stable identifiers;
5. `backend/rag` and RAG evaluation import-boundary checks remain clean;
6. the complete backend test suite passes with temporary databases.

## References

1. [Shadow Memory Extraction Design](../specs/2026-09-04-shadow-memory-extraction-design.md)
2. [Memory Evaluation Protocol](../evaluation/memory-evaluation.md)
3. [Conversation Persistence Design](../specs/2026-09-04-conversation-persistence-design.md)
4. [ADR 0004](./0004-shared-local-application-store-and-per-module-schema-registry.md)
5. [ADR 0005](./0005-conversation-orchestration-seam-and-optional-chat-binding.md)
