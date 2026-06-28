# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
uv venv .venv
uv pip install -e .
```

Requires Python ≥ 3.11. Dependencies are managed with `uv` and locked in `uv.lock`.

## Running

**Gradio web UI:**
```bash
python src/gradio_app.py
```

**CLI:**
```bash
python src/github_assistant_agent.py "Your GitHub question" --repo owner/repo --token ghp_...
```

**Render flow diagram (saves `github_assistant_flow.html`):**
```bash
python src/github_assistant_agent.py --plot
```

## Environment variables

Copy `src/.env` and populate:

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` | GitHub PAT for `GithubSearchTool` |
| `GROQ__API_KEY` | Groq API key (note double underscore — pydantic-settings nested delimiter) |
| `OPENAI_API_KEY` | Optional; not used by the agent itself |
| `CREWAI_TRACING_ENABLED` | Set `true` to enable CrewAI telemetry |

`Settings` loads from `<repo-root>/.env` (one level above `src/`). Nested Groq settings use the `GROQ__` prefix (e.g., `GROQ__API_KEY`, `GROQ__MODEL`, `GROQ__TEMPERATURE`).

## Architecture

The project is a **CrewAI Flow** (`GitHubAssistantFlow`) with three sequential stages:

```
initialize()  →  search()  →  summarise()
   @start         @listen       @listen
```

**`src/github_assistant_agent.py`** — the core module:
- `GitHubAssistantState` (Pydantic `BaseModel`) — shared state passed between all flow stages: `query`, `github_repo`, `gh_token`, `crew_result`, `summary`, `error`.
- `GitHubAssistantFlow` — the Flow subclass. Each stage returns a string event (`"initialized"`, `"done"`, `"error"`) that the next stage receives as its `event` argument to decide whether to skip.
- `initialize()` — validates the query and resolves the GitHub token (state value takes precedence over `GITHUB_TOKEN` env-var).
- `search()` — builds a `GithubSearchTool` (with `fastembed` as the embedding provider using `BAAI/bge-small-en-v1.5`), constructs a single ReAct `Agent`, wraps it in a `Crew`, and calls `crew.kickoff()`.
- `summarise()` — trims the crew output to 8 000 characters and stores it in `state.summary`.
- `kickoff()` / `plot()` — public helpers (also registered as `pyproject.toml` entry-points, though the entry-point paths in `pyproject.toml` reference `github_assistant_flow.main` which is a stale path; the real module is `src/github_assistant_agent.py`).
- `normalize_github_repo()` — accepts `owner/repo`, HTTPS URLs, and SSH clone URLs; normalises all forms to `owner/repo`.

**`src/gradio_app.py`** — thin Gradio `gr.Blocks` UI that calls `kickoff()` directly. Token entered in the UI overrides the env-var.

## Key design notes

- The LLM is accessed through `crewai.LLM` (which wraps LiteLLM). The model string must be prefixed with `groq/` (e.g., `"groq/llama-3.3-70b-versatile"`).
- `GithubSearchTool` requires `gh_token` to be passed explicitly at construction time — it does not read `GITHUB_TOKEN` automatically.
- The agent has `max_iter=10` and `max_rpm=20` to stay within Groq rate limits.
- `allow_delegation=False` keeps the single-agent Crew from spawning sub-agents.
