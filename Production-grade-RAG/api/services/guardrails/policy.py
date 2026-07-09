import logging

from api.config import GuardrailsSettings

from .llama_guard import LlamaGuardClassifier
from .models import GuardrailLayer, PolicyAction, PolicyCheckResult, PolicyDecision
from .presidio import PresidioRedactor

logger = logging.getLogger(__name__)


class GuardrailPolicyService:
    """Coordinates Presidio privacy checks and Llama Guard safety checks."""

    def __init__(
        self,
        settings: GuardrailsSettings,
        redactor: PresidioRedactor | None = None,
        llama_guard: LlamaGuardClassifier | None = None,
    ):
        self.settings = settings
        self.redactor = redactor
        self.llama_guard = llama_guard

    async def initialize(self) -> None:
        if not self.settings.enabled or not self.settings.llama_guard_enabled or self.llama_guard is None:
            return

        try:
            available = await self.llama_guard.ensure_model_available()
        except Exception as e:
            available = False
            logger.warning("Unable to verify Llama Guard model availability: %s", e)

        if not available:
            message = f"Llama Guard model '{self.settings.llama_guard_model}' is not available"
            if self.settings.llama_guard_fail_closed_input or self.settings.llama_guard_fail_closed_output:
                raise RuntimeError(message)
            else:
                logger.info(message)

    async def check_input(self, text: str) -> PolicyDecision:
        if not self.settings.enabled:
            return PolicyDecision(
                layer=GuardrailLayer.INPUT,
                action=PolicyAction.ALLOW,
                reason="Guardrails disabled",
                sanitized_text=text,
            )

        sanitized_text = text
        pii_redacted = False
        checks: list[PolicyCheckResult] = []

        if self.settings.presidio_enabled and self.redactor is not None:
            try:
                redaction = self.redactor.redact_text(text)
                sanitized_text = redaction.redacted_text
                pii_redacted = redaction.pii_redacted
                checks.append(
                    PolicyCheckResult(
                        name="presidio",
                        action=PolicyAction.REDACT if redaction.pii_redacted else PolicyAction.ALLOW,
                        reason="PII redacted" if redaction.pii_redacted else "No PII detected",
                        categories=redaction.entities,
                        metadata={"entities": redaction.entities},
                    )
                )
            except Exception as e:
                if self.settings.presidio_fail_closed:
                    return PolicyDecision(
                        layer=GuardrailLayer.INPUT,
                        action=PolicyAction.BLOCK,
                        reason=f"Presidio redaction failed: {e}",
                        checks=checks,
                        sanitized_text=sanitized_text,
                    )
                logger.warning("Presidio redaction failed; continuing because fail-closed is disabled: %s", e)
                checks.append(
                    PolicyCheckResult(
                        name="presidio",
                        action=PolicyAction.REVIEW,
                        reason=f"Presidio redaction failed: {e}",
                    )
                )

        safety_decision = await self._check_llama_guard(
            layer=GuardrailLayer.INPUT,
            prompt=sanitized_text,
            response=None,
            fail_closed=self.settings.llama_guard_fail_closed_input,
        )
        checks.extend(safety_decision.checks)
        if safety_decision.action == PolicyAction.BLOCK:
            return PolicyDecision(
                layer=GuardrailLayer.INPUT,
                action=PolicyAction.BLOCK,
                reason=safety_decision.reason,
                checks=checks,
                sanitized_text=sanitized_text,
                pii_redacted=pii_redacted,
                categories=safety_decision.categories,
            )

        return PolicyDecision(
            layer=GuardrailLayer.INPUT,
            action=PolicyAction.REDACT if pii_redacted else PolicyAction.ALLOW,
            reason="PII redacted; input allowed" if pii_redacted else "Input allowed",
            checks=checks,
            sanitized_text=sanitized_text,
            pii_redacted=pii_redacted,
        )

    async def check_output(self, prompt: str, response: str) -> PolicyDecision:
        if not self.settings.enabled:
            return PolicyDecision(
                layer=GuardrailLayer.OUTPUT,
                action=PolicyAction.ALLOW,
                reason="Guardrails disabled",
            )

        return await self._check_llama_guard(
            layer=GuardrailLayer.OUTPUT,
            prompt=prompt,
            response=response,
            fail_closed=self.settings.llama_guard_fail_closed_output,
        )

    def grounding_failed(self, reason: str) -> PolicyDecision:
        return PolicyDecision(
            layer=GuardrailLayer.OUTPUT,
            action=PolicyAction.BLOCK,
            reason=reason,
            checks=[
                PolicyCheckResult(
                    name="source_grounding",
                    action=PolicyAction.BLOCK,
                    reason=reason,
                )
            ],
            categories=["grounding_failed"],
        )

    async def _check_llama_guard(
        self,
        layer: GuardrailLayer,
        prompt: str,
        response: str | None,
        fail_closed: bool,
    ) -> PolicyDecision:
        if not self.settings.llama_guard_enabled or self.llama_guard is None:
            return PolicyDecision(layer=layer, action=PolicyAction.ALLOW, reason="Llama Guard disabled")

        try:
            result = (
                await self.llama_guard.classify_output(prompt, response)
                if response is not None
                else await self.llama_guard.classify_input(prompt)
            )
        except Exception as e:
            action = PolicyAction.BLOCK if fail_closed else PolicyAction.REVIEW
            return PolicyDecision(
                layer=layer,
                action=action,
                reason=f"Llama Guard classification failed: {e}",
                checks=[
                    PolicyCheckResult(
                        name="llama_guard",
                        action=action,
                        reason=f"classification failed: {e}",
                    )
                ],
            )

        action = PolicyAction.ALLOW if result.safe else PolicyAction.BLOCK
        return PolicyDecision(
            layer=layer,
            action=action,
            reason=result.reason,
            checks=[
                PolicyCheckResult(
                    name="llama_guard",
                    action=action,
                    reason=result.reason,
                    categories=result.categories,
                    metadata={"raw_response": result.raw_response},
                )
            ],
            categories=result.categories,
        )
