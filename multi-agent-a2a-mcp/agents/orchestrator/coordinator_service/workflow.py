"""LangGraph HITL workflow for validated learning-path approval."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from shared.learning_contracts import CoordinatorTaskState, LearningModule, LearningPath

from .pipeline import CoursePipeline

LOGGER = logging.getLogger(__name__)


class WorkflowState(TypedDict, total=False):
    task: CoordinatorTaskState
    feedback: str
    research_findings: str
    judge_feedback: str
    judge_passed: bool
    learning_path: LearningPath
    approved: bool
    judge_attempts: int


class LearningPathWorkflow:
    """Research, judge, then pause until the learner approves the path."""

    def __init__(self, pipeline: CoursePipeline) -> None:
        self._pipeline = pipeline
        self._graph = self._build().compile(checkpointer=MemorySaver())

    async def start(self, task: CoordinatorTaskState) -> dict[str, Any]:
        return await self._graph.ainvoke(
            {"task": task}, config={"configurable": {"thread_id": task.task_id}}
        )

    async def resume(self, task_id: str, payload: dict[str, str]) -> dict[str, Any]:
        return await self._graph.ainvoke(
            Command(resume=payload), config={"configurable": {"thread_id": task_id}}
        )

    def _build(self) -> StateGraph:
        async def research(state: WorkflowState) -> dict[str, str]:
            LOGGER.info(
                "workflow_progress task_id=%s stage=researching", state["task"].task_id
            )
            findings = await self._pipeline.research(
                state["task"], state.get("feedback", "")
            )
            return {"research_findings": findings}

        async def judge(state: WorkflowState) -> dict[str, Any]:
            LOGGER.info(
                "workflow_progress task_id=%s stage=fact-checking",
                state["task"].task_id,
            )
            passed, feedback = await self._pipeline.judge(
                state["task"], state["research_findings"]
            )
            return {
                "judge_passed": passed,
                "judge_feedback": feedback,
                # Feed a failed verdict back into the next research attempt so the
                # researcher can repair the exact missing or unsupported evidence.
                "feedback": feedback,
                "judge_attempts": state.get("judge_attempts", 0) + 1,
            }

        def judge_route(state: WorkflowState) -> str:
            if state["judge_passed"]:
                return "present_path"
            if state.get("judge_attempts", 0) >= 2:
                raise ValueError(
                    "Research could not pass the judge after two attempts."
                )
            return "research"

        def present_path(state: WorkflowState) -> dict[str, LearningPath]:
            task = state["task"]
            LOGGER.info(
                "workflow_progress task_id=%s stage=awaiting-approval", task.task_id
            )
            return {"learning_path": _path_for(task, state["judge_feedback"])}

        def review(state: WorkflowState) -> dict[str, Any]:
            decision = interrupt(
                {
                    "type": "learning_path_approval",
                    "prompt": "Does this match your current understanding and learning goal?",
                    "learning_path": state["learning_path"].model_dump(),
                }
            )
            if not isinstance(decision, dict):
                raise ValueError("A structured approval decision is required.")
            if decision.get("type") == "approve":
                LOGGER.info(
                    "workflow_resumed task_id=%s action=approve", state["task"].task_id
                )
                return {"approved": True}
            if decision.get("type") == "feedback" and isinstance(
                decision.get("text"), str
            ):
                LOGGER.info(
                    "workflow_resumed task_id=%s action=feedback", state["task"].task_id
                )
                return {"feedback": decision["text"], "approved": False}
            raise ValueError("The approval decision is not valid.")

        def review_route(state: WorkflowState) -> str:
            return END if state.get("approved") else "research"

        graph = StateGraph(WorkflowState)
        graph.add_node("research", research)
        graph.add_node("judge", judge)
        graph.add_node("present_path", present_path)
        graph.add_node("review", review)
        graph.add_edge(START, "research")
        graph.add_edge("research", "judge")
        graph.add_conditional_edges("judge", judge_route)
        graph.add_edge("present_path", "review")
        graph.add_conditional_edges("review", review_route)
        return graph


def _path_for(task: CoordinatorTaskState, judge_feedback: str) -> LearningPath:
    """Present a compact path only after the independent judge approves research."""
    if task.profile is None:
        raise ValueError("A learner profile is required to build a learning path.")
    subject = task.profile.subject
    goal = task.profile.goal
    return LearningPath(
        goal=goal,
        assumptions=["Assumed familiarity: intermediate (3/5)."],
        knowledge_gaps=[f"The concepts needed to achieve: {goal}"],
        modules=[
            LearningModule(
                title=f"Foundations of {subject}",
                outcome="Explain the essential concepts and vocabulary.",
            ),
            LearningModule(
                title="Core techniques",
                outcome="Apply the main techniques to focused exercises.",
            ),
            LearningModule(
                title="Practice and troubleshooting",
                outcome="Diagnose common mistakes and choose suitable approaches.",
            ),
            LearningModule(
                title="Goal-focused project",
                outcome=f"Use the skills to achieve: {goal}.",
            ),
        ],
        caveats=[judge_feedback] if judge_feedback else [],
    )
