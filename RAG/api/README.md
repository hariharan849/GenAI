# API — FastAPI Backend

The core backend service. Exposes REST endpoints for hybrid search, simple RAG, and agentic RAG over the Nuke documentation knowledge base.

---

## Endpoints

| Method | Path              | Description                                          |
|--------|-------------------|------------------------------------------------------|
| GET    | `/health`         | Liveness check                                       |
| GET    | `/metrics`        | Prometheus metrics                                   |
| POST   | `/hybrid-search`  | BM25 + kNN RRF search against OpenSearch             |
| POST   | `/ask`            | Single-turn Q&A (OpenSearch → Ollama, Redis cached)  |
| POST   | `/stream`         | Same as `/ask` but streams tokens via SSE            |
| POST   | `/ask-agentic`    | Full LangGraph agentic RAG pipeline                  |

---

## Directory Structure

```
api/
├── routers/           # FastAPI route handlers (one file per endpoint group)
├── services/          # Business logic
│   ├── agents/        # LangGraph agentic RAG (see agents/README.md)
│   ├── cache/         # Redis exact-match cache
│   ├── embeddings/    # Jina AI v3 client
│   ├── indexing/      # Section-aware text chunker
│   ├── langfuse/      # Tracing / observability client
│   ├── ollama/        # Local LLM client + prompt templates
│   └── opensearch/    # Hybrid search client + query builder
├── repositories/      # SQLAlchemy data access (nuke_page.py)
├── models/            # SQLAlchemy ORM models
├── schemas/           # Pydantic request/response models
├── db/                # Engine, session factory, abstract base (interfaces/)
├── evaluation/        # DeepEval harness (see evaluation/README.md)
├── tests/             # API-specific tests
├── config.py          # Pydantic BaseSettings (all config via env vars)
├── dependencies.py    # FastAPI Depends() injection helpers
├── main.py            # App lifespan, router registration, startup sequence
├── metrics.py         # Prometheus metric singletons
├── middlewares.py     # StatsD middleware
└── exceptions.py      # Custom HTTP exceptions
```

---

## Service Initialization Order

Services are created once at startup in `main.py` lifespan and attached to `app.state`:

```
database (SQLAlchemy)
  → OpenSearch client
  → Jina embeddings client
  → Ollama client
  → Langfuse client
  → Redis cache
  → LangGraph checkpointer pool (AsyncPostgresSaver + AsyncConnectionPool)
  → AgenticRAGService (compiled LangGraph)
```

The `AgenticRAGService` and its Postgres connection pool are **not** recreated per request. They live for the lifetime of the process.

---

## Configuration

All configuration comes from environment variables, grouped into nested Pydantic `BaseSettings` classes in `config.py`:

| Prefix           | Covers                                      |
|------------------|---------------------------------------------|
| `OPENSEARCH__*`  | Host, port, index name, RRF settings        |
| `CHUNKING__*`    | Target size, overlap, minimum size          |
| `LANGFUSE__*`    | Public/secret keys, host                    |
| `REDIS__*`       | Host, port, TTL                             |
| `EVAL__*`        | Judge model, golden dataset path            |
| `POSTGRES_*`     | Connection URL (SQLAlchemy + psycopg3)      |
| `OLLAMA_*`       | Base URL, model name                        |
| `JINA_API_KEY`   | Jina AI API key                             |

Copy `.env.example` to `.env` and fill in values before running.

---

## Running Locally

```bash
# Install dependencies
uv sync

# Start the server with hot reload
uvicorn api.main:app --host 0.0.0.0 --port 8083 --reload
```

Requires shared infrastructure to be running (`docker compose up -d` from the repo root).

---

## Caching

`/ask` and `/stream` use Redis. The cache key is a SHA256 hash of `(query, model, top_k, use_hybrid, categories)`. TTL is 6 hours. Hit/miss is visible in Langfuse traces.

---

## Observability

- Prometheus metrics at `/metrics` via `prometheus-fastapi-instrumentator` plus custom singletons in `metrics.py`.
- All LangChain/LangGraph calls are traced automatically by Langfuse `CallbackHandler`.
- StatsD middleware (`middlewares.py`) emits per-route latency/count stats.

---

## Further Reading

- [`services/agents/README.md`](services/agents/README.md) — LangGraph agentic RAG
- [`evaluation/README.md`](evaluation/README.md) — Evaluation harness
