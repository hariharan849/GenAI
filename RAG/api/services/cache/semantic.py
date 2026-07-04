"""Redis Stack-backed semantic cache for final RAG answers.

The cache is deliberately policy-heavy: Redis only stores and searches entries;
the application owns answer-shaping scope, safety gates, and fallback behavior.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import struct
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Mapping, Optional

import redis

from api.config import Settings
from api.schemas.api.ask import AskRequest, AskResponse
from api.search.protocol import SearchClient

logger = logging.getLogger(__name__)

RESPONSE_SCHEMA_VERSION = "ask-response-v1"
RAG_PROMPT_VERSION = "rag-prompt-v1"
EMBEDDING_MODEL_VERSION = "jina-embeddings-v3-query-1024"


@dataclass(frozen=True)
class SemanticCacheScope:
    """Answer-shaping fields that must match before a cached answer is valid."""

    endpoint: str
    response_schema_version: str
    model: str
    prompt_version: str
    embedding_model_version: str
    embedding_dimension: int
    search_backend: str
    search_index_name: str
    search_config: Mapping[str, Any]
    chunking_config: Mapping[str, Any]
    knowledge_source: str
    categories: tuple[str, ...]
    top_k: int
    use_hybrid: bool
    app_version: str
    semantic_scope_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "response_schema_version": self.response_schema_version,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "embedding_model_version": self.embedding_model_version,
            "embedding_dimension": self.embedding_dimension,
            "search_backend": self.search_backend,
            "search_index_name": self.search_index_name,
            "search_config": dict(self.search_config),
            "chunking_config": dict(self.chunking_config),
            "knowledge_source": self.knowledge_source,
            "categories": list(self.categories),
            "top_k": self.top_k,
            "use_hybrid": self.use_hybrid,
            "app_version": self.app_version,
            "semantic_scope_version": self.semantic_scope_version,
        }

    @property
    def hash(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SemanticCacheLookupResult:
    response: AskResponse
    distance: float
    scope_hash: str


@dataclass(frozen=True)
class SemanticCacheBypass:
    reason: str


def _vector_bytes(embedding: list[float]) -> bytes:
    return struct.pack(f"<{len(embedding)}f", *embedding)


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def build_semantic_scope(
    request: AskRequest,
    endpoint: str,
    settings: Settings,
    search_client: SearchClient,
) -> SemanticCacheScope:
    """Build the cache scope from every field that can shape the final answer."""

    try:
        index_stats = search_client.get_index_stats()
    except Exception as exc:
        logger.warning("Could not read search index stats for semantic cache scope: %s", exc)
        index_stats = {}

    search_index_name = str(index_stats.get("index_name") or getattr(search_client, "index_name", "unknown"))
    search_config = {
        "backend": settings.search.backend,
        "vector_dimension": settings.search.vector_dimension,
        "hybrid_candidate_multiplier": settings.search.hybrid_candidate_multiplier,
        "rrf_constant": settings.search.rrf_constant,
        "opensearch_index_name": settings.opensearch.index_name,
        "opensearch_chunk_index_suffix": settings.opensearch.chunk_index_suffix,
        "opensearch_rrf_pipeline_name": settings.opensearch.rrf_pipeline_name,
    }
    chunking_config = {
        "chunk_size": settings.chunking.chunk_size,
        "overlap_size": settings.chunking.overlap_size,
        "min_chunk_size": settings.chunking.min_chunk_size,
        "section_based": settings.chunking.section_based,
    }

    return SemanticCacheScope(
        endpoint=endpoint,
        response_schema_version=RESPONSE_SCHEMA_VERSION,
        model=request.model,
        prompt_version=RAG_PROMPT_VERSION,
        embedding_model_version=EMBEDDING_MODEL_VERSION,
        embedding_dimension=settings.search.vector_dimension,
        search_backend=getattr(search_client, "backend_name", settings.search.backend),
        search_index_name=search_index_name,
        search_config=search_config,
        chunking_config=chunking_config,
        knowledge_source=getattr(request, "knowledge_source", "nuke"),
        categories=tuple(sorted(request.categories or [])),
        top_k=request.top_k,
        use_hybrid=request.use_hybrid,
        app_version=settings.app_version,
        semantic_scope_version=settings.redis.semantic_cache_scope_version,
    )


class SemanticCacheClient:
    """Final-answer semantic cache using Redis Stack vector search."""

    def __init__(self, redis_client: redis.Redis, settings: Settings):
        self.redis = redis_client
        self.settings = settings
        self.redis_settings = settings.redis
        self.namespace = self.redis_settings.semantic_cache_namespace
        self.index_name = f"{self.namespace}:idx"
        self.key_prefix = f"{self.namespace}:entry:"
        self.ttl = timedelta(hours=self.redis_settings.semantic_cache_ttl_hours)
        self.dimension = settings.search.vector_dimension
        self.distance_threshold = self.redis_settings.semantic_cache_distance_threshold
        self.operation_timeout = self.redis_settings.semantic_cache_operation_timeout_seconds
        self.available = False
        self.disabled_reason = "not_checked"

    def endpoint_enabled(self, endpoint: str) -> bool:
        if endpoint == "/ask":
            return self.redis_settings.semantic_cache_ask_enabled
        if endpoint == "/stream":
            return self.redis_settings.semantic_cache_stream_enabled
        if endpoint == "/ask-agentic":
            return self.redis_settings.semantic_cache_agentic_enabled
        return False

    async def initialize(self) -> bool:
        if not self.redis_settings.semantic_cache_enabled:
            self.disabled_reason = "disabled"
            return False

        try:
            supported = await self._run(self._has_vector_search)
            if not supported:
                self.disabled_reason = "redis_capability_missing"
                logger.warning(
                    "Semantic cache disabled: Redis does not expose RediSearch/vector commands. "
                    "Use Redis Stack or disable REDIS__SEMANTIC_CACHE_ENABLED."
                )
                return False

            await self._run(self._ensure_index)
            self.available = True
            self.disabled_reason = ""
            logger.info("Semantic cache ready (namespace=%s, index=%s)", self.namespace, self.index_name)
            return True
        except Exception as exc:
            self.available = False
            self.disabled_reason = "redis_error"
            logger.warning("Semantic cache disabled after Redis capability/index check failed: %s", exc)
            return False

    async def find_cached_response(
        self,
        request: AskRequest,
        endpoint: str,
        embedding: list[float],
        scope: SemanticCacheScope,
    ) -> SemanticCacheLookupResult | SemanticCacheBypass | None:
        if not self._lookup_allowed(endpoint):
            return SemanticCacheBypass(self.disabled_reason or "lookup_disabled")

        try:
            return await self._run(lambda: self._find_cached_response(request, embedding, scope))
        except asyncio.TimeoutError:
            logger.warning("Semantic cache lookup timed out")
            return SemanticCacheBypass("timeout")
        except Exception as exc:
            logger.warning("Semantic cache lookup failed, falling back to live RAG: %s", exc)
            return SemanticCacheBypass("redis_error")

    async def store_response(
        self,
        request: AskRequest,
        response: AskResponse,
        endpoint: str,
        embedding: list[float],
        scope: SemanticCacheScope,
    ) -> bool | SemanticCacheBypass:
        if not self._store_allowed(endpoint):
            return SemanticCacheBypass(self.disabled_reason or "store_disabled")
        if response.chunks_used <= 0 or not response.sources:
            return SemanticCacheBypass("response_not_cacheable")

        try:
            return await self._run(lambda: self._store_response(request, response, endpoint, embedding, scope))
        except asyncio.TimeoutError:
            logger.warning("Semantic cache store timed out")
            return SemanticCacheBypass("timeout")
        except Exception as exc:
            logger.warning("Semantic cache store failed without failing request: %s", exc)
            return SemanticCacheBypass("redis_error")

    def _lookup_allowed(self, endpoint: str) -> bool:
        if not self.available:
            return False
        return self.redis_settings.semantic_cache_lookup_enabled and self.endpoint_enabled(endpoint)

    def _store_allowed(self, endpoint: str) -> bool:
        if not self.available:
            return False
        return self.redis_settings.semantic_cache_store_enabled and self.endpoint_enabled(endpoint)

    async def _run(self, fn):
        return await asyncio.wait_for(asyncio.to_thread(fn), timeout=self.operation_timeout)

    def _has_vector_search(self) -> bool:
        try:
            self.redis.execute_command("FT._LIST")
            return True
        except Exception:
            return False

    def _ensure_index(self) -> None:
        try:
            indexes = self.redis.execute_command("FT._LIST")
            if isinstance(indexes, list) and self.index_name in {_decode(item) for item in indexes}:
                return
        except Exception:
            pass

        self.redis.execute_command(
            "FT.CREATE",
            self.index_name,
            "ON",
            "HASH",
            "PREFIX",
            "1",
            self.key_prefix,
            "SCHEMA",
            "scope_hash",
            "TAG",
            "endpoint",
            "TAG",
            "query",
            "TEXT",
            "response_json",
            "TEXT",
            "embedding",
            "VECTOR",
            "HNSW",
            "6",
            "TYPE",
            "FLOAT32",
            "DIM",
            str(self.dimension),
            "DISTANCE_METRIC",
            "COSINE",
        )

    def _find_cached_response(
        self,
        request: AskRequest,
        embedding: list[float],
        scope: SemanticCacheScope,
    ) -> SemanticCacheLookupResult | None:
        del request
        result = self.redis.execute_command(
            "FT.SEARCH",
            self.index_name,
            f"(@scope_hash:{{{scope.hash}}})=>[KNN {self.redis_settings.semantic_cache_max_results} @embedding $vec AS distance]",
            "PARAMS",
            "2",
            "vec",
            _vector_bytes(embedding),
            "SORTBY",
            "distance",
            "ASC",
            "RETURN",
            "2",
            "response_json",
            "distance",
            "DIALECT",
            "2",
        )
        parsed = self._parse_search_result(result)
        if parsed is None:
            return None

        response_json, distance = parsed
        if distance > self.distance_threshold:
            return None

        return SemanticCacheLookupResult(
            response=AskResponse(**json.loads(response_json)),
            distance=distance,
            scope_hash=scope.hash,
        )

    def _store_response(
        self,
        request: AskRequest,
        response: AskResponse,
        endpoint: str,
        embedding: list[float],
        scope: SemanticCacheScope,
    ) -> bool:
        payload = {
            "query": request.query,
            "endpoint": endpoint,
            "scope_hash": scope.hash,
            "scope_json": json.dumps(scope.as_dict(), sort_keys=True),
            "response_json": response.model_dump_json(),
            "embedding": _vector_bytes(embedding),
        }
        key_material = f"{scope.hash}:{request.query}:{response.answer}"
        key = f"{self.key_prefix}{hashlib.sha256(key_material.encode('utf-8')).hexdigest()}"
        self.redis.hset(key, mapping=payload)
        return bool(self.redis.expire(key, self.ttl))

    @staticmethod
    def _parse_search_result(result: Any) -> Optional[tuple[str, float]]:
        if not isinstance(result, list) or not result or int(result[0]) == 0 or len(result) < 3:
            return None
        fields = result[2]
        if not isinstance(fields, list):
            return None
        data = {}
        for idx in range(0, len(fields), 2):
            data[_decode(fields[idx])] = fields[idx + 1]
        response_json = data.get("response_json")
        distance = data.get("distance")
        if response_json is None or distance is None:
            return None
        return _decode(response_json), float(_decode(distance))
