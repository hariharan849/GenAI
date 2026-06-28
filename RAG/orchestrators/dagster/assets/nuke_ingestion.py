import json
import logging
import os
from datetime import datetime

from dagster import AssetExecutionContext, MetadataValue, asset

logger = logging.getLogger(__name__)

NUKE_VERSION = "17.0"


@asset(group_name="nuke_ingestion", description="Scraped Nuke 17.0 reference guide pages")
def scraped_nuke_pages(context: AssetExecutionContext) -> list[dict]:
    from nuke_ingestion.scraping import scrape_nuke_reference_guide

    context.log.info(f"Starting Nuke {NUKE_VERSION} docs scrape")
    # scrape_nuke_reference_guide writes to a temp file and returns its path.
    # With no Airflow context (no ti), it skips XCom and just returns the result dict.
    result = scrape_nuke_reference_guide()
    file_path = result["file"]

    try:
        with open(file_path) as f:
            pages = json.load(f)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    context.log.info(f"Scraped {len(pages)} pages from Nuke {NUKE_VERSION} docs")
    context.add_output_metadata({"pages_scraped": MetadataValue.int(len(pages))})
    return pages


@asset(group_name="nuke_ingestion", description="Nuke pages upserted to PostgreSQL")
def saved_nuke_pages(context: AssetExecutionContext, scraped_nuke_pages: list[dict]) -> dict:
    from api.db.factory import make_database
    from api.repositories.nuke_page import NukePageRepository

    if not scraped_nuke_pages:
        context.log.info("No pages to save")
        return {"pages_scraped": 0, "pages_saved": 0, "dupes_skipped": 0}

    db = make_database()
    with db.get_session() as session:
        repo = NukePageRepository(session)
        count, skipped_dupes = repo.upsert_pages(scraped_nuke_pages, nuke_version=NUKE_VERSION)

    context.log.info(
        f"Upserted {count} pages (version {NUKE_VERSION}); "
        f"skipped {len(skipped_dupes)} near-duplicates"
    )
    for new_url, canon_url in skipped_dupes:
        context.log.info(f"  DEDUP: {new_url} skipped (similar to {canon_url})")

    stats = {
        "pages_scraped": len(scraped_nuke_pages),
        "pages_saved": count,
        "dupes_skipped": len(skipped_dupes),
    }
    context.add_output_metadata({
        "pages_scraped": MetadataValue.int(stats["pages_scraped"]),
        "pages_saved": MetadataValue.int(count),
        "dupes_skipped": MetadataValue.int(len(skipped_dupes)),
    })
    return stats


@asset(group_name="nuke_ingestion", description="Nuke docs chunked, embedded, and indexed into OpenSearch via Ray Data")
def indexed_nuke_docs(context: AssetExecutionContext, saved_nuke_pages: dict) -> dict:
    from nuke_ingestion.indexing import index_nuke_docs_ray

    context.log.info("Indexing unindexed Nuke pages from PostgreSQL into OpenSearch via Ray Data")
    stats = index_nuke_docs_ray()

    context.log.info(
        f"Indexed {stats.get('pages_indexed', 0)} pages, "
        f"{stats.get('chunks_indexed', 0)} chunks"
    )
    context.add_output_metadata({
        "pages_indexed": MetadataValue.int(stats.get("pages_indexed", 0)),
        "chunks_indexed": MetadataValue.int(stats.get("chunks_indexed", 0)),
    })
    return stats


@asset(group_name="nuke_ingestion", description="Summary report of the Nuke ingestion run")
def nuke_ingestion_report(
    context: AssetExecutionContext,
    saved_nuke_pages: dict,
    indexed_nuke_docs: dict,
) -> dict:
    report = {
        "pages_scraped": saved_nuke_pages.get("pages_scraped", 0),
        "pages_saved": saved_nuke_pages.get("pages_saved", 0),
        "dupes_skipped": saved_nuke_pages.get("dupes_skipped", 0),
        "pages_indexed": indexed_nuke_docs.get("pages_indexed", 0),
        "chunks_indexed": indexed_nuke_docs.get("chunks_indexed", 0),
        "completed_at": datetime.now().isoformat(),
    }
    context.log.info(f"Nuke ingestion report: {report}")
    context.add_output_metadata({k: MetadataValue.text(str(v)) for k, v in report.items()})
    return report
