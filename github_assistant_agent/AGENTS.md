# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.11+ CrewAI GitHub assistant project. Core source files live in `src/`:

- `src/github_assistant_agent.py` contains the CrewAI Flow, state model, GitHub search logic, CLI entry point, and flow plotting helper.
- `src/gradio_app.py` provides the Gradio web UI.
- `src/.env` is a local example/config file; keep real secrets out of commits.

There is currently no `tests/` directory. Add tests under `tests/` when changing behavior, mirroring source module names such as `tests/test_github_assistant_agent.py`.

## Build, Test, and Development Commands

Use `uv` for environment and dependency management:

```bash
uv venv .venv
uv pip install -e .
```

Run the Gradio UI:

```bash
python src/gradio_app.py
```

Run the assistant from the CLI:

```bash
python src/github_assistant_agent.py "Your GitHub question" --repo owner/repo --token ghp_...
```

Render the CrewAI flow diagram:

```bash
python src/github_assistant_agent.py --plot
```

## Coding Style & Naming Conventions

Follow idiomatic Python with 4-space indentation, type hints for public functions, and small functions with explicit responsibilities. Use `snake_case` for functions and variables, `PascalCase` for Pydantic models and classes, and clear names for CrewAI stages such as `initialize`, `search`, and `summarise`.

Prefer existing patterns in `src/github_assistant_agent.py`: Pydantic settings/state models, explicit error handling through state, and concise CLI-facing messages.

## Testing Guidelines

Use `pytest` for new tests. Focus on deterministic units first, especially repository normalization, settings handling, and error paths that do not require live GitHub or LLM calls. Mock external services such as GitHub, Groq, CrewAI, and embeddings.

Example:

```bash
uv pip install pytest
pytest
```

## Commit & Pull Request Guidelines

Recent history uses short subjects and occasional Conventional Commit prefixes, for example `feat: ...` and `chore: ...`. Prefer concise imperative subjects:

```text
feat: add repository normalization tests
chore: update agent dependencies
```

Pull requests should include a brief summary, commands run, linked issues when applicable, and screenshots for Gradio UI changes. Call out any new environment variables or changes to API-token handling.

## Security & Configuration Tips

Required configuration includes `GITHUB_TOKEN` and `GROQ__API_KEY`; `OPENAI_API_KEY` is optional. Load secrets from a local `.env` file and never commit personal access tokens. Keep CrewAI telemetry settings explicit with `CREWAI_TRACING_ENABLED` when debugging or sharing runs.
