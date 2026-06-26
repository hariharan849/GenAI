import logging
from typing import Dict, List

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..state import AgentState
from .utils import get_latest_query

logger = logging.getLogger(__name__)


async def ainvoke_out_of_scope_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, List[AIMessage]]:
    """Handle out-of-scope queries and rejected answers with a helpful message.

    Reachable from two predecessors: the input guardrail (query rejected
    before retrieval) and the output guardrail (answer rejected after
    generation). Reads output_guardrail_result to tell the two cases apart
    and tailor the response.

    :param state: Current agent state
    :param runtime: Runtime context (not used in this node)
    :returns: Dictionary with messages containing the out-of-scope response
    """
    logger.info("NODE: out_of_scope")

    question = state.get("original_query") or get_latest_query(state["messages"])
    output_guardrail_result = state.get("output_guardrail_result")

    if output_guardrail_result and output_guardrail_result.score == 0:
        response_text = (
            "I generated a response, but it didn't clearly reference the retrieved papers "
            "or address your question, so I'm not showing it.\n\n"
            f"Your question: '{question}'\n\n"
            "Please try rephrasing your question, or ask about a different aspect of the topic."
        )
    else:
        response_text = (
            "I apologize, but I can only help with questions about Foundry Nuke VFX software.\n\n"
            f"Your question: '{question}'\n\n"
            "This appears to be outside my domain of expertise. For questions like this, you might want to try:\n"
            "- General-purpose AI assistants for broad knowledge questions\n"
            "- The official Foundry documentation at learn.foundry.com\n"
            "- Domain-specific resources for non-Nuke topics\n\n"
            "If you have a question about Nuke nodes, compositing, or VFX workflows, I'd be happy to help!"
        )

    logger.info("Responding with out-of-scope message")

    return {"messages": [AIMessage(content=response_text)]}
