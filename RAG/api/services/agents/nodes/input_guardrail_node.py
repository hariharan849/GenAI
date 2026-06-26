import logging
import re
from typing import Dict, Literal, Tuple

from langgraph.runtime import Runtime

from ..context import Context
from ..models import GuardrailScoring
from ..prompts import GUARDRAIL_PROMPT
from ..state import AgentState
from .guardrail_common import ainvoke_guardrail_llm
from .utils import get_latest_query

logger = logging.getLogger(__name__)

# Fast-path prompt injection detection, matched before any LLM call so the
# model itself never sees an attempt to override its instructions.
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|prior|all|your)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(previous|prior|all)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|my)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+are|a|an)", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|your)\s+(you\s+know|instructions?|training)", re.IGNORECASE),
    re.compile(r"(reveal|show|print|display)\s+(your\s+)?(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"DAN\s+mode", re.IGNORECASE),
]

# Structured PII patterns. Matches are redacted from the query before it
# reaches the LLM scope check. The redacted text is never written back over
# the user's original query, since out_of_scope echoes that back verbatim.
PII_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone": re.compile(r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}


def detect_injection(query: str) -> bool:
    """Check whether a query matches a known prompt-injection pattern."""
    return any(pattern.search(query) for pattern in INJECTION_PATTERNS)


def redact_pii(query: str) -> Tuple[str, bool]:
    """Redact structured PII from a query.

    :param query: Raw user query
    :returns: (redacted_query, was_redacted)
    """
    redacted = query
    found = False
    for label, pattern in PII_PATTERNS.items():
        if pattern.search(redacted):
            found = True
            redacted = pattern.sub(f"[{label.upper()}]", redacted)
    return redacted, found


def continue_after_input_guardrail(state: AgentState, runtime: Runtime[Context]) -> Literal["continue", "out_of_scope"]:
    """Determine whether to continue or reject based on input guardrail results.

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

    logger.info(f"Input guardrail score: {score}, threshold: {threshold}")

    return "continue" if score >= threshold else "out_of_scope"


async def ainvoke_input_guardrail_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict:
    """Validate the user query before it enters the retrieval pipeline.

    Runs checks in order, short-circuiting on the first failure:
    (1) prompt injection regex — fast, no LLM call, so the model never sees
    an injection attempt; (2) structured PII redaction — strips PII before
    the query reaches the LLM; (3) LLM-based topic scope scoring.

    :param state: Current agent state
    :param runtime: Runtime context
    :returns: Dictionary with guardrail_result, and sanitized_query/pii_redacted if PII was found
    """
    logger.info("NODE: input_guardrail")

    query = get_latest_query(state["messages"])
    logger.debug(f"Evaluating query: {query[:100]}...")

    if detect_injection(query):
        logger.warning("Prompt injection pattern detected, rejecting without an LLM call")
        if runtime.context.langfuse_enabled and runtime.context.trace:
            try:
                span = runtime.context.langfuse_tracer.create_span(
                    trace=runtime.context.trace,
                    name="input_guardrail",
                    input_data={"query": query},
                    metadata={"node": "input_guardrail", "injection_detected": True},
                )
                runtime.context.langfuse_tracer.end_span(
                    span,
                    output={"score": 0, "reason": "Prompt injection detected", "decision": "out_of_scope"},
                )
            except Exception as e:
                logger.warning(f"Failed to create span for injection rejection: {e}")
        return {"guardrail_result": GuardrailScoring(score=0, reason="Prompt injection detected")}

    sanitized_query, pii_found = redact_pii(query)
    if pii_found:
        logger.info("PII detected in query, using redacted text for the LLM scope check")

    response = await ainvoke_guardrail_llm(
        runtime,
        span_name="input_guardrail",
        prompt_name="guardrail",
        fallback_template=GUARDRAIL_PROMPT,
        compile_kwargs={"question": sanitized_query if pii_found else query},
        node_label="input_guardrail",
        fallback_score=50,
    )

    logger.info(f"Input guardrail result - Score: {response.score}, Reason: {response.reason}")

    result: Dict = {"guardrail_result": response, "pii_redacted": pii_found}
    if pii_found:
        result["sanitized_query"] = sanitized_query
    return result
