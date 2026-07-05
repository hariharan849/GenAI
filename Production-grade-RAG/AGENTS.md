# Repository Guidelines

## Project Structure & Module Organization

This repository is a Nuke documentation RAG system. `api/` contains the FastAPI backend, routers, schemas, repositories, and service integrations for search, embeddings, graph extraction, LangGraph agents, caching, and evaluation. `ui/` contains the Next.js chat interface and API routes. `orchestrators/` holds ingestion pipelines for Airflow, Prefect, and Dagster. `infra/` contains Docker, monitoring, Nginx, and Terraform AWS layers. Root `tests/` covers shared services and ingestion behavior; `api/tests/` covers API-specific behavior. Utility scripts live in `scripts/`.

## Build, Test, and Development Commands

- `uv sync`: install Python dependencies from `pyproject.toml` and `uv.lock`.
- `uvicorn api.main:app --host 0.0.0.0 --port 8083 --reload`: run the FastAPI backend locally.
- `docker compose up -d`: start the local infrastructure stack.
- `docker compose --profile airflow up -d`: start Airflow ingestion; replace `airflow` with `prefect` or `dagster` for other orchestrators.
- `cd ui && npm install && npm run dev`: run the Next.js UI on port `3002`.
- `cd ui && npm run build`: build the frontend.
- `uv run pytest`: run the root pytest suite.

## Coding Style & Naming Conventions

Use Python 3.13+ as declared in `pyproject.toml`. Follow existing FastAPI service layering: routers in `api/routers/`, Pydantic schemas in `api/schemas/`, repositories in `api/repositories/`, and integrations under `api/services/<domain>/`. Python files and functions use `snake_case`; classes use `PascalCase`. Keep async code explicit and typed where practical. UI components use TypeScript/React with `PascalCase` component filenames such as `RAGCopilot.tsx`.

## Testing Guidelines

Pytest is configured with `testpaths = ["tests"]` and `asyncio_mode = "auto"`. Name tests `test_*.py` and place shared fixtures in `conftest.py`. Integration-style tests may require local Docker services such as PostgreSQL, OpenSearch, Redis, or Neo4j. Use `uv run pytest tests/test_semantic_chunking.py` for focused runs and `uv run pytest -m "not integration"` when skipping slower service-backed tests.

## Commit & Pull Request Guidelines

Recent commits use concise, imperative messages, often Conventional Commit prefixes such as `feat:`, `fix:`, and `chore:`. Keep commits scoped to one change. Pull requests should include a short summary, affected areas (`api`, `ui`, `infra`, `orchestrators`), test results, linked issues when applicable, and screenshots for UI changes.

## Security & Configuration Tips

Keep secrets in `.env` and never commit credentials or generated service data. Prefer `.env.example`-style documentation for new variables. When changing Terraform or Docker Compose, call out required ports, profiles, and migration steps in the PR.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
