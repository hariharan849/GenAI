"""Tests for save_nuke_pages Airflow callable."""

import json
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _write_temp(pages: list) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(pages, f)
        return f.name


def _make_pages(n: int = 3) -> list[dict]:
    return [
        {
            "url": f"https://example.com/node/{i}",
            "node_name": f"Node{i}",
            "section": "Reference",
            "content": f"Text for node {i}",
        }
        for i in range(n)
    ]


class TestSaveNukePages:
    def _run(self, pages, scraped_file=None):
        """Run save_nuke_pages with mocked DB and nuke_docs_ingestion module."""
        import importlib

        if scraped_file is None:
            scraped_file = _write_temp(pages)

        ti = MagicMock()
        ti.xcom_pull.return_value = scraped_file

        # Stub the nuke_docs_ingestion module so the deferred import works
        nuke_mod = SimpleNamespace(NUKE_VERSION="17.0")
        mock_repo = MagicMock()
        mock_repo.upsert_pages.return_value = len(pages)

        with patch.dict("sys.modules", {"nuke_docs_ingestion": nuke_mod}):
            # Reload to pick up the stub
            import nuke_ingestion.save as save_mod
            importlib.reload(save_mod)

            with (
                patch.object(save_mod, "make_database") as mock_make_db,
                patch.object(save_mod, "NukePageRepository", return_value=mock_repo),
            ):
                mock_db = MagicMock()
                mock_make_db.return_value = mock_db
                mock_session = MagicMock()
                mock_session.__enter__ = MagicMock(return_value=mock_session)
                mock_session.__exit__ = MagicMock(return_value=False)
                mock_db.get_session.return_value = mock_session

                result = save_mod.save_nuke_pages(ti=ti)

        return result, mock_repo, ti

    def test_raises_when_no_scraped_file(self):
        import importlib

        nuke_mod = SimpleNamespace(NUKE_VERSION="17.0")
        with patch.dict("sys.modules", {"nuke_docs_ingestion": nuke_mod}):
            import nuke_ingestion.save as save_mod
            importlib.reload(save_mod)

            ti = MagicMock()
            ti.xcom_pull.return_value = None

            with pytest.raises(ValueError, match="No scraped_file in XCom"):
                save_mod.save_nuke_pages(ti=ti)

    def test_happy_path_upserts_and_pushes_xcom(self):
        pages = _make_pages(3)
        result, mock_repo, ti = self._run(pages)

        mock_repo.upsert_pages.assert_called_once()
        call_args = mock_repo.upsert_pages.call_args
        called_pages, called_version = call_args[0][0], call_args[1].get(
            "nuke_version", call_args[0][1] if len(call_args[0]) > 1 else None
        )
        assert called_version == "17.0"
        assert len(called_pages) == 3
        ti.xcom_push.assert_called_once_with(key="pages_saved", value=3)
        assert result["pages_saved"] == 3

    def test_empty_pages_list_skips_db(self):
        import importlib

        nuke_mod = SimpleNamespace(NUKE_VERSION="17.0")
        scraped_file = _write_temp([])
        ti = MagicMock()
        ti.xcom_pull.return_value = scraped_file

        with patch.dict("sys.modules", {"nuke_docs_ingestion": nuke_mod}):
            import nuke_ingestion.save as save_mod
            importlib.reload(save_mod)

            with patch.object(save_mod, "make_database") as mock_make_db:
                result = save_mod.save_nuke_pages(ti=ti)

            mock_make_db.assert_not_called()

        assert result["pages_saved"] == 0
        ti.xcom_push.assert_called_once_with(key="pages_saved", value=0)
