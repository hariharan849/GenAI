import asyncio
import logging
import time
from typing import List, Optional

import httpx

from src.schemas.embeddings.jina import (
    JinaEmbeddingRequest,
    JinaEmbeddingResponse,
    JinaRerankRequest,
    JinaRerankResponse,
)

logger = logging.getLogger(__name__)

_LOCAL_MODEL_NAME = "BAAI/bge-large-en-v1.5"  # 1024-dim, matches OpenSearch index
_MAX_RETRIES = 5
_RETRY_STATUSES = {429, 503}


class JinaEmbeddingsClient:
    """Client for Jina AI embeddings API with retry, timeout, and local fallback."""

    def __init__(self, api_key: str, base_url: str = "https://api.jina.ai/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(timeout=60.0)
        self._local_model = None  # Loaded lazily on first fallback
        logger.info("Jina embeddings client initialized")

    def _get_local_model(self):
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer
            logger.warning(f"Loading local fallback model {_LOCAL_MODEL_NAME}")
            self._local_model = SentenceTransformer(_LOCAL_MODEL_NAME)
        return self._local_model

    def _embed_local(self, texts: List[str]) -> List[List[float]]:
        model = self._get_local_model()
        vecs = model.encode(texts, normalize_embeddings=True)
        return vecs.tolist()

    async def _post_with_retry(self, payload: dict, endpoint: str = "/embeddings") -> dict:
        """POST to the given Jina API endpoint with exponential backoff on 429/503."""
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = await self.client.post(
                    f"{self.base_url}{endpoint}",
                    headers=self.headers,
                    json=payload,
                )
                if response.status_code in _RETRY_STATUSES:
                    retry_after = float(response.headers.get("Retry-After", 0))
                    wait = retry_after if retry_after > 0 else min(2 ** attempt, 60)
                    logger.warning(
                        f"Jina API {response.status_code} on attempt {attempt + 1}/"
                        f"{_MAX_RETRIES}; retrying in {wait:.1f}s"
                    )
                    await asyncio.sleep(wait)
                    last_exc = httpx.HTTPStatusError(
                        str(response.status_code), request=response.request, response=response
                    )
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as e:
                wait = min(2 ** attempt, 60)
                logger.warning(
                    f"Jina API timeout on attempt {attempt + 1}/{_MAX_RETRIES}; "
                    f"retrying in {wait:.1f}s"
                )
                await asyncio.sleep(wait)
                last_exc = e
            except httpx.HTTPStatusError as e:
                if e.response.status_code not in _RETRY_STATUSES:
                    raise
                last_exc = e
            except httpx.HTTPError as e:
                raise

        raise last_exc

    async def embed_passages(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """Embed text passages for indexing, with local fallback on persistent API failure."""
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            request_data = JinaEmbeddingRequest(
                model="jina-embeddings-v3",
                task="retrieval.passage",
                dimensions=1024,
                input=batch,
            )

            try:
                data = await self._post_with_retry(request_data.model_dump())
                result = JinaEmbeddingResponse(**data)
                batch_embeddings = [item["embedding"] for item in result.data]
                embeddings.extend(batch_embeddings)
                logger.debug(f"Embedded batch of {len(batch)} passages via Jina API")
            except Exception as e:
                logger.error(
                    f"Jina API failed after {_MAX_RETRIES} attempts ({e}); "
                    f"falling back to local model for batch {i // batch_size + 1}"
                )
                local_vecs = await asyncio.to_thread(self._embed_local, batch)
                embeddings.extend(local_vecs)

        logger.info(f"Successfully embedded {len(texts)} passages")
        return embeddings

    async def embed_query(self, query: str) -> List[float]:
        """Embed a search query, with local fallback on persistent API failure."""
        request_data = JinaEmbeddingRequest(
            model="jina-embeddings-v3",
            task="retrieval.query",
            dimensions=1024,
            input=[query],
        )

        try:
            data = await self._post_with_retry(request_data.model_dump())
            result = JinaEmbeddingResponse(**data)
            return result.data[0]["embedding"]
        except Exception as e:
            logger.error(
                f"Jina API failed after {_MAX_RETRIES} attempts ({e}); "
                f"falling back to local model for query"
            )
            vecs = await asyncio.to_thread(self._embed_local, [query])
            return vecs[0]

    async def rerank(self, query: str, documents: List[str], top_n: int) -> JinaRerankResponse:
        """Rerank documents against a query using Jina's cross-encoder reranker API.

        No local fallback model (unlike embed_passages/embed_query) — on
        persistent API failure this raises, and the caller (rerank_node)
        is responsible for passing through the original order unchanged.
        This is a deliberate deviation from the embeddings resilience
        pattern, acceptable at personal-project scale.

        :param query: The search query
        :param documents: Candidate document texts to rerank
        :param top_n: Number of top results to return
        :returns: Jina rerank response with results sorted by relevance_score descending
        :raises: httpx.HTTPError subclasses on persistent API failure
        """
        request_data = JinaRerankRequest(query=query, documents=documents, top_n=top_n)
        data = await self._post_with_retry(request_data.model_dump(), endpoint="/rerank")
        return JinaRerankResponse(**data)

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
