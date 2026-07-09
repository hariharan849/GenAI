# LinkedIn Post Draft: Nuke Documentation RAG System

I spent some time building a RAG system for Foundry Nuke documentation, and the biggest takeaway was this:

RAG is not really an LLM problem first. It is a data and systems problem.

The first version of the idea sounds simple enough:

> Ask a question about Nuke docs. Get a useful answer with sources.

But once I started building it properly, the work quickly became much more than embedding a few pages and calling a model.

The pipeline now does a full ingestion pass:

```text
scrape Foundry Nuke 17.0 docs
  -> save pages in PostgreSQL
  -> split them into useful sections
  -> create Jina embeddings
  -> use Ray Data for batch chunking, embedding, and indexing
  -> index chunks for hybrid search
  -> extract relationship facts into Neo4j
  -> serve answers through FastAPI and a Next.js UI
```

I also added a few things that are easy to skip in demos but matter a lot in practice:

- Airflow, Prefect, and Dagster options for ingestion
- Ray Data for parallel indexing work
- PostgreSQL `pg_embedding` as the default vector backend
- OpenSearch as an alternate backend
- Neo4j knowledge graph retrieval for node relationships
- Redis exact-match caching
- optional semantic answer caching with Redis Stack
- LangGraph for the agentic RAG path
- Presidio and Llama Guard for guardrails
- Prometheus, Grafana, Loki, and Langfuse for visibility

One decision I liked was keeping simple RAG and agentic RAG separate.

The simple endpoint is predictable:

```text
cache -> retrieve -> generate -> store
```

The agentic path does more:

```text
guardrails -> intent check -> retrieve -> rerank -> grade -> rewrite if needed -> generate -> validate output
```

That split made the system easier to debug. When something feels wrong, I can compare the simple path against the agentic path instead of debugging one giant workflow.

Another lesson: metadata matters as much as embeddings.

For each chunk, I keep the source URL, node name, documentation section, section title, and chunk index. Those fields make filtering, source display, debugging, and future improvements much easier.

Ray also ended up in the right place: ingestion, not serving.

It helps with the batch-heavy work of turning pages into chunks, embeddings, and indexed records. User requests still hit a ready search index instead of waiting for distributed processing to spin up.

The retrieval path also has a knowledge graph layer. For the agentic flow, the retriever can combine BM25/vector results with Neo4j facts when it detects a known Nuke node in the query. That gives the model both documentation chunks and compact relationship facts like which knobs, inputs, or categories belong to a node.

The same goes for caching. Exact caching is straightforward. Semantic caching is powerful, but it can be dangerous if it reuses an answer after the model, prompt, search backend, or chunking strategy changes. So the cache scope includes those details.

The part I appreciate most now is the observability.

If an answer is slow or bad, I do not want to guess. I want to know whether the issue came from retrieval, embeddings, generation, cache misses, guardrails, or prompt construction.

So the system tracks those pieces separately.

My main takeaway from the build:

Production-style RAG is less about having the fanciest prompt and more about building the boring pieces carefully:

- clean ingestion
- batch indexing with Ray where it helps
- sensible chunking
- hybrid retrieval
- Neo4j graph facts where relationships matter
- useful metadata
- safe caching
- guardrails
- evaluation
- tracing and metrics

The user only sees a chat box.

Underneath, the quality comes from everything that happens before the model writes the answer.
