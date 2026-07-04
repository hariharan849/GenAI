"""Local LangGraph dev-server entrypoint.

This module is intentionally separate from the FastAPI lifespan wiring. The
LangGraph CLI imports a module-level graph object from ``langgraph.json``, so
we build the same AgenticRAGService graph using the repo's existing factories.
"""

import asyncio
import sys

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from api.services.agents.config import GraphConfig
from api.services.agents.context import Context
from api.services.agents.nodes import (
    ainvoke_generate_answer_step,
    ainvoke_grade_documents_step,
    ainvoke_input_guardrail_step,
    ainvoke_intent_classify_step,
    ainvoke_out_of_scope_step,
    ainvoke_output_guardrail_step,
    ainvoke_rerank_step,
    ainvoke_retrieve_step,
    ainvoke_rewrite_query_step,
    continue_after_input_guardrail,
    continue_after_output_guardrail,
)
from api.services.agents.state import AgentState
from api.services.agents.tools import create_retriever_tool
from api.services.embeddings.factory import make_embeddings_client
from api.services.graph.factory import make_neo4j_client
from api.services.ollama.factory import make_ollama_client
from api.search.factory import make_search_client

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class _StaticRuntime:
    def __init__(self, context: Context):
        self.context = context


def _with_context(node, runtime: _StaticRuntime):
    async def wrapped(state: AgentState):
        return await node(state, runtime)

    return wrapped


def _build_local_graph():
    search_client = make_search_client()
    embeddings_client = make_embeddings_client()
    ollama_client = make_ollama_client()
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

    workflow = StateGraph(AgentState)
    workflow.add_node("input_guardrail", _with_context(ainvoke_input_guardrail_step, runtime))
    workflow.add_node("intent_classify", _with_context(ainvoke_intent_classify_step, runtime))
    workflow.add_node("out_of_scope", _with_context(ainvoke_out_of_scope_step, runtime))
    workflow.add_node("retrieve", _with_context(ainvoke_retrieve_step, runtime))
    workflow.add_node("tool_retrieve", ToolNode([retriever_tool]))
    workflow.add_node("rerank", _with_context(ainvoke_rerank_step, runtime))
    workflow.add_node("grade_documents", _with_context(ainvoke_grade_documents_step, runtime))
    workflow.add_node("rewrite_query", _with_context(ainvoke_rewrite_query_step, runtime))
    workflow.add_node("generate_answer", _with_context(ainvoke_generate_answer_step, runtime))
    workflow.add_node("output_guardrail", _with_context(ainvoke_output_guardrail_step, runtime))

    workflow.add_edge(START, "input_guardrail")
    workflow.add_conditional_edges(
        "input_guardrail",
        lambda state: continue_after_input_guardrail(state, runtime),
        {
            "continue": "intent_classify",
            "out_of_scope": "out_of_scope",
        },
    )
    workflow.add_conditional_edges(
        "intent_classify",
        lambda state: state.get("routing_decision").route if state.get("routing_decision") else "retrieve",
        {
            "retrieve": "retrieve",
            "generate_answer": "generate_answer",
            "out_of_scope": "out_of_scope",
        },
    )
    workflow.add_edge("out_of_scope", END)
    workflow.add_conditional_edges(
        "retrieve",
        tools_condition,
        {
            "tools": "tool_retrieve",
            END: END,
        },
    )
    workflow.add_edge("tool_retrieve", "rerank")
    workflow.add_edge("rerank", "grade_documents")
    workflow.add_conditional_edges(
        "grade_documents",
        lambda state: state.get("routing_decision", "generate_answer"),
        {
            "generate_answer": "generate_answer",
            "rewrite_query": "rewrite_query",
        },
    )
    workflow.add_edge("rewrite_query", "retrieve")
    workflow.add_edge("generate_answer", "output_guardrail")
    workflow.add_conditional_edges(
        "output_guardrail",
        lambda state: continue_after_output_guardrail(state, runtime),
        {
            "pass": END,
            "out_of_scope": "out_of_scope",
        },
    )

    return workflow.compile()


agentic_rag = _build_local_graph()
