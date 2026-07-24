<div align="center">

# Vietnam Travel AI Agent

### Intelligent Travel Assistant Powered by RAG, FastAPI, React & GPT-4o-mini

![Python](https://img.shields.io/badge/python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)

**Ask travel questions. Discover destinations. Get accurate, source-cited recommendations.**

Vietnam Travel AI Agent combines Retrieval-Augmented Generation (RAG), vector similarity search, and a ChatGPT-inspired UI into a full-stack production-ready application.

[Features](#key-features) • [Quick Start](#quick-start-guide) • [Architecture](#system-architecture) • [Tech Stack](#tech-stack) • [Testing](#testing--quality-assurance)

</div>

---

## Key Features

- **ChatGPT-Inspired Workspace**: Clean, responsive dark-mode chat interface built with React.js and Tailwind CSS (extracted from Google Stitch designs).
- **Retrieval-Augmented Generation (RAG)**: Connects LLM generation directly to structured and semi-structured travel guide knowledge stored in ChromaDB.
- **Source Citation & Verification**: Answers include verifiable metadata links back to original travel guide articles.
- **Production-Ready Containerization**: Docker Compose setup orchestrating backend and frontend services with CPU-optimized builds.
- **Automated CI/CD**: Integrated GitHub Actions pipeline executing syntax validation and automated pytest suites on pull requests.
- **Modular Monolith & DDD**: Clean code separation following Domain-Driven Design principles across API, RAG, Agent, and Evaluation layers.

---

## System Architecture

The application implements a decoupled full-stack architecture with a clear separation between presentation, API routing, and AI domain logic.

<div align="center">
  <img src="docs/images/architecture_diagram.png" alt="Vietnam Travel AI Agent System Architecture Diagram" width="80%">
</div>

---

## Project Structure

```text
travel-agent/
├── backend/
│   ├── app/
│   │   ├── api/             # Route controllers (health, chat)
│   │   ├── schemas/         # Pydantic request and response models
│   │   ├── config.py        # Centralized settings and environment variables
│   │   └── main.py          # FastAPI application entrypoint and CORS
│   ├── rag/
│   │   ├── chunking/        # Document loaders and text splitters
│   │   ├── embedding/       # Multilingual embedding model integration
│   │   ├── retrieval/       # Vector store queries and hybrid search
│   │   ├── generation/      # Prompt construction and LLM clients
│   │   └── evaluation/      # RAGAS metrics and benchmark datasets
│   ├── tests/               # Pytest automated test suite
│   └── Dockerfile           # CPU-optimized Python container build
├── frontend/
│   ├── src/
│   │   ├── components/      # React UI modules (Sidebar, Header, ChatInput, etc.)
│   │   ├── services/        # Axios API client layer
│   │   ├── App.jsx          # Root application state management
│   │   └── main.jsx         # Application entrypoint
│   ├── tests/               # Vitest component test suite
│   ├── index.html           # HTML template
│   └── Dockerfile           # Node.js Alpine web container build
├── data/                    # Raw datasets and ChromaDB vector store
├── docs/
│   └── images/              # System architecture diagrams & screenshots
├── .agents/                 # Engineering standards and agent directives
├── .github/workflows/       # GitHub Actions CI pipeline configuration
├── docker-compose.yml       # Multi-container orchestration
└── requirements.txt         # Workspace Python dependencies
```

---

## Tech Stack

| Component | Technology / Library |
|---|---|
| **Frontend** | React 18, Vite, Tailwind CSS, Axios, Lucide Icons |
| **Backend API** | FastAPI, Uvicorn, Pydantic v2, Python-dotenv |
| **AI / RAG** | OpenAI SDK (GPT-4o-mini), BAAI/bge-m3, ChromaDB |
| **Testing** | Pytest, Httpx, Vitest |
| **DevOps** | Docker, Docker Compose, GitHub Actions CI |

---

## Quick Start Guide

### Prerequisites

- Git
- Docker and Docker Compose (Recommended)
- Python 3.11+ and Node.js 18+ (For manual local execution)

### Environment Configuration

Create a `.env` file in the root directory:

```bash
GITHUB_TOKEN=your_github_personal_access_token_here
LLM_MODEL=gpt-4o-mini
```

### Option 1: Run with Docker Compose (Recommended)

Start the entire full-stack application with a single command:

```bash
docker compose up --build
```

Access the services:
- **Frontend Workspace**: http://localhost:5173
- **Backend Swagger API**: http://localhost:8000/docs

To stop all running containers:

```bash
docker compose down
```

### Option 2: Run Manually for Local Development

#### 1. Start the Backend API

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server
uvicorn backend.app.main:app --reload --port 8000
```

#### 2. Start the Frontend Application

```bash
# Open a new terminal tab
cd frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```

---

## Testing & Quality Assurance

Automated unit tests are located in `backend/tests/`.

To execute backend unit tests locally:

```bash
source .venv/bin/activate
python -m pytest backend/tests/
```

GitHub Actions automatically runs these tests on every pull request to the `main` branch.

---

## License

Distributed under the MIT License. See `LICENSE` for more information.