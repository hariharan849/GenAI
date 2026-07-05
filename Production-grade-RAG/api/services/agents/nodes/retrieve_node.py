import logging
import time
from typing import Dict, Union

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..state import AgentState
from .utils import get_effective_query, get_latest_query
from .tracing import create_node_span, finish_node_span

logger = logging.getLogger(__name__)


async def ainvoke_retrieve_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, Union[int, str, list]]:
    """Initiate retrieval or return fallback if max attempts reached.

    This node creates a tool call to retrieve documents, or returns a fallback
    message if the maximum number of retrieval attempts has been reached.

    :param state: Current agent state
    :param runtime: Runtime context containing max_retrieval_attempts
    :returns: Dictionary with updated state (retrieval_attempts, messages, original_query)
    """
    logger.info("NODE: retrieve")
    start_time = time.time()

    messages = state["messages"]
    question = get_effective_query(state)
    current_attempts = state.get("retrieval_attempts", 0)

    # Get max attempts from context
    max_attempts = runtime.context.max_retrieval_attempts

    # Store original query if not set
    updates = {}
    if state.get("original_query") is None:
        original_query = get_latest_query(messages)
        updates["original_query"] = original_query
        logger.debug(f"Stored original query: {original_query[:100]}...")

    # Create span for retrieval initiation
    span = create_node_span(
        runtime,
        "document_retrieval_initiation",
        input_data={
            "query": question,
            "attempt": current_attempts + 1,
            "max_attempts": max_attempts,
        },
        metadata={
            "node": "retrieve",
            "retrieval_top_k": runtime.context.retrieval_top_k,
        },
    )
    if span:
        logger.debug(f"Created Langfuse span for retrieval attempt {current_attempts + 1}")

    # Check if max attempts reached
    if current_attempts >= max_attempts:
        logger.warning(f"Max retrieval attempts ({max_attempts}) reached")
        fallback_msg = (
            f"I apologize, but I couldn't find relevant Nuke documentation after {max_attempts} attempts.\n"
            "This may be because:\n"
            "1. No indexed documentation contains relevant information\n"
            "2. The query terms don't match the indexed content\n\n"
            "Please try rephrasing your question with more specific technical terms."
        )

        # Update span with max attempts reached
        finish_node_span(
            runtime,
            span,
            start_time,
            output={"status": "max_attempts_reached", "fallback": True},
        )

        return {**updates, "messages": [AIMessage(content=fallback_msg)]}

    # Increment retrieval attempts
    new_attempt_count = current_attempts + 1
    updates["retrieval_attempts"] = new_attempt_count
    logger.info(f"Retrieval attempt {new_attempt_count}/{max_attempts}")

    # Create tool call for retrieval
    updates["messages"] = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": f"retrieve_{new_attempt_count}",
                    "name": "retrieve_papers",
                    "args": {"query": question},
                }
            ],
        )
    ]

    logger.debug(f"Created tool call for query: {question[:100]}...")

    # Update span with successful tool call creation
    finish_node_span(
        runtime,
        span,
        start_time,
        output={
            "status": "tool_call_created",
            "query": question,
            "attempt": new_attempt_count,
        },
    )

    return updates
