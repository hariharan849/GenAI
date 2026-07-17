"""A2A application factory retaining the orchestrator public contract."""

import asyncio
import logging
import os
from typing import Any

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from fastapi import FastAPI, Header, HTTPException

from shared.learning_contracts import ContinuationRequest, LearnerProfile

from .a2a_executor import CoordinatorAgentExecutor
from .pipeline import CoursePipeline
from .service import CoordinatorService
from .workflow import LearningPathWorkflow

logger = logging.getLogger(__name__)

AGENT_PATH = "/a2a/agent"
AGENT_CARD_PATH = f"{AGENT_PATH}/.well-known/agent-card.json"


def create_app(
    service: CoordinatorService | None = None,
    pipeline: CoursePipeline | None = None,
    workflow: LearningPathWorkflow | None = None,
) -> FastAPI:
    service = service or CoordinatorService()
    pipeline = pipeline or CoursePipeline.from_environment()
    workflow = workflow or LearningPathWorkflow(pipeline)
    background_tasks: set[asyncio.Task[None]] = set()
    public_url = os.environ.get(
        "A2A_PUBLIC_URL", f"http://localhost:{os.environ.get('PORT', '8004')}"
    ).rstrip("/")
    card = AgentCard(
        name="Course Creation Coordinator",
        description="Coordinates learner-adaptive research, review, and course creation.",
        url=f"{public_url}{AGENT_PATH}",
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["application/json"],
        default_output_modes=["application/json", "text"],
        skills=[
            AgentSkill(
                id="create_course",
                name="Create adaptive course",
                description="Builds a course around learner knowledge gaps.",
                tags=["course", "learning"],
            )
        ],
    )
    app = A2AFastAPIApplication(
        card,
        DefaultRequestHandler(CoordinatorAgentExecutor(service), InMemoryTaskStore()),
    ).build(agent_card_url=AGENT_CARD_PATH, rpc_url=AGENT_PATH)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/learner/start")
    async def start(
        profile: LearnerProfile, x_browser_session: str = Header(min_length=1)
    ) -> dict:
        task = service.start(x_browser_session, profile)
        _schedule(
            background_tasks, _run_workflow(service, pipeline, workflow, task, None)
        )
        return _task_payload(task)

    @app.post("/internal/learner/continue")
    async def continue_course(
        request: ContinuationRequest, x_browser_session: str = Header(min_length=1)
    ) -> dict:
        try:
            task = service.continue_task(x_browser_session, request)
        except PermissionError as error:
            raise HTTPException(
                status_code=403, detail="Course session is not available."
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if request.action in {"approve", "learning_path_accepted", "feedback"}:
            service.set_stage(task.task_id, "queued")
            payload = (
                {"type": "approve"}
                if request.action in {"approve", "learning_path_accepted"}
                else {"type": "feedback", "text": request.response.strip()}
            )
            _schedule(
                background_tasks,
                _run_workflow(service, pipeline, workflow, task, payload),
            )
        return _task_payload(task)

    @app.get("/internal/learner/{task_id}")
    async def get_course_status(
        task_id: str, x_browser_session: str = Header(min_length=1)
    ) -> dict:
        try:
            return _task_payload(service.get_task(x_browser_session, task_id))
        except PermissionError as error:
            raise HTTPException(
                status_code=403, detail="Course session is not available."
            ) from error

    return app


def _task_payload(task: Any) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "context_id": task.context_id,
        "phase": task.phase.value,
        "sequence": task.sequence,
        "learning_path": task.learning_path.model_dump()
        if task.phase.value == "input_required" and task.learning_path
        else None,
        "expires_at": task.expires_at.isoformat(),
        "stage": task.stage,
        "course": task.course or None,
    }


def _schedule(background_tasks: set[asyncio.Task[None]], coroutine: Any) -> None:
    background_task = asyncio.create_task(coroutine)
    background_tasks.add(background_task)
    background_task.add_done_callback(background_tasks.discard)


async def _run_workflow(
    service: CoordinatorService,
    pipeline: CoursePipeline,
    workflow: LearningPathWorkflow,
    task: Any,
    resume_payload: dict[str, str] | None,
) -> None:
    try:
        service.set_stage(task.task_id, "researching")
        result = (
            await workflow.resume(task.task_id, resume_payload)
            if resume_payload
            else await workflow.start(task)
        )
        if "__interrupt__" in result:
            service.await_approval(
                task.task_id,
                result["learning_path"],
                result["research_findings"],
                result["judge_feedback"],
            )
            return
        if result.get("approved"):
            service.set_stage(task.task_id, "writing")
            course = await pipeline.build(result["research_findings"])
            service.complete_task(task.task_id, course)
    except Exception:
        logger.exception("learning_path_workflow_failed task_id=%s", task.task_id)
        service.fail_task(task.task_id)
