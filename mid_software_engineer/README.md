# Mid Software Engineer Deep Agent

This project creates a LangChain DeepAgents agent that behaves like a mid-level software developer:

1. Understand product-owner requirements.
2. Shape the idea with the global gstack `office-hours` skill.
3. Produce a design flow and send it through the global gstack `autoplan` review path.
4. Implement in small steps with unit tests.
5. Demo the requirement.
6. Use the global gstack `ship` skill when the work is verified and ready to package.

The agent intentionally references only these global gstack skill directories:

- `C:/Users/HARI/.agents/skills/office-hours/`
- `C:/Users/HARI/.agents/skills/autoplan/`
- `C:/Users/HARI/.agents/skills/ship/`

## Install

```powershell
uv sync --extra test
```

## Demo

The demo prints the configured DeepAgent inputs without requiring provider credentials.

```powershell
uv run mid-se-agent-demo --model openai:gpt-5.4
```

To construct the real agent object, set your provider credentials first and pass `--construct`:

```powershell
$env:OPENAI_API_KEY = "..."
uv run mid-se-agent-demo --model openai:gpt-5.4 --construct
```

To invoke the agent with a sample product-owner request:

```powershell
uv run mid-se-agent-demo --model openai:gpt-5.4 --invoke
```

## UI

Run the local ChatKit-oriented UI:

```powershell
$env:OPENAI_API_KEY = "..."
uv run mid-se-agent-ui --port 8000
```

Then open `http://127.0.0.1:8000/`.

Without provider credentials, run in configuration/demo mode:

```powershell
$env:MID_SE_AGENT_SKIP_CONSTRUCT = "true"
uv run mid-se-agent-ui --port 8000
```

The UI loads ChatKit's web script and reserves `/chatkit` for the custom ChatKit server protocol. The MVP console sends messages to `/api/agent/message`, which invokes the DeepAgent directly. The agent is configured with `CodeInterpreterMiddleware` and human-in-loop interrupts for file writes/edits.

## Tracing

Tool calls are traced to SQLite and correlated with LangSmith metadata.

```powershell
$env:LANGSMITH_API_KEY = "..."
$env:LANGSMITH_TRACING = "true"
$env:LANGSMITH_PROJECT = "mid-software-engineer"
$env:MID_SE_TRACE_DB = ".\agent_traces.sqlite3"
uv run mid-se-agent-ui --port 8001
```

Inspect recent local traces:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/traces
```

The trace middleware records tool name, arguments, status, latency, thread id, and inferred gstack skill usage when a `SKILL.md` read points at `office-hours`, `autoplan`, or `ship`.

## Test

```powershell
uv run pytest
```
