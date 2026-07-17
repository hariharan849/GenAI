# Source Intelligence MCP Server

This service exposes `search_web`, `fetch_webpage`, and `verify_citations` to
the researcher, judge, and content builder. Search uses Tavily; retrieval only
permits public HTTPS pages and caps evidence at 20,000 characters.

Set `TAVILY_API_KEY` before using `search_web`.

For local development, `run_local.sh` configures the three agents to launch
this service over stdio. To run it independently over Streamable HTTP:

```bash
cd agents/source_intelligence
uv sync
PORT=8005 uv run python main.py
```

The MCP endpoint is available at `http://localhost:8005/mcp`. In Cloud Run,
`deploy.sh` deploys the service as IAM-protected and grants only the researcher,
judge, and content-builder runtime identities the invoker role.
