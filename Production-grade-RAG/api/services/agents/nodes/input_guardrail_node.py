import logging
from typing import Dict, Literal

from langgraph.runtime import Runtime

from ..context import Context
from ..state import AgentState
from .utils import get_latest_query

logger = logging.getLogger(__name__)


def continue_after_input_guardrail(state: AgentState, runtime: Runtime[Context]) -> Literal["continue", "safety_refusal"]:
    """Route unsafe input to the dedicated safety refusal node."""
    guardrail_result = state.get("guardrail_result")
    if not guardrail_result:
        logger.warning("No guardrail result found, defaulting to continue")
        return "continue"

    score = guardrail_result.score
    threshold = runtime.context.guardrail_threshold

    logger.info(f"Input guardrail score: {score}, threshold: {threshold}")

    return "continue" if score >= threshold else "safety_refusal"


async def ainvoke_input_guardrail_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict:
    """Run Presidio privacy redaction and Llama Guard input safety."""
    logger.info("NODE: input_guardrail")

    query = get_latest_query(state["messages"])
    logger.debug(f"Evaluating query: {query[:100]}...")

    if runtime.context.guardrail_policy is None:
        logger.warning("No guardrail policy service configured; allowing input")
        return {"guardrail_result": None, "pii_redacted": False}

    decision = await runtime.context.guardrail_policy.check_input(query)
    response = decision.to_guardrail_scoring()

    logger.info(f"Input guardrail result - Score: {response.score}, Reason: {response.reason}")

    result: Dict = {
        "guardrail_result": response,
        "pii_redacted": decision.pii_redacted,
        "metadata": {
            **state.get("metadata", {}),
            "guardrails": {
                **state.get("metadata", {}).get("guardrails", {}),
                "input": decision.model_dump(mode="json"),
            },
        },
    }
    if decision.sanitized_text and decision.sanitized_text != query:
        result["sanitized_query"] = decision.sanitized_text
    return result
