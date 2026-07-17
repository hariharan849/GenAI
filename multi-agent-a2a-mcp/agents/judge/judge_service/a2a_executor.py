"""A2A adapter that turns judge feedback into task events."""

import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart

from .service import JudgeService

logger = logging.getLogger(__name__)


class JudgeAgentExecutor(AgentExecutor):
    """Publish a CrewAI assessment through the A2A task lifecycle."""

    def __init__(self, judge_service: JudgeService) -> None:
        self._judge_service = judge_service

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Evaluate the incoming text and publish its JSON result as an artifact."""
        if context.task_id is None or context.context_id is None:
            raise ValueError("A2A execution requires a task and context ID.")

        logger.warning("Starting assessment for task %s", context.task_id)
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        feedback = await self._judge_service.evaluate(context.get_user_input())
        await updater.add_artifact(
            parts=[Part(root=TextPart(text=feedback.model_dump_json()))],
            name="judge_feedback",
            artifact_id="judge_feedback",
            last_chunk=True,
        )
        await updater.complete()
        logger.warning(
            "Completed assessment for task %s with status=%s",
            context.task_id,
            feedback.status,
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Mark cancellation requests terminal; CrewAI has no cooperative cancel hook."""
        if context.task_id is None or context.context_id is None:
            raise ValueError("A2A cancellation requires a task and context ID.")
        logger.warning("Cancelling task %s", context.task_id)
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()
