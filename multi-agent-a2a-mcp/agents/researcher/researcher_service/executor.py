"""A2A adapter for the LangGraph researcher."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from time import perf_counter
from typing import Protocol, TypedDict

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, Role, TaskState, TextPart
from a2a.utils import get_message_text, new_agent_text_message

from .research import ResearchResult, normalize_request

logger = logging.getLogger(__name__)


class GraphState(TypedDict):
    """The portion of LangGraph state consumed by the executor."""

    result: ResearchResult


class ResearchGraph(Protocol):
    """Internal seam used to replace the compiled graph in tests."""

    def ainvoke(self, state: dict[str, str]) -> Awaitable[GraphState]: ...


class ResearcherAgentExecutor(AgentExecutor):
    """Translate A2A tasks to the LangGraph interface and publish task events."""

    def __init__(self, graph: ResearchGraph) -> None:
        self._graph = graph

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Run research and stream lifecycle updates plus the final artifact."""
        if not context.task_id or not context.context_id:
            raise ValueError(
                "A2A request did not provide task and context identifiers."
            )

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        started_at = perf_counter()
        try:
            request = _request_from_context(context)
            logger.warning(
                "research_request_received task_id=%s context_id=%s request_chars=%d",
                context.task_id,
                context.context_id,
                len(request),
            )
            await updater.start_work(new_agent_text_message("Research in progress."))
            logger.warning("research_started task_id=%s", context.task_id)
            state = await self._graph.ainvoke({"research_request": request})
            result = state["result"]
            logger.warning(
                "research_result_ready task_id=%s report_chars=%d source_count=%d",
                context.task_id,
                len(result["report"]),
                len(result["sources"]),
            )
            await updater.add_artifact(
                parts=[Part(root=TextPart(text=result["report"]))],
                name="research-findings",
                last_chunk=True,
            )
            logger.warning("research_artifact_published task_id=%s", context.task_id)
            await updater.complete(new_agent_text_message("Research completed."))
            logger.warning(
                "research_completed task_id=%s elapsed_ms=%d",
                context.task_id,
                (perf_counter() - started_at) * 1_000,
            )
        except Exception as error:
            logger.exception(
                "research_failed task_id=%s error=%s elapsed_ms=%d",
                context.task_id,
                type(error).__name__,
                (perf_counter() - started_at) * 1_000,
            )
            await updater.failed(
                new_agent_text_message("Research could not be completed.")
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Publish a terminal cancellation status for the requested task."""
        if not context.task_id or not context.context_id:
            return
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.update_status(
            TaskState.canceled,
            new_agent_text_message("Research was cancelled."),
            final=True,
        )
        logger.warning("research_cancelled task_id=%s", context.task_id)


def _request_from_context(context: RequestContext) -> str:
    """Collect ordered user text from the task history and current message."""
    messages = list(context.current_task.history or []) if context.current_task else []
    if context.message:
        messages.append(context.message)
    texts = [
        get_message_text(message) for message in messages if message.role == Role.user
    ]
    return normalize_request(texts)
