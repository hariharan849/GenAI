from prometheus_client import Counter, Gauge, Histogram

CACHE_HITS = Counter(
    "rag_cache_hits_total",
    "Total number of exact-match Redis cache hits",
    labelnames=["endpoint"],
)

CACHE_MISSES = Counter(
    "rag_cache_misses_total",
    "Total number of cache misses (query not found in Redis)",
    labelnames=["endpoint"],
)

EMBEDDING_LATENCY = Histogram(
    "rag_embedding_duration_seconds",
    "Time spent calling Jina AI embeddings API",
    labelnames=["operation"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

LLM_LATENCY = Histogram(
    "rag_llm_generation_duration_seconds",
    "Time spent waiting for Ollama LLM response",
    labelnames=["model", "endpoint"],
    buckets=[1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
)

SEARCH_LATENCY = Histogram(
    "rag_search_duration_seconds",
    "Time spent on OpenSearch search_unified() calls",
    labelnames=["search_mode"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

SEARCH_RESULTS_COUNT = Histogram(
    "rag_search_results_returned",
    "Number of search results returned per query",
    labelnames=["search_mode"],
    buckets=[0, 1, 3, 5, 10, 20, 50],
)

AGENTIC_RETRIEVAL_ATTEMPTS = Histogram(
    "rag_agentic_retrieval_attempts",
    "Number of retrieval attempts in agentic RAG loop before final answer",
    buckets=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
)

AGENTIC_REASONING_STEPS = Histogram(
    "rag_agentic_reasoning_steps",
    "Number of graph reasoning steps taken by the LangGraph agent",
    buckets=[1, 2, 3, 4, 5, 7, 10, 15, 20],
)

SERVICE_HEALTH = Gauge(
    "rag_service_health",
    "Health status of downstream services (1=healthy, 0=unhealthy)",
    labelnames=["service"],
)
