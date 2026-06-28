"""Unit tests for Neo4jClient.write_triples()."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.graph.client import Neo4jClient
from api.services.graph.extraction import Triple


def _make_client() -> Neo4jClient:
    with patch("api.services.graph.client.AsyncGraphDatabase") if False else patch(
        "neo4j.AsyncGraphDatabase.driver"
    ):
        client = Neo4jClient.__new__(Neo4jClient)
        mock_driver = MagicMock()
        client._driver = mock_driver
        return client, mock_driver


@pytest.fixture
def client_and_driver():
    client = Neo4jClient.__new__(Neo4jClient)
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    mock_driver = MagicMock()
    mock_driver.session = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_session),
        __aexit__=AsyncMock(return_value=False),
    ))
    client._driver = mock_driver
    return client, mock_session


@pytest.mark.asyncio
async def test_write_triples_happy_path(client_and_driver):
    client, mock_session = client_and_driver
    triples = [
        Triple(entity_a="Blur", relationship="ACCEPTS_INPUT", entity_b="Read"),
        Triple(entity_a="Blur", relationship="OUTPUTS_TO", entity_b="Write"),
    ]
    written = await client.write_triples(triples)
    assert written == 2
    assert mock_session.run.call_count == 2


@pytest.mark.asyncio
async def test_write_triples_empty_list(client_and_driver):
    client, mock_session = client_and_driver
    written = await client.write_triples([])
    assert written == 0
    mock_session.run.assert_not_called()


@pytest.mark.asyncio
async def test_write_triples_similar_to(client_and_driver):
    client, mock_session = client_and_driver
    triples = [Triple(entity_a="Blur", relationship="SIMILAR_TO", entity_b="Defocus")]
    written = await client.write_triples(triples)
    assert written == 1
    call_args = mock_session.run.call_args
    assert "SIMILAR_TO" in call_args[0][0]
    assert call_args[1]["ea"] == "Blur"
    assert call_args[1]["eb"] == "Defocus"


@pytest.mark.asyncio
async def test_write_triples_neo4j_unreachable(client_and_driver):
    client, mock_session = client_and_driver
    mock_session.run = AsyncMock(side_effect=Exception("ServiceUnavailable"))
    triples = [Triple(entity_a="Blur", relationship="ACCEPTS_INPUT", entity_b="Read")]
    written = await client.write_triples(triples)
    assert written == 0
