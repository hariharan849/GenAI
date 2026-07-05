"""Local LangGraph dev-server entrypoint."""

import asyncio
import sys

from api.config import get_settings
from api.search.factory import make_search_client
from api.services.agents.config import GraphConfig
from api.services.agents.context import Context
from api.services.agents.graph_builder import build_agentic_rag_graph
from api.services.agents.state import AgentState
from api.services.agents.tools import create_retriever_tool
from api.services.embeddings.factory import make_embeddings_client
from api.services.graph.factory import make_neo4j_client
from api.services.guardrails.factory import make_guardrail_policy_service
from api.services.ollama.factory import make_ollama_client

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class _StaticRuntime:
    def __init__(self, context: Context):
        self.context = context


def _with_context(node, runtime: _StaticRuntime):
    async def wrapped(state: AgentState):
        return await node(state, runtime)

    return wrapped


def _route_with_context(route, runtime: _StaticRuntime):
    def wrapped(state: AgentState):
        return route(state, runtime)

    return wrapped


def _build_local_graph():
    settings = get_settings()
    search_client = make_search_client(settings)
    embeddings_client = make_embeddings_client()
    ollama_client = make_ollama_client()
    guardrail_policy = make_guardrail_policy_service(settings, ollama_client)
    graph_client = make_neo4j_client()
    graph_config = GraphConfig()
    runtime = _StaticRuntime(
        Context(
            ollama_client=ollama_client,
            opensearch_client=search_client,
            embeddings_client=embeddings_client,
            langfuse_tracer=None,
            langfuse_enabled=False,
            model_name=graph_config.model,
            temperature=graph_config.temperature,
            top_k=graph_config.top_k,
            retrieval_top_k=graph_config.retrieval_top_k,
            rerank_top_k=graph_config.rerank_top_k,
            max_retrieval_attempts=graph_config.max_retrieval_attempts,
            guardrail_threshold=graph_config.guardrail_threshold,
            guardrail_policy=guardrail_policy,
        )
    )

    retriever_tool = create_retriever_tool(
        opensearch_client=search_client,
        embeddings_client=embeddings_client,
        top_k=graph_config.retrieval_top_k,
        use_hybrid=graph_config.use_hybrid,
        graph_client=graph_client,
        known_nodes=frozenset(),
    )

    return build_agentic_rag_graph(
        tools=[retriever_tool],
        wrap_node=lambda node: _with_context(node, runtime),
        wrap_route=lambda route: _route_with_context(route, runtime),
        use_context_schema=False,
    )


agentic_rag = _build_local_graph()
