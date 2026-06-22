# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

An AI-powered arXiv paper curator with agentic RAG capabilities. It:
1. Runs a daily Airflow pipeline to fetch, parse, chunk, embed, and index arXiv CS.AI papers
2. Exposes a FastAPI REST API for hybrid semantic+keyword search and question answering
3. Provides an agentic RAG endpoint backed by a LangGraph workflow with guardrails, document grading, and query rewriting
4. Uses Jina AI embeddings (1024-dim), OpenSearch for hybrid search (BM25 + vector RRF), Ollama for local LLM inference, Redis for caching, PostgreSQL for paper metadata, and Langfuse for observability

## Development Environment

**Package manager**: `uv` (not pip)

```bash
# Install dependencies
uv sync

# Run the FastAPI server locally
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Run all services via Docker Compose
docker compose up -d

# Build the application image only
docker compose build rag-api
```

**Airflow** runs on CeleryExecutor. Access the UI at `http://localhost:8081`. DAG: `arxiv_paper_ingestion` runs Mon–Fri at 06:00 UTC.

**Service ports**: FastAPI: 8000 | Airflow: 8081 | OpenSearch: 9200 | OpenSearch Dashboards: 5601 | Langfuse: 3001 | PostgreSQL: 5436

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
| Repositories | `src/repositories/` | SQLAlchemy data access (only `paper.py` exists) |
| Models | `src/models/` | SQLAlchemy ORM models |
| Schemas | `src/schemas/` | Pydantic request/response models |
| DB | `src/db/` | SQLAlchemy engine/session factory, abstract base classes |
| Agents | `src/services/agents/` | LangGraph agentic RAG (state, nodes, tools, prompts) |
| Airflow DAGs | `airflow/dags/` | Paper ingestion pipeline |

### Service Initialization

All services are initialized in `src/main.py` lifespan with strict ordering: database → OpenSearch → arXiv → PDF parser → Jina embeddings → Ollama → Langfuse → Redis → Telegram. Services are injected via FastAPI `Depends` through `src/dependencies.py`.

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

`airflow/dags/arxiv_paper_ingestion.py` — linear DAG:
`setup → fetch_daily_papers → index_papers_hybrid → generate_daily_report → cleanup_temp_files`

- `fetching.py`: arXiv API → download PDFs → Docling parse → PostgreSQL upsert
- `indexing.py`: PostgreSQL → chunk (600 words / 100 overlap) → Jina embed → OpenSearch bulk index

### Configuration

`src/config.py` uses nested Pydantic `BaseSettings`. All values come from environment variables (`.env` file at root). Key nested configs: `ArxivSettings`, `PDFParserSettings`, `ChunkingSettings`, `OpenSearchSettings`, `LangfuseSettings`, `RedisSettings`, `TelegramSettings`.

## Core Technology Choices

- **Chunking**: 600-word chunks, 100-word overlap. Section-based when available, falls back to word-based.
- **Embeddings**: Jina AI v3 (`retrieval.passage` for docs, `retrieval.query` for queries), 1024 dimensions, batched at 100 texts per API call.
- **Search**: OpenSearch RRF pipeline combining BM25 and k-NN vector search. Index: `arxiv-papers-chunks`.
- **LLM**: Ollama `llama3.2:1b` (local). Prompts live in `src/services/agents/prompts.py` (agentic) and `src/services/ollama/prompts.py` (simple RAG).
- **PDF parsing**: Docling only (no fallback parsers). CPU-bound, wrapped in `asyncio.to_thread`.
- **Tracing**: Langfuse v3. All LangChain/LangGraph calls traced automatically via `CallbackHandler`. Manual spans added for Ollama calls.
- **Caching**: Redis exact-match cache. Key = SHA256 of `(query, model, top_k, use_hybrid, categories)`. TTL: 6 hours.

## Data Models

**PostgreSQL `papers` table** (`src/models/paper.py`): `arxiv_id` is the natural key (unique, indexed). `sections` and `authors` are stored as JSON. `pdf_processed` boolean tracks ingestion state.

**OpenSearch index** `arxiv-papers-chunks`: Each document is a chunk with denormalized paper metadata (`arxiv_id`, `title`, `authors`, etc.) plus `chunk_text` (text field for BM25) and `embedding` (knn_vector, 1024-dim).

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
