"""MCP client for the shared Source Intelligence service."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any


class SourceIntelligenceClient:
    """Call the shared MCP service over local stdio or deployed HTTP."""

    def __init__(self) -> None:
        self._transport = os.getenv("SOURCE_INTELLIGENCE_TRANSPORT", "disabled")

    @property
    def enabled(self) -> bool:
        return self._transport in {"stdio", "http"}

    async def search_web(
        self, query: str, freshness_window: str | None = None
    ) -> dict[str, Any]:
        return await self._call_tool(
            "search_web", {"query": query, "freshness_window": freshness_window}
        )

    async def fetch_webpage(self, url: str) -> dict[str, Any]:
        return await self._call_tool("fetch_webpage", {"url": url})

    async def verify_citations(self, urls: list[str]) -> dict[str, Any]:
        return await self._call_tool("verify_citations", {"urls": urls})

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from mcp.client.streamable_http import streamablehttp_client

        if not self.enabled:
            raise RuntimeError("Source Intelligence MCP is not configured")
        if self._transport == "stdio":
            args = json.loads(os.environ["SOURCE_INTELLIGENCE_STDIO_ARGS"])
            params = StdioServerParameters(
                command=os.getenv("SOURCE_INTELLIGENCE_STDIO_COMMAND", "uv"), args=args
            )
            async with stdio_client(params) as (read, write):
                return await _call(ClientSession(read, write), name, arguments)
        headers = await _cloud_run_headers()
        async with streamablehttp_client(
            os.environ["SOURCE_INTELLIGENCE_URL"], headers=headers
        ) as (read, write, _):
            return await _call(ClientSession(read, write), name, arguments)


async def _call(session: Any, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async with session:
        await session.initialize()
        result = await session.call_tool(name, arguments)
    if result.isError:
        raise RuntimeError("Source Intelligence MCP tool failed")
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise RuntimeError("Source Intelligence MCP returned no structured content")


async def _cloud_run_headers() -> dict[str, str]:
    audience = os.getenv("SOURCE_INTELLIGENCE_AUDIENCE", "").strip()
    if not audience:
        return {}
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import fetch_id_token

    token = await asyncio.to_thread(fetch_id_token, Request(), audience)
    return {"Authorization": f"Bearer {token}"}
