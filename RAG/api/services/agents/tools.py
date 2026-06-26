import logging

from langchain_core.documents import Document
from langchain_core.tools import tool

from api.services.embeddings.jina_client import JinaEmbeddingsClient
from api.services.opensearch.client import OpenSearchClient

logger = logging.getLogger(__name__)


def create_retriever_tool(
    opensearch_client: OpenSearchClient,
    embeddings_client: JinaEmbeddingsClient,
    top_k: int = 3,
    use_hybrid: bool = True,
):
    """Create a retriever tool that wraps OpenSearch service.

    :param opensearch_client: Existing OpenSearch service
    :param embeddings_client: Existing Jina embeddings service
    :param top_k: Number of chunks to retrieve
    :param use_hybrid: Use hybrid search (BM25 + vector)
    :returns: LangChain tool for retrieving Nuke documentation
    """

    @tool(response_format="content_and_artifact")
    async def retrieve_papers(query: str) -> tuple[str, list[Document]]:
        """Search and return relevant Foundry Nuke documentation.

        Use this tool when the user asks about:
        - Nuke nodes and their parameters
        - Compositing techniques in Nuke
        - Color correction or grading in Nuke
        - VFX workflows and pipeline questions
        - Specific Nuke features or operations

        :param query: The search query describing what documentation to find
        :returns: Tuple of (flattened text content for the LLM, structured
            Document list for downstream nodes that need individual document
            boundaries, e.g. the rerank node). LangChain's ToolNode stores the
            second element on ``ToolMessage.artifact``.
        """
        logger.info(f"Retrieving documentation for query: {query[:100]}...")
        logger.debug(f"Search mode: {'hybrid' if use_hybrid else 'bm25'}, top_k: {top_k}")

        logger.debug("Generating query embedding")
        query_embedding = await embeddings_client.embed_query(query)
        logger.debug(f"Generated embedding with {len(query_embedding)} dimensions")

        logger.debug("Searching OpenSearch")
        search_results = opensearch_client.search_unified(
            query=query,
            query_embedding=query_embedding,
            size=top_k,
            use_hybrid=use_hybrid,
        )

        documents = []
        hits = search_results.get("hits", [])
        logger.info(f"Found {len(hits)} documents from OpenSearch")

        for hit in hits:
            doc = Document(
                page_content=hit["chunk_text"],
                metadata={
                    "url": hit.get("url", ""),
                    "nuke_node_name": hit.get("nuke_node_name", ""),
                    "section": hit.get("section", ""),
                    "score": hit.get("score", 0.0),
                    "search_mode": "hybrid" if use_hybrid else "bm25",
                    "top_k": top_k,
                },
            )
            documents.append(doc)

        logger.debug(f"Converted {len(documents)} hits to LangChain Documents")
        logger.info(f"Retrieved {len(documents)} documentation chunks successfully")

        content = "\n\n".join(doc.page_content for doc in documents)
        return content, documents

    return retrieve_papers
