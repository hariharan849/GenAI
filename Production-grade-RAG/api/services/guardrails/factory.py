from api.config import Settings
from api.services.ollama.client import OllamaClient

from .llama_guard import LlamaGuardClassifier
from .policy import GuardrailPolicyService
from .presidio import PresidioRedactor


def make_guardrail_policy_service(settings: Settings, ollama_client: OllamaClient) -> GuardrailPolicyService:
    guardrail_settings = settings.guardrails
    redactor = None
    if guardrail_settings.presidio_enabled:
        redactor = PresidioRedactor(
            entities=guardrail_settings.presidio_entities,
            score_threshold=guardrail_settings.presidio_score_threshold,
            allowlist_terms=guardrail_settings.presidio_allowlist_terms,
        )

    llama_guard = None
    if guardrail_settings.llama_guard_enabled:
        llama_guard = LlamaGuardClassifier(
            ollama_client=ollama_client,
            model=guardrail_settings.llama_guard_model,
            timeout_seconds=guardrail_settings.llama_guard_timeout_seconds,
        )

    return GuardrailPolicyService(
        settings=guardrail_settings,
        redactor=redactor,
        llama_guard=llama_guard,
    )
