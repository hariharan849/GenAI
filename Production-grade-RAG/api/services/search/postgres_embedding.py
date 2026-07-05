"""Compatibility shim for the Postgres search backend."""

from api.search.postgres_embedding import PostgresEmbeddingSearchClient, deterministic_chunk_id

__all__ = ["PostgresEmbeddingSearchClient", "deterministic_chunk_id"]
