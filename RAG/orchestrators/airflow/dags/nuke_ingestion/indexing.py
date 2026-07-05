import asyncio
import logging
import os
import uuid
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from api.db.factory import make_database
from api.repositories.nuke_page import NukePageRepository
from api.config import get_settings
from api.services.embeddings.factory import make_embeddings_client
from api.services.opensearch.factory import make_opensearch_client_fresh
from api.search.factory import make_search_client_fresh
from api.search.parent_child import (
    PostgresParentDocumentStore,
    make_child_chunk_id,
    make_parent_doc_id,
    make_recursive_splitter,
    split_parent_documents,
)
from api.search.postgres_embedding import deterministic_chunk_id

logger = logging.getLogger(__name__)

NUKE_INDEX = "nuke-docs-chunks"

# Parallelization constants
DEFAULT_NUM_PODS = 4  # Fixed parallelism level for K8s pod distribution
MIN_BATCH_SIZE = 5    # Minimum pages per batch to avoid excessive pod overhead

NUKE_INDEX_MAPPING = {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "nuke_node_name": {"type": "keyword"},
            "section": {"type": "keyword"},
            "section_title": {"type": "keyword"},
            "url": {"type": "keyword"},
            "page_id": {"type": "keyword"},
            "parent_doc_id": {"type": "keyword"},
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


@dataclass(frozen=True)
class _ChunkMetadata:
    chunk_index: int
    start_char: int
    end_char: int
    word_count: int
    overlap_with_previous: int
    overlap_with_next: int
    section_title: str | None = None


@dataclass(frozen=True)
class _TextChunk:
    text: str
    metadata: _ChunkMetadata
    doc_id: str
    page_id: str


def _word_count(text: str) -> int:
    return len(text.split())


def _calculate_batches(pages: list[dict], num_pods: int = DEFAULT_NUM_PODS) -> list[list[dict]]:
    """Distribute pages into roughly equal batches for parallel K8s pod execution.

    Args:
        pages: List of unindexed page dicts (id, url, node_name, section, raw_content, sections)
        num_pods: Number of K8s pods to create (parallelism level)

    Returns:
        List of batches, where each batch is a list of page dicts.
        If pages < num_pods, fewer batches are created.
    """
    if not pages:
        return []

    # If fewer pages than pods, create one batch per page
    actual_pods = min(len(pages), num_pods)
    batch_size = (len(pages) + actual_pods - 1) // actual_pods  # Ceiling division

    batches = []
    for i in range(actual_pods):
        start_idx = i * batch_size
        end_idx = min(start_idx + batch_size, len(pages))
        batches.append(pages[start_idx:end_idx])

    logger.info(
        "Calculated batches: %d pages → %d batches (%.0f pages/batch avg)",
        len(pages), len(batches), len(pages) / len(batches) if batches else 0
    )
    return batches


def _make_langchain_splitter(chunk_size: int = 600, chunk_overlap: int = 100) -> RecursiveCharacterTextSplitter:
    return make_recursive_splitter(chunk_size, chunk_overlap)


def _chunk_text_langchain(
    text: str,
    doc_id: str,
    page_id: str,
    *,
    start_index: int = 0,
    section_title: str | None = None,
) -> list[_TextChunk]:
    if not text or not text.strip():
        logger.warning("Empty text provided for doc %s", doc_id)
        return []

    settings = get_settings()
    splitter = _make_langchain_splitter(settings.chunking.chunk_size, settings.chunking.overlap_size)
    documents = splitter.create_documents([text])
    chunks: list[_TextChunk] = []
    for offset, document in enumerate(documents):
        chunk_text = document.page_content
        if not chunk_text:
            continue

        chunk_index = start_index + len(chunks)
        start_char = int(document.metadata.get("start_index", 0))
        end_char = start_char + len(chunk_text)
        word_count = _word_count(chunk_text)

        chunks.append(
            _TextChunk(
                text=chunk_text,
                metadata=_ChunkMetadata(
                    chunk_index=chunk_index,
                    start_char=start_char,
                    end_char=end_char,
                    word_count=word_count,
                    overlap_with_previous=100 if offset > 0 else 0,
                    overlap_with_next=100 if offset < len(documents) - 1 else 0,
                    section_title=section_title,
                ),
                doc_id=doc_id,
                page_id=page_id,
            )
        )

    logger.info("LangChain chunked doc %s: %d words -> %d chunks", doc_id, _word_count(text), len(chunks))
    return chunks


def _chunk_sections_langchain(sections: list[dict], doc_id: str, page_id: str) -> list[_TextChunk]:
    chunks: list[_TextChunk] = []
    for section in sections:
        section_chunks = _chunk_text_langchain(
            section.get("text", ""),
            doc_id=doc_id,
            page_id=page_id,
            start_index=len(chunks),
            section_title=section.get("title"),
        )
        chunks.extend(section_chunks)
    return chunks


def _chunk_page_langchain(page: dict) -> list[_TextChunk]:
    if page.get("sections"):
        return _chunk_sections_langchain(page["sections"], doc_id=page["url"], page_id=page["url"])
    return _chunk_text_langchain(page["raw_content"], doc_id=page["url"], page_id=page["url"])


def _page_source_documents(page: dict) -> list[Document]:
    base_metadata = {
        "page_id": page["id"],
        "url": page["url"],
        "nuke_node_name": page["node_name"],
        "section": page["section"],
    }
    if page.get("sections"):
        return [
            Document(
                page_content=section.get("text", ""),
                metadata={
                    **base_metadata,
                    "section_name": section.get("title") or "",
                    "section_title": section.get("title") or "",
                },
            )
            for section in page["sections"]
            if section.get("text", "").strip()
        ]
    raw_content = page.get("raw_content", "")
    if not raw_content.strip():
        return []
    return [Document(page_content=raw_content, metadata={**base_metadata, "section_name": "", "section_title": ""})]


def _chunk_page_parent_child(page: dict) -> list[dict]:
    settings = get_settings()
    child_splitter = _make_langchain_splitter(settings.chunking.chunk_size, settings.chunking.overlap_size)
    parent_id_key = settings.chunking.parent_doc_id_key
    rows: list[dict] = []
    parent_index = 0
    child_index = 0

    for source_doc in _page_source_documents(page):
        for parent_doc in split_parent_documents(source_doc, settings):
            parent_doc_id = make_parent_doc_id(page["url"], parent_index)
            parent_metadata = dict(parent_doc.metadata or {})
            parent_metadata[parent_id_key] = parent_doc_id
            parent_doc.metadata = parent_metadata

            for child_doc in child_splitter.split_documents([parent_doc]):
                metadata = dict(child_doc.metadata or {})
                rows.append(
                    {
                        "page_id": page["id"],
                        "parent_doc_id": parent_doc_id,
                        "parent_content": parent_doc.page_content,
                        "parent_metadata": parent_metadata,
                        "nuke_node_name": page["node_name"],
                        "section": page["section"],
                        "section_title": metadata.get("section_title") or metadata.get("section_name") or "",
                        "url": page["url"],
                        "chunk_text": child_doc.page_content,
                        "chunk_index": child_index,
                        "chunk_id": make_child_chunk_id(parent_doc_id, child_index),
                    }
                )
                child_index += 1
            parent_index += 1

    return rows


async def _index_pages(pages: list[dict]) -> tuple[dict, list]:
    """Index pages into OpenSearch. Returns (stats, indexed_page_ids).

    pages: plain dicts with keys id (UUID), url, node_name, section, raw_content.
    indexed_page_ids: UUID objects for pages with no bulk error (may contain duplicates
    for multi-chunk pages — SQL WHERE id IN (...) deduplicates naturally).
    """
    jina_client = make_embeddings_client()
    search_client = make_search_client_fresh()
    search_client.setup_indices(force=False)

    all_chunks = []
    all_chunks_meta = []  # parallel list: carries page UUID per chunk, never bulk-indexed
    settings = get_settings()
    for page in pages:
        if settings.chunking.splitter_type == "parent_child":
            rows = _chunk_page_parent_child(page)
            parent_pairs = {}
            for row in rows:
                parent_pairs[row["parent_doc_id"]] = Document(
                    page_content=row["parent_content"],
                    metadata=dict(row["parent_metadata"]),
                )
                all_chunks.append(
                    {
                        "chunk_id": row["chunk_id"],
                        "page_id": row["page_id"],
                        "parent_doc_id": row["parent_doc_id"],
                        "nuke_node_name": row["nuke_node_name"],
                        "section": row["section"],
                        "section_name": row["section_title"],
                        "url": row["url"],
                        "chunk_text": row["chunk_text"],
                        "chunk_index": row["chunk_index"],
                    }
                )
                all_chunks_meta.append({"id": page["id"]})
            if parent_pairs:
                PostgresParentDocumentStore(settings).mset(list(parent_pairs.items()))
            continue

        text_chunks = _chunk_page_langchain(page)
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



def _load_unindexed_pages_from_db(batch_page_ids: list[str] | None = None) -> list[dict]:
    """Load unindexed Nuke pages from PostgreSQL as plain dicts.

    Creates its own DB session — cannot pass a session from the driver
    process into Ray workers.

    Args:
        batch_page_ids: Optional list of page ID strings to filter. If provided,
                       only pages with IDs in this list are returned. If None,
                       all unindexed pages are returned.
    """
    db = make_database()
    with db.get_session() as session:
        repo = NukePageRepository(session)
        rows = repo.get_unindexed_pages()

        pages = [
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

        # Filter to batch if batch_page_ids provided
        if batch_page_ids:
            batch_set = set(batch_page_ids)
            pages = [p for p in pages if p["id"] in batch_set]
            logger.info("Filtered %d unindexed pages to batch of %d", len([p for r in rows]), len(pages))

        return pages


def _chunk_page_remote(row: dict) -> list[dict]:
    """Ray Data flat_map operator: 1 page dict → N chunk dicts."""
    if get_settings().chunking.splitter_type == "parent_child":
        return _chunk_page_parent_child(row)

    text_chunks = _chunk_page_langchain(row)
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
    if "parent_doc_id" in batch:
        parent_pairs = {}
        for i, parent_doc_id in enumerate(batch["parent_doc_id"]):
            if not parent_doc_id:
                continue
            parent_pairs[str(parent_doc_id)] = Document(
                page_content=batch["parent_content"][i],
                metadata=dict(batch["parent_metadata"][i]),
            )
        if parent_pairs:
            PostgresParentDocumentStore(settings).mset(list(parent_pairs.items()))

    if settings.search.backend == "postgres_embedding":
        search_client = make_search_client_fresh(settings)
        chunks = []
        page_ids = list(batch["page_id"])
        for i, chunk_text in enumerate(batch["chunk_text"]):
            chunk_id = batch["chunk_id"][i] if "chunk_id" in batch else _doc_id(batch["url"][i], batch["chunk_index"][i])
            chunk_data = {
                "chunk_id": chunk_id,
                "page_id": page_ids[i],
                "parent_doc_id": batch["parent_doc_id"][i] if "parent_doc_id" in batch else None,
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
        chunk_id = batch["chunk_id"][i] if "chunk_id" in batch else _doc_id(urls[i], chunk_indexes[i])
        body.append({"index": {"_index": NUKE_INDEX, "_id": chunk_id}})
        body.append({
            "chunk_id": chunk_id,
            "page_id": page_ids[i],
            "parent_doc_id": batch["parent_doc_id"][i] if "parent_doc_id" in batch else None,
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


# ---------------------------------------------------------------------------
# Batch-level indexing for parallel K8s pod execution
# ---------------------------------------------------------------------------


def index_nuke_docs_batch(batch_page_ids: list[str], batch_id: int, **context) -> dict:
    """Index a single batch of Nuke pages via Ray Data pipeline.

    This function is designed to run inside a K8s pod. Each pod processes one batch
    of pages independently. Pages with any indexing error stay unindexed and are
    retried on the next DAG run.

    Args:
        batch_page_ids: List of page ID strings (UUIDs as strings) in this batch
        batch_id: Batch number (0-based) for logging/identification
        context: Airflow task context (optional)

    Returns:
        dict with keys:
            - batch_id: The batch number
            - pages_indexed: Number of pages successfully indexed
            - chunks_indexed: Total chunks indexed
            - error_page_ids: List of page ID strings that had errors
            - indexed_page_ids: List of page ID strings that succeeded
    """
    import ray

    logger.info("Batch %d: Starting indexing of %d pages", batch_id, len(batch_page_ids))

    # Each pod initializes its own Ray cluster
    _dags_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _existing_pythonpath = os.environ.get("PYTHONPATH", "")
    _worker_env = dict(os.environ)
    _worker_env["PYTHONPATH"] = ":".join(filter(None, [_dags_dir, _existing_pythonpath]))

    ray.init(
        ignore_reinit_error=True,
        log_to_driver=True,
        object_store_memory=500_000_000,
        runtime_env={"env_vars": _worker_env},
    )

    try:
        # Load pages for this batch from DB
        pages_data = _load_unindexed_pages_from_db(batch_page_ids=batch_page_ids)
        if not pages_data:
            logger.info("Batch %d: No pages found for batch (all may already be indexed)", batch_id)
            return {
                "batch_id": batch_id,
                "pages_indexed": 0,
                "chunks_indexed": 0,
                "error_page_ids": [],
                "indexed_page_ids": [],
            }

        # Ensure index exists
        settings = get_settings()
        if settings.search.backend == "opensearch":
            os_client = make_opensearch_client_fresh(settings)
            if not os_client.client.indices.exists(index=NUKE_INDEX):
                os_client.client.indices.create(index=NUKE_INDEX, body=NUKE_INDEX_MAPPING)
                logger.info("Batch %d: Created index: %s", batch_id, NUKE_INDEX)
        else:
            make_search_client_fresh(settings).setup_indices(force=False)

        logger.info(
            "Batch %d: Ray Data pipeline: %d pages → chunk → embed (concurrency=3) → index",
            batch_id, len(pages_data)
        )

        # Run Ray Data pipeline for this batch (no global concurrency; K8s provides parallelism)
        ds = ray.data.from_items(pages_data)
        chunks_ds = ds.flat_map(_chunk_page_remote)
        embedded_ds = chunks_ds.map_batches(_embed_batch_remote, batch_size=100, concurrency=3)
        result_ds = embedded_ds.map_batches(_os_bulk_remote, batch_size=500, concurrency=1)

        result_rows = result_ds.take_all()

        total_indexed = sum(row["indexed"] for row in result_rows)
        error_page_ids_set: set[str] = set()
        for row in result_rows:
            raw = row.get("error_page_ids", "") or ""
            if raw:
                error_page_ids_set.update(raw.split(","))

        # Mark successfully indexed pages in DB
        success_ids = [
            uuid.UUID(p["id"]) for p in pages_data
            if p["id"] not in error_page_ids_set
        ]
        db = make_database()
        with db.get_session() as session:
            NukePageRepository(session).mark_indexed(success_ids)

        logger.info(
            "Batch %d: Indexed %d chunks across %d pages (%d pages had errors)",
            batch_id, total_indexed, len(success_ids), len(error_page_ids_set),
        )

        return {
            "batch_id": batch_id,
            "pages_indexed": len(success_ids),
            "chunks_indexed": total_indexed,
            "error_page_ids": list(error_page_ids_set),
            "indexed_page_ids": [str(page_id) for page_id in success_ids],
        }

    finally:
        ray.shutdown()


def index_nuke_docs_dynamic(**context) -> dict:
    """Orchestrate dynamic batch calculation and preparation for parallel K8s pod execution.

    This function:
    1. Loads all unindexed pages from PostgreSQL
    2. Calculates batch distribution (DEFAULT_NUM_PODS batches)
    3. Stores batch information in Airflow XCom for DAG to retrieve
    4. Returns batch orchestration metadata

    Designed to run as the first task in the parallel indexing workflow.

    Returns:
        dict with keys:
            - num_pages: Total unindexed pages found
            - num_batches: Number of K8s pods that will be spawned
            - batches: List of batch metadata, each containing:
                - batch_id: 0-based batch number
                - page_ids: List of page ID strings in this batch
                - page_count: Number of pages in this batch
    """
    logger.info("Dynamic batch orchestration: loading all unindexed pages...")

    # Load all unindexed pages
    db = make_database()
    with db.get_session() as session:
        repo = NukePageRepository(session)
        rows = repo.get_unindexed_pages()
        pages_data = [
            {
                "id": str(r.id),
                "url": r.url,
                "node_name": r.node_name,
                "section": r.section,
                "raw_content": r.raw_content,
                "sections": r.sections,
            }
            for r in rows
        ]

    if not pages_data:
        logger.info("No unindexed pages found for batch orchestration")
        ti = context.get("ti")
        if ti:
            ti.xcom_push(key="batch_metadata", value={
                "num_pages": 0,
                "num_batches": 0,
                "batches": [],
            })
        return {
            "num_pages": 0,
            "num_batches": 0,
            "batches": [],
        }

    # Calculate batches
    page_batches = _calculate_batches(pages_data, num_pods=DEFAULT_NUM_PODS)

    # Prepare batch metadata for XCom
    batch_metadata = []
    for batch_id, batch in enumerate(page_batches):
        batch_page_ids = [p["id"] for p in batch]
        batch_metadata.append({
            "batch_id": batch_id,
            "page_ids": batch_page_ids,
            "page_count": len(batch_page_ids),
        })

    orchestration_result = {
        "num_pages": len(pages_data),
        "num_batches": len(batch_metadata),
        "batches": batch_metadata,
    }

    logger.info(
        "Orchestration complete: %d pages → %d batches for parallel indexing",
        len(pages_data), len(batch_metadata)
    )

    # Push to XCom for downstream tasks to retrieve
    ti = context.get("ti")
    if ti:
        ti.xcom_push(key="batch_metadata", value=orchestration_result)

    return orchestration_result
