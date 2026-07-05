"""Search domain interfaces and backend factories."""

from api.search.factory import make_search_client, make_search_client_fresh
from api.search.postgres_embedding import PostgresEmbeddingSearchClient, deterministic_chunk_id
from api.search.protocol import SearchClient

__all__ = [
    "PostgresEmbeddingSearchClient",
    "SearchClient",
    "deterministic_chunk_id",
    "make_search_client",
    "make_search_client_fresh",
]
