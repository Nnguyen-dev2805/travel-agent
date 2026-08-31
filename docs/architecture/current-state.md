# Current-state Architecture

## Scope

This document records the implemented Travel Agent architecture at the current
repository state. It is an evidence-backed baseline for an early RAG prototype,
not a target design and not a production-readiness claim.

Use this document when a future package needs to compare proposed work against
what exists today. Use [Target-state Architecture](target-state.md) for the
approved direction and [Data Model](data-model.md) for the conceptual target
entities.

## Evidence Basis

Codebase Memory was checked at Verify tier for the source paths cited here.
The graph project was
`Users-tnhatnguyendev2805-Documents-Projects-travel-agent`; the refreshed
coverage generation was `2026-08-31T03:52:54Z`. The graph reported 713 nodes
and 1860 edges. Coverage for cited material paths returned
`no_recorded_issue` and `metadata_match`.

Coverage is a best-effort signal, not proof of semantic completeness. Exact
source and configuration files were also read directly. The index reported a
parse-partial range in `frontend/src/App.jsx` at line 76, but this document does
not rely on that file for material claims.

Material evidence paths:

| Path | Evidence used |
| --- | --- |
| [`../../backend/app/main.py`](../../backend/app/main.py) | FastAPI app setup, route mounting, CORS, startup RAG pre-warm behavior |
| [`../../backend/app/api/health.py`](../../backend/app/api/health.py) | `/health` response shape |
| [`../../backend/app/api/chat.py`](../../backend/app/api/chat.py) | Chat route validation, logging, process-global RAG service, `top_k=4` call |
| [`../../backend/app/schemas/chat.py`](../../backend/app/schemas/chat.py) | Current request and response schemas |
| [`../../frontend/src/services/api.js`](../../frontend/src/services/api.js) | Browser API origin and chat payload |
| [`../../backend/rag/generation/rag_service.py`](../../backend/rag/generation/rag_service.py) | RAG answer generation, prompt assembly, external model call |
| [`../../backend/rag/embedding/embedder.py`](../../backend/rag/embedding/embedder.py) | Embedding model, lazy load, deterministic fallback |
| [`../../backend/rag/retrieval/vector_store.py`](../../backend/rag/retrieval/vector_store.py) | Chroma persistence path, collection creation, add/search/count behavior |
| [`../../backend/rag/indexing.py`](../../backend/rag/indexing.py) | Offline indexing entry point and collections |
| [`../../backend/app/config.py`](../../backend/app/config.py) | Environment names, API prefix, model endpoint defaults |
| [`../../docker-compose.yml`](../../docker-compose.yml) | Local backend/frontend services, ports, bind mounts, env file, cache mount |
| [`../../backend/Dockerfile`](../../backend/Dockerfile) | Python 3.11 backend image and Uvicorn command |
| [`../../frontend/Dockerfile`](../../frontend/Dockerfile) | Node 18 frontend image and Vite command |
| [`../../frontend/package.json`](../../frontend/package.json) | Frontend development scripts and dependency names |
| [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml) | CI commands and masked test failures |
| [`../../.env.example`](../../.env.example) | Empty example environment file |

## Runtime Components

| Component | Implemented responsibility | Evidence |
| --- | --- | --- |
| React/Vite client | Sends one chat `message` to the backend and returns response data to the UI caller | `frontend/src/services/api.js`, `frontend/package.json` |
| FastAPI application | Creates the application, configures local CORS, mounts `/health`, and mounts chat routes under `/api/v1` | `backend/app/main.py` |
| Health route | Returns `status` and `service` metadata | `backend/app/api/health.py` |
| Chat route | Validates one stripped message, logs a prefix, calls process-global RAG, and returns typed response data | `backend/app/api/chat.py`, `backend/app/schemas/chat.py` |
| RAG generation service | Embeds the user message, retrieves Chroma context, builds the prompt, calls the configured external model endpoint, and formats citations | `backend/rag/generation/rag_service.py` |
| Vector embedder | Lazily loads `BAAI/bge-m3` through sentence-transformers when available, or returns deterministic 1024-dimensional fallback vectors | `backend/rag/embedding/embedder.py` |
| Chroma vector store | Creates or opens a persistent local Chroma collection, upserts baseline or parent-child chunks, searches by query embedding, and counts records | `backend/rag/retrieval/vector_store.py` |
| Offline indexing script | Loads travel datasets, chunks documents, embeds text, and upserts baseline and parent-child collections | `backend/rag/indexing.py` |
| Docker Compose stack | Defines local backend and frontend services only | `docker-compose.yml` |
| External model endpoint | Receives chat-completions calls through an OpenAI-compatible client configured by backend settings | `backend/app/config.py`, `backend/rag/generation/rag_service.py` |

## Online Chat Flow

```mermaid
sequenceDiagram
    participant Browser as React/Vite browser
    participant API as FastAPI /api/v1/chat
    participant RAG as RAGService
    participant Embedder as VectorEmbedder
    participant Chroma as Local Chroma
    participant Model as External model endpoint

    Browser->>API: POST { message }
    API->>API: strip message, reject empty value, log prefix
    API->>RAG: generate_answer(message, top_k=4)
    RAG->>Embedder: embed_query(message)
    Embedder-->>RAG: query vector
    RAG->>Chroma: search_similar(query_vector, top_k)
    Chroma-->>RAG: chunks, metadata, distances
    RAG->>Model: system prompt with retrieved context plus user message
    Model-->>RAG: generated answer
    RAG-->>API: reply, model, citations
    API-->>Browser: ChatResponse
```

The browser posts to `${VITE_API_URL}/api/v1/chat`; the default origin is
`http://localhost:8000`. The backend strips the incoming message, rejects empty
content, and calls `RAGService.generate_answer(user_message, top_k=4)`.

Codebase Memory trace evidence found `chat_endpoint` calling `get_rag_service`,
`RAGService.generate_answer`, and `ChatResponse`. It found `generate_answer`
calling `VectorEmbedder.embed_query`, `ChromaVectorStore.search_similar`, and
`_get_llm_client`.

## Current Request and Response Contracts

The current public chat request contains one required field:

```json
{
  "message": "Chao ban, Ha Noi co gi dep?"
}
```

The current response contains:

```json
{
  "reply": "assistant answer",
  "model": "gpt-4o-mini",
  "citations": [
    {
      "title": "source title",
      "url": "source URL"
    }
  ]
}
```

There is no implemented user identifier, trip workspace identifier,
conversation identifier, memory identifier, planner command, or evaluation run
identifier in this bounded request contract.

## RAG Module Shape

`RAGService` currently owns several responsibilities behind one method:

1. Normalize and validate user text.
2. Read the configured model name.
3. Embed the query through `VectorEmbedder`.
4. Retrieve similar chunks from `ChromaVectorStore`.
5. Build a context string and citation map.
6. Construct the Vietnamese system prompt.
7. Create an OpenAI-compatible client from `GITHUB_TOKEN` and
   `GITHUB_MODELS_URL`.
8. Call chat completions with `temperature=0.7` and `max_tokens=800`.
9. Return `reply`, `model`, and `citations`.

This is acceptable for a prototype baseline, but it is not yet split into the
target modules for orchestration, memory, knowledge retrieval, planning,
generation, and evaluation trace.

## Offline Data Preparation

Offline indexing is implemented as an opt-in script in `backend/rag/indexing.py`.
It is not part of the default Stage A startup path.

```mermaid
flowchart LR
    Raw[Processed or legacy raw dataset] --> Load[load_jsonl_dataset]
    Load --> Baseline[DocumentChunker baseline chunks]
    Load --> Structured[ParentChildChunker child chunks]
    Baseline --> EmbedA[VectorEmbedder.embed_texts]
    Structured --> EmbedB[VectorEmbedder.embed_texts]
    EmbedA --> StoreA[Chroma collection vietnam_travel_knowledge]
    EmbedB --> StoreB[Chroma collection vietnam_travel_parent_child]
    StoreA --> Disk[data/chromadb]
    StoreB --> Disk[data/chromadb]
```

The script resolves processed dataset paths first and falls back to legacy
paths. It may read travel data, load or download the embedding model through
the configured environment, and mutate persistent Chroma state under
`data/chromadb`.

## Local Runtime and Configuration

| Concern | Current configuration |
| --- | --- |
| Backend runtime | `backend/Dockerfile` uses `python:3.11-slim` and starts `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000` |
| Frontend runtime | `frontend/Dockerfile` uses `node:18-alpine` and starts `npm run dev -- --host 0.0.0.0` |
| Backend port | Docker Compose maps `8000:8000` |
| Frontend port | Docker Compose maps `5173:5173` |
| Backend environment file | Docker Compose references `.env` |
| Frontend API origin | Docker Compose sets `VITE_API_URL=http://localhost:8000` |
| Model credential name | `GITHUB_TOKEN` |
| Model name | `LLM_MODEL`, defaulting to `gpt-4o-mini` |
| Model endpoint URL | `https://models.inference.ai.azure.com` |
| Example environment file | `.env.example` is empty in this repository state |

`backend/app/main.py` allows CORS origins `http://localhost:5173`,
`http://127.0.0.1:5173`, and `*`.

## Current Data and Persistence

| Store | Current behavior | Limitation |
| --- | --- | --- |
| Chroma vector store | `ChromaVectorStore` creates or opens collections under `data/chromadb` by default | Stores travel knowledge vectors, not user or trip memory |
| Hugging Face cache | Docker Compose mounts `~/.cache/huggingface` into the backend container | Cache state is local development infrastructure |
| Travel datasets | Indexing reads processed paths or legacy fallback paths | Dataset quality and freshness are not established by Package 3 |
| Application environment | Backend loads `.env` if present | `.env.example` is empty and no secret values are documented |

There is no implemented relational store, user profile store, trip workspace
store, conversation history store, memory store, planner state store, or
evaluation trace store in the bounded online architecture.

## Current Tests and Verification Signals

Package 2 recorded the most recent development verification state:

1. Stage A Docker startup and `/health` passed in an escalated local shell.
2. The frontend production build passed.
3. Frontend lint failed because ESLint configuration was missing.
4. Frontend tests failed because `jsdom` was missing and Vitest hit sandbox
   port-binding limits.
5. CI contains shell fallbacks that can mask backend or frontend test failures.

These signals do not prove RAG answer quality, memory quality, planner
correctness, production readiness, privacy guarantees, or complete test health.

## Current Gaps and Risks

Current gaps:

1. No implemented memory read path.
2. No implemented memory write path.
3. No implemented trip workspace.
4. No implemented user identity or authentication.
5. No implemented conversation persistence.
6. No implemented planner module or itinerary state.
7. No implemented evaluation trace write in the bounded chat route.
8. No approved storage ownership decision for relational data, vector data, or
   trace data.
9. Travel knowledge retrieval and prompt assembly are coupled inside
   `RAGService.generate_answer`.
10. Local CORS is permissive.
11. The chat route logs a prefix of the user message.
12. Production security, privacy, tenant isolation, SLOs, and deployment
   topology are not established by this prototype.

## Compatibility Baseline

Future runtime work must preserve these current facts unless a separately
approved spec changes them:

1. Stage A health inspection remains `GET /health`.
2. The current chat route remains `POST /api/v1/chat`.
3. The current chat request remains `message` only.
4. The current chat response remains `reply`, `model`, and `citations`.
5. Chroma remains the current local travel-knowledge vector store.
6. `GITHUB_TOKEN`, `LLM_MODEL`, and `VITE_API_URL` remain the documented
   environment names.
7. Offline indexing remains opt-in and state-changing.
