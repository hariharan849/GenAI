import asyncio
import logging
import os
import uuid

from api.db.factory import make_database
from api.repositories.nuke_page import NukePageRepository
from api.config import get_settings
from api.services.embeddings.factory import make_embeddings_client
from api.services.indexing.text_chunker import TextChunker
from api.services.opensearch.factory import make_opensearch_client_fresh
from api.search.factory import make_search_client_fresh
from api.search.postgres_embedding import deterministic_chunk_id

logger = logging.getLogger(__name__)

NUKE_INDEX = "nuke-docs-chunks"

NUKE_INDEX_MAPPING = {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "nuke_node_name": {"type": "keyword"},
            "section": {"type": "keyword"},
            "section_title": {"type": "keyword"},
            "url": {"type": "keyword"},
            "chunk_text": {"type": "text", "analyzer": "standard"},
            "chunk_index": {"type": "integer"},
            "embedding": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {"name": "hnsw", "engine": "faiss"},
            },
        }
    },
}


def _doc_id(url: str, chunk_index: int) -> str:
    return deterministic_chunk_id(url, chunk_index)


async def _index_pages(pages: list[dict]) -> tuple[dict, list]:
    """Index pages into OpenSearch. Returns (stats, indexed_page_ids).

    pages: plain dicts with keys id (UUID), url, node_name, section, raw_content.
    indexed_page_ids: UUID objects for pages with no bulk error (may contain duplicates
    for multi-chunk pages — SQL WHERE id IN (...) deduplicates naturally).
    """
    jina_client = make_embeddings_client()
    search_client = make_search_client_fresh()
    search_client.setup_indices(force=False)

    chunker = TextChunker(chunk_size=600, overlap_size=100, min_chunk_size=50)

    all_chunks = []
    all_chunks_meta = []  # parallel list: carries page UUID per chunk, never bulk-indexed
    for page in pages:
        if page.get("sections"):
            text_chunks = chunker.chunk_sections(
                page["sections"], doc_id=page["url"], page_id=page["url"]
            )
        else:
            text_chunks = chunker.chunk_text(
                page["raw_content"], doc_id=page["url"], page_id=page["url"]
            )
        for chunk in text_chunks:
            all_chunks.append({
                "chunk_id": _doc_id(page["url"], chunk.metadata.chunk_index),
                "page_id": page["id"],
                "nuke_node_name": page["node_name"],
                "section": page["section"],
                "section_name": chunk.metadata.section_title,
                "url": page["url"],
                "chunk_text": chunk.text,
                "chunk_index": chunk.metadata.chunk_index,
            })
            all_chunks_meta.append({"id": page["id"]})

    if not all_chunks:
        return {"pages_indexed": 0, "chunks_created": 0, "bulk_errors": 0}, []

    texts = [c["chunk_text"] for c in all_chunks]
    embeddings = []
    for i in range(0, len(texts), 100):
        batch = texts[i: i + 100]
        batch_embeddings = await jina_client.embed_passages(batch)
        embeddings.extend(batch_embeddings)
        logger.info(f"Embedded batch {i // 100 + 1} ({len(batch)} chunks)")

    for chunk, embedding in zip(all_chunks, embeddings):
        chunk["embedding"] = embedding

    resp = search_client.bulk_index_chunks([{"chunk_data": chunk, "embedding": chunk["embedding"]} for chunk in all_chunks])
    errors_count = resp.get("failed", 0)
    if errors_count:
        logger.warning("Bulk index had %d errors", errors_count)

    indexed_ids = [meta["id"] for meta in all_chunks_meta] if errors_count == 0 else []

    stats = {
        "pages_indexed": len(pages),
        "chunks_created": len(all_chunks),
        "bulk_errors": errors_count,
    }
    return stats, indexed_ids


def index_nuke_docs(**context) -> dict:
    """Index unindexed Nuke pages from PostgreSQL into OpenSearch."""
    db = make_database()

    with db.get_session() as session:
        repo = NukePageRepository(session)
        rows = repo.get_unindexed_pages()
        pages_data = [
            {
                "id": r.id,
                "url": r.url,
                "node_name": r.node_name,
                "section": r.section,
                "raw_content": r.raw_content,
                "sections": r.sections,
            }
            for r in rows
        ]

    if not pages_data:
        logger.info("No unindexed pages to process")
        return {"pages_indexed": 0, "chunks_created": 0, "bulk_errors": 0, "indexed_page_ids": []}

    logger.info(f"Indexing {len(pages_data)} unindexed pages into {NUKE_INDEX}")
    stats, indexed_ids = asyncio.run(_index_pages(pages_data))

    with db.get_session() as session:
        repo = NukePageRepository(session)
        repo.mark_indexed(indexed_ids)

    logger.info(f"Marked {len(set(indexed_ids))} pages as indexed")

    stats["indexed_page_ids"] = [str(page_id) for page_id in indexed_ids]

    ti = context.get("ti")
    if ti:
        ti.xcom_push(key="index_stats", value=stats)

    return stats


# ---------------------------------------------------------------------------
# Ray Data pipeline — index_nuke_docs_ray
# ---------------------------------------------------------------------------



def _load_unindexed_pages_from_db() -> list[dict]:
    """Load unindexed Nuke pages from PostgreSQL as plain dicts.

    Creates its own DB session — cannot pass a session from the driver
    process into Ray workers.
    """
    db = make_database()
    with db.get_session() as session:
        repo = NukePageRepository(session)
        rows = repo.get_unindexed_pages()
        return [
            {
                "id": str(r.id),        # UUID → str for Arrow serialization
                "url": r.url,
                "node_name": r.node_name,
                "section": r.section,
                "raw_content": r.raw_content,
                "sections": r.sections,
            }
            for r in rows
        ]


def _chunk_page_remote(row: dict) -> list[dict]:
    """Ray Data flat_map operator: 1 page dict → N chunk dicts."""
    chunker = TextChunker(chunk_size=600, overlap_size=100, min_chunk_size=50)
    if row.get("sections"):
        text_chunks = chunker.chunk_sections(
            row["sections"], doc_id=row["url"], page_id=row["url"]
        )
    else:
        text_chunks = chunker.chunk_text(
            row["raw_content"], doc_id=row["url"], page_id=row["url"]
        )
    return [
        {
            "page_id": row["id"],
            "nuke_node_name": row["node_name"],
            "section": row["section"],
            "section_title": chunk.metadata.section_title or "",
            "url": row["url"],
            "chunk_text": chunk.text,
            "chunk_index": chunk.metadata.chunk_index,
        }
        for chunk in text_chunks
    ]


def _embed_batch_remote(batch: dict) -> dict:
    """Ray Data map_batches operator: add embedding column to a chunk batch.

    Ray Data passes Arrow-backed batches as dict[str, list]. Embeddings must
    be returned as numpy float32 arrays to round-trip cleanly through Arrow.

    The httpx.AsyncClient inside JinaEmbeddingsClient is bound to the event
    loop that runs it. asyncio.run() creates a new loop each call and closes
    it on exit — which tears down the TCP transport. Creating and closing the
    client inside a single asyncio.run() keeps the transport lifecycle
    self-contained and avoids 'handler is closed' errors across batches.
    """
    import numpy as np

    async def _run(texts):
        client = make_embeddings_client()
        try:
            return await client.embed_passages(texts)
        finally:
            await client.close()

    texts = list(batch["chunk_text"])
    embeddings = asyncio.run(_run(texts))
    batch["embedding"] = np.array(embeddings, dtype=np.float32)
    return batch


def _os_bulk_remote(batch: dict) -> dict:
    """Ray Data map_batches operator: bulk index embedded chunks into the configured search backend.

    Returns one row with indexed count and comma-joined page_ids that had errors,
    so the driver can exclude errored pages from mark_indexed.
    """
    settings = get_settings()
    if settings.search.backend == "postgres_embedding":
        search_client = make_search_client_fresh(settings)
        chunks = []
        page_ids = list(batch["page_id"])
        for i, chunk_text in enumerate(batch["chunk_text"]):
            chunk_data = {
                "chunk_id": _doc_id(batch["url"][i], batch["chunk_index"][i]),
                "page_id": page_ids[i],
                "nuke_node_name": batch["nuke_node_name"][i],
                "section": batch["section"][i],
                "section_name": batch["section_title"][i],
                "url": batch["url"][i],
                "chunk_text": chunk_text,
                "chunk_index": batch["chunk_index"][i],
            }
            chunks.append({"chunk_data": chunk_data, "embedding": batch["embedding"][i].tolist()})

        stats = search_client.bulk_index_chunks(chunks)
        failed_page_ids = set(stats.get("failed_page_ids", []))
        if stats.get("failed", 0) and not failed_page_ids:
            failed_page_ids = set(page_ids)
        return {
            "indexed": [stats.get("success", 0)],
            "error_page_ids": [",".join(sorted(failed_page_ids))],
        }

    os_wrapper = make_opensearch_client_fresh()

    urls = list(batch["url"])
    chunk_indexes = list(batch["chunk_index"])
    page_ids = list(batch["page_id"])

    body = []
    for i, chunk_text in enumerate(batch["chunk_text"]):
        body.append({"index": {"_index": NUKE_INDEX, "_id": _doc_id(urls[i], chunk_indexes[i])}})
        body.append({
            "nuke_node_name": batch["nuke_node_name"][i],
            "section": batch["section"][i],
            "section_title": batch["section_title"][i],
            "url": urls[i],
            "chunk_text": chunk_text,
            "chunk_index": chunk_indexes[i],
            "embedding": batch["embedding"][i].tolist(),
        })

    resp = os_wrapper.client.bulk(body=body, refresh=False)

    error_page_ids: set[str] = set()
    ok_count = 0
    for i, item in enumerate(resp["items"]):
        if "error" in item.get("index", {}):
            error_page_ids.add(page_ids[i])
            logger.warning("Bulk error for page %s chunk %s: %s",
                           page_ids[i], chunk_indexes[i], item["index"]["error"])
        else:
            ok_count += 1

    return {
        "indexed": [ok_count],
        "error_page_ids": [",".join(error_page_ids)],
    }


def index_nuke_docs_ray(**context) -> dict:
    """Index unindexed Nuke pages from PostgreSQL into OpenSearch via Ray Data.

    Ray Data pipeline: load pages → flat_map(chunk) → map_batches(embed, concurrency=3)
    → map_batches(bulk_index, concurrency=1).

    Pages with any bulk error stay unindexed in PostgreSQL and are retried on
    the next run. OpenSearch doc IDs are SHA256(url:chunk_index) — re-indexing
    is idempotent.
    """
    import ray

    # Ray local workers are fresh OS processes. They inherit the parent's environment
    # but runtime_env["env_vars"] is applied on top. Explicitly forwarding the full
    # environment ensures JINA_API_KEY and other secrets loaded via docker-compose
    # env_file reach workers, and overrides PYTHONPATH to include the dags directory
    # (Airflow adds this to sys.path at runtime — workers don't get that treatment).
    _dags_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _existing_pythonpath = os.environ.get("PYTHONPATH", "")
    _worker_env = dict(os.environ)
    _worker_env["PYTHONPATH"] = ":".join(filter(None, [_dags_dir, _existing_pythonpath]))

    # Cap object store at 500MB — prevents OOM inside Celery/Prefect/Dagster worker
    # containers where Docker memory limits may be set by the administrator.
    ray.init(
        ignore_reinit_error=True,
        log_to_driver=True,
        object_store_memory=500_000_000,
        runtime_env={"env_vars": _worker_env},
    )

    # Ensure the index exists with the correct knn_vector mapping before bulk indexing.
    # OpenSearch auto-creates indices with dynamic mappings (no HNSW) — vector search
    # silently breaks. This guard runs once in the driver process, not per-worker.
    settings = get_settings()
    if settings.search.backend == "opensearch":
        os_client = make_opensearch_client_fresh(settings)
        if not os_client.client.indices.exists(index=NUKE_INDEX):
            os_client.client.indices.create(index=NUKE_INDEX, body=NUKE_INDEX_MAPPING)
            logger.info("Created index: %s", NUKE_INDEX)
    else:
        make_search_client_fresh(settings).setup_indices(force=False)

    pages_data = _load_unindexed_pages_from_db()
    if not pages_data:
        logger.info("No unindexed pages to process")
        ray.shutdown()
        return {"pages_indexed": 0, "chunks_indexed": 0, "indexed_page_ids": []}

    logger.info("Ray Data pipeline: %d pages → chunk → embed (concurrency=3) → index", len(pages_data))

    try:
        ds = ray.data.from_items(pages_data)
        chunks_ds = ds.flat_map(_chunk_page_remote)
        embedded_ds = chunks_ds.map_batches(_embed_batch_remote, batch_size=100, concurrency=3)
        result_ds = embedded_ds.map_batches(_os_bulk_remote, batch_size=500, concurrency=1)

        # Collect results once — take_all() triggers execution and returns all rows.
        # Using take_all() instead of .sum() so we can also collect error_page_ids
        # without re-executing the pipeline a second time.
        result_rows = result_ds.take_all()
    finally:
        ray.shutdown()

    total_indexed = sum(row["indexed"] for row in result_rows)
    error_page_ids: set[str] = set()
    for row in result_rows:
        raw = row.get("error_page_ids", "") or ""
        if raw:
            error_page_ids.update(raw.split(","))

    # Mark only pages whose chunks all succeeded. Pages with any error stay
    # nuke_pages_indexed=False and will be retried on the next pipeline run.
    success_ids = [
        uuid.UUID(p["id"]) for p in pages_data
        if p["id"] not in error_page_ids
    ]
    db = make_database()
    with db.get_session() as session:
        NukePageRepository(session).mark_indexed(success_ids)

    logger.info(
        "Indexed %d chunks across %d pages (%d pages had errors)",
        total_indexed, len(success_ids), len(error_page_ids),
    )

    stats = {
        "pages_indexed": len(success_ids),
        "chunks_indexed": total_indexed,
        "indexed_page_ids": [str(page_id) for page_id in success_ids],
    }

    ti = context.get("ti")
    if ti:
        ti.xcom_push(key="index_stats", value=stats)

    return stats
