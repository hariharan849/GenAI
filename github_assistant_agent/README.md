# GitHub Assistant Agent

A CrewAI-powered GitHub assistant that can index a repository into a local disk cache and answer questions against that cached repository context. It also keeps the original live GitHub search fallback for broader questions or missing local context.

## Setup

```bash
uv venv .venv
uv pip install -e .
```

Required environment variables:

```bash
GITHUB_TOKEN=...
GROQ__API_KEY=...
```

`OPENAI_API_KEY` is optional for this project. Private repositories are supported when `GITHUB_TOKEN` has access.

## Index A Repository

Build or reuse a local index for the current default branch:

```bash
python src/github_assistant_agent.py --index --repo owner/repo
```

Force a refresh:

```bash
python src/github_assistant_agent.py --refresh --repo owner/repo
```

The cache is stored under `.github_assistant_cache` by default. The index key includes the normalized repo name and default-branch HEAD SHA, so a matching cache is reused and a changed default branch can be detected as stale.

## Ask Questions

Ask against a repository:

```bash
python src/github_assistant_agent.py "How is state modeled?" --repo owner/repo
```

Ask a global GitHub question:

```bash
python src/github_assistant_agent.py "What are popular Python async HTTP clients?"
```

When a repo is provided, the assistant retrieves relevant cached chunks first and includes file paths and source links in the CrewAI task. If no useful local context is found, it falls back to `GithubSearchTool`.

## Gradio UI

```bash
python src/gradio_app.py
```

The UI includes:

- repository and token inputs
- an index/refresh action with status
- a question box
- answer output with source links when available

## Configuration

These settings can be changed with environment variables:

```bash
GITHUB_ASSISTANT_CACHE_DIR=.github_assistant_cache
GITHUB_ASSISTANT_MAX_FILES=250
GITHUB_ASSISTANT_MAX_FILE_BYTES=250000
GITHUB_ASSISTANT_MAX_TOTAL_CHARS=2000000
```

Ignored content includes dependency directories, build outputs, binary files, images, archives, and lock files. Tokens are read from the environment or request input and are not written to cache.

## Docker

Build:

```bash
docker build -t github-assistant-agent .
```

Run the Gradio UI on `http://localhost:7860`.

Linux/macOS:

```bash
docker run --rm -p 7860:7860 \
  -e GITHUB_TOKEN=your_github_token \
  -e GROQ__API_KEY=your_groq_api_key \
  -v github-assistant-cache:/app/.github_assistant_cache \
  github-assistant-agent
```

PowerShell:

```powershell
docker run --rm -p 7860:7860 `
  -e GITHUB_TOKEN=your_github_token `
  -e GROQ__API_KEY=your_groq_api_key `
  -v github-assistant-cache:/app/.github_assistant_cache `
  github-assistant-agent
```

Run indexing through the image.

Linux/macOS:

```bash
docker run --rm \
  -e GITHUB_TOKEN=your_github_token \
  -e GROQ__API_KEY=your_groq_api_key \
  -v github-assistant-cache:/app/.github_assistant_cache \
  github-assistant-agent \
  python src/github_assistant_agent.py --index --repo owner/repo
```

PowerShell:

```powershell
docker run --rm `
  -e GITHUB_TOKEN=your_github_token `
  -e GROQ__API_KEY=your_groq_api_key `
  -v github-assistant-cache:/app/.github_assistant_cache `
  github-assistant-agent `
  python src/github_assistant_agent.py --index --repo owner/repo
```

Run Q&A through the image.

Linux/macOS:

```bash
docker run --rm \
  -e GITHUB_TOKEN=your_github_token \
  -e GROQ__API_KEY=your_groq_api_key \
  -v github-assistant-cache:/app/.github_assistant_cache \
  github-assistant-agent \
  python src/github_assistant_agent.py "Your GitHub question" --repo owner/repo
```

PowerShell:

```powershell
docker run --rm `
  -e GITHUB_TOKEN=your_github_token `
  -e GROQ__API_KEY=your_groq_api_key `
  -v github-assistant-cache:/app/.github_assistant_cache `
  github-assistant-agent `
  python src/github_assistant_agent.py "Your GitHub question" --repo owner/repo
```

## Tests

```bash
uv pip install pytest
pytest
```
