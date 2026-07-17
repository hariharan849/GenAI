"""Run the Source Intelligence MCP server over stdio or Streamable HTTP."""

from __future__ import annotations

import argparse
import os

from source_intelligence.server import mcp


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdio", action="store_true")
    args = parser.parse_args()
    if args.stdio:
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = os.getenv("HOST", "0.0.0.0")
        mcp.settings.port = int(os.getenv("PORT", "8005"))
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
