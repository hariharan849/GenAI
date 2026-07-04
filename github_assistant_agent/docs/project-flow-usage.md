# Project Flow and Usage Guide

This guide explains how the GitHub Assistant Agent works end to end, how to run it, and where to look when something fails.

## What This Project Does

GitHub Assistant Agent is a Python 3.11+ CrewAI application that answers questions about GitHub repositories.

It has two operating modes:

- Local repo-aware answers: index a repository into a disk cache, retrieve relevant chunks, and answer from that cached context.
- Live GitHub search fallback: when no useful local context exists, use `GithubSearchTool` to search GitHub directly.

The main implementation is in `src/github_assistant_agent.py`. The Gradio UI is in `src/gradio_app.py`.

## High-Level Flow

```text
User
  |
  | CLI or Gradio UI
  v
Input validation
  |
  | resolve token, normalize repo
  v
Repository provided?
  |
  +-- no ----------------------+
  |                            |
  v                            v
Try local index            Live GitHub search
  |                            |
  | load current.json          | GithubSearchTool
  | read index.json            | CrewAI agent
  v                            |
Retrieve matching chunks       |
  |                            |
  | lexical scoring            |
  v                            |
Context CrewAI agent <---------+
  |
  | final answer
  v
Summary output
```

## Project Structure

```text
github_assistant_agent/
  src/
    github_assistant_agent.py   Core settings, indexing, retrieval, CrewAI flow, CLI
    gradio_app.py               Web UI wrapper around indexing and Q&A helpers
  tests/
    test_github_assistant_agent.py
                                 Unit tests for repo normalization, indexing, cache reuse,
                                 retrieval, stale detection, token errors, and CLI dispatch
  README.md                     Setup, CLI, Gradio, Docker, and test commands
  pyproject.toml                Package metadata, dependencies, entry points
  Dockerfile                    Container image for running the Gradio UI
  AGENTS.md                     Repository guidance for coding agents
```

## Core Concepts

### Repository normalization

The assistant accepts these repository forms and normalizes them to `owner/repo`:

```text
owner/repo
https://github.com/owner/repo
https://github.com/owner/repo.git
git@github.com:owner/repo.git
```

Invalid values raise `InvalidRepositoryError`.

### Local index

The local index is a JSON snapshot of selected repository files. It stores:

- repository name
- default branch
- commit SHA
- file path
- language
- line range
- source URL
- chunk text

The default cache root is:

```text
.github_assistant_cache/
```

Inside that cache:

```text
.github_assistant_cache/
  repos/
    owner/
      repo/
        current.json        Pointer to the active index
  indexes/
    owner__repo__<sha>/
      index.json            RepoIndexSummary plus RepoIndexChunk entries
```

### Chunk retrieval

Retrieval is lexical. The assistant tokenizes the user query, scores each chunk by matching query terms against:

- file path
- language
- chunk text

Path matches receive extra weight. The top chunks are passed to the context agent.

### CrewAI flow

`GitHubAssistantFlow` has three stages:

```text
initialize()
  |
  | validates query, token, repo
  v
search()
  |
  | local index first, live search fallback
  v
summarise()
  |
  | output header, truncation, error formatting
  v
final answer
```

## Indexing Flow

Run:

```bash
python src/github_assistant_agent.py --index --repo owner/repo
```

Detailed flow:

```text
index_repository(repo, token, refresh=False)
  |
  v
resolve_github_token()
  |
  v
normalize_github_repo()
  |
  v
resolve repo with PyGithub
  |
  v
read default branch HEAD SHA
  |
  v
build cache key: owner__repo__<short-sha>
  |
  +-- matching cache exists and refresh is false?
  |       |
  |       +-- yes -> return cached summary
  |
  v
read recursive git tree
  |
  v
filter ignored directories, binaries, oversized files
  |
  v
download selected file contents
  |
  v
detect text files and chunk by line range
  |
  v
write index.json and current.json
```

Ignored content includes dependency directories, build outputs, binary files, archives, images, lock files, and common cache directories.

Force a refresh:

```bash
python src/github_assistant_agent.py --refresh --repo owner/repo
```

## Question Answering Flow

Run:

```bash
python src/github_assistant_agent.py "How is state modeled?" --repo owner/repo
```

Detailed flow:

```text
kickoff(query, repo, token)
  |
  v
GitHubAssistantFlow.initialize()
  |
  | missing query -> error
  | missing token -> error
  | invalid repo -> error
  v
GitHubAssistantFlow.search()
  |
  +-- repo provided?
  |     |
  |     v
  |   load current index
  |     |
  |     +-- index exists?
  |           |
  |           v
  |        check stale status against GitHub
  |           |
  |           v
  |        retrieve chunks
  |           |
  |           +-- chunks found -> _run_context_agent()
  |           |
  |           +-- no chunks -> live GitHub search
  |
  +-- no repo -> live GitHub search
  |
  v
GitHubAssistantFlow.summarise()
```

When local chunks are used, the answer starts with metadata like:

```text
Local index: owner/repo@abc123def456 (current)
Retrieved chunks: 6
```

## Live Search Fallback

The fallback path uses `GithubSearchTool` with FastEmbed configured as:

```text
provider: fastembed
model: BAAI/bge-small-en-v1.5
```

Use this path when:

- no repository is provided
- no local index exists
- the index exists but no retrieved chunks match the query

## Gradio UI Flow

Run:

```bash
python src/gradio_app.py
```

The UI exposes two workflows:

```text
Index repository button
  |
  v
run_index(repo, token, refresh)
  |
  v
index_repository()
  |
  v
Markdown status output
```

```text
Ask button or query submit
  |
  v
run_agent(query, repo, token)
  |
  v
kickoff()
  |
  v
Markdown answer output
```

The token field is optional. If entered, it overrides `GITHUB_TOKEN` from the environment.

## Configuration

Required:

```bash
GITHUB_TOKEN=...
GROQ__API_KEY=...
```

Optional:

```bash
OPENAI_API_KEY=...
CREWAI_TRACING_ENABLED=true
```

Index limits:

```bash
GITHUB_ASSISTANT_CACHE_DIR=.github_assistant_cache
GITHUB_ASSISTANT_MAX_FILES=250
GITHUB_ASSISTANT_MAX_FILE_BYTES=250000
GITHUB_ASSISTANT_MAX_TOTAL_CHARS=2000000
```

Groq settings:

```bash
GROQ__MODEL=llama-3.3-70b-versatile
GROQ__TEMPERATURE=0.2
GROQ__MAX_TOKENS=1000
```

Settings are loaded from:

```text
<repo-root>/.env
src/.env
environment variables
```

## CLI Reference

### Build or reuse an index

```bash
python src/github_assistant_agent.py --index --repo owner/repo
```

With an explicit token:

```bash
python src/github_assistant_agent.py --index --repo owner/repo --token ghp_your_token
```

### Refresh an index

```bash
python src/github_assistant_agent.py --refresh --repo owner/repo
```

### Ask a repo-scoped question

```bash
python src/github_assistant_agent.py "Where is the CLI parser defined?" --repo owner/repo
```

### Ask a global GitHub question

```bash
python src/github_assistant_agent.py "What are popular Python async HTTP clients?"
```

### Render the CrewAI flow diagram

```bash
python src/github_assistant_agent.py --plot
```

This writes:

```text
github_assistant_flow.html
```

## Docker Usage

Build:

```bash
docker build -t github-assistant-agent .
```

Run the Gradio UI:

```bash
docker run --rm -p 7860:7860 \
  -e GITHUB_TOKEN=your_github_token \
  -e GROQ__API_KEY=your_groq_api_key \
  -v github-assistant-cache:/app/.github_assistant_cache \
  github-assistant-agent
```

Run CLI indexing through Docker:

```bash
docker run --rm \
  -e GITHUB_TOKEN=your_github_token \
  -e GROQ__API_KEY=your_groq_api_key \
  -v github-assistant-cache:/app/.github_assistant_cache \
  github-assistant-agent \
  python src/github_assistant_agent.py --index --repo owner/repo
```

## Common Tasks

### How to index a private repository

1. Create a GitHub token that can read the repository contents and metadata.
2. Set it in your shell:

   ```bash
   export GITHUB_TOKEN=your_token
   ```

3. Run indexing:

   ```bash
   python src/github_assistant_agent.py --index --repo owner/repo
   ```

4. Verify the output includes file and chunk counts.

### How to ask from cached context

1. Index the repository first.
2. Ask a repo-scoped question:

   ```bash
   python src/github_assistant_agent.py "How does indexing work?" --repo owner/repo
   ```

3. Check that the answer includes `Local index:` and `Retrieved chunks:`.

### How to clear the cache

Delete the cache directory:

```bash
rm -rf .github_assistant_cache
```

PowerShell:

```powershell
Remove-Item -Recurse -Force .github_assistant_cache
```

Then re-run indexing.

## Error Handling and Troubleshooting

### Bad credentials

Error:

```text
Indexing error: GitHub API error while resolving repo: {'message': 'Bad credentials', ... 'status': '401'}
```

Meaning: GitHub rejected the token.

Fix:

- Check that `GITHUB_TOKEN` is set.
- Make sure the token is not expired or revoked.
- If using `--token`, remember it overrides the environment token.
- For private repos, make sure the token can read repository contents and metadata.

PowerShell checks without printing the token:

```powershell
[bool]$env:GITHUB_TOKEN
$env:GITHUB_TOKEN.Length
```

### Missing token

Error:

```text
A GitHub token is required. Set GITHUB_TOKEN or pass a token explicitly.
```

Fix:

```bash
export GITHUB_TOKEN=your_token
```

or:

```bash
python src/github_assistant_agent.py --index --repo owner/repo --token your_token
```

### Invalid repository

Error:

```text
Invalid GitHub repository format. Use owner/repo or a GitHub repo URL.
```

Fix: use `owner/repo`, an HTTPS GitHub repo URL, or an SSH GitHub clone URL.

### Rate limit exceeded

Error:

```text
GitHub API rate limit exceeded. Retry later.
```

Fix:

- Wait for the rate limit window to reset.
- Use a token with higher allowed usage.
- Avoid repeated refreshes unless needed.

### Empty or weak local answers

Possible causes:

- The repository was never indexed.
- The query terms do not match indexed paths or text.
- Important files were skipped due to size, extension, or total character limits.
- The local index is stale.

Fix:

```bash
python src/github_assistant_agent.py --refresh --repo owner/repo
```

Then ask a more specific question using file names, function names, or domain terms from the repo.

## Testing

Run:

```bash
uv run pytest -q
```

The current tests cover:

- repository normalization
- invalid repository rejection
- cache key generation
- ignored path filtering
- binary/text detection
- lexical retrieval scoring
- index persistence
- cache reuse
- stale index detection
- missing token errors
- CLI dispatch for indexing and Q&A

## Development Notes

The project currently keeps most backend behavior in `src/github_assistant_agent.py`. That is acceptable at this size, but new features should keep helpers small and grouped by responsibility.

Recommended organization inside the core module:

```text
Settings and models
GitHub access and indexing
Retrieval
CrewAI agents
Flow orchestration
CLI helpers
```

If a new feature grows beyond a few focused helpers, split it into a new module under `src/` and update `pyproject.toml` package inclusion.

## Design Trade-Offs

### Why cache a local index?

The cache avoids re-reading the same repository for every question. It also gives answers stable source links tied to a commit SHA.

Trade-off: the cache can become stale when the default branch changes. The assistant checks freshness when a repo-scoped answer uses a cached index.

### Why lexical retrieval first?

Lexical retrieval is simple, deterministic, and easy to test. It works well for questions that mention file names, functions, commands, or domain terms.

Trade-off: it can miss conceptual matches when the query uses different words than the code. A future semantic retriever could improve this.

### Why live search fallback?

Some questions are broader than one local repository, or no useful local chunks may be found. The fallback keeps the assistant useful in those cases.

Trade-off: live search depends on GitHub/tool behavior and is less deterministic than cached context.

## Reader Map

Use this guide when you want to understand the project flow.

Use `README.md` when you want the shortest setup and command reference.

Use `tests/test_github_assistant_agent.py` when you want executable examples of expected behavior.

Use `src/github_assistant_agent.py` when you need to change backend behavior.

Use `src/gradio_app.py` when you need to change the web UI.
