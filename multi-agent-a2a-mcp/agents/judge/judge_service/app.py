"""FastAPI application factory for the judge's stable A2A interface."""

import logging
import os

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from fastapi import FastAPI

from .a2a_executor import JudgeAgentExecutor
from .service import JudgeService

AGENT_PATH = "/a2a/agent"
AGENT_CARD_PATH = f"{AGENT_PATH}/.well-known/agent-card.json"
logger = logging.getLogger(__name__)


def create_app(judge_service: JudgeService | None = None) -> FastAPI:
    """Build the A2A server without exposing CrewAI details to callers."""
    public_url = os.environ.get(
        "A2A_PUBLIC_URL", f"http://localhost:{os.environ.get('PORT', '8002')}"
    ).rstrip("/")
    logger.warning("Configuring judge A2A application for %s", public_url)
    agent_card = AgentCard(
        name="Judge",
        description="Evaluates research findings for completeness and accuracy.",
        url=f"{public_url}{AGENT_PATH}",
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id="judge_research",
                name="Judge research",
                description="Assesses research against a user request.",
                tags=["research", "quality"],
            )
        ],
    )
    handler = DefaultRequestHandler(
        agent_executor=JudgeAgentExecutor(judge_service or JudgeService()),
        task_store=InMemoryTaskStore(),
    )
    return A2AFastAPIApplication(agent_card, handler).build(
        agent_card_url=AGENT_CARD_PATH,
        rpc_url=AGENT_PATH,
    )
