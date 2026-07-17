"""Canonical in-memory task service; never logs learner content."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from shared.learning_contracts import (
    ContinuationRequest,
    CoordinatorTaskState,
    LearnerProfile,
    LearningPath,
    TaskPhase,
)


class CoordinatorService:
    """Own state, idempotency, expiry, and learner-path progression."""

    def __init__(self) -> None:
        self._tasks: dict[str, CoordinatorTaskState] = {}
        self._idempotency: dict[tuple[str, str], CoordinatorTaskState] = {}

    def start(
        self, owner_session_id: str, profile: LearnerProfile
    ) -> CoordinatorTaskState:
        """Create a task and begin research before requesting learner input."""
        if not profile.goal:
            profile = profile.model_copy(update={"goal": f"Learn {profile.subject}"})
        task = CoordinatorTaskState(
            task_id=str(uuid.uuid4()),
            context_id=str(uuid.uuid4()),
            owner_session_id=owner_session_id,
            profile=profile,
            learning_path=_learning_path(profile),
            expires_at=_expiry(),
        )
        task.transition(TaskPhase.WORKING)
        self._tasks[task.task_id] = task
        return task

    def continue_task(
        self, owner_session_id: str, request: ContinuationRequest
    ) -> CoordinatorTaskState:
        """Validate an opaque continuation and apply one safe state transition."""
        task = self._tasks.get(request.task_id)
        if task is None or task.context_id != request.context_id:
            raise ValueError("Course session is no longer available.")
        if task.owner_session_id != owner_session_id:
            raise PermissionError("Course session does not belong to this browser.")
        if task.expires_at <= datetime.now(UTC):
            task.transition(TaskPhase.EXPIRED)
            raise ValueError("Course session has expired.")
        cached = self._idempotency.get((task.task_id, request.idempotency_key))
        if cached is not None:
            return cached
        if request.action == "cancel":
            task.transition(TaskPhase.CANCELED)
        elif request.action == "learning_path_adjusted":
            if task.adjustment_count >= 1:
                raise ValueError("Only one learning-path adjustment is allowed.")
            profile = LearnerProfile.model_validate_json(request.response)
            task.profile = profile
            task.learning_path = _learning_path(profile)
            task.adjustment_count += 1
            task.transition(TaskPhase.INPUT_REQUIRED)
        elif request.action in {"learning_path_accepted", "approve"}:
            if task.learning_path is None:
                raise ValueError("A learning path is required before starting.")
            task.transition(TaskPhase.WORKING)
        elif request.action == "feedback":
            if task.phase is not TaskPhase.INPUT_REQUIRED:
                raise ValueError(
                    "Feedback is only accepted while a path is awaiting approval."
                )
            if not request.response.strip():
                raise ValueError("Feedback cannot be empty.")
            task.transition(TaskPhase.WORKING)
        elif request.action == "retry":
            if task.phase != TaskPhase.RETRYABLE_FAILED or task.retry_count >= 2:
                raise ValueError("This task cannot be retried.")
            task.retry_count += 1
            task.transition(TaskPhase.WORKING)
        else:
            raise ValueError("This continuation action is not valid at this stage.")
        task.expires_at = _expiry()
        self._idempotency[(task.task_id, request.idempotency_key)] = task
        return task

    def get_task(self, owner_session_id: str, task_id: str) -> CoordinatorTaskState:
        task = self._tasks.get(task_id)
        if task is None or task.owner_session_id != owner_session_id:
            raise PermissionError("Course session is not available.")
        return task

    def set_stage(self, task_id: str, stage: str) -> None:
        self._tasks[task_id].stage = stage

    def await_approval(
        self,
        task_id: str,
        learning_path: LearningPath,
        findings: str,
        judge_feedback: str,
    ) -> None:
        task = self._tasks[task_id]
        task.learning_path = learning_path
        task.research_findings = findings
        task.judge_feedback = judge_feedback
        task.stage = "awaiting-approval"
        task.transition(TaskPhase.INPUT_REQUIRED)

    def complete_task(self, task_id: str, course: str) -> None:
        task = self._tasks[task_id]
        task.course = course
        task.stage = "completed"
        task.transition(TaskPhase.COMPLETED)

    def fail_task(self, task_id: str) -> None:
        task = self._tasks[task_id]
        task.stage = "failed"
        task.transition(TaskPhase.RETRYABLE_FAILED)


def _learning_path(profile: LearnerProfile) -> LearningPath:
    known = [item.strip() for item in profile.known_concepts.split(",") if item.strip()]
    return LearningPath(
        goal=profile.goal,
        assumed_prerequisites=known,
        skipped_basics=known if profile.familiarity >= 4 else [],
        knowledge_gaps=[f"Skills required for: {profile.goal}"],
        assumptions=[f"Familiarity level {profile.familiarity}/5."],
    )


def _expiry() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=30)
