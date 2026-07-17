from __future__ import annotations

import pytest
from source_intelligence.service import SourceIntelligenceService


@pytest.mark.asyncio
async def test_search_rejects_invalid_freshness_window() -> None:
    service = SourceIntelligenceService("test-key")

    with pytest.raises(ValueError, match="freshness_window"):
        await service.search_web("latest AI news", "yesterday")


@pytest.mark.asyncio
async def test_fetch_rejects_non_public_or_non_https_urls() -> None:
    service = SourceIntelligenceService("test-key")

    with pytest.raises(ValueError, match="public HTTPS"):
        await service.fetch_webpage("http://example.com")
    with pytest.raises(ValueError, match="private or local"):
        await service.fetch_webpage("https://127.0.0.1")
