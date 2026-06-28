# Agentic RAG — LangGraph Workflow

The `AgenticRAGService` wraps a compiled LangGraph graph that processes each user question through a multi-node pipeline with guardrails, intent classification, document grading, re-ranking, query rewriting, and final answer generation.

---

## Workflow

```
User Question
      │
      ▼
 InputGuardrail ──(unsafe)──► [blocked response]
      │
      ▼ (safe)
 IntentClassify ──(out-of-scope)──► OutOfScope ──► [deflection response]
      │
      ▼ (in-scope)
   Retrieve  (OpenSearch hybrid search)
      │
      ▼
 GradeDocuments  (relevance check per chunk)
      │
      ▼
    Rerank  (sort by relevance score)
      │
      ├──(insufficient docs)──► RewriteQuery ──► Retrieve (retry once)
      │
      ▼ (sufficient docs)
 OutputGuardrail ──(unsafe)──► [blocked response]
      │
      ▼ (safe)
 GenerateAnswer  (Ollama + citations)
      │
      ▼
  Final Answer
```

---

## Node Reference

| Node | File | Responsibility |
|------|------|----------------|
| `InputGuardrail` | `nodes/input_guardrail_node.py` | Blocks harmful or policy-violating input |
| `IntentClassify` | `nodes/intent_classify_node.py` | Routes Nuke-related vs off-topic questions |
| `OutOfScope` | `nodes/out_of_scope_node.py` | Returns a friendly deflection message |
| `Retrieve` | `nodes/retrieve_node.py` | Calls OpenSearch hybrid search via LangChain tool |
| `GradeDocuments` | `nodes/grade_documents_node.py` | Scores each retrieved chunk for relevance |
| `Rerank` | `nodes/rerank_node.py` | Sorts graded documents by descending score |
| `RewriteQuery` | `nodes/rewrite_query_node.py` | Rewrites the query when retrieved docs are insufficient |
| `OutputGuardrail` | `nodes/output_guardrail_node.py` | Checks generated answer before returning to user |
| `GenerateAnswer` | `nodes/generate_answer_node.py` | Produces the final answer with citations via Ollama |

Shared guardrail utilities (prompt templates, result parsing) live in `nodes/guardrail_common.py`.

---

## Key Files

| File | Purpose |
|------|---------|
| `agentic_rag.py` | Builds and compiles the LangGraph graph; `AgenticRAGService` class |
| `state.py` | `AgentState` TypedDict — shared state passed between all nodes |
| `context.py` | Dependency container injected into each node (avoids closures) |
| `factory.py` | Constructs `AgenticRAGService` with all dependencies wired up |
| `config.py` | Node-specific configuration (thresholds, retry limits) |
| `models.py` | Internal Pydantic models used across nodes |
| `prompts.py` | All LLM prompt templates for the agentic pipeline |
| `tools.py` | LangChain tool wrapping the OpenSearch retriever |

---

## State Shape (`AgentState`)

Key fields in the shared graph state:

| Field | Type | Description |
|-------|------|-------------|
| `question` | `str` | Original user question |
| `rewritten_question` | `str \| None` | Query after rewrite (if triggered) |
| `documents` | `list[Document]` | Retrieved + graded chunks |
| `generation` | `str \| None` | Final answer text |
| `guardrail_triggered` | `bool` | Whether input/output guardrail fired |
| `intent` | `str` | `"in_scope"` or `"out_of_scope"` |
| `retry_count` | `int` | Number of retrieve-rewrite cycles attempted |

---

## Thread ID / Checkpointing

The graph uses `AsyncPostgresSaver` for conversation memory. Pass a `thread_id` in the request body to continue a prior conversation. Each thread's checkpoints are stored in PostgreSQL (tables created automatically by `AsyncPostgresSaver.setup()` at startup).

A dedicated `AsyncConnectionPool` (size 5) is reserved for checkpointing and is separate from the SQLAlchemy application pool.

---

## Configuration

Agentic RAG thresholds and limits are in `config.py`:

- `min_relevant_docs` — minimum graded-relevant docs before triggering query rewrite
- `max_retries` — maximum retrieve-rewrite cycles
- `grade_threshold` — minimum relevance score to keep a chunk

These can also be overridden via environment variables (see `api/config.py`).
