"""Converts A2A text messages into judge input without coupling to ADK state."""

import json
import logging

from .models import JudgeInput, SpecialistRequest

logger = logging.getLogger(__name__)


def parse_judge_input(message_text: str) -> JudgeInput:
    """Prefer the structured task format and safely fall back to plain text."""
    try:
        payload = json.loads(message_text)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        if SpecialistRequest is not None:
            try:
                request = SpecialistRequest.model_validate(payload)
                return JudgeInput(
                    original_request=request.profile.goal,
                    research_findings=request.research_findings,
                    skipped_basics=request.learning_path.skipped_basics,
                    knowledge_gaps=request.learning_path.knowledge_gaps,
                )
            except ValueError:
                logger.warning("Input did not match SpecialistRequest schema")
                pass
        original_request = payload.get("original_request")
        research_findings = payload.get("research_findings")
        if isinstance(original_request, str) and isinstance(research_findings, str):
            return JudgeInput(
                original_request=original_request,
                research_findings=research_findings,
            )

    logger.warning("Using unstructured judge input (%d characters)", len(message_text))
    return JudgeInput(research_findings=message_text)
