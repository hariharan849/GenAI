import logging
import time
from typing import Dict, List

from langchain_core.documents import Document
from langgraph.runtime import Runtime

from ..context import Context
from ..state import AgentState
from .utils import get_latest_documents, get_latest_query
from .tracing import create_node_span, finish_node_span

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

    span = create_node_span(
        runtime,
        "rerank",
        input_data={"query": question, "candidate_count": len(candidates)},
        metadata={"node": "rerank", "rerank_top_k": runtime.context.rerank_top_k},
    )

    if not candidates:
        logger.info("No candidates to rerank, skipping Jina rerank call")
        finish_node_span(
            runtime,
            span,
            start_time,
            output={"status": "skipped_empty_candidates"},
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

        finish_node_span(
            runtime,
            span,
            start_time,
            output={
                "status": "reranked",
                "candidate_count": len(candidates),
                "result_count": len(reranked),
            },
        )

        return {"retrieved_documents": reranked}

    except Exception as e:
        # No local fallback model for rerank (unlike embeddings) — pass
        # through the original retrieval order rather than failing the graph.
        logger.warning(f"Jina rerank API call failed: {e}, passing through original order")

        finish_node_span(
            runtime,
            span,
            start_time,
            output={"status": "passthrough_on_failure", "error": str(e)},
            metadata={"fallback": True},
            level="WARNING",
        )

        return {"retrieved_documents": candidates}
