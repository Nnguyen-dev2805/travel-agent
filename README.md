# Travel Agent

Travel Agent is an early-stage open-source travel assistant prototype using
retrieval-augmented generation. Today it is a local RAG chat prototype.
Evaluated trip planning, trip workspaces, and layered memory are planned
direction, not implemented behavior.

## Current Status

The current repository is useful for learning, local inspection, and shaping the
foundation of a production-oriented travel assistant. It should not be treated
as a finished product, a quality-certified RAG system, or a production service.

The implemented browser flow sends a single chat message to the backend, asks
the RAG service for retrieved travel context, and returns a reply with
citations. The public request contract contains only `message`; it does not yet
include user, trip, conversation, or memory identity.

## What Works Today

- A React/Vite frontend can post chat messages to the backend API.
- A FastAPI backend exposes `/health` and `/api/v1/chat`.
- The chat path uses a RAG service that embeds the message, queries local
  Chroma data, and calls a configured external model endpoint.
- Responses include `reply`, `model`, and `citations` fields.
- Docker Compose defines a local frontend/backend development stack.

## Quick Start

This Stage A path is for startup and health inspection only. It may build
images, install dependencies, start local containers, and create or open local
Chroma state during backend startup. It does not crawl data, index data,
download an embedding model intentionally, or make a paid or external model
call as the expected quick-start outcome.

From the repository root:

```bash
docker compose up --build
```

In another shell:

```bash
curl http://localhost:8000/health
```

A health response proves only that the health route is reachable. It does not
prove retrieval quality, populated Chroma data, model-provider access,
credentials, or end-to-end chat readiness.

For detailed setup, command effects, side effects, and verification status, use
[DEVELOPMENT.md](DEVELOPMENT.md).

## Stage B: RAG Chat Readiness

Real RAG chat is a separate readiness stage. Before using chat, expect to
provide or verify:

- external model credential configuration,
- network access to the configured model provider,
- local embedding model availability or first-use download,
- populated Chroma data,
- and acceptance that the external model request contains the user message and
  retrieved travel context.

Crawling, ETL, indexing, model download, and model-dependent evaluation are
opt-in development operations. They are not part of the default quick start.

## Repository Map

| Path | Purpose |
| --- | --- |
| `frontend/` | React/Vite browser client |
| `backend/app/` | FastAPI application, routes, settings, and schemas |
| `backend/rag/` | RAG embedding, retrieval, generation, indexing, and evaluation code |
| `data/` | Local data and Chroma storage paths used by the prototype |
| `docs/specs/` | Approved and in-review specifications |
| `docs/plans/` | Implementation plans derived from approved specifications |
| `docs/adr/` | Architecture decision record workflow |
| `docs/runbooks/` | Diagnosed local recovery, deployment readiness, and incident response |
| `.github/` | GitHub issue intake, PR review, and CI configuration surfaces |

## Documentation

- [DEVELOPMENT.md](DEVELOPMENT.md) covers local setup, commands, side effects,
  and verification status.
- [ARCHITECTURE.md](ARCHITECTURE.md) maps the implemented high-level system and
  known architecture gaps.
- [docs/roadmap/master-roadmap.md](docs/roadmap/master-roadmap.md) defines the
  milestone order, dependencies, and exit gates.
- [docs/evaluation/rag-evaluation.md](docs/evaluation/rag-evaluation.md) defines
  the RAG quality measurement and promotion protocol.
- [docs/evaluation/memory-evaluation.md](docs/evaluation/memory-evaluation.md)
  defines the memory quality, lifecycle, and safety measurement protocol.
- [SECURITY.md](SECURITY.md) defines repository security, privacy, secret,
  evidence, data-handling, vulnerability-reporting, and public-production gates.
- [docs/runbooks/local-development.md](docs/runbooks/local-development.md),
  [docs/runbooks/deployment.md](docs/runbooks/deployment.md), and
  [docs/runbooks/incident-response.md](docs/runbooks/incident-response.md) own
  diagnosed local recovery, deployment readiness, and incident response.
- [docs/learning/engineering-curriculum.md](docs/learning/engineering-curriculum.md)
  maps project milestones to engineering learning tracks.
- [CONTRIBUTING.md](CONTRIBUTING.md) covers contribution workflow, approvals,
  branches, commits, review, and evidence.
- [LICENSE](LICENSE) defines the default project-authored source and
  documentation license as `Apache-2.0`.
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) records bounded third-party
  notice, attribution, and provenance review status.
- [CHANGELOG.md](CHANGELOG.md) records released user-visible history only.
- [AGENTS.md](AGENTS.md) is the coding-agent operating guide for this
  repository.
- [docs/specs/README.md](docs/specs/README.md) defines the specification
  workflow.
- [docs/plans/README.md](docs/plans/README.md) defines the implementation-plan
  workflow.
- [docs/adr/README.md](docs/adr/README.md) defines the ADR workflow.

## Known Limitations

- The project is an early prototype; production readiness is not established.
- RAG quality has not been certified by an approved evaluation gate.
- Chat readiness can depend on credentials, network access, model availability,
  and populated local vector data.
- The current chat request is stateless beyond one `message` field.
- Trip workspaces, long-term memory, short-term memory, user identity, and
  durable personalization are future direction rather than current capability.
- The repository now has an `Apache-2.0` source license, GitHub intake
  templates, third-party notice baseline, and release-only changelog, but full
  open-source release readiness remains a later gated milestone.
- Security policy and runbooks now exist, but they explicitly block unsupported
  public-production claims rather than certifying the current prototype.
