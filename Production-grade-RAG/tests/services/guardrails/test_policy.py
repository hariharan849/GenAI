import pytest

from api.config import GuardrailsSettings
from api.services.guardrails.llama_guard import LlamaGuardClassifier
from api.services.guardrails.models import LlamaGuardResult, PiiRedactionResult, PolicyAction
from api.services.guardrails.policy import GuardrailPolicyService


class FakeRedactor:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def redact_text(self, text: str):
        if self.error:
            raise self.error
        return self.result or PiiRedactionResult(original_text=text, redacted_text=text)


class FakeLlamaGuard:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.input_prompt = None
        self.output_prompt = None
        self.output_response = None
        self.available = True

    async def ensure_model_available(self):
        if self.error:
            raise self.error
        return self.available

    async def classify_input(self, prompt: str):
        self.input_prompt = prompt
        if self.error:
            raise self.error
        return self.result or LlamaGuardResult(safe=True, raw_response="safe")

    async def classify_output(self, prompt: str, response: str):
        self.output_prompt = prompt
        self.output_response = response
        if self.error:
            raise self.error
        return self.result or LlamaGuardResult(safe=True, raw_response="safe")


@pytest.mark.asyncio
async def test_input_redacts_pii_then_classifies_sanitized_text():
    redactor = FakeRedactor(
        PiiRedactionResult(
            original_text="Alex is in Boston",
            redacted_text="[PERSON] is in [LOCATION]",
            pii_redacted=True,
            entities=["PERSON", "LOCATION"],
        )
    )
    llama_guard = FakeLlamaGuard()
    service = GuardrailPolicyService(GuardrailsSettings(), redactor=redactor, llama_guard=llama_guard)

    decision = await service.check_input("Alex is in Boston")

    assert decision.action == PolicyAction.REDACT
    assert decision.pii_redacted is True
    assert decision.sanitized_text == "[PERSON] is in [LOCATION]"
    assert llama_guard.input_prompt == "[PERSON] is in [LOCATION]"
    scoring = decision.to_guardrail_scoring()
    assert scoring.score == 100


@pytest.mark.asyncio
async def test_unsafe_input_blocks():
    service = GuardrailPolicyService(
        GuardrailsSettings(),
        redactor=FakeRedactor(),
        llama_guard=FakeLlamaGuard(LlamaGuardResult(safe=False, categories=["S1"], raw_response="unsafe\nS1")),
    )

    decision = await service.check_input("unsafe prompt")

    assert decision.action == PolicyAction.BLOCK
    assert decision.categories == ["S1"]
    assert decision.to_guardrail_scoring().score == 0


@pytest.mark.asyncio
async def test_llama_guard_timeout_fails_closed_for_output():
    service = GuardrailPolicyService(
        GuardrailsSettings(llama_guard_fail_closed_output=True),
        redactor=FakeRedactor(),
        llama_guard=FakeLlamaGuard(error=TimeoutError("timed out")),
    )

    decision = await service.check_output("question", "answer")

    assert decision.action == PolicyAction.BLOCK
    assert decision.to_guardrail_scoring().score == 0


def test_llama_guard_parser_accepts_safe_and_unsafe_categories():
    assert LlamaGuardClassifier.parse_response("safe").safe is True

    unsafe = LlamaGuardClassifier.parse_response("unsafe\nS1, S2")

    assert unsafe.safe is False
    assert unsafe.categories == ["S1", "S2"]


def test_grounding_failed_projects_to_zero_with_category():
    service = GuardrailPolicyService(GuardrailsSettings(), redactor=FakeRedactor(), llama_guard=FakeLlamaGuard())

    decision = service.grounding_failed("Answer does not reference any retrieved source")

    assert decision.action == PolicyAction.BLOCK
    assert decision.categories == ["grounding_failed"]
    assert decision.to_guardrail_scoring().score == 0


@pytest.mark.asyncio
async def test_initialize_raises_when_model_missing_and_fail_closed():
    llama_guard = FakeLlamaGuard()
    llama_guard.available = False
    service = GuardrailPolicyService(
        GuardrailsSettings(llama_guard_fail_closed_input=True),
        redactor=FakeRedactor(),
        llama_guard=llama_guard,
    )

    with pytest.raises(RuntimeError, match="Llama Guard model"):
        await service.initialize()
