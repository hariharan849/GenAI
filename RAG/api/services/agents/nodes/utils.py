import logging
from typing import Dict, List, Optional

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ..models import ReasoningStep, SourceItem, ToolArtefact
from ..state import AgentState

logger = logging.getLogger(__name__)


def extract_sources_from_tool_messages(messages: List) -> List[SourceItem]:
    """Extract sources from tool messages in conversation.

    :param messages: List of messages from graph state
    :returns: List of SourceItem objects
    """
    sources = []

    for msg in messages:
        if isinstance(msg, ToolMessage) and hasattr(msg, "name"):
            if msg.name == "retrieve_papers":
                # Parse tool response for sources
                # This would need to parse the actual document metadata
                # For now, return empty list
                pass

    return sources


def extract_tool_artefacts(messages: List) -> List[ToolArtefact]:
    """Extract tool artifacts from messages.

    :param messages: List of messages from graph state
    :returns: List of ToolArtefact objects
    """
    artefacts = []

    for msg in messages:
        if isinstance(msg, ToolMessage):
            artefact = ToolArtefact(
                tool_name=getattr(msg, "name", "unknown"),
                tool_call_id=getattr(msg, "tool_call_id", ""),
                content=msg.content,
                metadata={},
            )
            artefacts.append(artefact)

    return artefacts


def create_reasoning_step(
    step_name: str,
    description: str,
    metadata: Optional[Dict] = None,
) -> ReasoningStep:
    """Create a reasoning step record.

    :param step_name: Name of the step/node
    :param description: Human-readable description
    :param metadata: Additional metadata
    :returns: ReasoningStep object
    """
    return ReasoningStep(
        step_name=step_name,
        description=description,
        metadata=metadata or {},
    )


def filter_messages(messages: List) -> List[AIMessage | HumanMessage]:
    """Filter messages to include only HumanMessage and AIMessage types.

    Excludes tool messages and other internal message types.

    :param messages: List of messages to filter
    :returns: Filtered list of messages
    """
    return [msg for msg in messages if isinstance(msg, (HumanMessage, AIMessage))]


def get_latest_query(messages: List) -> str:
    """Get the latest user query from messages.

    :param messages: List of messages
    :returns: Latest query text
    :raises ValueError: If no user query found
    """
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content

    raise ValueError("No user query found in messages")


def get_latest_context(messages: List) -> str:
    """Get the latest context from tool messages.

    :param messages: List of messages
    :returns: Latest context text or empty string
    """
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            return msg.content if hasattr(msg, "content") else ""

    return ""


def get_latest_documents(messages: List) -> List[Document]:
    """Get the structured documents from the most recent tool call.

    Reads ``ToolMessage.artifact`` rather than ``ToolMessage.content`` —
    the content is a flattened string (document boundaries lost), while
    the artifact preserves the original ``list[Document]`` returned by the
    ``retrieve_papers`` tool (set via ``response_format="content_and_artifact"``).

    :param messages: List of messages
    :returns: List of Document objects, or empty list if none found
    """
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            artifact = getattr(msg, "artifact", None)
            return artifact if isinstance(artifact, list) else []

    return []


def get_context_text(state: AgentState) -> str:
    """Get the context text to use for grading/generation.

    Prefers ``state["retrieved_documents"]`` (the rerank node's reordered,
    truncated output) when set, falling back to the flattened
    message-based context for any path where rerank didn't run.

    :param state: Current agent state
    :returns: Context text or empty string
    """
    documents = state.get("retrieved_documents")
    if documents:
        return "\n\n".join(doc.page_content for doc in documents)

    return get_latest_context(state["messages"])
