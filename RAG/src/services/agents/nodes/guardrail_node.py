import logging
import time
from contextlib import nullcontext
from typing import Dict, Literal

from langgraph.runtime import Runtime

from src.services.langfuse.client import FallbackPrompt
from ..context import Context
from ..models import GuardrailScoring
from ..prompts import GUARDRAIL_PROMPT
from ..state import AgentState
from .utils import get_latest_query

logger = logging.getLogger(__name__)


def continue_after_guardrail(state: AgentState, runtime: Runtime[Context]) -> Literal["continue", "out_of_scope"]:
    """Determine whether to continue or reject based on guardrail results.

    This function checks the guardrail_result score against a threshold.
    If the score is above threshold, continue; otherwise route to out_of_scope.

    :param state: Current agent state with guardrail results
    :param runtime: Runtime context containing guardrail threshold
    :returns: "continue" if score >= threshold, "out_of_scope" otherwise
    """
    guardrail_result = state.get("guardrail_result")
    if not guardrail_result:
        logger.warning("No guardrail result found, defaulting to continue")
        return "continue"

    score = guardrail_result.score
    threshold = runtime.context.guardrail_threshold

    logger.info(f"Guardrail score: {score}, threshold: {threshold}")

    return "continue" if score >= threshold else "out_of_scope"


async def ainvoke_guardrail_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, GuardrailScoring]:
    """Asynchronously invoke the guardrail validation step using LLM.

    This function evaluates whether the user query is within scope
    (CS/AI/ML research papers) and assigns a score using an LLM.

    :param state: Current agent state
    :param runtime: Runtime context
    :returns: Dictionary with guardrail_result
    """
    logger.info("NODE: guardrail_validation")
    start_time = time.time()

    # Get the latest user query
    query = get_latest_query(state["messages"])
    logger.debug(f"Evaluating query: {query[:100]}...")

    # Create span for guardrail validation (v2 SDK)
    span = None
    if runtime.context.langfuse_enabled and runtime.context.trace:
        try:
            span = runtime.context.langfuse_tracer.create_span(
                trace=runtime.context.trace,
                name="guardrail_validation",
                input_data={
                    "query": query,
                    "threshold": runtime.context.guardrail_threshold,
                },
                metadata={
                    "node": "guardrail",
                    "model": runtime.context.model_name,
                },
            )
            logger.debug("Created Langfuse span for guardrail validation (v2 SDK)")
        except Exception as e:
            logger.warning(f"Failed to create span for guardrail validation: {e}")

    # Fetch versioned prompt (falls back to hardcoded constant when Langfuse is down)
    tracer = runtime.context.langfuse_tracer
    if tracer:
        prompt_obj = tracer.fetch_prompt("guardrail", fallback_template=GUARDRAIL_PROMPT)
    else:
        prompt_obj = FallbackPrompt(GUARDRAIL_PROMPT)
    guardrail_prompt = prompt_obj.compile(question=query)

    try:
        # Get LLM from runtime context
        llm = runtime.context.ollama_client.get_langchain_model(
            model=runtime.context.model_name,
            temperature=0.0,
        )

        # Create structured output LLM for guardrail scoring
        structured_llm = llm.with_structured_output(GuardrailScoring)

        # Invoke LLM for guardrail evaluation, linking prompt version to the trace
        logger.info("Invoking LLM for guardrail validation")
        gen_ctx = tracer.start_generation(
            "guardrail_llm", model=runtime.context.model_name,
            input_data=guardrail_prompt, prompt=prompt_obj,
        ) if tracer else nullcontext(None)
        with gen_ctx as gen:
            response = await structured_llm.ainvoke(guardrail_prompt)
            if gen:
                source = "fallback" if getattr(prompt_obj, "is_fallback", False) else "langfuse"
                gen.update(
                    output={"score": response.score, "reason": response.reason},
                    metadata={"prompt_source": source},
                )

        logger.info(f"Guardrail result - Score: {response.score}, Reason: {response.reason}")

        # Update span with successful result
        if span:
            execution_time = (time.time() - start_time) * 1000  # Convert to ms
            runtime.context.langfuse_tracer.end_span(
                span,
                output={
                    "score": response.score,
                    "reason": response.reason,
                    "decision": "continue" if response.score >= runtime.context.guardrail_threshold else "out_of_scope",
                },
                metadata={
                    "execution_time_ms": execution_time,
                    "threshold": runtime.context.guardrail_threshold,
                },
            )

    except Exception as e:
        logger.error(f"LLM guardrail validation failed: {e}, falling back to default")

        # Fallback to a conservative default if LLM fails
        response = GuardrailScoring(
            score=50,
            reason=f"LLM validation failed, using conservative default: {str(e)}"
        )

        # Update span with error
        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.update_span(
                span,
                output={"score": response.score, "reason": response.reason, "error": str(e)},
                metadata={"execution_time_ms": execution_time, "fallback": True},
                level="WARNING",
            )
            runtime.context.langfuse_tracer.end_span(span)

    return {"guardrail_result": response}
