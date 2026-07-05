# Graph Report - RAG  (2026-07-05)

## Corpus Check
- 241 files · ~67,032 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1506 nodes · 3201 edges · 108 communities (94 shown, 14 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 166 edges (avg confidence: 0.57)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `386d9e62`
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
- [[_COMMUNITY_persistence.py|persistence.py]]
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
- [[_COMMUNITY_test_graph_ingestion.py|test_graph_ingestion.py]]
- [[_COMMUNITY_nuke_docs_ingestion.py|nuke_docs_ingestion.py]]
- [[_COMMUNITY_extraction.py|extraction.py]]
- [[_COMMUNITY_TestUpsertPages|TestUpsertPages]]
- [[_COMMUNITY_nuke_docs_ingestion.py|nuke_docs_ingestion.py]]
- [[_COMMUNITY_LangfuseTracer|LangfuseTracer]]
- [[_COMMUNITY_metrics.py|metrics.py]]
- [[_COMMUNITY_test_neo4j_client.py|test_neo4j_client.py]]
- [[_COMMUNITY_make_neo4j_client|make_neo4j_client]]
- [[_COMMUNITY_.end_span|.end_span]]
- [[_COMMUNITY___init__.py|__init__.py]]
- [[_COMMUNITY_test_tracing.py|test_tracing.py]]
- [[_COMMUNITY_create_retriever_tool|create_retriever_tool]]
- [[_COMMUNITY_Domain Context|Domain Context]]
- [[_COMMUNITY_test_agentic_rag_thread_id.py|test_agentic_rag_thread_id.py]]
- [[_COMMUNITY___init__.py|__init__.py]]
- [[_COMMUNITY___init__.py|__init__.py]]
- [[_COMMUNITY___init__.py|__init__.py]]
- [[_COMMUNITY___init__.py|__init__.py]]
- [[_COMMUNITY_Config|Config]]
- [[_COMMUNITY_.find_cached_response|.find_cached_response]]

## God Nodes (most connected - your core abstractions)
1. `Settings` - 64 edges
2. `NukePageRepository` - 45 edges
3. `get_settings()` - 42 edges
4. `Context` - 41 edges
5. `AgentState` - 39 edges
6. `AskRequest` - 38 edges
7. `JinaEmbeddingsClient` - 35 edges
8. `GuardrailPolicyService` - 33 edges
9. `AgenticRAGService` - 32 edges
10. `OllamaClient` - 32 edges

## Surprising Connections (you probably didn't know these)
- `_SessionContext` --uses--> `SearchSettings`  [INFERRED]
  tests/test_search_backend.py → api/config.py
- `_SearchClient` --uses--> `RedisSettings`  [INFERRED]
  tests/test_semantic_cache.py → api/config.py
- `_SessionContext` --uses--> `Settings`  [INFERRED]
  tests/test_search_backend.py → api/config.py
- `_SearchClient` --uses--> `Settings`  [INFERRED]
  tests/test_semantic_cache.py → api/config.py
- `TestUpsertPages` --uses--> `NukePage`  [INFERRED]
  tests/test_nuke_page_repository.py → api/models/nuke_page.py

## Import Cycles
- 1-file cycle: `api/routers/__init__.py -> api/routers/__init__.py`

## Communities (108 total, 14 thin omitted)

### Community 0 - "AgentState"
Cohesion: 0.17
Nodes (25): Context, Runtime context for agent dependencies.      This contains immutable dependencie, ainvoke_grade_documents_step(), Grade retrieved documents for relevance using LLM.      This function uses an LL, ainvoke_input_guardrail_step(), continue_after_input_guardrail(), Route unsafe input to the dedicated safety refusal node., Run Presidio privacy redaction and Llama Guard input safety. (+17 more)

### Community 1 - "BaseModel"
Cohesion: 0.11
Nodes (19): OpenSearch search backend exports., make_embeddings_client(), Factory function to create embeddings client.      Creates a new client instance, make_hybrid_indexing_service(), Factory function to create hybrid indexing service.      Creates a new service i, OpenSearchClient, Unified OpenSearch client supporting both simple BM25 and hybrid search., Create RRF search pipeline for native hybrid search.          :param force: If T (+11 more)

### Community 2 - "OpenSearchClient"
Cohesion: 0.08
Nodes (21): Any, BM25 search for papers., Pure vector search on chunks.          :param query_embedding: Query embedding v, Unified search method supporting BM25, vector, and hybrid modes.          :param, Pure BM25 search implementation., Native OpenSearch hybrid search with RRF pipeline., Hybrid search combining BM25 and vector similarity using native RRF., Index a single chunk with its embedding.          :param chunk_data: Chunk data (+13 more)

### Community 3 - "OllamaClient"
Cohesion: 0.13
Nodes (22): get_ollama_client(), Get Ollama client from the request state., LLMException, OllamaConnectionError, OllamaException, OllamaTimeoutError, Base exception for LLM-related errors., Exception raised for Ollama service errors. (+14 more)

### Community 4 - "extract_triples"
Cohesion: 0.11
Nodes (24): GuardrailsSettings, Privacy and safety guardrail services., LlamaGuardClassifier, Llama Guard classifier backed by the local Ollama API., GuardrailLayer, LlamaGuardResult, PiiRedactionResult, PolicyAction (+16 more)

### Community 5 - "get_settings"
Cohesion: 0.18
Nodes (20): get_settings(), main(), _print_score_table(), CaseResult, Run the eval harness end to end against /ask-agentic and print + persist results, lifespan(), _load_graph_client(), _load_known_nodes() (+12 more)

### Community 6 - "NukePageRepository"
Cohesion: 0.10
Nodes (13): Update a record by ID., NukePage, _compute_minhash(), NukePageRepository, Session, MinHash, save_nuke_pages(), _make_nuke_page() (+5 more)

### Community 7 - "eval.py"
Cohesion: 0.18
Nodes (23): GoldenCase, load_golden_dataset(), A single hand-curated RAG eval case, pinned to an already-indexed Nuke docs page, Load golden eval cases from a YAML file.      :param path: Path to the golden da, _build_metrics(), CaseResult, Run harness from pre-loaded cases. Called by the eval router (cases already pars, Run every golden case in the dataset through the pipeline and score it.      :pa (+15 more)

### Community 8 - "LangfuseTracer"
Cohesion: 0.08
Nodes (17): LangfuseTracer, Any, Context manager to wrap LangGraph agent execution with a top-level trace span., Create a top-level trace for a RAG request., Create a child span on an existing trace. Returns the span or None., Get the current trace ID from Langfuse context.          In Langfuse v3, the Cal, Submit user feedback for a trace (following Langfuse cookbook pattern)., Fetch a versioned prompt from Langfuse.          Returns the Langfuse prompt obj (+9 more)

### Community 9 - "dependencies.py"
Cohesion: 0.10
Nodes (22): get_agentic_rag_service(), get_cache_client(), get_database(), get_db_session(), get_embeddings_service(), get_langfuse_tracer(), get_opensearch_client(), get_search_client() (+14 more)

### Community 10 - "Dagster Orchestrator"
Cohesion: 0.07
Nodes (25): Airflow Orchestrator, Containers, DAG, Directory Structure, Environment Variables, Starting, Assets, Containers (+17 more)

### Community 11 - "make_database"
Cohesion: 0.21
Nodes (14): ask_question(), ask_question_stream(), DatabaseDep, EmbeddingsDep, LangfuseDep, SearchDep, SemanticCacheDep, SessionDep (+6 more)

### Community 12 - "AskRequest"
Cohesion: 0.23
Nodes (9): ensure_nuke_page_kg_columns(), ensure_search_parent_child_columns(), Patch existing nuke_pages tables with KG state columns., Patch existing search tables for parent-child retrieval metadata., Initialize the database connection., Connection, Engine, main() (+1 more)

### Community 13 - "test_eval_router.py"
Cohesion: 0.08
Nodes (29): metrics_endpoint(), Response, MetricsMiddleware, Request, Response, Logs every request with method, path, status code, and duration., configure_event_loop_policy(), configure_prometheus_registry() (+21 more)

### Community 14 - "SemanticCacheClient"
Cohesion: 0.19
Nodes (7): _decode(), Any, Final-answer semantic cache using Redis Stack vector search., Answer-shaping fields that must match before a cached answer is valid., SemanticCacheClient, SemanticCacheScope, _vector_bytes()

### Community 15 - "indexing.py"
Cohesion: 0.06
Nodes (52): parse_optional_uuid(), UUID, make_child_chunk_id(), make_parent_doc_id(), make_recursive_splitter(), PostgresParentDocumentStore, Any, Document (+44 more)

### Community 16 - "BaseDatabase"
Cohesion: 0.18
Nodes (16): hybrid_search(), EmbeddingsDep, SearchDep, Hybrid search endpoint supporting multiple search modes., Config, HybridSearchRequest, Request model for hybrid search supporting all search modes., Individual search result from Nuke documentation. (+8 more)

### Community 17 - "AgenticRAGService"
Cohesion: 0.24
Nodes (17): _eval_runs_state(), EvalRunDetail, EvalRunStartResponse, EvalRunStatusResponse, EvalRunSummary, get_run(), get_run_status(), list_runs() (+9 more)

### Community 18 - "PostgresEmbeddingSearchClient"
Cohesion: 0.39
Nodes (7): make_cache_client(), make_redis_client(), make_semantic_cache_client(), Redis, Create Redis client with connection pooling., Create exact match cache client., Create semantic cache client when enabled.      Capability/index setup is async

### Community 19 - "agentic_rag.py"
Cohesion: 0.15
Nodes (15): health_check(), DatabaseDep, SearchDep, SettingsDep, Comprehensive health check endpoint for monitoring and load balancer probes., Config, HealthResponse, Health check response model. (+7 more)

### Community 20 - "scrape_nuke_reference_guide"
Cohesion: 0.07
Nodes (28): Knowledge graph ingestion task helpers., Knowledge graph ingestion exports., Knowledge graph domain package., BeautifulSoup, cleanup_nuke_temp(), Delete the temp file written by scrape_nuke_docs, plus any orphaned files older, Airflow compatibility wrapper for KG ingestion tasks., generate_nuke_report() (+20 more)

### Community 21 - "TelegramBot"
Cohesion: 0.15
Nodes (16): get_database(), get_db_session(), Get or create database instance., Get a database session context manager., make_database(), Factory function to create a database instance.      :returns: An instance of th, _load_unindexed_pages_from_db(), Load unindexed Nuke pages from PostgreSQL as plain dicts.      Creates its own D (+8 more)

### Community 22 - "dependencies"
Cohesion: 0.09
Nodes (21): dependencies, @copilotkit/react-core, @copilotkit/react-ui, @copilotkit/runtime, next, openai, react, react-dom (+13 more)

### Community 23 - "RAGTracer"
Cohesion: 0.08
Nodes (18): Observability helpers., Tracing helper exports., _extract_sources(), _generate_query_embedding(), _prepare_chunks_and_sources(), Retrieve and prepare chunks for RAG with clean tracing., RAGTracer, Simple, efficient Langfuse tracing utility for RAG pipeline. (+10 more)

### Community 24 - "compilerOptions"
Cohesion: 0.10
Nodes (19): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+11 more)

### Community 25 - "ask.py"
Cohesion: 0.29
Nodes (14): SearchSettings, AskResponse, Response model for RAG question answering., build_semantic_scope(), SearchClient, Build the cache scope from every field that can shape the final answer., SemanticCacheBypass, _SearchClient (+6 more)

### Community 26 - "RAGCopilot.tsx"
Cohesion: 0.14
Nodes (11): ChatProvider, PROVIDERS, AgentSteps(), AgentStepsProps, NukeResults(), SearchHit, KnowledgeSource, Message (+3 more)

### Community 27 - "ask.py"
Cohesion: 0.13
Nodes (24): _build_user_metadata(), Any, Session, RAGInteractionRepository, record_rag_interaction(), ask_agentic(), AgenticRAGDep, LangfuseDep (+16 more)

### Community 28 - "JinaEmbeddingsClient"
Cohesion: 0.14
Nodes (14): JinaEmbeddingRequest, JinaEmbeddingResponse, JinaRerankRequest, JinaRerankResponse, Response model from Jina embeddings API., Request model for Jina rerank API., Response model from Jina rerank API., Request model for Jina embeddings API. (+6 more)

### Community 29 - "CLAUDE.md"
Cohesion: 0.12
Nodes (14): Agentic RAG Workflow (LangGraph), Architecture, Configuration, Core Technology Choices, Data Models, Development Environment, graphify, Ingestion Pipelines (+6 more)

### Community 30 - "Settings"
Cohesion: 0.13
Nodes (17): psycopg3-compatible URL — strips the SQLAlchemy driver prefix (+psycopg2), Settings, get_request_settings(), get_settings(), Get application settings., Get settings from the request state., make_search_client(), make_search_client_fresh() (+9 more)

### Community 31 - "Neo4jClient"
Cohesion: 0.09
Nodes (17): Knowledge graph client exports., Any, SearchClient, # NOTE: top_k is baked in here as a closure constant at service-init, # IMPORTANT: CallbackHandler automatically inherits the current span context, GraphConfig, Configuration for the entire graph execution.      This is the configuration use, Redis Stack-backed semantic cache for final RAG answers.  The cache is deliberat (+9 more)

### Community 32 - "Terraform Infrastructure — Nuke RAG Stack"
Cohesion: 0.18
Nodes (11): Debugging a failed boot, Independent redeploy, Prerequisites, Step 0 — Seed SSM secrets (once), Step 1 — Bootstrap (once), Step 2 — Configure each layer, Step 3 — Split docker-compose (code change), Step 4 — Deploy in order (+3 more)

### Community 33 - "test_agentic_rag_thread_id.py"
Cohesion: 0.11
Nodes (12): AgenticRAGService, Ask a question using agentic RAG.          :param query: User question, Execute the workflow with the given trace context., Agentic RAG service      This implementation uses:     - context_schema for d, Extract final answer from graph result., Tell API consumers which guardrail layer rejected the request, if any., Extract retrieved chunk text from graph result, for eval/RAG-metric use., Extract sources from graph result. (+4 more)

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

### Community 38 - "persistence.py"
Cohesion: 0.18
Nodes (15): aggregate_scores(), compare(), main(), Average each metric across scored cases in a run. Errored cases are excluded., Diff aggregate metric scores between two runs.      :param threshold: Absolute d, _git_commit_hash(), latest_run(), load_run() (+7 more)

### Community 39 - "nuke_ingestion.py"
Cohesion: 0.38
Nodes (5): NukeDocChunk, NukeParentDocument, RAGInteraction, PostgreSQL pg_embedding-backed search client., Base

### Community 42 - "page.tsx"
Cohesion: 0.22
Nodes (5): CaseResult, RunDetail, RunStatus, RunSummary, Scores

### Community 43 - "TestUpsertPages"
Cohesion: 0.17
Nodes (9): Service for chunking text into overlapping segments.      Uses word-based chunki, Chunk a list of sections, preserving section boundaries.          Each section i, Initialize text chunker.          :param chunk_size: Target number of words per, Split text into words while preserving whitespace information., Reconstruct text from words., Chunk text into overlapping segments.          :param text: Full text to chunk, TextChunker, TestChunkSections (+1 more)

### Community 44 - "route.ts"
Cohesion: 0.25
Nodes (4): ALLOWED_SOURCES, FASTAPI_ROUTES, KnowledgeSource, tools

### Community 45 - "Agentic RAG — LangGraph Workflow"
Cohesion: 0.33
Nodes (6): Agentic RAG - LangGraph Workflow, Guardrail Split, Key Files, Node Reference, State Notes, Workflow

### Community 46 - "[Unreleased] - 2026-06-28"
Cohesion: 0.29
Nodes (6): Added, Changed, Changelog, Fixed, Removed, [Unreleased] - 2026-06-28

### Community 47 - "Monitoring Stack"
Cohesion: 0.25
Nodes (7): Alertmanager, Components, Grafana, Loki + Promtail, Monitoring Stack, Prometheus, StatsD

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
Cohesion: 0.14
Nodes (25): ainvoke_generate_answer_step(), AIMessage, Generate final answer using retrieved documents.      This node generates a comp, ainvoke_guardrail_llm(), Any, Run a guardrail LLM scoring call with Langfuse tracing and graceful fallback., ainvoke_intent_classify_step(), Classify whether the query needs retrieval, before paying for a     retrieval+gr (+17 more)

### Community 57 - "route.ts"
Cohesion: 0.60
Nodes (4): GET(), POST(), proxyToFastAPI(), RouteContext

### Community 58 - "OpenAIChat.tsx"
Cohesion: 0.11
Nodes (19): ChunkingSettings, deterministic_chunk_id(), PostgresEmbeddingSearchClient, Any, Search client using PostgreSQL full-text search and pg_embedding HNSW., Compatibility shim for the Postgres search backend., _bulk_client(), _chunk() (+11 more)

### Community 61 - "TODOS"
Cohesion: 0.11
Nodes (23): GradeDocuments, GradingResult, Binary score for document relevance check.      :param binary_score: Relevance s, Artifact returned by tool calls with metadata.      :param tool_name: Name of th, Routing decision for graph navigation.      :param route: The next node to route, Result of document grading with details.      :param document_id: Identifier for, A reasoning step in the agent workflow.      :param step_name: Name of the step/, ReasoningStep (+15 more)

### Community 86 - "config.py"
Cohesion: 0.39
Nodes (6): BaseConfigSettings, EvalSettings, LangfuseSettings, Neo4jSettings, OpenSearchSettings, DeepEval RAG evaluation harness settings.      The judge LLM is intentionally se

### Community 87 - "test_graph_ingestion.py"
Cohesion: 0.33
Nodes (6): AssetExecutionContext, extracted_nuke_kg(), indexed_nuke_docs(), nuke_ingestion_report(), saved_nuke_pages(), scraped_nuke_pages()

### Community 88 - "nuke_docs_ingestion.py"
Cohesion: 0.09
Nodes (19): ABC, BaseDatabase, BaseRepository, Any, Session, Initialize the database connection., Close the database connection., Get a database session. (+11 more)

### Community 89 - "extraction.py"
Cohesion: 0.14
Nodes (19): GuardrailScoring, Any, Source item from retrieved documents.      :param url: Link to the documentation, Convert to dictionary for JSON serialization., Scoring result of a user query for guardrail validation.      :param score: Rele, SourceItem, ainvoke_output_guardrail_step(), _check_source_grounding() (+11 more)

### Community 91 - "nuke_docs_ingestion.py"
Cohesion: 0.14
Nodes (12): RAGResponse, Pydantic models for Ollama structured outputs., Structured response model for RAG queries., Any, RAGPromptBuilder, Extract JSON from response text as fallback.          Args:             response, Builder class for creating RAG prompts., Initialize the prompt builder. (+4 more)

### Community 92 - "LangfuseTracer"
Cohesion: 0.06
Nodes (48): Session, Get a database session., ConfigurationError, OpenSearchException, Base exception for repository-related errors., Exception raised when configuration is invalid., Base exception for OpenSearch-related errors., RepositoryException (+40 more)

### Community 93 - "metrics.py"
Cohesion: 0.40
Nodes (3): Render all registered Prometheus metrics for the /metrics endpoint., render_metrics(), Prometheus metric exports.

### Community 94 - "test_neo4j_client.py"
Cohesion: 0.50
Nodes (3): ChunkIndexPayload, Shared search indexing payloads., Backend-neutral chunk payload accepted by search clients.

### Community 95 - "make_neo4j_client"
Cohesion: 0.18
Nodes (13): Knowledge graph factory exports., build_agentic_rag_graph(), Any, BaseCheckpointSaver, Build the shared Agentic RAG graph topology., _build_local_graph(), Local LangGraph dev-server entrypoint., _route_with_context() (+5 more)

### Community 96 - ".end_span"
Cohesion: 0.33
Nodes (5): 0001 Modular Architecture, Consequences, Context, Decision, Status

### Community 98 - "test_tracing.py"
Cohesion: 0.23
Nodes (8): FakePrompt, FakeTracer, runtime(), test_create_node_span_creates_span_when_enabled(), test_create_node_span_returns_none_when_disabled(), test_fetch_prompt_falls_back_without_tracer(), test_finish_node_span_adds_execution_time_and_ends_span(), test_start_generation_returns_noop_context_without_tracer()

### Community 99 - "create_retriever_tool"
Cohesion: 0.15
Nodes (12): create_parent_document_retriever(), BaseCheckpointSaver, SearchClient, Initialize agentic RAG service.          :param opensearch_client: Client for, Build and compile the LangGraph workflow.          Uses context_schema for typ, create_retriever_tool(), SearchClient, Create a retriever tool combining hybrid search and Neo4j KG.      :param opense (+4 more)

### Community 100 - "Domain Context"
Cohesion: 0.50
Nodes (3): Compatibility Rule, Domain Context, Vocabulary

### Community 101 - "test_agentic_rag_thread_id.py"
Cohesion: 0.25
Nodes (10): _make_service(), Regression tests for the thread_id / checkpointer config-key fix.  Mandatory per, Build an AgenticRAGService with mocked clients (no real I/O)., LangGraph reads thread_id from config['configurable'], not the top level., thread_id must be derived from user_id, not a per-call timestamp., An explicit session_id must produce a different thread_id for the same user., test_different_users_get_different_thread_ids(), test_session_id_starts_a_fresh_thread() (+2 more)

### Community 105 - "__init__.py"
Cohesion: 0.67
Nodes (3): get_latest_documents(), Document, Get the structured documents from the most recent tool call.      Reads ``ToolMe

### Community 106 - "Config"
Cohesion: 0.70
Nodes (4): _extract_kg_for_indexed_pages(), _normalize_page_ids(), UUID, Extract KG triples for indexed pages that have not already been processed.

### Community 107 - ".find_cached_response"
Cohesion: 0.23
Nodes (8): RedisSettings, CacheClient, Redis, Redis-based exact match cache for RAG queries., Generate exact cache key based on request parameters., Find cached response for exact query match., Store response for exact query matching., test_exact_cache_key_includes_knowledge_source()

## Knowledge Gaps
- **177 isolated node(s):** `Config`, `Config`, `Config`, `dependencies`, `agentic_rag` (+172 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Settings` to `BaseModel`, `create_retriever_tool`, `OllamaClient`, `get_settings`, `nuke_ingestion.py`, `LangfuseTracer`, `SemanticCacheClient`, `indexing.py`, `PostgresEmbeddingSearchClient`, `config.py`, `route.ts`, `ask.py`, `OpenAIChat.tsx`, `make_neo4j_client`, `Neo4jClient`?**
  _High betweenness centrality (0.093) - this node is a cross-community bridge._
- **Why does `AgenticRAGService` connect `test_agentic_rag_thread_id.py` to `AgentState`, `create_retriever_tool`, `extract_triples`, `get_settings`, `test_agentic_rag_thread_id.py`, `eval.py`, `dependencies.py`, `JinaEmbeddingsClient`, `Neo4jClient`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Why does `LangfuseTracer` connect `LangfuseTracer` to `AgentState`, `create_retriever_tool`, `get_settings`, `dependencies.py`, `RAGTracer`, `Settings`, `Neo4jClient`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `Settings` (e.g. with `PostgresParentDocumentStore` and `SearchClientVectorStore`) actually correct?**
  _`Settings` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `Context` (e.g. with `AgenticRAGService` and `SearchClient`) actually correct?**
  _`Context` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `AgentState` (e.g. with `AgenticRAGService` and `_StaticRuntime`) actually correct?**
  _`AgentState` has 7 INFERRED edges - model-reasoned connections that need verification._
- **What connects `DeepEval RAG evaluation harness settings.      The judge LLM is intentionally se`, `psycopg3-compatible URL — strips the SQLAlchemy driver prefix (+psycopg2)`, `Get or create database instance.` to the rest of the system?**
  _492 weakly-connected nodes found - possible documentation gaps or missing edges._