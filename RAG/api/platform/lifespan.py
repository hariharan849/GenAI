"""FastAPI lifespan and service construction."""

import logging
from contextlib import asynccontextmanager

import psycopg.errors
from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from api.config import get_settings
from api.db.factory import make_database
from api.repositories.nuke_page import NukePageRepository
from api.search.factory import make_search_client
from api.services.agents.factory import make_agentic_rag_service
from api.services.cache.factory import make_cache_client, make_semantic_cache_client
from api.services.embeddings.factory import make_embeddings_service
from api.services.graph.factory import make_neo4j_client
from api.services.langfuse.factory import make_langfuse_tracer
from api.services.ollama.factory import make_ollama_client

logger = logging.getLogger(__name__)


async def _load_graph_client(app: FastAPI):
    graph_client = make_neo4j_client()
    app.state.graph_client = graph_client
    if graph_client is None:
        return None

    reachable = await graph_client.verify_connectivity()
    if reachable:
        count = await graph_client.node_count()
        logger.info("Neo4j connected - %s NukeNode(s) in graph", count)
        return graph_client

    logger.warning("Neo4j enabled but unreachable - KG retrieval disabled for this session")
    app.state.graph_client = None
    return None


def _load_known_nodes(database) -> frozenset[str]:
    try:
        with database.get_session() as session:
            repo = NukePageRepository(session)
            node_names = repo.get_distinct_node_names()
        logger.info("Loaded %d known Nuke node names for KG entity matching", len(node_names))
        return frozenset(node_names)
    except Exception as e:
        logger.warning("Could not load known_nodes from DB (KG entity matching disabled): %s", e)
        return frozenset()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting RAG API...")

    settings = get_settings()
    app.state.settings = settings
    app.state.eval_runs = {}

    database = make_database()
    app.state.database = database
    logger.info("Database connected")

    search_client = make_search_client(settings)
    app.state.search_client = search_client
    app.state.opensearch_client = search_client

    if search_client.health_check():
        logger.info("%s search backend connected successfully", search_client.backend_name)
        setup_results = search_client.setup_indices(force=False)
        logger.info("Search backend setup results: %s", setup_results)
        stats = search_client.get_index_stats()
        logger.info("%s search ready: %s chunks indexed", search_client.backend_name, stats.get("document_count", 0))
    else:
        logger.warning("%s search backend connection failed - search features will be limited", search_client.backend_name)

    app.state.embeddings_service = make_embeddings_service()
    app.state.ollama_client = make_ollama_client()
    app.state.langfuse_tracer = make_langfuse_tracer()
    app.state.cache_client = make_cache_client(settings)
    app.state.semantic_cache_client = make_semantic_cache_client(settings)
    if app.state.semantic_cache_client is not None:
        await app.state.semantic_cache_client.initialize()
    logger.info("Services initialized: Search, Embeddings, Ollama, Langfuse, Cache")

    graph_client = await _load_graph_client(app)
    app.state.known_nodes = _load_known_nodes(database)

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
            pass
        app.state.checkpointer = checkpointer
        logger.info("Checkpointer ready (Postgres pool size=%s)", settings.postgres_checkpointer_pool_size)

        app.state.agentic_rag_service = make_agentic_rag_service(
            search_client=app.state.search_client,
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

    if graph_client is not None:
        await graph_client.close()
    database.teardown()
    logger.info("API shutdown complete")
