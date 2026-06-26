import logging
import time
from contextlib import nullcontext
from typing import Dict, List

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from src.services.langfuse.client import FallbackPrompt
from ..context import Context
from ..prompts import REWRITE_PROMPT
from ..state import AgentState

logger = logging.getLogger(__name__)


class QueryRewriteOutput(BaseModel):
    """Structured output for query rewriting."""

    rewritten_query: str = Field(
        description="The improved query optimized for document retrieval"
    )
    reasoning: str = Field(
        description="Brief explanation of how the query was improved"
    )


async def ainvoke_rewrite_query_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, str | List]:
    """Rewrite the original query for better document retrieval using LLM.

    This node uses an LLM to intelligently rewrite the user's query
    to improve the chances of finding relevant documents.

    :param state: Current agent state
    :param runtime: Runtime context
    :returns: Dictionary with rewritten_query and updated messages
    """
    logger.info("NODE: rewrite_query")
    start_time = time.time()

    # Get original query
    original_question = state.get("original_query") or state["messages"][0].content
    current_attempt = state.get("retrieval_attempts", 0)

    logger.debug(f"Rewriting query using LLM: {original_question[:100]}...")

    # Create span for query rewriting
    span = None
    if runtime.context.langfuse_enabled and runtime.context.trace:
        try:
            span = runtime.context.langfuse_tracer.create_span(
                trace=runtime.context.trace,
                name="query_rewriting",
                input_data={
                    "original_query": original_question,
                    "attempt": current_attempt,
                },
                metadata={
                    "node": "rewrite_query",
                    "strategy": "llm_based_expansion",
                    "model": runtime.context.model_name,
                },
            )
            logger.debug("Created Langfuse span for query rewriting")
        except Exception as e:
            logger.warning(f"Failed to create span for rewrite_query node: {e}")

    # Fetch versioned prompt (falls back to hardcoded constant when Langfuse is down)
    tracer = runtime.context.langfuse_tracer
    if tracer:
        prompt_obj = tracer.fetch_prompt("rewrite_query", fallback_template=REWRITE_PROMPT)
    else:
        prompt_obj = FallbackPrompt(REWRITE_PROMPT)
    rewrite_prompt = prompt_obj.compile(question=original_question)

    # Use LLM to rewrite the query intelligently
    try:
        # Create structured LLM for query rewriting
        llm = runtime.context.ollama_client.get_langchain_model(
            model=runtime.context.model_name,
            temperature=0.3,  # Lower temperature for more focused rewriting
        )
        structured_llm = llm.with_structured_output(QueryRewriteOutput)

        logger.debug(f"Invoking LLM for query rewriting (model: {runtime.context.model_name})")
        llm_start = time.time()

        # Get rewritten query from LLM, linking prompt version to the trace
        gen_ctx = tracer.start_generation(
            "rewrite_query_llm", model=runtime.context.model_name,
            input_data=rewrite_prompt, prompt=prompt_obj,
        ) if tracer else nullcontext(None)
        with gen_ctx as gen:
            result: QueryRewriteOutput = await structured_llm.ainvoke(rewrite_prompt)
            if gen:
                source = "fallback" if getattr(prompt_obj, "is_fallback", False) else "langfuse"
                gen.update(
                    output={"rewritten_query": result.rewritten_query if result else None},
                    metadata={"prompt_source": source},
                )

        # Validate LLM output
        if not result or not result.rewritten_query:
            raise ValueError("LLM failed to return valid structured output for query rewriting")

        rewritten_query = result.rewritten_query.strip()
        if not rewritten_query:
            raise ValueError("LLM returned empty rewritten query")

        reasoning = result.reasoning

        llm_duration = time.time() - llm_start
        logger.info(
            f"Query rewritten in {llm_duration:.2f}s: "
            f"'{original_question[:50]}...' -> '{rewritten_query[:50]}...'"
        )
        logger.debug(f"Rewriting reasoning: {reasoning}")

    except Exception as e:
        logger.error(f"Failed to rewrite query using LLM: {e}")
        logger.warning("Falling back to simple keyword expansion")
        # Fallback to simple expansion if LLM fails
        rewritten_query = f"{original_question} nuke vfx compositing documentation"
        reasoning = "Fallback: Simple keyword expansion due to LLM error"

    # Update span with rewriting result
    if span:
        execution_time = (time.time() - start_time) * 1000
        runtime.context.langfuse_tracer.end_span(
            span,
            output={
                "rewritten_query": rewritten_query,
                "reasoning": reasoning,
                "original_query": original_question,
            },
            metadata={
                "execution_time_ms": execution_time,
                "original_length": len(original_question),
                "rewritten_length": len(rewritten_query),
                "llm_duration_seconds": llm_duration if 'llm_duration' in locals() else None,
            },
        )

    return {
        "messages": [HumanMessage(content=rewritten_query)],
        "rewritten_query": rewritten_query,
    }
