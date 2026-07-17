"""FastAPI transport for the LangGraph-backed A2A researcher."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from fastapi import FastAPI

from .a2a_executor import ResearcherAgentExecutor
from .config import Settings
from .research import OpenAIResearcher, ResearchCallable, build_research_graph

AGENT_PATH = "/a2a/agent"
AGENT_CARD_PATH = f"{AGENT_PATH}/.well-known/agent-card.json"


def create_app(
    settings_factory: Callable[[], Settings] = Settings.from_environment,
    research: ResearchCallable | None = None,
) -> FastAPI:
    """Create the HTTP app without exposing graph or provider internals to callers."""
    settings = settings_factory()
    if research is None:
        research = OpenAIResearcher(settings).research
    executor = ResearcherAgentExecutor(build_research_graph(research))
    handler = DefaultRequestHandler(executor, InMemoryTaskStore())
    card = _agent_card(settings)
    app = A2AFastAPIApplication(agent_card=card, http_handler=handler).build(
        agent_card_url=AGENT_CARD_PATH,
        rpc_url=AGENT_PATH,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _agent_card(settings: Settings) -> AgentCard:
    return AgentCard(
        name="Researcher",
        description="Produces research reports on a requested topic using OpenAI.",
        url=f"{settings.public_url}{AGENT_PATH}",
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id="research",
                name="Research report",
                description="Researches a topic and returns a plain-text report.",
                tags=["research", "openai"],
            )
        ],
    )


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
