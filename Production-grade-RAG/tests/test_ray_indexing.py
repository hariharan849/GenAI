"""Unit tests for Ray Data indexing pipeline functions.

Tests cover the three pure stateless operators and the empty-pages fast-path.
Each test mocks its IO boundaries (DB, Jina API, OpenSearch) so no running
services are required.
"""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

import numpy as np
import pytest

# Make nuke_ingestion importable (mirrors conftest.py)
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrators" / "airflow" / "dags"))

from nuke_ingestion.indexing import (
    _RayIndexingOptions,
    _chunk_page_remote,
    _configure_ray_memory_monitor_env,
    _embed_batch_remote,
    _os_bulk_remote,
    _ray_indexing_options,
    _run_ray_indexing_pipeline,
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
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert {c["section_title"] for c in chunks} == {"Overview", "Parameters"}
    overview_indexes = [c["chunk_index"] for c in chunks if c["section_title"] == "Overview"]
    parameter_indexes = [c["chunk_index"] for c in chunks if c["section_title"] == "Parameters"]
    assert max(overview_indexes) < min(parameter_indexes)
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


def test_chunk_page_remote_parent_child_adds_parent_doc_id():
    settings = SimpleNamespace(
        chunking=SimpleNamespace(
            splitter_type="parent_child",
            chunk_size=40,
            overlap_size=5,
            parent_chunk_size=80,
            parent_overlap_size=10,
            parent_doc_id_key="parent_doc_id",
        )
    )

    with patch("nuke_ingestion.indexing.get_settings", return_value=settings):
        chunks = _chunk_page_remote(PAGE_WITH_RAW_CONTENT)

    assert len(chunks) > 0
    assert all(c["parent_doc_id"] for c in chunks)
    assert all(c["parent_content"] for c in chunks)
    assert all(c["parent_metadata"]["parent_doc_id"] == c["parent_doc_id"] for c in chunks)
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


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
    mock_client.close = AsyncMock()

    # asyncio.run calls embed_passages as a coroutine — wrap in coroutine mock
    import asyncio

    async def _async_embed(texts, **kwargs):
        return fake_embeddings

    mock_client.embed_passages = _async_embed

    with patch("nuke_ingestion.indexing.make_embeddings_client", return_value=mock_client):
        result = _embed_batch_remote(batch)

    assert "embedding" in result
    assert isinstance(result["embedding"], np.ndarray)
    assert result["embedding"].dtype == np.float32
    assert result["embedding"].shape == (2, 1024)


def test_ray_indexing_options_reads_env(monkeypatch):
    monkeypatch.setenv("RAG_RAY_OBJECT_STORE_MEMORY_BYTES", "123456789")
    monkeypatch.setenv("RAG_RAY_NUM_CPUS", "6")
    monkeypatch.setenv("RAG_RAY_EMBED_BATCH_SIZE", "16")
    monkeypatch.setenv("RAG_RAY_EMBED_CONCURRENCY", "2")
    monkeypatch.setenv("RAG_RAY_EMBED_NUM_CPUS", "4")
    monkeypatch.setenv("RAG_RAY_BULK_BATCH_SIZE", "64")
    monkeypatch.setenv("RAG_RAY_BULK_CONCURRENCY", "1")
    monkeypatch.setenv("RAG_RAY_BULK_NUM_CPUS", "2")

    options = _ray_indexing_options()

    assert options.object_store_memory == 123456789
    assert options.num_cpus == 6
    assert options.embed_batch_size == 16
    assert options.embed_concurrency == 2
    assert options.embed_num_cpus == 4
    assert options.bulk_batch_size == 64
    assert options.bulk_concurrency == 1
    assert options.bulk_num_cpus == 2


def test_configure_ray_memory_monitor_env_uses_prefixed_overrides(monkeypatch):
    monkeypatch.delenv("RAY_memory_usage_threshold", raising=False)
    monkeypatch.delenv("RAY_memory_monitor_refresh_ms", raising=False)
    monkeypatch.setenv("RAG_RAY_MEMORY_USAGE_THRESHOLD", "0.98")
    monkeypatch.setenv("RAG_RAY_MEMORY_MONITOR_REFRESH_MS", "0")

    _configure_ray_memory_monitor_env()

    assert os.environ["RAY_memory_usage_threshold"] == "0.98"
    assert os.environ["RAY_memory_monitor_refresh_ms"] == "0"


def test_run_ray_indexing_pipeline_applies_memory_safe_map_batch_options():
    class FakeDataset:
        def __init__(self):
            self.map_batches_calls = []

        def flat_map(self, fn):
            self.flat_map_fn = fn
            return self

        def map_batches(self, fn, **kwargs):
            self.map_batches_calls.append((fn, kwargs))
            return self

        def take_all(self):
            return [{"indexed": 1, "error_page_ids": ""}]

    dataset = FakeDataset()
    fake_ray = SimpleNamespace(data=SimpleNamespace(from_items=MagicMock(return_value=dataset)))
    options = _RayIndexingOptions(
        object_store_memory=500_000_000,
        num_cpus=2,
        embed_batch_size=16,
        embed_concurrency=1,
        embed_num_cpus=3,
        bulk_batch_size=128,
        bulk_concurrency=1,
        bulk_num_cpus=2,
    )

    rows = _run_ray_indexing_pipeline(fake_ray, [{"id": "page-1"}], options)

    assert rows == [{"indexed": 1, "error_page_ids": ""}]
    assert dataset.map_batches_calls[0][1] == {
        "batch_size": 16,
        "concurrency": 1,
        "num_cpus": 3,
    }
    assert dataset.map_batches_calls[1][1] == {
        "batch_size": 128,
        "concurrency": 1,
        "num_cpus": 2,
    }


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


def test_bulk_remote_postgres_parent_child_sends_parent_doc_id():
    batch = {
        "page_id": ["00000000-0000-0000-0000-000000000001"],
        "parent_doc_id": ["parent-1"],
        "parent_content": ["parent text"],
        "parent_metadata": [{"parent_doc_id": "parent-1", "page_id": "00000000-0000-0000-0000-000000000001", "url": "https://example.com/a.html"}],
        "chunk_id": ["child-1"],
        "chunk_text": ["child text"],
        "chunk_index": [0],
        "url": ["https://example.com/a.html"],
        "nuke_node_name": ["A"],
        "section": ["s"],
        "section_title": ["Overview"],
        "embedding": [np.zeros(1024, dtype=np.float32)],
    }
    settings = SimpleNamespace(search=SimpleNamespace(backend="postgres_embedding"), postgres_database_url="postgresql://x")
    search_client = MagicMock()
    search_client.bulk_index_chunks.return_value = {"success": 1, "failed": 0, "failed_page_ids": []}

    with (
        patch("nuke_ingestion.indexing.get_settings", return_value=settings),
        patch("nuke_ingestion.indexing.PostgresParentDocumentStore") as store_cls,
        patch("nuke_ingestion.indexing.make_search_client_fresh", return_value=search_client),
    ):
        result = _os_bulk_remote(batch)

    assert result["indexed"] == [1]
    store_cls.return_value.mset.assert_called_once()
    sent = search_client.bulk_index_chunks.call_args.args[0][0]
    assert sent["chunk_data"]["chunk_id"] == "child-1"
    assert sent["chunk_data"]["parent_doc_id"] == "parent-1"


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
    assert mock_ray.init.call_args.kwargs["num_cpus"] == 2
    mock_ray.shutdown.assert_called_once()
