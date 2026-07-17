"""Live-source operations exposed through the Source Intelligence MCP server."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

MAX_EVIDENCE_CHARS = 20_000
CACHE_TTL_SECONDS = 60 * 60
MAX_SEARCH_RESULTS = 10


class LiveSourceError(RuntimeError):
    """Raised when the upstream live-source provider is unavailable."""


@dataclass(frozen=True)
class CacheEntry:
    value: dict[str, Any]
    expires_at: float


class SourceIntelligenceService:
    """Search Tavily and retrieve safe public webpages with a small TTL cache."""

    def __init__(self, tavily_api_key: str | None = None) -> None:
        self._tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY", "").strip()
        self._cache: dict[str, CacheEntry] = {}

    async def search_web(
        self,
        query: str,
        freshness_window: str | None = None,
        allowed_domains: list[str] | None = None,
        max_results: int = 5,
    ) -> dict[str, Any]:
        """Return structured current sources discovered by Tavily."""
        if not query.strip():
            raise ValueError("query must not be empty")
        if freshness_window not in (None, "24h", "7d", "30d"):
            raise ValueError("freshness_window must be one of: 24h, 7d, 30d")
        if not 1 <= max_results <= MAX_SEARCH_RESULTS:
            raise ValueError(f"max_results must be between 1 and {MAX_SEARCH_RESULTS}")
        domains = sorted(
            {
                domain.lower().strip()
                for domain in allowed_domains or []
                if domain.strip()
            }
        )
        key = f"search:{query.strip()}:{freshness_window}:{','.join(domains)}:{max_results}"
        cached = self._get_cached(key)
        if cached:
            return cached
        if not self._tavily_api_key:
            raise LiveSourceError("TAVILY_API_KEY is not configured")

        payload: dict[str, Any] = {
            "api_key": self._tavily_api_key,
            "query": query.strip(),
            "max_results": max_results,
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": False,
        }
        if domains:
            payload["include_domains"] = domains
        if freshness_window:
            payload["days"] = {"24h": 1, "7d": 7, "30d": 30}[freshness_window]
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    "https://api.tavily.com/search", json=payload
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise LiveSourceError("Tavily search is unavailable") from error
        body = response.json()
        records = [self._search_record(item) for item in body.get("results", [])]
        result = {"sources": records, "retrieved_at": _timestamp(), "cached": False}
        self._put_cached(key, result)
        return result

    async def fetch_webpage(self, url: str) -> dict[str, Any]:
        """Extract up to 20,000 characters from a safe public HTTPS URL."""
        await _validate_public_https_url(url)
        key = f"fetch:{url.strip()}"
        cached = self._get_cached(key)
        if cached:
            return cached
        try:
            async with httpx.AsyncClient(
                timeout=20.0, follow_redirects=True, max_redirects=5
            ) as client:
                response = await client.get(
                    url, headers={"User-Agent": "PRAI-SourceIntelligence/1.0"}
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise LiveSourceError("Webpage retrieval is unavailable") from error
        await _validate_public_https_url(str(response.url))
        soup = BeautifulSoup(response.text, "html.parser")
        for element in soup(["script", "style", "noscript", "svg"]):
            element.decompose()
        text = " ".join(soup.stripped_strings)
        truncated = len(text) > MAX_EVIDENCE_CHARS
        result = {
            "source": {
                "url": str(response.url),
                "title": soup.title.get_text(" ", strip=True) if soup.title else None,
                "publisher": urlparse(str(response.url)).netloc,
                "published_at": None,
                "retrieved_at": _timestamp(),
                "text": text[:MAX_EVIDENCE_CHARS],
                "truncated": truncated,
            },
            "cached": False,
        }
        self._put_cached(key, result)
        return result

    async def verify_citations(self, urls: list[str]) -> dict[str, Any]:
        """Retrieve each distinct citation and return safe, judge-ready evidence.

        A bad citation is represented in the result rather than aborting the
        entire batch.  This lets the judge provide the researcher a specific
        repair action without exposing the retrieval tool itself.
        """
        if not isinstance(urls, list):
            raise ValueError("urls must be a list")

        submitted_urls: list[str] = []
        seen: set[str] = set()
        for url in urls:
            # Retain malformed values once so callers get an actionable result.
            value = url.strip() if isinstance(url, str) else str(url)
            if value not in seen:
                seen.add(value)
                submitted_urls.append(value)

        citations = await asyncio.gather(
            *(self._verify_citation(url) for url in submitted_urls)
        )
        return {"citations": citations, "retrieved_at": _timestamp()}

    async def _verify_citation(self, submitted_url: str) -> dict[str, Any]:
        record: dict[str, Any] = {
            "submitted_url": submitted_url,
            "canonical_url": None,
            "title": None,
            "publisher": None,
            "status": "unverified",
            "evidence": None,
            "reason": None,
        }
        try:
            source = (await self.fetch_webpage(submitted_url))["source"]
        except ValueError as error:
            record["reason"] = str(error)
        except LiveSourceError:
            record["reason"] = "citation could not be retrieved"
        else:
            record.update(
                {
                    "canonical_url": source["url"],
                    "title": source["title"],
                    "publisher": source["publisher"],
                    "status": "verified",
                    "evidence": source["text"],
                }
            )
        return record

    def _get_cached(self, key: str) -> dict[str, Any] | None:
        entry = self._cache.get(key)
        if not entry or entry.expires_at <= time.monotonic():
            self._cache.pop(key, None)
            return None
        return {**entry.value, "cached": True}

    def _put_cached(self, key: str, value: dict[str, Any]) -> None:
        self._cache[key] = CacheEntry(
            value=value, expires_at=time.monotonic() + CACHE_TTL_SECONDS
        )

    @staticmethod
    def _search_record(item: dict[str, Any]) -> dict[str, Any]:
        url = str(item.get("url", ""))
        return {
            "url": url,
            "title": item.get("title"),
            "publisher": urlparse(url).netloc or None,
            "published_at": item.get("published_date"),
            "retrieved_at": _timestamp(),
            "text": item.get("content", ""),
            "truncated": False,
        }


async def _validate_public_https_url(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("url must be a public HTTPS URL without credentials")
    try:
        addresses = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: socket.getaddrinfo(parsed.hostname, None, type=socket.SOCK_STREAM),
        )
    except socket.gaierror as error:
        raise ValueError("url hostname could not be resolved") from error
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("url must not resolve to a private or local address")


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
