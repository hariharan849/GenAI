from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from coordinator_service.workflow import LearningPathWorkflow

from shared.learning_contracts import CoordinatorTaskState, LearnerProfile, LearningPath


class FakePipeline:
    def __init__(self) -> None:
        self.research_calls: list[str] = []

    async def research(self, task: CoordinatorTaskState, feedback: str = "") -> str:
        self.research_calls.append(feedback)
        return "research"

    async def judge(
        self, task: CoordinatorTaskState, findings: str
    ) -> tuple[bool, str]:
        return True, "Validated by the judge."


def task() -> CoordinatorTaskState:
    return CoordinatorTaskState(
        task_id="thread-1",
        context_id="context-1",
        owner_session_id="browser",
        profile=LearnerProfile(subject="Python", goal="Build an API client"),
        learning_path=LearningPath(goal="Build an API client"),
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )


def test_workflow_interrupts_after_judge_and_resumes_approval() -> None:
    pipeline = FakePipeline()
    workflow = LearningPathWorkflow(pipeline)  # type: ignore[arg-type]

    paused = asyncio.run(workflow.start(task()))

    assert "__interrupt__" in paused
    assert len(paused["learning_path"].modules) == 4
    assert paused["judge_feedback"] == "Validated by the judge."

    completed = asyncio.run(workflow.resume("thread-1", {"type": "approve"}))

    assert completed["approved"] is True
    assert pipeline.research_calls == [""]


def test_feedback_replays_research_then_interrupts_again() -> None:
    pipeline = FakePipeline()
    workflow = LearningPathWorkflow(pipeline)  # type: ignore[arg-type]
    asyncio.run(workflow.start(task()))

    paused_again = asyncio.run(
        workflow.resume("thread-1", {"type": "feedback", "text": "More practice"})
    )

    assert "__interrupt__" in paused_again
    assert pipeline.research_calls == ["", "More practice"]


def test_judge_failure_retries_research_with_actionable_feedback() -> None:
    class RetryPipeline(FakePipeline):
        def __init__(self) -> None:
            super().__init__()
            self.judge_calls = 0

        async def judge(
            self, task: CoordinatorTaskState, findings: str
        ) -> tuple[bool, str]:
            self.judge_calls += 1
            if self.judge_calls == 1:
                return False, "Replace inaccessible source URL: https://example.com"
            return True, "Evidence verified."

    pipeline = RetryPipeline()
    workflow = LearningPathWorkflow(pipeline)  # type: ignore[arg-type]

    paused = asyncio.run(workflow.start(task()))

    assert "__interrupt__" in paused
    assert pipeline.research_calls == [
        "",
        "Replace inaccessible source URL: https://example.com",
    ]
    assert paused["judge_attempts"] == 2
