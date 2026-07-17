# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

import pytest

JUDGE_DIR = Path(__file__).parents[1] / "agents" / "judge"
sys.path.insert(0, str(JUDGE_DIR))

from judge_service.service import FALLBACK_FEEDBACK, JudgeService


class FakeSourceClient:
    enabled = True

    async def verify_citations(self, urls: list[str]) -> dict[str, object]:
        return {
            "citations": [
                {
                    "submitted_url": url,
                    "status": "verified",
                    "evidence": "Supporting source text.",
                }
                for url in urls
            ]
        }


REPORT = "Research findings.\n\n## Sources\n- https://example.com/source"


@pytest.mark.asyncio
async def test_invalid_model_output_is_retried_once() -> None:
    calls = 0

    def invalid_assessment(_: object) -> str:
        nonlocal calls
        calls += 1
        return "not JSON"

    feedback = await JudgeService(
        invalid_assessment, FakeSourceClient(), default_pass=False
    ).evaluate(REPORT)

    assert calls == 2
    assert feedback.status == "fail"
    assert feedback.feedback == FALLBACK_FEEDBACK


@pytest.mark.asyncio
async def test_valid_model_output_is_returned() -> None:
    service = JudgeService(
        lambda _: '{"status":"pass","feedback":"Complete."}', FakeSourceClient()
    )

    feedback = await service.evaluate(REPORT)

    assert feedback.model_dump() == {"status": "pass", "feedback": "Complete."}


@pytest.mark.asyncio
async def test_missing_citations_are_optional() -> None:
    feedback = await JudgeService(
        lambda _: '{"status":"pass","feedback":"No citations needed."}',
        FakeSourceClient(),
        default_pass=False,
    ).evaluate("Research findings only")

    assert feedback.model_dump() == {
        "status": "pass",
        "feedback": "No citations needed.",
    }


@pytest.mark.asyncio
async def test_unverified_citation_fails_with_url() -> None:
    class InaccessibleSourceClient(FakeSourceClient):
        async def verify_citations(self, urls: list[str]) -> dict[str, object]:
            return {
                "citations": [
                    {
                        "submitted_url": urls[0],
                        "status": "unverified",
                        "reason": "citation could not be retrieved",
                    }
                ]
            }

    feedback = await JudgeService(
        lambda _: "should not run", InaccessibleSourceClient(), default_pass=False
    ).evaluate(REPORT)

    assert feedback.status == "fail"
    assert "https://example.com/source" in feedback.feedback


@pytest.mark.asyncio
async def test_citation_verification_outage_fails_closed() -> None:
    class UnavailableSourceClient(FakeSourceClient):
        async def verify_citations(self, urls: list[str]) -> dict[str, object]:
            raise RuntimeError("MCP unavailable")

    feedback = await JudgeService(
        lambda _: "should not run", UnavailableSourceClient(), default_pass=False
    ).evaluate(REPORT)

    assert feedback.status == "fail"
    assert "unavailable" in feedback.feedback


@pytest.mark.asyncio
async def test_model_fail_is_preserved() -> None:
    feedback = await JudgeService(
        lambda _: '{"status":"fail","feedback":"Claim lacks evidence."}',
        FakeSourceClient(),
        default_pass=False,
    ).evaluate(REPORT)

    assert feedback.status == "fail"
    assert feedback.feedback == "Claim lacks evidence."


@pytest.mark.asyncio
async def test_local_default_pass_accepts_verified_research_after_one_review() -> None:
    calls = 0

    def failing_assessment(_: object) -> str:
        nonlocal calls
        calls += 1
        return '{"status":"fail","feedback":"Optional local caveat."}'

    feedback = await JudgeService(
        failing_assessment, FakeSourceClient(), default_pass=True
    ).evaluate(REPORT)

    assert calls == 1
    assert feedback.model_dump() == {
        "status": "pass",
        "feedback": "Optional local caveat.",
    }
