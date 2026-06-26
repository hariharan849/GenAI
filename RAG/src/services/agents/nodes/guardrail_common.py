import logging
import time
from contextlib import nullcontext
from typing import Any, Dict

from langgraph.runtime import Runtime

from src.services.langfuse.client import FallbackPrompt
from ..context import Context
from ..models import GuardrailScoring

logger = logging.getLogger(__name__)


async def ainvoke_guardrail_llm(
    runtime: Runtime[Context],
    *,
    span_name: str,
    prompt_name: str,
    fallback_template: str,
    compile_kwargs: Dict[str, Any],
    node_label: str,
    fallback_score: int,
) -> GuardrailScoring:
    """Run a guardrail LLM scoring call with Langfuse tracing and graceful fallback.

    Shared by the input and output guardrail nodes so the span-creation /
    prompt-fetch / structured-output / fallback boilerplate isn't duplicated
    across both files.

    :param runtime: Runtime context with the LLM client and tracer
    :param span_name: Langfuse span name for this guardrail layer
    :param prompt_name: Langfuse prompt registry name
    :param fallback_template: Hardcoded prompt template used if Langfuse is down
    :param compile_kwargs: Keyword args used to compile the prompt template
    :param node_label: Short label for span/log metadata (e.g. "input_guardrail")
    :param fallback_score: Score to return if the LLM call fails. Callers should
        pass a fail-closed score (0) for post-generation checks and a
        conservative-but-permissive score for pre-generation checks.
    :returns: GuardrailScoring result
    """
    start_time = time.time()

    span = None
    if runtime.context.langfuse_enabled and runtime.context.trace:
        try:
            span = runtime.context.langfuse_tracer.create_span(
                trace=runtime.context.trace,
                name=span_name,
                input_data=compile_kwargs,
                metadata={"node": node_label, "model": runtime.context.model_name},
            )
        except Exception as e:
            logger.warning(f"Failed to create span for {span_name}: {e}")

    tracer = runtime.context.langfuse_tracer
    if tracer:
        prompt_obj = tracer.fetch_prompt(prompt_name, fallback_template=fallback_template)
    else:
        prompt_obj = FallbackPrompt(fallback_template)
    compiled_prompt = prompt_obj.compile(**compile_kwargs)

    try:
        llm = runtime.context.ollama_client.get_langchain_model(
            model=runtime.context.model_name,
            temperature=0.0,
        )
        structured_llm = llm.with_structured_output(GuardrailScoring)

        gen_ctx = (
            tracer.start_generation(
                f"{node_label}_llm",
                model=runtime.context.model_name,
                input_data=compiled_prompt,
                prompt=prompt_obj,
            )
            if tracer
            else nullcontext(None)
        )
        with gen_ctx as gen:
            response = await structured_llm.ainvoke(compiled_prompt)
            if gen:
                source = "fallback" if getattr(prompt_obj, "is_fallback", False) else "langfuse"
                gen.update(
                    output={"score": response.score, "reason": response.reason},
                    metadata={"prompt_source": source},
                )

        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.end_span(
                span,
                output={"score": response.score, "reason": response.reason},
                metadata={"execution_time_ms": execution_time},
            )

    except Exception as e:
        logger.error(f"{node_label} LLM scoring failed: {e}, falling back to default score {fallback_score}")

        response = GuardrailScoring(
            score=fallback_score,
            reason=f"LLM validation failed, using default: {str(e)}",
        )

        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.update_span(
                span,
                output={"score": response.score, "reason": response.reason, "error": str(e)},
                metadata={"execution_time_ms": execution_time, "fallback": True},
                level="WARNING",
            )
            runtime.context.langfuse_tracer.end_span(span)

    return response
