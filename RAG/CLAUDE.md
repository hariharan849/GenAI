# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A Nuke documentation RAG system with agentic RAG capabilities. It:
1. Runs an Airflow pipeline (manual trigger) to scrape, chunk, embed, and index Foundry Nuke 17.0 reference guide pages
2. Exposes a FastAPI REST API for hybrid semantic+keyword search and question answering over Nuke docs
3. Provides an agentic RAG endpoint backed by a LangGraph workflow with guardrails, document grading, and query rewriting
4. Uses Jina AI embeddings (1024-dim), OpenSearch for hybrid search (BM25 + vector RRF), Ollama for local LLM inference, Redis for caching, PostgreSQL for page metadata, and Langfuse for observability

## Development Environment

**Package manager**: `uv` (not pip)

```bash
# Install dependencies
uv sync

# Run the FastAPI server locally
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Run shared infrastructure only (OpenSearch, PostgreSQL, Redis, Langfuse, monitoring)
docker compose up -d

# Run with Airflow orchestrator (UI at localhost:8081)
docker compose --profile airflow up -d

# Run with Prefect orchestrator (UI at localhost:4200)
docker compose --profile prefect up -d
# Single-env-var equivalent:
COMPOSE_PROFILES=prefect docker compose up -d

# Run with Dagster orchestrator (UI at localhost:3002)
docker compose --profile dagster up -d

# Build the Prefect worker image
docker compose build prefect-worker

# Build the Dagster image (all three services share one Dockerfile)
docker compose --profile dagster build

# Build the application image only
docker compose build rag-api
```

**Note on orchestrator profiles**: Bare `docker compose up -d` starts shared infrastructure only (no Airflow, no Prefect, no Dagster). Use `--profile airflow`, `--profile prefect`, or `--profile dagster` explicitly to bring up an orchestrator.

**Airflow** runs on CeleryExecutor. Access the UI at `http://localhost:8081`. DAG: `nuke_docs_ingestion` is manually triggered (no schedule).

**Dagster** runs three containers (user-code gRPC server, webserver, daemon). Access the asset lineage UI at `http://localhost:3002`.

**Service ports**: FastAPI: 8000 | Airflow: 8081 | Prefect: 4200 | Dagster: 3002 | OpenSearch: 9200 | OpenSearch Dashboards: 5601 | Langfuse: 3001 | PostgreSQL: 5436

## Architecture

### Request Flow

```
Client
  └─► FastAPI routers (src/routers/)
        ├── /hybrid-search  → OpenSearchClient.search_unified() (BM25+vector RRF)
        ├── /ask            → OpenSearch → Ollama (+ Redis cache + Langfuse trace)
        ├── /stream         → same as /ask but streaming
        └── /ask-agentic    → AgenticRAGService (LangGraph graph)
                                  Guardrail → Route → Retrieve → Grade → [Rewrite] → Generate
```

### Key Layers

| Layer | Location | Purpose |
|-------|----------|---------|
| Routers | `src/routers/` | HTTP endpoints, request validation, response formatting |
| Services | `src/services/` | Business logic, external client wrappers |
| Repositories | `src/repositories/` | SQLAlchemy data access (`nuke_page.py`) |
| Models | `src/models/` | SQLAlchemy ORM models |
| Schemas | `src/schemas/` | Pydantic request/response models |
| DB | `src/db/` | SQLAlchemy engine/session factory, abstract base classes |
| Agents | `src/services/agents/` | LangGraph agentic RAG (state, nodes, tools, prompts) |
| Airflow DAGs | `airflow/dags/` | Nuke docs ingestion pipeline |

### Service Initialization

All services are initialized in `src/main.py` lifespan with strict ordering: database → OpenSearch → Jina embeddings → Ollama → Langfuse → Redis → Telegram. Services are injected via FastAPI `Depends` through `src/dependencies.py`.

### Agentic RAG Workflow (LangGraph)

Located in `src/services/agents/`. Uses `AgentState` (TypedDict) with nodes:
1. **Guardrail** — content safety check
2. **Out-of-scope router** — redirects non-research questions
3. **Retrieve** — OpenSearch hybrid search via LangChain tool
4. **Grade Documents** — relevance grading + re-ranking
5. **Rewrite Query** — query optimization if documents are insufficient
6. **Generate Answer** — final Ollama generation with citations

Nodes use `context.py` for dependency injection rather than closures.

### Ingestion Pipeline (Airflow)

`airflow/dags/nuke_docs_ingestion.py` — linear DAG (manual trigger):
`setup → scrape_nuke_docs → save_nuke_pages_to_db → index_nuke_docs → generate_nuke_report → cleanup_temp_files`

- `scraping.py`: Crawls Foundry Nuke 17.0 reference guide → extracts node pages → writes JSON via XCom
- `save.py`: Loads scraped JSON → upserts pages to PostgreSQL via `NukePageRepository`
- `indexing.py`: PostgreSQL → chunk (600 chars / 100 overlap) → Jina embed → OpenSearch bulk index to `nuke-docs-chunks`

### Configuration

`src/config.py` uses nested Pydantic `BaseSettings`. All values come from environment variables (`.env` file at root). Key nested configs: `ChunkingSettings`, `OpenSearchSettings`, `LangfuseSettings`, `RedisSettings`, `TelegramSettings`.

## Core Technology Choices

- **Chunking**: 600-char chunks, 100-char overlap, 50-char minimum. Text-based (Nuke pages are scraped HTML, not PDFs).
- **Embeddings**: Jina AI v3 (`retrieval.passage` for docs, `retrieval.query` for queries), 1024 dimensions, batched at 100 texts per API call.
- **Search**: OpenSearch RRF pipeline combining BM25 and k-NN vector search. Index: `nuke-docs-chunks`.
- **LLM**: Ollama `llama3.2:1b` (local). Prompts live in `src/services/agents/prompts.py` (agentic) and `src/services/ollama/prompts.py` (simple RAG).
- **Tracing**: Langfuse v3. All LangChain/LangGraph calls traced automatically via `CallbackHandler`. Manual spans added for Ollama calls.
- **Caching**: Redis exact-match cache. Key = SHA256 of `(query, model, top_k, use_hybrid, categories)`. TTL: 6 hours.

## Data Models

**PostgreSQL `nuke_pages` table** (`src/models/nuke_page.py`): stores scraped Nuke documentation pages with fields `node_name`, `section`, `url`, `content`, and an `indexed` boolean tracking ingestion state.

**OpenSearch index** `nuke-docs-chunks`: Each document is a chunk with `node_name`, `section`, `url`, `chunk_text` (text field for BM25), and `embedding` (knn_vector, 1024-dim).

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
