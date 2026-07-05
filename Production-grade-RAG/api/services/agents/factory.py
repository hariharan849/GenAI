from typing import TYPE_CHECKING, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver

from api.services.embeddings.jina_client import JinaEmbeddingsClient
from api.services.guardrails.policy import GuardrailPolicyService
from api.services.langfuse.client import LangfuseTracer
from api.services.ollama.client import OllamaClient
from api.search.protocol import SearchClient

if TYPE_CHECKING:
    from api.services.graph.client import Neo4jClient

from .agentic_rag import AgenticRAGService
from .config import GraphConfig


def make_agentic_rag_service(
    ollama_client: OllamaClient,
    embeddings_client: JinaEmbeddingsClient,
    search_client: Optional[SearchClient] = None,
    opensearch_client: Optional[SearchClient] = None,
    langfuse_tracer: Optional[LangfuseTracer] = None,
    top_k: int = 3,
    use_hybrid: bool = True,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    graph_client: Optional["Neo4jClient"] = None,
    known_nodes: Optional[frozenset] = None,
    guardrail_policy: Optional[GuardrailPolicyService] = None,
) -> AgenticRAGService:
    """
    Create AgenticRAGService with dependency injection.

    Args:
        search_client: Client for document search
        ollama_client: Client for LLM generation
        embeddings_client: Client for embeddings
        langfuse_tracer: Optional Langfuse tracer for observability
        top_k: Number of documents to retrieve (default: 3)
        use_hybrid: Use hybrid search (default: True)
        checkpointer: Optional LangGraph checkpoint saver for thread-scoped
            conversation memory (caller owns its connection lifecycle)
        graph_client: Optional Neo4j client for KG retrieval (None = disabled)
        known_nodes: frozenset of known Nuke node names for entity matching

    Returns:
        Configured AgenticRAGService instance
    """
    selected_search_client = search_client or opensearch_client
    if selected_search_client is None:
        raise ValueError("A search client is required")

    graph_config = GraphConfig(
        top_k=top_k,
        use_hybrid=use_hybrid,
    )

    return AgenticRAGService(
        opensearch_client=selected_search_client,
        ollama_client=ollama_client,
        embeddings_client=embeddings_client,
        langfuse_tracer=langfuse_tracer,
        graph_config=graph_config,
        checkpointer=checkpointer,
        graph_client=graph_client,
        known_nodes=known_nodes or frozenset(),
        guardrail_policy=guardrail_policy,
    )
