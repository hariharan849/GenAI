# Tests

Root-level test suite covering service integrations, repository operations, and agentic RAG behaviour. API-specific tests live under `api/tests/`.

---

## Running Tests

```bash
# Run all tests
uv run pytest

# Run a specific file
uv run pytest tests/test_semantic_chunking.py

# Run with verbose output
uv run pytest -v

# Run only fast unit tests (skip slow integration tests)
uv run pytest -m "not integration"
```

---

## Test Files

| File | What it tests |
|------|---------------|
| `test_semantic_chunking.py` | Section-aware text chunker (target size, overlap, minimum) |
| `test_nuke_page_repository.py` | PostgreSQL NukePageRepository CRUD operations |
| `test_save_nuke_pages.py` | End-to-end save pipeline step |
| `test_ray_indexing.py` | Parallel indexing behaviour |
| `test_graph_extraction.py` | Graph extraction utilities |
| `test_neo4j_client.py` | Neo4j client integration |
| `services/agents/test_agentic_rag_thread_id.py` | Thread ID continuity across LangGraph checkpoints |
| `conftest.py` | Shared fixtures (DB session, mock clients) |

API-level tests (router, harness) are in `api/tests/`.

---

## Configuration

Tests that hit real services (PostgreSQL, OpenSearch, Redis) require the local infrastructure stack to be running:

```bash
docker compose up -d
```

Integration tests are slower and may be skipped in CI with `-m "not integration"`.

Test environment variables are read from `.env` in the repo root (same as development).
