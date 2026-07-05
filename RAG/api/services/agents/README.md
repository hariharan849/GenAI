# Agentic RAG - LangGraph Workflow

The `AgenticRAGService` wraps a compiled LangGraph graph that processes each user question through privacy/safety guardrails, intent classification, retrieval, grading, reranking, answer generation, and output validation.

## Workflow

```text
User Question
  |
  v
InputGuardrail -- unsafe --> SafetyRefusal --> END
  |
  v
IntentClassify -- out_of_scope --> OutOfScope --> END
  |
  v
Retrieve --> ToolRetrieve --> Rerank --> GradeDocuments
                                      |
                                      +-- rewrite_query --> RewriteQuery --> Retrieve
                                      |
                                      v
GenerateAnswer --> OutputGuardrail -- unsafe --> SafetyRefusal --> END
                         |
                         +-- grounding_failed --> OutOfScope --> END
                         |
                         v
                        END
```

## Guardrail Split

| Layer | Owner | Responsibility |
|------|------|----------------|
| Privacy | `api/services/guardrails/presidio.py` | Redacts PII with Presidio before downstream LLM/tool calls |
| Safety | `api/services/guardrails/llama_guard.py` | Classifies unsafe input/output with Llama Guard |
| Policy | `api/services/guardrails/policy.py` | Projects native decisions into legacy `GuardrailScoring` |
| Domain scope | `nodes/intent_classify_node.py` | Routes Nuke/VFX questions separately from safety policy |
| RAG quality | `nodes/output_guardrail_node.py` | Checks source grounding before final response |

## Node Reference

| Node | File | Responsibility |
|------|------|----------------|
| `InputGuardrail` | `nodes/input_guardrail_node.py` | Runs Presidio redaction and Llama Guard input safety |
| `IntentClassify` | `nodes/intent_classify_node.py` | Routes Nuke-related vs off-topic questions |
| `OutOfScope` | `nodes/out_of_scope_node.py` | Returns a domain/RAG-quality deflection message |
| `SafetyRefusal` | `nodes/safety_refusal_node.py` | Returns the distinct safety refusal |
| `Retrieve` | `nodes/retrieve_node.py` | Creates the retrieval tool call |
| `ToolRetrieve` | `tools.py` | Runs documentation retrieval |
| `Rerank` | `nodes/rerank_node.py` | Sorts retrieved documents by descending score |
| `GradeDocuments` | `nodes/grade_documents_node.py` | Scores retrieved chunks for relevance |
| `RewriteQuery` | `nodes/rewrite_query_node.py` | Rewrites the effective query when docs are insufficient |
| `GenerateAnswer` | `nodes/generate_answer_node.py` | Produces the answer with retrieved context |
| `OutputGuardrail` | `nodes/output_guardrail_node.py` | Checks grounding and Llama Guard output safety |

## Key Files

| File | Purpose |
|------|---------|
| `agentic_rag.py` | Service wrapper, request execution, response compatibility fields |
| `graph_builder.py` | Shared LangGraph topology for FastAPI and local LangGraph entrypoints |
| `state.py` | `AgentState` TypedDict shared between nodes |
| `context.py` | Runtime dependency container injected into nodes |
| `factory.py` | Constructs `AgenticRAGService` |
| `nodes/utils.py` | Query/context helpers, including `get_effective_query(state)` |
| `api/services/guardrails/` | Presidio, Llama Guard, and policy orchestration |

## State Notes

`sanitized_query` is set when Presidio redacts user input. Downstream LLM/tool nodes call `get_effective_query(state)`, which prefers `sanitized_query` and falls back to the latest human message. The original user query remains in message history for audit and user-facing echo paths.

Existing API response fields are preserved:

- `guardrail_score`
- `output_guardrail_score`
- `rejected_at`
- `pii_redacted`
