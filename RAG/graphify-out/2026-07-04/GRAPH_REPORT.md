# Graph Report - RAG  (2026-07-04)

## Corpus Check
- 205 files · ~63,277 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1290 nodes · 2607 edges · 92 communities (80 shown, 12 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 125 edges (avg confidence: 0.57)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6a269539`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_AgentState|AgentState]]
- [[_COMMUNITY_BaseModel|BaseModel]]
- [[_COMMUNITY_OpenSearchClient|OpenSearchClient]]
- [[_COMMUNITY_OllamaClient|OllamaClient]]
- [[_COMMUNITY_extract_triples|extract_triples]]
- [[_COMMUNITY_get_settings|get_settings]]
- [[_COMMUNITY_NukePageRepository|NukePageRepository]]
- [[_COMMUNITY_eval.py|eval.py]]
- [[_COMMUNITY_LangfuseTracer|LangfuseTracer]]
- [[_COMMUNITY_dependencies.py|dependencies.py]]
- [[_COMMUNITY_Dagster Orchestrator|Dagster Orchestrator]]
- [[_COMMUNITY_make_database|make_database]]
- [[_COMMUNITY_AskRequest|AskRequest]]
- [[_COMMUNITY_test_eval_router.py|test_eval_router.py]]
- [[_COMMUNITY_SemanticCacheClient|SemanticCacheClient]]
- [[_COMMUNITY_indexing.py|indexing.py]]
- [[_COMMUNITY_BaseDatabase|BaseDatabase]]
- [[_COMMUNITY_AgenticRAGService|AgenticRAGService]]
- [[_COMMUNITY_PostgresEmbeddingSearchClient|PostgresEmbeddingSearchClient]]
- [[_COMMUNITY_agentic_rag.py|agentic_rag.py]]
- [[_COMMUNITY_scrape_nuke_reference_guide|scrape_nuke_reference_guide]]
- [[_COMMUNITY_TelegramBot|TelegramBot]]
- [[_COMMUNITY_dependencies|dependencies]]
- [[_COMMUNITY_RAGTracer|RAGTracer]]
- [[_COMMUNITY_compilerOptions|compilerOptions]]
- [[_COMMUNITY_ask.py|ask.py]]
- [[_COMMUNITY_RAGCopilot.tsx|RAGCopilot.tsx]]
- [[_COMMUNITY_ask.py|ask.py]]
- [[_COMMUNITY_JinaEmbeddingsClient|JinaEmbeddingsClient]]
- [[_COMMUNITY_CLAUDE|CLAUDE.md]]
- [[_COMMUNITY_Settings|Settings]]
- [[_COMMUNITY_Neo4jClient|Neo4jClient]]
- [[_COMMUNITY_Terraform Infrastructure — Nuke RAG Stack|Terraform Infrastructure — Nuke RAG Stack]]
- [[_COMMUNITY_test_agentic_rag_thread_id.py|test_agentic_rag_thread_id.py]]
- [[_COMMUNITY_TestSaveNukePages|TestSaveNukePages]]
- [[_COMMUNITY_UI — Next.js Frontend|UI — Next.js Frontend]]
- [[_COMMUNITY_Repository Guidelines|Repository Guidelines]]
- [[_COMMUNITY_API — FastAPI Backend|API — FastAPI Backend]]
- [[_COMMUNITY_.__init__|.__init__]]
- [[_COMMUNITY_nuke_ingestion.py|nuke_ingestion.py]]
- [[_COMMUNITY_nuke_docs_ingestion.py|nuke_docs_ingestion.py]]
- [[_COMMUNITY_page.tsx|page.tsx]]
- [[_COMMUNITY_TestUpsertPages|TestUpsertPages]]
- [[_COMMUNITY_route.ts|route.ts]]
- [[_COMMUNITY_Agentic RAG — LangGraph Workflow|Agentic RAG — LangGraph Workflow]]
- [[_COMMUNITY_Unreleased - 2026-06-28|[Unreleased] - 2026-06-28]]
- [[_COMMUNITY_Monitoring Stack|Monitoring Stack]]
- [[_COMMUNITY_Quick Start (Local)|Quick Start (Local)]]
- [[_COMMUNITY_Nuke RAG System|Nuke RAG System]]
- [[_COMMUNITY_Evaluation Harness|Evaluation Harness]]
- [[_COMMUNITY_Infrastructure|Infrastructure]]
- [[_COMMUNITY_langgraph.json|langgraph.json]]
- [[_COMMUNITY_hello_world.py|hello_world.py]]
- [[_COMMUNITY_Tests|Tests]]
- [[_COMMUNITY_route.ts|route.ts]]
- [[_COMMUNITY_route.ts|route.ts]]
- [[_COMMUNITY_OpenAIChat.tsx|OpenAIChat.tsx]]
- [[_COMMUNITY_conftest.py|conftest.py]]
- [[_COMMUNITY_TODOS|TODOS]]
- [[_COMMUNITY_check-stack.sh|check-stack.sh]]
- [[_COMMUNITY_layout.tsx|layout.tsx]]
- [[_COMMUNITY_entrypoint.sh|entrypoint.sh]]
- [[_COMMUNITY_entrypoint.sh|entrypoint.sh]]
- [[_COMMUNITY_next.config.ts|next.config.ts]]
- [[_COMMUNITY_rag|rag]]
- [[_COMMUNITY_POST|POST]]
- [[_COMMUNITY_config.py|config.py]]
- [[_COMMUNITY_LangfuseTracer|LangfuseTracer]]
- [[_COMMUNITY_factory.py|factory.py]]
- [[_COMMUNITY_.end_span|.end_span]]
- [[_COMMUNITY_.flush|.flush]]
- [[_COMMUNITY_.get_callback_handler|.get_callback_handler]]

## God Nodes (most connected - your core abstractions)
1. `Settings` - 52 edges
2. `NukePageRepository` - 45 edges
3. `AskRequest` - 38 edges
4. `get_settings()` - 35 edges
5. `AgentState` - 35 edges
6. `Context` - 34 edges
7. `AgenticRAGService` - 31 edges
8. `JinaEmbeddingsClient` - 30 edges
9. `LangfuseTracer` - 30 edges
10. `OllamaClient` - 28 edges

## Surprising Connections (you probably didn't know these)
- `_SearchClient` --uses--> `SearchSettings`  [INFERRED]
  tests/test_semantic_cache.py → api/config.py
- `_SearchClient` --uses--> `RedisSettings`  [INFERRED]
  tests/test_semantic_cache.py → api/config.py
- `_SessionContext` --uses--> `Settings`  [INFERRED]
  tests/test_search_backend.py → api/config.py
- `_SearchClient` --uses--> `Settings`  [INFERRED]
  tests/test_semantic_cache.py → api/config.py
- `TestChunkSections` --uses--> `NukePage`  [INFERRED]
  tests/test_semantic_chunking.py → api/models/nuke_page.py

## Import Cycles
- 1-file cycle: `api/routers/__init__.py -> api/routers/__init__.py`

## Communities (92 total, 12 thin omitted)

### Community 0 - "AgentState"
Cohesion: 0.06
Nodes (86): # NOTE: top_k is baked in here as a closure constant at service-init, # IMPORTANT: CallbackHandler automatically inherits the current span context, Context, Runtime context for agent dependencies.      This contains immutable dependencie, _build_local_graph(), Local LangGraph dev-server entrypoint.  This module is intentionally separate fr, _StaticRuntime, _with_context() (+78 more)

### Community 1 - "BaseModel"
Cohesion: 0.06
Nodes (37): hybrid_search(), EmbeddingsDep, SearchDep, Hybrid search endpoint supporting multiple search modes., Router modules for the RAG API., health_check(), DatabaseDep, SearchDep (+29 more)

### Community 2 - "OpenSearchClient"
Cohesion: 0.06
Nodes (29): OpenSearchClient, Any, Unified OpenSearch client supporting both simple BM25 and hybrid search., Create RRF search pipeline for native hybrid search.          :param force: If T, BM25 search for papers., Pure vector search on chunks.          :param query_embedding: Query embedding v, OpenSearch client supporting BM25 and hybrid search with native RRF., Unified search method supporting BM25, vector, and hybrid modes.          :param (+21 more)

### Community 3 - "OllamaClient"
Cohesion: 0.07
Nodes (40): ConfigurationError, LLMException, OllamaConnectionError, OllamaException, OllamaTimeoutError, OpenSearchException, Base exception for LLM-related errors., Exception raised for Ollama service errors. (+32 more)

### Community 4 - "extract_triples"
Cohesion: 0.07
Nodes (40): _dedupe_triples(), _extract_control_triples(), _extract_deterministic_triples(), _extract_input_triples(), _extract_section(), extract_triples(), _extraction_to_triple(), _input_object_name() (+32 more)

### Community 5 - "get_settings"
Cohesion: 0.15
Nodes (18): main(), _print_score_table(), CaseResult, Run the eval harness end to end against /ask-agentic and print + persist results, lifespan(), metrics_endpoint(), FastAPI, Response (+10 more)

### Community 6 - "NukePageRepository"
Cohesion: 0.07
Nodes (24): Update a record by ID., NukeDocChunk, NukePage, _compute_minhash(), NukePageRepository, Session, make_neo4j_client(), Return a Neo4jClient if Neo4j is enabled in settings, else None. (+16 more)

### Community 7 - "eval.py"
Cohesion: 0.07
Nodes (55): aggregate_scores(), compare(), main(), Average each metric across scored cases in a run. Errored cases are excluded., Diff aggregate metric scores between two runs.      :param threshold: Absolute d, GoldenCase, load_golden_dataset(), A single hand-curated RAG eval case, pinned to an already-indexed Nuke docs page (+47 more)

### Community 8 - "LangfuseTracer"
Cohesion: 0.18
Nodes (6): Any, Create a top-level trace for a RAG request., Create a child span on an existing trace. Returns the span or None., Start a generation span for LLM calls (following Langfuse cookbook pattern)., Start a generic span for non-LLM operations (following Langfuse cookbook pattern, Update a generation span with output and usage metrics.          Args:

### Community 9 - "dependencies.py"
Cohesion: 0.13
Nodes (22): get_agentic_rag_service(), get_cache_client(), get_database(), get_embeddings_service(), get_langfuse_tracer(), get_ollama_client(), get_opensearch_client(), get_request_settings() (+14 more)

### Community 10 - "Dagster Orchestrator"
Cohesion: 0.07
Nodes (25): Airflow Orchestrator, Containers, DAG, Directory Structure, Environment Variables, Starting, Assets, Containers (+17 more)

### Community 11 - "make_database"
Cohesion: 0.13
Nodes (20): Render all registered Prometheus metrics for the /metrics endpoint., render_metrics(), ask_question(), ask_question_stream(), _extract_sources(), _generate_query_embedding(), _prepare_chunks_and_sources(), DatabaseDep (+12 more)

### Community 12 - "AskRequest"
Cohesion: 0.36
Nodes (10): build_semantic_scope(), SearchClient, Build the cache scope from every field that can shape the final answer., _SearchClient, _settings(), test_semantic_cache_disabled_returns_bypass(), test_semantic_cache_endpoint_flags(), test_semantic_cache_hit_respects_distance_threshold() (+2 more)

### Community 13 - "test_eval_router.py"
Cohesion: 0.13
Nodes (21): MetricsMiddleware, Request, Response, Logs every request with method, path, status code, and duration., client(), _make_app(), FastAPI, Path (+13 more)

### Community 14 - "SemanticCacheClient"
Cohesion: 0.15
Nodes (13): AskResponse, Response model for RAG question answering., _decode(), Any, Redis, Redis Stack-backed semantic cache for final RAG answers.  The cache is deliberat, Final-answer semantic cache using Redis Stack vector search., Answer-shaping fields that must match before a cached answer is valid. (+5 more)

### Community 15 - "indexing.py"
Cohesion: 0.11
Nodes (27): make_database(), Factory function to create a database instance.      :returns: An instance of th, deterministic_chunk_id(), PostgreSQL pg_embedding-backed search client., _chunk_page_remote(), _doc_id(), _embed_batch_remote(), index_nuke_docs() (+19 more)

### Community 16 - "BaseDatabase"
Cohesion: 0.06
Nodes (31): ABC, BaseDatabase, BaseRepository, Any, Session, Initialize the database connection., Close the database connection., Get a database session. (+23 more)

### Community 17 - "AgenticRAGService"
Cohesion: 0.17
Nodes (6): Execute the workflow with the given trace context., Extract final answer from graph result., Tell API consumers which guardrail layer rejected the request, if any., Extract retrieved chunk text from graph result, for eval/RAG-metric use., Extract sources from graph result., Extract reasoning steps from graph result.

### Community 18 - "PostgresEmbeddingSearchClient"
Cohesion: 0.30
Nodes (3): PostgresEmbeddingSearchClient, Any, Search client using PostgreSQL full-text search and pg_embedding HNSW.

### Community 19 - "agentic_rag.py"
Cohesion: 0.15
Nodes (12): AgenticRAGService, Ask a question using agentic RAG.          :param query: User question         :, Agentic RAG service      This implementation uses:     - context_schema for depe, Get the LangGraph workflow visualization as PNG.          This method generates, Get the LangGraph workflow as a mermaid diagram string.          This method gen, Get ASCII representation of the graph.          This method generates a simple A, GraphConfig, Configuration for the entire graph execution.      This is the configuration use (+4 more)

### Community 20 - "scrape_nuke_reference_guide"
Cohesion: 0.06
Nodes (37): AssetExecutionContext, BeautifulSoup, cleanup_nuke_temp(), Delete the temp file written by scrape_nuke_docs, plus any orphaned files older, generate_nuke_report(), Log a summary of the Nuke docs ingestion run., _absolute(), _extract_node_links() (+29 more)

### Community 21 - "TelegramBot"
Cohesion: 0.50
Nodes (4): get_database(), get_db_session(), Get or create database instance., Get a database session context manager.

### Community 22 - "dependencies"
Cohesion: 0.09
Nodes (21): dependencies, @copilotkit/react-core, @copilotkit/react-ui, @copilotkit/runtime, next, openai, react, react-dom (+13 more)

### Community 23 - "RAGTracer"
Cohesion: 0.10
Nodes (11): RAGTracer, End generation span with response., Clean, purpose-built tracer for RAG operations., End main request trace., Main request trace context manager., Query embedding operation with timing., Search operation with timing., End search span with essential results. (+3 more)

### Community 24 - "compilerOptions"
Cohesion: 0.10
Nodes (19): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+11 more)

### Community 25 - "ask.py"
Cohesion: 0.23
Nodes (8): RedisSettings, CacheClient, Redis, Redis-based exact match cache for RAG queries., Generate exact cache key based on request parameters., Find cached response for exact query match., Store response for exact query matching., test_exact_cache_key_includes_knowledge_source()

### Community 26 - "RAGCopilot.tsx"
Cohesion: 0.25
Nodes (5): AgentSteps(), AgentStepsProps, NukeResults(), SearchHit, RAGCopilot()

### Community 27 - "ask.py"
Cohesion: 0.12
Nodes (25): RAGInteraction, _build_user_metadata(), Any, Session, RAGInteractionRepository, record_rag_interaction(), ask_agentic(), AgenticRAGDep (+17 more)

### Community 28 - "JinaEmbeddingsClient"
Cohesion: 0.12
Nodes (16): JinaEmbeddingRequest, JinaEmbeddingResponse, JinaRerankRequest, JinaRerankResponse, JinaRerankResultItem, Response model from Jina embeddings API., Request model for Jina rerank API., A single reranked result from Jina's rerank API. (+8 more)

### Community 29 - "CLAUDE.md"
Cohesion: 0.12
Nodes (14): Agentic RAG Workflow (LangGraph), Architecture, Configuration, Core Technology Choices, Data Models, Development Environment, graphify, Ingestion Pipelines (+6 more)

### Community 30 - "Settings"
Cohesion: 0.22
Nodes (11): psycopg3-compatible URL — strips the SQLAlchemy driver prefix (+psycopg2), Settings, get_settings(), Get application settings., make_cache_client(), make_redis_client(), make_semantic_cache_client(), Redis (+3 more)

### Community 31 - "Neo4jClient"
Cohesion: 0.22
Nodes (11): SearchSettings, make_search_client_fresh(), _bulk_client(), _chunk(), _SessionContext, test_deterministic_chunk_id_matches_existing_ingestion_semantics(), test_postgres_bulk_upsert_empty_batch(), test_postgres_bulk_upsert_partial_failure_reports_page_id() (+3 more)

### Community 32 - "Terraform Infrastructure — Nuke RAG Stack"
Cohesion: 0.18
Nodes (11): Debugging a failed boot, Independent redeploy, Prerequisites, Step 0 — Seed SSM secrets (once), Step 1 — Bootstrap (once), Step 2 — Configure each layer, Step 3 — Split docker-compose (code change), Step 4 — Deploy in order (+3 more)

### Community 33 - "test_agentic_rag_thread_id.py"
Cohesion: 0.25
Nodes (10): _make_service(), Regression tests for the thread_id / checkpointer config-key fix.  Mandatory per, Build an AgenticRAGService with mocked clients (no real I/O)., LangGraph reads thread_id from config['configurable'], not the top level., thread_id must be derived from user_id, not a per-call timestamp., An explicit session_id must produce a different thread_id for the same user., test_different_users_get_different_thread_ids(), test_session_id_starts_a_fresh_thread() (+2 more)

### Community 34 - "TestSaveNukePages"
Cohesion: 0.29
Nodes (5): _make_pages(), Tests for save_nuke_pages Airflow callable., Run save_nuke_pages with mocked DB and nuke_docs_ingestion module., TestSaveNukePages, _write_temp()

### Community 35 - "UI — Next.js Frontend"
Cohesion: 0.20
Nodes (9): Chat Providers, CopilotKit, Directory Structure, Docker, Environment Variables, Getting Started, Knowledge Source, OpenAI Responses API (+1 more)

### Community 36 - "Repository Guidelines"
Cohesion: 0.22
Nodes (8): Build, Test, and Development Commands, Coding Style & Naming Conventions, Commit & Pull Request Guidelines, graphify, Project Structure & Module Organization, Repository Guidelines, Security & Configuration Tips, Testing Guidelines

### Community 37 - "API — FastAPI Backend"
Cohesion: 0.22
Nodes (9): API — FastAPI Backend, Caching, Configuration, Directory Structure, Endpoints, Further Reading, Observability, Running Locally (+1 more)

### Community 38 - ".__init__"
Cohesion: 0.22
Nodes (7): BaseCheckpointSaver, SearchClient, Build and compile the LangGraph workflow.          Uses context_schema for type-, Initialize agentic RAG service.          :param opensearch_client: Client for do, create_retriever_tool(), SearchClient, Create a retriever tool combining hybrid search and Neo4j KG.      :param opense

### Community 39 - "nuke_ingestion.py"
Cohesion: 0.28
Nodes (3): Any, SearchClient, Protocol

### Community 42 - "page.tsx"
Cohesion: 0.22
Nodes (5): CaseResult, RunDetail, RunStatus, RunSummary, Scores

### Community 43 - "TestUpsertPages"
Cohesion: 0.16
Nodes (6): _fact_cypher(), Neo4jClient, Document, Merge typed graph facts into Neo4j. Returns facts written., Async Neo4j client for knowledge graph retrieval., Return 1-hop neighbours of a NukeNode as Documents.

### Community 44 - "route.ts"
Cohesion: 0.25
Nodes (4): ALLOWED_SOURCES, FASTAPI_ROUTES, KnowledgeSource, tools

### Community 45 - "Agentic RAG — LangGraph Workflow"
Cohesion: 0.29
Nodes (7): Agentic RAG — LangGraph Workflow, Configuration, Key Files, Node Reference, State Shape (`AgentState`), Thread ID / Checkpointing, Workflow

### Community 46 - "[Unreleased] - 2026-06-28"
Cohesion: 0.29
Nodes (6): Added, Changed, Changelog, Fixed, Removed, [Unreleased] - 2026-06-28

### Community 47 - "Monitoring Stack"
Cohesion: 0.29
Nodes (6): Components, Grafana, Loki + Promtail, Monitoring Stack, Prometheus, StatsD

### Community 48 - "Quick Start (Local)"
Cohesion: 0.29
Nodes (7): 1. Configure environment, 2. Start shared infrastructure, 3. Start an ingestion orchestrator (pick one), 4. Run the API, 5. Run the UI, Prerequisites, Quick Start (Local)

### Community 49 - "Nuke RAG System"
Cohesion: 0.29
Nodes (7): Architecture Overview, Deployment (AWS), Further Reading, Key Technology Choices, Nuke RAG System, Repository Layout, Service Ports

### Community 51 - "Evaluation Harness"
Cohesion: 0.33
Nodes (6): Configuration, Evaluation Harness, Files, Golden Dataset Format, Metrics, Running an Evaluation

### Community 52 - "Infrastructure"
Cohesion: 0.33
Nodes (6): AWS Deployment, Directory Structure, Infrastructure, Local Monitoring Stack, Nginx, Redis Cache Modes

### Community 53 - "langgraph.json"
Cohesion: 0.40
Nodes (4): dependencies, env, graphs, agentic_rag

### Community 54 - "hello_world.py"
Cohesion: 0.40
Nodes (4): check_services(), hello_world(), Simple hello world function., Check if other services are accessible.

### Community 55 - "Tests"
Cohesion: 0.40
Nodes (4): Configuration, Running Tests, Test Files, Tests

### Community 56 - "route.ts"
Cohesion: 0.40
Nodes (3): { handleRequest }, openai, serviceAdapter

### Community 57 - "route.ts"
Cohesion: 0.60
Nodes (4): GET(), POST(), proxyToFastAPI(), RouteContext

### Community 58 - "OpenAIChat.tsx"
Cohesion: 0.40
Nodes (3): KnowledgeSource, Message, OpenAIChatProps

### Community 61 - "TODOS"
Cohesion: 0.50
Nodes (3): TODO-1: KG Extraction — Extend to Prefect and Dagster Orchestrators, TODO-2: Triple Quality Evaluation — Semantic Correctness of Extracted Triples, TODOS

### Community 86 - "config.py"
Cohesion: 0.36
Nodes (7): BaseConfigSettings, ChunkingSettings, EvalSettings, LangfuseSettings, Neo4jSettings, OpenSearchSettings, DeepEval RAG evaluation harness settings.      The judge LLM is intentionally se

### Community 92 - "LangfuseTracer"
Cohesion: 0.18
Nodes (6): LangfuseTracer, Get the current trace ID from Langfuse context.          In Langfuse v3, the Cal, Submit user feedback for a trace (following Langfuse cookbook pattern)., Fetch a versioned prompt from Langfuse.          Returns the Langfuse prompt obj, Wrapper for Langfuse v3 tracing client with CallbackHandler support., Simple, efficient Langfuse tracing utility for RAG pipeline.

### Community 93 - "factory.py"
Cohesion: 0.20
Nodes (14): get_settings(), make_embeddings_client(), Factory function to create embeddings client.      Creates a new client instance, make_hybrid_indexing_service(), Factory function to create hybrid indexing service.      Creates a new service i, make_opensearch_client(), make_opensearch_client_fresh(), Unified factory for OpenSearch client. (+6 more)

## Knowledge Gaps
- **171 isolated node(s):** `Config`, `Config`, `Config`, `dependencies`, `agentic_rag` (+166 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Settings` to `AgentState`, `OpenSearchClient`, `OllamaClient`, `get_settings`, `dependencies.py`, `AskRequest`, `SemanticCacheClient`, `indexing.py`, `PostgresEmbeddingSearchClient`, `agentic_rag.py`, `config.py`, `LangfuseTracer`, `factory.py`, `Neo4jClient`?**
  _High betweenness centrality (0.117) - this node is a cross-community bridge._
- **Why does `AgenticRAGService` connect `agentic_rag.py` to `AgentState`, `test_agentic_rag_thread_id.py`, `.__init__`, `eval.py`, `nuke_ingestion.py`, `dependencies.py`, `AgenticRAGService`, `JinaEmbeddingsClient`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `get_settings()` connect `factory.py` to `extract_triples`, `get_settings`, `NukePageRepository`, `eval.py`, `indexing.py`, `BaseDatabase`, `agentic_rag.py`, `config.py`, `Settings`, `Neo4jClient`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Are the 12 inferred relationships involving `Settings` (e.g. with `GraphConfig` and `SemanticCacheBypass`) actually correct?**
  _`Settings` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `AskRequest` (e.g. with `RAGInteractionRepository` and `CacheClient`) actually correct?**
  _`AskRequest` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `AgentState` (e.g. with `AgenticRAGService` and `_StaticRuntime`) actually correct?**
  _`AgentState` has 7 INFERRED edges - model-reasoned connections that need verification._
- **What connects `DeepEval RAG evaluation harness settings.      The judge LLM is intentionally se`, `psycopg3-compatible URL — strips the SQLAlchemy driver prefix (+psycopg2)`, `Get or create database instance.` to the rest of the system?**
  _454 weakly-connected nodes found - possible documentation gaps or missing edges._