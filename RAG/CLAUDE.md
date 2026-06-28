# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A Nuke documentation RAG system with agentic RAG capabilities. It:
1. Runs ingestion pipelines (Airflow, Prefect, or Dagster — pick one) to scrape, chunk, embed, and index Foundry Nuke 17.0 reference guide pages
2. Exposes a FastAPI REST API for hybrid semantic+keyword search and question answering over Nuke docs
3. Provides an agentic RAG endpoint backed by a LangGraph workflow with guardrails, intent classification, document grading, re-ranking, and query rewriting
4. Uses Jina AI embeddings (1024-dim), OpenSearch for hybrid search (BM25 + vector RRF), Ollama for local LLM inference, Redis for caching, PostgreSQL for page metadata and LangGraph checkpointing, and Langfuse for observability
5. Ships a Next.js UI with CopilotKit and OpenAI Responses API chat providers, supporting both Nuke and arXiv knowledge bases

## Development Environment

**Package manager**: `uv` (not pip)

```bash
# Install dependencies
uv sync

# Run the FastAPI server locally
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

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

**Service ports**: FastAPI: 8083 | UI: 3004 | Nginx: 80 | Airflow: 8081 | Prefect: 4200 | Dagster: 3002 | OpenSearch: 9200 | OpenSearch Dashboards: 5601 | Langfuse: 3001 | Grafana: 3000 | Prometheus: 9099 | Loki: 3100 | PostgreSQL: 5436

## Architecture

### Request Flow

```
Client
  └─► FastAPI routers (api/routers/)
        ├── /hybrid-search  → OpenSearchClient.search_unified() (BM25+vector RRF)
        ├── /ask            → OpenSearch → Ollama (+ Redis cache + Langfuse trace)
        ├── /stream         → same as /ask but streaming
        └── /ask-agentic    → AgenticRAGService (LangGraph graph)
                                  InputGuardrail → IntentClassify → [OutOfScope] →
                                  Retrieve → GradeDocuments → Rerank →
                                  [RewriteQuery → Retrieve (retry)] →
                                  OutputGuardrail → GenerateAnswer
```

### Key Layers

| Layer | Location | Purpose |
|-------|----------|---------|
| Routers | `api/routers/` | HTTP endpoints, request validation, response formatting |
| Services | `api/services/` | Business logic, external client wrappers |
| Repositories | `api/repositories/` | SQLAlchemy data access (`nuke_page.py`) |
| Models | `api/models/` | SQLAlchemy ORM models |
| Schemas | `api/schemas/` | Pydantic request/response models |
| DB | `api/db/` | SQLAlchemy engine/session factory, abstract base classes (`db/interfaces/`) |
| Agents | `api/services/agents/` | LangGraph agentic RAG (state, nodes/, tools, prompts) |
| Evaluation | `api/evaluation/` | DeepEval harness, golden dataset, run comparison |
| Metrics | `api/metrics.py`, `api/middlewares.py` | Prometheus metric singletons + StatsD middleware |
| Airflow | `orchestrators/airflow/dags/` | Nuke docs ingestion DAG + task modules |
| Prefect | `orchestrators/prefect/flows/`, `deployments/` | Prefect flow + deployment definition |
| Dagster | `orchestrators/dagster/assets/` | Dagster software-defined assets |
| UI | `ui/` | Next.js frontend with CopilotKit and OpenAI Responses API providers |

### Service Initialization

All services are initialized in `api/main.py` lifespan with strict ordering: database → OpenSearch → Jina embeddings → Ollama → Langfuse → Redis → LangGraph checkpointer pool → AgenticRAGService. Services are injected via FastAPI `Depends` through `api/dependencies.py`.

The `AgenticRAGService` and its LangGraph checkpointer (`AsyncPostgresSaver` backed by a dedicated `AsyncConnectionPool`) are built **once at startup** and stored on `app.state` — not recreated per request. This keeps the Postgres connection pool alive across requests and avoids rebuilding the compiled graph on every call.

### Agentic RAG Workflow (LangGraph)

Located in `api/services/agents/`. Uses `AgentState` (TypedDict) with nodes split into individual files under `nodes/`:
1. **InputGuardrail** (`input_guardrail_node.py`) — content safety check on the incoming question
2. **IntentClassify** (`intent_classify_node.py`) — routes in-scope vs out-of-scope questions
3. **OutOfScope** (`out_of_scope_node.py`) — friendly deflection response
4. **Retrieve** (`retrieve_node.py`) — OpenSearch hybrid search via LangChain tool
5. **GradeDocuments** (`grade_documents_node.py`) — relevance grading of retrieved chunks
6. **Rerank** (`rerank_node.py`) — re-ranks graded documents by score
7. **RewriteQuery** (`rewrite_query_node.py`) — query optimisation when docs are insufficient, then retries retrieve
8. **OutputGuardrail** (`output_guardrail_node.py`) — safety check on the generated answer
9. **GenerateAnswer** (`generate_answer_node.py`) — final Ollama generation with citations

Nodes use `context.py` for dependency injection rather than closures. Shared guardrail logic lives in `guardrail_common.py`.

### Ingestion Pipelines

Three orchestrator implementations exist under `orchestrators/`; pick one to run alongside shared infrastructure.

**Airflow** (`orchestrators/airflow/`) — CeleryExecutor, UI at `:8081`
DAG `nuke_docs_ingestion` (manual trigger): `setup → scrape_nuke_docs → save_nuke_pages_to_db → index_nuke_docs → generate_nuke_report → cleanup_temp_files`
- `nuke_ingestion/scraping.py`: Crawls Foundry Nuke 17.0 reference guide → extracts node pages → writes JSON via XCom
- `nuke_ingestion/save.py`: Upserts scraped pages to PostgreSQL via `NukePageRepository`
- `nuke_ingestion/indexing.py`: PostgreSQL → section-aware chunk → Jina embed → OpenSearch bulk index

**Prefect** (`orchestrators/prefect/`) — UI at `:4200`
- `flows/nuke_ingestion.py`: Prefect flow mirroring the Airflow DAG steps
- `deployments/nuke_ingestion_deployment.py`: Deployment definition for the worker

**Dagster** (`orchestrators/dagster/`) — three containers (user-code gRPC, webserver, daemon), UI at `:3002`
- `assets/nuke_ingestion.py`: Software-defined assets (`scraped_nuke_pages`, `saved_nuke_pages`, `indexed_nuke_docs`, `nuke_ingestion_report`) grouped under `nuke_ingestion`
- `definitions.py`: Wires assets into `nuke_docs_ingestion` job

### Configuration

`api/config.py` uses nested Pydantic `BaseSettings`. All values come from environment variables (`.env` file at root). Key nested configs: `ChunkingSettings`, `OpenSearchSettings`, `LangfuseSettings`, `RedisSettings`, `EvalSettings`. Telegram has been removed. `Settings.postgres_psycopg_url` is a property that strips the SQLAlchemy driver prefix (`+psycopg2`) for the psycopg3 async checkpointer pool.

## Core Technology Choices

- **Chunking**: Section-aware, 600-char target, 100-char overlap, 100-char minimum. Text-based (Nuke pages are scraped HTML, not PDFs). Configured via `CHUNKING__*` env vars.
- **Embeddings**: Jina AI v3 (`retrieval.passage` for docs, `retrieval.query` for queries), 1024 dimensions, batched at 100 texts per API call.
- **Search**: OpenSearch RRF pipeline combining BM25 and k-NN vector search. Index: `nuke-docs-chunks`.
- **LLM**: Ollama `llama3.2:1b` (local). Prompts live in `api/services/agents/prompts.py` (agentic) and `api/services/ollama/prompts.py` (simple RAG).
- **Checkpointing**: LangGraph conversation memory via `AsyncPostgresSaver` (psycopg3). Dedicated connection pool (`postgres_checkpointer_pool_size=5`) separate from the SQLAlchemy sync pool.
- **Tracing**: Langfuse v3. All LangChain/LangGraph calls traced automatically via `CallbackHandler`. Manual spans added for Ollama calls.
- **Caching**: Redis exact-match cache. Key = SHA256 of `(query, model, top_k, use_hybrid, categories)`. TTL: 6 hours.
- **Evaluation**: DeepEval harness in `api/evaluation/`. Golden dataset at `api/evaluation/golden_dataset.yaml`. Uses a cloud judge model (`gpt-4o-mini` by default) separate from the production Ollama model.
- **Observability**: Prometheus metrics exposed at `/metrics` via `prometheus-fastapi-instrumentator`. Custom metric singletons in `api/metrics.py`. StatsD middleware in `api/middlewares.py`. Grafana dashboards at `:3000`, Loki at `:3100`.

## Data Models

**PostgreSQL `nuke_pages` table** (`api/models/nuke_page.py`): stores scraped Nuke documentation pages with fields `node_name`, `section`, `url`, `content`, and an `indexed` boolean tracking ingestion state. Also hosts the LangGraph checkpointer tables (created automatically by `AsyncPostgresSaver.setup()`).

**OpenSearch index** `nuke-docs-chunks`: Each document is a chunk with `node_name`, `section`, `url`, `chunk_text` (text field for BM25), and `embedding` (knn_vector, 1024-dim).

### UI

Next.js app at `ui/`. Accessed via Nginx reverse proxy (`:80`) or directly at `:3004`.

- **`ui/app/page.tsx`**: Knowledge-source picker (Nuke / arXiv) and chat-provider picker (CopilotKit / OpenAI).
- **`ui/components/RAGCopilot.tsx`**: CopilotKit sidebar using agentic RAG hooks.
- **`ui/components/AgentSteps.tsx`**: Renders intermediate agent steps from the agentic RAG workflow.
- **`ui/components/OpenAIChat.tsx`**: OpenAI Responses API chat with tool-calling loop (Nuke knowledge base only).
- **`ui/app/api/copilotkit/`**: CopilotKit backend route.
- **`ui/app/api/openai-chat/route.ts`**: OpenAI Responses API proxy route.

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
