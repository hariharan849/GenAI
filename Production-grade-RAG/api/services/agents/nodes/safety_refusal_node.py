import logging
from typing import Dict, List

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..state import AgentState

logger = logging.getLogger(__name__)


async def ainvoke_safety_refusal_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, List[AIMessage]]:
    """Return the dedicated safety refusal for unsafe input or output."""
    logger.info("NODE: safety_refusal")

    response_text = (
        "I can't help with that request because it was classified as unsafe by the safety policy. "
        "I can still help with safe questions about Foundry Nuke nodes, compositing, and VFX workflows."
    )
    return {"messages": [AIMessage(content=response_text)]}
