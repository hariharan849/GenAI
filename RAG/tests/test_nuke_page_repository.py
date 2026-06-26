"""Tests for NukePageRepository — upsert, get_unindexed, mark_indexed."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from src.models.nuke_page import NukePage
from src.repositories.nuke_page import NukePageRepository


def _make_page(url: str = "https://example.com/node", content: str = "some text") -> dict:
    return {
        "url": url,
        "node_name": "Blur",
        "section": "Reference",
        "content": content,
    }


def _make_nuke_page(url: str = "https://example.com/node") -> NukePage:
    page = NukePage()
    page.id = uuid.uuid4()
    page.url = url
    page.node_name = "Blur"
    page.section = "Reference"
    page.raw_content = "existing text"
    page.nuke_version = "17.0"
    page.scraped_at = datetime.now(timezone.utc)
    page.nuke_pages_indexed = True
    return page


class TestUpsertPages:
    def test_inserts_new_page(self):
        session = MagicMock()
        repo = NukePageRepository(session)
        repo.get_by_url = MagicMock(return_value=None)

        count = repo.upsert_pages([_make_page()], nuke_version="17.0")

        session.add.assert_called_once()
        added: NukePage = session.add.call_args[0][0]
        assert added.url == "https://example.com/node"
        assert added.raw_content == "some text"
        assert added.nuke_version == "17.0"
        assert not added.nuke_pages_indexed  # None or False before DB insert
        session.commit.assert_called_once()
        assert count == 1

    def test_updates_existing_page_and_resets_indexed_flag(self):
        session = MagicMock()
        repo = NukePageRepository(session)
        existing = _make_nuke_page()
        existing.nuke_pages_indexed = True
        repo.get_by_url = MagicMock(return_value=existing)

        count = repo.upsert_pages([_make_page(content="new text")], nuke_version="17.1")

        assert existing.raw_content == "new text"
        assert existing.nuke_version == "17.1"
        assert existing.nuke_pages_indexed is False
        session.add.assert_not_called()
        session.commit.assert_called_once()
        assert count == 1

    def test_skips_page_with_empty_content(self):
        session = MagicMock()
        repo = NukePageRepository(session)
        repo.get_by_url = MagicMock(return_value=None)

        count = repo.upsert_pages([_make_page(content="")], nuke_version="17.0")

        session.add.assert_not_called()
        assert count == 0

    def test_skips_page_with_missing_content_key(self):
        session = MagicMock()
        repo = NukePageRepository(session)
        repo.get_by_url = MagicMock(return_value=None)
        page = {"url": "https://example.com/node", "node_name": "Blur", "section": "Ref"}

        count = repo.upsert_pages([page], nuke_version="17.0")

        session.add.assert_not_called()
        assert count == 0

    def test_upserts_multiple_pages_in_one_commit(self):
        session = MagicMock()
        repo = NukePageRepository(session)
        repo.get_by_url = MagicMock(return_value=None)
        pages = [_make_page(url=f"https://example.com/{i}") for i in range(3)]

        count = repo.upsert_pages(pages, nuke_version="17.0")

        assert session.add.call_count == 3
        session.commit.assert_called_once()
        assert count == 3


class TestGetUnindexedPages:
    def test_returns_only_unindexed_rows(self):
        session = MagicMock()
        unindexed = [_make_nuke_page()]
        unindexed[0].nuke_pages_indexed = False
        session.scalars.return_value = iter(unindexed)

        repo = NukePageRepository(session)
        result = repo.get_unindexed_pages()

        assert result == unindexed
        session.scalars.assert_called_once()

    def test_returns_empty_when_all_indexed(self):
        session = MagicMock()
        session.scalars.return_value = iter([])

        repo = NukePageRepository(session)
        result = repo.get_unindexed_pages()

        assert result == []


class TestMarkIndexed:
    def test_marks_correct_rows_and_commits(self):
        session = MagicMock()
        repo = NukePageRepository(session)
        ids = [uuid.uuid4(), uuid.uuid4()]

        repo.mark_indexed(ids)

        session.execute.assert_called_once()
        session.commit.assert_called_once()

    def test_handles_empty_id_list(self):
        session = MagicMock()
        repo = NukePageRepository(session)

        repo.mark_indexed([])

        session.execute.assert_called_once()
        session.commit.assert_called_once()
