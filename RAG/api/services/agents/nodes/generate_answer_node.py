import logging
import time
from typing import Dict, List

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..prompts import GENERATE_ANSWER_PROMPT
from ..state import AgentState
from .utils import get_context_text, get_effective_query
from .tracing import create_node_span, fetch_prompt, finish_node_span, start_generation

logger = logging.getLogger(__name__)


async def ainvoke_generate_answer_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, List[AIMessage]]:
    """Generate final answer using retrieved documents.

    This node generates a comprehensive answer to the
    user's question based on the retrieved context using an LLM.

    :param state: Current agent state
    :param runtime: Runtime context
    :returns: Dictionary with messages containing the generated answer
    """
    logger.info("NODE: generate_answer")
    start_time = time.time()

    # Get question and context
    question = get_effective_query(state)
    context = get_context_text(state)

    # Count sources from relevant_sources
    sources_count = len(state.get("relevant_sources", []))

    if not context:
        context = "No relevant documents found."
        logger.warning("No context available for answer generation")

    logger.debug(f"Generating answer for query: {question[:100]}...")
    logger.debug(f"Using context of length: {len(context)} characters")

    # Extract document chunks preview for logging
    chunks_preview = []
    if context:
        context_preview = context[:1000] + "..." if len(context) > 1000 else context
        chunks_preview = [{"text_preview": context_preview, "length": len(context)}]

    # Create span for answer generation
    span = create_node_span(
        runtime,
        "answer_generation",
        input_data={
            "query": question,
            "context_length": len(context),
            "sources_count": sources_count,
            "chunks_used": chunks_preview,
        },
        metadata={
            "node": "generate_answer",
            "model": runtime.context.model_name,
            "temperature": runtime.context.temperature,
        },
    )
    if span:
        logger.debug("Created Langfuse span for answer generation")

    # Fetch versioned prompt (falls back to hardcoded constant when Langfuse is down)
    prompt_obj = fetch_prompt(runtime, "generate_answer", GENERATE_ANSWER_PROMPT)
    answer_prompt = prompt_obj.compile(context=context, question=question)

    try:
        # Get LLM from runtime context
        llm = runtime.context.ollama_client.get_langchain_model(
            model=runtime.context.model_name,
            temperature=runtime.context.temperature,
        )

        # Invoke LLM for answer generation, linking prompt version to the trace
        logger.info("Invoking LLM for answer generation")
        gen_ctx = start_generation(
            runtime,
            "generate_answer_llm",
            model=runtime.context.model_name,
            input_data=answer_prompt,
            prompt=prompt_obj,
        )
        with gen_ctx as gen:
            response = await llm.ainvoke(answer_prompt)
            if gen:
                answer_preview = response.content[:200] if hasattr(response, "content") else str(response)[:200]
                source = "fallback" if getattr(prompt_obj, "is_fallback", False) else "langfuse"
                gen.update(
                    output=answer_preview,
                    metadata={"prompt_source": source, "sources_count": sources_count},
                )

        # Extract content from response
        answer = response.content if hasattr(response, 'content') else str(response)
        logger.info(f"Generated answer of length: {len(answer)} characters")

        # Update span with successful result
        finish_node_span(
            runtime,
            span,
            start_time,
            output={
                "answer_length": len(answer),
                "sources_used": sources_count,
            },
            metadata={
                "context_length": len(context),
            },
        )

    except Exception as e:
        logger.error(f"LLM answer generation failed: {e}, falling back to error message")

        # Fallback to error message if LLM fails
        answer = f"I apologize, but I encountered an error while generating the answer: {str(e)}\n\nPlease try again or rephrase your question."

        # Update span with error
        finish_node_span(
            runtime,
            span,
            start_time,
            output={"error": str(e), "fallback": True},
            metadata={"context_length": len(context)},
            level="ERROR",
        )

    return {"messages": [AIMessage(content=answer)]}
