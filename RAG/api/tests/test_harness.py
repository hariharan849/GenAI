from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.evaluation.dataset import GoldenCase
from api.evaluation.harness import CaseResult, run_case, run_harness_from_cases


def _make_case(case_id: str = "test-1") -> GoldenCase:
    return GoldenCase(
        case_id=case_id,
        url="https://docs.foundry.com/nuke/node",
        question="What does the Merge node do?",
        expected_output="The Merge node composites two inputs.",
    )


@pytest.mark.asyncio
async def test_run_case_happy_path(mock_agentic_rag_service: MagicMock) -> None:
    with patch("api.evaluation.harness._score_case_sync", return_value={"FaithfulnessMetric": 0.9}):
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_executor = AsyncMock(return_value={"FaithfulnessMetric": 0.9})
            mock_loop.return_value.run_in_executor = mock_executor

            result = await run_case(mock_agentic_rag_service, _make_case(), judge_model="gpt-4o-mini")

    assert result.status == "scored"
    assert result.actual_output == "Nuke uses nodes for compositing."
    assert result.retrieval_context == ["Context chunk 1", "Context chunk 2"]
    assert result.expected_output == "The Merge node composites two inputs."
    assert "FaithfulnessMetric" in result.scores


@pytest.mark.asyncio
async def test_run_case_service_error() -> None:
    service = MagicMock()
    service.ask = AsyncMock(side_effect=RuntimeError("Ollama timeout"))

    result = await run_case(service, _make_case(), judge_model="gpt-4o-mini")

    assert result.status == "errored"
    assert result.expected_output == "The Merge node composites two inputs."
    assert "Ollama timeout" in (result.error or "")


@pytest.mark.asyncio
async def test_run_harness_from_cases_progress_cb(mock_agentic_rag_service: MagicMock) -> None:
    cases = [_make_case(f"case-{i}") for i in range(3)]
    call_count = 0

    def _cb() -> None:
        nonlocal call_count
        call_count += 1

    with patch("api.evaluation.harness.run_case", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = CaseResult(
            case_id="x", question="q", expected_output="a", status="scored", scores={"F": 0.8}
        )
        results = await run_harness_from_cases(
            mock_agentic_rag_service, cases, judge_model="gpt-4o-mini", progress_cb=_cb
        )

    assert len(results) == 3
    assert call_count == 3


@pytest.mark.asyncio
async def test_run_harness_from_cases_empty(mock_agentic_rag_service: MagicMock) -> None:
    results = await run_harness_from_cases(mock_agentic_rag_service, [], judge_model="gpt-4o-mini")
    assert results == []


@pytest.mark.asyncio
async def test_run_harness_from_cases_no_progress_cb(mock_agentic_rag_service: MagicMock) -> None:
    cases = [_make_case()]
    with patch("api.evaluation.harness.run_case", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = CaseResult(
            case_id="test-1", question="q", expected_output="a", status="scored", scores={}
        )
        # Should not raise even with progress_cb=None
        results = await run_harness_from_cases(mock_agentic_rag_service, cases, "gpt-4o-mini")
    assert len(results) == 1
