"""MCP tool definitions for live source intelligence."""

from mcp.server.fastmcp import FastMCP

from .service import SourceIntelligenceService

mcp = FastMCP("Source Intelligence", json_response=True)
service = SourceIntelligenceService()


@mcp.tool()
async def search_web(
    query: str,
    freshness_window: str = "",
    allowed_domains: list = None,
    max_results: int = 5,
) -> dict:
    """Discover current sources. Use a freshness window for news or recent events."""
    return await service.search_web(
        query, freshness_window or None, allowed_domains, max_results
    )


@mcp.tool()
async def fetch_webpage(url: str) -> dict:
    """Retrieve readable evidence from a public HTTPS URL, capped at 20,000 characters."""
    return await service.fetch_webpage(url)


@mcp.tool()
async def verify_citations(urls: list) -> dict:
    """Verify cited public HTTPS pages and return readable evidence or safe failures."""
    return await service.verify_citations(urls)
