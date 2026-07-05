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

This starts: OpenSearch, PostgreSQL with the `pg_embedding` extension, Redis, Langfuse, Prometheus, Grafana, Loki, Promtail, StatsD exporter, Nginx.

The default search backend is PostgreSQL `pg_embedding`:

```bash
SEARCH__BACKEND=postgres_embedding
SEARCH__VECTOR_DIMENSION=1024
SEARCH__HYBRID_CANDIDATE_MULTIPLIER=2
SEARCH__RRF_CONSTANT=60
```

OpenSearch remains available as a rollback path:

```bash
SEARCH__BACKEND=opensearch
```

Semantic answer caching is disabled by default. It requires Redis Stack or another
Redis endpoint with RediSearch vector commands; the plain local Redis service is
enough for exact-match caching only.

```bash
REDIS__SEMANTIC_CACHE_ENABLED=false
```

To test semantic caching locally, run Redis Stack on port 6379 or point
`REDIS__HOST`/`REDIS__PORT` at a vector-capable Redis endpoint, then enable:

```bash
REDIS__SEMANTIC_CACHE_ENABLED=true
REDIS__SEMANTIC_CACHE_LOOKUP_ENABLED=true
REDIS__SEMANTIC_CACHE_STORE_ENABLED=true
REDIS__SEMANTIC_CACHE_SCOPE_VERSION=v1
REDIS__SEMANTIC_CACHE_DISTANCE_THRESHOLD=0.08
```

The API checks Redis capability at startup. If `FT._LIST` is unavailable, it
keeps serving live RAG and records semantic-cache bypasses instead of failing
startup. Rotate `REDIS__SEMANTIC_CACHE_SCOPE_VERSION` after ingestion, prompt,
search, or chunking changes so old semantic answers cannot match new behavior.

`pg_embedding` is archived upstream and is intentionally pinned here for compatibility with the Postgres vector backend. The local Postgres image builds the extension from tag `0.3.6` (`055b71946024d72abecd8302fcfa17fe1bfb22f1`).

If you already have a `postgres_data` volume from the plain `postgres` image, rebuild and recreate the Postgres container so the extension exists:

```bash
docker compose build postgres
docker compose down
docker volume rm rag_postgres_data
docker compose up -d postgres
```

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
| Vector search   | PostgreSQL `pg_embedding` by default; OpenSearch fallback |
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
