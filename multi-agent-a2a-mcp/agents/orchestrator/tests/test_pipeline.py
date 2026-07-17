from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from coordinator_service.pipeline import CoursePipeline

from shared.learning_contracts import CoordinatorTaskState, LearnerProfile, LearningPath


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class FakeClient:
    def __init__(self, responses: list[dict]) -> None:
        self._responses = responses
        self.posts: list[str] = []
        self.requests: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        pass

    async def get(self, url: str) -> FakeResponse:
        return FakeResponse({"url": url.replace("/.well-known/agent-card.json", "")})

    async def post(self, url: str, json: dict) -> FakeResponse:
        self.posts.append(url)
        self.requests.append(json)
        return FakeResponse(self._responses.pop(0))


def completed(text: str) -> dict:
    return {
        "result": {
            "status": {"state": "completed"},
            "artifacts": [{"parts": [{"kind": "text", "text": text}]}],
        }
    }


def test_pipeline_calls_every_specialist_in_order(monkeypatch) -> None:
    client = FakeClient(
        [
            completed("research"),
            completed('{"status":"pass","feedback":"ready"}'),
            completed("# Course"),
        ]
    )
    monkeypatch.setattr(
        "coordinator_service.pipeline._authenticated_client", lambda _: client
    )
    task = CoordinatorTaskState(
        task_id="task",
        context_id="context",
        owner_session_id="browser",
        profile=LearnerProfile(subject="Python", familiarity=3, goal="asyncio"),
        learning_path=LearningPath(goal="asyncio"),
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    stages: list[str] = []

    course = asyncio.run(
        CoursePipeline(
            {
                "researcher": "http://researcher/a2a/agent/.well-known/agent-card.json",
                "judge": "http://judge/a2a/agent/.well-known/agent-card.json",
                "content_builder": "http://builder/a2a/agent/.well-known/agent-card.json",
            }
        ).run(task, stages.append)
    )

    assert course == "# Course"
    assert stages == ["researching", "fact-checking", "writing"]
    assert client.posts == [
        "http://researcher/a2a/agent",
        "http://judge/a2a/agent",
        "http://builder/a2a/agent",
    ]
    judge_payload = json.loads(
        client.requests[1]["params"]["message"]["parts"][0]["text"]
    )
    assert judge_payload["profile"]["goal"] == "asyncio"
    assert judge_payload["research_findings"] == "research"


def test_pipeline_writes_after_one_failed_fact_check(monkeypatch) -> None:
    client = FakeClient(
        [
            completed("research"),
            completed('{"status":"fail","feedback":"needs sources"}'),
            completed("# Course"),
        ]
    )
    monkeypatch.setattr(
        "coordinator_service.pipeline._authenticated_client", lambda _: client
    )
    task = CoordinatorTaskState(
        task_id="task",
        context_id="context",
        owner_session_id="browser",
        profile=LearnerProfile(subject="Python", familiarity=3, goal="asyncio"),
        learning_path=LearningPath(goal="asyncio"),
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )

    course = asyncio.run(
        CoursePipeline(
            {
                "researcher": "http://researcher/a2a/agent/.well-known/agent-card.json",
                "judge": "http://judge/a2a/agent/.well-known/agent-card.json",
                "content_builder": "http://builder/a2a/agent/.well-known/agent-card.json",
            }
        ).run(task, lambda _: None)
    )

    assert course == "# Course"
    assert client.posts == [
        "http://researcher/a2a/agent",
        "http://judge/a2a/agent",
        "http://builder/a2a/agent",
    ]
