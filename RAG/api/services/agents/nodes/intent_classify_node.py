import logging
import time
from typing import Dict

from langgraph.runtime import Runtime

from ..context import Context
from ..models import RoutingDecision
from ..prompts import INTENT_CLASSIFY_PROMPT
from ..state import AgentState
from .utils import get_effective_query
from .tracing import create_node_span, fetch_prompt, finish_node_span, start_generation

logger = logging.getLogger(__name__)


async def ainvoke_intent_classify_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, RoutingDecision]:
    """Classify whether the query needs retrieval, before paying for a
    retrieval+grade round trip.

    Runs right after input_guardrail. Routes to "retrieve" (needs research
    papers), "generate_answer" (no retrieval needed — answered directly),
    or "out_of_scope" (backstop, input_guardrail should normally catch this
    first).

    :param state: Current agent state
    :param runtime: Runtime context
    :returns: Dictionary with routing_decision
    """
    logger.info("NODE: intent_classify")
    start_time = time.time()

    question = get_effective_query(state)
    logger.debug(f"Classifying intent for query: {question[:100]}...")

    span = create_node_span(
        runtime,
        "intent_classify",
        input_data={"query": question},
        metadata={"node": "intent_classify", "model": runtime.context.model_name},
    )
    prompt_obj = fetch_prompt(runtime, "intent_classify", INTENT_CLASSIFY_PROMPT)
    compiled_prompt = prompt_obj.compile(question=question)

    try:
        llm = runtime.context.ollama_client.get_langchain_model(
            model=runtime.context.model_name,
            temperature=0.0,
        )
        structured_llm = llm.with_structured_output(RoutingDecision)

        gen_ctx = start_generation(
            runtime,
            "intent_classify_llm",
            model=runtime.context.model_name,
            input_data=compiled_prompt,
            prompt=prompt_obj,
        )
        with gen_ctx as gen:
            routing_decision = await structured_llm.ainvoke(compiled_prompt)
            if gen:
                source = "fallback" if getattr(prompt_obj, "is_fallback", False) else "langfuse"
                gen.update(
                    output={"route": routing_decision.route, "reason": routing_decision.reason},
                    metadata={"prompt_source": source},
                )

        logger.info(f"Intent classified: route={routing_decision.route}, reason={routing_decision.reason}")

        finish_node_span(
            runtime,
            span,
            start_time,
            output={"route": routing_decision.route, "reason": routing_decision.reason},
        )

    except Exception as e:
        # Never block the graph on a classifier outage — default to the safe
        # choice (retrieve) rather than silently skipping research queries.
        logger.warning(f"Intent classification failed: {e}, defaulting to route='retrieve'")

        routing_decision = RoutingDecision(
            route="retrieve",
            reason=f"classification failed, defaulting to retrieve: {str(e)}",
        )

        finish_node_span(
            runtime,
            span,
            start_time,
            output={"route": routing_decision.route, "reason": routing_decision.reason, "error": str(e)},
            metadata={"fallback": True},
            level="WARNING",
        )

    return {"routing_decision": routing_decision}
