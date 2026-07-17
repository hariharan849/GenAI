"""A2A adapter for the coordinator's learner-path state machine."""

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart

from .service import CoordinatorService


class CoordinatorAgentExecutor(AgentExecutor):
    def __init__(self, service: CoordinatorService) -> None:
        self._service = service

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.task_id is None or context.context_id is None:
            raise ValueError("A2A execution requires task and context IDs.")
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        # The browser adapter owns profile parsing; A2A callers may provide it as JSON.
        from shared.learning_contracts import LearnerProfile

        profile = LearnerProfile.model_validate_json(context.get_user_input())
        task = self._service.start(
            context.metadata.get("browser_session", "anonymous"), profile
        )
        await updater.requires_input(
            updater.new_agent_message(
                [
                    Part(
                        root=TextPart(
                            text=task.learning_path.model_dump_json()
                            if task.learning_path
                            else "{}"
                        )
                    )
                ]
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.task_id is None or context.context_id is None:
            return
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()
