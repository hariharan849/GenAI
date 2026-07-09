from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PolicyAction(StrEnum):
    ALLOW = "allow"
    REDACT = "redact"
    BLOCK = "block"
    REVIEW = "review"


class GuardrailLayer(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


class PolicyCheckResult(BaseModel):
    name: str
    action: PolicyAction
    reason: str
    categories: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PiiRedactionResult(BaseModel):
    original_text: str
    redacted_text: str
    pii_redacted: bool = False
    entities: list[str] = Field(default_factory=list)
    analyzer_results: list[dict[str, Any]] = Field(default_factory=list)


class LlamaGuardResult(BaseModel):
    safe: bool
    categories: list[str] = Field(default_factory=list)
    raw_response: str = ""
    reason: str = ""


class PolicyDecision(BaseModel):
    layer: GuardrailLayer
    action: PolicyAction
    reason: str
    checks: list[PolicyCheckResult] = Field(default_factory=list)
    sanitized_text: str | None = None
    pii_redacted: bool = False
    categories: list[str] = Field(default_factory=list)

    def to_guardrail_scoring(self):
        """Project native policy decisions into the legacy score-shaped API."""
        from api.services.agents.models import GuardrailScoring

        score_by_action = {
            PolicyAction.ALLOW: 100,
            PolicyAction.REDACT: 100,
            PolicyAction.BLOCK: 0,
            PolicyAction.REVIEW: 50,
        }
        return GuardrailScoring(
            score=score_by_action[self.action],
            reason=self.reason,
        )
