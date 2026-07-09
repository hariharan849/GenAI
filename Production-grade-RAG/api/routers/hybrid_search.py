import logging
import time

from fastapi import APIRouter, HTTPException
from api.dependencies import EmbeddingsDep, SearchDep
from api.metrics import EMBEDDING_LATENCY, SEARCH_LATENCY, SEARCH_RESULTS_COUNT
from api.schemas.api.search import HybridSearchRequest, SearchHit, SearchResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hybrid-search", tags=["hybrid-search"])


@router.post("", response_model=SearchResponse, include_in_schema=False)
@router.post("/", response_model=SearchResponse)
async def hybrid_search(
    request: HybridSearchRequest, search_client: SearchDep, embeddings_service: EmbeddingsDep
) -> SearchResponse:
    """
    Hybrid search endpoint supporting multiple search modes.
    """
    try:
        if not search_client.health_check():
            raise HTTPException(status_code=503, detail="Search service is currently unavailable")

        query_embedding = None
        if request.use_hybrid:
            try:
                _t0 = time.perf_counter()
                query_embedding = await embeddings_service.embed_query(request.query)
                EMBEDDING_LATENCY.labels(operation="embed_query").observe(time.perf_counter() - _t0)
                logger.info("Generated query embedding for hybrid search")
            except Exception as e:
                logger.warning(f"Failed to generate embeddings, falling back to BM25: {e}")
                query_embedding = None

        _search_mode = "hybrid" if (request.use_hybrid and query_embedding is not None) else "bm25"
        logger.info(f"Hybrid search: '{request.query}' (hybrid: {request.use_hybrid and query_embedding is not None})")

        _t0 = time.perf_counter()
        results = search_client.search_unified(
            query=request.query,
            query_embedding=query_embedding,
            size=request.size,
            from_=request.from_,
            categories=request.categories,
            latest=request.latest_papers,
            use_hybrid=request.use_hybrid,
            min_score=request.min_score,
            knowledge_source=request.knowledge_source,
        )
        SEARCH_LATENCY.labels(search_mode=_search_mode).observe(time.perf_counter() - _t0)
        SEARCH_RESULTS_COUNT.labels(search_mode=_search_mode).observe(len(results.get("hits", [])))

        hits = []
        for hit in results.get("hits", []):
            hits.append(
                SearchHit(
                    score=hit.get("score", 0.0),
                    highlights=hit.get("highlights"),
                    chunk_text=hit.get("chunk_text"),
                    chunk_id=hit.get("chunk_id"),
                    section_name=hit.get("section_name"),
                    url=hit.get("url"),
                    nuke_node_name=hit.get("nuke_node_name"),
                    section=hit.get("section"),
                )
            )

        search_response = SearchResponse(
            query=request.query,
            total=results.get("total", 0),
            hits=hits,
            size=request.size,
            **{"from": request.from_},
            search_mode="hybrid" if (request.use_hybrid and query_embedding) else "bm25",
        )

        logger.info(f"Search completed: {search_response.total} results returned")
        return search_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Hybrid search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
