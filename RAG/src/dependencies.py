from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, Generator, Optional

if TYPE_CHECKING:
    from fastapi import Depends, Request
    from sqlalchemy.orm import Session
else:
    try:
        from fastapi import Depends, Request
        from sqlalchemy.orm import Session
    except ImportError:
        pass

from src.config import Settings
from src.db.interfaces.base import BaseDatabase
from src.services.cache.client import CacheClient
from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.langfuse.client import LangfuseTracer
from src.services.ollama.client import OllamaClient
from src.services.opensearch.client import OpenSearchClient
from src.services.telegram.bot import TelegramBot
from src.services.agents.agentic_rag import AgenticRAGService


@lru_cache
def get_settings() -> Settings:
    """Get application settings."""
    return Settings()


def get_request_settings(request: Request) -> Settings:
    """Get settings from the request state."""
    return request.app.state.settings


def get_database(request: Request) -> BaseDatabase:
    """Get database from the request state."""
    return request.app.state.database


def get_db_session(database: Annotated[BaseDatabase, Depends(get_database)]) -> Generator[Session, None, None]:
    """Get database session dependency."""
    with database.get_session() as session:
        yield session


def get_opensearch_client(request: Request) -> OpenSearchClient:
    """Get OpenSearch client from the request state."""
    return request.app.state.opensearch_client


def get_embeddings_service(request: Request) -> JinaEmbeddingsClient:
    """Get embeddings service from the request state."""
    return request.app.state.embeddings_service


def get_ollama_client(request: Request) -> OllamaClient:
    """Get Ollama client from the request state."""
    return request.app.state.ollama_client


def get_langfuse_tracer(request: Request) -> LangfuseTracer:
    """Get Langfuse tracer from the request state."""
    return request.app.state.langfuse_tracer


def get_cache_client(request: Request) -> CacheClient | None:
    """Get cache client from the request state."""
    return getattr(request.app.state, "cache_client", None)


def get_telegram_service(request: Request) -> Optional[TelegramBot]:
    """Get Telegram service from the request state."""
    return getattr(request.app.state, "telegram_service", None)


# Dependency annotations
SettingsDep = Annotated[Settings, Depends(get_settings)]
DatabaseDep = Annotated[BaseDatabase, Depends(get_database)]
SessionDep = Annotated[Session, Depends(get_db_session)]
OpenSearchDep = Annotated[OpenSearchClient, Depends(get_opensearch_client)]
EmbeddingsDep = Annotated[JinaEmbeddingsClient, Depends(get_embeddings_service)]
OllamaDep = Annotated[OllamaClient, Depends(get_ollama_client)]
LangfuseDep = Annotated[LangfuseTracer, Depends(get_langfuse_tracer)]
CacheDep = Annotated[CacheClient | None, Depends(get_cache_client)]
TelegramDep = Annotated[Optional[TelegramBot], Depends(get_telegram_service)]


def get_agentic_rag_service(request: Request) -> AgenticRAGService:
    """Get agentic RAG service from request state.

    Built once at app startup (main.py lifespan), not per-request — the
    checkpointer's Postgres connection pool needs to persist across requests,
    and rebuilding the LangGraph workflow on every call was wasted work anyway.
    """
    return request.app.state.agentic_rag_service


AgenticRAGDep = Annotated[AgenticRAGService, Depends(get_agentic_rag_service)]
