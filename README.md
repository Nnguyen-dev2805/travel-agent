# Travel Agent

Travel Agent is a learning-oriented travel assistant built around authenticated
chat, Retrieval-Augmented Generation (RAG), PostgreSQL persistence, and an
experimental semantic Memory write pipeline.

The repository is intentionally a prototype. It is useful for engineering,
experimentation, and architecture work, but it is not a production-ready or
quality-certified service.

## Current Runtime

The checked-out code currently provides:

- authenticated `POST /api/v1/chat` with automatic conversation creation and
  continuation;
- standalone conversation CRUD and paged message history under
  `/api/v1/conversations`;
- PostgreSQL 16 persistence with owner-scoped access and row-level security;
- a transactional conversation outbox whose events become claimable only after
  the producing turn reaches a terminal state;
- RAG retrieval from Chroma, query embedding with `BAAI/bge-m3`, and
  source-cited generation;
- a separate semantic Memory worker/write pipeline for background extraction;
- runtime readiness diagnostics at `GET /api/v1/ops/readiness`;
- a React/Vite frontend and Docker Compose local stack.

The semantic Memory write path is feature-gated. Both
`MEMORY_WRITE_PIPELINE_ENABLED` and `MEMORY_SHADOW_EXTRACT_ENABLED` default to
`false`, so the presence of the implementation does not mean background Memory
extraction is enabled in a default runtime.

## Current Memory Boundary

The implemented Memory slice is deliberately small:

- registry version: `semantic-registry-v1`;
- implemented key: `travel.preference.hotel_atmosphere`;
- cardinality: single value;
- normalized values: `quiet`, `lively`, `central`, `secluded`;
- supported scopes: user and conversation;
- write-side concepts include candidate extraction, deterministic policy and
  resolution, versioned assertions, evidence, decisions, idempotency, and a
  background worker.

The current runtime does **not** yet provide the target Memory Read/Use engine,
chat-native `remember`/`correct`/`forget`/`inspect`, Episodic Memory, Working
Memory, or Procedural Memory publication. Those belong to the target
architecture, not the current-state claim.

## Quick Start

From the repository root:

```bash
docker compose up --build
```

Then check process liveness:

```bash
curl http://localhost:8000/health
```

`/health` proves only that the API process is reachable. It does not prove that
PostgreSQL migrations are current, Chroma contains usable data, the external
model provider is configured, RAG quality is acceptable, or Memory features are
enabled.

Real chat additionally depends on local environment configuration, a reachable
model provider, available embedding weights, and populated Chroma data.

## Repository Map

| Path | Purpose |
| --- | --- |
| `frontend/` | React/Vite browser client |
| `backend/app/` | FastAPI application, routes, configuration, and composition root |
| `backend/conversations/` | Conversation domain, service, and PostgreSQL repository |
| `backend/rag/` | Embedding, Chroma retrieval, context assembly, generation, and RAG evaluation code |
| `backend/memory/write_pipeline/` | Current semantic Memory write-side implementation and worker |
| `backend/storage/migrations/` | PostgreSQL/Alembic schema history |
| `backend/tests/` | Unit, integration, boundary, and evaluation fixtures/tests |
| `docs/architecture/` | Living current-state, target-state, and conceptual data-model documentation |

## Architecture Documentation

The project intentionally keeps only three living architecture documents:

- [Current-state Architecture](docs/architecture/current-state.md) — what the
  checked-out runtime actually implements.
- [Target-state Architecture](docs/architecture/target-state.md) — where the
  system is intended to evolve and what gaps remain.
- [Data Model](docs/architecture/data-model.md) — the conceptual target Memory
  entities, relationships, lifecycle, and ownership model.

For current behavior, source code, migrations, tests, configuration, and fresh
runtime evidence take precedence over prose.

## Known Limitations

- Production readiness is not established.
- RAG quality depends on the indexed corpus and has not been established by the
  existence of the runtime alone.
- Chat readiness depends on PostgreSQL, Chroma, embedding/model availability,
  credentials, and network access.
- Memory background extraction is disabled by default and the current Memory
  implementation is write-side only.
- The target Memory architecture is intentionally broader than the code that is
  implemented today.
