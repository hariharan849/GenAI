# Repository Guidelines

## Project Structure & Module Organization

This repository is a distributed course-creation system built with Google ADK and A2A. Each service is independently packaged:

- `agents/orchestrator/` coordinates the workflow.
- `agents/researcher/`, `agents/judge/`, and `agents/content_builder/` provide specialized agent services.
- `app/` contains the FastAPI web server; browser assets live in `app/frontend/`.
- `shared/` contains common A2A, HTTP, and ADK helpers mirrored or linked into services.
- Root scripts (`run_local.sh`, `deploy.sh`, `init.sh`) manage local startup and Google Cloud setup/deployment.

Keep service-specific logic in its service directory. When changing a shared helper, verify every mirrored copy remains consistent.

## Build, Test, and Development Commands

- `uv sync --all-groups --all-extras`: install runtime, test, lint, and optional dependencies from `uv.lock`.
- `gcloud auth application-default login`: configure local Google Cloud credentials.
- `./run_local.sh`: start the agents on ports 8001-8004 and the web app on port 8000 (run from Bash/WSL on Windows).
- `uv run pytest`: run the test suite.
- `uv run ruff check .`: check Python style, imports, and common defects.
- `uv run ruff format --check .`: verify formatting.
- `uv run mypy .`: run static type checks.

For a single service, run commands from its directory; for example, `cd app && uv run uvicorn main:app --reload --port 8000`.

## Coding Style & Naming Conventions

Target Python 3.10+. Use four-space indentation, type annotations for public functions, `snake_case` for functions/modules, and `PascalCase` for classes. Ruff enforces an 88-column target and import ordering; format code before submitting. Use descriptive agent and environment-variable names, following existing patterns such as `CONTENT_BUILDER_AGENT_CARD_URL`. Never commit `.env`, API keys, or cloud credentials.

## Testing Guidelines

Pytest and `pytest-asyncio` are configured, although no tests are currently checked in. Add tests under `tests/`, named `test_<feature>.py`, and name cases `test_<behavior>`. Cover success, failure, and async/A2A integration paths for changed behavior. Run `uv run pytest` before opening a pull request.

## Commit & Pull Request Guidelines

Git history is not included in this starter workspace. Use concise, imperative commits, optionally with Conventional Commit prefixes, such as `feat: add judge retry limit` or `fix: validate agent card URL`. Pull requests should explain the user-visible change, list verification commands, link relevant issues, and include screenshots for frontend changes. Call out configuration, deployment, or API-contract changes explicitly.
