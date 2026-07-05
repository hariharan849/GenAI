# 0001 Modular Architecture

## Status

Accepted

## Context

The codebase has working API, search, graph, ingestion, and agentic RAG behavior, but some modules are organized around original service or orchestrator locations instead of domain ownership. This makes changes harder because API routers, ingestion adapters, and tests know backend-specific details.

## Decision

Keep `api/` as the FastAPI application package and introduce domain-oriented modules:

- `api.rag` owns classic RAG orchestration.
- `api.search` owns search protocols, factories, backend adapters, chunk IDs, and indexing payloads.
- `api.ingestion` owns reusable scrape, save, chunk, embed, bulk index, mark indexed, and reporting implementation.
- `api.knowledge_graph` owns Neo4j connectivity, triple extraction, and KG ingestion.
- `api.observability` owns metrics and tracing helpers.
- `api.platform` owns settings, service construction, app lifespan wiring, and dependency startup.

Existing import paths under `api.services.*` and orchestrator DAG modules remain as compatibility shims until callers and tests migrate.

## Consequences

Callers should depend on domain interfaces, not backend-specific setup details. Orchestrators should become runtime adapters over reusable ingestion functions. Refactoring must preserve route paths, payloads, environment variable names, Docker behavior, and UI behavior.
