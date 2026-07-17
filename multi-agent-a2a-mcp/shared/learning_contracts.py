"""Versioned contracts for learner-adaptive course creation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "v1"


class TaskPhase(str, Enum):
    SUBMITTED = "submitted"
    INPUT_REQUIRED = "input_required"
    WORKING = "working"
    RETRYABLE_FAILED = "retryable_failed"
    TERMINAL_FAILED = "terminal_failed"
    CANCELED = "canceled"
    EXPIRED = "expired"
    COMPLETED = "completed"


class LearnerProfile(BaseModel):
    """The bounded learner input used to scope a personalized course."""

    subject: str = Field(min_length=1, max_length=500)
    familiarity: int = Field(default=3, ge=1, le=5)
    known_concepts: str = Field(default="", max_length=4000)
    goal: str = Field(default="", max_length=1000)


class LearningModule(BaseModel):
    """One learner-visible, outcome-oriented learning-path step."""

    title: str
    outcome: str


class LearningPath(BaseModel):
    """The learner-visible explanation of personalized course scope."""

    goal: str
    assumed_prerequisites: list[str] = Field(default_factory=list)
    skipped_basics: list[str] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    modules: list[LearningModule] = Field(default_factory=list, max_length=6)
    caveats: list[str] = Field(default_factory=list)


class SpecialistRequest(BaseModel):
    """Payload sent from coordinator to researcher, judge, and builder."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["v1"] = "v1"
    profile: LearnerProfile
    learning_path: LearningPath
    research_findings: str = ""
    judge_feedback: str = ""


class ContinuationRequest(BaseModel):
    """Browser-to-coordinator continuation payload; config stays server-side."""

    task_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    action: Literal[
        "profile_submitted",
        "clarification_answered",
        "learning_path_adjusted",
        "learning_path_accepted",
        "retry",
        "cancel",
        "approve",
        "feedback",
    ]
    response: str = Field(default="", max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=128)


class CoordinatorTaskState(BaseModel):
    """Canonical, in-memory coordinator state with bounded counters."""

    task_id: str
    context_id: str
    owner_session_id: str
    phase: TaskPhase = TaskPhase.SUBMITTED
    sequence: int = 0
    clarification_count: int = Field(default=0, ge=0, le=1)
    adjustment_count: int = Field(default=0, ge=0, le=1)
    retry_count: int = Field(default=0, ge=0, le=2)
    profile: LearnerProfile | None = None
    learning_path: LearningPath | None = None
    research_findings: str = ""
    judge_feedback: str = ""
    course: str = ""
    stage: str = ""
    expires_at: datetime

    def transition(self, phase: TaskPhase) -> None:
        """Move between valid public phases in one place."""
        terminal = {
            TaskPhase.TERMINAL_FAILED,
            TaskPhase.CANCELED,
            TaskPhase.EXPIRED,
            TaskPhase.COMPLETED,
        }
        if self.phase in terminal:
            raise ValueError("Terminal tasks cannot transition.")
        self.phase = phase
        self.sequence += 1
