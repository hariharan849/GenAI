"""Standalone A2A server for the Bedrock-backed content builder."""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AFastAPIApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)
from claude_service import BedrockContentBuilder, BedrockSettings, ContentBuilder
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

LOGGER = logging.getLogger(__name__)
AGENT_PATH = "/a2a/agent"
DEFAULT_PORT = 8003


class ContentBuilderExecutor(AgentExecutor):
    def __init__(self, builder: ContentBuilder):
        self._builder = builder
        self._running_tasks: dict[str, asyncio.Task[None]] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or str(uuid.uuid4())
        context_id = context.context_id or str(uuid.uuid4())
        LOGGER.warning(
            "a2a_task_received task_id=%s context_id=%s", task_id, context_id
        )
        updater = TaskUpdater(event_queue, task_id, context_id)
        if context.current_task is None:
            await event_queue.enqueue_event(
                Task(
                    id=task_id,
                    context_id=context_id,
                    history=[context.message] if context.message else None,
                    status=TaskStatus(
                        state=TaskState.submitted,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ),
                )
            )

        await updater.start_work()
        current = asyncio.current_task()
        if current:
            self._running_tasks[task_id] = current
        try:
            findings = context.get_user_input()
            if not findings.strip():
                LOGGER.warning("a2a_task_missing_findings task_id=%s", task_id)
                await updater.failed(
                    updater.new_agent_message(
                        [TextPart(text="Approved research findings are required.")]
                    )
                )
                return
            course_module = await self._builder.generate(findings)
            await updater.add_artifact(
                parts=[TextPart(text=course_module)],
                name="course-module.md",
                last_chunk=True,
            )
            await updater.complete()
            LOGGER.warning("a2a_task_completed task_id=%s", task_id)
        except asyncio.CancelledError:
            LOGGER.warning("a2a_task_cancelled task_id=%s", task_id)
            await updater.cancel()
            raise
        except Exception as error:
            LOGGER.error(
                "a2a_task_failed task_id=%s error_type=%s error_code=%s request_id=%s",
                task_id,
                type(error).__name__,
                getattr(error, "error_code", None),
                getattr(error, "request_id", None),
            )
            await updater.failed(
                updater.new_agent_message(
                    [TextPart(text="Course generation failed. Please retry.")]
                )
            )
        finally:
            self._running_tasks.pop(task_id, None)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id
        if task_id and (running_task := self._running_tasks.get(task_id)):
            running_task.cancel()
            return
        updater = TaskUpdater(
            event_queue,
            task_id or str(uuid.uuid4()),
            context.context_id or str(uuid.uuid4()),
        )
        await updater.cancel()


def create_app(
    builder: ContentBuilder | None = None, public_url: str | None = None
) -> FastAPI:
    """Create the A2A application; dependency injection keeps its seam testable."""
    if builder is None:
        builder = BedrockContentBuilder(BedrockSettings.from_environment())

    public_url = public_url or os.getenv("A2A_PUBLIC_URL", "http://localhost:8003")
    card = AgentCard(
        name="content_builder",
        description="Transforms approved research findings into a structured course.",
        url=f"{public_url.rstrip('/')}{AGENT_PATH}",
        version="0.1.0",
        protocol_version="0.3.0",
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain"],
        default_output_modes=["text/markdown"],
        skills=[
            AgentSkill(
                id="build_course_module",
                name="Build course module",
                description="Creates a Markdown course module from approved research.",
                tags=["course", "content", "markdown"],
                input_modes=["text/plain"],
                output_modes=["text/markdown"],
            )
        ],
    )
    handler = DefaultRequestHandler(
        ContentBuilderExecutor(builder), InMemoryTaskStore()
    )

    app = A2AFastAPIApplication(agent_card=card, http_handler=handler).build(
        agent_card_url=f"{AGENT_PATH}/.well-known/agent-card.json",
        rpc_url=AGENT_PATH,
    )
    app.add_route("/health", health_check, methods=["GET"])

    LOGGER.warning("a2a_application_configured public_url=%s", public_url)

    return app


async def health_check(_request: Request) -> JSONResponse:
    LOGGER.warning("health_check_ready")
    return JSONResponse({"status": "ready"})


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    LOGGER.info(
        "starting_content_builder host=%s port=%s",
        os.getenv("HOST", "0.0.0.0"),
        os.getenv("PORT", str(DEFAULT_PORT)),
    )
    uvicorn.run(
        create_app(),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", str(DEFAULT_PORT))),
    )
