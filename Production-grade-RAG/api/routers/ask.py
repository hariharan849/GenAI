import json
import logging
import time
from typing import Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from api.dependencies import (
    CacheDep,
    DatabaseDep,
    EmbeddingsDep,
    LangfuseDep,
    OllamaDep,
    SearchDep,
    SemanticCacheDep,
    SessionDep,
    SettingsDep,
)
from api.metrics import (
    CACHE_HITS,
    CACHE_MISSES,
    EMBEDDING_LATENCY,
    LLM_LATENCY,
    SEARCH_LATENCY,
    SEARCH_RESULTS_COUNT,
    SEMANTIC_CACHE_BYPASSES,
    SEMANTIC_CACHE_DISTANCE,
    SEMANTIC_CACHE_HITS,
    SEMANTIC_CACHE_MISSES,
    SEMANTIC_CACHE_STORES,
)
from api.schemas.api.ask import AskRequest, AskResponse
from api.repositories.rag_interaction import record_rag_interaction
from api.services.cache.semantic import SemanticCacheBypass, build_semantic_scope
from api.services.langfuse.tracer import RAGTracer

logger = logging.getLogger(__name__)

# Two separate routers - one for regular ask, one for streaming
ask_router = APIRouter(tags=["ask"])
stream_router = APIRouter(tags=["stream"])


def _extract_sources(hits: list[dict]) -> tuple[list[str], list[str]]:
    sources: set[str] = set()
    for hit in hits:
        url = hit.get("url", "")
        if url:
            sources.add(url)
    return [], list(sources)


async def _prepare_chunks_and_sources(
    request: AskRequest,
    search_client,
    embeddings_service,
    rag_tracer: RAGTracer,
    trace=None,
    query_embedding: list[float] | None = None,
) -> tuple[List[Dict], List[str], List[str], list[float] | None]:
    """Retrieve and prepare chunks for RAG with clean tracing."""

    # Handle embeddings for hybrid search
    if request.use_hybrid and query_embedding is None:
        with rag_tracer.trace_embedding(trace, request.query) as embedding_span:
            try:
                _t0 = time.perf_counter()
                query_embedding = await embeddings_service.embed_query(request.query)
                EMBEDDING_LATENCY.labels(operation="embed_query").observe(time.perf_counter() - _t0)
                logger.info("Generated query embedding for hybrid search")
            except Exception as e:
                logger.warning(f"Failed to generate embeddings, falling back to BM25: {e}")
                if embedding_span:
                    rag_tracer.tracer.update_span(embedding_span, output={"success": False, "error": str(e)})

    # Search with tracing
    _search_mode = "hybrid" if (request.use_hybrid and query_embedding is not None) else "bm25"
    with rag_tracer.trace_search(trace, request.query, request.top_k) as search_span:
        _t0 = time.perf_counter()
        search_results = search_client.search_unified(
            query=request.query,
            query_embedding=query_embedding,
            size=request.top_k,
            from_=0,
            categories=request.categories,
            use_hybrid=request.use_hybrid and query_embedding is not None,
            min_score=0.0,
            knowledge_source=getattr(request, "knowledge_source", "nuke"),
        )
        SEARCH_LATENCY.labels(search_mode=_search_mode).observe(time.perf_counter() - _t0)

        # Extract essential data for LLM
        hits = search_results.get("hits", [])
        chunks = [
            {
                "chunk_text": hit.get("chunk_text", ""),
            }
            for hit in hits
        ]
        _, sources_list = _extract_sources(hits)

        SEARCH_RESULTS_COUNT.labels(search_mode=_search_mode).observe(len(chunks))
        # End search span with essential metadata
        rag_tracer.end_search(search_span, chunks, [], search_results.get("total", 0))

    return chunks, sources_list, [], query_embedding


async def _generate_query_embedding(
    request: AskRequest,
    embeddings_service,
    rag_tracer: RAGTracer,
    trace=None,
) -> list[float] | None:
    with rag_tracer.trace_embedding(trace, request.query) as embedding_span:
        try:
            _t0 = time.perf_counter()
            query_embedding = await embeddings_service.embed_query(request.query)
            EMBEDDING_LATENCY.labels(operation="embed_query").observe(time.perf_counter() - _t0)
            logger.info("Generated query embedding for semantic cache/search")
            return query_embedding
        except Exception as e:
            logger.warning(f"Failed to generate embeddings: {e}")
            if embedding_span:
                rag_tracer.tracer.update_span(embedding_span, output={"success": False, "error": str(e)})
            return None


@ask_router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    search_client: SearchDep,
    embeddings_service: EmbeddingsDep,
    ollama_client: OllamaDep,
    langfuse_tracer: LangfuseDep,
    cache_client: CacheDep,
    semantic_cache_client: SemanticCacheDep,
    settings: SettingsDep,
    db_session: SessionDep,
) -> AskResponse:
    """Clean RAG endpoint with essential tracing and exact match caching."""

    rag_tracer = RAGTracer(langfuse_tracer)
    start_time = time.time()

    with rag_tracer.trace_request("api_user", request.query) as trace:
        try:
            # Check exact cache first
            cached_response = None
            if cache_client:
                try:
                    cached_response = await cache_client.find_cached_response(request)
                    if cached_response:
                        CACHE_HITS.labels(endpoint="/ask").inc()
                        logger.info("Returning cached response for exact query match")
                        record_rag_interaction(db_session, "/ask", request, cached_response.answer)
                        return cached_response
                    else:
                        CACHE_MISSES.labels(endpoint="/ask").inc()
                except Exception as e:
                    logger.warning(f"Cache check failed, proceeding with normal flow: {e}")

            query_embedding = None
            semantic_scope = None
            if semantic_cache_client and semantic_cache_client.endpoint_enabled("/ask"):
                if not semantic_cache_client.available:
                    reason = semantic_cache_client.disabled_reason or "unavailable"
                    SEMANTIC_CACHE_BYPASSES.labels(endpoint="/ask", reason=reason).inc()
                else:
                    semantic_scope = build_semantic_scope(request, "/ask", settings, search_client)
                    query_embedding = await _generate_query_embedding(request, embeddings_service, rag_tracer, trace)
                    if query_embedding is None:
                        SEMANTIC_CACHE_BYPASSES.labels(endpoint="/ask", reason="embedding_failed").inc()
                    else:
                        semantic_result = await semantic_cache_client.find_cached_response(
                            request, "/ask", query_embedding, semantic_scope
                        )
                        if isinstance(semantic_result, SemanticCacheBypass):
                            SEMANTIC_CACHE_BYPASSES.labels(endpoint="/ask", reason=semantic_result.reason).inc()
                        elif semantic_result is not None:
                            SEMANTIC_CACHE_HITS.labels(endpoint="/ask").inc()
                            SEMANTIC_CACHE_DISTANCE.labels(endpoint="/ask").observe(semantic_result.distance)
                            logger.info("Returning cached response for semantic query match")
                            record_rag_interaction(db_session, "/ask", request, semantic_result.response.answer)
                            return semantic_result.response
                        else:
                            SEMANTIC_CACHE_MISSES.labels(endpoint="/ask", reason="not_found").inc()

            # Retrieve chunks
            chunks, sources, _, query_embedding = await _prepare_chunks_and_sources(
                request, search_client, embeddings_service, rag_tracer, trace, query_embedding=query_embedding
            )

            if not chunks:
                response = AskResponse(
                    query=request.query,
                    answer="I couldn't find any relevant information in the papers to answer your question.",
                    sources=[],
                    chunks_used=0,
                    search_mode="bm25" if not request.use_hybrid else "hybrid",
                )
                rag_tracer.end_request(trace, response.answer, time.time() - start_time)
                record_rag_interaction(db_session, "/ask", request, response.answer)
                return response

            # Build prompt
            with rag_tracer.trace_prompt_construction(trace, chunks) as prompt_span:
                from api.services.ollama.prompts import RAGPromptBuilder

                prompt_builder = RAGPromptBuilder()

                try:
                    prompt_data = prompt_builder.create_structured_prompt(request.query, chunks)
                    final_prompt = prompt_data["prompt"]
                except Exception:
                    final_prompt = prompt_builder.create_rag_prompt(request.query, chunks)

                rag_tracer.end_prompt(prompt_span, final_prompt)

            # Generate answer
            with rag_tracer.trace_generation(trace, request.model, final_prompt) as gen_span:
                _t0 = time.perf_counter()
                rag_response = await ollama_client.generate_rag_answer(query=request.query, chunks=chunks, model=request.model)
                LLM_LATENCY.labels(model=request.model, endpoint="/ask").observe(time.perf_counter() - _t0)
                answer = rag_response.get("answer", "Unable to generate answer")
                rag_tracer.end_generation(gen_span, answer, request.model)

            # Prepare response
            response = AskResponse(
                query=request.query,
                answer=answer,
                sources=sources,
                chunks_used=len(chunks),
                search_mode="bm25" if not request.use_hybrid else "hybrid",
            )

            rag_tracer.end_request(trace, answer, time.time() - start_time)

            # Store response in exact match cache
            if cache_client:
                try:
                    await cache_client.store_response(request, response)
                except Exception as e:
                    logger.warning(f"Failed to store response in cache: {e}")

            if semantic_cache_client and semantic_scope and query_embedding is not None:
                store_result = await semantic_cache_client.store_response(
                    request, response, "/ask", query_embedding, semantic_scope
                )
                if isinstance(store_result, SemanticCacheBypass):
                    SEMANTIC_CACHE_STORES.labels(endpoint="/ask", status=f"bypassed_{store_result.reason}").inc()
                else:
                    SEMANTIC_CACHE_STORES.labels(endpoint="/ask", status="stored" if store_result else "failed").inc()

            record_rag_interaction(db_session, "/ask", request, response.answer)
            return response

        except Exception as e:
            logger.error(f"Error processing request: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@stream_router.post("/stream")
async def ask_question_stream(
    request: AskRequest,
    search_client: SearchDep,
    embeddings_service: EmbeddingsDep,
    ollama_client: OllamaDep,
    langfuse_tracer: LangfuseDep,
    cache_client: CacheDep,
    semantic_cache_client: SemanticCacheDep,
    settings: SettingsDep,
    database: DatabaseDep,
) -> StreamingResponse:
    """Clean streaming RAG endpoint."""

    def record_stream_interaction(final_response: str) -> None:
        with database.get_session() as session:
            record_rag_interaction(session, "/stream", request, final_response)

    async def generate_stream():
        rag_tracer = RAGTracer(langfuse_tracer)
        start_time = time.time()

        with rag_tracer.trace_request("api_user", request.query) as trace:
            try:
                # Check exact cache first
                if cache_client:
                    try:
                        cached_response = await cache_client.find_cached_response(request)
                        if cached_response:
                            CACHE_HITS.labels(endpoint="/stream").inc()
                            logger.info("Returning cached response for exact streaming query match")
                            record_stream_interaction(cached_response.answer)

                            # Send metadata first (same format as non-cached)
                            metadata_response = {
                                "sources": cached_response.sources,
                                "chunks_used": cached_response.chunks_used,
                                "search_mode": cached_response.search_mode,
                            }
                            yield f"data: {json.dumps(metadata_response)}\n\n"

                            # Stream the cached response in chunks
                            for chunk in cached_response.answer.split():
                                yield f"data: {json.dumps({'chunk': chunk + ' '})}\n\n"

                            # Send completion signal with just the final answer
                            yield f"data: {json.dumps({'answer': cached_response.answer, 'done': True})}\n\n"
                            return
                        else:
                            CACHE_MISSES.labels(endpoint="/stream").inc()
                    except Exception as e:
                        logger.warning(f"Cache check failed, proceeding with normal flow: {e}")

                query_embedding = None
                semantic_scope = None
                if semantic_cache_client and semantic_cache_client.endpoint_enabled("/stream"):
                    if not semantic_cache_client.available:
                        reason = semantic_cache_client.disabled_reason or "unavailable"
                        SEMANTIC_CACHE_BYPASSES.labels(endpoint="/stream", reason=reason).inc()
                    else:
                        semantic_scope = build_semantic_scope(request, "/stream", settings, search_client)
                        query_embedding = await _generate_query_embedding(request, embeddings_service, rag_tracer, trace)
                        if query_embedding is None:
                            SEMANTIC_CACHE_BYPASSES.labels(endpoint="/stream", reason="embedding_failed").inc()
                        else:
                            semantic_result = await semantic_cache_client.find_cached_response(
                                request, "/stream", query_embedding, semantic_scope
                            )
                            if isinstance(semantic_result, SemanticCacheBypass):
                                SEMANTIC_CACHE_BYPASSES.labels(endpoint="/stream", reason=semantic_result.reason).inc()
                            elif semantic_result is not None:
                                SEMANTIC_CACHE_HITS.labels(endpoint="/stream").inc()
                                SEMANTIC_CACHE_DISTANCE.labels(endpoint="/stream").observe(semantic_result.distance)
                                logger.info("Returning cached response for semantic streaming query match")
                                record_stream_interaction(semantic_result.response.answer)
                                metadata_response = {
                                    "sources": semantic_result.response.sources,
                                    "chunks_used": semantic_result.response.chunks_used,
                                    "search_mode": semantic_result.response.search_mode,
                                }
                                yield f"data: {json.dumps(metadata_response)}\n\n"
                                for chunk in semantic_result.response.answer.split():
                                    yield f"data: {json.dumps({'chunk': chunk + ' '})}\n\n"
                                yield f"data: {json.dumps({'answer': semantic_result.response.answer, 'done': True})}\n\n"
                                return
                            else:
                                SEMANTIC_CACHE_MISSES.labels(endpoint="/stream", reason="not_found").inc()

                # Retrieve chunks
                chunks, sources, _, query_embedding = await _prepare_chunks_and_sources(
                    request, search_client, embeddings_service, rag_tracer, trace, query_embedding=query_embedding
                )

                if not chunks:
                    final_response = "No relevant information found."
                    record_stream_interaction(final_response)
                    yield f"data: {json.dumps({'answer': final_response, 'sources': [], 'done': True})}\n\n"
                    return

                # Send metadata first
                search_mode = "bm25" if not request.use_hybrid else "hybrid"
                metadata_response = {"sources": sources, "chunks_used": len(chunks), "search_mode": search_mode}
                yield f"data: {json.dumps(metadata_response)}\n\n"

                # Build prompt
                with rag_tracer.trace_prompt_construction(trace, chunks) as prompt_span:
                    from api.services.ollama.prompts import RAGPromptBuilder

                    prompt_builder = RAGPromptBuilder()
                    final_prompt = prompt_builder.create_rag_prompt(request.query, chunks)
                    rag_tracer.end_prompt(prompt_span, final_prompt)

                # Stream generation
                with rag_tracer.trace_generation(trace, request.model, final_prompt) as gen_span:
                    full_response = ""
                    async for chunk in ollama_client.generate_rag_answer_stream(
                        query=request.query, chunks=chunks, model=request.model
                    ):
                        if chunk.get("response"):
                            text_chunk = chunk["response"]
                            full_response += text_chunk
                            yield f"data: {json.dumps({'chunk': text_chunk})}\n\n"

                        if chunk.get("done", False):
                            rag_tracer.end_generation(gen_span, full_response, request.model)
                            record_stream_interaction(full_response)
                            yield f"data: {json.dumps({'answer': full_response, 'done': True})}\n\n"
                            break

                rag_tracer.end_request(trace, full_response, time.time() - start_time)

                # Store response in exact match cache
                if cache_client and full_response:
                    try:
                        search_mode = "bm25" if not request.use_hybrid else "hybrid"
                        response_to_cache = AskResponse(
                            query=request.query,
                            answer=full_response,
                            sources=sources,
                            chunks_used=len(chunks),
                            search_mode=search_mode,
                        )
                        await cache_client.store_response(request, response_to_cache)
                    except Exception as e:
                        logger.warning(f"Failed to store streaming response in cache: {e}")

                if semantic_cache_client and semantic_scope and query_embedding is not None and full_response:
                    response_to_cache = AskResponse(
                        query=request.query,
                        answer=full_response,
                        sources=sources,
                        chunks_used=len(chunks),
                        search_mode="bm25" if not request.use_hybrid else "hybrid",
                    )
                    store_result = await semantic_cache_client.store_response(
                        request, response_to_cache, "/stream", query_embedding, semantic_scope
                    )
                    if isinstance(store_result, SemanticCacheBypass):
                        SEMANTIC_CACHE_STORES.labels(endpoint="/stream", status=f"bypassed_{store_result.reason}").inc()
                    else:
                        SEMANTIC_CACHE_STORES.labels(
                            endpoint="/stream", status="stored" if store_result else "failed"
                        ).inc()

            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate_stream(), media_type="text/plain", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
