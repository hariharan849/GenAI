import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

# psycopg's async mode cannot run on Windows' default ProactorEventLoop — it
# requires a selector-based loop. Must be set before uvicorn/asyncio creates
# the event loop, so this runs at import time, ahead of the FastAPI app object.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from prometheus_fastapi_instrumentator import Instrumentator
import psycopg.errors
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from api import metrics  # noqa: F401 — registers all Prometheus metric singletons
from api.config import get_settings
from api.db.factory import make_database
from api.middlewares import MetricsMiddleware
from api.routers import agentic_ask, hybrid_search, ping
from api.routers.ask import ask_router, stream_router
from api.services.agents.factory import make_agentic_rag_service
from api.services.cache.factory import make_cache_client
from api.services.embeddings.factory import make_embeddings_service
from api.services.graph.factory import make_neo4j_client
from api.services.langfuse.factory import make_langfuse_tracer
from api.services.ollama.factory import make_ollama_client
from api.services.opensearch.factory import make_opensearch_client

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan for the API.
    """
    logger.info("Starting RAG API...")

    settings = get_settings()
    app.state.settings = settings

    database = make_database()
    app.state.database = database
    logger.info("Database connected")

    # Initialize search service
    opensearch_client = make_opensearch_client()
    app.state.opensearch_client = opensearch_client

    # Verify OpenSearch connectivity and create index if needed
    if opensearch_client.health_check():
        logger.info("OpenSearch connected successfully")

        # Setup hybrid index (supports all search types)
        setup_results = opensearch_client.setup_indices(force=False)
        if setup_results.get("hybrid_index"):
            logger.info("Hybrid index created")
        else:
            logger.info("Hybrid index already exists")

        # Get simple statistics
        try:
            stats = opensearch_client.client.count(index=opensearch_client.index_name)
            logger.info(f"OpenSearch ready: {stats['count']} documents indexed")
        except Exception:
            logger.info("OpenSearch index ready (stats unavailable)")
    else:
        logger.warning("OpenSearch connection failed - search features will be limited")

    app.state.embeddings_service = make_embeddings_service()
    app.state.ollama_client = make_ollama_client()
    app.state.langfuse_tracer = make_langfuse_tracer()
    app.state.cache_client = make_cache_client(settings)
    logger.info("Services initialized: OpenSearch, Embeddings, Ollama, Langfuse, Cache")

    # Neo4j knowledge graph (optional — graceful degradation if disabled)
    graph_client = make_neo4j_client()
    app.state.graph_client = graph_client
    if graph_client is not None:
        reachable = await graph_client.verify_connectivity()
        if reachable:
            count = await graph_client.node_count()
            logger.info(f"Neo4j connected — {count} NukeNode(s) in graph")
        else:
            logger.warning("Neo4j enabled but unreachable — KG retrieval disabled for this session")
            graph_client = None
            app.state.graph_client = None

    # Build known_nodes frozenset from DB for entity matching in retrieve_papers
    known_nodes: frozenset[str] = frozenset()
    try:
        from api.repositories.nuke_page import NukePageRepository
        with database.get_session() as session:
            repo = NukePageRepository(session)
            node_names = repo.get_distinct_node_names()
            known_nodes = frozenset(node_names)
        logger.info(f"Loaded {len(known_nodes)} known Nuke node names for KG entity matching")
    except Exception as e:
        logger.warning(f"Could not load known_nodes from DB (KG entity matching disabled): {e}")
    app.state.known_nodes = known_nodes

    # LangGraph checkpointer pool — owned here (connect/setup/disconnect), not by
    # AgenticRAGService, so it survives across the per-request dependency lookups
    # and is sized explicitly (separate from the sync psycopg2 pool used for paper
    # metadata, so the two drivers don't silently compete for max_connections).
    # psycopg3 requires a plain postgresql:// URI — strip the SQLAlchemy driver suffix.
    psycopg_conninfo = settings.postgres_psycopg_url
    checkpointer_connection_kwargs = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
    async with AsyncConnectionPool(
        conninfo=psycopg_conninfo,
        kwargs=checkpointer_connection_kwargs,
        max_size=settings.postgres_checkpointer_pool_size,
        open=False,
    ) as checkpointer_pool:
        await checkpointer_pool.open(wait=True)
        checkpointer = AsyncPostgresSaver(checkpointer_pool)
        try:
            await checkpointer.setup()
        except psycopg.errors.UniqueViolation:
            pass  # schema already exists from a previous run; safe to ignore
        app.state.checkpointer = checkpointer
        logger.info(f"Checkpointer ready (Postgres pool size={settings.postgres_checkpointer_pool_size})")

        app.state.agentic_rag_service = make_agentic_rag_service(
            opensearch_client=app.state.opensearch_client,
            ollama_client=app.state.ollama_client,
            embeddings_client=app.state.embeddings_service,
            langfuse_tracer=app.state.langfuse_tracer,
            checkpointer=checkpointer,
            graph_client=app.state.graph_client,
            known_nodes=app.state.known_nodes,
        )
        logger.info("Agentic RAG service initialized (built once, not per-request)")

        logger.info("API ready")
        yield

    if app.state.graph_client is not None:
        await app.state.graph_client.close()
    database.teardown()
    logger.info("API shutdown complete")


app = FastAPI(
    title="Nuke Documentation RAG API",
    description="Nuke documentation search and question answering with RAG capabilities",
    version=os.getenv("APP_VERSION", "0.1.0"),
    lifespan=lifespan,
)

app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator(
    should_group_status_codes=True,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics"],
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# Include routers
app.include_router(ping.router, prefix="/api/v1")  # Health check endpoint
app.include_router(hybrid_search.router, prefix="/api/v1")  # Search chunks with BM25/hybrid
app.include_router(ask_router, prefix="/api/v1")  # RAG question answering with LLM
app.include_router(stream_router, prefix="/api/v1")  # Streaming RAG responses
app.include_router(agentic_ask.router)  # Agentic RAG with intelligent retrieval


if __name__ == "__main__":
    uvicorn.run(app, port=8083, host="0.0.0.0")
