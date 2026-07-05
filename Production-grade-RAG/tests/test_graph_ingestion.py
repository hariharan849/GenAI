"""Tests for explicit knowledge graph ingestion."""

import logging
import uuid
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.graph.ingestion import extract_kg_for_indexed_pages
from api.services.graph.extraction import Triple

ROOT = Path(__file__).resolve().parents[1]
DAGS_DIR = ROOT / "orchestrators" / "airflow" / "dags"
sys.path.insert(0, str(DAGS_DIR))

from nuke_ingestion.graph import extract_all_pending_nuke_kg


def test_extract_kg_for_indexed_pages_empty_ids_skips_io():
    with (
        patch("api.services.graph.ingestion.make_neo4j_client") as neo4j_factory,
        patch("api.services.graph.ingestion.make_database") as db_factory,
    ):
        stats = extract_kg_for_indexed_pages([])

    assert stats["kg_pages_considered"] == 0
    assert stats["kg_pages_extracted"] == 0
    neo4j_factory.assert_not_called()
    db_factory.assert_not_called()


def test_extract_kg_for_indexed_pages_neo4j_disabled_returns_skipped_stats():
    with patch("api.services.graph.ingestion.make_neo4j_client", return_value=None):
        stats = extract_kg_for_indexed_pages()

    assert stats["kg_enabled"] is False
    assert stats["kg_skipped"] is True
    assert stats["kg_skip_reason"] == "neo4j_disabled"


def test_extract_kg_for_indexed_pages_marks_successful_pages(caplog):
    page_id = uuid.uuid4()
    page = SimpleNamespace(
        id=page_id,
        node_name="Blur",
        section="filter_nodes",
        raw_content="Blur outputs to Write.",
    )
    repo = MagicMock()
    repo.get_indexed_pages_pending_kg.return_value = [page]
    db = MagicMock()
    db.get_session.return_value.__enter__.return_value = MagicMock()

    def repo_factory(_session):
        return repo

    client = MagicMock()
    client.write_triples = AsyncMock(return_value=1)
    client.close = AsyncMock()

    triple = Triple(
        subject_name="Blur",
        subject_type="NukeNode",
        predicate="OUTPUTS",
        object_name="image stream",
        object_type="OutputType",
    )
    extract_mock = AsyncMock(return_value=[triple])
    with (
        caplog.at_level(logging.INFO, logger="api.services.graph.ingestion"),
        patch("api.services.graph.ingestion.make_neo4j_client", return_value=client),
        patch("api.services.graph.ingestion.make_database", return_value=db),
        patch("api.services.graph.ingestion.NukePageRepository", side_effect=repo_factory),
        patch("api.services.graph.ingestion.extract_triples", extract_mock),
    ):
        stats = extract_kg_for_indexed_pages([page_id])

    assert stats["kg_pages_considered"] == 1
    assert stats["kg_pages_extracted"] == 1
    assert stats["kg_triples_written"] == 1
    assert "Writing 1 KG triple(s) for Blur" in caplog.text
    assert "Wrote 1/1 KG triple(s) for Blur" in caplog.text
    extract_mock.assert_awaited_once_with(
        "Blur outputs to Write.",
        node_name="Blur",
        section="filter_nodes",
        raise_on_provider_error=True,
    )
    repo.mark_kg_extracted.assert_called_once_with([page_id])


def test_extract_kg_for_indexed_pages_logs_no_triples(caplog):
    page_id = uuid.uuid4()
    page = SimpleNamespace(
        id=page_id,
        node_name="Grade",
        section="color_nodes",
        raw_content="Grade adjusts colors.",
    )
    repo = MagicMock()
    repo.get_indexed_pages_pending_kg.return_value = [page]
    db = MagicMock()
    db.get_session.return_value.__enter__.return_value = MagicMock()

    def repo_factory(_session):
        return repo

    client = MagicMock()
    client.write_triples = AsyncMock()
    client.close = AsyncMock()

    with (
        caplog.at_level(logging.INFO, logger="api.services.graph.ingestion"),
        patch("api.services.graph.ingestion.make_neo4j_client", return_value=client),
        patch("api.services.graph.ingestion.make_database", return_value=db),
        patch("api.services.graph.ingestion.NukePageRepository", side_effect=repo_factory),
        patch("api.services.graph.ingestion.extract_triples", AsyncMock(return_value=[])),
    ):
        stats = extract_kg_for_indexed_pages([page_id])

    assert stats["kg_pages_considered"] == 1
    assert stats["kg_pages_extracted"] == 1
    assert stats["kg_triples_written"] == 0
    assert "No KG triples extracted for Grade" in caplog.text
    client.write_triples.assert_not_called()


def test_extract_kg_for_indexed_pages_keeps_failed_pages_pending(caplog):
    page_id = uuid.uuid4()
    page = SimpleNamespace(
        id=page_id,
        node_name="Kronos",
        section="time_nodes",
        raw_content="Kronos has time controls.",
    )
    repo = MagicMock()
    repo.get_indexed_pages_pending_kg.return_value = [page]
    db = MagicMock()
    db.get_session.return_value.__enter__.return_value = MagicMock()

    def repo_factory(_session):
        return repo

    client = MagicMock()
    client.write_triples = AsyncMock()
    client.close = AsyncMock()

    with (
        caplog.at_level(logging.WARNING, logger="api.services.graph.ingestion"),
        patch("api.services.graph.ingestion.make_neo4j_client", return_value=client),
        patch("api.services.graph.ingestion.make_database", return_value=db),
        patch("api.services.graph.ingestion.NukePageRepository", side_effect=repo_factory),
        patch("api.services.graph.ingestion.extract_triples", AsyncMock(side_effect=RuntimeError("provider down"))),
    ):
        stats = extract_kg_for_indexed_pages([page_id])

    assert stats["kg_pages_considered"] == 1
    assert stats["kg_pages_extracted"] == 0
    assert stats["kg_pages_failed"] == 1
    assert stats["kg_triples_written"] == 0
    assert "KG extraction skipped for Kronos: provider down" in caplog.text
    client.write_triples.assert_not_called()
    repo.mark_kg_extracted.assert_not_called()


def test_extract_all_pending_nuke_kg_omits_page_ids_and_pushes_stats():
    ti = MagicMock()
    stats = {
        "kg_enabled": True,
        "kg_skipped": False,
        "kg_pages_considered": 3,
        "kg_pages_extracted": 3,
        "kg_pages_failed": 0,
        "kg_triples_written": 9,
    }

    with patch(
        "nuke_ingestion.graph.extract_kg_for_indexed_pages",
        return_value=stats,
    ) as extract_kg:
        result = extract_all_pending_nuke_kg(ti=ti)

    assert result == stats
    extract_kg.assert_called_once_with()
    ti.xcom_push.assert_called_once_with(key="kg_stats", value=stats)
