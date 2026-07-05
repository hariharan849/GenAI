import json
import logging
import os
from datetime import datetime

from prefect import flow, task, get_run_logger

NUKE_VERSION = "17.0"


@task(
    name="scrape_nuke_docs",
    retries=2,
    retry_delay_seconds=600,  # 10 min — mirrors Airflow retry_delay
    timeout_seconds=1800,     # 30 min — mirrors Airflow execution_timeout
    description="Crawl the Nuke 17.0 reference guide and return scraped pages",
)
def scrape_nuke_docs() -> list[dict]:
    from nuke_ingestion.scraping import scrape_nuke_reference_guide

    logger = get_run_logger()
    logger.info(f"Starting Nuke {NUKE_VERSION} docs scrape")

    # scrape_nuke_reference_guide writes pages to a temp JSON file and returns its path.
    # With no Airflow context (no ti), it skips XCom and returns the result dict.
    result = scrape_nuke_reference_guide()
    file_path = result["file"]

    try:
        with open(file_path) as f:
            pages = json.load(f)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    logger.info(f"Scraped {len(pages)} pages from Nuke {NUKE_VERSION} docs")
    return pages


@task(
    name="save_nuke_pages_to_db",
    retries=2,
    retry_delay_seconds=600,
    timeout_seconds=300,  # 5 min
    description="Upsert scraped Nuke pages to PostgreSQL",
)
def save_nuke_pages_to_db(pages: list[dict]) -> dict:
    from api.db.factory import make_database
    from api.repositories.nuke_page import NukePageRepository

    logger = get_run_logger()

    if not pages:
        logger.info("No pages to save")
        return {"pages_scraped": 0, "pages_saved": 0, "dupes_skipped": 0}

    db = make_database()
    with db.get_session() as session:
        repo = NukePageRepository(session)
        count, skipped_dupes = repo.upsert_pages(pages, nuke_version=NUKE_VERSION)

    logger.info(
        f"Upserted {count} pages (version {NUKE_VERSION}); "
        f"skipped {len(skipped_dupes)} near-duplicates"
    )
    for new_url, canon_url in skipped_dupes:
        logger.info(f"  DEDUP: {new_url} skipped (similar to {canon_url})")

    return {
        "pages_scraped": len(pages),
        "pages_saved": count,
        "dupes_skipped": len(skipped_dupes),
    }


@task(
    name="index_nuke_docs",
    retries=1,
    retry_delay_seconds=600,
    timeout_seconds=1200,  # 20 min
    description="Chunk, embed, and bulk-index unindexed Nuke pages into OpenSearch",
)
def index_nuke_docs(save_stats: dict) -> dict:
    from nuke_ingestion.indexing import index_nuke_docs_ray

    logger = get_run_logger()
    logger.info("Indexing unindexed Nuke pages from PostgreSQL into OpenSearch via Ray Data")

    stats = index_nuke_docs_ray()

    logger.info(
        f"Indexed {stats.get('pages_indexed', 0)} pages, "
        f"{stats.get('chunks_indexed', 0)} chunks"
    )
    return stats


@task(
    name="extract_nuke_kg",
    retries=0,
    timeout_seconds=1200,
    description="Extract Nuke knowledge graph triples for successfully indexed pages",
)
def extract_nuke_kg(index_stats: dict) -> dict:
    from api.services.graph.ingestion import extract_kg_for_indexed_pages

    logger = get_run_logger()
    stats = extract_kg_for_indexed_pages(index_stats.get("indexed_page_ids", []))
    logger.info(f"KG extraction stats: {stats}")
    return stats


@task(
    name="generate_nuke_report",
    description="Log a summary of the Nuke ingestion run",
)
def generate_nuke_report(save_stats: dict, index_stats: dict, kg_stats: dict) -> dict:
    logger = get_run_logger()

    report = {
        "pages_scraped": save_stats.get("pages_scraped", 0),
        "pages_saved": save_stats.get("pages_saved", 0),
        "dupes_skipped": save_stats.get("dupes_skipped", 0),
        "pages_indexed": index_stats.get("pages_indexed", 0),
        "chunks_indexed": index_stats.get("chunks_indexed", 0),
        "kg_pages_extracted": kg_stats.get("kg_pages_extracted", 0),
        "kg_pages_failed": kg_stats.get("kg_pages_failed", 0),
        "kg_triples_written": kg_stats.get("kg_triples_written", 0),
        "kg_skipped": kg_stats.get("kg_skipped", False),
        "completed_at": datetime.now().isoformat(),
    }
    logger.info(f"Nuke ingestion report: {report}")
    return report


@flow(
    name="nuke_docs_ingestion",
    description="Scrape Foundry Nuke 17.0 reference guide and index into OpenSearch for RAG",
    log_prints=True,
)
def nuke_docs_ingestion_flow() -> dict:
    pages = scrape_nuke_docs()
    save_stats = save_nuke_pages_to_db(pages)
    index_stats = index_nuke_docs(save_stats)
    kg_stats = extract_nuke_kg(index_stats)
    report = generate_nuke_report(save_stats, index_stats, kg_stats)
    return report
