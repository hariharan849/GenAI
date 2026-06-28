# Nuke RAG System

A production-grade Retrieval-Augmented Generation system for Foundry Nuke 17.0 documentation. Combines hybrid semantic+keyword search with an agentic LangGraph workflow, a Next.js chat UI, and three interchangeable ingestion orchestrators.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Client (Browser)                                               │
│   └── Next.js UI (port 3004 / Nginx port 80)                   │
│         ├── CopilotKit sidebar  → /ask-agentic                  │
│         └── OpenAI Chat         → /ask-agentic                  │
└───────────────────────────┬─────────────────────────────────────┘
                             │
┌───────────────────────────▼─────────────────────────────────────┐
│  FastAPI (port 8083)                                            │
│   ├── GET  /health                                              │
│   ├── POST /hybrid-search  → OpenSearch RRF (BM25 + kNN)       │
│   ├── POST /ask            → OpenSearch → Ollama (+ cache)      │
│   ├── POST /stream         → streaming SSE variant of /ask      │
│   └── POST /ask-agentic    → LangGraph agentic RAG workflow     │
└───────────────────────────┬─────────────────────────────────────┘
                             │
     ┌───────────────────────┼──────────────────────┐
     │                       │                      │
┌────▼────┐           ┌──────▼──────┐        ┌──────▼──────┐
│OpenSearch│           │  Ollama     │        │  PostgreSQL  │
│  :9200   │           │ llama3.2:1b │        │   :5436      │
│ BM25+kNN │           │ (local LLM) │        │ pages +      │
└──────────┘           └─────────────┘        │ LG checkpts  │
                                               └─────────────┘
     │
┌────▼────────────────────────────────────────────────────────────┐
│  Ingestion Pipeline  (pick one orchestrator)                    │
│   ├── Airflow  (port 8081)  — CeleryExecutor DAG               │
│   ├── Prefect  (port 4200)  — flow + worker deployment          │
│   └── Dagster  (port 3002)  — software-defined assets           │
│                                                                  │
│  Pipeline steps:                                                 │
│  scrape → save to PostgreSQL → chunk → embed (Jina) → index     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Repository Layout

```
RAG/
├── api/                   # FastAPI backend — routers, services, agents
├── orchestrators/         # Ingestion pipelines (Airflow / Prefect / Dagster)
├── ui/                    # Next.js frontend (CopilotKit + OpenAI Responses API)
├── infra/                 # Docker configs, monitoring stack, Terraform (AWS)
├── tests/                 # Root-level test suite
├── scripts/               # Utility scripts (DB table creation, etc.)
└── docker-compose.yaml    # Full local stack
```

See each subdirectory's README for detailed documentation.

---

## Quick Start (Local)

### Prerequisites

- Docker + Docker Compose
- Python 3.12+ with `uv` (`pip install uv`)
- Node.js 20+ (for UI development)
- A Jina AI API key (`JINA_API_KEY`)
- An OpenAI API key (`OPENAI_API_KEY`) — used only by the eval harness

### 1. Configure environment

```bash
cp .env.example .env
# Fill in JINA_API_KEY, OPENSEARCH_*, POSTGRES_*, LANGFUSE_*, REDIS_* values
```

### 2. Start shared infrastructure

```bash
docker compose up -d
```

This starts: OpenSearch, PostgreSQL, Redis, Langfuse, Prometheus, Grafana, Loki, Promtail, StatsD exporter, Nginx.

### 3. Start an ingestion orchestrator (pick one)

```bash
# Airflow  (UI at http://localhost:8081)
docker compose --profile airflow up -d

# Prefect  (UI at http://localhost:4200)
docker compose --profile prefect up -d

# Dagster  (UI at http://localhost:3002)
docker compose --profile dagster up -d
```

Trigger the `nuke_docs_ingestion` job from the orchestrator UI.

### 4. Run the API

```bash
uv sync
uvicorn api.main:app --host 0.0.0.0 --port 8083 --reload
```

Or via Docker:

```bash
docker compose up rag-api
```

### 5. Run the UI

```bash
cd ui
npm install
npm run dev    # http://localhost:3004
```

---

## Service Ports

| Service              | Port  |
|----------------------|-------|
| FastAPI              | 8083  |
| Next.js UI           | 3004  |
| Nginx (reverse proxy)| 80    |
| Airflow              | 8081  |
| Prefect              | 4200  |
| Dagster              | 3002  |
| OpenSearch           | 9200  |
| OpenSearch Dashboards| 5601  |
| Langfuse             | 3001  |
| Grafana              | 3000  |
| Prometheus           | 9099  |
| Loki                 | 3100  |
| PostgreSQL           | 5436  |

---

## Key Technology Choices

| Concern         | Technology                        |
|-----------------|-----------------------------------|
| Embeddings      | Jina AI v3, 1024-dim              |
| Vector search   | OpenSearch RRF (BM25 + kNN)       |
| Local LLM       | Ollama `llama3.2:1b`              |
| Agentic RAG     | LangGraph                         |
| Checkpointing   | `AsyncPostgresSaver` (psycopg3)   |
| Caching         | Redis (SHA256 key, 6h TTL)        |
| Tracing         | Langfuse v3                       |
| Metrics         | Prometheus + Grafana + Loki       |
| Evaluation      | DeepEval + `gpt-4o-mini` judge    |
| IaC (AWS)       | Terraform (4-layer)               |

---

## Deployment (AWS)

See [`infra/terraform/README.md`](infra/terraform/README.md) for the full 4-layer AWS deployment guide.

---

## Further Reading

- [`api/README.md`](api/README.md) — FastAPI backend internals
- [`api/services/agents/README.md`](api/services/agents/README.md) — Agentic RAG LangGraph workflow
- [`api/evaluation/README.md`](api/evaluation/README.md) — Evaluation harness
- [`orchestrators/README.md`](orchestrators/README.md) — Ingestion pipeline comparison
- [`ui/README.md`](ui/README.md) — Next.js frontend
- [`infra/README.md`](infra/README.md) — Infrastructure overview
- [`tests/README.md`](tests/README.md) — Test suite
