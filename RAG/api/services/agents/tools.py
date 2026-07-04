import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from langchain_core.documents import Document
from langchain_core.tools import tool

from api.services.embeddings.jina_client import JinaEmbeddingsClient
from api.search.protocol import SearchClient

if TYPE_CHECKING:
    from api.services.graph.client import Neo4jClient

logger = logging.getLogger(__name__)


def create_retriever_tool(
    opensearch_client: SearchClient,
    embeddings_client: JinaEmbeddingsClient,
    top_k: int = 3,
    use_hybrid: bool = True,
    graph_client: Optional["Neo4jClient"] = None,
    known_nodes: Optional[frozenset] = None,
):
    """Create a retriever tool combining hybrid search and Neo4j KG.

    :param opensearch_client: Existing search service
    :param embeddings_client: Existing Jina embeddings service
    :param top_k: Number of chunks to retrieve
    :param use_hybrid: Use hybrid search (BM25 + vector)
    :param graph_client: Optional Neo4j client for KG hop (None = disabled)
    :param known_nodes: frozenset of Nuke node names for entity matching
    :returns: LangChain tool for retrieving Nuke documentation
    """
    _known_nodes: frozenset = known_nodes or frozenset()

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

        # Entity detection — sort by length desc so "Merge2" wins over "Merge"
        query_lower = query.lower()
        sorted_nodes = sorted(_known_nodes, key=len, reverse=True)
        entity = next((n for n in sorted_nodes if n.lower() in query_lower), None)
        if entity:
            logger.debug(f"KG entity detected: {entity}")

        loop = asyncio.get_running_loop()

        async def _hybrid() -> list[Document]:
            embedding = await embeddings_client.embed_query(query)
            search_results = await loop.run_in_executor(
                None,
                lambda: opensearch_client.search_unified(
                    query=query,
                    query_embedding=embedding,
                    size=top_k,
                    use_hybrid=use_hybrid,
                ),
            )
            hits = search_results.get("hits", [])
            logger.info("Found %d documents from %s", len(hits), getattr(opensearch_client, "backend_name", "search"))
            return [
                Document(
                    page_content=hit["chunk_text"],
                    metadata={
                        "url": hit.get("url", ""),
                        "nuke_node_name": hit.get("nuke_node_name", ""),
                        "section": hit.get("section", ""),
                        "score": hit.get("score", 0.0),
                        "source": "hybrid",
                        "search_mode": "hybrid" if use_hybrid else "bm25",
                        "top_k": top_k,
                    },
                )
                for hit in hits
            ]

        async def _kg() -> list[Document]:
            if graph_client is None or entity is None:
                return []
            try:
                docs = await graph_client.kg_search(entity)
                logger.info(f"Found {len(docs)} documents from Neo4j KG for entity '{entity}'")
                return docs
            except Exception as e:
                logger.warning(f"KG search failed for entity '{entity}': {e}")
                return []

        hybrid_docs, kg_docs = await asyncio.gather(_hybrid(), _kg())

        # Merge with dedup — compound key avoids false collisions on short KG sentences
        seen: set[tuple] = set()
        merged: list[Document] = []
        for doc in hybrid_docs + kg_docs:
            key = (
                doc.metadata.get("source", ""),
                doc.metadata.get("url", ""),
                doc.page_content[:100],
            )
            if key not in seen:
                seen.add(key)
                merged.append(doc)

        logger.info(f"Retrieved {len(merged)} documents total ({len(hybrid_docs)} hybrid + {len(kg_docs)} KG)")
        content = "\n\n".join(d.page_content for d in merged)
        return content, merged

    return retrieve_papers
