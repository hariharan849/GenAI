from unittest.mock import MagicMock

import pytest

from api.config import RedisSettings, SearchSettings, Settings
from api.schemas.api.ask import AskRequest, AskResponse
from api.services.cache.client import CacheClient
from api.services.cache.semantic import (
    SemanticCacheBypass,
    SemanticCacheClient,
    build_semantic_scope,
)


class _SearchClient:
    backend_name = "postgres_embedding"

    def get_index_stats(self):
        return {"index_name": "nuke_doc_chunks"}


def _settings(**redis_overrides):
    return Settings(
        redis=RedisSettings(**redis_overrides),
        search=SearchSettings(backend="postgres_embedding"),
    )


def test_semantic_scope_changes_with_version_and_sorts_categories():
    request = AskRequest(query="How do I use Blur?", categories=["filter", "blur"])
    settings = _settings(semantic_cache_scope_version="v1")

    scope_a = build_semantic_scope(request, "/ask", settings, _SearchClient())
    scope_b = build_semantic_scope(
        AskRequest(query="How do I use Blur?", categories=["blur", "filter"]),
        "/ask",
        settings,
        _SearchClient(),
    )
    scope_c = build_semantic_scope(
        request,
        "/ask",
        _settings(semantic_cache_scope_version="v2"),
        _SearchClient(),
    )

    assert scope_a.hash == scope_b.hash
    assert scope_a.hash != scope_c.hash
    assert scope_a.as_dict()["categories"] == ["blur", "filter"]
    assert scope_a.as_dict()["search_backend"] == "postgres_embedding"


def test_exact_cache_key_includes_knowledge_source():
    redis_client = MagicMock()
    client = CacheClient(redis_client, RedisSettings())

    nuke_key = client._generate_cache_key(AskRequest(query="Blur node", knowledge_source="nuke"))

    request = AskRequest(query="Blur node", knowledge_source="nuke")
    object.__setattr__(request, "knowledge_source", "other")
    other_key = client._generate_cache_key(request)

    assert nuke_key != other_key


@pytest.mark.asyncio
async def test_semantic_cache_disabled_returns_bypass():
    redis_client = MagicMock()
    client = SemanticCacheClient(redis_client, _settings(semantic_cache_enabled=True))
    scope = build_semantic_scope(AskRequest(query="Blur"), "/ask", client.settings, _SearchClient())

    result = await client.find_cached_response(AskRequest(query="Blur"), "/ask", [0.1] * 1024, scope)

    assert isinstance(result, SemanticCacheBypass)
    assert result.reason == "not_checked"


@pytest.mark.asyncio
async def test_semantic_cache_hit_respects_distance_threshold():
    redis_client = MagicMock()
    settings = _settings(
        semantic_cache_enabled=True,
        semantic_cache_distance_threshold=0.08,
        semantic_cache_operation_timeout_seconds=1.0,
    )
    client = SemanticCacheClient(redis_client, settings)
    client.available = True
    request = AskRequest(query="How do I use Blur?")
    scope = build_semantic_scope(request, "/ask", settings, _SearchClient())
    response = AskResponse(
        query=request.query,
        answer="Use Blur to soften an image.",
        sources=["https://example.com/blur"],
        chunks_used=1,
        search_mode="hybrid",
    )
    redis_client.execute_command.return_value = [
        1,
        "doc-1",
        ["response_json", response.model_dump_json(), "distance", "0.04"],
    ]

    result = await client.find_cached_response(request, "/ask", [0.1] * 1024, scope)

    assert result is not None
    assert result.response.answer == response.answer
    assert result.distance == 0.04


@pytest.mark.asyncio
async def test_semantic_cache_rejects_far_distance():
    redis_client = MagicMock()
    settings = _settings(
        semantic_cache_enabled=True,
        semantic_cache_distance_threshold=0.08,
        semantic_cache_operation_timeout_seconds=1.0,
    )
    client = SemanticCacheClient(redis_client, settings)
    client.available = True
    request = AskRequest(query="How do I use Blur?")
    scope = build_semantic_scope(request, "/ask", settings, _SearchClient())
    response = AskResponse(
        query=request.query,
        answer="Use Blur to soften an image.",
        sources=["https://example.com/blur"],
        chunks_used=1,
        search_mode="hybrid",
    )
    redis_client.execute_command.return_value = [
        1,
        "doc-1",
        ["response_json", response.model_dump_json(), "distance", "0.12"],
    ]

    result = await client.find_cached_response(request, "/ask", [0.1] * 1024, scope)

    assert result is None


def test_semantic_cache_endpoint_flags():
    client = SemanticCacheClient(MagicMock(), _settings(semantic_cache_enabled=True, semantic_cache_agentic_enabled=False))

    assert client.endpoint_enabled("/ask")
    assert client.endpoint_enabled("/stream")
    assert not client.endpoint_enabled("/ask-agentic")
    assert not client.endpoint_enabled("/unknown")
