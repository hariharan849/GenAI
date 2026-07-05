from pathlib import Path
from typing import List, Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"


class BaseConfigSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        extra="ignore",
        frozen=True,
        env_nested_delimiter="__",
        case_sensitive=False,
    )


class ChunkingSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="CHUNKING__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    splitter_type: Literal["recursive", "parent_child"] = "recursive"
    chunk_size: int = 600  # Target words per child chunk
    overlap_size: int = 100  # Words to overlap between child chunks
    parent_chunk_size: int = 1800  # Target words per parent chunk
    parent_overlap_size: int = 200  # Words to overlap between parent chunks
    parent_doc_id_key: str = "parent_doc_id"
    min_chunk_size: int = 100  # Minimum words for a valid chunk
    section_based: bool = True  # Use section-based chunking when available


class OpenSearchSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="OPENSEARCH__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    host: str = "http://localhost:9200"
    index_name: str = "nuke-docs"
    chunk_index_suffix: str = "chunks"  # Creates single hybrid index: {index_name}-{suffix}
    max_text_size: int = 1000000

    # Vector search settings
    vector_dimension: int = 1024  # Jina embeddings dimension
    vector_space_type: str = "cosinesimil"  # cosinesimil, l2, innerproduct

    # Hybrid search settings
    rrf_pipeline_name: str = "hybrid-rrf-pipeline"
    hybrid_search_size_multiplier: int = 2  # Get k*multiplier for better recall


class SearchSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="SEARCH__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    backend: Literal["postgres_embedding", "opensearch"] = "postgres_embedding"
    vector_dimension: int = 1024
    hybrid_candidate_multiplier: int = 2
    rrf_constant: int = 60


class LangfuseSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="LANGFUSE__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    public_key: str = ""
    secret_key: str = ""
    host: str = "http://localhost:3000"  # Self-hosted Langfuse URL
    enabled: bool = True
    flush_at: int = 15  # Number of events before flushing
    flush_interval: float = 1.0  # Seconds between flushes
    max_retries: int = 3
    timeout: int = 30
    debug: bool = False


class RedisSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="REDIS__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    decode_responses: bool = True
    socket_timeout: int = 30
    socket_connect_timeout: int = 30

    # Cache settings
    ttl_hours: int = 6  # Cache TTL in hours

    # Semantic cache settings. Disabled by default because it requires Redis Stack
    # / RediSearch vector commands, not plain Redis.
    semantic_cache_enabled: bool = False
    semantic_cache_lookup_enabled: bool = True
    semantic_cache_store_enabled: bool = True
    semantic_cache_ask_enabled: bool = True
    semantic_cache_stream_enabled: bool = True
    semantic_cache_agentic_enabled: bool = False
    semantic_cache_namespace: str = "rag-semantic-cache"
    semantic_cache_scope_version: str = "v1"
    semantic_cache_ttl_hours: int = 6
    semantic_cache_distance_threshold: float = 0.08
    semantic_cache_max_results: int = 1
    semantic_cache_operation_timeout_seconds: float = 0.25



class Neo4jSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="NEO4J__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    host: str = "localhost"
    port: int = 7687
    user: str = "neo4j"
    password: str = "nukedocs123"
    enabled: bool = False

    @property
    def bolt_url(self) -> str:
        return f"bolt://{self.host}:{self.port}"


class EvalSettings(BaseConfigSettings):
    """DeepEval RAG evaluation harness settings.

    The judge LLM is intentionally separate from the production Ollama
    model: a 1B local model is too weak to produce stable DeepEval scores,
    so the harness uses a cloud model (e.g. gpt-4o-mini) as judge only.
    """

    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="EVAL__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    judge_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    regression_threshold: float = 0.05
    golden_dataset_path: str = "api/evaluation/golden_dataset.yaml"
    results_dir: str = "api/evaluation/runs"


class GuardrailsSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="GUARDRAILS__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    enabled: bool = True
    presidio_enabled: bool = True
    presidio_entities: List[str] = [
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "US_SSN",
        "CREDIT_CARD",
        "IP_ADDRESS",
        "PERSON",
        "LOCATION",
    ]
    presidio_score_threshold: float = 0.5
    presidio_allowlist_terms: List[str] = []
    presidio_fail_closed: bool = False

    llama_guard_enabled: bool = True
    llama_guard_model: str = "llama-guard"
    llama_guard_timeout_seconds: float = 10.0
    llama_guard_fail_closed_input: bool = True
    llama_guard_fail_closed_output: bool = True


class Settings(BaseConfigSettings):
    app_version: str = "0.1.0"
    debug: bool = True
    environment: Literal["development", "staging", "production"] = "development"
    service_name: str = "rag-api"

    postgres_database_url: str = "postgresql://rag_user:rag_password@localhost:5432/rag_db"
    postgres_echo_sql: bool = False
    postgres_pool_size: int = 20
    postgres_max_overflow: int = 0
    # Separate, explicitly-sized pool for the LangGraph checkpointer (async psycopg3
    # driver) so it doesn't silently compete unbounded with the sync pool above for
    # Postgres max_connections.
    postgres_checkpointer_pool_size: int = 5

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:1b"
    ollama_timeout: int = 300

    cors_origins: List[str] = ["http://localhost", "http://localhost:3002", "http://localhost:3000"]

    # Jina AI embeddings configuration
    jina_api_key: str = ""

    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    eval: EvalSettings = Field(default_factory=EvalSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    guardrails: GuardrailsSettings = Field(default_factory=GuardrailsSettings)

    @field_validator("postgres_database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not (v.startswith("postgresql://") or v.startswith("postgresql+psycopg2://")):
            raise ValueError("Database URL must start with 'postgresql://' or 'postgresql+psycopg2://'")
        return v

    @property
    def postgres_psycopg_url(self) -> str:
        """psycopg3-compatible URL — strips the SQLAlchemy driver prefix (+psycopg2)
        that libpq cannot parse and that causes AsyncConnectionPool to time out silently."""
        return self.postgres_database_url.replace("postgresql+psycopg2://", "postgresql://")


def get_settings() -> Settings:
    return Settings()
