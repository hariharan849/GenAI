from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.documents import Document

from api.services.agents.tools import create_retriever_tool


@pytest.mark.asyncio
async def test_recursive_retriever_tool_calls_search_unified():
    search_client = MagicMock()
    search_client.backend_name = "postgres_embedding"
    search_client.search_unified.return_value = {
        "hits": [
            {
                "chunk_text": "Blur applies a gaussian blur.",
                "url": "https://example.com/blur.html",
                "nuke_node_name": "Blur",
                "section": "filter_nodes",
                "score": 0.7,
            }
        ]
    }
    embeddings_client = MagicMock()
    embeddings_client.embed_query = AsyncMock(return_value=[0.1] * 3)

    tool = create_retriever_tool(search_client, embeddings_client, top_k=1)
    content, docs = await tool.coroutine("blur")

    assert "gaussian blur" in content
    assert docs[0].page_content == "Blur applies a gaussian blur."
    search_client.search_unified.assert_called_once()


@pytest.mark.asyncio
async def test_parent_child_retriever_tool_uses_parent_retriever():
    search_client = MagicMock()
    embeddings_client = MagicMock()
    embeddings_client.embed_query = AsyncMock()
    parent_retriever = MagicMock()
    parent_retriever.ainvoke = AsyncMock(
        return_value=[Document(page_content="Full parent documentation text.", metadata={"url": "https://example.com/blur.html"})]
    )

    tool = create_retriever_tool(
        search_client,
        embeddings_client,
        top_k=1,
        parent_retriever=parent_retriever,
    )
    content, docs = await tool.coroutine("blur")

    assert content == "Full parent documentation text."
    assert docs[0].metadata["search_mode"] == "parent_child"
    parent_retriever.ainvoke.assert_awaited_once_with("blur")
    search_client.search_unified.assert_not_called()
    embeddings_client.embed_query.assert_not_called()
