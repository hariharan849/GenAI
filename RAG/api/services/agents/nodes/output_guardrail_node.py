import logging
from typing import Dict, List, Literal

from langchain_core.messages import RemoveMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..models import GuardrailScoring, SourceItem
from ..prompts import OUTPUT_GUARDRAIL_PROMPT
from ..state import AgentState
from .guardrail_common import ainvoke_guardrail_llm
from .utils import get_latest_query

logger = logging.getLogger(__name__)


def continue_after_output_guardrail(state: AgentState, runtime: Runtime[Context]) -> Literal["pass", "out_of_scope"]:
    """Route based on the output guardrail score: 0 means rejected, anything else passes.

    :param state: Current agent state with output guardrail results
    :param runtime: Runtime context (unused, kept for routing-function symmetry)
    :returns: "pass" if the answer cleared both checks, "out_of_scope" otherwise
    """
    result = state.get("output_guardrail_result")
    if not result:
        return "pass"
    return "out_of_scope" if result.score == 0 else "pass"


def _check_source_grounding(answer: str, relevant_sources: List[SourceItem]) -> bool:
    """Fast rule-based check: does the answer reference at least one retrieved source?

    If no sources were retrieved there's nothing to cite against, so this
    auto-passes and the LLM topic-relevance judge becomes the only gate.
    """
    if not relevant_sources:
        return True
    answer_lower = answer.lower()
    return any(source.node_name.lower() in answer_lower or source.url.lower() in answer_lower for source in relevant_sources)


async def ainvoke_output_guardrail_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict:
    """Validate the generated answer before it's returned to the user.

    Runs two checks: (1) rule-based source grounding — fails immediately,
    without an LLM call, if the answer cites none of the retrieved sources;
    (2) an LLM judge for topic relevance. Either failing routes to
    out_of_scope with the bad answer removed from message history so the
    caller never sees two contradictory AI messages.

    :param state: Current agent state
    :param runtime: Runtime context
    :returns: Dictionary with output_guardrail_result, and a RemoveMessage if rejected
    """
    logger.info("NODE: output_guardrail")

    answer_message = state["messages"][-1]
    answer = answer_message.content if hasattr(answer_message, "content") else str(answer_message)
    question = state.get("original_query") or get_latest_query(state["messages"])
    relevant_sources = state.get("relevant_sources") or []
    source_ids = [source.url for source in relevant_sources]

    if not _check_source_grounding(answer, relevant_sources):
        logger.warning("Output guardrail: answer does not reference any retrieved source")
        result = GuardrailScoring(score=0, reason="Answer does not reference any retrieved source")
        return {
            "output_guardrail_result": result,
            "messages": [RemoveMessage(id=answer_message.id)],
        }

    response = await ainvoke_guardrail_llm(
        runtime,
        span_name="output_guardrail",
        prompt_name="output_guardrail",
        fallback_template=OUTPUT_GUARDRAIL_PROMPT,
        compile_kwargs={
            "question": question,
            "answer": answer,
            "source_ids": ", ".join(source_ids) or "none",
        },
        node_label="output_guardrail",
        fallback_score=0,  # fail closed: an LLM error must not let an unchecked answer through
    )

    logger.info(f"Output guardrail result - Score: {response.score}, Reason: {response.reason}")

    result_dict: Dict = {"output_guardrail_result": response}
    if response.score == 0:
        result_dict["messages"] = [RemoveMessage(id=answer_message.id)]
    return result_dict
