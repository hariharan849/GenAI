"""Tests for section-aware semantic chunking.

Covers: TextChunker.chunk_sections(), _parse_node_page() section extraction,
and NukePageRepository.upsert_pages() sections persistence.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup

from api.models.nuke_page import NukePage
from api.repositories.nuke_page import NukePageRepository
from api.services.indexing.text_chunker import TextChunker


# ── Fixtures ──────────────────────────────────────────────────────────────────

_NUKE_URL = "https://learn.foundry.com/nuke/17.0/content/reference_guide/filter_nodes/filter_nodes/blur.html"

_NUKE_HTML_WITH_H2 = """
<html><body>
<h1>Blur</h1>
<div class="mc-main-content">
  <p>The Blur node applies a Gaussian blur to the input image across all
     channels. It is one of the most commonly used filter nodes in Nuke and
     accepts any 2D image as input. You can control the blur radius and which
     channels are affected independently for x and y axes to create motion blur
     or soft glow effects. This node supports float and integer bit depths.</p>
  <h2>Inputs</h2>
  <p>Connect the source image here. This input accepts any 2D image stream
     including deep images. Multiple inputs can be connected for layered blurs.</p>
  <h2>Knobs</h2>
  <p>Size: Controls the blur radius in pixels. Channels: Selects which image
     channels are affected by the blur operation. Filter: Chooses the convolution
     kernel shape used for blurring.</p>
</div>
</body></html>
"""

_NUKE_HTML_NO_H2 = """
<html><body>
<h1>Blur</h1>
<div class="mc-main-content">
  <p>The Blur node applies a Gaussian blur to the input image across all
     channels. It is one of the most commonly used filter nodes in Nuke and
     accepts any 2D image as input. You can control the blur radius and which
     channels are affected independently for x and y axes to create directional
     motion blur or soft diffused glow effects on any layer. This node supports
     float and integer bit depths and works across all color spaces without
     needing a colorspace conversion node upstream. The blur kernel is fully
     configurable via the Size knob which accepts a single value for uniform
     blur or separate x and y values for asymmetric results. The Channels knob
     restricts processing to specific image planes such as rgba or depth so
     you can blur only the alpha channel while leaving rgb untouched. Multiple
     Blur nodes can be stacked in series to simulate lens defocus effects that
     match real optical aberration patterns observed in anamorphic lenses used
     in feature film production pipelines.</p>
</div>
</body></html>
"""


# ── TextChunker.chunk_sections() ─────────────────────────────────────────────

class TestChunkSections:
    def _chunker(self):
        return TextChunker(chunk_size=50, overlap_size=5, min_chunk_size=3)

    def test_populates_section_title_on_all_chunks(self):
        chunker = self._chunker()
        sections = [{"title": "Knobs", "text": "knob one size radius channels filter " * 5}]
        chunks = chunker.chunk_sections(sections, doc_id="url", page_id="url")
        assert chunks
        assert all(c.metadata.section_title == "Knobs" for c in chunks)

    def test_global_chunk_index_is_monotonically_increasing_across_sections(self):
        chunker = self._chunker()
        sections = [
            {"title": "Inputs", "text": "input description source image stream " * 5},
            {"title": "Knobs", "text": "knob parameter size radius channels " * 5},
        ]
        chunks = chunker.chunk_sections(sections, doc_id="url", page_id="url")
        indices = [c.metadata.chunk_index for c in chunks]
        assert indices == list(range(len(chunks))), "chunk_index must be globally sequential"
        inputs_chunks = [c for c in chunks if c.metadata.section_title == "Inputs"]
        knobs_chunks = [c for c in chunks if c.metadata.section_title == "Knobs"]
        assert inputs_chunks, "expected chunks from Inputs section"
        assert knobs_chunks, "expected chunks from Knobs section"
        assert max(c.metadata.chunk_index for c in inputs_chunks) < min(
            c.metadata.chunk_index for c in knobs_chunks
        ), "Inputs chunks must come before Knobs chunks"


# ── scraping._parse_node_page() section extraction ───────────────────────────

class TestParseNodePageSections:
    def _parse(self, html: str):
        from nuke_ingestion.scraping import _parse_node_page
        soup = BeautifulSoup(html, "html.parser")
        return _parse_node_page(soup, _NUKE_URL)

    def test_extracts_h2_sections_with_correct_titles_and_text(self):
        result = self._parse(_NUKE_HTML_WITH_H2)
        assert result is not None
        sections = result["sections"]
        titles = [s["title"] for s in sections]
        assert "Inputs" in titles
        assert "Knobs" in titles
        knobs = next(s for s in sections if s["title"] == "Knobs")
        assert "Size" in knobs["text"]

    def test_no_h2_returns_empty_sections_and_preserves_raw_content(self):
        result = self._parse(_NUKE_HTML_NO_H2)
        assert result is not None
        assert result["sections"] == []
        assert result["content"]


# ── NukePageRepository.upsert_pages() sections persistence ───────────────────

class TestUpsertPagesStoresSections:
    _SECTIONS = [{"title": "Knobs", "text": "Size controls blur radius."}]
    _PAGE = {
        "url": "https://example.com/blur",
        "node_name": "Blur",
        "section": "filter_nodes",
        "content": "Some content about the blur node with enough words",
        "sections": _SECTIONS,
    }

    def test_stores_sections_on_new_page_insert(self):
        session = MagicMock()
        repo = NukePageRepository(session)
        repo.get_by_url = MagicMock(return_value=None)
        repo.get_all_pages = MagicMock(return_value=[])

        repo.upsert_pages([self._PAGE], nuke_version="17.0")

        session.add.assert_called_once()
        added: NukePage = session.add.call_args[0][0]
        assert added.sections == self._SECTIONS

    def test_updates_sections_on_existing_page(self):
        session = MagicMock()
        repo = NukePageRepository(session)

        existing = NukePage()
        existing.id = uuid.uuid4()
        existing.url = self._PAGE["url"]
        existing.node_name = "Blur"
        existing.section = "filter_nodes"
        existing.raw_content = "old content"
        existing.nuke_version = "17.0"
        existing.scraped_at = datetime.now(timezone.utc)
        existing.nuke_pages_indexed = True
        existing.sections = None

        repo.get_by_url = MagicMock(return_value=existing)
        repo.get_all_pages = MagicMock(return_value=[])

        repo.upsert_pages([self._PAGE], nuke_version="17.0")

        assert existing.sections == self._SECTIONS
