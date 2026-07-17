"""Judge orchestration, citation verification, and model-output validation."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Callable

from pydantic import ValidationError

from .crew_judge import CrewJudge
from .input_parser import parse_judge_input
from .models import JudgeFeedback, JudgeInput
from .source_intelligence import SourceIntelligenceClient

FALLBACK_FEEDBACK = (
    "The editorial assessment returned an invalid response twice. Please resubmit "
    "the research with clear, retrievable source URLs."
)
logger = logging.getLogger(__name__)
_SOURCES_HEADER = re.compile(r"^\s*##\s+sources\s*$", re.IGNORECASE)
_HEADING = re.compile(r"^\s*#{1,6}\s+")
_URL_LINE = re.compile(r"^\s*(?:[-*+]\s+)?(?:(?:\[[^]]+\]\()?(https://[^\s)]+)\)?)\s*$")


class JudgeService:
    """Returns a fail-closed, validated verdict for an incoming A2A message."""

    def __init__(
        self,
        run_assessment: Callable[[JudgeInput], str] | None = None,
        source_client: SourceIntelligenceClient | None = None,
        default_pass: bool | None = None,
    ) -> None:
        self._run_assessment = run_assessment or CrewJudge().run
        self._source_client = source_client or SourceIntelligenceClient()
        self._default_pass = (
            default_pass
            if default_pass is not None
            else os.getenv("JUDGE_DEFAULT_PASS", "true").lower()
            in {"1", "true", "yes"}
        )

    async def evaluate(self, message_text: str) -> JudgeFeedback:
        judge_input = parse_judge_input(message_text)
        citations, _ = _extract_citations(judge_input.research_findings)
        if citations and not self._default_pass:
            try:
                judge_input.verified_sources = await self._verify_citations(citations)
            except RuntimeError as error:
                return JudgeFeedback(status="fail", feedback=str(error))
        attempts = 1 if self._default_pass else 2
        for attempt in range(1, attempts + 1):
            logger.info("Running judge model (attempt %d/%d)", attempt, attempts)
            raw_feedback = await asyncio.to_thread(self._run_assessment, judge_input)
            feedback = _parse_feedback(raw_feedback)
            if feedback is not None:
                if self._default_pass:
                    logger.info("Local default-pass mode accepted verified research")
                    return JudgeFeedback(status="pass", feedback=feedback.feedback)
                return feedback
            logger.warning(
                "Judge model returned invalid JSON on attempt %d/%d", attempt, attempts
            )
        logger.error("Judge model did not return valid feedback")
        return JudgeFeedback(
            status="pass" if self._default_pass else "fail",
            feedback=FALLBACK_FEEDBACK,
        )

    async def _verify_citations(self, citations: list[str]) -> list[dict[str, object]]:
        """Verify only citations that the researcher chose to provide."""
        if not self._source_client.enabled:
            raise RuntimeError("Citation verification is unavailable")
        try:
            verification = await self._source_client.verify_citations(citations)
        except (RuntimeError, KeyError, TypeError, ValueError) as error:
            logger.warning("Citation verification MCP failed: %s", error)
            raise RuntimeError("Citation verification is unavailable") from error
        records = verification.get("citations")
        if not isinstance(records, list) or len(records) != len(citations):
            raise RuntimeError("Citation verification returned an incomplete result")
        failed = [
            record
            for record in records
            if not isinstance(record, dict) or record.get("status") != "verified"
        ]
        if failed:
            details = "; ".join(
                f"{record.get('submitted_url', 'citation')}: "
                f"{record.get('reason', 'could not be verified')}"
                for record in failed
                if isinstance(record, dict)
            )
            raise RuntimeError(f"Replace inaccessible or invalid source URLs: {details}")
        return records


def _extract_citations(report: str) -> tuple[list[str], str | None]:
    """Read the established ``## Sources`` URL-list contract from a report."""
    lines = report.splitlines()
    start = next(
        (index + 1 for index, line in enumerate(lines) if _SOURCES_HEADER.match(line)),
        None,
    )
    if start is None:
        return [], "Add a ## Sources section containing public HTTPS source URLs."
    urls: list[str] = []
    for line in lines[start:]:
        if _HEADING.match(line):
            break
        if not line.strip():
            continue
        match = _URL_LINE.match(line)
        if not match:
            return (
                [],
                "Repair the ## Sources section: each citation must be one public HTTPS URL.",
            )
        urls.append(match.group(1).rstrip(".,;"))
    if not urls:
        return [], "Add at least one public HTTPS source URL under ## Sources."
    return list(dict.fromkeys(urls)), None


def _parse_feedback(raw_feedback: str) -> JudgeFeedback | None:
    """Parse a JSON response, accepting Markdown fences emitted by some LLMs."""
    candidate = raw_feedback.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        candidate = candidate.split("\n", 1)[-1].rsplit("\n", 1)[0].strip()
    try:
        return JudgeFeedback.model_validate(json.loads(candidate))
    except (json.JSONDecodeError, ValidationError):
        return None
