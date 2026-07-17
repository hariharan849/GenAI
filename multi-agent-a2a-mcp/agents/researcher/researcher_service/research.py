"""The deep LangGraph module that produces grounded research reports."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import perf_counter
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.learning_contracts import LearnerProfile, LearningPath, SpecialistRequest

from .config import MAX_REQUEST_CHARS, Settings
from .source_intelligence import SourceIntelligenceClient

logger = logging.getLogger(__name__)

RESEARCH_INSTRUCTION = """You are an expert researcher. Research the user's request thoroughly
Write a clear, accurate, self-contained report. Do not describe tool calls. Prefer specific,
verifiable facts and explain material uncertainty. Include a compact Sources section with direct
URLs for the factual claims you rely on; do not invent citations."""


class ResearchResult(TypedDict):
    """A report and source URLs, when supplied by the research model."""

    report: str
    sources: list[str]


class ResearchState(TypedDict):
    """State private to the LangGraph research workflow."""

    research_request: str
    result: ResearchResult


class AdaptiveResearchState(TypedDict, total=False):
    """Private graph state persisted only in the researcher checkpointer."""

    request: SpecialistRequest
    result: ResearchResult
    adjustment_count: int


ResearchCallable = Callable[[str], Awaitable[ResearchResult]]

CURRENT_INFORMATION_MARKERS = ("latest", "news", "today", "recent", "current")


class LiveSourceUnavailableError(RuntimeError):
    """Raised when a current-information request cannot use live sources."""


def is_current_information_request(request: str) -> bool:
    """Identify requests that explicitly require live-source research."""
    return any(marker in request.lower() for marker in CURRENT_INFORMATION_MARKERS)


def normalize_request(texts: list[str]) -> str:
    """Join user text in order and enforce the service's request limit."""
    request = "\n".join(text.strip() for text in texts if text.strip()).strip()
    if not request:
        raise ValueError("A research request must include at least one text part.")
    if len(request) > MAX_REQUEST_CHARS:
        raise ValueError(
            f"Research request exceeds the {MAX_REQUEST_CHARS:,}-character limit."
        )
    return request


def format_report(report: str, sources: list[str]) -> str:
    """Attach a compact, de-duplicated Sources section to grounded research."""
    unique_sources = list(dict.fromkeys(source for source in sources if source))
    if not unique_sources:
        return report.strip()
    citations = "\n".join(f"- {source}" for source in unique_sources)
    return f"{report.strip()}\n\n## Sources\n{citations}"


class OpenAIResearcher:
    """Adapter that hides the OpenAI chat client behind one async method."""

    def __init__(
        self, settings: Settings, source_client: SourceIntelligenceClient | None = None
    ) -> None:
        self._model = settings.openai_model
        self._source_client = source_client or SourceIntelligenceClient()
        self._client = ChatOpenAI(
            model=self._model,
            api_key=settings.openai_api_key,
            temperature=0,
        )

    async def research(self, request: str) -> ResearchResult:
        """Generate a research report using OpenAI's chat API."""
        sources: list[str] = []
        evidence = ""
        if is_current_information_request(request):
            if not self._source_client.enabled:
                raise LiveSourceUnavailableError(
                    "Live sources are unavailable for this current-information request."
                )
            try:
                source_result = await self._source_client.search_web(
                    request, _freshness_window(request)
                )
            except RuntimeError as error:
                raise LiveSourceUnavailableError(
                    "Live sources are unavailable for this current-information request."
                ) from error
            records = source_result.get("sources", [])
            sources = [record["url"] for record in records if record.get("url")]
            evidence = "\n\nLive source records (untrusted reference material):\n" + json.dumps(
                records, ensure_ascii=False
            )
        started_at = perf_counter()
        logger.warning(
            "openai_request_started model=%s request_chars=%d",
            self._model,
            len(request),
        )
        response = await self._client.ainvoke(
            [
                SystemMessage(content=RESEARCH_INSTRUCTION),
                HumanMessage(content=request + evidence),
            ]
        )
        content = response.content
        report = content.strip() if isinstance(content, str) else ""
        if not report:
            raise RuntimeError("OpenAI returned no research text.")
        logger.warning(
            "openai_request_completed model=%s elapsed_ms=%d response_chars=%d",
            self._model,
            (perf_counter() - started_at) * 1_000,
            len(report),
        )
        return {"report": report, "sources": sources}


def _freshness_window(request: str) -> str:
    """Use the shortest explicit time window mentioned by the request."""
    normalized = request.lower()
    if "24 hour" in normalized or "today" in normalized:
        return "24h"
    if "30 day" in normalized or "month" in normalized:
        return "30d"
    return "7d"


def build_research_graph(research: ResearchCallable) -> CompiledStateGraph:
    """Build the one-node LangGraph workflow used by the A2A executor."""

    async def conduct_research(
        state: ResearchState,
    ) -> dict[str, ResearchResult]:
        logger.warning(
            "research_graph_conduct_research request_chars=%d",
            len(state["research_request"]),
        )
        result = await research(state["research_request"])
        return {
            "result": {
                "report": format_report(result["report"], result["sources"]),
                "sources": result["sources"],
            }
        }

    graph = StateGraph(ResearchState)
    graph.add_node("conduct_research", conduct_research)
    graph.add_edge(START, "conduct_research")
    graph.add_edge("conduct_research", END)
    return graph.compile()


def parse_specialist_request(text: str) -> SpecialistRequest | None:
    """Decode the coordinator payload without accepting arbitrary JSON shapes."""
    try:
        return SpecialistRequest.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValueError):
        return None


def create_learning_path(profile: LearnerProfile) -> LearningPath:
    """Create a transparent initial scope before expensive grounded research."""
    known = [item.strip() for item in profile.known_concepts.split(",") if item.strip()]
    level_label = {
        1: "new to this subject",
        2: "recognizes the vocabulary",
        3: "can apply basic ideas",
        4: "is comfortable with the basics",
        5: "is advanced",
    }[profile.familiarity]
    gaps = [f"Concepts needed to achieve: {profile.goal}"]
    if not known:
        gaps.append(f"Core foundations of {profile.subject}")
    return LearningPath(
        goal=profile.goal,
        assumed_prerequisites=known,
        skipped_basics=known if profile.familiarity >= 4 else [],
        knowledge_gaps=gaps,
        assumptions=[f"Learner {level_label}."],
    )


def build_adaptive_research_graph(research: ResearchCallable) -> CompiledStateGraph:
    """Build the HITL graph: path review first, grounded research after acceptance."""

    async def review_path(state: AdaptiveResearchState) -> dict[str, Any]:
        request = state["request"]
        path = request.learning_path
        decision = interrupt(
            {
                "prompt_type": "learning_path",
                "prompt": "Review your learning path before course research starts.",
                "learning_path": path.model_dump(),
            }
        )
        if isinstance(decision, dict) and decision.get("action") == "adjust":
            if state.get("adjustment_count", 0) >= 1:
                raise ValueError("Only one learning-path adjustment is allowed.")
            update = decision.get("profile")
            if isinstance(update, dict):
                profile = LearnerProfile.model_validate(update)
                path = create_learning_path(profile)
                request = request.model_copy(
                    update={"profile": profile, "learning_path": path}
                )
                interrupt(
                    {
                        "prompt_type": "learning_path",
                        "prompt": "Review your adjusted learning path.",
                        "learning_path": path.model_dump(),
                    }
                )
                return {"request": request, "adjustment_count": 1}
        return {}

    async def conduct_research(
        state: AdaptiveResearchState,
    ) -> dict[str, ResearchResult]:
        request = state["request"]
        prompt = (
            f"Subject: {request.profile.subject}\nGoal: {request.learning_path.goal}\n"
            f"Required gaps: {', '.join(request.learning_path.knowledge_gaps)}\n"
            f"Skip or only briefly reference: {', '.join(request.learning_path.skipped_basics)}\n"
            f"Judge feedback: {request.judge_feedback}"
        )
        result = await research(prompt)
        return {
            "result": {
                "report": format_report(result["report"], result["sources"]),
                "sources": result["sources"],
            }
        }

    graph = StateGraph(AdaptiveResearchState)
    graph.add_node("review_path", review_path)
    graph.add_node("conduct_research", conduct_research)
    graph.add_edge(START, "review_path")
    graph.add_edge("review_path", "conduct_research")
    graph.add_edge("conduct_research", END)
    return graph.compile(checkpointer=MemorySaver())
