# API — FastAPI Backend

The core backend service. Exposes REST endpoints for hybrid search, simple RAG, and agentic RAG over the Nuke documentation knowledge base.

---

## Endpoints

| Method | Path              | Description                                          |
|--------|-------------------|------------------------------------------------------|
| GET    | `/health`         | Liveness check                                       |
| GET    | `/metrics`        | Prometheus metrics                                   |
| POST   | `/hybrid-search`  | BM25 + vector hybrid search against the configured backend |
| POST   | `/ask`            | Single-turn Q&A (search backend -> Ollama, Redis cached) |
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
│   ├── opensearch/    # OpenSearch backend + query builder
│   └── search/        # Backend abstraction + PostgreSQL pg_embedding backend
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
  → configured search client
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
| `SEARCH__*`      | Backend selection, vector dimension, hybrid/RRF tuning |
| `OPENSEARCH__*`  | Host, port, index name, RRF settings        |
| `CHUNKING__*`    | Target size, overlap, minimum size          |
| `LANGFUSE__*`    | Public/secret keys, host                    |
| `REDIS__*`       | Host, port, TTL                             |
| `EVAL__*`        | Judge model, golden dataset path            |
| `POSTGRES_*`     | Connection URL (SQLAlchemy + psycopg3)      |
| `OLLAMA_*`       | Base URL, model name                        |
| `JINA_API_KEY`   | Jina AI API key                             |

Copy `.env.example` to `.env` and fill in values before running.

Default search settings:

```bash
SEARCH__BACKEND=postgres_embedding
SEARCH__VECTOR_DIMENSION=1024
SEARCH__HYBRID_CANDIDATE_MULTIPLIER=2
SEARCH__RRF_CONSTANT=60
```

Set `SEARCH__BACKEND=opensearch` to use the existing OpenSearch implementation. The Postgres backend requires the custom local Postgres image with the archived `pg_embedding` extension installed.

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

`/ask` and `/stream` use Redis exact-match caching by default. The exact cache key is a SHA256 hash of `(query, model, top_k, use_hybrid, categories, knowledge_source)`. TTL is 6 hours. Hit/miss is visible in Prometheus and Langfuse traces.

Semantic final-answer caching is optional and disabled by default. Phase one only supports `/ask` and `/stream`; `/ask-agentic` records a semantic-cache bypass because its guardrail and memory safety checks happen inside the LangGraph run.

To enable semantic caching, point Redis at Redis Stack or another Redis deployment with RediSearch vector commands:

```bash
REDIS__SEMANTIC_CACHE_ENABLED=true
REDIS__SEMANTIC_CACHE_LOOKUP_ENABLED=true
REDIS__SEMANTIC_CACHE_STORE_ENABLED=true
REDIS__SEMANTIC_CACHE_ASK_ENABLED=true
REDIS__SEMANTIC_CACHE_STREAM_ENABLED=true
REDIS__SEMANTIC_CACHE_AGENTIC_ENABLED=false
REDIS__SEMANTIC_CACHE_NAMESPACE=rag-semantic-cache
REDIS__SEMANTIC_CACHE_SCOPE_VERSION=v1
REDIS__SEMANTIC_CACHE_DISTANCE_THRESHOLD=0.08
```

Startup checks `FT._LIST`. If Redis does not expose RediSearch/vector commands, the app boots normally and logs:

```text
Semantic cache disabled: Redis does not expose RediSearch/vector commands. Use Redis Stack or disable REDIS__SEMANTIC_CACHE_ENABLED.
```

Rollback:

```bash
# Stop semantic hits immediately
REDIS__SEMANTIC_CACHE_LOOKUP_ENABLED=false

# Stop new semantic writes
REDIS__SEMANTIC_CACHE_STORE_ENABLED=false

# Prevent old entries from matching after ingestion, prompt, search, or chunking changes
REDIS__SEMANTIC_CACHE_SCOPE_VERSION=v2

# Optional Redis Stack cleanup
redis-cli FT.DROPINDEX rag-semantic-cache:idx DD
```

---

## Observability

- Prometheus metrics at `/metrics` via `prometheus-fastapi-instrumentator` plus custom singletons in `metrics.py`.
- Request golden-signal metrics follow the referenced homelab monitoring pattern:
  `app_requests_total`, `app_errors_total`, and `app_request_duration_seconds`.
- All LangChain/LangGraph calls are traced automatically by Langfuse `CallbackHandler`.
- `MetricsMiddleware` records per-route request counts, warning/critical error counts, latency histograms, and structured request logs.

---

## Further Reading

- [`services/agents/README.md`](services/agents/README.md) — LangGraph agentic RAG
- [`evaluation/README.md`](evaluation/README.md) — Evaluation harness
