from __future__ import annotations

import pytest
from coordinator_service.service import CoordinatorService

from shared.learning_contracts import ContinuationRequest, LearnerProfile, TaskPhase


def profile() -> LearnerProfile:
    return LearnerProfile(
        subject="Python", familiarity=4, known_concepts="functions", goal="asyncio"
    )


def continuation(
    task_id: str, context_id: str, action: str, key: str = "key"
) -> ContinuationRequest:
    return ContinuationRequest(
        task_id=task_id, context_id=context_id, action=action, idempotency_key=key
    )


def test_start_begins_research_before_path_review() -> None:
    task = CoordinatorService().start("browser", profile())
    assert task.phase is TaskPhase.WORKING
    assert task.learning_path is not None
    assert "functions" in task.learning_path.skipped_basics


def test_owner_and_idempotency_are_enforced() -> None:
    service = CoordinatorService()
    task = service.start("browser", profile())
    request = continuation(task.task_id, task.context_id, "learning_path_accepted")
    accepted = service.continue_task("browser", request)
    duplicate = service.continue_task("browser", request)
    assert accepted.phase is TaskPhase.WORKING
    assert duplicate.sequence == accepted.sequence
    with pytest.raises(PermissionError):
        service.continue_task(
            "another-browser",
            continuation(task.task_id, task.context_id, "retry", "other"),
        )


def test_only_one_adjustment_is_allowed() -> None:
    service = CoordinatorService()
    task = service.start("browser", profile())
    adjusted = LearnerProfile(subject="Python", familiarity=2, goal="asyncio")
    request = continuation(task.task_id, task.context_id, "learning_path_adjusted")
    request.response = adjusted.model_dump_json()
    service.continue_task("browser", request)
    second = continuation(
        task.task_id, task.context_id, "learning_path_adjusted", "second"
    )
    second.response = adjusted.model_dump_json()
    with pytest.raises(ValueError, match="Only one"):
        service.continue_task("browser", second)
