from __future__ import annotations

from collections.abc import Awaitable
from typing import TypedDict

import pytest
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Message,
    MessageSendParams,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
    TextPart,
)
from fastapi.testclient import TestClient
from researcher_service.app import create_app
from researcher_service.config import Settings
from researcher_service.executor import ResearcherAgentExecutor
from researcher_service.research import (
    ResearchResult,
    format_report,
    is_current_information_request,
    normalize_request,
)


class _GraphState(TypedDict):
    result: ResearchResult


class FakeGraph:
    def __init__(self, result: ResearchResult | Exception) -> None:
        self._result = result
        self.requests: list[dict[str, str]] = []

    def ainvoke(self, state: dict[str, str]) -> Awaitable[_GraphState]:
        async def invoke() -> _GraphState:
            self.requests.append(state)
            if isinstance(self._result, Exception):
                raise self._result
            return {"result": self._result}

        return invoke()


def _context(*texts: str) -> RequestContext:
    message = Message(
        role=Role.user,
        messageId="message-1",
        taskId="task-1",
        contextId="context-1",
        parts=[Part(root=TextPart(text=text)) for text in texts],
    )
    return RequestContext(request=MessageSendParams(message=message))


async def _events(queue: EventQueue) -> list[object]:
    events: list[object] = []
    while not queue.queue.empty():
        events.append(await queue.dequeue_event(no_wait=True))
    return events


def test_normalize_request_and_format_sources() -> None:
    assert normalize_request([" topic ", "feedback"]) == "topic\nfeedback"
    assert format_report("Findings", ["https://one", "https://one", "https://two"]) == (
        "Findings\n\n## Sources\n- https://one\n- https://two"
    )


def test_current_information_request_detection() -> None:
    assert is_current_information_request("What is the latest AI news?")
    assert not is_current_information_request("Explain the history of algebra")


def test_normalize_request_rejects_oversized_input() -> None:
    with pytest.raises(ValueError, match="32,000"):
        normalize_request(["x" * 32_001])


@pytest.mark.asyncio
async def test_executor_streams_work_artifact_and_completion() -> None:
    graph = FakeGraph({"report": "Research", "sources": ["https://example.test"]})
    queue = EventQueue()

    await ResearcherAgentExecutor(graph).execute(_context("climate", "policy"), queue)

    events = await _events(queue)
    assert graph.requests == [{"research_request": "climate\npolicy"}]
    assert isinstance(events[0], TaskStatusUpdateEvent)
    assert events[0].status.state is TaskState.working
    assert isinstance(events[1], TaskArtifactUpdateEvent)
    assert events[1].artifact.parts[0].root.text == "Research"
    assert isinstance(events[2], TaskStatusUpdateEvent)
    assert events[2].status.state is TaskState.completed


@pytest.mark.asyncio
async def test_executor_streams_terminal_failure() -> None:
    queue = EventQueue()
    await ResearcherAgentExecutor(FakeGraph(RuntimeError("provider down"))).execute(
        _context("topic"), queue
    )

    events = await _events(queue)
    assert isinstance(events[-1], TaskStatusUpdateEvent)
    assert events[-1].status.state is TaskState.failed


def test_app_exposes_health_and_preserved_agent_card() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        public_url="http://localhost:8001",
    )

    async def research(_: str) -> ResearchResult:
        return {"report": "Research", "sources": []}

    client = TestClient(create_app(lambda: settings, research))
    assert client.get("/healthz").json() == {"status": "ok"}
    card = client.get("/a2a/agent/.well-known/agent-card.json")
    assert card.status_code == 200
    assert card.json()["url"] == "http://localhost:8001/a2a/agent"
    assert card.json()["capabilities"]["streaming"] is True

    response = client.post(
        "/a2a/agent",
        json={
            "jsonrpc": "2.0",
            "id": "request-1",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "messageId": "message-1",
                    "parts": [{"kind": "text", "text": "topic"}],
                }
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["status"]["state"] == "completed"
