import logging
from typing import Dict, List, Literal

from langchain_core.messages import RemoveMessage
from langgraph.runtime import Runtime

from api.services.guardrails.models import PolicyAction

from ..context import Context
from ..models import GuardrailScoring, SourceItem
from ..state import AgentState
from .utils import get_effective_query

logger = logging.getLogger(__name__)


def continue_after_output_guardrail(
    state: AgentState,
    runtime: Runtime[Context],
) -> Literal["pass", "out_of_scope", "safety_refusal"]:
    """Route grounding failures separately from unsafe generated output."""
    result = state.get("output_guardrail_result")
    if not result:
        return "pass"

    if result.score != 0:
        return "pass"

    metadata = state.get("metadata", {}).get("guardrails", {}).get("output", {})
    categories = set(metadata.get("categories") or [])
    if "grounding_failed" in categories:
        return "out_of_scope"
    return "safety_refusal"


def _check_source_grounding(answer: str, relevant_sources: List[SourceItem]) -> bool:
    """Fast rule-based check: does the answer reference at least one retrieved source?"""
    if not relevant_sources:
        return True
    answer_lower = answer.lower()
    return any(source.node_name.lower() in answer_lower or source.url.lower() in answer_lower for source in relevant_sources)


async def ainvoke_output_guardrail_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict:
    """Run deterministic grounding, then Llama Guard output safety."""
    logger.info("NODE: output_guardrail")

    answer_message = state["messages"][-1]
    answer = answer_message.content if hasattr(answer_message, "content") else str(answer_message)
    question = get_effective_query(state)
    relevant_sources = state.get("relevant_sources") or []

    if not _check_source_grounding(answer, relevant_sources):
        logger.warning("Output guardrail: answer does not reference any retrieved source")
        if runtime.context.guardrail_policy is not None:
            decision = runtime.context.guardrail_policy.grounding_failed("Answer does not reference any retrieved source")
            result = decision.to_guardrail_scoring()
            metadata = {
                **state.get("metadata", {}),
                "guardrails": {
                    **state.get("metadata", {}).get("guardrails", {}),
                    "output": decision.model_dump(mode="json"),
                },
            }
        else:
            result = GuardrailScoring(score=0, reason="Answer does not reference any retrieved source")
            metadata = state.get("metadata", {})
        return {
            "output_guardrail_result": result,
            "messages": [RemoveMessage(id=answer_message.id)],
            "metadata": metadata,
        }

    if runtime.context.guardrail_policy is None:
        logger.warning("No guardrail policy service configured; allowing output")
        response = GuardrailScoring(score=100, reason="No guardrail policy service configured")
        return {"output_guardrail_result": response}

    decision = await runtime.context.guardrail_policy.check_output(question, answer)
    response = decision.to_guardrail_scoring()

    logger.info(f"Output guardrail result - Score: {response.score}, Reason: {response.reason}")

    result_dict: Dict = {
        "output_guardrail_result": response,
        "metadata": {
            **state.get("metadata", {}),
            "guardrails": {
                **state.get("metadata", {}).get("guardrails", {}),
                "output": decision.model_dump(mode="json"),
            },
        },
    }
    if decision.action == PolicyAction.BLOCK:
        result_dict["messages"] = [RemoveMessage(id=answer_message.id)]
    return result_dict
