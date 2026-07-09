from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .context import Context
from .nodes import (
    ainvoke_generate_answer_step,
    ainvoke_grade_documents_step,
    ainvoke_input_guardrail_step,
    ainvoke_intent_classify_step,
    ainvoke_out_of_scope_step,
    ainvoke_output_guardrail_step,
    ainvoke_rerank_step,
    ainvoke_retrieve_step,
    ainvoke_rewrite_query_step,
    ainvoke_safety_refusal_step,
    continue_after_input_guardrail,
    continue_after_output_guardrail,
)
from .state import AgentState


def build_agentic_rag_graph(
    tools: list[Any],
    checkpointer: BaseCheckpointSaver | None = None,
    wrap_node: Callable[[Callable[..., Any]], Callable[..., Any]] | None = None,
    wrap_route: Callable[[Callable[..., Any]], Callable[..., Any]] | None = None,
    use_context_schema: bool = True,
):
    """Build the shared Agentic RAG graph topology."""
    workflow = StateGraph(AgentState, context_schema=Context) if use_context_schema else StateGraph(AgentState)
    wrap = wrap_node or (lambda node: node)
    route = wrap_route or (lambda node: node)

    workflow.add_node("input_guardrail", wrap(ainvoke_input_guardrail_step))
    workflow.add_node("intent_classify", wrap(ainvoke_intent_classify_step))
    workflow.add_node("out_of_scope", wrap(ainvoke_out_of_scope_step))
    workflow.add_node("safety_refusal", wrap(ainvoke_safety_refusal_step))
    workflow.add_node("retrieve", wrap(ainvoke_retrieve_step))
    workflow.add_node("tool_retrieve", ToolNode(tools))
    workflow.add_node("rerank", wrap(ainvoke_rerank_step))
    workflow.add_node("grade_documents", wrap(ainvoke_grade_documents_step))
    workflow.add_node("rewrite_query", wrap(ainvoke_rewrite_query_step))
    workflow.add_node("generate_answer", wrap(ainvoke_generate_answer_step))
    workflow.add_node("output_guardrail", wrap(ainvoke_output_guardrail_step))

    workflow.add_edge(START, "input_guardrail")
    workflow.add_conditional_edges(
        "input_guardrail",
        route(continue_after_input_guardrail),
        {
            "continue": "intent_classify",
            "safety_refusal": "safety_refusal",
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
    workflow.add_edge("safety_refusal", END)
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
        route(continue_after_output_guardrail),
        {
            "pass": END,
            "out_of_scope": "out_of_scope",
            "safety_refusal": "safety_refusal",
        },
    )

    return workflow.compile(checkpointer=checkpointer)
