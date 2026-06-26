from typing import Dict, List

from pydantic import BaseModel


class JinaEmbeddingRequest(BaseModel):
    """Request model for Jina embeddings API."""

    model: str = "jina-embeddings-v3"
    task: str = "retrieval.passage"  # or "retrieval.query" for queries
    dimensions: int = 1024
    late_chunking: bool = False
    embedding_type: str = "float"
    input: List[str]


class JinaEmbeddingResponse(BaseModel):
    """Response model from Jina embeddings API."""

    model: str
    object: str = "list"
    usage: Dict[str, int]
    data: List[Dict]


class JinaRerankRequest(BaseModel):
    """Request model for Jina rerank API."""

    model: str = "jina-reranker-v2-base-multilingual"
    query: str
    documents: List[str]
    top_n: int


class JinaRerankResultItem(BaseModel):
    """A single reranked result from Jina's rerank API."""

    index: int
    relevance_score: float


class JinaRerankResponse(BaseModel):
    """Response model from Jina rerank API."""

    model: str
    usage: Dict[str, int]
    results: List[JinaRerankResultItem]
