"""Unit tests for Ray Data indexing pipeline functions.

Tests cover the three pure stateless operators and the empty-pages fast-path.
Each test mocks its IO boundaries (DB, Jina API, OpenSearch) so no running
services are required.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import numpy as np
import pytest

# Make nuke_ingestion importable (mirrors conftest.py)
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrators" / "airflow" / "dags"))

from nuke_ingestion.indexing import (
    _chunk_page_remote,
    _embed_batch_remote,
    _os_bulk_remote,
    index_nuke_docs_ray,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PAGE_WITH_SECTIONS = {
    "id": "00000000-0000-0000-0000-000000000001",
    "url": "https://example.com/nuke/blur.html",
    "node_name": "Blur",
    "section": "filter_nodes",
    "raw_content": "",
    "sections": [
        {"title": "Overview", "text": "The Blur node applies a gaussian blur. " * 20},
        {"title": "Parameters", "text": "Width: controls the blur radius. " * 20},
    ],
}

PAGE_WITH_RAW_CONTENT = {
    "id": "00000000-0000-0000-0000-000000000002",
    "url": "https://example.com/nuke/grade.html",
    "node_name": "Grade",
    "section": "color_nodes",
    "raw_content": "The Grade node performs per-channel colour correction. " * 30,
    "sections": [],
}


# ---------------------------------------------------------------------------
# _chunk_page_remote
# ---------------------------------------------------------------------------

def test_chunk_page_remote_with_sections():
    chunks = _chunk_page_remote(PAGE_WITH_SECTIONS)
    assert len(chunks) > 0
    for c in chunks:
        assert c["chunk_text"]
        assert c["page_id"] == PAGE_WITH_SECTIONS["id"]
        assert c["url"] == PAGE_WITH_SECTIONS["url"]
        assert c["nuke_node_name"] == "Blur"
        assert "chunk_index" in c
        assert "section_title" in c


def test_chunk_page_remote_with_raw_content():
    chunks = _chunk_page_remote(PAGE_WITH_RAW_CONTENT)
    assert len(chunks) > 0
    for c in chunks:
        assert c["chunk_text"]
        assert c["page_id"] == PAGE_WITH_RAW_CONTENT["id"]
        assert c["nuke_node_name"] == "Grade"


# ---------------------------------------------------------------------------
# _embed_batch_remote
# ---------------------------------------------------------------------------

def test_embed_batch_remote_adds_float32_embedding():
    batch = {
        "page_id": ["id1", "id2"],
        "chunk_text": ["Hello world", "Nuke blur node"],
        "chunk_index": [0, 1],
        "url": ["https://example.com/a.html", "https://example.com/b.html"],
        "nuke_node_name": ["A", "B"],
        "section": ["s", "s"],
        "section_title": ["", ""],
    }

    fake_embeddings = [[0.1] * 1024, [0.2] * 1024]
    mock_client = MagicMock()
    mock_client.embed_passages = MagicMock(return_value=fake_embeddings)

    # asyncio.run calls embed_passages as a coroutine — wrap in coroutine mock
    import asyncio

    async def _async_embed(texts, **kwargs):
        return fake_embeddings

    mock_client.embed_passages = _async_embed

    with patch("api.services.embeddings.factory.make_embeddings_client", return_value=mock_client):
        result = _embed_batch_remote(batch)

    assert "embedding" in result
    assert isinstance(result["embedding"], np.ndarray)
    assert result["embedding"].dtype == np.float32
    assert result["embedding"].shape == (2, 1024)


# ---------------------------------------------------------------------------
# _os_bulk_remote
# ---------------------------------------------------------------------------

def test_os_bulk_remote_all_success():
    batch = {
        "page_id": ["pid1", "pid1"],
        "chunk_text": ["chunk A", "chunk B"],
        "chunk_index": [0, 1],
        "url": ["https://example.com/a.html", "https://example.com/a.html"],
        "nuke_node_name": ["A", "A"],
        "section": ["s", "s"],
        "section_title": ["", ""],
        "embedding": [np.zeros(1024, dtype=np.float32), np.zeros(1024, dtype=np.float32)],
    }

    mock_resp = {
        "items": [
            {"index": {"_id": "abc", "result": "created"}},
            {"index": {"_id": "def", "result": "created"}},
        ]
    }
    mock_os = MagicMock()
    mock_os.client.bulk.return_value = mock_resp

    settings = SimpleNamespace(search=SimpleNamespace(backend="opensearch"))
    with (
        patch("nuke_ingestion.indexing.get_settings", return_value=settings),
        patch("nuke_ingestion.indexing.make_opensearch_client_fresh", return_value=mock_os),
    ):
        result = _os_bulk_remote(batch)

    assert result["indexed"] == [2]
    assert result["error_page_ids"] == [""]


def test_os_bulk_remote_partial_error():
    batch = {
        "page_id": ["pid1", "pid2"],
        "chunk_text": ["chunk A", "chunk B"],
        "chunk_index": [0, 0],
        "url": ["https://example.com/a.html", "https://example.com/b.html"],
        "nuke_node_name": ["A", "B"],
        "section": ["s", "s"],
        "section_title": ["", ""],
        "embedding": [np.zeros(1024, dtype=np.float32), np.zeros(1024, dtype=np.float32)],
    }

    mock_resp = {
        "items": [
            {"index": {"_id": "abc", "result": "created"}},
            {"index": {"_id": "def", "error": {"type": "mapper_parsing_exception", "reason": "boom"}}},
        ]
    }
    mock_os = MagicMock()
    mock_os.client.bulk.return_value = mock_resp

    settings = SimpleNamespace(search=SimpleNamespace(backend="opensearch"))
    with (
        patch("nuke_ingestion.indexing.get_settings", return_value=settings),
        patch("nuke_ingestion.indexing.make_opensearch_client_fresh", return_value=mock_os),
    ):
        result = _os_bulk_remote(batch)

    assert result["indexed"] == [1]
    assert "pid2" in result["error_page_ids"][0]
    assert "pid1" not in result["error_page_ids"][0]


def test_bulk_remote_postgres_backend_uses_search_client():
    batch = {
        "page_id": ["00000000-0000-0000-0000-000000000001"],
        "chunk_text": ["chunk A"],
        "chunk_index": [0],
        "url": ["https://example.com/a.html"],
        "nuke_node_name": ["A"],
        "section": ["s"],
        "section_title": ["Overview"],
        "embedding": [np.zeros(1024, dtype=np.float32)],
    }
    settings = SimpleNamespace(search=SimpleNamespace(backend="postgres_embedding"))
    search_client = MagicMock()
    search_client.bulk_index_chunks.return_value = {"success": 1, "failed": 0, "failed_page_ids": []}

    with (
        patch("nuke_ingestion.indexing.get_settings", return_value=settings),
        patch("nuke_ingestion.indexing.make_search_client_fresh", return_value=search_client),
    ):
        result = _os_bulk_remote(batch)

    assert result["indexed"] == [1]
    assert result["error_page_ids"] == [""]
    sent = search_client.bulk_index_chunks.call_args.args[0][0]
    assert sent["chunk_data"]["section_name"] == "Overview"
    assert sent["chunk_data"]["chunk_id"]


# ---------------------------------------------------------------------------
# index_nuke_docs_ray — empty pages fast path (mocks ray module for portability)
# ---------------------------------------------------------------------------

def test_index_nuke_docs_ray_empty_pages():
    # Ray has no Windows wheels — mock the entire module so this test runs everywhere.
    mock_ray = MagicMock()
    mock_ray.init = MagicMock()
    mock_ray.shutdown = MagicMock()

    with (
        patch.dict(sys.modules, {"ray": mock_ray, "ray.data": MagicMock()}),
        patch("nuke_ingestion.indexing._load_unindexed_pages_from_db", return_value=[]),
        patch("nuke_ingestion.indexing.get_settings", return_value=SimpleNamespace(search=SimpleNamespace(backend="opensearch"))),
        patch("nuke_ingestion.indexing.make_opensearch_client_fresh") as mock_os_factory,
    ):
        mock_os = MagicMock()
        mock_os.client.indices.exists.return_value = True
        mock_os_factory.return_value = mock_os

        result = index_nuke_docs_ray()

    assert result == {"pages_indexed": 0, "chunks_indexed": 0, "indexed_page_ids": []}
    mock_ray.shutdown.assert_called_once()
