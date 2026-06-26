import asyncio
import hashlib
import logging

from api.db.factory import make_database
from api.repositories.nuke_page import NukePageRepository
from api.services.embeddings.factory import make_embeddings_client
from api.services.indexing.text_chunker import TextChunker
from api.services.opensearch.factory import make_opensearch_client_fresh

logger = logging.getLogger(__name__)

NUKE_INDEX = "nuke-docs-chunks"

NUKE_INDEX_MAPPING = {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "nuke_node_name": {"type": "keyword"},
            "section": {"type": "keyword"},
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
    return hashlib.sha256(f"{url}:{chunk_index}".encode()).hexdigest()


async def _index_pages(pages: list[dict]) -> tuple[dict, list]:
    """Index pages into OpenSearch. Returns (stats, indexed_page_ids).

    pages: plain dicts with keys id (UUID), url, node_name, section, raw_content.
    indexed_page_ids: UUID objects for pages with no bulk error (may contain duplicates
    for multi-chunk pages — SQL WHERE id IN (...) deduplicates naturally).
    """
    jina_client = make_embeddings_client()
    os_client = make_opensearch_client_fresh()

    if not os_client.client.indices.exists(index=NUKE_INDEX):
        os_client.client.indices.create(index=NUKE_INDEX, body=NUKE_INDEX_MAPPING)
        logger.info(f"Created index: {NUKE_INDEX}")
    else:
        logger.info(f"Index already exists: {NUKE_INDEX}")

    chunker = TextChunker(chunk_size=600, overlap_size=100, min_chunk_size=50)

    all_chunks = []
    all_chunks_meta = []  # parallel list: carries page UUID per chunk, never bulk-indexed
    for page in pages:
        text_chunks = chunker.chunk_text(
            page["raw_content"], doc_id=page["url"], page_id=page["url"]
        )
        for chunk in text_chunks:
            all_chunks.append({
                "_id": _doc_id(page["url"], chunk.metadata.chunk_index),
                "nuke_node_name": page["node_name"],
                "section": page["section"],
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

    body = []
    for chunk in all_chunks:
        doc_id = chunk.pop("_id")
        body.append({"index": {"_index": NUKE_INDEX, "_id": doc_id}})
        body.append(chunk)

    resp = os_client.client.bulk(body=body, refresh=True)
    errors = [item for item in resp["items"] if "error" in item.get("index", {})]
    if errors:
        logger.warning(f"Bulk index had {len(errors)} errors: {errors[:3]}")

    indexed_ids = [
        meta["id"]
        for meta, item in zip(all_chunks_meta, resp["items"])
        if "error" not in item.get("index", {})
    ]

    stats = {
        "pages_indexed": len(pages),
        "chunks_created": len(all_chunks),
        "bulk_errors": len(errors),
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
            }
            for r in rows
        ]

    if not pages_data:
        logger.info("No unindexed pages to process")
        return {"pages_indexed": 0, "chunks_created": 0, "bulk_errors": 0}

    logger.info(f"Indexing {len(pages_data)} unindexed pages into {NUKE_INDEX}")
    stats, indexed_ids = asyncio.run(_index_pages(pages_data))

    with db.get_session() as session:
        repo = NukePageRepository(session)
        repo.mark_indexed(indexed_ids)

    logger.info(f"Marked {len(set(indexed_ids))} pages as indexed")

    ti = context.get("ti")
    if ti:
        ti.xcom_push(key="index_stats", value=stats)

    return stats
