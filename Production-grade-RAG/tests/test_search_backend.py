from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from api.config import ChunkingSettings, SearchSettings, Settings
from api.search.factory import make_search_client, make_search_client_fresh
from api.search.postgres_embedding import PostgresEmbeddingSearchClient, deterministic_chunk_id


def test_search_factory_selects_postgres_embedding():
    settings = Settings(search=SearchSettings(backend="postgres_embedding"))

    with patch("api.search.factory.PostgresEmbeddingSearchClient") as client_cls:
        client = make_search_client_fresh(settings)

    assert client == client_cls.return_value
    client_cls.assert_called_once_with(settings)


def test_chunking_settings_default_to_recursive_splitter():
    settings = ChunkingSettings()

    assert settings.splitter_type == "recursive"
    assert settings.parent_chunk_size == 1800
    assert settings.parent_overlap_size == 200
    assert settings.parent_doc_id_key == "parent_doc_id"


def test_chunking_settings_accept_parent_child_splitter():
    settings = ChunkingSettings(splitter_type="parent_child")

    assert settings.splitter_type == "parent_child"


def test_search_factory_selects_opensearch():
    settings = Settings(search=SearchSettings(backend="opensearch"))

    with patch("api.search.factory.make_opensearch_client_fresh") as factory:
        client = make_search_client_fresh(settings, host="http://search:9200")

    assert client == factory.return_value
    factory.assert_called_once_with(settings, host="http://search:9200")


def test_search_factory_fresh_option_selects_fresh_client():
    settings = Settings(search=SearchSettings(backend="opensearch"))

    with patch("api.search.factory.make_opensearch_client_fresh") as factory:
        client = make_search_client(settings, fresh=True)

    assert client == factory.return_value
    factory.assert_called_once_with(settings)


def test_search_import_shims_expose_new_interfaces():
    from api.search import SearchClient as NewSearchClient
    from api.services.search import SearchClient as OldSearchClient
    from api.services.search.postgres_embedding import deterministic_chunk_id as old_chunk_id

    assert OldSearchClient is NewSearchClient
    assert old_chunk_id("https://example.com/a", 1) == deterministic_chunk_id("https://example.com/a", 1)


def test_postgres_search_result_shape():
    client = PostgresEmbeddingSearchClient.__new__(PostgresEmbeddingSearchClient)
    row = {
        "score": 0.42,
        "chunk_id": "chunk-1",
        "page_id": "00000000-0000-0000-0000-000000000001",
        "parent_doc_id": "parent-1",
        "url": "https://example.com/blur.html",
        "nuke_node_name": "Blur",
        "section": "filter_nodes",
        "section_name": "Overview",
        "chunk_index": 0,
        "chunk_text": "Blur applies a gaussian blur.",
        "headline": "<b>Blur</b> applies a gaussian blur.",
    }

    hit = client._row_to_hit(row)

    assert hit == {
        "score": 0.42,
        "chunk_id": "chunk-1",
        "page_id": "00000000-0000-0000-0000-000000000001",
        "parent_doc_id": "parent-1",
        "url": "https://example.com/blur.html",
        "nuke_node_name": "Blur",
        "section": "filter_nodes",
        "section_name": "Overview",
        "chunk_index": 0,
        "chunk_text": "Blur applies a gaussian blur.",
        "highlights": {"chunk_text": ["<b>Blur</b> applies a gaussian blur."]},
    }


class _SessionContext:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


def _bulk_client(session):
    client = PostgresEmbeddingSearchClient.__new__(PostgresEmbeddingSearchClient)
    client.session_factory = lambda: _SessionContext(session)
    return client


def _chunk(page_id="00000000-0000-0000-0000-000000000001", text="chunk"):
    return {
        "chunk_data": {
            "page_id": page_id,
            "url": "https://example.com/blur.html",
            "nuke_node_name": "Blur",
            "section": "filter_nodes",
            "section_title": "Overview",
            "chunk_index": 0,
            "chunk_text": text,
        },
        "embedding": [0.1] * 1024,
    }


def test_postgres_bulk_upsert_empty_batch():
    session = MagicMock()
    stats = _bulk_client(session).bulk_index_chunks([])

    assert stats == {"success": 0, "failed": 0}
    session.execute.assert_not_called()


def test_postgres_bulk_upsert_success_and_duplicate_update():
    session = MagicMock()
    client = _bulk_client(session)

    stats = client.bulk_index_chunks([_chunk(text="old"), _chunk(text="new")])

    assert stats == {"success": 2, "failed": 0, "failed_page_ids": []}
    assert session.execute.call_count == 2
    assert session.commit.call_count == 2
    session.rollback.assert_not_called()


def test_postgres_bulk_upsert_partial_failure_reports_page_id():
    session = MagicMock()
    session.execute.side_effect = [None, RuntimeError("boom")]
    client = _bulk_client(session)

    stats = client.bulk_index_chunks(
        [
            _chunk(page_id="00000000-0000-0000-0000-000000000001"),
            _chunk(page_id="00000000-0000-0000-0000-000000000002"),
        ]
    )

    assert stats == {
        "success": 1,
        "failed": 1,
        "failed_page_ids": ["00000000-0000-0000-0000-000000000002"],
    }
    assert session.commit.call_count == 1
    assert session.rollback.call_count == 1


def test_deterministic_chunk_id_matches_existing_ingestion_semantics():
    assert deterministic_chunk_id("https://example.com/a", 3) == deterministic_chunk_id("https://example.com/a", 3)
    assert deterministic_chunk_id("https://example.com/a", 3) != deterministic_chunk_id("https://example.com/a", 4)


def test_postgres_normalize_chunk_preserves_parent_doc_id():
    client = PostgresEmbeddingSearchClient.__new__(PostgresEmbeddingSearchClient)
    payload = client._normalize_chunk(_chunk() | {"chunk_data": _chunk()["chunk_data"] | {"parent_doc_id": "parent-1"}})

    assert payload["parent_doc_id"] == "parent-1"


def test_postgres_normalize_chunk_allows_missing_parent_doc_id():
    client = PostgresEmbeddingSearchClient.__new__(PostgresEmbeddingSearchClient)
    payload = client._normalize_chunk(_chunk())

    assert payload["parent_doc_id"] is None
