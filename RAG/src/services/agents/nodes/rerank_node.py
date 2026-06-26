import logging
import time
from typing import Dict, List

from langchain_core.documents import Document
from langgraph.runtime import Runtime

from ..context import Context
from ..state import AgentState
from .utils import get_latest_documents, get_latest_query

logger = logging.getLogger(__name__)


async def ainvoke_rerank_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, List[Document]]:
    """Rerank the wide candidate set retrieved before grading.

    Reads the structured documents from the tool call's artifact (not the
    flattened ToolMessage content, which loses document boundaries), calls
    Jina's cross-encoder rerank API to narrow the wide candidate set down
    to rerank_top_k, and writes the result to state["retrieved_documents"]
    for grade_documents/generate_answer to consume.

    Degrades gracefully: if there are zero candidates, the Jina API call is
    skipped entirely (no point spending a network round-trip on nothing).
    If the Jina API call fails, the original retrieval order is passed
    through unchanged rather than failing the graph.

    :param state: Current agent state
    :param runtime: Runtime context
    :returns: Dictionary with retrieved_documents
    """
    logger.info("NODE: rerank")
    start_time = time.time()

    question = get_latest_query(state["messages"])
    candidates = get_latest_documents(state["messages"])

    span = None
    if runtime.context.langfuse_enabled and runtime.context.trace:
        try:
            span = runtime.context.langfuse_tracer.create_span(
                trace=runtime.context.trace,
                name="rerank",
                input_data={"query": question, "candidate_count": len(candidates)},
                metadata={"node": "rerank", "rerank_top_k": runtime.context.rerank_top_k},
            )
        except Exception as e:
            logger.warning(f"Failed to create span for rerank: {e}")

    if not candidates:
        logger.info("No candidates to rerank, skipping Jina rerank call")
        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.end_span(
                span,
                output={"status": "skipped_empty_candidates"},
                metadata={"execution_time_ms": execution_time},
            )
        return {"retrieved_documents": []}

    try:
        texts = [doc.page_content for doc in candidates]
        response = await runtime.context.embeddings_client.rerank(
            query=question,
            documents=texts,
            top_n=runtime.context.rerank_top_k,
        )

        reranked = [candidates[item.index] for item in response.results]

        logger.info(f"Reranked {len(candidates)} candidates down to {len(reranked)}")

        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.end_span(
                span,
                output={
                    "status": "reranked",
                    "candidate_count": len(candidates),
                    "result_count": len(reranked),
                },
                metadata={"execution_time_ms": execution_time},
            )

        return {"retrieved_documents": reranked}

    except Exception as e:
        # No local fallback model for rerank (unlike embeddings) — pass
        # through the original retrieval order rather than failing the graph.
        logger.warning(f"Jina rerank API call failed: {e}, passing through original order")

        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.update_span(
                span,
                output={"status": "passthrough_on_failure", "error": str(e)},
                metadata={"execution_time_ms": execution_time, "fallback": True},
                level="WARNING",
            )
            runtime.context.langfuse_tracer.end_span(span)

        return {"retrieved_documents": candidates}
