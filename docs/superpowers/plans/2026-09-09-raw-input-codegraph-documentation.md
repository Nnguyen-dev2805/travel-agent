# Raw Input CodeGraph Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create one source-grounded Markdown document that explains every raw-input entry point in the `standalone-conversation` worktree and gives two Mermaid diagrams: the complete input-to-code map and the detailed user-chat input-to-output lifecycle.

**Architecture:** The document will treat `backend/app/main.py` as the HTTP routing boundary, then trace each mounted route into its request schema, route handler, service/orchestrator, persistence or external provider, response schema, and controlled error paths. The chat diagram will be detailed separately because `/api/v1/chat` has bound/unbound, memory-gated, persistence-degraded, and outbox branches; memory controls, planner, workspace, conversation, shadow extraction, and evaluation will remain explicit sibling flows rather than being incorrectly presented as part of the synchronous chat response.

**Tech Stack:** Markdown, GitHub Mermaid (`flowchart`, `sequenceDiagram`), FastAPI/Pydantic route contracts, Python source, CodeGraph call-path evidence.

**Spec:** User-approved in conversation on 2026-09-09; requested output is a detailed Markdown file in the `standalone-conversation` worktree.

## Global Constraints

- Source of truth for behavior is the current `standalone-conversation` worktree, not the repository-root branch.
- Use CodeGraph for structural discovery, then direct source reads for branch-specific or unindexed code.
- Do not modify existing dirty files; add only the documentation artifact and this local plan.
- Do not invent call paths, outputs, endpoint behavior, streaming, or model use that source does not show.
- Distinguish synchronous HTTP output from asynchronous outbox-worker output.
- Include file paths, symbols, and line ranges for material claims.
- Mermaid must be valid GitHub-flavored fenced Mermaid and use high-contrast styles with explicit text colors.

---

### Task 1: Build the source evidence inventory

**Files:**
- Read only: `backend/app/main.py`, `backend/app/api/chat.py`, `backend/orchestration/conversation_orchestrator.py`, `backend/rag/generation/rag_service.py`, `backend/rag/retrieval/service.py`, `backend/rag/generation/context.py`, `backend/rag/generation/llm.py`
- Read only: mounted route files under `backend/app/api/`
- Read only: request/response schemas under `backend/app/schemas/`
- Read only: memory write-pipeline service, worker, model adapter, policy, resolver, UoW, evaluation runner/CLI

**Interfaces:**
- Consumes: CodeGraph results and current source from the linked worktree.
- Produces: A bounded inventory of entry points, exact symbols, source paths, line ranges, output types, and error branches used by Task 2.

- [ ] **Step 1: Reconcile the mounted route inventory**

  Confirm `app.include_router` registrations in `backend/app/main.py` and list every route method/path in `backend/app/api/*.py`, including routes with no body but path/query input.

- [ ] **Step 2: Reconcile branch-specific contracts**

  Confirm the standalone conversation fields (`owner_user_id`, optional `workspace_id`) and the chat outbox flag from the actual worktree source before documenting any conversation identity or background extraction claim.

- [ ] **Step 3: Record evidence boundaries**

  Mark any flow that CodeGraph cannot resolve in the worktree as `direct-source verified`, and exclude unsupported claims such as frontend transport behavior or streaming unless the source shows them.

### Task 2: Write the two-diagram Markdown document

**Files:**
- Create: `docs/architecture/raw-input-codegraph-flow.md`

**Interfaces:**
- Consumes: Task 1 evidence inventory.
- Produces: One standalone Markdown document with two Mermaid diagrams and detailed case-by-case explanations.

- [ ] **Step 1: Add scope and evidence rules**

  State the worktree path, branch, analysis date, CodeGraph/source method, and the distinction between user raw input, structured HTTP input, path/query input, and internal transcript input.

- [ ] **Step 2: Add Diagram 1 for all raw-input entry paths**

  Use a Mermaid `flowchart TD` beginning at the FastAPI middleware/body-limit/validation boundary, branching to chat, workspaces, conversations, memory shadow routes, memory controls, planner, and evaluation CLI/worker inputs. Every terminal output must name the response or artifact type and its file/symbol.

- [ ] **Step 3: Add Diagram 2 for user chat input to output**

  Use a Mermaid `sequenceDiagram` covering request schema validation, empty-message rejection, `chat_endpoint`, unbound and bound turns, owner/retention checks, user-message persistence, optional outbox creation, memory disabled/none-selected/selected/skipped cases, RAG retrieval/context/LLM, assistant persistence success/failure, response serialization, and HTTP errors.

- [ ] **Step 4: Explain every chat case**

  Add tables and prose for unbound, bound, authenticated owner match, missing/foreign conversation, deleted workspace/conversation, user-write failure, generation failure, memory unavailable, no memory selected, selected memory, assistant-write failure, and successful persistence. Identify exactly which branches do and do not call the model.

- [ ] **Step 5: Explain sibling raw-input cases**

  Document workspace creation/deletion, conversation CRUD/message history, manual shadow extraction/listing/promotion, planner writes/lifecycle operations, direct memory command parsing and outcomes, preview confirmation, outbox worker extraction, and evaluation CLI dataset/example input. Keep read-only routes labeled as input through path/query rather than body.

- [ ] **Step 6: Add source index and limitations**

  Include a route-to-symbol table, a file/symbol evidence index, and explicit limitations: CodeGraph index branch mismatch, no frontend network call claimed without source proof, and no undocumented streaming path.

### Task 3: Validate the artifact against source and Mermaid

**Files:**
- Read: `docs/architecture/raw-input-codegraph-flow.md`
- Read only: all source files cited by the document

**Interfaces:**
- Consumes: Task 2 Markdown.
- Produces: A verified document with no unsupported nodes or edges.

- [ ] **Step 1: Extract Mermaid blocks**

  Run the repository Mermaid extraction/validation utility if available; otherwise use a local Mermaid CLI or a syntax-only check and report the exact command/result.

- [ ] **Step 2: Recheck citations and route coverage**

  Compare every diagram node and edge against the cited source symbols and compare the route table against `main.py` router registration plus route decorators.

- [ ] **Step 3: Inspect final worktree status**

  Run `git status --short --untracked-files=all`, inspect the new document directly, and confirm no pre-existing dirty file was changed.

- [ ] **Step 4: Report the handoff**

  Report the new file, verification commands/results, source-grounding limitations, existing dirty files left untouched, and that no Git delivery was performed.
