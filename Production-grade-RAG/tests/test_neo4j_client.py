"""Unit tests for Neo4jClient.write_triples()."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.services.graph.client import Neo4jClient
from api.services.graph.extraction import Triple


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
        Triple(
            subject_name="Blur",
            subject_type="NukeNode",
            predicate="HAS_KNOB",
            object_name="Size",
            object_type="Knob",
        ),
        Triple(
            subject_name="Size",
            subject_type="Knob",
            predicate="KNOB_CONTROLS",
            object_name="blur radius",
            object_type="Operation",
        ),
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
async def test_write_triples_uses_typed_labels_and_predicate(client_and_driver):
    client, mock_session = client_and_driver
    triples = [
        Triple(
            subject_name="Blur",
            subject_type="NukeNode",
            predicate="ACCEPTS_INPUT",
            object_name="2D image",
            object_type="InputType",
        )
    ]

    written = await client.write_triples(triples)

    assert written == 1
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]
    assert "MERGE (a:NukeNode" in cypher
    assert "MERGE (b:InputType" in cypher
    assert "[:ACCEPTS_INPUT]" in cypher
    assert call_args[1]["subject_name"] == "Blur"
    assert call_args[1]["subject_type"] == "NukeNode"
    assert call_args[1]["object_name"] == "2D image"
    assert call_args[1]["object_type"] == "InputType"


@pytest.mark.asyncio
async def test_write_triples_skips_unknown_fact_shape(client_and_driver):
    client, mock_session = client_and_driver
    triples = [
        SimpleNamespace(
            subject_name="Blur",
            subject_type="Tool",
            predicate="HAS_KNOB",
            object_name="Size",
            object_type="Knob",
        )
    ]

    written = await client.write_triples(triples)

    assert written == 0
    mock_session.run.assert_not_called()


@pytest.mark.asyncio
async def test_write_triples_neo4j_unreachable(client_and_driver):
    client, mock_session = client_and_driver
    mock_session.run = AsyncMock(side_effect=Exception("ServiceUnavailable"))
    triples = [
        Triple(
            subject_name="Blur",
            subject_type="NukeNode",
            predicate="HAS_KNOB",
            object_name="Size",
            object_type="Knob",
        )
    ]
    written = await client.write_triples(triples)
    assert written == 0
