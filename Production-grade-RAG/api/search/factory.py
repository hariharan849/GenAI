"""Factory for the configured search backend."""

from typing import Optional

from api.config import Settings, get_settings
from api.search.opensearch import make_opensearch_client, make_opensearch_client_fresh
from api.search.postgres_embedding import PostgresEmbeddingSearchClient
from api.search.protocol import SearchClient


def make_search_client(settings: Optional[Settings] = None, fresh: bool = False) -> SearchClient:
    if settings is None:
        settings = get_settings()

    if settings.search.backend == "opensearch":
        return make_opensearch_client_fresh(settings) if fresh else make_opensearch_client(settings)
    if settings.search.backend == "postgres_embedding":
        return PostgresEmbeddingSearchClient(settings)
    raise ValueError(f"Unsupported search backend: {settings.search.backend}")


def make_search_client_fresh(settings: Optional[Settings] = None, host: Optional[str] = None) -> SearchClient:
    if settings is None:
        settings = get_settings()

    if settings.search.backend == "opensearch":
        return make_opensearch_client_fresh(settings, host=host)
    if settings.search.backend == "postgres_embedding":
        return PostgresEmbeddingSearchClient(settings)
    raise ValueError(f"Unsupported search backend: {settings.search.backend}")
