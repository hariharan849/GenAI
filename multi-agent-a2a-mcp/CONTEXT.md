# Course-Creation System

This context defines the shared concepts used by the agents that research,
assess, and turn learning material into courses.

## Language

**Source Intelligence MCP Server**:
A shared MCP server that makes current, externally sourced information
available to the course-creation agents.
_Avoid_: researcher search tool, web-search agent

**Web Search**:
Discovery of current candidate sources as URL, title, snippet, and publication
metadata. It does not provide the source's full content.
_Avoid_: web scraping, evidence retrieval

**Webpage Retrieval**:
Extraction of readable source content from one discovered URL for use as
evidence by an agent.
_Avoid_: search, crawling

**Source Record**:
The structured representation of one externally sourced item, including its
provenance, available dates, and evidence text.
_Avoid_: citation string, search result text

**Freshness Window**:
The caller-selected maximum age for a latest-news search, expressed as 24
hours, 7 days, or 30 days.
_Avoid_: latest, recent

**Domain Allowlist**:
An optional caller-supplied set of publisher domains that limits a web search
to those sources.
_Avoid_: trusted-source mode, source filter

**Current-Information Request**:
A learning request that explicitly asks for news, latest developments, today,
recent events, or a date range, and therefore requires live-source research.
_Avoid_: current topic, fresh query

**Live-Source Failure**:
The unavailability of search or retrieval required to satisfy a
Current-Information Request. It produces a clear research failure rather than
an answer based on potentially stale model knowledge.
_Avoid_: fallback research, uncited current answer
