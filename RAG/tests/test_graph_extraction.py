"""Unit tests for api.services.graph.extraction."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.graph.extraction import Triple, TripleList, extract_triples


def _make_instructor_mock(return_value=None, side_effect=None):
    """Patch instructor.from_openai to return a mock client."""
    mock_client = MagicMock()
    if side_effect:
        mock_client.chat.completions.create = AsyncMock(side_effect=side_effect)
    else:
        mock_client.chat.completions.create = AsyncMock(return_value=return_value)

    mock_instructor = MagicMock()
    mock_instructor.from_openai.return_value = mock_client
    mock_instructor.Mode.JSON = "json"
    return mock_instructor, mock_client


@pytest.mark.asyncio
async def test_extract_triples_happy_path():
    mock_result = TripleList(triples=[
        Triple(entity_a="Blur", relationship="ACCEPTS_INPUT", entity_b="Read"),
        Triple(entity_a="Blur", relationship="OUTPUTS_TO", entity_b="Write"),
    ])
    mock_instructor, _ = _make_instructor_mock(return_value=mock_result)

    with patch("api.services.graph.extraction.instructor", mock_instructor), \
         patch("api.services.graph.extraction.AsyncOpenAI"):
        triples = await extract_triples("Blur node accepts input from Read node.")

    assert len(triples) == 2
    assert triples[0].entity_a == "Blur"
    assert triples[0].relationship == "ACCEPTS_INPUT"
    assert triples[0].entity_b == "Read"


@pytest.mark.asyncio
async def test_extract_triples_empty_text():
    triples = await extract_triples("")
    assert triples == []

    triples = await extract_triples("   ")
    assert triples == []


@pytest.mark.asyncio
async def test_extract_triples_retry_exhausted():
    mock_instructor, _ = _make_instructor_mock(
        side_effect=Exception("instructor retry exhausted")
    )

    with patch("api.services.graph.extraction.instructor", mock_instructor), \
         patch("api.services.graph.extraction.AsyncOpenAI"):
        triples = await extract_triples("Some Nuke documentation text.")

    assert triples == []


@pytest.mark.asyncio
async def test_extract_triples_ollama_unreachable():
    import httpx

    mock_instructor, _ = _make_instructor_mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    with patch("api.services.graph.extraction.instructor", mock_instructor), \
         patch("api.services.graph.extraction.AsyncOpenAI"):
        triples = await extract_triples("Some Nuke documentation text.")

    assert triples == []


@pytest.mark.asyncio
async def test_extract_triples_no_relationships():
    mock_result = TripleList(triples=[])
    mock_instructor, _ = _make_instructor_mock(return_value=mock_result)

    with patch("api.services.graph.extraction.instructor", mock_instructor), \
         patch("api.services.graph.extraction.AsyncOpenAI"):
        triples = await extract_triples("No relationships in this text.")

    assert triples == []
