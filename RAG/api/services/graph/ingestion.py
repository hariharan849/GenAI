import asyncio
import logging
import uuid
from typing import Iterable

from api.db.factory import make_database
from api.repositories.nuke_page import NukePageRepository
from api.services.graph.extraction import extract_triples
from api.services.graph.factory import make_neo4j_client

logger = logging.getLogger(__name__)


def _normalize_page_ids(page_ids: Iterable[str | uuid.UUID] | None) -> list[uuid.UUID] | None:
    if page_ids is None:
        return None
    return [page_id if isinstance(page_id, uuid.UUID) else uuid.UUID(str(page_id)) for page_id in page_ids]


async def _extract_kg_for_indexed_pages(page_ids: list[uuid.UUID] | None = None) -> dict:
    client = make_neo4j_client()
    if client is None:
        return {
            "kg_enabled": False,
            "kg_skipped": True,
            "kg_skip_reason": "neo4j_disabled",
            "kg_pages_considered": 0,
            "kg_pages_extracted": 0,
            "kg_pages_failed": 0,
            "kg_triples_written": 0,
        }

    db = make_database()
    with db.get_session() as session:
        repo = NukePageRepository(session)
        pages = repo.get_indexed_pages_pending_kg(page_ids)
        page_payloads = [
            {
                "id": page.id,
                "node_name": page.node_name,
                "section": page.section,
                "raw_content": page.raw_content,
            }
            for page in pages
        ]

    extracted_page_ids: list[uuid.UUID] = []
    failed_pages = 0
    total_triples = 0
    try:
        logger.info("Starting KG extraction for %d indexed page(s)", len(page_payloads))
        for page in page_payloads:
            raw_content = page.get("raw_content") or ""
            node_name = page.get("node_name")
            section = page.get("section")
            try:
                triples = await extract_triples(
                    raw_content,
                    node_name=node_name,
                    section=section,
                    raise_on_provider_error=True,
                )
                written = 0
                if triples:
                    logger.info(
                        "Writing %d KG triple(s) for %s",
                        len(triples),
                        node_name,
                    )
                    written = await client.write_triples(triples)
                    logger.info(
                        "Wrote %d/%d KG triple(s) for %s",
                        written,
                        len(triples),
                        node_name,
                    )
                    if written < len(triples):
                        failed_pages += 1
                        logger.warning(
                            "KG write incomplete for %s: wrote %d of %d triple(s)",
                            node_name,
                            written,
                            len(triples),
                        )
                        continue
                else:
                    logger.info("No KG triples extracted for %s", node_name)
                total_triples += written
                extracted_page_ids.append(page["id"])
            except Exception as exc:
                failed_pages += 1
                logger.warning("KG extraction skipped for %s: %s", node_name, exc)
    finally:
        await client.close()

    if extracted_page_ids:
        with db.get_session() as session:
            NukePageRepository(session).mark_kg_extracted(extracted_page_ids)

    stats = {
        "kg_enabled": True,
        "kg_skipped": False,
        "kg_pages_considered": len(page_payloads),
        "kg_pages_extracted": len(extracted_page_ids),
        "kg_pages_failed": failed_pages,
        "kg_triples_written": total_triples,
    }
    logger.info("KG extraction stats: %s", stats)
    return stats


def extract_kg_for_indexed_pages(page_ids: Iterable[str | uuid.UUID] | None = None) -> dict:
    """Extract KG triples for indexed pages that have not already been processed."""
    page_id_values = None if page_ids is None else list(page_ids)
    try:
        normalized_page_ids = _normalize_page_ids(page_id_values)
        if normalized_page_ids == []:
            return {
                "kg_enabled": True,
                "kg_skipped": False,
                "kg_pages_considered": 0,
                "kg_pages_extracted": 0,
                "kg_pages_failed": 0,
                "kg_triples_written": 0,
            }
        return asyncio.run(_extract_kg_for_indexed_pages(normalized_page_ids))
    except Exception as exc:
        page_count = 0 if page_id_values is None else len(page_id_values)
        logger.warning("KG extraction step failed without blocking ingestion: %s", exc)
        return {
            "kg_enabled": True,
            "kg_skipped": False,
            "kg_error": str(exc),
            "kg_pages_considered": page_count,
            "kg_pages_extracted": 0,
            "kg_pages_failed": page_count,
            "kg_triples_written": 0,
        }
