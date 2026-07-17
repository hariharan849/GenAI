"""Domain models shared by the judge implementation."""

from typing import Any, Literal

from pydantic import BaseModel, Field

try:
    from shared.learning_contracts import SpecialistRequest
except ModuleNotFoundError:  # Service image has no repository-root import path.
    SpecialistRequest = None  # type: ignore[assignment]


class JudgeInput(BaseModel):
    """The user request and research that the judge evaluates."""

    original_request: str = ""
    research_findings: str
    skipped_basics: list[str] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    verified_sources: list[dict[str, Any]] = Field(default_factory=list)


class JudgeFeedback(BaseModel):
    """The stable feedback contract consumed by the ADK orchestrator."""

    status: Literal["pass", "fail"]
    feedback: str = Field(min_length=1)
